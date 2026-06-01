"""Prompt 29.4.4s-10aq — LSR-v2 third open paper-position monitor.

Read-only monitor for the third supervised LSR-v2 paper trade opened by
29.4.4s-10ao and verified by 29.4.4s-10ap.  It reads paper state/status,
third lifecycle/execution artifacts and paper events, then computes current
price, unrealized PnL, R multiple and SL/TP diagnostics.

The module never submits, closes, mutates paper_state/paper_status, calls a
broker, enables live/testnet/exchange execution, or performs automatic close.
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

PROMPT_ID = "29.4.4s-10aq"
EVENT_TYPE = "LSR_V2_THIRD_OPEN_POSITION_MONITOR"
REPORT_NAME = "lsr_v2_third_open_position_monitor_report.json"
JSONL_NAME = "lsr_v2_third_open_position_monitor.jsonl"

LIFECYCLE_REPORT_NAME = "lsr_v2_third_trade_position_lifecycle_report.json"
EXECUTION_REPORT_NAME = "lsr_v2_third_trade_submit_execution_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

READY_DECISION = "LSR_V2_THIRD_OPEN_POSITION_MONITOR_READY"
EXECUTION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_MONITOR_EXECUTION_NOT_FOUND"
POSITION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_MONITOR_POSITION_NOT_FOUND"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_MONITOR_STATE_INCONSISTENT"
CLOSE_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_CLOSE_REQUIRED_DIAGNOSTIC"
REJECT_DECISION = "REJECT_LSR_V2_THIRD_OPEN_POSITION_MONITOR_SAFETY_FAILED"

THIRD_EXECUTION_SOURCE = "lsr_v2_third_trade_submit_execution"
EXECUTED_DECISION = "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED"
LIFECYCLE_READY_DECISION = "LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE_READY"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "open", "pass", "ready"}:
        return True
    if text in {"0", "false", "no", "n", "off", "closed", "", "none", "null"}:
        return False
    return default


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
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return float(default)


def _round(value: Any, digits: int = 10) -> float:
    return round(_safe_float(value, 0.0), digits)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def _status_upper(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or default).upper()


def _is_open_position(row: Mapping[str, Any]) -> bool:
    status = _status_upper(row, "OPEN")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED"}:
        return False
    return _safe_bool(row.get("open"), status == "OPEN")


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


def _is_matching_third_lsr_v2_row(row: Mapping[str, Any], *, cycle_id: str = "", symbol: str = "", side: str = "") -> bool:
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


def _all_open_lsr_v2_positions(state: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    positions = _as_mapping(state.get("positions"))
    out: list[tuple[str, Mapping[str, Any]]] = []
    for pid, raw in positions.items():
        row = _as_mapping(raw)
        markers = " ".join(_source_markers(row)).lower()
        if _is_open_position(row) and ("lsr_v2" in markers or _safe_bool(_as_mapping(row.get("metadata")).get("third_trade_single_order_gate"), False)):
            out.append((str(pid), row))
    return out


def _pending_orders(state: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    orders = _as_mapping(state.get("orders"))
    out: list[tuple[str, Mapping[str, Any]]] = []
    for oid, raw in orders.items():
        row = _as_mapping(raw)
        status = _status_upper(row)
        if _safe_bool(row.get("pending"), False) or _safe_bool(row.get("open"), False) or status == "PENDING":
            out.append((str(oid), row))
    return out


def _latest_price_from_event(row: Mapping[str, Any], symbol: str) -> float:
    for key in ("current_price", "mark_price", "last_price", "price", "close"):
        value = _safe_float(row.get(key), 0.0)
        if value > 0:
            return value
    candle = _as_mapping(row.get("candle"))
    value = _safe_float(candle.get("close"), 0.0)
    if value > 0:
        return value
    levels = _as_mapping(row.get("levels"))
    value = _safe_float(levels.get("last_price"), 0.0)
    if value > 0:
        return value
    return 0.0


def _latest_symbol_price(data_dir: str | Path, symbol: str, *, max_lines: int = 50000) -> tuple[float, str, str]:
    rows = _iter_jsonl_tail(Path(data_dir) / PAPER_EVENTS_NAME, max_lines=max_lines)
    for row in reversed(rows):
        if str(row.get("symbol") or "") != symbol:
            continue
        price = _latest_price_from_event(row, symbol)
        if price > 0:
            return price, str(row.get("event_type") or ""), str(row.get("ts") or row.get("created_at") or "")
    return 0.0, "", ""


def _position_price(row: Mapping[str, Any], key: str) -> float:
    meta = _as_mapping(row.get("metadata"))
    for source in (row, meta):
        value = _safe_float(source.get(key), 0.0)
        if value > 0:
            return value
    return 0.0


def _position_qty(row: Mapping[str, Any]) -> float:
    meta = _as_mapping(row.get("metadata"))
    for key in ("quantity", "qty", "position_size", "size", "amount"):
        for source in (row, meta):
            value = _safe_float(source.get(key), 0.0)
            if value > 0:
                return value
    return 0.0


def _risk_amount(row: Mapping[str, Any], execution_report: Mapping[str, Any]) -> float:
    meta = _as_mapping(row.get("metadata"))
    for key in ("risk_amount", "total_risk_amount"):
        for source in (row, meta, execution_report):
            value = _safe_float(source.get(key), 0.0)
            if value > 0:
                return value
    return 0.0


def _notional(row: Mapping[str, Any], execution_report: Mapping[str, Any], entry: float, qty: float) -> float:
    meta = _as_mapping(row.get("metadata"))
    for key in ("notional", "total_notional"):
        for source in (row, meta, execution_report):
            value = _safe_float(source.get(key), 0.0)
            if value > 0:
                return value
    return entry * qty if entry > 0 and qty > 0 else 0.0


def _directional_pnl(side: str, entry: float, current: float, qty: float) -> float:
    if entry <= 0 or current <= 0 or qty <= 0:
        return 0.0
    if side.upper() == "SELL":
        return (entry - current) * qty
    return (current - entry) * qty


def _risk_multiple(side: str, entry: float, current: float, stop: float) -> float:
    if entry <= 0 or current <= 0 or stop <= 0:
        return 0.0
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0:
        return 0.0
    if side.upper() == "SELL":
        return (entry - current) / risk_per_unit
    return (current - entry) / risk_per_unit


def _distance_pct(current: float, target: float) -> float | None:
    if current <= 0 or target <= 0:
        return None
    return abs(current - target) / current * 100.0


def _tp_hit(side: str, current: float, take: float) -> bool:
    if current <= 0 or take <= 0:
        return False
    return current <= take if side.upper() == "SELL" else current >= take


def _sl_hit(side: str, current: float, stop: float) -> bool:
    if current <= 0 or stop <= 0:
        return False
    return current >= stop if side.upper() == "SELL" else current <= stop


@dataclass(frozen=True)
class LSRV2ThirdOpenPositionMonitorSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    lifecycle_report_name: str = LIFECYCLE_REPORT_NAME
    execution_report_name: str = EXECUTION_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    max_event_lines: int = 50000
    mode: str = "paper"
    max_positions: int = 1
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _select_open_third_position(
    *,
    state: Mapping[str, Any],
    lifecycle_report: Mapping[str, Any],
    execution_report: Mapping[str, Any],
    requested_cycle_id: str = "",
) -> tuple[str, list[tuple[str, Mapping[str, Any]]]]:
    cycle_id = str(requested_cycle_id or lifecycle_report.get("cycle_id") or execution_report.get("cycle_id") or "")
    symbol = ""
    side = ""
    symbols = lifecycle_report.get("symbols") if isinstance(lifecycle_report.get("symbols"), list) else []
    sides = lifecycle_report.get("sides") if isinstance(lifecycle_report.get("sides"), list) else []
    if symbols:
        symbol = str(symbols[0] or "")
    if sides:
        side = str(sides[0] or "")
    if not symbol:
        symbol = str(execution_report.get("symbol") or "")
    if not side:
        side = str(execution_report.get("side") or "")

    matches: list[tuple[str, Mapping[str, Any]]] = []
    for pid, raw in _as_mapping(state.get("positions")).items():
        row = _as_mapping(raw)
        if _is_open_position(row) and _is_matching_third_lsr_v2_row(row, cycle_id=cycle_id, symbol=symbol, side=side):
            matches.append((str(pid), row))
    # Fallback: if symbol/side metadata was not preserved, use source+cycle only.
    if not matches:
        for pid, raw in _as_mapping(state.get("positions")).items():
            row = _as_mapping(raw)
            if _is_open_position(row) and _is_matching_third_lsr_v2_row(row, cycle_id=cycle_id):
                matches.append((str(pid), row))
    return cycle_id, matches


def build_lsr_v2_third_open_position_monitor_event(
    *,
    position_id: str,
    position: Mapping[str, Any],
    data_dir: str | Path,
    lifecycle_report: Mapping[str, Any],
    execution_report: Mapping[str, Any],
    status: Mapping[str, Any],
    settings: LSRV2ThirdOpenPositionMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2ThirdOpenPositionMonitorSettings(data_dir=str(data_dir))
    cycle_id = _cycle_from_state_row(position) or str(lifecycle_report.get("cycle_id") or execution_report.get("cycle_id") or "")
    symbol = str(position.get("symbol") or execution_report.get("symbol") or "")
    side = str(position.get("side") or execution_report.get("side") or "BUY").upper()
    entry = _position_price(position, "entry_price") or _safe_float(execution_report.get("entry_price"), 0.0)
    stop = _position_price(position, "stop_loss") or _safe_float(execution_report.get("stop_loss"), 0.0)
    take = _position_price(position, "take_profit") or _safe_float(execution_report.get("take_profit"), 0.0)
    qty = _position_qty(position) or _safe_float(execution_report.get("position_size"), 0.0) or _safe_float(execution_report.get("quantity"), 0.0)
    current = _position_price(position, "current_price") or _position_price(position, "mark_price") or _position_price(position, "last_price")
    price_source = "paper_state_position"
    price_ts = ""
    if current <= 0:
        current, price_event_type, price_ts = _latest_symbol_price(settings.data_dir, symbol, max_lines=settings.max_event_lines)
        price_source = f"paper_events_jsonl:{price_event_type}" if current > 0 else "entry_price_fallback"
    if current <= 0:
        current = entry
    risk_amount = _risk_amount(position, execution_report)
    notional = _notional(position, execution_report, entry, qty)
    pnl = _directional_pnl(side, entry, current, qty)
    # Prefer price-derived R for SL/TP accuracy; keep risk amount available separately.
    r_current = _risk_multiple(side, entry, current, stop)
    stop_hit = _sl_hit(side, current, stop)
    take_hit = _tp_hit(side, current, take)
    close_required = stop_hit or take_hit
    dist_sl = _distance_pct(current, stop)
    dist_tp = _distance_pct(current, take)
    paper_status_open_positions = _safe_int(status.get("open_positions"), 0)
    paper_status_pending_orders = _safe_int(status.get("pending_orders"), 0)

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": cycle_id,
        "source_event_type": "LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE",
        "position_id": str(position_id),
        "candidate_id": _candidate_from_state_row(position) or str(execution_report.get("candidate_id") or ""),
        "trade_ordinal": 3,
        "symbol": symbol,
        "symbols": [symbol] if symbol else [],
        "side": side,
        "sides": [side] if side else [],
        "position_open": True,
        "third_trade_position_open": True,
        "current_status": _status_upper(position, "OPEN"),
        "current_statuses": [_status_upper(position, "OPEN")],
        "entry_price": _round(entry),
        "current_price": _round(current),
        "stop_loss": _round(stop),
        "take_profit": _round(take),
        "entry_prices": {symbol: _round(entry)} if symbol else {},
        "current_prices": {symbol: _round(current)} if symbol else {},
        "stop_losses": {symbol: _round(stop)} if symbol else {},
        "take_profits": {symbol: _round(take)} if symbol else {},
        "quantity": _round(qty),
        "position_size": _round(qty),
        "notional": _round(notional),
        "risk_amount": _round(risk_amount),
        "unrealized_pnl": _round(pnl),
        "unrealized_pnl_total": _round(pnl),
        "risk_multiple_current": _round(r_current),
        "risk_multiple_current_avg": _round(r_current),
        "risk_multiple_max_seen": _round(r_current),
        "risk_multiple_min_seen": _round(r_current),
        "distance_to_stop_pct": None if dist_sl is None else _round(dist_sl),
        "distance_to_take_profit_pct": None if dist_tp is None else _round(dist_tp),
        "stop_hit_diagnostic": bool(stop_hit),
        "take_profit_hit_diagnostic": bool(take_hit),
        "close_required_diagnostic": bool(close_required),
        "close_reason": "TAKE_PROFIT_HIT_DIAGNOSTIC" if take_hit else ("STOP_LOSS_HIT_DIAGNOSTIC" if stop_hit else ""),
        "price_source": price_source,
        "price_ts": price_ts,
        "paper_status_open_positions": paper_status_open_positions,
        "paper_status_pending_orders": paper_status_pending_orders,
        "orders_submitted_by_third_open_position_monitor": 0,
        "positions_opened_by_third_open_position_monitor": 0,
        "positions_closed_by_third_open_position_monitor": 0,
        "broker_submit_called_by_third_open_position_monitor": False,
        "broker_close_called_by_third_open_position_monitor": False,
        "paper_state_modified_by_third_open_position_monitor": False,
        "paper_status_modified_by_third_open_position_monitor": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "mode": str(settings.mode),
    }


def build_lsr_v2_third_open_position_monitor_report_from_files(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2ThirdOpenPositionMonitorSettings | None = None,
    requested_cycle_id: str = "",
) -> dict[str, Any]:
    settings = settings or LSRV2ThirdOpenPositionMonitorSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    state = _read_json(base / settings.paper_state_name)
    status = _read_json(base / settings.paper_status_name)
    lifecycle_report = _read_json(base / settings.lifecycle_report_name)
    execution_report = _read_json(base / settings.execution_report_name)
    cycle_id, positions = _select_open_third_position(
        state=state,
        lifecycle_report=lifecycle_report,
        execution_report=execution_report,
        requested_cycle_id=requested_cycle_id,
    )
    all_open_lsr_v2 = _all_open_lsr_v2_positions(state)
    pending_orders = _pending_orders(state)

    lifecycle_ready = lifecycle_report.get("status") == "PASS" and lifecycle_report.get("decision") == LIFECYCLE_READY_DECISION
    execution_ready = execution_report.get("status") == "PASS" and execution_report.get("decision") == EXECUTED_DECISION
    monitor_events = [
        build_lsr_v2_third_open_position_monitor_event(
            position_id=pid,
            position=row,
            data_dir=base,
            lifecycle_report=lifecycle_report,
            execution_report=execution_report,
            status=status,
            settings=settings,
        )
        for pid, row in positions
    ]

    blockers: list[str] = []
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")
    if not execution_ready:
        blockers.append("third_trade_execution_not_ready")
    if not lifecycle_ready:
        blockers.append("third_trade_lifecycle_not_ready")
    if not positions:
        blockers.append("third_trade_open_position_not_found")
    if len(positions) > 1:
        blockers.append("duplicate_third_trade_open_position_detected")
    if len(all_open_lsr_v2) > int(settings.max_positions):
        blockers.append("max_positions_check_failed")
    if pending_orders:
        blockers.append("pending_order_detected")
    paper_status_open_positions = _safe_int(status.get("open_positions"), 0)
    paper_status_pending_orders = _safe_int(status.get("pending_orders"), 0)
    paper_state_consistency = len(positions) == 1 and len(all_open_lsr_v2) == 1
    paper_status_consistency = paper_status_open_positions == len(all_open_lsr_v2) and paper_status_pending_orders == len(pending_orders)
    if positions and not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if positions and not paper_status_consistency:
        blockers.append("paper_status_inconsistent")

    close_required = any(_safe_bool(e.get("close_required_diagnostic"), False) for e in monitor_events)
    if not execution_ready:
        decision = EXECUTION_NOT_FOUND_DECISION
        status_value = "WARN"
    elif not positions:
        decision = POSITION_NOT_FOUND_DECISION
        status_value = "WARN"
    elif any(b for b in blockers if b not in {"pending_order_detected"}):
        decision = STATE_INCONSISTENT_DECISION
        status_value = "WARN"
    elif close_required:
        decision = CLOSE_REQUIRED_DECISION
        status_value = "WARN"
    else:
        decision = READY_DECISION
        status_value = "PASS"

    symbols = sorted({str(e.get("symbol") or "") for e in monitor_events if str(e.get("symbol") or "")})
    sides = sorted({str(e.get("side") or "") for e in monitor_events if str(e.get("side") or "")})
    aggregate = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status_value,
        "decision": decision,
        "blockers": sorted(set(blockers)),
        "classification_labels": [],
        "cycle_id": cycle_id,
        "event_source": "paper_state_and_paper_events",
        "strict_cycle_scope": True,
        "jsonl": str(base / settings.jsonl_name),
        "report": str(base / settings.report_name),
        "settings": settings.to_dict(),
        "execution_report_present": bool(execution_report),
        "execution_report_status": str(execution_report.get("status") or ""),
        "execution_report_decision": str(execution_report.get("decision") or ""),
        "execution_report_ready": bool(execution_ready),
        "lifecycle_report_present": bool(lifecycle_report),
        "lifecycle_report_status": str(lifecycle_report.get("status") or ""),
        "lifecycle_report_decision": str(lifecycle_report.get("decision") or ""),
        "lifecycle_report_ready": bool(lifecycle_ready),
        "monitor_events": len(monitor_events),
        "open_lsr_v2_position_count": len(positions),
        "open_third_lsr_v2_position_count": len(positions),
        "state_open_lsr_v2_positions": len(all_open_lsr_v2),
        "paper_status_open_positions": paper_status_open_positions,
        "paper_status_pending_orders": paper_status_pending_orders,
        "state_pending_order_count": len(pending_orders),
        "paper_state_consistency": bool(paper_state_consistency),
        "paper_status_consistency": bool(paper_status_consistency),
        "pending_order_detected": bool(pending_orders),
        "duplicate_position_check": len(positions) <= 1,
        "max_positions_check": len(all_open_lsr_v2) <= int(settings.max_positions),
        "third_trade_position_open": len(positions) == 1,
        "fourth_submit_or_reentry_detected": bool(pending_orders or len(positions) > 1),
        "current_statuses": sorted({s for e in monitor_events for s in (e.get("current_statuses") or [])}) if monitor_events else [],
        "symbols": symbols,
        "sides": sides,
        "entry_prices": {k: v for e in monitor_events for k, v in _as_mapping(e.get("entry_prices")).items()},
        "current_prices": {k: v for e in monitor_events for k, v in _as_mapping(e.get("current_prices")).items()},
        "stop_losses": {k: v for e in monitor_events for k, v in _as_mapping(e.get("stop_losses")).items()},
        "take_profits": {k: v for e in monitor_events for k, v in _as_mapping(e.get("take_profits")).items()},
        "unrealized_pnl_total": _round(sum(_safe_float(e.get("unrealized_pnl"), 0.0) for e in monitor_events)),
        "risk_multiple_current_avg": _round(sum(_safe_float(e.get("risk_multiple_current"), 0.0) for e in monitor_events) / len(monitor_events)) if monitor_events else None,
        "risk_multiple_max_seen": max([_safe_float(e.get("risk_multiple_current"), 0.0) for e in monitor_events] or [None]),
        "risk_multiple_min_seen": min([_safe_float(e.get("risk_multiple_current"), 0.0) for e in monitor_events] or [None]),
        "close_required_diagnostic": bool(close_required),
        "close_required_diagnostic_count": sum(1 for e in monitor_events if _safe_bool(e.get("close_required_diagnostic"), False)),
        "take_profit_hit_diagnostic_count": sum(1 for e in monitor_events if _safe_bool(e.get("take_profit_hit_diagnostic"), False)),
        "stop_hit_diagnostic_count": sum(1 for e in monitor_events if _safe_bool(e.get("stop_hit_diagnostic"), False)),
        "close_reasons": sorted({str(e.get("close_reason") or "") for e in monitor_events if str(e.get("close_reason") or "")}),
        "total_notional": _round(sum(_safe_float(e.get("notional"), 0.0) for e in monitor_events)),
        "total_risk_amount": _round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in monitor_events)),
        "orders_submitted_by_third_open_position_monitor": 0,
        "positions_opened_by_third_open_position_monitor": 0,
        "positions_closed_by_third_open_position_monitor": 0,
        "broker_submit_called_by_third_open_position_monitor": False,
        "broker_close_called_by_third_open_position_monitor": False,
        "paper_state_modified_by_third_open_position_monitor": False,
        "paper_status_modified_by_third_open_position_monitor": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "next_step": "third_trade_close_preflight" if close_required else "continue_monitoring_or_send_telegram_position_monitor",
    }
    if decision == READY_DECISION:
        aggregate["classification_labels"] = [
            "THIRD_OPEN_POSITION_MONITOR_READY",
            "THIRD_POSITION_OPEN",
            "NO_CLOSE_REQUIRED_DIAGNOSTIC",
            "PAPER_STATE_STATUS_CONSISTENT",
        ]
    elif decision == CLOSE_REQUIRED_DECISION:
        aggregate["classification_labels"] = [
            "THIRD_OPEN_POSITION_MONITOR_READY",
            "THIRD_CLOSE_REQUIRED_DIAGNOSTIC",
            "PAPER_STATE_STATUS_CONSISTENT",
        ]
    else:
        aggregate["classification_labels"] = ["KEEP_DIAGNOSTIC_THIRD_OPEN_POSITION_MONITOR"]

    _write_json(base / settings.report_name, aggregate)
    _write_jsonl_replace(base / settings.jsonl_name, monitor_events)
    return aggregate


__all__ = [
    "EVENT_TYPE",
    "JSONL_NAME",
    "REPORT_NAME",
    "READY_DECISION",
    "CLOSE_REQUIRED_DECISION",
    "LSRV2ThirdOpenPositionMonitorSettings",
    "build_lsr_v2_third_open_position_monitor_event",
    "build_lsr_v2_third_open_position_monitor_report_from_files",
]
