from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_trade_submit_preflight import EVENT_TYPE as PREFLIGHT_EVENT_TYPE, READY_DECISION as PREFLIGHT_READY_DECISION
from trading_bot.core.lsr_v2_second_trade_submit_boundary import (
    EVENT_TYPE,
    READY_ARMED_DECISION,
    NOT_ARMED_DECISION,
    CONFIRMATION_MISSING_DECISION,
    PREFLIGHT_MISSING_DECISION,
    STATE_NOT_CLEAN_DECISION,
    REJECT_DECISION,
    LSRV2SecondTradeSubmitBoundarySettings,
    build_lsr_v2_second_trade_submit_boundary_event,
    build_lsr_v2_second_trade_submit_boundary_report_from_files,
)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _preflight_report(cycle_id: str = "pc_second") -> dict:
    return {
        "status": "PASS",
        "decision": PREFLIGHT_READY_DECISION,
        "cycle_id": cycle_id,
        "second_trade_eligible": True,
        "second_trade_rearm_ready": True,
        "second_trade_route_preflight_ready": True,
        "second_trade_order_intent_ready": True,
        "handoff_pass": True,
        "submit_preflight_events": 1,
        "would_prepare_submit_count": 1,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_second_trade_submit_preflight": False,
        "orders_submitted_by_second_trade_submit_preflight": 0,
        "positions_opened_by_second_trade_submit_preflight": 0,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
    }


def _preflight(cycle_id: str = "pc_second", *, would_prepare: bool = True) -> dict:
    return {
        "event_type": PREFLIGHT_EVENT_TYPE,
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
        "payload_valid": True,
        "would_create_paper_order": True,
        "would_prepare_submit": would_prepare,
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "paper_order_submission_enabled": False,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_status_open_positions": 0,
        "paper_status_pending_orders": 0,
        "state_open_lsr_v2_positions": 0,
        "orders_submitted_by_second_trade_submit_preflight": 0,
        "positions_opened_by_second_trade_submit_preflight": 0,
    }


def _write_preflight(tmp_path: Path, cycle_id: str = "pc_second", *, report: dict | None = None, event: dict | None = None) -> None:
    (tmp_path / "lsr_v2_second_trade_submit_preflight_report.json").write_text(json.dumps(report or _preflight_report(cycle_id)), encoding="utf-8")
    _append_jsonl(tmp_path / "lsr_v2_second_trade_submit_preflight.jsonl", event or _preflight(cycle_id))


def test_boundary_event_is_ready_when_armed_and_confirmation_ok() -> None:
    settings = LSRV2SecondTradeSubmitBoundarySettings(
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER",
        max_orders=1,
    )
    prereq = _preflight_report()
    prereq.update({"preflight_report_present": True, "preflight_pass": True})
    event = build_lsr_v2_second_trade_submit_boundary_event(
        preflight_event=_preflight(),
        settings=settings,
        prerequisites=prereq,
    )

    assert event["event_type"] == EVENT_TYPE
    assert event["second_trade_submit_ready"] is True
    assert event["second_trade_submit_armed"] is True
    assert event["second_trade_submit_confirmation_ok"] is True
    assert event["would_submit"] is False
    assert event["would_submit_to_paper_broker"] is False
    assert event["broker_submit_called"] is False
    assert event["orders_submitted_by_second_trade_submit_boundary"] == 0
    assert event["positions_opened_by_second_trade_submit_boundary"] == 0


def test_report_blocks_when_not_armed(tmp_path: Path) -> None:
    _write_preflight(tmp_path, "pc_second")

    report = build_lsr_v2_second_trade_submit_boundary_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == NOT_ARMED_DECISION
    assert report["second_trade_submit_ready_count"] == 0
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_second_trade_submit_boundary"] == 0


def test_report_blocks_when_confirmation_missing(tmp_path: Path) -> None:
    _write_preflight(tmp_path, "pc_second")
    settings = LSRV2SecondTradeSubmitBoundarySettings(data_dir=str(tmp_path), submit_arm="1", submit_confirmation="", max_orders=1)

    report = build_lsr_v2_second_trade_submit_boundary_report_from_files(data_dir=tmp_path, settings=settings)

    assert report["status"] == "WARN"
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["second_trade_submit_armed"] is True
    assert report["second_trade_submit_confirmation_ok"] is False
    assert report["would_submit_count"] == 0


def test_report_ready_armed_from_submit_preflight_jsonl(tmp_path: Path) -> None:
    _write_preflight(tmp_path, "pc_old")
    _write_preflight(tmp_path, "pc_new")
    settings = LSRV2SecondTradeSubmitBoundarySettings(
        data_dir=str(tmp_path),
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER",
        max_orders=1,
    )

    report = build_lsr_v2_second_trade_submit_boundary_report_from_files(data_dir=tmp_path, settings=settings)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_ARMED_DECISION
    assert report["cycle_id"] == "pc_new"
    assert report["strict_cycle_scope"] is True
    assert report["submit_preflight_events"] == 1
    assert report["submit_boundary_events"] == 1
    assert report["second_trade_submit_ready_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_second_trade_submit_boundary"] == 0
    assert report["positions_opened_by_second_trade_submit_boundary"] == 0
    assert report["historical_second_trade_submit_preflight_events"] == 1
    assert (tmp_path / "lsr_v2_second_trade_submit_boundary_report.json").exists()
    assert (tmp_path / "lsr_v2_second_trade_submit_boundary.jsonl").exists()


def test_missing_preflight_blocks_boundary(tmp_path: Path) -> None:
    report = build_lsr_v2_second_trade_submit_boundary_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == PREFLIGHT_MISSING_DECISION
    assert report["submit_preflight_events"] == 0
    assert report["would_submit_count"] == 0


def test_state_not_clean_blocks_even_when_armed(tmp_path: Path) -> None:
    report_payload = _preflight_report("pc_dirty")
    report_payload["paper_status_open_positions"] = 1
    event = _preflight("pc_dirty")
    event["paper_status_open_positions"] = 1
    _write_preflight(tmp_path, "pc_dirty", report=report_payload, event=event)
    settings = LSRV2SecondTradeSubmitBoundarySettings(
        data_dir=str(tmp_path),
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER",
        max_orders=1,
    )

    report = build_lsr_v2_second_trade_submit_boundary_report_from_files(data_dir=tmp_path, settings=settings)

    assert report["status"] == "WARN"
    assert report["decision"] == STATE_NOT_CLEAN_DECISION
    assert "paper_state_not_clean" in report["blockers"]
    assert report["second_trade_submit_ready_count"] == 0
    assert report["orders_submitted_by_second_trade_submit_boundary"] == 0


def test_upstream_submit_attempt_rejects_boundary(tmp_path: Path) -> None:
    report_payload = _preflight_report("pc_bad")
    report_payload["would_submit_count"] = 1
    event = _preflight("pc_bad")
    event["would_submit"] = True
    _write_preflight(tmp_path, "pc_bad", report=report_payload, event=event)
    settings = LSRV2SecondTradeSubmitBoundarySettings(
        data_dir=str(tmp_path),
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER",
        max_orders=1,
    )

    report = build_lsr_v2_second_trade_submit_boundary_report_from_files(data_dir=tmp_path, settings=settings)

    assert report["status"] == "FAIL"
    assert report["decision"] == REJECT_DECISION
    assert report["would_submit_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_second_trade_submit_boundary"] == 0
