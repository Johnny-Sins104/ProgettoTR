"""Prompt 29.4.4s-10ap — LSR-v2 third paper trade position lifecycle audit.

Consumes the third-trade submit-execution artifacts from 29.4.4s-10ao and
verifies that the paper broker state/status contain exactly one matching third
LSR-v2 paper position.  This is an audit-only lifecycle layer: it never submits
orders, never closes positions, never calls a broker, and never mutates
``paper_state.json`` or ``paper_status.json``.
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

# Local minimal helpers are duplicated here deliberately so this lifecycle audit
# remains importable in patch-only contexts where earlier third-trade modules may
# not be present.
EXECUTION_EVENT_TYPE = "LSR_V2_THIRD_TRADE_SUBMIT_EXECUTION"
EXECUTED_DECISION = "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED"
EXECUTION_JSONL_NAME = "lsr_v2_third_trade_submit_execution.jsonl"
EXECUTION_REPORT_NAME = "lsr_v2_third_trade_submit_execution_report.json"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _event_cycle(row: Mapping[str, Any]) -> str:
    return str(row.get("cycle_id") or row.get("lsr_v2_runtime_cycle_id") or "")


PROMPT_ID = "29.4.4s-10ap"
EVENT_TYPE = "LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE"
REPORT_NAME = "lsr_v2_third_trade_position_lifecycle_report.json"
JSONL_NAME = "lsr_v2_third_trade_position_lifecycle.jsonl"

READY_DECISION = "LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE_READY"
EXECUTION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_EXECUTION_NOT_FOUND"
POSITION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_POSITION_NOT_FOUND"
POSITION_CLOSED_AUDIT_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_POSITION_CLOSED_AUDIT_REQUIRED"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_STATE_INCONSISTENT"
REJECT_DECISION = "REJECT_LSR_V2_THIRD_POSITION_LIFECYCLE_SAFETY_FAILED"

THIRD_EXECUTION_SOURCE = "lsr_v2_third_trade_submit_execution"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class LSRV2ThirdTradePositionLifecycleSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    execution_report_name: str = EXECUTION_REPORT_NAME
    execution_jsonl_name: str = EXECUTION_JSONL_NAME
    max_event_lines: int = 50000
    mode: str = "paper"
    max_positions: int = 1
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _source_markers(row: Mapping[str, Any]) -> set[str]:
    meta = _as_mapping(row.get("metadata"))
    markers = {
        str(row.get("paper_order_source") or ""),
        str(row.get("execution_source") or ""),
        str(row.get("source") or ""),
        str(meta.get("paper_order_source") or ""),
        str(meta.get("execution_source") or ""),
        str(meta.get("source") or ""),
    }
    return {m for m in markers if m}


def _cycle_from_state_row(row: Mapping[str, Any]) -> str:
    meta = _as_mapping(row.get("metadata"))
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _candidate_from_state_row(row: Mapping[str, Any]) -> str:
    meta = _as_mapping(row.get("metadata"))
    return str(row.get("candidate_id") or meta.get("candidate_id") or "")


def _status_upper(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or default).upper()


def _is_open_position(row: Mapping[str, Any]) -> bool:
    status = _status_upper(row, "OPEN")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED"}:
        return False
    return _safe_bool(row.get("open"), status == "OPEN")


def _is_matching_third_lsr_v2_row(row: Mapping[str, Any], *, cycle_id: str, symbol: str = "", side: str = "") -> bool:
    markers = _source_markers(row)
    meta = _as_mapping(row.get("metadata"))
    has_source = THIRD_EXECUTION_SOURCE in markers or _safe_bool(meta.get("third_trade_single_order_gate"), False)
    if not has_source:
        return False
    if cycle_id and _cycle_from_state_row(row) != cycle_id:
        return False
    if symbol and str(row.get("symbol") or "") != symbol:
        return False
    if side and str(row.get("side") or "").upper() != side.upper():
        return False
    return True


def _order_open_or_pending(row: Mapping[str, Any]) -> bool:
    status = _status_upper(row)
    if _safe_bool(row.get("pending"), False) or _safe_bool(row.get("open"), False):
        return True
    return status == "PENDING"


def _read_state_and_status(data_dir: str | Path) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    base = Path(data_dir)
    return _read_json(base / "paper_state.json"), _read_json(base / "paper_status.json")


def _event_key(event: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(event.get("event_type") or ""),
        _event_cycle(event),
        str(event.get("symbol") or ""),
        str(event.get("candidate_id") or ""),
        str(event.get("timeframe") or ""),
    )


def _dedupe_execution_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in events:
        row = dict(raw)
        if row.get("event_type") != EXECUTION_EVENT_TYPE:
            continue
        key = _event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def select_third_trade_submit_execution_events(
    *,
    data_dir: str | Path,
    settings: LSRV2ThirdTradePositionLifecycleSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    settings = settings or LSRV2ThirdTradePositionLifecycleSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_execution_events(_iter_jsonl_tail(base / settings.execution_jsonl_name, max_lines=settings.max_event_lines))
    execution_report = _read_json(base / settings.execution_report_name)
    cycle_id = str(requested_cycle_id or execution_report.get("cycle_id") or "")
    if not cycle_id:
        for row in reversed(rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break
    scoped = [row for row in rows if not cycle_id or _event_cycle(row) == cycle_id]
    executed = [
        row for row in scoped
        if _safe_bool(row.get("order_submitted"), False)
        or _safe_int(row.get("orders_submitted_by_third_trade_execution"), 0) > 0
        or _safe_bool(row.get("broker_submit_called"), False)
    ]
    metadata = {
        "event_source": "third_trade_execution_jsonl" if rows else "third_trade_execution_report",
        "strict_cycle_scope": True,
        "historical_third_trade_execution_events": max(0, len(rows) - len(scoped)),
        "execution_report_present": bool(execution_report),
        "execution_report_decision": str(execution_report.get("decision") or ""),
        "execution_report_status": str(execution_report.get("status") or ""),
        "execution_report_ready": (
            execution_report.get("status") == "PASS"
            and execution_report.get("decision") == EXECUTED_DECISION
            and _safe_int(execution_report.get("orders_submitted_by_third_trade_execution"), 0) == 1
            and _safe_int(execution_report.get("positions_opened_by_third_trade_execution"), 0) == 1
        ),
        "execution_report_cycle_id": str(execution_report.get("cycle_id") or ""),
        "scoped_execution_events": len(scoped),
        "scoped_executed_events": len(executed),
    }
    return cycle_id, executed, metadata


def build_lsr_v2_third_trade_position_lifecycle_event(
    *,
    execution_event: Mapping[str, Any],
    state: Mapping[str, Any],
    status: Mapping[str, Any],
    settings: LSRV2ThirdTradePositionLifecycleSettings | None = None,
    index: int = 0,
) -> dict[str, Any]:
    settings = settings or LSRV2ThirdTradePositionLifecycleSettings()
    cycle_id = _event_cycle(execution_event)
    symbol = str(execution_event.get("symbol") or "")
    side = str(execution_event.get("side") or "").upper()
    orders = _as_mapping(state.get("orders"))
    positions = _as_mapping(state.get("positions"))

    matching_orders: list[tuple[str, Mapping[str, Any]]] = []
    for oid, raw in orders.items():
        row = _as_mapping(raw)
        if _is_matching_third_lsr_v2_row(row, cycle_id=cycle_id, symbol=symbol, side=side):
            matching_orders.append((str(oid), row))

    matching_positions: list[tuple[str, Mapping[str, Any]]] = []
    open_positions: list[tuple[str, Mapping[str, Any]]] = []
    closed_positions: list[tuple[str, Mapping[str, Any]]] = []
    for pid, raw in positions.items():
        row = _as_mapping(raw)
        if _is_matching_third_lsr_v2_row(row, cycle_id=cycle_id, symbol=symbol, side=side):
            matching_positions.append((str(pid), row))
            if _is_open_position(row):
                open_positions.append((str(pid), row))
            else:
                closed_positions.append((str(pid), row))

    all_open_lsr_v2_positions = [
        (str(pid), _as_mapping(raw))
        for pid, raw in positions.items()
        if _is_open_position(_as_mapping(raw))
        and (THIRD_EXECUTION_SOURCE in _source_markers(_as_mapping(raw)) or "lsr_v2" in " ".join(_source_markers(_as_mapping(raw))).lower())
    ]
    pending_orders = [
        (str(oid), _as_mapping(raw))
        for oid, raw in orders.items()
        if _order_open_or_pending(_as_mapping(raw))
    ]

    paper_status_open_positions = _safe_int(status.get("open_positions"), 0)
    paper_status_pending_orders = _safe_int(status.get("pending_orders"), 0)
    matching_order_count = len(matching_orders)
    matching_position_count = len(matching_positions)
    open_count = len(open_positions)
    closed_count = len(closed_positions)

    duplicate_position_check = matching_position_count <= 1
    max_positions_check = open_count <= int(settings.max_positions)
    paper_state_consistency = matching_order_count == 1 and matching_position_count == 1
    paper_status_consistency = paper_status_open_positions == open_count and paper_status_pending_orders == len(pending_orders)
    third_trade_position_open = open_count == 1
    fourth_submit_or_reentry_detected = len(pending_orders) > 0 or matching_order_count > 1 or matching_position_count > 1

    current_statuses = sorted({str(row.get("status") or row.get("state") or "UNKNOWN").upper() for _, row in matching_positions}) or ["UNKNOWN"]
    entry_prices = {str(row.get("symbol") or symbol): _safe_float(row.get("entry_price"), 0.0) for _, row in open_positions}
    stop_losses = {str(row.get("symbol") or symbol): _safe_float(row.get("stop_loss"), 0.0) for _, row in open_positions}
    take_profits = {str(row.get("symbol") or symbol): _safe_float(row.get("take_profit"), 0.0) for _, row in open_positions}

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": cycle_id,
        "source_event_type": str(execution_event.get("event_type") or EXECUTION_EVENT_TYPE),
        "symbol": symbol,
        "symbols": [symbol] if symbol else [],
        "side": side,
        "sides": [side] if side else [],
        "candidate_id": str(execution_event.get("candidate_id") or ""),
        "trade_ordinal": 3,
        "profile_name": str(execution_event.get("profile_name") or ""),
        "selected_overlay_id": str(execution_event.get("selected_overlay_id") or ""),
        "third_trade_execution_events": 1,
        "third_trade_position_open": third_trade_position_open,
        "matching_order_count": matching_order_count,
        "matching_position_count": matching_position_count,
        "open_lsr_v2_position_count": open_count,
        "closed_lsr_v2_position_count": closed_count,
        "active_lsr_v2_state_positions": open_count,
        "state_open_lsr_v2_positions": len(all_open_lsr_v2_positions),
        "state_pending_order_count": len(pending_orders),
        "paper_status_open_positions": paper_status_open_positions,
        "paper_status_pending_orders": paper_status_pending_orders,
        "paper_state_consistency": paper_state_consistency,
        "paper_status_consistency": paper_status_consistency,
        "duplicate_position_check": duplicate_position_check,
        "max_positions_check": max_positions_check,
        "pending_order_detected": len(pending_orders) > 0,
        "fourth_submit_or_reentry_detected": fourth_submit_or_reentry_detected,
        "current_statuses": current_statuses,
        "matching_order_ids": [oid for oid, _ in matching_orders],
        "matching_position_ids": [pid for pid, _ in matching_positions],
        "open_position_ids": [pid for pid, _ in open_positions],
        "entry_prices": entry_prices,
        "stop_losses": stop_losses,
        "take_profits": take_profits,
        "entry_price": _safe_float(execution_event.get("entry_price"), 0.0),
        "stop_loss": _safe_float(execution_event.get("stop_loss"), 0.0),
        "take_profit": _safe_float(execution_event.get("take_profit"), 0.0),
        "risk_per_trade_pct": _safe_float(execution_event.get("risk_per_trade_pct"), 0.0025),
        "total_risk_amount": _safe_float(execution_event.get("risk_amount"), 0.0),
        "total_notional": _safe_float(execution_event.get("notional"), 0.0),
        "orders_submitted_by_third_trade_lifecycle_audit": 0,
        "positions_opened_by_third_trade_lifecycle_audit": 0,
        "positions_closed_by_third_trade_lifecycle_audit": 0,
        "broker_submit_called_by_third_trade_lifecycle_audit": False,
        "broker_close_called_by_third_trade_lifecycle_audit": False,
        "paper_state_modified_by_third_trade_lifecycle_audit": False,
        "paper_status_modified_by_third_trade_lifecycle_audit": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "mode": str(settings.mode),
        "index": index,
    }


def build_lsr_v2_third_trade_position_lifecycle_report_from_files(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2ThirdTradePositionLifecycleSettings | None = None,
    requested_cycle_id: str = "",
) -> dict[str, Any]:
    settings = settings or LSRV2ThirdTradePositionLifecycleSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    state, status = _read_state_and_status(base)
    cycle_id, execution_events, metadata = select_third_trade_submit_execution_events(
        data_dir=base,
        settings=settings,
        requested_cycle_id=requested_cycle_id,
    )

    lifecycle_events = [
        build_lsr_v2_third_trade_position_lifecycle_event(
            execution_event=row,
            state=state,
            status=status,
            settings=settings,
            index=i,
        )
        for i, row in enumerate(execution_events)
    ]

    if not execution_events:
        decision = EXECUTION_NOT_FOUND_DECISION
        status_value = "WARN"
        blockers = ["third_trade_execution_event_missing"]
    else:
        blockers = []
        matching_order_count = sum(_safe_int(e.get("matching_order_count"), 0) for e in lifecycle_events)
        matching_position_count = sum(_safe_int(e.get("matching_position_count"), 0) for e in lifecycle_events)
        open_count = sum(_safe_int(e.get("open_lsr_v2_position_count"), 0) for e in lifecycle_events)
        closed_count = sum(_safe_int(e.get("closed_lsr_v2_position_count"), 0) for e in lifecycle_events)
        state_ok = all(_safe_bool(e.get("paper_state_consistency"), False) for e in lifecycle_events)
        status_ok = all(_safe_bool(e.get("paper_status_consistency"), False) for e in lifecycle_events)
        duplicate_ok = all(_safe_bool(e.get("duplicate_position_check"), False) for e in lifecycle_events)
        maxpos_ok = all(_safe_bool(e.get("max_positions_check"), False) for e in lifecycle_events)
        reentry = any(_safe_bool(e.get("fourth_submit_or_reentry_detected"), False) for e in lifecycle_events)

        if matching_position_count == 0 or matching_order_count == 0:
            decision = POSITION_NOT_FOUND_DECISION
            status_value = "WARN"
            blockers.append("third_trade_order_or_position_not_found")
        elif closed_count >= 1 and open_count == 0:
            decision = POSITION_CLOSED_AUDIT_REQUIRED_DECISION
            status_value = "WARN"
            blockers.append("third_trade_position_already_closed")
        elif not (state_ok and status_ok and duplicate_ok and maxpos_ok) or reentry:
            decision = STATE_INCONSISTENT_DECISION
            status_value = "WARN"
            if not state_ok:
                blockers.append("paper_state_inconsistent")
            if not status_ok:
                blockers.append("paper_status_inconsistent")
            if not duplicate_ok:
                blockers.append("duplicate_third_trade_position_detected")
            if not maxpos_ok:
                blockers.append("max_positions_check_failed")
            if reentry:
                blockers.append("fourth_submit_or_reentry_detected")
        else:
            decision = READY_DECISION
            status_value = "PASS"

    aggregate: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status_value,
        "decision": decision,
        "blockers": blockers,
        "classification_labels": [],
        "cycle_id": cycle_id,
        "event_source": metadata.get("event_source", "third_trade_execution_jsonl"),
        "strict_cycle_scope": True,
        "jsonl": str(base / settings.jsonl_name),
        "report": str(base / settings.report_name),
        "settings": settings.to_dict(),
        **metadata,
        "third_trade_execution_events": len(execution_events),
        "lifecycle_events": len(lifecycle_events),
        "matching_order_count": sum(_safe_int(e.get("matching_order_count"), 0) for e in lifecycle_events),
        "matching_position_count": sum(_safe_int(e.get("matching_position_count"), 0) for e in lifecycle_events),
        "open_lsr_v2_position_count": sum(_safe_int(e.get("open_lsr_v2_position_count"), 0) for e in lifecycle_events),
        "closed_lsr_v2_position_count": sum(_safe_int(e.get("closed_lsr_v2_position_count"), 0) for e in lifecycle_events),
        "active_lsr_v2_state_positions": sum(_safe_int(e.get("active_lsr_v2_state_positions"), 0) for e in lifecycle_events),
        "state_open_lsr_v2_positions": max([_safe_int(e.get("state_open_lsr_v2_positions"), 0) for e in lifecycle_events] or [0]),
        "state_pending_order_count": max([_safe_int(e.get("state_pending_order_count"), 0) for e in lifecycle_events] or [0]),
        "paper_status_open_positions": _safe_int(status.get("open_positions"), 0),
        "paper_status_pending_orders": _safe_int(status.get("pending_orders"), 0),
        "paper_state_consistency": all(_safe_bool(e.get("paper_state_consistency"), False) for e in lifecycle_events) if lifecycle_events else False,
        "paper_status_consistency": all(_safe_bool(e.get("paper_status_consistency"), False) for e in lifecycle_events) if lifecycle_events else False,
        "duplicate_position_check": all(_safe_bool(e.get("duplicate_position_check"), False) for e in lifecycle_events) if lifecycle_events else False,
        "max_positions_check": all(_safe_bool(e.get("max_positions_check"), False) for e in lifecycle_events) if lifecycle_events else False,
        "pending_order_detected": any(_safe_bool(e.get("pending_order_detected"), False) for e in lifecycle_events),
        "third_trade_position_open": any(_safe_bool(e.get("third_trade_position_open"), False) for e in lifecycle_events),
        "fourth_submit_or_reentry_detected": any(_safe_bool(e.get("fourth_submit_or_reentry_detected"), False) for e in lifecycle_events),
        "current_statuses": sorted({s for e in lifecycle_events for s in (e.get("current_statuses") or [])}) if lifecycle_events else ["UNKNOWN"],
        "symbols": sorted({s for e in lifecycle_events for s in (e.get("symbols") or [])}),
        "sides": sorted({s for e in lifecycle_events for s in (e.get("sides") or [])}),
        "total_notional": sum(_safe_float(e.get("total_notional"), 0.0) for e in lifecycle_events),
        "total_risk_amount": sum(_safe_float(e.get("total_risk_amount"), 0.0) for e in lifecycle_events),
        "orders_submitted_by_third_trade_lifecycle_audit": 0,
        "positions_opened_by_third_trade_lifecycle_audit": 0,
        "positions_closed_by_third_trade_lifecycle_audit": 0,
        "broker_submit_called_by_third_trade_lifecycle_audit": False,
        "broker_close_called_by_third_trade_lifecycle_audit": False,
        "paper_state_modified_by_third_trade_lifecycle_audit": False,
        "paper_status_modified_by_third_trade_lifecycle_audit": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "next_step": "third_open_position_monitor" if decision == READY_DECISION else "resolve_lifecycle_blockers_or_closed_audit",
    }

    if decision == READY_DECISION:
        aggregate["classification_labels"] = [
            "THIRD_TRADE_POSITION_LIFECYCLE_READY",
            "THIRD_POSITION_OPEN",
            "NO_FOURTH_REENTRY_DETECTED",
            "PAPER_STATE_STATUS_CONSISTENT",
        ]
    elif decision == POSITION_CLOSED_AUDIT_REQUIRED_DECISION:
        aggregate["classification_labels"] = ["THIRD_POSITION_CLOSED_AUDIT_REQUIRED"]
    else:
        aggregate["classification_labels"] = ["KEEP_DIAGNOSTIC_THIRD_POSITION_LIFECYCLE"]

    _write_json(base / settings.report_name, aggregate)
    _write_jsonl_replace(base / settings.jsonl_name, lifecycle_events)
    return aggregate


__all__ = [
    "EVENT_TYPE",
    "JSONL_NAME",
    "REPORT_NAME",
    "READY_DECISION",
    "LSRV2ThirdTradePositionLifecycleSettings",
    "build_lsr_v2_third_trade_position_lifecycle_event",
    "build_lsr_v2_third_trade_position_lifecycle_report_from_files",
    "select_third_trade_submit_execution_events",
]
