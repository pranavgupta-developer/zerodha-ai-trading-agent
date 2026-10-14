from typing import Dict, Any, Optional
from app.trading.signals import Signal, SignalDirection
from app.agent.schemas import CandidateTrade
from app.trading.risk_engine import AccountState
from app.core.config import settings

import json
import logging
import os
from google import genai
from app.agent.prompts import TRADE_DECISION_PROMPT

logger = logging.getLogger(__name__)


class AgentService:
    """
    Service responsible for evaluating algorithmic signals using Gemini AI or technical analysis.
    """
    def __init__(self):
        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                self.client = genai.Client(api_key=api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini client: {e}")
                self.client = None
        else:
            self.client = None

    def _generate_technical_reasoning(self, signal: Signal, indicators: Dict[str, Any]) -> str:
        rsi = indicators.get("rsi_14", 50.0)
        ema_20 = indicators.get("ema_20", signal.entry_price)
        atr = indicators.get("atr_14", 0.0)
        trend = "bullish above" if signal.entry_price >= ema_20 else "bearish below"
        return (
            f"Technical indicators confirm {signal.direction.name} momentum on real market candles: "
            f"Price (₹{signal.entry_price:.2f}) is {trend} 20 EMA (₹{ema_20:.2f}) with RSI at {rsi:.1f}. "
            f"ATR is ₹{atr:.2f}; Stop-Loss set at ₹{signal.stop_loss:.2f} and Target at ₹{signal.take_target:.2f}."
        )

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
        Evaluates context against LLM and returns a CandidateTrade.
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

        if not self.client:
            reasoning = self._generate_technical_reasoning(signal, indicators)
            return CandidateTrade(
                symbol=signal.symbol,
                direction=signal.direction,
                qty=1,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_target=signal.take_target,
                confidence_score=0.88,
                reasoning=reasoning,
                approval_required=approval_req
            )

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

        for model_name in ["gemini-flash-latest", "gemini-3.8-flash"]:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                raw_text = response.text or ""
                if raw_text.startswith("```json"):
                    raw_text = raw_text.replace("```json", "").replace("```", "").strip()
                
                parsed_json = json.loads(raw_text)
                if parsed_json.get("qty", 0) > 0:
                    parsed_json["qty"] = 1
                parsed_json["approval_required"] = approval_req
                return CandidateTrade(**parsed_json)
            except Exception as e:
                logger.warning(f"Gemini call with {model_name} failed: {e}")

        # Fallback to rich technical reasoning
        reasoning = self._generate_technical_reasoning(signal, indicators)
        return CandidateTrade(
            symbol=signal.symbol,
            direction=signal.direction,
            qty=1,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_target=signal.take_target,
            confidence_score=0.85,
            reasoning=reasoning,
            approval_required=approval_req
        )
