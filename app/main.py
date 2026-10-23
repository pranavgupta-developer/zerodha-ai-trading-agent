from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from contextlib import asynccontextmanager
import asyncio
import json
import random
import logging
import time
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

import threading
import numpy as np
import pandas as pd

from app.core.config import settings
from app.broker.kite_adapter import BrokerAdapter
from app.db.database import engine, Base, SessionLocal
import app.db.models
from app.db.models import AuditLog
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from app.trading.order_manager import OrderManager
from app.trading.signals import Signal, SignalDirection
from app.trading.position_manager import PositionManager, ExitReason
from app.broker.ticker import MarketTicker
from app.trading.pipeline import TradingPipeline
from app.trading.strategy import EmaRsiVwapStrategy
from app.agent.service import AgentService
from app.trading.position_sizer import DynamicPositionSizer
from app.trading.reconciliation import ReconciliationEngine, ReconciliationReport
from app.security.anomaly_detector import AnomalyDetector
from app.security.audit_chain import AuditChain
from app.trading.ml_monitor import MLMonitor, PredictionRecord
from app.trading.paper_report import PaperTradingJournal, DailySnapshot
from app.trading.model_registry import ModelRegistry, ModelRole, ModelStatus, RollbackConfig, ModelProfile
from app.security.unified_risk_center import UnifiedRiskCenter, SystemRiskState
from app.trading.ml_engine import MLEngine
from app.trading.quant_engine import QuantEngine
from app.trading.portfolio_optimizer import PortfolioOptimizer
from app.broker.instrument_master import instrument_master
from app.core.state import ThreadSafePriceCache, state_manager

# Configured Logging with Rotation (Max 10MB per file, 5 backups)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Core Global Singletons & Mutable State (Maintained for backward compatibility)
price_cache = state_manager.price_cache
active_connections: list[WebSocket] = state_manager.active_connections
candidate_cache: dict = state_manager.candidate_cache
autonomous_trades_history: list = state_manager.autonomous_trades_history
EMERGENCY_STOP_ACTIVE: bool = False
global_candles_cache: dict[str, list] = state_manager.global_candles_cache
global_holdings: list = state_manager.global_holdings
global_positions: list = state_manager.global_positions
global_available_margin: float = state_manager.global_available_margin
recent_order_timestamps: list = state_manager.recent_order_timestamps
daily_prev_closes: dict[str, float] = state_manager.daily_prev_closes
market_ticker: Optional[MarketTicker] = None

# Business Engines
broker = BrokerAdapter()
risk_engine = RiskEngine(config=RiskConfig(check_market_hours=settings.CHECK_MARKET_HOURS))
order_manager = OrderManager(broker)
position_manager = PositionManager(broker=broker)
strategy = EmaRsiVwapStrategy()
agent_service = AgentService()
position_sizer = DynamicPositionSizer()
reconciliation_engine = ReconciliationEngine(broker=broker, position_manager=position_manager, order_manager=order_manager)
reconciler = reconciliation_engine
anomaly_detector = AnomalyDetector()
ml_monitor = MLMonitor()
paper_journal = PaperTradingJournal()
audit_chain = AuditChain("audit.jsonl")
model_registry = ModelRegistry("model_registry.json")
ml_engine = MLEngine()
quant_engine = QuantEngine()
portfolio_optimizer = PortfolioOptimizer()

def sync_emergency_stop_callback(active: bool, reason: str = ""):
    global EMERGENCY_STOP_ACTIVE
    EMERGENCY_STOP_ACTIVE = active
    state_manager.set_emergency_stop(active, reason)
    notify_state_changed()

unified_risk_center = UnifiedRiskCenter(
    audit_chain=audit_chain,
    reconciliation_engine=reconciliation_engine,
    anomaly_detector=anomaly_detector,
    risk_engine=risk_engine,
    model_registry=model_registry,
    emergency_stop_callback=sync_emergency_stop_callback
)

pipeline = TradingPipeline(
    strategy=strategy,
    agent=agent_service,
    risk_engine=risk_engine,
    order_manager=order_manager,
    position_sizer=position_sizer,
    anomaly_detector=anomaly_detector,
    model_registry=model_registry,
    ml_engine=ml_engine,
    quant_engine=quant_engine
)

# Parse configured trading symbols
_configured_symbols = [s.strip().replace(".NS", "") for s in settings.TRADING_SYMBOLS.split(",") if s.strip()]
if not _configured_symbols:
    _configured_symbols = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

