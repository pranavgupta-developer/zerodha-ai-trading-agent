import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import pandas as pd
import numpy as np
from app.trading.risk_engine import AccountState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Risk & Compliance"])


class RiskHaltReq(BaseModel):
    reason: str = "Manual emergency halt triggered by operator"
    triggered_by: str = "OPERATOR"


class RiskResumeReq(BaseModel):
    confirmation: str = "CONFIRM_RESUME"
    authorized_by: str = "ADMIN"


@router.get("/api/v1/system/risk/sectors")
def get_risk_sectors():
    """
    Returns current portfolio sector concentration versus statutory limits.
    """
    import app.main as m
    effective_margin = m.global_available_margin if m.global_available_margin > 0 else 500000.0
    active_positions = {
        p.symbol: p.entry_price * p.quantity
        for p in m.position_manager.get_all_tracked().values()
        if p.is_active
    }
    account = AccountState(
        available_margin=effective_margin,
        open_positions=active_positions
    )
    breakdown = m.risk_engine.get_sector_breakdown(account)
    is_compliant = not any(sec.get("breached", False) for sec in breakdown.get("sectors", {}).values())
    return {
        "status": "success",
        "compliant": is_compliant,
        "max_sector_exposure_pct": m.risk_engine.config.max_sector_exposure_pct,
        "total_exposure": breakdown.get("total_exposure", 0.0),
        "portfolio_capital": breakdown.get("portfolio_capital", effective_margin),
        "sectors": breakdown.get("sectors", {})
    }


@router.get("/api/v1/system/risk/var")
def get_risk_var(confidence: float = 0.95):
    """
    Calculates portfolio Value at Risk (VaR) and Expected Shortfall (CVaR)
    using 100% genuine real historical price returns (zero random/synthetic data).
    """
    import app.main as m
    effective_margin = m.global_available_margin if m.global_available_margin > 0 else 500000.0
    active_positions = {
        p.symbol: p.entry_price * p.quantity
        for p in m.position_manager.get_all_tracked().values()
        if p.is_active
    }
    account = AccountState(
        available_margin=effective_margin,
        open_positions=active_positions
    )
    
    total_val = sum(active_positions.values())
    if total_val > 0:
        symbols = list(active_positions.keys())
        price_dict = {}
        for sym in symbols:
            candles = m.global_candles_cache.get(sym, [])
            if candles and len(candles) >= 10:
                price_dict[sym] = [float(getattr(c, "close", 0.0)) for c in candles]
            else:
                try:
                    import yfinance as yf
                    yf_sym = f"{sym}.NS" if not sym.endswith(".NS") else sym
                    hist = yf.download(yf_sym, period="1mo", interval="1d", progress=False)
                    if not hist.empty:
                        close_vals = hist['Close'].values.flatten().tolist()
                        price_dict[sym] = [float(v) for v in close_vals if not np.isnan(v)]
                except Exception as e:
                    logger.debug(f"Historical price download for VaR {sym}: {e}")

        min_len = min((len(v) for v in price_dict.values()), default=0) if price_dict else 0
        if min_len >= 5:
            aligned_prices = pd.DataFrame({s: price_dict[s][-min_len:] for s in price_dict})
            returns_df = aligned_prices.pct_change().dropna()
        else:
            returns_df = None

        metrics_hist = m.risk_engine.get_portfolio_var_cvar(account, returns_df, confidence=confidence, method="historical")
        metrics_param = m.risk_engine.get_portfolio_var_cvar(account, returns_df, confidence=confidence, method="parametric")
    else:
        metrics_hist = m.risk_engine.get_portfolio_var_cvar(account, None, confidence=confidence, method="historical")
        metrics_param = m.risk_engine.get_portfolio_var_cvar(account, None, confidence=confidence, method="parametric")

    return {
        "status": "success",
        "confidence": confidence,
        "historical": metrics_hist,
        "parametric": metrics_param,
        "max_var_pct": m.risk_engine.config.max_portfolio_var_pct,
        "max_cvar_pct": m.risk_engine.config.max_portfolio_cvar_pct,
        "is_safe": bool(metrics_hist.get("is_safe", True) and metrics_param.get("is_safe", True))
    }


@router.get("/api/v1/system/risk-center/status")
def get_unified_risk_center_status():
    """
    Returns consolidated institutional state machine across all security/risk subsystems.
    """
    import app.main as m
    return {
        "status": "success",
        "data": m.unified_risk_center.evaluate_status(m.global_positions)
    }


@router.post("/api/v1/system/risk-center/halt")
def post_unified_risk_center_halt(req: RiskHaltReq):
    """
    Manually trips system-wide emergency halt across all subsystems.
    """
    import app.main as m
    result = m.unified_risk_center.trigger_emergency_halt(reason=req.reason, triggered_by=req.triggered_by)
    m.notify_state_changed()
    return result


@router.post("/api/v1/system/risk-center/resume")
def post_unified_risk_center_resume(req: RiskResumeReq):
    """
    Resets the emergency halt after confirmation.
    """
    import app.main as m
    result = m.unified_risk_center.resume_system(confirmation=req.confirmation, authorized_by=req.authorized_by)
    if result.get("status") == "REJECTED":
        raise HTTPException(status_code=400, detail=result.get("message"))
    m.notify_state_changed()
    return result


# Export aliases for backward compatibility
get_risk_center_status = get_unified_risk_center_status
halt_risk_center = post_unified_risk_center_halt
resume_risk_center = post_unified_risk_center_resume

