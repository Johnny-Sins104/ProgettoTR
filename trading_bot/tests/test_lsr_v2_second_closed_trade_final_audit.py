from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_closed_trade_final_audit import (
    PASS_DECISION,
    RESIDUAL_POSITION_DECISION,
    PNL_RECONCILIATION_DECISION,
    THIRD_SUBMIT_DECISION,
    STATE_INCOMPLETE_DECISION,
    build_lsr_v2_second_closed_trade_final_audit_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed_closed(tmp_path: Path, *, open_position: bool = False, submit_events: int = 1, close_events: int = 1, realized_pnl: float = 11.495718971) -> Path:
    data = tmp_path / "data"
    cycle_id = "pc_second_closed"
    submit_row = {
        "event_type": "LSR_V2_SECOND_TRADE_SUBMIT_EXECUTION",
        "decision": "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": cycle_id,
        "order_id": "ord_second",
        "position_id": "pos_second",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "broker_submit_called": True,
        "orders_submitted_by_second_trade_execution": 1,
        "positions_opened_by_second_trade_execution": 1,
        "total_risk_amount": 2.5,
        "total_notional": 894.7190629227,
    }
    close_row = {
        "event_type": "LSR_V2_SECOND_TRADE_CLOSE_EXECUTION",
        "decision": "LSR_V2_SECOND_SINGLE_PAPER_POSITION_CLOSED",
        "cycle_id": cycle_id,
        "order_id": "ord_second",
        "position_id": "pos_second",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "broker_close_called": True,
        "positions_closed_by_second_trade_close_execution": 1,
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
        "realized_pnl_total": realized_pnl,
        "total_risk_amount": 2.5,
        "total_notional": 894.7190629227,
    }
    _write_jsonl(data / "lsr_v2_second_trade_submit_execution.jsonl", [dict(submit_row, order_id=f"ord_second_{i}") for i in range(submit_events)])
    _write_jsonl(data / "lsr_v2_second_trade_close_execution.jsonl", [dict(close_row, position_id=f"pos_second_{i}") for i in range(close_events)])
    _write_json(data / "lsr_v2_second_trade_submit_execution_report.json", submit_row)
    _write_json(data / "lsr_v2_second_trade_close_execution_report.json", close_row)
    _write_json(data / "paper_state.json", {
        "orders": {
            "ord_second": {
                "order_id": "ord_second",
                "position_id": "pos_second",
                "cycle_id": cycle_id,
                "symbol": "BTC/USDT",
                "side": "BUY",
                "source": "lsr_v2_second_trade_submit_execution",
                "status": "FILLED",
                "trade_sequence": "SECOND",
            }
        },
        "positions": {
            "pos_second": {
                "position_id": "pos_second",
                "order_id": "ord_second",
                "cycle_id": cycle_id,
                "symbol": "BTC/USDT",
                "side": "BUY",
                "source": "lsr_v2_second_trade_submit_execution",
                "status": "OPEN" if open_position else "CLOSED",
                "open": bool(open_position),
                "trade_sequence": "SECOND",
                "realized_pnl": realized_pnl,
                "notional": 894.7190629227,
                "risk_amount": 2.5,
            }
        },
    })
    _write_json(data / "paper_status.json", {"open_positions": 1 if open_position else 0, "pending_orders": 0})
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": cycle_id}])
    return data


def test_second_closed_trade_final_audit_passes(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path)
    report = build_lsr_v2_second_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["second_closed_trade_complete"] is True
    assert report["submit_execution_events"] == 1
    assert report["close_execution_events"] == 1
    assert report["realized_pnl_total"] == 11.495718971
    assert report["realized_r"] == round(11.495718971 / 2.5, 10)
    assert report["residual_open_position"] is False
    assert report["third_submit_or_reentry_detected"] is False
    assert report["orders_submitted_by_second_final_audit"] == 0
    assert report["positions_opened_by_second_final_audit"] == 0
    assert report["positions_closed_by_second_final_audit"] == 0
    assert report["paper_state_modified_by_second_final_audit"] is False
    assert report["paper_status_modified_by_second_final_audit"] is False


def test_residual_open_position_warns(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, open_position=True)
    report = build_lsr_v2_second_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == THIRD_SUBMIT_DECISION or report["decision"] == RESIDUAL_POSITION_DECISION
    assert report["residual_open_position"] is True
    assert report["state_open_second_lsr_v2_positions"] == 1


def test_missing_close_execution_warns_state_incomplete(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, close_events=0)
    (data / "lsr_v2_second_trade_close_execution_report.json").write_text("{}\n", encoding="utf-8")
    report = build_lsr_v2_second_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] in {STATE_INCOMPLETE_DECISION, PNL_RECONCILIATION_DECISION}
    assert report["close_executed"] is False


def test_zero_pnl_warns_reconciliation_required(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, realized_pnl=0.0)
    report = build_lsr_v2_second_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == PNL_RECONCILIATION_DECISION
    assert report["pnl_reconciliation_ok"] is False


def test_multiple_submit_detects_third_submit_or_reentry(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, submit_events=2)
    report = build_lsr_v2_second_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == THIRD_SUBMIT_DECISION
    assert report["submit_multiple_detected"] is True
    assert report["third_submit_or_reentry_detected"] is True


def test_live_flag_rejects(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path)
    close_report = json.loads((data / "lsr_v2_second_trade_close_execution_report.json").read_text())
    close_report["live_enabled"] = True
    _write_json(data / "lsr_v2_second_trade_close_execution_report.json", close_report)
    report = build_lsr_v2_second_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == "REJECT_LSR_V2_SECOND_CLOSED_TRADE_AUDIT_FAILED"
