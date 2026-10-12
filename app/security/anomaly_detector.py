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
        0: Orders per minute (Normal: 0-5)
        1: Order size as % of portfolio (Normal: 1%-15%)
        2: Portfolio concentration in single asset (Normal: 5%-30%)
        3: AI Confidence Score (Normal: 0.6 to 0.95)
        4: Market data lag in ms (Normal: 50ms - 1000ms)
        """
        np.random.seed(42)
        for _ in range(200):
            self.baseline_data.append([
                np.random.uniform(0, 5),          # orders_per_minute
                np.random.uniform(0.01, 0.15),    # order_value_pct
                np.random.uniform(0.05, 0.30),    # concentration_pct
                np.random.uniform(0.6, 0.95),     # ai_confidence
                np.random.uniform(50, 1000)       # data_lag_ms
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
        
        is_anomaly = (prediction == -1)
        
        # Define a critical threshold for halting trading (depends on contamination and data)
        halt_trading = bool(is_anomaly and score < -0.50)
        
        if halt_trading:
            logger.critical(f"CRITICAL ANOMALY DETECTED! HALTING TRADING. Score: {score:.4f}. Features: {df_features.to_dict(orient='records')[0]}")
        elif is_anomaly:
            logger.warning(f"ANOMALY DETECTED (Warning). Score: {score:.4f}. Features: {df_features.to_dict(orient='records')[0]}")
            
        return {
            "is_anomaly": bool(is_anomaly),
            "anomaly_score": float(score),
            "halt_trading": halt_trading
        }
