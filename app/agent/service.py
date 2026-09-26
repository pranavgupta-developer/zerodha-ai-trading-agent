from typing import Dict, Any
from app.trading.signals import Signal, SignalDirection
from app.agent.schemas import CandidateTrade
from app.trading.risk_engine import AccountState

class AgentService:
    """
    Service responsible for querying the LLM to evaluate algorithmic signals.
    """
    def __init__(self):
        # Initialize actual LLM client here in the future
        pass

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
        # TODO: Implement actual LLM call here using app.agent.prompts.TRADE_DECISION_PROMPT
        
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
            
        # Mock LLM decision: accept the trade with a fixed qty
        qty = 50
        
        return CandidateTrade(
            symbol=signal.symbol,
            direction=signal.direction,
            qty=qty,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_target=signal.take_target,
            confidence_score=0.9, # High confidence
            reasoning=f"AI confirmed {signal.direction.value} signal based on momentum and available margin.",
            approval_required=False
        )
