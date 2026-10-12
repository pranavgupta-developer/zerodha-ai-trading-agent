import time
import logging
from enum import Enum
from typing import Dict, Optional, List
from pydantic import BaseModel
from app.broker.kite_adapter import BrokerAdapter
from app.trading.signals import Signal, SignalDirection
from app.agent.schemas import CandidateTrade
from app.trading.risk_engine import RiskEngine, AccountState

logger = logging.getLogger(__name__)

class OrderState(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class ManagedOrder(BaseModel):
    idempotency_key: str
    symbol: str
    direction: SignalDirection
    qty: int
    price: float
    state: OrderState = OrderState.CREATED
    broker_order_id: Optional[str] = None
    filled_qty: int = 0
    message: str = ""

class OrderManager:
    """
    Manages order execution lifecycle, including state transitions, idempotency, and error retries.
    """
    def __init__(self, broker: BrokerAdapter, risk_engine: Optional[RiskEngine] = None):
        self.broker = broker
        self.risk_engine = risk_engine
        self._order_cache: Dict[str, ManagedOrder] = {}

    def generate_idempotency_key(self, signal: Signal) -> str:
        """
        Generates a unique key for a trade candidate bucketed to the current minute.
        Prevents submitting duplicate orders for the same signal.
        """
        minute_bucket = int(time.time() / 60)
        return f"{signal.symbol}_{signal.direction.value}_{minute_bucket}"

    def place_order(self, signal: Signal, qty: int, idempotency_key: Optional[str] = None) -> ManagedOrder:
        """
        Places a new order with retry logic and state machine tracking.
        """
        if not idempotency_key:
            idempotency_key = self.generate_idempotency_key(signal)
            
        if idempotency_key in self._order_cache:
            logger.info(f"Idempotent request for key {idempotency_key}. Returning cached order.")
            return self._order_cache[idempotency_key]
            
        order = ManagedOrder(
            idempotency_key=idempotency_key,
            symbol=signal.symbol,
            direction=signal.direction,
            qty=qty,
            price=signal.entry_price,
            state=OrderState.CREATED
        )
        self._order_cache[idempotency_key] = order
        
        # Retry with exponential backoff for transient errors
        max_retries = 3
        backoff_factor = 2.0
        delay = 0.5
        
        transaction_type = "BUY" if signal.direction == SignalDirection.BUY else "SELL"
        
        for attempt in range(1, max_retries + 1):
            try:
                order_id = self.broker.place_order(
                    symbol=signal.symbol,
                    transaction_type=transaction_type,
                    quantity=qty,
                    price=signal.entry_price
                )
                
                order.broker_order_id = order_id
                order.state = OrderState.SUBMITTED
                logger.info(f"Successfully submitted order {order_id} for {signal.symbol}")
                break
                
            except Exception as e:
                error_msg = str(e).lower()
                is_transient = any(word in error_msg for word in ["timeout", "connection", "502", "503", "unavailable"])
                
                if is_transient and attempt < max_retries:
                    logger.warning(f"Transient error placing order (attempt {attempt}/{max_retries}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= backoff_factor
                else:
                    logger.error(f"Failed to place order after {attempt} attempts: {e}")
                    order.state = OrderState.REJECTED
                    order.message = str(e)
                    break
                    
        return order
        
    def sync_order_state(self, order: ManagedOrder) -> ManagedOrder:
        """
        Updates the local order state from the broker's system.
        """
        if order.state in (OrderState.COMPLETE, OrderState.REJECTED, OrderState.CANCELLED):
            return order
            
        if not order.broker_order_id:
            return order
            
        try:
            history = self.broker.get_order_history(order.broker_order_id)
            if history:
                latest = history[-1]
                broker_status = latest.get("status")
                
                if broker_status == "COMPLETE":
                    order.state = OrderState.COMPLETE
                elif broker_status == "REJECTED":
                    order.state = OrderState.REJECTED
                elif broker_status == "CANCELLED":
                    order.state = OrderState.CANCELLED
                elif broker_status == "OPEN":
                    order.state = OrderState.OPEN
                elif broker_status == "UPDATE":
                    if latest.get("filled_quantity", 0) > 0:
                        order.state = OrderState.PARTIALLY_FILLED
                        
                order.filled_qty = latest.get("filled_quantity", 0)
                order.message = latest.get("status_message", "")
        except Exception as e:
            logger.error(f"Failed to sync order state for {order.broker_order_id}: {e}")
            
        return order

    def recover_state(self):
        """
        Recovers open orders from the broker on startup to rebuild the idempotency cache
        and prevent duplicate orders after a process restart.
        """
        try:
            logger.info("Recovering OrderManager state from broker...")
            orders = self.broker.get_orders()
            if orders:
                for o in orders:
                    ikey = o.get("order_id")
                    if ikey and ikey not in self._order_cache:
                        direction = SignalDirection.BUY if o.get("transaction_type") == "BUY" else SignalDirection.SELL
                        mo = ManagedOrder(
                            idempotency_key=ikey,
                            symbol=o.get("tradingsymbol"),
                            direction=direction,
                            qty=o.get("quantity", 0),
                            price=o.get("price", 0.0) or 0.0,
                            state=OrderState.COMPLETE if o.get("status") == "COMPLETE" else OrderState.OPEN,
                            broker_order_id=ikey,
                            filled_qty=o.get("filled_quantity", 0)
                        )
                        self._order_cache[ikey] = mo
            logger.info(f"Recovered {len(self._order_cache)} orders into cache.")
        except Exception as e:
            logger.error(f"Failed to recover OrderManager state: {e}")

    def execute_trade(self, trade: CandidateTrade, account: AccountState, idempotency_key: Optional[str] = None) -> ManagedOrder:
        """
        Executes a CandidateTrade safely.
        - Checks for human approval requirement.
        - Performs a final, immediate second risk check before hitting the broker.
        """
        if trade.approval_required:
            logger.warning(f"Trade for {trade.symbol} rejected: Human approval required.")
            raise ValueError(f"Human approval required for trade: {trade.symbol}")
            
        if self.risk_engine:
            # We need to construct a Signal object to run it through Risk Engine
            sig = Signal(
                symbol=trade.symbol,
                direction=trade.direction,
                entry_price=trade.entry_price,
                stop_loss=trade.stop_loss,
                take_target=trade.take_target,
                confidence=trade.confidence_score,
                timestamp=str(time.time()),
                reason=trade.reasoning
            )
            approved, reason = self.risk_engine.validate_signal(sig, account, trade.qty)
            if not approved:
                logger.error(f"Second risk check failed: {reason}")
                raise ValueError(f"Second risk check failed: {reason}")
                
        return self.place_order(
            signal=Signal(
                symbol=trade.symbol, direction=trade.direction, entry_price=trade.entry_price,
                stop_loss=trade.stop_loss, take_target=trade.take_target, confidence=trade.confidence_score,
                timestamp=str(time.time()), reason=trade.reasoning
            ),
            qty=trade.qty,
            idempotency_key=idempotency_key
        )

    def modify_order(self, order: ManagedOrder, new_price: float = None, new_qty: int = None) -> ManagedOrder:
        """Modifies an open order on the broker."""
        if not order.broker_order_id:
            raise ValueError("Order does not have a broker ID yet.")
            
        if order.state not in [OrderState.OPEN, OrderState.PARTIALLY_FILLED]:
            raise ValueError(f"Cannot modify order in state {order.state}")
            
        try:
            self.broker.modify_order(
                order.broker_order_id,
                price=new_price,
                quantity=new_qty
            )
            if new_price: order.price = new_price
            if new_qty: order.qty = new_qty
            logger.info(f"Successfully modified order {order.broker_order_id}")
        except Exception as e:
            logger.error(f"Failed to modify order {order.broker_order_id}: {e}")
            raise e
            
        return order

    def cancel_order(self, order: ManagedOrder) -> ManagedOrder:
        """Cancels an open order on the broker."""
        if not order.broker_order_id:
            raise ValueError("Order does not have a broker ID yet.")
            
        if order.state not in [OrderState.OPEN, OrderState.PARTIALLY_FILLED]:
            raise ValueError(f"Cannot cancel order in state {order.state}")
            
        try:
            self.broker.cancel_order(order.broker_order_id)
            order.state = OrderState.CANCELLED
            logger.info(f"Successfully cancelled order {order.broker_order_id}")
        except Exception as e:
            logger.error(f"Failed to cancel order {order.broker_order_id}: {e}")
            raise e
            
        return order
