import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class AnomalyDetector:
    """
    Runtime Behavioral Protection using Isolation Forest.
    Detects abnormal trading patterns, strategy deviations, and data anomalies.
    """
    def __init__(self, contamination: float = 0.05):
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.is_fitted = False
        self.baseline_data = []
        
        # Seed with synthetic "normal" operational parameters to allow immediate runtime protection
        self._seed_baseline()

    def _seed_baseline(self):
        """
        Provides the model with standard normal operational boundaries.
        Features mapping:
        0: Orders per minute (Normal: 0-6)
        1: Order size as % of portfolio (Normal: 0.05%-15%)
        2: Portfolio concentration in single asset (Normal: 0.05%-30%)
        3: AI Confidence Score (Normal: 0.5 to 0.98)
        4: Market data lag in ms (Normal: 20ms - 1000ms)
        """
        np.random.seed(42)
        for _ in range(400):
            self.baseline_data.append([
                np.random.uniform(0, 6),           # orders_per_minute
                np.random.uniform(0.0005, 0.15),   # order_value_pct (0.05% to 15%)
                np.random.uniform(0.0005, 0.30),   # concentration_pct (0.05% to 30%)
                np.random.uniform(0.50, 0.98),     # ai_confidence
                np.random.uniform(20, 1000)        # data_lag_ms
            ])
        columns = ['orders_per_minute', 'order_value_pct', 'concentration_pct', 'ai_confidence', 'data_lag_ms']
        df = pd.DataFrame(self.baseline_data, columns=columns)
        self.fit(df)

    def fit(self, df: pd.DataFrame):
        self.model.fit(df)
        self.is_fitted = True

    def evaluate(self, 
                 orders_per_minute: float, 
                 order_value_pct: float, 
                 concentration_pct: float, 
                 ai_confidence: float, 
                 data_lag_ms: float) -> Dict[str, Any]:
        """
        Evaluates the current system state for anomalies.
        Returns whether to halt trading.
        """
        if not self.is_fitted:
            return {"is_anomaly": False, "anomaly_score": 0.0, "halt_trading": False}
            
        columns = ['orders_per_minute', 'order_value_pct', 'concentration_pct', 'ai_confidence', 'data_lag_ms']
        df_features = pd.DataFrame([[
            orders_per_minute, 
            order_value_pct, 
            concentration_pct, 
            ai_confidence, 
            data_lag_ms
        ]], columns=columns)
        
        prediction = self.model.predict(df_features)[0]  # 1 for normal, -1 for anomaly
        score = self.model.score_samples(df_features)[0] # Lower is more anomalous
        
        # Anomaly is flagged if model predicts -1 or score is sufficiently low
        is_anomaly = bool(prediction == -1 or score < -0.50)
        
        # Halt trading only for dangerous directional anomalies (excessive frequency, fat-finger size, high concentration, or severe data lag)
        # Small orders, low frequency, and low latency are inherently safe and must never trigger a halt.
        is_dangerous_risk = bool(
            orders_per_minute > 10.0
            or order_value_pct > 0.25
            or concentration_pct > 0.40
            or data_lag_ms > 2500.0
            or (ai_confidence < 0.25 and (order_value_pct > 0.15 or orders_per_minute > 5.0))
        )
        
        halt_trading = bool(is_anomaly and is_dangerous_risk)
        
        if halt_trading:
            logger.critical(f"CRITICAL ANOMALY DETECTED! HALTING TRADING. Score: {score:.4f}. Features: {df_features.to_dict(orient='records')[0]}")
        elif is_anomaly:
            logger.warning(f"ANOMALY DETECTED (Warning). Score: {score:.4f}. Features: {df_features.to_dict(orient='records')[0]}")
            
        return {
            "is_anomaly": bool(is_anomaly),
            "anomaly_score": float(score),
            "halt_trading": halt_trading
        }
