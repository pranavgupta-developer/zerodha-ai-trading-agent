import os
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


class ModelRole(str, Enum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"
    FALLBACK = "FALLBACK"
    ARCHIVED = "ARCHIVED"


class ModelStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SHADOW = "SHADOW"
    DEGRADED = "DEGRADED"
    PROMOTABLE = "PROMOTABLE"
    STANDBY = "STANDBY"


@dataclass
class ModelProfile:
    model_id: str
    name: str
    version: str
    role: ModelRole
    status: ModelStatus = ModelStatus.STANDBY
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True
    # Performance Metrics
    total_predictions: int = 0
    completed_predictions: int = 0
    correct_predictions: int = 0
    recent_outcomes: List[bool] = field(default_factory=list)
    recent_brier_scores: List[float] = field(default_factory=list)
    rolling_accuracy: float = 0.0
    brier_score: float = 0.0
    simulated_pnl: float = 0.0
    consecutive_losses: int = 0
    promoted_at: Optional[str] = None
    rolled_back_at: Optional[str] = None


@dataclass
class ShadowPrediction:
    shadow_id: str
    model_id: str
    symbol: str
    predicted_direction: str  # "BUY", "SELL", "HOLD"
    confidence: float
    entry_price: float
    reasoning: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "PENDING"  # "PENDING", "COMPLETED"
    trade_id: Optional[str] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    is_correct: Optional[bool] = None
    exit_timestamp: Optional[str] = None


@dataclass
class RollbackConfig:
    min_evaluations: int = 15                   # Minimum completed predictions before auto-actions
    accuracy_rollback_threshold: float = 0.45   # Drop below 45% -> rollback Champion
    critical_killswitch_threshold: float = 0.35 # Drop below 35% -> emergency stop
    promotion_win_delta: float = 0.05           # Challenger must outperform Champion by 5%
    promotion_min_accuracy: float = 0.55        # Challenger must reach >= 55% accuracy
    rolling_window: int = 20                    # Rolling evaluation window
    enable_auto_rollback: bool = True
    enable_auto_promotion: bool = True


class ModelRegistry:
    """
    Champion–Challenger Model Registry with Shadow Mode Execution,
    Live Accuracy Comparison, and Automatic Rollback / Promotion.
    """
    def __init__(
        self,
        storage_path: str = "model_registry.json",
        config: Optional[RollbackConfig] = None
    ):
        self.storage_path = storage_path
        self.config = config or RollbackConfig()
        self.models: Dict[str, ModelProfile] = {}
        self.shadow_predictions: List[ShadowPrediction] = []
        self._load_state()

        if not self.models:
            self._initialize_default_models()
        else:
            self._ensure_baseline_models()

    def _ensure_baseline_models(self):
        """Ensures that Champion, Challenger, and Fallback baseline models always exist and remain healthy."""
        if not self.get_champion():
            champ = self.models.get("champ_gemini_quant_v1")
            if champ:
                champ.role = ModelRole.CHAMPION
                champ.status = ModelStatus.ACTIVE
                champ.is_active = True
            else:
                self.register_model(ModelProfile(
                    model_id="champ_gemini_quant_v1",
                    name="Gemini-Quant-Ensemble",
                    version="v1.0",
                    role=ModelRole.CHAMPION,
                    status=ModelStatus.ACTIVE,
                    description="Primary production model combining Gemini AI reasoning with quant momentum factors."
                ))
        if not self.get_challenger():
            chall = self.models.get("challenger_xgb_v1_1")
            if chall:
                chall.role = ModelRole.CHALLENGER
                chall.status = ModelStatus.SHADOW
                chall.is_active = True
            else:
                self.register_model(ModelProfile(
                    model_id="challenger_xgb_v1_1",
                    name="XGBoost-Trend-Shadow",
                    version="v1.1",
                    role=ModelRole.CHALLENGER,
                    status=ModelStatus.SHADOW,
                    description="Shadow candidate model leveraging gradient-boosted technical feature trees."
                ))
        if not self.get_fallback():
            fb = self.models.get("fallback_rules_v0_9")
            if fb:
                fb.role = ModelRole.FALLBACK
                fb.status = ModelStatus.STANDBY
                fb.is_active = True
            else:
                self.register_model(ModelProfile(
                    model_id="fallback_rules_v0_9",
                    name="Deterministic-Rule-Fallback",
                    version="v0.9",
                    role=ModelRole.FALLBACK,
                    status=ModelStatus.STANDBY,
                    description="Hardened deterministic EMA+RSI+VWAP technical rule system."
                ))
        self._save_state()

    def _initialize_default_models(self):
        """Initializes standard baseline models if registry is empty."""
        champion = ModelProfile(
            model_id="champ_gemini_quant_v1",
            name="Gemini-Quant-Ensemble",
            version="v1.0",
            role=ModelRole.CHAMPION,
            status=ModelStatus.ACTIVE,
            description="Primary production model combining Gemini AI reasoning with quant momentum factors."
        )
        challenger = ModelProfile(
            model_id="challenger_xgb_v1_1",
            name="XGBoost-Trend-Shadow",
            version="v1.1",
            role=ModelRole.CHALLENGER,
            status=ModelStatus.SHADOW,
            description="Shadow candidate model leveraging gradient-boosted technical feature trees."
        )
        fallback = ModelProfile(
            model_id="fallback_rules_v0_9",
            name="Deterministic-Rule-Fallback",
            version="v0.9",
            role=ModelRole.FALLBACK,
            status=ModelStatus.STANDBY,
            description="Hardened deterministic EMA+RSI+VWAP technical rule system."
        )
        self.register_model(champion)
        self.register_model(challenger)
        self.register_model(fallback)
        self._save_state()

    def _load_state(self):
        """Loads models and shadow predictions from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    for m_dict in data.get("models", []):
                        m_dict["role"] = ModelRole(m_dict["role"])
                        m_dict["status"] = ModelStatus(m_dict["status"])
                        profile = ModelProfile(**m_dict)
                        self.models[profile.model_id] = profile
                    for p_dict in data.get("shadow_predictions", []):
                        self.shadow_predictions.append(ShadowPrediction(**p_dict))
                logger.info(f"Loaded {len(self.models)} models from {self.storage_path}")
            except Exception as e:
                logger.warning(f"Could not load model registry: {e}")

    def _save_state(self):
        """Persists models and shadow predictions to disk."""
        try:
            data = {
                "models": [asdict(m) for m in self.models.values()],
                "shadow_predictions": [asdict(p) for p in self.shadow_predictions[-200:]]
            }
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save model registry: {e}")

    def register_model(self, model: ModelProfile) -> ModelProfile:
        """Registers a model profile in the registry."""
        self.models[model.model_id] = model
        self._save_state()
        return model

    def get_champion(self) -> Optional[ModelProfile]:
        """Returns the currently active champion model."""
        for m in self.models.values():
            if m.role == ModelRole.CHAMPION and m.is_active:
                return m
        return None

    def get_challenger(self) -> Optional[ModelProfile]:
        """Returns the active challenger model in shadow mode."""
        for m in self.models.values():
            if m.role == ModelRole.CHALLENGER and m.is_active:
                return m
        return None

    def get_fallback(self) -> Optional[ModelProfile]:
        """Returns the deterministic fallback model."""
        for m in self.models.values():
            if m.role == ModelRole.FALLBACK and m.is_active:
                return m
        return None

    def evaluate_shadow(
        self,
        symbol: str,
        indicators: Dict[str, Any],
        entry_price: float,
        trade_id: Optional[str] = None
    ) -> Optional[ShadowPrediction]:
        """
        Runs the Challenger model in shadow mode on live market signals.
        Produces a shadow prediction for comparison against actual trade outcomes.
        """
        challenger = self.get_challenger()
        if not challenger:
            return None

        clean_symbol = symbol.replace(".NS", "").strip()
        rsi = float(indicators.get("rsi_14", 50.0))
        ema_20 = float(indicators.get("ema_20", entry_price))
        atr = float(indicators.get("atr_14", 0.0))

        # Challenger Decision Logic: Multi-factor momentum & volatility confirmation
        # Evaluates trend continuation with ATR confirmation
        direction = "HOLD"
        confidence = 0.50
        reasoning = "Neutral market momentum."

        if rsi >= 54.0 and entry_price >= ema_20:
            direction = "BUY"
            rsi_strength = min(0.35, (rsi - 50.0) / 100.0)
            confidence = round(0.55 + rsi_strength, 4)
            reasoning = f"Challenger Bullish: RSI {rsi:.1f} > 54 and Price above EMA 20 (ATR: ₹{atr:.2f})"
        elif rsi <= 46.0 and entry_price <= ema_20:
            direction = "SELL"
            rsi_weakness = min(0.35, (50.0 - rsi) / 100.0)
            confidence = round(0.55 + rsi_weakness, 4)
            reasoning = f"Challenger Bearish: RSI {rsi:.1f} < 46 and Price below EMA 20 (ATR: ₹{atr:.2f})"

        shadow_id = f"shadow_{challenger.model_id}_{clean_symbol}_{int(datetime.now(timezone.utc).timestamp())}_{len(self.shadow_predictions)}"
        pred = ShadowPrediction(
            shadow_id=shadow_id,
            model_id=challenger.model_id,
            symbol=clean_symbol,
            predicted_direction=direction,
            confidence=confidence,
            entry_price=round(float(entry_price), 2),
            reasoning=reasoning,
            trade_id=trade_id
        )
        self.shadow_predictions.append(pred)
        challenger.total_predictions += 1
        self._save_state()
        logger.info(f"ModelRegistry generated Shadow Prediction {shadow_id} for {clean_symbol} [{direction}] conf={confidence:.2f}")
        return pred

    def record_trade_outcome(
        self,
        trade_id: Optional[str],
        symbol: str,
        exit_price: float,
        realized_pnl: float,
        is_champion_correct: bool = True,
        champion_confidence: float = 0.85,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Registers actual trade execution outcome, updating performance for Champion
        and resolving corresponding shadow predictions for Challenger.
        Checks auto-rollback and auto-promotion triggers.
        """
        if "is_correct" in kwargs:
            is_champion_correct = kwargs["is_correct"]
        if "confidence" in kwargs:
            champion_confidence = kwargs["confidence"]
        clean_symbol = symbol.replace(".NS", "").strip()
        champion = self.get_champion()
        challenger = self.get_challenger()

        champ_stats = None
        challenger_stats = None
        action_triggered = None
        action_details = ""

        # 1. Update Champion Metrics
        if champion:
            champion.completed_predictions += 1
            if is_champion_correct:
                champion.correct_predictions += 1
                champion.consecutive_losses = 0
            else:
                champion.consecutive_losses += 1

            champion.recent_outcomes.append(is_champion_correct)
            if len(champion.recent_outcomes) > self.config.rolling_window * 2:
                champion.recent_outcomes = champion.recent_outcomes[-self.config.rolling_window:]

            window = champion.recent_outcomes[-self.config.rolling_window:]
            champion.rolling_accuracy = round(float(sum(1 for x in window if x) / len(window)), 4) if window else 0.0

            # Brier Score = (confidence - actual_outcome)^2
            brier_single = (champion_confidence - (1.0 if is_champion_correct else 0.0)) ** 2
            champion.recent_brier_scores.append(brier_single)
            champion.brier_score = round(float(sum(champion.recent_brier_scores) / len(champion.recent_brier_scores)), 4)

            champion.simulated_pnl = round(champion.simulated_pnl + realized_pnl, 2)
            champ_stats = {
                "model_id": champion.model_id,
                "rolling_accuracy": champion.rolling_accuracy,
                "is_correct": is_champion_correct,
                "consecutive_losses": champion.consecutive_losses,
                "completed": champion.completed_predictions
            }

        # 2. Update Challenger Metrics from matching Shadow Prediction
        matched_shadow: Optional[ShadowPrediction] = None
        for sp in reversed(self.shadow_predictions):
            if sp.status == "PENDING":
                if trade_id and sp.trade_id == trade_id:
                    matched_shadow = sp
                    break
                elif sp.symbol == clean_symbol:
                    matched_shadow = sp
                    break

        if matched_shadow and challenger:
            is_challenger_correct = False
            if matched_shadow.predicted_direction == "BUY":
                is_challenger_correct = bool(realized_pnl > 0 or exit_price > matched_shadow.entry_price)
            elif matched_shadow.predicted_direction == "SELL":
                is_challenger_correct = bool(realized_pnl > 0 or exit_price < matched_shadow.entry_price)
            else:
                is_challenger_correct = bool(abs(realized_pnl) < 1.0)

            matched_shadow.status = "COMPLETED"
            matched_shadow.exit_price = round(float(exit_price), 2)
            matched_shadow.realized_pnl = round(float(realized_pnl), 2)
            matched_shadow.is_correct = is_challenger_correct
            matched_shadow.exit_timestamp = datetime.now(timezone.utc).isoformat()

            challenger.completed_predictions += 1
            if is_challenger_correct:
                challenger.correct_predictions += 1
                challenger.consecutive_losses = 0
            else:
                challenger.consecutive_losses += 1

            challenger.recent_outcomes.append(is_challenger_correct)
            if len(challenger.recent_outcomes) > self.config.rolling_window * 2:
                challenger.recent_outcomes = challenger.recent_outcomes[-self.config.rolling_window:]

            c_window = challenger.recent_outcomes[-self.config.rolling_window:]
            challenger.rolling_accuracy = round(float(sum(1 for x in c_window if x) / len(c_window)), 4) if c_window else 0.0
            challenger.simulated_pnl = round(challenger.simulated_pnl + (realized_pnl if is_challenger_correct else -abs(realized_pnl)), 2)

            challenger_stats = {
                "model_id": challenger.model_id,
                "rolling_accuracy": challenger.rolling_accuracy,
                "is_correct": is_challenger_correct,
                "completed": challenger.completed_predictions
            }

        # 3. Check Automatic Rollback / Promotion Rules
        if champion and champion.completed_predictions >= self.config.min_evaluations:
            # 3a. Critical Degradation -> Killswitch Alert
            if champion.rolling_accuracy < self.config.critical_killswitch_threshold:
                action_triggered = "KILLSWITCH_TRIGGERED"
                action_details = (
                    f"CRITICAL MODEL DEGRADATION: Champion accuracy dropped to {champion.rolling_accuracy*100:.1f}% "
                    f"(below critical threshold {self.config.critical_killswitch_threshold*100:.1f}%)."
                )
                champion.status = ModelStatus.DEGRADED
                self.rollback_champion(reason=action_details)

            # 3b. Standard Degradation -> Auto-Rollback
            elif self.config.enable_auto_rollback and champion.rolling_accuracy < self.config.accuracy_rollback_threshold:
                action_triggered = "ROLLBACK_TRIGGERED"
                action_details = (
                    f"Champion accuracy {champion.rolling_accuracy*100:.1f}% dropped below threshold "
                    f"{self.config.accuracy_rollback_threshold*100:.1f}%. Rolling back."
                )
                self.rollback_champion(reason=action_details)

        # 3c. Auto-Promotion of Challenger
        if (
            self.config.enable_auto_promotion and 
            challenger and 
            champion and 
            challenger.completed_predictions >= self.config.min_evaluations and
            challenger.rolling_accuracy >= self.config.promotion_min_accuracy
        ):
            delta = challenger.rolling_accuracy - champion.rolling_accuracy
            if delta >= self.config.promotion_win_delta:
                action_triggered = "PROMOTION_TRIGGERED"
                action_details = (
                    f"Challenger {challenger.name} outperforming Champion {champion.name} by "
                    f"{delta*100:.1f}% (Acc: {challenger.rolling_accuracy*100:.1f}% vs {champion.rolling_accuracy*100:.1f}%). Auto-promoting."
                )
                self.promote_challenger(reason=action_details)

        self._save_state()
        return {
            "champion": champ_stats,
            "challenger": challenger_stats,
            "action_triggered": action_triggered,
            "details": action_details
        }

    def promote_challenger(self, reason: str = "Manual Promotion") -> Dict[str, Any]:
        """
        Promotes the current Challenger to Champion, demoting current Champion to Challenger.
        """
        old_champion = self.get_champion()
        challenger = self.get_challenger()

        if not challenger:
            self._ensure_baseline_models()
            challenger = self.get_challenger()

        if not challenger:
            return {"status": "error", "message": "No active challenger found to promote"}

        now_iso = datetime.now(timezone.utc).isoformat()

        if old_champion:
            old_champion.role = ModelRole.CHALLENGER
            old_champion.status = ModelStatus.SHADOW
            old_champion.rolled_back_at = now_iso

        challenger.role = ModelRole.CHAMPION
        challenger.status = ModelStatus.ACTIVE
        challenger.promoted_at = now_iso

        self._save_state()
        logger.warning(f"MODEL PROMOTED: {challenger.name} ({challenger.version}) is now Champion. Reason: {reason}")
        return {
            "status": "success",
            "new_champion": challenger.name,
            "new_version": challenger.version,
            "demoted_model": old_champion.name if old_champion else None,
            "reason": reason,
            "timestamp": now_iso
        }

    def rollback_champion(self, reason: str = "Manual Rollback") -> Dict[str, Any]:
        """
        Demotes current Champion.
        If Challenger is healthy (accuracy >= promotion_min_accuracy), promotes Challenger.
        Otherwise, activates the deterministic Fallback model.
        """
        champion = self.get_champion()
        challenger = self.get_challenger()
        fallback = self.get_fallback()
        now_iso = datetime.now(timezone.utc).isoformat()

        if champion:
            champion.status = ModelStatus.DEGRADED
            champion.role = ModelRole.ARCHIVED
            champion.rolled_back_at = now_iso

        # Check if challenger can take over
        if challenger and challenger.rolling_accuracy >= self.config.promotion_min_accuracy:
            challenger.role = ModelRole.CHAMPION
            challenger.status = ModelStatus.ACTIVE
            challenger.promoted_at = now_iso
            active_model = challenger
            logger.warning(f"MODEL ROLLBACK: Promoted healthy Challenger {challenger.name} to Champion. Reason: {reason}")
        elif fallback:
            fallback.role = ModelRole.CHAMPION
            fallback.status = ModelStatus.ACTIVE
            fallback.promoted_at = now_iso
            active_model = fallback
            logger.warning(f"MODEL ROLLBACK: Activated Fallback Heuristic {fallback.name}. Reason: {reason}")
        else:
            active_model = None

        self._save_state()
        return {
            "status": "success",
            "active_model": active_model.name if active_model else "NONE",
            "active_version": active_model.version if active_model else "NONE",
            "demoted_champion": champion.name if champion else None,
            "reason": reason,
            "timestamp": now_iso
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns unified Champion–Challenger status for UI and APIs."""
        champion = self.get_champion()
        challenger = self.get_challenger()
        fallback = self.get_fallback()

        win_delta = 0.0
        if champion and challenger:
            win_delta = round(challenger.rolling_accuracy - champion.rolling_accuracy, 4)

        # Health assessment
        health_status = "HEALTHY"
        if champion:
            if champion.rolling_accuracy < self.config.critical_killswitch_threshold and champion.completed_predictions >= self.config.min_evaluations:
                health_status = "CRITICAL_DEGRADATION"
            elif champion.rolling_accuracy < self.config.accuracy_rollback_threshold and champion.completed_predictions >= self.config.min_evaluations:
                health_status = "DEGRADED"
            elif challenger and win_delta >= self.config.promotion_win_delta and challenger.completed_predictions >= self.config.min_evaluations:
                health_status = "PROMOTABLE"

        return {
            "health_status": health_status,
            "champion": {
                "model_id": champion.model_id if champion else None,
                "name": champion.name if champion else "None",
                "version": champion.version if champion else "N/A",
                "rolling_accuracy": champion.rolling_accuracy if champion else 0.0,
                "completed": champion.completed_predictions if champion else 0,
                "simulated_pnl": champion.simulated_pnl if champion else 0.0,
                "status": champion.status.value if champion else "INACTIVE",
                "consecutive_losses": champion.consecutive_losses if champion else 0
            },
            "challenger": {
                "model_id": challenger.model_id if challenger else None,
                "name": challenger.name if challenger else "None",
                "version": challenger.version if challenger else "N/A",
                "rolling_accuracy": challenger.rolling_accuracy if challenger else 0.0,
                "completed": challenger.completed_predictions if challenger else 0,
                "simulated_pnl": challenger.simulated_pnl if challenger else 0.0,
                "status": challenger.status.value if challenger else "INACTIVE",
                "win_delta": win_delta
            },
            "fallback": {
                "name": fallback.name if fallback else "None",
                "version": fallback.version if fallback else "N/A",
                "is_active": fallback.role == ModelRole.CHAMPION if fallback else False
            },
            "config": {
                "min_evaluations": self.config.min_evaluations,
                "accuracy_rollback_threshold": self.config.accuracy_rollback_threshold,
                "promotion_win_delta": self.config.promotion_win_delta,
                "rolling_window": self.config.rolling_window
            },
            "pending_shadow_predictions": len([p for p in self.shadow_predictions if p.status == "PENDING"])
        }
