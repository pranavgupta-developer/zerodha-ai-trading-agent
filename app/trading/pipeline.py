import logging
from typing import List, Optional, Tuple, Any
from app.trading.signals import Signal, SignalDirection
from app.trading.strategy import EmaRsiVwapStrategy
from app.agent.schemas import CandidateTrade
from app.agent.service import AgentService
from app.trading.risk_engine import RiskEngine, AccountState
from app.trading.order_manager import OrderManager, ManagedOrder
from app.trading.position_sizer import DynamicPositionSizer

logger = logging.getLogger(__name__)

class TradingPipeline:
    """
    Orchestrates the entire trading flow:
    Data -> Strategy -> AI Agent -> Dynamic Sizing -> Risk Engine -> Order Manager
    """
    def __init__(
        self, 
        strategy: EmaRsiVwapStrategy, 
        agent: AgentService, 
        risk_engine: RiskEngine, 
        order_manager: OrderManager,
        position_sizer: Optional[DynamicPositionSizer] = None,
        anomaly_detector: Optional[Any] = None,
        model_registry: Optional[Any] = None
    ):
        self.strategy = strategy
        self.agent = agent
        self.risk_engine = risk_engine
        self.order_manager = order_manager
        self.position_sizer = position_sizer or DynamicPositionSizer()
        self.anomaly_detector = anomaly_detector
        self.model_registry = model_registry

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

        # 2b. Dynamic Capital Allocation & Position Sizing
        atr_val = indicators.get("atr_14") if indicators else None
        alloc = self.position_sizer.calculate_allocation(
            symbol=candidate_trade.symbol,
            entry_price=candidate_trade.entry_price,
            stop_loss=candidate_trade.stop_loss,
            account_equity=account_state.available_margin,
            atr=atr_val,
            confidence=candidate_trade.confidence_score,
            available_margin=account_state.available_margin
        )
        candidate_trade.qty = alloc.quantity
        candidate_trade.allocated_capital = alloc.allocated_capital
        candidate_trade.risk_budget = alloc.risk_budget
        candidate_trade.risk_pct = alloc.risk_budget_pct
        candidate_trade.sizing_rationale = alloc.sizing_rationale

        # 2c. Run Challenger in Shadow Mode if ModelRegistry is configured
        if self.model_registry:
            self.model_registry.evaluate_shadow(
                symbol=candidate_trade.symbol,
                indicators=indicators,
                entry_price=candidate_trade.entry_price
            )
            
        # Check if human approval is required
        if candidate_trade.approval_required:
            return candidate_trade, None, "Awaiting operator approval."

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

        # 3b. Runtime Anomaly Detection Check
        if self.anomaly_detector:
            opm = float(account_state.orders_placed_last_minute)
            avail_margin = max(float(account_state.available_margin), 10000.0)
            order_val = float(candidate_trade.qty * candidate_trade.entry_price)
            order_pct = min(1.0, order_val / avail_margin)
            curr_pos_val = float(account_state.open_positions.get(candidate_trade.symbol, 0.0))
            conc_pct = min(1.0, (curr_pos_val + order_val) / avail_margin)
            conf = float(candidate_trade.confidence_score)
            
            anomaly_res = self.anomaly_detector.evaluate(
                orders_per_minute=opm,
                order_value_pct=order_pct,
                concentration_pct=conc_pct,
                ai_confidence=conf,
                data_lag_ms=150.0
            )
            if anomaly_res.get("halt_trading"):
                return candidate_trade, None, f"ANOMALY_HALT: Critical anomaly detected (score {anomaly_res.get('anomaly_score', 0):.4f}). Auto-halting trading."

        # 4. Order Execution
        order = self.order_manager.place_order(risk_signal, candidate_trade.qty)
        return candidate_trade, order, f"Order placed successfully: {order.state}"
