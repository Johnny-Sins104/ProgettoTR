from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_telegram_notification_bridge import (
    LSRV2TelegramNotificationBridgeSettings,
    REQUIRED_CONFIRMATION,
    build_lsr_v2_telegram_notifications,
    run_lsr_v2_telegram_notification_bridge,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _seed_reports(data_dir: Path) -> None:
    _write(data_dir / "lsr_v2_second_trade_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": "pc_000360_test",
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "total_notional": 894.7,
        "total_risk_amount": 2.5,
    })
    _write(data_dir / "lsr_v2_second_trade_close_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_SINGLE_PAPER_POSITION_CLOSED",
        "cycle_id": "pc_000360_test",
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
        "realized_pnl_total": 11.5,
        "total_risk_amount": 2.5,
    })
    _write(data_dir / "lsr_v2_second_closed_trade_final_audit_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS",
        "cycle_id": "pc_000360_test",
        "realized_pnl_total": 11.5,
        "realized_r": 4.6,
        "residual_open_position": False,
        "third_trade_allowed": False,
    })
    _write(data_dir / "lsr_v2_two_trade_paper_cycle_postmortem_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS",
        "cycle_ids": ["pc_000228_test", "pc_000360_test"],
        "total_realized_pnl": 21.1,
        "average_realized_r": 4.2,
        "submit_execution_events_total": 2,
        "close_execution_events_total": 2,
        "third_trade_locked": True,
    })
    _write(data_dir / "lsr_v2_two_trade_observation_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_TWO_TRADE_OBSERVATION_PASS",
        "cycle_ids": ["pc_000228_test", "pc_000360_test"],
        "completed_observation_cycles": 43,
        "failed_observation_cycles": 0,
        "timed_out_cycles": 0,
        "new_submit_cycles": [],
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "third_trade_locked": True,
    })


def test_build_notifications_from_pass_reports(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    notifications, diagnostics = build_lsr_v2_telegram_notifications(tmp_path)
    assert len(notifications) == 5
    assert {n.kind for n in notifications} == {
        "SECOND_ORDER_EXECUTED",
        "SECOND_POSITION_CLOSED",
        "SECOND_FINAL_AUDIT_PASS",
        "TWO_TRADE_POSTMORTEM_PASS",
        "TWO_TRADE_OBSERVATION_PASS",
    }
    assert diagnostics["notification_candidate_count"] == 5
    assert "LSR-v2" in notifications[0].text


def test_dry_run_does_not_send_or_mutate_trading_state(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    report = run_lsr_v2_telegram_notification_bridge(data_dir=tmp_path)
    assert report["status"] == "PASS"
    assert report["decision"] == "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_READY_DRY_RUN"
    assert report["notification_selected_count"] == 5
    assert report["telegram_send_attempted_count"] == 0
    assert report["orders_submitted_by_telegram_bridge"] == 0
    assert report["positions_opened_by_telegram_bridge"] == 0
    assert report["positions_closed_by_telegram_bridge"] == 0
    assert report["paper_state_modified_by_telegram_bridge"] is False
    assert report["paper_status_modified_by_telegram_bridge"] is False


def test_send_requires_confirmation_and_config(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    settings = LSRV2TelegramNotificationBridgeSettings(
        data_dir=str(tmp_path),
        send_enable="1",
        send_confirmation="WRONG",
        telegram_token="token",
        telegram_chat_id="chat",
    )
    calls: list[str] = []
    report = run_lsr_v2_telegram_notification_bridge(data_dir=tmp_path, settings=settings, sender=lambda text: calls.append(text) or {"ok": True})
    assert report["decision"] == "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_READY_DRY_RUN"
    assert calls == []
    assert "telegram_bridge_confirmation_missing" in report["blockers"]


def test_actual_send_with_confirmation_writes_state(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    settings = LSRV2TelegramNotificationBridgeSettings(
        data_dir=str(tmp_path),
        send_enable="1",
        send_confirmation=REQUIRED_CONFIRMATION,
        telegram_token="token",
        telegram_chat_id="chat",
        max_messages=2,
    )
    calls: list[str] = []
    report = run_lsr_v2_telegram_notification_bridge(
        data_dir=tmp_path,
        settings=settings,
        sender=lambda text: calls.append(text) or {"ok": True, "message_id": len(calls)},
    )
    assert report["status"] == "PASS"
    assert report["decision"] == "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_SENT"
    assert report["telegram_send_attempted_count"] == 2
    assert report["telegram_send_ok_count"] == 2
    assert len(calls) == 2
    state = json.loads((tmp_path / "lsr_v2_telegram_notification_bridge_state.json").read_text(encoding="utf-8"))
    assert len(state["sent_keys"]) == 2


def test_duplicate_notifications_are_skipped_after_send(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    settings = LSRV2TelegramNotificationBridgeSettings(
        data_dir=str(tmp_path),
        send_enable="1",
        send_confirmation=REQUIRED_CONFIRMATION,
        telegram_token="token",
        telegram_chat_id="chat",
        max_messages=5,
    )
    report1 = run_lsr_v2_telegram_notification_bridge(data_dir=tmp_path, settings=settings, sender=lambda text: {"ok": True})
    assert report1["telegram_send_ok_count"] == 5
    report2 = run_lsr_v2_telegram_notification_bridge(data_dir=tmp_path, settings=settings, sender=lambda text: {"ok": True})
    assert report2["notification_selected_count"] == 0
    assert report2["notification_duplicate_skipped_count"] == 5
    assert report2["telegram_send_attempted_count"] == 0


def test_missing_reports_returns_warn(tmp_path: Path) -> None:
    report = run_lsr_v2_telegram_notification_bridge(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_NOTHING_TO_NOTIFY"
    assert report["notification_candidate_count"] == 0
