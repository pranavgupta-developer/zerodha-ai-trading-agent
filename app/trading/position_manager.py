import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, List, Tuple, Any

from app.broker.kite_adapter import BrokerAdapter
from app.trading.signals import SignalDirection

logger = logging.getLogger(__name__)


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    MANUAL_SQUARE_OFF = "MANUAL_SQUARE_OFF"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass
class TrackedPosition:
    symbol: str
    direction: SignalDirection  # BUY (Long) or SELL (Short)
    quantity: int
    entry_price: float
    stop_loss: float
    take_target: float
    trailing_sl_pct: Optional[float] = None  # e.g. 0.015 for 1.5% trailing
    highest_price: float = 0.0
    lowest_price: float = 0.0
    entry_time: float = field(default_factory=time.time)
    broker_order_id: Optional[str] = None
    is_active: bool = True

    def __post_init__(self):
        if self.highest_price <= 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price <= 0.0:
            self.lowest_price = self.entry_price


@dataclass
class ExitEvent:
    symbol: str
    reason: ExitReason
    exit_price: float
    quantity: int
    pnl: float
    pnl_pct: float
    broker_order_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class PositionManager:
    """
    Monitors active positions on every tick/price update against Stop-Loss and Take-Profit rules,
    including dynamic trailing stop-loss execution and one-click manual square-offs.
    """

    def __init__(self, broker: Optional[BrokerAdapter] = None):
        self.broker = broker
        self._positions: Dict[str, TrackedPosition] = {}

    def register_position(
        self,
        symbol: str,
        direction: SignalDirection,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        take_target: float,
        trailing_sl_pct: Optional[float] = None,
        broker_order_id: Optional[str] = None,
    ) -> TrackedPosition:
        """
        Registers or updates a tracked position with SL/TP bounds.
        """
        clean_symbol = symbol.replace(".NS", "").strip()
        quantity = abs(int(quantity))

        if quantity == 0:
            if clean_symbol in self._positions:
                del self._positions[clean_symbol]
            return None

        # Sanity check stop loss & take target for direction
        if direction == SignalDirection.BUY:
            if stop_loss >= entry_price or stop_loss <= 0.0:
                stop_loss = round(entry_price * 0.98, 2)  # Default 2% stop loss
            if take_target <= entry_price or take_target <= 0.0:
                take_target = round(entry_price * 1.05, 2)  # Default 5% take target
        else:
            if stop_loss <= entry_price or stop_loss <= 0.0:
                stop_loss = round(entry_price * 1.02, 2)
            if take_target >= entry_price or take_target <= 0.0:
                take_target = round(entry_price * 0.95, 2)

        pos = TrackedPosition(
            symbol=clean_symbol,
            direction=direction,
            quantity=quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_target=take_target,
            trailing_sl_pct=trailing_sl_pct,
            highest_price=entry_price,
            lowest_price=entry_price,
            broker_order_id=broker_order_id,
            is_active=True,
        )

        self._positions[clean_symbol] = pos
        logger.info(
            f"Registered tracked position for {clean_symbol}: {direction.name} {quantity} @ ₹{entry_price:.2f} "
            f"(SL: ₹{stop_loss:.2f}, TP: ₹{take_target:.2f}, Trailing: {trailing_sl_pct})"
        )
        return pos

    def get_tracked_position(self, symbol: str) -> Optional[TrackedPosition]:
        clean_symbol = symbol.replace(".NS", "").strip()
        pos = self._positions.get(clean_symbol)
        if pos and pos.is_active:
            return pos
        return None

    def get_all_tracked(self) -> Dict[str, TrackedPosition]:
        return {k: v for k, v in self._positions.items() if v.is_active}

    def sync_with_broker_positions(
        self,
        broker_positions: List[Dict[str, Any]],
        default_sl_pct: float = 0.02,
        default_tp_pct: float = 0.05,
    ):
        """
        Ensures all net broker positions have an active tracking envelope with protective SL/TP.
        Removes tracked positions that are no longer open at the broker.
        """
        broker_symbols = set()
        for p in broker_positions:
            raw_sym = p.get("tradingsymbol", "")
            clean_sym = raw_sym.replace(".NS", "").strip()
            qty = abs(int(p.get("quantity", 0)))
            if not clean_sym or qty == 0:
                continue

            broker_symbols.add(clean_sym)
            avg_price = float(p.get("average_price", 0.0))
            if avg_price <= 0.0:
                avg_price = float(p.get("last_price", 100.0))

            if clean_sym not in self._positions or not self._positions[clean_sym].is_active:
                # Assign default protective SL/TP
                sl = round(avg_price * (1.0 - default_sl_pct), 2)
                tp = round(avg_price * (1.0 + default_tp_pct), 2)
                self.register_position(
                    symbol=clean_sym,
                    direction=SignalDirection.BUY,
                    quantity=qty,
                    entry_price=avg_price,
                    stop_loss=sl,
                    take_target=tp,
                )
            else:
                # Update quantity if changed
                tracked = self._positions[clean_sym]
                if tracked.quantity != qty:
                    tracked.quantity = qty

        # Mark positions closed if no longer present at broker
        for sym in list(self._positions.keys()):
            if sym not in broker_symbols:
                self._positions[sym].is_active = False

    def evaluate_price(self, symbol: str, current_price: float) -> Optional[ExitEvent]:
        """
        Evaluates current price against SL/TP rules for a symbol.
        Does NOT execute broker order directly (allows check before execution or unit testing).
        """
        pos = self.get_tracked_position(symbol)
        if not pos or not pos.is_active or current_price <= 0.0:
            return None

        # Update price extremes
        if current_price > pos.highest_price:
            pos.highest_price = current_price
        if pos.lowest_price <= 0.0 or current_price < pos.lowest_price:
            pos.lowest_price = current_price

        # Evaluate Trailing SL if configured
        if pos.trailing_sl_pct and pos.trailing_sl_pct > 0.0:
            if pos.direction == SignalDirection.BUY:
                trail_price = round(pos.highest_price * (1.0 - pos.trailing_sl_pct), 2)
                if trail_price > pos.stop_loss:
                    logger.debug(
                        f"Trailing SL raised for {pos.symbol}: ₹{pos.stop_loss:.2f} -> ₹{trail_price:.2f}"
                    )
                    pos.stop_loss = trail_price
            else:
                trail_price = round(pos.lowest_price * (1.0 + pos.trailing_sl_pct), 2)
                if trail_price < pos.stop_loss:
                    logger.debug(
                        f"Trailing SL lowered for {pos.symbol}: ₹{pos.stop_loss:.2f} -> ₹{trail_price:.2f}"
                    )
                    pos.stop_loss = trail_price

        # Check breach conditions
        reason: Optional[ExitReason] = None

        if pos.direction == SignalDirection.BUY:
            if current_price <= pos.stop_loss:
                reason = (
                    ExitReason.TRAILING_STOP
                    if pos.trailing_sl_pct and pos.stop_loss > pos.entry_price
                    else ExitReason.STOP_LOSS
                )
            elif pos.take_target > 0.0 and current_price >= pos.take_target:
                reason = ExitReason.TAKE_PROFIT
        else:  # SHORT
            if current_price >= pos.stop_loss:
                reason = (
                    ExitReason.TRAILING_STOP
                    if pos.trailing_sl_pct and pos.stop_loss < pos.entry_price
                    else ExitReason.STOP_LOSS
                )
            elif pos.take_target > 0.0 and current_price <= pos.take_target:
                reason = ExitReason.TAKE_PROFIT

        if reason:
            pnl = (
                (current_price - pos.entry_price) * pos.quantity
                if pos.direction == SignalDirection.BUY
                else (pos.entry_price - current_price) * pos.quantity
            )
            cost_basis = pos.entry_price * pos.quantity
            pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

            return ExitEvent(
                symbol=pos.symbol,
                reason=reason,
                exit_price=current_price,
                quantity=pos.quantity,
                pnl=round(pnl, 2),
                pnl_pct=round(pnl_pct, 2),
            )

        return None

    def check_and_execute_exit(self, symbol: str, current_price: float) -> Optional[ExitEvent]:
        """
        Evaluates current price and executes the broker exit order if SL or TP is hit.
        """
        event = self.evaluate_price(symbol, current_price)
        if not event:
            return None

        pos = self.get_tracked_position(symbol)
        if not pos:
            return None

        # Execute exit order with broker
        transaction_type = "SELL" if pos.direction == SignalDirection.BUY else "BUY"
        broker_order_id = None

        if self.broker:
            try:
                broker_order_id = self.broker.place_order(
                    symbol=pos.symbol,
                    transaction_type=transaction_type,
                    quantity=pos.quantity,
                    price=0.0,
                    order_type="MARKET",
                    product="MIS",
                )
                logger.info(
                    f"Auto-exit executed for {pos.symbol} ({event.reason.value}) @ ₹{current_price:.2f}. "
                    f"Order ID: {broker_order_id}, P&L: ₹{event.pnl:.2f} ({event.pnl_pct:.2f}%)"
                )
            except Exception as e:
                logger.error(f"Failed to execute auto-exit order for {pos.symbol}: {e}")
                return None

        event.broker_order_id = broker_order_id
        pos.is_active = False
        return event

    def manual_square_off(self, symbol: str, current_price: float = 0.0) -> Optional[ExitEvent]:
        """
        Manually squares off a position immediately, executing a market exit.
        """
        pos = self.get_tracked_position(symbol)
        clean_symbol = symbol.replace(".NS", "").strip()

        qty = pos.quantity if pos else 1
        direction = pos.direction if pos else SignalDirection.BUY
        entry_price = pos.entry_price if pos else current_price

        transaction_type = "SELL" if direction == SignalDirection.BUY else "BUY"
        broker_order_id = None

        if self.broker:
            try:
                broker_order_id = self.broker.place_order(
                    symbol=clean_symbol,
                    transaction_type=transaction_type,
                    quantity=qty,
                    price=0.0,
                    order_type="MARKET",
                    product="MIS",
                )
            except Exception as e:
                logger.error(f"Manual square-off broker order failed for {clean_symbol}: {e}")
                raise e

        if current_price <= 0.0 and pos:
            current_price = pos.entry_price

        pnl = (
            (current_price - entry_price) * qty
            if direction == SignalDirection.BUY
            else (entry_price - current_price) * qty
        )
        cost_basis = entry_price * qty
        pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

        if pos:
            pos.is_active = False

        event = ExitEvent(
            symbol=clean_symbol,
            reason=ExitReason.MANUAL_SQUARE_OFF,
            exit_price=current_price,
            quantity=qty,
            pnl=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            broker_order_id=broker_order_id,
        )
        logger.info(f"Manual square off completed for {clean_symbol}. Order: {broker_order_id}")
        return event
