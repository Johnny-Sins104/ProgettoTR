"""Prompt 29.4.4s-10h — LSR-v2 paper broker handoff dry-run / order payload schema audit.

Converts fail-closed LSR-v2 paper order intent rows into a diagnostic payload
that is compatible with a paper broker handoff boundary, without calling the
broker and without mutating paper state.  This is the schema/payload audit layer
after ``LSR_V2_PAPER_ORDER_INTENT_AUDIT`` and before any supervised paper
submission layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

try:  # package import in the full project
    from .lsr_v2_order_intent_audit import (
        ORDER_INTENT_EVENT_TYPE,
        ORDER_INTENT_JSONL_NAME,
        ORDER_INTENT_REPORT_NAME,
        _iter_jsonl_tail,
        _latest_completed_cycle_from_paper_events,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_order_intent_audit import (  # type: ignore
        ORDER_INTENT_EVENT_TYPE,
        ORDER_INTENT_JSONL_NAME,
        ORDER_INTENT_REPORT_NAME,
        _iter_jsonl_tail,
        _latest_completed_cycle_from_paper_events,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
    )

PROMPT_ID = "29.4.4s-10h"
HANDOFF_EVENT_TYPE = "LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN"
HANDOFF_REPORT_NAME = "lsr_v2_paper_broker_handoff_dry_run_report.json"
HANDOFF_JSONL_NAME = "lsr_v2_paper_broker_handoff_dry_run.jsonl"
PAPER_EVENTS_NAME = "paper_events.jsonl"

READY_DECISION = "LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC"
NO_INTENTS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_NO_ORDER_INTENTS"
NO_CREATE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_NO_CREATABLE_INTENTS"
INVALID_PAYLOAD_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_PAYLOAD_INVALID"
SAFETY_BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_SAFETY_BLOCKED"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_ERROR"


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


def _event_cycle(event: Mapping[str, Any]) -> str:
    return str(event.get("cycle_id") or event.get("lsr_v2_runtime_cycle_id") or "")


def _intent_key(event: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(event), sort_keys=True, default=str)
    except Exception:
        return "|".join([
            str(event.get("event_type") or ""),
            str(event.get("cycle_id") or ""),
            str(event.get("symbol") or ""),
            str(event.get("candidate_id") or ""),
        ])


def _dedupe_intents(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        if row.get("event_type") != ORDER_INTENT_EVENT_TYPE:
            continue
        key = _intent_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _round(value: Any, digits: int = 10) -> float:
    return round(float(_safe_float(value, 0.0)), digits)


@dataclass(frozen=True)
class LSRV2PaperBrokerHandoffDryRunSettings:
    data_dir: str = "data"
    events_name: str = PAPER_EVENTS_NAME
    order_intent_report_name: str = ORDER_INTENT_REPORT_NAME
    order_intent_jsonl_name: str = ORDER_INTENT_JSONL_NAME
    report_name: str = HANDOFF_REPORT_NAME
    jsonl_name: str = HANDOFF_JSONL_NAME
    max_event_lines: int = 50000
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    default_order_type: str = "LIMIT"
    profile_name: str = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    selected_overlay_id: str = "combo_loss3_dd10_side_cap"
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_cycle_scoped_order_intents(
    *,
    data_dir: str | Path,
    settings: LSRV2PaperBrokerHandoffDryRunSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Select strict cycle-scoped order intents.

    The order-intent JSONL is primary because s-10g materializes exactly the
    payload-level candidates that reached ``would_route=true``.  The report and
    paper events are only used to infer the latest cycle id when the caller does
    not provide one.
    """
    settings = settings or LSRV2PaperBrokerHandoffDryRunSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    intent_rows = _dedupe_intents(_iter_jsonl_tail(base / settings.order_intent_jsonl_name, max_lines=settings.max_event_lines))
    paper_rows = _iter_jsonl_tail(base / settings.events_name, max_lines=settings.max_event_lines)
    intent_report = _read_json(base / settings.order_intent_report_name)

    cycle_id = str(requested_cycle_id or "")
    if not cycle_id:
        cycle_id = str(intent_report.get("cycle_id") or "")
    if not cycle_id:
        cycle_id = _latest_completed_cycle_from_paper_events(paper_rows)
    if not cycle_id:
        for row in reversed(intent_rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break

    selected = [row for row in intent_rows if not cycle_id or _event_cycle(row) == cycle_id]
    historical = [row for row in intent_rows if _event_cycle(row) and _event_cycle(row) != cycle_id]
    metadata = {
        "prompt_id": PROMPT_ID,
        "event_source": "order_intent_jsonl",
        "strict_cycle_scope": True,
        "order_intent_report_decision": intent_report.get("decision"),
        "order_intent_report_cycle_id": intent_report.get("cycle_id"),
        "historical_order_intent_events": len(historical),
        "historical_would_create_order_events": sum(1 for row in historical if _safe_bool(row.get("would_create_order"), False)),
    }
    return cycle_id, selected, metadata


def validate_lsr_v2_paper_order_payload(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
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


def build_lsr_v2_paper_broker_payload_from_intent(
    intent: Mapping[str, Any],
    *,
    settings: LSRV2PaperBrokerHandoffDryRunSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperBrokerHandoffDryRunSettings()
    order_type = str(intent.get("order_type") or settings.default_order_type or "LIMIT").upper()
    payload = {
        "source": "lsr_v2_order_intent",
        "profile_name": str(intent.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(intent.get("selected_overlay_id") or settings.selected_overlay_id),
        "cycle_id": str(intent.get("cycle_id") or ""),
        "symbol": str(intent.get("symbol") or ""),
        "timeframe": str(intent.get("timeframe") or ""),
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
        "candidate_id": str(intent.get("candidate_id") or ""),
        "duplicate_check": intent.get("duplicate_check") if isinstance(intent.get("duplicate_check"), Mapping) else {},
        "cadence_check": intent.get("cadence_check") if isinstance(intent.get("cadence_check"), Mapping) else {},
        "paper_broker_adapter": settings.paper_broker_adapter_name,
    }
    valid, reasons = validate_lsr_v2_paper_order_payload(payload)
    payload["payload_valid"] = bool(valid)
    payload["payload_invalid_reasons"] = reasons
    return payload


def build_lsr_v2_paper_broker_handoff_event(
    *,
    order_intent: Mapping[str, Any],
    settings: LSRV2PaperBrokerHandoffDryRunSettings | None = None,
) -> dict[str, Any]:
    """Build one fail-closed paper-broker handoff dry-run event."""
    settings = settings or LSRV2PaperBrokerHandoffDryRunSettings()
    intent = dict(order_intent or {})
    payload = build_lsr_v2_paper_broker_payload_from_intent(intent, settings=settings)
    payload_valid = _safe_bool(payload.get("payload_valid"), False)
    would_create_order = _safe_bool(intent.get("would_create_order"), False)
    would_route = _safe_bool(intent.get("would_route"), False)
    operator_authorized = _safe_bool(intent.get("operator_authorized"), False) or (
        _safe_bool(intent.get("operator_enable"), False) and _safe_bool(intent.get("operator_confirmation_ok"), False)
    )
    blocked_reasons: list[str] = []
    if not would_route:
        blocked_reasons.append("would_route_false")
    if not would_create_order:
        blocked_reasons.append("order_intent_not_creatable")
    if not operator_authorized:
        blocked_reasons.append("operator_not_authorized")
    if not payload_valid:
        blocked_reasons.extend([f"payload_{reason}" for reason in payload.get("payload_invalid_reasons", [])])
    if not settings.fail_closed:
        blocked_reasons.append("fail_closed_setting_disabled")

    would_create_paper_order = bool(would_route and would_create_order and operator_authorized and payload_valid and settings.fail_closed)
    if would_create_paper_order:
        blocked_reasons.append("paper_broker_submit_still_disabled")
    blocked_reason = "paper_broker_submit_still_disabled" if would_create_paper_order else (blocked_reasons[0] if blocked_reasons else "paper_broker_submit_still_disabled")
    return {
        "event_type": HANDOFF_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": str(payload.get("cycle_id") or ""),
        "symbol": str(payload.get("symbol") or ""),
        "timeframe": str(payload.get("timeframe") or ""),
        "side": str(payload.get("side") or ""),
        "order_type": str(payload.get("order_type") or ""),
        "profile_name": str(payload.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(payload.get("selected_overlay_id") or settings.selected_overlay_id),
        "source": "lsr_v2_order_intent",
        "source_event_type": str(intent.get("event_type") or ORDER_INTENT_EVENT_TYPE),
        "candidate_id": str(payload.get("candidate_id") or ""),
        "entry_price": _round(payload.get("entry_price")),
        "stop_loss": _round(payload.get("stop_loss")),
        "take_profit": _round(payload.get("take_profit")),
        "risk_per_trade_pct": _safe_float(payload.get("risk_per_trade_pct"), 0.0025),
        "risk_amount": _round(payload.get("risk_amount")),
        "position_size": _round(payload.get("position_size")),
        "quantity": _round(payload.get("quantity")),
        "notional": _round(payload.get("notional")),
        "max_positions": _safe_int(payload.get("max_positions"), 1),
        "duplicate_check": payload.get("duplicate_check"),
        "cadence_check": payload.get("cadence_check"),
        "payload": payload,
        "payload_valid": bool(payload_valid),
        "payload_invalid_reasons": list(payload.get("payload_invalid_reasons") or []),
        "would_route": bool(would_route),
        "would_create_order": bool(would_create_order),
        "would_create_paper_order": bool(would_create_paper_order),
        "would_submit": False,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "blocked_reason": blocked_reason,
        "blocked_reasons": blocked_reasons,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_lsr_v2_handoff": 0,
        "positions_opened_by_lsr_v2_handoff": 0,
        "orders_submitted_by_lsr_v2_order_intent": 0,
        "positions_opened_by_lsr_v2_order_intent": 0,
        "dry_run_only": True,
        "audit_only": True,
    }


def build_lsr_v2_paper_broker_handoff_events_from_intents(
    intents: Iterable[Mapping[str, Any]],
    *,
    settings: LSRV2PaperBrokerHandoffDryRunSettings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or LSRV2PaperBrokerHandoffDryRunSettings()
    rows = _dedupe_intents([dict(i) for i in intents])
    events: list[dict[str, Any]] = []
    for intent in rows:
        if not _safe_bool(intent.get("would_create_order"), False):
            continue
        events.append(build_lsr_v2_paper_broker_handoff_event(order_intent=intent, settings=settings))
    return events


def summarize_lsr_v2_paper_broker_handoff_dry_run(
    *,
    cycle_id: str,
    intents: Iterable[Mapping[str, Any]],
    handoff_events: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2PaperBrokerHandoffDryRunSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperBrokerHandoffDryRunSettings(data_dir=str(data_dir))
    metadata = dict(metadata or {})
    intent_rows = _dedupe_intents([dict(i) for i in intents])
    handoff_rows = [dict(e) for e in handoff_events]
    creatable_intents = [i for i in intent_rows if _safe_bool(i.get("would_create_order"), False)]
    valid_payloads = [e for e in handoff_rows if _safe_bool(e.get("payload_valid"), False)]
    paper_order_events = [e for e in handoff_rows if _safe_bool(e.get("would_create_paper_order"), False)]
    safety_checks = {
        "would_submit_zero": not any(_safe_bool(e.get("would_submit"), False) or _safe_bool(e.get("would_submit_to_paper_broker"), False) for e in handoff_rows),
        "broker_submit_called_false": not any(_safe_bool(e.get("broker_submit_called"), False) for e in handoff_rows),
        "orders_submitted_zero": sum(_safe_int(e.get("orders_submitted_by_lsr_v2_handoff"), 0) for e in handoff_rows) == 0,
        "positions_opened_zero": sum(_safe_int(e.get("positions_opened_by_lsr_v2_handoff"), 0) for e in handoff_rows) == 0,
        "routing_disabled": True,
        "execution_disabled": True,
        "paper_order_submission_disabled": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    if not intent_rows:
        decision = NO_INTENTS_DECISION
        status = "WARN"
    elif not creatable_intents:
        decision = NO_CREATE_DECISION
        status = "PASS" if safety_ok else "WARN"
    elif handoff_rows and len(valid_payloads) != len(handoff_rows):
        decision = INVALID_PAYLOAD_DECISION
        status = "WARN"
    elif safety_ok and paper_order_events:
        decision = READY_DECISION
        status = "PASS"
    else:
        decision = SAFETY_BLOCKED_DECISION
        status = "WARN"

    blockers: list[str] = []
    if not intent_rows:
        blockers.append("no_order_intents")
    if intent_rows and not creatable_intents:
        blockers.append("no_creatable_order_intents")
    if handoff_rows and len(valid_payloads) != len(handoff_rows):
        blockers.append("invalid_payload_fields")
    if not safety_ok:
        blockers.append("safety_invariant_failed")
    invalid_reasons: list[str] = []
    for event in handoff_rows:
        invalid_reasons.extend(str(r) for r in event.get("payload_invalid_reasons", []) if r)
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "PAPER_BROKER_HANDOFF_DRY_RUN",
            "PAYLOAD_SCHEMA_AUDIT",
            "SUBMIT_STILL_BLOCKED",
            "FAIL_CLOSED",
        ] + (["WOULD_CREATE_PAPER_ORDER_PRESENT"] if paper_order_events else ["NO_PAPER_ORDER_PAYLOAD_READY"]),
        "blockers": blockers,
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "order_intent_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_order_intent_events": _safe_int(metadata.get("historical_order_intent_events"), 0),
        "historical_would_create_order_events": _safe_int(metadata.get("historical_would_create_order_events"), 0),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "order_intent_events": len(intent_rows),
        "creatable_order_intents": len(creatable_intents),
        "handoff_dry_run_events": len(handoff_rows),
        "payload_valid_count": len(valid_payloads),
        "payload_invalid_count": len(handoff_rows) - len(valid_payloads),
        "would_create_paper_order_count": len(paper_order_events),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called_count": 0,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "total_risk_amount": round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in paper_order_events), 10),
        "total_notional": round(sum(_safe_float(e.get("notional"), 0.0) for e in paper_order_events), 10),
        "symbols": sorted({str(e.get("symbol") or "") for e in handoff_rows if e.get("symbol")}),
        "side_counts": {side: sum(1 for e in handoff_rows if str(e.get("side") or "") == side) for side in sorted({str(e.get("side") or "") for e in handoff_rows if e.get("side")})},
        "payload_invalid_reason_counts": {reason: invalid_reasons.count(reason) for reason in sorted(set(invalid_reasons))},
        "safety_checks": safety_checks,
        "safety_ok": bool(safety_ok),
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_lsr_v2_handoff": 0,
        "positions_opened_by_lsr_v2_handoff": 0,
        "promotion_ready": False,
        "audit_only": True,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


def write_lsr_v2_paper_broker_handoff_dry_run_artifacts(
    *,
    data_dir: str | Path,
    cycle_id: str,
    order_intents: Iterable[Mapping[str, Any]],
    settings: LSRV2PaperBrokerHandoffDryRunSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperBrokerHandoffDryRunSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    intents = [dict(i) for i in order_intents if not cycle_id or _event_cycle(i) == cycle_id]
    handoff_events = build_lsr_v2_paper_broker_handoff_events_from_intents(intents, settings=settings)
    _write_jsonl_replace(base / settings.jsonl_name, handoff_events)
    report = summarize_lsr_v2_paper_broker_handoff_dry_run(
        cycle_id=cycle_id,
        intents=intents,
        handoff_events=handoff_events,
        data_dir=base,
        settings=settings,
        metadata=metadata,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def build_lsr_v2_paper_broker_handoff_dry_run_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2PaperBrokerHandoffDryRunSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperBrokerHandoffDryRunSettings(data_dir=str(data_dir))
    selected_cycle_id, intents, metadata = select_cycle_scoped_order_intents(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    return write_lsr_v2_paper_broker_handoff_dry_run_artifacts(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        order_intents=intents,
        settings=settings,
        metadata=metadata,
    )
