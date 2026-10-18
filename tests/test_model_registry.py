import pytest
import os
from app.trading.model_registry import (
    ModelRegistry,
    ModelProfile,
    ModelRole,
    ModelStatus,
    RollbackConfig
)

@pytest.fixture
def registry(tmp_path):
    storage_file = str(tmp_path / "test_model_registry.json")
    config = RollbackConfig(
        min_evaluations=5,              # Lower for testing
        accuracy_rollback_threshold=0.40,
        critical_killswitch_threshold=0.30,
        promotion_win_delta=0.10,
        promotion_min_accuracy=0.60,
        rolling_window=5,
        enable_auto_rollback=True,
        enable_auto_promotion=True
    )
    return ModelRegistry(storage_path=storage_file, config=config)

def test_initialization_defaults(registry):
    champion = registry.get_champion()
    challenger = registry.get_challenger()
    fallback = registry.get_fallback()

    assert champion is not None
    assert champion.role == ModelRole.CHAMPION
    assert champion.status == ModelStatus.ACTIVE
    assert "Gemini" in champion.name

    assert challenger is not None
    assert challenger.role == ModelRole.CHALLENGER
    assert challenger.status == ModelStatus.SHADOW
    assert "XGBoost" in challenger.name

    assert fallback is not None
    assert fallback.role == ModelRole.FALLBACK
    assert fallback.status == ModelStatus.STANDBY

def test_evaluate_shadow(registry):
    indicators = {"rsi_14": 62.0, "ema_20": 100.0, "atr_14": 2.5}
    shadow_pred = registry.evaluate_shadow("RELIANCE", indicators, entry_price=105.0, trade_id="t_shadow_1")

    assert shadow_pred is not None
    assert shadow_pred.symbol == "RELIANCE"
    assert shadow_pred.predicted_direction == "BUY"
    assert shadow_pred.confidence > 0.5
    assert shadow_pred.status == "PENDING"
    assert shadow_pred.trade_id == "t_shadow_1"

    status = registry.get_status()
    assert status["pending_shadow_predictions"] == 1

def test_record_trade_outcome_dual_evaluation(registry):
    # Setup a shadow prediction
    indicators = {"rsi_14": 60.0, "ema_20": 100.0}
    registry.evaluate_shadow("INFY", indicators, entry_price=100.0, trade_id="t_dual_1")

    # Trade exits profitably
    res = registry.record_trade_outcome(
        trade_id="t_dual_1",
        symbol="INFY",
        exit_price=105.0,
        realized_pnl=500.0,
        is_champion_correct=True,
        champion_confidence=0.85
    )

    assert res["champion"] is not None
    assert res["champion"]["is_correct"] is True
    assert res["champion"]["rolling_accuracy"] == 1.0

    assert res["challenger"] is not None
    assert res["challenger"]["is_correct"] is True
    assert res["challenger"]["rolling_accuracy"] == 1.0

def test_auto_promotion_when_challenger_outperforms(registry):
    # Simulate 5 trades where Challenger is correct but Champion fails
    for i in range(5):
        tid = f"t_promo_{i}"
        # Create shadow prediction with BUY direction
        registry.evaluate_shadow("TCS", {"rsi_14": 60.0, "ema_20": 100.0}, entry_price=100.0, trade_id=tid)
        
        # Outcome: trade goes UP (Challenger correct), but Champion was incorrect
        res = registry.record_trade_outcome(
            trade_id=tid,
            symbol="TCS",
            exit_price=105.0,
            realized_pnl=100.0,
            is_champion_correct=False
        )

    # After 5 trades, Challenger has 100% accuracy, Champion has 0% accuracy
    # Delta = 100% >= 10% delta threshold and Challenger >= 60%
    champion = registry.get_champion()
    assert "XGBoost" in champion.name
    assert champion.role == ModelRole.CHAMPION
    assert champion.version == "v1.1"

def test_auto_rollback_when_champion_degrades(registry):
    # Simulate 5 trades where Champion keeps failing and no challenger shadow prediction
    for i in range(5):
        tid = f"t_degrade_{i}"
        registry.record_trade_outcome(
            trade_id=tid,
            symbol="SBIN",
            exit_price=95.0,
            realized_pnl=-50.0,
            is_champion_correct=False
        )

    # Champion accuracy is 0.0% (< 40% threshold)
    # Since challenger has 0 predictions, it activates Fallback!
    champion = registry.get_champion()
    assert champion is not None
    assert "Fallback" in champion.name or "Deterministic" in champion.name

def test_manual_promote_and_rollback(registry):
    # Initial: Gemini is Champion, XGBoost is Challenger
    assert "Gemini" in registry.get_champion().name

    # Manual promote
    prom_res = registry.promote_challenger(reason="Operator benchmark test")
    assert prom_res["status"] == "success"
    assert "XGBoost" in registry.get_champion().name

    # Manual rollback
    roll_res = registry.rollback_champion(reason="Reverting benchmark test")
    assert roll_res["status"] == "success"

def test_get_status_summary(registry):
    status = registry.get_status()
    assert "health_status" in status
    assert "champion" in status
    assert "challenger" in status
    assert "fallback" in status
    assert status["champion"]["name"] == "Gemini-Quant-Ensemble"
    assert status["challenger"]["name"] == "XGBoost-Trend-Shadow"
