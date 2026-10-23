import time
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.trading.signals import Signal, SignalDirection
from app.trading.risk_engine import AccountState
from app.utils.indicators import get_feature_snapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Trades"])


class TradeActionReq(BaseModel):
    trade_id: str
    action: str  # "APPROVE" or "REJECT"


class TradeCloseReq(BaseModel):
    symbol: str
    quantity: Optional[int] = None


@router.post("/api/v1/trades/action")
def handle_trade_action(action: TradeActionReq):
    """
    Operator approves or rejects a candidate trade requiring human authorization.
    """
    import app.main as m
    
    candidate = m.candidate_cache.get(action.trade_id)
    symbol = candidate["symbol"] if candidate else ""
    
    if action.action == "REJECT":
        if action.trade_id in m.candidate_cache:
            del m.candidate_cache[action.trade_id]
        logger.info(f"Trade {action.trade_id} rejected by user.")
        m.log_audit_event("USER_DECISION", action.trade_id, symbol, "REJECT", "User rejected the trade.")
        m.notify_state_changed()
        return {"status": "success", "trade_id": action.trade_id, "action": action.action, "message": "Rejected and discarded"}
        
    elif action.action == "APPROVE":
        if m.EMERGENCY_STOP_ACTIVE:
            m.log_audit_event("RISK_DECISION", action.trade_id, symbol, "REJECT", "Emergency Stop is active")
            m.notify_state_changed()
            raise HTTPException(status_code=400, detail="Emergency Stop is active. No new orders allowed.")
            
        if not candidate:
            raise HTTPException(status_code=404, detail="Trade candidate not found in cache.")
            
        del m.candidate_cache[action.trade_id]
        m.log_audit_event("USER_DECISION", action.trade_id, symbol, "APPROVE", "User approved the trade.")
        
        # Build Signal
        direction = SignalDirection.BUY if candidate.get("action") == "BUY" else SignalDirection.SELL
        entry_price = float(candidate.get("price", 0.0))
        sl_cand = candidate.get("stop_loss") or (entry_price * 0.98 if direction == SignalDirection.BUY else entry_price * 1.02)
        tp_cand = candidate.get("take_target") or (entry_price * 1.05 if direction == SignalDirection.BUY else entry_price * 0.95)
        stop_loss = round(float(sl_cand), 2)
        take_target = round(float(tp_cand), 2)
        qty = candidate.get("qty")
        if not qty or qty <= 0:
            effective_margin = m.global_available_margin if m.global_available_margin > 0 else 500000.0
            alloc = m.position_sizer.calculate_allocation(
                symbol=symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                account_equity=effective_margin,
                available_margin=effective_margin
            )
            qty = alloc.quantity
        
        signal = Signal(
            symbol=symbol,
            direction=direction,
            confidence=0.90,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_target=take_target,
            reason=candidate.get("reasoning", "Approved by human operator")
        )
        
        # Fetch current broker quote for liquidity and circuit checks
        quote_data = None
        try:
            kite_sym = f"NSE:{symbol}"
            quotes = m.broker.get_quote([kite_sym])
            if kite_sym in quotes:
                quote_data = quotes[kite_sym]
        except Exception as e:
            logger.warning(f"Could not fetch quote for trade validation: {e}")
            
        # Re-validate with Risk Engine
        active_pos_map = {p.symbol: p.quantity * p.entry_price for p in m.position_manager.get_all_tracked().values()}
        effective_margin = m.global_available_margin if m.global_available_margin > 0 else 500000.0
        account = AccountState(
            available_margin=effective_margin,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            open_positions=active_pos_map
        )
            
        is_approved, reason = m.risk_engine.validate_signal(signal, account, qty, quote_data)
        
        if not is_approved:
            logger.warning(f"Risk Engine rejected trade {action.trade_id}: {reason}")
            m.log_audit_event("RISK_DECISION", action.trade_id, symbol, "REJECT", f"Risk Engine Rejected: {reason}")
            m.notify_state_changed()
            raise HTTPException(status_code=400, detail=f"Risk Engine Rejected: {reason}")
            
        m.log_audit_event("RISK_DECISION", action.trade_id, symbol, "APPROVE", "Risk Engine Approved")
        
        # Anomaly Detection Safeguard
        opm = float(len([t for t in m.recent_order_timestamps if time.time() - t <= 60.0]))
        order_val = float(qty * signal.entry_price)
        order_pct = min(1.0, order_val / max(effective_margin, 1000.0))
        curr_val = float(account.open_positions.get(symbol, 0.0))
        conc_pct = min(1.0, (curr_val + order_val) / max(effective_margin, 1000.0))
        anom = m.anomaly_detector.evaluate(opm, order_pct, conc_pct, signal.confidence, 150.0)
        if anom.get("halt_trading"):
            m.EMERGENCY_STOP_ACTIVE = True
            m.log_audit_event("ANOMALY_HALT", action.trade_id, symbol, "HALT", f"Manual approval halted by AnomalyDetector (score: {anom.get('anomaly_score', 0):.4f})")
            m.notify_state_changed()
            raise HTTPException(status_code=400, detail="CRITICAL ANOMALY: Order blocked and Emergency Stop engaged.")

        try:
            order = m.order_manager.place_order(signal, qty)
            m.recent_order_timestamps.append(time.time())
            logger.info(f"Order placed successfully: {order.broker_order_id}")
            candles_for_feat = m.global_candles_cache.get(symbol, [])
            feat_snap = get_feature_snapshot(candles_for_feat) if candles_for_feat else {
                "price": signal.entry_price, "rsi_14": 50.0, "atr_14": 0.0, 
                "vwap": signal.entry_price, "ema_20": signal.entry_price, "adx_14": 20.0
            }
            m.ml_monitor.record_prediction(
                symbol=symbol,
                predicted_direction=direction.name,
                confidence=signal.confidence,
                entry_price=signal.entry_price,
                features=feat_snap,
                trade_id=action.trade_id
            )
            m.model_registry.evaluate_shadow(
                symbol=symbol,
                indicators=feat_snap,
                entry_price=signal.entry_price,
                trade_id=action.trade_id
            )
            m.position_manager.register_position(
                symbol=symbol,
                direction=direction,
                quantity=qty,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_target=signal.take_target,
                trailing_sl_pct=0.015,
                broker_order_id=order.broker_order_id
            )
            m.log_audit_event("ORDER_EVENT", action.trade_id, symbol, "SUBMITTED", f"Broker Order ID: {order.broker_order_id}")
            m.notify_state_changed()
            return {"status": "success", "trade_id": action.trade_id, "action": action.action, "broker_order_id": order.broker_order_id}
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            m.log_audit_event("ORDER_EVENT", action.trade_id, symbol, "FAILED", f"Order placement failed: {str(e)}")
            m.notify_state_changed()
            raise HTTPException(status_code=500, detail=f"Order placement failed: {str(e)}")


