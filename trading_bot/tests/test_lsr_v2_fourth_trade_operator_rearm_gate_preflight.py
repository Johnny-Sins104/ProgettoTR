from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_fourth_trade_operator_rearm_gate_preflight import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PASS_DECISION,
    REPORTS_NOT_READY_DECISION,
    SOURCE_MARKERS_MISSING_DECISION,
    STATE_NOT_LOCKED_DECISION,
    OPERATOR_REARM_CONFIRMATION_ENV,
    OPERATOR_REARM_CONFIRMATION_PHRASE,
    OPERATOR_REARM_ENABLE_ENV,
    OPERATOR_REARM_MAX_POSITIONS_ENV,
    build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_source_tree(root: Path, *, missing_marker: bool = False) -> None:
    files = {
        "trading_bot/core/lsr_v2_fourth_trade_rearm_readiness_preflight.py": "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT\nfourth_trade_rearm_readiness_ready=True\n",
        "trading_bot/core/lsr_v2_candidate_lifecycle_hook_preflight.py": "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT\ncandidate_lifecycle_hook_allowed=False\n",
        "trading_bot/core/lsr_v2_launcher_runner_read_only_handoff_preflight.py": "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT\npaper_only_execution_allowed=False\n",
        "trading_bot/core/lsr_v2_engine_read_only_artifact_hook.py": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK\npaper_engine_hook_read_only=True\n",
        "trading_bot/core/liquidity_sweep_reversal_v2.py": "LIQUIDITY SWEEP REVERSAL candidate detector\n",
    }
    if missing_marker:
        files["trading_bot/core/lsr_v2_fourth_trade_rearm_readiness_preflight.py"] = "# missing readiness marker\n"
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _seed(
    tmp_path: Path,
    *,
    missing_report: bool = False,
    missing_marker: bool = False,
    open_position: bool = False,
    live: bool = False,
    fourth_allowed: bool = False,
) -> tuple[Path, Path]:
    data = tmp_path / "data"
    project = tmp_path / "project"
    _write_source_tree(project, missing_marker=missing_marker)
    common_safe = {
        "status": "PASS",
        "lifecycle_state": "FLAT_LOCKED",
        "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
        "telegram_payload_ready": True,
        "telegram_update_ready": True,
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "visual_sl_tp_progress_bar_ready": True,
        "visual_sl_tp_progress_bar": "SL ================● TP",
        "fourth_trade_allowed": fourth_allowed,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "fourth_submit_or_reentry_detected": False,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.7543376227,
        "balance_after": 1023.7543376227,
    }
    if not missing_report:
        _write_json(data / "lsr_v2_fourth_trade_rearm_readiness_preflight_report.json", {
            **common_safe,
            "decision": "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY",
            "rearm_readiness_preflight_ready": True,
            "fourth_trade_rearm_readiness_ready": True,
        })
    _write_json(data / "lsr_v2_candidate_lifecycle_hook_preflight_report.json", {
        **common_safe,
        "decision": "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY",
        "candidate_lifecycle_hook_preflight_ready": True,
    })
    _write_json(data / "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json", {
        **common_safe,
        "decision": "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY",
        "read_only_handoff_preflight_ready": True,
    })
    _write_json(data / "lsr_v2_launcher_runner_visibility_parity_audit_report.json", {
        **common_safe,
        "decision": "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY",
        "launcher_runner_visibility_parity_ok": True,
    })
    _write_json(data / "lsr_v2_engine_read_only_artifact_hook_report.json", {
        **common_safe,
        "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
        "engine_artifact_hook_ready": True,
    })
    _write_json(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", {
        **common_safe,
        "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY",
        "lifecycle_auto_monitor_ready": True,
    })
    _write_json(data / "lsr_v2_telegram_trade_dashboard_report.json", {
        **common_safe,
        "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY",
        "dashboard_ready": True,
    })
    _write_json(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", {
        **common_safe,
        "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
        "three_trade_postmortem_complete": True,
    })
    positions = []
    if open_position:
        positions.append({"position_id": "p4", "status": "OPEN", "source": "lsr_v2_fourth_trade"})
    _write_json(data / "paper_state.json", {"balance": 1023.7543376227, "realized_pnl": 23.7543376227, "positions": positions, "orders": []})
    _write_json(data / "paper_status.json", {"open_positions": 1 if open_position else 0, "pending_orders": 0})
    return data, project


def test_operator_rearm_gate_preflight_passes_but_keeps_all_permissions_disabled(tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["operator_rearm_gate_preflight_ready"] is True
    assert report["operator_rearm_gate_plan_ready"] is True
    assert report["operator_rearm_gate_allowed"] is False
    assert report["operator_rearm_confirmation_phrase"] == OPERATOR_REARM_CONFIRMATION_PHRASE
    assert report["operator_rearm_enable_env_name"] == OPERATOR_REARM_ENABLE_ENV
    assert report["operator_rearm_confirmation_env_name"] == OPERATOR_REARM_CONFIRMATION_ENV
    assert report["operator_rearm_max_positions_env_name"] == OPERATOR_REARM_MAX_POSITIONS_ENV
    assert report["future_candidate_detection_allowed"] is False
    assert report["candidate_routing_execution_allowed"] is False
    assert report["candidate_submit_execution_allowed"] is False
    assert report["paper_only_execution_allowed"] is False
    assert report["orders_submitted_by_operator_rearm_gate_preflight"] == 0
    assert report["positions_opened_by_operator_rearm_gate_preflight"] == 0
    assert report["positions_closed_by_operator_rearm_gate_preflight"] == 0


def test_missing_readiness_report_warns(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, missing_report=True)
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == REPORTS_NOT_READY_DECISION
    assert "required_operator_gate_reports_not_ready" in report["blockers"]


def test_missing_operator_gate_source_marker_warns(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, missing_marker=True)
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == SOURCE_MARKERS_MISSING_DECISION
    assert "operator_gate_required_markers_missing" in report["blockers"]


def test_open_position_warns_state_not_locked(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]


def test_operator_env_warns_before_explicit_unlock_patch(monkeypatch, tmp_path: Path) -> None:
    data, project = _seed(tmp_path)
    monkeypatch.setenv(OPERATOR_REARM_ENABLE_ENV, "1")
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["active_lsr_v2_operator_env_count"] == 1
    assert report["operator_rearm_gate_allowed"] is False


def test_fourth_allowed_warns_state_not_locked(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, fourth_allowed=True)
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "three_trade_state_not_flat_locked_or_fourth_lock_invalid" in report["blockers"]


def test_live_flag_fails_closed(tmp_path: Path) -> None:
    data, project = _seed(tmp_path, live=True)
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(data_dir=data, project_root=project)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
