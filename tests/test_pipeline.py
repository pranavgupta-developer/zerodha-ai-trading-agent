import pytest
from unittest.mock import Mock, patch
from app.trading.pipeline import TradingPipeline
from app.trading.strategy import EmaRsiVwapStrategy
from app.agent.service import AgentService
from app.trading.risk_engine import RiskEngine, AccountState
from app.trading.order_manager import OrderManager, ManagedOrder, OrderState
from app.trading.signals import Signal, SignalDirection
from app.agent.schemas import CandidateTrade

@pytest.fixture
def mock_strategy():
    strategy = Mock(spec=EmaRsiVwapStrategy)
    return strategy

@pytest.fixture
def mock_agent():
    agent = Mock(spec=AgentService)
    return agent

@pytest.fixture
def mock_risk_engine():
    risk = Mock(spec=RiskEngine)
    return risk

@pytest.fixture
def mock_order_manager():
    om = Mock(spec=OrderManager)
    return om

@pytest.fixture
def pipeline(mock_strategy, mock_agent, mock_risk_engine, mock_order_manager):
    return TradingPipeline(
        strategy=mock_strategy,
        agent=mock_agent,
        risk_engine=mock_risk_engine,
        order_manager=mock_order_manager
    )

@pytest.fixture
def base_account():
    return AccountState(
        available_margin=1000000.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        open_positions={},
        orders_placed_today=0,
        orders_placed_last_minute=0
    )

def test_pipeline_strategy_hold(pipeline, mock_strategy, base_account):
    # If strategy generates HOLD, pipeline stops early
    mock_strategy.generate_signal.return_value = Signal(
        symbol="RELIANCE", direction=SignalDirection.HOLD, confidence=0, 
        entry_price=0, stop_loss=0, take_target=0
    )
    
    trade, order, msg = pipeline.process_tick("RELIANCE", [], {}, {}, base_account)
    
    assert trade is None
    assert order is None
    assert "Strategy generated HOLD" in msg
    pipeline.agent.evaluate_trade.assert_not_called()

def test_pipeline_agent_rejects(pipeline, mock_strategy, mock_agent, base_account):
    # Strategy says BUY
    signal = Signal(symbol="RELIANCE", direction=SignalDirection.BUY, confidence=0.8, entry_price=100, stop_loss=90, take_target=120)
    mock_strategy.generate_signal.return_value = signal
    
    # Agent says HOLD
    mock_agent.evaluate_trade.return_value = CandidateTrade(
        symbol="RELIANCE", direction=SignalDirection.HOLD, qty=0, entry_price=100, 
        stop_loss=90, take_target=120, confidence_score=0.1, reasoning="Too risky", approval_required=False
    )
    
    trade, order, msg = pipeline.process_tick("RELIANCE", [], {}, {}, base_account)
    
    assert trade is not None
    assert trade.direction == SignalDirection.HOLD
    assert order is None
    assert "AI Agent rejected trade" in msg
    pipeline.risk_engine.validate_signal.assert_not_called()

def test_pipeline_agent_requires_approval(pipeline, mock_strategy, mock_agent, base_account):
    signal = Signal(symbol="RELIANCE", direction=SignalDirection.BUY, confidence=0.8, entry_price=100, stop_loss=90, take_target=120)
    mock_strategy.generate_signal.return_value = signal
    
    # Agent says BUY but needs approval
    mock_agent.evaluate_trade.return_value = CandidateTrade(
        symbol="RELIANCE", direction=SignalDirection.BUY, qty=10, entry_price=100, 
        stop_loss=90, take_target=120, confidence_score=0.6, reasoning="Maybe?", approval_required=True
    )
    
    trade, order, msg = pipeline.process_tick("RELIANCE", [], {}, {}, base_account)
    
    assert trade is not None
    assert order is None
    assert "requires human approval" in msg
    pipeline.risk_engine.validate_signal.assert_not_called()

def test_pipeline_risk_rejects(pipeline, mock_strategy, mock_agent, mock_risk_engine, base_account):
    signal = Signal(symbol="RELIANCE", direction=SignalDirection.BUY, confidence=0.8, entry_price=100, stop_loss=90, take_target=120)
    mock_strategy.generate_signal.return_value = signal
    
    mock_agent.evaluate_trade.return_value = CandidateTrade(
        symbol="RELIANCE", direction=SignalDirection.BUY, qty=10, entry_price=100, 
        stop_loss=90, take_target=120, confidence_score=0.9, reasoning="Yes!", approval_required=False
    )
    
    # Risk engine says False
    mock_risk_engine.validate_signal.return_value = (False, "Insufficient Margin")
    
    trade, order, msg = pipeline.process_tick("RELIANCE", [], {}, {}, base_account)
    
    assert trade is not None
    assert order is None
    assert "Risk Engine rejected trade: Insufficient Margin" in msg
    pipeline.order_manager.place_order.assert_not_called()

def test_pipeline_full_execution(pipeline, mock_strategy, mock_agent, mock_risk_engine, mock_order_manager, base_account):
    signal = Signal(symbol="RELIANCE", direction=SignalDirection.BUY, confidence=0.8, entry_price=100, stop_loss=90, take_target=120)
    mock_strategy.generate_signal.return_value = signal
    
    mock_agent.evaluate_trade.return_value = CandidateTrade(
        symbol="RELIANCE", direction=SignalDirection.BUY, qty=10, entry_price=100, 
        stop_loss=90, take_target=120, confidence_score=0.9, reasoning="Yes!", approval_required=False
    )
    
    mock_risk_engine.validate_signal.return_value = (True, "Approved")
    
    managed_order = ManagedOrder(
        idempotency_key="key123", symbol="RELIANCE", direction=SignalDirection.BUY, 
        qty=10, price=100, state=OrderState.SUBMITTED
    )
    mock_order_manager.place_order.return_value = managed_order
    
    trade, order, msg = pipeline.process_tick("RELIANCE", [], {}, {}, base_account)
    
    assert trade is not None
    assert order is not None
    assert order.state == OrderState.SUBMITTED
    assert "Order placed successfully" in msg
    
    mock_order_manager.place_order.assert_called_once()
