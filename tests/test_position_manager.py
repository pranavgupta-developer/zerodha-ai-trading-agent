import pytest
from unittest.mock import MagicMock
from app.trading.signals import SignalDirection
from app.trading.position_manager import (
    PositionManager,
    TrackedPosition,
    ExitReason,
    ExitEvent
)

def test_register_and_get_position():
    pm = PositionManager()
    pos = pm.register_position(
        symbol="TATASTEEL",
        direction=SignalDirection.BUY,
        quantity=10,
        entry_price=150.0,
        stop_loss=147.0,
        take_target=157.5,
    )
    assert pos is not None
    assert pos.symbol == "TATASTEEL"
    assert pos.quantity == 10
    assert pos.stop_loss == 147.0
    assert pos.take_target == 157.5
    assert pos.is_active is True

    retrieved = pm.get_tracked_position("TATASTEEL")
    assert retrieved == pos

def test_long_stop_loss_trigger():
    mock_broker = MagicMock()
    mock_broker.place_order.return_value = "order_sl_123"
    pm = PositionManager(broker=mock_broker)

    pm.register_position(
        symbol="INFY",
        direction=SignalDirection.BUY,
        quantity=5,
        entry_price=1500.0,
        stop_loss=1470.0,
        take_target=1575.0,
    )

    # Price holds safe
    assert pm.evaluate_price("INFY", 1490.0) is None

    # Price hits stop loss
    event = pm.check_and_execute_exit("INFY", 1469.0)
    assert event is not None
    assert event.reason == ExitReason.STOP_LOSS
    assert event.symbol == "INFY"
    assert event.pnl < 0
    assert event.broker_order_id == "order_sl_123"
    mock_broker.place_order.assert_called_once_with(
        symbol="INFY",
        transaction_type="SELL",
        quantity=5,
        price=0.0,
        order_type="MARKET",
        product="MIS"
    )

    # Position is now closed
    assert pm.get_tracked_position("INFY") is None

def test_long_take_profit_trigger():
    mock_broker = MagicMock()
    mock_broker.place_order.return_value = "order_tp_123"
    pm = PositionManager(broker=mock_broker)

    pm.register_position(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        quantity=2,
        entry_price=2500.0,
        stop_loss=2450.0,
        take_target=2600.0,
    )

    # Price hits target
    event = pm.check_and_execute_exit("RELIANCE", 2605.0)
    assert event is not None
    assert event.reason == ExitReason.TAKE_PROFIT
    assert event.pnl > 0
    assert event.broker_order_id == "order_tp_123"
    mock_broker.place_order.assert_called_once_with(
        symbol="RELIANCE",
        transaction_type="SELL",
        quantity=2,
        price=0.0,
        order_type="MARKET",
        product="MIS"
    )

def test_short_stop_loss_and_take_profit():
    mock_broker = MagicMock()
    mock_broker.place_order.return_value = "order_short_123"
    pm = PositionManager(broker=mock_broker)

    # Short position
    pm.register_position(
        symbol="SBIN",
        direction=SignalDirection.SELL,
        quantity=10,
        entry_price=800.0,
        stop_loss=816.0,  # +2% SL
        take_target=760.0, # -5% TP
    )

    # Price falls -> in profit, not exit
    assert pm.evaluate_price("SBIN", 780.0) is None

    # Price reaches target 760.0
    event = pm.check_and_execute_exit("SBIN", 755.0)
    assert event is not None
    assert event.reason == ExitReason.TAKE_PROFIT
    assert event.pnl > 0
    mock_broker.place_order.assert_called_once_with(
        symbol="SBIN",
        transaction_type="BUY",
        quantity=10,
        price=0.0,
        order_type="MARKET",
        product="MIS"
    )

def test_trailing_stop_loss():
    pm = PositionManager()
    pos = pm.register_position(
        symbol="TCS",
        direction=SignalDirection.BUY,
        quantity=1,
        entry_price=3000.0,
        stop_loss=2940.0,   # Initial SL -2%
        take_target=3300.0,
        trailing_sl_pct=0.02 # Trail 2% below highest
    )

    # Price moves up to 3200
    pm.evaluate_price("TCS", 3200.0)
    # Trailing SL should be 3200 * 0.98 = 3136
    assert pos.stop_loss == 3136.0

    # Price moves higher to 3300 without triggering take profit (say TP is 3500)
    pos.take_target = 3500.0
    pm.evaluate_price("TCS", 3300.0)
    assert pos.stop_loss == round(3300.0 * 0.98, 2) # 3234

    # Price pulls back to 3230 (below trailing SL of 3234)
    event = pm.evaluate_price("TCS", 3230.0)
    assert event is not None
    assert event.reason == ExitReason.TRAILING_STOP
    assert event.pnl > 0  # Still in profit!

def test_manual_square_off():
    mock_broker = MagicMock()
    mock_broker.place_order.return_value = "manual_order_999"
    pm = PositionManager(broker=mock_broker)

    pm.register_position(
        symbol="WIPRO",
        direction=SignalDirection.BUY,
        quantity=4,
        entry_price=400.0,
        stop_loss=390.0,
        take_target=420.0
    )

    event = pm.manual_square_off("WIPRO", current_price=410.0)
    assert event is not None
    assert event.reason == ExitReason.MANUAL_SQUARE_OFF
    assert event.broker_order_id == "manual_order_999"
    assert event.pnl == (410.0 - 400.0) * 4
    assert pm.get_tracked_position("WIPRO") is None

def test_sync_with_broker_positions():
    pm = PositionManager()
    broker_positions = [
        {"tradingsymbol": "HDFCBANK.NS", "quantity": 10, "average_price": 1600.0},
        {"tradingsymbol": "ICICIBANK", "quantity": 5, "average_price": 1000.0},
    ]

    pm.sync_with_broker_positions(broker_positions)
    tracked = pm.get_all_tracked()
    assert "HDFCBANK" in tracked
    assert "ICICIBANK" in tracked
    assert tracked["HDFCBANK"].stop_loss == 1600.0 * 0.98
    assert tracked["ICICIBANK"].take_target == 1000.0 * 1.05
