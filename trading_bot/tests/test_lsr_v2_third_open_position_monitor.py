from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_open_position_monitor import (
    CLOSE_REQUIRED_DECISION,
    POSITION_NOT_FOUND_DECISION,
    READY_DECISION,
    build_lsr_v2_third_open_position_monitor_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _base_data(tmp_path: Path, *, current_price: float = 72800.0, status_open: int = 1) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    cycle_id = "pc_third"
    position = {
        "symbol": "BTC/USDT",
        "side": "BUY",
        "status": "OPEN",
        "open": True,
        "entry_price": 72771.64,
        "stop_loss": 72568.303436,
        "take_profit": 73178.313128,
        "quantity": 0.0122948907,
        "notional": 894.7190629227,
        "metadata": {
            "cycle_id": cycle_id,
            "paper_order_source": "lsr_v2_third_trade_submit_execution",
            "execution_source": "lsr_v2_third_trade_submit_execution",
            "candidate_id": "cand_3",
            "risk_amount": 2.5,
            "third_trade_single_order_gate": True,
        },
    }
    order = dict(position)
    order.update({"status": "FILLED", "open": False})
    _write_json(data / "paper_state.json", {"orders": {"o3": order}, "positions": {"p3": position}})
    _write_json(data / "paper_status.json", {"open_positions": status_open, "pending_orders": 0})
    _write_json(data / "lsr_v2_third_trade_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 72771.64,
        "stop_loss": 72568.303436,
        "take_profit": 73178.313128,
        "position_size": 0.0122948907,
        "risk_amount": 2.5,
        "total_notional": 894.7190629227,
    })
    _write_json(data / "lsr_v2_third_trade_position_lifecycle_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE_READY",
        "cycle_id": cycle_id,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": 0,
    })
    _write_jsonl(data / "paper_events.jsonl", [
        {"event_type": "PRICE_SNAPSHOT", "symbol": "BTC/USDT", "cycle_id": "pc_latest", "price": current_price, "ts": "2026-01-01T00:00:00+00:00"}
    ])
    return data


def test_open_position_monitor_ready_and_non_mutating(tmp_path: Path) -> None:
    data = _base_data(tmp_path, current_price=72800.0)
    before_state = (data / "paper_state.json").read_text(encoding="utf-8")
    before_status = (data / "paper_status.json").read_text(encoding="utf-8")
    report = build_lsr_v2_third_open_position_monitor_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["open_lsr_v2_position_count"] == 1
    assert report["paper_status_open_positions"] == 1
    assert report["paper_status_consistency"] is True
    assert report["close_required_diagnostic"] is False
    assert report["positions_closed_by_third_open_position_monitor"] == 0
    assert (data / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (data / "paper_status.json").read_text(encoding="utf-8") == before_status


def test_take_profit_hit_is_warn_close_required(tmp_path: Path) -> None:
    data = _base_data(tmp_path, current_price=73200.0)
    report = build_lsr_v2_third_open_position_monitor_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == CLOSE_REQUIRED_DECISION
    assert report["close_required_diagnostic"] is True
    assert report["take_profit_hit_diagnostic_count"] == 1
    assert report["stop_hit_diagnostic_count"] == 0
    assert report["close_reasons"] == ["TAKE_PROFIT_HIT_DIAGNOSTIC"]


def test_stop_loss_hit_is_warn_close_required(tmp_path: Path) -> None:
    data = _base_data(tmp_path, current_price=72500.0)
    report = build_lsr_v2_third_open_position_monitor_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == CLOSE_REQUIRED_DECISION
    assert report["stop_hit_diagnostic_count"] == 1
    assert report["close_reasons"] == ["STOP_LOSS_HIT_DIAGNOSTIC"]


def test_no_open_position_is_warn(tmp_path: Path) -> None:
    data = _base_data(tmp_path, current_price=72800.0, status_open=0)
    state = json.loads((data / "paper_state.json").read_text(encoding="utf-8"))
    state["positions"]["p3"]["status"] = "CLOSED"
    state["positions"]["p3"]["open"] = False
    _write_json(data / "paper_state.json", state)
    report = build_lsr_v2_third_open_position_monitor_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert report["open_lsr_v2_position_count"] == 0


def test_status_inconsistency_is_warn(tmp_path: Path) -> None:
    data = _base_data(tmp_path, current_price=72800.0, status_open=0)
    report = build_lsr_v2_third_open_position_monitor_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_THIRD_MONITOR_STATE_INCONSISTENT"
    assert report["paper_status_consistency"] is False


def test_jsonl_event_contains_telegram_bridge_fields(tmp_path: Path) -> None:
    data = _base_data(tmp_path, current_price=72850.0)
    report = build_lsr_v2_third_open_position_monitor_report_from_files(data_dir=data)
    rows = [json.loads(line) for line in (data / "lsr_v2_third_open_position_monitor.jsonl").read_text(encoding="utf-8").splitlines()]
    assert report["monitor_events"] == 1
    assert len(rows) == 1
    event = rows[0]
    assert event["position_open"] is True
    assert event["symbol"] == "BTC/USDT"
    assert event["current_price"] == 72850.0
    assert event["entry_price"] == 72771.64
    assert event["stop_loss"] == 72568.303436
    assert event["take_profit"] == 73178.313128
