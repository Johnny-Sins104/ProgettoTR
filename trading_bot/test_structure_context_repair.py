from __future__ import annotations

import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.structure_context_repair as scr
from core.structure_context_repair import (
    STATE_CONFIRMATION,
    STATE_CONFLICT,
    STATE_CONTEXT,
    STATE_WAIT,
    StructureContextRepairSettings,
    classify_structure_state,
    repair_structure_rows,
    build_structure_context_repair_report,
)


def test_wait_is_not_confirmation() -> None:
    row = {
        "side": "BUY",
        "structure_bias": "BULLISH",
        "price_location": "IN_DEMAND_ZONE",
        "confirmation_summary": "PRICE_IN_DEMAND_WAIT_CONFIRMATION",
        "confirmation_close": False,
        "in_demand_zone": True,
        "structure_context_ok": True,
        "structure_confirmed": False,
    }
    out = classify_structure_state(row)
    assert out["structure_state"] == STATE_WAIT
    assert out["repaired_wait_state"] is True
    assert out["repaired_structure_context_ok"] is False
    assert out["repaired_structure_confirmed"] is False
    assert out["wait_not_entry_confirmation"] is True


def test_directional_confirmation() -> None:
    row = {
        "side": "BUY",
        "structure_bias": "BULLISH",
        "price_location": "LOWER_RANGE",
        "confirmation_summary": "BULLISH_BOS",
        "confirmation_close": True,
        "bos_bullish": True,
        "structure_context_ok": True,
        "structure_confirmed": True,
    }
    out = classify_structure_state(row)
    assert out["structure_state"] == STATE_CONFIRMATION
    assert out["repaired_structure_context_ok"] is True
    assert out["repaired_structure_confirmed"] is True


def test_buy_in_supply_without_bullish_confirmation_is_conflict() -> None:
    row = {
        "side": "BUY",
        "structure_bias": "BULLISH",
        "price_location": "IN_SUPPLY_ZONE",
        "confirmation_summary": "PRICE_IN_SUPPLY_WAIT_CONFIRMATION",
        "confirmation_close": False,
        "in_supply_zone": True,
        "structure_context_ok": True,
        "structure_confirmed": False,
    }
    out = classify_structure_state(row)
    assert out["structure_state"] == STATE_CONFLICT
    assert out["repaired_conflict"] is True
    assert out["repaired_structure_context_ok"] is False
    assert "BUY_IN_SUPPLY_WITHOUT_BULLISH_CONFIRMATION" in out["structure_repair_reasons"]


def test_context_without_wait_or_conflict() -> None:
    row = {
        "side": "SELL",
        "structure_bias": "BEARISH",
        "price_location": "UPPER_RANGE",
        "confirmation_summary": "BEARISH_CONTEXT",
        "confirmation_close": False,
        "structure_context_ok": True,
        "structure_confirmed": False,
    }
    out = classify_structure_state(row)
    assert out["structure_state"] == STATE_CONTEXT
    assert out["repaired_structure_context_ok"] is True
    assert out["repaired_structure_confirmed"] is False


def test_build_report_with_monkeypatched_rows() -> None:
    rows = repair_structure_rows([
        {"symbol": "BTC/USDT", "bucket": "BUY_BUY_REJECTION_CANDIDATE", "side": "BUY", "structure_bias": "BULLISH", "price_location": "LOWER_RANGE", "confirmation_summary": "BULLISH_BOS", "confirmation_close": True, "bos_bullish": True, "structure_context_ok": True, "structure_confirmed": True, "range_filter_ok": True, "has_conflicting_patterns": False, "pattern_score": 70.0, "r": 1.0, "outcome": "TP1_ONLY"},
        {"symbol": "BTC/USDT", "bucket": "BUY_BUY_REJECTION_CANDIDATE", "side": "BUY", "structure_bias": "BULLISH", "price_location": "IN_DEMAND_ZONE", "confirmation_summary": "PRICE_IN_DEMAND_WAIT_CONFIRMATION", "confirmation_close": False, "in_demand_zone": True, "structure_context_ok": True, "structure_confirmed": False, "range_filter_ok": True, "has_conflicting_patterns": False, "pattern_score": 65.0, "r": -0.1, "outcome": "TIME_EXIT"},
        {"symbol": "ETH/USDT", "bucket": "SELL_SELL_REJECTION_CANDIDATE", "side": "SELL", "structure_bias": "BULLISH", "price_location": "IN_DEMAND_ZONE", "confirmation_summary": "PRICE_IN_DEMAND_WAIT_CONFIRMATION", "confirmation_close": False, "in_demand_zone": True, "structure_context_ok": True, "structure_confirmed": False, "range_filter_ok": False, "has_conflicting_patterns": False, "pattern_score": 60.0, "r": -1.0, "outcome": "SL"},
    ])

    original = scr._collect_historical_rows
    try:
        scr._collect_historical_rows = lambda data_dir, settings: {
            "status": "PASS",
            "candidate_rows": rows,
            "warnings": [],
            "by_asset": {},
            "scenario_pattern_evaluation_rows": 3,
            "candidate_rows_pre_structure": 3,
        }
        report = build_structure_context_repair_report("data", StructureContextRepairSettings(min_variant_candidates=1))
    finally:
        scr._collect_historical_rows = original

    assert report["report_type"] == "strict_structure_context_repair_confirmation_relabeling"
    assert report["operational_unlock_allowed"] is False
    assert report["counts"]["structured_candidate_rows"] == 3
    assert report["transition_matrix"]["state_counts"][STATE_CONFIRMATION] >= 1
    assert report["transition_matrix"]["state_counts"][STATE_WAIT] >= 1
    assert report["transition_matrix"]["state_counts"][STATE_CONFLICT] >= 1


def main() -> None:
    test_wait_is_not_confirmation()
    test_directional_confirmation()
    test_buy_in_supply_without_bullish_confirmation_is_conflict()
    test_context_without_wait_or_conflict()
    test_build_report_with_monkeypatched_rows()
    print("Structure context repair tests passed.")


if __name__ == "__main__":
    main()
