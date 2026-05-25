from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.independent_repaired_validation as irv
from core.independent_repaired_validation import (
    IndependentRepairedValidationSettings,
    build_independent_repaired_validation_report,
)
from core.structure_context_repair import repair_structure_rows


def _row(i: int, r: float, outcome: str = "TP1_ONLY", **overrides):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    row = {
        "symbol": ["BTC/USDT", "ETH/USDT", "SOL/USDT"][i % 3],
        "bucket": "BUY_BUY_REJECTION_CANDIDATE",
        "side": "BUY" if i % 2 == 0 else "SELL",
        "structure_bias": "BULLISH" if i % 2 == 0 else "BEARISH",
        "price_location": "LOWER_RANGE" if i % 2 == 0 else "UPPER_RANGE",
        "confirmation_summary": "BULLISH_BOS" if i % 2 == 0 else "BEARISH_BOS",
        "confirmation_close": True,
        "bos_bullish": i % 2 == 0,
        "bos_bearish": i % 2 == 1,
        "structure_context_ok": True,
        "structure_confirmed": True,
        "range_filter_ok": True,
        "has_conflicting_patterns": False,
        "pattern_score": 60.0,
        "map_score": 65.0 + float(i % 3) * 5.0,
        "range_pos_400": 0.5,
        "r": r,
        "outcome": outcome,
        "datetime": ts.isoformat(),
    }
    row.update(overrides)
    return row


def test_stability_candidate_remains_non_operational() -> None:
    source_rows = []
    for i in range(60):
        if i % 5 == 0:
            source_rows.append(_row(i, -1.0, "SL"))
        elif i % 7 == 0:
            source_rows.append(_row(i, 2.0, "TP2"))
        else:
            source_rows.append(_row(i, 1.0, "TP1_ONLY"))
    rows = repair_structure_rows(source_rows)
    original = irv._collect_historical_rows
    try:
        irv._collect_historical_rows = lambda data_dir, settings: {
            "status": "PASS",
            "candidate_rows": rows,
            "warnings": [],
            "by_asset": {},
            "scenario_pattern_evaluation_rows": len(rows),
            "candidate_rows_pre_structure": len(rows),
        }
        report = build_independent_repaired_validation_report(
            "data",
            IndependentRepairedValidationSettings(
                min_variant_candidates=50,
                min_fold_candidates=10,
                min_holdout_candidates=12,
                max_asset_concentration_pct=80.0,
                max_side_concentration_pct=80.0,
            ),
        )
    finally:
        irv._collect_historical_rows = original
    assert report["report_type"] == "independent_repaired_validation_stability_guard"
    assert report["decision"]["status"] == "STABILITY_CANDIDATE_DIAGNOSTIC"
    assert report["operational_unlock_allowed"] is False
    assert report["paper_unlock_refinement_allowed"] is False
    assert report["walk_forward"]["stability_checks"]["passes_walk_forward_guard"] is True


def test_weak_holdout_blocks_candidate() -> None:
    source_rows = []
    for i in range(60):
        if i >= 45:
            source_rows.append(_row(i, -1.0, "SL"))
        else:
            source_rows.append(_row(i, 1.0, "TP1_ONLY"))
    rows = repair_structure_rows(source_rows)
    original = irv._collect_historical_rows
    try:
        irv._collect_historical_rows = lambda data_dir, settings: {
            "status": "PASS",
            "candidate_rows": rows,
            "warnings": [],
            "by_asset": {},
            "scenario_pattern_evaluation_rows": len(rows),
            "candidate_rows_pre_structure": len(rows),
        }
        report = build_independent_repaired_validation_report(
            "data",
            IndependentRepairedValidationSettings(
                min_variant_candidates=50,
                min_fold_candidates=10,
                min_holdout_candidates=12,
                max_asset_concentration_pct=80.0,
                max_side_concentration_pct=80.0,
            ),
        )
    finally:
        irv._collect_historical_rows = original
    assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
    assert report["walk_forward"]["stability_checks"]["holdout_ok"] is False
    assert report["operational_unlock_allowed"] is False


def test_no_rows_fallback_is_safe() -> None:
    original = irv._collect_historical_rows
    original_fallback = irv._fallback_from_existing_reports
    try:
        irv._collect_historical_rows = lambda data_dir, settings: {
            "status": "PASS",
            "candidate_rows": [],
            "warnings": ["synthetic_empty"],
            "by_asset": {},
            "scenario_pattern_evaluation_rows": 0,
            "candidate_rows_pre_structure": 0,
        }
        irv._fallback_from_existing_reports = lambda base: {"available": True, "repaired_structure_shadow_validation_report.json": {"status": "PASS"}}
        report = build_independent_repaired_validation_report("data", IndependentRepairedValidationSettings())
    finally:
        irv._collect_historical_rows = original
        irv._fallback_from_existing_reports = original_fallback
    assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"]["fallback_summary_only"] is True
    assert report["operational_unlock_allowed"] is False


def main() -> None:
    test_stability_candidate_remains_non_operational()
    test_weak_holdout_blocks_candidate()
    test_no_rows_fallback_is_safe()
    print("Independent repaired validation tests passed.")


if __name__ == "__main__":
    main()
