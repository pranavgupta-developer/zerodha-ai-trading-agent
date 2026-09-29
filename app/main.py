from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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
from datetime import datetime
from app.trading.pipeline import TradingPipeline
from app.trading.strategy import EmaCrossoverRsiStrategy
from app.agent.service import AgentService
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler("app.log")])
logger = logging.getLogger(__name__)

active_connections: list[WebSocket] = []
candidate_cache: dict = {}
EMERGENCY_STOP_ACTIVE = False

def log_audit_event(event_type: str, trade_id: str, symbol: str, action: str, details: str):
    db = SessionLocal()
    try:
        log = AuditLog(
            event_type=event_type,
            trade_id=trade_id,
            symbol=symbol,
            action=action,
            details=details,
            timestamp=datetime.utcnow()
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
    finally:
        db.close()

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
    
    # You can add or remove Yahoo Finance symbols (e.g., '.NS' for NSE) here:
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
    display_symbols = {s: s.replace(".NS", "") for s in symbols}
    
    # Initialize the real pipeline
    strategy = EmaCrossoverRsiStrategy()
    agent_service = AgentService()
    # Using the global risk_engine and order_manager defined below (we can just reference them since they are global)
    

    last_broker_sync = 0
    cached_holdings = []
    cached_positions = []
    
    while True:
        try:
            # Sync broker data every 10 seconds to avoid rate limits
            if time.time() - last_broker_sync > 10:
                try:
                    cached_holdings = broker.get_holdings() or []
                    cached_positions_data = broker.get_positions()
                    cached_positions = cached_positions_data.get("net", []) if cached_positions_data else []
                except Exception as e:
                    logger.error(f"Failed to sync broker data: {e}")
                last_broker_sync = time.time()

            # Dynamically adding portfolio symbols here slowed down Yahoo Finance significantly,
            # so we keep the watchlist to the core symbols only.

            watchlist_payload = []
            
            # Fetch all symbols concurrently to prevent event-loop blocking
            tasks = [asyncio.to_thread(yf.download, sym, period="5d", interval="1m", progress=False) for sym in symbols]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            source_ts = time.time() # Timestamp when data was received from source
            
            for sym, result in zip(symbols, results):

                try:
                    if isinstance(result, Exception):
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
                
                    # Calculate daily change relative to the previous trading day's close
                    try:
                        last_date = df.index[-1].date()
                        prev_day_data = df[df.index.date < last_date]
                        if not prev_day_data.empty:
                            pc = prev_day_data['Close'].iloc[-1]
                            prev_close = float(pc.iloc[0]) if hasattr(pc, 'iloc') else float(pc)
                        else:
                            # Fallback to the very first candle in the 5d window
                            pc = df['Close'].iloc[0]
                            prev_close = float(pc.iloc[0]) if hasattr(pc, 'iloc') else float(pc)
                    except Exception:
                        prev_close = current_price
                    
                    change = ((current_price - prev_close) / prev_close) * 100 if prev_close else 0.0
                
                    snapshot = get_feature_snapshot(candles)
                    account_state = AccountState(available_margin=500000.0, unrealized_pnl=0.0, realized_pnl=0.0)
                
                    try:
                        kite_symbol = f"NSE:{display_symbols[sym]}"
                        quotes = broker.get_quote([kite_symbol])
                        quote_data = quotes.get(kite_symbol) if quotes else None
                    except Exception:
                        quote_data = None
                    
                    # Use real-time broker data for the UI if available (yfinance can be delayed)
                    if quote_data:
                        current_price = quote_data.get("last_price", current_price)
                        kite_prev_close = quote_data.get("ohlc", {}).get("close")
                        if kite_prev_close and kite_prev_close > 0:
                            change = ((current_price - kite_prev_close) / kite_prev_close) * 100
                
                    pipeline = TradingPipeline(strategy, agent_service, risk_engine, order_manager)
                    candidate_trade, order, msg = pipeline.process_tick(
                        symbol=display_symbols[sym],
                        candles=candles,
                        market_snapshot=snapshot,
                        indicators=snapshot,
                        account_state=account_state,
                        quote_data=quote_data
                    )
                
                    signal_str = candidate_trade.direction.name if candidate_trade else "HOLD"
                    if candidate_trade and candidate_trade.direction == SignalDirection.HOLD:
                        signal_str = "HOLD"
                    
                    watchlist_payload.append({
                        "symbol": display_symbols[sym],
                        "ltp": current_price,
                        "change": change,
                        "signal": signal_str,
                        "source_ts": source_ts
                    })
                
                    if candidate_trade and candidate_trade.direction != SignalDirection.HOLD:
                        trade_id = f"t{random.randint(1000, 9999)}"
                    
                        if order:
                            # Trade was autonomously executed by the pipeline
                            log_audit_event("ORDER_EVENT", trade_id, candidate_trade.symbol, "AUTONOMOUS", f"Broker ID: {order.broker_order_id} | {msg}")
                        else:
                            cand_dict = {
                                "id": trade_id,
                                "symbol": candidate_trade.symbol,
                                "action": candidate_trade.direction.name,
                                "reasoning": candidate_trade.reasoning,
                                "price": candidate_trade.entry_price
                            }
                            candidate_cache[trade_id] = cand_dict
                        
                            log_audit_event("SIGNAL", trade_id, cand_dict["symbol"], cand_dict["action"], f"AI Reasoning: {cand_dict['reasoning']} ({msg})")
                        
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
            # Broadcast market update
            if active_connections:
                try:
                    pos_list = cached_positions
                    holdings_list = cached_holdings
                    
                    quote_symbols = set()
                    for p in pos_list:
                        if p.get("quantity", 0) != 0 and p.get("tradingsymbol"):
                            quote_symbols.add(f"NSE:{p.get('tradingsymbol')}")
                    for h in holdings_list:
                        if h.get("tradingsymbol"):
                            quote_symbols.add(f"NSE:{h.get('tradingsymbol')}")
                            
                    portfolio_quotes = {}
                    if quote_symbols:
                        try:
                            portfolio_quotes = broker.get_quote(list(quote_symbols)) or {}
                        except Exception as e:
                            logger.error(f"Failed to fetch quotes for portfolio: {e}")
                    
                    frontend_positions = []
                    for p in pos_list:
                        if p.get("quantity", 0) != 0:
                            sym = p.get("tradingsymbol")
                            kite_sym = f"NSE:{sym}"
                            
                            ltp = 0.0
                            if kite_sym in portfolio_quotes:
                                ltp = portfolio_quotes[kite_sym].get("last_price", 0.0)
                            else:
                                for w in watchlist_payload:
                                    if w["symbol"] == sym:
                                        ltp = w["ltp"]
                                        break
                            
                            frontend_positions.append({
                                "symbol": sym,
                                "qty": p.get("quantity"),
                                "avg": p.get("average_price", 0.0),
                                "ltp": ltp
                            })
                            
                except Exception as e:
                    logger.error(f"Failed to process positions: {e}")
                    frontend_positions = []
                    
                try:
                    margin_data = broker.get_margins()
                    if margin_data and "equity" in margin_data:
                        available_margin = margin_data["equity"].get("available", {}).get("live_balance", 0)
                    else:
                        available_margin = 0
                except Exception:
                    available_margin = 0
                    
                for h in holdings_list:
                    sym = h.get("tradingsymbol")
                    kite_sym = f"NSE:{sym}"
                    if kite_sym in portfolio_quotes:
                        h["last_price"] = portfolio_quotes[kite_sym].get("last_price", h.get("last_price", 0.0))
                    else:
                        for w in watchlist_payload:
                            if w["symbol"] == sym:
                                h["last_price"] = w["ltp"]
                                break
                    
                backend_ts = time.time()
                for connection in active_connections:
                    try:
                        await connection.send_text(json.dumps({
                            "type": "market_update",
                            "watchlist": watchlist_payload,
                            "positions": frontend_positions,
                            "holdings": holdings_list,
                            "account_stats": {
                                "margin": available_margin,
                                "realized_pnl": 0 # Realized PNL calculation can be added later
                            },
                            "backend_ts": backend_ts
                        }))
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error in live market simulation: {e}")
            
        await asyncio.sleep(0.5) # Non-blocking poll every 0.5 seconds

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables
    Base.metadata.create_all(bind=engine)
    
    # Recover state
    order_manager.recover_state()
    
    task = asyncio.create_task(simulate_trades_stream())
    yield
    task.cancel()
    
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)
broker = BrokerAdapter()
risk_engine = RiskEngine(config=RiskConfig(check_market_hours=False))
order_manager = OrderManager(broker)

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
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)

class TradeActionReq(BaseModel):
    trade_id: str
    action: str

class TradeCloseReq(BaseModel):
    symbol: str
    quantity: int

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
        return {"status": "success", "trade_id": action.trade_id, "action": action.action, "message": "Rejected and discarded"}
        
    if action.action == "APPROVE":
        if EMERGENCY_STOP_ACTIVE:
            log_audit_event("RISK_DECISION", action.trade_id, symbol, "REJECT", "Emergency Stop is active")
            raise HTTPException(status_code=400, detail="Emergency Stop is active. No new orders allowed.")
            
        if not candidate:
            raise HTTPException(status_code=404, detail="Trade candidate not found in cache.")
            
        log_audit_event("USER_DECISION", action.trade_id, symbol, "APPROVE", "User approved the trade.")
            
        direction = SignalDirection.BUY if candidate["action"] == "BUY" else SignalDirection.SELL
        signal = Signal(
            symbol=candidate["symbol"],
            direction=direction,
            entry_price=candidate["price"],
            confidence=0.9,
            stop_loss=candidate["price"] * 0.98 if direction == SignalDirection.BUY else candidate["price"] * 1.02,
            take_target=candidate["price"] * 1.05 if direction == SignalDirection.BUY else candidate["price"] * 0.95,
            reason=candidate.get("reasoning", "")
        )
        
        # Mock account state
        account = AccountState(
            available_margin=500000.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0
        )
        
        qty = 1 # Smallest possible real order size
        
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
            raise HTTPException(status_code=400, detail=f"Risk Engine Rejected: {reason}")
            
        log_audit_event("RISK_DECISION", action.trade_id, symbol, "APPROVE", "Risk Engine Approved")
        
        try:
            order = order_manager.place_order(signal, qty)
            logger.info(f"Order placed successfully: {order.broker_order_id}")
            log_audit_event("ORDER_EVENT", action.trade_id, symbol, "SUBMITTED", f"Broker Order ID: {order.broker_order_id}")
            return {"status": "success", "trade_id": action.trade_id, "action": action.action, "broker_order_id": order.broker_order_id}
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            log_audit_event("ORDER_EVENT", action.trade_id, symbol, "FAILED", f"Order placement failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Order placement failed: {str(e)}")

