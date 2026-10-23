import logging
from typing import Optional, Dict, Any
from dataclasses import asdict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio
import pandas as pd
from app.trading.model_registry import ModelRole, ModelStatus, ModelProfile

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Machine Learning & Models"])


class ManualPredictionReq(BaseModel):
    symbol: str
    predicted_direction: str  # "BUY", "SELL", "HOLD"
    confidence: float
    entry_price: float
    features: Optional[Dict[str, float]] = None
    market_regime: Optional[str] = None
    trade_id: Optional[str] = None


class ManualOutcomeReq(BaseModel):
    symbol: str
    exit_price: float
    realized_pnl: float
    exit_reason: str = "MANUAL"
    trade_id: Optional[str] = None


class ModelRegisterReq(BaseModel):
    model_id: str
    name: str
    version: str
    role: str = "CHALLENGER"
    description: str = ""


class ModelPromoteReq(BaseModel):
    reason: str = "Manual promotion"


class ModelRollbackReq(BaseModel):
    reason: str = "Manual rollback"


@router.get("/api/v1/ml/metrics")
def get_ml_metrics():
    """
    Returns rolling ML metrics: accuracy, Brier calibration score, drift, and regime breakdown.
    """
    import app.main as m
    return m.ml_monitor.get_metrics_summary()


@router.get("/api/v1/ml/predictions")
def get_ml_predictions(limit: int = 50):
    """
    Returns recent ML prediction records with trade outcomes and calibration metrics.
    """
    import app.main as m
    return [asdict(r) for r in m.ml_monitor.records[-limit:]]


@router.post("/api/v1/ml/record")
def record_manual_prediction(req: ManualPredictionReq):
    """
    Manually logs a prediction record to the closed-loop ML feedback monitor.
    """
    import app.main as m
    rec = m.ml_monitor.record_prediction(
        symbol=req.symbol,
        predicted_direction=req.predicted_direction,
        confidence=req.confidence,
        entry_price=req.entry_price,
        features=req.features or {},
        market_regime=req.market_regime,
        trade_id=req.trade_id
    )
    return {"status": "success", "prediction": asdict(rec)}


@router.post("/api/v1/ml/outcome")
def record_manual_outcome(req: ManualOutcomeReq):
    """
    Manually records an outcome for a closed position to evaluate ML accuracy.
    """
    import app.main as m
    rec = m.ml_monitor.record_outcome(
        symbol=req.symbol,
        exit_price=req.exit_price,
        realized_pnl=req.realized_pnl,
        exit_reason=req.exit_reason,
        trade_id=req.trade_id
    )
    if not rec:
        raise HTTPException(status_code=404, detail=f"No pending prediction found for symbol {req.symbol}")
    m.sync_model_registry_outcome(
        symbol=req.symbol,
        exit_price=req.exit_price,
        realized_pnl=req.realized_pnl,
        exit_reason=req.exit_reason,
        trade_id=req.trade_id,
        ml_outcome=rec
    )
    return {"status": "success", "outcome": asdict(rec)}


@router.post("/api/v1/ml/train")
async def trigger_walk_forward_retraining(symbol: Optional[str] = None):
    """
    Triggers walk-forward retraining of XGBoost, Random Forest, and Regressors
    on real historical candle data.
    """
    import app.main as m
    import yfinance as yf
    from app.core.config import settings

    target_symbols = [symbol.strip().replace(".NS", "")] if symbol else [
        s.strip().replace(".NS", "") for s in settings.TRADING_SYMBOLS.split(",") if s.strip()
    ]

    results = {}
    for sym in target_symbols:
        try:
            yf_sym = f"{sym}.NS"
            df = await asyncio.to_thread(yf.download, yf_sym, period="1y", interval="1d", progress=False)
            if not df.empty and len(df) >= 60:
                df_clean = pd.DataFrame({
                    "open": df["Open"].values.flatten(),
                    "high": df["High"].values.flatten(),
                    "low": df["Low"].values.flatten(),
                    "close": df["Close"].values.flatten(),
                    "volume": df["Volume"].values.flatten(),
                }).dropna()
                
                res = m.ml_engine.walk_forward_retrain(sym, df_clean)
                results[sym] = res
            else:
                results[sym] = {"status": "failed", "reason": "Insufficient historical candle bars"}
        except Exception as e:
            logger.error(f"Walk-forward retraining error for {sym}: {e}")
            results[sym] = {"status": "error", "error": str(e)}

    return {
        "status": "success",
        "retrained_symbols": len(results),
        "details": results
    }


@router.get("/api/v1/system/models/status")
def get_model_registry_status():
    """
    Returns Champion–Challenger status, shadow evaluations, and win/loss statistics.
    """
    import app.main as m
    return {
        "status": "success",
        "data": m.model_registry.get_status()
    }


@router.post("/api/v1/system/models/promote")
def promote_challenger_model(req: ModelPromoteReq):
    """
    Promotes Challenger to Champion if it passes outperformance and safety gates.
    """
    import app.main as m
    res = m.model_registry.promote_challenger(reason=req.reason or "Manual promotion")
    m.log_audit_event(
        "MODEL_PROMOTION",
        "manual_promo",
        res.get("new_champion", "CHALLENGER"),
        "PROMOTED",
        f"Version: {res.get('new_version')} | Reason: {res.get('reason')}"
    )
    m.notify_state_changed()
    return res


@router.post("/api/v1/system/models/rollback")
def rollback_champion_model(req: ModelRollbackReq):
    """
    Rolls back Champion to Fallback baseline if performance degrades.
    """
    import app.main as m
    res = m.model_registry.rollback_champion(reason=req.reason or "Manual rollback")
    m.log_audit_event(
        "MODEL_ROLLBACK",
        "manual_rollback",
        res.get("active_model", "FALLBACK"),
        "ROLLBACK",
        f"Active: {res.get('active_model')} ({res.get('active_version')}) | Reason: {res.get('reason')}"
    )
    m.notify_state_changed()
    return res


@router.post("/api/v1/system/models/register")
def register_challenger_model(req: ModelRegisterReq):
    """
    Registers a new ML model into Champion–Challenger shadow competition.
    """
    import app.main as m
    try:
        role = ModelRole(req.role.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid model role: {req.role}")
    
    profile = ModelProfile(
        model_id=req.model_id,
        name=req.name,
        version=req.version,
        role=role,
        status=ModelStatus.SHADOW if role == ModelRole.CHALLENGER else ModelStatus.STANDBY,
        description=req.description
    )
    registered = m.model_registry.register_model(profile)
    m.log_audit_event(
        "MODEL_REGISTRY",
        req.model_id,
        req.name,
        "REGISTER",
        f"Registered new model {req.name} {req.version} as {req.role}"
    )
    m.notify_state_changed()
    return {"status": "success", "model": asdict(registered)}
