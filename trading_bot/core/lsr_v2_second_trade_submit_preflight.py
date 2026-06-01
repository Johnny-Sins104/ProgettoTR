"""Prompt 29.4.4s-10w — LSR-v2 second trade supervised submit preflight.

Builds the disabled-by-default submit preflight boundary for the second
supervised LSR-v2 paper trade.  It consumes the second-trade handoff dry-run
payloads and verifies the eligibility/re-arm/route/handoff chain, then emits a
strict cycle-scoped diagnostic submit-preflight event.

This module is deliberately non-operative: it never calls PaperBrokerAdapter,
never submits an order, never opens a position, never closes a position, and
never mutates paper state/status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # package import in the full project
    from .lsr_v2_second_trade_handoff_dry_run import (  # type: ignore
        HANDOFF_EVENT_TYPE,
        JSONL_NAME as HANDOFF_JSONL_NAME,
        REPORT_NAME as HANDOFF_REPORT_NAME,
        READY_DECISION as HANDOFF_READY_DECISION,
        _event_cycle,
        _iter_jsonl_tail,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
        utc_now_iso,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_second_trade_handoff_dry_run import (  # type: ignore
        HANDOFF_EVENT_TYPE,
        JSONL_NAME as HANDOFF_JSONL_NAME,
        REPORT_NAME as HANDOFF_REPORT_NAME,
        READY_DECISION as HANDOFF_READY_DECISION,
        _event_cycle,
        _iter_jsonl_tail,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
        utc_now_iso,
    )

PROMPT_ID = "29.4.4s-10w"
EVENT_TYPE = "LSR_V2_SECOND_TRADE_SUBMIT_PREFLIGHT"
REPORT_NAME = "lsr_v2_second_trade_submit_preflight_report.json"
JSONL_NAME = "lsr_v2_second_trade_submit_preflight.jsonl"

ELIGIBILITY_REPORT_NAME = "lsr_v2_second_trade_eligibility_gate_report.json"
REARM_REPORT_NAME = "lsr_v2_second_trade_rearm_gate_report.json"
ROUTE_REPORT_NAME = "lsr_v2_second_trade_route_preflight_report.json"

ELIGIBILITY_READY_DECISION = "LSR_V2_SECOND_PAPER_TRADE_ELIGIBILITY_PASS"
REARM_READY_DECISION = "LSR_V2_SECOND_TRADE_REARM_READY_DIAGNOSTIC"
ROUTE_READY_DECISION = "LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_READY"

READY_DECISION = "LSR_V2_SECOND_TRADE_SUBMIT_PREFLIGHT_READY"
HANDOFF_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_HANDOFF_MISSING"
REARM_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_MISSING"
ROUTE_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_ROUTE_MISSING"
REPORTS_INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_SUBMIT_PREFLIGHT_REPORTS_INCOMPLETE"
SUBMIT_DISABLED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_SUBMIT_DISABLED"
SAFETY_REJECT_DECISION = "REJECT_LSR_V2_SECOND_TRADE_SUBMIT_PREFLIGHT_FAILED"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


@dataclass(frozen=True)
class LSRV2SecondTradeSubmitPreflightSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    handoff_report_name: str = HANDOFF_REPORT_NAME
    handoff_jsonl_name: str = HANDOFF_JSONL_NAME
    eligibility_report_name: str = ELIGIBILITY_REPORT_NAME
    rearm_report_name: str = REARM_REPORT_NAME
    route_report_name: str = ROUTE_REPORT_NAME
    max_event_lines: int = 50000
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    submit_enabled: bool = False
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _event_key(event: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(event.get("event_type") or ""),
        _event_cycle(event),
        str(event.get("symbol") or ""),
        str(event.get("candidate_id") or ""),
        str(event.get("timeframe") or ""),
    )


def _dedupe_handoff_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in events:
        row = dict(raw)
        if row.get("event_type") != HANDOFF_EVENT_TYPE:
            continue
        key = _event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _report_prerequisites(
    *,
    data_dir: str | Path,
    settings: LSRV2SecondTradeSubmitPreflightSettings,
) -> dict[str, Any]:
    base = Path(data_dir)
    eligibility = _read_json(base / settings.eligibility_report_name)
    rearm = _read_json(base / settings.rearm_report_name)
    route = _read_json(base / settings.route_report_name)
    handoff = _read_json(base / settings.handoff_report_name)

    return {
        "eligibility_report_present": bool(eligibility),
        "rearm_report_present": bool(rearm),
        "route_report_present": bool(route),
        "handoff_report_present": bool(handoff),
        "eligibility_pass": str(eligibility.get("decision") or "") == ELIGIBILITY_READY_DECISION and _safe_bool(eligibility.get("second_trade_eligible"), False),
        "second_trade_eligible": _safe_bool(eligibility.get("second_trade_eligible"), False),
        "observation_pass": _safe_bool(eligibility.get("observation_pass"), False),
        "second_trade_locked": _safe_bool(eligibility.get("second_trade_locked"), False),
        "rearm_pass": str(rearm.get("decision") or "") == REARM_READY_DECISION and _safe_bool(rearm.get("second_trade_rearm_ready"), False),
        "second_trade_rearm_ready": _safe_bool(rearm.get("second_trade_rearm_ready"), False),
        "route_pass": str(route.get("decision") or "") == ROUTE_READY_DECISION and _safe_bool(route.get("second_trade_route_preflight_ready"), False),
        "second_trade_route_preflight_ready": _safe_bool(route.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(route.get("second_trade_order_intent_ready"), False),
        "second_trade_would_route_count": _safe_int(route.get("second_trade_would_route_count"), 0),
        "second_trade_order_intent_events": _safe_int(route.get("second_trade_order_intent_events"), 0),
        "route_would_submit_count": _safe_int(route.get("would_submit_count"), 0) + _safe_int(route.get("would_submit_to_paper_broker_count"), 0),
        "route_orders_submitted": _safe_int(route.get("orders_submitted_by_second_trade_route_preflight"), 0),
        "route_positions_opened": _safe_int(route.get("positions_opened_by_second_trade_route_preflight"), 0),
        "route_broker_submit_called": _safe_bool(route.get("broker_submit_called_by_second_trade_route_preflight"), False),
        "handoff_pass": str(handoff.get("decision") or "") == HANDOFF_READY_DECISION,
        "payload_valid_count": _safe_int(handoff.get("payload_valid_count"), 0),
        "would_create_paper_order_count": _safe_int(handoff.get("would_create_paper_order_count"), 0),
        "handoff_would_submit_count": _safe_int(handoff.get("would_submit_count"), 0) + _safe_int(handoff.get("would_submit_to_paper_broker_count"), 0),
        "handoff_broker_submit_called": _safe_bool(handoff.get("broker_submit_called"), False) or _safe_bool(handoff.get("broker_submit_called_by_second_trade_handoff"), False),
        "handoff_orders_submitted": _safe_int(handoff.get("orders_submitted_by_second_trade_handoff"), 0),
        "handoff_positions_opened": _safe_int(handoff.get("positions_opened_by_second_trade_handoff"), 0),
        "paper_status_open_positions": _safe_int(handoff.get("paper_status_open_positions"), 0),
        "paper_status_pending_orders": _safe_int(handoff.get("paper_status_pending_orders"), 0),
        "state_open_lsr_v2_positions": _safe_int(handoff.get("state_open_lsr_v2_positions"), 0),
    }


def select_second_trade_handoff_events(
    *,
    data_dir: str | Path,
    settings: LSRV2SecondTradeSubmitPreflightSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Select strict cycle-scoped second-trade handoff dry-run rows."""
    settings = settings or LSRV2SecondTradeSubmitPreflightSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_handoff_events(_iter_jsonl_tail(base / settings.handoff_jsonl_name, max_lines=settings.max_event_lines))
    handoff_report = _read_json(base / settings.handoff_report_name)
    route_report = _read_json(base / settings.route_report_name)
    rearm_report = _read_json(base / settings.rearm_report_name)
    eligibility_report = _read_json(base / settings.eligibility_report_name)

    cycle_id = str(requested_cycle_id or handoff_report.get("cycle_id") or route_report.get("cycle_id") or rearm_report.get("cycle_id") or eligibility_report.get("cycle_id") or "")
    if not cycle_id:
        for row in reversed(rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break

    selected = [row for row in rows if not cycle_id or _event_cycle(row) == cycle_id]
    historical = [row for row in rows if _event_cycle(row) and _event_cycle(row) != cycle_id]
    metadata = {
        "prompt_id": PROMPT_ID,
        "event_source": "second_trade_handoff_dry_run_jsonl",
        "strict_cycle_scope": True,
        "handoff_report_decision": handoff_report.get("decision"),
        "handoff_report_status": handoff_report.get("status"),
        "handoff_report_cycle_id": handoff_report.get("cycle_id"),
        "route_report_cycle_id": route_report.get("cycle_id"),
        "rearm_report_cycle_id": rearm_report.get("cycle_id"),
        "eligibility_report_cycle_id": eligibility_report.get("cycle_id"),
        "historical_second_trade_handoff_events": len(historical),
    }
    return cycle_id, selected, metadata


def build_lsr_v2_second_trade_submit_preflight_event(
    *,
    handoff_event: Mapping[str, Any],
    settings: LSRV2SecondTradeSubmitPreflightSettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitPreflightSettings()
    prereq = dict(prerequisites or {})
    h = dict(handoff_event or {})
    payload = h.get("payload") if isinstance(h.get("payload"), Mapping) else {}

    payload_valid = _safe_bool(h.get("payload_valid"), False)
    would_create_paper_order = _safe_bool(h.get("would_create_paper_order"), False)
    handoff_would_submit = _safe_bool(h.get("would_submit"), False) or _safe_bool(h.get("would_submit_to_paper_broker"), False)
    broker_submit_called = _safe_bool(h.get("broker_submit_called"), False)

    blockers: list[str] = []
    if not _safe_bool(prereq.get("eligibility_pass"), False):
        blockers.append("second_trade_eligibility_not_passed")
    if not _safe_bool(prereq.get("rearm_pass"), False) or not _safe_bool(prereq.get("second_trade_rearm_ready"), False):
        blockers.append("second_trade_rearm_not_ready")
    if not _safe_bool(prereq.get("route_pass"), False) or not _safe_bool(prereq.get("second_trade_route_preflight_ready"), False):
        blockers.append("second_trade_route_not_ready")
    if not _safe_bool(prereq.get("second_trade_order_intent_ready"), False):
        blockers.append("second_trade_order_intent_not_ready")
    if _safe_int(prereq.get("second_trade_would_route_count"), 0) <= 0:
        blockers.append("second_trade_would_route_missing")
    if not _safe_bool(prereq.get("handoff_pass"), False):
        blockers.append("second_trade_handoff_not_passed")
    if not payload_valid:
        blockers.append("second_trade_handoff_payload_invalid")
    if not would_create_paper_order:
        blockers.append("second_trade_handoff_would_create_false")
    if handoff_would_submit or broker_submit_called:
        blockers.append("second_trade_handoff_submit_attempt_detected")
    if _safe_int(prereq.get("handoff_orders_submitted"), 0) != 0 or _safe_int(prereq.get("handoff_positions_opened"), 0) != 0:
        blockers.append("second_trade_handoff_order_or_position_detected")
    if _safe_int(prereq.get("paper_status_open_positions"), 0) != 0 or _safe_int(prereq.get("paper_status_pending_orders"), 0) != 0 or _safe_int(prereq.get("state_open_lsr_v2_positions"), 0) != 0:
        blockers.append("paper_state_not_clean")
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    would_prepare_submit = bool(not blockers and would_create_paper_order and payload_valid and settings.fail_closed)
    blocked_reason = "second_trade_paper_submit_disabled_by_default" if would_prepare_submit else (blockers[0] if blockers else "second_trade_paper_submit_disabled_by_default")

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": str(h.get("cycle_id") or payload.get("cycle_id") or ""),
        "symbol": str(h.get("symbol") or payload.get("symbol") or ""),
        "timeframe": str(h.get("timeframe") or payload.get("timeframe") or ""),
        "side": str(h.get("side") or payload.get("side") or ""),
        "order_type": str(h.get("order_type") or payload.get("order_type") or ""),
        "profile_name": str(h.get("profile_name") or payload.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(h.get("selected_overlay_id") or payload.get("selected_overlay_id") or settings.selected_overlay_id),
        "source": "lsr_v2_second_trade_handoff_dry_run",
        "source_event_type": str(h.get("event_type") or HANDOFF_EVENT_TYPE),
        "candidate_id": str(h.get("candidate_id") or payload.get("candidate_id") or ""),
        "entry_price": _safe_float(h.get("entry_price", payload.get("entry_price")), 0.0),
        "stop_loss": _safe_float(h.get("stop_loss", payload.get("stop_loss")), 0.0),
        "take_profit": _safe_float(h.get("take_profit", payload.get("take_profit")), 0.0),
        "risk_per_trade_pct": _safe_float(h.get("risk_per_trade_pct", payload.get("risk_per_trade_pct")), 0.0025),
        "risk_amount": _safe_float(h.get("risk_amount", payload.get("risk_amount")), 0.0),
        "position_size": _safe_float(h.get("position_size", payload.get("position_size")), 0.0),
        "quantity": _safe_float(h.get("quantity", payload.get("quantity")), 0.0),
        "notional": _safe_float(h.get("notional", payload.get("notional")), 0.0),
        "max_positions": _safe_int(h.get("max_positions", payload.get("max_positions")), 1),
        "payload_valid": bool(payload_valid),
        "would_create_paper_order": bool(would_create_paper_order),
        "would_prepare_submit": bool(would_prepare_submit),
        "second_trade_submit_enabled": False,
        "submit_enabled": False,
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "blocked_reason": blocked_reason,
        "blocked_reasons": blockers + (["second_trade_paper_submit_disabled_by_default"] if would_prepare_submit else []),
        "second_trade_eligible": _safe_bool(prereq.get("second_trade_eligible"), False),
        "second_trade_rearm_ready": _safe_bool(prereq.get("second_trade_rearm_ready"), False),
        "second_trade_route_preflight_ready": _safe_bool(prereq.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(prereq.get("second_trade_order_intent_ready"), False),
        "handoff_pass": _safe_bool(prereq.get("handoff_pass"), False),
        "second_trade_execute_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_submit_preflight": 0,
        "positions_opened_by_second_trade_submit_preflight": 0,
        "promotion_ready": False,
        "dry_run_only": True,
        "audit_only": True,
        "submit_preflight_only": True,
    }


def build_lsr_v2_second_trade_submit_preflight_events(
    handoff_events: Iterable[Mapping[str, Any]],
    *,
    settings: LSRV2SecondTradeSubmitPreflightSettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = settings or LSRV2SecondTradeSubmitPreflightSettings()
    events: list[dict[str, Any]] = []
    for handoff in _dedupe_handoff_events(handoff_events):
        if not _safe_bool(handoff.get("would_create_paper_order"), False):
            continue
        events.append(build_lsr_v2_second_trade_submit_preflight_event(
            handoff_event=handoff,
            settings=settings,
            prerequisites=prerequisites,
        ))
    return events


def summarize_lsr_v2_second_trade_submit_preflight(
    *,
    cycle_id: str,
    handoff_events: Iterable[Mapping[str, Any]],
    preflight_events: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2SecondTradeSubmitPreflightSettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitPreflightSettings(data_dir=str(data_dir))
    prereq = dict(prerequisites or {})
    metadata = dict(metadata or {})
    handoff_rows = _dedupe_handoff_events(handoff_events)
    rows = [dict(e) for e in preflight_events]
    prepare_rows = [e for e in rows if _safe_bool(e.get("would_prepare_submit"), False)]

    blockers: list[str] = []
    if not handoff_rows:
        blockers.append("second_trade_handoff_missing")
    missing_reports = [
        key for key in ("eligibility_report_present", "rearm_report_present", "route_report_present", "handoff_report_present")
        if not _safe_bool(prereq.get(key), False)
    ]
    if missing_reports:
        blockers.append("upstream_reports_incomplete")
    if not _safe_bool(prereq.get("eligibility_pass"), False):
        blockers.append("second_trade_eligibility_not_passed")
    if not _safe_bool(prereq.get("rearm_pass"), False) or not _safe_bool(prereq.get("second_trade_rearm_ready"), False):
        blockers.append("second_trade_rearm_not_ready")
    if not _safe_bool(prereq.get("route_pass"), False) or not _safe_bool(prereq.get("second_trade_route_preflight_ready"), False):
        blockers.append("second_trade_route_not_ready")
    if not _safe_bool(prereq.get("second_trade_order_intent_ready"), False) or _safe_int(prereq.get("second_trade_would_route_count"), 0) <= 0:
        blockers.append("second_trade_order_intent_not_ready")
    if not _safe_bool(prereq.get("handoff_pass"), False) or _safe_int(prereq.get("would_create_paper_order_count"), 0) <= 0:
        blockers.append("second_trade_handoff_not_ready")

    safety_violation = any([
        _safe_bool(prereq.get("handoff_broker_submit_called"), False),
        _safe_int(prereq.get("handoff_would_submit_count"), 0) != 0,
        _safe_int(prereq.get("handoff_orders_submitted"), 0) != 0,
        _safe_int(prereq.get("handoff_positions_opened"), 0) != 0,
        _safe_int(prereq.get("route_would_submit_count"), 0) != 0,
        _safe_int(prereq.get("route_orders_submitted"), 0) != 0,
        _safe_int(prereq.get("route_positions_opened"), 0) != 0,
        _safe_bool(prereq.get("route_broker_submit_called"), False),
        _safe_int(prereq.get("paper_status_open_positions"), 0) != 0,
        _safe_int(prereq.get("paper_status_pending_orders"), 0) != 0,
        _safe_int(prereq.get("state_open_lsr_v2_positions"), 0) != 0,
        any(
            _safe_bool(h.get("would_submit"), False)
            or _safe_bool(h.get("would_submit_to_paper_broker"), False)
            or _safe_bool(h.get("broker_submit_called"), False)
            or _safe_int(h.get("orders_submitted_by_second_trade_handoff"), 0) != 0
            or _safe_int(h.get("positions_opened_by_second_trade_handoff"), 0) != 0
            for h in handoff_rows
        ),
        any(
            _safe_bool(e.get("would_submit"), False)
            or _safe_bool(e.get("would_submit_to_paper_broker"), False)
            or _safe_bool(e.get("broker_submit_called"), False)
            for e in rows
        ),
    ])
    if safety_violation:
        blockers.append("safety_violation_detected")

    if not handoff_rows:
        decision = HANDOFF_MISSING_DECISION
        status = "WARN"
    elif missing_reports:
        decision = REPORTS_INCOMPLETE_DECISION
        status = "WARN"
    elif safety_violation:
        decision = SAFETY_REJECT_DECISION
        status = "FAIL"
    elif "second_trade_rearm_not_ready" in blockers:
        decision = REARM_MISSING_DECISION
        status = "WARN"
    elif "second_trade_route_not_ready" in blockers or "second_trade_order_intent_not_ready" in blockers:
        decision = ROUTE_MISSING_DECISION
        status = "WARN"
    elif prepare_rows and not blockers:
        decision = READY_DECISION
        status = "PASS"
    elif prepare_rows:
        decision = SUBMIT_DISABLED_DECISION
        status = "PASS"
    else:
        decision = SAFETY_REJECT_DECISION
        status = "WARN"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in prepare_rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in prepare_rows), 10)
    safety_checks = {
        "second_trade_submit_enabled_false": True,
        "second_trade_execute_enabled_false": True,
        "would_submit_zero": True,
        "would_submit_to_paper_broker_zero": True,
        "broker_submit_called_false": True,
        "orders_submitted_zero": True,
        "positions_opened_zero": True,
        "routing_disabled": True,
        "execution_disabled": True,
        "paper_order_submission_disabled": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
        "paper_state_clean": _safe_int(prereq.get("paper_status_open_positions"), 0) == 0 and _safe_int(prereq.get("paper_status_pending_orders"), 0) == 0 and _safe_int(prereq.get("state_open_lsr_v2_positions"), 0) == 0,
    }
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "SECOND_TRADE_SUBMIT_PREFLIGHT",
            "SUBMIT_DISABLED_BY_DEFAULT",
            "SECOND_TRADE_BROKER_BOUNDARY_FAIL_CLOSED",
        ] + (["SECOND_TRADE_SUBMIT_PREFLIGHT_READY"] if decision == READY_DECISION else ["KEEP_DIAGNOSTIC"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "second_trade_handoff_dry_run_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_second_trade_handoff_events": _safe_int(metadata.get("historical_second_trade_handoff_events"), 0),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "second_trade_eligible": _safe_bool(prereq.get("second_trade_eligible"), False),
        "second_trade_rearm_ready": _safe_bool(prereq.get("second_trade_rearm_ready"), False),
        "second_trade_route_preflight_ready": _safe_bool(prereq.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(prereq.get("second_trade_order_intent_ready"), False),
        "handoff_pass": _safe_bool(prereq.get("handoff_pass"), False),
        "handoff_dry_run_events": len(handoff_rows),
        "submit_preflight_events": len(rows),
        "would_prepare_submit_count": len(prepare_rows),
        "payload_valid_count": sum(1 for e in rows if _safe_bool(e.get("payload_valid"), False)),
        "would_create_paper_order_count": _safe_int(prereq.get("would_create_paper_order_count"), 0),
        "second_trade_would_route_count": _safe_int(prereq.get("second_trade_would_route_count"), 0),
        "second_trade_order_intent_events": _safe_int(prereq.get("second_trade_order_intent_events"), 0),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_second_trade_submit_preflight": False,
        "second_trade_submit_enabled": False,
        "second_trade_execute_enabled": False,
        "submit_enabled": False,
        "submit_enabled_default": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "paper_status_open_positions": _safe_int(prereq.get("paper_status_open_positions"), 0),
        "paper_status_pending_orders": _safe_int(prereq.get("paper_status_pending_orders"), 0),
        "state_open_lsr_v2_positions": _safe_int(prereq.get("state_open_lsr_v2_positions"), 0),
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_submit_preflight": 0,
        "positions_opened_by_second_trade_submit_preflight": 0,
        "positions_closed_by_second_trade_submit_preflight": 0,
        "promotion_ready": False,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


def write_lsr_v2_second_trade_submit_preflight_artifacts(
    *,
    data_dir: str | Path,
    cycle_id: str,
    handoff_events: Iterable[Mapping[str, Any]],
    settings: LSRV2SecondTradeSubmitPreflightSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitPreflightSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    prereq = _report_prerequisites(data_dir=base, settings=settings)
    selected_handoffs = [dict(e) for e in handoff_events if not cycle_id or _event_cycle(e) == cycle_id]
    preflight_events = build_lsr_v2_second_trade_submit_preflight_events(selected_handoffs, settings=settings, prerequisites=prereq)
    _write_jsonl_replace(base / settings.jsonl_name, preflight_events)
    report = summarize_lsr_v2_second_trade_submit_preflight(
        cycle_id=cycle_id,
        handoff_events=selected_handoffs,
        preflight_events=preflight_events,
        data_dir=base,
        settings=settings,
        prerequisites=prereq,
        metadata=metadata,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def build_lsr_v2_second_trade_submit_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondTradeSubmitPreflightSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitPreflightSettings(data_dir=str(data_dir))
    selected_cycle_id, handoff_events, metadata = select_second_trade_handoff_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    return write_lsr_v2_second_trade_submit_preflight_artifacts(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        handoff_events=handoff_events,
        settings=settings,
        metadata=metadata,
    )
