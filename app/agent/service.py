from typing import Dict, Any
from app.trading.signals import Signal, SignalDirection
from app.agent.schemas import CandidateTrade
from app.trading.risk_engine import AccountState

import json
import logging
import os
from google import genai
from pydantic import ValidationError
from app.agent.prompts import TRADE_DECISION_PROMPT

logger = logging.getLogger(__name__)

class AgentService:
    """
    Service responsible for querying the LLM to evaluate algorithmic signals.
    """
    def __init__(self):
        # Initialize actual LLM client
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            logger.warning("GEMINI_API_KEY not found in environment, LLM calls will fail.")
            self.client = None

    def evaluate_trade(
        self, 
        signal: Signal, 
        market_snapshot: Dict[str, Any], 
        indicators: Dict[str, Any], 
        account_state: AccountState
    ) -> CandidateTrade:
        """
        Sends context to the LLM and returns a CandidateTrade.
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
            
        if not self.client:
            logger.error("Cannot evaluate trade because Gemini client is not initialized.")
            return CandidateTrade(
                symbol=signal.symbol,
                direction=SignalDirection.HOLD,
                qty=0,
                entry_price=signal.entry_price,
                stop_loss=0.0,
                take_target=0.0,
                confidence_score=0.0,
                reasoning="System Error: LLM client not initialized.",
                approval_required=False
            )

        # Build prompt
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
            account_state=json.dumps({
                "available_margin": account_state.available_margin,
                "unrealized_pnl": account_state.unrealized_pnl,
                "realized_pnl": account_state.realized_pnl
            })
        )

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            raw_text = response.text
            # Clean up potential markdown formatting
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()
            
            parsed_json = json.loads(raw_text)
            
            # For this MVP, we enforce a quantity of 1 for safety if the LLM suggests > 0
            # You can remove this constraint later
            if parsed_json.get("qty", 0) > 0:
                parsed_json["qty"] = 1
                
            # FORCE AUTONOMOUS MODE: No human approval required for any AI-approved trade
            parsed_json["approval_required"] = False
                
            return CandidateTrade(**parsed_json)
            
        except Exception as e:
            logger.error(f"Error querying LLM or parsing response: {e}")
            return CandidateTrade(
                symbol=signal.symbol,
                direction=SignalDirection.HOLD,
                qty=0,
                entry_price=signal.entry_price,
                stop_loss=0.0,
                take_target=0.0,
                confidence_score=0.0,
                reasoning=f"LLM Error: {str(e)}",
                approval_required=False
            )
