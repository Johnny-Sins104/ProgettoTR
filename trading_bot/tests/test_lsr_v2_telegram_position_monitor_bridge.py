from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_telegram_position_monitor_bridge import (
    DRY_RUN_DECISION,
    NO_OPEN_POSITION_DECISION,
    SENT_DECISION,
    LSRV2TelegramPositionMonitorBridgeSettings,
    build_lsr_v2_position_monitor_notifications,
    progress_bar,
    progress_to_target,
    run_lsr_v2_telegram_position_monitor_bridge,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def test_progress_bar_buy_moves_marker_toward_tp() -> None:
    progress = progress_to_target(side="BUY", current=105, stop_loss=90, take_profit=110)
    assert progress == 0.75
    bar, pct, status = progress_bar(side="BUY", current=105, stop_loss=90, take_profit=110, width=10)
    assert "●" in bar
    assert pct == 0.75
    assert status in {"NEAR_TAKE_PROFIT", "IN_RANGE"}


def test_progress_bar_sell_moves_marker_toward_lower_tp() -> None:
    progress = progress_to_target(side="SELL", current=95, stop_loss=110, take_profit=90)
    assert progress == 0.75
    bar, pct, _status = progress_bar(side="SELL", current=95, stop_loss=110, take_profit=90, width=10)
    assert "SL 110" in bar
    assert "TP 90" in bar
    assert "●" in bar
    assert pct == 0.75


def test_build_notifications_from_second_monitor_report(tmp_path: Path) -> None:
    _write_json(tmp_path / "lsr_v2_second_open_position_monitor_report.json", {
        "status": "WARN",
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_SECOND_CLOSE_REQUIRED_DIAGNOSTIC",
        "cycle_id": "pc_test",
        "second_trade_position_open": True,
        "open_second_lsr_v2_position_count": 1,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "entry_prices": {"BTC/USDT": 100.0},
        "current_prices": {"BTC/USDT": 108.0},
        "stop_losses": {"BTC/USDT": 95.0},
        "take_profits": {"BTC/USDT": 110.0},
        "risk_multiple_current_avg": 2.5,
        "unrealized_pnl_total": 7.5,
        "total_risk_amount": 3.0,
        "take_profit_hit_diagnostic_count": 0,
        "stop_hit_diagnostic_count": 0,
        "close_required_diagnostic": False,
    })
    notifications, diagnostics = build_lsr_v2_position_monitor_notifications(tmp_path, bar_width=16)
    assert diagnostics["open_position_candidate_count"] == 1
    assert len(notifications) == 1
    text = notifications[0].text
    assert "LSR-v2 PAPER POSITION MONITOR" in text
    assert "BTC/USDT" in text
    assert "SL 95" in text and "TP 110" in text
    assert "●" in text
    assert "R=2.5" in text


def test_run_dry_run_with_open_position_has_no_side_effects(tmp_path: Path) -> None:
    _write_json(tmp_path / "lsr_v2_second_open_position_monitor_report.json", {
        "cycle_id": "pc_test",
        "second_trade_position_open": True,
        "open_second_lsr_v2_position_count": 1,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "entry_prices": {"BTC/USDT": 100.0},
        "current_prices": {"BTC/USDT": 102.0},
        "stop_losses": {"BTC/USDT": 95.0},
        "take_profits": {"BTC/USDT": 110.0},
        "risk_multiple_current_avg": 0.5,
        "unrealized_pnl_total": 2.0,
        "total_risk_amount": 4.0,
    })
    report = run_lsr_v2_telegram_position_monitor_bridge(data_dir=tmp_path)
    assert report["status"] == "PASS"
    assert report["decision"] == DRY_RUN_DECISION
    assert report["open_position_candidate_count"] == 1
    assert report["telegram_send_attempted_count"] == 0
    assert report["orders_submitted_by_position_monitor_bridge"] == 0
    assert report["positions_opened_by_position_monitor_bridge"] == 0
    assert report["positions_closed_by_position_monitor_bridge"] == 0
    assert report["paper_state_modified_by_position_monitor_bridge"] is False
    assert report["paper_status_modified_by_position_monitor_bridge"] is False


def test_run_no_open_position_is_pass_diagnostic(tmp_path: Path) -> None:
    _write_json(tmp_path / "lsr_v2_second_open_position_monitor_report.json", {
        "status": "WARN",
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_SECOND_POSITION_NOT_FOUND",
        "cycle_id": "pc_test",
        "second_trade_position_open": False,
        "open_second_lsr_v2_position_count": 0,
        "symbols": [],
    })
    report = run_lsr_v2_telegram_position_monitor_bridge(data_dir=tmp_path)
    assert report["status"] == "PASS"
    assert report["decision"] == NO_OPEN_POSITION_DECISION
    assert report["open_position_candidate_count"] == 0


def test_send_with_fake_sender_updates_state(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "lsr_v2_second_open_position_monitor.jsonl", [{
        "event_type": "LSR_V2_SECOND_OPEN_POSITION_MONITOR_AUDIT",
        "cycle_id": "pc_test",
        "symbol": "ETH/USDT",
        "side": "BUY",
        "position_open": True,
        "entry_price": 100.0,
        "current_price": 106.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "unrealized_pnl": 6.0,
        "risk_amount": 2.0,
        "risk_multiple_current": 3.0,
    }])
    sent: list[str] = []

    def sender(text: str) -> dict:
        sent.append(text)
        return {"ok": True}

    settings = LSRV2TelegramPositionMonitorBridgeSettings(
        data_dir=str(tmp_path),
        send_enable="1",
        send_confirmation="I_UNDERSTAND_SEND_LSR_V2_POSITION_MONITOR",
        telegram_token="token",
        telegram_chat_id="chat",
    )
    report = run_lsr_v2_telegram_position_monitor_bridge(data_dir=tmp_path, settings=settings, sender=sender)
    assert report["status"] == "PASS"
    assert report["decision"] == SENT_DECISION
    assert report["telegram_send_ok_count"] == 1
    assert len(sent) == 1
    assert "ETH/USDT" in sent[0]
    state = json.loads((tmp_path / "lsr_v2_telegram_position_monitor_bridge_state.json").read_text(encoding="utf-8"))
    assert state["sent_keys"]


def test_duplicate_is_skipped_without_force_resend(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "lsr_v2_second_open_position_monitor.jsonl", [{
        "cycle_id": "pc_test",
        "symbol": "SOL/USDT",
        "side": "BUY",
        "position_open": True,
        "entry_price": 100.0,
        "current_price": 101.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "unrealized_pnl": 1.0,
        "risk_amount": 2.0,
    }])
    key = "position_monitor:pc_test:SOL/USDT:101.0000:IN_RANGE"
    _write_json(tmp_path / "lsr_v2_telegram_position_monitor_bridge_state.json", {"sent_keys": [key]})
    settings = LSRV2TelegramPositionMonitorBridgeSettings(data_dir=str(tmp_path), send_enable="", telegram_token="token", telegram_chat_id="chat")
    report = run_lsr_v2_telegram_position_monitor_bridge(data_dir=tmp_path, settings=settings)
    assert report["notification_selected_count"] == 0
    assert report["notification_duplicate_skipped_count"] == 1


def test_stale_guard_skips_monitor_after_second_close_execution(tmp_path: Path) -> None:
    _write_json(tmp_path / "paper_status.json", {
        "open_positions": 0,
        "pending_orders": 0,
    })
    _write_json(tmp_path / "paper_state.json", {
        "orders": {},
        "positions": {
            "p1": {
                "cycle_id": "pc_closed",
                "symbol": "BTC/USDT",
                "status": "CLOSED",
                "open": False,
                "metadata": {"execution_source": "lsr_v2_second_trade_submit_execution"},
            }
        },
    })
    _write_json(tmp_path / "lsr_v2_second_trade_close_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_SINGLE_PAPER_POSITION_CLOSED",
        "cycle_id": "pc_closed",
        "positions_closed_by_second_trade_close_execution": 1,
        "open_second_lsr_v2_positions_after": 0,
        "paper_status_open_positions_after": 0,
    })
    _write_json(tmp_path / "lsr_v2_second_open_position_monitor_report.json", {
        "status": "WARN",
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_SECOND_CLOSE_REQUIRED_DIAGNOSTIC",
        "cycle_id": "pc_closed",
        "second_trade_position_open": True,
        "open_second_lsr_v2_position_count": 1,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "entry_prices": {"BTC/USDT": 100.0},
        "current_prices": {"BTC/USDT": 111.0},
        "stop_losses": {"BTC/USDT": 95.0},
        "take_profits": {"BTC/USDT": 110.0},
        "risk_multiple_current_avg": 3.0,
        "unrealized_pnl_total": 6.0,
        "total_risk_amount": 2.0,
        "take_profit_hit_diagnostic_count": 1,
        "close_required_diagnostic": True,
    })
    report = run_lsr_v2_telegram_position_monitor_bridge(data_dir=tmp_path)
    assert report["status"] == "PASS"
    assert report["decision"] == NO_OPEN_POSITION_DECISION
    assert report["open_position_candidate_count"] == 0
    assert report["stale_monitor_skipped_count"] == 1
    assert "paper_status_flat" in report["stale_monitor_skipped_reasons"] or "closed_by_lsr_v2_second_trade_close_execution_report.json" in report["stale_monitor_skipped_reasons"]


