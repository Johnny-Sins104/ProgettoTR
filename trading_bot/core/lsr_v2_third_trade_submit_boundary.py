"""Prompt 29.4.4s-10an — LSR-v2 third paper-trade submit boundary.

Consumes the third-trade submit preflight from 29.4.4s-10am and creates a
manual submit-boundary audit record for a future supervised paper-only submit
execution.  This module is intentionally non-operational: it never submits an
order, never calls a broker, never opens/closes a position, and never mutates
paper state/status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import os

try:  # package import in the full project
    from .lsr_v2_third_trade_submit_preflight import (  # type: ignore
        EVENT_TYPE as PREFLIGHT_EVENT_TYPE,
        JSONL_NAME as PREFLIGHT_JSONL_NAME,
        READY_DECISION as PREFLIGHT_READY_DECISION,
        REPORT_NAME as PREFLIGHT_REPORT_NAME,
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
    from lsr_v2_third_trade_submit_preflight import (  # type: ignore
        EVENT_TYPE as PREFLIGHT_EVENT_TYPE,
        JSONL_NAME as PREFLIGHT_JSONL_NAME,
        READY_DECISION as PREFLIGHT_READY_DECISION,
        REPORT_NAME as PREFLIGHT_REPORT_NAME,
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

PROMPT_ID = "29.4.4s-10an"
EVENT_TYPE = "LSR_V2_THIRD_TRADE_SUBMIT_BOUNDARY"
REPORT_NAME = "lsr_v2_third_trade_submit_boundary_report.json"
JSONL_NAME = "lsr_v2_third_trade_submit_boundary.jsonl"

SUBMIT_ARM_ENV = "LSR_V2_THIRD_TRADE_SUBMIT_ARM"
SUBMIT_CONFIRM_ENV = "LSR_V2_THIRD_TRADE_SUBMIT_CONFIRMATION"
MAX_ORDERS_ENV = "LSR_V2_THIRD_TRADE_MAX_ORDERS"
REQUIRED_SUBMIT_ARM_VALUE = "1"
REQUIRED_SUBMIT_CONFIRMATION = "I_UNDERSTAND_THIRD_SINGLE_PAPER_ORDER"

READY_ARMED_DECISION = "LSR_V2_THIRD_SINGLE_PAPER_SUBMIT_READY_ARMED"
NOT_ARMED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_NOT_ARMED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_CONFIRMATION_MISSING"
PREFLIGHT_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_PREFLIGHT_MISSING"
PAYLOAD_INVALID_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_BOUNDARY_PAYLOAD_INVALID"
MAX_ORDER_CAP_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_MAX_ORDER_CAP_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_THIRD_SUBMIT_BOUNDARY_SAFETY_FAILED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LSRV2ThirdTradeSubmitBoundarySettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    preflight_report_name: str = PREFLIGHT_REPORT_NAME
    preflight_jsonl_name: str = PREFLIGHT_JSONL_NAME
    max_event_lines: int = 50000
    submit_arm: str = ""
    submit_confirmation: str = ""
    required_submit_arm_value: str = REQUIRED_SUBMIT_ARM_VALUE
    required_submit_confirmation: str = REQUIRED_SUBMIT_CONFIRMATION
    max_orders: int = 1
    mode: str = "paper"
    paper_broker_adapter: str = PAPER_BROKER_ADAPTER_NAME
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2ThirdTradeSubmitBoundarySettings":
        max_orders = _safe_int(os.getenv(MAX_ORDERS_ENV), 1)
        if max_orders <= 0:
            max_orders = 1
        return cls(
            data_dir=data_dir,
            submit_arm=str(os.getenv(SUBMIT_ARM_ENV) or ""),
            submit_confirmation=str(os.getenv(SUBMIT_CONFIRM_ENV) or ""),
            max_orders=max_orders,
            mode=str(os.getenv("LSR_V2_THIRD_TRADE_SUBMIT_MODE") or "paper"),
        )

    @property
    def submit_armed(self) -> bool:
        return str(self.submit_arm).strip() == self.required_submit_arm_value

    @property
    def submit_confirmation_ok(self) -> bool:
        return str(self.submit_confirmation).strip() == self.required_submit_confirmation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _event_cycle(row: Mapping[str, Any]) -> str:
    return str(row.get("cycle_id") or row.get("lsr_v2_runtime_cycle_id") or "")


def _payload_from_preflight(row: Mapping[str, Any]) -> dict[str, Any]:
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


def _dedupe_preflight_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        if row.get("event_type") != PREFLIGHT_EVENT_TYPE:
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


def _preflight_report_ready(report: Mapping[str, Any]) -> bool:
    return (
        report.get("status") == "PASS"
        and report.get("decision") == PREFLIGHT_READY_DECISION
        and _safe_bool(report.get("third_trade_handoff_ready"), False)
        and _safe_bool(report.get("third_trade_route_preflight_ready"), False)
        and _safe_bool(report.get("third_trade_order_intent_ready"), False)
        and _safe_int(report.get("payload_valid_count"), 0) > 0
        and _safe_int(report.get("would_prepare_submit_count"), 0) > 0
    )


def _unsafe_preflight_flags(report: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> list[str]:
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
        "broker_submit_called_by_third_trade_submit_preflight",
        "broker_close_called_by_third_trade_submit_preflight",
        "paper_state_modified_by_third_trade_submit_preflight",
        "paper_status_modified_by_third_trade_submit_preflight",
    ]
    unsafe_count_keys = [
        "orders_submitted_by_third_trade_submit_preflight",
        "positions_opened_by_third_trade_submit_preflight",
        "positions_closed_by_third_trade_submit_preflight",
        "would_submit_count",
        "would_submit_to_paper_broker_count",
    ]
    for key in unsafe_bool_keys:
        if _safe_bool(report.get(key), False):
            blockers.append(f"preflight_report_{key}")
    for key in unsafe_count_keys:
        if _safe_int(report.get(key), 0) > 0:
            blockers.append(f"preflight_report_{key}")
    for row in rows:
        for key in unsafe_bool_keys:
            if _safe_bool(row.get(key), False):
                blockers.append(f"preflight_event_{key}")
        for key in unsafe_count_keys:
            if _safe_int(row.get(key), 0) > 0:
                blockers.append(f"preflight_event_{key}")
        if _safe_bool(row.get("would_submit"), False):
            blockers.append("preflight_event_would_submit")
        if _safe_bool(row.get("would_submit_to_paper_broker"), False):
            blockers.append("preflight_event_would_submit_to_paper_broker")
    return sorted(set(blockers))


def build_third_trade_submit_boundary_event(
    *,
    preflight_event: Mapping[str, Any],
    settings: LSRV2ThirdTradeSubmitBoundarySettings,
    index: int = 0,
) -> dict[str, Any]:
    payload = _payload_from_preflight(preflight_event)
    payload_ok, invalid_reasons = _payload_valid(payload)
    preflight_ready = bool(
        _safe_bool(preflight_event.get("would_prepare_submit"), False)
        and _safe_bool(preflight_event.get("payload_valid"), False)
    )
    controls_ok = bool(settings.submit_armed and settings.submit_confirmation_ok)
    max_orders_ok = bool(settings.max_orders == 1 and index < max(settings.max_orders, 0))
    mode_ok = str(settings.mode).lower() == "paper"
    ready = bool(payload_ok and preflight_ready and controls_ok and max_orders_ok and mode_ok and settings.fail_closed)

    blockers: list[str] = []
    if not preflight_ready:
        blockers.append("third_trade_submit_preflight_not_ready")
    if not settings.submit_armed:
        blockers.append("third_trade_submit_not_armed")
    if not settings.submit_confirmation_ok:
        blockers.append("third_trade_submit_confirmation_missing")
    if settings.max_orders != 1:
        blockers.append("max_orders_not_one")
    if index >= max(settings.max_orders, 0):
        blockers.append("third_trade_max_order_cap_exceeded")
    if not mode_ok:
        blockers.append("mode_not_paper")
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")
    if not payload_ok:
        blockers.extend([f"payload_{reason}" for reason in invalid_reasons])

    if not settings.submit_armed:
        blocked_reason = "third_trade_submit_not_armed"
    elif not settings.submit_confirmation_ok:
        blocked_reason = "third_trade_submit_confirmation_missing"
    elif settings.max_orders != 1 or index >= max(settings.max_orders, 0):
        blocked_reason = "third_trade_max_order_cap_exceeded"
    elif not payload_ok:
        blocked_reason = "payload_invalid"
    elif not preflight_ready:
        blocked_reason = "third_trade_submit_preflight_not_ready"
    elif ready:
        blocked_reason = "third_trade_execution_still_disabled"
    else:
        blocked_reason = blockers[0] if blockers else "third_trade_submit_not_ready"

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
        "source": "lsr_v2_third_trade_submit_preflight",
        "source_event_type": str(preflight_event.get("event_type") or PREFLIGHT_EVENT_TYPE),
        "payload": payload,
        "payload_valid": bool(payload_ok),
        "payload_invalid_reasons": invalid_reasons,
        "side": payload.get("side", ""),
        "order_type": payload.get("order_type", "LIMIT"),
        "entry_price": payload.get("entry_price", 0.0),
        "stop_loss": payload.get("stop_loss", 0.0),
        "take_profit": payload.get("take_profit", 0.0),
        "risk_per_trade_pct": payload.get("risk_per_trade_pct", 0.0025),
        "risk_amount": payload.get("risk_amount", 0.0) if ready else 0.0,
        "position_size": payload.get("position_size", 0.0) if ready else 0.0,
        "quantity": payload.get("quantity", 0.0) if ready else 0.0,
        "notional": payload.get("notional", 0.0) if ready else 0.0,
        "max_positions": payload.get("max_positions", 1),
        "max_orders": int(settings.max_orders),
        "mode": str(settings.mode),
        "paper_broker_adapter": settings.paper_broker_adapter,
        "third_trade_eligible": True,
        "third_trade_rearm_ready": True,
        "third_trade_route_preflight_ready": True,
        "third_trade_order_intent_ready": True,
        "third_trade_handoff_ready": True,
        "third_trade_submit_preflight_ready": True,
        "third_trade_submit_armed": bool(settings.submit_armed),
        "third_trade_submit_confirmation_ok": bool(settings.submit_confirmation_ok),
        "third_trade_submit_ready": bool(ready),
        "third_trade_submit_boundary_ready": bool(ready),
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "would_create_paper_order": bool(ready),
        "would_create_order": bool(ready),
        "would_prepare_submit": bool(ready),
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "broker_close_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_third_trade_submit_boundary": 0,
        "positions_opened_by_third_trade_submit_boundary": 0,
        "positions_closed_by_third_trade_submit_boundary": 0,
        "paper_state_modified_by_third_trade_submit_boundary": False,
        "paper_status_modified_by_third_trade_submit_boundary": False,
        "blocked_reason": blocked_reason,
        "blocked_reasons": sorted(set(blockers)),
        "single_order_gate": True,
        "audit_only": True,
    }


def build_lsr_v2_third_trade_submit_boundary_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2ThirdTradeSubmitBoundarySettings | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or LSRV2ThirdTradeSubmitBoundarySettings.from_env(data_dir=str(base))
    preflight_report = _read_json(base / settings.preflight_report_name)
    preflight_rows = _iter_jsonl_tail(base / settings.preflight_jsonl_name, max_lines=settings.max_event_lines)
    selected_cycle_id = str(cycle_id or preflight_report.get("cycle_id") or "")
    preflight_events_all = _dedupe_preflight_rows([row for row in preflight_rows if not selected_cycle_id or _event_cycle(row) == selected_cycle_id])
    prepared_preflights = [row for row in preflight_events_all if _safe_bool(row.get("would_prepare_submit"), False)]
    unsafe_blockers = _unsafe_preflight_flags(preflight_report, preflight_events_all)
    preflight_ready = _preflight_report_ready(preflight_report)

    blockers: list[str] = []
    if not preflight_ready:
        blockers.append("third_trade_submit_preflight_not_ready")
    if not preflight_events_all:
        blockers.append("third_trade_submit_preflight_event_missing")
    if preflight_events_all and not prepared_preflights:
        blockers.append("third_trade_no_prepared_submit")
    if not settings.submit_armed:
        blockers.append("third_trade_submit_not_armed")
    if settings.submit_armed and not settings.submit_confirmation_ok:
        blockers.append("third_trade_submit_confirmation_missing")
    if settings.max_orders != 1:
        blockers.append("max_orders_not_one")
    if str(settings.mode).lower() != "paper":
        blockers.append("mode_not_paper")
    blockers.extend(unsafe_blockers)
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    boundary_events: list[dict[str, Any]] = []
    if preflight_ready and prepared_preflights and not unsafe_blockers and settings.fail_closed:
        boundary_events = [build_third_trade_submit_boundary_event(preflight_event=prepared_preflights[-1], settings=settings)]

    payload_valid_count = sum(1 for row in boundary_events if _safe_bool(row.get("payload_valid"), False))
    payload_invalid_count = sum(1 for row in boundary_events if not _safe_bool(row.get("payload_valid"), False))
    ready_rows = [row for row in boundary_events if _safe_bool(row.get("third_trade_submit_ready"), False)]
    would_create_count = sum(1 for row in boundary_events if _safe_bool(row.get("would_create_order"), False))
    would_prepare_count = sum(1 for row in boundary_events if _safe_bool(row.get("would_prepare_submit"), False))
    broker_submit_called = any(_safe_bool(row.get("broker_submit_called"), False) for row in boundary_events)

    if unsafe_blockers or not settings.fail_closed or broker_submit_called or str(settings.mode).lower() != "paper":
        decision = REJECT_DECISION
        status = "FAIL"
    elif not preflight_ready:
        decision = PREFLIGHT_MISSING_DECISION
        status = "WARN"
    elif not preflight_events_all or (preflight_events_all and not prepared_preflights):
        decision = PAYLOAD_INVALID_DECISION
        status = "WARN"
    elif settings.max_orders != 1:
        decision = MAX_ORDER_CAP_DECISION
        status = "WARN"
    elif not settings.submit_armed:
        decision = NOT_ARMED_DECISION
        status = "WARN"
    elif not settings.submit_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status = "WARN"
    elif payload_invalid_count > 0 or payload_valid_count == 0 or not ready_rows:
        decision = PAYLOAD_INVALID_DECISION
        status = "WARN"
    else:
        decision = READY_ARMED_DECISION
        status = "PASS"

    classification_labels: list[str] = ["THIRD_TRADE_SUBMIT_BOUNDARY", "EXECUTION_STILL_DISABLED"]
    if decision == READY_ARMED_DECISION:
        classification_labels.extend(["THIRD_SINGLE_PAPER_SUBMIT_READY_ARMED", "PAPER_BROKER_SUBMIT_STILL_DISABLED"])
    elif decision == NOT_ARMED_DECISION:
        classification_labels.append("THIRD_TRADE_SUBMIT_NOT_ARMED")
    elif decision == CONFIRMATION_MISSING_DECISION:
        classification_labels.append("THIRD_TRADE_SUBMIT_CONFIRMATION_MISSING")
    elif decision == PREFLIGHT_MISSING_DECISION:
        classification_labels.append("THIRD_TRADE_SUBMIT_PREFLIGHT_MISSING")
    elif decision == MAX_ORDER_CAP_DECISION:
        classification_labels.append("THIRD_TRADE_MAX_ORDER_CAP_BLOCKED")
    else:
        classification_labels.append("THIRD_TRADE_SUBMIT_BOUNDARY_REJECTED")

    total_risk_amount = round(sum(_safe_float(row.get("risk_amount"), 0.0) for row in ready_rows), 10)
    total_notional = round(sum(_safe_float(row.get("notional"), 0.0) for row in ready_rows), 10)
    report = {
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": sorted(set(blockers)),
        "cycle_id": selected_cycle_id,
        "event_source": "third_trade_submit_preflight_jsonl",
        "strict_cycle_scope": True,
        "preflight_decision": preflight_report.get("decision"),
        "preflight_status": preflight_report.get("status"),
        "submit_preflight_pass": bool(preflight_ready),
        "third_trade_submit_preflight_ready": bool(preflight_ready),
        "third_trade_handoff_ready": bool(_safe_bool(preflight_report.get("third_trade_handoff_ready"), False)),
        "third_trade_route_preflight_ready": bool(_safe_bool(preflight_report.get("third_trade_route_preflight_ready"), False)),
        "third_trade_order_intent_ready": bool(_safe_bool(preflight_report.get("third_trade_order_intent_ready"), False)),
        "third_trade_rearm_ready": bool(_safe_bool(preflight_report.get("third_trade_rearm_ready"), False)),
        "third_trade_eligible": bool(_safe_bool(preflight_report.get("third_trade_eligible"), False)),
        "submit_preflight_events": len(preflight_events_all),
        "prepared_submit_preflight_events": len(prepared_preflights),
        "submit_boundary_events": len(boundary_events),
        "third_trade_submit_armed": bool(settings.submit_armed),
        "third_trade_submit_confirmation_ok": bool(settings.submit_confirmation_ok),
        "third_trade_submit_ready_count": len(ready_rows),
        "payload_valid_count": payload_valid_count,
        "payload_invalid_count": payload_invalid_count,
        "would_create_paper_order_count": would_create_count,
        "would_create_order_count": would_create_count,
        "would_prepare_submit_count": would_prepare_count,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_third_trade_submit_boundary": False,
        "broker_close_called_by_third_trade_submit_boundary": False,
        "paper_broker_adapter": settings.paper_broker_adapter,
        "max_orders": int(settings.max_orders),
        "mode": str(settings.mode),
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "orders_submitted_by_third_trade_submit_boundary": 0,
        "positions_opened_by_third_trade_submit_boundary": 0,
        "positions_closed_by_third_trade_submit_boundary": 0,
        "paper_state_modified_by_third_trade_submit_boundary": False,
        "paper_status_modified_by_third_trade_submit_boundary": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "symbols": sorted({str(row.get("symbol") or "") for row in boundary_events if row.get("symbol")}),
        "sides": sorted({str(row.get("side") or "") for row in boundary_events if row.get("side")}),
        "total_risk_amount": total_risk_amount,
        "total_notional": total_notional,
        "settings": settings.to_dict(),
        "next_step": "third_trade_submit_execution" if decision == READY_ARMED_DECISION else "operator_submit_arm_or_resolve_blockers",
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    if write_outputs:
        _write_json(base / settings.report_name, report)
        _write_jsonl_replace(base / settings.jsonl_name, boundary_events)
    return report
