import logging
import time
from typing import Optional
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import AuditLog
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System & Operations"])


class PaperSnapshotReq(BaseModel):
    starting_margin: float
    ending_margin: float
    realized_pnl: float
    unrealized_pnl: float = 0.0
    total_trades: int = 0
    win_trades: int = 0
    loss_trades: int = 0
    date_str: Optional[str] = None
    brokerage_per_order: float = 20.0
    avg_latency_ms: float = 120.0


@router.post("/api/v1/system/emergency-stop")
def toggle_emergency_stop():
    """
    Emergency kill switch toggling trade placement.
    """
    import app.main as m
    m.EMERGENCY_STOP_ACTIVE = not m.EMERGENCY_STOP_ACTIVE
    status_str = "ENGAGED" if m.EMERGENCY_STOP_ACTIVE else "DISENGAGED"
    logger.critical(f"EMERGENCY STOP {status_str} BY USER.")
    m.log_audit_event("EMERGENCY_STOP", "system", "SYSTEM", status_str, f"Emergency stop manually toggled to {status_str}")
    m.notify_state_changed()
    return {"status": "success", "emergency_stop_active": m.EMERGENCY_STOP_ACTIVE}


@router.get("/api/v1/system/status")
def get_system_status():
    """
    Returns overarching health and subsystem status.
    """
    import app.main as m
    from app.utils.market_utils import is_market_open
    from app.broker.market_status import get_market_status
    is_live = m.broker.is_authenticated()
    mkt_open = is_market_open() if settings.CHECK_MARKET_HOURS else True
    mkt_status = get_market_status()
    open_h = getattr(settings, "MARKET_OPEN_HOUR", 9)
    open_m = getattr(settings, "MARKET_OPEN_MINUTE", 30)
    close_h = getattr(settings, "MARKET_CLOSE_HOUR", 15)
    close_m = getattr(settings, "MARKET_CLOSE_MINUTE", 30)
    return {
        "emergency_stop_active": m.EMERGENCY_STOP_ACTIVE,
        "trading_mode": settings.TRADING_MODE,
        "autonomous_execution": settings.AUTONOMOUS_EXECUTION,
        "zerodha_authenticated": is_live,
        "market_open": mkt_open,
        "market_status": mkt_status,
        "check_market_hours": settings.CHECK_MARKET_HOURS,
        "market_hours": f"{open_h:02d}:{open_m:02d} - {close_h:02d}:{close_m:02d} IST",
        "data_source": "ZERODHA_KITE_LIVE" if is_live else "ZERODHA_AUTH_REQUIRED",
        "login_url": m.broker.get_login_url()
    }


@router.post("/api/v1/system/reconcile")
def run_manual_reconciliation():
    """
    Triggers immediate reconciliation between internal positions and broker positions.
    """
    import app.main as m
    try:
        report = m.reconciliation_engine.run_reconciliation(auto_sync=True)
        if not report.is_synced:
            m.log_audit_event(
                "RECONCILIATION_ALERT",
                f"rec_{int(report.timestamp)}",
                "PORTFOLIO",
                "MISMATCH",
                f"Manual audit found {report.total_discrepancies} mismatches ({report.critical_count} critical). Auto-synced: {report.auto_resolved}"
            )
        m.notify_state_changed()
        return {
            "status": "success",
            "report": report.model_dump()
        }
    except Exception as e:
        logger.error(f"Manual reconciliation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/system/reconciliation/status")
def get_reconciliation_status():
    """
    Returns latest reconciliation report.
    """
    import app.main as m
    report = m.reconciliation_engine.latest_report
    if not report:
        report = m.reconciliation_engine.run_reconciliation(auto_sync=False)
    return {
        "report": report.model_dump(),
        "quarantined_count": len(m.reconciliation_engine.quarantined_payloads)
    }


@router.get("/api/v1/system/anomaly/status")
def get_anomaly_status():
    """
    Returns real-time anomaly detector score and telemetry.
    """
    import app.main as m
    opm = len([t for t in m.recent_order_timestamps if time.time() - t <= 60.0])
    return {
        "is_fitted": m.anomaly_detector.is_fitted,
        "current_orders_per_minute": opm,
        "emergency_stop_active": m.EMERGENCY_STOP_ACTIVE
    }


@router.get("/api/v1/system/paper-report")
def get_paper_report():
    """
    Returns cumulative paper trading journal statistics and daily snapshots.
    """
    import app.main as m
    return {
        "metrics": m.paper_journal.calculate_metrics(),
        "snapshots": [asdict(s) for s in m.paper_journal.daily_snapshots]
    }


@router.get("/api/v1/system/paper-report/markdown")
def get_paper_report_markdown():
    """
    Exports institutional paper trading journal in markdown format.
    """
    import app.main as m
    return {
        "markdown": m.paper_journal.generate_markdown_report()
    }


@router.post("/api/v1/system/paper-report/snapshot")
def record_paper_snapshot(req: PaperSnapshotReq):
    """
    Records an end-of-day portfolio snapshot to the journal.
    """
    import app.main as m
    snap = m.paper_journal.record_daily_snapshot(
        starting_margin=req.starting_margin,
        ending_margin=req.ending_margin,
        realized_pnl=req.realized_pnl,
        unrealized_pnl=req.unrealized_pnl,
        total_trades=req.total_trades,
        win_trades=req.win_trades,
        loss_trades=req.loss_trades,
        date_str=req.date_str,
        brokerage_per_order=req.brokerage_per_order,
        avg_latency_ms=req.avg_latency_ms
    )
    return {"status": "success", "snapshot": asdict(snap)}


@router.get("/api/v1/system/audit/verify")
def verify_audit_chain():
    """
    Verifies cryptographic SHA-256 integrity of the entire audit hash chain.
    """
    import app.main as m
    return m.audit_chain.verify_chain_detailed()


@router.get("/api/v1/system/audit/chain")
def get_audit_chain(limit: int = 50):
    """
    Returns the latest tamper-evident audit chain blocks.
    """
    import app.main as m
    return {
        "status": "success",
        "records": m.audit_chain.get_recent_records(limit=limit)
    }


@router.post("/api/v1/instruments/sync")
def sync_instruments(db: Session = Depends(get_db)):
    """
    Synchronizes instrument tokens from Zerodha Kite into local SQLite master.
    """
    import app.main as m
    from app.broker.instrument_master import instrument_master
    try:
        instrument_master.fetch_and_store_instruments(m.broker, db)
        return {"status": "success", "message": "Instruments synchronized successfully"}
    except Exception as e:
        logger.error(f"Failed to sync instruments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/audit-logs")
def get_audit_logs(limit: int = 50, db: Session = Depends(get_db)):
    """
    Returns recent audit logs from database.
    """
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return {
        "status": "success",
        "logs": [
            {
                "id": l.id,
                "event_type": l.event_type,
                "trade_id": l.trade_id,
                "symbol": l.symbol,
                "action": l.action,
                "details": l.details,
                "timestamp": l.timestamp.isoformat() if l.timestamp else ""
            }
            for l in logs
        ]
    }
