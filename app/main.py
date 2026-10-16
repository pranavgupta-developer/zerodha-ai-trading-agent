from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
import asyncio
import json
import random
import logging
import time
from app.core.config import settings
from app.broker.kite_adapter import BrokerAdapter
from app.db.database import engine, Base, SessionLocal
import app.db.models  # to register models
from app.db.models import AuditLog
from app.trading.risk_engine import RiskEngine, RiskConfig, AccountState
from app.trading.order_manager import OrderManager
from app.trading.signals import Signal, SignalDirection
from app.trading.position_manager import PositionManager, ExitReason
from datetime import datetime, timezone
from app.broker.ticker import MarketTicker

from app.trading.pipeline import TradingPipeline
from app.trading.strategy import EmaRsiVwapStrategy
from app.agent.service import AgentService
from app.trading.position_sizer import DynamicPositionSizer
from app.trading.reconciliation import ReconciliationEngine, ReconciliationReport
from app.security.anomaly_detector import AnomalyDetector
from app.trading.ml_monitor import MLMonitor, PredictionRecord
from app.trading.paper_report import PaperTradingJournal, DailySnapshot
from dataclasses import asdict
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler("app.log")])
logger = logging.getLogger(__name__)

active_connections: list[WebSocket] = []
candidate_cache: dict = {}
autonomous_trades_history: list = []
EMERGENCY_STOP_ACTIVE = False

import threading
import time

class ThreadSafePriceCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._token_cache = {}
        self._symbol_cache = {}
        self._token_to_symbol = {
            738561: "RELIANCE",
            2953217: "TCS",
            408065: "INFY",
            341249: "HDFCBANK",
            1270529: "ICICIBANK"
        }

    def register_token_symbol(self, token, symbol: str):
        try:
            token_int = int(token)
            clean_sym = symbol.upper().replace(".NS", "").replace("NSE:", "")
            with self._lock:
                self._token_to_symbol[token_int] = clean_sym
        except (ValueError, TypeError):
            pass

    def update(self, token, ltp: float):
        try:
            token_int = int(token)
        except (ValueError, TypeError):
            token_int = None
            
        with self._lock:
            if token_int is not None:
                self._token_cache[token_int] = {
                    "ltp": float(ltp),
                    "timestamp": time.time()
                }
                sym = self._token_to_symbol.get(token_int)
                if sym:
                    self._symbol_cache[sym] = float(ltp)

    def update_symbol(self, symbol: str, ltp: float):
        clean_sym = symbol.upper().replace(".NS", "").replace("NSE:", "")
        with self._lock:
            self._symbol_cache[clean_sym] = float(ltp)

    def get(self, token, default_ltp: float = 0.0) -> float:
        try:
            token_int = int(token)
        except (ValueError, TypeError):
            token_int = None
            
        with self._lock:
            if token_int is not None and token_int in self._token_cache:
                return self._token_cache[token_int]["ltp"]
            return default_ltp

    def get_by_symbol(self, symbol: str, default_ltp: float = 0.0) -> float:
        clean_sym = symbol.upper().replace(".NS", "").replace("NSE:", "")
        with self._lock:
            return self._symbol_cache.get(clean_sym, default_ltp)

price_cache = ThreadSafePriceCache()
global_holdings: list = []
global_positions: list = []
global_available_margin: float = 0.0
market_ticker = None

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
    global market_ticker, price_cache
    if market_ticker:
        try:
            market_ticker.stop()
        except:
            pass
            
    # Register default top tokens for symbol lookup
    price_cache.register_token_symbol(738561, "RELIANCE")
    price_cache.register_token_symbol(2953217, "TCS")
    price_cache.register_token_symbol(408065, "INFY")
    price_cache.register_token_symbol(341249, "HDFCBANK")
    price_cache.register_token_symbol(1270529, "ICICIBANK")

    if not broker._access_token or broker._access_token == "fake_token" or broker._access_token.startswith("fake_"):
        return
        
    try:
        market_ticker = MarketTicker(broker.api_key, broker._access_token)
        tokens = list(market_ticker.watchlist)
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
        
        if tokens:
            market_ticker.watchlist = list(set(tokens))

        def on_ticks(ticks):
            for tick in ticks:
                token = tick.get("instrument_token")
                if token and "last_price" in tick:
                    price_cache.update(token, float(tick["last_price"]))
                
        market_ticker.on_ticks_callback = on_ticks
        market_ticker.start(threaded=True)
    except Exception as e:
        logger.error(f"Failed to start KiteTicker: {e}")

