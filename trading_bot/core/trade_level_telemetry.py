"""Prompt 29.4.4s-5 trade-level telemetry export.

Diagnostic-only foundation for the next research phase.  It reconstructs a
trade-level dataset from local paper/backtest event logs and produces summary
statistics for edge forensics.  It never changes gates, risk, routing, broker
state, orders, positions, live/testnet paths, or thresholds.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable
import json
import math

from core.jsonl_utils import iter_jsonl_tail

PROMPT_ID = "29.4.4s-5"
TRADE_JSONL_NAME = "trade_level_telemetry.jsonl"
SUMMARY_REPORT_NAME = "trade_level_summary_report.json"
READY_DECISION = "TRADE_LEVEL_TELEMETRY_READY_DIAGNOSTIC"
NO_EVENT_LOG_DECISION = "KEEP_DIAGNOSTIC_NO_EVENT_LOG"
READ_ERROR_DECISION = "KEEP_DIAGNOSTIC_TRADE_LEVEL_READ_ERROR"

TRADE_CLOSE_EVENTS = {"POSITION_CLOSED", "TRADE_CLOSED", "BACKTEST_TRADE_CLOSED"}
TRADE_OPEN_EVENTS = {"POSITION_OPENED", "TRADE_OPENED", "BACKTEST_TRADE_OPENED"}
SIGNAL_EVENTS = {"SIGNAL_DETECTED", "PAPER_UNLOCK_SIGNAL"}
ORDER_EVENTS = {"PAPER_ORDER_SUBMITTED", "PAPER_ORDER_CONFIRMED", "ORDER_FILLED"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_div(num: float, den: float, default: float | None = None) -> float | None:
    try:
        if abs(float(den)) <= 1e-12:
            return default
        out = float(num) / float(den)
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def _nested_get(data: Any, *keys: str, default: Any = None) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current.get(key)
    return current


def _first_non_empty(*values: Any, default: Any = None) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def normalize_archetype(value: Any) -> str:
    text = str(value or "UNKNOWN").strip().upper().replace(" ", "_")
    return text or "UNKNOWN"


def _extract_metadata(source: dict[str, Any]) -> dict[str, Any]:
    for key in ("metadata", "order_metadata"):
        raw = source.get(key)
        if isinstance(raw, dict):
            return raw
    nested = source.get("position")
    if isinstance(nested, dict) and isinstance(nested.get("metadata"), dict):
        return nested.get("metadata") or {}
    nested = source.get("order")
    if isinstance(nested, dict) and isinstance(nested.get("metadata"), dict):
        return nested.get("metadata") or {}
    return {}


def _extract_archetype(*sources: Any) -> str:
    keys = (
        "setup_archetype",
        "archetype",
        "selected_archetype",
        "structure_archetype",
        "combination",
    )
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if source.get(key):
                return normalize_archetype(source.get(key))
        conf = source.get("confidence")
        if isinstance(conf, dict):
            found = _extract_archetype(conf)
            if found != "UNKNOWN":
                return found
        meta = source.get("metadata")
        if isinstance(meta, dict):
            found = _extract_archetype(meta)
            if found != "UNKNOWN":
                return found
    return "UNKNOWN"


def _session_bucket(ts: Any) -> str:
    if not ts:
        return "UNKNOWN"
    text = str(ts).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        hour = dt.hour
    except Exception:
        return "UNKNOWN"
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 12:
        return "EUROPE_MORNING"
    if 12 <= hour < 16:
        return "EUROPE_US_OVERLAP"
    if 16 <= hour < 21:
        return "US"
    return "LATE_US_ASIA_HANDOFF"


def _volatility_bucket(*sources: dict[str, Any]) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("volatility_bucket", "vol_bucket", "volatility_regime", "realized_vol_bucket"):
            if source.get(key):
                return str(source.get(key)).strip().upper()
        scenario = str(source.get("scenario") or "").upper()
        if "LOW_VOL" in scenario:
            return "LOW_VOL"
        if "HIGH_VOL" in scenario:
            return "HIGH_VOL"
        if "EXTREME" in scenario:
            return "EXTREME_VOL"
    return "UNKNOWN"


def _side_sign(side: str) -> int:
    return 1 if str(side).upper() == "BUY" else -1


@dataclass(frozen=True)
class TradeTelemetrySettings:
    data_dir: str = "data"
    event_log_name: str = "paper_events.jsonl"
    trade_jsonl_name: str = TRADE_JSONL_NAME
    summary_report_name: str = SUMMARY_REPORT_NAME
    max_event_lines: int = 250000
    fee_rate_default: float = 0.0004
    slippage_bps_default: float = 0.0
    spread_bps_default: float = 0.0
    cost_model: str = "conservative"
    include_open_positions: bool = True

    @classmethod
    def default(cls) -> "TradeTelemetrySettings":
        return cls()


def _position_from_event(event: dict[str, Any]) -> dict[str, Any]:
    pos = event.get("position")
    return pos if isinstance(pos, dict) else {}


def _order_from_event(event: dict[str, Any]) -> dict[str, Any]:
    order = event.get("order")
    return order if isinstance(order, dict) else {}


def _risk_amount(entry_price: float, stop_loss: float, qty: float) -> float:
    return abs(entry_price - stop_loss) * abs(qty)


def _gross_pnl(side: str, entry_price: float, exit_price: float, qty: float) -> float:
    sign = _side_sign(side)
    return sign * (exit_price - entry_price) * abs(qty)


def _build_trade_row_from_close(
    event: dict[str, Any],
    *,
    open_event: dict[str, Any] | None,
    signal_event: dict[str, Any] | None,
    order_event: dict[str, Any] | None,
    settings: TradeTelemetrySettings,
) -> dict[str, Any]:
    pos = _position_from_event(event)
    open_pos = _position_from_event(open_event or {})
    order = _order_from_event(order_event or {})
    close_meta = _extract_metadata(event)
    open_meta = _extract_metadata(open_event or {})
    order_meta = _extract_metadata(order_event or {})
    signal_conf = (signal_event or {}).get("confidence") if isinstance((signal_event or {}).get("confidence"), dict) else {}

    position_id = str(_first_non_empty(event.get("position_id"), pos.get("position_id"), (open_event or {}).get("position_id"), open_pos.get("position_id"), default=""))
    order_id = str(_first_non_empty(event.get("order_id"), pos.get("metadata", {}).get("source_order_id") if isinstance(pos.get("metadata"), dict) else None, order.get("order_id"), default=""))
    symbol = str(_first_non_empty(event.get("symbol"), pos.get("symbol"), (open_event or {}).get("symbol"), open_pos.get("symbol"), (signal_event or {}).get("symbol"), default=""))
    side = str(_first_non_empty(event.get("side"), pos.get("side"), (open_event or {}).get("side"), open_pos.get("side"), (signal_event or {}).get("side"), default="UNKNOWN")).upper()
    entry_price = _safe_float(_first_non_empty(pos.get("entry_price"), open_pos.get("entry_price"), order.get("filled_price"), order.get("requested_price"), default=0.0))
    exit_price = _safe_float(_first_non_empty(pos.get("exit_price"), event.get("exit_price"), default=0.0))
    qty = abs(_safe_float(_first_non_empty(pos.get("qty"), open_pos.get("qty"), order.get("qty"), event.get("qty"), default=0.0)))
    stop_loss = _safe_float(_first_non_empty(pos.get("stop_loss"), open_pos.get("stop_loss"), event.get("stop_loss"), default=0.0))
    take_profit = _safe_float(_first_non_empty(pos.get("take_profit"), open_pos.get("take_profit"), event.get("take_profit"), default=0.0))
    fees_paid = _safe_float(_first_non_empty(pos.get("fees_paid"), event.get("fees_paid"), default=0.0))
    realized_pnl = _safe_float(_first_non_empty(pos.get("realized_pnl"), event.get("realized_pnl"), default=0.0))
    gross = _gross_pnl(side, entry_price, exit_price, qty) if entry_price > 0 and exit_price > 0 and qty > 0 else 0.0
    if fees_paid <= 0.0 and entry_price > 0 and exit_price > 0 and qty > 0:
        fees_paid = abs(qty * entry_price) * settings.fee_rate_default + abs(qty * exit_price) * settings.fee_rate_default
    if abs(realized_pnl) <= 1e-12 and gross != 0.0:
        realized_pnl = gross - fees_paid
    risk_amount = _risk_amount(entry_price, stop_loss, qty)
    r_multiple = _safe_div(realized_pnl, risk_amount, None)
    notional = abs(qty * entry_price) if entry_price > 0 else 0.0
    pnl_pct = _safe_div(realized_pnl, notional, None)
    opened_at = str(_first_non_empty(pos.get("opened_at"), open_pos.get("opened_at"), (open_event or {}).get("ts"), default=""))
    closed_at = str(_first_non_empty(pos.get("closed_at"), event.get("ts"), default=""))
    archetype = _extract_archetype(close_meta, open_meta, order_meta, signal_event or {}, signal_conf)
    regime = str(_first_non_empty(close_meta.get("regime"), open_meta.get("regime"), order_meta.get("regime"), (signal_event or {}).get("regime"), signal_conf.get("regime"), default="UNKNOWN")).upper()
    scenario = str(_first_non_empty(close_meta.get("crypto_scenario"), open_meta.get("crypto_scenario"), order_meta.get("crypto_scenario"), (signal_event or {}).get("scenario"), default="UNKNOWN"))
    entry_type = str(_first_non_empty(close_meta.get("entry_type"), open_meta.get("entry_type"), order_meta.get("entry_type"), close_meta.get("execution_source"), open_meta.get("execution_source"), default="UNKNOWN"))
    cost_to_edge_ratio = _safe_div(fees_paid, abs(realized_pnl), None) if abs(realized_pnl) > 1e-12 else None
    return {
        "prompt": PROMPT_ID,
        "row_type": "closed_trade",
        "position_id": position_id,
        "order_id": order_id,
        "cycle_id": str(_first_non_empty(event.get("cycle_id"), pos.get("metadata", {}).get("cycle_id") if isinstance(pos.get("metadata"), dict) else None, (open_event or {}).get("cycle_id"), default="")),
        "symbol": symbol,
        "side": side,
        "archetype": archetype,
        "regime": regime,
        "scenario": scenario,
        "session_bucket": _session_bucket(opened_at or event.get("ts")),
        "volatility_bucket": _volatility_bucket(close_meta, open_meta, signal_event or {}),
        "entry_type": entry_type,
        "entry_price": round(entry_price, 10),
        "exit_price": round(exit_price, 10),
        "qty": round(qty, 12),
        "notional": round(notional, 8),
        "stop_loss": round(stop_loss, 10),
        "take_profit": round(take_profit, 10),
        "opened_at": opened_at,
        "closed_at": closed_at,
        "holding_seconds": _holding_seconds(opened_at, closed_at),
        "exit_reason": str(_first_non_empty(event.get("reason"), pos.get("close_reason"), default="UNKNOWN")).upper(),
        "gross_pnl": round(gross, 8),
        "fees_paid": round(fees_paid, 8),
        "estimated_spread_cost": round(notional * settings.spread_bps_default / 10000.0, 8),
        "estimated_slippage_cost": round(notional * settings.slippage_bps_default / 10000.0, 8),
        "net_pnl": round(realized_pnl, 8),
        "pnl_pct": round((pnl_pct or 0.0) * 100.0, 8) if pnl_pct is not None else None,
        "risk_amount": round(risk_amount, 8),
        "r_multiple": round(r_multiple, 8) if r_multiple is not None else None,
        "cost_to_edge_ratio": round(cost_to_edge_ratio, 8) if cost_to_edge_ratio is not None else None,
        "mae_r": None,
        "mfe_r": None,
        "mae_mfe_status": "UNAVAILABLE_WITHOUT_INTRATRADE_BAR_PATH",
        "source_event_type": event.get("event_type"),
        "source_event_ts": event.get("ts"),
        "diagnostic_only": True,
        "orders_submitted_by_telemetry": 0,
        "positions_opened_by_telemetry": 0,
    }


def _build_open_position_row(event: dict[str, Any], *, signal_event: dict[str, Any] | None, order_event: dict[str, Any] | None) -> dict[str, Any]:
    pos = _position_from_event(event)
    meta = _extract_metadata(event)
    signal_conf = (signal_event or {}).get("confidence") if isinstance((signal_event or {}).get("confidence"), dict) else {}
    return {
        "prompt": PROMPT_ID,
        "row_type": "open_position_snapshot",
        "position_id": str(_first_non_empty(event.get("position_id"), pos.get("position_id"), default="")),
        "order_id": str(_first_non_empty(event.get("order_id"), pos.get("metadata", {}).get("source_order_id") if isinstance(pos.get("metadata"), dict) else None, (order_event or {}).get("order_id"), default="")),
        "cycle_id": str(_first_non_empty(event.get("cycle_id"), pos.get("metadata", {}).get("cycle_id") if isinstance(pos.get("metadata"), dict) else None, default="")),
        "symbol": str(_first_non_empty(event.get("symbol"), pos.get("symbol"), default="")),
        "side": str(_first_non_empty(event.get("side"), pos.get("side"), default="UNKNOWN")).upper(),
        "archetype": _extract_archetype(meta, signal_event or {}, signal_conf),
        "regime": str(_first_non_empty(meta.get("regime"), (signal_event or {}).get("regime"), signal_conf.get("regime"), default="UNKNOWN")).upper(),
        "scenario": str(_first_non_empty(meta.get("crypto_scenario"), (signal_event or {}).get("scenario"), default="UNKNOWN")),
        "session_bucket": _session_bucket(_first_non_empty(pos.get("opened_at"), event.get("ts"), default="")),
        "volatility_bucket": _volatility_bucket(meta, signal_event or {}),
        "entry_price": round(_safe_float(pos.get("entry_price"), 0.0), 10),
        "qty": round(abs(_safe_float(pos.get("qty"), 0.0)), 12),
        "notional": round(abs(_safe_float(pos.get("qty"), 0.0) * _safe_float(pos.get("entry_price"), 0.0)), 8),
        "stop_loss": round(_safe_float(pos.get("stop_loss"), 0.0), 10),
        "take_profit": round(_safe_float(pos.get("take_profit"), 0.0), 10),
        "opened_at": str(_first_non_empty(pos.get("opened_at"), event.get("ts"), default="")),
        "status": str(pos.get("status") or "OPEN"),
        "mae_r": None,
        "mfe_r": None,
        "mae_mfe_status": "UNAVAILABLE_UNTIL_CLOSED_AND_INTRATRADE_BAR_PATH_EXPORTED",
        "diagnostic_only": True,
        "orders_submitted_by_telemetry": 0,
        "positions_opened_by_telemetry": 0,
    }


def _holding_seconds(opened_at: str, closed_at: str) -> float | None:
    if not opened_at or not closed_at:
        return None
    try:
        a = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(closed_at).replace("Z", "+00:00"))
        return round(max(0.0, (b - a).total_seconds()), 6)
    except Exception:
        return None


def _index_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    signals_by_cycle_symbol: dict[tuple[str, str], dict[str, Any]] = {}
    orders_by_order_id: dict[str, dict[str, Any]] = {}
    opens_by_position_id: dict[str, dict[str, Any]] = {}
    closes_by_position_id: dict[str, dict[str, Any]] = {}

    for event in events:
        et = str(event.get("event_type") or "")
        symbol = str(event.get("symbol") or "")
        cycle_id = str(event.get("cycle_id") or "")
        if et in SIGNAL_EVENTS and symbol:
            signals_by_cycle_symbol[(cycle_id, symbol)] = event
        if et in ORDER_EVENTS:
            order = _order_from_event(event)
            order_id = str(_first_non_empty(event.get("order_id"), order.get("order_id"), default=""))
            if order_id:
                orders_by_order_id[order_id] = event
        if et in TRADE_OPEN_EVENTS:
            pos = _position_from_event(event)
            position_id = str(_first_non_empty(event.get("position_id"), pos.get("position_id"), default=""))
            if position_id:
                opens_by_position_id[position_id] = event
        if et in TRADE_CLOSE_EVENTS:
            pos = _position_from_event(event)
            position_id = str(_first_non_empty(event.get("position_id"), pos.get("position_id"), default=""))
            if position_id:
                closes_by_position_id[position_id] = event

    return {
        "signals_by_cycle_symbol": signals_by_cycle_symbol,
        "orders_by_order_id": orders_by_order_id,
        "opens_by_position_id": opens_by_position_id,
        "closes_by_position_id": closes_by_position_id,
    }


def build_trade_rows_from_events(events: list[dict[str, Any]], settings: TradeTelemetrySettings | None = None) -> list[dict[str, Any]]:
    settings = settings or TradeTelemetrySettings.default()
    idx = _index_events(events)
    rows: list[dict[str, Any]] = []
    closed_ids: set[str] = set()

    for position_id, close_event in sorted(idx["closes_by_position_id"].items(), key=lambda kv: str(kv[1].get("ts") or "")):
        pos = _position_from_event(close_event)
        order_id = str(_first_non_empty(close_event.get("order_id"), pos.get("metadata", {}).get("source_order_id") if isinstance(pos.get("metadata"), dict) else None, default=""))
        symbol = str(_first_non_empty(close_event.get("symbol"), pos.get("symbol"), default=""))
        cycle_id = str(_first_non_empty(close_event.get("cycle_id"), pos.get("metadata", {}).get("cycle_id") if isinstance(pos.get("metadata"), dict) else None, default=""))
        open_event = idx["opens_by_position_id"].get(position_id)
        order_event = idx["orders_by_order_id"].get(order_id)
        signal_event = idx["signals_by_cycle_symbol"].get((cycle_id, symbol))
        rows.append(
            _build_trade_row_from_close(
                close_event,
                open_event=open_event,
                signal_event=signal_event,
                order_event=order_event,
                settings=settings,
            )
        )
        closed_ids.add(position_id)

    if settings.include_open_positions:
        for position_id, open_event in sorted(idx["opens_by_position_id"].items(), key=lambda kv: str(kv[1].get("ts") or "")):
            if position_id in closed_ids:
                continue
            pos = _position_from_event(open_event)
            order_id = str(_first_non_empty(open_event.get("order_id"), pos.get("metadata", {}).get("source_order_id") if isinstance(pos.get("metadata"), dict) else None, default=""))
            symbol = str(_first_non_empty(open_event.get("symbol"), pos.get("symbol"), default=""))
            cycle_id = str(_first_non_empty(open_event.get("cycle_id"), pos.get("metadata", {}).get("cycle_id") if isinstance(pos.get("metadata"), dict) else None, default=""))
            rows.append(
                _build_open_position_row(
                    open_event,
                    signal_event=idx["signals_by_cycle_symbol"].get((cycle_id, symbol)),
                    order_event=idx["orders_by_order_id"].get(order_id),
                )
            )
    return rows


def _closed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("row_type") == "closed_trade"]


def _bucket_summary(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _closed_rows(rows):
        grouped[str(row.get(field) or "UNKNOWN")].append(row)
    out: dict[str, Any] = {}
    for key, items in sorted(grouped.items()):
        r_values = [_safe_float(r.get("r_multiple"), 0.0) for r in items if r.get("r_multiple") is not None]
        pnl_values = [_safe_float(r.get("net_pnl"), 0.0) for r in items]
        wins = sum(1 for x in pnl_values if x > 0)
        losses = sum(1 for x in pnl_values if x < 0)
        breakevens = sum(1 for x in pnl_values if abs(x) <= 1e-12)
        out[key] = {
            "closed_trades": len(items),
            "net_pnl": round(sum(pnl_values), 8),
            "avg_r": round(sum(r_values) / len(r_values), 8) if r_values else None,
            "median_r": round(median(r_values), 8) if r_values else None,
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "win_ratio": round(wins / len(items), 8) if items else 0.0,
            "breakeven_ratio": round(breakevens / len(items), 8) if items else 0.0,
        }
    return out


def summarize_trade_rows(rows: list[dict[str, Any]], *, settings: TradeTelemetrySettings | None = None) -> dict[str, Any]:
    settings = settings or TradeTelemetrySettings.default()
    closed = _closed_rows(rows)
    open_rows = [r for r in rows if r.get("row_type") == "open_position_snapshot"]
    pnl_values = [_safe_float(r.get("net_pnl"), 0.0) for r in closed]
    r_values = [_safe_float(r.get("r_multiple"), 0.0) for r in closed if r.get("r_multiple") is not None]
    fees = [_safe_float(r.get("fees_paid"), 0.0) for r in closed]
    wins = sum(1 for pnl in pnl_values if pnl > 0)
    losses = sum(1 for pnl in pnl_values if pnl < 0)
    breakevens = sum(1 for pnl in pnl_values if abs(pnl) <= 1e-12)
    total_pnl = sum(pnl_values)
    total_fees = sum(fees)
    top_abs = sorted([abs(p) for p in pnl_values], reverse=True)
    top_10_count = max(1, int(math.ceil(len(top_abs) * 0.10))) if top_abs else 0
    top_10_abs_sum = sum(top_abs[:top_10_count]) if top_abs else 0.0
    total_abs_sum = sum(top_abs)
    top_trade_concentration = _safe_div(top_10_abs_sum, total_abs_sum, 0.0) or 0.0
    breakeven_drag_detected = bool(closed and breakevens / max(1, len(closed)) >= 0.45 and (not r_values or sum(r_values) / len(r_values) <= 0.0))
    cost_to_edge_ratio = _safe_div(total_fees, abs(total_pnl), None) if abs(total_pnl) > 1e-12 else None

    return {
        "prompt": PROMPT_ID,
        "status": "PASS",
        "decision": READY_DECISION,
        "ts": utc_now_iso(),
        "data_dir": settings.data_dir,
        "trade_jsonl": str(Path(settings.data_dir) / settings.trade_jsonl_name),
        "report": str(Path(settings.data_dir) / settings.summary_report_name),
        "settings": asdict(settings),
        "trade_level_rows": len(rows),
        "closed_trades": len(closed),
        "open_position_snapshots": len(open_rows),
        "orders_submitted_by_telemetry": 0,
        "positions_opened_by_telemetry": 0,
        "promotion_ready": False,
        "promotion_blockers": [
            "diagnostic_export_only",
            "requires_multi_window_cost_stress_walk_forward_oos_before_promotion",
        ],
        "summary": {
            "net_pnl": round(total_pnl, 8),
            "gross_fees": round(total_fees, 8),
            "closed_trades": len(closed),
            "wins": wins,
            "losses": losses,
            "breakevens": breakevens,
            "win_ratio": round(wins / len(closed), 8) if closed else 0.0,
            "loss_ratio": round(losses / len(closed), 8) if closed else 0.0,
            "breakeven_ratio": round(breakevens / len(closed), 8) if closed else 0.0,
            "avg_r": round(sum(r_values) / len(r_values), 8) if r_values else None,
            "median_r": round(median(r_values), 8) if r_values else None,
            "min_r": round(min(r_values), 8) if r_values else None,
            "max_r": round(max(r_values), 8) if r_values else None,
            "cost_to_edge_ratio": round(cost_to_edge_ratio, 8) if cost_to_edge_ratio is not None else None,
            "top_10_abs_pnl_concentration": round(top_trade_concentration, 8),
            "breakeven_drag_detected": breakeven_drag_detected,
        },
        "by_archetype": _bucket_summary(rows, "archetype"),
        "by_regime": _bucket_summary(rows, "regime"),
        "by_side": _bucket_summary(rows, "side"),
        "by_session": _bucket_summary(rows, "session_bucket"),
        "by_volatility_bucket": _bucket_summary(rows, "volatility_bucket"),
        "mae_mfe_note": (
            "MAE/MFE remain null unless the next backtest/paper logs export the intra-trade bar path. "
            "This patch intentionally refuses to infer MAE/MFE from entry/exit-only events."
        ),
        "safety_note": (
            "Diagnostic only: exports telemetry and summaries from existing event logs. It does not lower thresholds, "
            "route signals, call brokers, submit orders, open positions, enable live/testnet/exchange broker, or mutate paper state."
        ),
    }


def export_trade_level_telemetry(settings: TradeTelemetrySettings | None = None) -> dict[str, Any]:
    settings = settings or TradeTelemetrySettings.default()
    data_dir = Path(settings.data_dir)
    event_log = data_dir / settings.event_log_name
    if not event_log.exists():
        report = {
            "prompt": PROMPT_ID,
            "status": "WARN",
            "decision": NO_EVENT_LOG_DECISION,
            "ts": utc_now_iso(),
            "data_dir": str(data_dir),
            "event_log": str(event_log),
            "trade_jsonl": str(data_dir / settings.trade_jsonl_name),
            "report": str(data_dir / settings.summary_report_name),
            "trade_level_rows": 0,
            "closed_trades": 0,
            "orders_submitted_by_telemetry": 0,
            "positions_opened_by_telemetry": 0,
            "safety_note": "Diagnostic only; no broker/order/position state is changed.",
        }
        _write_json(data_dir / settings.summary_report_name, report)
        _write_jsonl(data_dir / settings.trade_jsonl_name, [])
        return report
    try:
        events = iter_jsonl_tail(event_log, max_lines=settings.max_event_lines, require_event_type=True)
        rows = build_trade_rows_from_events(events, settings)
        _write_jsonl(data_dir / settings.trade_jsonl_name, rows)
        report = summarize_trade_rows(rows, settings=settings)
        report["event_log"] = str(event_log)
        report["events_scanned"] = len(events)
        _write_json(data_dir / settings.summary_report_name, report)
        return report
    except Exception as exc:
        report = {
            "prompt": PROMPT_ID,
            "status": "WARN",
            "decision": READ_ERROR_DECISION,
            "ts": utc_now_iso(),
            "data_dir": str(data_dir),
            "event_log": str(event_log),
            "error": str(exc),
            "trade_level_rows": 0,
            "closed_trades": 0,
            "orders_submitted_by_telemetry": 0,
            "positions_opened_by_telemetry": 0,
            "safety_note": "Diagnostic only; no broker/order/position state is changed.",
        }
        _write_json(data_dir / settings.summary_report_name, report)
        return report
