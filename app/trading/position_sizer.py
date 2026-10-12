"""
Dynamic Position Sizing & Capital Allocation Engine.
Implements institutional Fixed Fractional Risk, Volatility-Adjusted (ATR) Position Sizing,
and Capital Allocation constraints for automated trading.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import math
import logging

logger = logging.getLogger(__name__)

class PositionSizerConfig(BaseModel):
    risk_per_trade_pct: float = Field(0.01, description="Fraction of account equity risked per trade (default 1.0%)")
    max_position_capital_pct: float = Field(0.20, description="Max fraction of account capital in a single position (default 20%)")
    max_qty_per_order: int = Field(500, description="Absolute ceiling for shares per order to prevent liquidity impact")
    min_qty: int = Field(1, description="Minimum order size floor")
    default_atr_multiplier: float = Field(1.5, description="ATR multiplier used to estimate SL distance if missing")
    confidence_scaling: bool = Field(True, description="Whether to scale position size based on AI/strategy conviction")

class AllocationResult(BaseModel):
    quantity: int
    allocated_capital: float
    capital_allocation_pct: float
    risk_budget: float
    risk_budget_pct: float
    sl_distance: float
    confidence_multiplier: float
    sizing_rationale: str

class DynamicPositionSizer:
    """
    Computes mathematically sound, risk-adjusted share quantities and portfolio weights.
    Balances volatility (ATR/SL distance), account margin, and portfolio concentration limits.
    """
    def __init__(self, config: Optional[PositionSizerConfig] = None):
        self.config = config or PositionSizerConfig()

    def calculate_allocation(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        account_equity: float,
        atr: Optional[float] = None,
        confidence: float = 1.0,
        available_margin: Optional[float] = None
    ) -> AllocationResult:
        """
        Calculates optimal quantity based on volatility (ATR/SL distance) and risk budget.
        
        Formula:
          Risk Budget = Account Equity * risk_per_trade_pct
          SL Distance = abs(entry_price - stop_loss)
          Raw Qty = (Risk Budget / SL Distance) * confidence_scale
          Capital Cap Qty = (Account Equity * max_position_capital_pct) / entry_price
          Final Qty = min(Raw Qty, Capital Cap Qty, max_qty_per_order, available_margin / entry_price)
        """
        if entry_price <= 0.0:
            return AllocationResult(
                quantity=self.config.min_qty,
                allocated_capital=0.0,
                capital_allocation_pct=0.0,
                risk_budget=0.0,
                risk_budget_pct=0.0,
                sl_distance=0.0,
                confidence_multiplier=1.0,
                sizing_rationale="Invalid entry price; defaulted to min_qty."
            )

        equity = max(account_equity, 10000.0) # Floor equity at 10,000 for realistic sizing
        effective_margin = available_margin if (available_margin is not None and available_margin > 0) else equity

        # 1. Calculate SL Distance (with ATR fallback if SL is missing, <= 0, or equal to entry)
        if stop_loss <= 0.0 or stop_loss == entry_price:
            if atr and atr > 0.0:
                sl_distance = atr * self.config.default_atr_multiplier
            else:
                sl_distance = entry_price * 0.02 # Fallback 2% risk distance
        else:
            sl_distance = abs(entry_price - stop_loss)
        
        # Ensure SL distance is at least 0.25% of price to prevent division by near-zero
        min_sl_dist = entry_price * 0.0025
        if sl_distance < min_sl_dist:
            sl_distance = min_sl_dist

        # 2. Compute Base Rupee Risk Budget
        risk_budget = equity * self.config.risk_per_trade_pct

        # 3. Confidence Scaling
        conf = max(0.1, min(confidence, 1.0))
        if self.config.confidence_scaling:
            # Scale from 0.5x (low confidence 0.5) to 1.0x (full confidence 1.0)
            confidence_multiplier = round(0.5 + (0.5 * conf), 2)
        else:
            confidence_multiplier = 1.0

        effective_risk_budget = risk_budget * confidence_multiplier

        # 4. Volatility-Targeted Quantity
        raw_qty = math.floor(effective_risk_budget / sl_distance)

        # 5. Single Position Capital Allocation Ceiling (e.g., max 20% of account equity)
        max_capital_for_asset = equity * self.config.max_position_capital_pct
        cap_qty = math.floor(max_capital_for_asset / entry_price)

        # 6. Available Margin Ceiling (cannot buy more than available funds)
        margin_qty = math.floor(effective_margin / entry_price)

        # 7. Apply Constraints
        calculated_qty = min(raw_qty, cap_qty, self.config.max_qty_per_order, margin_qty)
        final_qty = max(self.config.min_qty, calculated_qty)

        # Safety check: if 1 share exceeds available margin, set to 1 if dry run
        allocated_capital = round(final_qty * entry_price, 2)
        capital_allocation_pct = round((allocated_capital / equity) * 100.0, 2)
        actual_risk_rupees = round(final_qty * sl_distance, 2)
        actual_risk_pct = round((actual_risk_rupees / equity) * 100.0, 2)

        rationale = (
            f"Risk Budget: ₹{risk_budget:,.0f} ({self.config.risk_per_trade_pct*100:.1f}%), "
            f"SL Dist: ₹{sl_distance:.2f}, Conf Scale: {confidence_multiplier}x, "
            f"Allocated: ₹{allocated_capital:,.0f} ({capital_allocation_pct}%), "
            f"Risk at SL: ₹{actual_risk_rupees:,.0f} ({actual_risk_pct}%)"
        )

        return AllocationResult(
            quantity=final_qty,
            allocated_capital=allocated_capital,
            capital_allocation_pct=capital_allocation_pct,
            risk_budget=actual_risk_rupees,
            risk_budget_pct=actual_risk_pct,
            sl_distance=round(sl_distance, 2),
            confidence_multiplier=confidence_multiplier,
            sizing_rationale=rationale
        )
