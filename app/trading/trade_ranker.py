from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.agent.schemas import CandidateTrade
from app.trading.signals import SignalDirection

class RankedTrade(BaseModel):
    candidate: CandidateTrade
    rank: int
    composite_priority: float
    risk_adjusted_return: float
    selection_verdict: str  # "SELECTED", "SKIPPED_CAPITAL", "REJECTED_QUALITY"
    reasoning: str = ""

class TradeRanker:
    """
    Cross-Sectional Trade Ranking & Portfolio Selection Engine.
    When multiple watchlist symbols produce candidate signals concurrently,
    this engine filters, scores, ranks, and selects the optimal subset
    to prevent over-concentration and maximize risk-adjusted portfolio return.
    """
    def __init__(self, max_concurrent_selections: int = 3, min_quality_threshold: float = 60.0):
        self.max_concurrent_selections = max_concurrent_selections
        self.min_quality_threshold = min_quality_threshold

    def rank_and_select(
        self,
        candidates: List[CandidateTrade],
        available_margin: float,
        volatilities: Optional[Dict[str, float]] = None
    ) -> List[RankedTrade]:
        if not candidates:
            return []

        volatilities = volatilities or {}
        scored_candidates = []

        for candidate in candidates:
            if candidate.direction == SignalDirection.HOLD:
                continue

            quality = float(candidate.quality_score or 65.0)
            exp_ret = float(candidate.expected_return_pct or 1.0)
            vol = float(volatilities.get(candidate.symbol, 1.5))
            vol = max(vol, 0.2)  # avoid division by zero

            risk_adj_ret = round(exp_ret / vol, 3)
            confidence = float(candidate.confidence_score or 0.8)

            # Composite Priority: 50% Quality Score + 30% Risk-Adjusted Return + 20% Conviction
            priority = round(
                (quality / 100.0) * 0.50 +
                min(risk_adj_ret / 2.0, 1.0) * 0.30 +
                confidence * 0.20,
                4
            )

            scored_candidates.append({
                "candidate": candidate,
                "quality": quality,
                "risk_adj_ret": risk_adj_ret,
                "priority": priority
            })

        # Sort descending by priority
        scored_candidates.sort(key=lambda x: x["priority"], reverse=True)

        ranked_results: List[RankedTrade] = []
        remaining_margin = available_margin
        selected_count = 0

        for idx, item in enumerate(scored_candidates, 1):
            candidate = item["candidate"]
            quality = item["quality"]
            risk_adj_ret = item["risk_adj_ret"]
            priority = item["priority"]
            order_cost = float(candidate.qty * candidate.entry_price)

            verdict = "REJECTED_QUALITY"
            reason = f"Quality score {quality:.1f} < threshold {self.min_quality_threshold:.1f}"

            if quality >= self.min_quality_threshold:
                if selected_count >= self.max_concurrent_selections:
                    verdict = "SKIPPED_CAPITAL"
                    reason = f"Exceeds max concurrent batch selections ({self.max_concurrent_selections})"
                elif order_cost > remaining_margin:
                    verdict = "SKIPPED_CAPITAL"
                    reason = f"Insufficient remaining margin (Required: ₹{order_cost:.2f}, Available: ₹{remaining_margin:.2f})"
                else:
                    verdict = "SELECTED"
                    reason = f"Selected for execution: Priority {priority:.3f}, Risk-Adj Return {risk_adj_ret:.2f}"
                    selected_count += 1
                    remaining_margin = max(0.0, remaining_margin - order_cost)

            ranked_results.append(RankedTrade(
                candidate=candidate,
                rank=idx,
                composite_priority=priority,
                risk_adjusted_return=risk_adj_ret,
                selection_verdict=verdict,
                reasoning=reason
            ))

        return ranked_results
