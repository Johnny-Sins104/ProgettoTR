from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_closed_trade_final_audit import (
    BACKUP_MISSING_DECISION,
    ENV_STILL_ACTIVE_DECISION,
    READY_DECISION,
    SAFETY_FAILED_DECISION,
    STATE_NOT_FLAT_DECISION,
    build_lsr_v2_third_closed_trade_final_audit_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed_closed(tmp_path: Path, *, open_position: bool = False, backups: bool = True, submit_count: int = 0) -> Path:
    data = tmp_path / "data"
    backup_dir = data / "lsr_v2_third_trade_close_execution_backups"
    backup_state = backup_dir / "paper_state_20260530T131600Z.json"
    backup_status = backup_dir / "paper_status_20260530T131600Z.json"
    if backups:
        _write_json(backup_state, {"before": "state"})
        _write_json(backup_status, {"before": "status"})

    closed_position = {
        "position_id": "pos_third",
        "order_id": "ord_third",
        "cycle_id": "pc_third_close",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "status": "CLOSED",
        "open": False,
        "source": "lsr_v2_third_trade_submit_execution",
        "paper_close_source": "lsr_v2_third_trade_close_execution",
        "entry_price": 100.0,
        "close_price": 112.0,
        "position_size": 2.0,
        "risk_amount": 10.0,
        "realized_pnl": 24.0,
        "metadata": {"trade_sequence": "THIRD", "cycle_id": "pc_third_close"},
    }
    if open_position:
        closed_position["status"] = "OPEN"
        closed_position["open"] = True
    _write_json(data / "paper_state.json", {
        "balance": 1024.0,
        "realized_pnl": 24.0,
        "orders": {},
        "positions": {"pos_third": closed_position},
    })
    _write_json(data / "paper_status.json", {
        "open_positions": 1 if open_position else 0,
        "pending_orders": 0,
        "balance": 1024.0,
        "realized_pnl": 24.0,
        "position_monitor": {"status": "OPEN" if open_position else "FLAT", "open_position_count": 1 if open_position else 0},
    })
    close_event = {
        "event_type": "LSR_V2_THIRD_TRADE_CLOSE_EXECUTION",
        "cycle_id": "pc_third_close",
        "position_id": "pos_third",
        "order_id": "ord_third",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "close_reason": "TAKE_PROFIT_HIT_DIAGNOSTIC",
        "realized_pnl": 24.0,
        "orders_submitted_by_third_trade_close_execution": 0,
        "positions_opened_by_third_trade_close_execution": 0,
        "positions_closed_by_third_trade_close_execution": 1,
    }
    _write_jsonl(data / "lsr_v2_third_trade_close_execution.jsonl", [close_event])
    _write_jsonl(data / "paper_events.jsonl", [close_event])
    _write_json(data / "lsr_v2_third_trade_close_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_SINGLE_PAPER_POSITION_CLOSED",
        "cycle_id": "pc_third_close",
        "positions_closed_by_third_trade_close_execution": 1,
        "orders_submitted_by_third_trade_close_execution": submit_count,
        "positions_opened_by_third_trade_close_execution": 0,
        "open_third_lsr_v2_positions_after": 0,
        "paper_status_open_positions_after": 0,
        "automatic_reentry_enabled": False,
        "backup_state_path": str(backup_state),
        "backup_status_path": str(backup_status),
        "realized_pnl_total": 24.0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    })
    _write_json(data / "lsr_v2_third_trade_close_preflight_report.json", {"cycle_id": "pc_third_close"})
    return data


def test_closed_trade_final_audit_passes_when_flat_and_env_absent(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path)
    before_state = json.loads((data / "paper_state.json").read_text())
    before_status = json.loads((data / "paper_status.json").read_text())
    report = build_lsr_v2_third_closed_trade_final_audit_report_from_files(data_dir=data)
    after_state = json.loads((data / "paper_state.json").read_text())
    after_status = json.loads((data / "paper_status.json").read_text())
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["closed_trade_confirmed"] is True
    assert report["flat_state_confirmed"] is True
    assert report["backups_present"] is True
    assert report["close_env_absent"] is True
    assert report["positions_closed_by_final_audit"] == 0
    assert report["orders_submitted_by_final_audit"] == 0
    assert report["positions_opened_by_final_audit"] == 0
    assert before_state == after_state
    assert before_status == after_status




def test_closed_trade_final_audit_passes_when_latest_report_was_overwritten_by_noop(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path)
    # A subsequent safe/default run of the close runner can overwrite the JSON report
    # with POSITION_NOT_FOUND after the paper position is already flat. The final
    # audit must still confirm the historical close from JSONL and backup files.
    _write_json(data / "lsr_v2_third_trade_close_execution_report.json", {
        "status": "WARN",
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_THIRD_POSITION_NOT_FOUND",
        "cycle_id": "pc_third_close",
        "positions_closed_by_third_trade_close_execution": 0,
        "orders_submitted_by_third_trade_close_execution": 0,
        "positions_opened_by_third_trade_close_execution": 0,
        "open_third_lsr_v2_positions_after": 0,
        "paper_status_open_positions_after": 0,
        "automatic_reentry_enabled": False,
        "backup_state_path": "",
        "backup_status_path": "",
        "realized_pnl_total": 0.0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    })
    report = build_lsr_v2_third_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["closed_trade_confirmed"] is True
    assert report["closed_trade_confirmed_from_report"] is False
    assert report["closed_trade_confirmed_from_event_log"] is True
    assert report["positions_closed_by_close_execution"] == 1
    assert report["backups_present"] is True
    assert report["backup_state_exists"] is True
    assert report["backup_status_exists"] is True
    assert report["flat_state_confirmed"] is True

def test_env_still_active_warns(tmp_path: Path, monkeypatch) -> None:
    data = _seed_closed(tmp_path)
    monkeypatch.setenv("LSR_V2_THIRD_TRADE_CLOSE_ENABLE", "1")
    report = build_lsr_v2_third_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == ENV_STILL_ACTIVE_DECISION
    assert report["close_env_absent"] is False
    assert "close_operator_env_still_present" in report["blockers"]


def test_open_position_after_close_warns_not_flat(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, open_position=True)
    report = build_lsr_v2_third_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == STATE_NOT_FLAT_DECISION
    assert report["flat_state_confirmed"] is False
    assert report["open_third_lsr_v2_positions_after"] == 1


def test_missing_backups_warns(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, backups=False)
    report = build_lsr_v2_third_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == BACKUP_MISSING_DECISION
    assert report["backups_present"] is False


def test_submit_or_reentry_after_close_rejects(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, submit_count=1)
    report = build_lsr_v2_third_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == SAFETY_FAILED_DECISION
    assert report["no_submit_or_reentry"] is False
    assert "submit_or_reentry_detected" in report["blockers"]
