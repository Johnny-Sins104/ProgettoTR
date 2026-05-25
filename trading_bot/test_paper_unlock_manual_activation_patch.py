from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paper_unlock_manual_activation_patch import (
    DEFAULT_ACTIVATION_CONFIRM_VALUE,
    DEFAULT_CONFIRM_VALUE,
    PaperUnlockManualActivationPatchSettings,
    build_paper_unlock_manual_activation_patch_report,
    write_paper_unlock_manual_activation_patch_report,
)


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="manual_activation_patch_test_"))


def _preflight_report(
    tmp: Path,
    *,
    ready: bool = True,
    selected_entries: int = 21,
    paper_orders_enabled: bool = False,
    manual_allowed: bool = False,
) -> None:
    decision_status = "MANUAL_PAPER_SWITCH_PREFLIGHT_READY_DIAGNOSTIC" if ready else "KEEP_DIAGNOSTIC"
    payload = {
        "status": "PASS" if ready else "WARN",
        "preflight_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT",
        "switch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT",
        "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
        "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": paper_orders_enabled,
        "profile_activation_allowed": False,
        "automatic_activation_allowed": False,
        "manual_activation_allowed": manual_allowed,
        "switch_draft_guard": {
            "passes_switch_draft_guard": ready,
            "best_stability_review_variant": "bounded_6_daily_30_weekly_0h",
            "selected_entries": selected_entries,
        },
        "preflight_suite": {
            "passes_preflight_suite": ready,
            "negative_fail_closed_ok": ready,
            "future_patch_simulation_ok": ready,
            "all_scenarios_no_orders_ok": True,
        },
        "counts": {
            "source_target_rows": 51,
            "entry_candidate_rows": 23,
            "selected_entries": selected_entries,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "decision": {
            "status": decision_status,
            "preflight_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT",
            "switch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT",
            "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
            "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
            "selected_entries": selected_entries,
            "switch_draft_ready": ready,
            "fail_closed_preflight_ok": ready,
            "future_patch_simulation_ok": ready,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": paper_orders_enabled,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": False,
            "manual_activation_allowed": manual_allowed,
        },
    }
    (tmp / "paper_unlock_manual_switch_preflight_report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_manual_activation_patch_draft_ready_but_execution_disabled() -> None:
    tmp = _tmpdir()
    try:
        _preflight_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_manual_activation_patch_report(tmp, PaperUnlockManualActivationPatchSettings(required_selected_entries=20), env={})
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT_READY_DIAGNOSTIC"
        assert report["preflight_guard"]["passes_preflight_guard"] is True
        assert report["activation_preflight_suite"]["negative_fail_closed_ok"] is True
        assert report["activation_preflight_suite"]["future_activation_simulation_ok"] is True
        assert report["paper_orders_enabled"] is False
        assert report["manual_activation_allowed"] is False
        assert report["operational_unlock_allowed"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_actual_env_can_be_valid_but_this_draft_still_blocks_orders() -> None:
    tmp = _tmpdir()
    try:
        _preflight_report(tmp, ready=True, selected_entries=21)
        env = {
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE": "1",
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM": DEFAULT_CONFIRM_VALUE,
            "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH": "1",
            "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM": DEFAULT_ACTIVATION_CONFIRM_VALUE,
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE": "paper",
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER": "blocked",
        }
        report = build_paper_unlock_manual_activation_patch_report(tmp, env=env)
        actual = report["activation_preflight_suite"]["actual_environment"]
        assert actual["two_step_ok"] is True
        assert actual["activation_patch_ok"] is True
        assert actual["activation_confirm_ok"] is True
        assert actual["activation_patch_present"] is False
        assert actual["activation_contract_ok"] is False
        assert actual["activation_allowed_in_this_patch"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_when_preflight_missing() -> None:
    tmp = _tmpdir()
    try:
        report = build_paper_unlock_manual_activation_patch_report(tmp)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["preflight_guard"]["passes_preflight_guard"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_preflight_report_had_paper_orders_enabled() -> None:
    tmp = _tmpdir()
    try:
        _preflight_report(tmp, ready=True, selected_entries=21, paper_orders_enabled=True)
        report = build_paper_unlock_manual_activation_patch_report(tmp)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["preflight_guard"]["execution_disabled_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_sample_too_small() -> None:
    tmp = _tmpdir()
    try:
        _preflight_report(tmp, ready=True, selected_entries=7)
        report = build_paper_unlock_manual_activation_patch_report(tmp, PaperUnlockManualActivationPatchSettings(required_selected_entries=20))
        assert report["status"] == "WARN"
        assert report["preflight_guard"]["selected_entries_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report_persists_file() -> None:
    tmp = _tmpdir()
    try:
        _preflight_report(tmp, ready=True, selected_entries=21)
        report = write_paper_unlock_manual_activation_patch_report(tmp)
        path = tmp / "paper_unlock_manual_activation_patch_report.json"
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4l"
        assert saved["opens_orders"] is False
        assert saved["counts"]["orders_submitted"] == 0
        assert report["decision"]["activation_preflight_ok"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_manual_activation_patch_draft_ready_but_execution_disabled()
    test_actual_env_can_be_valid_but_this_draft_still_blocks_orders()
    test_fail_closed_when_preflight_missing()
    test_fail_closed_if_preflight_report_had_paper_orders_enabled()
    test_fail_closed_if_sample_too_small()
    test_write_report_persists_file()
    print("Paper unlock manual activation patch tests passed.")


if __name__ == "__main__":
    main()