DEFAULT_BASE_PRICES = {
    "TATASTEEL": 173.30,
    "MAXHEALTH": 881.50,
    "TCS": 2134.50,
    "ICICIBANK": 1338.40,
    "TMPV": 283.05,
    "INFY": 1012.70,
    "CIPLA": 1307.20,
    "INDIGO": 4804.50,
    "SUNPHARMA": 1761.00,
    "APOLLOHOSP": 8029.50,
    "HINDUNILVR": 1825.40,
    "TATACONSUM": 957.05,
    "BSE": 3330.80,
    "JSWSTEEL": 1170.40,
    "POWERGRID": 248.90,
    "LT": 3619.80,
    "M&M": 2811.00,
    "BHARTIARTL": 1770.00,
    "NESTLEIND": 1325.00,
    "TRENT": 2910.10,
    "BEL": 373.10,
    "SHRIRAMFIN": 932.30,
    "COALINDIA": 480.00,
    "SBILIFE": 1669.90,
    "KOTAKBANK": 442.05,
    "ADANIENT": 2629.00,
    "TECHM": 1451.20,
    "TITAN": 4394.40,
    "ADANIPORTS": 1755.70,
    "BAJFINANCE": 957.70,
    "MARUTI": 11320.00,
    "ITC": 257.35,
    "NTPC": 309.05,
    "HDFCBANK": 702.30,
    "AXISBANK": 1251.40,
    "JIOFIN": 213.85,
    "DRREDDY": 1232.70,
    "HDFCLIFE": 557.75,
    "HCLTECH": 1219.40,
    "BAJAJ-AUTO": 10065.00,
    "EICHERMOT": 7130.00,
    "ONGC": 219.45,
    "HINDALCO": 888.45,
    "ASIANPAINT": 2328.50,
    "SBIN": 941.00,
    "BAJAJFINSV": 1717.60,
    "RELIANCE": 2950.00,
    "ETERNAL": 323.05,
    "GRASIM": 2861.60,
    "ULTRACEMCO": 11200.00
}

# Pre-populate price_cache and current_watchlist_payload immediately on startup
for _sym, _price in DEFAULT_BASE_PRICES.items():
    price_cache.update_symbol(_sym, _price)

current_watchlist_payload: list = [
    {
        "symbol": _sym,
        "ltp": _price,
        "prev_close": _price,
        "change": 0.0,
        "signal": "HOLD",
        "status": "HEALTHY",
        "source_ts": time.time(),
        "rsi": 50.0,
        "ml_predict": "NEUTRAL"
    }
    for _sym, _price in DEFAULT_BASE_PRICES.items()
]

def simulate_live_price_ticks():
    """
    Keeps price cache synced with real prices from current watchlist.
    No artificial random jitter is applied so the system runs on pure real market data.
    """
    for item in current_watchlist_payload:
        s = item.get("symbol")
        ltp = item.get("ltp")
        if s and ltp and ltp > 0:
            price_cache.update_symbol(s.replace(".NS", "").strip(), float(ltp))

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
            avg_price = DEFAULT_BASE_PRICES.get(clean_sym, 100.0)
            
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
            ltp = item["last_price"]
        if ltp == 0.0:
            ltp = DEFAULT_BASE_PRICES.get(sym, avg_price)
            price_cache.update_symbol(sym, ltp)
            
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
            ltp = DEFAULT_BASE_PRICES.get(sym, avg_price)
            price_cache.update_symbol(sym, ltp)
            
        pnl = (ltp - avg_price) * qty
        frontend_holdings.append({
            "tradingsymbol": sym,
            "quantity": qty,
            "average_price": round(avg_price, 2),
            "last_price": round(ltp, 2),
            "pnl": round(pnl, 2),
            "instrument_token": token
        })

    # Dynamically update watchlist with latest prices
    updated_watchlist = []
    for item in current_watchlist_payload:
        w_item = dict(item)
        sym = w_item.get("symbol", "").replace(".NS", "").strip()
        live_ltp = price_cache.get_by_symbol(sym, 0.0)
        if live_ltp > 0:
            w_item["ltp"] = round(live_ltp, 2)
            prev_close = w_item.get("prev_close")
            if not prev_close or prev_close <= 0:
                prev_close = DEFAULT_BASE_PRICES.get(sym, live_ltp)
                w_item["prev_close"] = prev_close
            w_item["change"] = round(((live_ltp - prev_close) / prev_close) * 100, 2)
        updated_watchlist.append(w_item)

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
            "total_day_pnl": round(position_manager.get_realized_pnl(), 2),
            "net_day_pnl": round(position_manager.get_realized_pnl() + total_unrealized_pnl, 2)
        },
        "emergency_stop_active": EMERGENCY_STOP_ACTIVE,
        "reconciliation": {
            "is_synced": reconciliation_engine.latest_report.is_synced if reconciliation_engine.latest_report else True,
            "discrepancies": reconciliation_engine.latest_report.total_discrepancies if reconciliation_engine.latest_report else 0,
            "critical_count": reconciliation_engine.latest_report.critical_count if reconciliation_engine.latest_report else 0
        },
        "ml_metrics": {
            "overall_accuracy": ml_monitor.get_metrics_summary().get("overall_accuracy", 0.0),
            "rolling_accuracy_20": ml_monitor.calculate_rolling_accuracy(20),
            "total_predictions": len(ml_monitor.records),
            "drift_detected": ml_monitor.detect_prediction_drift().get("drift_detected", False)
        },
        "paper_validation": {
            "verdict": paper_journal.calculate_metrics().get("validation_verdict", "IN_PROGRESS"),
            "days_completed": paper_journal.calculate_metrics().get("days_completed", 0),
            "sharpe_ratio": paper_journal.calculate_metrics().get("sharpe_ratio", 0.0),
            "max_drawdown_pct": paper_journal.calculate_metrics().get("max_drawdown_pct", 0.0),
            "net_pnl_after_fees": paper_journal.calculate_metrics().get("net_pnl_after_fees", 0.0)
        },
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
            simulate_live_price_ticks()
            await broadcast_portfolio_update()
        except Exception as e:
            logger.error(f"Error in portfolio broadcast loop: {e}")
        await asyncio.sleep(1.0)

