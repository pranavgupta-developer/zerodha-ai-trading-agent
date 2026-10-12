import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score
import xgboost as xgb
import logging

logger = logging.getLogger(__name__)

from app.trading.signals import Prediction

class MLEngine:
    def __init__(self, target_period: int = 5):
        """
        Engine for creating features and training predictive models.
        target_period: Number of periods ahead to predict the return.
        """
        self.target_period = target_period
        self.models = {
            'logistic_regression': LogisticRegression(max_iter=1000, random_state=42),
            'random_forest': RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42),
            'gradient_boosting': GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42),
            'xgboost': xgb.XGBClassifier(n_estimators=100, max_depth=3, random_state=42, eval_metric='logloss')
        }
        self.trained_models = {}
        self.metrics = {}
        self.best_model_name = None

    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Creates ML features from OHLCV data.
        Assumes df has 'close', 'high', 'low', 'volume'.
        """
        df = df.copy()
        
        # Returns
        df['ret_1'] = df['close'].pct_change(1)
        df['ret_5'] = df['close'].pct_change(5)
        df['ret_15'] = df['close'].pct_change(15)
        
        # Volatility
        df['vol_15'] = df['ret_1'].rolling(15).std()
        
        # Moving Averages
        df['sma_10'] = df['close'].rolling(10).mean()
        df['sma_30'] = df['close'].rolling(30).mean()
        df['sma_ratio'] = df['sma_10'] / df['sma_30']
        
        # Price to MA
        df['price_to_sma10'] = df['close'] / df['sma_10']
        
        # Drop NaNs
        df = df.dropna()
        return df

    def define_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Defines the prediction target: 1 if return over next `target_period` is > 0, else 0.
        """
        df = df.copy()
        # Future return
        df['future_ret'] = df['close'].pct_change(self.target_period).shift(-self.target_period)
        df['target'] = (df['future_ret'] > 0).astype(int)
        
        # Drop the last `target_period` rows as they won't have a target
        df = df.dropna(subset=['target'])
        return df

    def train_and_evaluate(self, symbol: str, df: pd.DataFrame):
        """
        Builds train/val/test pipeline, trains models, compares them, and saves the best.
        """
        logger.info(f"Preparing ML data for {symbol}")
        df_feat = self.create_features(df)
        df_tgt = self.define_target(df_feat)
        
        features = ['ret_1', 'ret_5', 'ret_15', 'vol_15', 'sma_ratio', 'price_to_sma10']
        X = df_tgt[features]
        y = df_tgt['target']
        
        if len(X) < 100:
            logger.warning(f"Not enough data to train ML for {symbol}. Needed 100, got {len(X)}")
            return
            
        # Chronological split (80% train, 20% test)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        best_acc = 0
        
        for name, model in self.models.items():
            logger.info(f"Training {name} for {symbol}...")
            model.fit(X_train, y_train)
            
            # Predict
            preds = model.predict(X_test)
            
            # Evaluate out-of-sample
            acc = accuracy_score(y_test, preds)
            prec = precision_score(y_test, preds, zero_division=0)
            rec = recall_score(y_test, preds, zero_division=0)
            
            self.metrics[name] = {'accuracy': acc, 'precision': prec, 'recall': rec}
            logger.info(f"{name} Out-of-sample metrics -> Acc: {acc:.4f}, Prec: {prec:.4f}, Rec: {rec:.4f}")
            
            self.trained_models[name] = model
            
            if acc > best_acc:
                best_acc = acc
                self.best_model_name = name
                
        logger.info(f"Best model for {symbol}: {self.best_model_name} with accuracy {best_acc:.4f}")

    def predict(self, symbol: str, df: pd.DataFrame) -> Optional[Prediction]:
        """
        Uses the best model to predict the next direction based on recent data.
        """
        if not self.best_model_name or self.best_model_name not in self.trained_models:
            logger.warning("Models not trained yet.")
            return None
            
        df_feat = self.create_features(df)
        if df_feat.empty:
            return None
            
        features = ['ret_1', 'ret_5', 'ret_15', 'vol_15', 'sma_ratio', 'price_to_sma10']
        X_recent = df_feat[features].iloc[[-1]]
        
        model = self.trained_models[self.best_model_name]
        
        pred_class = model.predict(X_recent)[0]
        prob = model.predict_proba(X_recent)[0]
        confidence = prob[1] if pred_class == 1 else prob[0]
        
        direction = "UP" if pred_class == 1 else "DOWN"
        
        pred = Prediction(
            symbol=symbol,
            predicted_direction=direction,
            confidence=confidence,
            model_used=self.best_model_name,
            target_period=self.target_period
        )
        logger.info(f"ML Prediction for {symbol}: {direction} (Conf: {confidence:.2f}) using {self.best_model_name}")
        return pred

