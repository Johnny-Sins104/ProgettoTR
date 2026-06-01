from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_engine_read_only_artifact_hook import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PASS_DECISION,
    REPORTS_MISSING_DECISION,
    STATE_NOT_LOCKED_DECISION,
    build_lsr_v2_engine_read_only_artifact_hook_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed(tmp_path: Path, *, missing_dashboard: bool = False, open_position: bool = False, live: bool = False) -> Path:
    data = tmp_path / "data"
    postmortem = {
        "status": "PASS",
        "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.7543376227,
        "total_realized_r_from_final_audits": 3.8830202656,
        "pnl_reconciliation_ok": True,
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "fourth_submit_or_reentry_detected": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    dashboard = {
        "status": "PASS" if not missing_dashboard else "WARN",
        "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY" if not missing_dashboard else "KEEP_DIAGNOSTIC",
        "dashboard_mode": "POST_THREE_TRADE_FLAT_LOCKED",
        "telegram_payload_ready": not missing_dashboard,
        "telegram_message_key": "lsr_v2_dashboard:POST_THREE_TRADE_FLAT_LOCKED:pc_000505_04a050a4",
        "telegram_message_text": "LSR-v2 Paper Dashboard\nSL ================● TP",
        "visual_sl_tp_progress_bar_ready": True,
        "visual_sl_tp_progress_bar": "SL ================● TP",
        "visual_sl_tp_progress_pct": 100.0,
        "progress_state": "TP_HIT_OR_BEYOND",
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "fourth_submit_or_reentry_detected": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    lifecycle = {
        "status": "PASS",
        "decision": "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY",
        "lifecycle_state": "FLAT_LOCKED" if not open_position else "OPEN",
        "telegram_update_ready": True,
        "telegram_lifecycle_message_key": "lsr_v2_lifecycle:FLAT_LOCKED:lsr_v2_dashboard",
        "telegram_message_text": "Lifecycle auto-monitor:\nState: FLAT_LOCKED",
        "visual_sl_tp_progress_bar_ready": True,
        "visual_sl_tp_progress_bar": "SL ================● TP",
        "visual_sl_tp_progress_pct": 100.0,
        "progress_state": "TP_HIT_OR_BEYOND",
        "balance_after": 1023.7543376227,
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "fourth_submit_or_reentry_detected": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    integration = {
        "status": "PASS",
        "decision": "LSR_V2_PAPER_ENGINE_INTEGRATION_PREFLIGHT_READY",
        "integration_preflight_ready": True,
        "lifecycle_auto_monitor_ready": True,
        "telegram_dashboard_ready": not missing_dashboard,
        "three_trade_postmortem_ready": True,
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "operator_env_absent": True,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    _write_json(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", postmortem)
    _write_json(data / "lsr_v2_telegram_trade_dashboard_report.json", dashboard)
    _write_json(data / "lsr_v2_trade_lifecycle_auto_monitor_report.json", lifecycle)
    _write_json(data / "lsr_v2_paper_engine_integration_preflight_report.json", integration)
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


def test_engine_artifact_hook_passes_for_validated_flat_locked_artifacts(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_engine_read_only_artifact_hook_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["engine_artifact_hook_ready"] is True
    assert report["paper_engine_hook_read_only"] is True
    assert report["paper_engine_artifact_hook_active"] is True
    assert report["lifecycle_state"] == "FLAT_LOCKED"
    assert report["telegram_payload_ready"] is True
    assert report["telegram_update_ready"] is True
    assert report["visual_sl_tp_progress_bar_ready"] is True
    assert "●" in report["visual_sl_tp_progress_bar"]
    assert report["fourth_trade_locked"] is True
    assert report["stability_lock_active"] is True
    assert report["orders_submitted_by_engine_artifact_hook"] == 0
    assert report["positions_opened_by_engine_artifact_hook"] == 0
    assert report["positions_closed_by_engine_artifact_hook"] == 0
    assert report["paper_state_modified_by_engine_artifact_hook"] is False
    assert report["paper_status_modified_by_engine_artifact_hook"] is False
    assert report["recommended_next_patch"].startswith("29.4.4t-2")


def test_engine_artifact_hook_warns_when_dashboard_not_ready(tmp_path: Path) -> None:
    data = _seed(tmp_path, missing_dashboard=True)
    report = build_lsr_v2_engine_read_only_artifact_hook_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == REPORTS_MISSING_DECISION
    assert "telegram_dashboard_not_ready" in report["blockers"]


def test_engine_artifact_hook_warns_when_state_not_flat(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_engine_read_only_artifact_hook_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]


def test_engine_artifact_hook_warns_when_operator_env_active(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_FOURTH_TRADE_ARM", "1")
    report = build_lsr_v2_engine_read_only_artifact_hook_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False


def test_engine_artifact_hook_fails_if_live_enabled(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_engine_read_only_artifact_hook_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]


def test_paper_engine_contains_read_only_hook_wiring() -> None:
    source = Path("trading_bot/core/paper_engine.py").read_text(encoding="utf-8")
    assert "write_lsr_v2_engine_read_only_artifact_hook_report" in source
    assert "lsr_v2_engine_read_only_artifact_hook" in source
    assert "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_ENABLED" in source
