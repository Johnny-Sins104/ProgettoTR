from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_order_intent_audit import ORDER_INTENT_EVENT_TYPE
from trading_bot.core.lsr_v2_paper_broker_handoff_dry_run import (
    HANDOFF_EVENT_TYPE,
    READY_DECISION,
    NO_CREATE_DECISION,
    LSRV2PaperBrokerHandoffDryRunSettings,
    build_lsr_v2_paper_broker_payload_from_intent,
    build_lsr_v2_paper_broker_handoff_event,
    build_lsr_v2_paper_broker_handoff_dry_run_report_from_files,
    validate_lsr_v2_paper_order_payload,
)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _intent(cycle_id: str = "pc_test", symbol: str = "BTC/USDT", would_create_order: bool = True) -> dict:
    return {
        "event_type": ORDER_INTENT_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "timeframe": "5m",
        "candidate_id": f"{symbol}_cand_1",
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
        "operator_enable": True,
        "operator_confirmation_ok": True,
        "operator_authorized": True,
        "would_route": True,
        "would_create_order": would_create_order,
        "would_submit": False,
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "orders_submitted_by_lsr_v2_order_intent": 0,
        "positions_opened_by_lsr_v2_order_intent": 0,
    }


def test_payload_schema_valid_for_buy_intent() -> None:
    payload = build_lsr_v2_paper_broker_payload_from_intent(_intent())
    valid, reasons = validate_lsr_v2_paper_order_payload(payload)

    assert valid is True
    assert reasons == []
    assert payload["source"] == "lsr_v2_order_intent"
    assert payload["order_type"] == "LIMIT"
    assert payload["quantity"] == 2.5
    assert payload["payload_valid"] is True


def test_handoff_event_is_fail_closed_even_when_payload_valid() -> None:
    event = build_lsr_v2_paper_broker_handoff_event(order_intent=_intent())

    assert event["event_type"] == HANDOFF_EVENT_TYPE
    assert event["payload_valid"] is True
    assert event["would_create_paper_order"] is True
    assert event["would_submit_to_paper_broker"] is False
    assert event["broker_submit_called"] is False
    assert event["blocked_reason"] == "paper_broker_submit_still_disabled"
    assert event["orders_submitted_by_lsr_v2_handoff"] == 0
    assert event["positions_opened_by_lsr_v2_handoff"] == 0


def test_report_from_order_intent_jsonl_is_strict_cycle_scoped(tmp_path: Path) -> None:
    intent_path = tmp_path / "lsr_v2_order_intent_audit.jsonl"
    _append_jsonl(intent_path, _intent("pc_old"))
    _append_jsonl(intent_path, _intent("pc_new"))
    (tmp_path / "lsr_v2_order_intent_audit_report.json").write_text(json.dumps({"cycle_id": "pc_new"}), encoding="utf-8")

    report = build_lsr_v2_paper_broker_handoff_dry_run_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_new"
    assert report["strict_cycle_scope"] is True
    assert report["order_intent_events"] == 1
    assert report["handoff_dry_run_events"] == 1
    assert report["would_create_paper_order_count"] == 1
    assert report["would_submit_to_paper_broker_count"] == 0
    assert report["broker_submit_called"] is False
    assert report["historical_order_intent_events"] == 1
    assert (tmp_path / "lsr_v2_paper_broker_handoff_dry_run_report.json").exists()
    assert (tmp_path / "lsr_v2_paper_broker_handoff_dry_run.jsonl").exists()


def test_non_creatable_intent_does_not_build_handoff_payload(tmp_path: Path) -> None:
    intent_path = tmp_path / "lsr_v2_order_intent_audit.jsonl"
    _append_jsonl(intent_path, _intent("pc_no_create", would_create_order=False))
    (tmp_path / "lsr_v2_order_intent_audit_report.json").write_text(json.dumps({"cycle_id": "pc_no_create"}), encoding="utf-8")

    report = build_lsr_v2_paper_broker_handoff_dry_run_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == NO_CREATE_DECISION
    assert report["handoff_dry_run_events"] == 0
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_lsr_v2_handoff"] == 0
    assert report["positions_opened_by_lsr_v2_handoff"] == 0


def test_invalid_sell_payload_fails_schema_validation() -> None:
    intent = _intent()
    intent.update({"side": "SELL", "entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0})
    payload = build_lsr_v2_paper_broker_payload_from_intent(intent)
    valid, reasons = validate_lsr_v2_paper_order_payload(payload)

    assert valid is False
    assert "sell_stop_not_above_entry" in reasons
    assert "sell_take_profit_not_below_entry" in reasons
