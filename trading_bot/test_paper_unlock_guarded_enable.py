from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paper_unlock_guarded_enable import (
    DEFAULT_ACTIVATION_CONFIRM_VALUE,
    DEFAULT_FINAL_CONFIRM_VALUE,
    DEFAULT_OPERATOR_CONFIRM_VALUE,
    DEFAULT_SWITCH_CONFIRM_VALUE,
    PaperUnlockGuardedEnableSettings,
    build_paper_unlock_guarded_enable_report,
    write_paper_unlock_guarded_enable_report,
)


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="guarded_enable_test_"))


def _final_preflight_report(
    tmp: Path,
    *,
    ready: bool = True,
    selected_entries: int = 21,
    paper_orders_enabled: bool = False,
    candidate_allowed: bool = True,
) -> None:
    decision_status = "FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT_READY_DIAGNOSTIC" if ready else "KEEP_DIAGNOSTIC"
    payload = {
        "status": "PASS" if ready else "WARN",
        "final_preflight_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT",
        "activation_patch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT",
        "switch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT",
        "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
        "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": paper_orders_enabled,
        "profile_activation_allowed": False,
        "automatic_activation_allowed": False,
        "manual_activation_allowed": False,
        "paper_order_activation_candidate_allowed": candidate_allowed,
        "final_enable_contract": {
            "required_cadence_variant": "bounded_6_daily_30_weekly_0h",
        },
        "runtime_profile_candidate": {
            "entry_state_policy": "CONFIRMATION_ONLY",
            "allowed_structure_states": ["CONFIRMATION"],
            "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
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
            "final_preflight_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT",
            "activation_patch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT",
            "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
            "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
            "selected_entries": selected_entries,
            "activation_patch_guard_ok": ready,
            "final_enable_preflight_ok": ready,
            "negative_fail_closed_ok": ready,
            "paper_order_activation_candidate_ok": ready and candidate_allowed,
            "paper_order_activation_candidate_allowed": ready and candidate_allowed,
            "paper_orders_enabled": paper_orders_enabled,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "manual_activation_allowed": False,
            "automatic_activation_allowed": False,
        },
    }
    (tmp / "paper_unlock_final_enable_preflight_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _valid_env() -> dict[str, str]:
    return {
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE": "1",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM": DEFAULT_SWITCH_CONFIRM_VALUE,
        "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH": "1",
        "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM": DEFAULT_ACTIVATION_CONFIRM_VALUE,
        "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH": "1",
        "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM": DEFAULT_FINAL_CONFIRM_VALUE,
        "PAPER_UNLOCK_OPERATOR_ENABLE_PAPER_ORDERS": "1",
        "PAPER_UNLOCK_OPERATOR_CONFIRM_PAPER_ORDERS": DEFAULT_OPERATOR_CONFIRM_VALUE,
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE": "paper",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE": "0",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET": "0",
        "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER": "blocked",
    }


def test_guarded_enable_ready_but_default_fail_closed() -> None:
    tmp = _tmpdir()
    try:
        _final_preflight_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_guarded_enable_report(tmp, PaperUnlockGuardedEnableSettings(required_selected_entries=20), env={})
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "GUARDED_PAPER_ENABLE_IMPLEMENTATION_READY_OPERATOR_CONTROLLED"
        assert report["final_preflight_guard"]["passes_final_preflight_guard"] is True
        assert report["operator_enable_suite"]["passes_operator_enable_suite"] is True
        assert report["operator_enable_suite"]["negative_fail_closed_ok"] is True
        assert report["paper_orders_enabled"] is False
        assert report["paper_unlock_experiment_allowed"] is False
        assert report["manual_activation_allowed"] is False
        assert report["operational_unlock_allowed"] is False
        assert report["orders_submitted"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_valid_operator_env_enables_paper_only_orders_flag() -> None:
    tmp = _tmpdir()
    try:
        _final_preflight_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_guarded_enable_report(tmp, env=_valid_env())
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "GUARDED_PAPER_ENABLE_ACTIVE_OPERATOR_CONTROLLED"
        assert report["paper_orders_enabled"] is True
        assert report["paper_unlock_experiment_allowed"] is True
        assert report["manual_activation_allowed"] is True
        assert report["automatic_activation_allowed"] is False
        assert report["operational_unlock_allowed"] is False
        assert report["enables_live_or_testnet"] is False
        assert report["exchange_broker_allowed"] is False
        assert report["orders_submitted"] == 0
        assert report["positions_opened"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_missing_final_preflight_report_keeps_diagnostic() -> None:
    tmp = _tmpdir()
    try:
        report = build_paper_unlock_guarded_enable_report(tmp, env=_valid_env())
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["final_preflight_guard"]["passes_final_preflight_guard"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_previous_preflight_had_orders_enabled() -> None:
    tmp = _tmpdir()
    try:
        _final_preflight_report(tmp, ready=True, selected_entries=21, paper_orders_enabled=True)
        report = build_paper_unlock_guarded_enable_report(tmp, env=_valid_env())
        assert report["status"] == "WARN"
        assert report["final_preflight_guard"]["no_orders_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_sample_too_small() -> None:
    tmp = _tmpdir()
    try:
        _final_preflight_report(tmp, ready=True, selected_entries=7)
        report = build_paper_unlock_guarded_enable_report(tmp, PaperUnlockGuardedEnableSettings(required_selected_entries=20), env=_valid_env())
        assert report["status"] == "WARN"
        assert report["final_preflight_guard"]["selected_entries_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_negative_operator_live_testnet_exchange_scenarios_fail_closed() -> None:
    tmp = _tmpdir()
    try:
        _final_preflight_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_guarded_enable_report(tmp)
        scenarios = {s["scenario"]: s for s in report["operator_enable_suite"]["scenarios"]}
        for name in ["live_mode_requested", "testnet_mode_requested", "exchange_broker_available", "operator_confirm_mismatch"]:
            assert scenarios[name]["operator_enable_contract_ok"] is False
            assert scenarios[name]["paper_orders_enabled_in_this_patch"] is False
            assert scenarios[name]["paper_unlock_experiment_allowed_in_this_patch"] is False
            assert scenarios[name]["fail_closed_when_not_authorized"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report_persists_file() -> None:
    tmp = _tmpdir()
    try:
        _final_preflight_report(tmp, ready=True, selected_entries=21)
        report = write_paper_unlock_guarded_enable_report(tmp)
        path = tmp / "paper_unlock_guarded_enable_report.json"
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4n"
        assert saved["runtime_enable_contract"]["entry_state_policy"] == "CONFIRMATION_ONLY"
        assert saved["counts"]["orders_submitted"] == 0
        assert report["decision"]["operator_enable_suite_ok"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_guarded_enable_ready_but_default_fail_closed()
    test_valid_operator_env_enables_paper_only_orders_flag()
    test_missing_final_preflight_report_keeps_diagnostic()
    test_fail_closed_if_previous_preflight_had_orders_enabled()
    test_fail_closed_if_sample_too_small()
    test_negative_operator_live_testnet_exchange_scenarios_fail_closed()
    test_write_report_persists_file()
    print("Paper unlock guarded enable tests passed.")


if __name__ == "__main__":
    main()
