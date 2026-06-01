from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_trade_submit_boundary import (
    EVENT_TYPE as BOUNDARY_EVENT_TYPE,
    READY_ARMED_DECISION as BOUNDARY_READY_ARMED_DECISION,
)
from trading_bot.core.lsr_v2_second_trade_submit_execution import (
    EVENT_TYPE,
    EXECUTED_DECISION,
    NOT_ARMED_DECISION,
    CONFIRMATION_MISSING_DECISION,
    BOUNDARY_MISSING_DECISION,
    STATE_NOT_CLEAN_DECISION,
    SUBMITTER_NOT_AVAILABLE_DECISION,
    MAX_ORDER_CAP_DECISION,
    LSRV2SecondTradeSubmitExecutionSettings,
    build_lsr_v2_second_trade_submit_execution_event,
    build_lsr_v2_second_trade_submit_execution_report_from_files,
)
from trading_bot.core.lsr_v2_second_trade_submit_boundary import LSRV2SecondTradeSubmitBoundarySettings


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _payload(cycle_id: str = "pc_second") -> dict:
    return {
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "candidate_id": "BTC_second_cand",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "side": "BUY",
        "order_type": "LIMIT",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_per_trade_pct": 0.0025,
        "risk_amount": 2.5,
        "position_size": 2.5,
        "quantity": 2.5,
        "notional": 250.0,
        "max_positions": 1,
    }


def _boundary_event(cycle_id: str = "pc_second", *, ready: bool = True) -> dict:
    payload = _payload(cycle_id)
    return {
        "event_type": BOUNDARY_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": payload["symbol"],
        "timeframe": payload["timeframe"],
        "candidate_id": payload["candidate_id"],
        "side": payload["side"],
        "payload": payload,
        "entry_price": payload["entry_price"],
        "stop_loss": payload["stop_loss"],
        "take_profit": payload["take_profit"],
        "risk_per_trade_pct": payload["risk_per_trade_pct"],
        "risk_amount": payload["risk_amount"],
        "position_size": payload["position_size"],
        "quantity": payload["quantity"],
        "notional": payload["notional"],
        "second_trade_submit_ready": ready,
        "second_trade_submit_armed": True,
        "second_trade_submit_confirmation_ok": True,
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "orders_submitted_by_second_trade_submit_boundary": 0,
        "positions_opened_by_second_trade_submit_boundary": 0,
    }


def _boundary_report(cycle_id: str = "pc_second", *, ready: bool = True) -> dict:
    return {
        "status": "PASS" if ready else "WARN",
        "decision": BOUNDARY_READY_ARMED_DECISION if ready else "KEEP_DIAGNOSTIC",
        "cycle_id": cycle_id,
        "submit_boundary_events": 1,
        "second_trade_submit_ready_count": 1 if ready else 0,
        "second_trade_submit_armed": True,
        "second_trade_submit_confirmation_ok": True,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "orders_submitted_by_second_trade_submit_boundary": 0,
        "positions_opened_by_second_trade_submit_boundary": 0,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
    }


def _write_clean_state(tmp_path: Path) -> None:
    (tmp_path / "paper_state.json").write_text(json.dumps({"orders": {}, "positions": {}}), encoding="utf-8")
    (tmp_path / "paper_status.json").write_text(json.dumps({"open_positions": 0, "pending_orders": 0}), encoding="utf-8")


def _write_boundary(tmp_path: Path, cycle_id: str = "pc_second", *, ready: bool = True) -> None:
    (tmp_path / "lsr_v2_second_trade_submit_boundary_report.json").write_text(json.dumps(_boundary_report(cycle_id, ready=ready)), encoding="utf-8")
    _append_jsonl(tmp_path / "lsr_v2_second_trade_submit_boundary.jsonl", _boundary_event(cycle_id, ready=ready))
    _write_clean_state(tmp_path)


def _fake_submitter(payload: dict):
    return {"order_submitted": True, "position_opened": True, "order_id": "ord_second", "paper_broker_adapter": "FakePaperBrokerAdapter"}


