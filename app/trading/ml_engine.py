import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import accuracy_score, precision_score, recall_score, mean_absolute_error, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler
from scipy.stats import spearmanr
import xgboost as xgb
import logging

logger = logging.getLogger(__name__)

from app.trading.signals import Prediction


# ---------------------------------------------------------------------------
# Per-Symbol Model Bundle
# ---------------------------------------------------------------------------

class SymbolModelBundle:
    """Stores trained models, scaler, feature list, and metrics for a single symbol."""
    __slots__ = (
        'best_classifier_name', 'best_classifier',
        'best_regressor_name', 'best_regressor',
        'scaler', 'feature_cols',
        'classifier_metrics', 'regressor_metrics',
        'information_coefficient',
    )

    def __init__(self):
        self.best_classifier_name: Optional[str] = None
        self.best_classifier: Any = None
        self.best_regressor_name: Optional[str] = None
        self.best_regressor: Any = None
        self.scaler: Optional[StandardScaler] = None
        self.feature_cols: List[str] = []
        self.classifier_metrics: Dict[str, Dict[str, float]] = {}
        self.regressor_metrics: Dict[str, Dict[str, float]] = {}
        self.information_coefficient: float = 0.0


# ---------------------------------------------------------------------------
# ML Engine
# ---------------------------------------------------------------------------

