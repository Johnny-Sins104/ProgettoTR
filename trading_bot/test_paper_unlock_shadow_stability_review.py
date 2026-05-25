from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.paper_unlock_shadow_stability_review as psr
from core.paper_unlock_shadow_stability_review import (
    PaperUnlockShadowStabilityReviewSettings,
    build_paper_unlock_shadow_stability_review_report,
    write_paper_unlock_shadow_stability_review_report,
)


def _row(i: int, *, symbol: str = "BTC/USDT", side: str = "BUY", r: float = 1.0, outcome: str = "TP1_ONLY") -> dict:
    day = 1 + (i // 4)
    hour = (i % 4) * 4
    return {
        "datetime": f"2026-04-{day:02d} {hour:02d}:00:00+00:00",
        "symbol": symbol,
        "side": side,
        "bucket": "BUY_BUY_REJECTION_CANDIDATE" if side == "BUY" else "SELL_SELL_REJECTION_CANDIDATE",
        "r": r,
        "outcome": outcome,
        "map_score": 65.0 + (i % 3) * 5.0,
        "structure_state": "CONFIRMATION" if i % 2 else "CONTEXT",
        "confirmation_summary": "BULLISH_BOS" if side == "BUY" else "BEARISH_BOS",
        "repaired_structure_context_ok": True,
        "repaired_structure_confirmed": i % 2 == 1,
        "price_location": ["LOWER_RANGE", "MID_RANGE", "UPPER_RANGE", "LOW_RANGE_NEAR_DEMAND"][i % 4],
    }


def _rows(n: int = 24) -> list[dict]:
    rows = []
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    sides = ["BUY", "SELL"]
    for i in range(n):
        r = -1.0 if i in {5, 13, 21} else (0.35 if i % 7 == 0 else 1.0)
        outcome = "SL" if r < 0 else ("TIME_EXIT" if r < 1 else "TP1_ONLY")
        rows.append(_row(i, symbol=symbols[i % len(symbols)], side=sides[i % 2], r=r, outcome=outcome))
    return rows


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="shadow_stability_review_test_"))


def _experiment_guard_file(tmp: Path) -> None:
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
        "operational_unlock_allowed": False,
    }
    (tmp / "paper_unlock_experiment_design_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _bounded_guard_file(tmp: Path, rows: list[dict] | None = None, *, ready: bool = True) -> None:
    rows = rows or _rows(24)
    payload = {
        "status": "PASS" if ready else "WARN",
        "decision": {
            "status": "ROLLING_SHADOW_COLLECTION_CANDIDATE_DIAGNOSTIC" if ready else "KEEP_DIAGNOSTIC",
            "best_bounded_cadence_variant": {
                "name": "bounded_6_daily_30_weekly_0h",
                "selected_entries": len(rows),
                "rolling_collection_candidate": ready,
            },
            "paper_orders_enabled": False,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
        },
        "counts": {"source_target_rows": len(rows), "entry_candidate_rows": len(rows), "best_selected_entries": len(rows)},
        "bounded_cadence_variants": [
            {
                "name": "bounded_6_daily_30_weekly_0h",
                "selected_entries": len(rows),
                "rolling_collection_candidate": ready,
                "selected_tail": rows,
                "summary": {"expectancy_r": 0.3, "loss_rate_pct": 30.0},
            }
        ],
        "paper_orders_enabled": False,
        "paper_unlock_experiment_allowed": False,
        "operational_unlock_allowed": False,
    }
    (tmp / "paper_unlock_bounded_cadence_report.json").write_text(json.dumps(payload), encoding="utf-8")


class _Patch:
    def __init__(self, name: str, value):
        self.name = name
        self.value = value
        self.old = getattr(psr, name)

    def __enter__(self):
        setattr(psr, self.name, self.value)

    def __exit__(self, exc_type, exc, tb):
        setattr(psr, self.name, self.old)


def test_shadow_stability_candidate_with_synthetic_rows() -> None:
    tmp = _tmpdir()
    try:
        _experiment_guard_file(tmp)
        _bounded_guard_file(tmp, _rows(24), ready=True)
        with _Patch("_collect_historical_rows", lambda base, settings: {
            "status": "PASS",
            "scenario_pattern_evaluation_rows": 90,
            "candidate_rows_pre_structure": 60,
            "candidate_rows": _rows(24),
            "by_asset": {},
        }), _Patch("repair_structure_rows", lambda rows: list(rows)):
            report = build_paper_unlock_shadow_stability_review_report(
                tmp,
                PaperUnlockShadowStabilityReviewSettings(
                    min_shadow_entries=20,
                    min_distinct_days=3,
                    max_single_day_concentration_pct=45.0,
                    max_shadow_loss_rate_pct=60.0,
                ),
            )
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC"
        assert report["decision"]["operational_unlock_allowed"] is False
        assert report["paper_orders_enabled"] is False
        checks = report["stability_checks"]
        assert checks["sample_ok"] is True
        assert checks["rolling_window_ok"] is True
        assert checks["holdout_ok"] is True
        assert checks["concentration_ok"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_keep_diagnostic_when_bounded_guard_missing() -> None:
    tmp = _tmpdir()
    try:
        _experiment_guard_file(tmp)
        _bounded_guard_file(tmp, _rows(24), ready=False)
        with _Patch("_collect_historical_rows", lambda base, settings: {"status": "PASS", "candidate_rows": _rows(24), "by_asset": {}}), _Patch("repair_structure_rows", lambda rows: list(rows)):
            report = build_paper_unlock_shadow_stability_review_report(tmp, PaperUnlockShadowStabilityReviewSettings(min_shadow_entries=20))
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["paper_unlock_experiment_allowed"] is False
        assert report["operational_unlock_allowed"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report_uses_fallback_tail_without_parquet() -> None:
    tmp = _tmpdir()
    try:
        rows = _rows(21)
        _experiment_guard_file(tmp)
        _bounded_guard_file(tmp, rows, ready=True)
        with _Patch("_collect_historical_rows", lambda base, settings: {"status": "WARN", "candidate_rows": [], "by_asset": {}}), _Patch("repair_structure_rows", lambda rows: []):
            report = write_paper_unlock_shadow_stability_review_report(tmp, PaperUnlockShadowStabilityReviewSettings(min_shadow_entries=20, max_shadow_loss_rate_pct=60.0))
        path = tmp / psr.REPORT_NAME
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4h"
        assert saved["fallback"]["available"] is True
        assert report["opens_orders"] is False
        assert report["counts"]["orders_submitted"] == 0
        assert report["counts"]["positions_opened"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_shadow_stability_candidate_with_synthetic_rows()
    test_keep_diagnostic_when_bounded_guard_missing()
    test_write_report_uses_fallback_tail_without_parquet()
    print("Paper unlock shadow stability review tests passed.")


if __name__ == "__main__":
    main()
