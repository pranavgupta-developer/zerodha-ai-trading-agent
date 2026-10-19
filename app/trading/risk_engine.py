from pydantic import BaseModel, Field
from typing import Dict, Tuple, Any, Optional
import pandas as pd
from app.trading.signals import Signal, SignalDirection
from app.utils.market_utils import is_market_open
from app.trading.quant_engine import QuantEngine

DEFAULT_SECTOR_MAP: Dict[str, str] = {
    # Banking & Financial Services
    "HDFCBANK": "BANKING_FINANCIAL",
    "ICICIBANK": "BANKING_FINANCIAL",
    "SBIN": "BANKING_FINANCIAL",
    "KOTAKBANK": "BANKING_FINANCIAL",
    "AXISBANK": "BANKING_FINANCIAL",
    "BAJFINANCE": "BANKING_FINANCIAL",
    "BAJAJFINSV": "BANKING_FINANCIAL",
    "SHRIRAMFIN": "BANKING_FINANCIAL",
    "JIOFIN": "BANKING_FINANCIAL",
    "HDFCLIFE": "BANKING_FINANCIAL",
    "SBILIFE": "BANKING_FINANCIAL",
    "INDUSINDBK": "BANKING_FINANCIAL",
    # Information Technology
    "TCS": "IT",
    "INFY": "IT",
    "HCLTECH": "IT",
    "TECHM": "IT",
    "WIPRO": "IT",
    "LTIM": "IT",
    # Energy, Power & Utilities
    "RELIANCE": "ENERGY",
    "ONGC": "ENERGY",
    "POWERGRID": "ENERGY",
    "NTPC": "ENERGY",
    "COALINDIA": "ENERGY",
    "BPCL": "ENERGY",
    "IOC": "ENERGY",
    # Metals & Mining
    "TATASTEEL": "METALS",
    "HINDALCO": "METALS",
    "JSWSTEEL": "METALS",
    "VEDL": "METALS",
    # Automobile
    "MARUTI": "AUTO",
    "M&M": "AUTO",
    "BAJAJ-AUTO": "AUTO",
    "EICHERMOT": "AUTO",
    "TATAMOTORS": "AUTO",
    "TMPV": "AUTO",
    "HEROMOTOCO": "AUTO",
    # Healthcare & Pharmaceuticals
    "SUNPHARMA": "PHARMA",
    "DRREDDY": "PHARMA",
    "CIPLA": "PHARMA",
    "APOLLOHOSP": "PHARMA",
    "MAXHEALTH": "PHARMA",
    "DIVISLAB": "PHARMA",
    # Consumer & FMCG
    "ITC": "FMCG_CONSUMER",
    "HINDUNILVR": "FMCG_CONSUMER",
    "NESTLEIND": "FMCG_CONSUMER",
    "TITAN": "FMCG_CONSUMER",
    "TATACONSUM": "FMCG_CONSUMER",
    "ASIANPAINT": "FMCG_CONSUMER",
    "BRITANNIA": "FMCG_CONSUMER",
    "TRENT": "FMCG_CONSUMER",
    # Infrastructure, Construction & Industrials
    "LT": "INFRA_INDUSTRIAL",
    "ADANIENT": "INFRA_INDUSTRIAL",
    "ADANIPORTS": "INFRA_INDUSTRIAL",
    "ULTRACEMCO": "INFRA_INDUSTRIAL",
    "GRASIM": "INFRA_INDUSTRIAL",
    "BEL": "INFRA_INDUSTRIAL",
    "BSE": "INFRA_INDUSTRIAL",
    "INDIGO": "INFRA_INDUSTRIAL",
    "ETERNAL": "INFRA_INDUSTRIAL"
}

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
    # Sector concentration controls
    check_sector_exposure: bool = True       # Enforce sector limits
    max_sector_exposure_pct: float = 0.35    # Max fraction of portfolio in any single sector (35%)
    max_sector_allocation_pct: float = 35.0  # Max percentage in single sector for UnifiedRiskCenter
    sector_map: Dict[str, str] = Field(default_factory=dict) # Custom overrides
    # Portfolio VaR/CVaR controls
    enforce_var_limits: bool = False         # Enforce portfolio VaR/CVaR caps
    max_portfolio_var_pct: float = 0.05      # Max 1-day VaR (5%)
    max_portfolio_cvar_pct: float = 0.08     # Max 1-day CVaR (8%)
    var_confidence: float = 0.95             # Confidence level for VaR/CVaR (95%)


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
        self.quant_engine = QuantEngine()

    def get_sector(self, symbol: str) -> str:
        """Returns the assigned sector for a stock symbol."""
        clean_sym = symbol.replace("NSE:", "").upper()
        if clean_sym in self.config.sector_map:
            return self.config.sector_map[clean_sym]
        return DEFAULT_SECTOR_MAP.get(clean_sym, "OTHER")

    def get_sector_breakdown(self, account: AccountState) -> Dict[str, Any]:
        """Calculates exposure and allocation percentages per sector."""
        total_open = sum(account.open_positions.values())
        portfolio_capital = self.config.max_total_exposure if self.config.max_total_exposure > 0 else max(account.available_margin + total_open, 1.0)
        
        breakdown: Dict[str, Dict[str, Any]] = {}
        for sym, val in account.open_positions.items():
            sec = self.get_sector(sym)
            if sec not in breakdown:
                breakdown[sec] = {"exposure": 0.0, "symbols": []}
            breakdown[sec]["exposure"] += val
            breakdown[sec]["symbols"].append(sym)
            
        result = {}
        for sec, data in breakdown.items():
            pct = data["exposure"] / portfolio_capital
            result[sec] = {
                "exposure": round(data["exposure"], 2),
                "pct": round(pct, 4),
                "cap_pct": self.config.max_sector_exposure_pct,
                "breached": pct > self.config.max_sector_exposure_pct,
                "symbols": data["symbols"]
            }
        return {
            "total_exposure": round(total_open, 2),
            "portfolio_capital": round(portfolio_capital, 2),
            "max_sector_exposure_pct": self.config.max_sector_exposure_pct,
            "sectors": result
        }

    def calculate_sector_exposure(self, positions: Any) -> Dict[str, float]:
        """Calculates percentage exposure per sector for given positions.
        Returns a dict mapping sector name to percentage (e.g., {'IT': 20.0, 'BANKING_FINANCIAL': 15.0}).
        """
        if not positions:
            return {}

        sector_totals: Dict[str, float] = {}
        total_val = 0.0

        if isinstance(positions, dict):
            for sym, val in positions.items():
                v = abs(float(val))
                if v <= 0:
                    continue
                sec = self.get_sector(str(sym))
                sector_totals[sec] = sector_totals.get(sec, 0.0) + v
                total_val += v
        elif isinstance(positions, list):
            for p in positions:
                sym = None
                val = 0.0
                if isinstance(p, dict):
                    sym = p.get("tradingsymbol") or p.get("symbol")
                    qty = abs(float(p.get("quantity", 0) or p.get("net_quantity", 0)))
                    price = float(p.get("last_price", 0) or p.get("close_price", 0) or p.get("average_price", 0) or 1.0)
                    val = float(p.get("value", 0)) or (qty * price)
                else:
                    sym = getattr(p, "symbol", getattr(p, "tradingsymbol", None))
                    qty = abs(float(getattr(p, "quantity", 0)))
                    price = float(getattr(p, "current_price", getattr(p, "entry_price", 0)) or 1.0)
                    val = float(getattr(p, "value", 0)) or (qty * price)

                if sym and val > 0:
                    sec = self.get_sector(str(sym))
                    sector_totals[sec] = sector_totals.get(sec, 0.0) + val
                    total_val += val

        if total_val <= 0:
            return {}

        return {sec: round((val / total_val) * 100.0, 2) for sec, val in sector_totals.items()}

    def get_portfolio_var_cvar(
        self,
        account: AccountState,
        returns_df: Optional[pd.DataFrame] = None,
        confidence: Optional[float] = None,
        method: str = "historical"
    ) -> Dict[str, Any]:
        """Calculates current portfolio VaR and CVaR."""
        conf = confidence if confidence is not None else self.config.var_confidence
        total_open = sum(account.open_positions.values())
        if total_open <= 0 or not account.open_positions or returns_df is None or returns_df.empty:
            return {
                "var_pct": 0.0,
                "cvar_pct": 0.0,
                "var_amount": 0.0,
                "cvar_amount": 0.0,
                "confidence": conf,
                "method": method,
                "max_var_pct": self.config.max_portfolio_var_pct,
                "max_cvar_pct": self.config.max_portfolio_cvar_pct,
                "is_safe": True
            }
        
        weights = {s: v / total_open for s, v in account.open_positions.items()}
        res = self.quant_engine.calculate_portfolio_var_cvar(
            weights=weights,
            returns_df=returns_df,
            confidence=conf,
            portfolio_value=total_open,
            method=method
        )
        res["max_var_pct"] = self.config.max_portfolio_var_pct
        res["max_cvar_pct"] = self.config.max_portfolio_cvar_pct
        res["is_safe"] = (
            res["var_pct"] <= self.config.max_portfolio_var_pct and
            res["cvar_pct"] <= self.config.max_portfolio_cvar_pct
        )
        return res

    def validate_signal(
        self,
        signal: Signal,
        account: AccountState,
        requested_qty: int,
        quote_data: Optional[Dict[str, Any]] = None,
        returns_data: Optional[pd.DataFrame] = None
    ) -> Tuple[bool, str]:
        """
        Validates if a signal can be executed based on the risk config and current account state.
        If quote_data is provided, it also checks circuit limits, liquidity, and slippage.
        If returns_data is provided and enforce_var_limits is enabled, checks VaR/CVaR caps.
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

        # 8b. Sector Concentration Check
        if self.config.check_sector_exposure and signal.direction == SignalDirection.BUY:
            sector = self.get_sector(signal.symbol)
            current_sector_exposure = sum(
                val for sym, val in account.open_positions.items()
                if self.get_sector(sym) == sector
            )
            projected_sector_exposure = current_sector_exposure + order_value
            portfolio_capital = self.config.max_total_exposure if self.config.max_total_exposure > 0 else max(account.available_margin + total_exposure, 1.0)
            projected_pct = projected_sector_exposure / portfolio_capital
            if projected_pct > self.config.max_sector_exposure_pct:
                return False, f"SECTOR_CONCENTRATION_BREACH: Sector {sector} exposure would reach {projected_pct*100:.2f}% (max {self.config.max_sector_exposure_pct*100:.2f}%)"

        # 8c. Portfolio VaR / CVaR Check
        if self.config.enforce_var_limits and returns_data is not None and not returns_data.empty and signal.direction == SignalDirection.BUY:
            projected_positions = dict(account.open_positions)
            projected_positions[signal.symbol] = projected_positions.get(signal.symbol, 0.0) + order_value
            total_proj_val = sum(projected_positions.values())
            if total_proj_val > 0:
                weights = {s: v / total_proj_val for s, v in projected_positions.items()}
                var_metrics = self.quant_engine.calculate_portfolio_var_cvar(
                    weights=weights,
                    returns_df=returns_data,
                    confidence=self.config.var_confidence,
                    portfolio_value=total_proj_val
                )
                if var_metrics["var_pct"] > self.config.max_portfolio_var_pct:
                    return False, f"VAR_LIMIT_BREACH: Projected 1-day {int(self.config.var_confidence*100)}% VaR is {var_metrics['var_pct']*100:.2f}% (max {self.config.max_portfolio_var_pct*100:.2f}%)"
                if var_metrics["cvar_pct"] > self.config.max_portfolio_cvar_pct:
                    return False, f"CVAR_LIMIT_BREACH: Projected 1-day {int(self.config.var_confidence*100)}% CVaR is {var_metrics['cvar_pct']*100:.2f}% (max {self.config.max_portfolio_cvar_pct*100:.2f}%)"

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