def log_audit_event(event_type: str, trade_id: str, symbol: str, action: str, details: str):
    db = SessionLocal()
    iso_now = datetime.now(timezone.utc).isoformat()
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

    # Immediate real-time broadcast of audit log to all connected browsers
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
                    "details": details
                }
            })
            for connection in list(active_connections):
                loop.create_task(connection.send_text(audit_msg))
        except RuntimeError:
            pass


class YFCandle:
    def __init__(self, c_open, c_high, c_low, c_close, c_volume):
        self.open = c_open
        self.high = c_high
        self.low = c_low
        self.close = c_close
        self.volume = c_volume

async def simulate_trades_stream():
    import yfinance as yf
    from app.utils.indicators import get_feature_snapshot
    from app.broker.market_status import get_market_status
    
    # Use the configurable list of symbols from the .env file (or defaults)
    symbols = [s.strip() for s in settings.TRADING_SYMBOLS.split(",") if s.strip()]
    display_symbols = {s: s.replace(".NS", "") for s in symbols}
    
    # Initialize the real pipeline
    strategy = EmaRsiVwapStrategy()
    agent_service = AgentService()
    # Using the global risk_engine and order_manager defined below (we can just reference them since they are global)
    

    global current_watchlist_payload
    
    # Cache for yfinance to avoid rate limits
    last_yf_fetch = 0
    yf_cache = {}
    
    while True:
        try:
            # Dynamically pull user's portfolio to monitor for automated trading
            portfolio_symbols = set()
            for h in global_holdings:
                sym = h.get("tradingsymbol")
                if sym:
                    portfolio_symbols.add(f"{sym}.NS")
            for p in global_positions:
                sym = p.get("tradingsymbol")
                if sym:
                    portfolio_symbols.add(f"{sym}.NS")
                    
            # Combine hardcoded watchlist with live portfolio
            # active_symbols = list(set(symbols) | portfolio_symbols)
            active_symbols = list(set(symbols)) # User wants to ONLY trade TATASTEEL
            display_symbols = {s: s.replace(".NS", "") for s in active_symbols}

            watchlist_payload = []
            
            # Fetch bulk quotes ONCE per loop to avoid Kite rate limits
            all_kite_symbols = [f"NSE:{display_symbols[s]}" for s in active_symbols]
            bulk_quotes = {}
            try:
                bulk_quotes = await asyncio.to_thread(broker.get_quote, all_kite_symbols)
                if bulk_quotes:
                    for k_sym, q_data in bulk_quotes.items():
                        if isinstance(q_data, dict):
                            clean_s = k_sym.replace("NSE:", "")
                            token = q_data.get("instrument_token")
                            ltp = q_data.get("last_price")
                            if token and clean_s:
                                price_cache.register_token_symbol(token, clean_s)
                            if ltp is not None:
                                price_cache.update_symbol(clean_s, float(ltp))
                                if token:
                                    price_cache.update(token, float(ltp))
            except Exception as e:
                logger.warning(f"Bulk quote fetch failed: {e}")

            # Fetch real market data in a single batch request
            current_time = time.time()
            if current_time - last_yf_fetch > 30 or not yf_cache:
                try:
                    batch_df = await asyncio.to_thread(
                        yf.download,
                        tickers=active_symbols,
                        period="1d",
                        interval="1m",
                        group_by="ticker",
                        progress=False
                    )
                    for sym in active_symbols:
                        try:
                            if len(active_symbols) == 1:
                                sym_df = batch_df
                            else:
                                sym_df = batch_df[sym] if sym in batch_df else None
                            if sym_df is not None and not sym_df.empty:
                                yf_cache[sym] = sym_df.dropna(how='all')
                        except Exception:
                            pass
                    last_yf_fetch = current_time
                except Exception as e:
                    logger.warning(f"Batch real market data download failed: {e}")
            
            # Map cached results
            results = [yf_cache.get(sym) for sym in active_symbols]
            source_ts = last_yf_fetch # Timestamp when real data was received
            
            for sym, result in zip(active_symbols, results):

                try:
                    if isinstance(result, BaseException) or result is None:
                        continue
                    
                    df = result
                    if df.empty:
                        continue
                
                    # Create candle objects
                    candles = []
                    # Ensure we handle pandas 2.0+ correctly where columns might be multiindex
                    for _, row in df.iterrows():
                        o = float(row['Open'].iloc[0]) if isinstance(row['Open'], (list, tuple, type(df))) or hasattr(row['Open'], 'iloc') else float(row['Open'])
                        h = float(row['High'].iloc[0]) if isinstance(row['High'], (list, tuple, type(df))) or hasattr(row['High'], 'iloc') else float(row['High'])
                        l = float(row['Low'].iloc[0]) if isinstance(row['Low'], (list, tuple, type(df))) or hasattr(row['Low'], 'iloc') else float(row['Low'])
                        c = float(row['Close'].iloc[0]) if isinstance(row['Close'], (list, tuple, type(df))) or hasattr(row['Close'], 'iloc') else float(row['Close'])
                        v = float(row['Volume'].iloc[0]) if isinstance(row['Volume'], (list, tuple, type(df))) or hasattr(row['Volume'], 'iloc') else float(row['Volume'])
                        candles.append(YFCandle(o, h, l, c, v))
                    
                    if not candles:
                        continue
                
                    current_price = candles[-1].close
                    prev_close = candles[-2].close if len(candles) >= 2 else current_price
                    
                    kite_symbol = f"NSE:{display_symbols[sym]}"
                    quote_data = bulk_quotes.get(kite_symbol) if bulk_quotes else None
                    
                    # Use real-time broker data for the UI if available
                    if quote_data:
                        current_price = quote_data.get("last_price", current_price)
                        kite_prev_close = quote_data.get("ohlc", {}).get("close")
                        if kite_prev_close and kite_prev_close > 0:
                            prev_close = kite_prev_close
                    
                    # Register live price into cache
                    price_cache.update_symbol(display_symbols[sym], current_price)

                    # Automated Position Exit check (Stop-Loss / Take-Profit / Trailing SL)
                    exit_event = position_manager.check_and_execute_exit(display_symbols[sym], current_price)
                    if exit_event:
                        ml_monitor.record_outcome(
                            symbol=exit_event.symbol,
                            exit_price=exit_event.exit_price,
                            realized_pnl=exit_event.pnl,
                            exit_reason=exit_event.reason.value
                        )
                        log_audit_event(
                            "POSITION_EXIT",
                            f"exit_{exit_event.symbol}",
                            exit_event.symbol,
                            exit_event.reason.value,
                            f"Triggered @ ₹{exit_event.exit_price:.2f} | P&L: ₹{exit_event.pnl:.2f} ({exit_event.pnl_pct:.2f}%) | Order: {exit_event.broker_order_id}"
                        )
                        notify_state_changed()
                        
                    change = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0
                
                    clean_sym = display_symbols[sym]
                    existing_pos = position_manager.get_tracked_position(clean_sym)
                    active_pos_map = {p.symbol: p.quantity * p.entry_price for p in position_manager.get_all_tracked().values()}
                    effective_margin = global_available_margin if global_available_margin > 0 else 500000.0
                    account_state = AccountState(available_margin=effective_margin, unrealized_pnl=0.0, realized_pnl=0.0, open_positions=active_pos_map)
                
                    snapshot = get_feature_snapshot(candles)
                
                    # Extract the actual timestamp of the latest market data tick/candle
                    latest_candle_time = None
                    try:
                        if quote_data and "timestamp" in quote_data:
                            latest_candle_time = quote_data["timestamp"]
                        else:
                            latest_candle_time = df.index[-1].to_pydatetime()
                    except Exception:
                        pass
                        
                    mkt_status = get_market_status(latest_tick_time=latest_candle_time)
                
                    if EMERGENCY_STOP_ACTIVE:
                        candidate_trade = None
                        order = None
                        msg = "Emergency stop active"
                    elif existing_pos:
                        candidate_trade = None
                        order = None
                        msg = f"Position already active for {clean_sym}"
                    elif mkt_status in ["CLOSED", "STALE"] and settings.TRADING_MODE != "DRY_RUN":
                        candidate_trade = None
                        order = None
                        msg = f"Market is {mkt_status}"
                    else:
                        pipeline = TradingPipeline(strategy, agent_service, risk_engine, order_manager, position_sizer, anomaly_detector=anomaly_detector)
                        candidate_trade, order, msg = await asyncio.to_thread(
                            pipeline.process_tick,
                            symbol=clean_sym,
                            candles=candles,
                            market_snapshot=snapshot,
                            indicators=snapshot,
                            account_state=account_state,
                            quote_data=quote_data
                        )
                        if msg and msg.startswith("ANOMALY_HALT"):
                            EMERGENCY_STOP_ACTIVE = True
                            log_audit_event("ANOMALY_HALT", f"anom_{clean_sym}", clean_sym, "HALT", msg)
                            notify_state_changed()
                
                    signal_str = candidate_trade.direction.name if candidate_trade else "HOLD"
                    if candidate_trade and candidate_trade.direction == SignalDirection.HOLD:
                        signal_str = "HOLD"
                    
                    # Generate mock ML prediction based on RSI and Signal for UI display
                    ml_predict = "NEUTRAL"
                    if signal_str == "BUY":
                        ml_predict = "BULLISH"
                    elif signal_str == "SELL":
                        ml_predict = "BEARISH"

                    # Append to watchlist payload
                    watchlist_payload.append({
                        "symbol": clean_sym,
                        "ltp": current_price,
                        "prev_close": prev_close,
                        "change": change,
                        "signal": signal_str,
                        "status": mkt_status,
                        "source_ts": source_ts,
                        "rsi": snapshot.get("rsi_14", 0.0) if snapshot else 0.0,
                        "ml_predict": ml_predict
                    })
                
                    if candidate_trade and candidate_trade.direction != SignalDirection.HOLD:
                        trade_id = f"t{random.randint(1000, 9999)}"
                    
                        if order:
                            # Trade was autonomously executed by the pipeline
                            log_audit_event("ORDER_EVENT", trade_id, candidate_trade.symbol, "AUTONOMOUS", f"Broker ID: {order.broker_order_id} | {msg}")
                            ml_monitor.record_prediction(
                                symbol=candidate_trade.symbol,
                                predicted_direction=candidate_trade.direction.name,
                                confidence=candidate_trade.confidence_score,
                                entry_price=candidate_trade.entry_price,
                                features=snapshot or {},
                                market_regime=MLMonitor.classify_regime(snapshot or {}, candidate_trade.entry_price),
                                trade_id=trade_id
                            )
                            position_manager.register_position(
                                symbol=candidate_trade.symbol,
                                direction=candidate_trade.direction,
                                quantity=candidate_trade.qty,
                                entry_price=candidate_trade.entry_price,
                                stop_loss=candidate_trade.stop_loss,
                                take_target=candidate_trade.take_target,
                                trailing_sl_pct=0.015,
                                broker_order_id=order.broker_order_id
                            )
                            exec_dict = {
                                "id": trade_id,
                                "symbol": candidate_trade.symbol,
                                "action": candidate_trade.direction.name,
                                "reasoning": candidate_trade.reasoning,
                                "price": candidate_trade.entry_price,
                                "stop_loss": candidate_trade.stop_loss,
                                "take_target": candidate_trade.take_target,
                                "qty": candidate_trade.qty,
                                "allocated_capital": candidate_trade.allocated_capital,
                                "risk_budget": candidate_trade.risk_budget,
                                "risk_pct": candidate_trade.risk_pct,
                                "sizing_rationale": candidate_trade.sizing_rationale,
                                "broker_order_id": order.broker_order_id,
                                "status": "AUTONOMOUSLY_EXECUTED",
                                "timestamp": datetime.now().strftime("%H:%M:%S")
                            }
                            autonomous_trades_history.insert(0, exec_dict)
                            if len(autonomous_trades_history) > 30:
                                autonomous_trades_history.pop()

                            if active_connections:
                                for connection in active_connections:
                                    try:
                                        await connection.send_text(json.dumps({
                                            "type": "autonomous_trade",
                                            "trade": exec_dict
                                        }))
                                    except Exception:
                                        pass

                            notify_state_changed()
                        elif not candidate_trade.approval_required:
                            log_audit_event("RISK_DECISION", trade_id, candidate_trade.symbol, "REJECT", f"Risk Engine Blocked Auto-Execution: {msg}")
                        else:
                            # Fallback if manual approval is ever enabled
                            already_pending = any(c.get("symbol") == candidate_trade.symbol for c in candidate_cache.values())
                            if not already_pending:
                                cand_dict = {
                                    "id": trade_id,
                                    "symbol": candidate_trade.symbol,
                                    "action": candidate_trade.direction.name,
                                    "reasoning": candidate_trade.reasoning,
                                    "price": candidate_trade.entry_price,
                                    "stop_loss": candidate_trade.stop_loss,
                                    "take_target": candidate_trade.take_target,
                                    "qty": candidate_trade.qty,
                                    "allocated_capital": candidate_trade.allocated_capital,
                                    "risk_budget": candidate_trade.risk_budget,
                                    "risk_pct": candidate_trade.risk_pct,
                                    "sizing_rationale": candidate_trade.sizing_rationale
                                }
                                candidate_cache[trade_id] = cand_dict
                            
                                log_audit_event("SIGNAL", trade_id, cand_dict["symbol"], cand_dict["action"], f"AI Reasoning: {cand_dict['reasoning']} ({msg}) | Sizing: {cand_dict.get('sizing_rationale')}")
                            
                                if active_connections:
                                    for connection in active_connections:
                                        try:
                                            await connection.send_text(json.dumps({
                                                "type": "candidate_trade",
                                                "candidate": cand_dict
                                            }))
                                        except Exception:
                                            pass
                                


                except Exception as e:
                    logger.error(f"Error processing symbol {sym}: {e}")
                    continue
            current_watchlist_payload = watchlist_payload
            await broadcast_portfolio_update()
        except Exception as e:
            logger.error(f"Error in live market simulation: {e}")
            
        await asyncio.sleep(1.0) # Non-blocking poll every 0.1 seconds

