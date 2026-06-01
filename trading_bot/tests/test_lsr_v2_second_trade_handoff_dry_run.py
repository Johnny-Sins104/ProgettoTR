from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_second_trade_route_preflight import SECOND_TRADE_INTENT_EVENT_TYPE
from trading_bot.core.lsr_v2_second_trade_handoff_dry_run import (
    HANDOFF_EVENT_TYPE,
    READY_DECISION,
    NO_CREATE_DECISION,
    ROUTE_MISSING_DECISION,
    build_second_trade_paper_broker_payload_from_intent,
    build_second_trade_paper_broker_handoff_event,
    build_lsr_v2_second_trade_handoff_dry_run_report_from_files,
    validate_second_trade_paper_order_payload,
)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _route_report(cycle_id: str = "pc_test") -> dict:
    return {
        "status": "PASS",
        "decision": "LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_READY",
        "cycle_id": cycle_id,
        "second_trade_eligible": True,
        "second_trade_rearm_ready": True,
        "second_trade_route_preflight_ready": True,
        "second_trade_order_intent_ready": True,
        "paper_order_submission_enabled": False,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "broker_submit_called_by_second_trade_route_preflight": False,
        "orders_submitted_by_second_trade_route_preflight": 0,
        "positions_opened_by_second_trade_route_preflight": 0,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
    }


def _intent(cycle_id: str = "pc_test", symbol: str = "BTC/USDT", would_create_order: bool = True) -> dict:
    return {
        "event_type": SECOND_TRADE_INTENT_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "timeframe": "5m",
        "candidate_id": f"{symbol}_cand_2",
        "side": "BUY",
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "risk_per_trade_pct": 0.0025,
        "risk_amount": 2.5,
        "position_size": 2.5,
        "notional": 250.0,
        "max_positions": 1,
        "second_trade_would_route": True,
        "would_route": True,
        "would_create_order": would_create_order,
        "would_submit": False,
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "orders_submitted_by_second_trade_route_preflight": 0,
        "positions_opened_by_second_trade_route_preflight": 0,
    }


def test_payload_schema_valid_for_second_trade_buy_intent() -> None:
    payload = build_second_trade_paper_broker_payload_from_intent(_intent())
    valid, reasons = validate_second_trade_paper_order_payload(payload)

    assert valid is True
    assert reasons == []
    assert payload["source"] == "lsr_v2_second_trade_order_intent"
    assert payload["paper_broker_adapter"] == "PaperBrokerAdapter"
    assert payload["payload_valid"] is True


def test_handoff_event_is_fail_closed_even_when_payload_valid() -> None:
    event = build_second_trade_paper_broker_handoff_event(order_intent=_intent())

    assert event["event_type"] == HANDOFF_EVENT_TYPE
    assert event["payload_valid"] is True
    assert event["would_create_paper_order"] is True
    assert event["would_submit_to_paper_broker"] is False
    assert event["would_submit"] is False
    assert event["broker_submit_called"] is False
    assert event["blocked_reason"] == "second_trade_paper_broker_submit_still_disabled"
    assert event["orders_submitted_by_second_trade_handoff"] == 0
    assert event["positions_opened_by_second_trade_handoff"] == 0


def test_report_from_second_trade_route_jsonl_is_strict_cycle_scoped(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_second_trade_route_preflight.jsonl", _intent("pc_old"))
    _append_jsonl(tmp_path / "lsr_v2_second_trade_route_preflight.jsonl", _intent("pc_new"))
    (tmp_path / "lsr_v2_second_trade_route_preflight_report.json").write_text(json.dumps(_route_report("pc_new")), encoding="utf-8")

    report = build_lsr_v2_second_trade_handoff_dry_run_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_new"
    assert report["strict_cycle_scope"] is True
    assert report["second_trade_order_intent_events"] == 1
    assert report["handoff_dry_run_events"] == 1
    assert report["would_create_paper_order_count"] == 1
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["historical_second_trade_order_intent_events"] == 1
    assert (tmp_path / "lsr_v2_second_trade_handoff_dry_run_report.json").exists()
    assert (tmp_path / "lsr_v2_second_trade_handoff_dry_run.jsonl").exists()


def test_non_creatable_second_trade_intent_does_not_build_handoff_payload(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_second_trade_route_preflight.jsonl", _intent("pc_no_create", would_create_order=False))
    (tmp_path / "lsr_v2_second_trade_route_preflight_report.json").write_text(json.dumps(_route_report("pc_no_create")), encoding="utf-8")

    report = build_lsr_v2_second_trade_handoff_dry_run_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == NO_CREATE_DECISION
    assert report["handoff_dry_run_events"] == 0
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_second_trade_handoff"] == 0
    assert report["positions_opened_by_second_trade_handoff"] == 0


def test_route_preflight_missing_blocks_handoff(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_second_trade_route_preflight.jsonl", _intent("pc_missing_route"))
    (tmp_path / "lsr_v2_second_trade_route_preflight_report.json").write_text(json.dumps({"cycle_id": "pc_missing_route", "status": "WARN"}), encoding="utf-8")

    report = build_lsr_v2_second_trade_handoff_dry_run_report_from_files(data_dir=tmp_path)

    assert report["status"] == "WARN"
    assert report["decision"] == ROUTE_MISSING_DECISION
    assert report["handoff_dry_run_events"] == 1  # diagnostic row is still materialized
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False


def test_invalid_sell_payload_fails_schema_validation() -> None:
    intent = _intent()
    intent.update({"side": "SELL", "entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0})
    payload = build_second_trade_paper_broker_payload_from_intent(intent)
    valid, reasons = validate_second_trade_paper_order_payload(payload)

    assert valid is False
    assert "sell_stop_not_above_entry" in reasons
    assert "sell_take_profit_not_below_entry" in reasons


def test_unsafe_upstream_flags_reject(tmp_path: Path) -> None:
    _append_jsonl(tmp_path / "lsr_v2_second_trade_route_preflight.jsonl", _intent("pc_unsafe"))
    report = _route_report("pc_unsafe")
    report["paper_order_submission_enabled"] = True
    (tmp_path / "lsr_v2_second_trade_route_preflight_report.json").write_text(json.dumps(report), encoding="utf-8")

    out = build_lsr_v2_second_trade_handoff_dry_run_report_from_files(data_dir=tmp_path)

    assert out["status"] == "FAIL"
    assert out["orders_submitted_by_second_trade_handoff"] == 0
    assert out["positions_opened_by_second_trade_handoff"] == 0
    assert out["broker_submit_called"] is False