@app.post("/api/v1/trades/close")
def close_trade_position(req: TradeCloseReq):
    global EMERGENCY_STOP_ACTIVE
    
    if EMERGENCY_STOP_ACTIVE:
        raise HTTPException(status_code=400, detail="Emergency Stop is active. Cannot place closing order.")
        
    symbol = req.symbol
    qty = req.quantity
    
    # To close a position, we take the opposite action.
    # E.g. If qty is positive (we are long), we SELL. If negative, we BUY.
    transaction_type = "SELL" if qty > 0 else "BUY"
    abs_qty = abs(qty)
    
    try:
        order_id = broker.place_order(
            symbol=symbol,
            transaction_type=transaction_type,
            quantity=abs_qty,
            price=0.0,
            order_type="MARKET",
            product="MIS"
        )
        logger.info(f"Closing order placed successfully for {symbol}: {order_id}")
        log_audit_event("ORDER_EVENT", f"close_{symbol}", symbol, "SUBMITTED", f"Broker Order ID: {order_id} (Close position)")
        return {"status": "success", "broker_order_id": order_id}
    except Exception as e:
        logger.error(f"Failed to close position for {symbol}: {e}")
        log_audit_event("ORDER_EVENT", f"close_{symbol}", symbol, "FAILED", f"Closing order failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to close position: {str(e)}")

@app.post("/api/v1/system/emergency-stop")
def toggle_emergency_stop():
    global EMERGENCY_STOP_ACTIVE
    EMERGENCY_STOP_ACTIVE = not EMERGENCY_STOP_ACTIVE
    return {"status": "success", "emergency_stop_active": EMERGENCY_STOP_ACTIVE}

@app.get("/api/v1/system/status")
def get_system_status():
    return {
        "emergency_stop_active": EMERGENCY_STOP_ACTIVE,
        "trading_mode": settings.TRADING_MODE
    }
