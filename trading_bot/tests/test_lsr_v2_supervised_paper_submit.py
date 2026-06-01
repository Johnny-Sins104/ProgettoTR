from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_supervised_paper_submit import (
    CONFIRMATION_MISSING_DECISION,
    EVENT_TYPE,
    EXECUTED_DECISION,
    NOT_ARMED_DECISION,
    PREFLIGHT_EVENT_TYPE,
    READY_ARMED_DECISION,
    REJECT_DECISION,
    LSRV2SupervisedPaperSubmitSettings,
    build_lsr_v2_supervised_paper_submit_event,
    build_lsr_v2_supervised_paper_submit_report_from_files,
)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _preflight(cycle_id: str = "pc_test", symbol: str = "BTC/USDT", hostile: bool = False) -> dict:
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
        "would_submit": bool(hostile),
        "would_submit_to_paper_broker": bool(hostile),
        "broker_submit_called": bool(hostile),
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


def test_not_armed_boundary_does_not_submit() -> None:
    event = build_lsr_v2_supervised_paper_submit_event(
        preflight_event=_preflight(),
        settings=LSRV2SupervisedPaperSubmitSettings(submit_arm="", submit_confirmation=""),
    )
    assert event["event_type"] == EVENT_TYPE
    assert event["submit_ready"] is False
    assert event["would_submit"] is False
    assert event["broker_submit_called"] is False
    assert event["orders_submitted_by_lsr_v2_submit"] == 0
    assert event["blocked_reason"] == "submit_not_armed"


def test_armed_without_submitter_is_ready_but_no_broker_call(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_supervised_paper_submit_preflight.jsonl", _preflight("pc_ready"))
    (tmp_path / "lsr_v2_supervised_paper_submit_preflight_report.json").write_text(json.dumps({
        "decision": "LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT_READY",
        "cycle_id": "pc_ready",
    }), encoding="utf-8")
    settings = LSRV2SupervisedPaperSubmitSettings(
        data_dir=str(tmp_path),
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SINGLE_PAPER_ORDER",
        max_orders=1,
    )
    report = build_lsr_v2_supervised_paper_submit_report_from_files(data_dir=tmp_path, settings=settings)
    assert report["status"] == "PASS"
    assert report["decision"] == READY_ARMED_DECISION
    assert report["submit_ready_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_lsr_v2_submit"] == 0


def test_missing_confirmation_blocks_even_when_armed(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_supervised_paper_submit_preflight.jsonl", _preflight("pc_confirm"))
    settings = LSRV2SupervisedPaperSubmitSettings(data_dir=str(tmp_path), submit_arm="1", submit_confirmation="wrong")
    report = build_lsr_v2_supervised_paper_submit_report_from_files(data_dir=tmp_path, settings=settings)
    assert report["status"] == "WARN"
    assert report["decision"] == CONFIRMATION_MISSING_DECISION
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_lsr_v2_submit"] == 0


def test_explicit_submitter_can_execute_single_paper_order(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_supervised_paper_submit_preflight.jsonl", _preflight("pc_exec"))
    calls: list[dict] = []

    def fake_submitter(payload):
        calls.append(dict(payload))
        return {"order_submitted": True, "position_opened": False, "paper_order_id": "paper_1"}

    settings = LSRV2SupervisedPaperSubmitSettings(
        data_dir=str(tmp_path),
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SINGLE_PAPER_ORDER",
        max_orders=1,
    )
    report = build_lsr_v2_supervised_paper_submit_report_from_files(
        data_dir=tmp_path,
        settings=settings,
        paper_submitter=fake_submitter,
    )
    assert report["status"] == "PASS"
    assert report["decision"] == EXECUTED_DECISION
    assert len(calls) == 1
    assert report["would_submit_count"] == 1
    assert report["broker_submit_called"] is True
    assert report["orders_submitted_by_lsr_v2_submit"] == 1
    assert report["positions_opened_by_lsr_v2_submit"] == 0


def test_hostile_preflight_submit_attempt_is_rejected(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_supervised_paper_submit_preflight.jsonl", _preflight("pc_hostile", hostile=True))
    settings = LSRV2SupervisedPaperSubmitSettings(
        data_dir=str(tmp_path),
        submit_arm="1",
        submit_confirmation="I_UNDERSTAND_SINGLE_PAPER_ORDER",
    )
    report = build_lsr_v2_supervised_paper_submit_report_from_files(data_dir=tmp_path, settings=settings)
    assert report["status"] == "WARN"
    assert report["decision"] == REJECT_DECISION
    assert "safety_violation_detected" in report["blockers"]
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_lsr_v2_submit"] == 0
