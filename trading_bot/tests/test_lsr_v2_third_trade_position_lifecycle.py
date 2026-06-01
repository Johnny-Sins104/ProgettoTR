from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_third_trade_position_lifecycle import (
    EVENT_TYPE,
    POSITION_CLOSED_AUDIT_REQUIRED_DECISION,
    POSITION_NOT_FOUND_DECISION,
    READY_DECISION,
    STATE_INCONSISTENT_DECISION,
    build_lsr_v2_third_trade_position_lifecycle_report_from_files,
)
EXECUTION_EVENT_TYPE = "LSR_V2_THIRD_TRADE_SUBMIT_EXECUTION"
EXECUTED_DECISION = "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _execution_event(cycle_id: str = "pc_third") -> dict:
    return {
        "event_type": EXECUTION_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "timeframe": "5m",
        "candidate_id": "BTC_third_cand",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_per_trade_pct": 0.0025,
        "risk_amount": 2.5,
        "position_size": 2.5,
        "quantity": 2.5,
        "notional": 250.0,
        "orders_submitted_by_third_trade_execution": 1,
        "positions_opened_by_third_trade_execution": 1,
        "order_submitted": True,
        "position_opened": True,
        "broker_submit_called": True,
    }


def _execution_report(cycle_id: str = "pc_third") -> dict:
    return {
        "status": "PASS",
        "decision": EXECUTED_DECISION,
        "cycle_id": cycle_id,
        "orders_submitted_by_third_trade_execution": 1,
        "positions_opened_by_third_trade_execution": 1,
    }


def _state(cycle_id: str = "pc_third", *, position_status: str = "OPEN", duplicate: bool = False) -> dict:
    metadata = {
        "cycle_id": cycle_id,
        "paper_order_source": "lsr_v2_third_trade_submit_execution",
        "execution_source": "lsr_v2_third_trade_submit_execution",
        "candidate_id": "BTC_third_cand",
        "third_trade_single_order_gate": True,
    }
    orders = {
        "po_third": {
            "order_id": "po_third",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "status": "FILLED",
            "qty": 2.5,
            "requested_price": 100.0,
            "filled_price": 100.0,
            "metadata": metadata,
        }
    }
    positions = {
        "pp_third": {
            "position_id": "pp_third",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "status": position_status,
            "qty": 2.5,
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
            "metadata": {**metadata, "source_order_id": "po_third"},
        }
    }
    if duplicate:
        positions["pp_third_dup"] = {**positions["pp_third"], "position_id": "pp_third_dup"}
    return {"orders": orders, "positions": positions, "balance": 1000.0, "realized_pnl": 0.0}


def _status(open_positions: int = 1, pending_orders: int = 0) -> dict:
    return {"open_positions": open_positions, "pending_orders": pending_orders}


def _write_base(tmp_path: Path, *, cycle_id: str = "pc_third", position_status: str = "OPEN", duplicate: bool = False, status_open: int = 1) -> None:
    _write_json(tmp_path / "lsr_v2_third_trade_submit_execution_report.json", _execution_report(cycle_id))
    _append_jsonl(tmp_path / "lsr_v2_third_trade_submit_execution.jsonl", _execution_event(cycle_id))
    _write_json(tmp_path / "paper_state.json", _state(cycle_id, position_status=position_status, duplicate=duplicate))
    _write_json(tmp_path / "paper_status.json", _status(open_positions=status_open))


def test_ready_when_third_position_is_open_and_state_matches(tmp_path: Path) -> None:
    _write_base(tmp_path)
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(data_dir=tmp_path)
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["third_trade_position_open"] is True
    assert report["matching_order_count"] == 1
    assert report["matching_position_count"] == 1
    assert report["open_lsr_v2_position_count"] == 1
    assert report["paper_state_consistency"] is True
    assert report["paper_status_consistency"] is True
    assert report["orders_submitted_by_third_trade_lifecycle_audit"] == 0


def test_missing_execution_is_warn(tmp_path: Path) -> None:
    _write_json(tmp_path / "paper_state.json", {"orders": {}, "positions": {}})
    _write_json(tmp_path / "paper_status.json", _status(open_positions=0))
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert "EXECUTION_NOT_FOUND" in report["decision"]
    assert report["third_trade_execution_events"] == 0


def test_missing_matching_position_is_warn(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_json(tmp_path / "paper_state.json", {"orders": {}, "positions": {}})
    _write_json(tmp_path / "paper_status.json", _status(open_positions=0))
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == POSITION_NOT_FOUND_DECISION
    assert report["matching_position_count"] == 0


def test_closed_position_requires_closed_audit(tmp_path: Path) -> None:
    _write_base(tmp_path, position_status="CLOSED", status_open=0)
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == POSITION_CLOSED_AUDIT_REQUIRED_DECISION
    assert report["closed_lsr_v2_position_count"] == 1
    assert report["open_lsr_v2_position_count"] == 0


def test_status_mismatch_is_warn(tmp_path: Path) -> None:
    _write_base(tmp_path, status_open=0)
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert report["paper_status_consistency"] is False


def test_duplicate_position_is_warn(tmp_path: Path) -> None:
    _write_base(tmp_path, duplicate=True, status_open=2)
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(data_dir=tmp_path)
    assert report["status"] == "WARN"
    assert report["decision"] == STATE_INCONSISTENT_DECISION
    assert report["duplicate_position_check"] is False
    assert report["fourth_submit_or_reentry_detected"] is True


def test_writes_report_and_jsonl_without_state_mutation(tmp_path: Path) -> None:
    _write_base(tmp_path)
    before_state = (tmp_path / "paper_state.json").read_text(encoding="utf-8")
    before_status = (tmp_path / "paper_status.json").read_text(encoding="utf-8")
    report = build_lsr_v2_third_trade_position_lifecycle_report_from_files(data_dir=tmp_path)
    assert (tmp_path / "lsr_v2_third_trade_position_lifecycle_report.json").exists()
    assert (tmp_path / "lsr_v2_third_trade_position_lifecycle.jsonl").exists()
    assert (tmp_path / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (tmp_path / "paper_status.json").read_text(encoding="utf-8") == before_status
    assert report["paper_state_modified_by_third_trade_lifecycle_audit"] is False
    assert report["paper_status_modified_by_third_trade_lifecycle_audit"] is False
