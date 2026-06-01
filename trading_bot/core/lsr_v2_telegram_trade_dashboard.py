"""Prompt 29.4.4s-10aw — LSR-v2 Telegram visual SL/TP progress bar.

Dashboard-only, read-only Telegram-ready summary for the completed three-trade
LSR-v2 paper cycle.  The module builds a single updateable Telegram message from
existing paper/report artifacts, including a visual SL/TP progress bar, but it
never sends Telegram messages, never submits orders, never closes positions,
never mutates paper_state/paper_status, and never enables live/testnet/exchange
brokers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import os

PROMPT_ID = "29.4.4s-10aw"
EVENT_TYPE = "LSR_V2_TELEGRAM_TRADE_DASHBOARD"
REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
JSONL_NAME = "lsr_v2_telegram_trade_dashboard.jsonl"

THREE_TRADE_POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
THIRD_OPEN_MONITOR_REPORT_NAME = "lsr_v2_third_open_position_monitor_report.json"
THIRD_CLOSE_PREFLIGHT_REPORT_NAME = "lsr_v2_third_trade_close_preflight_report.json"
THIRD_FINAL_AUDIT_REPORT_NAME = "lsr_v2_third_closed_trade_final_audit_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"
PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
LOCK_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_DASHBOARD_STABILITY_LOCK_MISSING"
STATE_NOT_FLAT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_DASHBOARD_STATE_NOT_FLAT"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_DASHBOARD_OPERATOR_ENV_ACTIVE"
REENTRY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_DASHBOARD_REENTRY_DETECTED"
FAILED_DECISION = "REJECT_LSR_V2_TELEGRAM_DASHBOARD_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = (
    "ARM",
    "EXECUTE",
    "ENABLE",
    "CONFIRMATION",
    "MAX_POSITIONS",
)


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


def _fmt_num(value: Any, digits: int = 4) -> str:
    number = _safe_float(value, 0.0)
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


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


def _append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), sort_keys=True) + "\n")


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
        or row.get("paper_close_source")
        or row.get("execution_source")
        or row.get("source")
        or meta.get("paper_order_source")
        or meta.get("paper_close_source")
        or meta.get("execution_source")
        or meta.get("source")
        or meta.get("closed_by")
        or ""
    )


def _row_status(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _row_status(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_pending_order(row: Mapping[str, Any]) -> bool:
    status = _row_status(row, "")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED", "FILLED"}:
        return False
    return _safe_bool(row.get("pending"), status not in {""})


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    text = " ".join(
        [
            _row_source(row),
            str(row.get("profile_name") or meta.get("profile_name") or ""),
            str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
        ]
    ).upper()
    return "LSR_V2" in text or "LIQUIDITY_SWEEP_REVERSAL" in text


def _map_get(report: Mapping[str, Any], key: str, symbol: str = "", default: Any = 0.0) -> Any:
    value = report.get(key)
    if isinstance(value, Mapping):
        if symbol and symbol in value:
            return value.get(symbol)
        if value:
            return next(iter(value.values()))
        return default
    return value if value is not None else default


def _operator_env_controls() -> dict[str, Any]:
    active: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = str(key).upper()
        if not upper.startswith(LSR_V2_OPERATOR_ENV_PREFIX):
            continue
        if any(marker in upper for marker in _OPERATOR_ENV_MARKERS):
            active[upper] = str(value)
    return {
        "active_lsr_v2_operator_env_keys": sorted(active),
        "active_lsr_v2_operator_env_count": len(active),
        "operator_env_absent": len(active) == 0,
    }


@dataclass(frozen=True)
class LSRV2TelegramTradeDashboardSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    three_trade_postmortem_report_name: str = THREE_TRADE_POSTMORTEM_REPORT_NAME
    third_open_monitor_report_name: str = THIRD_OPEN_MONITOR_REPORT_NAME
    third_close_preflight_report_name: str = THIRD_CLOSE_PREFLIGHT_REPORT_NAME
    third_final_audit_report_name: str = THIRD_FINAL_AUDIT_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2TelegramTradeDashboardSettings":
        return cls(data_dir=data_dir)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _last_trade_card(
    *,
    postmortem: Mapping[str, Any],
    monitor: Mapping[str, Any],
    preflight: Mapping[str, Any],
    final_audit: Mapping[str, Any],
) -> dict[str, Any]:
    source = preflight if preflight else monitor
    symbols = source.get("symbols") if isinstance(source.get("symbols"), list) else []
    sides = source.get("sides") if isinstance(source.get("sides"), list) else []
    symbol = str((symbols[0] if symbols else final_audit.get("symbols", [""])[0] if isinstance(final_audit.get("symbols"), list) and final_audit.get("symbols") else "") or "")
    side = str((sides[0] if sides else final_audit.get("sides", [""])[0] if isinstance(final_audit.get("sides"), list) and final_audit.get("sides") else "") or "")
    entry = _round(_map_get(source, "entry_prices", symbol, 0.0), 6)
    current = _round(_map_get(source, "current_prices", symbol, 0.0), 6)
    stop_loss = _round(_map_get(source, "stop_losses", symbol, 0.0), 6)
    take_profit = _round(_map_get(source, "take_profits", symbol, 0.0), 6)
    risk_amount = _round(source.get("total_risk_amount") or postmortem.get("total_risk_amount"), 6)
    realized = _round(final_audit.get("realized_pnl_total") or postmortem.get("third_realized_pnl"), 10)
    r_multiple = _round(realized / risk_amount, 6) if risk_amount > 0 else 0.0
    return {
        "trade_ordinal": 3,
        "cycle_id": str(final_audit.get("cycle_id") or source.get("cycle_id") or postmortem.get("third_trade_cycle_id") or ""),
        "symbol": symbol,
        "side": side,
        "status": "CLOSED_FLAT",
        "entry_price": entry,
        "current_price": current,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "realized_pnl": realized,
        "risk_amount": risk_amount,
        "realized_r_multiple": r_multiple,
        "close_reasons": list(source.get("close_reasons") or final_audit.get("close_reasons") or []),
    }




def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _price_progress_diagnostics(last_trade: Mapping[str, Any], *, width: int = 17) -> dict[str, Any]:
    """Build a Telegram-safe SL/TP visual progress card.

    The card is directional: for BUY trades progress moves from SL to TP as
    price rises; for SELL trades progress moves from SL to TP as price falls.
    Values outside the SL/TP range are clamped for the marker, while the raw
    percentages remain available for diagnostics.
    """
    side = str(last_trade.get("side") or "").upper()
    entry = _safe_float(last_trade.get("entry_price"), 0.0)
    current = _safe_float(last_trade.get("current_price"), 0.0)
    stop_loss = _safe_float(last_trade.get("stop_loss"), 0.0)
    take_profit = _safe_float(last_trade.get("take_profit"), 0.0)
    bar_width = max(5, int(width))

    distance_to_sl = abs(current - stop_loss) if stop_loss else 0.0
    distance_to_tp = abs(take_profit - current) if take_profit else 0.0
    sl_tp_range = abs(take_profit - stop_loss) if stop_loss and take_profit else 0.0
    entry_tp_range = abs(take_profit - entry) if entry and take_profit else 0.0

    range_progress_raw = 0.0
    entry_to_tp_raw = 0.0
    progress_valid = bool(sl_tp_range > 0 and entry_tp_range > 0 and current and stop_loss and take_profit)
    if progress_valid:
        if side == "SELL":
            range_progress_raw = ((stop_loss - current) / sl_tp_range) * 100.0
            entry_to_tp_raw = ((entry - current) / entry_tp_range) * 100.0
            tp_hit = current <= take_profit
            sl_hit = current >= stop_loss
        else:
            range_progress_raw = ((current - stop_loss) / sl_tp_range) * 100.0
            entry_to_tp_raw = ((current - entry) / entry_tp_range) * 100.0
            tp_hit = current >= take_profit
            sl_hit = current <= stop_loss
    else:
        tp_hit = False
        sl_hit = False

    range_progress_pct = _clamp(range_progress_raw)
    entry_to_tp_progress_pct = _clamp(entry_to_tp_raw)
    marker_index = int(round((range_progress_pct / 100.0) * (bar_width - 1))) if progress_valid else 0
    marker_index = max(0, min(bar_width - 1, marker_index))
    body = "".join("●" if idx == marker_index else "=" for idx in range(bar_width))
    bar = f"SL {body} TP"

    if not progress_valid:
        progress_state = "INSUFFICIENT_PRICE_DATA"
    elif tp_hit:
        progress_state = "TP_HIT_OR_BEYOND"
    elif sl_hit:
        progress_state = "SL_HIT_OR_BEYOND"
    else:
        progress_state = "IN_RANGE"

    return {
        "visual_sl_tp_progress_bar_ready": bool(progress_valid),
        "visual_sl_tp_progress_bar": bar,
        "visual_sl_tp_marker": "●",
        "visual_sl_tp_width": bar_width,
        "visual_sl_tp_marker_index": marker_index,
        "visual_sl_tp_progress_pct": _round(range_progress_pct, 4),
        "visual_sl_tp_progress_raw_pct": _round(range_progress_raw, 4),
        "entry_to_tp_progress_pct": _round(entry_to_tp_progress_pct, 4),
        "entry_to_tp_progress_raw_pct": _round(entry_to_tp_raw, 4),
        "distance_to_stop_loss": _round(distance_to_sl, 6),
        "distance_to_take_profit": _round(distance_to_tp, 6),
        "sl_tp_range": _round(sl_tp_range, 6),
        "entry_to_tp_range": _round(entry_tp_range, 6),
        "progress_state": progress_state,
        "tp_hit_or_beyond": bool(tp_hit),
        "sl_hit_or_beyond": bool(sl_hit),
    }

def _dashboard_message(*, postmortem: Mapping[str, Any], last_trade: Mapping[str, Any], progress: Mapping[str, Any], dashboard_mode: str) -> str:
    fourth_locked = "YES" if _safe_bool(postmortem.get("fourth_trade_locked"), False) else "NO"
    lock_active = "YES" if _safe_bool(postmortem.get("stability_lock_active"), False) else "NO"
    flat = "YES" if _safe_bool(postmortem.get("flat_state_confirmed"), False) else "NO"
    lines = [
        "LSR-v2 Paper Dashboard",
        f"Mode: {dashboard_mode}",
        f"Status: {postmortem.get('decision') or 'UNKNOWN'}",
        f"Trades: {_safe_int(postmortem.get('submit_execution_events_total'), 0)} submitted / {_safe_int(postmortem.get('close_execution_events_total'), 0)} closed",
        f"Balance: {_fmt_num(postmortem.get('balance_after'), 4)}",
        f"Aggregate PnL: {_fmt_num(postmortem.get('aggregate_realized_pnl'), 4)}",
        f"Total R: {_fmt_num(postmortem.get('total_realized_r_from_final_audits'), 4)}",
        f"Flat: {flat} | Pending: {_safe_int(postmortem.get('paper_status_pending_orders_after'), 0)}",
        f"Fourth trade locked: {fourth_locked} | Stability lock: {lock_active}",
        "",
        "Last trade:",
        f"{last_trade.get('symbol') or 'N/A'} {last_trade.get('side') or ''} — {last_trade.get('status') or 'UNKNOWN'}",
        f"Entry: {_fmt_num(last_trade.get('entry_price'), 2)} | Current: {_fmt_num(last_trade.get('current_price'), 2)}",
        f"SL: {_fmt_num(last_trade.get('stop_loss'), 2)} | TP: {_fmt_num(last_trade.get('take_profit'), 2)}",
        f"PnL: {_fmt_num(last_trade.get('realized_pnl'), 4)} | R: {_fmt_num(last_trade.get('realized_r_multiple'), 4)}",
        "",
        "SL/TP progress:",
        str(progress.get("visual_sl_tp_progress_bar") or "SL ? TP"),
        f"Current→TP: {_fmt_num(progress.get('distance_to_take_profit'), 2)} | Current→SL: {_fmt_num(progress.get('distance_to_stop_loss'), 2)}",
        f"Entry→TP: {_fmt_num(progress.get('entry_to_tp_progress_pct'), 2)}% | Range: {_fmt_num(progress.get('visual_sl_tp_progress_pct'), 2)}%",
        f"Progress state: {progress.get('progress_state') or 'UNKNOWN'}",
        "",
        "Live/Testnet/Exchange: OFF/OFF/OFF",
    ]
    return "\n".join(lines)


def build_lsr_v2_telegram_trade_dashboard_report_from_files(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2TelegramTradeDashboardSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2TelegramTradeDashboardSettings.from_env(data_dir=str(data_dir))
    data = Path(data_dir)

    postmortem = _read_json(data / settings.three_trade_postmortem_report_name)
    monitor = _read_json(data / settings.third_open_monitor_report_name)
    preflight = _read_json(data / settings.third_close_preflight_report_name)
    final_audit = _read_json(data / settings.third_final_audit_report_name)
    state = _read_json(data / settings.paper_state_name)
    status = _read_json(data / settings.paper_status_name)
    env = _operator_env_controls()

    positions = _collection_rows(state.get("positions"), id_field="position_id")
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    open_positions = [row for row in positions if _is_position_open(row)]
    open_lsr_v2_positions = [row for row in open_positions if _is_lsr_v2_row(row)]
    pending_orders = [row for row in orders if _is_pending_order(row)]

    status_open_positions = _safe_int(status.get("open_positions"), len(open_positions))
    status_pending_orders = _safe_int(status.get("pending_orders"), len(pending_orders))
    paper_state_status_consistency = bool(status_open_positions == len(open_positions) and status_pending_orders == len(pending_orders))
    flat_state_confirmed = bool(not open_positions and not open_lsr_v2_positions and status_open_positions == 0 and status_pending_orders == 0)

    postmortem_ready = bool(postmortem.get("status") == "PASS" and postmortem.get("decision") == POSTMORTEM_PASS_DECISION)
    stability_lock_active = _safe_bool(postmortem.get("stability_lock_active"), False)
    fourth_trade_locked = _safe_bool(postmortem.get("fourth_trade_locked"), False)
    fourth_submit_or_reentry_detected = _safe_bool(postmortem.get("fourth_submit_or_reentry_detected"), False)
    operator_env_absent = bool(env["operator_env_absent"])

    live_enabled = _safe_bool(postmortem.get("live_enabled") or status.get("live_enabled"), False)
    testnet_enabled = _safe_bool(postmortem.get("testnet_enabled") or status.get("testnet_enabled"), False)
    exchange_broker_enabled = _safe_bool(postmortem.get("exchange_broker_enabled") or status.get("exchange_broker_enabled"), False)
    operational_unlock_allowed = _safe_bool(postmortem.get("operational_unlock_allowed") or status.get("operational_unlock_allowed"), False)
    safety_ok = bool(not live_enabled and not testnet_enabled and not exchange_broker_enabled and not operational_unlock_allowed)

    blockers: list[str] = []
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if not stability_lock_active:
        blockers.append("stability_lock_not_active")
    if not fourth_trade_locked:
        blockers.append("fourth_trade_not_locked")
    if not flat_state_confirmed:
        blockers.append("paper_state_or_status_not_flat")
    if not paper_state_status_consistency:
        blockers.append("paper_state_status_inconsistent")
    if not operator_env_absent:
        blockers.append("lsr_v2_operator_env_still_present")
    if fourth_submit_or_reentry_detected:
        blockers.append("fourth_submit_or_reentry_detected")
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if operational_unlock_allowed:
        blockers.append("operational_unlock_allowed")

    if not safety_ok:
        decision = FAILED_DECISION
        status_text = "FAIL" if settings.fail_closed else "WARN"
    elif not operator_env_absent:
        decision = ENV_ACTIVE_DECISION
        status_text = "WARN"
    elif fourth_submit_or_reentry_detected:
        decision = REENTRY_DECISION
        status_text = "WARN"
    elif not flat_state_confirmed or not paper_state_status_consistency:
        decision = STATE_NOT_FLAT_DECISION
        status_text = "WARN"
    elif not postmortem_ready or not stability_lock_active or not fourth_trade_locked:
        decision = LOCK_MISSING_DECISION
        status_text = "WARN"
    else:
        decision = PASS_DECISION
        status_text = "PASS"

    dashboard_mode = "POST_THREE_TRADE_FLAT_LOCKED" if decision == PASS_DECISION else "DIAGNOSTIC_REVIEW_REQUIRED"
    last_trade = _last_trade_card(postmortem=postmortem, monitor=monitor, preflight=preflight, final_audit=final_audit)
    progress = _price_progress_diagnostics(last_trade)
    message = _dashboard_message(postmortem=postmortem, last_trade=last_trade, progress=progress, dashboard_mode=dashboard_mode)
    update_key = f"lsr_v2_dashboard:{dashboard_mode}:{postmortem.get('third_trade_cycle_id') or last_trade.get('cycle_id') or 'unknown'}"

    report = {
        "prompt": PROMPT_ID,
        "prompt_id": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": [
            "DASHBOARD_ONLY",
            "TELEGRAM_READY",
            "SINGLE_MESSAGE_UPSERT_READY",
            "NO_NETWORK_SEND",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
        ] + (["THREE_TRADE_FLAT_LOCKED"] if decision == PASS_DECISION else ["DIAGNOSTIC_REVIEW_REQUIRED"]),
        "blockers": sorted(set(blockers)),
        "dashboard_ready": decision == PASS_DECISION,
        "telegram_payload_ready": decision == PASS_DECISION,
        "visual_sl_tp_progress_bar_ready": bool(progress.get("visual_sl_tp_progress_bar_ready")) and decision == PASS_DECISION,
        "visual_sl_tp_progress_bar": str(progress.get("visual_sl_tp_progress_bar") or ""),
        "visual_sl_tp_progress_pct": _round(progress.get("visual_sl_tp_progress_pct"), 4),
        "entry_to_tp_progress_pct": _round(progress.get("entry_to_tp_progress_pct"), 4),
        "distance_to_take_profit": _round(progress.get("distance_to_take_profit"), 6),
        "distance_to_stop_loss": _round(progress.get("distance_to_stop_loss"), 6),
        "progress_state": str(progress.get("progress_state") or "UNKNOWN"),
        "telegram_message_text": message,
        "telegram_message_key": update_key,
        "telegram_update_mode": "single_message_upsert_ready",
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "telegram_message_sent": False,
        "dashboard_mode": dashboard_mode,
        "dashboard_cards": {
            "summary": {
                "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), 0),
                "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), 0),
                "balance_after": _round(postmortem.get("balance_after"), 10),
                "aggregate_realized_pnl": _round(postmortem.get("aggregate_realized_pnl"), 10),
                "realized_pnl_after": _round(postmortem.get("realized_pnl_after"), 10),
                "total_realized_r_from_final_audits": _round(postmortem.get("total_realized_r_from_final_audits"), 10),
            },
            "last_trade": last_trade,
            "visual_sl_tp_progress": progress,
            "lock": {
                "fourth_trade_allowed": False,
                "fourth_trade_locked": bool(fourth_trade_locked),
                "stability_lock_active": bool(stability_lock_active),
                "next_step": "telegram_visual_dashboard_then_lifecycle_monitoring_no_reentry",
            },
        },
        "three_trade_postmortem_present": bool(postmortem),
        "three_trade_postmortem_decision": str(postmortem.get("decision") or ""),
        "three_trade_postmortem_ready": bool(postmortem_ready),
        "three_trade_postmortem_complete": _safe_bool(postmortem.get("three_trade_postmortem_complete"), False),
        "three_trade_lifecycle_complete": _safe_bool(postmortem.get("three_trade_lifecycle_complete"), False),
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), 0),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), 0),
        "aggregate_realized_pnl": _round(postmortem.get("aggregate_realized_pnl"), 10),
        "realized_pnl_after": _round(postmortem.get("realized_pnl_after"), 10),
        "balance_after": _round(postmortem.get("balance_after"), 10),
        "pnl_reconciliation_ok": _safe_bool(postmortem.get("pnl_reconciliation_ok"), False),
        "open_positions_after": len(open_positions),
        "open_lsr_v2_positions_after": len(open_lsr_v2_positions),
        "pending_orders_after": len(pending_orders),
        "paper_status_open_positions_after": int(status_open_positions),
        "paper_status_pending_orders_after": int(status_pending_orders),
        "flat_state_confirmed": bool(flat_state_confirmed),
        "paper_state_status_consistency": bool(paper_state_status_consistency),
        "operator_env_controls": env,
        "operator_env_absent": bool(operator_env_absent),
        "fourth_submit_or_reentry_detected": bool(fourth_submit_or_reentry_detected),
        "fourth_trade_allowed": False,
        "fourth_trade_locked": bool(fourth_trade_locked),
        "stability_lock_active": bool(stability_lock_active),
        "automatic_reentry_enabled": False,
        "automatic_close_enabled": False,
        "orders_submitted_by_telegram_dashboard": 0,
        "positions_opened_by_telegram_dashboard": 0,
        "positions_closed_by_telegram_dashboard": 0,
        "broker_submit_called_by_telegram_dashboard": False,
        "broker_close_called_by_telegram_dashboard": False,
        "paper_state_modified_by_telegram_dashboard": False,
        "paper_status_modified_by_telegram_dashboard": False,
        "live_enabled": bool(live_enabled),
        "testnet_enabled": bool(testnet_enabled),
        "exchange_broker_enabled": bool(exchange_broker_enabled),
        "operational_unlock_allowed": bool(operational_unlock_allowed),
        "promotion_ready": False,
        "recommended_next_patch": "29.4.4s-10ax — Trade Lifecycle Auto Monitoring",
        "settings": settings.to_dict(),
        "report": str(data / settings.report_name),
        "jsonl": str(data / settings.jsonl_name),
    }
    _write_json(data / settings.report_name, report)
    _append_jsonl(data / settings.jsonl_name, report)
    return report
