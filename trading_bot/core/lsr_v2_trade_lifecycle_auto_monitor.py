"""Prompt 29.4.4s-10ax — LSR-v2 trade lifecycle auto monitoring.

Monitoring-only lifecycle layer for the completed three-trade LSR-v2 paper
cycle. It reads the Telegram dashboard and paper state/status artifacts to
produce a Telegram-ready lifecycle update, but it never schedules background
work, never sends Telegram messages, never submits or closes orders, never
mutates paper_state/paper_status, and never enables live/testnet/exchange
brokers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4s-10ax"
EVENT_TYPE = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR"
REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
JSONL_NAME = "lsr_v2_trade_lifecycle_auto_monitor.jsonl"

DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"
PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LIFECYCLE_DASHBOARD_NOT_READY"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LIFECYCLE_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LIFECYCLE_OPERATOR_ENV_ACTIVE"
REENTRY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LIFECYCLE_REENTRY_DETECTED"
FAILED_DECISION = "REJECT_LSR_V2_LIFECYCLE_AUTO_MONITOR_SAFETY_FAILED"

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
            str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
        ]
    ).upper()
    return "LSR_V2" in text or "LIQUIDITY_SWEEP_REVERSAL" in text


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
class LSRV2TradeLifecycleAutoMonitorSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    dashboard_report_name: str = DASHBOARD_REPORT_NAME
    postmortem_report_name: str = POSTMORTEM_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2TradeLifecycleAutoMonitorSettings":
        return cls(data_dir=data_dir)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _last_trade_card(dashboard: Mapping[str, Any]) -> dict[str, Any]:
    cards = dashboard.get("dashboard_cards")
    if isinstance(cards, Mapping):
        last = cards.get("last_trade")
        if isinstance(last, Mapping):
            return dict(last)
    return {}


def _classify_lifecycle_state(
    *,
    dashboard: Mapping[str, Any],
    postmortem: Mapping[str, Any],
    open_positions: list[Mapping[str, Any]],
    pending_orders: list[Mapping[str, Any]],
) -> str:
    progress_state = str(dashboard.get("progress_state") or "").upper()
    last_trade = _last_trade_card(dashboard)
    last_status = str(last_trade.get("status") or "").upper()
    fourth_locked = _safe_bool(dashboard.get("fourth_trade_locked") or postmortem.get("fourth_trade_locked"), False)
    stability_lock_active = _safe_bool(dashboard.get("stability_lock_active") or postmortem.get("stability_lock_active"), False)
    flat = bool(not open_positions and not pending_orders)
    if flat and fourth_locked and stability_lock_active:
        return "FLAT_LOCKED"
    if flat:
        return "CLOSED_FLAT" if last_status.startswith("CLOSED") else "FLAT"
    if progress_state == "TP_HIT_OR_BEYOND":
        return "TP_HIT"
    if progress_state == "SL_HIT_OR_BEYOND":
        return "SL_HIT"
    entry = _safe_float(last_trade.get("entry_price"), 0.0)
    current = _safe_float(last_trade.get("current_price"), 0.0)
    side = str(last_trade.get("side") or "").upper()
    if entry and current:
        in_profit = current > entry if side != "SELL" else current < entry
        if in_profit:
            return "IN_PROFIT"
    return "OPEN"


def _lifecycle_message(
    *,
    dashboard: Mapping[str, Any],
    lifecycle_state: str,
    flat_state_confirmed: bool,
    pending_orders_after: int,
) -> str:
    dashboard_text = str(dashboard.get("telegram_message_text") or "LSR-v2 Paper Dashboard")
    lines = [
        dashboard_text,
        "",
        "Lifecycle auto-monitor:",
        f"State: {lifecycle_state}",
        f"Flat: {'YES' if flat_state_confirmed else 'NO'} | Pending: {pending_orders_after}",
        "Auto action: NONE",
        "Network send: OFF",
    ]
    return "\n".join(lines)


def build_lsr_v2_trade_lifecycle_auto_monitor_report_from_files(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2TradeLifecycleAutoMonitorSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2TradeLifecycleAutoMonitorSettings.from_env(data_dir=str(data_dir))
    data = Path(data_dir)

    dashboard = _read_json(data / settings.dashboard_report_name)
    postmortem = _read_json(data / settings.postmortem_report_name)
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

    dashboard_ready = bool(dashboard.get("status") == "PASS" and dashboard.get("decision") == DASHBOARD_PASS_DECISION)
    telegram_payload_ready = _safe_bool(dashboard.get("telegram_payload_ready"), False)
    visual_progress_ready = _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready"), False)
    postmortem_ready = bool(postmortem.get("status") == "PASS" and postmortem.get("decision") == POSTMORTEM_PASS_DECISION)
    stability_lock_active = _safe_bool(dashboard.get("stability_lock_active") or postmortem.get("stability_lock_active"), False)
    fourth_trade_locked = _safe_bool(dashboard.get("fourth_trade_locked") or postmortem.get("fourth_trade_locked"), False)
    fourth_submit_or_reentry_detected = _safe_bool(
        dashboard.get("fourth_submit_or_reentry_detected") or postmortem.get("fourth_submit_or_reentry_detected"),
        False,
    )
    operator_env_absent = bool(env["operator_env_absent"])

    live_enabled = _safe_bool(dashboard.get("live_enabled") or postmortem.get("live_enabled") or status.get("live_enabled"), False)
    testnet_enabled = _safe_bool(dashboard.get("testnet_enabled") or postmortem.get("testnet_enabled") or status.get("testnet_enabled"), False)
    exchange_broker_enabled = _safe_bool(
        dashboard.get("exchange_broker_enabled") or postmortem.get("exchange_broker_enabled") or status.get("exchange_broker_enabled"),
        False,
    )
    operational_unlock_allowed = _safe_bool(
        dashboard.get("operational_unlock_allowed") or postmortem.get("operational_unlock_allowed") or status.get("operational_unlock_allowed"),
        False,
    )
    safety_ok = bool(not live_enabled and not testnet_enabled and not exchange_broker_enabled and not operational_unlock_allowed)

    lifecycle_state = _classify_lifecycle_state(
        dashboard=dashboard,
        postmortem=postmortem,
        open_positions=open_positions,
        pending_orders=pending_orders,
    )

    blockers: list[str] = []
    if not dashboard_ready or not telegram_payload_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not visual_progress_ready:
        blockers.append("visual_sl_tp_progress_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if not flat_state_confirmed:
        blockers.append("paper_state_or_status_not_flat")
    if not paper_state_status_consistency:
        blockers.append("paper_state_status_inconsistent")
    if not stability_lock_active:
        blockers.append("stability_lock_not_active")
    if not fourth_trade_locked:
        blockers.append("fourth_trade_not_locked")
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
    elif not dashboard_ready or not telegram_payload_ready or not visual_progress_ready or not postmortem_ready:
        decision = DASHBOARD_MISSING_DECISION
        status_text = "WARN"
    elif not flat_state_confirmed or not paper_state_status_consistency or not stability_lock_active or not fourth_trade_locked:
        decision = STATE_NOT_LOCKED_DECISION
        status_text = "WARN"
    else:
        decision = PASS_DECISION
        status_text = "PASS"

    lifecycle_update_ready = bool(decision == PASS_DECISION)
    telegram_update_text = _lifecycle_message(
        dashboard=dashboard,
        lifecycle_state=lifecycle_state,
        flat_state_confirmed=flat_state_confirmed,
        pending_orders_after=status_pending_orders,
    )
    dashboard_key = str(dashboard.get("telegram_message_key") or "lsr_v2_dashboard:unknown")
    lifecycle_key = f"lsr_v2_lifecycle:{lifecycle_state}:{dashboard_key}"

    report = {
        "prompt": PROMPT_ID,
        "prompt_id": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": [
            "MONITORING_ONLY",
            "AUTO_LIFECYCLE_CLASSIFICATION_READY",
            "TELEGRAM_UPDATE_READY",
            "NO_SCHEDULER",
            "NO_NETWORK_SEND",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
        ] + (["FLAT_LOCKED"] if lifecycle_state == "FLAT_LOCKED" else ["DIAGNOSTIC_REVIEW_REQUIRED"]),
        "blockers": sorted(set(blockers)),
        "lifecycle_auto_monitor_ready": bool(lifecycle_update_ready),
        "lifecycle_update_ready": bool(lifecycle_update_ready),
        "lifecycle_state": lifecycle_state,
        "lifecycle_state_sequence": ["OPEN", "IN_PROFIT", "TP_HIT", "SL_HIT", "CLOSED", "FLAT_LOCKED"],
        "telegram_update_ready": bool(lifecycle_update_ready),
        "telegram_update_mode": "single_message_upsert_ready",
        "telegram_message_key": dashboard_key,
        "telegram_lifecycle_message_key": lifecycle_key,
        "telegram_message_text": telegram_update_text,
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "telegram_message_sent": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "dashboard_ready": bool(dashboard_ready),
        "telegram_payload_ready": bool(telegram_payload_ready),
        "visual_sl_tp_progress_bar_ready": bool(visual_progress_ready),
        "visual_sl_tp_progress_bar": str(dashboard.get("visual_sl_tp_progress_bar") or ""),
        "visual_sl_tp_progress_pct": _round(dashboard.get("visual_sl_tp_progress_pct"), 4),
        "entry_to_tp_progress_pct": _round(dashboard.get("entry_to_tp_progress_pct"), 4),
        "progress_state": str(dashboard.get("progress_state") or "UNKNOWN"),
        "distance_to_take_profit": _round(dashboard.get("distance_to_take_profit"), 6),
        "distance_to_stop_loss": _round(dashboard.get("distance_to_stop_loss"), 6),
        "three_trade_postmortem_ready": bool(postmortem_ready),
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total") or dashboard.get("submit_execution_events_total"), 0),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total") or dashboard.get("close_execution_events_total"), 0),
        "aggregate_realized_pnl": _round(postmortem.get("aggregate_realized_pnl") or dashboard.get("aggregate_realized_pnl"), 10),
        "realized_pnl_after": _round(postmortem.get("realized_pnl_after") or dashboard.get("realized_pnl_after"), 10),
        "balance_after": _round(postmortem.get("balance_after") or dashboard.get("balance_after"), 10),
        "pnl_reconciliation_ok": _safe_bool(postmortem.get("pnl_reconciliation_ok") or dashboard.get("pnl_reconciliation_ok"), False),
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
        "orders_submitted_by_lifecycle_auto_monitor": 0,
        "positions_opened_by_lifecycle_auto_monitor": 0,
        "positions_closed_by_lifecycle_auto_monitor": 0,
        "broker_submit_called_by_lifecycle_auto_monitor": False,
        "broker_close_called_by_lifecycle_auto_monitor": False,
        "paper_state_modified_by_lifecycle_auto_monitor": False,
        "paper_status_modified_by_lifecycle_auto_monitor": False,
        "live_enabled": bool(live_enabled),
        "testnet_enabled": bool(testnet_enabled),
        "exchange_broker_enabled": bool(exchange_broker_enabled),
        "operational_unlock_allowed": bool(operational_unlock_allowed),
        "promotion_ready": False,
        "recommended_next_patch": "29.4.4t — Paper Engine integration planning / runner consolidation preflight",
        "settings": settings.to_dict(),
        "report": str(data / settings.report_name),
        "jsonl": str(data / settings.jsonl_name),
    }
    _write_json(data / settings.report_name, report)
    _append_jsonl(data / settings.jsonl_name, report)
    return report
