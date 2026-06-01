from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_open_position_monitor import (
    CLOSE_REQUIRED_DECISION,
    EVENT_TYPE,
    JSONL_NAME,
    POSITION_NOT_FOUND_DECISION,
    READY_DECISION,
    REPORT_NAME,
    STATE_INCONSISTENT_DECISION,
    build_lsr_v2_second_open_position_monitor_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _execution_event(cycle_id: str = "pc_second", order_id: str = "ord_second") -> dict:
    return {
        "event_type": "LSR_V2_SECOND_TRADE_SUBMIT_EXECUTION",
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "order_id": order_id,
        "candidate_id": "cand_second",
        "trade_ordinal": 2,
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "take_profit": 110.0,
        "position_size": 0.5,
        "notional": 50.0,
        "risk_amount": 2.5,
        "orders_submitted_by_second_trade_execution": 1,
        "positions_opened_by_second_trade_execution": 1,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "payload": {
            "cycle_id": cycle_id,
            "symbol": "BTC/USDT",
            "side": "BUY",
            "order_id": order_id,
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "position_size": 0.5,
            "notional": 50.0,
            "risk_amount": 2.5,
        },
    }


def _paper_state(cycle_id: str = "pc_second", order_id: str = "ord_second", position_id: str = "pos_second", *, status: str = "OPEN") -> dict:
    return {
        "balance": 1000.0,
        "orders": {
            order_id: {
                "order_id": order_id,
                "symbol": "BTC/USDT",
                "side": "BUY",
                "status": "FILLED",
                "cycle_id": cycle_id,
                "paper_order_source": "lsr_v2_second_trade_submit_execution",
                "trade_ordinal": 2,
                "metadata": {"cycle_id": cycle_id, "paper_order_source": "lsr_v2_second_trade_submit_execution", "trade_ordinal": 2},
            }
        },
        "positions": {
            position_id: {
                "position_id": position_id,
                "order_id": order_id,
                "symbol": "BTC/USDT",
                "side": "BUY",
                "status": status,
                "open": status == "OPEN",
                "cycle_id": cycle_id,
                "opened_at": "2026-05-29T10:00:00+00:00",
                "entry_price": 100.0,
                "current_price": 100.0,
                "stop_loss": 95.0,
                "take_profit": 110.0,
                "position_size": 0.5,
                "notional": 50.0,
                "risk_amount": 2.5,
                "paper_order_source": "lsr_v2_second_trade_submit_execution",
                "trade_ordinal": 2,
                "metadata": {"cycle_id": cycle_id, "paper_order_source": "lsr_v2_second_trade_submit_execution", "trade_ordinal": 2, "order_id": order_id},
            }
        },
    }


def _seed(tmp_path: Path, *, current_price: float = 102.0, status_open_positions: int = 1, with_position: bool = True, position_status: str = "OPEN") -> None:
    cycle_id = "pc_second"
    _write_jsonl(tmp_path / "lsr_v2_second_trade_submit_execution.jsonl", [_execution_event(cycle_id)])
    _write_json(tmp_path / "lsr_v2_second_trade_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": cycle_id,
        "orders_submitted_by_second_trade_execution": 1,
        "positions_opened_by_second_trade_execution": 1,
        "total_notional": 50.0,
        "total_risk_amount": 2.5,
    })
    state = _paper_state(cycle_id, status=position_status)
    if not with_position:
        state["positions"] = {}
    _write_json(tmp_path / "paper_state.json", state)
    _write_json(tmp_path / "paper_status.json", {"open_positions": status_open_positions, "pending_orders": 0})
    _write_jsonl(tmp_path / "paper_events.jsonl", [
        {"event_type": "ASSET_SCANNED", "cycle_id": cycle_id, "symbol": "BTC/USDT", "last_price": current_price, "timeframe": "5m", "ts": "2026-05-29T10:05:00+00:00"}
    ])


def test_second_open_position_monitor_ready(tmp_path: Path) -> None:
    _seed(tmp_path, current_price=102.0)

    report = build_lsr_v2_second_open_position_monitor_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_second"
    assert report["second_trade_position_open"] is True
    assert report["open_second_lsr_v2_position_count"] == 1
    assert report["paper_state_consistency"] is True
    assert report["paper_status_consistency"] is True
    assert report["close_required_diagnostic"] is False
    assert report["orders_submitted_by_second_open_position_monitor"] == 0
    assert (tmp_path / REPORT_NAME).exists()
    assert (tmp_path / JSONL_NAME).exists()
    events = [json.loads(line) for line in (tmp_path / JSONL_NAME).read_text().splitlines()]
    assert events[0]["event_type"] == EVENT_TYPE


def test_take_profit_hit_is_diagnostic_only(tmp_path: Path) -> None:
    _seed(tmp_path, current_price=111.0)

    report = build_lsr_v2_second_open_position_monitor_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == CLOSE_REQUIRED_DECISION
    assert report["take_profit_hit_diagnostic_count"] == 1
    assert report["stop_hit_diagnostic_count"] == 0
    assert report["close_required_diagnostic"] is True
    assert report["broker_close_called_by_second_open_position_monitor"] is False
    assert report["positions_closed_by_second_open_position_monitor"] == 0


def test_stop_hit_is_diagnostic_only(tmp_path: Path) -> None:
    _seed(tmp_path, current_price=94.0)

    report = build_lsr_v2_second_open_position_monitor_report_from_files(data_dir=tmp_path)

    assert report["decision"] == CLOSE_REQUIRED_DECISION
    assert report["stop_hit_diagnostic_count"] == 1
    assert report["take_profit_hit_diagnostic_count"] == 0
    assert report["automatic_close_enabled"] is False


def test_status_mismatch_returns_state_inconsistent(tmp_path: Path) -> None:
    _seed(tmp_path, current_price=102.0, status_open_positions=0)

    report = build_lsr_v2_second_open_position_monitor_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert report["paper_status_consistency"] is False
    assert "paper_status_inconsistent" in report["blockers"]


def test_missing_position_returns_not_found(tmp_path: Path) -> None:
    _seed(tmp_path, current_price=102.0, status_open_positions=0, with_position=False)

    report = build_lsr_v2_second_open_position_monitor_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert report["open_second_lsr_v2_position_count"] == 0
    assert report["orders_submitted_by_second_open_position_monitor"] == 0


def test_monitor_does_not_mutate_state_or_status(tmp_path: Path) -> None:
    _seed(tmp_path, current_price=102.0)
    before_state = (tmp_path / "paper_state.json").read_text(encoding="utf-8")
    before_status = (tmp_path / "paper_status.json").read_text(encoding="utf-8")

    report = build_lsr_v2_second_open_position_monitor_report_from_files(data_dir=tmp_path)

    assert report["broker_submit_called_by_second_open_position_monitor"] is False
    assert report["broker_close_called_by_second_open_position_monitor"] is False
    assert (tmp_path / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (tmp_path / "paper_status.json").read_text(encoding="utf-8") == before_status
