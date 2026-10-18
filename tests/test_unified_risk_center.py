import pytest
from unittest.mock import MagicMock
from app.security.unified_risk_center import UnifiedRiskCenter, SystemRiskState

@pytest.fixture
def mock_subsystems():
    audit_chain = MagicMock()
    audit_chain.verify_chain_detailed.return_value = {
        "is_valid": True,
        "total_events": 10,
        "last_hash": "a"*64
    }

    reconciliation_engine = MagicMock()
    reconciliation_engine.last_report = MagicMock()
    reconciliation_engine.last_report.discrepancies = []
    reconciliation_engine.quarantine_list = []

    anomaly_detector = MagicMock()
    anomaly_detector.is_halted = False
    anomaly_detector.anomalies_history = []

    risk_engine = MagicMock()
    risk_engine.calculate_sector_exposure.return_value = {"IT": 20.0, "BANKING_FINANCIAL": 15.0}
    risk_engine.config = MagicMock()
    risk_engine.config.max_sector_allocation_pct = 35.0

    model_registry = MagicMock()
    model_registry.get_status.return_value = {
        "champion": {"model_id": "champ-v1", "rolling_accuracy": 62.0, "total_evaluations": 20},
        "challenger": {"model_id": "chall-v2", "rolling_accuracy": 63.0, "total_evaluations": 20, "shadow_win_delta": 1.0}
    }

    return {
        "audit_chain": audit_chain,
        "reconciliation_engine": reconciliation_engine,
        "anomaly_detector": anomaly_detector,
        "risk_engine": risk_engine,
        "model_registry": model_registry
    }

def test_unified_risk_center_nominal_safe(mock_subsystems):
    center = UnifiedRiskCenter(**mock_subsystems)
    status = center.evaluate_status([])
    assert status["overall_state"] == SystemRiskState.SAFE.value
    assert len(status["reasons"]) == 0
    assert status["subsystems"]["audit_chain"]["status"] == "VERIFIED"
    assert status["subsystems"]["kill_switch"]["is_active"] is False
    assert center.is_halted() is False

def test_unified_risk_center_audit_tampered_triggers_halt(mock_subsystems):
    mock_subsystems["audit_chain"].verify_chain_detailed.return_value = {
        "is_valid": False,
        "total_events": 10,
        "tampered_at_line": 4,
        "last_hash": "b"*64
    }
    center = UnifiedRiskCenter(**mock_subsystems)
    status = center.evaluate_status([])
    assert status["overall_state"] == SystemRiskState.HALTED.value
    assert any("AUDIT INTEGRITY BREACH" in r for r in status["reasons"])

def test_unified_risk_center_anomaly_detector_halt(mock_subsystems):
    mock_subsystems["anomaly_detector"].is_halted = True
    center = UnifiedRiskCenter(**mock_subsystems)
    status = center.evaluate_status([])
    assert status["overall_state"] == SystemRiskState.HALTED.value
    assert center.is_halted() is True

def test_unified_risk_center_sector_breach_warning(mock_subsystems):
    # Sector exposure exceeds 35% cap
    mock_subsystems["risk_engine"].calculate_sector_exposure.return_value = {"IT": 42.0}
    center = UnifiedRiskCenter(**mock_subsystems)
    status = center.evaluate_status([])
    assert status["overall_state"] == SystemRiskState.WARNING.value
    assert any("PORTFOLIO RISK: Sector 'IT' at 42.0% exceeds" in r for r in status["reasons"])

def test_unified_risk_center_challenger_outperforming_warning(mock_subsystems):
    mock_subsystems["model_registry"].get_status.return_value = {
        "champion": {"model_id": "champ-v1", "rolling_accuracy": 55.0, "total_evaluations": 25},
        "challenger": {"model_id": "chall-v2", "rolling_accuracy": 62.0, "total_evaluations": 25, "shadow_win_delta": 7.0}
    }
    center = UnifiedRiskCenter(**mock_subsystems)
    status = center.evaluate_status([])
    assert status["overall_state"] == SystemRiskState.WARNING.value
    assert any("Challenger chall-v2 outperforming Champion" in r for r in status["reasons"])

def test_unified_risk_center_model_critical_drop_halt(mock_subsystems):
    mock_subsystems["model_registry"].get_status.return_value = {
        "champion": {"model_id": "champ-v1", "rolling_accuracy": 30.0, "total_evaluations": 20},
        "challenger": None
    }
    center = UnifiedRiskCenter(**mock_subsystems)
    status = center.evaluate_status([])
    assert status["overall_state"] == SystemRiskState.HALTED.value
    assert any("Champion champ-v1 accuracy collapsed" in r for r in status["reasons"])

def test_unified_risk_center_manual_halt_and_resume(mock_subsystems):
    callback_mock = MagicMock()
    center = UnifiedRiskCenter(**mock_subsystems, emergency_stop_callback=callback_mock)

    halt_res = center.trigger_emergency_halt("Operator noticed market flash crash", "DESK_TRADER")
    assert halt_res["status"] == "HALTED"
    assert center.is_halted() is True
    callback_mock.assert_called_with(True, "Operator noticed market flash crash")

    # Status evaluation shows HALTED
    status = center.evaluate_status([])
    assert status["overall_state"] == SystemRiskState.HALTED.value

    # Resume without correct confirmation is rejected
    rej = center.resume_system("WRONG_CONFIRM")
    assert rej["status"] == "REJECTED"
    assert center.is_halted() is True

    # Valid resume
    res = center.resume_system("CONFIRM_RESUME", "RISK_DIRECTOR")
    assert res["status"] == "RESUMED"
    assert center.is_halted() is False
    callback_mock.assert_called_with(False, "Manual resume")
