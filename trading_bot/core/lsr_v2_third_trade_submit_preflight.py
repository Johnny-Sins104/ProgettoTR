"""Prompt 29.4.4s-10am — LSR-v2 third paper-trade submit preflight.

Consumes the third-trade handoff dry-run from 29.4.4s-10al and prepares a
submit preflight record for a future supervised paper-only submit boundary.
This module is intentionally non-operational: it never submits an order, never
calls a broker, never opens/closes a position, and never mutates paper
state/status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

try:  # package import in the full project
    from .lsr_v2_third_trade_handoff_dry_run import (  # type: ignore
        EVENT_TYPE as HANDOFF_EVENT_TYPE,
        JSONL_NAME as HANDOFF_JSONL_NAME,
        READY_DECISION as HANDOFF_READY_DECISION,
        REPORT_NAME as HANDOFF_REPORT_NAME,
        PAPER_BROKER_ADAPTER_NAME,
        PROFILE_NAME,
        SELECTED_OVERLAY_ID,
        _iter_jsonl_tail,
        _payload_valid,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_third_trade_handoff_dry_run import (  # type: ignore
        EVENT_TYPE as HANDOFF_EVENT_TYPE,
        JSONL_NAME as HANDOFF_JSONL_NAME,
        READY_DECISION as HANDOFF_READY_DECISION,
        REPORT_NAME as HANDOFF_REPORT_NAME,
        PAPER_BROKER_ADAPTER_NAME,
        PROFILE_NAME,
        SELECTED_OVERLAY_ID,
        _iter_jsonl_tail,
        _payload_valid,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
    )

PROMPT_ID = "29.4.4s-10am"
EVENT_TYPE = "LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT"
REPORT_NAME = "lsr_v2_third_trade_submit_preflight_report.json"
JSONL_NAME = "lsr_v2_third_trade_submit_preflight.jsonl"

READY_DECISION = "LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT_READY"
HANDOFF_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_HANDOFF_MISSING"
PAYLOAD_INVALID_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT_PAYLOAD_INVALID"
NO_CREATABLE_ORDER_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT_NO_CREATABLE_ORDER"
REJECT_DECISION = "REJECT_LSR_V2_THIRD_TRADE_SUBMIT_PREFLIGHT_SAFETY_FAILED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LSRV2ThirdTradeSubmitPreflightSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    handoff_report_name: str = HANDOFF_REPORT_NAME
    handoff_jsonl_name: str = HANDOFF_JSONL_NAME
    max_event_lines: int = 50000
    paper_broker_adapter: str = PAPER_BROKER_ADAPTER_NAME
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _event_cycle(row: Mapping[str, Any]) -> str:
    return str(row.get("cycle_id") or row.get("lsr_v2_runtime_cycle_id") or "")


def _payload_from_handoff(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    if isinstance(payload, Mapping):
        out = dict(payload)
    else:
        qty = _safe_float(row.get("quantity"), 0.0)
        if qty <= 0.0:
            qty = _safe_float(row.get("position_size"), 0.0)
        out = {
            "cycle_id": _event_cycle(row),
            "symbol": str(row.get("symbol") or ""),
            "timeframe": str(row.get("timeframe") or ""),
            "candidate_id": str(row.get("candidate_id") or ""),
            "profile_name": str(row.get("profile_name") or PROFILE_NAME),
            "selected_overlay_id": str(row.get("selected_overlay_id") or SELECTED_OVERLAY_ID),
            "side": str(row.get("side") or "").upper(),
            "order_type": str(row.get("order_type") or "LIMIT"),
            "entry_price": _safe_float(row.get("entry_price"), 0.0),
            "stop_loss": _safe_float(row.get("stop_loss"), 0.0),
            "take_profit": _safe_float(row.get("take_profit"), 0.0),
            "risk_per_trade_pct": _safe_float(row.get("risk_per_trade_pct"), 0.0025),
            "risk_amount": _safe_float(row.get("risk_amount"), 0.0),
            "position_size": _safe_float(row.get("position_size"), 0.0),
            "quantity": qty,
            "notional": _safe_float(row.get("notional"), 0.0),
            "max_positions": _safe_int(row.get("max_positions"), 1),
        }
    # Normalise numeric fields when payload comes from JSON.
    out["side"] = str(out.get("side") or "").upper()
    out["entry_price"] = _safe_float(out.get("entry_price"), 0.0)
    out["stop_loss"] = _safe_float(out.get("stop_loss"), 0.0)
    out["take_profit"] = _safe_float(out.get("take_profit"), 0.0)
    out["risk_amount"] = _safe_float(out.get("risk_amount"), 0.0)
    out["position_size"] = _safe_float(out.get("position_size"), 0.0)
    out["quantity"] = _safe_float(out.get("quantity"), out.get("position_size") or 0.0)
    out["notional"] = _safe_float(out.get("notional"), 0.0)
    out["max_positions"] = _safe_int(out.get("max_positions"), 1)
    out.setdefault("profile_name", PROFILE_NAME)
    out.setdefault("selected_overlay_id", SELECTED_OVERLAY_ID)
    out.setdefault("order_type", "LIMIT")
    return out


def _dedupe_handoff_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if row.get("event_type") != HANDOFF_EVENT_TYPE:
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


def _handoff_report_ready(report: Mapping[str, Any]) -> bool:
    return (
        report.get("status") == "PASS"
        and report.get("decision") == HANDOFF_READY_DECISION
        and _safe_bool(report.get("third_trade_route_preflight_ready"), False)
        and _safe_bool(report.get("third_trade_order_intent_ready"), False)
        and _safe_int(report.get("payload_valid_count"), 0) > 0
        and _safe_int(report.get("would_create_paper_order_count"), 0) > 0
    )


def _unsafe_handoff_flags(report: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> list[str]:
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
        "broker_submit_called_by_third_trade_handoff",
        "broker_close_called_by_third_trade_handoff",
        "paper_state_modified_by_third_trade_handoff",
        "paper_status_modified_by_third_trade_handoff",
    ]
    unsafe_count_keys = [
        "orders_submitted_by_third_trade_handoff",
        "positions_opened_by_third_trade_handoff",
        "positions_closed_by_third_trade_handoff",
        "would_submit_count",
        "would_submit_to_paper_broker_count",
    ]
    for key in unsafe_bool_keys:
        if _safe_bool(report.get(key), False):
            blockers.append(f"handoff_report_{key}")
    for key in unsafe_count_keys:
        if _safe_int(report.get(key), 0) > 0:
            blockers.append(f"handoff_report_{key}")
    for row in rows:
        for key in unsafe_bool_keys:
            if _safe_bool(row.get(key), False):
                blockers.append(f"handoff_event_{key}")
        for key in unsafe_count_keys:
            if _safe_int(row.get(key), 0) > 0:
                blockers.append(f"handoff_event_{key}")
        if _safe_bool(row.get("would_submit"), False):
            blockers.append("handoff_event_would_submit")
        if _safe_bool(row.get("would_submit_to_paper_broker"), False):
            blockers.append("handoff_event_would_submit_to_paper_broker")
    return sorted(set(blockers))


def build_third_trade_submit_preflight_event(*, handoff_event: Mapping[str, Any], settings: LSRV2ThirdTradeSubmitPreflightSettings) -> dict[str, Any]:
    payload = _payload_from_handoff(handoff_event)
    payload_ok, invalid_reasons = _payload_valid(payload)
    handoff_ready = bool(_safe_bool(handoff_event.get("would_create_paper_order"), False) and _safe_bool(handoff_event.get("payload_valid"), False))
    would_prepare = bool(payload_ok and handoff_ready and settings.fail_closed)
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
        "source": "lsr_v2_third_trade_handoff_dry_run",
        "source_event_type": str(handoff_event.get("event_type") or HANDOFF_EVENT_TYPE),
        "payload": payload,
        "payload_valid": bool(payload_ok),
        "payload_invalid_reasons": invalid_reasons,
        "handoff_pass": bool(handoff_ready),
        "handoff_dry_run_ready": bool(handoff_ready),
        "side": payload.get("side", ""),
        "order_type": payload.get("order_type", "LIMIT"),
        "entry_price": payload.get("entry_price", 0.0),
        "stop_loss": payload.get("stop_loss", 0.0),
        "take_profit": payload.get("take_profit", 0.0),
        "risk_per_trade_pct": payload.get("risk_per_trade_pct", 0.0025),
        "risk_amount": payload.get("risk_amount", 0.0) if would_prepare else 0.0,
        "position_size": payload.get("position_size", 0.0) if would_prepare else 0.0,
        "quantity": payload.get("quantity", 0.0) if would_prepare else 0.0,
        "notional": payload.get("notional", 0.0) if would_prepare else 0.0,
        "max_positions": payload.get("max_positions", 1),
        "paper_broker_adapter": settings.paper_broker_adapter,
        "third_trade_order_intent_ready": True,
        "third_trade_route_preflight_ready": True,
        "third_trade_handoff_ready": bool(handoff_ready),
        "would_create_paper_order": bool(would_prepare),
        "would_create_order": bool(would_prepare),
        "would_prepare_submit": bool(would_prepare),
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
        "orders_submitted_by_third_trade_submit_preflight": 0,
        "positions_opened_by_third_trade_submit_preflight": 0,
        "positions_closed_by_third_trade_submit_preflight": 0,
        "paper_state_modified_by_third_trade_submit_preflight": False,
        "paper_status_modified_by_third_trade_submit_preflight": False,
        "blocked_reason": "third_trade_submit_still_disabled" if payload_ok else "payload_invalid",
        "blocked_reasons": ["third_trade_submit_still_disabled"] + [f"payload_{r}" for r in invalid_reasons],
        "audit_only": True,
    }


def build_lsr_v2_third_trade_submit_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2ThirdTradeSubmitPreflightSettings | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or LSRV2ThirdTradeSubmitPreflightSettings(data_dir=str(base))
    handoff_report = _read_json(base / settings.handoff_report_name)
    handoff_rows = _iter_jsonl_tail(base / settings.handoff_jsonl_name, max_lines=settings.max_event_lines)
    selected_cycle_id = str(cycle_id or handoff_report.get("cycle_id") or "")
    handoff_events_all = _dedupe_handoff_rows([row for row in handoff_rows if not selected_cycle_id or _event_cycle(row) == selected_cycle_id])
    creatable_handoffs = [row for row in handoff_events_all if _safe_bool(row.get("would_create_paper_order"), False)]
    unsafe_blockers = _unsafe_handoff_flags(handoff_report, handoff_events_all)
    handoff_ready = _handoff_report_ready(handoff_report)

    blockers: list[str] = []
    if not handoff_ready:
        blockers.append("third_trade_handoff_not_ready")
    if not handoff_events_all:
        blockers.append("third_trade_handoff_event_missing")
    if handoff_events_all and not creatable_handoffs:
        blockers.append("third_trade_no_creatable_handoff_order")
    blockers.extend(unsafe_blockers)
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    preflight_events: list[dict[str, Any]] = []
    if handoff_ready and creatable_handoffs and not unsafe_blockers and settings.fail_closed:
        preflight_events = [build_third_trade_submit_preflight_event(handoff_event=creatable_handoffs[-1], settings=settings)]

    payload_valid_count = sum(1 for row in preflight_events if _safe_bool(row.get("payload_valid"), False))
    payload_invalid_count = sum(1 for row in preflight_events if not _safe_bool(row.get("payload_valid"), False))
    would_create_count = sum(1 for row in preflight_events if _safe_bool(row.get("would_create_paper_order"), False))
    would_prepare_count = sum(1 for row in preflight_events if _safe_bool(row.get("would_prepare_submit"), False))
    broker_submit_called = any(_safe_bool(row.get("broker_submit_called"), False) for row in preflight_events)

    if unsafe_blockers or not settings.fail_closed or broker_submit_called:
        decision = REJECT_DECISION
        status = "FAIL"
    elif not handoff_ready:
        decision = HANDOFF_MISSING_DECISION
        status = "WARN"
    elif not handoff_events_all or (handoff_events_all and not creatable_handoffs):
        decision = NO_CREATABLE_ORDER_DECISION
        status = "WARN"
    elif payload_invalid_count > 0 or payload_valid_count == 0 or would_prepare_count == 0:
        decision = PAYLOAD_INVALID_DECISION
        status = "WARN"
    else:
        decision = READY_DECISION
        status = "PASS"

    classification_labels: list[str] = ["THIRD_TRADE_SUBMIT_PREFLIGHT", "SUBMIT_STILL_DISABLED"]
    if decision == READY_DECISION:
        classification_labels.extend(["THIRD_TRADE_SUBMIT_PREFLIGHT_READY", "PAPER_BROKER_SUBMIT_STILL_DISABLED"])
    elif decision == HANDOFF_MISSING_DECISION:
        classification_labels.append("THIRD_TRADE_HANDOFF_MISSING")
    elif decision == NO_CREATABLE_ORDER_DECISION:
        classification_labels.append("THIRD_TRADE_NO_CREATABLE_ORDER")
    elif decision == PAYLOAD_INVALID_DECISION:
        classification_labels.append("THIRD_TRADE_SUBMIT_PAYLOAD_INVALID")
    else:
        classification_labels.append("THIRD_TRADE_SUBMIT_PREFLIGHT_REJECTED")

    total_risk_amount = round(sum(_safe_float(row.get("risk_amount"), 0.0) for row in preflight_events), 10)
    total_notional = round(sum(_safe_float(row.get("notional"), 0.0) for row in preflight_events), 10)
    report = {
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": sorted(set(blockers)),
        "cycle_id": selected_cycle_id,
        "event_source": "third_trade_handoff_dry_run_jsonl",
        "strict_cycle_scope": True,
        "handoff_decision": handoff_report.get("decision"),
        "handoff_status": handoff_report.get("status"),
        "handoff_pass": bool(handoff_ready),
        "third_trade_handoff_ready": bool(handoff_ready),
        "third_trade_route_preflight_ready": bool(_safe_bool(handoff_report.get("third_trade_route_preflight_ready"), False)),
        "third_trade_order_intent_ready": bool(_safe_bool(handoff_report.get("third_trade_order_intent_ready"), False)),
        "third_trade_rearm_ready": bool(_safe_bool(handoff_report.get("third_trade_rearm_ready"), False)),
        "third_trade_eligible": bool(_safe_bool(handoff_report.get("third_trade_eligible"), False)),
        "handoff_dry_run_events": len(handoff_events_all),
        "creatable_handoff_events": len(creatable_handoffs),
        "submit_preflight_events": len(preflight_events),
        "payload_valid_count": payload_valid_count,
        "payload_invalid_count": payload_invalid_count,
        "would_create_paper_order_count": would_create_count,
        "would_create_order_count": would_create_count,
        "would_prepare_submit_count": would_prepare_count,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_third_trade_submit_preflight": False,
        "broker_close_called_by_third_trade_submit_preflight": False,
        "paper_broker_adapter": settings.paper_broker_adapter,
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "orders_submitted_by_third_trade_submit_preflight": 0,
        "positions_opened_by_third_trade_submit_preflight": 0,
        "positions_closed_by_third_trade_submit_preflight": 0,
        "paper_state_modified_by_third_trade_submit_preflight": False,
        "paper_status_modified_by_third_trade_submit_preflight": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "symbols": sorted({str(row.get("symbol") or "") for row in preflight_events if row.get("symbol")}),
        "sides": sorted({str(row.get("side") or "") for row in preflight_events if row.get("side")}),
        "total_risk_amount": total_risk_amount,
        "total_notional": total_notional,
        "settings": settings.to_dict(),
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    if write_outputs:
        _write_json(base / settings.report_name, report)
        _write_jsonl_replace(base / settings.jsonl_name, preflight_events)
    return report
