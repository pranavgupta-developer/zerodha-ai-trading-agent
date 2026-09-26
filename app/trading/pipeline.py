import logging
from typing import List, Optional, Tuple, Any
from app.trading.signals import Signal, SignalDirection
from app.trading.strategy import EmaCrossoverRsiStrategy
from app.agent.schemas import CandidateTrade
from app.agent.service import AgentService
from app.trading.risk_engine import RiskEngine, AccountState
from app.trading.order_manager import OrderManager, ManagedOrder

logger = logging.getLogger(__name__)

class TradingPipeline:
    """
    Orchestrates the entire trading flow:
    Data -> Strategy -> AI Agent -> Risk Engine -> Order Manager
    """
    def __init__(
        self, 
        strategy: EmaCrossoverRsiStrategy, 
        agent: AgentService, 
        risk_engine: RiskEngine, 
        order_manager: OrderManager
    ):
        self.strategy = strategy
        self.agent = agent
        self.risk_engine = risk_engine
        self.order_manager = order_manager

    def process_tick(
        self, 
        symbol: str, 
        candles: List[Any],
        market_snapshot: dict,
        indicators: dict,
        account_state: AccountState,
        quote_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[CandidateTrade], Optional[ManagedOrder], str]:
        """
        Runs the full pipeline for a new tick/candle.
        Returns (CandidateTrade, ManagedOrder, StatusMessage)
        """
        # 1. Strategy Signal
        signal = self.strategy.generate_signal(symbol, candles)
        if signal.direction == SignalDirection.HOLD:
            return None, None, "Strategy generated HOLD."

        # 2. AI Agent Evaluation
        candidate_trade = self.agent.evaluate_trade(
            signal=signal,
            market_snapshot=market_snapshot,
            indicators=indicators,
            account_state=account_state
        )
        
        if candidate_trade.direction == SignalDirection.HOLD:
            return candidate_trade, None, f"AI Agent rejected trade: {candidate_trade.reasoning}"
            
        if candidate_trade.approval_required:
            # Awaits human-in-the-loop approval
            return candidate_trade, None, "Trade requires human approval."

        # 3. Risk Engine Validation
        # Construct risk signal from CandidateTrade
        risk_signal = Signal(
            symbol=candidate_trade.symbol,
            direction=candidate_trade.direction,
            confidence=candidate_trade.confidence_score,
            entry_price=candidate_trade.entry_price,
            stop_loss=candidate_trade.stop_loss,
            take_target=candidate_trade.take_target,
            reason=candidate_trade.reasoning
        )
        
        is_approved, risk_reason = self.risk_engine.validate_signal(risk_signal, account_state, candidate_trade.qty, quote_data)
        if not is_approved:
            return candidate_trade, None, f"Risk Engine rejected trade: {risk_reason}"

        # 4. Order Execution
        order = self.order_manager.place_order(risk_signal, candidate_trade.qty)
        return candidate_trade, order, f"Order placed successfully: {order.state}"
