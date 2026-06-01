"""Prompt 29.4.4s-10ab — LSR-v2 second supervised paper close preflight.

Second-trade-specific close preflight for the LSR-v2 paper position opened by
29.4.4s-10y and monitored by 29.4.4s-10aa.  The module reads the second
open-position monitor, second lifecycle, paper state and paper status, then
prepares an auditable close boundary when SL/TP diagnostics require a close.

It never closes a position, opens a new order, submits to a broker, re-enters,
or mutates paper state/status.
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

PROMPT_ID = "29.4.4s-10ab"
EVENT_TYPE = "LSR_V2_SECOND_TRADE_CLOSE_PREFLIGHT"
REPORT_NAME = "lsr_v2_second_trade_close_preflight_report.json"
JSONL_NAME = "lsr_v2_second_trade_close_preflight.jsonl"

MONITOR_EVENT_TYPE = "LSR_V2_SECOND_OPEN_POSITION_MONITOR_AUDIT"
MONITOR_REPORT_NAME = "lsr_v2_second_open_position_monitor_report.json"
MONITOR_JSONL_NAME = "lsr_v2_second_open_position_monitor.jsonl"
LIFECYCLE_REPORT_NAME = "lsr_v2_second_trade_position_lifecycle_report.json"
LIFECYCLE_JSONL_NAME = "lsr_v2_second_trade_position_lifecycle.jsonl"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

READY_DECISION = "LSR_V2_SECOND_TRADE_CLOSE_PREFLIGHT_READY"
CLOSE_NOT_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_CLOSE_NOT_REQUIRED"
POSITION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_POSITION_NOT_FOUND"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_STATE_INCONSISTENT"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_CLOSE_PREFLIGHT_FAILED"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"
SOURCE_TAG = "lsr_v2_second_trade_submit_execution"
CLOSE_PREFLIGHT_ENABLE_ENV = "LSR_V2_SECOND_TRADE_CLOSE_PREFLIGHT_ENABLE"
CLOSE_PREFLIGHT_CONFIRM_ENV = "LSR_V2_SECOND_TRADE_CLOSE_PREFLIGHT_CONFIRMATION"
CLOSE_PREFLIGHT_CONFIRMATION = "I_UNDERSTAND_SECOND_CLOSE_PREFLIGHT_ONLY"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "ready", "open"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null", "closed"}:
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


def _metadata_of(row: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata
    meta = row.get("meta")
    if isinstance(meta, Mapping):
        return meta
    return {}


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


def _payload_of(row: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, Mapping) else {}


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    payload = _payload_of(row)
    return str(
        row.get("paper_order_source")
        or row.get("execution_source")
        or row.get("source")
        or payload.get("source")
        or meta.get("paper_order_source")
        or meta.get("execution_source")
        or meta.get("source")
        or ""
    )


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    payload = _payload_of(row)
    return str(row.get("cycle_id") or payload.get("cycle_id") or meta.get("cycle_id") or "")


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    payload = _payload_of(row)
    return str(row.get("symbol") or payload.get("symbol") or meta.get("symbol") or "")


def _row_side(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    payload = _payload_of(row)
    side = str(row.get("side") or row.get("direction") or payload.get("side") or meta.get("side") or "").upper()
    if side == "LONG":
        return "BUY"
    if side == "SHORT":
        return "SELL"
    return side


def _row_order_id(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    payload = _payload_of(row)
    return str(row.get("order_id") or row.get("id") or payload.get("order_id") or meta.get("order_id") or "")


def _row_position_id(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    payload = _payload_of(row)
    return str(row.get("position_id") or row.get("id") or payload.get("position_id") or meta.get("position_id") or "")


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_second_lsr_v2_position(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    source = _row_source(row)
    meta = _metadata_of(row)
    if SOURCE_TAG in source:
        return True
    if "SECOND" in source.upper() and "LSR_V2" in source.upper():
        return True
    if str(row.get("profile_name") or meta.get("profile_name") or "") == PROFILE_NAME and cycle_id and _row_cycle(row) == cycle_id:
        return True
    if cycle_id and _row_cycle(row) == cycle_id and "LSR_V2" in source.upper():
        return True
    return False


def _select_cycle_id(*, data_dir: str | Path, requested_cycle_id: str = "", settings: "LSRV2SecondTradeClosePreflightSettings") -> str:
    base = Path(data_dir)
    if requested_cycle_id:
        return str(requested_cycle_id)
    for name in (settings.monitor_report_name, settings.lifecycle_report_name):
        report = _read_json(base / name)
        if report.get("cycle_id"):
            return str(report.get("cycle_id") or "")
    for row in reversed(_iter_jsonl_tail(base / settings.monitor_jsonl_name, max_lines=settings.max_event_lines)):
        if row.get("cycle_id"):
            return str(row.get("cycle_id") or "")
    for row in reversed(_iter_jsonl_tail(base / settings.lifecycle_jsonl_name, max_lines=settings.max_event_lines)):
        if row.get("cycle_id"):
            return str(row.get("cycle_id") or "")
    return ""


def _select_monitor_events(*, data_dir: str | Path, cycle_id: str, settings: "LSRV2SecondTradeClosePreflightSettings") -> list[dict[str, Any]]:
    base = Path(data_dir)
    rows = [r for r in _iter_jsonl_tail(base / settings.monitor_jsonl_name, max_lines=settings.max_event_lines) if r.get("event_type") == MONITOR_EVENT_TYPE]
    selected = [dict(r) for r in rows if not cycle_id or str(r.get("cycle_id") or "") == cycle_id]
    if selected:
        return selected
    report = _read_json(base / settings.monitor_report_name)
    if report and (not cycle_id or str(report.get("cycle_id") or "") == cycle_id):
        symbols = report.get("symbols") if isinstance(report.get("symbols"), list) else []
        sides = report.get("sides") if isinstance(report.get("sides"), list) else []
        out: list[dict[str, Any]] = []
        for idx, symbol in enumerate(symbols or [""]):
            sym = str(symbol or "")
            out.append({
                "event_type": MONITOR_EVENT_TYPE,
                "cycle_id": str(report.get("cycle_id") or cycle_id),
                "symbol": sym,
                "side": str((sides[idx] if idx < len(sides) else "") or ""),
                "current_status": "OPEN",
                "position_open": True,
                "second_trade_position_open": True,
                "entry_price": (report.get("entry_prices") or {}).get(sym) if isinstance(report.get("entry_prices"), Mapping) else None,
                "current_price": (report.get("current_prices") or {}).get(sym) if isinstance(report.get("current_prices"), Mapping) else None,
                "stop_loss": (report.get("stop_losses") or {}).get(sym) if isinstance(report.get("stop_losses"), Mapping) else None,
                "take_profit": (report.get("take_profits") or {}).get(sym) if isinstance(report.get("take_profits"), Mapping) else None,
                "risk_amount": report.get("total_risk_amount"),
                "notional": report.get("total_notional"),
                "risk_multiple_current": report.get("risk_multiple_current_avg"),
                "unrealized_pnl": report.get("unrealized_pnl_total"),
                "stop_hit_diagnostic": _safe_int(report.get("stop_hit_diagnostic_count"), 0) > 0,
                "take_profit_hit_diagnostic": _safe_int(report.get("take_profit_hit_diagnostic_count"), 0) > 0,
                "close_required_diagnostic": _safe_bool(report.get("close_required_diagnostic"), False),
            })
        return out
    return []


def _find_matching_position(event: Mapping[str, Any], positions: Iterable[Mapping[str, Any]], *, cycle_id: str) -> dict[str, Any] | None:
    position_id = str(event.get("position_id") or "")
    order_id = str(event.get("order_id") or "")
    symbol = str(event.get("symbol") or "")
    side = str(event.get("side") or "").upper()
    rows = [dict(p) for p in positions]
    if position_id:
        for pos in rows:
            if _row_position_id(pos) == position_id:
                return pos
    if order_id:
        for pos in rows:
            meta = _metadata_of(pos)
            if str(pos.get("order_id") or meta.get("order_id") or "") == order_id:
                return pos
    scored: list[tuple[int, dict[str, Any]]] = []
    for pos in rows:
        score = 0
        if _is_position_open(pos):
            score += 2
        if _is_second_lsr_v2_position(pos, cycle_id=cycle_id):
            score += 5
        if cycle_id and _row_cycle(pos) == cycle_id:
            score += 3
        if symbol and _row_symbol(pos) == symbol:
            score += 2
        if side and _row_side(pos) == side:
            score += 1
        if score >= 6:
            scored.append((score, pos))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    return None


def _close_reason(event: Mapping[str, Any]) -> str:
    if _safe_bool(event.get("take_profit_hit_diagnostic"), False):
        return "TAKE_PROFIT_HIT_DIAGNOSTIC"
    if _safe_bool(event.get("stop_hit_diagnostic"), False):
        return "STOP_LOSS_HIT_DIAGNOSTIC"
    if _safe_bool(event.get("close_required_diagnostic"), False):
        return "CLOSE_REQUIRED_DIAGNOSTIC"
    return "CLOSE_NOT_REQUIRED"


@dataclass(frozen=True)
class LSRV2SecondTradeClosePreflightSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    monitor_report_name: str = MONITOR_REPORT_NAME
    monitor_jsonl_name: str = MONITOR_JSONL_NAME
    lifecycle_report_name: str = LIFECYCLE_REPORT_NAME
    lifecycle_jsonl_name: str = LIFECYCLE_JSONL_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    max_event_lines: int = 50000
    max_positions: int = 1
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def second_close_preflight_env_state(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ
    close_enabled = str(env.get(CLOSE_PREFLIGHT_ENABLE_ENV, "")).strip() == "1"
    confirmation_ok = str(env.get(CLOSE_PREFLIGHT_CONFIRM_ENV, "")).strip() == CLOSE_PREFLIGHT_CONFIRMATION
    return {
        "close_enabled": bool(close_enabled),
        "close_confirmation_ok": bool(confirmation_ok),
        "close_preflight_env": CLOSE_PREFLIGHT_ENABLE_ENV,
        "close_preflight_confirmation_env": CLOSE_PREFLIGHT_CONFIRM_ENV,
    }


def build_lsr_v2_second_trade_close_preflight_event(
    *,
    monitor_event: Mapping[str, Any],
    position: Mapping[str, Any] | None,
    env_state: Mapping[str, Any] | None = None,
    settings: LSRV2SecondTradeClosePreflightSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeClosePreflightSettings()
    env_state = dict(env_state or second_close_preflight_env_state())
    position = dict(position or {})
    position_found = bool(position)
    position_open = bool(position and _is_position_open(position))
    close_required = _safe_bool(monitor_event.get("close_required_diagnostic"), False)
    reason = _close_reason(monitor_event)
    symbol = str(monitor_event.get("symbol") or _row_symbol(position) or "")
    side = str(monitor_event.get("side") or _row_side(position) or "").upper()
    order_id = str(monitor_event.get("order_id") or position.get("order_id") or _metadata_of(position).get("order_id") or "")
    position_id = str(monitor_event.get("position_id") or _row_position_id(position) or "")
    would_prepare_close = bool(close_required and position_found and position_open)
    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": str(monitor_event.get("cycle_id") or _row_cycle(position) or ""),
        "source": "lsr_v2_second_open_position_monitor",
        "profile_name": str(monitor_event.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(monitor_event.get("selected_overlay_id") or settings.selected_overlay_id),
        "order_id": order_id,
        "position_id": position_id,
        "symbol": symbol,
        "side": side,
        "current_status": str(monitor_event.get("current_status") or _status_text(position, "UNKNOWN")),
        "position_found": bool(position_found),
        "position_open": bool(position_open),
        "second_trade_position_open": bool(position_open),
        "entry_price": _round(monitor_event.get("entry_price") or position.get("entry_price")),
        "current_price": _round(monitor_event.get("current_price") or position.get("current_price") or position.get("mark_price") or position.get("price")),
        "stop_loss": _round(monitor_event.get("stop_loss") or position.get("stop_loss")),
        "take_profit": _round(monitor_event.get("take_profit") or position.get("take_profit")),
        "position_size": _round(monitor_event.get("position_size") or position.get("position_size") or position.get("qty") or position.get("quantity") or position.get("size")),
        "notional": _round(monitor_event.get("notional") or position.get("notional")),
        "risk_amount": _round(monitor_event.get("risk_amount") or position.get("risk_amount")),
        "unrealized_pnl": _round(monitor_event.get("unrealized_pnl") or position.get("unrealized_pnl")),
        "risk_multiple_current": monitor_event.get("risk_multiple_current"),
        "stop_hit_diagnostic": _safe_bool(monitor_event.get("stop_hit_diagnostic"), False),
        "take_profit_hit_diagnostic": _safe_bool(monitor_event.get("take_profit_hit_diagnostic"), False),
        "close_required_diagnostic": bool(close_required),
        "close_reason": reason,
        "close_enabled": bool(env_state.get("close_enabled", False)),
        "close_confirmation_ok": bool(env_state.get("close_confirmation_ok", False)),
        "would_prepare_close": bool(would_prepare_close),
        "would_close_position": False,
        "broker_close_called": False,
        "orders_submitted_by_second_trade_close_preflight": 0,
        "positions_closed_by_second_trade_close_preflight": 0,
        "positions_opened_by_second_trade_close_preflight": 0,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }


def build_lsr_v2_second_trade_close_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondTradeClosePreflightSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeClosePreflightSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    selected_cycle_id = _select_cycle_id(data_dir=base, requested_cycle_id=cycle_id, settings=settings)
    monitor_report = _read_json(base / settings.monitor_report_name)
    lifecycle_report = _read_json(base / settings.lifecycle_report_name)
    state = _read_json(base / settings.paper_state_name)
    status = _read_json(base / settings.paper_status_name)
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    monitor_events = _select_monitor_events(data_dir=base, cycle_id=selected_cycle_id, settings=settings)
    env_state = second_close_preflight_env_state()

    preflight_events: list[dict[str, Any]] = []
    for monitor_event in monitor_events:
        position = _find_matching_position(monitor_event, positions, cycle_id=selected_cycle_id)
        preflight_events.append(build_lsr_v2_second_trade_close_preflight_event(
            monitor_event=monitor_event,
            position=position,
            env_state=env_state,
            settings=settings,
        ))

    _write_jsonl_replace(base / settings.jsonl_name, preflight_events)
    report = summarize_lsr_v2_second_trade_close_preflight(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        monitor_report=monitor_report,
        lifecycle_report=lifecycle_report,
        monitor_events=monitor_events,
        preflight_events=preflight_events,
        state=state,
        status=status,
        positions=positions,
        env_state=env_state,
        settings=settings,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def summarize_lsr_v2_second_trade_close_preflight(
    *,
    data_dir: str | Path,
    cycle_id: str,
    monitor_report: Mapping[str, Any],
    lifecycle_report: Mapping[str, Any],
    monitor_events: Iterable[Mapping[str, Any]],
    preflight_events: Iterable[Mapping[str, Any]],
    state: Mapping[str, Any],
    status: Mapping[str, Any],
    positions: Iterable[Mapping[str, Any]],
    env_state: Mapping[str, Any],
    settings: LSRV2SecondTradeClosePreflightSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeClosePreflightSettings(data_dir=str(data_dir))
    rows = [dict(e) for e in preflight_events]
    mon_rows = [dict(e) for e in monitor_events]
    position_rows = [dict(p) for p in positions]
    open_lsr_positions = [p for p in position_rows if _is_position_open(p) and _is_second_lsr_v2_position(p, cycle_id=cycle_id)]
    status_open_positions = _safe_int(status.get("open_positions"), 0)
    status_pending_orders = _safe_int(status.get("pending_orders"), 0)

    found_rows = [r for r in rows if _safe_bool(r.get("position_found"), False)]
    open_rows = [r for r in rows if _safe_bool(r.get("position_open"), False)]
    close_required_rows = [r for r in rows if _safe_bool(r.get("close_required_diagnostic"), False)]
    tp_rows = [r for r in rows if _safe_bool(r.get("take_profit_hit_diagnostic"), False)]
    stop_rows = [r for r in rows if _safe_bool(r.get("stop_hit_diagnostic"), False)]
    prepare_rows = [r for r in rows if _safe_bool(r.get("would_prepare_close"), False)]
    close_enabled = bool(env_state.get("close_enabled", False))
    close_confirmation_ok = bool(env_state.get("close_confirmation_ok", False))

    paper_state_consistency = bool(monitor_report.get("paper_state_consistency", False) or lifecycle_report.get("paper_state_consistency", False)) and len(open_lsr_positions) == max(len(open_rows), 0)
    paper_status_consistency = bool(monitor_report.get("paper_status_consistency", False) or lifecycle_report.get("paper_status_consistency", False)) and status_open_positions == len(open_lsr_positions)

    blockers: list[str] = []
    if not mon_rows:
        blockers.append("second_open_position_monitor_missing")
    if close_required_rows and not found_rows:
        blockers.append("matching_second_position_not_found")
    if close_required_rows and not open_rows:
        blockers.append("matching_second_position_not_open")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if status_pending_orders > 0:
        blockers.append("paper_status_pending_orders_nonzero")
    if len(open_lsr_positions) > settings.max_positions:
        blockers.append("max_positions_exceeded")

    safety_violation = any(
        _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        or _safe_bool(e.get("broker_close_called"), False)
        or _safe_int(e.get("orders_submitted_by_second_trade_close_preflight"), 0) > 0
        or _safe_int(e.get("positions_closed_by_second_trade_close_preflight"), 0) > 0
        or _safe_int(e.get("positions_opened_by_second_trade_close_preflight"), 0) > 0
        for e in rows
    )
    if safety_violation:
        blockers.append("second_trade_close_preflight_safety_violation_detected")

    if safety_violation or len(open_lsr_positions) > settings.max_positions:
        decision = REJECT_DECISION
        status_text = "FAIL" if safety_violation else "WARN"
    elif close_required_rows and (not found_rows or not open_rows):
        decision = POSITION_NOT_FOUND_DECISION
        status_text = "WARN"
    elif not paper_state_consistency or not paper_status_consistency or status_pending_orders > 0:
        decision = STATE_INCONSISTENT_DECISION
        status_text = "WARN"
    elif close_required_rows and prepare_rows:
        decision = READY_DECISION
        status_text = "PASS"
    else:
        decision = CLOSE_NOT_REQUIRED_DECISION
        status_text = "WARN"

    def _map_float(key: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for row in rows:
            sym = str(row.get("symbol") or "")
            if sym:
                out[sym] = _round(row.get(key))
        return out

    close_reasons = sorted({str(r.get("close_reason") or "") for r in rows if r.get("close_reason")})
    total_risk = _round(sum(_safe_float(r.get("risk_amount"), 0.0) for r in prepare_rows))
    total_notional = _round(sum(_safe_float(r.get("notional"), 0.0) for r in prepare_rows))

    safety_checks = {
        "no_new_order_by_second_trade_close_preflight": True,
        "no_new_position_by_second_trade_close_preflight": True,
        "no_close_by_second_trade_close_preflight": True,
        "no_broker_submit_by_second_trade_close_preflight": True,
        "no_broker_close_by_second_trade_close_preflight": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
        "automatic_close_disabled": True,
        "automatic_reentry_disabled": True,
        "max_positions_check": len(open_lsr_positions) <= settings.max_positions,
    }

    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_SECOND_TRADE_CLOSE_PREFLIGHT",
            "SECOND_TRADE_CLOSE_BOUNDARY",
        ] + (["CLOSE_REQUIRED_DIAGNOSTIC"] if close_required_rows else ["CLOSE_NOT_REQUIRED"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": "second_open_position_monitor_jsonl",
        "strict_cycle_scope": True,
        "monitor_decision": monitor_report.get("decision"),
        "monitor_events": len(mon_rows),
        "close_preflight_events": len(rows),
        "open_second_lsr_v2_position_count": len(open_lsr_positions),
        "open_lsr_v2_position_count": len(open_lsr_positions),
        "position_found_count": len(found_rows),
        "position_open_count": len(open_rows),
        "close_required_diagnostic_count": len(close_required_rows),
        "take_profit_hit_diagnostic_count": len(tp_rows),
        "stop_hit_diagnostic_count": len(stop_rows),
        "would_prepare_close_count": len(prepare_rows),
        "would_close_position_count": 0,
        "broker_close_called": False,
        "close_enabled": bool(close_enabled),
        "close_confirmation_ok": bool(close_confirmation_ok),
        "paper_state_consistency": bool(paper_state_consistency),
        "paper_status_consistency": bool(paper_status_consistency),
        "paper_status_open_positions": status_open_positions,
        "paper_status_pending_orders": status_pending_orders,
        "state_open_lsr_v2_positions": len(open_lsr_positions),
        "symbols": sorted({str(r.get("symbol") or "") for r in rows if r.get("symbol")}),
        "sides": sorted({str(r.get("side") or "") for r in rows if r.get("side")}),
        "close_reasons": close_reasons,
        "current_prices": _map_float("current_price"),
        "entry_prices": _map_float("entry_price"),
        "stop_losses": _map_float("stop_loss"),
        "take_profits": _map_float("take_profit"),
        "unrealized_pnl_total": _round(sum(_safe_float(r.get("unrealized_pnl"), 0.0) for r in rows)),
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "orders_submitted_by_second_trade_close_preflight": 0,
        "positions_closed_by_second_trade_close_preflight": 0,
        "positions_opened_by_second_trade_close_preflight": 0,
        "broker_submit_called_by_second_trade_close_preflight": False,
        "broker_close_called_by_second_trade_close_preflight": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


__all__ = [
    "EVENT_TYPE",
    "READY_DECISION",
    "CLOSE_NOT_REQUIRED_DECISION",
    "POSITION_NOT_FOUND_DECISION",
    "STATE_INCONSISTENT_DECISION",
    "REJECT_DECISION",
    "LSRV2SecondTradeClosePreflightSettings",
    "build_lsr_v2_second_trade_close_preflight_event",
    "build_lsr_v2_second_trade_close_preflight_report_from_files",
    "second_close_preflight_env_state",
]
