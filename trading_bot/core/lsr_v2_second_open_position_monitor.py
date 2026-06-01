"""Prompt 29.4.4s-10aa — LSR-v2 second open position monitor / SL-TP tracking audit.

Second-trade-specific open-position monitor for the supervised LSR-v2 paper
position opened by 29.4.4s-10y.  This module intentionally reads the second
trade lifecycle artifacts introduced in 29.4.4s-10z rather than the generic
first-trade monitor/lifecycle files.

It calculates current price, unrealized PnL, R multiple, distance to SL/TP,
and diagnostic stop/take-profit hit flags.  It never submits, closes, opens,
re-enters, calls a broker, or mutates paper state/status.
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

try:  # package import when installed in trading_bot/core
    from .lsr_v2_second_trade_position_lifecycle import (  # type: ignore
        LSRV2SecondTradePositionLifecycleSettings,
        build_lsr_v2_second_trade_position_lifecycle_report_from_files,
        _collection_rows,
        _current_price,
        _entry_price,
        _is_position_open,
        _metadata_of,
        _position_size,
        _read_json,
        _round,
        _row_cycle,
        _row_order_id,
        _row_position_id,
        _row_side,
        _row_source,
        _row_symbol,
        _safe_bool,
        _safe_float,
        _safe_int,
        _status_text,
        _write_json,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_second_trade_position_lifecycle import (  # type: ignore
        LSRV2SecondTradePositionLifecycleSettings,
        build_lsr_v2_second_trade_position_lifecycle_report_from_files,
        _collection_rows,
        _current_price,
        _entry_price,
        _is_position_open,
        _metadata_of,
        _position_size,
        _read_json,
        _round,
        _row_cycle,
        _row_order_id,
        _row_position_id,
        _row_side,
        _row_source,
        _row_symbol,
        _safe_bool,
        _safe_float,
        _safe_int,
        _status_text,
        _write_json,
    )

PROMPT_ID = "29.4.4s-10aa"
EVENT_TYPE = "LSR_V2_SECOND_OPEN_POSITION_MONITOR_AUDIT"
REPORT_NAME = "lsr_v2_second_open_position_monitor_report.json"
JSONL_NAME = "lsr_v2_second_open_position_monitor.jsonl"

LIFECYCLE_REPORT_NAME = "lsr_v2_second_trade_position_lifecycle_report.json"
LIFECYCLE_JSONL_NAME = "lsr_v2_second_trade_position_lifecycle.jsonl"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

READY_DECISION = "LSR_V2_SECOND_OPEN_POSITION_MONITOR_READY"
POSITION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_POSITION_NOT_FOUND"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_MONITOR_STATE_INCONSISTENT"
POSITION_CLOSED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_POSITION_CLOSED_AUDIT_REQUIRED"
CLOSE_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_CLOSE_REQUIRED_DIAGNOSTIC"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_OPEN_POSITION_MONITOR_SAFETY_FAILED"

SOURCE_TAG = "lsr_v2_second_trade_submit_execution"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _timeframe_minutes(value: Any, default: int = 5) -> int:
    text = str(value or "").strip().lower()
    if text.endswith("m"):
        return max(1, _safe_int(text[:-1], default))
    if text.endswith("h"):
        return max(1, _safe_int(text[:-1], 1) * 60)
    return max(1, _safe_int(text, default))


def _event_symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "")


def _event_timeframe(row: Mapping[str, Any]) -> str:
    return str(row.get("timeframe") or "")


def _event_price(row: Mapping[str, Any]) -> float:
    return _safe_float(
        row.get("last_price")
        or row.get("current_price")
        or row.get("mark_price")
        or row.get("close")
        or row.get("price"),
        0.0,
    )


def latest_market_snapshot(*, paper_events: Iterable[Mapping[str, Any]], symbol: str) -> dict[str, Any]:
    """Return the latest price-like event for a symbol from paper event logs."""
    selected: dict[str, Any] = {}
    for raw in paper_events:
        row = dict(raw)
        if _event_symbol(row) != symbol:
            continue
        price = _event_price(row)
        if price <= 0:
            continue
        selected = {
            "current_price": _round(price),
            "current_price_source_event_type": str(row.get("event_type") or ""),
            "current_price_ts": str(row.get("ts") or row.get("created_at") or ""),
            "timeframe": _event_timeframe(row) or selected.get("timeframe", "5m"),
            "source_cycle_id": str(row.get("cycle_id") or ""),
        }
    return selected


def _side_normalized(value: Any) -> str:
    text = str(value or "").upper()
    if text in {"LONG", "BUY"}:
        return "BUY"
    if text in {"SHORT", "SELL"}:
        return "SELL"
    return text


def _compute_unrealized_for_values(*, side: str, entry: float, current: float, size: float) -> float:
    if entry <= 0 or current <= 0 or size <= 0:
        return 0.0
    if _side_normalized(side) == "SELL":
        return _round((entry - current) * size)
    return _round((current - entry) * size)


def _hit_diagnostics(*, side: str, current: float, stop: float, take: float) -> tuple[bool, bool]:
    side = _side_normalized(side)
    if current <= 0:
        return False, False
    if side == "SELL":
        return bool(stop > 0 and current >= stop), bool(take > 0 and current <= take)
    return bool(stop > 0 and current <= stop), bool(take > 0 and current >= take)


def _distance_to_level(current: float, level: float) -> float | None:
    if current <= 0 or level <= 0:
        return None
    return _round(abs(current - level))


def _distance_pct(current: float, level: float) -> float | None:
    if current <= 0 or level <= 0:
        return None
    return _round(abs(current - level) / current * 100.0, 8)


def _monitor_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("cycle_id") or ""),
        str(row.get("symbol") or ""),
        str(row.get("position_id") or row.get("order_id") or ""),
    )


def _historical_r_extremes(
    *,
    existing_monitor_rows: Iterable[Mapping[str, Any]],
    key: tuple[str, str, str],
    current_r: float | None,
) -> tuple[float | None, float | None]:
    values: list[float] = []
    for raw in existing_monitor_rows:
        row = dict(raw)
        if _monitor_key(row) != key:
            continue
        if row.get("risk_multiple_current") is not None:
            values.append(_safe_float(row.get("risk_multiple_current"), 0.0))
    if current_r is not None:
        values.append(_safe_float(current_r, 0.0))
    if not values:
        return None, None
    return _round(max(values)), _round(min(values))


@dataclass(frozen=True)
class LSRV2SecondOpenPositionMonitorSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    lifecycle_report_name: str = LIFECYCLE_REPORT_NAME
    lifecycle_jsonl_name: str = LIFECYCLE_JSONL_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    max_positions: int = 1
    max_event_lines: int = 50000
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _select_cycle_id(data_dir: str | Path, settings: LSRV2SecondOpenPositionMonitorSettings) -> str:
    base = Path(data_dir)
    lifecycle_report = _read_json(base / settings.lifecycle_report_name)
    if lifecycle_report.get("cycle_id"):
        return str(lifecycle_report.get("cycle_id") or "")
    for row in reversed(_iter_jsonl_tail(base / settings.lifecycle_jsonl_name, max_lines=settings.max_event_lines)):
        if row.get("cycle_id"):
            return str(row.get("cycle_id") or "")
    return ""


def _ensure_second_lifecycle_ready(data_dir: str | Path, cycle_id: str = "") -> dict[str, Any]:
    try:
        return build_lsr_v2_second_trade_position_lifecycle_report_from_files(data_dir=data_dir, cycle_id=cycle_id)
    except Exception:
        return {}


def _is_second_lsr_v2_position(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    meta = _metadata_of(row)
    source = str(_row_source(row) or row.get("source") or meta.get("paper_order_source") or "")
    if SOURCE_TAG in source:
        return True
    if _safe_int(row.get("trade_ordinal") or meta.get("trade_ordinal"), 0) == 2:
        return True
    if cycle_id and _row_cycle(row) == cycle_id:
        return True
    return False


def build_lsr_v2_second_open_position_monitor_event(
    *,
    lifecycle_event: Mapping[str, Any],
    position: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    existing_monitor_rows: Iterable[Mapping[str, Any]] = (),
    now: datetime | None = None,
    settings: LSRV2SecondOpenPositionMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondOpenPositionMonitorSettings()
    now = now or datetime.now(timezone.utc)
    side = _side_normalized(_row_side(position) or lifecycle_event.get("side"))
    symbol = _row_symbol(position) or str(lifecycle_event.get("symbol") or "")
    entry = _entry_price(position) or _safe_float(lifecycle_event.get("entry_price"), 0.0)
    current = _safe_float(market_snapshot.get("current_price"), 0.0) or _current_price(position, entry) or _safe_float(lifecycle_event.get("current_price"), entry)
    stop = _safe_float(position.get("stop_loss") or lifecycle_event.get("stop_loss"), 0.0)
    take = _safe_float(position.get("take_profit") or lifecycle_event.get("take_profit"), 0.0)
    size = _position_size(position) or _safe_float(lifecycle_event.get("position_size"), 0.0)
    notional = _safe_float(position.get("notional") or lifecycle_event.get("notional"), 0.0)
    risk_amount = _safe_float(position.get("risk_amount") or lifecycle_event.get("risk_amount"), 0.0)
    pnl = _compute_unrealized_for_values(side=side, entry=entry, current=current, size=size)
    risk_multiple_current = _round(pnl / risk_amount) if risk_amount > 0 else None
    stop_hit, tp_hit = _hit_diagnostics(side=side, current=current, stop=stop, take=take)
    opened_at = str(position.get("opened_at") or position.get("created_at") or lifecycle_event.get("opened_at") or "")
    opened_dt = _parse_dt(opened_at)
    age_minutes: float | None = None
    if opened_dt:
        delta = now.astimezone(timezone.utc) - opened_dt
        age_minutes = max(0.0, delta.total_seconds() / 60.0)
    timeframe = str(market_snapshot.get("timeframe") or "5m")
    age_bars = _round((age_minutes or 0.0) / _timeframe_minutes(timeframe, 5), 4) if age_minutes is not None else None
    position_id = _row_position_id(position) or str(lifecycle_event.get("position_id") or "")
    order_id = str(position.get("order_id") or lifecycle_event.get("order_id") or "")
    cycle_id = str(lifecycle_event.get("cycle_id") or _row_cycle(position) or "")
    key = (cycle_id, symbol, position_id or order_id)
    max_r, min_r = _historical_r_extremes(existing_monitor_rows=existing_monitor_rows, key=key, current_r=risk_multiple_current)
    current_status = _status_text(position, str(lifecycle_event.get("current_status") or "OPEN"))
    position_open = _is_position_open(position)

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": cycle_id,
        "source": "lsr_v2_second_trade_position_lifecycle",
        "trade_ordinal": 2,
        "profile_name": str(lifecycle_event.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(lifecycle_event.get("selected_overlay_id") or settings.selected_overlay_id),
        "order_id": order_id,
        "position_id": position_id,
        "symbol": symbol,
        "side": side,
        "current_status": current_status,
        "position_open": bool(position_open),
        "second_trade_position_open": bool(position_open),
        "opened_at": opened_at,
        "entry_price": _round(entry),
        "current_price": _round(current),
        "current_price_source_event_type": str(market_snapshot.get("current_price_source_event_type") or ""),
        "current_price_ts": str(market_snapshot.get("current_price_ts") or ""),
        "stop_loss": _round(stop),
        "take_profit": _round(take),
        "position_size": _round(size),
        "notional": _round(notional),
        "risk_amount": _round(risk_amount),
        "unrealized_pnl": _round(pnl),
        "risk_multiple_current": risk_multiple_current,
        "risk_multiple_max_seen": max_r,
        "risk_multiple_min_seen": min_r,
        "distance_to_stop": _distance_to_level(current, stop),
        "distance_to_stop_pct": _distance_pct(current, stop),
        "distance_to_take_profit": _distance_to_level(current, take),
        "distance_to_take_profit_pct": _distance_pct(current, take),
        "position_age_minutes": _round(age_minutes, 4) if age_minutes is not None else None,
        "position_age_bars": age_bars,
        "timeframe": timeframe,
        "stop_hit_diagnostic": bool(stop_hit),
        "take_profit_hit_diagnostic": bool(tp_hit),
        "close_required_diagnostic": bool(stop_hit or tp_hit),
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "orders_submitted_by_second_open_position_monitor": 0,
        "positions_opened_by_second_open_position_monitor": 0,
        "positions_closed_by_second_open_position_monitor": 0,
        "broker_submit_called_by_second_open_position_monitor": False,
        "broker_close_called_by_second_open_position_monitor": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }


def build_lsr_v2_second_open_position_monitor_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondOpenPositionMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondOpenPositionMonitorSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    selected_cycle_id = cycle_id or _select_cycle_id(data_dir, settings)
    lifecycle_report = _ensure_second_lifecycle_ready(data_dir, selected_cycle_id)
    if lifecycle_report.get("cycle_id"):
        selected_cycle_id = str(lifecycle_report.get("cycle_id") or selected_cycle_id)
    lifecycle_rows = _iter_jsonl_tail(base / settings.lifecycle_jsonl_name, max_lines=settings.max_event_lines)
    lifecycle_rows = [row for row in lifecycle_rows if not selected_cycle_id or str(row.get("cycle_id") or "") == selected_cycle_id]
    open_lifecycle_rows = [row for row in lifecycle_rows if _safe_bool(row.get("second_trade_position_open") or row.get("position_open"), False)]

    state = _read_json(base / settings.paper_state_name)
    status = _read_json(base / settings.paper_status_name)
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = [p for p in positions if _is_position_open(p) and _is_second_lsr_v2_position(p, cycle_id=selected_cycle_id)]
    paper_events = _iter_jsonl_tail(base / settings.paper_events_name, max_lines=settings.max_event_lines)
    existing_monitor_rows = _iter_jsonl_tail(base / settings.jsonl_name, max_lines=settings.max_event_lines)

    monitor_events: list[dict[str, Any]] = []
    for lifecycle_event in open_lifecycle_rows:
        position_id = str(lifecycle_event.get("position_id") or "")
        order_id = str(lifecycle_event.get("order_id") or "")
        symbol = str(lifecycle_event.get("symbol") or "")
        selected_position: Mapping[str, Any] | None = None
        for pos in open_positions:
            if position_id and _row_position_id(pos) == position_id:
                selected_position = pos
                break
            if order_id and str(pos.get("order_id") or _metadata_of(pos).get("order_id") or "") == order_id:
                selected_position = pos
                break
        if selected_position is None:
            for pos in open_positions:
                if symbol and _row_symbol(pos) == symbol:
                    selected_position = pos
                    break
        if selected_position is None:
            continue
        snapshot = latest_market_snapshot(paper_events=paper_events, symbol=_row_symbol(selected_position) or symbol)
        monitor_events.append(build_lsr_v2_second_open_position_monitor_event(
            lifecycle_event=lifecycle_event,
            position=selected_position,
            market_snapshot=snapshot,
            existing_monitor_rows=existing_monitor_rows,
            settings=settings,
        ))

    _write_jsonl_replace(base / settings.jsonl_name, monitor_events)
    report = summarize_lsr_v2_second_open_position_monitor(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        lifecycle_report=lifecycle_report,
        lifecycle_events=lifecycle_rows,
        monitor_events=monitor_events,
        state=state,
        status=status,
        positions=positions,
        settings=settings,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def summarize_lsr_v2_second_open_position_monitor(
    *,
    data_dir: str | Path,
    cycle_id: str,
    lifecycle_report: Mapping[str, Any],
    lifecycle_events: Iterable[Mapping[str, Any]],
    monitor_events: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
    status: Mapping[str, Any],
    positions: Iterable[Mapping[str, Any]],
    settings: LSRV2SecondOpenPositionMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondOpenPositionMonitorSettings(data_dir=str(data_dir))
    lifecycle_rows = [dict(e) for e in lifecycle_events]
    rows = [dict(e) for e in monitor_events]
    position_rows = [dict(p) for p in positions]
    open_state_positions = [p for p in position_rows if _is_position_open(p) and _is_second_lsr_v2_position(p, cycle_id=cycle_id)]
    status_open_positions = _safe_int(status.get("open_positions"), 0)
    status_pending_orders = _safe_int(status.get("pending_orders"), 0)

    open_rows = [e for e in rows if _safe_bool(e.get("position_open"), False)]
    stop_hit = [e for e in rows if _safe_bool(e.get("stop_hit_diagnostic"), False)]
    tp_hit = [e for e in rows if _safe_bool(e.get("take_profit_hit_diagnostic"), False)]
    close_required = [e for e in rows if _safe_bool(e.get("close_required_diagnostic"), False)]

    paper_state_consistency = bool(lifecycle_report.get("paper_state_consistency", False)) and len(open_state_positions) == len(open_rows)
    paper_status_consistency = bool(lifecycle_report.get("paper_status_consistency", False)) and status_open_positions == len(open_state_positions)

    blockers: list[str] = []
    if not lifecycle_rows:
        blockers.append("second_trade_lifecycle_missing")
    if not open_rows:
        blockers.append("second_trade_open_position_not_found")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if status_pending_orders > 0:
        blockers.append("paper_status_pending_orders_nonzero")
    if len(open_state_positions) > settings.max_positions:
        blockers.append("max_positions_exceeded")

    safety_violation = any(
        _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        or _safe_int(e.get("orders_submitted_by_second_open_position_monitor"), 0) > 0
        or _safe_int(e.get("positions_opened_by_second_open_position_monitor"), 0) > 0
        or _safe_int(e.get("positions_closed_by_second_open_position_monitor"), 0) > 0
        or _safe_bool(e.get("broker_submit_called_by_second_open_position_monitor"), False)
        or _safe_bool(e.get("broker_close_called_by_second_open_position_monitor"), False)
        for e in rows
    )
    if safety_violation:
        blockers.append("second_open_position_monitor_safety_violation_detected")

    if safety_violation or len(open_state_positions) > settings.max_positions:
        decision = REJECT_DECISION
        status_text = "FAIL" if safety_violation else "WARN"
    elif not open_rows:
        if _safe_int(lifecycle_report.get("closed_lsr_v2_position_count"), 0) > 0:
            decision = POSITION_CLOSED_DECISION
        else:
            decision = POSITION_NOT_FOUND_DECISION
        status_text = "WARN"
    elif not paper_state_consistency or not paper_status_consistency or status_pending_orders > 0:
        decision = STATE_INCONSISTENT_DECISION
        status_text = "WARN"
    elif close_required:
        decision = CLOSE_REQUIRED_DECISION
        status_text = "WARN"
    else:
        decision = READY_DECISION
        status_text = "PASS"

    def _map_float(key: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if symbol:
                out[symbol] = _round(row.get(key))
        return out

    risk_values = [row.get("risk_multiple_current") for row in rows if row.get("risk_multiple_current") is not None]
    risk_avg = _round(sum(_safe_float(v, 0.0) for v in risk_values) / len(risk_values)) if risk_values else None
    risk_max_seen_values = [row.get("risk_multiple_max_seen") for row in rows if row.get("risk_multiple_max_seen") is not None]
    risk_min_seen_values = [row.get("risk_multiple_min_seen") for row in rows if row.get("risk_multiple_min_seen") is not None]

    safety_checks = {
        "no_new_order_by_second_open_position_monitor": True,
        "no_new_position_by_second_open_position_monitor": True,
        "no_close_by_second_open_position_monitor": True,
        "no_broker_submit_by_second_open_position_monitor": True,
        "no_broker_close_by_second_open_position_monitor": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
        "automatic_close_disabled": True,
        "automatic_reentry_disabled": True,
        "max_positions_check": len(open_state_positions) <= settings.max_positions,
    }

    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_SECOND_OPEN_POSITION_MONITOR",
            "SECOND_POSITION_MONITORING",
        ] + (["CLOSE_REQUIRED_DIAGNOSTIC"] if close_required else ["OPEN_POSITION_MONITOR_READY"] if decision == READY_DECISION else ["KEEP_DIAGNOSTIC"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": "second_trade_lifecycle_and_paper_events",
        "strict_cycle_scope": True,
        "lifecycle_decision": lifecycle_report.get("decision"),
        "lifecycle_status": lifecycle_report.get("status"),
        "lifecycle_events": len(lifecycle_rows),
        "monitor_events": len(rows),
        "second_trade_position_open": bool(open_rows),
        "open_second_lsr_v2_position_count": len(open_rows),
        "open_lsr_v2_position_count": len(open_rows),
        "state_open_lsr_v2_positions": len(open_state_positions),
        "paper_status_open_positions": status_open_positions,
        "paper_status_pending_orders": status_pending_orders,
        "paper_state_consistency": bool(paper_state_consistency),
        "paper_status_consistency": bool(paper_status_consistency),
        "current_statuses": sorted({str(e.get("current_status") or "") for e in rows if e.get("current_status")}),
        "symbols": sorted({str(e.get("symbol") or "") for e in rows if e.get("symbol")}),
        "sides": sorted({str(e.get("side") or "") for e in rows if e.get("side")}),
        "entry_prices": _map_float("entry_price"),
        "current_prices": _map_float("current_price"),
        "stop_losses": _map_float("stop_loss"),
        "take_profits": _map_float("take_profit"),
        "risk_multiple_current_avg": risk_avg,
        "risk_multiple_max_seen": _round(max(_safe_float(v, 0.0) for v in risk_max_seen_values)) if risk_max_seen_values else risk_avg,
        "risk_multiple_min_seen": _round(min(_safe_float(v, 0.0) for v in risk_min_seen_values)) if risk_min_seen_values else risk_avg,
        "unrealized_pnl_total": _round(sum(_safe_float(e.get("unrealized_pnl"), 0.0) for e in rows)),
        "total_risk_amount": _round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in rows)),
        "total_notional": _round(sum(_safe_float(e.get("notional"), 0.0) for e in rows)),
        "stop_hit_diagnostic_count": len(stop_hit),
        "take_profit_hit_diagnostic_count": len(tp_hit),
        "close_required_diagnostic": bool(close_required),
        "close_required_diagnostic_count": len(close_required),
        "orders_submitted_by_second_open_position_monitor": 0,
        "positions_opened_by_second_open_position_monitor": 0,
        "positions_closed_by_second_open_position_monitor": 0,
        "broker_submit_called_by_second_open_position_monitor": False,
        "broker_close_called_by_second_open_position_monitor": False,
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
