from pydantic import BaseModel
from enum import Enum

class SignalDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class Signal(BaseModel):
    symbol: str
    direction: SignalDirection
    confidence: float
    entry_price: float
    stop_loss: float
    take_target: float
    reason: str = ""
    strategy_version: str = "v1.0"

class Prediction(BaseModel):
    symbol: str
    predicted_direction: str  # "UP" or "DOWN"
    confidence: float
    model_used: str
    target_period: int
