from __future__ import annotations

import json
from pathlib import Path

from trading_bot.core.lsr_v2_order_intent_audit import (
    ORDER_INTENT_EVENT_TYPE,
    READY_DECISION,
    NO_ROUTE_DECISION,
    LSRV2OrderIntentAuditSettings,
    build_lsr_v2_order_intent_event,
    build_lsr_v2_order_intent_report_from_files,
    build_lsr_v2_order_intents_from_events,
)
from trading_bot.core.lsr_v2_runtime_bridge import BRIDGE_EVENT_TYPE, RUNTIME_CANDIDATE_EVENT_TYPE


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _candidate(cycle_id: str = "pc_test", symbol: str = "BTC/USDT") -> dict:
    return {
        "event_type": RUNTIME_CANDIDATE_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "timeframe": "5m",
        "candidate_id": f"{symbol}_cand_1",
        "candidate_ready": True,
        "side": "BUY",
        "levels": {"entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0},
        "quality": {"grade": "A"},
        "would_submit": False,
        "broker_submit_called": False,
    }


def _bridge(cycle_id: str = "pc_test", symbol: str = "BTC/USDT", would_route: bool = True) -> dict:
    return {
        "event_type": BRIDGE_EVENT_TYPE,
        "runtime_cycle_scoped": True,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "timeframe": "5m",
        "candidate_id": f"{symbol}_cand_1",
        "candidate_ready": True,
        "side": "BUY",
        "entry_price": 100.0,
        "stop_loss": 99.0,
        "take_profit": 102.0,
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
        "operator_enable": True,
        "operator_confirmation_ok": True,
        "operator_authorized": True,
        "would_route": would_route,
        "would_submit": False,
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
    }


def test_build_order_intent_from_route_event_fail_closed() -> None:
    intent = build_lsr_v2_order_intent_event(
        bridge_event=_bridge(),
        candidate_event=_candidate(),
        settings=LSRV2OrderIntentAuditSettings(account_equity=1000.0, risk_per_trade_pct=0.0025),
    )

    assert intent["event_type"] == ORDER_INTENT_EVENT_TYPE
    assert intent["would_create_order"] is True
    assert intent["would_submit"] is False
    assert intent["broker_submit_called"] is False
    assert intent["blocked_reason"] == "paper_order_submit_still_disabled"
    assert intent["risk_amount"] == 2.5
    assert intent["position_size"] == 2.5
    assert intent["notional"] == 250.0
    assert intent["orders_submitted_by_lsr_v2_order_intent"] == 0
    assert intent["positions_opened_by_lsr_v2_order_intent"] == 0


def test_no_would_route_does_not_create_intent() -> None:
    intents = build_lsr_v2_order_intents_from_events([_candidate(), _bridge(would_route=False)])
    assert intents == []


def test_report_from_paper_events_is_strict_cycle_scoped(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    _append_jsonl(events_path, {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_old"})
    _append_jsonl(events_path, _candidate("pc_old"))
    _append_jsonl(events_path, _bridge("pc_old"))
    _append_jsonl(events_path, {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_new"})
    _append_jsonl(events_path, _candidate("pc_new"))
    _append_jsonl(events_path, _bridge("pc_new"))

    report = build_lsr_v2_order_intent_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == READY_DECISION
    assert report["cycle_id"] == "pc_new"
    assert report["event_source"] == "paper_events_jsonl"
    assert report["strict_cycle_scope"] is True
    assert report["runtime_candidate_events"] == 1
    assert report["runtime_bridge_events"] == 1
    assert report["would_route_count"] == 1
    assert report["order_intent_events"] == 1
    assert report["would_create_order_count"] == 1
    assert report["would_submit_count"] == 0
    assert report["historical_lsr_v2_events"] == 2
    assert (tmp_path / "lsr_v2_order_intent_audit_report.json").exists()
    assert (tmp_path / "lsr_v2_order_intent_audit.jsonl").exists()


def test_report_without_route_events_stays_pass_no_submit(tmp_path: Path) -> None:
    events_path = tmp_path / "paper_events.jsonl"
    _append_jsonl(events_path, {"event_type": "CYCLE_COMPLETED", "cycle_id": "pc_no_route"})
    _append_jsonl(events_path, _candidate("pc_no_route"))
    _append_jsonl(events_path, _bridge("pc_no_route", would_route=False))

    report = build_lsr_v2_order_intent_report_from_files(data_dir=tmp_path)

    assert report["status"] == "PASS"
    assert report["decision"] == NO_ROUTE_DECISION
    assert report["order_intent_events"] == 0
    assert report["would_submit_count"] == 0
    assert report["orders_submitted_by_lsr_v2_order_intent"] == 0
    assert report["positions_opened_by_lsr_v2_order_intent"] == 0


def test_runtime_jsonl_fallback_deduplicates_current_cycle(tmp_path: Path) -> None:
    runtime_path = tmp_path / "lsr_v2_runtime_bridge_audit.jsonl"
    candidate = _candidate("pc_fallback")
    bridge = _bridge("pc_fallback")
    _append_jsonl(runtime_path, candidate)
    _append_jsonl(runtime_path, bridge)
    _append_jsonl(runtime_path, candidate)
    _append_jsonl(runtime_path, bridge)

    report = build_lsr_v2_order_intent_report_from_files(data_dir=tmp_path, cycle_id="pc_fallback")

    assert report["event_source"] == "runtime_bridge_jsonl_fallback"
    assert report["runtime_candidate_events"] == 1
    assert report["runtime_bridge_events"] == 1
    assert report["order_intent_events"] == 1
    assert report["would_submit_count"] == 0
