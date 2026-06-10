"""
run_phase_1_2_recertification.py — Prompt 2H: Hotfix e certificazione Fasi 1-2
================================================================================
Diagnostic-only runner. Verifies all 8 problems identified in the Prompt 2H
independent audit of Phases 1 and 2.

Does NOT: open orders, connect to exchanges, modify strategies, modify paper state,
          modify API keys, enable live or testnet trading.

Usage (from project root):
    python trading_bot/run_phase_1_2_recertification.py

Exit code: 0 if recertification PASS, 1 if BLOCKED.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parent.parent
_TRADING_BOT = _THIS_FILE.parent
for _p in (str(PROJECT_ROOT), str(_TRADING_BOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_PATH = DATA_DIR / "phase_1_2_recertification_status.json"
OPS_BASELINE_PATH = DATA_DIR / "ops_approved_baseline.json"
PHASE1_STATUS_PATH = DATA_DIR / "market_data_integrity_status.json"
PHASE2_STATUS_PATH = DATA_DIR / "cost_model_validation.json"

DIAGNOSTIC_ONLY: bool = True
OPENS_ORDERS: bool = False
LIVE_TRADING_ALLOWED: bool = False
PAPER_TRADING_ACTIVATION_ALLOWED: bool = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _md5_str(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _pf(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


# ===========================================================================
# Check 1 — Gate bypass analysis
# ===========================================================================

def check_gate_bypass(phase1_status: Dict) -> Dict[str, Any]:
    """
    Verify that the 3-tier gate architecture is present and no gate was bypassed.

    Phase 1 gate_result = BLOCKED (correct — contamination in derived artifacts).
    raw_data_gate = PASS (correct — all 8 raw OHLCV approved).
    derived_artifact_gate = BLOCKED (correct — contamination documented).
    benchmark_readiness_gate = PASS (Phase 3 can proceed using only raw OHLCV).

    Phase 2 does NOT bypass Phase 1 gate — it was certified independently because
    the cost model depends only on raw OHLCV (not on contaminated derived reports).
    This distinction is now formally documented with the 3-tier gate architecture.
    """
    raw_data_gate = phase1_status.get("raw_data_gate", "MISSING")
    derived_gate = phase1_status.get("derived_artifact_gate", "MISSING")
    benchmark_gate = phase1_status.get("benchmark_readiness_gate", "MISSING")
    overall_gate = phase1_status.get("gate_result", "MISSING")

    issues = []
    if raw_data_gate != "PASS":
        issues.append(f"raw_data_gate expected PASS, got {raw_data_gate!r}")
    if derived_gate != "BLOCKED":
        # derived contamination still exists — should still be BLOCKED
        issues.append(
            f"derived_artifact_gate expected BLOCKED (contamination not yet fixed), got {derived_gate!r}"
        )
    if benchmark_gate != "PASS":
        issues.append(f"benchmark_readiness_gate expected PASS, got {benchmark_gate!r}")
    if overall_gate != "BLOCKED":
        issues.append(f"gate_result expected BLOCKED (derived contamination present), got {overall_gate!r}")

    has_three_tier = all(
        k in phase1_status
        for k in ("raw_data_gate", "derived_artifact_gate", "benchmark_readiness_gate")
    )
    if not has_three_tier:
        issues.append("3-tier gate fields missing from market_data_integrity_status.json")

    return {
        "check": "gate_architecture",
        "raw_data_gate": raw_data_gate,
        "derived_artifact_gate": derived_gate,
        "benchmark_readiness_gate": benchmark_gate,
        "overall_gate": overall_gate,
        "three_tier_present": has_three_tier,
        "issues": issues,
        "status": _pf(len(issues) == 0),
    }


# ===========================================================================
# Check 2 — Cost model parity (compute_trade_outcome vs apply_cost_to_backtest)
# ===========================================================================

def check_cost_model_parity() -> Dict[str, Any]:
    """
    Verify that compute_trade_outcome and apply_cost_to_backtest_trade produce
    the same total_cost_amt on flat trades (entry == exit) for all scenarios.

    Prompt 3A: both APIs use _compute_cost_amounts(entry_notional, exit_notional, bps).
    Parity is EXACT on all trades — flat or non-flat. No documented approximation.
    Tested at flat, 1%, 20%, 100% price moves.
    """
    try:
        from core.unified_trade_cost import SCENARIO_NAMES, UnifiedCostModel
    except ImportError as exc:
        return {"check": "cost_parity", "status": "FAIL", "error": str(exc)}

    entry = 50000.0
    stop = 49000.0
    qty = 0.01
    initial_risk = abs(entry - stop) * qty

    issues = []
    parity_results = {}

    # Test flat and non-flat trade parity
    test_exits = {
        "flat": entry,
        "+1pct": entry * 1.01,
        "+20pct": entry * 1.20,
        "+100pct": entry * 2.0,
        "-4pct_loss": entry * 0.96,
    }

    for exit_label, exit_price in test_exits.items():
        gross_pnl = (exit_price - entry) * qty
        for sc in SCENARIO_NAMES:
            o = UnifiedCostModel.compute_trade_outcome(
                side="BUY", entry_price=entry, exit_price=exit_price,
                stop_price=stop, quantity=qty,
                scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
            )
            r = UnifiedCostModel.apply_cost_to_backtest_trade(
                gross_pnl=gross_pnl, initial_risk=initial_risk,
                entry_price=entry, exit_price=exit_price, quantity=qty,
                scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
            )
            diff = abs(o.total_cost_amt - r["cost_amt"])
            rel_diff = diff / max(abs(r["cost_amt"]), 1e-10)
            parity_ok = rel_diff < 1e-9  # exact parity required
            key = f"{sc}_{exit_label}"
            if not parity_ok:
                issues.append(
                    f"[{key}] parity failure: compute={o.total_cost_amt:.10f} "
                    f"apply={r['cost_amt']:.10f} rel_diff={rel_diff:.2e}"
                )
            parity_results[key] = {
                "exit_price": exit_price,
                "compute_total_cost_amt": round(o.total_cost_amt, 10),
                "apply_cost_amt": round(r["cost_amt"], 10),
                "rel_diff": round(rel_diff, 12),
                "parity_exact": parity_ok,
            }

    # Also verify SELL parity on flat trade
    stop_sell = 50500.0
    initial_risk_sell = abs(entry - stop_sell) * qty
    for sc in SCENARIO_NAMES:
        o_sell = UnifiedCostModel.compute_trade_outcome(
            side="SELL", entry_price=entry, exit_price=entry,
            stop_price=stop_sell, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        r_sell = UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=0.0, initial_risk=initial_risk_sell,
            entry_price=entry, exit_price=entry, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        diff = abs(o_sell.total_cost_amt - r_sell["cost_amt"])
        rel_diff = diff / max(abs(r_sell["cost_amt"]), 1e-10)
        if rel_diff >= 1e-9:
            issues.append(f"[{sc} SELL flat] parity failure rel_diff={rel_diff:.2e}")

    return {
        "check": "cost_parity",
        "parity_type": "EXACT — same _compute_cost_amounts() called by both APIs",
        "no_documented_approximation": True,
        "exit_prices_tested": list(test_exits.keys()),
        "parity_by_scenario_exit": parity_results,
        "issues": issues,
        "status": _pf(len(issues) == 0),
    }


# ===========================================================================
# Check 3 — latency + partial_fill in total_cost_amt
# ===========================================================================

def check_latency_partial_in_total_cost() -> Dict[str, Any]:
    """
    Verify that compute_trade_outcome().total_cost_amt includes latency_amt
    and partial_fill_amt (previously missing — these were in total_round_trip_bps
    but not charged in the amount calculation).
    """
    try:
        from core.unified_trade_cost import UnifiedCostModel
    except ImportError as exc:
        return {"check": "latency_partial_inclusion", "status": "FAIL", "error": str(exc)}

    issues = []
    results = {}

    # Severe scenario should have both latency and partial_fill > 0
    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY", entry_price=50000.0, exit_price=51000.0,
        stop_price=49500.0, quantity=0.01,
        scenario="severe", symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
    )

    # severe BTC/USDT 15m atr=0:
    # latency_bps = 2.5 * 2.75 * 1.0 = 6.875 → latency_amt = 500 * 6.875/10000 = 0.34375
    # partial_fill_bps = 2.0 * 2.75 * 1.0 = 5.5 → partial_fill_amt = 500 * 5.5/10000 = 0.275
    expected_latency_amt = 0.34375
    expected_partial_amt = 0.275

    if abs(o.latency_amt - expected_latency_amt) > 1e-6:
        issues.append(
            f"severe latency_amt={o.latency_amt:.8f} expected={expected_latency_amt}"
        )
    if abs(o.partial_fill_amt - expected_partial_amt) > 1e-6:
        issues.append(
            f"severe partial_fill_amt={o.partial_fill_amt:.8f} expected={expected_partial_amt}"
        )

    # total_cost_amt must equal sum of all 6 components
    manual_total = (
        o.fee_entry_amt + o.fee_exit_amt + o.spread_amt
        + o.slippage_amt + o.latency_amt + o.partial_fill_amt
    )
    if abs(o.total_cost_amt - manual_total) > 1e-9:
        issues.append(
            f"total_cost_amt={o.total_cost_amt:.8f} != sum of components={manual_total:.8f}"
        )

    # optimistic and realistic must have latency=0, partial=0
    for sc in ("optimistic", "realistic"):
        oc = UnifiedCostModel.compute_trade_outcome(
            side="BUY", entry_price=50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        if abs(oc.latency_amt) > 1e-10:
            issues.append(f"[{sc}] latency_amt={oc.latency_amt} expected 0")
        if abs(oc.partial_fill_amt) > 1e-10:
            issues.append(f"[{sc}] partial_fill_amt={oc.partial_fill_amt} expected 0")

    # conservative must have latency > 0, partial = 0
    oc = UnifiedCostModel.compute_trade_outcome(
        side="BUY", entry_price=50000.0, exit_price=51000.0,
        stop_price=49500.0, quantity=0.01,
        scenario="conservative", symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
    )
    if oc.latency_amt <= 0:
        issues.append(f"conservative latency_amt={oc.latency_amt} expected > 0")
    if abs(oc.partial_fill_amt) > 1e-10:
        issues.append(f"conservative partial_fill_amt={oc.partial_fill_amt} expected 0")

    results["severe"] = {
        "latency_amt": round(o.latency_amt, 8),
        "partial_fill_amt": round(o.partial_fill_amt, 8),
        "total_cost_amt": round(o.total_cost_amt, 8),
        "manual_sum": round(manual_total, 8),
        "all_components_included": abs(o.total_cost_amt - manual_total) < 1e-9,
    }

    return {
        "check": "latency_partial_in_total_cost",
        "results": results,
        "issues": issues,
        "status": _pf(len(issues) == 0),
    }


# ===========================================================================
# Check 4 — Fail-closed input validation
# ===========================================================================

def check_fail_closed() -> Dict[str, Any]:
    """
    Verify that all public API methods reject invalid inputs with ValueError.
    No silent defaults accepted.
    """
    try:
        from core.unified_trade_cost import UnifiedCostModel
    except ImportError as exc:
        return {"check": "fail_closed", "status": "FAIL", "error": str(exc)}

    issues = []

    # Each test: (description, callable that should raise ValueError)
    test_cases = [
        ("invalid side 'LONG'",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="LONG", entry_price=50000, exit_price=51000,
             stop_price=49500, quantity=0.01, scenario="realistic")),
        ("side=None",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side=None, entry_price=50000, exit_price=51000,
             stop_price=49500, quantity=0.01, scenario="realistic")),
        ("unknown scenario 'HIGH'",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000, exit_price=51000,
             stop_price=49500, quantity=0.01, scenario="HIGH")),
        ("unknown scenario 'DYNAMIC'",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000, exit_price=51000,
             stop_price=49500, quantity=0.01, scenario="DYNAMIC")),
        ("negative entry_price",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=-50000, exit_price=51000,
             stop_price=49500, quantity=0.01, scenario="realistic")),
        ("zero quantity",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000, exit_price=51000,
             stop_price=49500, quantity=0.0, scenario="realistic")),
        ("stop == entry",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000, exit_price=51000,
             stop_price=50000, quantity=0.01, scenario="realistic")),
        ("bps_for_scenario with 'LOW'",
         lambda: UnifiedCostModel.bps_for_scenario("LOW")),
        ("apply_cost zero entry_price",
         lambda: UnifiedCostModel.apply_cost_to_backtest_trade(
             gross_pnl=10.0, initial_risk=5.0,
             entry_price=0.0, exit_price=50000.0, quantity=0.01, scenario="realistic")),
        ("apply_cost zero initial_risk",
         lambda: UnifiedCostModel.apply_cost_to_backtest_trade(
             gross_pnl=10.0, initial_risk=0.0,
             entry_price=50000.0, exit_price=50000.0, quantity=0.01, scenario="realistic")),
        ("apply_cost unknown scenario",
         lambda: UnifiedCostModel.apply_cost_to_backtest_trade(
             gross_pnl=10.0, initial_risk=5.0,
             entry_price=50000.0, exit_price=50000.0, quantity=0.01, scenario="KELLY")),
        # Prompt 3A: NaN/Inf rejection
        ("NaN entry_price",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=float("nan"), exit_price=51000.0,
             stop_price=49500.0, quantity=0.01, scenario="realistic")),
        ("+Inf exit_price",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000.0, exit_price=float("inf"),
             stop_price=49500.0, quantity=0.01, scenario="realistic")),
        ("-Inf quantity",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000.0, exit_price=51000.0,
             stop_price=49500.0, quantity=float("-inf"), scenario="realistic")),
        # Prompt 3A: unsupported timeframe
        ("unsupported timeframe 30m",
         lambda: UnifiedCostModel.bps_for_scenario("realistic", timeframe="30m")),
        ("unsupported timeframe 2h",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000.0, exit_price=51000.0,
             stop_price=49500.0, quantity=0.01, scenario="realistic", timeframe="2h")),
        # Prompt 3A: side/stop consistency
        ("BUY stop above entry",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000.0, exit_price=51000.0,
             stop_price=51000.0, quantity=0.01, scenario="realistic")),
        ("SELL stop below entry",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="SELL", entry_price=50000.0, exit_price=49000.0,
             stop_price=49000.0, quantity=0.01, scenario="realistic")),
        # Prompt 3A-H: atr_pct < 0 must raise ValueError
        ("atr_pct negative",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000.0, exit_price=51000.0,
             stop_price=49500.0, quantity=0.01, scenario="realistic",
             atr_pct=-0.01)),
        # Fix D: 1m, 1h, 4h explicitly rejected — no implicit fallback allowed
        ("timeframe 1m rejected",
         lambda: UnifiedCostModel.bps_for_scenario("realistic", timeframe="1m")),
        ("timeframe 1h rejected",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000.0, exit_price=51000.0,
             stop_price=49500.0, quantity=0.01, scenario="realistic", timeframe="1h")),
        ("timeframe 4h rejected",
         lambda: UnifiedCostModel.compute_trade_outcome(
             side="BUY", entry_price=50000.0, exit_price=51000.0,
             stop_price=49500.0, quantity=0.01, scenario="realistic", timeframe="4h")),
    ]

    results = {}
    for desc, fn in test_cases:
        try:
            fn()
            issues.append(f"Should have raised ValueError for: {desc}")
            results[desc] = "FAIL (no exception)"
        except ValueError:
            results[desc] = "PASS (ValueError raised)"
        except Exception as exc:
            issues.append(f"Wrong exception type for '{desc}': {type(exc).__name__}: {exc}")
            results[desc] = f"FAIL ({type(exc).__name__})"

    return {
        "check": "fail_closed",
        "test_cases": results,
        "issues": issues,
        "status": _pf(len(issues) == 0),
    }


# ===========================================================================
# Check 5 — Cost model not yet shared by runners (documentation check)
# ===========================================================================

def check_cost_model_import() -> Dict[str, Any]:
    """
    Prompt 3A: cost_model_shared gate is NOT_YET_APPLICABLE at this stage.
    The Phase 3 benchmark runner does not exist yet. Checking importability alone
    proves nothing about actual runner integration. Gate returns NOT_YET_APPLICABLE.
    Integration will be verified per-runner when Phase 3 runner is built.
    """
    try:
        from core.unified_trade_cost import UnifiedCostModel
        import_ok = True
        import_error = None
    except ImportError as exc:
        import_ok = False
        import_error = str(exc)

    issues = []
    if not import_ok:
        issues.append(f"UnifiedCostModel import failed: {import_error}")

    # Verify module is importable and basic API works
    integration_test: Dict[str, Any] = {}
    if import_ok:
        try:
            result = UnifiedCostModel.apply_cost_to_backtest_trade(
                gross_pnl=10.0, initial_risk=5.0,
                entry_price=50000.0, exit_price=50000.0, quantity=0.01,
                scenario="realistic", symbol="BTC/USDT", timeframe="15m",
            )
            integration_test["apply_cost_works"] = True
            integration_test["net_R"] = result["net_R"]
        except Exception as exc:
            issues.append(f"Module API test failed: {exc}")
            integration_test["apply_cost_works"] = False

    return {
        "check": "cost_model_shared",
        "status": "NOT_YET_APPLICABLE",
        "reason": (
            "Phase 3 benchmark runner does not exist yet. "
            "Importability check alone does not verify actual runner usage. "
            "Gate is NOT_YET_APPLICABLE until the runner is built and imports this module."
        ),
        "module_importable": import_ok,
        "import_path": "from core.unified_trade_cost import UnifiedCostModel",
        "integration_test": integration_test,
        "issues": issues,
    }


# ===========================================================================
# Check 6 — Category B test fragility (verify tests are now non-fragile)
# ===========================================================================

def check_test_suite_not_fragile() -> Dict[str, Any]:
    """
    Verify that the integrity test suite no longer contains tests that PASS
    when an anomaly exists and FAIL when it is corrected (inverted semantics).

    The previous Category B tests used 'assert md5_5m == md5_15m' which passed
    when contamination was present. They have been rewritten to use warnings.warn()
    and always pass. Verify the rewrite is in place.
    """
    test_file = PROJECT_ROOT / "trading_bot" / "tests" / "test_market_data_integrity.py"

    issues = []
    if not test_file.exists():
        return {"check": "test_fragility", "status": "FAIL", "error": "test file missing"}

    source = test_file.read_text(encoding="utf-8")

    # The old fragile pattern: assert md5_X == md5_Y (passes when files are identical)
    fragile_pattern_removed = "assert md5_5m == md5_15m" not in source and \
                              "assert md5_runs == md5_multi" not in source

    if not fragile_pattern_removed:
        issues.append(
            "Fragile Category B assertion still present: 'assert md5_X == md5_Y' "
            "passes when contamination exists, fails when corrected"
        )

    # New pattern: warnings.warn present
    has_warnings = "warnings.warn" in source
    if not has_warnings:
        issues.append("warnings.warn() not found in test file — Category B rewrite may be incomplete")

    # Verify diagnostic function names are present
    for fn_name in (
        "test_signal_density_contamination_diagnostic",
        "test_signal_density_missing_metadata_diagnostic",
        "test_timeframe_runs_contamination_diagnostic",
    ):
        if fn_name not in source:
            issues.append(f"Expected diagnostic test function not found: {fn_name}")

    return {
        "check": "test_fragility",
        "fragile_assertion_removed": fragile_pattern_removed,
        "warnings_warn_present": has_warnings,
        "issues": issues,
        "status": _pf(len(issues) == 0),
    }


# ===========================================================================
# Check 7 — Aggregation sample size
# ===========================================================================

def check_aggregation_sample_size(phase1_status: Dict) -> Dict[str, Any]:
    """
    Verify that the aggregation check in market_data_integrity_status.json
    used a sample of at least 100 bars (previously only 20).
    """
    agg = phase1_status.get("aggregation_check", {})
    sample_size = agg.get("sample_size", 0)
    status_ok = agg.get("status") == "PASS"
    mismatches = agg.get("sample_mismatches", 0)
    min_sample = 100

    issues = []
    if sample_size < min_sample:
        issues.append(
            f"Aggregation sample_size={sample_size} is too small (minimum {min_sample}). "
            "Re-run market_data_integrity_audit.py to update."
        )
    if not status_ok:
        issues.append(f"Aggregation check status={agg.get('status')!r} is not PASS")
    if mismatches > 0:
        issues.append(f"Aggregation has {mismatches} mismatches")

    return {
        "check": "aggregation_sample_size",
        "sample_size": sample_size,
        "min_required": min_sample,
        "status_from_runner": agg.get("status"),
        "mismatches": mismatches,
        "issues": issues,
        "status": _pf(len(issues) == 0),
    }


# ===========================================================================
# Check 8 — Combined test suite green
# ===========================================================================

def check_combined_suite() -> Dict[str, Any]:
    """
    Prompt 3A-H: run FULL test suite from project root via:
      python -m pytest --collect-only -q   (verify collection)
      python -m pytest -q                  (verify all green)

    Collects from all directories (not just trading_bot/tests/) to detect
    any test outside the sub-directory that was previously skipped.
    Records: command, collected count, passed count, warnings, return code.
    """
    import subprocess
    import re as _re

    issues = []

    # Step 1: dry-run collection count
    collect_result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    collect_lines = collect_result.stdout.strip().splitlines()
    collect_summary = collect_lines[-1] if collect_lines else "(no output)"
    # Parse "N tests collected"
    collected_count = 0
    m = _re.search(r"(\d+)\s+tests?\s+(?:collected|selected)", collect_summary)
    if m:
        collected_count = int(m.group(1))
    if collect_result.returncode != 0:
        issues.append(f"--collect-only failed with rc={collect_result.returncode}: {collect_summary}")

    # Step 2: full run
    run_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", "--no-header"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    passed_ok = run_result.returncode == 0
    run_lines = run_result.stdout.strip().splitlines()
    run_summary = run_lines[-1] if run_lines else "(no output)"

    # Parse "N passed" and "N warning"
    passed_count = 0
    warning_count = 0
    m_pass = _re.search(r"(\d+)\s+passed", run_summary)
    m_warn = _re.search(r"(\d+)\s+warning", run_summary)
    if m_pass:
        passed_count = int(m_pass.group(1))
    if m_warn:
        warning_count = int(m_warn.group(1))

    failures_excerpt = ""
    if not passed_ok:
        failure_lines = [ln for ln in run_lines if "FAILED" in ln or "ERROR" in ln]
        failures_excerpt = "\n".join(failure_lines[:20])
        issues.append(f"Full test suite FAILED: {run_summary}")

    return {
        "check": "combined_suite",
        "collect_command": "python -m pytest --collect-only -q",
        "run_command": "python -m pytest -q",
        "collected_count": collected_count,
        "collect_summary": collect_summary,
        "collect_returncode": collect_result.returncode,
        "passed_count": passed_count,
        "warning_count": warning_count,
        "run_summary": run_summary,
        "run_returncode": run_result.returncode,
        "all_passed": passed_ok,
        "failures_excerpt": failures_excerpt,
        "issues": issues,
        "status": _pf(passed_ok and collect_result.returncode == 0),
    }


def check_no_live_modified(
    baseline_path: "Path | None" = None,
    project_root: "Path | None" = None,
    files: "List[str] | None" = None,
) -> Dict[str, Any]:
    """Verify no runtime files were modified vs the approved ops baseline.

    Replaces the before/after manifest MD5 approach (which only detected
    in-run mutations) with a comparison against an explicit approved-baseline
    JSON written once after intentional approval.  Covers config.py,
    core/client.py, and Telegram modules via RUNTIME_BASELINE_FILES.

    baseline_path: path to the approved-baseline JSON
        (defaults to OPS_BASELINE_PATH = data/ops_approved_baseline.json).
    project_root: project root for resolving relative paths
        (defaults to PROJECT_ROOT).
    files: monitored file list override; None → RUNTIME_BASELINE_FILES.
    """
    from trading_bot.clean_bot.ops_gates import no_live_modified as _no_live_modified

    bp = baseline_path if baseline_path is not None else OPS_BASELINE_PATH
    pr = project_root if project_root is not None else PROJECT_ROOT

    result = _no_live_modified(bp, files=files, project_root=pr)
    issues = result.get("issues", [])
    ok = result.get("no_live_modified", False)
    return {
        "check": "no_live_modified",
        "baseline_path": str(bp),
        "files_checked": result.get("files_checked", 0),
        "file_results": result.get("file_results", {}),
        "issues": issues,
        "status": "PASS" if ok else "BLOCKED",
    }


# ===========================================================================
# Markdown report generator (Fix E)
# ===========================================================================

def _generate_markdown_report(output: Dict[str, Any]) -> None:
    """Write docs/phase_1_2_recertification_report.md consistent with the JSON output."""
    docs_dir = PROJECT_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    report_path = docs_dir / "phase_1_2_recertification_report.md"

    gate = output["gate_result"]
    gate_checks = output.get("gate_checks", {})
    checks = output.get("checks", {})
    suite = checks.get("combined_suite", {})
    agg = checks.get("aggregation_sample_size", {})
    fc = checks.get("fail_closed", {})

    lines: list[str] = [
        "# Phase 1-2 Recertification Report",
        "",
        f"Generated: `{output['generated_at']}`  ",
        f"Gate result: **{gate}**  ",
        f"Approved for Phase 3: **{output.get('approved_for_phase_3')}**",
        "",
        "## Constraints",
        "",
        "| Parameter | Value |",
        "| --- | --- |",
        f"| diagnostic_only | {output['diagnostic_only']} |",
        f"| opens_orders | {output['opens_orders']} |",
        f"| live_trading_allowed | {output['live_trading_allowed']} |",
        f"| paper_trading_activation_allowed | {output['paper_trading_activation_allowed']} |",
        "",
        "## Gate Checks",
        "",
        "| Gate | Result |",
        "| --- | --- |",
    ]
    for k, v in gate_checks.items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Test Suite",
        "",
        f"- Tests collected: **{suite.get('collected_count', '?')}**",
        f"- Tests passed: **{suite.get('passed_count', '?')}**",
        f"- Warnings: {suite.get('warning_count', '?')}",
        f"- Run summary: `{suite.get('run_summary', '?')}`",
        "",
        "## Aggregation Check",
        "",
        f"- Sample size (complete buckets compared): **{agg.get('sample_size', '?')}**",
        f"- Aggregation status: **{agg.get('status_from_runner', '?')}**",
        f"- Unexplained mismatches: **{agg.get('mismatches', 0)}**",
        "",
        "## Fail-Closed Validation",
        "",
        f"- Test cases: **{len(fc.get('test_cases', {}))}** cases",
        f"- All passed: **{fc.get('status') == 'PASS'}**",
        "",
    ]

    if output.get("gate_issues"):
        lines += ["## Issues", ""]
        for iss in output["gate_issues"]:
            lines.append(f"- {iss}")
        lines.append("")

    lines += [
        "## Risk Policy (Phase 3+)",
        "",
        f"- risk_per_trade_pct: **{output.get('risk_policy_phase_3_plus', {}).get('risk_per_trade_pct')}** (0.5% of equity)",
        f"- Benchmark sizing: fixed 0.005 per trade across all configurations",
        "",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown report: {report_path}")


# ===========================================================================
# Main
# ===========================================================================

def main() -> int:
    print("=" * 70)
    print("  PHASE 2H — Hotfix e Certificazione Fasi 1-2")
    print("  Diagnostic only. No orders. No live trading. No paper activation.")
    print("=" * 70)

    # Load existing artifacts
    if not PHASE1_STATUS_PATH.exists():
        print(f"FATAL: {PHASE1_STATUS_PATH} not found. Run Phase 1 audit first.")
        return 1
    if not PHASE2_STATUS_PATH.exists():
        print(f"FATAL: {PHASE2_STATUS_PATH} not found. Run Phase 2 validation first.")
        return 1

    phase1_status = _load_json(PHASE1_STATUS_PATH)
    phase2_status = _load_json(PHASE2_STATUS_PATH)

    input_hashes = {
        "market_data_integrity_status.json": _md5_file(PHASE1_STATUS_PATH),
        "cost_model_validation.json": _md5_file(PHASE2_STATUS_PATH),
    }

    print(f"\n  Phase 1 gate_result     : {phase1_status.get('gate_result')}")
    print(f"  Phase 2 gate_result     : {phase2_status.get('gate_result')}")
    print(f"  Input hash Phase1 status: {input_hashes['market_data_integrity_status.json']}")

    checks: Dict[str, Any] = {}
    all_issues: List[str] = []

    # 1. Gate architecture
    print("\n[1/8] Checking 3-tier gate architecture ...")
    c1 = check_gate_bypass(phase1_status)
    checks["gate_architecture"] = c1
    print(f"  raw_data_gate              : {c1['raw_data_gate']}")
    print(f"  derived_artifact_gate      : {c1['derived_artifact_gate']}")
    print(f"  benchmark_readiness_gate   : {c1['benchmark_readiness_gate']}")
    print(f"  Status                     : {c1['status']}")
    all_issues.extend(c1["issues"])

    # 2. Cost model parity
    print("\n[2/8] Checking cost model API parity (flat trade) ...")
    c2 = check_cost_model_parity()
    print(f"  Status                     : {c2['status']}")
    if c2.get("issues"):
        for iss in c2["issues"]:
            print(f"    ISSUE: {iss}")
    checks["cost_parity"] = c2
    all_issues.extend(c2.get("issues", []))

    # 3. Latency + partial fill in total_cost_amt
    print("\n[3/8] Checking latency + partial_fill included in total_cost_amt ...")
    c3 = check_latency_partial_in_total_cost()
    sev = c3.get("results", {}).get("severe", {})
    print(f"  severe latency_amt         : {sev.get('latency_amt')}")
    print(f"  severe partial_fill_amt    : {sev.get('partial_fill_amt')}")
    print(f"  6-component sum matches    : {sev.get('all_components_included')}")
    print(f"  Status                     : {c3['status']}")
    all_issues.extend(c3.get("issues", []))
    checks["latency_partial_inclusion"] = c3

    # 4. Fail-closed validation
    print("\n[4/8] Checking fail-closed input validation ...")
    c4 = check_fail_closed()
    passed_cases = sum(1 for v in c4["test_cases"].values() if "PASS" in v)
    total_cases = len(c4["test_cases"])
    print(f"  Test cases passed          : {passed_cases}/{total_cases}")
    print(f"  Status                     : {c4['status']}")
    if c4.get("issues"):
        for iss in c4["issues"]:
            print(f"    ISSUE: {iss}")
    checks["fail_closed"] = c4
    all_issues.extend(c4.get("issues", []))

    # 5. Cost model shared — NOT_YET_APPLICABLE
    print("\n[5/8] Cost model shared gate (Prompt 3A) ...")
    c5 = check_cost_model_import()
    print(f"  Gate status                : {c5['status']}")
    print(f"  Reason                     : Phase 3 runner not yet built")
    # cost_model_import stored in checks later (after no_live_modified)
    all_issues.extend(c5.get("issues", []))

    # 6. Category B test fragility
    print("\n[6/8] Checking Category B test fragility removed ...")
    c6 = check_test_suite_not_fragile()
    print(f"  Fragile assertion removed  : {c6['fragile_assertion_removed']}")
    print(f"  warnings.warn present      : {c6['warnings_warn_present']}")
    print(f"  Status                     : {c6['status']}")
    checks["test_fragility"] = c6
    all_issues.extend(c6.get("issues", []))

    # 7. Aggregation sample size
    print("\n[7/8] Checking aggregation sample size ...")
    c7 = check_aggregation_sample_size(phase1_status)
    print(f"  Sample size                : {c7['sample_size']} (min {c7['min_required']})")
    print(f"  Aggregation status         : {c7['status_from_runner']}")
    print(f"  Status                     : {c7['status']}")
    checks["aggregation_sample_size"] = c7
    all_issues.extend(c7.get("issues", []))

    # 8. Combined suite — full project root (python -m pytest -q)
    print("\n[8/8] Running full test suite (project root: python -m pytest -q) ...")
    c8 = check_combined_suite()
    print(f"  Collected                  : {c8.get('collected_count')} tests")
    print(f"  Run summary                : {c8.get('run_summary')}")
    print(f"  Passed                     : {c8.get('passed_count')}  Warnings: {c8.get('warning_count')}")
    print(f"  Status                     : {c8['status']}")
    if c8.get("failures_excerpt"):
        print(f"  Failures:\n{c8['failures_excerpt']}")
    checks["combined_suite"] = c8
    all_issues.extend(c8.get("issues", []))

    # ---------------------------------------------------------------------------
    # Evaluate gates (Prompt 3A updates)
    # ---------------------------------------------------------------------------
    cost_model_parity_gate = c2["status"]
    invalid_input_rejection_gate = c4["status"]
    raw_data_gate = c1.get("raw_data_gate", "MISSING")
    benchmark_readiness_gate = c1.get("benchmark_readiness_gate", "MISSING")
    suite_green = c8["status"]
    no_gate_bypassed = c1["status"]

    # Baseline comparison (replaces before/after manifest MD5 approach)
    print("\n[no_live_modified] Checking runtime files vs approved baseline ...")
    c_nlm = check_no_live_modified()
    checks["no_live_modified"] = c_nlm
    print(f"  Files checked              : {c_nlm.get('files_checked')}")
    print(f"  Baseline                   : {c_nlm.get('baseline_path')}")
    print(f"  Status                     : {c_nlm['status']}")
    no_live_modified = c_nlm["status"]
    all_issues.extend(c_nlm.get("issues", []))

    # Prompt 3A: cost_model_shared is NOT_YET_APPLICABLE (not counted as PASS or FAIL)
    cost_model_shared_gate = c5.get("status")  # "NOT_YET_APPLICABLE"
    checks["cost_model_import"] = c5

    gate_checks = {
        "cost_model_parity": cost_model_parity_gate,
        "invalid_input_rejection": invalid_input_rejection_gate,
        "raw_data_gate": raw_data_gate,
        "benchmark_readiness_gate": benchmark_readiness_gate,
        "suite_green": suite_green,
        "no_gate_bypassed": no_gate_bypassed,
        "no_live_modified": no_live_modified,
        "cost_model_shared": cost_model_shared_gate,  # NOT_YET_APPLICABLE — excluded from gate
    }

    # All mandatory sub-gates must be PASS (NOT_YET_APPLICABLE excluded)
    mandatory_gates = {k: v for k, v in gate_checks.items() if k != "cost_model_shared"}
    all_gate_pass = all(v == "PASS" for v in mandatory_gates.values())
    gate_result = "PASS" if all_gate_pass else "BLOCKED"

    # Risk policy for Phase 3+ (Prompt 3A: 0.005 = 0.5%, NOT 0.5 = 50%)
    risk_policy_phase_3_plus = {
        "risk_per_trade_pct": 0.005,
        "risk_per_trade_label": "0.5% of equity per trade",
        "sizing_profiles_excluded_from_benchmark": ["LOW", "MEDIUM", "HIGH", "DYNAMIC", "Kelly"],
        "dynamic_risk_status": (
            "EXCLUDED from benchmark. May be evaluated later as reduce-only ablation "
            "after OOS edge demonstration."
        ),
        "benchmark_sizing": "fixed 0.005 (0.5% equity) per trade, identical across all configurations",
    }

    # ---------------------------------------------------------------------------
    # Compose output
    # ---------------------------------------------------------------------------
    output: Dict[str, Any] = {
        "report_type": "phase_1_2_recertification",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": DIAGNOSTIC_ONLY,
        "opens_orders": OPENS_ORDERS,
        "live_trading_allowed": LIVE_TRADING_ALLOWED,
        "paper_trading_activation_allowed": PAPER_TRADING_ACTIVATION_ALLOWED,
        "input_hashes": input_hashes,
        "phase1_inherited_gate": phase1_status.get("gate_result"),
        "phase2_inherited_gate": phase2_status.get("gate_result"),
        "checks": checks,
        "gate_checks": gate_checks,
        "gate_result": gate_result,
        "gate_issues": all_issues,
        "risk_policy_phase_3_plus": risk_policy_phase_3_plus,
        "approved_for_phase_3": gate_result == "PASS",
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    _generate_markdown_report(output)

    print("\n" + "=" * 70)
    print("  PHASE 2H RECERTIFICATION SUMMARY")
    print("=" * 70)
    for gate_name, gate_val in gate_checks.items():
        print(f"  {gate_name:<30} : {gate_val}")
    print(f"\n  GATE RESULT: {gate_result}")
    if all_issues:
        print(f"  Issues ({len(all_issues)}):")
        for iss in all_issues:
            print(f"    - {iss}")
    else:
        print("  All checks passed.")
    print(f"\n  Output: {OUTPUT_PATH}")
    print("=" * 70)

    return 0 if gate_result == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
