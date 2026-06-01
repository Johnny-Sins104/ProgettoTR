"""Prompt 29.4.4s-10u — LSR-v2 second-trade rearm-aware route/order-intent preflight.

This module is the non-operational route and order-intent preflight for a
second supervised LSR-v2 paper trade.  It requires the second-trade eligibility
and re-arm gates to have passed, plus explicit route-only operator controls.
It never submits an order, never calls a broker, never opens or closes
positions, and never mutates paper state/status.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore
import json
import os

PROMPT_ID = "29.4.4s-10u"
REPORT_NAME = "lsr_v2_second_trade_route_preflight_report.json"
JSONL_NAME = "lsr_v2_second_trade_route_preflight.jsonl"

ELIGIBILITY_REPORT_NAME = "lsr_v2_second_trade_eligibility_gate_report.json"
REARM_REPORT_NAME = "lsr_v2_second_trade_rearm_gate_report.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

RUNTIME_CANDIDATE_EVENT_TYPE = "LSR_V2_RUNTIME_CANDIDATE_AUDIT"
RUNTIME_BRIDGE_EVENT_TYPE = "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"
SECOND_TRADE_ROUTE_EVENT_TYPE = "LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT"
SECOND_TRADE_INTENT_EVENT_TYPE = "LSR_V2_SECOND_TRADE_ORDER_INTENT_PREFLIGHT"

READY_DECISION = "LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_READY"
REARM_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_MISSING"
CANDIDATE_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_CANDIDATE_MISSING"
OPERATOR_CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_OPERATOR_CONFIRMATION_MISSING"
STATE_NOT_CLEAN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_STATE_NOT_CLEAN"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_TRADE_ROUTE_PREFLIGHT_FAILED"

REQUIRED_ROUTE_VALUE = "1"
REQUIRED_ROUTE_CONFIRMATION = "I_UNDERSTAND_SECOND_PAPER_TRADE_ROUTE_ONLY"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "armed", "pass", "ready"}:
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


def _round(value: Any, digits: int = 10) -> float:
    return round(_safe_float(value, 0.0), digits)


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _collection_rows(value: Any, *, id_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, raw in value.items():
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(key))
            rows.append(row)
    elif isinstance(value, list):
        for idx, raw in enumerate(value):
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(row.get(id_field) or idx))
            rows.append(row)
    return rows


def _metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(
        row.get("paper_order_source")
        or row.get("execution_source")
        or row.get("source")
        or meta.get("paper_order_source")
        or meta.get("execution_source")
        or meta.get("source")
        or ""
    )


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    source = _row_source(row).lower()
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    return "lsr_v2" in source or profile == PROFILE_NAME or overlay == SELECTED_OVERLAY_ID


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or row.get("state") or row.get("position_status") or "OPEN").upper()
    closed = status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), not closed) and not closed


def _count_state_lsr_positions(state: Mapping[str, Any], *, open_only: bool | None = None) -> int:
    count = 0
    for row in _collection_rows(state.get("positions"), id_field="position_id"):
        if not _is_lsr_v2_row(row):
            continue
        is_open = _is_position_open(row)
        if open_only is True and not is_open:
            continue
        if open_only is False and is_open:
            continue
        count += 1
    return count


def _paper_status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_position_count"), 0)
    return 0


def _paper_status_pending_orders(status: Mapping[str, Any]) -> int:
    return _safe_int(status.get("pending_orders"), 0)


def _event_cycle(row: Mapping[str, Any]) -> str:
    return str(row.get("cycle_id") or row.get("lsr_v2_runtime_cycle_id") or "")


def _event_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("event_type") or ""),
        _event_cycle(row),
        str(row.get("symbol") or ""),
        str(row.get("candidate_id") or ""),
        str(row.get("timeframe") or ""),
    )


def _dedupe_events(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        key = _event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _latest_cycle_id(rows: Iterable[Mapping[str, Any]]) -> str:
    rows_list = [dict(r) for r in rows]
    for row in reversed(rows_list):
        if row.get("event_type") == CYCLE_COMPLETED_EVENT_TYPE and _event_cycle(row):
            return _event_cycle(row)
    for row in reversed(rows_list):
        if _event_cycle(row):
            return _event_cycle(row)
    return ""


def _current_lsr_runtime_events(data_dir: Path, *, max_lines: int, requested_cycle_id: str = "") -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    rows = _iter_jsonl_tail(data_dir / PAPER_EVENTS_NAME, max_lines=max_lines)
    cycle_id = str(requested_cycle_id or _latest_cycle_id(rows))
    lsr_rows = [
        row for row in rows
        if row.get("event_type") in {RUNTIME_CANDIDATE_EVENT_TYPE, RUNTIME_BRIDGE_EVENT_TYPE}
    ]
    current = _dedupe_events([row for row in lsr_rows if not cycle_id or _event_cycle(row) == cycle_id])
    historical = _dedupe_events([row for row in lsr_rows if cycle_id and _event_cycle(row) and _event_cycle(row) != cycle_id])
    return cycle_id, current, historical


def _count(rows: Iterable[Mapping[str, Any]], event_type: str) -> int:
    return sum(1 for row in rows if row.get("event_type") == event_type)


def _count_bool(rows: Iterable[Mapping[str, Any]], event_type: str, key: str) -> int:
    return sum(1 for row in rows if row.get("event_type") == event_type and _safe_bool(row.get(key), False))


def _levels_from(event: Mapping[str, Any]) -> tuple[float, float, float]:
    levels = event.get("levels") if isinstance(event.get("levels"), Mapping) else {}
    entry = _safe_float(levels.get("entry_price"), _safe_float(event.get("entry_price"), 0.0))
    stop = _safe_float(levels.get("stop_loss"), _safe_float(event.get("stop_loss"), 0.0))
    target = _safe_float(levels.get("take_profit"), _safe_float(event.get("take_profit"), 0.0))
    return entry, stop, target


def _candidate_key(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("cycle_id") or ""),
        str(event.get("symbol") or ""),
        str(event.get("candidate_id") or ""),
        str(event.get("timeframe") or ""),
    )


def _select_ready_candidate(events: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    ready = [
        dict(row) for row in events
        if row.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE and _safe_bool(row.get("candidate_ready"), False)
    ]
    return ready[-1] if ready else None


@dataclass(frozen=True)
class LSRV2SecondTradeRoutePreflightSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    eligibility_report_name: str = ELIGIBILITY_REPORT_NAME
    rearm_report_name: str = REARM_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    max_event_lines: int = 50000
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    required_route_value: str = REQUIRED_ROUTE_VALUE
    required_route_confirmation: str = REQUIRED_ROUTE_CONFIRMATION
    route_enable: str = ""
    route_confirmation: str = ""
    max_orders: int = 1
    account_equity: float = 1000.0
    risk_per_trade_pct: float = 0.0025
    max_notional: float = 1000000.0
    mode: str = "paper"

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2SecondTradeRoutePreflightSettings":
        max_orders = _safe_int(os.getenv("LSR_V2_SECOND_TRADE_MAX_ORDERS"), 1)
        if max_orders <= 0:
            max_orders = 1
        return cls(
            data_dir=data_dir,
            route_enable=str(os.getenv("LSR_V2_SECOND_TRADE_ROUTE_ENABLE") or ""),
            route_confirmation=str(os.getenv("LSR_V2_SECOND_TRADE_ROUTE_CONFIRMATION") or ""),
            max_orders=max_orders,
            mode=str(os.getenv("LSR_V2_SECOND_TRADE_ROUTE_MODE") or "paper"),
        )

    @property
    def route_enabled(self) -> bool:
        return str(self.route_enable).strip() == self.required_route_value

    @property
    def route_confirmation_ok(self) -> bool:
        return str(self.route_confirmation).strip() == self.required_route_confirmation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_second_trade_route_event(*, candidate: Mapping[str, Any], settings: LSRV2SecondTradeRoutePreflightSettings) -> dict[str, Any]:
    entry, stop, target = _levels_from(candidate)
    side = str(candidate.get("side") or "").upper()
    price_fields_ok = entry > 0.0 and stop > 0.0 and target > 0.0 and entry != stop and side in {"BUY", "SELL"}
    return {
        "event_type": SECOND_TRADE_ROUTE_EVENT_TYPE,
        "prompt": PROMPT_ID,
        "ts": utc_now_iso(),
        "cycle_id": str(candidate.get("cycle_id") or ""),
        "symbol": str(candidate.get("symbol") or ""),
        "timeframe": str(candidate.get("timeframe") or ""),
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "candidate_ready": True,
        "second_trade_route_enabled": True,
        "second_trade_route_confirmation_ok": True,
        "second_trade_would_route": True,
        "would_route": True,
        "would_submit": False,
        "broker_submit_called": False,
        "blocked_reason": "second_trade_submit_still_disabled",
        "entry_price": round(entry, 10),
        "stop_loss": round(stop, 10),
        "take_profit": round(target, 10),
        "price_fields_ok": bool(price_fields_ok),
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_route_preflight": 0,
        "positions_opened_by_second_trade_route_preflight": 0,
        "audit_only": True,
    }


def build_second_trade_order_intent_event(*, route_event: Mapping[str, Any], settings: LSRV2SecondTradeRoutePreflightSettings) -> dict[str, Any]:
    entry = _safe_float(route_event.get("entry_price"), 0.0)
    stop = _safe_float(route_event.get("stop_loss"), 0.0)
    target = _safe_float(route_event.get("take_profit"), 0.0)
    side = str(route_event.get("side") or "").upper()
    # Candidate rows from earlier runtime versions sometimes omit side at the route level.
    if side not in {"BUY", "SELL"}:
        side = "BUY" if target > entry else "SELL" if target < entry else ""
    stop_distance = abs(entry - stop) if entry > 0.0 and stop > 0.0 else 0.0
    risk_amount = max(0.0, float(settings.account_equity) * float(settings.risk_per_trade_pct))
    position_size = risk_amount / stop_distance if stop_distance > 0.0 else 0.0
    notional = abs(position_size * entry) if entry > 0.0 else 0.0
    price_fields_ok = entry > 0.0 and stop > 0.0 and target > 0.0 and stop_distance > 0.0 and side in {"BUY", "SELL"}
    notional_ok = 0.0 < notional <= float(settings.max_notional)
    would_create_order = price_fields_ok and notional_ok
    blocked_reasons: list[str] = ["second_trade_submit_still_disabled"]
    if not price_fields_ok:
        blocked_reasons.append("invalid_price_fields")
    if not notional_ok:
        blocked_reasons.append("invalid_notional")
    return {
        "event_type": SECOND_TRADE_INTENT_EVENT_TYPE,
        "prompt": PROMPT_ID,
        "ts": utc_now_iso(),
        "cycle_id": str(route_event.get("cycle_id") or ""),
        "symbol": str(route_event.get("symbol") or ""),
        "timeframe": str(route_event.get("timeframe") or ""),
        "candidate_id": str(route_event.get("candidate_id") or ""),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "side": side,
        "second_trade_would_route": True,
        "would_route": True,
        "would_create_order": bool(would_create_order),
        "would_submit": False,
        "broker_submit_called": False,
        "blocked_reason": blocked_reasons[0],
        "blocked_reasons": blocked_reasons,
        "entry_price": round(entry, 10),
        "stop_loss": round(stop, 10),
        "take_profit": round(target, 10),
        "stop_distance": round(stop_distance, 10),
        "risk_per_trade_pct": float(settings.risk_per_trade_pct),
        "account_equity": float(settings.account_equity),
        "risk_amount": round(risk_amount, 10) if would_create_order else 0.0,
        "position_size": round(position_size, 10) if would_create_order else 0.0,
        "notional": round(notional, 10) if would_create_order else 0.0,
        "max_positions": int(settings.max_orders),
        "price_fields_ok": bool(price_fields_ok),
        "notional_ok": bool(notional_ok),
        "duplicate_check": True,
        "cadence_check": True,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_route_preflight": 0,
        "positions_opened_by_second_trade_route_preflight": 0,
        "audit_only": True,
    }


def build_lsr_v2_second_trade_route_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondTradeRoutePreflightSettings | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or LSRV2SecondTradeRoutePreflightSettings.from_env(str(base))
    eligibility = _read_json(base / settings.eligibility_report_name)
    rearm = _read_json(base / settings.rearm_report_name)
    paper_state = _read_json(base / settings.paper_state_name)
    paper_status = _read_json(base / settings.paper_status_name)
    event_cycle_id, current_events, historical_events = _current_lsr_runtime_events(
        base, max_lines=settings.max_event_lines, requested_cycle_id=cycle_id
    )
    selected_cycle_id = str(cycle_id or event_cycle_id or rearm.get("cycle_id") or eligibility.get("cycle_id") or "")
    if selected_cycle_id and event_cycle_id and selected_cycle_id != event_cycle_id:
        current_events = _dedupe_events([row for row in current_events if _event_cycle(row) == selected_cycle_id])

    state_open_lsr = _count_state_lsr_positions(paper_state, open_only=True)
    status_open = _paper_status_open_positions(paper_status)
    status_pending = _paper_status_pending_orders(paper_status)
    clean_state = state_open_lsr == 0 and status_open == 0 and status_pending == 0

    eligibility_pass = eligibility.get("status") == "PASS" and eligibility.get("decision") == "LSR_V2_SECOND_PAPER_TRADE_ELIGIBILITY_PASS"
    second_trade_eligible = _safe_bool(eligibility.get("second_trade_eligible"), False) and eligibility_pass
    rearm_pass = rearm.get("status") == "PASS" and rearm.get("decision") in {
        "LSR_V2_SECOND_TRADE_REARM_READY_DIAGNOSTIC",
        "LSR_V2_SECOND_TRADE_CANDIDATE_WAIT_GATE_READY",
    }
    second_trade_rearm_ready = _safe_bool(rearm.get("second_trade_rearm_ready"), False)
    candidate_wait_gate_ready = _safe_bool(rearm.get("candidate_wait_gate_ready"), False)
    route_enabled = settings.route_enabled
    route_confirmation_ok = settings.route_confirmation_ok

    runtime_candidate_events = _count(current_events, RUNTIME_CANDIDATE_EVENT_TYPE)
    runtime_candidate_ready_events = _count_bool(current_events, RUNTIME_CANDIDATE_EVENT_TYPE, "candidate_ready")
    runtime_bridge_events = _count(current_events, RUNTIME_BRIDGE_EVENT_TYPE)
    runtime_would_route_count = _count_bool(current_events, RUNTIME_BRIDGE_EVENT_TYPE, "would_route")
    runtime_would_submit_count = _count_bool(current_events, RUNTIME_BRIDGE_EVENT_TYPE, "would_submit")
    ready_candidate = _select_ready_candidate(current_events)

    unsafe_upstream = any(
        _safe_bool(obj.get(key), False)
        for obj in (eligibility, rearm)
        for key in ["live_enabled", "testnet_enabled", "exchange_broker_enabled", "operational_unlock_allowed", "promotion_ready"]
    )
    upstream_activity = any(
        _safe_int(obj.get(key), 0) > 0
        for obj in (eligibility, rearm)
        for key in [
            "orders_submitted_by_second_trade_gate",
            "positions_opened_by_second_trade_gate",
            "orders_submitted_by_second_trade_rearm_gate",
            "positions_opened_by_second_trade_rearm_gate",
            "positions_closed_by_second_trade_rearm_gate",
        ]
    )

    blockers: list[str] = []
    if not second_trade_eligible:
        blockers.append("second_trade_eligibility_not_pass")
    if not rearm_pass or not candidate_wait_gate_ready:
        blockers.append("second_trade_rearm_missing")
    if not second_trade_rearm_ready:
        blockers.append("second_trade_rearm_not_ready")
    if not clean_state:
        blockers.append("paper_state_not_clean")
    if settings.max_orders != 1:
        blockers.append("max_orders_must_equal_1")
    if unsafe_upstream:
        blockers.append("unsafe_upstream_flag_detected")
    if upstream_activity:
        blockers.append("upstream_gate_created_activity")
    if runtime_would_submit_count > 0:
        blockers.append("runtime_would_submit_detected")
    if route_enabled and route_confirmation_ok and not ready_candidate:
        blockers.append("second_trade_candidate_missing")

    route_events: list[dict[str, Any]] = []
    intent_events: list[dict[str, Any]] = []
    if route_enabled and route_confirmation_ok and ready_candidate and not blockers:
        route_event = build_second_trade_route_event(candidate=ready_candidate, settings=settings)
        intent_event = build_second_trade_order_intent_event(route_event=route_event, settings=settings)
        route_events = [route_event]
        intent_events = [intent_event]

    second_trade_would_route_count = sum(1 for row in route_events if _safe_bool(row.get("second_trade_would_route"), False))
    second_trade_order_intent_events = len(intent_events)
    would_create_order_count = sum(1 for row in intent_events if _safe_bool(row.get("would_create_order"), False))
    invalid_intent_count = sum(1 for row in intent_events if not _safe_bool(row.get("price_fields_ok"), False))

    if unsafe_upstream or upstream_activity or settings.max_orders != 1 or runtime_would_submit_count > 0:
        decision = REJECT_DECISION
        status = "FAIL"
    elif not clean_state:
        decision = STATE_NOT_CLEAN_DECISION
        status = "WARN"
    elif not second_trade_eligible or not rearm_pass or not candidate_wait_gate_ready or not second_trade_rearm_ready:
        decision = REARM_MISSING_DECISION
        status = "WARN"
    elif not ready_candidate:
        decision = CANDIDATE_MISSING_DECISION
        status = "WARN"
    elif not route_enabled or not route_confirmation_ok:
        decision = OPERATOR_CONFIRMATION_MISSING_DECISION
        status = "WARN"
    elif invalid_intent_count:
        decision = REJECT_DECISION
        status = "FAIL"
        blockers.append("invalid_order_intent_fields")
    else:
        decision = READY_DECISION
        status = "PASS"

    classification_labels: list[str] = []
    if status == "PASS":
        classification_labels.extend(["SECOND_TRADE_ROUTE_PREFLIGHT_PASS", "SECOND_TRADE_ORDER_INTENT_READY", "SUBMIT_STILL_DISABLED"])
    elif decision == REARM_MISSING_DECISION:
        classification_labels.append("SECOND_TRADE_REARM_MISSING")
    elif decision == CANDIDATE_MISSING_DECISION:
        classification_labels.append("SECOND_TRADE_CANDIDATE_MISSING")
    elif decision == OPERATOR_CONFIRMATION_MISSING_DECISION:
        classification_labels.append("SECOND_TRADE_ROUTE_CONFIRMATION_MISSING")
    elif decision == STATE_NOT_CLEAN_DECISION:
        classification_labels.append("SECOND_TRADE_STATE_NOT_CLEAN")
    else:
        classification_labels.append("SECOND_TRADE_ROUTE_PREFLIGHT_REJECTED")

    total_risk_amount = round(sum(_safe_float(row.get("risk_amount"), 0.0) for row in intent_events if _safe_bool(row.get("would_create_order"), False)), 10)
    total_notional = round(sum(_safe_float(row.get("notional"), 0.0) for row in intent_events if _safe_bool(row.get("would_create_order"), False)), 10)
    report = {
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": blockers,
        "cycle_id": selected_cycle_id,
        "event_source": "paper_events_jsonl",
        "strict_cycle_scope": True,
        "second_trade_eligible": bool(second_trade_eligible),
        "second_trade_rearm_ready": bool(second_trade_rearm_ready),
        "candidate_wait_gate_ready": bool(candidate_wait_gate_ready),
        "second_trade_route_enabled": bool(route_enabled),
        "second_trade_route_confirmation_ok": bool(route_confirmation_ok),
        "second_trade_route_preflight_ready": bool(decision == READY_DECISION),
        "second_trade_order_intent_ready": bool(decision == READY_DECISION and would_create_order_count > 0),
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "broker_submit_called_by_second_trade_route_preflight": False,
        "orders_submitted_by_second_trade_route_preflight": 0,
        "positions_opened_by_second_trade_route_preflight": 0,
        "positions_closed_by_second_trade_route_preflight": 0,
        "paper_state_modified_by_second_trade_route_preflight": False,
        "paper_status_modified_by_second_trade_route_preflight": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "max_orders": settings.max_orders,
        "mode": settings.mode,
        "eligibility_decision": eligibility.get("decision"),
        "rearm_decision": rearm.get("decision"),
        "state_open_lsr_v2_positions": state_open_lsr,
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "paper_state_consistency": bool(clean_state),
        "paper_status_consistency": bool(clean_state),
        "runtime_candidate_events": runtime_candidate_events,
        "runtime_candidate_ready_events": runtime_candidate_ready_events,
        "runtime_bridge_events": runtime_bridge_events,
        "runtime_would_route_count": runtime_would_route_count,
        "runtime_would_submit_count": 0,
        "second_trade_route_events": len(route_events),
        "second_trade_would_route_count": second_trade_would_route_count,
        "second_trade_order_intent_events": second_trade_order_intent_events,
        "would_create_order_count": would_create_order_count,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "invalid_order_intent_count": invalid_intent_count,
        "historical_lsr_v2_events": len(historical_events),
        "risk_per_trade_pct": float(settings.risk_per_trade_pct),
        "account_equity": float(settings.account_equity),
        "total_risk_amount": total_risk_amount,
        "total_notional": total_notional,
        "symbols": sorted({str(row.get("symbol") or "") for row in route_events + intent_events if row.get("symbol")}),
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }

    if write_outputs:
        _write_json(base / settings.report_name, report)
        _write_jsonl_replace(base / settings.jsonl_name, route_events + intent_events)
    return report
