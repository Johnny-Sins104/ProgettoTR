"""Prompt 29.4.4s-10al — LSR-v2 third paper-trade handoff dry-run.

This module consumes the third-trade route/order-intent preflight from
29.4.4s-10ak and validates that the resulting paper order payload would be
acceptable for a PaperBrokerAdapter handoff.  It is intentionally dry-run only:
it never submits an order, never calls a broker, never opens/closes a position,
and never mutates paper state/status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

try:  # package import in the full project
    from .lsr_v2_third_trade_route_preflight import (  # type: ignore
        JSONL_NAME as ROUTE_JSONL_NAME,
        READY_DECISION as ROUTE_READY_DECISION,
        REPORT_NAME as ROUTE_REPORT_NAME,
        THIRD_TRADE_INTENT_EVENT_TYPE,
        THIRD_TRADE_ROUTE_EVENT_TYPE,
        PROFILE_NAME,
        SELECTED_OVERLAY_ID,
        _iter_jsonl_tail,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_third_trade_route_preflight import (  # type: ignore
        JSONL_NAME as ROUTE_JSONL_NAME,
        READY_DECISION as ROUTE_READY_DECISION,
        REPORT_NAME as ROUTE_REPORT_NAME,
        THIRD_TRADE_INTENT_EVENT_TYPE,
        THIRD_TRADE_ROUTE_EVENT_TYPE,
        PROFILE_NAME,
        SELECTED_OVERLAY_ID,
        _iter_jsonl_tail,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
    )

PROMPT_ID = "29.4.4s-10al"
EVENT_TYPE = "LSR_V2_THIRD_TRADE_HANDOFF_DRY_RUN"
REPORT_NAME = "lsr_v2_third_trade_handoff_dry_run_report.json"
JSONL_NAME = "lsr_v2_third_trade_handoff_dry_run.jsonl"

READY_DECISION = "LSR_V2_THIRD_TRADE_HANDOFF_DRY_RUN_READY"
ROUTE_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_ROUTE_PREFLIGHT_MISSING"
PAYLOAD_INVALID_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_HANDOFF_PAYLOAD_INVALID"
NO_CREATABLE_INTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_NO_CREATABLE_ORDER_INTENT"
REJECT_DECISION = "REJECT_LSR_V2_THIRD_TRADE_HANDOFF_SAFETY_FAILED"

PAPER_BROKER_ADAPTER_NAME = "PaperBrokerAdapter"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LSRV2ThirdTradeHandoffDryRunSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    route_report_name: str = ROUTE_REPORT_NAME
    route_jsonl_name: str = ROUTE_JSONL_NAME
    max_event_lines: int = 50000
    paper_broker_adapter: str = PAPER_BROKER_ADAPTER_NAME
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _event_cycle(row: Mapping[str, Any]) -> str:
    return str(row.get("cycle_id") or row.get("lsr_v2_runtime_cycle_id") or "")


def _dedupe_intents(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if row.get("event_type") != THIRD_TRADE_INTENT_EVENT_TYPE:
            continue
        key = (
            _event_cycle(row),
            str(row.get("symbol") or ""),
            str(row.get("candidate_id") or ""),
            str(row.get("timeframe") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _payload_from_intent(intent: Mapping[str, Any]) -> dict[str, Any]:
    qty = _safe_float(intent.get("quantity"), 0.0)
    if qty <= 0.0:
        qty = _safe_float(intent.get("position_size"), 0.0)
    return {
        "cycle_id": _event_cycle(intent),
        "symbol": str(intent.get("symbol") or ""),
        "timeframe": str(intent.get("timeframe") or ""),
        "candidate_id": str(intent.get("candidate_id") or ""),
        "profile_name": str(intent.get("profile_name") or PROFILE_NAME),
        "selected_overlay_id": str(intent.get("selected_overlay_id") or SELECTED_OVERLAY_ID),
        "side": str(intent.get("side") or "").upper(),
        "order_type": str(intent.get("order_type") or "LIMIT"),
        "entry_price": _safe_float(intent.get("entry_price"), 0.0),
        "stop_loss": _safe_float(intent.get("stop_loss"), 0.0),
        "take_profit": _safe_float(intent.get("take_profit"), 0.0),
        "risk_per_trade_pct": _safe_float(intent.get("risk_per_trade_pct"), 0.0025),
        "account_equity": _safe_float(intent.get("account_equity"), 1000.0),
        "risk_amount": _safe_float(intent.get("risk_amount"), 0.0),
        "position_size": _safe_float(intent.get("position_size"), 0.0),
        "quantity": qty,
        "notional": _safe_float(intent.get("notional"), 0.0),
        "max_positions": _safe_int(intent.get("max_positions"), 1),
    }


def _payload_valid(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    side = str(payload.get("side") or "").upper()
    entry = _safe_float(payload.get("entry_price"), 0.0)
    stop = _safe_float(payload.get("stop_loss"), 0.0)
    target = _safe_float(payload.get("take_profit"), 0.0)
    risk_amount = _safe_float(payload.get("risk_amount"), 0.0)
    qty = _safe_float(payload.get("quantity"), 0.0)
    notional = _safe_float(payload.get("notional"), 0.0)
    max_positions = _safe_int(payload.get("max_positions"), 0)
    if not str(payload.get("cycle_id") or ""):
        reasons.append("missing_cycle_id")
    if not str(payload.get("symbol") or ""):
        reasons.append("missing_symbol")
    if side not in {"BUY", "SELL"}:
        reasons.append("invalid_side")
    if entry <= 0.0:
        reasons.append("invalid_entry_price")
    if stop <= 0.0:
        reasons.append("invalid_stop_loss")
    if target <= 0.0:
        reasons.append("invalid_take_profit")
    if entry > 0.0 and stop > 0.0 and entry == stop:
        reasons.append("entry_equals_stop")
    if risk_amount <= 0.0:
        reasons.append("invalid_risk_amount")
    if qty <= 0.0:
        reasons.append("invalid_quantity")
    if notional <= 0.0:
        reasons.append("invalid_notional")
    if max_positions != 1:
        reasons.append("max_positions_not_one")
    return not reasons, reasons


def _route_report_ready(route_report: Mapping[str, Any]) -> bool:
    return (
        route_report.get("status") == "PASS"
        and route_report.get("decision") == ROUTE_READY_DECISION
        and _safe_bool(route_report.get("third_trade_route_preflight_ready"), False)
        and _safe_bool(route_report.get("third_trade_order_intent_ready"), False)
    )


def _unsafe_route_flags(route_report: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    unsafe_bool_keys = [
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "third_trade_submit_enabled",
        "third_trade_execute_enabled",
        "paper_order_submission_enabled",
        "routing_enabled",
        "execution_enabled",
        "broker_submit_called",
        "broker_submit_called_by_third_trade_route_preflight",
    ]
    unsafe_count_keys = [
        "orders_submitted_by_third_trade_route_preflight",
        "positions_opened_by_third_trade_route_preflight",
        "positions_closed_by_third_trade_route_preflight",
        "would_submit_count",
        "would_submit_to_paper_broker_count",
    ]
    for key in unsafe_bool_keys:
        if _safe_bool(route_report.get(key), False):
            blockers.append(f"route_report_{key}")
    for key in unsafe_count_keys:
        if _safe_int(route_report.get(key), 0) > 0:
            blockers.append(f"route_report_{key}")
    for row in rows:
        for key in unsafe_bool_keys:
            if _safe_bool(row.get(key), False):
                blockers.append(f"route_event_{key}")
        for key in ["orders_submitted_by_third_trade_route_preflight", "positions_opened_by_third_trade_route_preflight", "positions_closed_by_third_trade_route_preflight"]:
            if _safe_int(row.get(key), 0) > 0:
                blockers.append(f"route_event_{key}")
        if _safe_bool(row.get("would_submit"), False):
            blockers.append("route_event_would_submit")
        if _safe_bool(row.get("would_submit_to_paper_broker"), False):
            blockers.append("route_event_would_submit_to_paper_broker")
        if _safe_bool(row.get("broker_submit_called"), False):
            blockers.append("route_event_broker_submit_called")
    return sorted(set(blockers))


def build_third_trade_handoff_dry_run_event(*, intent: Mapping[str, Any], settings: LSRV2ThirdTradeHandoffDryRunSettings) -> dict[str, Any]:
    payload = _payload_from_intent(intent)
    payload_ok, invalid_reasons = _payload_valid(payload)
    would_create = bool(payload_ok and _safe_bool(intent.get("would_create_order"), False))
    return {
        "event_type": EVENT_TYPE,
        "prompt": PROMPT_ID,
        "ts": utc_now_iso(),
        "cycle_id": payload.get("cycle_id", ""),
        "symbol": payload.get("symbol", ""),
        "timeframe": payload.get("timeframe", ""),
        "candidate_id": payload.get("candidate_id", ""),
        "profile_name": payload.get("profile_name", PROFILE_NAME),
        "selected_overlay_id": payload.get("selected_overlay_id", SELECTED_OVERLAY_ID),
        "source": "lsr_v2_third_trade_route_preflight",
        "source_event_type": str(intent.get("event_type") or THIRD_TRADE_INTENT_EVENT_TYPE),
        "payload": payload,
        "payload_valid": bool(payload_ok),
        "payload_invalid_reasons": invalid_reasons,
        "side": payload.get("side", ""),
        "order_type": payload.get("order_type", "LIMIT"),
        "entry_price": payload.get("entry_price", 0.0),
        "stop_loss": payload.get("stop_loss", 0.0),
        "take_profit": payload.get("take_profit", 0.0),
        "risk_per_trade_pct": payload.get("risk_per_trade_pct", 0.0025),
        "risk_amount": payload.get("risk_amount", 0.0) if would_create else 0.0,
        "position_size": payload.get("position_size", 0.0) if would_create else 0.0,
        "quantity": payload.get("quantity", 0.0) if would_create else 0.0,
        "notional": payload.get("notional", 0.0) if would_create else 0.0,
        "max_positions": payload.get("max_positions", 1),
        "paper_broker_adapter": settings.paper_broker_adapter,
        "third_trade_order_intent_ready": True,
        "third_trade_route_preflight_ready": True,
        "would_create_paper_order": bool(would_create),
        "would_create_order": bool(would_create),
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "broker_close_called": False,
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_third_trade_handoff": 0,
        "positions_opened_by_third_trade_handoff": 0,
        "positions_closed_by_third_trade_handoff": 0,
        "paper_state_modified_by_third_trade_handoff": False,
        "paper_status_modified_by_third_trade_handoff": False,
        "blocked_reason": "third_trade_submit_still_disabled" if payload_ok else "payload_invalid",
        "blocked_reasons": ["third_trade_submit_still_disabled"] + [f"payload_{r}" for r in invalid_reasons],
        "audit_only": True,
    }


def build_lsr_v2_third_trade_handoff_dry_run_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2ThirdTradeHandoffDryRunSettings | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or LSRV2ThirdTradeHandoffDryRunSettings(data_dir=str(base))
    route_report = _read_json(base / settings.route_report_name)
    route_rows = _iter_jsonl_tail(base / settings.route_jsonl_name, max_lines=settings.max_event_lines)
    selected_cycle_id = str(cycle_id or route_report.get("cycle_id") or "")
    route_events = [dict(row) for row in route_rows if row.get("event_type") == THIRD_TRADE_ROUTE_EVENT_TYPE and (not selected_cycle_id or _event_cycle(row) == selected_cycle_id)]
    intent_events = _dedupe_intents([row for row in route_rows if not selected_cycle_id or _event_cycle(row) == selected_cycle_id])
    creatable_intents = [row for row in intent_events if _safe_bool(row.get("would_create_order"), False)]
    unsafe_blockers = _unsafe_route_flags(route_report, route_events + intent_events)

    route_ready = _route_report_ready(route_report)
    if not route_ready:
        route_missing = True
    else:
        route_missing = False

    blockers: list[str] = []
    if route_missing:
        blockers.append("third_trade_route_preflight_not_ready")
    if not intent_events:
        blockers.append("third_trade_order_intent_missing")
    if intent_events and not creatable_intents:
        blockers.append("third_trade_no_creatable_order_intent")
    blockers.extend(unsafe_blockers)
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    handoff_events: list[dict[str, Any]] = []
    if route_ready and creatable_intents and not unsafe_blockers and settings.fail_closed:
        handoff_events = [build_third_trade_handoff_dry_run_event(intent=creatable_intents[-1], settings=settings)]

    payload_valid_count = sum(1 for row in handoff_events if _safe_bool(row.get("payload_valid"), False))
    payload_invalid_count = sum(1 for row in handoff_events if not _safe_bool(row.get("payload_valid"), False))
    would_create_paper_order_count = sum(1 for row in handoff_events if _safe_bool(row.get("would_create_paper_order"), False))
    broker_submit_called = any(_safe_bool(row.get("broker_submit_called"), False) for row in handoff_events)

    if unsafe_blockers or not settings.fail_closed or broker_submit_called:
        decision = REJECT_DECISION
        status = "FAIL"
    elif route_missing:
        decision = ROUTE_MISSING_DECISION
        status = "WARN"
    elif not intent_events or (intent_events and not creatable_intents):
        decision = NO_CREATABLE_INTENT_DECISION
        status = "WARN"
    elif payload_invalid_count > 0 or payload_valid_count == 0:
        decision = PAYLOAD_INVALID_DECISION
        status = "WARN"
    else:
        decision = READY_DECISION
        status = "PASS"

    classification_labels: list[str] = ["THIRD_TRADE_HANDOFF_DRY_RUN", "SUBMIT_STILL_DISABLED"]
    if decision == READY_DECISION:
        classification_labels.extend(["THIRD_TRADE_PAYLOAD_VALID", "PAPER_BROKER_HANDOFF_READY_DRY_RUN"])
    elif decision == ROUTE_MISSING_DECISION:
        classification_labels.append("THIRD_TRADE_ROUTE_PREFLIGHT_MISSING")
    elif decision == NO_CREATABLE_INTENT_DECISION:
        classification_labels.append("THIRD_TRADE_NO_CREATABLE_INTENT")
    elif decision == PAYLOAD_INVALID_DECISION:
        classification_labels.append("THIRD_TRADE_PAYLOAD_INVALID")
    else:
        classification_labels.append("THIRD_TRADE_HANDOFF_REJECTED")

    total_risk_amount = round(sum(_safe_float(row.get("risk_amount"), 0.0) for row in handoff_events), 10)
    total_notional = round(sum(_safe_float(row.get("notional"), 0.0) for row in handoff_events), 10)
    report = {
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": sorted(set(blockers)),
        "cycle_id": selected_cycle_id,
        "event_source": "third_trade_route_preflight_jsonl",
        "strict_cycle_scope": True,
        "route_preflight_decision": route_report.get("decision"),
        "route_preflight_status": route_report.get("status"),
        "third_trade_route_preflight_ready": bool(route_ready),
        "third_trade_order_intent_ready": bool(_safe_bool(route_report.get("third_trade_order_intent_ready"), False) and bool(intent_events)),
        "third_trade_rearm_ready": bool(_safe_bool(route_report.get("third_trade_rearm_ready"), False)),
        "third_trade_eligible": bool(_safe_bool(route_report.get("third_trade_eligible"), False)),
        "route_events": len(route_events),
        "third_trade_order_intent_events": len(intent_events),
        "creatable_order_intents": len(creatable_intents),
        "handoff_dry_run_events": len(handoff_events),
        "payload_valid_count": payload_valid_count,
        "payload_invalid_count": payload_invalid_count,
        "would_create_paper_order_count": would_create_paper_order_count,
        "would_create_order_count": would_create_paper_order_count,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_third_trade_handoff": False,
        "broker_close_called_by_third_trade_handoff": False,
        "paper_broker_adapter": settings.paper_broker_adapter,
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "orders_submitted_by_third_trade_handoff": 0,
        "positions_opened_by_third_trade_handoff": 0,
        "positions_closed_by_third_trade_handoff": 0,
        "paper_state_modified_by_third_trade_handoff": False,
        "paper_status_modified_by_third_trade_handoff": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "symbols": sorted({str(row.get("symbol") or "") for row in handoff_events if row.get("symbol")}),
        "sides": sorted({str(row.get("side") or "") for row in handoff_events if row.get("side")}),
        "total_risk_amount": total_risk_amount,
        "total_notional": total_notional,
        "settings": settings.to_dict(),
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    if write_outputs:
        _write_json(base / settings.report_name, report)
        _write_jsonl_replace(base / settings.jsonl_name, handoff_events)
    return report
