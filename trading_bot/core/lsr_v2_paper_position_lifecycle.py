"""Prompt 29.4.4s-10l — LSR-v2 paper position lifecycle audit.

Reads the first supervised paper-only LSR-v2 submit execution artifacts and the
active paper state/status files to verify that the submitted paper order is
visible as an auditable paper position.  This module never submits, closes,
re-enters, or mutates the broker state.  It only writes lifecycle audit reports.
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

PROMPT_ID = "29.4.4s-10l"
EVENT_TYPE = "LSR_V2_PAPER_POSITION_LIFECYCLE_AUDIT"
REPORT_NAME = "lsr_v2_paper_position_lifecycle_report.json"
JSONL_NAME = "lsr_v2_paper_position_lifecycle.jsonl"

EXECUTION_EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION"
EXECUTION_REPORT_NAME = "lsr_v2_supervised_paper_submit_execution_report.json"
EXECUTION_JSONL_NAME = "lsr_v2_supervised_paper_submit_execution.jsonl"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

READY_DECISION = "LSR_V2_PAPER_POSITION_LIFECYCLE_READY"
POSITION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_STATE_INCONSISTENT"
POSITION_OPEN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSITION_OPEN_MONITORING"
POSITION_CLOSED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSITION_CLOSED_AUDIT_REQUIRED"
REJECT_DECISION = "REJECT_LSR_V2_POSITION_LIFECYCLE_SAFETY_FAILED"

SOURCE_TAG = "lsr_v2_supervised_paper_submit_execution"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "armed", "open"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null", "closed", "cancelled"}:
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
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _payload_of(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _metadata_of(row: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata
    meta = row.get("meta")
    if isinstance(meta, Mapping):
        return meta
    return {}


def _event_cycle(row: Mapping[str, Any]) -> str:
    payload = _payload_of(row)
    meta = _metadata_of(row)
    return str(row.get("cycle_id") or payload.get("cycle_id") or meta.get("cycle_id") or "")


def _event_symbol(row: Mapping[str, Any]) -> str:
    payload = _payload_of(row)
    return str(row.get("symbol") or payload.get("symbol") or "")


def _event_side(row: Mapping[str, Any]) -> str:
    payload = _payload_of(row)
    return str(row.get("side") or payload.get("side") or "").upper()


def _event_order_id(row: Mapping[str, Any]) -> str:
    submit_result = row.get("submit_result")
    result = submit_result if isinstance(submit_result, Mapping) else {}
    payload = _payload_of(row)
    return str(row.get("order_id") or result.get("order_id") or payload.get("order_id") or "")


def _event_candidate_id(row: Mapping[str, Any]) -> str:
    payload = _payload_of(row)
    return str(row.get("candidate_id") or payload.get("candidate_id") or "")


def _execution_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        _event_cycle(row),
        _event_symbol(row),
        _event_side(row),
        _event_candidate_id(row),
        _event_order_id(row),
    )


def _dedupe_execution_events(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for item in rows:
        row = dict(item)
        if row.get("event_type") != EXECUTION_EVENT_TYPE:
            continue
        key = _execution_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _collection_rows(value: Any, *, id_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, raw in value.items():
            if isinstance(raw, Mapping):
                row = dict(raw)
            else:
                row = {"value": raw}
            row.setdefault(id_field, str(key))
            rows.append(row)
    elif isinstance(value, list):
        for idx, raw in enumerate(value):
            if isinstance(raw, Mapping):
                row = dict(raw)
            else:
                row = {"value": raw}
            row.setdefault(id_field, str(row.get(id_field) or idx))
            rows.append(row)
    return rows


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("order_status") or row.get("position_status") or default).upper()


def _is_order_active(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "FILLED")
    if status in {"NEW", "OPEN", "PENDING", "PLACED", "SUBMITTED", "ACCEPTED"}:
        return True
    return False


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(
        row.get("paper_order_source")
        or row.get("execution_source")
        or row.get("source")
        or meta.get("paper_order_source")
        or meta.get("execution_source")
        or meta.get("source")
        or ""
    )


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("symbol") or meta.get("symbol") or "")


def _row_side(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("side") or row.get("direction") or meta.get("side") or "").upper()


def _row_order_id(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("order_id") or row.get("id") or meta.get("order_id") or "")


def _row_position_id(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("position_id") or row.get("id") or meta.get("position_id") or "")


def _entry_price(row: Mapping[str, Any]) -> float:
    return _safe_float(row.get("entry_price") or row.get("entry") or row.get("price") or row.get("avg_entry_price"), 0.0)


def _position_size(row: Mapping[str, Any]) -> float:
    return _safe_float(row.get("position_size") or row.get("qty") or row.get("quantity") or row.get("size"), 0.0)


def _current_price(row: Mapping[str, Any], fallback: float = 0.0) -> float:
    return _safe_float(row.get("current_price") or row.get("mark_price") or row.get("last_price") or row.get("price"), fallback)


def _compute_unrealized_pnl(row: Mapping[str, Any]) -> float:
    direct = row.get("unrealized_pnl")
    if direct is not None:
        return _round(direct)
    entry = _entry_price(row)
    current = _current_price(row, entry)
    qty = _position_size(row)
    side = _row_side(row)
    if entry <= 0 or current <= 0 or qty <= 0:
        return 0.0
    if side == "SELL":
        return _round((entry - current) * qty)
    return _round((current - entry) * qty)


def _risk_multiple(row: Mapping[str, Any], fallback_risk_amount: float = 0.0) -> float | None:
    pnl = _compute_unrealized_pnl(row)
    risk_amount = _safe_float(row.get("risk_amount"), 0.0) or fallback_risk_amount
    if risk_amount <= 0:
        return None
    return _round(pnl / risk_amount)


def _distance_to_stop(row: Mapping[str, Any]) -> float | None:
    stop = _safe_float(row.get("stop_loss"), 0.0)
    current = _current_price(row, _entry_price(row))
    if stop <= 0 or current <= 0:
        return None
    return _round(abs(current - stop))


def _distance_to_take_profit(row: Mapping[str, Any]) -> float | None:
    take = _safe_float(row.get("take_profit"), 0.0)
    current = _current_price(row, _entry_price(row))
    if take <= 0 or current <= 0:
        return None
    return _round(abs(take - current))


@dataclass(frozen=True)
class LSRV2PaperPositionLifecycleSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    execution_report_name: str = EXECUTION_REPORT_NAME
    execution_jsonl_name: str = EXECUTION_JSONL_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    max_event_lines: int = 50000
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    max_positions: int = 1
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_cycle_scoped_execution_events(
    *,
    data_dir: str | Path,
    settings: LSRV2PaperPositionLifecycleSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    settings = settings or LSRV2PaperPositionLifecycleSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_execution_events(_iter_jsonl_tail(base / settings.execution_jsonl_name, max_lines=settings.max_event_lines))
    report = _read_json(base / settings.execution_report_name)
    paper_rows = _iter_jsonl_tail(base / settings.paper_events_name, max_lines=settings.max_event_lines)

    cycle_id = str(requested_cycle_id or report.get("cycle_id") or "")
    if not cycle_id:
        for row in reversed(rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break
    if not cycle_id:
        for row in reversed(paper_rows):
            cid = str(row.get("cycle_id") or row.get("lsr_v2_runtime_cycle_id") or "")
            if cid:
                cycle_id = cid
                break

    selected = [row for row in rows if not cycle_id or _event_cycle(row) == cycle_id]
    submitted = [row for row in selected if _safe_int(row.get("orders_submitted_by_lsr_v2_submit"), 0) > 0]
    # Execution report is a fallback if the JSONL is missing but reports a submit.
    if not submitted and str(report.get("cycle_id") or "") == cycle_id and _safe_int(report.get("orders_submitted_by_lsr_v2_execution"), 0) > 0:
        fallback = {
            "event_type": EXECUTION_EVENT_TYPE,
            "cycle_id": cycle_id,
            "symbol": report.get("symbol", ""),
            "side": report.get("side", ""),
            "profile_name": report.get("profile_name", settings.profile_name),
            "selected_overlay_id": report.get("selected_overlay_id", settings.selected_overlay_id),
            "order_submitted": True,
            "position_opened": _safe_int(report.get("positions_opened_by_lsr_v2_execution"), 0) > 0,
            "orders_submitted_by_lsr_v2_submit": _safe_int(report.get("orders_submitted_by_lsr_v2_execution"), 0),
            "positions_opened_by_lsr_v2_submit": _safe_int(report.get("positions_opened_by_lsr_v2_execution"), 0),
        }
        selected = [fallback]
        submitted = [fallback]

    historical = [row for row in rows if _event_cycle(row) and _event_cycle(row) != cycle_id]
    metadata = {
        "prompt_id": PROMPT_ID,
        "event_source": "execution_jsonl" if rows else "execution_report_json",
        "strict_cycle_scope": True,
        "execution_report_decision": report.get("decision"),
        "execution_report_cycle_id": report.get("cycle_id"),
        "historical_execution_events": len(historical),
        "historical_submitted_events": sum(1 for row in historical if _safe_int(row.get("orders_submitted_by_lsr_v2_submit"), 0) > 0),
        "paper_events_scanned": len(paper_rows),
    }
    return cycle_id, submitted, metadata


def find_matching_order(execution_event: Mapping[str, Any], orders: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    event_order_id = _event_order_id(execution_event)
    cycle_id = _event_cycle(execution_event)
    symbol = _event_symbol(execution_event)
    side = _event_side(execution_event)
    rows = [dict(o) for o in orders]
    if event_order_id:
        for order in rows:
            if _row_order_id(order) == event_order_id:
                return order
    scored: list[tuple[int, dict[str, Any]]] = []
    for order in rows:
        score = 0
        if cycle_id and _row_cycle(order) == cycle_id:
            score += 4
        if SOURCE_TAG in _row_source(order):
            score += 3
        if symbol and _row_symbol(order) == symbol:
            score += 2
        if side and _row_side(order) == side:
            score += 1
        if score >= 4:
            scored.append((score, order))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    return None


def find_matching_position(execution_event: Mapping[str, Any], positions: Iterable[Mapping[str, Any]], order: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    event_order_id = _event_order_id(execution_event)
    order_id = _row_order_id(order or {}) or event_order_id
    cycle_id = _event_cycle(execution_event)
    symbol = _event_symbol(execution_event) or _row_symbol(order or {})
    side = _event_side(execution_event) or _row_side(order or {})
    rows = [dict(p) for p in positions]
    if order_id:
        for pos in rows:
            meta = _metadata_of(pos)
            if str(pos.get("order_id") or meta.get("order_id") or "") == order_id:
                return pos
    scored: list[tuple[int, dict[str, Any]]] = []
    for pos in rows:
        score = 0
        if cycle_id and _row_cycle(pos) == cycle_id:
            score += 4
        if SOURCE_TAG in _row_source(pos):
            score += 3
        if symbol and _row_symbol(pos) == symbol:
            score += 2
        if side and _row_side(pos) == side:
            score += 1
        if score >= 4:
            scored.append((score, pos))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    return None


def build_lsr_v2_position_lifecycle_event(
    *,
    execution_event: Mapping[str, Any],
    order: Mapping[str, Any] | None,
    position: Mapping[str, Any] | None,
    settings: LSRV2PaperPositionLifecycleSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperPositionLifecycleSettings()
    payload = _payload_of(execution_event)
    order = dict(order or {})
    position = dict(position or {})
    position_open = bool(position and _is_position_open(position))
    entry = _entry_price(position) or _safe_float(execution_event.get("entry_price") or payload.get("entry_price"), 0.0)
    current = _current_price(position, entry)
    risk_amount = _safe_float(position.get("risk_amount"), 0.0) or _safe_float(execution_event.get("risk_amount") or payload.get("risk_amount"), 0.0)
    side = _row_side(position) or _row_side(order) or _event_side(execution_event)
    symbol = _row_symbol(position) or _row_symbol(order) or _event_symbol(execution_event)
    row = {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": _event_cycle(execution_event),
        "source_event_type": str(execution_event.get("event_type") or EXECUTION_EVENT_TYPE),
        "source": "lsr_v2_supervised_paper_submit_execution",
        "profile_name": str(execution_event.get("profile_name") or payload.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(execution_event.get("selected_overlay_id") or payload.get("selected_overlay_id") or settings.selected_overlay_id),
        "candidate_id": _event_candidate_id(execution_event),
        "order_id": _row_order_id(order) or _event_order_id(execution_event),
        "position_id": _row_position_id(position),
        "symbol": symbol,
        "side": side,
        "entry_price": _round(entry),
        "current_price": _round(current),
        "stop_loss": _round(position.get("stop_loss") or execution_event.get("stop_loss") or payload.get("stop_loss")),
        "take_profit": _round(position.get("take_profit") or execution_event.get("take_profit") or payload.get("take_profit")),
        "position_size": _round(_position_size(position) or execution_event.get("position_size") or payload.get("position_size")),
        "notional": _round(position.get("notional") or execution_event.get("notional") or payload.get("notional")),
        "risk_amount": _round(risk_amount),
        "risk_per_trade_pct": _safe_float(position.get("risk_per_trade_pct") or execution_event.get("risk_per_trade_pct") or payload.get("risk_per_trade_pct"), 0.0025),
        "order_found": bool(order),
        "position_found": bool(position),
        "position_open": bool(position_open),
        "current_status": _status_text(position, "OPEN" if position_open else "UNKNOWN"),
        "opened_at": str(position.get("opened_at") or position.get("created_at") or order.get("created_at") or execution_event.get("created_at") or ""),
        "unrealized_pnl": _compute_unrealized_pnl(position) if position else 0.0,
        "distance_to_stop": _distance_to_stop(position) if position else None,
        "distance_to_take_profit": _distance_to_take_profit(position) if position else None,
        "risk_multiple_current": _risk_multiple(position, risk_amount) if position else None,
        "duplicate_position_check": True,
        "max_positions_check": True,
        "paper_state_consistency": bool(order and position),
        "paper_status_consistency": True,
        "orders_submitted_by_lifecycle_audit": 0,
        "positions_opened_by_lifecycle_audit": 0,
        "broker_submit_called_by_lifecycle_audit": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
    }
    return row


def build_lsr_v2_paper_position_lifecycle_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2PaperPositionLifecycleSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperPositionLifecycleSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    selected_cycle_id, execution_events, metadata = select_cycle_scoped_execution_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    state = _read_json(base / settings.paper_state_name)
    status = _read_json(base / settings.paper_status_name)
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")

    lifecycle_events: list[dict[str, Any]] = []
    for event in execution_events:
        order = find_matching_order(event, orders)
        position = find_matching_position(event, positions, order=order)
        lifecycle_events.append(build_lsr_v2_position_lifecycle_event(
            execution_event=event,
            order=order,
            position=position,
            settings=settings,
        ))

    _write_jsonl_replace(base / settings.jsonl_name, lifecycle_events)
    report = summarize_lsr_v2_paper_position_lifecycle(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        execution_events=execution_events,
        lifecycle_events=lifecycle_events,
        state=state,
        status=status,
        orders=orders,
        positions=positions,
        metadata=metadata,
        settings=settings,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def summarize_lsr_v2_paper_position_lifecycle(
    *,
    data_dir: str | Path,
    cycle_id: str,
    execution_events: Iterable[Mapping[str, Any]],
    lifecycle_events: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
    status: Mapping[str, Any],
    orders: Iterable[Mapping[str, Any]],
    positions: Iterable[Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
    settings: LSRV2PaperPositionLifecycleSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperPositionLifecycleSettings(data_dir=str(data_dir))
    metadata = dict(metadata or {})
    exec_rows = [dict(e) for e in execution_events]
    rows = [dict(e) for e in lifecycle_events]
    order_rows = [dict(o) for o in orders]
    position_rows = [dict(p) for p in positions]
    matched_orders = [e for e in rows if _safe_bool(e.get("order_found"), False)]
    matched_positions = [e for e in rows if _safe_bool(e.get("position_found"), False)]
    open_rows = [e for e in rows if _safe_bool(e.get("position_open"), False)]
    closed_rows = [e for e in rows if _safe_bool(e.get("position_found"), False) and not _safe_bool(e.get("position_open"), False)]
    active_lsr_positions = [p for p in position_rows if _is_position_open(p) and (SOURCE_TAG in _row_source(p) or _row_cycle(p) == cycle_id)]
    active_lsr_orders = [o for o in order_rows if _is_order_active(o) and (SOURCE_TAG in _row_source(o) or _row_cycle(o) == cycle_id)]
    status_open_positions = _safe_int(status.get("open_positions"), 0)
    status_pending_orders = _safe_int(status.get("pending_orders"), 0)

    paper_state_consistency = bool(rows and len(matched_positions) == len(exec_rows) and len(matched_orders) == len(exec_rows))
    if not exec_rows:
        paper_state_consistency = False
    paper_status_consistency = True
    if "open_positions" in status and status_open_positions != len(active_lsr_positions):
        paper_status_consistency = False
    if "pending_orders" in status and status_pending_orders < len(active_lsr_orders):
        paper_status_consistency = False
    duplicate_position_check = len(active_lsr_positions) <= settings.max_positions
    max_positions_check = len(active_lsr_positions) <= settings.max_positions

    blockers: list[str] = []
    if not exec_rows:
        blockers.append("execution_event_not_found")
    if exec_rows and not matched_positions:
        blockers.append("matching_position_not_found")
    if exec_rows and not matched_orders:
        blockers.append("matching_order_not_found")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if not duplicate_position_check:
        blockers.append("duplicate_lsr_v2_positions_detected")
    if not max_positions_check:
        blockers.append("max_positions_exceeded")

    safety_violation = any(
        _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        or _safe_int(e.get("orders_submitted_by_lifecycle_audit"), 0) > 0
        or _safe_int(e.get("positions_opened_by_lifecycle_audit"), 0) > 0
        for e in rows
    )
    if safety_violation:
        blockers.append("lifecycle_safety_violation_detected")

    if safety_violation or not duplicate_position_check or not max_positions_check:
        decision = REJECT_DECISION
        status_text = "WARN"
    elif not exec_rows or (exec_rows and not matched_positions):
        decision = POSITION_NOT_FOUND_DECISION
        status_text = "WARN"
    elif not paper_state_consistency or not paper_status_consistency:
        decision = STATE_INCONSISTENT_DECISION
        status_text = "WARN"
    elif open_rows:
        decision = READY_DECISION
        status_text = "PASS"
    elif closed_rows:
        decision = POSITION_CLOSED_DECISION
        status_text = "WARN"
    else:
        decision = POSITION_NOT_FOUND_DECISION
        status_text = "WARN"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in rows), 10)
    safety_checks = {
        "no_new_order_by_lifecycle_audit": True,
        "no_new_position_by_lifecycle_audit": True,
        "no_broker_submit_by_lifecycle_audit": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
        "automatic_close_disabled": True,
        "automatic_reentry_disabled": True,
        "max_positions_check": bool(max_positions_check),
        "duplicate_position_check": bool(duplicate_position_check),
    }

    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_PAPER_POSITION_LIFECYCLE_AUDIT",
            "FIRST_ORDER_MONITORING",
        ] + (["POSITION_OPEN_MONITORING"] if open_rows else []) + (["KEEP_DIAGNOSTIC"] if decision != READY_DECISION else ["LIFECYCLE_READY"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "execution_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_execution_events": _safe_int(metadata.get("historical_execution_events"), 0),
        "execution_report_decision": metadata.get("execution_report_decision"),
        "execution_report_cycle_id": metadata.get("execution_report_cycle_id"),
        "execution_events": len(exec_rows),
        "lifecycle_events": len(rows),
        "matching_order_count": len(matched_orders),
        "matching_position_count": len(matched_positions),
        "open_lsr_v2_position_count": len(open_rows),
        "closed_lsr_v2_position_count": len(closed_rows),
        "active_lsr_v2_state_positions": len(active_lsr_positions),
        "active_lsr_v2_state_orders": len(active_lsr_orders),
        "paper_status_open_positions": status_open_positions,
        "paper_status_pending_orders": status_pending_orders,
        "duplicate_position_check": bool(duplicate_position_check),
        "max_positions_check": bool(max_positions_check),
        "paper_state_consistency": bool(paper_state_consistency),
        "paper_status_consistency": bool(paper_status_consistency),
        "current_statuses": sorted({str(e.get("current_status") or "") for e in rows if e.get("current_status")}),
        "symbols": sorted({str(e.get("symbol") or "") for e in rows if e.get("symbol")}),
        "sides": sorted({str(e.get("side") or "") for e in rows if e.get("side")}),
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "orders_submitted_by_lifecycle_audit": 0,
        "positions_opened_by_lifecycle_audit": 0,
        "broker_submit_called_by_lifecycle_audit": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "promotion_ready": False,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }
