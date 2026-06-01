from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_paper_order_submit_execution import (
    ARM_ENV,
    CONFIRMATION_ENV,
    CONFIRMATION_PHRASE,
    EXECUTE_CONFIRMATION_ENV,
    EXECUTE_CONFIRMATION_PHRASE,
    EXECUTE_ENV,
    EXECUTED_DECISION,
    MAX_ORDER_CAP_DECISION,
    MAX_ORDERS_ENV,
    NOT_ARMED_DECISION,
    PREREQ_BLOCKED_DECISION,
    STATE_BLOCKED_DECISION,
    SUBMITTER_NOT_AVAILABLE_DECISION,
    build_lsr_v2_second_paper_order_submit_execution_report_from_files,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed(tmp_path: Path, *, open_positions: int = 0, gate_ok: bool = True, readiness_ok: bool = True) -> Path:
    data = tmp_path / "data"
    candidate = {
        "candidate_valid": True,
        "cycle_id": "pc_000734_second",
        "candidate_id": "candidate_second",
        "symbol": "BTC/USDT",
        "side": "SELL",
        "entry_price": 99076.7,
        "stop_loss": 99367.46952,
        "take_profit": 98495.16096,
    }
    _write_json(data / "lsr_v2_second_paper_order_gate_report.json", {
        "status": "PASS" if gate_ok else "WARN",
        "decision": "LSR_V2_SECOND_PAPER_ORDER_GATE_READY_DEFAULT_OFF" if gate_ok else "KEEP_DIAGNOSTIC",
        "second_order_gate_ready": gate_ok,
        "candidate": candidate,
    })
    _write_json(data / "lsr_v2_paper_bounded_multi_order_session_readiness_report.json", {
        "status": "PASS" if readiness_ok else "WARN",
        "decision": "LSR_V2_PAPER_BOUNDED_MULTI_ORDER_SESSION_READY_DEFAULT_OFF" if readiness_ok else "KEEP_DIAGNOSTIC",
        "multi_order_session_ready": readiness_ok,
        "candidate": candidate,
    })
    _write_json(data / "lsr_v2_paper_final_runtime_audit_report.json", {
        "status": "WARN",
        "decision": "LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_WARN_NON_BLOCKING",
        "final_state": "FLAT" if open_positions == 0 else "OPEN_POSITION",
    })
    _write_json(data / "lsr_v2_paper_realized_pnl_reconciliation_report.json", {
        "status": "WARN",
        "reconciliation_status": "WARN",
        "decision": "LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_WARN_NON_BLOCKING",
    })
    _write_json(data / "paper_state.json", {
        "balance": 1019.2088998391052,
        "drawdown_pct": 0.0,
        "initial_balance": 1000.0,
        "is_paused": False,
        "kill_switch": False,
        "peak_balance": 1023.7543376227,
        "realized_pnl": 19.20889983910528,
        "orders": {
            "po_first": {
                "created_at": "2026-06-01T10:00:00+00:00",
                "filled_price": 99076.7,
                "metadata": {"cycle_id": "pc_000517_first", "execution_source": "lsr_v2_supervised_paper_submit_execution"},
                "order_id": "po_first",
                "order_type": "MARKET",
                "qty": 0.008597875,
                "reason": "",
                "requested_price": 99076.7,
                "side": "SELL",
                "status": "FILLED",
                "symbol": "BTC/USDT",
                "updated_at": "2026-06-01T10:00:00+00:00",
            }
        },
        "positions": {
            "pp_first": {
                "closed_at": None if open_positions else "2026-06-01T10:05:00+00:00",
                "close_reason": "" if open_positions else "SL",
                "entry_price": 99076.7,
                "exit_price": None if open_positions else 99367.46952,
                "fees_paid": 2.045437796824708,
                "metadata": {"cycle_id": "pc_000517_first", "execution_source": "lsr_v2_supervised_paper_submit_execution", "source_order_id": "po_first"},
                "opened_at": "2026-06-01T10:00:00+00:00",
                "position_id": "pp_first",
                "qty": 0.008597875,
                "realized_pnl": 0.0 if open_positions else -2.841739619569722,
                "side": "SELL",
                "status": "OPEN" if open_positions else "CLOSED",
                "stop_loss": 99367.46952,
                "symbol": "BTC/USDT",
                "take_profit": 98495.16096,
            }
        },
    })
    _write_json(data / "paper_status.json", {"open_positions": open_positions, "pending_orders": 0, "balance": 1019.2088998391052})
    return data


def _arm(monkeypatch) -> None:
    monkeypatch.setenv(ARM_ENV, "1")
    monkeypatch.setenv(CONFIRMATION_ENV, CONFIRMATION_PHRASE)
    monkeypatch.setenv(EXECUTE_ENV, "1")
    monkeypatch.setenv(EXECUTE_CONFIRMATION_ENV, EXECUTE_CONFIRMATION_PHRASE)
    monkeypatch.setenv(MAX_ORDERS_ENV, "1")


def _fake_submitter(payload: dict) -> dict:
    assert payload["symbol"] == "BTC/USDT"
    assert payload["side"] == "SELL"
    assert payload["quantity"] > 0
    return {"order_submitted": True, "position_opened": True, "order_id": "po_second", "position_id": "pp_second"}


def test_not_armed_does_not_submit(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    monkeypatch.delenv(EXECUTE_ENV, raising=False)
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(data_dir=data, paper_submitter=_fake_submitter)
    assert report["decision"] == NOT_ARMED_DECISION
    assert report["orders_submitted_by_second_paper_execution"] == 0
    assert report["broker_submit_called"] is False


def test_missing_submitter_blocks_after_all_controls_ok(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    _arm(monkeypatch)
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(data_dir=data)
    assert report["decision"] == SUBMITTER_NOT_AVAILABLE_DECISION
    assert "paper_submitter_not_available" in report["blockers"]


def test_executes_one_order_with_injected_submitter(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    _arm(monkeypatch)
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(
        data_dir=data,
        paper_submitter=_fake_submitter,
        sync_status_after_submit=False,
    )
    assert report["status"] == "PASS"
    assert report["decision"] == EXECUTED_DECISION
    assert report["orders_submitted_by_second_paper_execution"] == 1
    assert report["positions_opened_by_second_paper_execution"] == 1
    assert report["positions_closed_by_second_paper_execution"] == 0
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_project_submitter_mutates_paper_state_and_syncs_status(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    _arm(monkeypatch)
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(data_dir=data, allow_project_submitter=True)
    state = json.loads((data / "paper_state.json").read_text(encoding="utf-8"))
    status = json.loads((data / "paper_status.json").read_text(encoding="utf-8"))
    assert report["decision"] == EXECUTED_DECISION
    assert len(state["orders"]) == 2
    assert sum(1 for row in state["positions"].values() if row["status"] == "OPEN") == 1
    assert status["open_positions"] == 1
    assert report["paper_status_sync"]["paper_status_modified"] is True


def test_open_position_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, open_positions=1)
    _arm(monkeypatch)
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(data_dir=data, paper_submitter=_fake_submitter)
    assert report["decision"] == STATE_BLOCKED_DECISION
    assert "open_positions_not_zero" in report["blockers"]
    assert report["orders_submitted_by_second_paper_execution"] == 0


def test_gate_not_ready_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path, gate_ok=False)
    _arm(monkeypatch)
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(data_dir=data, paper_submitter=_fake_submitter)
    assert report["decision"] == PREREQ_BLOCKED_DECISION
    assert "second_order_gate_not_ready" in report["blockers"]


def test_max_order_cap_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    data = _seed(tmp_path)
    _arm(monkeypatch)
    monkeypatch.setenv(MAX_ORDERS_ENV, "2")
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(data_dir=data, paper_submitter=_fake_submitter)
    assert report["decision"] == MAX_ORDER_CAP_DECISION
    assert report["orders_submitted_by_second_paper_execution"] == 0
