from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_trade_handoff_dry_run import HANDOFF_EVENT_TYPE, READY_DECISION as HANDOFF_READY_DECISION
from trading_bot.core.lsr_v2_second_trade_submit_preflight import (
    EVENT_TYPE,
    READY_DECISION,
    HANDOFF_MISSING_DECISION,
    REARM_MISSING_DECISION,
    ROUTE_MISSING_DECISION,
    SAFETY_REJECT_DECISION,
    build_lsr_v2_second_trade_submit_preflight_event,
    build_lsr_v2_second_trade_submit_preflight_report_from_files,
)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _eligibility_report(cycle_id: str = "pc_test") -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_PAPER_TRADE_ELIGIBILITY_PASS",
        "cycle_id": cycle_id,
        "second_trade_eligible": True,
        "observation_pass": True,
        "second_trade_locked": True,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
        "broker_submit_called_by_second_trade_gate": False,
        "orders_submitted_by_second_trade_gate": 0,
        "positions_opened_by_second_trade_gate": 0,
    }


def _rearm_report(cycle_id: str = "pc_test") -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_TRADE_REARM_READY_DIAGNOSTIC",
        "cycle_id": cycle_id,
        "second_trade_eligible": True,
        "second_trade_rearm_ready": True,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
        "broker_submit_called_by_second_trade_rearm_gate": False,
        "orders_submitted_by_second_trade_rearm_gate": 0,
        "positions_opened_by_second_trade_rearm_gate": 0,
    }


def _route_report(cycle_id: str = "pc_test") -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_READY",
        "cycle_id": cycle_id,
        "second_trade_eligible": True,
        "second_trade_rearm_ready": True,
        "second_trade_route_preflight_ready": True,
        "second_trade_order_intent_ready": True,
        "second_trade_would_route_count": 1,
        "second_trade_order_intent_events": 1,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "paper_order_submission_enabled": False,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "broker_submit_called_by_second_trade_route_preflight": False,
        "orders_submitted_by_second_trade_route_preflight": 0,
        "positions_opened_by_second_trade_route_preflight": 0,
    }


def _handoff_report(cycle_id: str = "pc_test") -> dict:
    return {
        "status": "PASS",
        "decision": HANDOFF_READY_DECISION,
        "cycle_id": cycle_id,
        "second_trade_eligible": True,
        "second_trade_rearm_ready": True,
        "second_trade_route_preflight_ready": True,
        "second_trade_order_intent_ready": True,
        "handoff_dry_run_events": 1,
        "payload_valid_count": 1,
        "payload_invalid_count": 0,
        "would_create_paper_order_count": 1,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_second_trade_handoff": False,
        "orders_submitted_by_second_trade_handoff": 0,
        "positions_opened_by_second_trade_handoff": 0,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
    }


def _handoff(cycle_id: str = "pc_test", *, would_create: bool = True) -> dict:
    return {
        "event_type": HANDOFF_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": "BTC/USDT",
        "timeframe": "5m",
        "candidate_id": "BTC_cand_2",
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
        "payload_valid": True,
        "would_create_paper_order": would_create,
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "paper_order_submission_enabled": False,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "orders_submitted_by_second_trade_handoff": 0,
        "positions_opened_by_second_trade_handoff": 0,
    }


def _write_all_reports(tmp_path: Path, cycle_id: str = "pc_test") -> None:
    (tmp_path / "lsr_v2_second_trade_eligibility_gate_report.json").write_text(json.dumps(_eligibility_report(cycle_id)), encoding="utf-8")
    (tmp_path / "lsr_v2_second_trade_rearm_gate_report.json").write_text(json.dumps(_rearm_report(cycle_id)), encoding="utf-8")
    (tmp_path / "lsr_v2_second_trade_route_preflight_report.json").write_text(json.dumps(_route_report(cycle_id)), encoding="utf-8")
    (tmp_path / "lsr_v2_second_trade_handoff_dry_run_report.json").write_text(json.dumps(_handoff_report(cycle_id)), encoding="utf-8")


def test_preflight_event_is_fail_closed_with_valid_second_trade_handoff() -> None:
    prereq = {
        "eligibility_pass": True,
        "second_trade_eligible": True,
        "rearm_pass": True,
        "second_trade_rearm_ready": True,
        "route_pass": True,
        "second_trade_route_preflight_ready": True,
        "second_trade_order_intent_ready": True,
        "second_trade_would_route_count": 1,
        "handoff_pass": True,
    }
    event = build_lsr_v2_second_trade_submit_preflight_event(handoff_event=_handoff(), prerequisites=prereq)

    assert event["event_type"] == EVENT_TYPE
    assert event["would_prepare_submit"] is True
    assert event["would_submit"] is False
    assert event["would_submit_to_paper_broker"] is False
    assert event["broker_submit_called"] is False
    assert event["second_trade_submit_enabled"] is False
    assert event["orders_submitted_by_second_trade_submit_preflight"] == 0
    assert event["positions_opened_by_second_trade_submit_preflight"] == 0


