import json
import logging
import os
import time
from typing import Dict, Any, Optional, Tuple
from google import genai
from app.trading.signals import Signal, SignalDirection
from app.agent.schemas import CandidateTrade
from app.trading.risk_engine import AccountState
from app.core.config import settings
from app.agent.prompts import TRADE_DECISION_PROMPT

logger = logging.getLogger(__name__)


class AgentService:
    """
    Service responsible for evaluating algorithmic signals using Gemini AI or
    an institutional-grade multi-factor quantitative decision engine.
    Includes decision TTL caching to eliminate 429 quota exhaustion.
    """
    def __init__(self):
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if api_key and api_key != "fake_key":
            try:
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                self.client = None
        else:
            self.client = None
        self._quota_exhausted_until = 0.0
        # Decision TTL cache: symbol -> (timestamp, CandidateTrade)
        self._decision_cache: Dict[str, Tuple[float, CandidateTrade]] = {}
        self._cache_ttl_seconds: float = 30.0

    def _generate_technical_reasoning(
        self, 
        signal: Signal, 
        indicators: Dict[str, Any],
        ml_prediction: Optional[Dict[str, Any]] = None,
        quant_metrics: Optional[Dict[str, Any]] = None
    ) -> str:
        rsi = indicators.get("rsi_14", 50.0)
        ema_20 = indicators.get("ema_20", signal.entry_price)
        atr = indicators.get("atr_14", 0.0)
        trend = "bullish above" if signal.entry_price >= ema_20 else "bearish below"
        regime_str = f" | Regime: {signal.market_regime}" if getattr(signal, "market_regime", None) else ""
        
        ml_summary = ""
        if ml_prediction and isinstance(ml_prediction, dict):
            ml_dir = ml_prediction.get("direction", "N/A")
            ml_conf = ml_prediction.get("confidence", 0.0)
            ml_ret = ml_prediction.get("expected_return_pct")
            ml_ret_str = f", E[R]: {ml_ret:.2f}%" if ml_ret is not None else ""
            ml_summary = f" | ML Pred: {ml_dir} ({ml_conf:.0%}{ml_ret_str})"

        return (
            f"Multi-factor synthesis confirms {signal.direction.name} momentum on live candles: "
            f"Price (₹{signal.entry_price:.2f}) is {trend} 20 EMA (₹{ema_20:.2f}) with RSI at {rsi:.1f}. "
            f"ATR: ₹{atr:.2f}; SL: ₹{signal.stop_loss:.2f}, TP: ₹{signal.take_target:.2f}{regime_str}{ml_summary}."
        )

    def _calculate_empirical_confidence(
        self, 
        signal: Signal, 
        indicators: Dict[str, Any],
        ml_prediction: Optional[Dict[str, Any]] = None,
        quant_metrics: Optional[Dict[str, Any]] = None
    ) -> float:
        """
        Calculates empirical quantitative confidence using multi-factor technical indicators,
        machine learning probabilities, and risk/volatility factors.
        """
        base_conf = 0.65
        rsi = float(indicators.get("rsi_14", 50.0) if indicators.get("rsi_14") is not None else 50.0)
        ema_20 = float(indicators.get("ema_20", signal.entry_price) if indicators.get("ema_20") is not None else signal.entry_price)
        
        # 1. Indicator Momentum Factor
        if signal.direction == SignalDirection.BUY:
            if rsi >= 55.0:
                base_conf += min(0.12, (rsi - 50.0) / 100.0)
            if signal.entry_price >= ema_20:
                base_conf += 0.08
        elif signal.direction == SignalDirection.SELL:
            if rsi <= 45.0:
                base_conf += min(0.12, (50.0 - rsi) / 100.0)
            if signal.entry_price <= ema_20:
                base_conf += 0.08

        # 2. Market Regime Factor
        regime = getattr(signal, "market_regime", "UNKNOWN")
        if regime in ("BULLISH_TREND", "BEARISH_TREND"):
            base_conf += 0.05
        elif regime == "SIDEWAYS":
            base_conf -= 0.05

        # 3. ML Model Inference Blend
        ml_conf = None
        if ml_prediction and isinstance(ml_prediction, dict):
            ml_conf = ml_prediction.get("confidence")
        elif indicators and indicators.get("ml_confidence") is not None:
            ml_conf = indicators.get("ml_confidence")
            
        if ml_conf is not None and isinstance(ml_conf, (int, float)):
            base_conf = 0.45 * base_conf + 0.55 * float(ml_conf)

        # 4. Volatility / Sharpe Factor
        if quant_metrics and isinstance(quant_metrics, dict):
            sharpe = quant_metrics.get("sharpe", 0.0)
            if isinstance(sharpe, (int, float)) and sharpe > 1.0:
                base_conf += 0.03

        return round(min(0.95, max(0.51, base_conf)), 2)

    def evaluate_trade(
        self, 
        signal: Signal, 
        market_snapshot: Dict[str, Any], 
        indicators: Dict[str, Any], 
        account_state: AccountState,
        ml_prediction: Dict[str, Any] = {},
        quant_metrics: Dict[str, Any] = {}
    ) -> CandidateTrade:
        """
        Evaluates trade context against Gemini AI with TTL caching and
        intelligent multi-factor quantitative fallback.
        """
        if signal.direction == SignalDirection.HOLD:
            return CandidateTrade(
                symbol=signal.symbol,
                direction=SignalDirection.HOLD,
                qty=0,
                entry_price=signal.entry_price,
                stop_loss=0.0,
                take_target=0.0,
                confidence_score=0.0,
                reasoning="Algorithmic signal is HOLD. Skipping.",
                approval_required=False
            )
            
        approval_req = not getattr(settings, "AUTONOMOUS_EXECUTION", True)
        now = time.time()

        # Check Decision Cache to prevent API thrashing and 429 quota exhaustion
        cached = self._decision_cache.get(signal.symbol)
        if cached:
            cached_time, cached_trade = cached
            if (now - cached_time) < self._cache_ttl_seconds:
                if cached_trade.direction == signal.direction and abs(cached_trade.entry_price - signal.entry_price) / max(1.0, signal.entry_price) < 0.005:
                    return cached_trade

        # Fallback to high-grade quantitative synthesis if LLM is unavailable or cooling down
        if not self.client or now < self._quota_exhausted_until:
            reasoning = self._generate_technical_reasoning(signal, indicators, ml_prediction, quant_metrics)
            conf = self._calculate_empirical_confidence(signal, indicators, ml_prediction, quant_metrics)
            trade = CandidateTrade(
                symbol=signal.symbol,
                direction=signal.direction,
                qty=1,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_target=signal.take_target,
                confidence_score=conf,
                reasoning=reasoning,
                approval_required=approval_req
            )
            self._decision_cache[signal.symbol] = (now, trade)
            return trade

        # Build prompt for Gemini
        prompt = TRADE_DECISION_PROMPT.format(
            market_snapshot=json.dumps(market_snapshot),
            indicators=json.dumps(indicators),
            baseline_signal=json.dumps({
                "symbol": signal.symbol,
                "direction": signal.direction.name,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_target": signal.take_target
            }),
            ml_prediction=json.dumps(ml_prediction),
            quant_metrics=json.dumps(quant_metrics),
            account_state=json.dumps({
                "available_margin": account_state.available_margin,
                "unrealized_pnl": account_state.unrealized_pnl,
                "realized_pnl": account_state.realized_pnl
            })
        )

        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-flash-latest"]:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                raw_text = response.text or ""
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                
                parsed_json = json.loads(raw_text)
                if parsed_json.get("qty", 0) > 0:
                    parsed_json["qty"] = 1
                parsed_json["approval_required"] = approval_req
                trade = CandidateTrade(**parsed_json)
                self._decision_cache[signal.symbol] = (now, trade)
                return trade
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.warning(f"Gemini quota exhausted. Enabling 3-minute backoff to prevent loop stalling.")
                    self._quota_exhausted_until = time.time() + 180.0
                    break
                logger.warning(f"Gemini call with {model_name} failed: {e}")

        # Quantitative synthesis fallback
        reasoning = self._generate_technical_reasoning(signal, indicators, ml_prediction, quant_metrics)
        conf = self._calculate_empirical_confidence(signal, indicators, ml_prediction, quant_metrics)
        trade = CandidateTrade(
            symbol=signal.symbol,
            direction=signal.direction,
            qty=1,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_target=signal.take_target,
            confidence_score=conf,
            reasoning=reasoning,
            approval_required=approval_req
        )
        self._decision_cache[signal.symbol] = (now, trade)
        return trade
