import os
import json
import logging
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)

@dataclass
class PredictionRecord:
    prediction_id: str
    symbol: str
    predicted_direction: str  # "BUY", "SELL", "HOLD"
    confidence: float
    entry_price: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    features: Dict[str, float] = field(default_factory=dict)
    market_regime: str = "SIDEWAYS"  # "BULLISH_TREND", "BEARISH_TREND", "SIDEWAYS", "HIGH_VOLATILITY"
    status: str = "PENDING"  # "PENDING", "COMPLETED"
    trade_id: Optional[str] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    realized_pnl_pct: Optional[float] = None
    exit_reason: Optional[str] = None
    is_correct: Optional[bool] = None
    exit_timestamp: Optional[str] = None
    expected_return_pct: Optional[float] = None
    quality_score: Optional[float] = None
    return_error: Optional[float] = None

class MLMonitor:
    """
    Closed-Loop Machine Learning Performance & Feedback Monitoring.
    Tracks predictions against real trade execution outcomes, calculates rolling accuracy,
    brier calibration score, prediction drift, feature drift, and performance by market regime.
    """
    def __init__(self, storage_path: str = "ml_monitor_records.json"):
        self.storage_path = storage_path
        self.records: List[PredictionRecord] = []
        self._load_records()

    def _load_records(self):
        """Loads records from disk if present."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.records = [PredictionRecord(**item) for item in data]
                logger.info(f"Loaded {len(self.records)} ML prediction records from {self.storage_path}")
            except Exception as e:
                logger.warning(f"Could not load ML monitor records: {e}")
                self.records = []

    def _save_records(self):
        """Persists records to disk safely."""
        try:
            data = [asdict(r) for r in self.records[-500:]]  # keep latest 500
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save ML monitor records: {e}")

    @staticmethod
    def classify_regime(indicators: Dict[str, Any], current_price: float = 0.0) -> str:
        """
        Classifies current market condition into one of 4 regimes:
        BULLISH_TREND, BEARISH_TREND, SIDEWAYS, HIGH_VOLATILITY.
        """
        if not indicators:
            return "SIDEWAYS"

        rsi = float(indicators.get("rsi_14", 50.0))
        ema_20 = float(indicators.get("ema_20", current_price if current_price > 0 else 100.0))
        atr_14 = float(indicators.get("atr_14", 0.0))

        # Check for High Volatility first (ATR > 2.5% of price or explicit volatility > 35%)
        ref_price = current_price if current_price > 0 else ema_20
        if ref_price > 0 and (atr_14 / ref_price > 0.025):
            return "HIGH_VOLATILITY"

        # Check for Trend
        if rsi >= 56.0 and ref_price >= ema_20:
            return "BULLISH_TREND"
        elif rsi <= 44.0 and ref_price <= ema_20:
            return "BEARISH_TREND"
        else:
            return "SIDEWAYS"

    def record_prediction(
        self,
        symbol: str,
        predicted_direction: str,
        confidence: float,
        entry_price: float,
        features: Optional[Dict[str, float]] = None,
        market_regime: Optional[str] = None,
        trade_id: Optional[str] = None,
        prediction_id: Optional[str] = None,
        expected_return_pct: Optional[float] = None,
        quality_score: Optional[float] = None
    ) -> PredictionRecord:
        """
        Records a new ML/Agent signal prediction at trade entry.
        """
        clean_symbol = symbol.replace(".NS", "").strip()
        features = features or {}
        
        if not market_regime:
            market_regime = self.classify_regime(features, entry_price)

        pred_id = prediction_id or f"pred_{clean_symbol}_{int(datetime.now(timezone.utc).timestamp())}_{len(self.records)}"

        record = PredictionRecord(
            prediction_id=pred_id,
            symbol=clean_symbol,
            predicted_direction=predicted_direction.upper(),
            confidence=round(float(confidence), 4),
            entry_price=round(float(entry_price), 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
            features={k: round(float(v), 4) for k, v in features.items() if isinstance(v, (int, float))},
            market_regime=market_regime,
            status="PENDING",
            trade_id=trade_id,
            expected_return_pct=round(float(expected_return_pct), 3) if expected_return_pct is not None else None,
            quality_score=round(float(quality_score), 1) if quality_score is not None else None
        )

        self.records.append(record)
        self._save_records()
        logger.info(f"MLMonitor recorded prediction {pred_id} for {clean_symbol} [{predicted_direction}] conf={confidence:.2f} regime={market_regime}")
        return record

    def record_outcome(
        self,
        symbol: str,
        exit_price: float,
        realized_pnl: float,
        exit_reason: str,
        trade_id: Optional[str] = None,
        realized_pnl_pct: Optional[float] = None  # Pass from ExitEvent.pnl_pct for correct qty-weighted %
    ) -> Optional[PredictionRecord]:
        """
        Closes the loop when a trade exits, comparing predicted direction against actual outcome.
        """
        clean_symbol = symbol.replace(".NS", "").strip()
        
        # Match latest pending prediction for this symbol or trade_id
        matched: Optional[PredictionRecord] = None
        for record in reversed(self.records):
            if record.status == "PENDING":
                if trade_id and record.trade_id == trade_id:
                    matched = record
                    break
                elif record.symbol == clean_symbol:
                    matched = record
                    break

        if not matched:
            logger.debug(f"No pending prediction found in MLMonitor for symbol {clean_symbol}")
            return None

        # Determine if prediction was correct
        # BUY is correct if realized_pnl > 0 or exit_price > entry_price
        # SELL (Short) is correct if realized_pnl > 0 or exit_price < entry_price
        is_correct = False
        if matched.predicted_direction == "BUY":
            is_correct = bool(realized_pnl > 0 or (exit_price > matched.entry_price and realized_pnl >= 0))
        elif matched.predicted_direction == "SELL":
            is_correct = bool(realized_pnl > 0 or (exit_price < matched.entry_price and realized_pnl >= 0))
        else:
            is_correct = bool(abs(realized_pnl) < 1.0)  # HOLD prediction

        # Use caller-supplied pnl_pct (from ExitEvent) if available; it is quantity-weighted.
        # Fallback: per-share approximation — only valid when realized_pnl is also per-share.
        if realized_pnl_pct is not None:
            pnl_pct = realized_pnl_pct
        else:
            cost_basis = matched.entry_price
            pnl_pct = (realized_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

        matched.status = "COMPLETED"
        matched.exit_price = round(float(exit_price), 2)
        matched.realized_pnl = round(float(realized_pnl), 2)
        matched.realized_pnl_pct = round(float(pnl_pct), 2)
        matched.exit_reason = exit_reason
        matched.is_correct = is_correct
        matched.exit_timestamp = datetime.now(timezone.utc).isoformat()
        if matched.expected_return_pct is not None:
            matched.return_error = round(abs(matched.expected_return_pct - pnl_pct), 3)

        self._save_records()
        logger.info(
            f"MLMonitor recorded outcome for {matched.prediction_id}: "
            f"Correct={is_correct} (P&L: ₹{realized_pnl:.2f}, Reason: {exit_reason})"
        )
        return matched

    def calculate_rolling_accuracy(self, window: int = 20) -> float:
        """Calculates accuracy over the last N completed trades."""
        completed = [r for r in self.records if r.status == "COMPLETED" and r.is_correct is not None]
        if not completed:
            return 0.0
        subset = completed[-window:]
        correct_count = sum(1 for r in subset if r.is_correct)
        return round(float(correct_count / len(subset)), 4)

    def calculate_brier_score(self) -> float:
        """
        Calculates Brier Score (Mean Squared Error between predicted probability/confidence and binary outcome).
        Lower is better (0.0 = perfect calibration, 0.25 = uninformative).
        """
        completed = [r for r in self.records if r.status == "COMPLETED" and r.is_correct is not None]
        if not completed:
            return 0.0
        sq_errors = [((r.confidence) - (1.0 if r.is_correct else 0.0)) ** 2 for r in completed]
        return round(float(np.mean(sq_errors)), 4)

    def calculate_expected_return_mae(self, window: int = 50) -> float:
        """
        Calculates Mean Absolute Error between predicted expected return % and actual realized return %.
        """
        completed = [r for r in self.records if r.status == "COMPLETED" and r.return_error is not None]
        if not completed:
            return 0.0
        subset = completed[-window:]
        return round(float(np.mean([r.return_error for r in subset])), 4)

    def get_regime_performance_summary(self) -> Dict[str, Any]:
        """
        Aggregates completed trade performance segmented by market regime.
        """
        summary = {
            "BULLISH_TREND": {"trades": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0},
            "BEARISH_TREND": {"trades": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0},
            "SIDEWAYS": {"trades": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0},
            "HIGH_VOLATILITY": {"trades": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0}
        }
        for r in self.records:
            if r.status == "COMPLETED" and r.market_regime in summary:
                reg = summary[r.market_regime]
                reg["trades"] += 1
                if r.is_correct:
                    reg["wins"] += 1
                if r.realized_pnl:
                    reg["total_pnl"] = round(reg["total_pnl"] + r.realized_pnl, 2)

        for reg, stats in summary.items():
            if stats["trades"] > 0:
                stats["win_rate"] = round(float(stats["wins"] / stats["trades"]) * 100.0, 1)

        return summary

    def detect_prediction_drift(self, reference_window: int = 40, current_window: int = 20) -> Dict[str, Any]:
        """
        Detects drift in predicted confidence distributions and direction frequencies between
        a reference historical window and the current window.
        """
        if len(self.records) < (reference_window + current_window):
            # Not enough data for statistical divergence test
            return {
                "drift_detected": False,
                "confidence_drift": 0.0,
                "direction_drift": 0.0,
                "reason": "Insufficient sample size (requires at least 60 predictions)"
            }

        ref_records = self.records[-(reference_window + current_window):-current_window]
        curr_records = self.records[-current_window:]

        ref_conf = [r.confidence for r in ref_records]
        curr_conf = [r.confidence for r in curr_records]

        # Shift in mean confidence
        conf_mean_diff = abs(float(np.mean(curr_conf) - np.mean(ref_conf)))

        # Shift in BUY percentage
        ref_buy_pct = sum(1 for r in ref_records if r.predicted_direction == "BUY") / len(ref_records)
        curr_buy_pct = sum(1 for r in curr_records if r.predicted_direction == "BUY") / len(curr_records)
        direction_shift = abs(float(curr_buy_pct - ref_buy_pct))

        drift_detected = bool(conf_mean_diff > 0.15 or direction_shift > 0.30)
        
        reason = "Normal distribution stability"
        if drift_detected:
            reason = f"Significant shift detected: Confidence diff={conf_mean_diff:.3f}, Direction shift={direction_shift:.3f}"

        return {
            "drift_detected": drift_detected,
            "confidence_drift": round(conf_mean_diff, 4),
            "direction_drift": round(direction_shift, 4),
            "reason": reason
        }

    def detect_feature_drift(self, reference_window: int = 40, current_window: int = 20) -> Dict[str, Any]:
        """
        Monitors input technical indicators (e.g. RSI, ATR) across rolling windows for statistical shifts.
        """
        records_with_features = [r for r in self.records if r.features]
        if len(records_with_features) < (reference_window + current_window):
            return {
                "drift_detected": False,
                "feature_shifts": {},
                "reason": "Insufficient samples for feature drift evaluation"
            }

        ref_records = records_with_features[-(reference_window + current_window):-current_window]
        curr_records = records_with_features[-current_window:]

        feature_keys = ["rsi_14", "atr_14"]
        feature_shifts = {}
        drift_flags = []

        for key in feature_keys:
            ref_vals = [r.features[key] for r in ref_records if key in r.features]
            curr_vals = [r.features[key] for r in curr_records if key in r.features]

            if len(ref_vals) >= 10 and len(curr_vals) >= 10:
                ref_mean = float(np.mean(ref_vals))
                ref_std = float(np.std(ref_vals)) if np.std(ref_vals) > 0 else 1.0
                curr_mean = float(np.mean(curr_vals))

                # Normalized mean shift (z-score like)
                normalized_shift = abs(curr_mean - ref_mean) / ref_std
                is_drift = normalized_shift > 1.8
                feature_shifts[key] = {
                    "ref_mean": round(ref_mean, 2),
                    "curr_mean": round(curr_mean, 2),
                    "normalized_shift": round(normalized_shift, 2),
                    "drift": is_drift
                }
                if is_drift:
                    drift_flags.append(key)

        return {
            "drift_detected": len(drift_flags) > 0,
            "flagged_features": drift_flags,
            "feature_shifts": feature_shifts,
            "reason": f"Drift detected in: {', '.join(drift_flags)}" if drift_flags else "Features within historical variance"
        }

    def get_performance_by_regime(self) -> Dict[str, Any]:
        """
        Breaks down model accuracy, trade counts, and P&L by market regime.
        """
        regimes = ["BULLISH_TREND", "BEARISH_TREND", "SIDEWAYS", "HIGH_VOLATILITY"]
        results = {}

        for regime in regimes:
            matching = [r for r in self.records if r.market_regime == regime and r.status == "COMPLETED"]
            total_trades = len(matching)
            if total_trades == 0:
                results[regime] = {
                    "total_trades": 0,
                    "win_count": 0,
                    "win_rate": 0.0,
                    "total_pnl": 0.0,
                    "avg_pnl": 0.0
                }
                continue

            wins = sum(1 for r in matching if r.is_correct)
            total_pnl = sum(r.realized_pnl or 0.0 for r in matching)
            win_rate = (wins / total_trades) * 100.0

            results[regime] = {
                "total_trades": total_trades,
                "win_count": wins,
                "win_rate": round(win_rate, 2),
                "total_pnl": round(total_pnl, 2),
                "avg_pnl": round(total_pnl / total_trades, 2)
            }

        return results

    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Comprehensive summary of closed-loop ML performance metrics.
        """
        completed = [r for r in self.records if r.status == "COMPLETED"]
        total_predictions = len(self.records)
        completed_count = len(completed)

        overall_acc = 0.0
        win_count = 0
        loss_count = 0
        total_realized_pnl = 0.0

        if completed_count > 0:
            win_count = sum(1 for r in completed if r.is_correct)
            loss_count = completed_count - win_count
            overall_acc = round(win_count / completed_count, 4)
            total_realized_pnl = round(sum(r.realized_pnl or 0.0 for r in completed), 2)

        win_loss_ratio = round(win_count / max(loss_count, 1), 2)
        avg_confidence = round(float(np.mean([r.confidence for r in self.records])) if self.records else 0.0, 3)

        return {
            "total_predictions": total_predictions,
            "completed_evaluations": completed_count,
            "overall_accuracy": overall_acc,
            "rolling_accuracy_20": self.calculate_rolling_accuracy(20),
            "rolling_accuracy_50": self.calculate_rolling_accuracy(50),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_loss_ratio": win_loss_ratio,
            "average_confidence": avg_confidence,
            "brier_score": self.calculate_brier_score(),
            "total_realized_pnl": total_realized_pnl,
            "prediction_drift": self.detect_prediction_drift(),
            "feature_drift": self.detect_feature_drift(),
            "regime_performance": self.get_performance_by_regime(),
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
