from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.paper_unlock_shadow_rate_calibration as psrc
from core.paper_unlock_shadow_rate_calibration import (
    PaperUnlockShadowRateCalibrationSettings,
    build_paper_unlock_shadow_rate_calibration_report,
)


def _row(i: int, r: float, outcome: str = "TP1_ONLY", **overrides):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i * 6)
    side = "BUY" if i % 2 == 0 else "SELL"
    row = {
        "symbol": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"][i % 4],
        "bucket": "BUY_BUY_REJECTION_CANDIDATE" if side == "BUY" else "SELL_SELL_REJECTION_CANDIDATE",
        "side": side,
        "structure_bias": "BULLISH" if side == "BUY" else "BEARISH",
        "price_location": "LOWER_RANGE" if side == "BUY" else "UPPER_RANGE",
        "confirmation_summary": "BULLISH_BOS" if side == "BUY" else "BEARISH_BOS",
        "confirmation_close": True,
        "bos_bullish": side == "BUY",
        "bos_bearish": side == "SELL",
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


def _write_experiment_ready(tmp: Path) -> None:
    payload = {
        "status": "PASS",
        "decision": {
            "status": "PAPER_EXPERIMENT_DESIGN_READY_DIAGNOSTIC",
            "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
            "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
        },
        "paper_orders_enabled": False,
        "paper_unlock_experiment_allowed": False,
        "operational_unlock_allowed": False,
    }
    (tmp / "paper_unlock_experiment_design_report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_rate_calibration_expands_sample_without_orders() -> None:
    rows = []
    for i in range(30):
        if i in {7, 18, 25}:
            rows.append(_row(i, -1.0, "SL"))
        elif i in {12, 23}:
            rows.append(_row(i, 2.0, "TP2"))
        else:
            rows.append(_row(i, 0.55, "TP1_ONLY"))
    original = psrc._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        _write_experiment_ready(tmp)
        try:
            psrc._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(rows),
                "candidate_rows_pre_structure": len(rows),
            }
            report = build_paper_unlock_shadow_rate_calibration_report(
                tmp,
                PaperUnlockShadowRateCalibrationSettings(min_shadow_entries=20, min_shadow_expectancy_r=0.05),
            )
        finally:
            psrc._collect_historical_rows = original
    assert report["report_type"] == "paper_only_shadow_rate_limit_calibration"
    assert report["decision"]["status"] == "SHADOW_RATE_CALIBRATION_READY_DIAGNOSTIC"
    assert report["counts"]["best_selected_entries"] >= 20
    assert report["operational_unlock_allowed"] is False
    assert report["paper_unlock_experiment_allowed"] is False
    assert report["paper_orders_enabled"] is False
    assert report["counts"]["orders_submitted"] == 0
    assert report["counts"]["positions_opened"] == 0


def test_missing_experiment_design_blocks_rate_calibration() -> None:
    rows = [_row(i, 1.0) for i in range(30)]
    original = psrc._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            psrc._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(rows),
                "candidate_rows_pre_structure": len(rows),
            }
            report = build_paper_unlock_shadow_rate_calibration_report(tmp, PaperUnlockShadowRateCalibrationSettings())
        finally:
            psrc._collect_historical_rows = original
    assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
    assert report["experiment_design_guard"]["experiment_design_ready"] is False
    assert report["paper_orders_enabled"] is False


def test_all_shadow_ceiling_alone_is_not_deployable() -> None:
    # All rows occur on the same day. Only the unbounded ceiling can pass sample,
    # so the report must remain diagnostic and not recommend activation.
    rows = [_row(i, 0.8, datetime=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()) for i in range(22)]
    original = psrc._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        _write_experiment_ready(tmp)
        try:
            psrc._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(rows),
                "candidate_rows_pre_structure": len(rows),
            }
            report = build_paper_unlock_shadow_rate_calibration_report(tmp, PaperUnlockShadowRateCalibrationSettings(min_shadow_entries=20))
        finally:
            psrc._collect_historical_rows = original
    assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
    assert "all-shadow" in report["decision"]["reason"] or "unbounded" in report["decision"]["reason"]
    assert report["paper_orders_enabled"] is False


def main() -> None:
    test_rate_calibration_expands_sample_without_orders()
    test_missing_experiment_design_blocks_rate_calibration()
    test_all_shadow_ceiling_alone_is_not_deployable()
    print("Paper unlock shadow rate calibration tests passed.")


if __name__ == "__main__":
    main()
