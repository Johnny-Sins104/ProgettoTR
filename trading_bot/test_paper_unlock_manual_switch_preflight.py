from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paper_unlock_manual_switch_preflight import (
    DEFAULT_CONFIRM_VALUE,
    PaperUnlockManualSwitchPreflightSettings,
    build_paper_unlock_manual_switch_preflight_report,
    write_paper_unlock_manual_switch_preflight_report,
)


def _tmpdir() -> Path:
    return Path(tempfile.mkdtemp(prefix="manual_switch_preflight_test_"))


def _switch_report(
    tmp: Path,
    *,
    ready: bool = True,
    selected_entries: int = 21,
    paper_orders_enabled: bool = False,
    manual_allowed: bool = False,
    exchange_allowed: bool = False,
) -> None:
    decision_status = "GUARDED_PAPER_SWITCH_IMPLEMENTATION_DRAFT_READY_DIAGNOSTIC" if ready else "KEEP_DIAGNOSTIC"
    payload = {
        "status": "PASS" if ready else "WARN",
        "switch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT",
        "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
        "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": paper_orders_enabled,
        "profile_activation_allowed": False,
        "automatic_activation_allowed": False,
        "manual_activation_allowed": manual_allowed,
        "activation_draft_guard": {
            "passes_activation_draft_guard": ready,
            "selected_entries": selected_entries,
            "best_stability_review_variant": "bounded_6_daily_30_weekly_0h",
        },
        "switch_contract": {
            "draft_only": True,
            "activation_in_this_patch_allowed": False,
            "automatic_activation_allowed": False,
            "paper_orders_enabled_in_this_patch": False,
            "operational_unlock_allowed_in_this_patch": False,
            "testnet_allowed": False,
            "live_allowed": False,
            "exchange_broker_allowed": exchange_allowed,
            "manual_switch_controls": {
                "separate_activation_patch_required": True,
                "two_step_confirmation_required": True,
                "manual_enable_env": "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE",
                "manual_enable_required_value": "1",
                "manual_confirm_env": "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM",
                "manual_confirm_required_value": DEFAULT_CONFIRM_VALUE,
                "required_mode": "paper",
                "must_fail_closed_if_missing": True,
                "must_fail_closed_if_live_or_testnet": True,
                "must_fail_closed_if_exchange_broker_enabled": True,
                "must_recheck_activation_draft_report": True,
                "must_recheck_shadow_stability_report": True,
            },
            "runtime_profile": {
                "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
                "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
                "entry_state_policy": "CONFIRMATION_ONLY",
                "allowed_structure_states": ["CONFIRMATION"],
                "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
                "map_score_min": 65.0,
                "map_score_max": 79.999,
                "max_positions": 1,
                "risk_per_trade_pct": 0.0025,
                "max_daily_entries": 6,
                "max_weekly_entries": 30,
            },
            "abort_interlocks": {
                "max_consecutive_losses": 3,
                "max_drawdown_pct": 1.0,
                "pause_on_manual_confirmation_missing": True,
                "pause_on_any_live_or_testnet_mode": True,
                "pause_on_exchange_broker_available": True,
            },
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
            "switch_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT",
            "profile_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
            "experiment_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN",
            "selected_entries": selected_entries,
            "best_stability_review_variant": "bounded_6_daily_30_weekly_0h",
            "activation_guard_ok": ready,
            "switch_implementation_ready": ready,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": paper_orders_enabled,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": False,
            "manual_activation_allowed": manual_allowed,
        },
    }
    (tmp / "paper_unlock_experiment_switch_draft_report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_manual_switch_preflight_ready_but_execution_disabled() -> None:
    tmp = _tmpdir()
    try:
        _switch_report(tmp, ready=True, selected_entries=21)
        report = build_paper_unlock_manual_switch_preflight_report(tmp, PaperUnlockManualSwitchPreflightSettings(required_selected_entries=20), env={})
        assert report["status"] == "PASS"
        assert report["decision"]["status"] == "MANUAL_PAPER_SWITCH_PREFLIGHT_READY_DIAGNOSTIC"
        assert report["switch_draft_guard"]["passes_switch_draft_guard"] is True
        assert report["preflight_suite"]["passes_preflight_suite"] is True
        assert report["preflight_suite"]["negative_fail_closed_ok"] is True
        assert report["preflight_suite"]["future_patch_simulation_ok"] is True
        assert report["paper_orders_enabled"] is False
        assert report["manual_activation_allowed"] is False
        assert report["operational_unlock_allowed"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_preflight_actual_env_can_be_valid_but_this_patch_still_blocks_activation() -> None:
    tmp = _tmpdir()
    try:
        _switch_report(tmp, ready=True, selected_entries=21)
        env = {
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE": "1",
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM": DEFAULT_CONFIRM_VALUE,
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE": "paper",
            "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER": "blocked",
        }
        report = build_paper_unlock_manual_switch_preflight_report(tmp, env=env)
        actual = report["preflight_suite"]["actual_environment"]
        assert actual["two_step_ok"] is True
        assert actual["separate_patch_ok"] is False
        assert actual["future_manual_preflight_ok"] is False
        assert actual["activation_allowed_in_this_patch"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_when_switch_draft_missing() -> None:
    tmp = _tmpdir()
    try:
        report = build_paper_unlock_manual_switch_preflight_report(tmp)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["switch_draft_guard"]["passes_switch_draft_guard"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_switch_draft_had_paper_orders_enabled() -> None:
    tmp = _tmpdir()
    try:
        _switch_report(tmp, ready=True, selected_entries=21, paper_orders_enabled=True)
        report = build_paper_unlock_manual_switch_preflight_report(tmp)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["switch_draft_guard"]["execution_disabled_ok"] is False
        assert report["paper_orders_enabled"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_fail_closed_if_exchange_broker_allowed_in_switch_contract() -> None:
    tmp = _tmpdir()
    try:
        _switch_report(tmp, ready=True, selected_entries=21, exchange_allowed=True)
        report = build_paper_unlock_manual_switch_preflight_report(tmp)
        assert report["status"] == "WARN"
        assert report["decision"]["status"] == "KEEP_DIAGNOSTIC"
        assert report["switch_draft_guard"]["contract_blocks_execution_ok"] is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_write_report_persists_file() -> None:
    tmp = _tmpdir()
    try:
        _switch_report(tmp, ready=True, selected_entries=21)
        report = write_paper_unlock_manual_switch_preflight_report(tmp)
        path = tmp / "paper_unlock_manual_switch_preflight_report.json"
        assert path.exists()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["prompt"] == "29.4.4k"
        assert saved["opens_orders"] is False
        assert saved["counts"]["orders_submitted"] == 0
        assert report["decision"]["fail_closed_preflight_ok"] is True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    test_manual_switch_preflight_ready_but_execution_disabled()
    test_preflight_actual_env_can_be_valid_but_this_patch_still_blocks_activation()
    test_fail_closed_when_switch_draft_missing()
    test_fail_closed_if_switch_draft_had_paper_orders_enabled()
    test_fail_closed_if_exchange_broker_allowed_in_switch_contract()
    test_write_report_persists_file()
    print("Paper unlock manual switch preflight tests passed.")


if __name__ == "__main__":
    main()
