from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paper_unlock_final_enable_preflight import (
    DEFAULT_ACTIVATION_CONFIRM_VALUE,
    DEFAULT_FINAL_CONFIRM_VALUE,
    DEFAULT_SWITCH_CONFIRM_VALUE,
    PaperUnlockFinalEnablePreflightSettings,
    build_paper_unlock_final_enable_preflight_report,
    write_paper_unlock_final_enable_preflight_report,
)


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="final_enable_preflight_test_"))


def _activation_patch_report(
    tmp: Path,
    *,
    ready: bool = True,
    selected_entries: int = 21,
    paper_orders_enabled: bool = False,
    manual_allowed: bool = False,
) -> None:
    decision_status = "EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT_READY_DIAGNOSTIC" if ready else "KEEP_DIAGNOSTIC"
    payload = {
        "status": "PASS" if ready else "WARN",
        "activation_patch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT",
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
        "preflight_guard": {
            "passes_preflight_guard": ready,
            "required_cadence_variant": "bounded_6_daily_30_weekly_0h",
            "selected_entries": selected_entries,
        },
        "activation_preflight_suite": {
            "passes_activation_preflight_suite": ready,
            "negative_fail_closed_ok": ready,
            "future_activation_simulation_ok": ready,
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
            "activation_patch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT",
            "preflight_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT",
            "switch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT",
            "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
            "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
            "selected_entries": selected_entries,
            "preflight_guard_ok": ready,
            "activation_preflight_ok": ready,
            "negative_fail_closed_ok": ready,
            "future_activation_simulation_ok": ready,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": paper_orders_enabled,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": False,
            "manual_activation_allowed": manual_allowed,
        },
    }
    (tmp / "paper_unlock_manual_activation_patch_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _valid_env() -> dict[str, str]:
    return {
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE": "1",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM": DEFAULT_SWITCH_CONFIRM_VALUE,
        "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH": "1",
        "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM": DEFAULT_ACTIVATION_CONFIRM_VALUE,
        "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH": "1",
        "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM": DEFAULT_FINAL_CONFIRM_VALUE,
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE": "paper",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE": "0",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET": "0",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER": "blocked",
    }


def test_final_enable_preflight_ready_but_no_orders() -> None:
    tmp = _tmpdir()
    try:
        _activation_patch_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_final_enable_preflight_report(tmp, PaperUnlockFinalEnablePreflightSettings(required_selected_entries=20), env={})
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT_READY_DIAGNOSTIC"
        assert report["activation_patch_guard"]["passes_activation_patch_guard"] is True
        assert report["final_enable_preflight_suite"]["negative_fail_closed_ok"] is True
        assert report["final_enable_preflight_suite"]["paper_order_activation_candidate_ok"] is True
        assert report["paper_order_activation_candidate_allowed"] is True
        assert report["paper_orders_enabled"] is False
        assert report["manual_activation_allowed"] is False
        assert report["operational_unlock_allowed"] is False
        assert report["counts"]["orders_submitted"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_actual_valid_env_marks_candidate_but_still_no_real_orders() -> None:
    tmp = _tmpdir()
    try:
        _activation_patch_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_final_enable_preflight_report(tmp, env=_valid_env())
        actual = report["final_enable_preflight_suite"]["actual_environment"]
        assert actual["final_enable_contract_ok"] is False  # final patch context is intentionally absent for actual env in this preflight
        assert actual["paper_order_activation_candidate_allowed"] is False
        candidate = report["final_enable_preflight_suite"]["paper_order_activation_candidate"]
        assert candidate["final_enable_contract_ok"] is True
        assert candidate["paper_order_activation_candidate_allowed"] is True
        assert candidate["paper_orders_enabled_in_this_patch"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_when_activation_patch_report_missing() -> None:
    tmp = _tmpdir()
    try:
        report = build_paper_unlock_final_enable_preflight_report(tmp)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["activation_patch_guard"]["passes_activation_patch_guard"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_previous_report_had_paper_orders_enabled() -> None:
    tmp = _tmpdir()
    try:
        _activation_patch_report(tmp, ready=True, selected_entries=21, paper_orders_enabled=True)
        report = build_paper_unlock_final_enable_preflight_report(tmp)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["activation_patch_guard"]["execution_disabled_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_sample_too_small() -> None:
    tmp = _tmpdir()
    try:
        _activation_patch_report(tmp, ready=True, selected_entries=7)
        report = build_paper_unlock_final_enable_preflight_report(tmp, PaperUnlockFinalEnablePreflightSettings(required_selected_entries=20))
        assert report["status"] == "WARN"
        assert report["activation_patch_guard"]["selected_entries_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_negative_live_testnet_exchange_scenarios_fail_closed() -> None:
    tmp = _tmpdir()
    try:
        _activation_patch_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_final_enable_preflight_report(tmp)
        scenarios = {s["scenario"]: s for s in report["final_enable_preflight_suite"]["scenarios"]}
        for name in ["live_mode_requested", "testnet_mode_requested", "exchange_broker_available"]:
            assert scenarios[name]["final_enable_contract_ok"] is False
            assert scenarios[name]["paper_order_activation_candidate_allowed"] is False
            assert scenarios[name]["fail_closed_for_real_execution"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report_persists_file() -> None:
    tmp = _tmpdir()
    try:
        _activation_patch_report(tmp, ready=True, selected_entries=21)
        report = write_paper_unlock_final_enable_preflight_report(tmp)
        path = tmp / "paper_unlock_final_enable_preflight_report.json"
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4m"
        assert saved["opens_orders"] is False
        assert saved["counts"]["orders_submitted"] == 0
        assert report["decision"]["final_enable_preflight_ok"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_final_enable_preflight_ready_but_no_orders()
    test_actual_valid_env_marks_candidate_but_still_no_real_orders()
    test_fail_closed_when_activation_patch_report_missing()
    test_fail_closed_if_previous_report_had_paper_orders_enabled()
    test_fail_closed_if_sample_too_small()
    test_negative_live_testnet_exchange_scenarios_fail_closed()
    test_write_report_persists_file()
    print("Paper unlock final enable preflight tests passed.")


if __name__ == "__main__":
    main()
