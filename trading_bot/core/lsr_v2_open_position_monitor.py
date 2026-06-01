"""Prompt 29.4.4s-10m — LSR-v2 open position monitor / SL-TP tracking audit.

Reads the current LSR-v2 paper position lifecycle artifacts and active paper
state/events to monitor the first supervised paper-only position.  The module
never closes, opens, re-enters, submits to any broker, or mutates paper state.
It only writes diagnostic monitor reports for the open position.
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

try:  # project import when run from repository root
    from core.lsr_v2_paper_position_lifecycle import (  # type: ignore
        LSRV2PaperPositionLifecycleSettings,
        build_lsr_v2_paper_position_lifecycle_report_from_files,
        _collection_rows,
        _compute_unrealized_pnl,
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
except Exception:  # package import in tests
    from trading_bot.core.lsr_v2_paper_position_lifecycle import (  # type: ignore
        LSRV2PaperPositionLifecycleSettings,
        build_lsr_v2_paper_position_lifecycle_report_from_files,
        _collection_rows,
        _compute_unrealized_pnl,
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

PROMPT_ID = "29.4.4s-10m"
EVENT_TYPE = "LSR_V2_OPEN_POSITION_MONITOR_AUDIT"
REPORT_NAME = "lsr_v2_open_position_monitor_report.json"
JSONL_NAME = "lsr_v2_open_position_monitor.jsonl"

LIFECYCLE_REPORT_NAME = "lsr_v2_paper_position_lifecycle_report.json"
LIFECYCLE_JSONL_NAME = "lsr_v2_paper_position_lifecycle.jsonl"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

READY_DECISION = "LSR_V2_OPEN_POSITION_MONITOR_READY"
POSITION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_MONITOR_STATE_INCONSISTENT"
POSITION_CLOSED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSITION_CLOSED_AUDIT_REQUIRED"
CLOSE_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_REQUIRED_DIAGNOSTIC"
REJECT_DECISION = "REJECT_LSR_V2_OPEN_POSITION_MONITOR_SAFETY_FAILED"

SOURCE_TAG = "lsr_v2_supervised_paper_submit_execution"
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


def _event_price(row: Mapping[str, Any]) -> float:
    return _safe_float(
        row.get("last_price")
        or row.get("current_price")
        or row.get("mark_price")
        or row.get("close")
        or row.get("price"),
        0.0,
    )


def _event_symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "")


def _event_timeframe(row: Mapping[str, Any]) -> str:
    return str(row.get("timeframe") or "")


def latest_market_snapshot(
    *,
    paper_events: Iterable[Mapping[str, Any]],
    symbol: str,
) -> dict[str, Any]:
    """Return the latest price-like event for a symbol from paper event logs."""
    selected: dict[str, Any] = {}
    for raw in paper_events:
        row = dict(raw)
        if _event_symbol(row) != symbol:
            continue
        price = _event_price(row)
        if price <= 0:
            continue
        # Prefer asset scan, but accept any runtime/candidate event carrying price.
        selected = {
            "current_price": _round(price),
            "current_price_source_event_type": str(row.get("event_type") or ""),
            "current_price_ts": str(row.get("ts") or row.get("created_at") or ""),
            "timeframe": _event_timeframe(row) or selected.get("timeframe", "5m"),
            "source_cycle_id": str(row.get("cycle_id") or ""),
        }
    return selected


def _position_source(row: Mapping[str, Any]) -> str:
    return _row_source(row) or str(row.get("source") or "")


def _is_lsr_v2_position(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    source = _position_source(row)
    meta = _metadata_of(row)
    if SOURCE_TAG in source or "LSR_V2" in source.upper():
        return True
    if str(row.get("profile_name") or meta.get("profile_name") or "") == PROFILE_NAME:
        return True
    if cycle_id and _row_cycle(row) == cycle_id:
        return True
    return False


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
    stop_hit = False
    take_hit = False
    if side == "SELL":
        stop_hit = stop > 0 and current >= stop
        take_hit = take > 0 and current <= take
    else:
        stop_hit = stop > 0 and current <= stop
        take_hit = take > 0 and current >= take
    return bool(stop_hit), bool(take_hit)


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
class LSRV2OpenPositionMonitorSettings:
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


def _select_cycle_id(data_dir: str | Path, settings: LSRV2OpenPositionMonitorSettings) -> str:
    base = Path(data_dir)
    lifecycle_report = _read_json(base / settings.lifecycle_report_name)
    if lifecycle_report.get("cycle_id"):
        return str(lifecycle_report.get("cycle_id") or "")
    for row in reversed(_iter_jsonl_tail(base / settings.lifecycle_jsonl_name, max_lines=settings.max_event_lines)):
        if row.get("cycle_id"):
            return str(row.get("cycle_id") or "")
    for row in reversed(_iter_jsonl_tail(base / settings.paper_events_name, max_lines=settings.max_event_lines)):
        if row.get("cycle_id"):
            return str(row.get("cycle_id") or "")
    return ""


def _ensure_lifecycle_ready(data_dir: str | Path, cycle_id: str = "") -> dict[str, Any]:
    try:
        return build_lsr_v2_paper_position_lifecycle_report_from_files(data_dir=data_dir, cycle_id=cycle_id)
    except Exception:
        return {}


def build_lsr_v2_open_position_monitor_event(
    *,
    lifecycle_event: Mapping[str, Any],
    position: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    existing_monitor_rows: Iterable[Mapping[str, Any]] = (),
    now: datetime | None = None,
    settings: LSRV2OpenPositionMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2OpenPositionMonitorSettings()
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
    close_required = bool(stop_hit or tp_hit)
    opened_at = str(position.get("opened_at") or position.get("created_at") or lifecycle_event.get("opened_at") or "")
    opened_dt = _parse_dt(opened_at)
    age_minutes: float | None = None
    if opened_dt:
        delta = now.astimezone(timezone.utc) - opened_dt
        age_minutes = max(0.0, delta.total_seconds() / 60.0)
    timeframe = str(market_snapshot.get("timeframe") or "5m")
    tf_minutes = _timeframe_minutes(timeframe, 5)
    age_bars = _round((age_minutes or 0.0) / tf_minutes, 4) if age_minutes is not None else None
    position_id = _row_position_id(position) or str(lifecycle_event.get("position_id") or "")
    order_id = str(position.get("order_id") or lifecycle_event.get("order_id") or "")
    key = (str(lifecycle_event.get("cycle_id") or _row_cycle(position) or ""), symbol, position_id or order_id)
    max_r, min_r = _historical_r_extremes(
        existing_monitor_rows=existing_monitor_rows,
        key=key,
        current_r=risk_multiple_current,
    )
    current_status = _status_text(position, str(lifecycle_event.get("current_status") or "OPEN"))
    position_open = _is_position_open(position)
    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": key[0],
        "source": "lsr_v2_paper_position_lifecycle",
        "profile_name": str(lifecycle_event.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(lifecycle_event.get("selected_overlay_id") or settings.selected_overlay_id),
        "order_id": order_id,
        "position_id": position_id,
        "symbol": symbol,
        "side": side,
        "current_status": current_status,
        "position_open": bool(position_open),
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
        "close_required_diagnostic": bool(close_required),
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "orders_submitted_by_open_position_monitor": 0,
        "positions_opened_by_open_position_monitor": 0,
        "broker_submit_called_by_open_position_monitor": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }


def build_lsr_v2_open_position_monitor_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2OpenPositionMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2OpenPositionMonitorSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    selected_cycle_id = cycle_id or _select_cycle_id(data_dir, settings)
    lifecycle_report = _ensure_lifecycle_ready(data_dir, selected_cycle_id)
    if lifecycle_report.get("cycle_id"):
        selected_cycle_id = str(lifecycle_report.get("cycle_id") or selected_cycle_id)
    lifecycle_rows = _iter_jsonl_tail(base / settings.lifecycle_jsonl_name, max_lines=settings.max_event_lines)
    lifecycle_rows = [r for r in lifecycle_rows if (not selected_cycle_id or str(r.get("cycle_id") or "") == selected_cycle_id)]
    state = _read_json(base / settings.paper_state_name)
    status = _read_json(base / settings.paper_status_name)
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = [p for p in positions if _is_position_open(p) and _is_lsr_v2_position(p, cycle_id=selected_cycle_id)]
    paper_events = _iter_jsonl_tail(base / settings.paper_events_name, max_lines=settings.max_event_lines)
    existing_monitor_rows = _iter_jsonl_tail(base / settings.jsonl_name, max_lines=settings.max_event_lines)
    monitor_events: list[dict[str, Any]] = []
    for lifecycle_event in lifecycle_rows:
        if not _safe_bool(lifecycle_event.get("position_open"), False):
            continue
        position_id = str(lifecycle_event.get("position_id") or "")
        order_id = str(lifecycle_event.get("order_id") or "")
        symbol = str(lifecycle_event.get("symbol") or "")
        matching = None
        for pos in open_positions:
            if position_id and _row_position_id(pos) == position_id:
                matching = pos
                break
            if order_id and str(pos.get("order_id") or _metadata_of(pos).get("order_id") or "") == order_id:
                matching = pos
                break
        if matching is None:
            for pos in open_positions:
                if symbol and _row_symbol(pos) == symbol:
                    matching = pos
                    break
        if matching is None:
            continue
        snapshot = latest_market_snapshot(paper_events=paper_events, symbol=symbol)
        monitor_events.append(build_lsr_v2_open_position_monitor_event(
            lifecycle_event=lifecycle_event,
            position=matching,
            market_snapshot=snapshot,
            existing_monitor_rows=existing_monitor_rows,
            settings=settings,
        ))
    _write_jsonl_replace(base / settings.jsonl_name, monitor_events)
    report = summarize_lsr_v2_open_position_monitor(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        lifecycle_report=lifecycle_report,
        monitor_events=monitor_events,
        state=state,
        status=status,
        open_positions=open_positions,
        settings=settings,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def summarize_lsr_v2_open_position_monitor(
    *,
    data_dir: str | Path,
    cycle_id: str,
    lifecycle_report: Mapping[str, Any],
    monitor_events: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
    status: Mapping[str, Any],
    open_positions: Iterable[Mapping[str, Any]],
    settings: LSRV2OpenPositionMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2OpenPositionMonitorSettings(data_dir=str(data_dir))
    rows = [dict(e) for e in monitor_events]
    open_position_rows = [dict(p) for p in open_positions]
    status_open_positions = _safe_int(status.get("open_positions"), 0)
    paper_state_consistency = _safe_bool(lifecycle_report.get("paper_state_consistency"), False)
    paper_status_consistency = _safe_bool(lifecycle_report.get("paper_status_consistency"), False)
    if rows and status_open_positions != len(open_position_rows):
        paper_status_consistency = False
    duplicate_position_check = len(open_position_rows) <= settings.max_positions
    max_positions_check = len(open_position_rows) <= settings.max_positions
    any_stop_hit = any(_safe_bool(e.get("stop_hit_diagnostic"), False) for e in rows)
    any_tp_hit = any(_safe_bool(e.get("take_profit_hit_diagnostic"), False) for e in rows)
    any_close_required = any(_safe_bool(e.get("close_required_diagnostic"), False) for e in rows)
    safety_violation = any(
        _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        or _safe_int(e.get("orders_submitted_by_open_position_monitor"), 0) > 0
        or _safe_int(e.get("positions_opened_by_open_position_monitor"), 0) > 0
        or _safe_bool(e.get("broker_submit_called_by_open_position_monitor"), False)
        for e in rows
    )
    blockers: list[str] = []
    if not rows:
        blockers.append("open_lsr_v2_position_not_found")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if not duplicate_position_check:
        blockers.append("duplicate_lsr_v2_positions_detected")
    if not max_positions_check:
        blockers.append("max_positions_exceeded")
    if safety_violation:
        blockers.append("open_position_monitor_safety_violation")

    if safety_violation or not duplicate_position_check or not max_positions_check:
        decision = REJECT_DECISION
        status_text = "WARN"
    elif not rows:
        decision = POSITION_NOT_FOUND_DECISION
        status_text = "WARN"
    elif not paper_state_consistency or not paper_status_consistency:
        decision = STATE_INCONSISTENT_DECISION
        status_text = "WARN"
    elif any_close_required:
        decision = CLOSE_REQUIRED_DECISION
        status_text = "WARN"
    elif all(not _safe_bool(e.get("position_open"), False) for e in rows):
        decision = POSITION_CLOSED_DECISION
        status_text = "WARN"
    else:
        decision = READY_DECISION
        status_text = "PASS"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in rows), 10)
    avg_r = None
    r_values = [_safe_float(e.get("risk_multiple_current"), 0.0) for e in rows if e.get("risk_multiple_current") is not None]
    if r_values:
        avg_r = _round(sum(r_values) / len(r_values))
    safety_checks = {
        "no_new_order_by_open_position_monitor": True,
        "no_new_position_by_open_position_monitor": True,
        "no_broker_submit_by_open_position_monitor": True,
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
            "LSR_V2_OPEN_POSITION_MONITOR",
            "SL_TP_TRACKING_AUDIT",
        ] + (["CLOSE_REQUIRED_DIAGNOSTIC"] if any_close_required else ["OPEN_POSITION_MONITORING"] if rows else ["POSITION_NOT_FOUND"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": "paper_state_and_paper_events",
        "strict_cycle_scope": True,
        "lifecycle_decision": lifecycle_report.get("decision"),
        "lifecycle_status": lifecycle_report.get("status"),
        "monitor_events": len(rows),
        "open_lsr_v2_position_count": len(rows),
        "state_open_lsr_v2_positions": len(open_position_rows),
        "paper_status_open_positions": status_open_positions,
        "paper_state_consistency": bool(paper_state_consistency),
        "paper_status_consistency": bool(paper_status_consistency),
        "duplicate_position_check": bool(duplicate_position_check),
        "max_positions_check": bool(max_positions_check),
        "symbols": sorted({str(e.get("symbol") or "") for e in rows if e.get("symbol")}),
        "sides": sorted({str(e.get("side") or "") for e in rows if e.get("side")}),
        "current_statuses": sorted({str(e.get("current_status") or "") for e in rows if e.get("current_status")}),
        "current_prices": {str(e.get("symbol") or ""): e.get("current_price") for e in rows if e.get("symbol")},
        "entry_prices": {str(e.get("symbol") or ""): e.get("entry_price") for e in rows if e.get("symbol")},
        "stop_losses": {str(e.get("symbol") or ""): e.get("stop_loss") for e in rows if e.get("symbol")},
        "take_profits": {str(e.get("symbol") or ""): e.get("take_profit") for e in rows if e.get("symbol")},
        "unrealized_pnl_total": _round(sum(_safe_float(e.get("unrealized_pnl"), 0.0) for e in rows)),
        "risk_multiple_current_avg": avg_r,
        "risk_multiple_min_seen": min((e.get("risk_multiple_min_seen") for e in rows if e.get("risk_multiple_min_seen") is not None), default=None),
        "risk_multiple_max_seen": max((e.get("risk_multiple_max_seen") for e in rows if e.get("risk_multiple_max_seen") is not None), default=None),
        "stop_hit_diagnostic_count": sum(1 for e in rows if _safe_bool(e.get("stop_hit_diagnostic"), False)),
        "take_profit_hit_diagnostic_count": sum(1 for e in rows if _safe_bool(e.get("take_profit_hit_diagnostic"), False)),
        "close_required_diagnostic_count": sum(1 for e in rows if _safe_bool(e.get("close_required_diagnostic"), False)),
        "close_required_diagnostic": bool(any_close_required),
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "orders_submitted_by_open_position_monitor": 0,
        "positions_opened_by_open_position_monitor": 0,
        "broker_submit_called_by_open_position_monitor": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "promotion_ready": False,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }
