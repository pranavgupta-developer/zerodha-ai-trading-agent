import pytest
from unittest.mock import Mock, patch
from app.trading.order_manager import OrderManager, OrderState
from app.trading.signals import Signal, SignalDirection
from app.broker.kite_adapter import BrokerAdapter

@pytest.fixture
def mock_broker():
    broker = Mock(spec=BrokerAdapter)
    broker.place_order.return_value = "order_123"
    return broker

@pytest.fixture
def order_manager(mock_broker):
    return OrderManager(broker=mock_broker)

@pytest.fixture
def base_signal():
    return Signal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        confidence=0.9,
        entry_price=100.0,
        stop_loss=90.0,
        take_target=120.0,
        reason="Test"
    )

def test_place_order_success(order_manager, mock_broker, base_signal):
    order = order_manager.place_order(base_signal, 50)
    
    assert order.symbol == "RELIANCE"
    assert order.qty == 50
    assert order.state == OrderState.SUBMITTED
    assert order.broker_order_id == "order_123"
    
    mock_broker.place_order.assert_called_once_with(
        symbol="RELIANCE",
        transaction_type="BUY",
        quantity=50,
        price=100.0
    )

def test_order_idempotency(order_manager, mock_broker, base_signal):
    order1 = order_manager.place_order(base_signal, 50, idempotency_key="trade_A")
    order2 = order_manager.place_order(base_signal, 50, idempotency_key="trade_A")
    
    # Should only call broker once
    mock_broker.place_order.assert_called_once()
    assert order1 is order2 # Exact same object reference returned

def test_transient_error_retry_success(order_manager, mock_broker, base_signal):
    # Fail once with a timeout, then succeed
    mock_broker.place_order.side_effect = [Exception("Connection timeout"), "order_456"]
    
    with patch('time.sleep') as mock_sleep: # Mock sleep to speed up test
        order = order_manager.place_order(base_signal, 50)
        
    assert order.state == OrderState.SUBMITTED
    assert order.broker_order_id == "order_456"
    assert mock_broker.place_order.call_count == 2
    mock_sleep.assert_called_once_with(0.5)

def test_transient_error_max_retries_exceeded(order_manager, mock_broker, base_signal):
    # Fail repeatedly
    mock_broker.place_order.side_effect = Exception("502 Bad Gateway")
    
    with patch('time.sleep'):
        order = order_manager.place_order(base_signal, 50)
        
    assert order.state == OrderState.REJECTED
    assert "502 Bad Gateway" in order.message
    assert mock_broker.place_order.call_count == 3

def test_non_transient_error_no_retry(order_manager, mock_broker, base_signal):
    # Fail with a non-transient error (e.g. invalid auth)
    mock_broker.place_order.side_effect = Exception("Invalid API Key")
    
    with patch('time.sleep') as mock_sleep:
        order = order_manager.place_order(base_signal, 50)
        
    assert order.state == OrderState.REJECTED
    assert "Invalid API Key" in order.message
    assert mock_broker.place_order.call_count == 1
    mock_sleep.assert_not_called()

def test_sync_order_state(order_manager, mock_broker, base_signal):
    order = order_manager.place_order(base_signal, 50)
    assert order.state == OrderState.SUBMITTED
    
    # Mock broker history returning an OPEN state, then a COMPLETE state
    mock_broker.get_order_history.return_value = [{"status": "OPEN", "filled_quantity": 0}]
    order_manager.sync_order_state(order)
    assert order.state == OrderState.OPEN
    
    mock_broker.get_order_history.return_value = [
        {"status": "OPEN", "filled_quantity": 0},
        {"status": "COMPLETE", "filled_quantity": 50, "status_message": "Success"}
    ]
    order_manager.sync_order_state(order)
    assert order.state == OrderState.COMPLETE
    assert order.filled_qty == 50
    assert order.message == "Success"

def test_sync_terminal_state_noop(order_manager, mock_broker, base_signal):
    order = order_manager.place_order(base_signal, 50)
    order.state = OrderState.COMPLETE
    
    order_manager.sync_order_state(order)
    
    # Should not call API if already in terminal state
    mock_broker.get_order_history.assert_not_called()
