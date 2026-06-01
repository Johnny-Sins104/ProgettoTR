"""Prompt 29.4.4s-10g — LSR-v2 paper order intent audit / submit preflight dry-run.

Builds a diagnostic paper-order intent from cycle-scoped LSR-v2 runtime bridge
rows that reached ``would_route=true``.  This module deliberately never submits
orders, never calls a broker, never opens positions and never mutates paper
state.  It is the pre-submit dry-run layer after the operator-controlled route
audit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

try:  # package import in the full project
    from .lsr_v2_runtime_bridge import (
        BRIDGE_EVENT_TYPE,
        RUNTIME_CANDIDATE_EVENT_TYPE,
        _dedupe_runtime_events,
        _filter_runtime_events_for_cycle,
        _iter_jsonl_tail,
        _read_json,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_runtime_bridge import (  # type: ignore
        BRIDGE_EVENT_TYPE,
        RUNTIME_CANDIDATE_EVENT_TYPE,
        _dedupe_runtime_events,
        _filter_runtime_events_for_cycle,
        _iter_jsonl_tail,
        _read_json,
    )

PROMPT_ID = "29.4.4s-10g"
ORDER_INTENT_EVENT_TYPE = "LSR_V2_PAPER_ORDER_INTENT_AUDIT"
ORDER_INTENT_REPORT_NAME = "lsr_v2_order_intent_audit_report.json"
ORDER_INTENT_JSONL_NAME = "lsr_v2_order_intent_audit.jsonl"
RUNTIME_JSONL_NAME = "lsr_v2_runtime_bridge_audit.jsonl"
PAPER_EVENTS_NAME = "paper_events.jsonl"
OPERATOR_ROUTE_REPORT_NAME = "lsr_v2_operator_route_audit_report.json"

READY_DECISION = "LSR_V2_ORDER_INTENT_AUDIT_READY_DIAGNOSTIC"
NO_ROUTE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_NO_WOULD_ROUTE"
NO_EVENTS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_NO_RUNTIME_EVENTS"
INVALID_LEVELS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_INVALID_LEVELS"
SAFETY_BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_SAFETY_BLOCKED"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ORDER_INTENT_ERROR"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


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


def _is_lsr_v2_runtime_event(event: Mapping[str, Any]) -> bool:
    event_type = event.get("event_type")
    if event_type == RUNTIME_CANDIDATE_EVENT_TYPE:
        return True
    return event_type == BRIDGE_EVENT_TYPE and bool(event.get("runtime_cycle_scoped", False))


def _latest_completed_cycle_from_paper_events(rows: Iterable[Mapping[str, Any]]) -> str:
    latest = ""
    for row in rows:
        if row.get("event_type") == "CYCLE_COMPLETED" and _event_cycle(row):
            latest = _event_cycle(row)
    return latest


def _latest_lsr_cycle_from_events(rows: Iterable[Mapping[str, Any]]) -> str:
    latest = ""
    for row in rows:
        if _is_lsr_v2_runtime_event(row) and _event_cycle(row):
            latest = _event_cycle(row)
    return latest


def _count_runtime_events(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    rows_list = [dict(r) for r in rows if _is_lsr_v2_runtime_event(r)]
    return {
        "events": len(rows_list),
        "candidate_events": sum(1 for r in rows_list if r.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE),
        "bridge_events": sum(1 for r in rows_list if r.get("event_type") == BRIDGE_EVENT_TYPE),
        "candidate_ready_events": sum(1 for r in rows_list if r.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE and _safe_bool(r.get("candidate_ready"), False)),
        "would_route_events": sum(1 for r in rows_list if r.get("event_type") == BRIDGE_EVENT_TYPE and _safe_bool(r.get("would_route"), False)),
    }


def _candidate_key(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("cycle_id") or ""),
        str(event.get("symbol") or ""),
        str(event.get("candidate_id") or ""),
        str(event.get("timeframe") or ""),
    )


def _levels_from(event: Mapping[str, Any]) -> tuple[float, float, float]:
    levels = event.get("levels") if isinstance(event.get("levels"), Mapping) else {}
    entry = _safe_float(levels.get("entry_price"), _safe_float(event.get("entry_price"), 0.0))
    stop = _safe_float(levels.get("stop_loss"), _safe_float(event.get("stop_loss"), 0.0))
    target = _safe_float(levels.get("take_profit"), _safe_float(event.get("take_profit"), 0.0))
    return entry, stop, target


@dataclass(frozen=True)
class LSRV2OrderIntentAuditSettings:
    data_dir: str = "data"
    events_name: str = PAPER_EVENTS_NAME
    runtime_jsonl_name: str = RUNTIME_JSONL_NAME
    operator_route_report_name: str = OPERATOR_ROUTE_REPORT_NAME
    report_name: str = ORDER_INTENT_REPORT_NAME
    jsonl_name: str = ORDER_INTENT_JSONL_NAME
    max_event_lines: int = 50000
    risk_per_trade_pct: float = 0.0025
    account_equity: float = 1000.0
    max_positions: int = 1
    max_notional: float = 1000000.0
    profile_name: str = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    selected_overlay_id: str = "combo_loss3_dd10_side_cap"
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_cycle_scoped_runtime_events(
    *,
    data_dir: str | Path,
    settings: LSRV2OrderIntentAuditSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Select strict cycle-scoped runtime events for intent construction.

    ``paper_events.jsonl`` is authoritative for the just-completed cycle. The
    runtime bridge JSONL is a de-duplicated fallback only.
    """
    settings = settings or LSRV2OrderIntentAuditSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    paper_events = _iter_jsonl_tail(base / settings.events_name, max_lines=settings.max_event_lines)
    runtime_events = _iter_jsonl_tail(base / settings.runtime_jsonl_name, max_lines=settings.max_event_lines)

    cycle_id = str(requested_cycle_id or "")
    if not cycle_id:
        cycle_id = _latest_completed_cycle_from_paper_events(paper_events)
    if not cycle_id:
        cycle_id = _latest_lsr_cycle_from_events(paper_events)
    if not cycle_id:
        cycle_id = _latest_lsr_cycle_from_events(runtime_events)

    paper_current = _filter_runtime_events_for_cycle(paper_events, cycle_id)
    runtime_current = _filter_runtime_events_for_cycle(runtime_events, cycle_id)
    if paper_current:
        selected = paper_current
        source = "paper_events_jsonl"
    else:
        selected = runtime_current
        source = "runtime_bridge_jsonl_fallback"

    historical_rows = [
        r for r in _dedupe_runtime_events([r for r in paper_events + runtime_events if _is_lsr_v2_runtime_event(r)])
        if _event_cycle(r) and _event_cycle(r) != cycle_id
    ]
    diagnostics = {
        "prompt_id": PROMPT_ID,
        "event_source": source,
        "strict_cycle_scope": True,
        "runtime_jsonl_deduplicated": True,
        "paper_events_current_cycle": _count_runtime_events(paper_current),
        "runtime_jsonl_current_cycle": _count_runtime_events(runtime_current),
        "historical_lsr_v2_events": len(historical_rows),
        "historical_lsr_v2_candidate_events": sum(1 for r in historical_rows if r.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE),
        "historical_lsr_v2_bridge_events": sum(1 for r in historical_rows if r.get("event_type") == BRIDGE_EVENT_TYPE),
    }
    return cycle_id, selected, diagnostics


