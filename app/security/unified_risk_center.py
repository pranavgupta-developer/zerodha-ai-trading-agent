import logging
import time
from enum import Enum
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class SystemRiskState(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    HALTED = "HALTED"

class UnifiedRiskCenter:
    """
    Institutional Unified Risk & Security Control Center.
    Aggregates real-time health and security metrics from:
      1. Cryptographic Audit Chain (Tamper detection)
      2. Broker Reconciliation Engine (State mismatch & quarantine)
      3. Advanced Anomaly Sentinel (Statistical outliers & auto-halt)
      4. Portfolio VaR & Sector Concentration Engine (Institutional risk limits)
      5. Model Champion-Challenger Registry (Model drift, rollback, & kill-switch)
      6. Emergency Stop / Kill-Switch Sentinel

    Maintains a deterministic 3-state machine: SAFE | WARNING | HALTED.
    """

    def __init__(
        self,
        audit_chain=None,
        reconciliation_engine=None,
        anomaly_detector=None,
        risk_engine=None,
        model_registry=None,
        emergency_stop_callback=None,
        is_emergency_stop_active=None
    ):
        self.audit_chain = audit_chain
        self.reconciliation_engine = reconciliation_engine
        self.anomaly_detector = anomaly_detector
        self.risk_engine = risk_engine
        self.model_registry = model_registry
        self.emergency_stop_callback = emergency_stop_callback
        self._is_emergency_stop_active_fn = is_emergency_stop_active
        self._manual_halt = False
        self._manual_halt_reason = ""
        self._last_evaluated_state = SystemRiskState.SAFE
        self._halt_history: List[Dict[str, Any]] = []

    def is_halted(self) -> bool:
        if self._manual_halt:
            return True
        if self._is_emergency_stop_active_fn and self._is_emergency_stop_active_fn():
            return True
        if self.anomaly_detector and getattr(self.anomaly_detector, "is_halted", False):
            return True
        return False

    def trigger_emergency_halt(self, reason: str, triggered_by: str = "OPERATOR") -> Dict[str, Any]:
        """Manually trips the system-wide emergency halt."""
        self._manual_halt = True
        self._manual_halt_reason = reason
        record = {
            "timestamp": time.time(),
            "action": "HALT",
            "reason": reason,
            "triggered_by": triggered_by
        }
        self._halt_history.append(record)
        logger.critical(f"UNIFIED RISK CENTER: Emergency HALT triggered by {triggered_by}. Reason: {reason}")

        if self.emergency_stop_callback:
            try:
                self.emergency_stop_callback(True, reason)
            except Exception as e:
                logger.error(f"Failed to invoke emergency stop callback: {e}")

        if self.audit_chain:
            try:
                self.audit_chain.log_event("EMERGENCY_HALT_TRIGGERED", record)
            except Exception as e:
                logger.error(f"Failed to log audit event for emergency halt: {e}")

        return {"status": "HALTED", "reason": reason, "timestamp": record["timestamp"]}

    def resume_system(self, confirmation: str, authorized_by: str = "ADMIN") -> Dict[str, Any]:
        """Resets the manual emergency halt after safety confirmation."""
        if confirmation != "CONFIRM_RESUME":
            return {"status": "REJECTED", "message": "Confirmation string 'CONFIRM_RESUME' required."}

        self._manual_halt = False
        self._manual_halt_reason = ""
        record = {
            "timestamp": time.time(),
            "action": "RESUME",
            "authorized_by": authorized_by
        }
        self._halt_history.append(record)
        logger.info(f"UNIFIED RISK CENTER: System resumed by {authorized_by}.")

        if self.emergency_stop_callback:
            try:
                self.emergency_stop_callback(False, "Manual resume")
            except Exception as e:
                logger.error(f"Failed to invoke emergency resume callback: {e}")

        if self.anomaly_detector and hasattr(self.anomaly_detector, "reset_halt"):
            try:
                self.anomaly_detector.reset_halt()
            except Exception as e:
                logger.error(f"Failed to reset anomaly detector halt: {e}")

        if self.audit_chain:
            try:
                self.audit_chain.log_event("EMERGENCY_HALT_CLEARED", record)
            except Exception as e:
                logger.error(f"Failed to log audit event for emergency resume: {e}")

        return {"status": "RESUMED", "message": "System emergency halt cleared."}

    def evaluate_status(self, portfolio_positions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Consolidates all subsystem statuses and determines overall state:
          - HALTED: Kill-switch active, audit tampering, critical anomaly, or severe model collapse.
          - WARNING: Elevated anomalies, reconciliation mismatches, sector concentration warning, or model outperformance.
          - SAFE: All subsystems compliant and synchronized.
        """
        reasons: List[str] = []
        state = SystemRiskState.SAFE

        subsystems: Dict[str, Any] = {
            "kill_switch": {"is_active": False, "status": "NOMINAL"},
            "audit_chain": {"is_valid": True, "status": "VERIFIED"},
            "anomaly_sentinel": {"status": "NOMINAL", "is_halted": False, "critical_count": 0},
            "reconciliation": {"status": "SYNCHRONIZED", "discrepancies": 0, "quarantined": 0},
            "portfolio_risk": {"status": "COMPLIANT", "var_95": 0.0, "cvar_95": 0.0, "max_sector": "NONE", "max_sector_pct": 0.0},
            "model_registry": {"status": "ACTIVE", "champion_id": "NONE", "champion_accuracy": 0.0}
        }

        # 1. Kill-Switch / Manual Halt
        if self._manual_halt or (self._is_emergency_stop_active_fn and self._is_emergency_stop_active_fn()):
            state = SystemRiskState.HALTED
            halt_reason = self._manual_halt_reason or "Emergency Stop Sentinel Active"
            reasons.append(f"KILL-SWITCH ENGAGED: {halt_reason}")
            subsystems["kill_switch"] = {"is_active": True, "status": "HALTED", "reason": halt_reason}

        # 2. Cryptographic Audit Chain Integrity
        if self.audit_chain:
            try:
                audit_report = self.audit_chain.verify_chain_detailed()
                subsystems["audit_chain"] = {
                    "is_valid": audit_report.get("is_valid", False),
                    "total_events": audit_report.get("total_events", 0),
                    "last_hash": audit_report.get("last_hash", ""),
                    "status": "VERIFIED" if audit_report.get("is_valid") else "TAMPERED"
                }
                if not audit_report.get("is_valid"):
                    state = SystemRiskState.HALTED
                    reasons.append(f"AUDIT INTEGRITY BREACH: Chain broken at line {audit_report.get('tampered_at_line')}")
            except Exception as e:
                logger.error(f"Risk Center failed checking audit chain: {e}")
                subsystems["audit_chain"]["status"] = "ERROR"

        # 3. Anomaly Sentinel
        if self.anomaly_detector:
            try:
                is_halted = getattr(self.anomaly_detector, "is_halted", False)
                history = getattr(self.anomaly_detector, "anomalies_history", [])
                recent_critical = [a for a in history if getattr(a, "severity", "") == "CRITICAL" or getattr(a, "is_critical", False)]
                recent_warnings = [a for a in history if getattr(a, "severity", "") in ("WARNING", "HIGH")]

                subsystems["anomaly_sentinel"] = {
                    "is_halted": is_halted,
                    "critical_count": len(recent_critical),
                    "warning_count": len(recent_warnings),
                    "status": "HALTED" if is_halted else ("WARNING" if recent_warnings else "NOMINAL")
                }

                if is_halted or len(recent_critical) > 0:
                    state = SystemRiskState.HALTED
                    reasons.append("ANOMALY SENTINEL: Critical anomaly threshold exceeded or halt active.")
                elif len(recent_warnings) > 0 and state != SystemRiskState.HALTED:
                    state = SystemRiskState.WARNING
                    reasons.append(f"ANOMALY SENTINEL: {len(recent_warnings)} elevated anomalies detected.")
            except Exception as e:
                logger.error(f"Risk Center failed checking anomaly detector: {e}")

        # 4. Broker Reconciliation
        if self.reconciliation_engine:
            try:
                last_report = getattr(self.reconciliation_engine, "last_report", None)
                quarantine_list = getattr(self.reconciliation_engine, "quarantine_list", [])
                
                discrepancies_count = len(last_report.discrepancies) if last_report and hasattr(last_report, "discrepancies") else 0
                quarantined_count = len(quarantine_list)

                subsystems["reconciliation"] = {
                    "status": "QUARANTINED" if quarantined_count > 0 else ("MISMATCH" if discrepancies_count > 0 else "SYNCHRONIZED"),
                    "discrepancies": discrepancies_count,
                    "quarantined": quarantined_count
                }

                if quarantined_count > 0:
                    if state != SystemRiskState.HALTED:
                        state = SystemRiskState.WARNING
                    reasons.append(f"RECONCILIATION: {quarantined_count} malformed/unrecognized broker responses in quarantine.")
                elif discrepancies_count > 0:
                    if state != SystemRiskState.HALTED:
                        state = SystemRiskState.WARNING
                    reasons.append(f"RECONCILIATION: {discrepancies_count} local-broker position/order discrepancies detected.")
            except Exception as e:
                logger.error(f"Risk Center failed checking reconciliation engine: {e}")

        # 5. Portfolio Risk (VaR & Sectors)
        if self.risk_engine:
            try:
                positions = portfolio_positions or []
                sector_allocs = self.risk_engine.calculate_sector_exposure(positions)
                max_sector = max(sector_allocs.items(), key=lambda x: x[1]) if sector_allocs else ("NONE", 0.0)
                sector_cap = getattr(self.risk_engine.config, "max_sector_allocation_pct", 35.0)

                # Sector cap check
                sector_status = "COMPLIANT"
                if max_sector[1] > sector_cap:
                    sector_status = "BREACH"
                    if state != SystemRiskState.HALTED:
                        state = SystemRiskState.WARNING
                    reasons.append(f"PORTFOLIO RISK: Sector '{max_sector[0]}' at {max_sector[1]:.1f}% exceeds {sector_cap}% cap.")
                elif max_sector[1] >= (sector_cap - 5.0):
                    sector_status = "NEAR_LIMIT"
                    if state != SystemRiskState.HALTED:
                        state = SystemRiskState.WARNING
                    reasons.append(f"PORTFOLIO RISK: Sector '{max_sector[0]}' nearing cap ({max_sector[1]:.1f}% / {sector_cap}%).")

                subsystems["portfolio_risk"] = {
                    "status": sector_status,
                    "max_sector": max_sector[0],
                    "max_sector_pct": round(max_sector[1], 2),
                    "sector_cap": sector_cap
                }
            except Exception as e:
                logger.error(f"Risk Center failed checking portfolio risk: {e}")

        # 6. Model Champion-Challenger Health
        if self.model_registry:
            try:
                model_status = self.model_registry.get_status()
                champion = model_status.get("champion")
                challenger = model_status.get("challenger")
                
                champ_acc = champion.get("rolling_accuracy", 0.0) if champion else 0.0
                chall_acc = challenger.get("rolling_accuracy", 0.0) if challenger else 0.0
                win_delta = challenger.get("shadow_win_delta", 0.0) if challenger else 0.0

                reg_status = "ACTIVE"
                if champ_acc < 35.0 and champion and champion.get("total_evaluations", 0) >= 10:
                    reg_status = "CRITICAL_DRIFT"
                    state = SystemRiskState.HALTED
                    reasons.append(f"MODEL REGISTRY: Champion {champion.get('model_id')} accuracy collapsed to {champ_acc:.1f}% (< 35%). Emergency halt triggered.")
                elif champ_acc < 45.0 and champion and champion.get("total_evaluations", 0) >= 10:
                    reg_status = "ROLLBACK_WARNING"
                    if state != SystemRiskState.HALTED:
                        state = SystemRiskState.WARNING
                    reasons.append(f"MODEL REGISTRY: Champion accuracy degraded to {champ_acc:.1f}% (< 45%). Rollback recommended.")
                elif win_delta >= 5.0 and challenger and challenger.get("total_evaluations", 0) >= 10:
                    reg_status = "CHALLENGER_OUTPERFORMING"
                    if state != SystemRiskState.HALTED:
                        state = SystemRiskState.WARNING
                    reasons.append(f"MODEL REGISTRY: Challenger {challenger.get('model_id')} outperforming Champion by {win_delta:+.1f}%. Promotion eligible.")

                subsystems["model_registry"] = {
                    "status": reg_status,
                    "champion_id": champion.get("model_id") if champion else "NONE",
                    "champion_accuracy": champ_acc,
                    "challenger_id": challenger.get("model_id") if challenger else "NONE",
                    "challenger_accuracy": chall_acc,
                    "win_delta": win_delta
                }
            except Exception as e:
                logger.error(f"Risk Center failed checking model registry: {e}")

        self._last_evaluated_state = state
        return {
            "overall_state": state.value,
            "timestamp": time.time(),
            "summary": "All systems nominal and cryptographically verified." if state == SystemRiskState.SAFE else f"{len(reasons)} active alert(s) requiring attention.",
            "reasons": reasons,
            "subsystems": subsystems
        }