def test_report_ready_from_second_trade_handoff_jsonl(tmp_path: Path) -> None:
    _write_all_reports(tmp_path, "pc_new")
    _append_jsonl(tmp_path / "lsr_v2_second_trade_handoff_dry_run.jsonl", _handoff("pc_old"))
    _append_jsonl(tmp_path / "lsr_v2_second_trade_handoff_dry_run.jsonl", _handoff("pc_new"))

    report = build_lsr_v2_second_trade_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_new"
    assert report["strict_cycle_scope"] is True
    assert report["handoff_dry_run_events"] == 1
    assert report["submit_preflight_events"] == 1
    assert report["would_prepare_submit_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_second_trade_submit_preflight"] == 0
    assert report["positions_opened_by_second_trade_submit_preflight"] == 0
    assert report["historical_second_trade_handoff_events"] == 1
    assert (tmp_path / "lsr_v2_second_trade_submit_preflight_report.json").exists()
    assert (tmp_path / "lsr_v2_second_trade_submit_preflight.jsonl").exists()


def test_missing_handoff_blocks_submit_preflight(tmp_path: Path) -> None:
    _write_all_reports(tmp_path, "pc_missing")

    report = build_lsr_v2_second_trade_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == HANDOFF_MISSING_DECISION
    assert report["handoff_dry_run_events"] == 0
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_second_trade_submit_preflight"] == 0


def test_rearm_missing_blocks_submit_preflight(tmp_path: Path) -> None:
    _write_all_reports(tmp_path, "pc_rearm_missing")
    rearm = _rearm_report("pc_rearm_missing")
    rearm["decision"] = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_NOT_ENABLED"
    rearm["second_trade_rearm_ready"] = False
    (tmp_path / "lsr_v2_second_trade_rearm_gate_report.json").write_text(json.dumps(rearm), encoding="utf-8")
    _append_jsonl(tmp_path / "lsr_v2_second_trade_handoff_dry_run.jsonl", _handoff("pc_rearm_missing"))

    report = build_lsr_v2_second_trade_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == REARM_MISSING_DECISION
    assert "second_trade_rearm_not_ready" in report["blockers"]
    assert report["would_submit_count"] == 0


def test_route_missing_blocks_submit_preflight(tmp_path: Path) -> None:
    _write_all_reports(tmp_path, "pc_route_missing")
    route = _route_report("pc_route_missing")
    route["decision"] = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_OPERATOR_CONFIRMATION_MISSING"
    route["second_trade_route_preflight_ready"] = False
    (tmp_path / "lsr_v2_second_trade_route_preflight_report.json").write_text(json.dumps(route), encoding="utf-8")
    _append_jsonl(tmp_path / "lsr_v2_second_trade_handoff_dry_run.jsonl", _handoff("pc_route_missing"))

    report = build_lsr_v2_second_trade_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == ROUTE_MISSING_DECISION
    assert report["would_submit_count"] == 0


def test_unsafe_handoff_submit_attempt_rejects(tmp_path: Path) -> None:
    _write_all_reports(tmp_path, "pc_unsafe")
    handoff_report = _handoff_report("pc_unsafe")
    handoff_report["would_submit_count"] = 1
    (tmp_path / "lsr_v2_second_trade_handoff_dry_run_report.json").write_text(json.dumps(handoff_report), encoding="utf-8")
    event = _handoff("pc_unsafe")
    event["would_submit"] = True
    _append_jsonl(tmp_path / "lsr_v2_second_trade_handoff_dry_run.jsonl", event)

    report = build_lsr_v2_second_trade_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "FAIL"
    assert report["decision"] == SAFETY_REJECT_DECISION
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_second_trade_submit_preflight"] == 0
    assert report["positions_opened_by_second_trade_submit_preflight"] == 0


def test_dirty_paper_state_rejects_preflight(tmp_path: Path) -> None:
    _write_all_reports(tmp_path, "pc_dirty")
    handoff_report = _handoff_report("pc_dirty")
    handoff_report["paper_status_open_positions"] = 1
    (tmp_path / "lsr_v2_second_trade_handoff_dry_run_report.json").write_text(json.dumps(handoff_report), encoding="utf-8")
    _append_jsonl(tmp_path / "lsr_v2_second_trade_handoff_dry_run.jsonl", _handoff("pc_dirty"))

    report = build_lsr_v2_second_trade_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "FAIL"
    assert report["decision"] == SAFETY_REJECT_DECISION
    assert "safety_violation_detected" in report["blockers"]
    assert report["paper_status_open_positions"] == 1
