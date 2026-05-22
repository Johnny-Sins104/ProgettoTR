"""
core/meta_labeling.py — Institutional-Grade Lopez de Prado Meta-Labeling Engine
=============================================================================
Implements a clean, decoupled Meta-Labeling Layer (Stage 2 Model).
Instead of predicting next-candle price direction (which is highly noisy and subject to
non-stationarity), this engine predicts the probability of setup success:
    P(Success | Setup) = P(TP hit before SL | Technical Setup Candidate)

Now completely refactored to delegate core training and routing mechanics to
RegimeModelManager, keeping full backwards compatibility with the legacy double-model API.
"""

import os
import pandas as pd
import numpy as np

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
from core.regime_model_manager import RegimeModelManager

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


class MetaLabelingEngine:
    """
    Stateful Meta-Labeling Engine (Stage 2 Classifier).
    Trained to predict setup success probability Y in {0, 1}
    to either Accept (1) or Reject (0) primary setup candidates.
    Delegates back-end logic to RegimeModelManager.
    Implemented as a thread-safe Singleton.
    """
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MetaLabelingEngine, cls).__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.manager = RegimeModelManager()
        
        # Cache for walk-forward dual-model states per fold
        self._wf_models = {}
        
        self._initialized = True

    @property
    def model_path(self):
        return self.manager.model_path

    @model_path.setter
    def model_path(self, value):
        self.manager.model_path = value

    @property
    def features_path(self):
        return self.manager.features_path

    @features_path.setter
    def features_path(self, value):
        self.manager.features_path = value

    # --- Backward-Compatibility properties ---
    @property
    def trending_model(self):
        return self.manager.models.get("TRENDING")

    @trending_model.setter
    def trending_model(self, value):
        self.manager.models["TRENDING"] = value

    @property
    def ranging_model(self):
        return self.manager.models.get("RANGING")

    @ranging_model.setter
    def ranging_model(self, value):
        self.manager.models["RANGING"] = value

    @property
    def trending_calibrator(self):
        return self.manager.calibrators.get("TRENDING")

    @trending_calibrator.setter
    def trending_calibrator(self, value):
        self.manager.calibrators["TRENDING"] = value

    @property
    def ranging_calibrator(self):
        return self.manager.calibrators.get("RANGING")

    @ranging_calibrator.setter
    def ranging_calibrator(self, value):
        self.manager.calibrators["RANGING"] = value

    @property
    def trending_calibration_report(self):
        return self.manager.calibration_reports.get("TRENDING")

    @trending_calibration_report.setter
    def trending_calibration_report(self, value):
        self.manager.calibration_reports["TRENDING"] = value

    @property
    def ranging_calibration_report(self):
        return self.manager.calibration_reports.get("RANGING")

    @ranging_calibration_report.setter
    def ranging_calibration_report(self, value):
        self.manager.calibration_reports["RANGING"] = value

    @property
    def _trending_accuracy(self):
        return self.manager.accuracies.get("TRENDING", 0.0)

    @_trending_accuracy.setter
    def _trending_accuracy(self, value):
        self.manager.accuracies["TRENDING"] = value

    @property
    def _ranging_accuracy(self):
        return self.manager.accuracies.get("RANGING", 0.0)

    @_ranging_accuracy.setter
    def _ranging_accuracy(self, value):
        self.manager.accuracies["RANGING"] = value

    @property
    def _trending_train_accuracy(self):
        return self.manager.train_accuracies.get("TRENDING", 0.0)

    @_trending_train_accuracy.setter
    def _trending_train_accuracy(self, value):
        self.manager.train_accuracies["TRENDING"] = value

    @property
    def _ranging_train_accuracy(self):
        return self.manager.train_accuracies.get("RANGING", 0.0)

    @_ranging_train_accuracy.setter
    def _ranging_train_accuracy(self, value):
        self.manager.train_accuracies["RANGING"] = value

    @property
    def _trending_f1(self):
        return self.manager.f1s.get("TRENDING", 0.0)

    @_trending_f1.setter
    def _trending_f1(self, value):
        self.manager.f1s["TRENDING"] = value

    @property
    def _ranging_f1(self):
        return self.manager.f1s.get("RANGING", 0.0)

    @_ranging_f1.setter
    def _ranging_f1(self, value):
        self.manager.f1s["RANGING"] = value

    @property
    def model(self):
        return self.trending_model

    @model.setter
    def model(self, value):
        self.trending_model = value

    @property
    def calibrator(self):
        return self.trending_calibrator

    @calibrator.setter
    def calibrator(self, value):
        self.trending_calibrator = value

    @property
    def accuracy(self):
        t_acc = self.manager.accuracies.get("TRENDING", 0.0)
        r_acc = self.manager.accuracies.get("RANGING", 0.0)
        if t_acc > 0.0 and r_acc > 0.0:
            return (t_acc + r_acc) / 2.0
        return self.manager.accuracies.get("UNIFIED", 0.0)

    @accuracy.setter
    def accuracy(self, value):
        self.manager.accuracies["UNIFIED"] = value

    @property
    def train_accuracy(self):
        t_acc = self.manager.train_accuracies.get("TRENDING", 0.0)
        r_acc = self.manager.train_accuracies.get("RANGING", 0.0)
        if t_acc > 0.0 and r_acc > 0.0:
            return (t_acc + r_acc) / 2.0
        return self.manager.train_accuracies.get("UNIFIED", 0.0)

    @train_accuracy.setter
    def train_accuracy(self, value):
        self.manager.train_accuracies["UNIFIED"] = value

    @property
    def f1(self):
        t_f1 = self.manager.f1s.get("TRENDING", 0.0)
        r_f1 = self.manager.f1s.get("RANGING", 0.0)
        if t_f1 > 0.0 and r_f1 > 0.0:
            return (t_f1 + r_f1) / 2.0
        return self.manager.f1s.get("UNIFIED", 0.0)

    @f1.setter
    def f1(self, value):
        self.manager.f1s["UNIFIED"] = value

    @property
    def is_trained(self):
        return self.manager.is_trained

    @is_trained.setter
    def is_trained(self, value):
        pass

    def is_ready(self) -> bool:
        """
        Returns True if the ML library is installed, models are loaded/trained,
        and features dataset contains enough samples for reliable predictions.
        """
        if not XGBOOST_AVAILABLE:
            return False
            
        if not self.is_trained:
            return False
            
        if os.path.exists(self.features_path):
            try:
                import polars as pl
                row_count = pl.scan_parquet(self.features_path).select(pl.len()).collect().item()
                if row_count < Config.AI_MIN_SAMPLES:
                    return False
            except Exception:
                return False
                
        return True

    def detect_regime(self, features_dict: dict) -> str:
        """
        Detects active market regime (TRENDING vs RANGING) from candidate features.
        Exposed here for backwards compatibility.
        """
        regime_val = features_dict.get("regime", 0)
        if regime_val == 1 or str(regime_val).upper() in ("1", "TRENDING") or regime_val is True:
            return "TRENDING"
        return "RANGING"

    def apply_symmetry_transform(self, features_dict: dict, side: str) -> dict:
        """
        Applies a directional sign inversion on features for Short signals.
        Enforces sign-invariance so the model learns 'neutral setup strength'.
        """
        return self.manager.apply_symmetry_transform(features_dict, side)

    def train(
        self,
        csv_path: str = None,
        features_df: pd.DataFrame = None,
        save_to_disk: bool = True,
        fit_calibrator: bool = True,
    ) -> dict:
        """
        Delegates dataset loading and full 5-model regime training to RegimeModelManager.
        """
        if not XGBOOST_AVAILABLE:
            return {"status": "error", "message": "xgboost not available"}
            
        try:
            if features_df is not None:
                df = features_df
            else:
                if csv_path is None:
                    csv_path = self.features_path
                    
                if not os.path.exists(csv_path):
                    print(f"❌ Feature file not found at: {csv_path}")
                    return {"status": "error", "message": "features file not found"}
                
                try:
                    from core.data_collector import DatasetVersioning
                    metadata = DatasetVersioning.read_metadata(csv_path)
                    if metadata:
                        print(f"📁 [META-LABELING] Loaded dataset version: {metadata.get('version', 'N/A')} (Rows: {metadata.get('row_count', 'N/A')})")
                except Exception as me:
                    print(f"⚠️ Failed to read Parquet metadata: {me}")
                
                import polars as pl
                df_pl = pl.read_parquet(csv_path)
                df = df_pl.to_pandas()
                
            res = self.manager.train_all(df, fit_calibrator=fit_calibrator, save_to_disk=save_to_disk)
            
            if res.get("status") == "success":
                # Ensure the local legacy attributes sync to TRENDING regime
                t_samples = len(df[(df["atr_pct"] >= self.manager.vol_low_thresh) & (df["atr_pct"] <= self.manager.vol_high_thresh) & (df["regime"] == 1)])
                r_samples = len(df[(df["atr_pct"] >= self.manager.vol_low_thresh) & (df["atr_pct"] <= self.manager.vol_high_thresh) & (df["regime"] == 0)])

                return {
                    "status": "success",
                    "samples": len(df),
                    "accuracy": self.accuracy,
                    "train_accuracy": self.train_accuracy,
                    "f1_score": self.f1,
                    "importances": self.manager.feature_importances["UNIFIED"],
                    "calibration_fitted": (self.manager.calibrators["UNIFIED"].is_fitted if self.manager.calibrators["UNIFIED"] else False),
                    "trending": {
                        "samples": t_samples,
                        "accuracy": res["accuracies"]["TRENDING"],
                        "train_accuracy": res["train_accuracies"]["TRENDING"],
                        "f1_score": res["f1_scores"]["TRENDING"],
                        "importances": self.manager.feature_importances["TRENDING"],
                        "calibration_fitted": (self.manager.calibrators["TRENDING"].is_fitted if self.manager.calibrators["TRENDING"] else False)
                    },
                    "ranging": {
                        "samples": r_samples,
                        "accuracy": res["accuracies"]["RANGING"],
                        "train_accuracy": res["train_accuracies"]["RANGING"],
                        "f1_score": res["f1_scores"]["RANGING"],
                        "importances": self.manager.feature_importances["RANGING"],
                        "calibration_fitted": (self.manager.calibrators["RANGING"].is_fitted if self.manager.calibrators["RANGING"] else False)
                    }
                }
            return res
            
        except Exception as e:
            print(f"❌ Error during Meta-Labeling training delegate: {e}")
            return {"status": "error", "message": str(e)}

    def predict_probability(self, features_dict: dict, side: str = "BUY") -> float:
        """
        Routes the candidate features to the correct specialized regime model in the manager.
        Returns calibrated probability as a percentage (0.0 to 100.0).
        """
        return self.manager.predict_probability(features_dict, side=side, use_specialized=True)

    def get_feature_importance_by_regime(self, regime: str) -> dict:
        """Exposes ordered feature importances per regime model."""
        return self.manager.get_feature_importance(regime.upper())

    def get_feature_importance(self) -> dict:
        """Exposes default feature importances (maps to UNIFIED model)."""
        return self.manager.get_feature_importance("UNIFIED")

    def ensure_wf_model(self, df: pd.DataFrame, features_df: pd.DataFrame, train_limit, embargo_gap: int = None):
        """
        Caches walk-forward fold states chronologically.

        Prompt 28.1 changes the default behavior: short adaptive folds are used
        for out-of-sample evaluation/routing only.  They no longer retrain a new
        XGBoost stack on 80-100 local samples, which produced 99% in-sample
        accuracy and 0% OOS F1.  Local retraining is allowed only when explicitly
        enabled and the fold has enough clean meta-label samples.
        """
        from core.walk_forward import WalkForwardFold

        if isinstance(train_limit, WalkForwardFold):
            fold = train_limit
            fold_key = fold.test_start
            train_start = fold.train_start
            train_end = fold.train_end
            embargo_start = fold.embargo_start
            embargo_end = fold.embargo_end
            test_start = fold.test_start
            test_end = fold.test_end
            e_gap = embargo_end - embargo_start + 1
            label_horizon = int(getattr(fold, "label_horizon", getattr(Config, "WF_LABEL_HORIZON", 100)))
        else:
            fold_key = train_limit
            test_start = train_limit
            e_gap = embargo_gap if embargo_gap is not None else Config.EMBARGO_GAP
            train_end = test_start - 1 - e_gap
            train_start = 0
            embargo_start = train_end + 1
            embargo_end = test_start - 1
            test_end = min(test_start + getattr(Config, "WF_TEST_SIZE", 500) - 1, len(df) - 1)
            label_horizon = int(getattr(Config, "WF_LABEL_HORIZON", 100))

        if fold_key in self._wf_models:
            return

        from core.data_collector import DataCollector

        # Calculate raw technical candidates to keep the audit comparable with
        # previous versions.  This does not influence labels or model training.
        from core.engine import DecisionEngine
        engine = DecisionEngine()
        raw_train_samples = 0
        for i in range(train_start, train_end + 1):
            if i >= len(df):
                continue
            tech_verdict, _, _, _, _, _ = engine._evaluate_score(df.iloc[:i+1])
            if tech_verdict in ("BUY", "SELL"):
                raw_train_samples += 1

        df_subset = DataCollector.generate_training_dataset(
            df=df,
            train_start=train_start,
            train_end=train_end,
            features_df=features_df,
            label_horizon=label_horizon,
        )

        effective_train_size = len(df_subset)
        num_purged_samples = max(0, raw_train_samples - effective_train_size)
        effective_test_size = test_end - test_start + 1

        if isinstance(train_limit, WalkForwardFold):
            train_limit.num_purged_samples = num_purged_samples
            train_limit.effective_train_size = effective_train_size
            train_limit.effective_test_size = effective_test_size

        min_local = int(getattr(Config, "WF_MIN_LOCAL_TRAIN_SAMPLES", 1000))
        eval_only_cfg = bool(getattr(Config, "WF_EVALUATION_ONLY", True))
        allow_local_retrain = bool(getattr(Config, "WF_ALLOW_LOCAL_RETRAIN", False))
        should_local_retrain = (
            allow_local_retrain
            and not eval_only_cfg
            and effective_train_size >= max(min_local, int(getattr(Config, "AI_MIN_SAMPLES", 80)))
        )

        if not should_local_retrain:
            reason = "evaluation_only" if eval_only_cfg or not allow_local_retrain else f"insufficient_local_samples<{min_local}"
            if bool(getattr(Config, "BACKTEST_PRINT_WF_MODEL_LINES", True)):
                print(
                    f"📊 [META-LABELING FOLD {fold_key}] Purged: {num_purged_samples} | "
                    f"Train: {effective_train_size} | Test: {effective_test_size} | "
                    f"Mode: EVAL_ONLY_GLOBAL ({reason})"
                )
            self._wf_models[fold_key] = self._snapshot_current_manager_state(
                train_start=train_start,
                train_end=train_end,
                embargo_start=embargo_start,
                embargo_end=embargo_end,
                test_start=test_start,
                test_end=test_end,
                num_purged_samples=num_purged_samples,
                effective_train_size=effective_train_size,
                effective_test_size=effective_test_size,
                evaluation_only=True,
                evaluation_reason=reason,
            )
            return

        if bool(getattr(Config, "BACKTEST_PRINT_WF_MODEL_LINES", True)):
            print(
                f"📊 [META-LABELING FOLD {fold_key}] Purged: {num_purged_samples} | "
                f"Train: {effective_train_size} | Test: {effective_test_size} | Mode: LOCAL_RETRAIN"
            )

        if df_subset.empty or len(df_subset) < Config.AI_MIN_SAMPLES:
            self._wf_models[fold_key] = self._create_empty_fold_state(
                train_start, train_end, embargo_start, embargo_end, test_start, test_end,
                num_purged_samples, effective_train_size, effective_test_size
            )
            self._wf_models[fold_key]["evaluation_only"] = False
            self._wf_models[fold_key]["evaluation_reason"] = "empty_or_below_ai_min_samples"
            return

        # Preserve the global model registry while the local fold is trained.
        # Without this snapshot, training a fold mutates the live manager used by
        # subsequent folds/profiles.
        global_state = self._snapshot_current_manager_state(
            train_start=train_start,
            train_end=train_end,
            embargo_start=embargo_start,
            embargo_end=embargo_end,
            test_start=test_start,
            test_end=test_end,
            num_purged_samples=num_purged_samples,
            effective_train_size=effective_train_size,
            effective_test_size=effective_test_size,
            evaluation_only=True,
            evaluation_reason="pre_local_retrain_global_backup",
        )

        metrics = self.manager.train_all(df_subset, save_to_disk=False, fit_calibrator=True)

        if metrics["status"] == "success":
            state = self._snapshot_current_manager_state(
                train_start=train_start,
                train_end=train_end,
                embargo_start=embargo_start,
                embargo_end=embargo_end,
                test_start=test_start,
                test_end=test_end,
                num_purged_samples=num_purged_samples,
                effective_train_size=effective_train_size,
                effective_test_size=effective_test_size,
                evaluation_only=False,
                evaluation_reason="local_retrain",
            )
            self._wf_models[fold_key] = state
            # Restore global registry after caching the fold-local model.
            self._restore_manager_from_state(global_state)
        else:
            self._wf_models[fold_key] = self._create_empty_fold_state(
                train_start, train_end, embargo_start, embargo_end, test_start, test_end,
                num_purged_samples, effective_train_size, effective_test_size
            )
            self._wf_models[fold_key]["evaluation_only"] = False
            self._wf_models[fold_key]["evaluation_reason"] = "local_retrain_failed"
            self._restore_manager_from_state(global_state)

    def _snapshot_current_manager_state(
        self,
        *,
        train_start,
        train_end,
        embargo_start,
        embargo_end,
        test_start,
        test_end,
        num_purged_samples,
        effective_train_size,
        effective_test_size,
        evaluation_only: bool,
        evaluation_reason: str,
    ):
        """Return a serializable fold state backed by the current model registry."""
        state = {
            "models":                     dict(self.manager.models),
            "calibrators":                dict(self.manager.calibrators),
            "calibration_reports":        dict(self.manager.calibration_reports),
            "vol_low_thresh":             self.manager.vol_low_thresh,
            "vol_high_thresh":            self.manager.vol_high_thresh,
            "accuracies":                 dict(self.manager.accuracies),
            "train_accuracies":           dict(self.manager.train_accuracies),
            "f1s":                        dict(self.manager.f1s),
            "feature_importances":        dict(self.manager.feature_importances),

            "trending_model":             self.manager.models.get("TRENDING"),
            "ranging_model":              self.manager.models.get("RANGING"),
            "trending_calibrator":        self.manager.calibrators.get("TRENDING"),
            "ranging_calibrator":         self.manager.calibrators.get("RANGING"),
            "trending_accuracy":          self.manager.accuracies.get("TRENDING", 0.5),
            "ranging_accuracy":           self.manager.accuracies.get("RANGING", 0.5),
            "trending_train_accuracy":    self.manager.train_accuracies.get("TRENDING", 0.5),
            "ranging_train_accuracy":     self.manager.train_accuracies.get("RANGING", 0.5),
            "trending_f1":                self.manager.f1s.get("TRENDING", 0.0),
            "ranging_f1":                 self.manager.f1s.get("RANGING", 0.0),

            "model":             self.manager.models.get("UNIFIED"),
            "calibrator":        self.manager.calibrators.get("UNIFIED"),
            "accuracy":          self.manager.accuracies.get("UNIFIED", self.accuracy),
            "train_accuracy":    self.manager.train_accuracies.get("UNIFIED", self.train_accuracy),
            "f1":                self.manager.f1s.get("UNIFIED", self.f1),
            "is_trained":        bool(self.is_trained),
            "importances":       dict(self.manager.feature_importances.get("UNIFIED", {})),
            "calibration_fitted": (
                self.manager.calibrators.get("UNIFIED").is_fitted
                if self.manager.calibrators.get("UNIFIED") else False
            ),

            "train_start": train_start,
            "train_end": train_end,
            "embargo_start": embargo_start,
            "embargo_end": embargo_end,
            "test_start": test_start,
            "test_end": test_end,
            "num_purged_samples": num_purged_samples,
            "effective_train_size": effective_train_size,
            "effective_test_size": effective_test_size,
            "evaluation_only": bool(evaluation_only),
            "evaluation_reason": str(evaluation_reason),
        }
        return state

    def _restore_manager_from_state(self, state):
        self.manager.models = dict(state.get("models", self.manager.models))
        self.manager.calibrators = dict(state.get("calibrators", self.manager.calibrators))
        self.manager.calibration_reports = dict(state.get("calibration_reports", self.manager.calibration_reports))
        self.manager.vol_low_thresh = state.get("vol_low_thresh", self.manager.vol_low_thresh)
        self.manager.vol_high_thresh = state.get("vol_high_thresh", self.manager.vol_high_thresh)
        self.manager.accuracies = dict(state.get("accuracies", self.manager.accuracies))
        self.manager.train_accuracies = dict(state.get("train_accuracies", self.manager.train_accuracies))
        self.manager.f1s = dict(state.get("f1s", self.manager.f1s))
        self.manager.feature_importances = dict(state.get("feature_importances", self.manager.feature_importances))

    def _create_empty_fold_state(self, t_start, t_end, e_start, e_end, test_s, test_e, purged, eff_train, eff_test):
        return {
            "models": {k: None for k in self.manager.models},
            "calibrators": {k: None for k in self.manager.models},
            "calibration_reports": {k: None for k in self.manager.models},
            "vol_low_thresh": 0.33,
            "vol_high_thresh": 0.66,
            "accuracies": {k: 0.5 for k in self.manager.models},
            "train_accuracies": {k: 0.5 for k in self.manager.models},
            "f1s": {k: 0.0 for k in self.manager.models},
            "feature_importances": {k: {} for k in self.manager.models},
            
            # retrocompatibilità
            "trending_model":             None,
            "ranging_model":              None,
            "trending_calibrator":        None,
            "ranging_calibrator":         None,
            "trending_accuracy":          0.5,
            "ranging_accuracy":           0.5,
            "trending_train_accuracy":    0.5,
            "ranging_train_accuracy":     0.5,
            "trending_f1":                0.0,
            "ranging_f1":                 0.0,
            
            "model":             None,
            "calibrator":        None,
            "accuracy":          0.5,
            "train_accuracy":    0.5,
            "f1":                0.0,
            "is_trained":        False,
            "importances":       {},
            "calibration_fitted": False,
            
            "train_start": t_start,
            "train_end": t_end,
            "embargo_start": e_start,
            "embargo_end": e_end,
            "test_start": test_s,
            "test_end": test_e,
            "num_purged_samples": purged,
            "effective_train_size": eff_train,
            "effective_test_size": eff_test,
            "evaluation_only": False,
            "evaluation_reason": "empty_fold",
        }

    def set_active_model(self, train_limit):
        """
        Sets the active model state based on active fold boundaries.
        Called dynamically by backtester/live executor loops.

        Prompt 28.6: in WF evaluation-only mode, ``None`` means "no active
        OOS fold yet", not "delete the global model registry".  The old
        behavior reset the registry before the first fold, making all later
        predictions fall back to the neutral 50.0 probability.
        """
        if train_limit is None:
            if bool(getattr(Config, "WF_EVALUATION_ONLY", True)) and bool(getattr(Config, "WF_KEEP_GLOBAL_MODEL_WHEN_NO_ACTIVE_FOLD", True)):
                self._active_model_key = None
                self._active_model_source = "GLOBAL_EVAL_ONLY_NO_ACTIVE_FOLD"
                return
            self.manager._reset_registry()
            self._active_model_key = None
            self._active_model_source = "RESET_NO_ACTIVE_FOLD"
            return

        if train_limit not in self._wf_models:
            if bool(getattr(Config, "WF_EVALUATION_ONLY", True)) and bool(getattr(Config, "WF_KEEP_GLOBAL_MODEL_WHEN_NO_ACTIVE_FOLD", True)):
                self._active_model_key = None
                self._active_model_source = "GLOBAL_EVAL_ONLY_MISSING_FOLD"
                return
            self.manager._reset_registry()
            self._active_model_key = None
            self._active_model_source = "RESET_MISSING_FOLD"
            return
            
        state = self._wf_models[train_limit]
        self._restore_manager_from_state(state)
        self._active_model_key = train_limit
        self._active_model_source = "EVAL_ONLY_GLOBAL" if state.get("evaluation_only") else "LOCAL_RETRAIN"

    def save_model(self, path: str = None):
        """Delegates serialization to RegimeModelManager."""
        self.manager.save_models(path)

    def load_model(self, path: str = None):
        """Delegates loading to RegimeModelManager."""
        self.manager.load_models(path)
