"""Prompt 29.4.4s-10x — LSR-v2 second trade submit boundary.

This module arms the second supervised paper trade only up to a single-order
submit boundary.  It consumes the second-trade submit-preflight artifacts and
can declare READY_ARMED when explicit operator confirmation is present.

It is deliberately non-operative: it never calls PaperBrokerAdapter, never
submits an order, never opens a position, never closes a position, and never
mutates paper state/status.  A later patch must add a separate execution
boundary if the operator decides to execute the second paper-only order.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import os

try:  # package import in the full project
    from .lsr_v2_second_trade_submit_preflight import (  # type: ignore
        EVENT_TYPE as PREFLIGHT_EVENT_TYPE,
        JSONL_NAME as PREFLIGHT_JSONL_NAME,
        REPORT_NAME as PREFLIGHT_REPORT_NAME,
        READY_DECISION as PREFLIGHT_READY_DECISION,
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
    from lsr_v2_second_trade_submit_preflight import (  # type: ignore
        EVENT_TYPE as PREFLIGHT_EVENT_TYPE,
        JSONL_NAME as PREFLIGHT_JSONL_NAME,
        REPORT_NAME as PREFLIGHT_REPORT_NAME,
        READY_DECISION as PREFLIGHT_READY_DECISION,
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

PROMPT_ID = "29.4.4s-10x"
EVENT_TYPE = "LSR_V2_SECOND_TRADE_SUBMIT_BOUNDARY"
REPORT_NAME = "lsr_v2_second_trade_submit_boundary_report.json"
JSONL_NAME = "lsr_v2_second_trade_submit_boundary.jsonl"

READY_ARMED_DECISION = "LSR_V2_SECOND_SINGLE_PAPER_SUBMIT_READY_ARMED"
NOT_ARMED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_NOT_ARMED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_CONFIRMATION_MISSING"
PREFLIGHT_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_PREFLIGHT_MISSING"
STATE_NOT_CLEAN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_STATE_NOT_CLEAN"
CAP_EXCEEDED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_MAX_ORDER_CAP_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_SUBMIT_BOUNDARY_FAILED"

REQUIRED_ARM_VALUE = "1"
REQUIRED_CONFIRMATION = "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


@dataclass(frozen=True)
class LSRV2SecondTradeSubmitBoundarySettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    preflight_report_name: str = PREFLIGHT_REPORT_NAME
    preflight_jsonl_name: str = PREFLIGHT_JSONL_NAME
    max_event_lines: int = 50000
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    required_arm_value: str = REQUIRED_ARM_VALUE
    required_confirmation: str = REQUIRED_CONFIRMATION
    submit_arm: str = ""
    submit_confirmation: str = ""
    max_orders: int = 1
    mode: str = "paper"
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2SecondTradeSubmitBoundarySettings":
        max_orders = _safe_int(os.getenv("LSR_V2_SECOND_TRADE_MAX_ORDERS"), 1)
        if max_orders <= 0:
            max_orders = 1
        return cls(
            data_dir=data_dir,
            submit_arm=str(os.getenv("LSR_V2_SECOND_TRADE_SUBMIT_ARM") or ""),
            submit_confirmation=str(os.getenv("LSR_V2_SECOND_TRADE_SUBMIT_CONFIRMATION") or ""),
            max_orders=max_orders,
            mode=str(os.getenv("LSR_V2_SECOND_TRADE_SUBMIT_MODE") or "paper"),
        )

    @property
    def submit_armed(self) -> bool:
        return str(self.submit_arm).strip() == self.required_arm_value

    @property
    def submit_confirmation_ok(self) -> bool:
        return str(self.submit_confirmation).strip() == self.required_confirmation

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


def _dedupe_preflight_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in events:
        row = dict(raw)
        if row.get("event_type") != PREFLIGHT_EVENT_TYPE:
            continue
        key = _event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _payload_from_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cycle_id": str(preflight.get("cycle_id") or ""),
        "symbol": str(preflight.get("symbol") or ""),
        "timeframe": str(preflight.get("timeframe") or ""),
        "side": str(preflight.get("side") or ""),
        "order_type": str(preflight.get("order_type") or "LIMIT"),
        "profile_name": str(preflight.get("profile_name") or PROFILE_NAME),
        "selected_overlay_id": str(preflight.get("selected_overlay_id") or SELECTED_OVERLAY_ID),
        "entry_price": _safe_float(preflight.get("entry_price"), 0.0),
        "stop_loss": _safe_float(preflight.get("stop_loss"), 0.0),
        "take_profit": _safe_float(preflight.get("take_profit"), 0.0),
        "risk_per_trade_pct": _safe_float(preflight.get("risk_per_trade_pct"), 0.0025),
        "risk_amount": _safe_float(preflight.get("risk_amount"), 0.0),
        "position_size": _safe_float(preflight.get("position_size"), 0.0),
        "quantity": _safe_float(preflight.get("quantity"), _safe_float(preflight.get("position_size"), 0.0)),
        "notional": _safe_float(preflight.get("notional"), 0.0),
        "max_positions": _safe_int(preflight.get("max_positions"), 1),
        "candidate_id": str(preflight.get("candidate_id") or ""),
        "paper_broker_adapter": str(preflight.get("paper_broker_adapter") or "PaperBrokerAdapter"),
    }


def _payload_valid(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not payload.get("symbol"):
        reasons.append("symbol_missing")
    side = str(payload.get("side") or "")
    if side not in {"BUY", "SELL"}:
        reasons.append("side_invalid")
    if _safe_float(payload.get("entry_price"), 0.0) <= 0:
        reasons.append("entry_price_invalid")
    if _safe_float(payload.get("stop_loss"), 0.0) <= 0:
        reasons.append("stop_loss_invalid")
    if _safe_float(payload.get("take_profit"), 0.0) <= 0:
        reasons.append("take_profit_invalid")
    if _safe_float(payload.get("quantity"), 0.0) <= 0:
        reasons.append("quantity_invalid")
    if _safe_float(payload.get("risk_amount"), 0.0) <= 0:
        reasons.append("risk_amount_invalid")
    if _safe_float(payload.get("notional"), 0.0) <= 0:
        reasons.append("notional_invalid")
    entry = _safe_float(payload.get("entry_price"), 0.0)
    stop = _safe_float(payload.get("stop_loss"), 0.0)
    take = _safe_float(payload.get("take_profit"), 0.0)
    if side == "BUY" and stop >= entry:
        reasons.append("buy_stop_not_below_entry")
    if side == "BUY" and take <= entry:
        reasons.append("buy_take_profit_not_above_entry")
    if side == "SELL" and stop <= entry:
        reasons.append("sell_stop_not_above_entry")
    if side == "SELL" and take >= entry:
        reasons.append("sell_take_profit_not_below_entry")
    return not reasons, reasons


def _preflight_safety_ok(preflight: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not _safe_bool(preflight.get("would_prepare_submit"), False):
        reasons.append("would_prepare_submit_false")
    if _safe_bool(preflight.get("would_submit"), False) or _safe_bool(preflight.get("would_submit_to_paper_broker"), False):
        reasons.append("upstream_would_submit_detected")
    if _safe_bool(preflight.get("broker_submit_called"), False) or _safe_bool(preflight.get("broker_submit_called_by_second_trade_submit_preflight"), False):
        reasons.append("upstream_broker_submit_called")
    if _safe_int(preflight.get("orders_submitted_by_second_trade_submit_preflight"), 0) != 0:
        reasons.append("upstream_orders_submitted_nonzero")
    if _safe_int(preflight.get("positions_opened_by_second_trade_submit_preflight"), 0) != 0:
        reasons.append("upstream_positions_opened_nonzero")
    if _safe_int(preflight.get("paper_status_open_positions"), 0) != 0:
        reasons.append("paper_status_open_positions_nonzero")
    if _safe_int(preflight.get("paper_status_pending_orders"), 0) != 0:
        reasons.append("paper_status_pending_orders_nonzero")
    if _safe_int(preflight.get("state_open_lsr_v2_positions"), 0) != 0:
        reasons.append("state_open_lsr_v2_positions_nonzero")
    for field in ("live_enabled", "testnet_enabled", "exchange_broker_enabled", "operational_unlock_allowed"):
        if _safe_bool(preflight.get(field), False):
            reasons.append(f"{field}_true")
    return not reasons, reasons


def _report_prerequisites(data_dir: str | Path, settings: LSRV2SecondTradeSubmitBoundarySettings) -> dict[str, Any]:
    report = _read_json(Path(data_dir) / settings.preflight_report_name)
    return {
        "preflight_report_present": bool(report),
        "preflight_pass": str(report.get("decision") or "") == PREFLIGHT_READY_DECISION,
        "second_trade_eligible": _safe_bool(report.get("second_trade_eligible"), False),
        "second_trade_rearm_ready": _safe_bool(report.get("second_trade_rearm_ready"), False),
        "second_trade_route_preflight_ready": _safe_bool(report.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(report.get("second_trade_order_intent_ready"), False),
        "handoff_pass": _safe_bool(report.get("handoff_pass"), False),
        "submit_preflight_events": _safe_int(report.get("submit_preflight_events"), 0),
        "would_prepare_submit_count": _safe_int(report.get("would_prepare_submit_count"), 0),
        "would_submit_count": _safe_int(report.get("would_submit_count"), 0) + _safe_int(report.get("would_submit_to_paper_broker_count"), 0),
        "broker_submit_called": _safe_bool(report.get("broker_submit_called"), False) or _safe_bool(report.get("broker_submit_called_by_second_trade_submit_preflight"), False),
        "orders_submitted": _safe_int(report.get("orders_submitted_by_second_trade_submit_preflight"), 0),
        "positions_opened": _safe_int(report.get("positions_opened_by_second_trade_submit_preflight"), 0),
        "paper_status_open_positions": _safe_int(report.get("paper_status_open_positions"), 0),
        "paper_status_pending_orders": _safe_int(report.get("paper_status_pending_orders"), 0),
        "state_open_lsr_v2_positions": _safe_int(report.get("state_open_lsr_v2_positions"), 0),
    }


def select_second_trade_submit_preflight_events(
    *,
    data_dir: str | Path,
    settings: LSRV2SecondTradeSubmitBoundarySettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    settings = settings or LSRV2SecondTradeSubmitBoundarySettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_preflight_events(_iter_jsonl_tail(base / settings.preflight_jsonl_name, max_lines=settings.max_event_lines))
    preflight_report = _read_json(base / settings.preflight_report_name)

    cycle_id = str(requested_cycle_id or preflight_report.get("cycle_id") or "")
    if not cycle_id:
        for row in reversed(rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break

    selected = [row for row in rows if not cycle_id or _event_cycle(row) == cycle_id]
    historical = [row for row in rows if _event_cycle(row) and _event_cycle(row) != cycle_id]
    metadata = {
        "prompt_id": PROMPT_ID,
        "event_source": "second_trade_submit_preflight_jsonl",
        "strict_cycle_scope": True,
        "preflight_report_decision": preflight_report.get("decision"),
        "preflight_report_status": preflight_report.get("status"),
        "preflight_report_cycle_id": preflight_report.get("cycle_id"),
        "historical_second_trade_submit_preflight_events": len(historical),
    }
    return cycle_id, selected, metadata


def build_lsr_v2_second_trade_submit_boundary_event(
    *,
    preflight_event: Mapping[str, Any],
    settings: LSRV2SecondTradeSubmitBoundarySettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
    index: int = 0,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitBoundarySettings()
    prereq = dict(prerequisites or {})
    pre = dict(preflight_event or {})
    payload = _payload_from_preflight(pre)
    payload_ok, payload_reasons = _payload_valid(payload)
    safety_ok, safety_reasons = _preflight_safety_ok(pre)

    blockers: list[str] = []
    if str(settings.mode).lower() != "paper":
        blockers.append("mode_not_paper")
    if not _safe_bool(prereq.get("preflight_pass"), False):
        blockers.append("second_trade_submit_preflight_not_passed")
    if not _safe_bool(prereq.get("second_trade_eligible"), False):
        blockers.append("second_trade_not_eligible")
    if not _safe_bool(prereq.get("second_trade_rearm_ready"), False):
        blockers.append("second_trade_rearm_not_ready")
    if not _safe_bool(prereq.get("second_trade_route_preflight_ready"), False):
        blockers.append("second_trade_route_not_ready")
    if not _safe_bool(prereq.get("second_trade_order_intent_ready"), False):
        blockers.append("second_trade_order_intent_not_ready")
    if _safe_int(prereq.get("would_prepare_submit_count"), 0) <= 0:
        blockers.append("second_trade_would_prepare_submit_missing")
    if _safe_int(prereq.get("paper_status_open_positions"), 0) != 0 or _safe_int(prereq.get("paper_status_pending_orders"), 0) != 0 or _safe_int(prereq.get("state_open_lsr_v2_positions"), 0) != 0:
        blockers.append("paper_state_not_clean")
    if _safe_int(prereq.get("would_submit_count"), 0) != 0 or _safe_bool(prereq.get("broker_submit_called"), False):
        blockers.append("upstream_submit_attempt_detected")
    if _safe_int(prereq.get("orders_submitted"), 0) != 0 or _safe_int(prereq.get("positions_opened"), 0) != 0:
        blockers.append("upstream_order_or_position_detected")
    if not payload_ok:
        blockers.extend([f"payload_{reason}" for reason in payload_reasons])
    if not safety_ok:
        blockers.extend(safety_reasons)
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")
    if not settings.submit_armed:
        blockers.append("second_trade_submit_not_armed")
    if not settings.submit_confirmation_ok:
        blockers.append("second_trade_submit_confirmation_missing")
    if index >= max(settings.max_orders, 0):
        blockers.append("second_trade_max_order_cap_exceeded")

    submit_ready = bool(
        payload_ok
        and safety_ok
        and settings.fail_closed
        and str(settings.mode).lower() == "paper"
        and _safe_bool(prereq.get("preflight_pass"), False)
        and _safe_bool(prereq.get("second_trade_eligible"), False)
        and _safe_bool(prereq.get("second_trade_rearm_ready"), False)
        and _safe_bool(prereq.get("second_trade_route_preflight_ready"), False)
        and _safe_bool(prereq.get("second_trade_order_intent_ready"), False)
        and _safe_int(prereq.get("would_prepare_submit_count"), 0) > 0
        and _safe_int(prereq.get("paper_status_open_positions"), 0) == 0
        and _safe_int(prereq.get("paper_status_pending_orders"), 0) == 0
        and _safe_int(prereq.get("state_open_lsr_v2_positions"), 0) == 0
        and _safe_int(prereq.get("would_submit_count"), 0) == 0
        and not _safe_bool(prereq.get("broker_submit_called"), False)
        and _safe_int(prereq.get("orders_submitted"), 0) == 0
        and _safe_int(prereq.get("positions_opened"), 0) == 0
        and settings.submit_armed
        and settings.submit_confirmation_ok
        and index < max(settings.max_orders, 0)
    )

    if not settings.submit_armed:
        blocked_reason = "second_trade_submit_not_armed"
    elif not settings.submit_confirmation_ok:
        blocked_reason = "second_trade_submit_confirmation_missing"
    elif index >= max(settings.max_orders, 0):
        blocked_reason = "second_trade_max_order_cap_exceeded"
    elif not submit_ready:
        blocked_reason = blockers[0] if blockers else "second_trade_submit_not_ready"
    else:
        blocked_reason = "second_trade_submit_ready_armed_broker_not_wired"

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": payload.get("cycle_id", ""),
        "symbol": payload.get("symbol", ""),
        "timeframe": payload.get("timeframe", ""),
        "side": payload.get("side", ""),
        "order_type": payload.get("order_type", ""),
        "profile_name": payload.get("profile_name", settings.profile_name),
        "selected_overlay_id": payload.get("selected_overlay_id", settings.selected_overlay_id),
        "source": "lsr_v2_second_trade_submit_preflight",
        "source_event_type": str(pre.get("event_type") or PREFLIGHT_EVENT_TYPE),
        "candidate_id": payload.get("candidate_id", ""),
        "payload": payload,
        "payload_valid": bool(payload_ok),
        "payload_invalid_reasons": payload_reasons,
        "entry_price": payload.get("entry_price"),
        "stop_loss": payload.get("stop_loss"),
        "take_profit": payload.get("take_profit"),
        "risk_per_trade_pct": payload.get("risk_per_trade_pct"),
        "risk_amount": payload.get("risk_amount"),
        "position_size": payload.get("position_size"),
        "quantity": payload.get("quantity"),
        "notional": payload.get("notional"),
        "max_positions": payload.get("max_positions"),
        "second_trade_submit_armed": bool(settings.submit_armed),
        "second_trade_submit_confirmation_ok": bool(settings.submit_confirmation_ok),
        "second_trade_submit_ready": bool(submit_ready),
        "second_trade_submit_enabled": False,
        "second_trade_execute_enabled": False,
        "submit_enabled": False,
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "order_submitted": False,
        "position_opened": False,
        "blocked_reason": blocked_reason,
        "blocked_reasons": sorted(set(blockers)),
        "second_trade_eligible": _safe_bool(prereq.get("second_trade_eligible"), False),
        "second_trade_rearm_ready": _safe_bool(prereq.get("second_trade_rearm_ready"), False),
        "second_trade_route_preflight_ready": _safe_bool(prereq.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(prereq.get("second_trade_order_intent_ready"), False),
        "handoff_pass": _safe_bool(prereq.get("handoff_pass"), False),
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_submit_boundary": 0,
        "positions_opened_by_second_trade_submit_boundary": 0,
        "positions_closed_by_second_trade_submit_boundary": 0,
        "promotion_ready": False,
        "max_orders": settings.max_orders,
        "single_order_gate": True,
        "audit_only": True,
    }


def build_lsr_v2_second_trade_submit_boundary_events(
    preflight_events: Iterable[Mapping[str, Any]],
    *,
    settings: LSRV2SecondTradeSubmitBoundarySettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = settings or LSRV2SecondTradeSubmitBoundarySettings()
    eligible = [dict(e) for e in _dedupe_preflight_events(preflight_events) if _safe_bool(e.get("would_prepare_submit"), False)]
    events: list[dict[str, Any]] = []
    for idx, preflight in enumerate(eligible):
        events.append(build_lsr_v2_second_trade_submit_boundary_event(
            preflight_event=preflight,
            settings=settings,
            prerequisites=prerequisites,
            index=idx,
        ))
    return events


def summarize_lsr_v2_second_trade_submit_boundary(
    *,
    cycle_id: str,
    preflight_events: Iterable[Mapping[str, Any]],
    boundary_events: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2SecondTradeSubmitBoundarySettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitBoundarySettings(data_dir=str(data_dir))
    prereq = dict(prerequisites or {})
    metadata = dict(metadata or {})
    preflight_rows = _dedupe_preflight_events(preflight_events)
    boundary_rows = [dict(e) for e in boundary_events]
    ready_rows = [e for e in boundary_rows if _safe_bool(e.get("second_trade_submit_ready"), False)]

    blockers: list[str] = []
    if not preflight_rows:
        blockers.append("second_trade_submit_preflight_missing")
    if not _safe_bool(prereq.get("preflight_report_present"), False):
        blockers.append("second_trade_submit_preflight_report_missing")
    if not _safe_bool(prereq.get("preflight_pass"), False):
        blockers.append("second_trade_submit_preflight_not_passed")
    if _safe_int(prereq.get("paper_status_open_positions"), 0) != 0 or _safe_int(prereq.get("paper_status_pending_orders"), 0) != 0 or _safe_int(prereq.get("state_open_lsr_v2_positions"), 0) != 0:
        blockers.append("paper_state_not_clean")
    if _safe_int(prereq.get("would_submit_count"), 0) != 0 or _safe_bool(prereq.get("broker_submit_called"), False):
        blockers.append("upstream_submit_attempt_detected")
    if _safe_int(prereq.get("orders_submitted"), 0) != 0 or _safe_int(prereq.get("positions_opened"), 0) != 0:
        blockers.append("upstream_order_or_position_detected")
    if not settings.submit_armed:
        blockers.append("second_trade_submit_not_armed")
    if not settings.submit_confirmation_ok:
        blockers.append("second_trade_submit_confirmation_missing")
    if settings.max_orders != 1:
        blockers.append("max_orders_not_single_order_gate")

    event_safety_violation = any(
        _safe_bool(e.get("would_submit"), False)
        or _safe_bool(e.get("would_submit_to_paper_broker"), False)
        or _safe_bool(e.get("broker_submit_called"), False)
        or _safe_int(e.get("orders_submitted_by_second_trade_submit_boundary"), 0) != 0
        or _safe_int(e.get("positions_opened_by_second_trade_submit_boundary"), 0) != 0
        or _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        for e in boundary_rows
    )
    if event_safety_violation:
        blockers.append("safety_violation_detected")

    if not preflight_rows or not _safe_bool(prereq.get("preflight_report_present"), False):
        decision = PREFLIGHT_MISSING_DECISION
        status = "WARN"
    elif event_safety_violation or _safe_int(prereq.get("would_submit_count"), 0) != 0 or _safe_bool(prereq.get("broker_submit_called"), False):
        decision = REJECT_DECISION
        status = "FAIL"
    elif "paper_state_not_clean" in blockers:
        decision = STATE_NOT_CLEAN_DECISION
        status = "WARN"
    elif not settings.submit_armed:
        decision = NOT_ARMED_DECISION
        status = "WARN"
    elif not settings.submit_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status = "WARN"
    elif settings.max_orders != 1:
        decision = CAP_EXCEEDED_DECISION
        status = "WARN"
    elif ready_rows:
        decision = READY_ARMED_DECISION
        status = "PASS"
    else:
        decision = REJECT_DECISION
        status = "WARN"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in ready_rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in ready_rows), 10)
    safety_checks = {
        "second_trade_submit_enabled_false": True,
        "second_trade_execute_enabled_false": True,
        "would_submit_zero": True,
        "would_submit_to_paper_broker_zero": True,
        "broker_submit_called_false": True,
        "orders_submitted_zero": True,
        "positions_opened_zero": True,
        "paper_state_clean": _safe_int(prereq.get("paper_status_open_positions"), 0) == 0 and _safe_int(prereq.get("paper_status_pending_orders"), 0) == 0 and _safe_int(prereq.get("state_open_lsr_v2_positions"), 0) == 0,
        "single_order_gate": settings.max_orders == 1,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
    }
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "SECOND_TRADE_SUBMIT_BOUNDARY",
            "SECOND_TRADE_EXECUTION_STILL_DISABLED",
            "SINGLE_ORDER_GATE",
        ] + (["SECOND_TRADE_READY_ARMED"] if decision == READY_ARMED_DECISION else ["KEEP_DIAGNOSTIC"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "second_trade_submit_preflight_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_second_trade_submit_preflight_events": _safe_int(metadata.get("historical_second_trade_submit_preflight_events"), 0),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "second_trade_eligible": _safe_bool(prereq.get("second_trade_eligible"), False),
        "second_trade_rearm_ready": _safe_bool(prereq.get("second_trade_rearm_ready"), False),
        "second_trade_route_preflight_ready": _safe_bool(prereq.get("second_trade_route_preflight_ready"), False),
        "second_trade_order_intent_ready": _safe_bool(prereq.get("second_trade_order_intent_ready"), False),
        "handoff_pass": _safe_bool(prereq.get("handoff_pass"), False),
        "submit_preflight_pass": _safe_bool(prereq.get("preflight_pass"), False),
        "submit_preflight_events": len(preflight_rows),
        "submit_boundary_events": len(boundary_rows),
        "second_trade_submit_ready_count": len(ready_rows),
        "second_trade_submit_armed": bool(settings.submit_armed),
        "second_trade_submit_confirmation_ok": bool(settings.submit_confirmation_ok),
        "max_orders": settings.max_orders,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_second_trade_submit_boundary": False,
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
        "safety_ok": bool(all(safety_checks.values()) and not event_safety_violation),
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_submit_boundary": 0,
        "positions_opened_by_second_trade_submit_boundary": 0,
        "positions_closed_by_second_trade_submit_boundary": 0,
        "promotion_ready": False,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


def build_lsr_v2_second_trade_submit_boundary_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondTradeSubmitBoundarySettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitBoundarySettings(data_dir=str(data_dir))
    selected_cycle_id, preflight_events, metadata = select_second_trade_submit_preflight_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    prereq = _report_prerequisites(data_dir, settings)
    boundary_events = build_lsr_v2_second_trade_submit_boundary_events(
        preflight_events,
        settings=settings,
        prerequisites=prereq,
    )
    base = Path(data_dir)
    _write_jsonl_replace(base / settings.jsonl_name, boundary_events)
    report = summarize_lsr_v2_second_trade_submit_boundary(
        cycle_id=selected_cycle_id,
        preflight_events=preflight_events,
        boundary_events=boundary_events,
        data_dir=base,
        settings=settings,
        prerequisites=prereq,
        metadata=metadata,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