def test_execution_event_calls_fake_submitter_when_all_controls_ok() -> None:
    execution_settings = LSRV2SecondTradeSubmitExecutionSettings(
        execute_arm="1",
        execute_confirmation="I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY",
        max_orders=1,
    )
    boundary_settings = LSRV2SecondTradeSubmitBoundarySettings(
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER",
        max_orders=1,
    )
    event = build_lsr_v2_second_trade_submit_execution_event(
        boundary_event=_boundary_event(),
        settings=execution_settings,
        boundary_settings=boundary_settings,
        paper_state={"paper_state_clean": True, "paper_state_blockers": []},
        paper_submitter=_fake_submitter,
    )

    assert event["event_type"] == EVENT_TYPE
    assert event["broker_submit_called"] is True
    assert event["orders_submitted_by_second_trade_execution"] == 1
    assert event["positions_opened_by_second_trade_execution"] == 1
    assert event["positions_closed_by_second_trade_execution"] == 0
    assert event["live_enabled"] is False
    assert event["testnet_enabled"] is False
    assert event["exchange_broker_enabled"] is False


def test_report_blocks_when_not_armed(tmp_path: Path) -> None:
    _write_boundary(tmp_path)

    report = build_lsr_v2_second_trade_submit_execution_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == NOT_ARMED_DECISION
    assert report["orders_submitted_by_second_trade_execution"] == 0
    assert report["positions_opened_by_second_trade_execution"] == 0
    assert report["broker_submit_called"] is False


def test_report_blocks_when_execution_confirmation_missing(tmp_path: Path, monkeypatch) -> None:
    _write_boundary(tmp_path)
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE", "1")

    report = build_lsr_v2_second_trade_submit_execution_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["second_trade_execute_armed"] is True
    assert report["second_trade_execute_confirmation_ok"] is False
    assert report["broker_submit_called"] is False


def test_report_blocks_when_submitter_not_available(tmp_path: Path, monkeypatch) -> None:
    _write_boundary(tmp_path)
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE_CONFIRMATION", "I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY")

    report = build_lsr_v2_second_trade_submit_execution_report_from_files(data_dir=tmp_path, allow_project_submitter=False)

    assert report["status"] == "WARN"
    assert report["decision"] == SUBMITTER_NOT_AVAILABLE_DECISION
    assert "paper_submitter_not_available" in report["blockers"]
    assert report["orders_submitted_by_second_trade_execution"] == 0


def test_report_executes_one_order_with_injected_submitter(tmp_path: Path, monkeypatch) -> None:
    _write_boundary(tmp_path)
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE_CONFIRMATION", "I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY")

    report = build_lsr_v2_second_trade_submit_execution_report_from_files(data_dir=tmp_path, paper_submitter=_fake_submitter)

    assert report["status"] == "PASS"
    assert report["decision"] == EXECUTED_DECISION
    assert report["orders_submitted_by_second_trade_execution"] == 1
    assert report["positions_opened_by_second_trade_execution"] == 1
    assert report["positions_closed_by_second_trade_execution"] == 0
    assert report["would_submit_count"] == 1
    assert report["broker_submit_called"] is True


def test_dirty_paper_state_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    _write_boundary(tmp_path)
    (tmp_path / "paper_status.json").write_text(json.dumps({"open_positions": 1, "pending_orders": 0}), encoding="utf-8")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE_CONFIRMATION", "I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY")

    report = build_lsr_v2_second_trade_submit_execution_report_from_files(data_dir=tmp_path, paper_submitter=_fake_submitter)

    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_CLEAN_DECISION
    assert report["orders_submitted_by_second_trade_execution"] == 0
    assert report["paper_state_clean"] is False


def test_max_order_cap_blocks_execution(tmp_path: Path, monkeypatch) -> None:
    _write_boundary(tmp_path)
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE", "1")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_EXECUTE_CONFIRMATION", "I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY")
    monkeypatch.setenv("LSR_V2_SECOND_TRADE_MAX_ORDERS", "2")

    report = build_lsr_v2_second_trade_submit_execution_report_from_files(data_dir=tmp_path, paper_submitter=_fake_submitter)

    assert report["status"] == "WARN"
    assert report["decision"] == MAX_ORDER_CAP_DECISION
    assert report["max_orders"] == 2
    assert report["orders_submitted_by_second_trade_execution"] == 0


def test_missing_boundary_blocks_execution(tmp_path: Path) -> None:
    _write_clean_state(tmp_path)

    report = build_lsr_v2_second_trade_submit_execution_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == BOUNDARY_MISSING_DECISION
    assert report["submit_boundary_events"] == 0
    assert report["orders_submitted_by_second_trade_execution"] == 0