async def periodic_reconciliation_loop():
    while True:
        try:
            await asyncio.sleep(60.0)
            report = await asyncio.to_thread(reconciliation_engine.run_reconciliation, True)
            if not report.is_synced:
                logger.warning(f"[RECONCILIATION] Discrepancies detected: {report.total_discrepancies}")
                log_audit_event(
                    "RECONCILIATION_ALERT",
                    f"rec_{int(report.timestamp)}",
                    "PORTFOLIO",
                    "MISMATCH",
                    f"Auto-audit found {report.total_discrepancies} mismatches ({report.critical_count} critical). Auto-synced: {report.auto_resolved}"
                )
                notify_state_changed()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic reconciliation loop: {e}")

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
    
    task = asyncio.create_task(simulate_trades_stream())
    broadcast_task = asyncio.create_task(portfolio_broadcast_loop())
    reconcile_task = asyncio.create_task(periodic_reconciliation_loop())
    yield
    task.cancel()
    broadcast_task.cancel()
    reconcile_task.cancel()
    if market_ticker:
        market_ticker.stop()
    
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
broker = BrokerAdapter()
risk_engine = RiskEngine(config=RiskConfig(check_market_hours=False))
order_manager = OrderManager(broker)
position_manager = PositionManager(broker=broker)
position_sizer = DynamicPositionSizer()
reconciliation_engine = ReconciliationEngine(broker=broker, position_manager=position_manager, order_manager=order_manager)
anomaly_detector = AnomalyDetector()
ml_monitor = MLMonitor()
paper_journal = PaperTradingJournal()
recent_order_timestamps: list[float] = []

app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME} in {settings.TRADING_MODE} mode"}

@app.get("/dashboard")
def get_dashboard():
    """Returns the main trading dashboard UI."""
    return FileResponse("app/static/index.html")

@app.get("/api/v1/auth/login")
def login():
    """
    Returns the Kite Connect login URL to which the user should be redirected.
    """
    return {"login_url": broker.get_login_url()}

@app.get("/api/v1/auth/callback")
def auth_callback(request_token: str, action: Optional[str] = None, type: Optional[str] = None, status: Optional[str] = None):
    """
    Callback endpoint for Kite Connect redirect.
    Exchanges the request_token for an access_token.
    """
    try:
        session_data = broker.generate_session(request_token)
        # TODO: Store session_data["access_token"] securely at rest (e.g., SQLite / Encrypted file)
        
        # Refresh holdings and positions with new token
        global global_holdings, global_positions, global_available_margin
        try:
            global_holdings = broker.get_holdings() or []
            pos_data = broker.get_positions()
            global_positions = pos_data.get("net", []) if pos_data else []
            margin_data = broker.get_margins()
            if margin_data and "equity" in margin_data:
                global_available_margin = margin_data["equity"].get("available", {}).get("live_balance", 0)
            
            start_ticker()
        except Exception as e:
            logger.error(f"Failed to fetch portfolio after auth: {e}")
            
        return {"status": "success", "message": "Authenticated successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/auth/kite/callback")
def kite_auth_callback(request_token: str, action: Optional[str] = None, type: Optional[str] = None, status: Optional[str] = None):
    """
    Alias endpoint for Kite Connect redirect when configured directly in the Kite Developer console.
    """
    return auth_callback(request_token, action, type, status)

@app.post("/api/v1/instruments/sync")
def sync_instruments():
    """
    Fetches the instrument master from Kite and stores it in the database.
    """
    from app.broker.instrument_master import instrument_master
    from app.db.database import SessionLocal
    
    db = SessionLocal()
    try:
        instrument_master.fetch_and_store_instruments(broker, db)
        return {"status": "success", "message": "Instruments synchronized successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.websocket("/ws/candidate-trades")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        # Push initial data immediately so the UI populates on first render
        await websocket.send_text(json.dumps(build_portfolio_payload()))
    except Exception:
        pass
        
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)

class TradeActionReq(BaseModel):
    trade_id: str
    action: str

class TradeCloseReq(BaseModel):
    symbol: str
    quantity: int

@app.get("/api/v1/portfolio")
def get_portfolio():
    """Returns current live portfolio, watchlist, and account statistics."""
    return build_portfolio_payload()

@app.get("/api/v1/audit-logs")
def get_audit_logs():
    db = SessionLocal()
    try:
        logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50).all()
        return {"logs": [{"timestamp": log.timestamp.isoformat(), "event_type": log.event_type, "trade_id": log.trade_id, "symbol": log.symbol, "action": log.action, "details": log.details} for log in logs]}
    finally:
        db.close()


