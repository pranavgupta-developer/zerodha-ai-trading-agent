from typing import Optional
from pydantic import BaseModel, Field
from app.trading.signals import SignalDirection

class CandidateTrade(BaseModel):
    """
    Represents a trade proposed by the AI Agent.
    Requires evaluation and potentially human-in-the-loop approval.
    """
    symbol: str = Field(..., description="The trading symbol (e.g., RELIANCE)")
    direction: SignalDirection = Field(..., description="BUY, SELL, or HOLD")
    qty: int = Field(..., description="Quantity to trade. 0 if HOLD.")
    entry_price: float = Field(..., description="Target entry price")
    stop_loss: float = Field(..., description="Calculated stop loss")
    take_target: float = Field(..., description="Calculated take profit target")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="AI's conviction level from 0.0 to 1.0")
    reasoning: str = Field(..., description="Detailed explanation of the trade rationale")
    approval_required: bool = Field(True, description="True if human approval is needed before execution")
    allocated_capital: Optional[float] = Field(None, description="Total capital allocated to this trade")
    risk_budget: Optional[float] = Field(None, description="Rupee amount risked between entry and stop-loss")
    risk_pct: Optional[float] = Field(None, description="Percentage of total portfolio equity risked")
    sizing_rationale: Optional[str] = Field(None, description="Explanation of dynamic position sizing")
