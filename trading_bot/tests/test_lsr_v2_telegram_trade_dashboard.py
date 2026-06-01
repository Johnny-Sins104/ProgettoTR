from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_telegram_trade_dashboard import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    PASS_DECISION,
    STATE_NOT_FLAT_DECISION,
    build_lsr_v2_telegram_trade_dashboard_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed(tmp_path: Path, *, open_position: bool = False, operator_env: bool = False, live: bool = False) -> Path:
    data = tmp_path / "data"
    postmortem = {
        "status": "PASS",
        "decision": "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY",
        "third_trade_cycle_id": "pc_third",
        "three_trade_postmortem_complete": True,
        "three_trade_lifecycle_complete": True,
        "submit_execution_events_total": 3,
        "close_execution_events_total": 3,
        "aggregate_realized_pnl": 23.7543376227,
        "realized_pnl_after": 23.7543376227,
        "balance_after": 1023.7543376227,
        "total_realized_r_from_final_audits": 3.8830202656,
        "total_risk_amount": 7.5,
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
    preflight = {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_TRADE_CLOSE_PREFLIGHT_READY",
        "cycle_id": "pc_third",
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "entry_prices": {"BTC/USDT": 72771.64},
        "current_prices": {"BTC/USDT": 73420.66},
        "stop_losses": {"BTC/USDT": 72568.303436},
        "take_profits": {"BTC/USDT": 73178.313128},
        "total_risk_amount": 2.5,
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
    }
    final_audit = {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT_READY",
        "cycle_id": "pc_third",
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "realized_pnl_total": 7.9796273011,
    }
    _write_json(data / "lsr_v2_three_trade_postmortem_stability_lock_report.json", postmortem)
    _write_json(data / "lsr_v2_third_trade_close_preflight_report.json", preflight)
    _write_json(data / "lsr_v2_third_closed_trade_final_audit_report.json", final_audit)
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


def test_dashboard_passes_for_three_trade_flat_locked_state(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_telegram_trade_dashboard_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["dashboard_ready"] is True
    assert report["telegram_payload_ready"] is True
    assert report["telegram_send_allowed"] is False
    assert report["telegram_network_called"] is False
    assert report["dashboard_mode"] == "POST_THREE_TRADE_FLAT_LOCKED"
    assert report["fourth_trade_locked"] is True
    assert report["stability_lock_active"] is True
    assert report["orders_submitted_by_telegram_dashboard"] == 0
    assert report["positions_opened_by_telegram_dashboard"] == 0
    assert report["positions_closed_by_telegram_dashboard"] == 0
    assert report["paper_state_modified_by_telegram_dashboard"] is False
    assert report["paper_status_modified_by_telegram_dashboard"] is False
    assert "LSR-v2 Paper Dashboard" in report["telegram_message_text"]
    assert "BTC/USDT" in report["telegram_message_text"]
    assert report["dashboard_cards"]["last_trade"]["realized_r_multiple"] > 3
    assert report["visual_sl_tp_progress_bar_ready"] is True
    assert report["visual_sl_tp_progress_bar"].startswith("SL ")
    assert report["visual_sl_tp_progress_bar"].endswith(" TP")
    assert "●" in report["visual_sl_tp_progress_bar"]
    assert report["entry_to_tp_progress_pct"] == 100.0
    assert report["distance_to_take_profit"] > 0
    assert report["distance_to_stop_loss"] > report["distance_to_take_profit"]
    assert report["progress_state"] == "TP_HIT_OR_BEYOND"
    assert "SL/TP progress:" in report["telegram_message_text"]
    assert report["dashboard_cards"]["visual_sl_tp_progress"]["tp_hit_or_beyond"] is True


def test_visual_progress_handles_sell_direction(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    preflight_path = data / "lsr_v2_third_trade_close_preflight_report.json"
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight.update(
        {
            "sides": ["SELL"],
            "entry_prices": {"BTC/USDT": 100.0},
            "current_prices": {"BTC/USDT": 92.0},
            "stop_losses": {"BTC/USDT": 105.0},
            "take_profits": {"BTC/USDT": 90.0},
        }
    )
    _write_json(preflight_path, preflight)
    report = build_lsr_v2_telegram_trade_dashboard_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["visual_sl_tp_progress_bar_ready"] is True
    assert report["entry_to_tp_progress_pct"] == 80.0
    assert report["progress_state"] == "IN_RANGE"
    assert report["distance_to_take_profit"] == 2.0
    assert report["distance_to_stop_loss"] == 13.0


def test_dashboard_warns_when_state_is_not_flat(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_telegram_trade_dashboard_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_FLAT_DECISION
    assert "paper_state_or_status_not_flat" in report["blockers"]
    assert report["dashboard_ready"] is False


def test_dashboard_warns_when_operator_env_is_active(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_DASHBOARD_ENABLE", "1")
    report = build_lsr_v2_telegram_trade_dashboard_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False


def test_dashboard_fails_if_live_enabled(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_telegram_trade_dashboard_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
    assert "live_enabled" in report["blockers"]
