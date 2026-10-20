import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import accuracy_score, precision_score, recall_score, mean_absolute_error, brier_score_loss
import xgboost as xgb
import logging

logger = logging.getLogger(__name__)

from app.trading.signals import Prediction

class MLEngine:
    def __init__(self, target_period: int = 5):
        """
        Engine for creating features, training predictive classifiers,
        estimating continuous expected returns, and running walk-forward retraining.
        target_period: Number of periods ahead to predict return.
        """
        self.target_period = target_period
        self.models = {
            'logistic_regression': LogisticRegression(max_iter=1000, random_state=42),
            'random_forest': RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42),
            'gradient_boosting': GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42),
            'xgboost': xgb.XGBClassifier(n_estimators=100, max_depth=3, random_state=42, eval_metric='logloss')
        }
        self.regressors = {
            'xgboost_reg': xgb.XGBRegressor(n_estimators=100, max_depth=3, random_state=42),
            'gradient_boosting_reg': GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
            'ridge_reg': Ridge(alpha=1.0)
        }
        self.trained_models = {}
        self.trained_regressors = {}
        self.metrics = {}
        self.regression_metrics = {}
        self.best_model_name = None
        self.best_regressor_name = None

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
        Defines prediction targets:
        - target: binary 1 if return over next `target_period` > 0, else 0
        - target_return: continuous percentage return over next `target_period`
        """
        df = df.copy()
        df['future_ret'] = df['close'].pct_change(self.target_period).shift(-self.target_period)
        df['target'] = (df['future_ret'] > 0).astype(int)
        df['target_return'] = df['future_ret'] * 100.0  # percentage return
        
        df = df.dropna(subset=['target', 'target_return'])
        return df

    def train_and_evaluate(self, symbol: str, df: pd.DataFrame):
        """
        Builds chronological train/test split (80/20), trains directional classifiers
        and expected-return regressors, compares them, and saves the best.
        """
        logger.info(f"Preparing ML data for {symbol}")
        df_feat = self.create_features(df)
        df_tgt = self.define_target(df_feat)
        
        features = ['ret_1', 'ret_5', 'ret_15', 'vol_15', 'sma_ratio', 'price_to_sma10']
        X = df_tgt[features]
        y_class = df_tgt['target']
        y_reg = df_tgt['target_return']
        
        if len(X) < 100:
            logger.warning(f"Not enough data to train ML for {symbol}. Needed 100, got {len(X)}")
            return
            
        # Chronological split (80% train, 20% test)
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train_c, y_test_c = y_class.iloc[:split_idx], y_class.iloc[split_idx:]
        y_train_r, y_test_r = y_reg.iloc[:split_idx], y_reg.iloc[split_idx:]
        
        # 1. Train Classifiers
        best_acc = 0.0
        for name, model in self.models.items():
            model.fit(X_train, y_train_c)
            preds = model.predict(X_test)
            acc = accuracy_score(y_test_c, preds)
            prec = precision_score(y_test_c, preds, zero_division=0)
            rec = recall_score(y_test_c, preds, zero_division=0)
            
            self.metrics[name] = {'accuracy': acc, 'precision': prec, 'recall': rec}
            self.trained_models[name] = model
            
            if acc > best_acc:
                best_acc = acc
                self.best_model_name = name

        # 2. Train Regressors (Expected-Return Prediction)
        best_mae = float('inf')
        for name, reg in self.regressors.items():
            reg.fit(X_train, y_train_r)
            preds_r = reg.predict(X_test)
            mae = mean_absolute_error(y_test_r, preds_r)
            self.regression_metrics[name] = {'mae': mae}
            self.trained_regressors[name] = reg
            
            if mae < best_mae:
                best_mae = mae
                self.best_regressor_name = name

        logger.info(
            f"Best models for {symbol} -> Classifier: {self.best_model_name} (Acc: {best_acc:.4f}) | "
            f"Regressor: {self.best_regressor_name} (MAE: {best_mae:.4f}%)"
        )

    def walk_forward_retrain(
        self,
        symbol: str,
        df: pd.DataFrame,
        train_window: int = 120,
        test_window: int = 30,
        step: int = 20
    ) -> Dict[str, Any]:
        """
        Walk-Forward Retraining & Validation:
        Iterates chronologically through historical candles with expanding/rolling windows,
        evaluates out-of-sample accuracy, Brier scores, and MAE across market regimes,
        and fits the final production models on the latest window.
        """
        df_feat = self.create_features(df)
        df_tgt = self.define_target(df_feat)
        
        features = ['ret_1', 'ret_5', 'ret_15', 'vol_15', 'sma_ratio', 'price_to_sma10']
        X = df_tgt[features]
        y_class = df_tgt['target']
        y_reg = df_tgt['target_return']

        total_rows = len(X)
        if total_rows < (train_window + test_window):
            logger.warning(f"Insufficient data for walk-forward retraining on {symbol}. Got {total_rows}, needed {train_window + test_window}")
            return {
                "status": "failed",
                "reason": "Insufficient historical data for walk-forward windows",
                "windows_evaluated": 0
            }

        accuracies = []
        brier_scores = []
        maes = []
        start_idx = 0

        while (start_idx + train_window + test_window) <= total_rows:
            train_end = start_idx + train_window
            test_end = train_end + test_window

            X_tr, y_tr_c, y_tr_r = X.iloc[start_idx:train_end], y_class.iloc[start_idx:train_end], y_reg.iloc[start_idx:train_end]
            X_te, y_te_c, y_te_r = X.iloc[train_end:test_end], y_class.iloc[train_end:test_end], y_reg.iloc[train_end:test_end]

            # Fit candidate tree model
            clf = xgb.XGBClassifier(n_estimators=60, max_depth=3, random_state=42, eval_metric='logloss')
            clf.fit(X_tr, y_tr_c)
            preds_c = clf.predict(X_te)
            probs_c = clf.predict_proba(X_te)[:, 1]

            acc = accuracy_score(y_te_c, preds_c)
            brier = brier_score_loss(y_te_c, probs_c)
            accuracies.append(acc)
            brier_scores.append(brier)

            # Fit candidate regressor
            reg = xgb.XGBRegressor(n_estimators=60, max_depth=3, random_state=42)
            reg.fit(X_tr, y_tr_r)
            preds_r = reg.predict(X_te)
            mae = mean_absolute_error(y_te_r, preds_r)
            maes.append(mae)

            start_idx += step

        # Re-fit final production models on the latest window
        latest_X_tr = X.iloc[-train_window:]
        latest_y_tr_c = y_class.iloc[-train_window:]
        latest_y_tr_r = y_reg.iloc[-train_window:]

        prod_clf = xgb.XGBClassifier(n_estimators=100, max_depth=3, random_state=42, eval_metric='logloss')
        prod_clf.fit(latest_X_tr, latest_y_tr_c)
        self.trained_models['xgboost'] = prod_clf
        self.best_model_name = 'xgboost'

        prod_reg = xgb.XGBRegressor(n_estimators=100, max_depth=3, random_state=42)
        prod_reg.fit(latest_X_tr, latest_y_tr_r)
        self.trained_regressors['xgboost_reg'] = prod_reg
        self.best_regressor_name = 'xgboost_reg'

        mean_acc = round(float(np.mean(accuracies)), 4) if accuracies else 0.0
        mean_brier = round(float(np.mean(brier_scores)), 4) if brier_scores else 0.0
        mean_mae = round(float(np.mean(maes)), 4) if maes else 0.0

        result = {
            "status": "success",
            "symbol": symbol,
            "windows_evaluated": len(accuracies),
            "walk_forward_accuracy": mean_acc,
            "mean_brier_score": mean_brier,
            "mean_mae_pct": mean_mae,
            "best_classifier": self.best_model_name,
            "best_regressor": self.best_regressor_name
        }
        logger.info(f"Walk-Forward Retraining completed for {symbol}: Acc={mean_acc:.4f}, Brier={mean_brier:.4f}, MAE={mean_mae:.4f}%")
        return result

    def predict(self, symbol: str, df: pd.DataFrame) -> Optional[Prediction]:
        """
        Uses the best trained classifier and regressor to predict direction,
        confidence probability, and continuous expected return %.
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
        confidence = float(prob[1] if pred_class == 1 else prob[0])
        direction = "UP" if pred_class == 1 else "DOWN"
        
        # Expected return estimation
        expected_ret = 0.0
        if self.best_regressor_name and self.best_regressor_name in self.trained_regressors:
            reg = self.trained_regressors[self.best_regressor_name]
            expected_ret = float(reg.predict(X_recent)[0])
        else:
            # Fallback estimation using calibrated confidence and rolling volatility
            vol = float(X_recent['vol_15'].iloc[0]) if 'vol_15' in X_recent else 0.01
            expected_ret = (confidence - 0.5) * 2.0 * vol * 100.0

        expected_ret = round(expected_ret, 3)

        pred = Prediction(
            symbol=symbol,
            predicted_direction=direction,
            confidence=round(confidence, 4),
            model_used=self.best_model_name,
            target_period=self.target_period,
            expected_return_pct=expected_ret
        )
        logger.info(f"ML Prediction for {symbol}: {direction} (Conf: {confidence:.2f}, ExpRet: {expected_ret:+.2f}%) using {self.best_model_name}")
        return pred
