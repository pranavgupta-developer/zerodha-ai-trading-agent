from pydantic import BaseModel
from typing import List, Any
from app.trading.signals import Signal, SignalDirection
from app.utils.indicators import calculate_ema, calculate_rsi, calculate_atr, calculate_vwap

class StrategyConfig(BaseModel):
    fast_ema_period: int = 9
    slow_ema_period: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    risk_reward_ratio: float = 2.0
    atr_stop_multiplier: float = 1.5

class EmaRsiVwapStrategy:
    """
    Concrete Strategy: EMA Crossover + RSI Filter + VWAP Trend.
    Generates BUY signals when fast EMA crosses above slow EMA, RSI is not overbought, and Price > VWAP.
    Generates SELL signals when fast EMA crosses below slow EMA, RSI is not oversold, and Price < VWAP.
    Uses ATR for dynamic Stop Loss and Take Target calculation.
    """
    def __init__(self, config: StrategyConfig = StrategyConfig()):
        self.config = config
        self.version = "v1.1-EMA-RSI-VWAP"
        
    def generate_signal(self, symbol: str, candles: List[Any]) -> Signal:
        min_candles = max(self.config.slow_ema_period, self.config.rsi_period) + 1
        if len(candles) < min_candles:
            return Signal(
                symbol=symbol, direction=SignalDirection.HOLD, confidence=0.0, 
                entry_price=0.0, stop_loss=0.0, take_target=0.0, reason="Not enough data", strategy_version=self.version
            )
            
        closes = [float(c.close) for c in candles]
        highs = [float(c.high) for c in candles]
        lows = [float(c.low) for c in candles]
        volumes = [float(c.volume) for c in candles]
        current_price = closes[-1]
        
        fast_ema = calculate_ema(closes, self.config.fast_ema_period)
        slow_ema = calculate_ema(closes, self.config.slow_ema_period)
        rsi = calculate_rsi(closes, self.config.rsi_period)
        atr = calculate_atr(highs, lows, closes, 14)
        vwap = calculate_vwap(highs, lows, closes, volumes)
        
        prev_fast = fast_ema[-2]
        curr_fast = fast_ema[-1]
        prev_slow = slow_ema[-2]
        curr_slow = slow_ema[-1]
        curr_rsi = rsi[-1]
        curr_atr = atr[-1]
        curr_vwap = vwap[-1]
        
        if None in (prev_fast, curr_fast, prev_slow, curr_slow, curr_rsi, curr_atr, curr_vwap):
            return Signal(
                symbol=symbol, direction=SignalDirection.HOLD, confidence=0.0, 
                entry_price=current_price, stop_loss=0.0, take_target=0.0, reason="Insufficient indicator data", strategy_version=self.version
            )
            
        # Bullish Crossover (fast crosses above slow)
        bullish_cross = prev_fast <= prev_slow and curr_fast > curr_slow # type: ignore
        # Bearish Crossover (fast crosses below slow)
        bearish_cross = prev_fast >= prev_slow and curr_fast < curr_slow # type: ignore
        direction = SignalDirection.HOLD
        reason = "No signal"
        
        # BUY: EMA Crossover + RSI not overbought + Price above VWAP
        if bullish_cross and curr_rsi < self.config.rsi_overbought and current_price > curr_vwap: # type: ignore
            direction = SignalDirection.BUY
            reason = f"Bullish EMA crossover (RSI: {curr_rsi:.1f}, Price > VWAP)" # type: ignore
        # SELL: EMA Crossover + RSI not oversold + Price below VWAP
        elif bearish_cross and curr_rsi > self.config.rsi_oversold and current_price < curr_vwap: # type: ignore
            direction = SignalDirection.SELL
            reason = f"Bearish EMA crossover (RSI: {curr_rsi:.1f}, Price < VWAP)" # type: ignore
            
        if direction == SignalDirection.HOLD:
            return Signal(
                symbol=symbol, direction=direction, confidence=0.0, 
                entry_price=current_price, stop_loss=0.0, take_target=0.0, reason=reason, strategy_version=self.version
            )
            
        stop_distance = curr_atr * self.config.atr_stop_multiplier # type: ignore
        
        if direction == SignalDirection.BUY:
            stop_loss = current_price - stop_distance
            target = current_price + (stop_distance * self.config.risk_reward_ratio)
        else:
            stop_loss = current_price + stop_distance
            target = current_price - (stop_distance * self.config.risk_reward_ratio)
            
        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=0.8,
            entry_price=current_price,
            stop_loss=round(stop_loss, 2),
            take_target=round(target, 2),
            reason=reason,
            strategy_version=self.version
        )
