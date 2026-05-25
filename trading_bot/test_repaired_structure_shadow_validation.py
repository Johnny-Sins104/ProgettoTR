from __future__ import annotations

import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.repaired_structure_shadow_validation as rsv
from core.repaired_structure_shadow_validation import (
    RepairedStructureShadowValidationSettings,
    build_repaired_structure_shadow_validation_report,
)
from core.structure_context_repair import repair_structure_rows


def _base_row(**overrides):
    row = {
        "symbol": "BTC/USDT",
        "bucket": "BUY_BUY_REJECTION_CANDIDATE",
        "side": "BUY",
        "structure_bias": "BULLISH",
        "price_location": "LOWER_RANGE",
        "confirmation_summary": "BULLISH_BOS",
        "confirmation_close": True,
        "bos_bullish": True,
        "structure_context_ok": True,
        "structure_confirmed": True,
        "range_filter_ok": True,
        "has_conflicting_patterns": False,
        "pattern_score": 70.0,
        "map_score": 65.0,
        "range_pos_400": 0.25,
        "r": 1.0,
        "outcome": "TP1_ONLY",
    }
    row.update(overrides)
    return row


def test_validation_report_with_monkeypatched_rows() -> None:
    rows = repair_structure_rows([
        _base_row(r=1.0, outcome="TP1_ONLY"),
        _base_row(r=2.0, outcome="TP2", map_score=75.0),
        _base_row(r=-1.0, outcome="SL", map_score=80.0),
        _base_row(confirmation_summary="PRICE_IN_DEMAND_WAIT_CONFIRMATION", confirmation_close=False, bos_bullish=False, map_score=45.0, r=0.2, outcome="TIME_EXIT"),
        _base_row(confirmation_summary="NO_STRUCTURAL_CONFIRMATION", confirmation_close=False, bos_bullish=False, structure_bias="RANGING", map_score=30.0, r=0.5, outcome="TIME_EXIT"),
        _base_row(price_location="IN_SUPPLY_ZONE", in_supply_zone=True, confirmation_summary="PRICE_IN_SUPPLY_WAIT_CONFIRMATION", confirmation_close=False, bos_bullish=False, map_score=60.0, r=-1.0, outcome="SL"),
    ])

    original = rsv._collect_historical_rows
    try:
        rsv._collect_historical_rows = lambda data_dir, settings: {
            "status": "PASS",
            "candidate_rows": rows,
            "warnings": [],
            "by_asset": {},
            "scenario_pattern_evaluation_rows": len(rows),
            "candidate_rows_pre_structure": len(rows),
        }
        report = build_repaired_structure_shadow_validation_report(
            "data",
            RepairedStructureShadowValidationSettings(min_variant_candidates=2, min_component_candidates=1),
        )
    finally:
        rsv._collect_historical_rows = original

    assert report["report_type"] == "repaired_structure_shadow_validation_component_audit"
    assert report["operational_unlock_allowed"] is False
    assert report["counts"]["structured_candidate_rows"] == len(rows)
    assert "hypothesis_matrix" in report
    assert report["hypothesis_matrix"]["map_score_65_79_count"] >= 2
    assert report["hypothesis_matrix"]["directional_bos_count"] >= 2
    assert "validation_variants" in report
    assert any(v["name"] == "map_score_65_79_repaired_entry_state" for v in report["validation_variants"])
    wait_variant = next(v for v in report["validation_variants"] if v["name"] == "wait_states_watchlist_only")
    assert wait_variant["entry_candidate"] is False
    assert wait_variant["gate_checks"]["entry_candidate_allowed"] is False


def test_no_rows_fallback_is_safe() -> None:
    original = rsv._collect_historical_rows
    original_fallback = rsv._fallback_from_existing_reports
    try:
        rsv._collect_historical_rows = lambda data_dir, settings: {
            "status": "PASS",
            "candidate_rows": [],
            "warnings": ["synthetic_empty"],
            "by_asset": {},
            "scenario_pattern_evaluation_rows": 0,
            "candidate_rows_pre_structure": 0,
        }
        rsv._fallback_from_existing_reports = lambda base: {"available": True, "structure_context_repair": {"status": "WARN"}}
        report = build_repaired_structure_shadow_validation_report("data", RepairedStructureShadowValidationSettings())
    finally:
        rsv._collect_historical_rows = original
        rsv._fallback_from_existing_reports = original_fallback

    assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
    assert report["decision"]["fallback_summary_only"] is True
    assert report["operational_unlock_allowed"] is False


def main() -> None:
    test_validation_report_with_monkeypatched_rows()
    test_no_rows_fallback_is_safe()
    print("Repaired structure shadow validation tests passed.")


if __name__ == "__main__":
    main()