class MLEngine:
    """
    Engine for creating features, training predictive classifiers,
    estimating continuous expected returns, and running walk-forward retraining.

    Key improvements over v1:
      - Correct forward-return target (no leakage)
      - Embargo gap between train/test to prevent lookahead contamination
      - Per-symbol model storage (no cross-symbol overwrite)
      - Expanded feature set (15 features incl. RSI, NATR, BB, MACD, volume)
      - StandardScaler normalisation for scale-sensitive models
      - Information Coefficient (IC) for model selection instead of raw accuracy
    """

    FEATURE_COLS = [
        'ret_1', 'ret_3', 'ret_5', 'ret_10', 'ret_20',
        'vol_5', 'vol_20', 'vol_ratio',
        'sma_ratio', 'ema_spread',
        'rsi_14', 'natr_14',
        'volume_ratio', 'bb_position', 'macd_hist_norm',
    ]

    def __init__(self, target_period: int = 5):
        """
        Engine for creating features, training predictive classifiers,
        estimating continuous expected returns, and running walk-forward retraining.
        target_period: Number of periods ahead to predict return.
        """
        self.target_period = target_period

        # ── Per-symbol model storage ──
        self.symbol_bundles: Dict[str, SymbolModelBundle] = {}

        # ── Backward-compat globals (set to latest trained symbol) ──
        self.trained_models: Dict[str, Any] = {}
        self.trained_regressors: Dict[str, Any] = {}
        self.metrics: Dict[str, Any] = {}
        self.regression_metrics: Dict[str, Any] = {}
        self.best_model_name: Optional[str] = None
        self.best_regressor_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Factory helpers – fresh sklearn instances per training run
    # ------------------------------------------------------------------

    @staticmethod
    def _make_classifiers() -> Dict[str, Any]:
        return {
            'logistic_regression': LogisticRegression(max_iter=1000, random_state=42),
            'random_forest': RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42),
            'gradient_boosting': GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42),
            'xgboost': xgb.XGBClassifier(n_estimators=100, max_depth=3, random_state=42, eval_metric='logloss'),
        }

    @staticmethod
    def _make_regressors() -> Dict[str, Any]:
        return {
            'xgboost_reg': xgb.XGBRegressor(n_estimators=100, max_depth=3, random_state=42),
            'gradient_boosting_reg': GradientBoostingRegressor(n_estimators=100, max_depth=3, random_state=42),
            'ridge_reg': Ridge(alpha=1.0),
        }

    # ------------------------------------------------------------------
    # Feature Engineering
    # ------------------------------------------------------------------

    def extract_features(self, candles: Any) -> pd.DataFrame:
        """
        Extracts feature DataFrame from a list of candles or a DataFrame.
        Handles Candle objects (with attribute access) or dicts.
        """
        if isinstance(candles, pd.DataFrame):
            return self.create_features(candles)

        if not candles:
            return pd.DataFrame()

        records = []
        for c in candles:
            if hasattr(c, "close"):
                records.append({
                    "open": float(getattr(c, "open", getattr(c, "close"))),
                    "high": float(getattr(c, "high", getattr(c, "close"))),
                    "low": float(getattr(c, "low", getattr(c, "close"))),
                    "close": float(c.close),
                    "volume": float(getattr(c, "volume", 1000.0)),
                })
            elif isinstance(c, dict):
                records.append({
                    "open": float(c.get("open", c.get("close", 0.0))),
                    "high": float(c.get("high", c.get("close", 0.0))),
                    "low": float(c.get("low", c.get("close", 0.0))),
                    "close": float(c.get("close", 0.0)),
                    "volume": float(c.get("volume", 1000.0)),
                })
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        return self.create_features(df)

    def create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Creates ML features from OHLCV data.
        Expanded: returns (5), volatility (3), trend (2), RSI, NATR,
        volume profile, Bollinger position, MACD histogram.
        """
        df = df.copy()

        # ── Returns (multi-scale) ──
        for w in [1, 3, 5, 10, 20]:
            df[f'ret_{w}'] = df['close'].pct_change(w)

        # ── Volatility (multi-scale + regime ratio) ──
        df['vol_5'] = df['ret_1'].rolling(5).std()
        df['vol_20'] = df['ret_1'].rolling(20).std()
        df['vol_ratio'] = df['vol_5'] / df['vol_20'].replace(0, np.nan)

        # ── Trend Indicators ──
        sma_10 = df['close'].rolling(10).mean()
        sma_30 = df['close'].rolling(30).mean()
        df['sma_ratio'] = sma_10 / sma_30

        ema_9 = df['close'].ewm(span=9, adjust=False).mean()
        ema_21 = df['close'].ewm(span=21, adjust=False).mean()
        df['ema_spread'] = (ema_9 - ema_21) / df['close']  # normalised

        # ── RSI (Wilder's smoothing via pandas) ──
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['rsi_14'] = 100.0 - (100.0 / (1.0 + rs))

        # ── Normalised ATR (price-independent volatility) ──
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs(),
        ], axis=1).max(axis=1)
        df['natr_14'] = tr.rolling(14).mean() / df['close']

        # ── Volume Profile ──
        vol_sma_20 = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / vol_sma_20.replace(0, np.nan)

        # ── Bollinger Band Position (z-score within bands) ──
        bb_mid = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_position'] = (df['close'] - bb_mid) / (2.0 * bb_std).replace(0, np.nan)

        # ── MACD Histogram (normalised by price) ──
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        df['macd_hist_norm'] = (macd_line - macd_signal) / df['close']

        df = df.dropna()
        return df

    # ------------------------------------------------------------------
    # Target Definition (FIXED: true forward return, no leakage)
    # ------------------------------------------------------------------

    def define_target(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Defines prediction targets:
        - target: binary 1 if return over next `target_period` > 0, else 0
        - target_return: continuous percentage return over next `target_period`

        Uses true forward return: close[t + N] / close[t] - 1
        """
        df = df.copy()
        df['future_ret'] = df['close'].shift(-self.target_period) / df['close'] - 1.0
        df['target'] = (df['future_ret'] > 0).astype(int)
        df['target_return'] = df['future_ret'] * 100.0

        df = df.dropna(subset=['target', 'target_return'])
        return df

    # ------------------------------------------------------------------
    # Training (FIXED: embargo, scaling, IC selection, per-symbol storage)
    # ------------------------------------------------------------------

    def train_and_evaluate(self, symbol: str, df: pd.DataFrame):
        """
        Builds chronological train/test split with embargo gap, trains
        directional classifiers and expected-return regressors, evaluates
        using Information Coefficient (IC), and saves per-symbol.
        """
        logger.info(f"Preparing ML data for {symbol}")
        df_feat = self.create_features(df)
        df_tgt = self.define_target(df_feat)

        available = [f for f in self.FEATURE_COLS if f in df_tgt.columns]
        X = df_tgt[available]
        y_class = df_tgt['target']
        y_reg = df_tgt['target_return']

        if len(X) < 100:
            logger.warning(f"Not enough data to train ML for {symbol}. Needed 100, got {len(X)}")
            return

        # Chronological split with embargo gap to avoid lookahead
        embargo = self.target_period
        split_idx = int(len(X) * 0.8)
        X_train = X.iloc[:split_idx - embargo]
        X_test = X.iloc[split_idx:]
        y_train_c = y_class.iloc[:split_idx - embargo]
        y_test_c = y_class.iloc[split_idx:]
        y_train_r = y_reg.iloc[:split_idx - embargo]
        y_test_r = y_reg.iloc[split_idx:]

        if len(X_train) < 50 or len(X_test) < 10:
            logger.warning(f"Insufficient split sizes for {symbol} after embargo. Train: {len(X_train)}, Test: {len(X_test)}")
            return

        # Feature scaling
        scaler = StandardScaler()
        X_train_scaled = pd.DataFrame(
            scaler.fit_transform(X_train), columns=X_train.columns, index=X_train.index
        )
        X_test_scaled = pd.DataFrame(
            scaler.transform(X_test), columns=X_test.columns, index=X_test.index
        )

        bundle = SymbolModelBundle()
        bundle.scaler = scaler
        bundle.feature_cols = available

        # ── 1. Train Classifiers — select by Information Coefficient ──
        best_ic = -999.0
        classifiers = self._make_classifiers()
        for name, model in classifiers.items():
            model.fit(X_train_scaled, y_train_c)
            preds = model.predict(X_test_scaled)
            probs = model.predict_proba(X_test_scaled)[:, 1]

            acc = accuracy_score(y_test_c, preds)
            prec = precision_score(y_test_c, preds, zero_division=0)
            rec = recall_score(y_test_c, preds, zero_division=0)

            # IC: rank correlation between predicted edge and actual return
            predicted_edge = probs - 0.5
            ic_val, _ = spearmanr(predicted_edge, y_test_r.values)
            if np.isnan(ic_val):
                ic_val = 0.0

            bundle.classifier_metrics[name] = {
                'accuracy': acc, 'precision': prec, 'recall': rec,
                'ic': round(ic_val, 4),
            }

            if ic_val > best_ic:
                best_ic = ic_val
                bundle.best_classifier_name = name
                bundle.best_classifier = model

        # ── 2. Train Regressors ──
        best_mae = float('inf')
        regressors = self._make_regressors()
        for name, reg in regressors.items():
            reg.fit(X_train_scaled, y_train_r)
            preds_r = reg.predict(X_test_scaled)
            mae = mean_absolute_error(y_test_r, preds_r)
            bundle.regressor_metrics[name] = {'mae': mae}

            if mae < best_mae:
                best_mae = mae
                bundle.best_regressor_name = name
                bundle.best_regressor = reg

        bundle.information_coefficient = round(best_ic, 4)

        # ── Store per-symbol ──
        self.symbol_bundles[symbol] = bundle

        # ── Backward-compat globals (latest trained symbol wins — for logging) ──
        self.best_model_name = bundle.best_classifier_name
        self.best_regressor_name = bundle.best_regressor_name
        if bundle.best_classifier_name:
            self.trained_models[bundle.best_classifier_name] = bundle.best_classifier
        if bundle.best_regressor_name:
            self.trained_regressors[bundle.best_regressor_name] = bundle.best_regressor
        self.metrics = bundle.classifier_metrics
        self.regression_metrics = bundle.regressor_metrics

        logger.info(
            f"Best models for {symbol} -> Classifier: {bundle.best_classifier_name} "
            f"(IC: {best_ic:.4f}) | Regressor: {bundle.best_regressor_name} (MAE: {best_mae:.4f}%)"
        )

    # ------------------------------------------------------------------
    # Walk-Forward Retraining (FIXED: embargo, scaling, per-symbol)
    # ------------------------------------------------------------------

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
        Iterates chronologically through historical candles with rolling windows,
        evaluates out-of-sample accuracy, Brier scores, IC, and MAE across market
        regimes, and fits the final production models on the latest window.
        """
        df_feat = self.create_features(df)
        df_tgt = self.define_target(df_feat)

        available = [f for f in self.FEATURE_COLS if f in df_tgt.columns]
        X = df_tgt[available]
        y_class = df_tgt['target']
        y_reg = df_tgt['target_return']

        embargo = self.target_period
        total_rows = len(X)
        if total_rows < (train_window + embargo + test_window):
            logger.warning(
                f"Insufficient data for walk-forward retraining on {symbol}. "
                f"Got {total_rows}, needed {train_window + embargo + test_window}"
            )
            return {
                "status": "failed",
                "reason": "Insufficient historical data for walk-forward windows",
                "windows_evaluated": 0
            }

        accuracies = []
        brier_scores = []
        maes = []
        ics = []
        start_idx = 0

        while (start_idx + train_window + embargo + test_window) <= total_rows:
            train_end = start_idx + train_window
            test_start = train_end + embargo
            test_end = test_start + test_window

            X_tr = X.iloc[start_idx:train_end]
            y_tr_c = y_class.iloc[start_idx:train_end]
            y_tr_r = y_reg.iloc[start_idx:train_end]
            X_te = X.iloc[test_start:test_end]
            y_te_c = y_class.iloc[test_start:test_end]
            y_te_r = y_reg.iloc[test_start:test_end]

            # Per-fold scaling
            wf_scaler = StandardScaler()
            X_tr_s = wf_scaler.fit_transform(X_tr)
            X_te_s = wf_scaler.transform(X_te)

            # Classifier
            clf = xgb.XGBClassifier(n_estimators=60, max_depth=3, random_state=42, eval_metric='logloss')
            clf.fit(X_tr_s, y_tr_c)
            preds_c = clf.predict(X_te_s)
            probs_c = clf.predict_proba(X_te_s)[:, 1]

            acc = accuracy_score(y_te_c, preds_c)
            brier = brier_score_loss(y_te_c, probs_c)
            accuracies.append(acc)
            brier_scores.append(brier)

            ic_val, _ = spearmanr(probs_c - 0.5, y_te_r.values)
            if not np.isnan(ic_val):
                ics.append(ic_val)

            # Regressor
            reg = xgb.XGBRegressor(n_estimators=60, max_depth=3, random_state=42)
            reg.fit(X_tr_s, y_tr_r)
            preds_r = reg.predict(X_te_s)
            mae = mean_absolute_error(y_te_r, preds_r)
            maes.append(mae)

            start_idx += step

        # Re-fit final production models on the latest window
        bundle = self.symbol_bundles.get(symbol, SymbolModelBundle())

        latest_X_tr = X.iloc[-train_window:]
        latest_y_tr_c = y_class.iloc[-train_window:]
        latest_y_tr_r = y_reg.iloc[-train_window:]

        prod_scaler = StandardScaler()
        latest_X_tr_s = prod_scaler.fit_transform(latest_X_tr)

        prod_clf = xgb.XGBClassifier(n_estimators=100, max_depth=3, random_state=42, eval_metric='logloss')
        prod_clf.fit(latest_X_tr_s, latest_y_tr_c)
        bundle.best_classifier = prod_clf
        bundle.best_classifier_name = 'xgboost'

        prod_reg = xgb.XGBRegressor(n_estimators=100, max_depth=3, random_state=42)
        prod_reg.fit(latest_X_tr_s, latest_y_tr_r)
        bundle.best_regressor = prod_reg
        bundle.best_regressor_name = 'xgboost_reg'
        bundle.scaler = prod_scaler
        bundle.feature_cols = available

        self.symbol_bundles[symbol] = bundle

        # Backward-compat globals
        self.best_model_name = 'xgboost'
        self.best_regressor_name = 'xgboost_reg'
        self.trained_models['xgboost'] = prod_clf
        self.trained_regressors['xgboost_reg'] = prod_reg

        mean_acc = round(float(np.mean(accuracies)), 4) if accuracies else 0.0
        mean_brier = round(float(np.mean(brier_scores)), 4) if brier_scores else 0.0
        mean_mae = round(float(np.mean(maes)), 4) if maes else 0.0
        mean_ic = round(float(np.mean(ics)), 4) if ics else 0.0

        result = {
            "status": "success",
            "symbol": symbol,
            "windows_evaluated": len(accuracies),
            "walk_forward_accuracy": mean_acc,
            "mean_brier_score": mean_brier,
            "mean_mae_pct": mean_mae,
            "mean_ic": mean_ic,
            "best_classifier": bundle.best_classifier_name,
            "best_regressor": bundle.best_regressor_name
        }
        logger.info(
            f"Walk-Forward Retraining completed for {symbol}: "
            f"Acc={mean_acc:.4f}, IC={mean_ic:.4f}, Brier={mean_brier:.4f}, MAE={mean_mae:.4f}%"
        )
        return result

    # ------------------------------------------------------------------
    # Prediction (FIXED: per-symbol lookup, scaling)
    # ------------------------------------------------------------------

    def predict(self, *args, **kwargs) -> Optional[Prediction]:
        """
        Uses the best trained classifier and regressor for the given symbol
        to predict direction, confidence probability, and continuous expected return %.
        Accepts:
            predict(symbol, df)
            predict(df_or_candles, symbol="...")
            predict(symbol="...", df=...)
        """
        symbol = "UNKNOWN"
        df_or_candles = None

        if len(args) == 2:
            if isinstance(args[0], str):
                symbol = args[0]
                df_or_candles = args[1]
            else:
                df_or_candles = args[0]
                symbol = str(args[1])
        elif len(args) == 1:
            if isinstance(args[0], str):
                symbol = args[0]
            else:
                df_or_candles = args[0]

        if "symbol" in kwargs:
            symbol = kwargs["symbol"]
        if "df" in kwargs:
            df_or_candles = kwargs["df"]
        elif "features" in kwargs:
            df_or_candles = kwargs["features"]

        if df_or_candles is None:
            logger.warning("No data provided for ML prediction.")
            return None

        # Convert candles to feature DataFrame if needed
        if isinstance(df_or_candles, list):
            df_feat = self.extract_features(df_or_candles)
        elif isinstance(df_or_candles, pd.DataFrame):
            if all(col in df_or_candles.columns for col in self.FEATURE_COLS):
                df_feat = df_or_candles
            else:
                df_feat = self.create_features(df_or_candles)
        else:
            return None

        if df_feat.empty:
            return None

        # Determine which features are available
        available = [f for f in self.FEATURE_COLS if f in df_feat.columns]
        if len(available) < 5:
            return None

        X_recent = df_feat[available].iloc[[-1]]

        # ── Look up per-symbol model bundle ──
        clean_symbol = symbol.replace(".NS", "").strip()
        bundle = self.symbol_bundles.get(clean_symbol)

        # If no trained model for this symbol, use empirical quant fallback
        if not bundle or not bundle.best_classifier:
            ret1 = float(X_recent['ret_1'].iloc[0]) if 'ret_1' in X_recent.columns else 0.0
            sma_rat = float(X_recent['sma_ratio'].iloc[0]) if 'sma_ratio' in X_recent.columns else 1.0
            direction = "UP" if (ret1 > 0 and sma_rat >= 1.0) else "DOWN"
            confidence = min(0.75, max(0.51, 0.5 + abs(ret1) * 10.0))
            expected_ret = round(float(ret1 * 100.0 * 2.5), 3)
            return Prediction(
                symbol=symbol,
                predicted_direction=direction,
                confidence=round(confidence, 4),
                model_used="empirical_quant_fallback",
                target_period=self.target_period,
                expected_return_pct=expected_ret
            )

        # Align features to what the bundle was trained on
        bundle_features = bundle.feature_cols if bundle.feature_cols else available
        common_features = [f for f in bundle_features if f in df_feat.columns]
        if len(common_features) < 5:
            return None
        X_recent = df_feat[common_features].iloc[[-1]]

        # Scale features using the symbol's scaler
        if bundle.scaler:
            X_scaled = pd.DataFrame(
                bundle.scaler.transform(X_recent),
                columns=X_recent.columns,
                index=X_recent.index
            )
        else:
            X_scaled = X_recent

        model = bundle.best_classifier
        pred_class = model.predict(X_scaled)[0]
        prob = model.predict_proba(X_scaled)[0]
        confidence = float(prob[1] if pred_class == 1 else prob[0])
        direction = "UP" if pred_class == 1 else "DOWN"

        # Expected return estimation
        expected_ret = 0.0
        if bundle.best_regressor:
            expected_ret = float(bundle.best_regressor.predict(X_scaled)[0])
        else:
            vol = float(X_recent['vol_5'].iloc[0]) if 'vol_5' in X_recent.columns else 0.01
            expected_ret = (confidence - 0.5) * 2.0 * vol * 100.0

        expected_ret = round(expected_ret, 3)

        pred = Prediction(
            symbol=symbol,
            predicted_direction=direction,
            confidence=round(confidence, 4),
            model_used=bundle.best_classifier_name or "unknown",
            target_period=self.target_period,
            expected_return_pct=expected_ret
        )
        logger.info(f"ML Prediction for {symbol}: {direction} (Conf: {confidence:.2f}, ExpRet: {expected_ret:+.2f}%) using {bundle.best_classifier_name}")
        return pred
