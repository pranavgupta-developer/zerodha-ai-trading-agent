import pytest
from app.trading.order_manager import OrderManager, ManagedOrder, OrderState
from app.broker.kite_adapter import BrokerAdapter
from app.trading.signals import Signal, SignalDirection
from app.agent.schemas import CandidateTrade
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from unittest.mock import MagicMock

def test_order_modification_and_cancellation():
    broker = MagicMock()
    broker.modify_order = MagicMock(return_value="MODIFIED_ID")
    broker.cancel_order = MagicMock(return_value="CANCELLED_ID")
    
    om = OrderManager(broker)
    
    # Mock an existing order
    mo = ManagedOrder(
        idempotency_key="test_key",
        symbol="TCS",
        direction=SignalDirection.BUY,
        qty=10,
        price=100.0,
        state=OrderState.OPEN,
        broker_order_id="BROKER_ORDER_123"
    )
    om._order_cache["test_key"] = mo
    
    # Test Modify
    result_mod = om.modify_order(mo, new_price=105.0)
    assert result_mod.price == 105.0
    broker.modify_order.assert_called_with("BROKER_ORDER_123", price=105.0, quantity=None)
    
    # Test Cancel
    result_can = om.cancel_order(mo)
    assert result_can.state == OrderState.CANCELLED
    broker.cancel_order.assert_called_with("BROKER_ORDER_123")

def test_human_approval_and_second_risk_check():
    broker = MagicMock()
    risk_engine = RiskEngine(RiskConfig(max_order_value=5000, check_market_hours=False))
    om = OrderManager(broker, risk_engine=risk_engine)
    
    account = AccountState(available_margin=100000, open_positions={})
    
    trade = CandidateTrade(
        symbol="RELIANCE", direction=SignalDirection.BUY, qty=10, entry_price=2500, 
        stop_loss=2400, take_target=2600, confidence_score=0.9, reasoning="", 
        approval_required=True
    )
    
    # Should fail due to human approval
    with pytest.raises(ValueError, match="Human approval required"):
        om.execute_trade(trade, account)
        
    # Set approved
    trade.approval_required = False
    
    # Risk check should fail because 10 * 2500 = 25000 > 5000
    with pytest.raises(ValueError, match="Second risk check failed"):
        om.execute_trade(trade, account)
        
    # Reduce qty to pass risk check
    trade.qty = 1
    broker.place_order = MagicMock(return_value="ORDER123")
    order = om.execute_trade(trade, account)
    assert order.state == OrderState.SUBMITTED
    broker.place_order.assert_called_once()
