from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_trade_position_lifecycle import (
    EVENT_TYPE,
    EXECUTION_EVENT_TYPE,
    JSONL_NAME,
    POSITION_NOT_FOUND_DECISION,
    READY_DECISION,
    REPORT_NAME,
    STATE_INCONSISTENT_DECISION,
    THIRD_SUBMIT_DETECTED_DECISION,
    build_lsr_v2_second_trade_position_lifecycle_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _execution_event(cycle_id: str = "pc_second", order_id: str = "ord_second") -> dict:
    return {
        "event_type": EXECUTION_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "candidate_id": "cand_second",
        "order_id": order_id,
        "trade_ordinal": 2,
        "entry_price": 72771.64,
        "stop_loss": 72568.303436,
        "take_profit": 73178.313128,
        "position_size": 0.012295,
        "notional": 894.7190629227,
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
            "candidate_id": "cand_second",
            "entry_price": 72771.64,
            "stop_loss": 72568.303436,
            "take_profit": 73178.313128,
            "position_size": 0.012295,
            "notional": 894.7190629227,
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
                "entry_price": 72771.64,
                "current_price": 72771.64,
                "stop_loss": 72568.303436,
                "take_profit": 73178.313128,
                "position_size": 0.012295,
                "notional": 894.7190629227,
                "risk_amount": 2.5,
                "paper_order_source": "lsr_v2_second_trade_submit_execution",
                "trade_ordinal": 2,
                "metadata": {"cycle_id": cycle_id, "paper_order_source": "lsr_v2_second_trade_submit_execution", "trade_ordinal": 2, "order_id": order_id},
            }
        },
    }


def _write_base(tmp_path: Path, *, cycle_id: str = "pc_second", status_open_positions: int = 1, with_position: bool = True, events: list[dict] | None = None) -> None:
    rows = events if events is not None else [_execution_event(cycle_id)]
    _write_jsonl(tmp_path / "lsr_v2_second_trade_submit_execution.jsonl", rows)
    _write_json(tmp_path / "lsr_v2_second_trade_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": cycle_id,
        "orders_submitted_by_second_trade_execution": 1,
        "positions_opened_by_second_trade_execution": 1,
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
    })
    state = _paper_state(cycle_id)
    if not with_position:
        state["positions"] = {}
    _write_json(tmp_path / "paper_state.json", state)
    _write_json(tmp_path / "paper_status.json", {"open_positions": status_open_positions, "pending_orders": 0})
    _write_jsonl(tmp_path / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": cycle_id}])


def test_second_trade_lifecycle_ready_when_position_open_and_status_synced(tmp_path: Path) -> None:
    _write_base(tmp_path)

    report = build_lsr_v2_second_trade_position_lifecycle_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_second"
    assert report["second_trade_position_open"] is True
    assert report["open_lsr_v2_position_count"] == 1
    assert report["state_open_lsr_v2_positions"] == 1
    assert report["paper_status_open_positions"] == 1
    assert report["paper_state_consistency"] is True
    assert report["paper_status_consistency"] is True
    assert report["third_submit_or_reentry_detected"] is False
    assert report["orders_submitted_by_second_trade_lifecycle_audit"] == 0
    assert (tmp_path / REPORT_NAME).exists()
    assert (tmp_path / JSONL_NAME).exists()


def test_status_mismatch_returns_state_inconsistent(tmp_path: Path) -> None:
    _write_base(tmp_path, status_open_positions=0)

    report = build_lsr_v2_second_trade_position_lifecycle_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert report["paper_state_consistency"] is True
    assert report["paper_status_consistency"] is False
    assert "paper_status_inconsistent" in report["blockers"]


def test_missing_matching_position_is_reported(tmp_path: Path) -> None:
    _write_base(tmp_path, status_open_positions=0, with_position=False)

    report = build_lsr_v2_second_trade_position_lifecycle_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert report["matching_order_count"] == 1
    assert report["matching_position_count"] == 0


def test_third_submit_or_reentry_detected_for_multiple_second_trade_events(tmp_path: Path) -> None:
    events = [_execution_event("pc_second", "ord_a"), _execution_event("pc_second", "ord_b")]
    state = _paper_state("pc_second", "ord_a", "pos_a")
    state["orders"]["ord_b"] = dict(state["orders"]["ord_a"], order_id="ord_b")
    state["positions"]["pos_b"] = dict(state["positions"]["pos_a"], position_id="pos_b", order_id="ord_b")
    _write_jsonl(tmp_path / "lsr_v2_second_trade_submit_execution.jsonl", events)
    _write_json(tmp_path / "lsr_v2_second_trade_submit_execution_report.json", {"cycle_id": "pc_second"})
    _write_json(tmp_path / "paper_state.json", state)
    _write_json(tmp_path / "paper_status.json", {"open_positions": 2, "pending_orders": 0})

    report = build_lsr_v2_second_trade_position_lifecycle_report_from_files(data_dir=tmp_path)

    assert report["decision"] in {THIRD_SUBMIT_DETECTED_DECISION, "REJECT_LSR_V2_SECOND_POSITION_LIFECYCLE_SAFETY_FAILED"}
    assert report["third_submit_or_reentry_detected"] is True
    assert "third_submit_or_reentry_detected" in report["blockers"]


def test_closed_second_position_is_not_lifecycle_ready(tmp_path: Path) -> None:
    _write_base(tmp_path, status_open_positions=0)
    state = _paper_state(status="CLOSED")
    _write_json(tmp_path / "paper_state.json", state)

    report = build_lsr_v2_second_trade_position_lifecycle_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == "KEEP_DIAGNOSTIC_LSR_V2_SECOND_POSITION_CLOSED_AUDIT_REQUIRED"
    assert report["open_lsr_v2_position_count"] == 0
    assert report["closed_lsr_v2_position_count"] == 1


def test_module_does_not_mutate_paper_state_or_status(tmp_path: Path) -> None:
    _write_base(tmp_path)
    before_state = (tmp_path / "paper_state.json").read_text(encoding="utf-8")
    before_status = (tmp_path / "paper_status.json").read_text(encoding="utf-8")

    report = build_lsr_v2_second_trade_position_lifecycle_report_from_files(data_dir=tmp_path)

    assert report["broker_submit_called_by_second_trade_lifecycle_audit"] is False
    assert report["broker_close_called_by_second_trade_lifecycle_audit"] is False
    assert (tmp_path / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (tmp_path / "paper_status.json").read_text(encoding="utf-8") == before_status
