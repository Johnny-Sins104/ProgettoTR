from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.calibrated_structure_shadow import (
    CalibratedStructureShadowSettings,
    _build_variants,
    _structure_confirmed,
    _structure_context_ok,
    build_calibrated_structure_shadow_report,
    write_calibrated_structure_shadow_report,
)


def _row(i: int, r: float, confirmed: bool = False) -> dict:
    return {
        "symbol": "BTC/USDT",
        "idx": i,
        "datetime": str(i),
        "side": "BUY",
        "bucket": "BUY_BUY_REJECTION_CANDIDATE",
        "pattern_score": 70.0,
        "has_conflicting_patterns": False,
        "range_filter_ok": True,
        "range_pos_400": 0.18,
        "r": r,
        "outcome": "TP1_ONLY" if r > 0 and r < 2 else "TP2" if r >= 2 else "SL" if r <= -1 else "TIME_EXIT",
        "structure_bias": "BULLISH",
        "price_location": "LOW_RANGE_NEAR_DEMAND",
        "liquidity_below_lows": True,
        "liquidity_above_highs": False,
        "in_demand_zone": True,
        "in_supply_zone": False,
        "bos_bullish": confirmed,
        "bos_bearish": False,
        "choch_bullish": False,
        "choch_bearish": False,
        "mss_bullish": False,
        "mss_bearish": False,
        "breakout_retest_confirmed": False,
        "breakdown_retest_confirmed": False,
        "confirmation_close": confirmed,
        "confirmation_summary": "BULLISH_BOS" if confirmed else "PRICE_IN_DEMAND_WAIT_CONFIRMATION",
        "map_score": 70.0 if confirmed else 45.0,
        "structure_context_ok": True,
        "structure_confirmed": confirmed,
    }


def test_structure_context_and_confirmation() -> None:
    buy_ctx = {
        "structure_bias": "BULLISH",
        "price_location": "LOW_RANGE_NEAR_DEMAND",
        "liquidity_below_lows": True,
        "nearest_liquidity": {"side": "BELOW", "distance_pct": 0.2},
        "confirmation_close": True,
        "bos_bullish": True,
    }
    assert _structure_context_ok("BUY", buy_ctx)
    assert _structure_confirmed("BUY", buy_ctx)
    assert not _structure_context_ok("SELL", buy_ctx)


def test_variant_gate_is_non_operational_candidate_only() -> None:
    rows = [_row(i, 1.0, confirmed=True) for i in range(55)] + [_row(100 + i, -1.0, confirmed=True) for i in range(5)]
    settings = CalibratedStructureShadowSettings(min_variant_candidates=50, min_structure_expectancy_r=0.10, min_structure_win_rate_pct=52.0, max_structure_loss_rate_pct=45.0)
    variants = _build_variants(rows, settings)
    names = {v["name"]: v for v in variants}
    assert names["btc_focus_score_70_structure_confirmed"]["passes_candidate_gate"] is True
    assert names["btc_focus_score_70_structure_confirmed"]["candidates"] == 60


def test_report_fallback_without_parquet() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        (data / "scenario_pattern_calibration_report.json").write_text(json.dumps({
            "status": "WARN",
            "counts": {"historical_candidates": 5713},
            "decision": {"status": "KEEP_DIAGNOSTIC", "candidate_profile": {"name": "BTC_BUY_REJECTION_PATTERN_CONFIRMED"}},
        }), encoding="utf-8")
        (data / "market_structure_map_report.json").write_text(json.dumps({
            "status": "PASS",
            "counts": {"historical_snapshots_evaluated": 364},
            "decision": {"status": "STRUCTURE_MAP_READY_DIAGNOSTIC", "focus_latest": {"structure_bias": "BULLISH"}},
        }), encoding="utf-8")
        settings = CalibratedStructureShadowSettings(symbols=("BTC/USDT",), historical_enabled=True)
        report = build_calibrated_structure_shadow_report(data, settings)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["operational_unlock_allowed"] is False
        written = write_calibrated_structure_shadow_report(data, settings)
        assert (data / "calibrated_structure_shadow_report.json").exists()
        assert written["opens_orders"] is False


if __name__ == "__main__":
    test_structure_context_and_confirmation()
    test_variant_gate_is_non_operational_candidate_only()
    test_report_fallback_without_parquet()
    print("Calibrated structure shadow tests passed.")
