from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_supervised_paper_submit import PREFLIGHT_EVENT_TYPE
from trading_bot.core.lsr_v2_supervised_paper_submit_execution import (
    CONFIRMATION_MISSING_DECISION,
    EXECUTED_DECISION,
    NOT_ARMED_DECISION,
    STATE_NOT_CLEAN_DECISION,
    SUBMITTER_NOT_AVAILABLE_DECISION,
    LSRV2SupervisedPaperSubmitExecutionSettings,
    build_lsr_v2_supervised_paper_submit_execution_report_from_files,
    read_paper_state_cleanliness,
)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _preflight(cycle_id: str = "pc_exec", symbol: str = "BTC/USDT") -> dict:
    return {
        "event_type": PREFLIGHT_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "timeframe": "5m",
        "side": "BUY",
        "order_type": "LIMIT",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "candidate_id": f"{symbol}_cand_1",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_per_trade_pct": 0.0025,
        "risk_amount": 2.5,
        "position_size": 2.5,
        "quantity": 2.5,
        "notional": 250.0,
        "max_positions": 1,
        "payload_valid": True,
        "would_create_paper_order": True,
        "would_prepare_submit": True,
        "submit_enabled": False,
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_lsr_v2_submit_preflight": 0,
        "positions_opened_by_lsr_v2_submit_preflight": 0,
    }


def _write_preflight(tmp_path: Path, cycle_id: str = "pc_exec") -> None:
    _append_jsonl(tmp_path / "lsr_v2_supervised_paper_submit_preflight.jsonl", _preflight(cycle_id))
    (tmp_path / "lsr_v2_supervised_paper_submit_preflight_report.json").write_text(json.dumps({
        "decision": "LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT_READY",
        "cycle_id": cycle_id,
    }), encoding="utf-8")


def _exec_settings(tmp_path: Path, *, execute: bool = False, confirm: bool = False) -> LSRV2SupervisedPaperSubmitExecutionSettings:
    return LSRV2SupervisedPaperSubmitExecutionSettings(
        data_dir=str(tmp_path),
        execute_arm="1" if execute else "",
        execute_confirmation="I_UNDERSTAND_EXECUTE_ONE_PAPER_ORDER_ONLY" if confirm else "",
        max_orders=1,
    )


def test_default_execution_boundary_not_armed(tmp_path: Path, monkeypatch) -> None:
    _write_preflight(tmp_path, "pc_not_armed")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SINGLE_PAPER_ORDER")
    report = build_lsr_v2_supervised_paper_submit_execution_report_from_files(
        data_dir=tmp_path,
        execution_settings=_exec_settings(tmp_path, execute=False, confirm=False),
    )
    assert report["decision"] == NOT_ARMED_DECISION
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_lsr_v2_execution"] == 0
    assert report["positions_opened_by_lsr_v2_execution"] == 0


def test_execute_confirmation_missing_blocks(tmp_path: Path, monkeypatch) -> None:
    _write_preflight(tmp_path, "pc_missing_confirm")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SINGLE_PAPER_ORDER")
    report = build_lsr_v2_supervised_paper_submit_execution_report_from_files(
        data_dir=tmp_path,
        execution_settings=_exec_settings(tmp_path, execute=True, confirm=False),
    )
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["would_submit_count"] == 0


def test_clean_state_and_explicit_submitter_executes_one_order(tmp_path: Path, monkeypatch) -> None:
    _write_preflight(tmp_path, "pc_real_paper")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SINGLE_PAPER_ORDER")
    calls: list[dict] = []

    def fake_submitter(payload):
        calls.append(dict(payload))
        return {"order_submitted": True, "position_opened": True, "order_id": "paper_one"}

    report = build_lsr_v2_supervised_paper_submit_execution_report_from_files(
        data_dir=tmp_path,
        execution_settings=_exec_settings(tmp_path, execute=True, confirm=True),
        paper_submitter=fake_submitter,
    )
    assert report["decision"] == EXECUTED_DECISION
    assert len(calls) == 1
    assert report["broker_submit_called"] is True
    assert report["orders_submitted_by_lsr_v2_execution"] == 1
    assert report["positions_opened_by_lsr_v2_execution"] == 1
    assert report["live_enabled"] is False
    assert report["testnet_enabled"] is False
    assert report["exchange_broker_enabled"] is False


def test_armed_without_submitter_reports_submitter_not_available(tmp_path: Path, monkeypatch) -> None:
    _write_preflight(tmp_path, "pc_no_submitter")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SINGLE_PAPER_ORDER")
    report = build_lsr_v2_supervised_paper_submit_execution_report_from_files(
        data_dir=tmp_path,
        execution_settings=_exec_settings(tmp_path, execute=True, confirm=True),
        paper_submitter=None,
        allow_project_submitter=False,
    )
    assert report["decision"] == SUBMITTER_NOT_AVAILABLE_DECISION
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_lsr_v2_execution"] == 0


def test_dirty_paper_state_blocks_before_submit(tmp_path: Path, monkeypatch) -> None:
    _write_preflight(tmp_path, "pc_dirty")
    (tmp_path / "paper_state.json").write_text(json.dumps({
        "orders": {},
        "positions": {"pos_1": {"symbol": "BTC/USDT", "status": "OPEN", "open": True}},
    }), encoding="utf-8")
    clean, state = read_paper_state_cleanliness(tmp_path)
    assert clean is False
    assert "active_positions_present" in state["paper_state_blockers"]
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_ARM", "1")
    monkeypatch.setenv("LSR_V2_PAPER_SUBMIT_CONFIRMATION", "I_UNDERSTAND_SINGLE_PAPER_ORDER")
    calls: list[dict] = []

    def fake_submitter(payload):
        calls.append(dict(payload))
        return {"order_submitted": True, "position_opened": True}

    report = build_lsr_v2_supervised_paper_submit_execution_report_from_files(
        data_dir=tmp_path,
        execution_settings=_exec_settings(tmp_path, execute=True, confirm=True),
        paper_submitter=fake_submitter,
    )
    assert report["decision"] == STATE_NOT_CLEAN_DECISION
    assert calls == []
    assert report["orders_submitted_by_lsr_v2_execution"] == 0
    assert report["positions_opened_by_lsr_v2_execution"] == 0
