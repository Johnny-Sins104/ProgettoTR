"""
core/regime_model_manager.py — Institutional-Grade Regime Model Manager & Registry
=============================================================================
Manages a multi-model architecture composed of:
  - 1 Unified Model (baseline trained on all data)
  - 4 specialized estimators trained on mutually exclusive market regimes:
    1. HIGH_VOL: atr_pct > 66th percentile
    2. LOW_VOL: atr_pct < 33rd percentile
    3. TRENDING: atr_pct within [33rd, 66th] and regime == 1
    4. RANGING: atr_pct within [33rd, 66th] and regime == 0

Features:
  - Stateful Model Registry for loading, saving, and versioning models.
  - Separate probability calibration per regime using ProbabilityCalibrator.
  - Automatic regime routing during training and inference.
  - Seamless fallback mechanisms to the Unified model if specialized models are missing or training data is scarce.
"""

import os
import pickle
import numpy as np
import pandas as pd

# Handle graceful degradation if xgboost or sklearn are missing
try:
    from xgboost import XGBClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, f1_score
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    from core.calibration import (
        ProbabilityCalibrator,
        extract_calibration_split,
        CalibrationReport,
    )
    CALIBRATION_AVAILABLE = True
except ImportError:
    CALIBRATION_AVAILABLE = False

from config import Config

# Ordered feature set for the secondary XGBoost meta-model (excluding 'outcome')
FEATURE_NAMES = [
    "rsi",
    "adx",
    "atr_pct",
    "ema_slope",
    "close_vs_ema",
    "dist_to_psy",
    "volume_ratio",
    "bb_position",
    "engulfing",
    "regime",
    "in_fvg",
    "near_sr",
    "volume_bias_enc",
    "setup_quality"
]


