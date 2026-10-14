from pydantic import BaseModel
from typing import Dict, Tuple, Any, Optional
from app.trading.signals import Signal, SignalDirection
from app.utils.market_utils import is_market_open

class RiskConfig(BaseModel):
    max_order_value: float = 100000.0        # Max capital per order
    max_qty_per_order: int = 1000            # Max absolute quantity
    max_orders_per_min: int = 5              # Rate limit
    max_orders_per_day: int = 50             # Global daily limit
    max_position_size: float = 500000.0      # Max capital in a single symbol
    max_total_exposure: float = 500000.0     # Max capital across all symbols
    max_open_positions: int = 10             # Max number of discrete assets to hold
    max_daily_loss: float = 10000.0          # Absolute stop trading if loss > this
    max_daily_loss_pct: float = 0.02         # Or if loss > 2% of actual margin
    max_drawdown_pct: float = 0.05           # Drawdown from peak limit
    circuit_buffer_pct: float = 0.01         # Must be at least 1% away from circuit limits
    min_volume: int = 50000                  # Minimum daily volume
    max_slippage_pct: float = 0.005          # Max bid-ask spread as % of last price
    check_market_hours: bool = True          # Block orders outside market hours

class AccountState(BaseModel):
    """Represents a snapshot of the current portfolio and limits."""
    available_margin: float
    peak_margin: float = 0.0               # Track highest margin for drawdown calc
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    open_positions: Dict[str, float] = {}  # symbol -> position value in base currency
    orders_placed_today: int = 0
    orders_placed_last_minute: int = 0

class RiskEngine:
    """
    Deterministic Risk Engine.
    Evaluates signals against a strict set of configuration bounds before allowing order execution.
    """
    def __init__(self, config: RiskConfig = RiskConfig()):
        self.config = config

    def validate_signal(self, signal: Signal, account: AccountState, requested_qty: int, quote_data: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
        """
        Validates if a signal can be executed based on the risk config and current account state.
        If quote_data is provided, it also checks circuit limits, liquidity, and slippage.
        Returns a tuple: (is_approved, reason).
        """
        if signal.direction == SignalDirection.HOLD:
            return False, "Signal is HOLD"

        # 1. Market Hours Check
        if self.config.check_market_hours and not is_market_open():
            return False, "Market is closed"
            
        # 2. Daily Loss and Drawdown Kill-Switches
        total_pnl = account.realized_pnl + account.unrealized_pnl
        dynamic_loss_limit = account.available_margin * self.config.max_daily_loss_pct
        effective_loss_limit = min(self.config.max_daily_loss, dynamic_loss_limit)
        
        if total_pnl <= -effective_loss_limit:
            return False, f"KILL-SWITCH TRIGGERED: Max daily loss exceeded (PnL: {total_pnl}, Limit: -{effective_loss_limit})"
            
        current_equity = account.available_margin + total_pnl
        if account.peak_margin > 0:
            drawdown = (account.peak_margin - current_equity) / account.peak_margin
            if drawdown > self.config.max_drawdown_pct:
                return False, f"KILL-SWITCH TRIGGERED: Max drawdown exceeded ({drawdown*100:.2f}% > {self.config.max_drawdown_pct*100:.2f}%)"

        # 3. Order Rate Limits
        if account.orders_placed_today >= self.config.max_orders_per_day:
            return False, "Max orders per day exceeded"
        if account.orders_placed_last_minute >= self.config.max_orders_per_min:
            return False, "Max orders per minute exceeded"

        # 3b. Max Open Positions Check
        if signal.direction == SignalDirection.BUY and signal.symbol not in account.open_positions:
            if len(account.open_positions) >= self.config.max_open_positions:
                return False, f"Max open positions ({self.config.max_open_positions}) reached"

        # 4. Max Quantity Check
        if requested_qty > self.config.max_qty_per_order:
            return False, f"Requested quantity {requested_qty} exceeds max {self.config.max_qty_per_order}"

        # 5. Max Order Value Check
        order_value = requested_qty * signal.entry_price
        if order_value > self.config.max_order_value:
            return False, f"Order value {order_value} exceeds max {self.config.max_order_value}"

        # 6. Funds / Margin Check
        if signal.direction == SignalDirection.BUY and order_value > account.available_margin:
            return False, f"Insufficient margin: required {order_value}, available {account.available_margin}"

        # 7. Max Position Size Check
        current_position_value = account.open_positions.get(signal.symbol, 0.0)
        if signal.direction == SignalDirection.BUY:
            if (current_position_value + order_value) > self.config.max_position_size:
                return False, "Max position size for symbol exceeded"

        # 8. Max Total Exposure Check
        total_exposure = sum(account.open_positions.values())
        if signal.direction == SignalDirection.BUY:
            if (total_exposure + order_value) > self.config.max_total_exposure:
                return False, "Max total exposure exceeded"

        # 9. Circuit Limit, Liquidity, and Slippage Checks
        if quote_data:
            last_price = quote_data.get("last_price", signal.entry_price)
            lower_circuit = quote_data.get("lower_circuit_limit", 0.0)
            upper_circuit = quote_data.get("upper_circuit_limit", float('inf'))
            volume = quote_data.get("volume", 0)
            
            # 9a. Circuit Limit Check
            if lower_circuit > 0 and signal.entry_price <= lower_circuit * (1 + self.config.circuit_buffer_pct):
                return False, f"Entry price {signal.entry_price} too close to lower circuit limit ({lower_circuit})"
            if upper_circuit < float('inf') and signal.entry_price >= upper_circuit * (1 - self.config.circuit_buffer_pct):
                return False, f"Entry price {signal.entry_price} too close to upper circuit limit ({upper_circuit})"
                
            # 9b. Liquidity Check
            if volume < self.config.min_volume:
                return False, f"Insufficient liquidity: volume {volume} < min {self.config.min_volume}"
                
            # 9c. Slippage Check (using bid-ask spread)
            depth = quote_data.get("depth", {})
            buy_depth = depth.get("buy", [])
            sell_depth = depth.get("sell", [])
            if buy_depth and sell_depth:
                best_bid = buy_depth[0].get("price", 0)
                best_ask = sell_depth[0].get("price", 0)
                if best_bid > 0 and best_ask > 0 and last_price > 0:
                    spread = best_ask - best_bid
                    spread_pct = spread / last_price
                    if spread_pct > self.config.max_slippage_pct:
                        return False, f"Slippage too high: bid-ask spread is {spread_pct*100:.2f}% (max {self.config.max_slippage_pct*100:.2f}%)"

        return True, "Approved"
