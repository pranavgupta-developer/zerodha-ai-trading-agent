import pytest
import os
from unittest.mock import MagicMock
from app.agent.service import AgentService
from app.trading.signals import Signal, SignalDirection, Prediction
from app.trading.risk_engine import AccountState
from app.agent.schemas import CandidateTrade

from dotenv import load_dotenv
load_dotenv()

@pytest.fixture
def mock_agent():
    # If GEMINI_API_KEY is available, this will run a real test.
    # Otherwise, we can mock it, but testing the real LLM output is better for integration.
    agent = AgentService()
    return agent

def test_ai_agent_evaluate_hold(mock_agent):
    sig = Signal(symbol="RELIANCE", direction=SignalDirection.HOLD, entry_price=2500, stop_loss=0, take_target=0, timestamp="2023", reason="None", confidence=0.0)
    account = AccountState(available_margin=100000, open_positions={})
    
    trade = mock_agent.evaluate_trade(
        signal=sig,
        market_snapshot={"price": 2500, "volume": 100000},
        indicators={"rsi": 50},
        account_state=account,
        ml_prediction={"direction": "HOLD", "confidence": 0.5},
        quant_metrics={"volatility": 0.01}
    )
    
    assert trade.direction == SignalDirection.HOLD
    assert trade.qty == 0

def test_ai_agent_evaluate_buy(mock_agent):
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")
        
    sig = Signal(symbol="TCS", direction=SignalDirection.BUY, entry_price=3500, stop_loss=3450, take_target=3600, timestamp="2023", reason="Bullish cross", confidence=0.8)
    account = AccountState(available_margin=100000, open_positions={})
    
    trade = mock_agent.evaluate_trade(
        signal=sig,
        market_snapshot={"price": 3500, "volume": 2500000},
        indicators={"rsi": 45, "vwap": 3480},
        account_state=account,
        ml_prediction={"direction": "UP", "confidence": 0.88},
        quant_metrics={"volatility": 0.015, "sharpe": 1.2}
    )
    
    assert isinstance(trade, CandidateTrade)
    assert trade.symbol == "TCS"
    assert trade.direction in [SignalDirection.BUY, SignalDirection.HOLD, SignalDirection.SELL]
    # AI might decide to HOLD if it thinks 0.88 is not enough, but it should output a valid schema!
    assert trade.confidence_score >= 0.0 and trade.confidence_score <= 1.0
    assert hasattr(trade, 'reasoning')
    assert isinstance(trade.reasoning, str)
