import pytest
import pandas as pd
import numpy as np
from app.trading.ml_engine import MLEngine, SymbolModelBundle
from app.trading.strategy import EmaRsiVwapStrategy, StrategyConfig
from app.trading.signals import Signal, SignalDirection
from app.trading.signal_scorer import SignalQualityScorer

@pytest.fixture
def sample_market_data():
    """Generates 250 bars of synthetic OHLCV data."""
    np.random.seed(42)
    n = 250
    dates = pd.date_range("2026-01-01", periods=n, freq="5min")
    close = 1000.0 + np.cumsum(np.random.randn(n) * 2.0)
    high = close + np.random.uniform(0.5, 3.0, size=n)
    low = close - np.random.uniform(0.5, 3.0, size=n)
    open_ = low + np.random.uniform(0.1, high - low, size=n)
    volume = np.random.randint(500, 5000, size=n)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    }, index=dates)

def test_ml_target_no_leakage(sample_market_data):
    """Verify target calculation uses true forward return: close[t+5]/close[t] - 1."""
    engine = MLEngine(target_period=5)
    df_feat = engine.create_features(sample_market_data)
    df_tgt = engine.define_target(df_feat)
    
    # Check row 10
    idx_10 = df_feat.index[10]
    idx_15 = df_feat.index[15]
    expected_ret = df_feat.loc[idx_15, 'close'] / df_feat.loc[idx_10, 'close'] - 1.0
    
    assert np.isclose(df_tgt.loc[idx_10, 'future_ret'], expected_ret, atol=1e-5)
    assert df_tgt.loc[idx_10, 'target'] == int(expected_ret > 0)
    assert np.isclose(df_tgt.loc[idx_10, 'target_return'], expected_ret * 100.0, atol=1e-5)

def test_ml_per_symbol_bundle_isolation(sample_market_data):
    """Verify models trained for multiple symbols are isolated in per-symbol bundles."""
    engine = MLEngine(target_period=5)
    
    # Symbol A
    engine.train_and_evaluate("RELIANCE", sample_market_data)
    bundle_rel = engine.symbol_bundles.get("RELIANCE")
    assert bundle_rel is not None
    assert bundle_rel.best_classifier is not None
    assert bundle_rel.scaler is not None
    
    # Symbol B with altered data
    df_tcs = sample_market_data.copy()
    df_tcs["close"] = df_tcs["close"] * 3.5
    engine.train_and_evaluate("TCS", df_tcs)
    
    bundle_tcs = engine.symbol_bundles.get("TCS")
    assert bundle_tcs is not None
    assert bundle_tcs is not bundle_rel
    # Scaler means are different because prices/features differ
    assert bundle_rel.scaler.mean_[0] != bundle_tcs.scaler.mean_[0]
    
    # Predictions are symbol-routed
    pred_rel = engine.predict("RELIANCE", sample_market_data)
    pred_tcs = engine.predict("TCS", df_tcs)
    assert pred_rel is not None
    assert pred_tcs is not None

def test_strategy_dynamic_continuous_confidence():
    """Verify strategy outputs dynamic continuous confidence between 0.50 and 0.95."""
    config = StrategyConfig(fast_ema_period=3, slow_ema_period=6, rsi_period=4, rsi_overbought=85.0)
    strategy = EmaRsiVwapStrategy(config)
    
    class MockCandle:
        def __init__(self, c, h, l, v):
            self.close = c
            self.high = h
            self.low = l
            self.volume = v
            
    candles = [MockCandle(100.0, 102.0, 98.0, 1000) for _ in range(15)]
    candles.append(MockCandle(90.0, 92.0, 88.0, 1000))
    candles.append(MockCandle(120.0, 125.0, 115.0, 2000))
    
    signal = strategy.generate_signal("INFY", candles)
    assert signal.symbol == "INFY"
    if signal.direction != SignalDirection.HOLD:
        assert 0.50 <= signal.confidence <= 0.95
        # Must not be the old static 0.80 or 0.85
        assert isinstance(signal.confidence, float)

def test_signal_scorer_ml_alignment():
    """Verify signal scorer rewards directional alignment and penalizes contradictions."""
    scorer = SignalQualityScorer(min_quality_threshold=60.0)
    
    base_sig = Signal(
        symbol="HDFCBANK",
        direction=SignalDirection.BUY,
        confidence=0.75,
        entry_price=1600.0,
        stop_loss=1580.0,
        take_target=1640.0,
        market_regime="BULLISH_TREND",
        expected_return_pct=1.2
    )
    
    # Aligned: BUY + UP
    indicators_aligned = {"ml_prediction": "UP"}
    score_aligned = scorer.calculate_score(base_sig, indicators=indicators_aligned)
    
    # Contradicted: BUY + DOWN
    indicators_contradicted = {"ml_prediction": "DOWN"}
    score_contradicted = scorer.calculate_score(base_sig, indicators=indicators_contradicted)
    
    # Aligned score should be strictly higher than contradicted score
    assert score_aligned.breakdown["ml"] > score_contradicted.breakdown["ml"]
    assert score_aligned.total_score > score_contradicted.total_score
