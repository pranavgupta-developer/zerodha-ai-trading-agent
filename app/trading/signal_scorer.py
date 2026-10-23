from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from app.trading.signals import Signal, SignalDirection

class SignalScore(BaseModel):
    total_score: float = Field(..., ge=0.0, le=100.0, description="Overall signal quality score (0 to 100)")
    breakdown: Dict[str, float] = Field(default_factory=dict, description="Factor breakdown scores")
    is_high_quality: bool = Field(..., description="Whether score meets minimum threshold")
    rationale: str = Field(..., description="Detailed explanation of score components")

class SignalQualityScorer:
    """
    Quantitative Multi-Factor Signal Quality Scorer (0-100 Score).
    Evaluates:
      1. Trend Strength (0-25 pts): Spread between fast & slow moving averages + MTF confirmation.
      2. Momentum Confirmation (0-20 pts): RSI positioning within optimal expansion zones.
      3. Volume Expansion (0-15 pts): Volume relative to 20-period rolling average.
      4. ML Conviction & Expected Return (0-25 pts): Predictive model confidence and return hurdle.
      5. Market Regime Suitability (0-15 pts): Harmony with overarching macroeconomic/volatility regime.
    """
    def __init__(self, min_quality_threshold: float = 60.0):
        self.min_quality_threshold = min_quality_threshold

    def calculate_score(
        self,
        signal: Signal,
        indicators: Optional[Dict[str, Any]] = None,
        candles: Optional[List[Any]] = None,
        ml_confidence: Optional[float] = None,
        expected_return_pct: Optional[float] = None
    ) -> SignalScore:
        if signal.direction == SignalDirection.HOLD:
            return SignalScore(
                total_score=0.0,
                breakdown={"trend": 0.0, "momentum": 0.0, "volume": 0.0, "ml": 0.0, "regime": 0.0},
                is_high_quality=False,
                rationale="Signal is HOLD. Quality score is 0.0."
            )

        indicators = indicators or {}
        
        # 1. Trend Strength (0-25 pts)
        trend_score = 10.0 # baseline for having valid crossover
        if signal.mtf_confirmed:
            trend_score += 10.0
        
        fast_ema = indicators.get("ema_9") or indicators.get("ema_fast")
        slow_ema = indicators.get("ema_21") or indicators.get("ema_slow") or indicators.get("ema_20")
        if fast_ema and slow_ema and slow_ema > 0:
            spread_pct = abs(float(fast_ema) - float(slow_ema)) / float(slow_ema) * 100.0
            if spread_pct >= 0.5:
                trend_score += 5.0
            elif spread_pct >= 0.2:
                trend_score += 3.0
            else:
                trend_score += 1.0
        else:
            trend_score += 3.0
        trend_score = min(25.0, trend_score)

        # 2. Momentum Confirmation (0-20 pts)
        rsi = float(indicators.get("rsi_14", 50.0))
        momentum_score = 0.0
        if signal.direction == SignalDirection.BUY:
            if 52.0 <= rsi <= 68.0:
                momentum_score = 20.0
            elif 45.0 <= rsi < 52.0:
                momentum_score = 14.0
            elif 68.0 < rsi < 75.0:
                momentum_score = 10.0
            else:
                momentum_score = 4.0
        else: # SELL
            if 32.0 <= rsi <= 48.0:
                momentum_score = 20.0
            elif 48.0 < rsi <= 55.0:
                momentum_score = 14.0
            elif 25.0 < rsi < 32.0:
                momentum_score = 10.0
            else:
                momentum_score = 4.0

        # 3. Volume Expansion (0-15 pts)
        volume_score = 7.5 # default median if candle history missing
        if candles and len(candles) >= 5:
            volumes = [float(c.volume) for c in candles]
            curr_vol = volumes[-1]
            avg_vol = sum(volumes[-20:]) / min(len(volumes), 20)
            if avg_vol > 0:
                vol_ratio = curr_vol / avg_vol
                if vol_ratio >= 1.8:
                    volume_score = 15.0
                elif vol_ratio >= 1.2:
                    volume_score = 12.0
                elif vol_ratio >= 0.9:
                    volume_score = 9.0
                else:
                    volume_score = 4.0

        # 4. ML Conviction, Alignment & Expected Return (0-25 pts)
        conf = ml_confidence if ml_confidence is not None else signal.confidence
        exp_ret = expected_return_pct if expected_return_pct is not None else signal.expected_return_pct
        
        # Base confidence contributes up to 12 pts
        ml_base = min(12.0, conf * 12.0)
        
        # Expected return contributes up to 8 pts
        ret_pts = 0.0
        if exp_ret >= 1.5:
            ret_pts = 8.0
        elif exp_ret >= 1.0:
            ret_pts = 6.0
        elif exp_ret >= 0.5:
            ret_pts = 4.0
        elif exp_ret > 0.0:
            ret_pts = 2.0

        # Directional alignment bonus / penalty (up to +/- 5 pts)
        alignment_pts = 2.5  # Neutral default when no explicit ML prediction tag
        if indicators and isinstance(indicators, dict):
            ml_pred = indicators.get("ml_prediction")
            if ml_pred:
                pred_str = str(ml_pred).upper()
                if (signal.direction == SignalDirection.BUY and pred_str in ("UP", "BUY")) or \
                   (signal.direction == SignalDirection.SELL and pred_str in ("DOWN", "SELL")):
                    alignment_pts = 5.0
                elif (signal.direction == SignalDirection.BUY and pred_str in ("DOWN", "SELL")) or \
                     (signal.direction == SignalDirection.SELL and pred_str in ("UP", "BUY")):
                    alignment_pts = -5.0

        ml_score = max(0.0, min(25.0, ml_base + ret_pts + alignment_pts))

        # 5. Market Regime Suitability (0-15 pts)
        regime = signal.market_regime
        regime_score = 5.0
        if signal.direction == SignalDirection.BUY and regime == "BULLISH_TREND":
            regime_score = 15.0
        elif signal.direction == SignalDirection.SELL and regime == "BEARISH_TREND":
            regime_score = 15.0
        elif regime == "SIDEWAYS":
            regime_score = 8.0
        elif regime == "HIGH_VOLATILITY":
            regime_score = 6.0
        elif regime in ("UNKNOWN", "", None):
            regime_score = 10.0

        total_score = round(trend_score + momentum_score + volume_score + ml_score + regime_score, 1)
        total_score = max(0.0, min(100.0, total_score))
        is_high_quality = total_score >= self.min_quality_threshold

        breakdown = {
            "trend": round(trend_score, 1),
            "momentum": round(momentum_score, 1),
            "volume": round(volume_score, 1),
            "ml": round(ml_score, 1),
            "regime": round(regime_score, 1)
        }

        rationale = (
            f"Score: {total_score}/100 (Trend: {trend_score:.1f}, Momentum: {momentum_score:.1f}, "
            f"Volume: {volume_score:.1f}, ML: {ml_score:.1f}, Regime: {regime_score:.1f}) | "
            f"Quality: {'PASSED' if is_high_quality else 'REJECTED'}"
        )

        return SignalScore(
            total_score=total_score,
            breakdown=breakdown,
            is_high_quality=is_high_quality,
            rationale=rationale
        )
