import pytest
import os
from app.trading.ml_monitor import MLMonitor, PredictionRecord

@pytest.fixture
def monitor(tmp_path):
    storage_file = str(tmp_path / "test_ml_records.json")
    return MLMonitor(storage_path=storage_file)

def test_record_prediction(monitor):
    rec = monitor.record_prediction(
        symbol="RELIANCE",
        predicted_direction="BUY",
        confidence=0.85,
        entry_price=2500.0,
        features={"rsi_14": 62.0, "ema_20": 2480.0, "atr_14": 15.0},
        trade_id="t101"
    )

    assert rec.symbol == "RELIANCE"
    assert rec.predicted_direction == "BUY"
    assert rec.confidence == 0.85
    assert rec.entry_price == 2500.0
    assert rec.status == "PENDING"
    assert rec.market_regime == "BULLISH_TREND"
    assert len(monitor.records) == 1

def test_record_outcome_buy_win(monitor):
    monitor.record_prediction(
        symbol="INFY",
        predicted_direction="BUY",
        confidence=0.80,
        entry_price=1500.0,
        trade_id="t102"
    )

    outcome = monitor.record_outcome(
        symbol="INFY",
        exit_price=1530.0,
        realized_pnl=300.0,
        exit_reason="TAKE_PROFIT",
        trade_id="t102"
    )

    assert outcome is not None
    assert outcome.status == "COMPLETED"
    assert outcome.is_correct is True
    assert outcome.realized_pnl == 300.0
    assert outcome.exit_reason == "TAKE_PROFIT"

def test_record_outcome_buy_loss(monitor):
    monitor.record_prediction(
        symbol="TCS",
        predicted_direction="BUY",
        confidence=0.75,
        entry_price=3500.0,
        trade_id="t103"
    )

    outcome = monitor.record_outcome(
        symbol="TCS",
        exit_price=3450.0,
        realized_pnl=-500.0,
        exit_reason="STOP_LOSS",
        trade_id="t103"
    )

    assert outcome is not None
    assert outcome.is_correct is False
    assert outcome.realized_pnl == -500.0

def test_record_outcome_sell_win(monitor):
    monitor.record_prediction(
        symbol="SBIN",
        predicted_direction="SELL",
        confidence=0.82,
        entry_price=800.0,
        trade_id="t104"
    )

    outcome = monitor.record_outcome(
        symbol="SBIN",
        exit_price=780.0,
        realized_pnl=200.0,
        exit_reason="TAKE_PROFIT",
        trade_id="t104"
    )

    assert outcome is not None
    assert outcome.is_correct is True

def test_rolling_accuracy_and_metrics(monitor):
    # Add 5 trades (3 wins, 2 losses)
    for i in range(5):
        t_id = f"tr_{i}"
        monitor.record_prediction(
            symbol=f"SYM_{i}",
            predicted_direction="BUY",
            confidence=0.8,
            entry_price=100.0,
            trade_id=t_id
        )
        pnl = 50.0 if i < 3 else -50.0
        exit_p = 105.0 if i < 3 else 95.0
        monitor.record_outcome(
            symbol=f"SYM_{i}",
            exit_price=exit_p,
            realized_pnl=pnl,
            exit_reason="TP" if i < 3 else "SL",
            trade_id=t_id
        )

    summary = monitor.get_metrics_summary()
    assert summary["total_predictions"] == 5
    assert summary["completed_evaluations"] == 5
    assert summary["overall_accuracy"] == 0.6  # 3/5
    assert summary["win_count"] == 3
    assert summary["loss_count"] == 2
    assert summary["total_realized_pnl"] == 50.0

def test_regime_classification(monitor):
    # Bullish
    assert monitor.classify_regime({"rsi_14": 65.0, "ema_20": 100.0, "atr_14": 1.0}, current_price=105.0) == "BULLISH_TREND"
    # Bearish
    assert monitor.classify_regime({"rsi_14": 35.0, "ema_20": 100.0, "atr_14": 1.0}, current_price=95.0) == "BEARISH_TREND"
    # High Volatility (ATR / price > 2.5%)
    assert monitor.classify_regime({"rsi_14": 50.0, "ema_20": 100.0, "atr_14": 3.5}, current_price=100.0) == "HIGH_VOLATILITY"
    # Sideways
    assert monitor.classify_regime({"rsi_14": 50.0, "ema_20": 100.0, "atr_14": 0.5}, current_price=100.0) == "SIDEWAYS"

def test_prediction_drift_detection(monitor):
    # Seed 40 reference predictions with high confidence
    for i in range(40):
        monitor.records.append(PredictionRecord(
            prediction_id=f"ref_{i}",
            symbol="TEST",
            predicted_direction="BUY",
            confidence=0.90,
            entry_price=100.0
        ))
    # Seed 20 current predictions with low confidence and SELL direction
    for i in range(20):
        monitor.records.append(PredictionRecord(
            prediction_id=f"curr_{i}",
            symbol="TEST",
            predicted_direction="SELL",
            confidence=0.55,
            entry_price=100.0
        ))

    drift = monitor.detect_prediction_drift(reference_window=40, current_window=20)
    assert drift["drift_detected"] is True
    assert drift["confidence_drift"] > 0.15

def test_performance_by_regime(monitor):
    # Record one trade in BULLISH_TREND and one in SIDEWAYS
    monitor.record_prediction(symbol="T1", predicted_direction="BUY", confidence=0.8, entry_price=100, market_regime="BULLISH_TREND", trade_id="t1")
    monitor.record_outcome(symbol="T1", exit_price=110, realized_pnl=100, exit_reason="TP", trade_id="t1")

    monitor.record_prediction(symbol="T2", predicted_direction="BUY", confidence=0.8, entry_price=100, market_regime="SIDEWAYS", trade_id="t2")
    monitor.record_outcome(symbol="T2", exit_price=90, realized_pnl=-100, exit_reason="SL", trade_id="t2")

    regimes = monitor.get_performance_by_regime()
    assert regimes["BULLISH_TREND"]["total_trades"] == 1
    assert regimes["BULLISH_TREND"]["win_rate"] == 100.0
    assert regimes["SIDEWAYS"]["total_trades"] == 1
    assert regimes["SIDEWAYS"]["win_rate"] == 0.0
