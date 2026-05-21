"""
test_calibration.py — Self-test for core/calibration.py and ai_engine integration.
Run from: trading_bot/ directory
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd

# ── Test 1: imports ──────────────────────────────────────────────────────────
from core.calibration import (
    ProbabilityCalibrator, CalibrationReport, ConfidenceBucket,
    extract_calibration_split, kelly_size_comparison,
)
print("[OK] core.calibration imports cleanly")

# ── Test 2: Kelly comparison utility ─────────────────────────────────────────
result = kelly_size_comparison(p_raw=0.85, p_cal=0.62, rr_ratio=2.0, kelly_fraction=0.5)
raw_hk = result["half_kelly_raw"]
cal_hk = result["half_kelly_cal"]
red    = result["size_reduction_pct"]
print(f"[OK] Kelly comparison: half-Kelly raw={raw_hk:.3f}  cal={cal_hk:.3f}  reduction={red}%")
assert raw_hk > cal_hk, "Calibrated Kelly must be smaller than raw Kelly when p_cal < p_raw"

# ── Test 3: temporal split ────────────────────────────────────────────────────
X_dummy = pd.DataFrame(np.random.randn(300, 5), columns=list("ABCDE"))
y_dummy = pd.Series(np.random.randint(0, 2, 300))
X_xgb, y_xgb, X_cal, y_cal = extract_calibration_split(X_dummy, y_dummy, cal_fraction=0.20)
assert len(X_xgb) + len(X_cal) == 300, "Split lengths must sum to total"
assert len(X_cal) >= 50, f"Cal set too small: {len(X_cal)}"
# Verify chronological order is preserved (no shuffle)
assert X_xgb.index[-1] < X_cal.index[0], "XGB split must precede calibration split temporally"
print(f"[OK] Temporal split: xgb={len(X_xgb)}, cal={len(X_cal)} — chronological order preserved")

# ── Test 4: full calibration pipeline ────────────────────────────────────────
try:
    from xgboost import XGBClassifier
    from sklearn.datasets import make_classification

    X, y = make_classification(n_samples=600, n_features=13, random_state=42,
                               weights=[0.45, 0.55])
    X_df = pd.DataFrame(X, columns=[f"f{i}" for i in range(13)])
    y_s  = pd.Series(y)

    X_xgb2, y_xgb2, X_cal2, y_cal2 = extract_calibration_split(X_df, y_s, cal_fraction=0.20)
    split = int(len(X_xgb2) * 0.8)
    X_train, X_test = X_xgb2.iloc[:split], X_xgb2.iloc[split:]
    y_train, y_test = y_xgb2.iloc[:split], y_xgb2.iloc[split:]

    clf = XGBClassifier(n_estimators=50, max_depth=3, random_state=42, eval_metric="logloss")
    clf.fit(X_train, y_train)

    for method in ("sigmoid", "isotonic", "auto"):
        cal = ProbabilityCalibrator(method=method)
        cal.fit(clf, X_cal2, y_cal2.values)
        report = cal.evaluate(clf, X_test, y_test.values)
        print(f"[OK] method={method:8s} fitted={cal.is_fitted}  active={cal._active_method:8s} "
              f"Brier {report.brier_raw:.4f}->{report.brier_cal:.4f}  "
              f"ECE {report.ece_raw:.4f}->{report.ece_cal:.4f}")

    # Print detailed report for the last calibrator
    ProbabilityCalibrator.print_report(report)

    # ── Test 5: single-sample calibration ────────────────────────────────────
    p_raw_test = 0.88
    p_cal_val  = cal.calibrate(p_raw_test)
    print(f"[OK] Single sample: p_raw={p_raw_test:.3f} -> p_cal={p_cal_val:.4f}")
    assert 0.0 < p_cal_val < 1.0, "Calibrated prob must be in (0, 1)"

    # ── Test 6: batch calibration consistency ────────────────────────────────
    arr = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    batch = cal.calibrate_batch(arr)
    singles = np.array([cal.calibrate(p) for p in arr])
    np.testing.assert_allclose(batch, singles, rtol=1e-5,
                               err_msg="Batch and single calibration must agree")
    print(f"[OK] Batch calibration consistent with single-sample: {batch.round(4)}")

    # ── Test 7: persistence round-trip ───────────────────────────────────────
    save_path = os.path.join("data", "_test_calibrator.pkl")
    os.makedirs("data", exist_ok=True)
    cal.save(save_path)
    cal2 = ProbabilityCalibrator.load(save_path)
    p_reloaded = cal2.calibrate(p_raw_test)
    assert abs(p_reloaded - p_cal_val) < 1e-8, "Reloaded calibrator must give identical output"
    os.remove(save_path)
    print(f"[OK] Persistence round-trip: saved and reloaded p_cal={p_reloaded:.4f}")

    # ── Test 8: reliability diagram chart ────────────────────────────────────
    chart_path = os.path.join("data", "_test_calibration_chart.png")
    out = ProbabilityCalibrator.plot_reliability_diagram(report, chart_path)
    if out:
        print(f"[OK] Reliability diagram saved: {chart_path}")
        os.remove(chart_path)
    else:
        print("[SKIP] Reliability diagram: matplotlib not available")

except ImportError as e:
    print(f"[SKIP] XGBoost/sklearn not available: {e}")

# ── Test 9: ai_engine integration check ──────────────────────────────────────
from core.ai_engine import TradingAI, CALIBRATION_AVAILABLE
print(f"[OK] ai_engine.py imports cleanly (CALIBRATION_AVAILABLE={CALIBRATION_AVAILABLE})")

ai = TradingAI()
print(f"[OK] TradingAI singleton created — calibrator type: {type(ai.calibrator).__name__}")
if ai.calibrator is not None:
    print(f"     calibrator.is_fitted={ai.calibrator.is_fitted}  method={ai.calibrator.method}")

# predict_probability fallback when model not trained
# predict_probability: if model is trained, returns a real prediction; fallback=50.0 only when untrained
p = ai.predict_probability({"rsi": 65, "adx": 30, "atr_pct": 0.02})
if ai.is_trained:
    assert 0.0 <= p <= 100.0, f"Trained model must return [0,100], got {p}"
    print(f"[OK] Trained model predict_probability() = {p:.2f} (within valid range)")
else:
    assert p == 50.0, f"Untrained model must return 50.0, got {p}"
    print(f"[OK] Untrained model fallback: predict_probability() = {p} (neutral)")

# ── Test 10: Dual-Regime Specific Training, Routing & Persistence ───────────────
print("\n[TEST] Running Dual-Regime Specific Architecture Integration Tests...")
from core.ai_engine import FEATURE_NAMES

# Generate synthetic dataset with regime column
np.random.seed(42)
n_samples = 400
data_dict = {feat: np.random.randn(n_samples) for feat in FEATURE_NAMES}
# Add regime: 1 = TRENDING, 0 = RANGING
data_dict["regime"] = np.random.choice([0, 1], size=n_samples)
# Add outcome target label
data_dict["outcome"] = np.random.choice([0, 1], size=n_samples)

synthetic_df = pd.DataFrame(data_dict)

print(f"   Created synthetic dataset with {n_samples} samples.")
print(f"   Trending samples: {len(synthetic_df[synthetic_df['regime'] == 1])}")
print(f"   Ranging samples: {len(synthetic_df[synthetic_df['regime'] == 0])}")

# Perform Dual-Model Training
test_model_path = os.path.join("data", "_test_dual_model.pkl")
ai_test = TradingAI()
ai_test.model_path = test_model_path

print("   Training dual-regime models...")
train_res = ai_test.train(features_df=synthetic_df, save_to_disk=True, fit_calibrator=True)

# Assertions
assert train_res["status"] == "success", "Training failed"
assert ai_test.trending_model is not None, "trending_model is None"
assert ai_test.ranging_model is not None, "ranging_model is None"
assert ai_test.trending_calibrator is not None, "trending_calibrator is None"
assert ai_test.ranging_calibrator is not None, "ranging_calibrator is None"

print("[OK] Dual models and calibrators successfully created and trained!")

# Verify separate feature importance tables
imp_trend = ai_test.get_feature_importance_by_regime("TRENDING")
imp_range = ai_test.get_feature_importance_by_regime("RANGING")
assert len(imp_trend) > 0, "Trending feature importances empty"
assert len(imp_range) > 0, "Ranging feature importances empty"
assert imp_trend != imp_range, "Feature importances for both regimes should not be identical under random seed"
print("[OK] Distinct feature importance tables verified!")

# Verify retrocompatibility attributes
assert ai_test.model == ai_test.trending_model, "Property 'model' must return trending_model"
assert ai_test.calibrator == ai_test.trending_calibrator, "Property 'calibrator' must return trending_calibrator"
expected_avg_acc = (ai_test._trending_accuracy + ai_test._ranging_accuracy) / 2.0
assert abs(ai_test.accuracy - expected_avg_acc) < 1e-8, "Property 'accuracy' must return average accuracy"
print("[OK] Backward-compatibility properties verified!")

# Verify dynamic model routing
# 1. Routing to TRENDING
sample_trending = {"rsi": 55.0, "adx": 35.0, "atr_pct": 0.03, "regime": 1}
p_trend = ai_test.predict_probability(sample_trending)
assert 0.0 <= p_trend <= 100.0, f"TRENDING routing returned out-of-bounds probability {p_trend}"

# 2. Routing to RANGING
sample_ranging = {"rsi": 45.0, "adx": 12.0, "atr_pct": 0.01, "regime": 0}
p_range = ai_test.predict_probability(sample_ranging)
assert 0.0 <= p_range <= 100.0, f"RANGING routing returned out-of-bounds probability {p_range}"

print(f"[OK] Dynamic routing tested successfully: TRENDING prob={p_trend:.2f}%, RANGING prob={p_range:.2f}%")

# Verify co-persistence (saving & loading both models)
print("   Testing co-persistence and round-trip loading...")
ai_loader = TradingAI()
# Force clean instance attributes to simulate clean reload
ai_loader.trending_model = None
ai_loader.ranging_model = None
ai_loader.trending_calibrator = None
ai_loader.ranging_calibrator = None

ai_loader.load_model(test_model_path)

assert ai_loader.trending_model is not None, "Reloaded trending_model is None"
assert ai_loader.ranging_model is not None, "Reloaded ranging_model is None"
assert ai_loader.trending_calibrator is not None, "Reloaded trending_calibrator is None"
assert ai_loader.ranging_calibrator is not None, "Reloaded ranging_calibrator is None"
print("[OK] Multi-model co-persistence and loading verified!")

# Clean up test artifacts
if os.path.exists(test_model_path):
    os.remove(test_model_path)

print()
print("=" * 60)
print("  ALL CALIBRATION AND DUAL-REGIME TESTS PASSED")
print("=" * 60)

