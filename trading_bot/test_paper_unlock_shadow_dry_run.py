from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.paper_unlock_shadow_dry_run as psd
from core.paper_unlock_shadow_dry_run import (
    PaperUnlockShadowDryRunSettings,
    build_paper_unlock_shadow_dry_run_report,
)


def _row(i: int, r: float, outcome: str = "TP1_ONLY", **overrides):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i // 2, hours=i)
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


def test_shadow_dry_run_ready_remains_execution_disabled() -> None:
    rows = []
    for i in range(72):
        if i % 9 == 0:
            rows.append(_row(i, -1.0, "SL"))
        elif i % 17 == 0:
            rows.append(_row(i, 2.0, "TP2"))
        else:
            rows.append(_row(i, 0.65, "TP1_ONLY"))
    original = psd._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        _write_experiment_ready(tmp)
        try:
            psd._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(rows),
                "candidate_rows_pre_structure": len(rows),
            }
            report = build_paper_unlock_shadow_dry_run_report(
                tmp,
                PaperUnlockShadowDryRunSettings(min_shadow_entries=20, dry_run_max_daily_entries=2, dry_run_max_weekly_entries=20),
            )
        finally:
            psd._collect_historical_rows = original
    assert report["report_type"] == "paper_only_shadow_experiment_dry_run_harness"
    assert report["decision"]["status"] == "SHADOW_DRY_RUN_READY_DIAGNOSTIC"
    assert report["shadow_dry_run_gate"]["passes_shadow_dry_run_gate"] is True
    assert report["operational_unlock_allowed"] is False
    assert report["paper_unlock_experiment_allowed"] is False
    assert report["paper_orders_enabled"] is False
    assert report["counts"]["orders_submitted"] == 0
    assert report["counts"]["positions_opened"] == 0


def test_missing_experiment_design_blocks_harness() -> None:
    rows = [_row(i, 1.0) for i in range(60)]
    original = psd._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            psd._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(rows),
                "candidate_rows_pre_structure": len(rows),
            }
            report = build_paper_unlock_shadow_dry_run_report(tmp, PaperUnlockShadowDryRunSettings())
        finally:
            psd._collect_historical_rows = original
    assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
    assert report["experiment_design_guard"]["experiment_design_ready"] is False
    assert report["paper_orders_enabled"] is False


def test_rate_limits_are_simulated_without_orders() -> None:
    rows = [_row(i, 1.0, datetime=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()) for i in range(10)]
    original = psd._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        _write_experiment_ready(tmp)
        try:
            psd._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(rows),
                "candidate_rows_pre_structure": len(rows),
            }
            report = build_paper_unlock_shadow_dry_run_report(
                tmp,
                PaperUnlockShadowDryRunSettings(min_shadow_entries=1, dry_run_max_daily_entries=1, dry_run_max_weekly_entries=10),
            )
        finally:
            psd._collect_historical_rows = original
    assert report["counts"]["shadow_selected_entries"] == 1
    assert report["counts"]["rate_limited_rejections"] == 9
    assert report["rate_limit_summary"]["rejection_counts"]["DAILY_LIMIT"] == 9
    assert report["counts"]["orders_submitted"] == 0


def main() -> None:
    test_shadow_dry_run_ready_remains_execution_disabled()
    test_missing_experiment_design_blocks_harness()
    test_rate_limits_are_simulated_without_orders()
    print("Paper unlock shadow dry-run tests passed.")


if __name__ == "__main__":
    main()
