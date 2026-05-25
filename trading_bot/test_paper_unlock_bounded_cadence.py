from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.paper_unlock_bounded_cadence as pbc
from core.paper_unlock_bounded_cadence import (
    PaperUnlockBoundedCadenceSettings,
    build_paper_unlock_bounded_cadence_report,
    write_paper_unlock_bounded_cadence_report,
)


def _row(i: int, *, symbol: str = "BTC/USDT", side: str = "BUY", r: float = 1.0, outcome: str = "TP1_ONLY") -> dict:
    day = 1 + (i // 5)
    hour = (i % 5) * 3
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
    }


def _rows(n: int = 30) -> list[dict]:
    rows = []
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    sides = ["BUY", "SELL"]
    for i in range(n):
        r = -1.0 if i in {4, 13, 22} else (0.35 if i % 7 == 0 else 1.0)
        outcome = "SL" if r < 0 else ("TIME_EXIT" if r < 1 else "TP1_ONLY")
        rows.append(_row(i, symbol=symbols[i % len(symbols)], side=sides[i % 2], r=r, outcome=outcome))
    return rows


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


def _rate_guard_file(tmp: Path) -> None:
    payload = {
        "status": "WARN",
        "decision": {"status": "KEEP_DIAGNOSTIC", "best_rate_variant": {"name": "all_shadow_ceiling_99_daily_99_weekly"}},
        "counts": {"entry_candidate_rows": 30, "best_selected_entries": 30},
        "paper_orders_enabled": False,
        "operational_unlock_allowed": False,
    }
    (tmp / "paper_unlock_shadow_rate_calibration_report.json").write_text(json.dumps(payload), encoding="utf-8")


class _Patch:
    def __init__(self, name: str, value):
        self.name = name
        self.value = value
        self.old = getattr(pbc, name)

    def __enter__(self):
        setattr(pbc, self.name, self.value)

    def __exit__(self, exc_type, exc, tb):
        setattr(pbc, self.name, self.old)


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="bounded_cadence_test_"))


def test_bounded_cadence_candidate_with_synthetic_rows() -> None:
    tmp = _tmpdir()
    try:
        _experiment_guard_file(tmp)
        _rate_guard_file(tmp)
        synthetic = _rows(30)
        with _Patch("_collect_historical_rows", lambda base, settings: {
            "status": "PASS",
            "scenario_pattern_evaluation_rows": 90,
            "candidate_rows_pre_structure": 60,
            "candidate_rows": synthetic,
            "by_asset": {},
        }), _Patch("repair_structure_rows", lambda rows: list(rows)):
            report = build_paper_unlock_bounded_cadence_report(
                tmp,
                PaperUnlockBoundedCadenceSettings(
                    min_shadow_entries=20,
                    min_positive_window_rate_pct=66.67,
                    min_holdout_entries=5,
                    max_shadow_loss_rate_pct=60.0,
                ),
            )
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "ROLLING_SHADOW_COLLECTION_CANDIDATE_DIAGNOSTIC"
        assert report["decision"]["operational_unlock_allowed"] is False
        assert report["paper_orders_enabled"] is False
        best = report["decision"]["best_bounded_cadence_variant"]
        assert best["selected_entries"] >= 20
        assert best["rolling_collection_candidate"] is True
        assert best["dry_run_gate"]["passes_shadow_dry_run_gate"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_activation_when_experiment_guard_missing() -> None:
    tmp = _tmpdir()
    try:
        _rate_guard_file(tmp)
        with _Patch("_collect_historical_rows", lambda base, settings: {
            "status": "PASS",
            "candidate_rows": _rows(30),
            "by_asset": {},
        }), _Patch("repair_structure_rows", lambda rows: list(rows)):
            report = build_paper_unlock_bounded_cadence_report(tmp, PaperUnlockBoundedCadenceSettings(min_shadow_entries=20))
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["paper_unlock_experiment_allowed"] is False
        assert report["operational_unlock_allowed"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report() -> None:
    tmp = _tmpdir()
    try:
        _experiment_guard_file(tmp)
        _rate_guard_file(tmp)
        with _Patch("_collect_historical_rows", lambda base, settings: {"status": "PASS", "candidate_rows": _rows(24), "by_asset": {}}), _Patch("repair_structure_rows", lambda rows: list(rows)):
            report = write_paper_unlock_bounded_cadence_report(tmp, PaperUnlockBoundedCadenceSettings(min_shadow_entries=20, max_shadow_loss_rate_pct=60.0))
        path = tmp / pbc.REPORT_NAME
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4g"
        assert report["opens_orders"] is False
        assert report["counts"]["orders_submitted"] == 0
        assert report["counts"]["positions_opened"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_bounded_cadence_candidate_with_synthetic_rows()
    test_no_activation_when_experiment_guard_missing()
    test_write_report()
    print("Paper unlock bounded cadence tests passed.")


if __name__ == "__main__":
    main()
