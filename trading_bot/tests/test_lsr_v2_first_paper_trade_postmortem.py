from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_first_paper_trade_postmortem import (
    PASS_DECISION,
    INCOMPLETE_DECISION,
    RESIDUAL_POSITION_DECISION,
    PNL_RECONCILIATION_DECISION,
    EXTRA_SUBMIT_DECISION,
    build_lsr_v2_first_paper_trade_postmortem_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed(tmp_path: Path, *, residual_open: bool = False, pnl: float = 9.6473057196, submit_events: int = 1, final_missing: bool = False) -> Path:
    data = tmp_path / "data"
    cycle = "pc_postmortem"
    submit_event = {
        "event_type": "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
        "cycle_id": cycle,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
        "broker_submit_called": True,
        "source": "lsr_v2_supervised_paper_submit_execution",
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
    }
    _write_jsonl(data / "lsr_v2_supervised_paper_submit_execution.jsonl", [submit_event] * submit_events)
    _write_json(data / "lsr_v2_supervised_paper_submit_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED",
        "cycle_id": cycle,
        "execution_events": submit_events,
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
        "broker_submit_called": True,
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_json(data / "lsr_v2_supervised_paper_close_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SINGLE_PAPER_POSITION_CLOSED",
        "cycle_id": cycle,
        "close_execution_events": 1,
        "positions_closed_by_lsr_v2_close_execution": 1,
        "paper_close_called": True,
        "broker_close_called": True,
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
        "realized_pnl_total": pnl,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_jsonl(data / "lsr_v2_supervised_paper_close_execution.jsonl", [{
        "event_type": "LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION",
        "cycle_id": cycle,
        "positions_closed_by_lsr_v2_close_execution": 1,
        "realized_pnl_total": pnl,
        "total_risk_amount": 2.5,
        "source": "lsr_v2_supervised_paper_close_execution",
    }])
    _write_json(data / "lsr_v2_paper_position_lifecycle_report.json", {
        "cycle_id": cycle,
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_POSITION_CLOSED_AUDIT_REQUIRED",
        "open_lsr_v2_position_count": 1 if residual_open else 0,
        "closed_lsr_v2_position_count": 1,
        "paper_state_consistency": not residual_open,
        "paper_status_consistency": not residual_open,
        "paper_status_open_positions": 1 if residual_open else 0,
    })
    _write_json(data / "lsr_v2_open_position_monitor_report.json", {"cycle_id": cycle, "open_lsr_v2_position_count": 0, "decision": "KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND"})
    _write_json(data / "lsr_v2_supervised_paper_close_preflight_report.json", {"cycle_id": cycle, "close_preflight_events": 1, "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"]})
    _write_json(data / "lsr_v2_paper_status_reconciliation_report.json", {"cycle_id": cycle, "sync_required_after": False})

    final = {
        "status": "PASS",
        "decision": "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS",
        "cycle_id": cycle,
        "closed_trade_complete": True,
        "submit_executed": True,
        "submit_execution_events": submit_events,
        "close_executed": True,
        "close_execution_events": 1,
        "realized_pnl_total": pnl,
        "realized_r": round(pnl / 2.5, 10) if pnl else 0.0,
        "total_risk_amount": 2.5,
        "total_notional": 894.7190629227,
        "pnl_reconciliation_ok": True,
        "state_open_lsr_v2_positions": 1 if residual_open else 0,
        "state_closed_lsr_v2_positions": 1,
        "paper_status_open_positions": 1 if residual_open else 0,
        "paper_status_pending_orders": 0,
        "paper_state_consistency": not residual_open,
        "paper_status_consistency": not residual_open,
        "residual_open_position": residual_open,
        "extra_submit_or_reentry_detected": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
    }
    if not final_missing:
        _write_json(data / "lsr_v2_closed_trade_final_audit_report.json", final)
        _write_jsonl(data / "lsr_v2_closed_trade_final_audit.jsonl", [{"event_type": "LSR_V2_CLOSED_TRADE_FINAL_AUDIT", **final}])

    positions = {
        "pos_1": {
            "position_id": "pos_1",
            "cycle_id": cycle,
            "symbol": "BTC/USDT",
            "side": "BUY",
            "status": "OPEN" if residual_open else "CLOSED",
            "open": residual_open,
            "source": "lsr_v2_supervised_paper_submit_execution",
        }
    }
    _write_json(data / "paper_state.json", {"balance": 1000 + pnl, "realized_pnl": pnl, "orders": {}, "positions": positions})
    _write_json(data / "paper_status.json", {"open_positions": 1 if residual_open else 0, "pending_orders": 0, "position_monitor": {"open_position_count": 1 if residual_open else 0}})
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": cycle}])
    return data


def test_postmortem_pass(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    report = build_lsr_v2_first_paper_trade_postmortem_report_from_files(data_dir=data)
    assert report["decision"] == PASS_DECISION
    assert report["postmortem_complete"] is True
    assert report["next_step_observation_required"] is True
    assert report["second_trade_allowed"] is False
    assert report["realized_r"] == 3.8589222878
    assert report["orders_submitted_by_postmortem"] == 0
    assert report["paper_state_modified_by_postmortem"] is False
    assert (data / "lsr_v2_first_paper_trade_postmortem_report.json").exists()


def test_missing_final_audit_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, final_missing=True)
    report = build_lsr_v2_first_paper_trade_postmortem_report_from_files(data_dir=data)
    assert report["decision"] == INCOMPLETE_DECISION
    assert "required_reports_missing" in report["blockers"]


def test_residual_position_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, residual_open=True)
    report = build_lsr_v2_first_paper_trade_postmortem_report_from_files(data_dir=data)
    assert report["decision"] == RESIDUAL_POSITION_DECISION
    assert report["residual_open_position"] is True


def test_pnl_reconciliation_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    final = json.loads((data / "lsr_v2_closed_trade_final_audit_report.json").read_text())
    final["realized_r"] = 999
    _write_json(data / "lsr_v2_closed_trade_final_audit_report.json", final)
    report = build_lsr_v2_first_paper_trade_postmortem_report_from_files(data_dir=data)
    assert report["decision"] == PNL_RECONCILIATION_DECISION
    assert "pnl_reconciliation_required" in report["blockers"]


def test_extra_submit_or_reentry_blocks(tmp_path: Path) -> None:
    data = _seed(tmp_path, submit_events=2)
    final = json.loads((data / "lsr_v2_closed_trade_final_audit_report.json").read_text())
    final["submit_execution_events"] = 2
    _write_json(data / "lsr_v2_closed_trade_final_audit_report.json", final)
    report = build_lsr_v2_first_paper_trade_postmortem_report_from_files(data_dir=data)
    assert report["decision"] == EXTRA_SUBMIT_DECISION
    assert report["extra_submit_or_reentry_detected"] is True


def test_live_flag_rejects(tmp_path: Path) -> None:
    data = _seed(tmp_path)
    submit = json.loads((data / "lsr_v2_supervised_paper_submit_execution_report.json").read_text())
    submit["live_enabled"] = True
    _write_json(data / "lsr_v2_supervised_paper_submit_execution_report.json", submit)
    report = build_lsr_v2_first_paper_trade_postmortem_report_from_files(data_dir=data)
    assert report["status"] == "FAIL"
    assert "unsafe_flag_detected" in report["blockers"]