@app.post("/api/v1/trades/action")
def handle_trade_action(action: TradeActionReq):
    global EMERGENCY_STOP_ACTIVE
    
    candidate = candidate_cache.get(action.trade_id)
    symbol = candidate["symbol"] if candidate else ""
    
    if action.action == "REJECT":
        logger.info(f"Trade {action.trade_id} rejected by user.")
        log_audit_event("USER_DECISION", action.trade_id, symbol, "REJECT", "User rejected the trade.")
        notify_state_changed()
        return {"status": "success", "trade_id": action.trade_id, "action": action.action, "message": "Rejected and discarded"}
        
    if action.action == "APPROVE":
        if EMERGENCY_STOP_ACTIVE:
            log_audit_event("RISK_DECISION", action.trade_id, symbol, "REJECT", "Emergency Stop is active")
            notify_state_changed()
            raise HTTPException(status_code=400, detail="Emergency Stop is active. No new orders allowed.")
            
        if not candidate:
            raise HTTPException(status_code=404, detail="Trade candidate not found in cache.")
            
        log_audit_event("USER_DECISION", action.trade_id, symbol, "APPROVE", "User approved the trade.")
            
        direction = SignalDirection.BUY if candidate["action"] == "BUY" else SignalDirection.SELL
        sl_candidate = candidate.get("stop_loss") or (candidate["price"] * 0.98 if direction == SignalDirection.BUY else candidate["price"] * 1.02)
        tp_candidate = candidate.get("take_target") or (candidate["price"] * 1.05 if direction == SignalDirection.BUY else candidate["price"] * 0.95)
        signal = Signal(
            symbol=candidate["symbol"],
            direction=direction,
            entry_price=candidate["price"],
            confidence=0.9,
            stop_loss=round(sl_candidate, 2),
            take_target=round(tp_candidate, 2),
            reason=candidate.get("reasoning", "")
        )
        
        # Account state using live available margin
        effective_margin = global_available_margin if global_available_margin > 0 else 500000.0
        account = AccountState(
            available_margin=effective_margin,
            unrealized_pnl=0.0,
            realized_pnl=0.0
        )
        
        # Dynamically size quantity based on volatility & risk budget
        qty = candidate.get("qty")
        if not qty or qty <= 0:
            alloc = position_sizer.calculate_allocation(
                symbol=candidate["symbol"],
                entry_price=candidate["price"],
                stop_loss=sl_candidate,
                account_equity=effective_margin,
                confidence=0.9,
                available_margin=effective_margin
            )
            qty = alloc.quantity
        
        try:
            kite_symbol = f"NSE:{symbol}"
            quotes = broker.get_quote([kite_symbol])
            quote_data = quotes.get(kite_symbol) if quotes else None
        except Exception:
            quote_data = None
            
        is_approved, reason = risk_engine.validate_signal(signal, account, qty, quote_data)
        
        if not is_approved:
            logger.warning(f"Risk Engine rejected trade {action.trade_id}: {reason}")
            log_audit_event("RISK_DECISION", action.trade_id, symbol, "REJECT", f"Risk Engine Rejected: {reason}")
            notify_state_changed()
            raise HTTPException(status_code=400, detail=f"Risk Engine Rejected: {reason}")
            
        log_audit_event("RISK_DECISION", action.trade_id, symbol, "APPROVE", "Risk Engine Approved")
        
        # Anomaly Detection Safeguard
        opm = float(len([t for t in recent_order_timestamps if time.time() - t <= 60.0]))
        order_val = float(qty * signal.entry_price)
        order_pct = min(1.0, order_val / max(effective_margin, 1000.0))
        curr_val = float(account.open_positions.get(symbol, 0.0))
        conc_pct = min(1.0, (curr_val + order_val) / max(effective_margin, 1000.0))
        anom = anomaly_detector.evaluate(opm, order_pct, conc_pct, signal.confidence, 150.0)
        if anom.get("halt_trading"):
            EMERGENCY_STOP_ACTIVE = True
            log_audit_event("ANOMALY_HALT", action.trade_id, symbol, "HALT", f"Manual approval halted by AnomalyDetector (score: {anom.get('anomaly_score', 0):.4f})")
            notify_state_changed()
            raise HTTPException(status_code=400, detail="CRITICAL ANOMALY: Order blocked and Emergency Stop engaged.")

        try:
            order = order_manager.place_order(signal, qty)
            recent_order_timestamps.append(time.time())
            logger.info(f"Order placed successfully: {order.broker_order_id}")
            ml_monitor.record_prediction(
                symbol=symbol,
                predicted_direction=direction.name,
                confidence=signal.confidence,
                entry_price=signal.entry_price,
                features={"rsi_14": 50.0, "atr_14": 0.0},
                trade_id=action.trade_id
            )
            position_manager.register_position(
                symbol=symbol,
                direction=direction,
                quantity=qty,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_target=signal.take_target,
                trailing_sl_pct=0.015,
                broker_order_id=order.broker_order_id
            )
            log_audit_event("ORDER_EVENT", action.trade_id, symbol, "SUBMITTED", f"Broker Order ID: {order.broker_order_id}")
            notify_state_changed()
            return {"status": "success", "trade_id": action.trade_id, "action": action.action, "broker_order_id": order.broker_order_id}
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            log_audit_event("ORDER_EVENT", action.trade_id, symbol, "FAILED", f"Order placement failed: {str(e)}")
            notify_state_changed()
            raise HTTPException(status_code=500, detail=f"Order placement failed: {str(e)}")

@app.post("/api/v1/trades/close")
def close_trade_position(req: TradeCloseReq):
    symbol = req.symbol
    try:
        current_ltp = price_cache.get_by_symbol(symbol, 0.0)
        event = position_manager.manual_square_off(symbol, current_price=current_ltp)
        if event:
            ml_monitor.record_outcome(
                symbol=symbol,
                exit_price=event.exit_price,
                realized_pnl=event.pnl,
                exit_reason=event.reason.value,
                trade_id=f"close_{symbol}"
            )
        broker_order_id = event.broker_order_id if event else None
        logger.info(f"Closing position manually for {symbol}: order={broker_order_id}")
        log_audit_event(
            "ORDER_EVENT",
            f"close_{symbol}",
            symbol,
            "SUBMITTED",
            f"Broker Order ID: {broker_order_id} (Manual square off)"
        )
        notify_state_changed()
        return {"status": "success", "broker_order_id": broker_order_id, "pnl": event.pnl if event else 0.0}
    except Exception as e:
        logger.error(f"Failed to close position for {symbol}: {e}")
        log_audit_event("ORDER_EVENT", f"close_{symbol}", symbol, "FAILED", f"Closing order failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to close position: {str(e)}")

@app.post("/api/v1/trades/close-all")
def close_all_trade_positions():
    try:
        closed = []
        tracked = list(position_manager.get_all_tracked().values())
        for pos in tracked:
            current_ltp = price_cache.get_by_symbol(pos.symbol, 0.0)
            event = position_manager.manual_square_off(pos.symbol, current_price=current_ltp)
            if event:
                ml_monitor.record_outcome(
                    symbol=pos.symbol,
                    exit_price=event.exit_price,
                    realized_pnl=event.pnl,
                    exit_reason=event.reason.value
                )
                closed.append({
                    "symbol": pos.symbol,
                    "broker_order_id": event.broker_order_id,
                    "pnl": event.pnl
                })
                log_audit_event(
                    "ORDER_EVENT",
                    f"close_all_{pos.symbol}",
                    pos.symbol,
                    "SUBMITTED",
                    f"Broker Order ID: {event.broker_order_id} (Close-all square off)"
                )
        notify_state_changed()
        return {"status": "success", "closed_positions": closed}
    except Exception as e:
        logger.error(f"Failed to close all positions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to close all positions: {str(e)}")

