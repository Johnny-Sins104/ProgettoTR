from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_launcher_runner_visibility_parity_audit import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PARITY_MISMATCH_DECISION,
    PASS_DECISION,
    REPORTS_NOT_READY_DECISION,
    STATE_NOT_LOCKED_DECISION,
    build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed(tmp_path: Path, *, mismatch: bool = False, missing_banner: bool = False, open_position: bool = False, live: bool = False) -> Path:
    data = tmp_path / "data"
    common_safe = {
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "fourth_submit_or_reentry_detected": False,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    engine_bar = "SL ================● TP"
    launcher_bar = "SL =====●========== TP" if mismatch else engine_bar
    if not missing_banner:
        _write_json(
            data / "lsr_v2_launcher_read_only_dashboard_banner_report.json",
            {
                "status": "PASS",
                "decision": "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY",
                "launcher_banner_ready": True,
                "launcher_banner_text": "[LSR-V2 LAUNCHER DASHBOARD] READ-ONLY",
                "lifecycle_state": "FLAT_LOCKED",
                "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
                "telegram_dashboard_ready": True,
                "telegram_payload_ready": True,
                "telegram_update_ready": True,
                "telegram_send_allowed": False,
                "telegram_network_called": False,
                "visual_sl_tp_progress_bar_ready": True,
                "visual_sl_tp_progress_bar": launcher_bar,
                "submit_execution_events_total": 3,
                "close_execution_events_total": 3,
                "aggregate_realized_pnl": 23.7543376227,
                "balance_after": 1023.7543376227,
                **common_safe,
            },
        )
    _write_json(
        data / "lsr_v2_engine_read_only_artifact_hook_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY",
            "engine_artifact_hook_ready": True,
            "paper_engine_hook_read_only": True,
            "lifecycle_state": "FLAT_LOCKED",
            "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
            "telegram_dashboard_ready": True,
            "telegram_payload_ready": True,
            "telegram_update_ready": True,
            "telegram_send_allowed": True,  # hostile value must be pinned false by runner footer loader
            "telegram_network_called": True,
            "visual_sl_tp_progress_bar_ready": True,
            "visual_sl_tp_progress_bar": engine_bar,
            "orders_submitted_by_engine_artifact_hook": 99,
            "positions_opened_by_engine_artifact_hook": 99,
            "positions_closed_by_engine_artifact_hook": 99,
            "submit_execution_events_total": 3,
            "close_execution_events_total": 3,
            **common_safe,
        },
    )
    _write_json(
        data / "lsr_v2_trade_lifecycle_auto_monitor_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY",
            "lifecycle_state": "FLAT_LOCKED",
            "telegram_update_ready": True,
            **common_safe,
        },
    )
    _write_json(
        data / "lsr_v2_telegram_trade_dashboard_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY",
            "telegram_payload_ready": True,
            "telegram_update_ready": True,
            "visual_sl_tp_progress_bar_ready": True,
            "visual_sl_tp_progress_bar": engine_bar,
            **common_safe,
        },
    )
    _write_json(
        data / "lsr_v2_three_trade_postmortem_stability_lock_report.json",
        {
            "status": "PASS",
            "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
            "submit_execution_events_total": 3,
            "close_execution_events_total": 3,
            "aggregate_realized_pnl": 23.7543376227,
            **common_safe,
        },
    )
    _write_json(
        data / "paper_state.json",
        {
            "balance": 1023.7543376227,
            "realized_pnl": 23.7543376227,
            "positions": {
                "p1": {
                    "source": "lsr_v2_third_trade_submit_execution",
                    "status": "OPEN" if open_position else "CLOSED",
                    "open": open_position,
                }
            },
            "orders": {},
        },
    )
    _write_json(
        data / "paper_status.json",
        {
            "open_positions": 1 if open_position else 0,
            "pending_orders": 0,
            "live_enabled": live,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "operational_unlock_allowed": False,
        },
    )
    return data


def test_visibility_parity_passes_for_matching_launcher_and_runner_footer(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["visibility_parity_audit_ready"] is True
    assert report["launcher_runner_visibility_parity_ok"] is True
    assert report["visibility_mismatch_detected"] is False
    assert report["telegram_send_allowed"] is False
    assert report["telegram_network_called"] is False
    assert report["fourth_trade_locked"] is True
    assert report["stability_lock_active"] is True
    assert report["orders_submitted_by_launcher_runner_parity_audit"] == 0
    assert report["positions_opened_by_launcher_runner_parity_audit"] == 0
    assert report["positions_closed_by_launcher_runner_parity_audit"] == 0
    assert report["paper_state_modified_by_launcher_runner_parity_audit"] is False
    assert report["paper_status_modified_by_launcher_runner_parity_audit"] is False
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_visibility_parity_warns_on_visual_bar_mismatch(tmp_path: Path) -> None:
    data = _seed(tmp_path, mismatch=True)
    report = build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == PARITY_MISMATCH_DECISION
    assert report["visibility_mismatch_detected"] is True
    assert "visual_sl_tp_progress_bar" in report["visibility_mismatch_fields"]
    assert "launcher_runner_visibility_mismatch" in report["blockers"]


def test_visibility_parity_warns_when_launcher_report_missing(tmp_path: Path) -> None:
    data = _seed(tmp_path, missing_banner=True)
    report = build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == REPORTS_NOT_READY_DECISION
    assert "launcher_banner_not_ready" in report["blockers"]


def test_visibility_parity_warns_when_state_not_flat_locked(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]


def test_visibility_parity_warns_when_operator_env_active(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_FOURTH_TRADE_ARM", "1")
    report = build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False
    assert "lsr_v2_operator_env_active" in report["blockers"]


def test_visibility_parity_fails_when_live_enabled(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_launcher_runner_visibility_parity_audit_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