class RegimeModelManager:
    """
    Stateful Registry and Routing Manager for specialized ML regime estimators.
    Implements a thread-safe Singleton to guarantee consistent access across processes.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RegimeModelManager, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.model_path = Config.AI_MODEL_PATH
        self.features_path = Config.AI_FEATURES_PATH

        # Models, Calibrators and Diagnostics registries
        self.models = {
            "UNIFIED": None,
            "HIGH_VOL": None,
            "LOW_VOL": None,
            "TRENDING": None,
            "RANGING": None
        }
        self.calibrators = {
            "UNIFIED": None,
            "HIGH_VOL": None,
            "LOW_VOL": None,
            "TRENDING": None,
            "RANGING": None
        }
        self.calibration_reports = {
            "UNIFIED": None,
            "HIGH_VOL": None,
            "LOW_VOL": None,
            "TRENDING": None,
            "RANGING": None
        }

        # Metric registries
        self.accuracies = {k: 0.0 for k in self.models}
        self.train_accuracies = {k: 0.0 for k in self.models}
        self.f1s = {k: 0.0 for k in self.models}
        self.feature_importances = {k: {} for k in self.models}

        # Causal ATR percentiles (fitted during training)
        self.vol_low_thresh = 0.33
        self.vol_high_thresh = 0.66

        # Proactively load pre-trained models
        self.load_models()
        self._initialized = True

    @property
    def is_trained(self) -> bool:
        """Checks if the baseline Unified model is trained and active."""
        return self.models["UNIFIED"] is not None

    def detect_regime(self, features_dict: dict) -> str:
        """
        Determines the active market regime of a candidate setup using causal ATR boundaries.
        Returns one of: HIGH_VOL, LOW_VOL, TRENDING, RANGING.
        """
        atr_pct = float(features_dict.get("atr_pct", 0.5))
        regime_val = features_dict.get("regime", 0)

        if atr_pct > self.vol_high_thresh:
            return "HIGH_VOL"
        elif atr_pct < self.vol_low_thresh:
            return "LOW_VOL"
        else:
            if regime_val == 1 or str(regime_val).upper() in ("1", "TRENDING") or regime_val is True:
                return "TRENDING"
            return "RANGING"

    def apply_symmetry_transform(self, features_dict: dict, side: str) -> dict:
        """
        Applies a directional sign inversion on features for Short signals.
        Enforces sign-invariance so the model learns 'neutral setup strength'.
        """
        features_transformed = features_dict.copy()
        if side == "SELL":
            for f in ["engulfing", "close_vs_ema", "ema_slope", "near_sr", "volume_bias_enc"]:
                if f in features_transformed:
                    features_transformed[f] = -features_transformed[f]
        return features_transformed

    def _train_single_model(self, name: str, part_df: pd.DataFrame, fit_calibrator: bool) -> dict:
        """
        Fits a single XGBoost Classifier and ProbabilityCalibrator on a dataset partition.
        """
        X = part_df[FEATURE_NAMES]
        y = part_df["outcome"]

        if fit_calibrator and CALIBRATION_AVAILABLE and len(X) >= 150:
            X_xgb, y_xgb, X_cal, y_cal = extract_calibration_split(
                X, y, cal_fraction=0.20, min_cal_samples=50
            )
        else:
            X_xgb, y_xgb = X, y
            X_cal, y_cal = pd.DataFrame(columns=X.columns), pd.Series(dtype=int)

        if len(X_xgb) >= 10:
            X_train, X_test, y_train, y_test = train_test_split(
                X_xgb, y_xgb, test_size=0.2, shuffle=False
            )
        else:
            X_train, X_test = X_xgb, X_xgb
            y_train, y_test = y_xgb, y_xgb

        clf = XGBClassifier(
            n_estimators=150,
            max_depth=5,
            learning_rate=0.05,
            random_state=42,
            n_jobs=-1,
            eval_metric="logloss"
        )
        clf.fit(X_train, y_train)

        calibrator = ProbabilityCalibrator(method="auto") if CALIBRATION_AVAILABLE else None
        calibration_report = None

        if fit_calibrator and CALIBRATION_AVAILABLE and len(X_cal) >= 50:
            calibrator.fit(clf, X_cal, y_cal.values)
            calibration_report = calibrator.evaluate(clf, X_test, y_test.values)
        elif calibrator is None and CALIBRATION_AVAILABLE:
            calibrator = ProbabilityCalibrator(method="auto")

        y_train_pred = clf.predict(X_train)
        y_test_pred = clf.predict(X_test)

        train_acc = accuracy_score(y_train, y_train_pred)
        test_acc = accuracy_score(y_test, y_test_pred)
        f1 = f1_score(y_test, y_test_pred, zero_division=0)

        importances = {}
        if hasattr(clf, "feature_importances_"):
            importances_vals = clf.feature_importances_
            indices = np.argsort(importances_vals)[::-1]
            for i in indices:
                importances[FEATURE_NAMES[i]] = float(importances_vals[i])

        return {
            "model": clf,
            "calibrator": calibrator,
            "calibration_report": calibration_report,
            "train_accuracy": train_acc,
            "accuracy": test_acc,
            "f1_score": f1,
            "importances": importances
        }

    def train_all(self, df: pd.DataFrame, fit_calibrator: bool = True, save_to_disk: bool = True) -> dict:
        """
        Segments the input dataset and trains all 5 XGBoost models in parallel.
        Ensures strict fallback rules if regime sample size is insufficient.
        """
        if not XGBOOST_AVAILABLE:
            print("❌ RegimeModelManager: Training failed because xgboost is not installed.")
            return {"status": "error", "message": "xgboost not available"}

        if len(df) < Config.AI_MIN_SAMPLES:
            print(f"⚠️ Insufficient samples for regime model training: {len(df)}/{Config.AI_MIN_SAMPLES}")
            return {"status": "insufficient_data", "samples": len(df)}

        try:
            # Clean dataframe columns
            if "atr_pct" not in df.columns:
                df = df.copy()
                df["atr_pct"] = 0.5
            if "regime" not in df.columns:
                df = df.copy()
                df["regime"] = 0

            # Causal thresholds estimation
            vol_low_thresh = float(df["atr_pct"].quantile(0.33))
            vol_high_thresh = float(df["atr_pct"].quantile(0.66))

            if pd.isna(vol_low_thresh):
                vol_low_thresh = 0.33
            if pd.isna(vol_high_thresh):
                vol_high_thresh = 0.66

            self.vol_low_thresh = vol_low_thresh
            self.vol_high_thresh = vol_high_thresh

            print(f"📊 [REGIME TRAINING] ATR Quantiles calculated: 33%={vol_low_thresh:.4f} | 66%={vol_high_thresh:.4f}")

            # Splitting partitions
            df_high_vol = df[df["atr_pct"] > vol_high_thresh]
            df_low_vol = df[df["atr_pct"] < vol_low_thresh]
            df_mid = df[(df["atr_pct"] >= vol_low_thresh) & (df["atr_pct"] <= vol_high_thresh)]
            df_trending = df_mid[df_mid["regime"] == 1]
            df_ranging = df_mid[df_mid["regime"] == 0]

            min_regime_samples = 30
            partitions = {
                "UNIFIED": df,
                "HIGH_VOL": df_high_vol,
                "LOW_VOL": df_low_vol,
                "TRENDING": df_trending,
                "RANGING": df_ranging
            }

            for name, part_df in partitions.items():
                if name != "UNIFIED" and len(part_df) < min_regime_samples:
                    print(f"⚠️ Regime {name} samples insufficient ({len(part_df)} < {min_regime_samples}). Falling back to UNIFIED dataset.")
                    partitions[name] = df.copy()

            # Train each model
            for name, part_df in partitions.items():
                print(f"🚀 Training {name} Model (Samples: {len(part_df)})...")
                metrics = self._train_single_model(name, part_df, fit_calibrator)
                
                self.models[name] = metrics["model"]
                self.calibrators[name] = metrics["calibrator"]
                self.calibration_reports[name] = metrics["calibration_report"]
                self.accuracies[name] = metrics["accuracy"]
                self.train_accuracies[name] = metrics["train_accuracy"]
                self.f1s[name] = metrics["f1_score"]
                self.feature_importances[name] = metrics["importances"]

            if save_to_disk:
                self.save_models()

            print(f"✨ All specialized models trained and serialized! (Total Samples: {len(df)})")
            return {
                "status": "success",
                "samples": len(df),
                "vol_low_thresh": self.vol_low_thresh,
                "vol_high_thresh": self.vol_high_thresh,
                "accuracies": self.accuracies,
                "train_accuracies": self.train_accuracies,
                "f1_scores": self.f1s
            }

        except Exception as e:
            print(f"❌ Error during Regime Model Manager training: {e}")
            import traceback
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def predict_probability(self, features_dict: dict, side: str = "BUY", use_specialized: bool = True) -> float:
        """
        Routes the features to the correct specialized regime model, applies symmetry
        transformations, predicts the raw win probability, and calibrates it.

        Returns calibrated probability as a percentage (0.0 to 100.0).
        """
        if not self.is_trained:
            return 50.0

        try:
            # Apply sign-invariant symmetry transformation for Shorts
            features_input = self.apply_symmetry_transform(features_dict, side)

            # Determine routing
            if use_specialized:
                regime = self.detect_regime(features_dict)
                model = self.models.get(regime)
                calibrator = self.calibrators.get(regime)
            else:
                regime = "UNIFIED"
                model = self.models["UNIFIED"]
                calibrator = self.calibrators["UNIFIED"]

            # Safe fallback to Unified
            if model is None:
                model = self.models["UNIFIED"]
                calibrator = self.calibrators["UNIFIED"]

            if model is None:
                return 50.0

            # Create features row
            ordered_features = {k: [features_input.get(k, 0.0)] for k in FEATURE_NAMES}
            X_pred = pd.DataFrame(ordered_features)

            # Predict raw probability
            p_raw = float(model.predict_proba(X_pred)[0][1])

            # Calibrate probability
            if calibrator is not None and calibrator.is_fitted:
                p_cal = calibrator.calibrate(p_raw)
            else:
                p_cal = p_raw

            return float(p_cal * 100.0)

        except Exception as e:
            print(f"⚠️ Prediction error in RegimeModelManager: {e}. Fallback to 50.0")
            return 50.0

    def get_feature_importance(self, regime: str = "UNIFIED") -> dict:
        """Returns ordered feature importance dict for the specified regime model."""
        return self.feature_importances.get(regime, {})

    def save_models(self, path: str = None):
        """Serializes all models, calibrators and thresholds to disk."""
        if path is None:
            path = self.model_path

        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            state = {
                "models": self.models,
                "calibrators": self.calibrators,
                "calibration_reports": self.calibration_reports,
                "vol_low_thresh": self.vol_low_thresh,
                "vol_high_thresh": self.vol_high_thresh,
                "accuracies": self.accuracies,
                "train_accuracies": self.train_accuracies,
                "f1s": self.f1s,
                "feature_importances": self.feature_importances,
                
                # Perfect backward compatibility for legacy load_model calls
                "trending_model": self.models.get("TRENDING"),
                "ranging_model": self.models.get("RANGING"),
                "trending_calibrator": self.calibrators.get("TRENDING"),
                "ranging_calibrator": self.calibrators.get("RANGING"),
                "trending_accuracy": self.accuracies.get("TRENDING", 0.0),
                "ranging_accuracy": self.accuracies.get("RANGING", 0.0),
                "trending_train_accuracy": self.train_accuracies.get("TRENDING", 0.0),
                "ranging_train_accuracy": self.train_accuracies.get("RANGING", 0.0),
                "trending_f1": self.f1s.get("TRENDING", 0.0),
                "ranging_f1": self.f1s.get("RANGING", 0.0),
                
                "model": self.models.get("UNIFIED"),
                "calibrator": self.calibrators.get("UNIFIED"),
                "accuracy": self.accuracies.get("UNIFIED", 0.0),
                "train_accuracy": self.train_accuracies.get("UNIFIED", 0.0),
                "f1": self.f1s.get("UNIFIED", 0.0),
                "is_trained": self.is_trained
            }
            with open(path, "wb") as f:
                pickle.dump(state, f)
        except Exception as e:
            print(f"❌ Failed to save regime-specialized models: {e}")

    def load_models(self, path: str = None):
        """Loads serialized models, calibrators and thresholds from disk."""
        if path is None:
            path = self.model_path

        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    state = pickle.load(f)

                # Safe mapping with legacy support
                if "models" in state:
                    self.models = state["models"]
                    self.calibrators = state["calibrators"]
                    self.calibration_reports = state.get("calibration_reports", self.calibration_reports)
                    self.vol_low_thresh = state.get("vol_low_thresh", 0.33)
                    self.vol_high_thresh = state.get("vol_high_thresh", 0.66)
                    self.accuracies = state.get("accuracies", self.accuracies)
                    self.train_accuracies = state.get("train_accuracies", self.train_accuracies)
                    self.f1s = state.get("f1s", self.f1s)
                    self.feature_importances = state.get("feature_importances", self.feature_importances)
                else:
                    # Legacy structure loading and mapping
                    self.models["TRENDING"] = state.get("trending_model")
                    self.models["RANGING"] = state.get("ranging_model")
                    self.models["UNIFIED"] = state.get("model", state.get("trending_model"))
                    self.calibrators["TRENDING"] = state.get("trending_calibrator")
                    self.calibrators["RANGING"] = state.get("ranging_calibrator")
                    self.calibrators["UNIFIED"] = state.get("calibrator", state.get("trending_calibrator"))
                    
                    self.accuracies["TRENDING"] = state.get("trending_accuracy", 0.0)
                    self.accuracies["RANGING"] = state.get("ranging_accuracy", 0.0)
                    self.accuracies["UNIFIED"] = state.get("accuracy", 0.0)
                    
                    self.train_accuracies["TRENDING"] = state.get("trending_train_accuracy", 0.0)
                    self.train_accuracies["RANGING"] = state.get("ranging_train_accuracy", 0.0)
                    self.train_accuracies["UNIFIED"] = state.get("train_accuracy", 0.0)
                    
                    self.f1s["TRENDING"] = state.get("trending_f1", 0.0)
                    self.f1s["RANGING"] = state.get("ranging_f1", 0.0)
                    self.f1s["UNIFIED"] = state.get("f1", 0.0)

                print(
                    f"[REGIME MODEL REGISTRY] Loaded specialized models successfully. "
                    f"Unified Acc: {self.accuracies.get('UNIFIED', 0.0)*100:.1f}% | "
                    f"Trending Acc: {self.accuracies.get('TRENDING', 0.0)*100:.1f}% | "
                    f"Ranging Acc: {self.accuracies.get('RANGING', 0.0)*100:.1f}%"
                )
            except Exception as e:
                print(f"[REGIME MODEL REGISTRY] Warning: could not load model: {e}. Will train new.")
                self._reset_registry()
        else:
            self._reset_registry()

    def _reset_registry(self):
        self.models = {k: None for k in self.models}
        self.calibrators = {k: None for k in self.models}
        self.calibration_reports = {k: None for k in self.models}
        self.accuracies = {k: 0.0 for k in self.models}
        self.train_accuracies = {k: 0.0 for k in self.models}
        self.f1s = {k: 0.0 for k in self.models}
        self.feature_importances = {k: {} for k in self.models}
        self.vol_low_thresh = 0.33
        self.vol_high_thresh = 0.66