@app.post("/api/v1/system/emergency-stop")
def toggle_emergency_stop():
    global EMERGENCY_STOP_ACTIVE
    EMERGENCY_STOP_ACTIVE = not EMERGENCY_STOP_ACTIVE
    notify_state_changed()
    return {"status": "success", "emergency_stop_active": EMERGENCY_STOP_ACTIVE}

@app.get("/api/v1/system/status")
def get_system_status():
    return {
        "emergency_stop_active": EMERGENCY_STOP_ACTIVE,
        "trading_mode": settings.TRADING_MODE,
        "autonomous_execution": settings.AUTONOMOUS_EXECUTION
    }

@app.post("/api/v1/system/reconcile")
def run_manual_reconciliation():
    """Manually triggers an independent audit and reconciliation against Zerodha broker state."""
    report = reconciliation_engine.run_reconciliation(auto_sync=True)
    if not report.is_synced:
        log_audit_event(
            "RECONCILIATION_ALERT",
            f"rec_{int(report.timestamp)}",
            "PORTFOLIO",
            "MISMATCH",
            f"Manual audit found {report.total_discrepancies} mismatches ({report.critical_count} critical). Auto-synced: {report.auto_resolved}"
        )
    notify_state_changed()
    return {
        "status": "success",
        "report": report.model_dump()
    }

@app.get("/api/v1/system/reconciliation/status")
def get_reconciliation_status():
    """Fetches the latest reconciliation report and quarantined count."""
    report = reconciliation_engine.latest_report
    if not report:
        report = reconciliation_engine.run_reconciliation(auto_sync=False)
    return {
        "report": report.model_dump(),
        "quarantined_count": len(reconciliation_engine.quarantined_payloads)
    }

@app.get("/api/v1/system/anomaly/status")
def get_anomaly_status():
    """Returns anomaly detector state and current runtime risk metrics."""
    opm = len([t for t in recent_order_timestamps if time.time() - t <= 60.0])
    return {
        "is_fitted": anomaly_detector.is_fitted,
        "current_orders_per_minute": opm,
        "emergency_stop_active": EMERGENCY_STOP_ACTIVE
    }

# ==========================================
# ML Performance & Feedback Monitoring Endpoints
# ==========================================

class ManualPredictionReq(BaseModel):
    symbol: str
    predicted_direction: str
    confidence: float
    entry_price: float
    features: Optional[dict] = None
    market_regime: Optional[str] = None
    trade_id: Optional[str] = None

class ManualOutcomeReq(BaseModel):
    symbol: str
    exit_price: float
    realized_pnl: float
    exit_reason: str
    trade_id: Optional[str] = None

@app.get("/api/v1/ml/metrics")
def get_ml_metrics():
    """Returns comprehensive ML performance metrics, rolling accuracy, calibration and drift."""
    return ml_monitor.get_metrics_summary()

@app.get("/api/v1/ml/predictions")
def get_ml_predictions(limit: int = 50):
    """Returns recent prediction records with linked execution outcomes."""
    return [asdict(r) for r in ml_monitor.records[-limit:]]

@app.post("/api/v1/ml/record")
def record_manual_prediction(req: ManualPredictionReq):
    rec = ml_monitor.record_prediction(
        symbol=req.symbol,
        predicted_direction=req.predicted_direction,
        confidence=req.confidence,
        entry_price=req.entry_price,
        features=req.features or {},
        market_regime=req.market_regime,
        trade_id=req.trade_id
    )
    return {"status": "success", "prediction": asdict(rec)}

@app.post("/api/v1/ml/outcome")
def record_manual_outcome(req: ManualOutcomeReq):
    rec = ml_monitor.record_outcome(
        symbol=req.symbol,
        exit_price=req.exit_price,
        realized_pnl=req.realized_pnl,
        exit_reason=req.exit_reason,
        trade_id=req.trade_id
    )
    if not rec:
        raise HTTPException(status_code=404, detail=f"No pending prediction found for symbol {req.symbol}")
    return {"status": "success", "outcome": asdict(rec)}

# ==========================================
# 3-7 Day Paper Trading Validation Endpoints
# ==========================================

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

@app.get("/api/v1/system/paper-report")
def get_paper_report():
    """Returns multi-day paper trading journal metrics and historical daily snapshots."""
    return {
        "metrics": paper_journal.calculate_metrics(),
        "snapshots": [asdict(s) for s in paper_journal.daily_snapshots]
    }

@app.get("/api/v1/system/paper-report/markdown")
def get_paper_report_markdown():
    """Generates formatted executive Markdown validation report."""
    return {
        "markdown": paper_journal.generate_markdown_report()
    }

@app.post("/api/v1/system/paper-report/snapshot")
def record_paper_snapshot(req: PaperSnapshotReq):
    snap = paper_journal.record_daily_snapshot(
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




if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )