import asyncio
import time
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd
from app.core.config import settings
from app.trading.signals import SignalDirection

logger = logging.getLogger(__name__)


class YFCandle:
    """Lightweight adapter representing a price candle with dict and attribute access."""
    def __init__(self, c_open, c_high, c_low, c_close, c_volume):
        self.open = float(c_open)
        self.high = float(c_high)
        self.low = float(c_low)
        self.close = float(c_close)
        self.volume = float(c_volume)
        
    def __getitem__(self, item):
        return getattr(self, item)
        
    def get(self, item, default=None):
        return getattr(self, item, default)


async def train_ml_models_startup():
    """
    Trains XGBoost, Random Forest, and Regressors on real historical data on startup.
    Runs asynchronously during server lifespan boot.
    """
    import app.main as m
    import yfinance as yf
    
    symbols = [s.strip().replace(".NS", "") for s in settings.TRADING_SYMBOLS.split(",") if s.strip()]
    for sym in symbols:
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
                m.ml_engine.train_and_evaluate(sym, df_clean)
                logger.info(f"Startup ML models trained for {sym} (Classifier: {m.ml_engine.best_model_name}, Regressor: {m.ml_engine.best_regressor_name})")
        except Exception as e:
            logger.debug(f"Startup ML training for {sym}: {e}")


async def periodic_reconciliation_loop():
    """
    Periodic background reconciliation worker.
    Audits internal tracked positions against broker state every 60 seconds to detect discrepancies.
    """
    import app.main as m
    
    while True:
        try:
            await asyncio.sleep(60.0)
            report = await asyncio.to_thread(m.reconciliation_engine.run_reconciliation, True)
            if not report.is_synced:
                logger.warning(f"[RECONCILIATION] Discrepancies detected: {report.total_discrepancies}")
                m.log_audit_event(
                    "RECONCILIATION_ALERT",
                    f"rec_{int(report.timestamp)}",
                    "PORTFOLIO",
                    "MISMATCH",
                    f"Auto-audit found {report.total_discrepancies} mismatches ({report.critical_count} critical). Auto-synced: {report.auto_resolved}"
                )
                m.notify_state_changed()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in periodic reconciliation loop: {e}")


async def portfolio_broadcast_loop():
    """
    Continuous 1Hz broadcast worker.
    Pushes real-time synced portfolio, metrics, and risk status to connected WebSocket clients.
    """
    import app.main as m
    
    while True:
        try:
            m.sync_live_market_prices()
            await m.broadcast_portfolio_update()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in portfolio broadcast loop: {e}")
        await asyncio.sleep(1.0)


