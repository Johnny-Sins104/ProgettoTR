from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.structure_filter_diagnostics import (
    StructureFilterDiagnosticsSettings,
    _build_audit_variants,
    _directional_conflict,
    _hard_confirmation_directional,
    _strict_directional_context,
    build_structure_filter_diagnostics_report,
    write_structure_filter_diagnostics_report,
)


def _row(i: int, side: str = "BUY", r: float = 1.0, loc: str = "IN_DEMAND_ZONE", bias: str = "BULLISH", confirmed: bool = False) -> dict:
    return {
        "symbol": "BTC/USDT",
        "idx": i,
        "datetime": str(i),
        "side": side,
        "bucket": "BUY_BUY_REJECTION_CANDIDATE" if side == "BUY" else "SELL_SELL_REJECTION_CANDIDATE",
        "pattern_score": 70.0,
        "has_conflicting_patterns": False,
        "range_filter_ok": True,
        "range_pos_400": 0.18 if side == "BUY" else 0.82,
        "r": r,
        "outcome": "TP1_ONLY" if r > 0 and r < 2 else "TP2" if r >= 2 else "SL" if r <= -1 else "TIME_EXIT",
        "structure_bias": bias,
        "price_location": loc,
        "liquidity_below_lows": side == "BUY",
        "liquidity_above_highs": side == "SELL",
        "nearest_liquidity": {"side": "BELOW" if side == "BUY" else "ABOVE", "distance_pct": 0.2},
        "in_demand_zone": "DEMAND" in loc,
        "in_supply_zone": "SUPPLY" in loc,
        "bos_bullish": confirmed and side == "BUY",
        "bos_bearish": confirmed and side == "SELL",
        "choch_bullish": False,
        "choch_bearish": False,
        "mss_bullish": False,
        "mss_bearish": False,
        "breakout_retest_confirmed": False,
        "breakdown_retest_confirmed": False,
        "confirmation_close": confirmed,
        "confirmation_summary": "BULLISH_BOS" if confirmed and side == "BUY" else "BEARISH_BOS" if confirmed else "PRICE_IN_DEMAND_WAIT_CONFIRMATION" if side == "BUY" else "PRICE_IN_SUPPLY_WAIT_CONFIRMATION",
        "map_score": 70.0 if confirmed else 45.0,
        "structure_context_ok": True,
        "structure_confirmed": confirmed,
    }


def test_strict_context_blocks_directional_conflicts() -> None:
    bad_buy = _row(1, side="BUY", loc="IN_SUPPLY_ZONE", bias="BEARISH", r=-1.0)
    good_buy = _row(2, side="BUY", loc="IN_DEMAND_ZONE", bias="BULLISH", r=1.0)
    assert _directional_conflict(bad_buy) == "BUY_IN_SUPPLY_OR_UPPER_SUPPLY"
    assert not _strict_directional_context(bad_buy)
    assert _strict_directional_context(good_buy)


def test_hard_confirmation_requires_directional_break() -> None:
    good = _row(1, side="BUY", confirmed=True)
    weak = _row(2, side="BUY", confirmed=False)
    assert _hard_confirmation_directional(good)
    assert not _hard_confirmation_directional(weak)


def test_audit_variants_remain_diagnostic() -> None:
    rows = [_row(i, r=1.0, confirmed=True) for i in range(55)] + [_row(100 + i, r=-1.0, confirmed=True) for i in range(5)]
    settings = StructureFilterDiagnosticsSettings(min_variant_candidates=50, min_expectancy_r=0.10, min_win_rate_pct=52.0, max_loss_rate_pct=45.0)
    variants = _build_audit_variants(rows, settings)
    names = {v["name"]: v for v in variants}
    assert names["hard_confirmation_directional"]["gate_checks"]["passes_candidate_gate"] is True
    assert names["btc_focus_clean_hard_confirmation"]["candidates"] == 60


def test_report_fallback_without_parquet() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        (data / "calibrated_structure_shadow_report.json").write_text(json.dumps({
            "status": "WARN",
            "decision": {"status": "KEEP_DIAGNOSTIC"},
            "counts": {"structured_candidate_rows": 880},
        }), encoding="utf-8")
        (data / "market_structure_map_report.json").write_text(json.dumps({
            "status": "PASS",
            "decision": {"status": "STRUCTURE_MAP_READY_DIAGNOSTIC"},
        }), encoding="utf-8")
        settings = StructureFilterDiagnosticsSettings(historical_enabled=True)
        report = build_structure_filter_diagnostics_report(data, settings)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["operational_unlock_allowed"] is False
        written = write_structure_filter_diagnostics_report(data, settings)
        assert (data / "structure_filter_diagnostics_report.json").exists()
        assert written["opens_orders"] is False


if __name__ == "__main__":
    test_strict_context_blocks_directional_conflicts()
    test_hard_confirmation_requires_directional_break()
    test_audit_variants_remain_diagnostic()
    test_report_fallback_without_parquet()
    print("Structure filter diagnostics tests passed.")
