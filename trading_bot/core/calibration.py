"""
core/calibration.py — Probability Calibration Layer
======================================================
Wraps a trained XGBoost classifier and transforms its raw predict_proba()
output into well-calibrated probabilities, then exposes reliability
diagnostics for monitoring calibration quality over time.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHY CALIBRATION MATTERS FOR KELLY CRITERION SIZING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The Kelly formula is:

    f* = (p · b − q) / b

where p is the TRUE win probability, q = 1 − p, b = reward-to-risk.

If the model outputs p = 0.85 but the true probability is only 0.60,
Kelly will compute an aggressively oversized position:

    f*_wrong  = (0.85·2 − 0.15) / 2  = 0.775   (77.5% of capital — ruinous)
    f*_correct = (0.60·2 − 0.40) / 2  = 0.400   (40.0% of capital — rational)

Even with Half-Kelly (×0.5), a 10-point overconfidence bias pushes
the bet size ~50% too large, dramatically increasing drawdown and
ruin probability. Calibration brings p into alignment with reality.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHY UNCALIBRATED XGBOOST PROBABILITIES ARE DANGEROUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tree-based ensembles (Random Forests, XGBoost, LightGBM) produce
*discriminative* probabilities — they rank samples well (high AUC)
but systematically over-compress predictions toward 0 and 1.

Root cause: each tree leaf assigns the empirical fraction from its
training split, but boosting loss functions optimise the cross-entropy
*ranking* objective, not the marginal probability distribution.

Observed pattern on financial data:
  · True win rate across all signals: ~55%
  · XGBoost outputs: mostly 0.80–0.95 and 0.05–0.20
  · Calibrated outputs: 0.50–0.75 (honest uncertainty)

Isotonic Regression (non-parametric, monotone) corrects this by
fitting a step-function mapping from raw scores to true frequencies
on a held-out calibration set, without assumptions about the shape.

Platt/Sigmoid scaling applies a logistic transform — faster but
assumes the miscalibration is sigmoid-shaped (reasonable for boosting).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TEMPORAL SAFETY NOTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The calibration set MUST be strictly temporally separated from both
the XGBoost training set AND the final test set.  This module enforces
the split:
    [---- TRAIN ----][-- CALIBRATION (embargo) --][-- TEST --]

If calibration is fitted on the same data as XGBoost training, the
calibrator will learn to map already-overfit XGBoost scores back to
the training labels — calibration will appear perfect in-sample but
fail catastrophically out-of-sample.
"""

from __future__ import annotations

import os
import pickle
import warnings
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

# ── Optional sklearn imports ─────────────────────────────────────────────────
try:
    from sklearn.calibration import CalibratedClassifierCV, calibration_curve
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# ── Optional matplotlib ──────────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# ════════════════════════════════════════════════════════════════════════════
# §1 — DIAGNOSTICS DATA STRUCTURES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ConfidenceBucket:
    """
    One bucket in the reliability diagram.
    Holds the mean predicted probability and the empirical win rate
    for all predictions falling within [lower, upper).
    """
    lower:      float = 0.0   # bucket lower bound  [0, 1)
    upper:      float = 0.1   # bucket upper bound  (0, 1]
    mean_pred:  float = 0.0   # avg model output in this bucket
    actual_win: float = 0.0   # observed win fraction in this bucket
    count:      int   = 0     # number of predictions in bucket
    gap:        float = 0.0   # |mean_pred − actual_win|  (calibration gap)


@dataclass
class CalibrationReport:
    """Full calibration diagnostics snapshot."""
    method:          str   = "isotonic"   # "isotonic" | "sigmoid" | "none"
    n_samples:       int   = 0
    brier_raw:       float = 0.0   # Brier score BEFORE calibration
    brier_cal:       float = 0.0   # Brier score AFTER calibration
    ece_raw:         float = 0.0   # Expected Calibration Error, raw
    ece_cal:         float = 0.0   # Expected Calibration Error, calibrated
    max_gap_raw:     float = 0.0   # worst bucket gap, raw
    max_gap_cal:     float = 0.0   # worst bucket gap, calibrated
    is_calibrated:   bool  = False
    buckets_raw:     List[ConfidenceBucket] = field(default_factory=list)
    buckets_cal:     List[ConfidenceBucket] = field(default_factory=list)
    # Avg raw vs calibrated probability (useful to detect direction of bias)
    avg_prob_raw:    float = 0.0
    avg_prob_cal:    float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# §2 — CORE CALIBRATION ENGINE