async def live_market_data_stream():
    """
    Core realtime market processing loop.
    Polls real Zerodha/market quotes, aggregates live candles, runs ML inference, and executes pipeline.
    """
    import app.main as m
    import yfinance as yf
    from app.utils.indicators import get_feature_snapshot
    from app.broker.market_status import get_market_status
    from app.broker.candle_aggregator import aggregator
    from app.utils.market_utils import is_market_open

    symbols = [s.strip() for s in settings.TRADING_SYMBOLS.split(",") if s.strip()]
    last_auth_warn = 0.0
    last_yf_fetch = 0.0
    yf_cache: dict = {}
    last_kite_hist_fetch: dict = {}

    while True:
        try:
            active_symbols = list(set(symbols))
            display_symbols = {s: s.replace(".NS", "") for s in active_symbols}
            
            is_zerodha_live = m.broker.is_authenticated()
            if not is_zerodha_live:
                now_ts = time.time()
                if now_ts - last_auth_warn > 300.0:
                    logger.info("[ZERODHA LIVE FEED] Waiting for Zerodha authentication. Set KITE_ACCESS_TOKEN or login.")
                    last_auth_warn = now_ts
                
                watchlist_payload = [
                    {
                        "symbol": display_symbols[s],
                        "ltp": m.price_cache.get_by_symbol(display_symbols[s], 0.0),
                        "prev_close": m.daily_prev_closes.get(display_symbols[s], 0.0),
                        "change": 0.0,
                        "signal": "HOLD",
                        "status": "ZERODHA_AUTH_REQUIRED",
                        "source_ts": time.time(),
                        "rsi": 0.0,
                        "ml_predict": "AWAITING_AUTH"
                    }
                    for s in active_symbols
                ]
                m.current_watchlist_payload = watchlist_payload
                await asyncio.sleep(2.0)
                continue
                
            if not m.market_ticker:
                m.start_ticker()

            all_kite_symbols = [f"NSE:{display_symbols[s]}" for s in active_symbols]
            bulk_quotes = {}
            try:
                bulk_quotes = await asyncio.to_thread(m.broker.get_quote, all_kite_symbols)
                if bulk_quotes:
                    for k_sym, q_data in bulk_quotes.items():
                        if isinstance(q_data, dict):
                            clean_s = k_sym.replace("NSE:", "")
                            token = q_data.get("instrument_token")
                            ltp = q_data.get("last_price")
                            if token and clean_s:
                                m.price_cache.register_token_symbol(token, clean_s)
                            if ltp is not None:
                                m.price_cache.update_symbol(clean_s, float(ltp))
                                if token:
                                    m.price_cache.update(token, float(ltp))
            except Exception as e:
                logger.debug(f"Error fetching real bulk quotes: {e}")

            watchlist_payload = []
            source_ts = time.time()

            for sym in active_symbols:
                clean_sym = display_symbols[sym]
                try:
                    quote_data = bulk_quotes.get(f"NSE:{clean_sym}")
                    current_price = 0.0
                    prev_close = 0.0

                    if quote_data and isinstance(quote_data, dict):
                        current_price = float(quote_data.get("last_price", 0.0))
                        ohlc = quote_data.get("ohlc", {})
                        if isinstance(ohlc, dict):
                            prev_close = float(ohlc.get("close", 0.0))
                            if prev_close > 0.0:
                                m.daily_prev_closes[clean_sym] = prev_close

                    if current_price <= 0.0:
                        current_price = m.price_cache.get_by_symbol(clean_sym, 0.0)
                    if prev_close <= 0.0:
                        prev_close = m.daily_prev_closes.get(clean_sym, 0.0)

                    # Build Candle History
                    candles = []
                    token = m.instrument_master.resolve_token(clean_sym)
                    if token:
                        agg_candles = aggregator.get_recent_candles(token, interval='1m', limit=60)
                        if agg_candles and len(agg_candles) >= 5:
                            candles = agg_candles

                    if not candles and token and is_zerodha_live:
                        last_fetch = last_kite_hist_fetch.get(clean_sym, 0.0)
                        if source_ts - last_fetch > 30.0:
                            try:
                                to_d = datetime.now()
                                from_d = to_d - timedelta(days=2)
                                raw_hist = await asyncio.to_thread(
                                    m.broker.get_historical_data,
                                    instrument_token=token,
                                    from_date=from_d,
                                    to_date=to_d,
                                    interval="minute"
                                )
                                if raw_hist:
                                    for h_bar in raw_hist:
                                        candles.append(YFCandle(h_bar["open"], h_bar["high"], h_bar["low"], h_bar["close"], h_bar["volume"]))
                                    m.global_candles_cache[clean_sym] = candles
                                    last_kite_hist_fetch[clean_sym] = source_ts
                            except Exception as h_err:
                                logger.debug(f"Zerodha historical data fetch for {clean_sym}: {h_err}")
                                last_kite_hist_fetch[clean_sym] = source_ts
                        if not candles and clean_sym in m.global_candles_cache:
                            candles = list(m.global_candles_cache[clean_sym])

                    if not candles:
                        if source_ts - last_yf_fetch > 15.0 or not yf_cache:
                            try:
                                batch_df = await asyncio.to_thread(
                                    yf.download,
                                    tickers=active_symbols,
                                    period="1d",
                                    interval="1m",
                                    progress=False,
                                    group_by="ticker"
                                )
                                if not batch_df.empty:
                                    yf_cache = {}
                                    for s_item in active_symbols:
                                        try:
                                            s_df = batch_df[s_item] if len(active_symbols) > 1 else batch_df
                                            if not s_df.empty and "Close" in s_df:
                                                yf_cache[s_item] = s_df.dropna()
                                        except Exception:
                                            pass
                                    last_yf_fetch = source_ts
                            except Exception as yf_err:
                                logger.debug(f"YFinance fallback batch download error: {yf_err}")
                                last_yf_fetch = source_ts

                        s_df = yf_cache.get(sym)
                        if s_df is not None and not s_df.empty:
                            candles = [
                                YFCandle(row["Open"], row["High"], row["Low"], row["Close"], row.get("Volume", 0))
                                for _, row in s_df.tail(60).iterrows()
                            ]
                            if current_price <= 0.0 and len(candles) > 0:
                                current_price = float(candles[-1].close)
                                m.price_cache.update_symbol(clean_sym, current_price)

                    if current_price <= 0.0:
                        continue

                    # Enforce Market Hours (09:15 - 15:30 IST Mon-Fri)
                    market_open = is_market_open() if settings.CHECK_MARKET_HOURS else True

                    # Evaluate Active Position Exits only during live market hours
                    if market_open:
                        exit_event = m.position_manager.check_and_execute_exit(clean_sym, current_price)
                        if exit_event:
                            logger.info(f"[POSITION MANAGER] Exit triggered for {clean_sym} on real price ₹{current_price:.2f}: {exit_event.reason.name} (P&L: ₹{exit_event.pnl:.2f})")
                            m.sync_model_registry_outcome(
                                symbol=clean_sym,
                                exit_price=current_price,
                                realized_pnl=exit_event.pnl,
                                exit_reason=exit_event.reason.name
                            )
                            m.paper_journal.record_trade_closure(
                                symbol=clean_sym,
                                exit_price=current_price,
                                realized_pnl=exit_event.pnl,
                                exit_reason=exit_event.reason.name
                            )
                            m.log_audit_event(
                                "POSITION_EXIT",
                                f"exit_{int(source_ts)}_{clean_sym}",
                                clean_sym,
                                "CLOSE",
                                f"Auto-exit executed on genuine market feed: {exit_event.reason.name} at ₹{current_price:.2f}. P&L: ₹{exit_event.pnl:.2f}. Broker Order ID: {exit_event.broker_order_id}"
                            )
                            m.notify_state_changed()

                    # Technical Indicators & Realtime Pipeline Evaluation
                    snapshot = get_feature_snapshot(candles, current_price)
                    signal_str = "HOLD" if market_open else "MARKET_CLOSED"
                    ml_predict = "CALCULATING" if market_open else "MARKET_CLOSED"
                    candidate_trade = None
                    order = None
                    msg = "Holding position" if market_open else "Market is closed (09:15-15:30 IST)"

                    if snapshot:
                        # Extract live expected return and model prediction
                        if len(candles) >= 15:
                            try:
                                feats = m.ml_engine.extract_features(candles)
                                pred = m.ml_engine.predict(feats, symbol=clean_sym)
                                if market_open:
                                    ml_predict = f"{pred.predicted_direction} ({pred.confidence:.0%})"
                                snapshot["ml_prediction"] = pred.predicted_direction
                                snapshot["ml_confidence"] = pred.confidence
                                snapshot["expected_return_pct"] = pred.expected_return_pct
                            except Exception as ml_err:
                                logger.debug(f"Live ML inference error for {clean_sym}: {ml_err}")
                                if market_open:
                                    ml_predict = "HOLD (50%)"

                        # Run unified trading pipeline ONLY during open market hours
                        if market_open and not m.EMERGENCY_STOP_ACTIVE:
                            acc_state = m.AccountState(
                                available_margin=m.global_available_margin if m.global_available_margin > 0 else 500000.0,
                                unrealized_pnl=sum(p.get("pnl", 0.0) for p in m.global_positions),
                                realized_pnl=m.position_manager.get_realized_pnl(),
                                open_positions={p["tradingsymbol"]: p["quantity"] * p.get("average_price", current_price) for p in m.global_positions}
                            )

                            mkt_snapshot = {
                                "symbol": clean_sym,
                                "price": current_price,
                                "volume": snapshot.get("volume", 0),
                                "timestamp": source_ts
                            }

                            candidate_trade, order, msg = m.pipeline.process_tick(
                                symbol=clean_sym,
                                candles=candles,
                                market_snapshot=mkt_snapshot,
                                indicators=snapshot,
                                account_state=acc_state,
                                timestamp=datetime.now().isoformat()
                            )
                            if candidate_trade:
                                signal_str = candidate_trade.direction.name

                    # Watchlist metrics
                    change = round(((current_price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
                    mkt_status = get_market_status()
                    if mkt_status == "CLOSED" or not market_open:
                        status_str = "MARKET_CLOSED"
                    elif is_zerodha_live:
                        status_str = "ZERODHA_LIVE"
                    else:
                        status_str = mkt_status

                    watchlist_payload.append({
                        "symbol": clean_sym,
                        "ltp": round(current_price, 2),
                        "prev_close": round(prev_close, 2),
                        "change": change,
                        "signal": signal_str,
                        "status": status_str,
                        "source_ts": source_ts,
                        "rsi": snapshot.get("rsi_14", 0.0) if snapshot else 0.0,
                        "ml_predict": ml_predict
                    })

                    # Autonomous Execution or Candidate Trade Broadcast
                    if candidate_trade and candidate_trade.direction != SignalDirection.HOLD:
                        trade_id = f"t{random.randint(1000, 9999)}"
                    
                        if order:
                            m.log_audit_event("ORDER_EVENT", trade_id, candidate_trade.symbol, "AUTONOMOUS", f"Broker ID: {order.broker_order_id} | {msg}")
                            m.ml_monitor.record_prediction(
                                symbol=candidate_trade.symbol,
                                predicted_direction=candidate_trade.direction.name,
                                confidence=candidate_trade.confidence_score,
                                entry_price=candidate_trade.entry_price,
                                features=snapshot or {},
                                market_regime=candidate_trade.market_regime or m.MLMonitor.classify_regime(snapshot or {}, candidate_trade.entry_price),
                                trade_id=trade_id,
                                expected_return_pct=candidate_trade.expected_return_pct,
                                quality_score=candidate_trade.quality_score
                            )
                            m.position_manager.register_position(
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
                            m.autonomous_trades_history.insert(0, exec_dict)
                            if len(m.autonomous_trades_history) > 30:
                                m.autonomous_trades_history.pop()

                            if m.active_connections:
                                for connection in m.active_connections:
                                    try:
                                        await connection.send_text(json.dumps({
                                            "type": "autonomous_trade",
                                            "trade": exec_dict
                                        }))
                                    except Exception:
                                        pass

                            m.notify_state_changed()
                        elif not candidate_trade.approval_required:
                            m.log_audit_event("RISK_DECISION", trade_id, candidate_trade.symbol, "REJECT", f"Risk Engine Blocked Auto-Execution: {msg}")
                        else:
                            already_pending = any(c.get("symbol") == candidate_trade.symbol for c in m.candidate_cache.values())
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
                                m.candidate_cache[trade_id] = cand_dict
                                m.log_audit_event("SIGNAL", trade_id, cand_dict["symbol"], cand_dict["action"], f"AI Reasoning: {cand_dict['reasoning']} ({msg}) | Sizing: {cand_dict.get('sizing_rationale')}")
                            
                                if m.active_connections:
                                    for connection in m.active_connections:
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

            m.current_watchlist_payload = watchlist_payload
            await m.broadcast_portfolio_update()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in live market streaming: {e}")
        sleep_sec = 5.0 if (settings.CHECK_MARKET_HOURS and not is_market_open()) else 1.0
        await asyncio.sleep(sleep_sec)
