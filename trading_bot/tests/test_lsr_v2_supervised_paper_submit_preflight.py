from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_paper_broker_handoff_dry_run import HANDOFF_EVENT_TYPE
from trading_bot.core.lsr_v2_supervised_paper_submit_preflight import (
    EVENT_TYPE,
    HANDOFF_MISSING_DECISION,
    OPERATOR_MISSING_DECISION,
    READY_DECISION,
    REJECT_DECISION,
    build_lsr_v2_submit_preflight_report_from_files,
    build_lsr_v2_supervised_paper_submit_preflight_event,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _handoff(cycle_id: str = "pc_test", symbol: str = "BTC/USDT", hostile: bool = False) -> dict:
    return {
        "event_type": HANDOFF_EVENT_TYPE,
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
        "would_route": True,
        "would_create_order": True,
        "would_create_paper_order": True,
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
        "orders_submitted_by_lsr_v2_handoff": 0,
        "positions_opened_by_lsr_v2_handoff": 0,
        "payload": {
            "cycle_id": cycle_id,
            "symbol": symbol,
            "side": "BUY",
            "order_type": "LIMIT",
            "entry_price": 100.0,
            "stop_loss": 99.0,
            "take_profit": 102.0,
            "risk_amount": 2.5,
            "position_size": 2.5,
            "quantity": 2.5,
            "notional": 250.0,
            "payload_valid": True,
        },
    }


def _reports(data_dir: Path, cycle_id: str = "pc_test", operator_ok: bool = True, handoff_ok: bool = True) -> None:
    _write_json(data_dir / "lsr_v2_promotion_gate_report.json", {
        "decision": "LSR_V2_PAPER_SUPERVISED_CANDIDATE",
        "paper_supervised_candidate": True,
    })
    _write_json(data_dir / "lsr_v2_operator_route_audit_report.json", {
        "decision": "LSR_V2_OPERATOR_ROUTE_AUDIT_READY_DIAGNOSTIC",
        "cycle_id": cycle_id,
        "operator_enable": operator_ok,
        "operator_confirmation_ok": operator_ok,
        "would_route_count": 1 if operator_ok else 0,
    })
    _write_json(data_dir / "lsr_v2_order_intent_audit_report.json", {
        "decision": "LSR_V2_ORDER_INTENT_AUDIT_READY_DIAGNOSTIC",
        "cycle_id": cycle_id,
        "would_create_order_count": 1,
    })
    _write_json(data_dir / "lsr_v2_paper_broker_handoff_dry_run_report.json", {
        "decision": "LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC" if handoff_ok else "KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_PAYLOAD_INVALID",
        "cycle_id": cycle_id,
        "payload_valid_count": 1 if handoff_ok else 0,
        "would_create_paper_order_count": 1 if handoff_ok else 0,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "orders_submitted_by_lsr_v2_handoff": 0,
        "positions_opened_by_lsr_v2_handoff": 0,
    })


def test_preflight_event_is_disabled_by_default_even_when_ready() -> None:
    event = build_lsr_v2_supervised_paper_submit_preflight_event(
        handoff_event=_handoff(),
        prerequisites={
            "promotion_gate_pass": True,
            "operator_route_pass": True,
            "operator_enable": True,
            "operator_confirmation_ok": True,
            "operator_would_route_count": 1,
            "order_intent_pass": True,
            "would_create_order_count": 1,
            "handoff_pass": True,
        },
    )
    assert event["event_type"] == EVENT_TYPE
    assert event["would_prepare_submit"] is True
    assert event["submit_enabled"] is False
    assert event["would_submit_to_paper_broker"] is False
    assert event["broker_submit_called"] is False
    assert event["orders_submitted_by_lsr_v2_submit_preflight"] == 0
    assert event["positions_opened_by_lsr_v2_submit_preflight"] == 0
    assert event["blocked_reason"] == "paper_submit_disabled_by_default"


def test_ready_report_from_handoff_and_upstream_reports(tmp_path: Path) -> None:
    _reports(tmp_path, cycle_id="pc_ready")
    _append_jsonl(tmp_path / "lsr_v2_paper_broker_handoff_dry_run.jsonl", _handoff("pc_old"))
    _append_jsonl(tmp_path / "lsr_v2_paper_broker_handoff_dry_run.jsonl", _handoff("pc_ready"))

    report = build_lsr_v2_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_ready"
    assert report["strict_cycle_scope"] is True
    assert report["handoff_dry_run_events"] == 1
    assert report["submit_preflight_events"] == 1
    assert report["would_prepare_submit_count"] == 1
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_lsr_v2_submit_preflight"] == 0
    assert report["historical_handoff_events"] == 1
    assert (tmp_path / "lsr_v2_supervised_paper_submit_preflight_report.json").exists()
    assert (tmp_path / "lsr_v2_supervised_paper_submit_preflight.jsonl").exists()


def test_missing_handoff_returns_handoff_missing(tmp_path: Path) -> None:
    _reports(tmp_path, cycle_id="pc_missing")

    report = build_lsr_v2_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == HANDOFF_MISSING_DECISION
    assert report["handoff_dry_run_events"] == 0
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_lsr_v2_submit_preflight"] == 0


def test_operator_confirmation_missing_blocks_preflight(tmp_path: Path) -> None:
    _reports(tmp_path, cycle_id="pc_no_operator", operator_ok=False)
    _append_jsonl(tmp_path / "lsr_v2_paper_broker_handoff_dry_run.jsonl", _handoff("pc_no_operator"))

    report = build_lsr_v2_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == OPERATOR_MISSING_DECISION
    assert "operator_confirmation_missing" in report["blockers"]
    assert report["would_submit_to_paper_broker_count"] == 0


def test_hostile_handoff_submit_attempt_is_rejected(tmp_path: Path) -> None:
    _reports(tmp_path, cycle_id="pc_hostile")
    _append_jsonl(tmp_path / "lsr_v2_paper_broker_handoff_dry_run.jsonl", _handoff("pc_hostile", hostile=True))

    report = build_lsr_v2_submit_preflight_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == REJECT_DECISION
    assert "safety_violation_detected" in report["blockers"]
    assert report["would_submit_count"] == 0
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["orders_submitted_by_lsr_v2_submit_preflight"] == 0
