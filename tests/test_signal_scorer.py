import pytest
from app.trading.signals import Signal, SignalDirection
from app.trading.signal_scorer import SignalQualityScorer, SignalScore

@pytest.fixture
def scorer():
    return SignalQualityScorer(min_quality_threshold=60.0)

def test_scorer_hold_signal(scorer):
    sig = Signal(
        symbol="RELIANCE",
        direction=SignalDirection.HOLD,
        confidence=0.0,
        entry_price=2500.0,
        stop_loss=0.0,
        take_target=0.0
    )
    res = scorer.calculate_score(sig)
    assert res.total_score == 0.0
    assert res.is_high_quality is False
    assert "Signal is HOLD" in res.rationale

def test_scorer_high_quality_bullish(scorer):
    sig = Signal(
        symbol="TCS",
        direction=SignalDirection.BUY,
        confidence=0.9,
        entry_price=3500.0,
        stop_loss=3460.0,
        take_target=3600.0,
        market_regime="BULLISH_TREND",
        mtf_confirmed=True,
        expected_return_pct=2.85
    )
    indicators = {
        "rsi_14": 58.0,
        "ema_9": 3510.0,
        "ema_21": 3480.0
    }
    
    class MockCandle:
        def __init__(self, vol):
            self.volume = vol
            self.close = 3500.0
            
    candles = [MockCandle(1000) for _ in range(19)] + [MockCandle(2500)] # high volume breakout
    
    res = scorer.calculate_score(sig, indicators=indicators, candles=candles)
    assert res.total_score >= 70.0
    assert res.is_high_quality is True
    assert res.breakdown["regime"] == 15.0
    assert res.breakdown["trend"] >= 20.0

def test_scorer_low_quality_counter_trend(scorer):
    sig = Signal(
        symbol="INFY",
        direction=SignalDirection.BUY,
        confidence=0.55,
        entry_price=1500.0,
        stop_loss=1490.0,
        take_target=1505.0,
        market_regime="HIGH_VOLATILITY",
        mtf_confirmed=False,
        expected_return_pct=0.33
    )
    indicators = {
        "rsi_14": 78.0, # overbought
        "ema_9": 1500.0,
        "ema_21": 1500.0
    }
    res = scorer.calculate_score(sig, indicators=indicators)
    assert res.total_score < 60.0
    assert res.is_high_quality is False
    assert "REJECTED" in res.rationale
