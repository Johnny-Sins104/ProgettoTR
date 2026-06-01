from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_trade_lifecycle_auto_monitor import (
    DASHBOARD_MISSING_DECISION,
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PASS_DECISION,
    STATE_NOT_LOCKED_DECISION,
    build_lsr_v2_trade_lifecycle_auto_monitor_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed(tmp_path: Path, *, open_position: bool = False, operator_env: bool = False, live: bool = False, dashboard_ready: bool = True) -> Path:
    data = tmp_path / "data"
    postmortem = {
        "status": "PASS",
        "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.7543376227,
        "realized_pnl_after": 23.7543376227,
        "balance_after": 1023.7543376227,
        "pnl_reconciliation_ok": True,
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "operator_env_absent": not operator_env,
        "fourth_submit_or_reentry_detected": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    dashboard = {
        "status": "PASS" if dashboard_ready else "WARN",
        "decision": "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY" if dashboard_ready else "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_DASHBOARD_STABILITY_LOCK_MISSING",
        "dashboard_ready": dashboard_ready,
        "telegram_payload_ready": dashboard_ready,
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "telegram_message_key": "lsr_v2_dashboard:POST_THREE_TRADE_FLAT_LOCKED:pc_third",
        "telegram_message_text": "LSR-v2 Paper Dashboard\nSL/TP progress:\nSL ================● TP",
        "visual_sl_tp_progress_bar_ready": dashboard_ready,
        "visual_sl_tp_progress_bar": "SL ================● TP",
        "visual_sl_tp_progress_pct": 100.0,
        "entry_to_tp_progress_pct": 100.0,
        "distance_to_take_profit": 242.346872,
        "distance_to_stop_loss": 852.356564,
        "progress_state": "TP_HIT_OR_BEYOND",
        "flat_state_confirmed": not open_position,
        "paper_state_status_consistency": True,
        "operator_env_absent": not operator_env,
        "fourth_submit_or_reentry_detected": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "stability_lock_active": True,
        "open_positions_after": 1 if open_position else 0,
        "paper_status_open_positions_after": 1 if open_position else 0,
        "paper_status_pending_orders_after": 0,
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.7543376227,
        "realized_pnl_after": 23.7543376227,
        "balance_after": 1023.7543376227,
        "pnl_reconciliation_ok": True,
        "dashboard_cards": {
            "last_trade": {
                "symbol": "BTC/USDT",
                "side": "BUY",
                "status": "CLOSED_FLAT" if not open_position else "OPEN",
                "entry_price": 72771.64,
                "current_price": 73420.66,
                "stop_loss": 72568.303436,
                "take_profit": 73178.313128,
                "realized_pnl": 7.9796273011,
                "realized_r_multiple": 3.1919,
            }
        },
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    _write_json(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", postmortem)
    _write_json(data / "lsr_v2_telegram_trade_dashboard_report.json", dashboard)
    _write_json(
        data / "paper_state.json",
        {
            "balance": 1023.7543376227,
            "realized_pnl": 23.7543376227,
            "positions": {
                "pos_third": {
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


def test_lifecycle_auto_monitor_passes_for_flat_locked_dashboard(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_trade_lifecycle_auto_monitor_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["lifecycle_auto_monitor_ready"] is True
    assert report["lifecycle_update_ready"] is True
    assert report["lifecycle_state"] == "FLAT_LOCKED"
    assert report["telegram_update_ready"] is True
    assert report["telegram_send_allowed"] is False
    assert report["telegram_network_called"] is False
    assert report["scheduler_enabled"] is False
    assert report["scheduler_started"] is False
    assert report["fourth_trade_locked"] is True
    assert report["stability_lock_active"] is True
    assert report["orders_submitted_by_lifecycle_auto_monitor"] == 0
    assert report["positions_opened_by_lifecycle_auto_monitor"] == 0
    assert report["positions_closed_by_lifecycle_auto_monitor"] == 0
    assert report["paper_state_modified_by_lifecycle_auto_monitor"] is False
    assert report["paper_status_modified_by_lifecycle_auto_monitor"] is False
    assert "Lifecycle auto-monitor:" in report["telegram_message_text"]
    assert "State: FLAT_LOCKED" in report["telegram_message_text"]


def test_lifecycle_warns_if_dashboard_not_ready(tmp_path: Path) -> None:
    data = _seed(tmp_path, dashboard_ready=False)
    report = build_lsr_v2_trade_lifecycle_auto_monitor_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == DASHBOARD_MISSING_DECISION
    assert "telegram_dashboard_not_ready" in report["blockers"]
    assert report["lifecycle_update_ready"] is False


def test_lifecycle_warns_if_state_not_flat(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_trade_lifecycle_auto_monitor_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_LOCKED_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]
    assert report["lifecycle_state"] == "TP_HIT"


def test_lifecycle_warns_when_operator_env_is_active(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_LIFECYCLE_MONITOR_ENABLE", "1")
    report = build_lsr_v2_trade_lifecycle_auto_monitor_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False


def test_lifecycle_fails_if_live_enabled(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_trade_lifecycle_auto_monitor_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
