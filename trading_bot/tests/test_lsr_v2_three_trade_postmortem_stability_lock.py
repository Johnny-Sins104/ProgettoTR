from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_three_trade_postmortem_stability_lock import (
    ENV_ACTIVE_DECISION,
    FAILED_DECISION,
    FOURTH_OR_REENTRY_DECISION,
    INCOMPLETE_DECISION,
    PASS_DECISION,
    PNL_RECONCILIATION_DECISION,
    STATE_NOT_FLAT_DECISION,
    build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed(tmp_path: Path, *, open_position: bool = False, pending_order: bool = False, third_pnl: float = 7.9796273011, live: bool = False, missing_third_final: bool = False) -> Path:
    data = tmp_path / "data"
    first = {
        "status": "PASS",
        "decision": "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS",
        "cycle_id": "pc_first",
        "submit_execution_events": 1,
        "close_execution_events": 1,
        "realized_pnl_total": 9.6473057196,
        "total_risk_amount": 2.5,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    first_pm = {
        "status": "PASS",
        "decision": "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS",
        "cycle_id": "pc_first",
        "realized_pnl_total": 9.6473057196,
        "total_risk_amount": 2.5,
        "extra_submit_or_reentry_detected": False,
    }
    second = {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS",
        "cycle_id": "pc_second",
        "submit_execution_events": 1,
        "close_execution_events": 1,
        "realized_pnl_total": 6.127404602,
        "total_risk_amount": 2.5,
        "third_submit_or_reentry_detected": False,
        "live_enabled": live,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    two = {
        "status": "PASS",
        "decision": "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS",
        "cycle_ids": ["pc_first", "pc_second"],
        "submit_execution_events_total": 2,
        "close_execution_events_total": 2,
        "third_trade_locked": True,
        "total_realized_pnl": 15.7747103216,
        "total_risk_amount": 5.0,
    }
    third_submit = {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": "pc_third",
        "execution_events": 1,
        "positions_opened_by_third_trade_execution": 1,
        "orders_submitted_by_third_trade_execution": 0,
        "total_risk_amount": 2.5,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    third_lifecycle = {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE_READY",
        "cycle_id": "pc_third",
        "fourth_submit_or_reentry_detected": False,
    }
    third_preflight = {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_TRADE_CLOSE_PREFLIGHT_READY",
        "cycle_id": "pc_third",
        "would_prepare_close_count": 1,
        "would_close_position_count": 0,
        "total_risk_amount": 2.5,
    }
    third_close = {
        "status": "WARN",
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_THIRD_POSITION_NOT_FOUND",
        "cycle_id": "pc_third",
        "close_execution_events": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    third_final = {
        "status": "PASS",
        "decision": "LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT_READY",
        "cycle_id": "pc_third",
        "closed_trade_confirmed": True,
        "flat_state_confirmed": True,
        "paper_state_status_consistency": True,
        "close_execution_events": 1,
        "realized_pnl_total": third_pnl,
        "realized_pnl_after": 15.7747103216 + third_pnl,
        "balance_after": 1000.0 + 15.7747103216 + third_pnl,
        "no_submit_or_reentry": True,
        "new_order_created_after_close": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    _write_json(data / "lsr_v2_closed_trade_final_audit_report.json", first)
    _write_json(data / "lsr_v2_first_paper_trade_postmortem_report.json", first_pm)
    _write_json(data / "lsr_v2_second_closed_trade_final_audit_report.json", second)
    _write_json(data / "lsr_v2_two_trade_paper_cycle_postmortem_report.json", two)
    _write_json(data / "lsr_v2_third_trade_submit_execution_report.json", third_submit)
    _write_json(data / "lsr_v2_third_trade_position_lifecycle_report.json", third_lifecycle)
    _write_json(data / "lsr_v2_third_trade_close_preflight_report.json", third_preflight)
    _write_json(data / "lsr_v2_third_trade_close_execution_report.json", third_close)
    if not missing_third_final:
        _write_json(data / "lsr_v2_third_closed_trade_final_audit_report.json", third_final)
    _write_json(
        data / "paper_state.json",
        {
            "balance": 1000.0 + 15.7747103216 + third_pnl,
            "realized_pnl": 15.7747103216 + third_pnl,
            "positions": {
                "pos_third": {
                    "source": "lsr_v2_third_trade_submit_execution",
                    "cycle_id": "pc_third",
                    "status": "OPEN" if open_position else "CLOSED",
                    "open": open_position,
                    "trade_sequence": "THIRD",
                    "trade_ordinal": 3,
                }
            },
            "orders": {
                "ord_pending": {
                    "source": "lsr_v2_third_trade_submit_execution",
                    "cycle_id": "pc_third",
                    "status": "PENDING" if pending_order else "FILLED",
                    "pending": pending_order,
                }
            } if pending_order else {},
        },
    )
    _write_json(data / "paper_status.json", {"open_positions": 1 if open_position else 0, "pending_orders": 1 if pending_order else 0})
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_third"}])
    return data


def test_three_trade_postmortem_passes_and_locks_fourth_trade(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == PASS_DECISION
    assert report["three_trade_postmortem_complete"] is True
    assert report["submit_execution_events_total"] == 3
    assert report["close_execution_events_total"] == 3
    assert report["flat_state_confirmed"] is True
    assert report["fourth_trade_allowed"] is False
    assert report["fourth_trade_locked"] is True
    assert report["stability_lock_active"] is True
    assert report["orders_submitted_by_three_trade_postmortem"] == 0
    assert report["paper_state_modified_by_three_trade_postmortem"] is False


def test_residual_open_position_warns(tmp_path: Path) -> None:
    data = _seed(tmp_path, open_position=True)
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=data)
    assert report["decision"] in {STATE_NOT_FLAT_DECISION, FOURTH_OR_REENTRY_DECISION}
    assert report["flat_state_confirmed"] is False
    assert report["fourth_submit_or_reentry_detected"] is True


def test_pending_order_warns_as_fourth_or_reentry(tmp_path: Path) -> None:
    data = _seed(tmp_path, pending_order=True)
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=data)
    assert report["decision"] == FOURTH_OR_REENTRY_DECISION
    assert report["pending_orders_after"] == 1


def test_zero_third_pnl_warns(tmp_path: Path) -> None:
    data = _seed(tmp_path, third_pnl=0.0)
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=data)
    assert report["decision"] == PNL_RECONCILIATION_DECISION
    assert report["pnl_reconciliation_ok"] is False


def test_missing_third_final_warns_incomplete(tmp_path: Path) -> None:
    data = _seed(tmp_path, missing_third_final=True)
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=data)
    assert report["status"] == "WARN"
    assert report["decision"] == INCOMPLETE_DECISION
    assert "third_closed_trade_final_audit_not_pass" in report["blockers"]


def test_active_operator_env_warns(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.setenv("LSR_V2_FOURTH_TRADE_SUBMIT_ARM", "1")
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=data)
    assert report["decision"] == ENV_ACTIVE_DECISION
    assert report["operator_env_absent"] is False


def test_live_flag_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path, live=True)
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert report["decision"] == FAILED_DECISION