def build_lsr_v2_order_intent_event(
    *,
    bridge_event: Mapping[str, Any],
    candidate_event: Mapping[str, Any] | None = None,
    settings: LSRV2OrderIntentAuditSettings | None = None,
) -> dict[str, Any]:
    """Build one fail-closed diagnostic paper-order intent from a route event."""
    settings = settings or LSRV2OrderIntentAuditSettings()
    candidate = dict(candidate_event or {})
    bridge = dict(bridge_event or {})
    source = candidate if candidate else bridge
    entry, stop, target = _levels_from(source)
    if entry <= 0.0 or stop <= 0.0 or target <= 0.0:
        entry2, stop2, target2 = _levels_from(bridge)
        entry = entry or entry2
        stop = stop or stop2
        target = target or target2
    side = str(bridge.get("side") or source.get("side") or "").upper()
    symbol = str(bridge.get("symbol") or source.get("symbol") or "")
    cycle_id = str(bridge.get("cycle_id") or source.get("cycle_id") or "")
    timeframe = str(bridge.get("timeframe") or source.get("timeframe") or "")
    candidate_id = str(bridge.get("candidate_id") or source.get("candidate_id") or "")
    stop_distance = abs(float(entry) - float(stop)) if entry > 0.0 and stop > 0.0 else 0.0
    risk_amount = max(0.0, float(settings.account_equity) * float(settings.risk_per_trade_pct))
    position_size = (risk_amount / stop_distance) if stop_distance > 0.0 else 0.0
    notional = position_size * entry if entry > 0.0 else 0.0
    price_fields_ok = bool(entry > 0.0 and stop > 0.0 and target > 0.0 and stop_distance > 0.0)
    side_ok = side in {"BUY", "SELL"}
    would_route = _safe_bool(bridge.get("would_route"), False)
    operator_authorized = _safe_bool(bridge.get("operator_authorized"), False) or (
        _safe_bool(bridge.get("operator_enable"), False) and _safe_bool(bridge.get("operator_confirmation_ok"), False)
    )
    candidate_ready = _safe_bool(bridge.get("candidate_ready"), _safe_bool(source.get("candidate_ready"), False))
    notional_ok = bool(notional <= float(settings.max_notional)) if notional > 0.0 else False
    duplicate_check = {
        "duplicate_key": "|".join([cycle_id, symbol, side, candidate_id]),
        "duplicate_found": False,
        "duplicate_blocked": False,
    }
    cadence_check = {
        "cadence_key": "|".join([symbol, timeframe, side]),
        "cadence_ok": True,
        "cadence_blocked": False,
    }
    blocked_reasons: list[str] = []
    if not would_route:
        blocked_reasons.append("would_route_false")
    if not operator_authorized:
        blocked_reasons.append("operator_not_authorized")
    if not candidate_ready:
        blocked_reasons.append("candidate_not_ready")
    if not side_ok:
        blocked_reasons.append("side_invalid")
    if not price_fields_ok:
        blocked_reasons.append("price_fields_invalid")
    if not notional_ok:
        blocked_reasons.append("notional_invalid_or_above_max")
    if not settings.fail_closed:
        blocked_reasons.append("fail_closed_setting_disabled")
    would_create_order = bool(
        would_route
        and operator_authorized
        and candidate_ready
        and side_ok
        and price_fields_ok
        and notional_ok
        and settings.fail_closed
    )
    if would_create_order:
        blocked_reasons.append("paper_order_submit_still_disabled")
    blocked_reason = "paper_order_submit_still_disabled" if would_create_order else (blocked_reasons[0] if blocked_reasons else "paper_order_submit_still_disabled")
    rr = 0.0
    if side == "BUY" and entry > 0.0 and stop > 0.0 and target > 0.0 and entry != stop:
        rr = (target - entry) / abs(entry - stop)
    elif side == "SELL" and entry > 0.0 and stop > 0.0 and target > 0.0 and entry != stop:
        rr = (entry - target) / abs(entry - stop)
    return {
        "event_type": ORDER_INTENT_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": cycle_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "side": side,
        "profile_name": str(bridge.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(bridge.get("selected_overlay_id") or settings.selected_overlay_id),
        "candidate_id": candidate_id,
        "candidate_ready": bool(candidate_ready),
        "operator_enable": bool(_safe_bool(bridge.get("operator_enable"), False)),
        "operator_confirmation_ok": bool(_safe_bool(bridge.get("operator_confirmation_ok"), False)),
        "operator_authorized": bool(operator_authorized),
        "would_route": bool(would_route),
        "would_create_order": bool(would_create_order),
        "would_submit": False,
        "broker_submit_called": False,
        "blocked_reason": blocked_reason,
        "blocked_reasons": blocked_reasons,
        "entry_price": round(float(entry), 10),
        "stop_loss": round(float(stop), 10),
        "take_profit": round(float(target), 10),
        "stop_distance": round(float(stop_distance), 10),
        "gross_rr": round(float(rr), 10),
        "risk_per_trade_pct": float(settings.risk_per_trade_pct),
        "account_equity": float(settings.account_equity),
        "risk_amount": round(float(risk_amount), 10),
        "position_size": round(float(position_size), 10),
        "notional": round(float(notional), 10),
        "max_positions": int(settings.max_positions),
        "duplicate_check": duplicate_check,
        "cadence_check": cadence_check,
        "price_fields_ok": bool(price_fields_ok),
        "notional_ok": bool(notional_ok),
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "orders_submitted_by_lsr_v2_order_intent": 0,
        "positions_opened_by_lsr_v2_order_intent": 0,
        "orders_submitted_by_lsr_v2_runtime_bridge": 0,
        "positions_opened_by_lsr_v2_runtime_bridge": 0,
        "audit_only": True,
    }


def build_lsr_v2_order_intents_from_events(
    events: Iterable[Mapping[str, Any]],
    *,
    settings: LSRV2OrderIntentAuditSettings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or LSRV2OrderIntentAuditSettings()
    rows = _dedupe_runtime_events([dict(e) for e in events if _is_lsr_v2_runtime_event(e)])
    candidates = [e for e in rows if e.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE]
    bridges = [e for e in rows if e.get("event_type") == BRIDGE_EVENT_TYPE and _safe_bool(e.get("runtime_cycle_scoped"), False)]
    candidate_by_key = {_candidate_key(c): c for c in candidates}
    candidate_by_symbol = {(str(c.get("cycle_id") or ""), str(c.get("symbol") or "")): c for c in candidates}
    intents: list[dict[str, Any]] = []
    for bridge in bridges:
        if not _safe_bool(bridge.get("would_route"), False):
            continue
        candidate = candidate_by_key.get(_candidate_key(bridge))
        if candidate is None:
            candidate = candidate_by_symbol.get((str(bridge.get("cycle_id") or ""), str(bridge.get("symbol") or "")))
        intents.append(build_lsr_v2_order_intent_event(bridge_event=bridge, candidate_event=candidate, settings=settings))
    return intents


def summarize_lsr_v2_order_intent_audit(
    *,
    cycle_id: str,
    events: Iterable[Mapping[str, Any]],
    intents: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2OrderIntentAuditSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2OrderIntentAuditSettings(data_dir=str(data_dir))
    metadata = dict(metadata or {})
    rows = _dedupe_runtime_events([dict(e) for e in events])
    bridge_events = [e for e in rows if e.get("event_type") == BRIDGE_EVENT_TYPE]
    candidate_events = [e for e in rows if e.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE]
    would_route_events = [e for e in bridge_events if _safe_bool(e.get("would_route"), False)]
    intent_rows = [dict(i) for i in intents]
    would_create_order_events = [i for i in intent_rows if _safe_bool(i.get("would_create_order"), False)]
    invalid_level_events = [i for i in intent_rows if not _safe_bool(i.get("price_fields_ok"), False)]
    safety_checks = {
        "would_submit_zero": not any(_safe_bool(i.get("would_submit"), False) for i in intent_rows),
        "broker_submit_called_false": not any(_safe_bool(i.get("broker_submit_called"), False) for i in intent_rows),
        "orders_submitted_zero": sum(_safe_int(i.get("orders_submitted_by_lsr_v2_order_intent"), 0) for i in intent_rows) == 0,
        "positions_opened_zero": sum(_safe_int(i.get("positions_opened_by_lsr_v2_order_intent"), 0) for i in intent_rows) == 0,
        "routing_disabled": True,
        "execution_disabled": True,
        "paper_order_submission_disabled": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    if not candidate_events and not bridge_events:
        decision = NO_EVENTS_DECISION
        status = "WARN"
    elif not would_route_events:
        decision = NO_ROUTE_DECISION
        status = "PASS" if safety_ok else "WARN"
    elif invalid_level_events and not would_create_order_events:
        decision = INVALID_LEVELS_DECISION
        status = "WARN"
    elif safety_ok and would_create_order_events:
        decision = READY_DECISION
        status = "PASS"
    else:
        decision = SAFETY_BLOCKED_DECISION
        status = "WARN"
    blockers: list[str] = []
    if not would_route_events:
        blockers.append("no_runtime_would_route_events")
    if invalid_level_events:
        blockers.append("invalid_price_fields")
    if not safety_ok:
        blockers.append("safety_invariant_failed")
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "ORDER_INTENT_AUDIT",
            "SUBMIT_STILL_BLOCKED",
            "FAIL_CLOSED",
        ] + (["WOULD_CREATE_ORDER_PRESENT"] if would_create_order_events else ["NO_ORDER_INTENT_READY"]),
        "blockers": blockers,
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "runtime_events"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_lsr_v2_events": _safe_int(metadata.get("historical_lsr_v2_events"), 0),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "runtime_candidate_events": len(candidate_events),
        "runtime_candidate_ready_events": sum(1 for e in candidate_events if _safe_bool(e.get("candidate_ready"), False)),
        "runtime_bridge_events": len(bridge_events),
        "would_route_count": len(would_route_events),
        "order_intent_events": len(intent_rows),
        "would_create_order_count": len(would_create_order_events),
        "would_submit_count": 0,
        "invalid_level_count": len(invalid_level_events),
        "risk_per_trade_pct": float(settings.risk_per_trade_pct),
        "account_equity": float(settings.account_equity),
        "max_positions": int(settings.max_positions),
        "total_risk_amount": round(sum(_safe_float(i.get("risk_amount"), 0.0) for i in would_create_order_events), 10),
        "total_notional": round(sum(_safe_float(i.get("notional"), 0.0) for i in would_create_order_events), 10),
        "symbols": sorted({str(i.get("symbol") or "") for i in intent_rows if i.get("symbol")}),
        "safety_checks": safety_checks,
        "safety_ok": bool(safety_ok),
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "orders_submitted_by_lsr_v2_order_intent": 0,
        "positions_opened_by_lsr_v2_order_intent": 0,
        "promotion_ready": False,
        "audit_only": True,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


def write_lsr_v2_order_intent_audit_artifacts(
    *,
    data_dir: str | Path,
    cycle_id: str,
    events: Iterable[Mapping[str, Any]],
    settings: LSRV2OrderIntentAuditSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2OrderIntentAuditSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    event_rows = _filter_runtime_events_for_cycle((dict(e) for e in events), cycle_id)
    intents = build_lsr_v2_order_intents_from_events(event_rows, settings=settings)
    _write_jsonl_replace(base / settings.jsonl_name, intents)
    report = summarize_lsr_v2_order_intent_audit(
        cycle_id=cycle_id,
        events=event_rows,
        intents=intents,
        data_dir=base,
        settings=settings,
        metadata=metadata,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def build_lsr_v2_order_intent_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2OrderIntentAuditSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2OrderIntentAuditSettings(data_dir=str(data_dir))
    selected_cycle_id, events, metadata = select_cycle_scoped_runtime_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    return write_lsr_v2_order_intent_audit_artifacts(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        events=events,
        settings=settings,
        metadata=metadata,
    )
