from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paper_unlock_experiment_switch_draft import (
    PaperUnlockExperimentSwitchDraftSettings,
    build_paper_unlock_experiment_switch_draft_report,
    write_paper_unlock_experiment_switch_draft_report,
)


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="switch_draft_test_"))


def _activation_report(
    tmp: Path,
    *,
    ready: bool = True,
    selected_entries: int = 21,
    paper_orders_enabled: bool = False,
    auto_activation: bool = False,
    confirmation_only: bool = True,
) -> None:
    decision_status = "GUARDED_PAPER_ACTIVATION_DRAFT_READY_DIAGNOSTIC" if ready else "KEEP_DIAGNOSTIC"
    allowed_states = ["CONFIRMATION"] if confirmation_only else ["CONTEXT", "CONFIRMATION"]
    policy = "CONFIRMATION_ONLY" if confirmation_only else "CONTEXT_OR_CONFIRMATION"
    payload = {
        "status": "PASS" if ready else "WARN",
        "draft_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ACTIVATION_DRAFT",
        "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
        "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": paper_orders_enabled,
        "profile_activation_allowed": False,
        "automatic_activation_allowed": auto_activation,
        "manual_activation_required": True,
        "counts": {
            "source_target_rows": 51,
            "entry_candidate_rows": 23,
            "selected_entries": selected_entries,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "stability_prerequisite": {
            "passes_stability_prerequisite": ready,
            "selected_entries": selected_entries,
            "best_stability_review_variant": "bounded_6_daily_30_weekly_0h",
        },
        "activation_interlocks": {
            "manual_activation_required": True,
            "automatic_activation_allowed": auto_activation,
            "paper_orders_enabled_in_this_patch": False,
            "operational_unlock_allowed_in_this_patch": False,
            "testnet_allowed": False,
            "live_allowed": False,
            "profile_activation_allowed": False,
            "future_manual_switch_requirements": {
                "separate_patch_required": True,
                "two_step_confirmation_required": True,
                "required_profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
                "required_experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
                "required_mode": "paper",
                "must_keep_live_and_testnet_blocked": True,
                "must_keep_exchange_broker_blocked": True,
                "must_recheck_latest_stability_report": True,
                "must_abort_if_any_prerequisite_missing": True,
            },
            "proposed_runtime_limits": {
                "max_positions": 1,
                "risk_per_trade_pct": 0.0025,
                "max_daily_entries": 6,
                "max_weekly_entries": 30,
                "map_score_min": 65.0,
                "map_score_max": 79.999,
                "entry_state_policy": policy,
                "allowed_structure_states": allowed_states,
                "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
            },
        },
        "activation_draft": {
            "entry_state_policy": policy,
            "runtime_limits": {
                "max_positions": 1,
                "risk_per_trade_pct": 0.0025,
                "max_daily_entries": 6,
                "max_weekly_entries": 30,
                "entry_state_policy": policy,
                "allowed_structure_states": allowed_states,
                "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
            },
        },
        "decision": {
            "status": decision_status,
            "draft_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ACTIVATION_DRAFT",
            "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
            "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
            "best_stability_review_variant": "bounded_6_daily_30_weekly_0h",
            "selected_entries": selected_entries,
            "interlocks_ready": ready,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": paper_orders_enabled,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": auto_activation,
        },
    }
    (tmp / "paper_unlock_activation_draft_report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_switch_draft_ready_but_execution_disabled() -> None:
    tmp = _tmpdir()
    try:
        _activation_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_experiment_switch_draft_report(tmp, PaperUnlockExperimentSwitchDraftSettings(required_selected_entries=20))
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "GUARDED_PAPER_SWITCH_IMPLEMENTATION_DRAFT_READY_DIAGNOSTIC"
        assert report["activation_draft_guard"]["passes_activation_draft_guard"] is True
        assert report["decision"]["switch_implementation_ready"] is True
        assert report["paper_orders_enabled"] is False
        assert report["paper_unlock_experiment_allowed"] is False
        assert report["operational_unlock_allowed"] is False
        assert report["automatic_activation_allowed"] is False
        assert report["manual_activation_allowed"] is False
        assert report["switch_contract"]["activation_in_this_patch_allowed"] is False
        assert report["switch_contract"]["runtime_profile"]["entry_state_policy"] == "CONFIRMATION_ONLY"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_keep_diagnostic_when_activation_draft_missing() -> None:
    tmp = _tmpdir()
    try:
        report = build_paper_unlock_experiment_switch_draft_report(tmp, PaperUnlockExperimentSwitchDraftSettings(required_selected_entries=20))
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["activation_draft_guard"]["passes_activation_draft_guard"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_activation_draft_enabled_paper_orders() -> None:
    tmp = _tmpdir()
    try:
        _activation_report(tmp, ready=True, selected_entries=21, paper_orders_enabled=True)
        report = build_paper_unlock_experiment_switch_draft_report(tmp, PaperUnlockExperimentSwitchDraftSettings(required_selected_entries=20))
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["activation_draft_guard"]["execution_disabled_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_confirmation_only_required_for_switch_draft() -> None:
    tmp = _tmpdir()
    try:
        _activation_report(tmp, ready=True, selected_entries=21, confirmation_only=False)
        report = build_paper_unlock_experiment_switch_draft_report(tmp, PaperUnlockExperimentSwitchDraftSettings(required_selected_entries=20, require_confirmation_only=True))
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["activation_draft_guard"]["confirmation_only_ok"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report_persists_file() -> None:
    tmp = _tmpdir()
    try:
        _activation_report(tmp, ready=True, selected_entries=21)
        report = write_paper_unlock_experiment_switch_draft_report(tmp, PaperUnlockExperimentSwitchDraftSettings(required_selected_entries=20))
        path = tmp / "paper_unlock_experiment_switch_draft_report.json"
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4j"
        assert saved["opens_orders"] is False
        assert saved["counts"]["orders_submitted"] == 0
        assert report["decision"]["switch_implementation_ready"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_switch_draft_ready_but_execution_disabled()
    test_keep_diagnostic_when_activation_draft_missing()
    test_fail_closed_if_activation_draft_enabled_paper_orders()
    test_confirmation_only_required_for_switch_draft()
    test_write_report_persists_file()
    print("Paper unlock experiment switch draft tests passed.")


if __name__ == "__main__":
    main()