# ════════════════════════════════════════════════════════════════════════════

class ProbabilityCalibrator:
    """
    Post-hoc calibration wrapper for a fitted XGBoost classifier.

    The calibrator sits between the raw XGBoost predict_proba() call and the
    Kelly / confidence-filter logic.  It:

      1.  Receives the raw XGBoost WIN probability p_raw ∈ [0, 1].
      2.  Applies a monotone mapping f: p_raw → p_cal that aligns predicted
          probabilities with empirically observed win rates.
      3.  Returns p_cal for downstream use by RiskManager.calculate_kelly_risk_pct().

    Calibration method
    ------------------
    "isotonic"  — IsotonicRegression (non-parametric, more powerful, needs ≥ 300 samples)
    "sigmoid"   — Platt scaling via LogisticRegression on logit(p_raw) (needs ≥ 50 samples)
    "auto"      — selects "isotonic" if n_cal ≥ 300, otherwise "sigmoid"

    Temporal safety
    ---------------
    The calibration set is extracted from the END of the training fold — after
    XGBoost training is complete — and is NEVER reused for XGBoost fitting.
    This is controlled by the `cal_fraction` parameter (default: last 20% of
    XGBoost training data, kept strictly out of XGBoost fitting).

    Thread safety
    -------------
    The calibrator is stateless during inference (transform() / calibrate()).
    The internal isotonic/logistic regressor is read-only after fit().
    """

    # Minimum samples needed to fit each method safely.
    _MIN_SAMPLES = {"isotonic": 100, "sigmoid": 40, "none": 0}

    def __init__(
        self,
        method:       str   = "auto",
        cal_fraction: float = 0.20,
        n_bins:       int   = 10,
        clip_eps:     float = 1e-6,
    ):
        """
        Parameters
        ----------
        method       : "auto" | "isotonic" | "sigmoid" | "none"
        cal_fraction : fraction of the XGBoost training data reserved for
                       calibration (taken from the chronological end of the
                       training window — AFTER XGBoost training).
        n_bins       : number of bins for reliability diagram / ECE.
        clip_eps     : probability output clipped to [clip_eps, 1−clip_eps]
                       to prevent log(0) in downstream Brier/log-loss calcs.
        """
        if not SKLEARN_AVAILABLE:
            warnings.warn(
                "[Calibration] scikit-learn not found — calibration disabled. "
                "Raw XGBoost probabilities will be used. Install scikit-learn >= 1.3.",
                RuntimeWarning,
            )

        self.method       = method
        self.cal_fraction = cal_fraction
        self.n_bins       = n_bins
        self.clip_eps     = clip_eps

        # Internal state (set by fit())
        self._calibrator    = None   # IsotonicRegression | LogisticRegression | None
        self._active_method = "none"
        self.is_fitted      = False

    # ── Public interface ──────────────────────────────────────────────────────

    def fit(
        self,
        xgb_model,                 # fitted XGBClassifier
        X_cal: pd.DataFrame,       # calibration features (temporally held-out)
        y_cal: np.ndarray,         # calibration labels (0 / 1)
    ) -> "ProbabilityCalibrator":
        """
        Fit the calibration mapping on a temporally isolated calibration set.

        CRITICAL: X_cal / y_cal must be data the XGBoost model has NEVER seen
        during training (no leakage).  In the walk-forward pipeline this means
        the calibration set is carved from the embargo zone immediately after
        the training window closes.

        Parameters
        ----------
        xgb_model : fitted XGBClassifier (from ai_engine.py)
        X_cal     : calibration feature DataFrame  (shape: [n_cal, n_features])
        y_cal     : calibration outcome array (0 = loss, 1 = win)

        Returns self for chaining.
        """
        self.is_fitted = False
        self._calibrator = None

        if not SKLEARN_AVAILABLE:
            return self

        if xgb_model is None or len(X_cal) == 0:
            warnings.warn("[Calibration] fit() called with empty calibration set — skipping.")
            return self

        n_cal = len(y_cal)
        unique_labels = np.unique(y_cal)
        if len(unique_labels) < 2:
            warnings.warn(
                f"[Calibration] Calibration set has only one class ({unique_labels}). "
                "Calibration requires both WIN (1) and LOSS (0) samples. Skipping."
            )
            return self

        # Determine active method
        if self.method == "auto":
            self._active_method = "isotonic" if n_cal >= self._MIN_SAMPLES["isotonic"] else "sigmoid"
        else:
            self._active_method = self.method

        min_needed = self._MIN_SAMPLES.get(self._active_method, 40)
        if n_cal < min_needed:
            warnings.warn(
                f"[Calibration] Only {n_cal} calibration samples available "
                f"(need ≥ {min_needed} for '{self._active_method}'). "
                "Falling back to 'none' — raw XGBoost probabilities used."
            )
            self._active_method = "none"
            return self

        try:
            # Get raw scores from XGBoost on calibration set
            p_raw = xgb_model.predict_proba(X_cal)[:, 1].astype(float)
            p_raw = np.clip(p_raw, self.clip_eps, 1.0 - self.clip_eps)
            y_cal = np.array(y_cal, dtype=int)

            if self._active_method == "isotonic":
                # Isotonic Regression: monotone non-parametric step function
                # Fits a non-decreasing function f such that p_cal = f(p_raw).
                # Guaranteed monotone (higher raw score → higher calibrated score)
                iso = IsotonicRegression(out_of_bounds="clip", increasing=True)
                iso.fit(p_raw, y_cal.astype(float))
                self._calibrator = iso

            elif self._active_method == "sigmoid":
                # Platt Scaling: fits σ(A·log(p/(1-p)) + B) via LogisticRegression
                # on 1D logit-transformed raw scores.
                logit_p = np.log(p_raw / (1.0 - p_raw)).reshape(-1, 1)
                lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
                lr.fit(logit_p, y_cal)
                self._calibrator = lr

            self.is_fitted = True
            print(
                f"[Calibration] Fitted '{self._active_method}' calibrator on "
                f"{n_cal} samples. Raw avg prob: {p_raw.mean():.3f}, "
                f"observed win rate: {y_cal.mean():.3f}."
            )

        except Exception as exc:
            warnings.warn(f"[Calibration] fit() failed: {exc}. Raw probabilities used.")
            self._active_method = "none"
            self.is_fitted = False

        return self

    def calibrate(self, p_raw: float) -> float:
        """
        Transform a single raw XGBoost WIN probability into a calibrated one.

        Parameters
        ----------
        p_raw : raw predict_proba() output ∈ [0.0, 1.0]

        Returns
        -------
        p_cal : calibrated probability ∈ [clip_eps, 1−clip_eps]

        Fallback behaviour
        ------------------
        If the calibrator is not fitted (insufficient data, import error, etc.)
        the raw probability is returned unchanged.  This guarantees the
        inference pipeline never breaks even when calibration is unavailable.
        """
        if not self.is_fitted or self._calibrator is None:
            return float(np.clip(p_raw, self.clip_eps, 1.0 - self.clip_eps))

        try:
            p_in = float(np.clip(p_raw, self.clip_eps, 1.0 - self.clip_eps))

            if self._active_method == "isotonic":
                p_cal = float(self._calibrator.transform([p_in])[0])

            elif self._active_method == "sigmoid":
                logit_p = math.log(p_in / (1.0 - p_in))
                p_cal = float(self._calibrator.predict_proba([[logit_p]])[0][1])

            else:
                p_cal = p_in

            return float(np.clip(p_cal, self.clip_eps, 1.0 - self.clip_eps))

        except Exception as exc:
            warnings.warn(f"[Calibration] calibrate() error: {exc}. Returning raw prob.")
            return float(np.clip(p_raw, self.clip_eps, 1.0 - self.clip_eps))

    def calibrate_batch(self, p_raw_arr: np.ndarray) -> np.ndarray:
        """
        Vectorised version of calibrate() — O(n) transform over an array.
        Used during backtesting and diagnostics computation.
        """
        if not self.is_fitted or self._calibrator is None:
            return np.clip(p_raw_arr, self.clip_eps, 1.0 - self.clip_eps)

        try:
            arr = np.clip(p_raw_arr.astype(float), self.clip_eps, 1.0 - self.clip_eps)

            if self._active_method == "isotonic":
                return np.clip(
                    self._calibrator.transform(arr),
                    self.clip_eps, 1.0 - self.clip_eps
                )

            elif self._active_method == "sigmoid":
                logits = np.log(arr / (1.0 - arr)).reshape(-1, 1)
                return np.clip(
                    self._calibrator.predict_proba(logits)[:, 1],
                    self.clip_eps, 1.0 - self.clip_eps
                )

            return arr

        except Exception as exc:
            warnings.warn(f"[Calibration] calibrate_batch() error: {exc}.")
            return np.clip(p_raw_arr, self.clip_eps, 1.0 - self.clip_eps)

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def evaluate(
        self,
        xgb_model,
        X_eval: pd.DataFrame,
        y_eval: np.ndarray,
    ) -> CalibrationReport:
        """
        Compute a full CalibrationReport on an evaluation set.

        Produces:
        - Brier score (before and after calibration)
        - Expected Calibration Error (before and after calibration)
        - Per-bucket reliability data for the reliability diagram
        - Average predicted probability shift

        Parameters
        ----------
        xgb_model : fitted XGBClassifier
        X_eval    : feature DataFrame for evaluation
        y_eval    : true outcome labels

        Returns
        -------
        CalibrationReport dataclass
        """
        report = CalibrationReport(method=self._active_method)

        if not SKLEARN_AVAILABLE or xgb_model is None or len(X_eval) == 0:
            return report

        y_eval = np.array(y_eval, dtype=int)
        report.n_samples = len(y_eval)

        try:
            p_raw = xgb_model.predict_proba(X_eval)[:, 1].astype(float)
            p_raw = np.clip(p_raw, self.clip_eps, 1.0 - self.clip_eps)
            p_cal = self.calibrate_batch(p_raw)

            report.avg_prob_raw = float(p_raw.mean())
            report.avg_prob_cal = float(p_cal.mean())

            # Brier scores
            if len(np.unique(y_eval)) > 1:
                report.brier_raw = float(brier_score_loss(y_eval, p_raw))
                report.brier_cal = float(brier_score_loss(y_eval, p_cal))

            # Bucket-level reliability
            report.buckets_raw = self._compute_buckets(p_raw, y_eval)
            report.buckets_cal = self._compute_buckets(p_cal, y_eval)

            # ECE = weighted average |gap|
            report.ece_raw = self._ece(report.buckets_raw, report.n_samples)
            report.ece_cal = self._ece(report.buckets_cal, report.n_samples)

            # Max gap
            report.max_gap_raw = max((b.gap for b in report.buckets_raw), default=0.0)
            report.max_gap_cal = max((b.gap for b in report.buckets_cal), default=0.0)

            report.is_calibrated = self.is_fitted

        except Exception as exc:
            warnings.warn(f"[Calibration] evaluate() failed: {exc}")

        return report

    def _compute_buckets(
        self, p: np.ndarray, y: np.ndarray
    ) -> List[ConfidenceBucket]:
        """Bin predictions into equal-width buckets and compute reliability stats."""
        buckets: List[ConfidenceBucket] = []
        edges = np.linspace(0.0, 1.0, self.n_bins + 1)

        for i in range(self.n_bins):
            lo, hi = edges[i], edges[i + 1]
            mask = (p >= lo) & (p < hi if hi < 1.0 else p <= hi)
            count = int(mask.sum())
            if count == 0:
                buckets.append(ConfidenceBucket(lower=lo, upper=hi))
                continue
            mean_pred  = float(p[mask].mean())
            actual_win = float(y[mask].mean())
            gap        = abs(mean_pred - actual_win)
            buckets.append(ConfidenceBucket(
                lower=lo, upper=hi,
                mean_pred=mean_pred, actual_win=actual_win,
                count=count, gap=gap,
            ))

        return buckets

    @staticmethod
    def _ece(buckets: List[ConfidenceBucket], n_total: int) -> float:
        """
        Expected Calibration Error:
            ECE = Σ_b (|B_b| / n) · |acc(B_b) − conf(B_b)|
        where B_b is the set of samples in bucket b.
        """
        if n_total == 0:
            return 0.0
        return float(sum(b.count / n_total * b.gap for b in buckets))

    # ── Console report ────────────────────────────────────────────────────────

    @staticmethod
    def print_report(report: CalibrationReport, width: int = 88) -> None:
        """Print a formatted calibration diagnostics dashboard to stdout."""
        sep = "=" * width
        print(f"\n{sep}")
        print(f"  PROBABILITY CALIBRATION DIAGNOSTICS  [method: {report.method.upper()}]")
        print(sep)

        def pct_improve(before: float, after: float) -> str:
            if before <= 0:
                return "n/a"
            delta = (before - after) / before * 100
            sign  = "+" if delta >= 0 else ""
            return f"{sign}{delta:.1f}% improvement" if delta >= 0 else f"{delta:.1f}% worse"

        print(f"  Samples evaluated   : {report.n_samples}")
        print(f"  Calibrated          : {'YES' if report.is_calibrated else 'NO (raw probs used)'}")
        print(f"  Avg predicted prob  : {report.avg_prob_raw:.4f} -> {report.avg_prob_cal:.4f}  "
              f"(shift: {report.avg_prob_cal - report.avg_prob_raw:+.4f})")
        print()

        # Brier table
        print(f"  {'Metric':<32} {'Raw':>10} {'Calibrated':>12} {'Change':>22}")
        print(f"  {'-'*76}")
        print(f"  {'Brier Score (lower=better)':<32} {report.brier_raw:>10.4f} "
              f"{report.brier_cal:>12.4f}  {pct_improve(report.brier_raw, report.brier_cal):>20}")
        print(f"  {'Expected Calib. Error (lower=better)':<32} {report.ece_raw:>10.4f} "
              f"{report.ece_cal:>12.4f}  {pct_improve(report.ece_raw, report.ece_cal):>20}")
        print(f"  {'Max Bucket Gap (lower=better)':<32} {report.max_gap_raw:>10.4f} "
              f"{report.max_gap_cal:>12.4f}  {pct_improve(report.max_gap_raw, report.max_gap_cal):>20}")
        print()

        # Reliability table
        print(f"  CONFIDENCE BUCKET ANALYSIS (Calibrated):")
        print(f"  {'Bucket':<14} {'Mean Pred':>10} {'Actual Win':>12} {'Gap':>8} {'Count':>8} {'Bias':>10}")
        print(f"  {'-'*64}")
        for b in report.buckets_cal:
            if b.count == 0:
                continue
            bias = "OVER" if b.mean_pred > b.actual_win else "UNDER"
            flag = " !" if b.gap > 0.10 else ""
            print(f"  [{b.lower:.1f}, {b.upper:.1f}){'':<5} "
                  f"{b.mean_pred:>10.3f} {b.actual_win:>12.3f} "
                  f"{b.gap:>8.3f} {b.count:>8} {bias:>10}{flag}")

        # Interpretation
        print()
        if report.ece_cal < 0.03:
            quality = "EXCELLENT — model probabilities are reliable for Kelly sizing"
        elif report.ece_cal < 0.06:
            quality = "GOOD — minor residual bias; Half-Kelly recommended"
        elif report.ece_cal < 0.10:
            quality = "FAIR — moderate miscalibration; use conservative Kelly fraction"
        else:
            quality = "POOR — significant miscalibration; avoid raw Kelly; use fixed sizing"
        print(f"  Calibration Quality : {quality}")
        print(sep + "\n")

    # ── Chart ─────────────────────────────────────────────────────────────────

    @staticmethod
    def plot_reliability_diagram(
        report: CalibrationReport,
        output_path: str = "data/calibration_chart.png",
    ) -> Optional[str]:
        """
        Save a reliability diagram comparing raw vs calibrated probabilities.

        A perfectly calibrated model follows the diagonal y = x.
        Curves above the diagonal are UNDERCONFIDENT (model outputs lower p than actual win rate).
        Curves below the diagonal are OVERCONFIDENT (model outputs higher p than actual win rate).
        XGBoost is typically OVERCONFIDENT — the calibrated curve should sit closer to the diagonal.

        Returns the saved path or None if matplotlib is unavailable.
        """
        if not MATPLOTLIB_AVAILABLE:
            return None

        BG   = "#0D1117"
        FG   = "#E6EDF3"
        GRID = "#21262D"
        C_RAW = "#EF5350"
        C_CAL = "#4FC3F7"

        style = {
            "figure.facecolor": BG, "axes.facecolor": BG,
            "axes.edgecolor": GRID, "axes.labelcolor": FG,
            "text.color": FG, "xtick.color": FG, "ytick.color": FG,
            "grid.color": GRID, "grid.linestyle": "--", "grid.linewidth": 0.5,
        }

        with plt.rc_context(style):
            fig, axes = plt.subplots(1, 2, figsize=(14, 6))
            fig.suptitle("Probability Calibration — Reliability Diagram",
                         fontsize=14, fontweight="bold", color=FG)

            # ── Left: reliability curves ─────────────────────────────────────
            ax = axes[0]
            ax.plot([0, 1], [0, 1], linestyle="--", color="#90A4AE",
                    linewidth=1.2, label="Perfect calibration")

            def _plot_curve(buckets, color, label):
                xs = [b.mean_pred for b in buckets if b.count > 0]
                ys = [b.actual_win for b in buckets if b.count > 0]
                if xs:
                    ax.plot(xs, ys, marker="o", color=color, linewidth=1.6,
                            markersize=6, label=label)
                    ax.fill_between(xs, xs, ys, alpha=0.08, color=color)

            _plot_curve(report.buckets_raw, C_RAW,
                        f"Raw XGBoost (ECE={report.ece_raw:.3f})")
            _plot_curve(report.buckets_cal, C_CAL,
                        f"Calibrated  (ECE={report.ece_cal:.3f})")

            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.set_xlabel("Mean Predicted Probability")
            ax.set_ylabel("Observed Win Rate (Fraction of Positives)")
            ax.set_title("Reliability Diagram")
            ax.legend(framealpha=0.15)
            ax.grid(True)

            # ── Right: Brier + ECE bar comparison ────────────────────────────
            ax2 = axes[1]
            metrics = ["Brier Score", "ECE"]
            raw_vals = [report.brier_raw, report.ece_raw]
            cal_vals = [report.brier_cal, report.ece_cal]
            x = np.arange(len(metrics))
            w = 0.35

            bars_r = ax2.bar(x - w/2, raw_vals, w, color=C_RAW,
                             alpha=0.8, label="Raw XGBoost", edgecolor="none")
            bars_c = ax2.bar(x + w/2, cal_vals, w, color=C_CAL,
                             alpha=0.8, label="Calibrated",  edgecolor="none")

            for bar in list(bars_r) + list(bars_c):
                h = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width() / 2, h + 0.002,
                         f"{h:.4f}", ha="center", va="bottom", fontsize=9, color=FG)

            ax2.set_xticks(x)
            ax2.set_xticklabels(metrics)
            ax2.set_ylabel("Score (lower is better)")
            ax2.set_title("Brier Score & ECE Comparison")
            ax2.legend(framealpha=0.15)
            ax2.grid(axis="y")
            ax2.set_ylim(0, max(max(raw_vals), 0.01) * 1.4)

            plt.tight_layout()
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close()

        print(f"  [Calibration] Reliability diagram saved -> {output_path}")
        return output_path

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Pickle the calibrator state to disk."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        state = {
            "method":         self.method,
            "active_method":  self._active_method,
            "cal_fraction":   self.cal_fraction,
            "n_bins":         self.n_bins,
            "clip_eps":       self.clip_eps,
            "is_fitted":      self.is_fitted,
            "_calibrator":    self._calibrator,
        }
        with open(path, "wb") as fh:
            pickle.dump(state, fh)
        print(f"  [Calibration] Saved calibrator -> {path}")

    @classmethod
    def load(cls, path: str) -> "ProbabilityCalibrator":
        """Load a previously saved calibrator from disk."""
        with open(path, "rb") as fh:
            state = pickle.load(fh)
        obj = cls(
            method=state["method"],
            cal_fraction=state.get("cal_fraction", 0.20),
            n_bins=state.get("n_bins", 10),
            clip_eps=state.get("clip_eps", 1e-6),
        )
        obj._active_method = state.get("active_method", "none")
        obj._calibrator    = state.get("_calibrator")
        obj.is_fitted      = state.get("is_fitted", False)
        print(f"  [Calibration] Loaded calibrator from {path} "
              f"[method={obj._active_method}, fitted={obj.is_fitted}]")
        return obj