@router.post("/api/v1/trades/close")
def close_trade_position(req: TradeCloseReq):
    """
    Manual single-position square-off with immediate ML feedback and audit logging.
    """
    import app.main as m
    symbol = req.symbol
    try:
        current_ltp = m.price_cache.get_by_symbol(symbol, 0.0)
        event = m.position_manager.manual_square_off(symbol, current_price=current_ltp)
        if event:
            out_rec = m.ml_monitor.record_outcome(
                symbol=symbol,
                exit_price=event.exit_price,
                realized_pnl=event.pnl,
                exit_reason=event.reason.value,
                trade_id=f"close_{symbol}"
            )
            m.sync_model_registry_outcome(
                symbol=symbol,
                exit_price=event.exit_price,
                realized_pnl=event.pnl,
                exit_reason=event.reason.value,
                trade_id=f"close_{symbol}",
                ml_outcome=out_rec
            )
        broker_order_id = event.broker_order_id if event else None
        logger.info(f"Closing position manually for {symbol}: order={broker_order_id}")
        m.log_audit_event(
            "MANUAL_CLOSE", 
            f"close_{symbol}", 
            symbol, 
            "CLOSED", 
            f"Manual square-off executed @ ₹{current_ltp:.2f} (Order ID: {broker_order_id})"
        )
        m.notify_state_changed()
        return {
            "status": "success",
            "symbol": symbol,
            "broker_order_id": broker_order_id,
            "message": f"Successfully squared off {symbol}"
        }
    except Exception as e:
        logger.error(f"Failed to close position for {symbol}: {e}")
        m.log_audit_event("MANUAL_CLOSE", f"close_{symbol}", symbol, "FAILED", str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/trades/close-all")
def close_all_trade_positions():
    """
    Square off all open positions across the entire portfolio immediately.
    """
    import app.main as m
    try:
        active_positions = m.position_manager.get_all_tracked()
        results = []
        for symbol, pos in list(active_positions.items()):
            if pos.is_active:
                current_ltp = m.price_cache.get_by_symbol(symbol, pos.entry_price)
                event = m.position_manager.manual_square_off(symbol, current_price=current_ltp)
                if event:
                    out_rec = m.ml_monitor.record_outcome(
                        symbol=symbol,
                        exit_price=event.exit_price,
                        realized_pnl=event.pnl,
                        exit_reason=event.reason.value,
                        trade_id=f"close_all_{symbol}"
                    )
                    m.sync_model_registry_outcome(
                        symbol=symbol,
                        exit_price=event.exit_price,
                        realized_pnl=event.pnl,
                        exit_reason=event.reason.value,
                        trade_id=f"close_all_{symbol}",
                        ml_outcome=out_rec
                    )
                results.append({
                    "symbol": symbol,
                    "order_id": event.broker_order_id if event else None,
                    "pnl": event.pnl if event else 0.0
                })
                m.log_audit_event(
                    "MANUAL_CLOSE_ALL",
                    f"close_{symbol}",
                    symbol,
                    "CLOSED",
                    f"Square-off all executed for {symbol}"
                )
        m.notify_state_changed()
        return {
            "status": "success",
            "closed_count": len(results),
            "details": results
        }
    except Exception as e:
        logger.error(f"Failed to close all positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
