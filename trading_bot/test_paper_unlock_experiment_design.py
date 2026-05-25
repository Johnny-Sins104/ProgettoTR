from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.paper_unlock_experiment_design as ped
from core.paper_unlock_experiment_design import (
    PaperUnlockExperimentDesignSettings,
    build_paper_unlock_experiment_design_report,
)


def _row(i: int, r: float, outcome: str = "TP1_ONLY", **overrides):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
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


def _write_profile_ready(tmp: Path) -> None:
    payload = {
        "status": "PASS",
        "decision": {
            "status": "PROFILE_REFINEMENT_DESIGN_READY_DIAGNOSTIC",
            "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "best_profile_design_variant": {
                "name": "source_map_score_65_79_all",
                "candidates": 60,
                "expectancy_r": 0.2,
                "win_rate_pct": 60.0,
                "loss_rate_pct": 40.0,
                "time_exit_rate_pct": 25.0,
                "passes_profile_design_gate": True,
            },
        },
        "source_validation": {
            "independent_report_status": "PASS",
            "independent_decision_status": "STABILITY_CANDIDATE_DIAGNOSTIC",
            "independent_guard_ok": True,
        },
        "counts": {"target_candidate_rows": 60},
    }
    (tmp / "paper_unlock_profile_refinement_report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_experiment_design_ready_remains_execution_disabled() -> None:
    source_rows = []
    for i in range(60):
        if i % 6 == 0:
            source_rows.append(_row(i, -1.0, "SL"))
        elif i % 11 == 0:
            source_rows.append(_row(i, 2.0, "TP2"))
        else:
            source_rows.append(_row(i, 1.0, "TP1_ONLY"))
    original = ped._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        _write_profile_ready(tmp)
        try:
            ped._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": source_rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(source_rows),
                "candidate_rows_pre_structure": len(source_rows),
            }
            report = build_paper_unlock_experiment_design_report(
                tmp,
                PaperUnlockExperimentDesignSettings(min_variant_candidates=50),
            )
        finally:
            ped._collect_historical_rows = original
    assert report["report_type"] == "calibrated_paper_only_unlock_experiment_design"
    assert report["decision"]["status"] == "PAPER_EXPERIMENT_DESIGN_READY_DIAGNOSTIC"
    assert report["experiment_plan"]["experiment_status"] == "DESIGN_ONLY_NOT_ENABLED"
    assert report["operational_unlock_allowed"] is False
    assert report["paper_unlock_experiment_allowed"] is False
    assert report["paper_orders_enabled"] is False
    assert report["counts"]["orders_submitted"] == 0
    assert report["counts"]["positions_opened"] == 0


def test_missing_profile_guard_blocks_experiment_design() -> None:
    rows = [_row(i, 1.0, "TP1_ONLY") for i in range(60)]
    original = ped._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        try:
            ped._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": rows,
                "warnings": [],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": len(rows),
                "candidate_rows_pre_structure": len(rows),
            }
            report = build_paper_unlock_experiment_design_report(tmp, PaperUnlockExperimentDesignSettings())
        finally:
            ped._collect_historical_rows = original
    assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
    assert report["profile_guard"]["profile_design_ready"] is False
    assert report["paper_unlock_experiment_allowed"] is False


def test_profile_fallback_can_draft_design_without_rows() -> None:
    original = ped._collect_historical_rows
    with TemporaryDirectory() as td:
        tmp = Path(td)
        _write_profile_ready(tmp)
        try:
            ped._collect_historical_rows = lambda data_dir, settings: {
                "status": "PASS",
                "candidate_rows": [],
                "warnings": ["synthetic_empty"],
                "by_asset": {},
                "scenario_pattern_evaluation_rows": 0,
                "candidate_rows_pre_structure": 0,
            }
            report = build_paper_unlock_experiment_design_report(tmp, PaperUnlockExperimentDesignSettings())
        finally:
            ped._collect_historical_rows = original
    assert report["decision"]["status"] == "PAPER_EXPERIMENT_DESIGN_READY_DIAGNOSTIC"
    assert report["fallback"]["available"] is True
    assert report["paper_orders_enabled"] is False


def main() -> None:
    test_experiment_design_ready_remains_execution_disabled()
    test_missing_profile_guard_blocks_experiment_design()
    test_profile_fallback_can_draft_design_without_rows()
    print("Paper unlock experiment design tests passed.")


if __name__ == "__main__":
    main()