def test_stale_guard_skips_monitor_when_state_has_different_open_cycle(tmp_path: Path) -> None:
    _write_json(tmp_path / "paper_status.json", {
        "open_positions": 1,
        "pending_orders": 0,
    })
    _write_json(tmp_path / "paper_state.json", {
        "orders": {},
        "positions": {
            "p_current": {
                "cycle_id": "pc_current",
                "symbol": "BTC/USDT",
                "status": "OPEN",
                "open": True,
                "metadata": {"execution_source": "lsr_v2_second_paper_order_submit_execution"},
            }
        },
    })
    _write_jsonl(tmp_path / "lsr_v2_open_position_monitor.jsonl", [{
        "cycle_id": "pc_old",
        "symbol": "BTC/USDT",
        "side": "SELL",
        "position_open": True,
        "entry_price": 100.0,
        "current_price": 99.0,
        "stop_loss": 110.0,
        "take_profit": 90.0,
        "unrealized_pnl": 1.0,
        "risk_amount": 2.0,
    }])
    _write_jsonl(tmp_path / "lsr_v2_second_open_position_monitor.jsonl", [{
        "cycle_id": "pc_current",
        "symbol": "BTC/USDT",
        "side": "SELL",
        "position_open": True,
        "entry_price": 100.0,
        "current_price": 98.0,
        "stop_loss": 110.0,
        "take_profit": 90.0,
        "unrealized_pnl": 2.0,
        "risk_amount": 2.0,
    }])
    report = run_lsr_v2_telegram_position_monitor_bridge(data_dir=tmp_path)
    assert report["status"] == "PASS"
    assert report["open_position_candidate_count"] == 1
    assert report["notification_keys"][0].startswith("position_monitor:pc_current:")
    assert "paper_state_open_cycle_mismatch" in report["stale_monitor_skipped_reasons"]
