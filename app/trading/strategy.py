from pydantic import BaseModel
from typing import List, Any, Optional, Dict
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
    # Regime & Multi-Timeframe controls
    enable_regime_filter: bool = True
    filter_sideways_regime: bool = False  # If True, strictly suppresses in SIDEWAYS; if False, applies compressed targets
    enable_mtf_filter: bool = True
    mtf_ema_period: int = 20

class EmaRsiVwapStrategy:
    """
    Concrete Strategy: EMA Crossover + RSI Filter + VWAP Trend with
    Market Regime Adaptation and Multi-Timeframe (MTF) Trend Alignment.
    
    Generates BUY signals when fast EMA crosses above slow EMA, RSI is not overbought, and Price > VWAP.
    Generates SELL signals when fast EMA crosses below slow EMA, RSI is not oversold, and Price < VWAP.
    Adapts Stop-Loss and Take-Target dynamically to market regimes (Trending, Sideways, High Volatility).
    Validates lower timeframe signals against higher timeframe trend (MTF) to avoid counter-trend trades.
    """
    def __init__(self, config: StrategyConfig = StrategyConfig()):
        self.config = config
        self.version = "v1.2-MTF-Regime-EMA-RSI"

    def _classify_regime_internal(self, current_price: float, rsi: float, ema_slow: float, atr: float) -> str:
        """Lightweight fallback regime classifier from current indicators."""
        if current_price > 0 and (atr / current_price > 0.025):
            return "HIGH_VOLATILITY"
        if rsi >= 56.0 and current_price >= ema_slow:
            return "BULLISH_TREND"
        elif rsi <= 44.0 and current_price <= ema_slow:
            return "BEARISH_TREND"
        return "SIDEWAYS"
        
    def generate_signal(
        self, 
        symbol: str, 
        candles: List[Any],
        mtf_candles: Optional[List[Any]] = None,
        market_regime: Optional[str] = None
    ) -> Signal:
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
            
        # Determine Market Regime if not explicitly provided
        active_regime = market_regime
        if not active_regime or active_regime == "UNKNOWN":
            active_regime = self._classify_regime_internal(current_price, float(curr_rsi), float(curr_slow), float(curr_atr)) # type: ignore

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
                entry_price=current_price, stop_loss=0.0, take_target=0.0, reason=reason, 
                strategy_version=self.version, market_regime=active_regime
            )

        # 1. Market Regime Gating Filter
        if self.config.enable_regime_filter:
            if self.config.filter_sideways_regime and active_regime == "SIDEWAYS":
                return Signal(
                    symbol=symbol, direction=SignalDirection.HOLD, confidence=0.0,
                    entry_price=current_price, stop_loss=0.0, take_target=0.0,
                    reason="Signal suppressed: Trend crossover disabled in SIDEWAYS market regime",
                    strategy_version=self.version, market_regime=active_regime
                )
            if active_regime == "BULLISH_TREND" and direction == SignalDirection.SELL:
                return Signal(
                    symbol=symbol, direction=SignalDirection.HOLD, confidence=0.0,
                    entry_price=current_price, stop_loss=0.0, take_target=0.0,
                    reason="Signal suppressed: Bearish signal counter to active BULLISH_TREND regime",
                    strategy_version=self.version, market_regime=active_regime
                )
            if active_regime == "BEARISH_TREND" and direction == SignalDirection.BUY:
                return Signal(
                    symbol=symbol, direction=SignalDirection.HOLD, confidence=0.0,
                    entry_price=current_price, stop_loss=0.0, take_target=0.0,
                    reason="Signal suppressed: Bullish signal counter to active BEARISH_TREND regime",
                    strategy_version=self.version, market_regime=active_regime
                )

        # 2. Multi-Timeframe (MTF) Trend Alignment Filter
        mtf_confirmed = False
        if self.config.enable_mtf_filter and mtf_candles and len(mtf_candles) >= (self.config.mtf_ema_period + 1):
            mtf_closes = [float(c.close) for c in mtf_candles]
            mtf_ema = calculate_ema(mtf_closes, self.config.mtf_ema_period)
            curr_mtf_close = mtf_closes[-1]
            curr_mtf_ema = mtf_ema[-1]
            
            if curr_mtf_ema is not None:
                if direction == SignalDirection.BUY:
                    if curr_mtf_close < curr_mtf_ema:
                        return Signal(
                            symbol=symbol, direction=SignalDirection.HOLD, confidence=0.0,
                            entry_price=current_price, stop_loss=0.0, take_target=0.0,
                            reason=f"MTF Misalignment: 1m Bullish signal contradicted by Bearish MTF trend (MTF Close {curr_mtf_close:.2f} < MTF EMA {curr_mtf_ema:.2f})",
                            strategy_version=self.version, market_regime=active_regime, mtf_confirmed=False
                        )
                    mtf_confirmed = True
                elif direction == SignalDirection.SELL:
                    if curr_mtf_close > curr_mtf_ema:
                        return Signal(
                            symbol=symbol, direction=SignalDirection.HOLD, confidence=0.0,
                            entry_price=current_price, stop_loss=0.0, take_target=0.0,
                            reason=f"MTF Misalignment: 1m Bearish signal contradicted by Bullish MTF trend (MTF Close {curr_mtf_close:.2f} > MTF EMA {curr_mtf_ema:.2f})",
                            strategy_version=self.version, market_regime=active_regime, mtf_confirmed=False
                        )
                    mtf_confirmed = True

        # 3. Dynamic Stop-Loss and Take-Profit Adaptation
        effective_stop_mult = self.config.atr_stop_multiplier
        effective_rr = self.config.risk_reward_ratio

        if active_regime == "BULLISH_TREND":
            effective_stop_mult = 1.5
            effective_rr = 2.5
        elif active_regime == "BEARISH_TREND":
            effective_stop_mult = 1.5
            effective_rr = 2.5
        elif active_regime == "SIDEWAYS":
            effective_stop_mult = 1.2
            effective_rr = 1.3
        elif active_regime == "HIGH_VOLATILITY":
            effective_stop_mult = 2.2
            effective_rr = 2.0

        stop_distance = curr_atr * effective_stop_mult # type: ignore
        
        if direction == SignalDirection.BUY:
            stop_loss = current_price - stop_distance
            target = current_price + (stop_distance * effective_rr)
            expected_ret = round(((target - current_price) / current_price) * 100.0, 3)
        else:
            stop_loss = current_price + stop_distance
            target = current_price - (stop_distance * effective_rr)
            expected_ret = round(((current_price - target) / current_price) * 100.0, 3)
            
        return Signal(
            symbol=symbol,
            direction=direction,
            confidence=0.85 if mtf_confirmed else 0.8,
            entry_price=current_price,
            stop_loss=round(stop_loss, 2),
            take_target=round(target, 2),
            reason=f"{reason} | Regime: {active_regime} (StopMult: {effective_stop_mult}x, RR: {effective_rr}x)",
            strategy_version=self.version,
            market_regime=active_regime,
            expected_return_pct=expected_ret,
            mtf_confirmed=mtf_confirmed
        )
