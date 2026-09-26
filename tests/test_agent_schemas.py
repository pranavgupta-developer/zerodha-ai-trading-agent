import pytest
from pydantic import ValidationError
from app.agent.schemas import CandidateTrade
from app.trading.signals import SignalDirection

def test_candidate_trade_valid():
    trade = CandidateTrade(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        qty=100,
        entry_price=2500.0,
        stop_loss=2450.0,
        take_target=2600.0,
        confidence_score=0.9,
        reasoning="Strong bullish momentum with RSI not overbought.",
        approval_required=False
    )
    assert trade.symbol == "RELIANCE"
    assert trade.direction == SignalDirection.BUY
    assert trade.confidence_score == 0.9
    assert trade.approval_required is False

def test_candidate_trade_invalid_confidence():
    # Confidence score must be <= 1.0
    with pytest.raises(ValidationError):
        CandidateTrade(
            symbol="RELIANCE",
            direction=SignalDirection.BUY,
            qty=100,
            entry_price=2500.0,
            stop_loss=2450.0,
            take_target=2600.0,
            confidence_score=1.5, # Invalid
            reasoning="Testing invalid confidence",
            approval_required=True
        )

def test_candidate_trade_hold():
    trade = CandidateTrade(
        symbol="HDFC",
        direction=SignalDirection.HOLD,
        qty=0,
        entry_price=0.0,
        stop_loss=0.0,
        take_target=0.0,
        confidence_score=0.2,
        reasoning="Market too volatile",
        approval_required=True
    )
    assert trade.qty == 0
    assert trade.direction == SignalDirection.HOLD
