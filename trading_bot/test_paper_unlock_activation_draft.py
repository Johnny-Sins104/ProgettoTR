from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paper_unlock_activation_draft import (
    PaperUnlockActivationDraftSettings,
    build_paper_unlock_activation_draft_report,
    write_paper_unlock_activation_draft_report,
)


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="activation_draft_test_"))


def _stability_report(tmp: Path, *, ready: bool = True, selected_entries: int = 21, confirmation_only: bool = True) -> None:
    decision_status = "SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC" if ready else "KEEP_DIAGNOSTIC"
    state_counts = {"CONFIRMATION": selected_entries} if confirmation_only else {"CONFIRMATION": selected_entries - 1, "CONTEXT": 1}
    payload = {
        "status": "PASS" if ready else "WARN",
        "review_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_SAMPLE_STABILITY_REVIEW",
        "decision": {
            "status": decision_status,
            "best_stability_review_variant": "bounded_6_daily_30_weekly_0h",
            "selected_entries": selected_entries,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
        },
        "counts": {
            "source_target_rows": 51,
            "entry_candidate_rows": 23,
            "selected_entries": selected_entries,
            "rejected_entries": 2,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "stability_checks": {
            "sample_ok": ready,
            "rolling_window_ok": ready,
            "holdout_ok": ready,
            "concentration_ok": ready,
            "temporal_dispersion_ok": ready,
            "equity_guard_ok": ready,
            "dry_run_gate": {"passes_shadow_dry_run_gate": ready},
            "equity_dry_run": {
                "entries": selected_entries,
                "cumulative_r": 3.2,
                "max_consecutive_losses": 2,
                "max_drawdown_pct": 0.65,
                "would_abort_on_consecutive_losses": False,
                "would_abort_on_drawdown": False,
            },
            "concentration": {"passes_concentration_guard": ready, "distinct_assets": 4, "distinct_sides": 2},
            "holdout": {"holdout_ok": ready, "entries": 5},
            "temporal_dispersion": {"temporal_dispersion_ok": ready, "distinct_days": 7},
            "window_stability": {"positive_window_rate_pct": 100.0, "passing_window_rate_pct": 66.6667},
            "state_breakdown": {"state_counts": state_counts},
        },
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
    }
    (tmp / "paper_unlock_shadow_stability_review_report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_activation_draft_ready_but_execution_disabled() -> None:
    tmp = _tmpdir()
    try:
        _stability_report(tmp, ready=True, selected_entries=21, confirmation_only=True)
        report = build_paper_unlock_activation_draft_report(tmp, PaperUnlockActivationDraftSettings(required_selected_entries=20))
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "GUARDED_PAPER_ACTIVATION_DRAFT_READY_DIAGNOSTIC"
        assert report["stability_prerequisite"]["passes_stability_prerequisite"] is True
        assert report["decision"]["interlocks_ready"] is True
        assert report["paper_orders_enabled"] is False
        assert report["paper_unlock_experiment_allowed"] is False
        assert report["operational_unlock_allowed"] is False
        assert report["profile_activation_allowed"] is False
        assert report["activation_interlocks"]["automatic_activation_allowed"] is False
        assert report["activation_draft"]["runtime_limits"]["entry_state_policy"] == "CONFIRMATION_ONLY"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_keep_diagnostic_when_stability_review_missing() -> None:
    tmp = _tmpdir()
    try:
        report = build_paper_unlock_activation_draft_report(tmp, PaperUnlockActivationDraftSettings(required_selected_entries=20))
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["stability_prerequisite"]["passes_stability_prerequisite"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_confirmation_only_guard_blocks_context_for_first_activation() -> None:
    tmp = _tmpdir()
    try:
        _stability_report(tmp, ready=True, selected_entries=21, confirmation_only=False)
        report = build_paper_unlock_activation_draft_report(tmp, PaperUnlockActivationDraftSettings(required_selected_entries=20, require_confirmation_only_first_activation=True))
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["stability_prerequisite"]["confirmation_only_ok"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report_persists_file() -> None:
    tmp = _tmpdir()
    try:
        _stability_report(tmp, ready=True, selected_entries=21, confirmation_only=True)
        report = write_paper_unlock_activation_draft_report(tmp, PaperUnlockActivationDraftSettings(required_selected_entries=20))
        path = tmp / "paper_unlock_activation_draft_report.json"
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4i"
        assert saved["opens_orders"] is False
        assert report["counts"]["orders_submitted"] == 0
        assert report["counts"]["positions_opened"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_activation_draft_ready_but_execution_disabled()
    test_keep_diagnostic_when_stability_review_missing()
    test_confirmation_only_guard_blocks_context_for_first_activation()
    test_write_report_persists_file()
    print("Paper unlock activation draft tests passed.")


if __name__ == "__main__":
    main()
