"""Prompt 29.4.4s-10v — LSR-v2 second trade paper broker handoff dry-run.

Converts the second-trade route/order-intent preflight into a paper-broker
compatible payload audit.  This layer is deliberately fail-closed: it never
calls PaperBrokerAdapter, never submits an order, never opens a position, and
never mutates paper state/status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

try:  # package import in full project
    from .lsr_v2_second_trade_route_preflight import (  # type: ignore
        JSONL_NAME as ROUTE_JSONL_NAME,
        REPORT_NAME as ROUTE_REPORT_NAME,
        SECOND_TRADE_INTENT_EVENT_TYPE,
        _event_cycle,
        _iter_jsonl_tail,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_second_trade_route_preflight import (  # type: ignore
        JSONL_NAME as ROUTE_JSONL_NAME,
        REPORT_NAME as ROUTE_REPORT_NAME,
        SECOND_TRADE_INTENT_EVENT_TYPE,
        _event_cycle,
        _iter_jsonl_tail,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
    )

PROMPT_ID = "29.4.4s-10v"
HANDOFF_EVENT_TYPE = "LSR_V2_SECOND_TRADE_PAPER_BROKER_HANDOFF_DRY_RUN"
REPORT_NAME = "lsr_v2_second_trade_handoff_dry_run_report.json"
JSONL_NAME = "lsr_v2_second_trade_handoff_dry_run.jsonl"
PAPER_EVENTS_NAME = "paper_events.jsonl"

READY_DECISION = "LSR_V2_SECOND_TRADE_HANDOFF_DRY_RUN_READY"
ROUTE_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_MISSING"
NO_INTENTS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_HANDOFF_NO_ORDER_INTENTS"
NO_CREATE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_HANDOFF_NO_CREATABLE_INTENTS"
INVALID_PAYLOAD_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_HANDOFF_PAYLOAD_INVALID"
SAFETY_BLOCKED_DECISION = "REJECT_LSR_V2_SECOND_TRADE_HANDOFF_SAFETY_FAILED"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_HANDOFF_ERROR"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _latest_completed_cycle_from_paper_events(rows: Iterable[Mapping[str, Any]]) -> str:
    cycle_id = ""
    for row in rows:
        event_type = str(row.get("event_type") or row.get("type") or "")
        if event_type == "CYCLE_COMPLETED" and _event_cycle(row):
            cycle_id = _event_cycle(row)
    return cycle_id


def _event_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("event_type") or ""),
        _event_cycle(row),
        str(row.get("symbol") or ""),
        str(row.get("candidate_id") or ""),
        str(row.get("timeframe") or ""),
    )


def _dedupe_intents(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in events:
        row = dict(raw)
        if row.get("event_type") != SECOND_TRADE_INTENT_EVENT_TYPE:
            continue
        key = _event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _round(value: Any, digits: int = 10) -> float:
    return round(_safe_float(value, 0.0), digits)


@dataclass(frozen=True)
class LSRV2SecondTradeHandoffDryRunSettings:
    data_dir: str = "data"
    route_report_name: str = ROUTE_REPORT_NAME
    route_jsonl_name: str = ROUTE_JSONL_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    max_event_lines: int = 50000
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    default_order_type: str = "LIMIT"
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_second_trade_order_intents(
    *,
    data_dir: str | Path,
    settings: LSRV2SecondTradeHandoffDryRunSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Select strict cycle-scoped second-trade order-intent rows.

    The s-10u route preflight JSONL is primary because it materializes the
    second-trade route and intent rows.  Reports/paper events are only used to
    infer a cycle id when not explicitly provided.
    """
    settings = settings or LSRV2SecondTradeHandoffDryRunSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    route_rows = _dedupe_intents(_iter_jsonl_tail(base / settings.route_jsonl_name, max_lines=settings.max_event_lines))
    route_report = _read_json(base / settings.route_report_name)
    paper_rows = _iter_jsonl_tail(base / settings.paper_events_name, max_lines=settings.max_event_lines)

    cycle_id = str(requested_cycle_id or route_report.get("cycle_id") or "")
    if not cycle_id:
        cycle_id = _latest_completed_cycle_from_paper_events(paper_rows)
    if not cycle_id:
        for row in reversed(route_rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break

    selected = [row for row in route_rows if not cycle_id or _event_cycle(row) == cycle_id]
    historical = [row for row in route_rows if _event_cycle(row) and _event_cycle(row) != cycle_id]
    metadata = {
        "prompt_id": PROMPT_ID,
        "event_source": "second_trade_route_preflight_jsonl",
        "strict_cycle_scope": True,
        "route_report_decision": route_report.get("decision"),
        "route_report_status": route_report.get("status"),
        "route_report_cycle_id": route_report.get("cycle_id"),
        "route_preflight_ready": _safe_bool(route_report.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(route_report.get("second_trade_order_intent_ready"), False),
        "historical_second_trade_order_intent_events": len(historical),
        "historical_would_create_order_events": sum(1 for row in historical if _safe_bool(row.get("would_create_order"), False)),
    }
    return cycle_id, selected, metadata


def validate_second_trade_paper_order_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    symbol = str(payload.get("symbol") or "")
    side = str(payload.get("side") or "").upper()
    order_type = str(payload.get("order_type") or "").upper()
    entry = _safe_float(payload.get("entry_price"), 0.0)
    stop = _safe_float(payload.get("stop_loss"), 0.0)
    take = _safe_float(payload.get("take_profit"), 0.0)
    qty = _safe_float(payload.get("quantity"), 0.0)
    risk_amount = _safe_float(payload.get("risk_amount"), 0.0)
    notional = _safe_float(payload.get("notional"), 0.0)

    if not symbol:
        reasons.append("symbol_missing")
    if side not in {"BUY", "SELL"}:
        reasons.append("side_invalid")
    if order_type not in {"LIMIT", "MARKET", "STOP_LIMIT", "STOP_MARKET"}:
        reasons.append("order_type_invalid")
    if entry <= 0.0:
        reasons.append("entry_price_invalid")
    if stop <= 0.0:
        reasons.append("stop_loss_invalid")
    if take <= 0.0:
        reasons.append("take_profit_invalid")
    if qty <= 0.0:
        reasons.append("quantity_invalid")
    if risk_amount <= 0.0:
        reasons.append("risk_amount_invalid")
    if notional <= 0.0:
        reasons.append("notional_invalid")
    if side == "BUY" and stop >= entry:
        reasons.append("buy_stop_not_below_entry")
    if side == "BUY" and take <= entry:
        reasons.append("buy_take_profit_not_above_entry")
    if side == "SELL" and stop <= entry:
        reasons.append("sell_stop_not_above_entry")
    if side == "SELL" and take >= entry:
        reasons.append("sell_take_profit_not_below_entry")
    return not reasons, reasons


def build_second_trade_paper_broker_payload_from_intent(
    intent: Mapping[str, Any],
    *,
    settings: LSRV2SecondTradeHandoffDryRunSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeHandoffDryRunSettings()
    order_type = str(intent.get("order_type") or settings.default_order_type or "LIMIT").upper()
    payload = {
        "source": "lsr_v2_second_trade_order_intent",
        "profile_name": str(intent.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(intent.get("selected_overlay_id") or settings.selected_overlay_id),
        "cycle_id": str(intent.get("cycle_id") or ""),
        "symbol": str(intent.get("symbol") or ""),
        "timeframe": str(intent.get("timeframe") or ""),
        "candidate_id": str(intent.get("candidate_id") or ""),
        "side": str(intent.get("side") or "").upper(),
        "order_type": order_type,
        "entry_price": _round(intent.get("entry_price")),
        "stop_loss": _round(intent.get("stop_loss")),
        "take_profit": _round(intent.get("take_profit")),
        "risk_per_trade_pct": _safe_float(intent.get("risk_per_trade_pct"), 0.0025),
        "risk_amount": _round(intent.get("risk_amount")),
        "quantity": _round(intent.get("position_size")),
        "position_size": _round(intent.get("position_size")),
        "notional": _round(intent.get("notional")),
        "max_positions": _safe_int(intent.get("max_positions"), 1),
        "second_trade_would_route": _safe_bool(intent.get("second_trade_would_route"), False),
        "would_route": _safe_bool(intent.get("would_route"), False),
        "would_create_order": _safe_bool(intent.get("would_create_order"), False),
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }
    valid, reasons = validate_second_trade_paper_order_payload(payload)
    payload["payload_valid"] = bool(valid)
    payload["payload_invalid_reasons"] = reasons
    return payload


def build_second_trade_paper_broker_handoff_event(
    *,
    order_intent: Mapping[str, Any],
    settings: LSRV2SecondTradeHandoffDryRunSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeHandoffDryRunSettings()
    payload = build_second_trade_paper_broker_payload_from_intent(order_intent, settings=settings)
    payload_valid = _safe_bool(payload.get("payload_valid"), False)
    creatable = _safe_bool(order_intent.get("would_create_order"), False) and payload_valid
    blocked_reasons = ["second_trade_paper_broker_submit_still_disabled"]
    if not _safe_bool(order_intent.get("would_create_order"), False):
        blocked_reasons.append("order_intent_not_creatable")
    if not payload_valid:
        blocked_reasons.extend(str(x) for x in payload.get("payload_invalid_reasons") or [])
    return {
        "event_type": HANDOFF_EVENT_TYPE,
        "prompt": PROMPT_ID,
        "ts": utc_now_iso(),
        "cycle_id": str(order_intent.get("cycle_id") or ""),
        "symbol": str(order_intent.get("symbol") or ""),
        "timeframe": str(order_intent.get("timeframe") or ""),
        "candidate_id": str(order_intent.get("candidate_id") or ""),
        "profile_name": payload.get("profile_name"),
        "selected_overlay_id": payload.get("selected_overlay_id"),
        "source": "lsr_v2_second_trade_route_preflight",
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "payload": payload,
        "payload_valid": bool(payload_valid),
        "payload_invalid_reasons": payload.get("payload_invalid_reasons") or [],
        "side": payload.get("side"),
        "order_type": payload.get("order_type"),
        "entry_price": payload.get("entry_price"),
        "stop_loss": payload.get("stop_loss"),
        "take_profit": payload.get("take_profit"),
        "risk_per_trade_pct": payload.get("risk_per_trade_pct"),
        "risk_amount": payload.get("risk_amount"),
        "position_size": payload.get("position_size"),
        "quantity": payload.get("quantity"),
        "notional": payload.get("notional"),
        "max_positions": payload.get("max_positions"),
        "second_trade_would_route": _safe_bool(order_intent.get("second_trade_would_route"), False),
        "would_create_paper_order": bool(creatable),
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "blocked_reason": blocked_reasons[0],
        "blocked_reasons": blocked_reasons,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_handoff": 0,
        "positions_opened_by_second_trade_handoff": 0,
        "audit_only": True,
    }


def build_lsr_v2_second_trade_handoff_dry_run_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondTradeHandoffDryRunSettings | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or LSRV2SecondTradeHandoffDryRunSettings(data_dir=str(base))
    route_report = _read_json(base / settings.route_report_name)
    selected_cycle_id, intents, metadata = select_second_trade_order_intents(data_dir=base, settings=settings, requested_cycle_id=cycle_id)

    route_ready = route_report.get("status") == "PASS" and route_report.get("decision") == "LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_READY"
    route_intent_ready = _safe_bool(route_report.get("second_trade_order_intent_ready"), False)
    unsafe_upstream = any(_safe_bool(route_report.get(key), False) for key in [
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "second_trade_execute_enabled",
        "second_trade_submit_enabled",
        "paper_order_submission_enabled",
        "broker_submit_called_by_second_trade_route_preflight",
    ])
    upstream_activity = any(_safe_int(route_report.get(key), 0) > 0 for key in [
        "orders_submitted_by_second_trade_route_preflight",
        "positions_opened_by_second_trade_route_preflight",
        "positions_closed_by_second_trade_route_preflight",
        "would_submit_count",
        "would_submit_to_paper_broker_count",
    ])

    creatable_intents = [row for row in intents if _safe_bool(row.get("would_create_order"), False)]
    handoff_events = [build_second_trade_paper_broker_handoff_event(order_intent=row, settings=settings) for row in creatable_intents]
    payload_valid_count = sum(1 for row in handoff_events if _safe_bool(row.get("payload_valid"), False))
    payload_invalid_count = len(handoff_events) - payload_valid_count
    would_create_paper_order_count = sum(1 for row in handoff_events if _safe_bool(row.get("would_create_paper_order"), False))

    blockers: list[str] = []
    if not route_ready or not route_intent_ready:
        blockers.append("second_trade_route_preflight_not_ready")
    if unsafe_upstream:
        blockers.append("unsafe_upstream_flag_detected")
    if upstream_activity:
        blockers.append("upstream_activity_detected")
    if not intents:
        blockers.append("second_trade_order_intent_missing")
    if intents and not creatable_intents:
        blockers.append("second_trade_order_intent_not_creatable")
    if payload_invalid_count > 0:
        blockers.append("payload_invalid")

    if unsafe_upstream or upstream_activity:
        decision = SAFETY_BLOCKED_DECISION
        status = "FAIL"
    elif not route_ready or not route_intent_ready:
        decision = ROUTE_MISSING_DECISION
        status = "WARN"
    elif not intents:
        decision = NO_INTENTS_DECISION
        status = "WARN"
    elif not creatable_intents:
        decision = NO_CREATE_DECISION
        status = "WARN"
    elif payload_invalid_count > 0:
        decision = INVALID_PAYLOAD_DECISION
        status = "WARN"
    else:
        decision = READY_DECISION
        status = "PASS"

    classification_labels: list[str] = []
    if status == "PASS":
        classification_labels.extend(["SECOND_TRADE_HANDOFF_DRY_RUN_READY", "PAYLOAD_VALID", "SUBMIT_STILL_DISABLED"])
    elif decision == ROUTE_MISSING_DECISION:
        classification_labels.append("SECOND_TRADE_ROUTE_PREFLIGHT_MISSING")
    elif decision == NO_INTENTS_DECISION:
        classification_labels.append("SECOND_TRADE_ORDER_INTENT_MISSING")
    elif decision == NO_CREATE_DECISION:
        classification_labels.append("SECOND_TRADE_ORDER_INTENT_NOT_CREATABLE")
    elif decision == INVALID_PAYLOAD_DECISION:
        classification_labels.append("SECOND_TRADE_HANDOFF_PAYLOAD_INVALID")
    else:
        classification_labels.append("SECOND_TRADE_HANDOFF_SAFETY_FAILED")

    total_risk_amount = round(sum(_safe_float(row.get("risk_amount"), 0.0) for row in handoff_events if _safe_bool(row.get("would_create_paper_order"), False)), 10)
    total_notional = round(sum(_safe_float(row.get("notional"), 0.0) for row in handoff_events if _safe_bool(row.get("would_create_paper_order"), False)), 10)
    report = {
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": blockers,
        "cycle_id": selected_cycle_id,
        "event_source": "second_trade_route_preflight_jsonl",
        "strict_cycle_scope": True,
        "route_report_decision": route_report.get("decision"),
        "route_report_status": route_report.get("status"),
        "second_trade_eligible": _safe_bool(route_report.get("second_trade_eligible"), False),
        "second_trade_rearm_ready": _safe_bool(route_report.get("second_trade_rearm_ready"), False),
        "second_trade_route_preflight_ready": _safe_bool(route_report.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(route_report.get("second_trade_order_intent_ready"), False),
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "broker_submit_called": False,
        "broker_submit_called_by_second_trade_handoff": False,
        "orders_submitted_by_second_trade_handoff": 0,
        "positions_opened_by_second_trade_handoff": 0,
        "positions_closed_by_second_trade_handoff": 0,
        "paper_state_modified_by_second_trade_handoff": False,
        "paper_status_modified_by_second_trade_handoff": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "second_trade_order_intent_events": len(intents),
        "creatable_order_intents": len(creatable_intents),
        "handoff_dry_run_events": len(handoff_events),
        "payload_valid_count": payload_valid_count,
        "payload_invalid_count": payload_invalid_count,
        "would_create_paper_order_count": would_create_paper_order_count,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "total_risk_amount": total_risk_amount,
        "total_notional": total_notional,
        "symbols": sorted({str(row.get("symbol") or "") for row in handoff_events if row.get("symbol")}),
        "historical_second_trade_order_intent_events": metadata.get("historical_second_trade_order_intent_events", 0),
        "historical_would_create_order_events": metadata.get("historical_would_create_order_events", 0),
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }

    if write_outputs:
        _write_json(base / settings.report_name, report)
        _write_jsonl_replace(base / settings.jsonl_name, handoff_events)
    return report
