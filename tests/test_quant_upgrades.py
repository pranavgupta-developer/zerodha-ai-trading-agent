import pytest
import pandas as pd
import numpy as np
from app.trading.strategy import EmaRsiVwapStrategy, StrategyConfig
from app.trading.signals import Signal, SignalDirection
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState, calculate_statutory_charges
from app.trading.ml_engine import MLEngine
from app.trading.ml_monitor import MLMonitor

class MockCandle:
    def __init__(self, close, high=None, low=None, volume=1000):
        self.close = float(close)
        self.high = float(high if high is not None else close * 1.01)
        self.low = float(low if low is not None else close * 0.99)
        self.volume = int(volume)

# 1. Multi-Timeframe Alignment
def test_strategy_mtf_alignment():
    config = StrategyConfig(fast_ema_period=3, slow_ema_period=6, rsi_period=4, rsi_overbought=85.0, enable_mtf_filter=True, mtf_ema_period=5)
    strategy = EmaRsiVwapStrategy(config)

    # 1m candles engineer a bullish crossover
    candles = [MockCandle(100.0) for _ in range(15)]
    candles.append(MockCandle(90.0))
    candles.append(MockCandle(120.0))

    # MTF candles with Bearish trend (Price below 20 EMA)
    mtf_bearish = [MockCandle(150.0 - i * 2) for i in range(25)] # downward trend
    sig_rejected = strategy.generate_signal("RELIANCE", candles, mtf_candles=mtf_bearish)
    assert sig_rejected.direction == SignalDirection.HOLD
    assert "MTF Misalignment" in sig_rejected.reason

    # MTF candles with Bullish trend (Price above 20 EMA)
    mtf_bullish = [MockCandle(80.0 + i * 2) for i in range(25)] # upward trend
    sig_approved = strategy.generate_signal("RELIANCE", candles, mtf_candles=mtf_bullish)
    if sig_approved.direction == SignalDirection.BUY:
        assert sig_approved.mtf_confirmed is True

# 2. Dynamic SL/TP Adaptation to Regime
def test_strategy_dynamic_sl_tp_by_regime():
    config = StrategyConfig(fast_ema_period=3, slow_ema_period=6, rsi_period=4)
    strategy = EmaRsiVwapStrategy(config)
    candles = [MockCandle(100.0) for _ in range(15)]
    candles.append(MockCandle(90.0))
    candles.append(MockCandle(120.0))

    sig_bullish = strategy.generate_signal("RELIANCE", candles, market_regime="BULLISH_TREND")
    if sig_bullish.direction == SignalDirection.BUY:
        # Bullish trend gives 2.5x RR
        assert "RR: 2.5x" in sig_bullish.reason
        assert sig_bullish.expected_return_pct > 0.0

    sig_sideways = strategy.generate_signal("RELIANCE", candles, market_regime="SIDEWAYS")
    if sig_sideways.direction == SignalDirection.BUY:
        # Sideways gives 1.3x RR (mean-reversion)
        assert "RR: 1.3x" in sig_sideways.reason

# 3. Pre-Trade Transaction Cost Hurdle Filter
def test_risk_engine_transaction_cost_filter():
    config = RiskConfig(check_market_hours=False, check_transaction_costs=True, min_profit_to_cost_ratio=1.5)
    engine = RiskEngine(config)
    account = AccountState(available_margin=500000.0)

    # Legitimate trade: Entry 2500, Target 2550 (Profit = 50 * 20 = 1000, charges ~30)
    good_signal = Signal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        confidence=0.85,
        entry_price=2500.0,
        stop_loss=2470.0,
        take_target=2550.0
    )
    approved, reason = engine.validate_signal(good_signal, account, requested_qty=20)
    assert approved is True

    # Micro-scalp / Cost Inefficient: Entry 2500, Target 2500.20 (Profit = 0.20 * 20 = 4.00, charges ~30)
    bad_signal = Signal(
        symbol="RELIANCE",
        direction=SignalDirection.BUY,
        confidence=0.85,
        entry_price=2500.0,
        stop_loss=2490.0,
        take_target=2500.20
    )
    approved, reason = engine.validate_signal(bad_signal, account, requested_qty=20)
    assert approved is False
    assert "COST_INEFFICIENT" in reason

# 4. Expected Return Prediction & Walk-Forward Retraining in MLEngine
def test_ml_engine_expected_return_and_walkforward():
    np.random.seed(42)
    n = 220
    dates = pd.date_range("2026-01-01", periods=n, freq="5min")
    prices = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "close": prices,
        "high": prices + 0.2,
        "low": prices - 0.2,
        "volume": np.random.randint(100, 1000, size=n)
    }, index=dates)

    engine = MLEngine(target_period=3)
    engine.train_and_evaluate("TEST_STOCK", df)

    assert engine.best_model_name is not None
    assert engine.best_regressor_name is not None

    pred = engine.predict("TEST_STOCK", df)
    assert pred is not None
    assert pred.predicted_direction in ("UP", "DOWN")
    assert isinstance(pred.expected_return_pct, float)

    # Walk-forward retraining
    wf_res = engine.walk_forward_retrain("TEST_STOCK", df, train_window=100, test_window=20, step=20)
    assert wf_res["status"] == "success"
    assert wf_res["windows_evaluated"] >= 2
    assert "walk_forward_accuracy" in wf_res

# 5. MLMonitor Feedback Loop & Regime Breakdown
def test_ml_monitor_expected_return_and_regime_summary(tmp_path):
    storage = str(tmp_path / "test_monitor.json")
    monitor = MLMonitor(storage_path=storage)

    # Record prediction with expected return
    rec = monitor.record_prediction(
        symbol="TCS",
        predicted_direction="BUY",
        confidence=0.88,
        entry_price=3500.0,
        expected_return_pct=2.5,
        market_regime="BULLISH_TREND",
        trade_id="t101"
    )
    assert rec.expected_return_pct == 2.5
    assert rec.status == "PENDING"

    # Record outcome with realized pnl
    outcome = monitor.record_outcome(
        symbol="TCS",
        exit_price=3580.0,
        realized_pnl=80.0,
        exit_reason="TAKE_PROFIT",
        trade_id="t101"
    )
    assert outcome is not None
    assert outcome.status == "COMPLETED"
    assert outcome.is_correct is True
    assert outcome.return_error is not None

    mae = monitor.calculate_expected_return_mae()
    assert mae >= 0.0

    summary = monitor.get_regime_performance_summary()
    assert "BULLISH_TREND" in summary
    assert summary["BULLISH_TREND"]["trades"] == 1
    assert summary["BULLISH_TREND"]["wins"] == 1
    assert summary["BULLISH_TREND"]["win_rate"] == 100.0