# ════════════════════════════════════════════════════════════════════════════
# §3 — TEMPORAL CALIBRATION SET EXTRACTOR
#       Integrates with the walk-forward pipeline
# ════════════════════════════════════════════════════════════════════════════

def extract_calibration_split(
    X: pd.DataFrame,
    y: pd.Series,
    cal_fraction: float = 0.20,
    min_cal_samples: int = 50,
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """
    Temporally splits (X, y) into (X_train, y_train) and (X_cal, y_cal).

    The calibration set is taken from the CHRONOLOGICAL END of the supplied
    data.  It is NEVER shuffled, ensuring strict temporal ordering.

    Parameters
    ----------
    X             : feature matrix (ordered chronologically)
    y             : label series
    cal_fraction  : fraction allocated to calibration (from the end)
    min_cal_samples : minimum samples required; if not met, cal set is empty

    Returns
    -------
    X_train, y_train : XGBoost training portion (early period)
    X_cal,   y_cal   : calibration portion (later period — XGBoost never sees this)
    """
    n = len(X)
    n_cal = max(0, int(n * cal_fraction))

    if n_cal < min_cal_samples:
        # Not enough data for a meaningful calibration set — return all for training
        return X, y, pd.DataFrame(columns=X.columns), pd.Series(dtype=int)

    split_idx = n - n_cal
    return (
        X.iloc[:split_idx],     y.iloc[:split_idx],
        X.iloc[split_idx:],     y.iloc[split_idx:],
    )


# ════════════════════════════════════════════════════════════════════════════
# §4 — KELLY ADJUSTMENT HELPER
#       Shows the numerical impact of calibration on position sizing
# ════════════════════════════════════════════════════════════════════════════

def kelly_size_comparison(
    p_raw: float,
    p_cal: float,
    rr_ratio: float,
    kelly_fraction: float = 0.5,
) -> dict:
    """
    Compute Full-Kelly and Half-Kelly sizes for raw vs calibrated probabilities.

    Returns a dict with sizing info for logging / diagnostics.
    This makes the calibration effect *quantitatively* visible.

    Example
    -------
    >>> kelly_size_comparison(p_raw=0.85, p_cal=0.62, rr_ratio=2.0)
    {
      'kelly_raw':  0.775,  'half_kelly_raw':  0.388,
      'kelly_cal':  0.430,  'half_kelly_cal':  0.215,
      'size_reduction_pct': 44.6,
    }
    """
    def _kelly(p: float, b: float) -> float:
        q = 1.0 - p
        k = (p * b - q) / b
        return max(0.0, k)

    k_raw = _kelly(p_raw, rr_ratio)
    k_cal = _kelly(p_cal, rr_ratio)

    reduction = (k_raw - k_cal) / max(k_raw, 1e-9) * 100

    return {
        "p_raw":              round(p_raw, 4),
        "p_cal":              round(p_cal, 4),
        "rr_ratio":           round(rr_ratio, 2),
        "kelly_raw":          round(k_raw, 4),
        "half_kelly_raw":     round(k_raw * kelly_fraction, 4),
        "kelly_cal":          round(k_cal, 4),
        "half_kelly_cal":     round(k_cal * kelly_fraction, 4),
        "size_reduction_pct": round(reduction, 1),
    }
