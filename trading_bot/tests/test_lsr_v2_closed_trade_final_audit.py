from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_closed_trade_final_audit import (
    PASS_DECISION,
    INCOMPLETE_DECISION,
    RESIDUAL_POSITION_DECISION,
    PNL_RECONCILIATION_DECISION,
    EXTRA_SUBMIT_DECISION,
    build_lsr_v2_closed_trade_final_audit_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def _seed_closed(tmp_path: Path, *, residual_open: bool = False, pnl: float = 9.6473057196, submit_events: int = 1) -> Path:
    data = tmp_path / "data"
    cycle = "pc_closed"
    submit_event = {
        "event_type": "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
        "cycle_id": cycle,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 72771.64,
        "stop_loss": 72568.303436,
        "take_profit": 73178.313128,
        "position_size": 0.012295,
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
        "orders_submitted_by_lsr_v2_execution": 1,
        "positions_opened_by_lsr_v2_execution": 1,
        "broker_submit_called": True,
        "source": "lsr_v2_supervised_paper_submit_execution",
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
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 72771.64,
        "stop_loss": 72568.303436,
        "take_profit": 73178.313128,
        "position_size": 0.012295,
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    _write_json(data / "lsr_v2_supervised_paper_submit_report.json", {"cycle_id": cycle, "submit_ready_count": 1})
    _write_json(data / "lsr_v2_supervised_paper_submit_preflight_report.json", {"cycle_id": cycle, "would_prepare_submit_count": 1})
    _write_json(data / "lsr_v2_paper_broker_handoff_dry_run_report.json", {"cycle_id": cycle, "payload_valid_count": 1})
    _write_json(data / "lsr_v2_order_intent_audit_report.json", {"cycle_id": cycle, "order_intent_events": 1})

    monitor_event = {
        "event_type": "LSR_V2_OPEN_POSITION_MONITOR",
        "cycle_id": cycle,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 72771.64,
        "current_price": 73556.3,
        "stop_loss": 72568.303436,
        "take_profit": 73178.313128,
        "position_size": 0.012295,
        "notional": 894.7190629227,
        "risk_amount": 2.5,
        "take_profit_hit_diagnostic": True,
        "close_required_diagnostic": True,
    }
    _write_jsonl(data / "lsr_v2_open_position_monitor.jsonl", [monitor_event])
    _write_json(data / "lsr_v2_open_position_monitor_report.json", {
        "cycle_id": cycle,
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND" if not residual_open else "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_REQUIRED_DIAGNOSTIC",
        "open_lsr_v2_position_count": 1 if residual_open else 0,
        "take_profit_hit_diagnostic_count": 1,
        "close_required_diagnostic_count": 1,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
    })

    _write_json(data / "lsr_v2_supervised_paper_close_preflight_report.json", {
        "cycle_id": cycle,
        "decision": "LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT_READY",
        "close_preflight_events": 1,
        "take_profit_hit_diagnostic_count": 1,
        "close_required_diagnostic_count": 1,
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
    })
    _write_jsonl(data / "lsr_v2_supervised_paper_close_preflight.jsonl", [{"event_type": "LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT", "cycle_id": cycle, "close_reason": "TAKE_PROFIT_HIT_DIAGNOSTIC"}])

    close_event = {
        "event_type": "LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION",
        "cycle_id": cycle,
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 72771.64,
        "close_price": 73556.3,
        "stop_loss": 72568.303436,
        "take_profit": 73178.313128,
        "position_size": 0.012295,
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
        "realized_pnl_total": pnl,
        "positions_closed_by_lsr_v2_close_execution": 1,
        "paper_close_called": True,
        "broker_close_called": True,
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
    }
    _write_jsonl(data / "lsr_v2_supervised_paper_close_execution.jsonl", [close_event])
    _write_json(data / "lsr_v2_supervised_paper_close_execution_report.json", {
        "status": "PASS",
        "decision": "LSR_V2_SINGLE_PAPER_POSITION_CLOSED",
        "cycle_id": cycle,
        "close_execution_events": 1,
        "positions_closed_by_lsr_v2_close_execution": 1,
        "open_lsr_v2_positions_after": 1 if residual_open else 0,
        "paper_status_open_positions_after": 1 if residual_open else 0,
        "paper_close_called": True,
        "broker_close_called": True,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
        "close_reasons": ["TAKE_PROFIT_HIT_DIAGNOSTIC"],
        "total_notional": 894.7190629227,
        "total_risk_amount": 2.5,
        "realized_pnl_total": pnl,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })

    _write_jsonl(data / "lsr_v2_paper_position_lifecycle.jsonl", [{"event_type": "LSR_V2_PAPER_POSITION_LIFECYCLE", "cycle_id": cycle, "current_status": "CLOSED"}])
    _write_json(data / "lsr_v2_paper_position_lifecycle_report.json", {
        "cycle_id": cycle,
        "decision": "KEEP_DIAGNOSTIC_LSR_V2_POSITION_CLOSED_AUDIT_REQUIRED",
        "open_lsr_v2_position_count": 1 if residual_open else 0,
        "closed_lsr_v2_position_count": 1,
        "paper_state_consistency": not residual_open,
        "paper_status_consistency": not residual_open,
        "paper_status_open_positions": 1 if residual_open else 0,
        "symbols": ["BTC/USDT"],
        "sides": ["BUY"],
    })

    positions = {}
    if residual_open:
        positions["pos_1"] = {
            "position_id": "pos_1",
            "cycle_id": cycle,
            "symbol": "BTC/USDT",
            "side": "BUY",
            "status": "OPEN",
            "open": True,
            "source": "lsr_v2_supervised_paper_submit_execution",
        }
    else:
        positions["pos_1"] = {
            "position_id": "pos_1",
            "cycle_id": cycle,
            "symbol": "BTC/USDT",
            "side": "BUY",
            "status": "CLOSED",
            "open": False,
            "source": "lsr_v2_supervised_paper_submit_execution",
        }
    _write_json(data / "paper_state.json", {"balance": 1000.0 + pnl, "realized_pnl": pnl, "orders": {}, "positions": positions})
    _write_json(data / "paper_status.json", {"open_positions": 1 if residual_open else 0, "pending_orders": 0, "realized_pnl": pnl, "position_monitor": {"open_position_count": 1 if residual_open else 0, "positions": []}})
    _write_jsonl(data / "paper_events.jsonl", [{"event_type": "CYCLE_COMPLETED", "cycle_id": cycle}])
    return data


def test_closed_trade_audit_pass(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path)
    report = build_lsr_v2_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == PASS_DECISION
    assert report["closed_trade_complete"] is True
    assert report["residual_open_position"] is False
    assert report["realized_pnl_total"] == 9.6473057196
    assert report["realized_r"] == 3.8589222878
    assert report["orders_submitted_by_final_audit"] == 0
    assert report["positions_closed_by_final_audit"] == 0
    assert (data / "lsr_v2_closed_trade_final_audit_report.json").exists()


def test_missing_submit_report_is_incomplete(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path)
    (data / "lsr_v2_supervised_paper_submit_execution_report.json").unlink()
    report = build_lsr_v2_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == INCOMPLETE_DECISION
    assert "required_reports_missing" in report["blockers"]


def test_residual_open_position_blocks(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, residual_open=True)
    report = build_lsr_v2_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == RESIDUAL_POSITION_DECISION
    assert report["residual_open_position"] is True


def test_zero_pnl_requires_reconciliation(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, pnl=0.0)
    report = build_lsr_v2_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == PNL_RECONCILIATION_DECISION
    assert report["pnl_reconciliation_ok"] is False


def test_extra_submit_or_reentry_blocks(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path, submit_events=2)
    report = build_lsr_v2_closed_trade_final_audit_report_from_files(data_dir=data)
    assert report["decision"] == EXTRA_SUBMIT_DECISION
    assert report["extra_submit_or_reentry_detected"] is True


def test_final_audit_does_not_mutate_state(tmp_path: Path) -> None:
    data = _seed_closed(tmp_path)
    before_state = (data / "paper_state.json").read_text(encoding="utf-8")
    before_status = (data / "paper_status.json").read_text(encoding="utf-8")
    build_lsr_v2_closed_trade_final_audit_report_from_files(data_dir=data)
    assert (data / "paper_state.json").read_text(encoding="utf-8") == before_state
    assert (data / "paper_status.json").read_text(encoding="utf-8") == before_status