current_watchlist_payload: list[dict] = [
    {
        "symbol": _sym,
        "ltp": 0.0,
        "prev_close": 0.0,
        "change": 0.0,
        "signal": "HOLD",
        "status": "WAITING_FOR_ZERODHA_FEED",
        "source_ts": time.time(),
        "rsi": 0.0,
        "ml_predict": "AWAITING_FEED"
    }
    for _sym in _configured_symbols
]


def notify_state_changed():
    """Triggers an immediate broadcast if active clients are connected."""
    if not active_connections:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_portfolio_update())
    except RuntimeError:
        pass


def start_ticker():
    """Starts the real-time KiteTicker WebSocket connection for market streaming."""
    global market_ticker, price_cache
    if market_ticker:
        try:
            market_ticker.stop()
        except Exception:
            pass

    # Resolve and register tokens dynamically via InstrumentMaster
    sym_list = [s.strip().replace(".NS", "") for s in settings.TRADING_SYMBOLS.split(",") if s.strip()]
    tokens = []
    for s in sym_list:
        tok = instrument_master.resolve_token(s)
        if tok:
            tokens.append(tok)
            price_cache.register_token_symbol(tok, s)

    if not broker._access_token or broker._access_token.startswith("fake_"):
        return
        
    try:
        market_ticker = MarketTicker(broker.api_key, broker._access_token)
        for p in global_positions:
            if p.get("instrument_token"): 
                t_int = int(p.get("instrument_token"))
                tokens.append(t_int)
                price_cache.register_token_symbol(t_int, p.get("tradingsymbol", ""))
        for h in global_holdings:
            if h.get("instrument_token"): 
                t_int = int(h.get("instrument_token"))
                tokens.append(t_int)
                price_cache.register_token_symbol(t_int, h.get("tradingsymbol", ""))
        
        # Subscribe all active watchlist symbols via broker quotes
        kite_symbols = [f"NSE:{s}" for s in sym_list]
        try:
            quotes = broker.get_quote(kite_symbols)
            for k_sym, q in quotes.items():
                if isinstance(q, dict) and "instrument_token" in q:
                    tok = int(q["instrument_token"])
                    tokens.append(tok)
                    clean = k_sym.replace("NSE:", "")
                    price_cache.register_token_symbol(tok, clean)
                    if "last_price" in q:
                        price_cache.update_symbol(clean, float(q["last_price"]))
        except Exception as q_err:
            logger.debug(f"Could not bulk-register tokens from quotes: {q_err}")

        if tokens:
            market_ticker.watchlist = list(set(tokens))

        def on_ticks(ticks):
            updated = False
            for tick in ticks:
                token = tick.get("instrument_token")
                if token and "last_price" in tick:
                    price_cache.update(token, float(tick["last_price"]))
                    updated = True
            try:
                from app.broker.candle_aggregator import aggregator
                aggregator.process_ticks(ticks)
            except Exception as e:
                logger.debug(f"Error aggregating live ticks: {e}")
            if updated:
                notify_state_changed()
                
        market_ticker.on_ticks_callback = on_ticks
        market_ticker.start(threaded=True)
        logger.info(f"KiteTicker started and subscribed to {len(market_ticker.watchlist)} live instruments.")
    except Exception as e:
        logger.error(f"Failed to start KiteTicker: {e}")


def sync_live_market_prices():
    """Keeps price cache strictly synced with genuine real-time market prices."""
    for item in current_watchlist_payload:
        s = item.get("symbol")
        ltp = item.get("ltp")
        if s and ltp and ltp > 0:
            clean = s.replace(".NS", "").strip()
            price_cache.update_symbol(clean, float(ltp))


