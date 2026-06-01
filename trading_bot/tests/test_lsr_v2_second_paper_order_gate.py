from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_paper_order_gate import (
    ARM_ENV,
    CONFIRMATION_ENV,
    CONFIRMATION_PHRASE,
    OPERATOR_REQUIRED_DECISION,
    PREREQ_BLOCKED_DECISION,
    READY_DECISION,
    STATE_BLOCKED_DECISION,
    build_lsr_v2_second_paper_order_gate_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _seed(tmp_path: Path, *, final_status: str = "WARN", pnl_status: str = "WARN", postmortem_status: str = "WARN", open_positions: int = 0, candidate: bool = True) -> Path:
    data = tmp_path / "data"
    _write_json(data / "lsr_v2_paper_final_runtime_audit_report.json", {
        "status": final_status,
        "decision": "LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_WARN_NON_BLOCKING" if final_status != "FAIL" else "REJECT_LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_FAILED",
        "final_state": "OPEN_POSITION" if open_positions else "FLAT",
        "paper_state_status_consistent": open_positions == 0,
        "cycle_id": "pc_first",
    })
    _write_json(data / "lsr_v2_paper_realized_pnl_reconciliation_report.json", {
        "status": pnl_status,
        "reconciliation_status": pnl_status,
        "decision": "LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_WARN_NON_BLOCKING" if pnl_status != "FAIL" else "REJECT_LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_FAILED",
    })
    _write_json(data / "lsr_v2_paper_trade_postmortem_report.json", {
        "status": postmortem_status,
        "decision": "LSR_V2_PAPER_TRADE_POSTMORTEM_WARN_NON_BLOCKING" if postmortem_status != "FAIL" else "REJECT_LSR_V2_PAPER_TRADE_POSTMORTEM_FAILED",
        "should_block_next_order_experimentation": postmortem_status == "FAIL",
    })
    _write_json(data / "paper_state.json", {
        "orders": {
            "po_first": {"order_id": "po_first", "status": "FILLED"}
        },
        "positions": {
            "pp_first": {"position_id": "pp_first", "status": "OPEN" if open_positions else "CLOSED", "open": bool(open_positions)}
        },
    })
    _write_json(data / "paper_status.json", {
        "open_positions": open_positions,
        "pending_orders": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    })
    events = []
    if candidate:
        events.append({
            "event_type": "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT",
            "cycle_id": "pc_second_candidate",
            "candidate_ready": True,
            "would_route": True,
            "candidate_id": "candidate_second",
            "symbol": "BTC/USDT",
            "side": "SELL",
            "entry_price": 99076.7,
            "stop_loss": 99367.46952,
            "take_profit": 98495.16096,
            "quality_grade": "A",
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        })
    _write_jsonl(data / "paper_events.jsonl", events)
    return data


def test_ready_when_prereqs_and_operator_confirmation_are_present(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.setenv(ARM_ENV, "1")
    monkeypatch.setenv(CONFIRMATION_ENV, CONFIRMATION_PHRASE)
    report = build_lsr_v2_second_paper_order_gate_report_from_files(data_dir=data)
    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["second_order_gate_ready"] is True
    assert report["second_order_execute_enabled"] is False
    assert report["read_only_safety"]["orders_submitted_by_gate"] == 0


def test_operator_confirmation_missing_blocks_but_system_ready(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.delenv(ARM_ENV, raising=False)
    monkeypatch.delenv(CONFIRMATION_ENV, raising=False)
    report = build_lsr_v2_second_paper_order_gate_report_from_files(data_dir=data)
    assert report["decision"] == OPERATOR_REQUIRED_DECISION
    assert report["system_ready"] is True
    assert report["second_order_gate_ready"] is False
    assert "operator_confirmation_missing" in report["blockers"]


def test_final_audit_fail_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, final_status="FAIL")
    monkeypatch.setenv(ARM_ENV, "1")
    monkeypatch.setenv(CONFIRMATION_ENV, CONFIRMATION_PHRASE)
    report = build_lsr_v2_second_paper_order_gate_report_from_files(data_dir=data)
    assert report["decision"] == PREREQ_BLOCKED_DECISION
    assert "final_runtime_audit_missing_or_fail" in report["blockers"]


def test_pnl_fail_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, pnl_status="FAIL")
    monkeypatch.setenv(ARM_ENV, "1")
    monkeypatch.setenv(CONFIRMATION_ENV, CONFIRMATION_PHRASE)
    report = build_lsr_v2_second_paper_order_gate_report_from_files(data_dir=data)
    assert report["decision"] == PREREQ_BLOCKED_DECISION
    assert "pnl_reconciliation_missing_or_fail" in report["blockers"]


def test_open_position_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, open_positions=1)
    monkeypatch.setenv(ARM_ENV, "1")
    monkeypatch.setenv(CONFIRMATION_ENV, CONFIRMATION_PHRASE)
    report = build_lsr_v2_second_paper_order_gate_report_from_files(data_dir=data)
    assert report["decision"] == STATE_BLOCKED_DECISION
    assert "open_positions_not_zero" in report["blockers"]


def test_candidate_missing_blocks(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, candidate=False)
    monkeypatch.setenv(ARM_ENV, "1")
    monkeypatch.setenv(CONFIRMATION_ENV, CONFIRMATION_PHRASE)
    report = build_lsr_v2_second_paper_order_gate_report_from_files(data_dir=data)
    assert report["decision"] == PREREQ_BLOCKED_DECISION
    assert "candidate_not_valid" in report["blockers"]