def build_portfolio_payload() -> dict:
    global global_positions, global_holdings, global_available_margin
    try:
        pos_data = broker.get_positions()
        current_net_positions = pos_data.get("net", []) if pos_data else []
    except Exception:
        current_net_positions = global_positions

    position_manager.sync_with_broker_positions(current_net_positions)

    # Deduplicate and normalize symbols, enforce strictly positive quantities
    merged_positions = {}
    for p in current_net_positions:
        raw_sym = p.get("tradingsymbol", "")
        clean_sym = raw_sym.replace(".NS", "").strip()
        if not clean_sym:
            continue
        qty = abs(int(p.get("quantity", 0)))
        if qty == 0:
            continue
            
        avg_price = float(p.get("average_price", 0.0))
        if avg_price <= 0.0:
            avg_price = float(p.get("last_price", 0.0))
            
        token = p.get("instrument_token")
        last_price = float(p.get("last_price", 0.0))
        
        if clean_sym not in merged_positions:
            merged_positions[clean_sym] = {
                "symbol": clean_sym,
                "qty": qty,
                "avg_price": avg_price,
                "token": token,
                "last_price": last_price
            }
        else:
            prev = merged_positions[clean_sym]
            total_qty = prev["qty"] + qty
            if total_qty > 0 and prev["avg_price"] > 0 and avg_price > 0:
                merged_avg = (prev["qty"] * prev["avg_price"] + qty * avg_price) / total_qty
            else:
                merged_avg = prev["avg_price"] if prev["avg_price"] > 0 else avg_price
            prev["qty"] = total_qty
            prev["avg_price"] = round(merged_avg, 2)

    frontend_positions = []
    total_unrealized_pnl = 0.0
    for sym, item in merged_positions.items():
        qty = item["qty"]
        avg_price = item["avg_price"]
        token = item["token"]
        
        ltp = price_cache.get(token, 0.0) if token else 0.0
        if ltp == 0.0:
            ltp = price_cache.get_by_symbol(sym, 0.0)
        if ltp == 0.0:
            ltp = float(item.get("last_price", 0.0))
        if ltp == 0.0:
            ltp = avg_price
            
        pnl = (ltp - avg_price) * qty
        cost_basis = avg_price * qty
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
        total_unrealized_pnl += pnl

        tracked = position_manager.get_tracked_position(sym)
        sl_val = tracked.stop_loss if tracked else round(avg_price * 0.98, 2)
        tp_val = tracked.take_target if tracked else round(avg_price * 1.05, 2)

        frontend_positions.append({
            "symbol": sym,
            "qty": qty,
            "avg": round(avg_price, 2),
            "ltp": round(ltp, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "stop_loss": round(sl_val, 2),
            "take_target": round(tp_val, 2)
        })

    frontend_holdings = []
    for h in global_holdings:
        raw_sym = h.get("tradingsymbol", "")
        sym = raw_sym.replace(".NS", "").strip()
        token = h.get("instrument_token")
        qty = abs(int(h.get("quantity", 0)))
        avg_price = float(h.get("average_price", 0.0))
        
        ltp = price_cache.get(token, 0.0) if token else 0.0
        if ltp == 0.0:
            ltp = price_cache.get_by_symbol(sym, 0.0)
        if ltp == 0.0:
            ltp = float(h.get("last_price", 0.0))
        if ltp == 0.0:
            ltp = avg_price
            
        pnl = (ltp - avg_price) * qty
        frontend_holdings.append({
            "tradingsymbol": sym,
            "quantity": qty,
            "average_price": round(avg_price, 2),
            "last_price": round(ltp, 2),
            "pnl": round(pnl, 2),
            "instrument_token": token
        })

    updated_watchlist = []
    for item in current_watchlist_payload:
        w_item = dict(item)
        sym = w_item.get("symbol", "").replace(".NS", "").strip()
        live_ltp = price_cache.get_by_symbol(sym, 0.0)
        if live_ltp > 0:
            w_item["ltp"] = round(live_ltp, 2)
            prev_close = daily_prev_closes.get(sym) or w_item.get("prev_close", 0.0)
            if prev_close == 0.0:
                prev_close = live_ltp
            w_item["prev_close"] = prev_close
            w_item["change"] = round(((live_ltp - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
            if broker.is_authenticated():
                w_item["status"] = "ZERODHA_LIVE"
        updated_watchlist.append(w_item)

    _paper_metrics = paper_journal.calculate_metrics()
    _ml_summary = ml_monitor.get_metrics_summary()
    _chain_valid = audit_chain.verify_chain()

    return {
        "type": "market_update",
        "watchlist": updated_watchlist,
        "positions": frontend_positions,
        "holdings": frontend_holdings,
        "autonomous_trades": autonomous_trades_history,
        "autonomous_execution": settings.AUTONOMOUS_EXECUTION,
        "account_stats": {
            "margin": global_available_margin,
            "realized_pnl": round(position_manager.get_realized_pnl(), 2),
            "unrealized_pnl": round(total_unrealized_pnl, 2),
            "total_day_pnl": round(position_manager.get_realized_pnl() + total_unrealized_pnl, 2),
            "net_day_pnl": round(position_manager.get_realized_pnl() + total_unrealized_pnl, 2)
        },
        "emergency_stop_active": EMERGENCY_STOP_ACTIVE,
        "reconciliation": {
            "is_synced": reconciliation_engine.latest_report.is_synced if reconciliation_engine.latest_report else True,
            "discrepancies": reconciliation_engine.latest_report.total_discrepancies if reconciliation_engine.latest_report else 0,
            "critical_count": reconciliation_engine.latest_report.critical_count if reconciliation_engine.latest_report else 0
        },
        "ml_metrics": {
            "overall_accuracy": _ml_summary.get("overall_accuracy", 0.0),
            "rolling_accuracy_20": _ml_summary.get("rolling_accuracy_20", 0.0),
            "total_predictions": _ml_summary.get("total_predictions", len(ml_monitor.records)),
            "drift_detected": _ml_summary.get("prediction_drift", {}).get("drift_detected", False)
        },
        "paper_validation": {
            "verdict": _paper_metrics.get("validation_verdict", "IN_PROGRESS"),
            "days_completed": _paper_metrics.get("days_completed", 0),
            "sharpe_ratio": _paper_metrics.get("sharpe_ratio", 0.0),
            "max_drawdown_pct": _paper_metrics.get("max_drawdown_pct", 0.0),
            "net_pnl_after_fees": _paper_metrics.get("net_pnl_after_fees", 0.0)
        },
        "audit_chain": {
            "is_valid": _chain_valid,
            "last_hash": (audit_chain.last_hash[:16] + "...") if audit_chain.last_hash else "GENESIS"
        },
        "risk_metrics": {
            "sectors": risk_engine.get_sector_breakdown(
                AccountState(
                    available_margin=global_available_margin if global_available_margin > 0 else 500000.0,
                    open_positions={p.symbol: p.entry_price * p.quantity for p in position_manager.get_all_tracked().values() if p.is_active}
                )
            ),
            "max_sector_pct": risk_engine.config.max_sector_exposure_pct,
            "max_var_pct": risk_engine.config.max_portfolio_var_pct,
            "max_cvar_pct": risk_engine.config.max_portfolio_cvar_pct
        },
        "model_status": model_registry.get_status(),
        "unified_risk": unified_risk_center.evaluate_status(global_positions),
        "backend_ts": time.time()
    }


async def broadcast_portfolio_update():
    if not active_connections:
        return
        
    payload = json.dumps(build_portfolio_payload())
    dead_connections = []
    for connection in list(active_connections):
        try:
            await connection.send_text(payload)
        except Exception:
            dead_connections.append(connection)
            
    for dc in dead_connections:
        if dc in active_connections:
            active_connections.remove(dc)


async def portfolio_broadcast_loop():
    while True:
        try:
            sync_live_market_prices()
            await broadcast_portfolio_update()
        except Exception as e:
            logger.error(f"Error in portfolio broadcast loop: {e}")
        await asyncio.sleep(1.0)


def log_audit_event(event_type: str, trade_id: str, symbol: str, action: str, details: str):
    iso_now = datetime.now(timezone.utc).isoformat()
    chain_hash = None
    try:
        chain_hash = audit_chain.log_event(
            event_type=event_type,
            data={
                "trade_id": trade_id,
                "symbol": symbol,
                "action": action,
                "details": details,
                "timestamp": iso_now
            }
        )
    except Exception as e:
        logger.error(f"Failed to record in audit chain: {e}")

    db = SessionLocal()
    try:
        log = AuditLog(
            event_type=event_type,
            trade_id=trade_id,
            symbol=symbol,
            action=action,
            details=details,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
    finally:
        db.close()

    if active_connections:
        try:
            loop = asyncio.get_running_loop()
            audit_msg = json.dumps({
                "type": "audit_log",
                "log": {
                    "timestamp": iso_now,
                    "event_type": event_type,
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "action": action,
                    "details": details,
                    "chain_hash": chain_hash
                }
            })
            for connection in list(active_connections):
                loop.create_task(connection.send_text(audit_msg))
        except RuntimeError:
            pass


def sync_model_registry_outcome(
    symbol: str,
    exit_price: float,
    realized_pnl: float,
    exit_reason: str,
    trade_id: Optional[str] = None,
    ml_outcome: Optional[Any] = None
):
    global EMERGENCY_STOP_ACTIVE
    is_correct = ml_outcome.is_correct if ml_outcome and ml_outcome.is_correct is not None else (realized_pnl > 0)
    conf = ml_outcome.confidence if ml_outcome else 0.85
    reg_res = model_registry.record_trade_outcome(
        trade_id=trade_id,
        symbol=symbol,
        exit_price=exit_price,
        realized_pnl=realized_pnl,
        is_correct=is_correct,
        confidence=conf
    )
    if reg_res.get("critical_killswitch_tripped"):
        EMERGENCY_STOP_ACTIVE = True
        logger.critical(f"CRITICAL MODEL REGISTRY KILLSWITCH: {reg_res.get('reason')}")
        log_audit_event(
            "MODEL_KILLSWITCH",
            trade_id or f"reg_{symbol}",
            symbol,
            "HALT",
            f"ModelRegistry kill switch engaged: {reg_res.get('reason')}"
        )
        notify_state_changed()


# Modular Background Streaming & Analysis Workers
from app.trading.streaming_worker import (
    YFCandle,
    train_ml_models_startup,
    live_market_data_stream,
    periodic_reconciliation_loop,
    portfolio_broadcast_loop
)




@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    Base.metadata.create_all(bind=engine)
    
    # Recover state
    order_manager.recover_state()
    position_manager.recover_state()
    
    global global_holdings, global_positions, global_available_margin, market_ticker
    try:
        if broker._access_token or settings.TRADING_MODE == "DRY_RUN":
            try:
                global_holdings = broker.get_holdings() or []
                pos_data = broker.get_positions()
                global_positions = pos_data.get("net", []) if pos_data else []
                margin_data = broker.get_margins()
                if margin_data and "equity" in margin_data:
                    global_available_margin = margin_data["equity"].get("available", {}).get("live_balance", 0)
                
                start_ticker()
            except Exception as e:
                logger.error(f"Failed to fetch initial portfolio/start ticker: {e}")
    except Exception as e:
        logger.error(f"Lifespan initialization error: {e}")
    
    # Launch background tasks
    task = asyncio.create_task(live_market_data_stream())
    broadcast_task = asyncio.create_task(portfolio_broadcast_loop())
    reconcile_task = asyncio.create_task(periodic_reconciliation_loop())
    ml_train_task = asyncio.create_task(train_ml_models_startup())
    
    yield
    
    task.cancel()
    broadcast_task.cancel()
    reconcile_task.cancel()
    ml_train_task.cancel()
    if market_ticker:
        market_ticker.stop()


# Initialize FastAPI Application
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Import and Register Modular API Routers
from app.api import (
    auth_router,
    trades_router,
    portfolio_router,
    risk_router,
    ml_router,
    system_router
)

app.include_router(auth_router)
app.include_router(trades_router)
app.include_router(portfolio_router)
app.include_router(risk_router)
app.include_router(ml_router)
app.include_router(system_router)


# Root Web UI Endpoints
@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} in {settings.TRADING_MODE} mode"}


@app.get("/dashboard")
def get_dashboard():
    return FileResponse("app/static/index.html")


# Live WebSocket Endpoint for Frontend Streaming
@app.websocket("/ws/candidate-trades")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # Push initial snapshot immediately upon connection
        initial_payload = build_portfolio_payload()
        await websocket.send_text(json.dumps(initial_payload))
        
        for cand in candidate_cache.values():
            await websocket.send_text(json.dumps({"type": "candidate_trade", "candidate": cand}))
            
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)
    except Exception as e:
        logger.debug(f"WebSocket client error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)


# Exported function references for complete backward compatibility
from app.api.auth import login, set_auth_token, auth_callback, kite_auth_callback
from app.api.trades import handle_trade_action, close_trade_position, close_all_trade_positions
from app.api.portfolio import get_portfolio, optimize_portfolio_weights
from app.api.risk import get_risk_sectors, get_risk_var, get_risk_center_status, halt_risk_center, resume_risk_center
from app.api.ml import (
    get_ml_metrics, get_ml_predictions, record_manual_prediction, record_manual_outcome,
    get_model_registry_status, promote_challenger_model, rollback_champion_model, register_challenger_model
)
from app.api.system import (
    toggle_emergency_stop, get_system_status, run_manual_reconciliation, get_reconciliation_status,
    get_anomaly_status, get_paper_report, get_paper_report_markdown, record_paper_snapshot,
    verify_audit_chain, get_audit_chain, sync_instruments, get_audit_logs
)