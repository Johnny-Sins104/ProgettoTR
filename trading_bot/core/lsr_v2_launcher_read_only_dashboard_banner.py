"""Prompt 29.4.4t-4 — LSR-v2 launcher read-only dashboard banner/footer wiring.

Read-only visibility wiring for the launcher path.  This module reads the
validated LSR-v2 dashboard/lifecycle artifacts and prepares a console banner for
``avvia_bot_live.py``.  It deliberately does not submit or close orders, mutate
paper_state/paper_status, start schedulers, or send Telegram/network messages.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t-4"
EVENT_TYPE = "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER"
REPORT_NAME = "lsr_v2_launcher_read_only_dashboard_banner_report.json"
JSONL_NAME = "lsr_v2_launcher_read_only_dashboard_banner.jsonl"

LAUNCHER_PREFLIGHT_REPORT_NAME = "lsr_v2_launcher_read_only_visibility_preflight_report.json"
ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

LAUNCHER_PREFLIGHT_PASS_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_VISIBILITY_PREFLIGHT_READY"
ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY"
REPORTS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_BANNER_REPORTS_NOT_READY"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_BANNER_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_BANNER_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_LAUNCHER_BANNER_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = ("ARM", "EXECUTE", "ENABLE", "CONFIRMATION", "MAX_POSITIONS")


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


def _row_status(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _row_source(row: Mapping[str, Any]) -> str:
    meta = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
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


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    text = " ".join(
        [
            _row_source(row),
            str(row.get("profile_name") or meta.get("profile_name") or ""),
            str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
            str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
        ]
    ).upper()
    return "LSR_V2" in text or "LIQUIDITY_SWEEP_REVERSAL" in text


def _is_open_position(row: Mapping[str, Any]) -> bool:
    status = _row_status(row, "OPEN")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}:
        return False
    return _safe_bool(row.get("open"), True)


def _is_pending_order(row: Mapping[str, Any]) -> bool:
    status = _row_status(row, "")
    if status in {"", "CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED", "FILLED"}:
        return False
    return _safe_bool(row.get("pending"), True)


def _pass_report(report: Mapping[str, Any], decision: str) -> bool:
    return report.get("status") == "PASS" and report.get("decision") == decision


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


def _state_status_snapshot(paper_state: Mapping[str, Any], paper_status: Mapping[str, Any]) -> dict[str, Any]:
    positions = _collection_rows(paper_state.get("positions"), id_field="position_id")
    orders = _collection_rows(paper_state.get("orders"), id_field="order_id")
    open_lsr_positions = [row for row in positions if _is_lsr_v2_row(row) and _is_open_position(row)]
    pending_lsr_orders = [row for row in orders if _is_lsr_v2_row(row) and _is_pending_order(row)]
    status_open = _safe_int(paper_status.get("open_positions"), len(open_lsr_positions))
    status_pending = _safe_int(paper_status.get("pending_orders"), len(pending_lsr_orders))
    return {
        "open_lsr_v2_positions_after": len(open_lsr_positions),
        "pending_lsr_v2_orders_after": len(pending_lsr_orders),
        "open_positions_after": status_open,
        "pending_orders_after": status_pending,
        "paper_status_open_positions_after": status_open,
        "paper_status_pending_orders_after": status_pending,
        "flat_state_confirmed": len(open_lsr_positions) == 0 and status_open == 0,
        "pending_orders_clear": len(pending_lsr_orders) == 0 and status_pending == 0,
        "paper_state_status_consistency": len(open_lsr_positions) == status_open and len(pending_lsr_orders) == status_pending,
        "balance_after": _safe_float(paper_state.get("balance"), _safe_float(paper_status.get("equity"), 0.0)),
        "realized_pnl_after": _safe_float(paper_state.get("realized_pnl"), 0.0),
    }


@dataclass(frozen=True)
class LauncherDashboardBannerSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    fail_closed: bool = True
    print_banner: bool = True

    @property
    def report_path(self) -> Path:
        return Path(self.data_dir) / self.report_name

    @property
    def jsonl_path(self) -> Path:
        return Path(self.data_dir) / self.jsonl_name


def _fmt_bool(value: bool) -> str:
    return "YES" if value else "NO"


def _fmt_float(value: Any, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "0.0000"


def _build_banner_text(snapshot: Mapping[str, Any]) -> str:
    visual_bar = str(snapshot.get("visual_sl_tp_progress_bar") or "SL ? TP")
    lines = [
        "[LSR-V2 LAUNCHER DASHBOARD] READ-ONLY",
        f"state={snapshot.get('lifecycle_state') or 'UNKNOWN'} mode={snapshot.get('dashboard_mode') or 'UNKNOWN'}",
        (
            f"dashboard_ready={str(snapshot.get('telegram_dashboard_ready')).lower()} "
            f"lifecycle_ready={str(snapshot.get('lifecycle_auto_monitor_ready')).lower()} "
            f"engine_hook_ready={str(snapshot.get('engine_hook_ready')).lower()}"
        ),
        f"trades={snapshot.get('submit_execution_events_total', 0)} submitted / {snapshot.get('close_execution_events_total', 0)} closed",
        f"balance={_fmt_float(snapshot.get('balance_after'))} aggregate_pnl={_fmt_float(snapshot.get('aggregate_realized_pnl'))}",
        f"SL/TP: {visual_bar}",
        (
            f"flat={_fmt_bool(bool(snapshot.get('flat_state_confirmed')))} "
            f"pending={snapshot.get('paper_status_pending_orders_after', 0)} "
            f"fourth_locked={_fmt_bool(bool(snapshot.get('fourth_trade_locked')))} "
            f"stability_lock={_fmt_bool(bool(snapshot.get('stability_lock_active')))}"
        ),
        (
            f"telegram_send={_fmt_bool(bool(snapshot.get('telegram_send_allowed')))} "
            f"network={_fmt_bool(bool(snapshot.get('telegram_network_called')))} "
            f"scheduler={_fmt_bool(bool(snapshot.get('scheduler_started')))}"
        ),
        (
            f"live/testnet/exchange={_fmt_bool(bool(snapshot.get('live_enabled')))}"
            f"/{_fmt_bool(bool(snapshot.get('testnet_enabled')))}"
            f"/{_fmt_bool(bool(snapshot.get('exchange_broker_enabled')))}"
        ),
    ]
    return "\n".join(lines)


def build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files(
    *,
    data_dir: str | Path = "data",
    report_name: str = REPORT_NAME,
    jsonl_name: str = JSONL_NAME,
) -> dict[str, Any]:
    settings = LauncherDashboardBannerSettings(data_dir=str(data_dir), report_name=report_name, jsonl_name=jsonl_name)
    data = Path(data_dir)
    preflight = _read_json(data / LAUNCHER_PREFLIGHT_REPORT_NAME)
    engine_hook = _read_json(data / ENGINE_HOOK_REPORT_NAME)
    lifecycle = _read_json(data / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)

    env = _operator_env_controls()
    state = _state_status_snapshot(paper_state, paper_status)

    preflight_ready = _pass_report(preflight, LAUNCHER_PREFLIGHT_PASS_DECISION)
    engine_hook_ready = _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION)
    lifecycle_ready = _pass_report(lifecycle, LIFECYCLE_PASS_DECISION)
    dashboard_ready = _pass_report(dashboard, DASHBOARD_PASS_DECISION)
    postmortem_ready = _pass_report(postmortem, POSTMORTEM_PASS_DECISION)

    lifecycle_state = str(engine_hook.get("lifecycle_state") or lifecycle.get("lifecycle_state") or preflight.get("lifecycle_state") or "")
    dashboard_mode = str(engine_hook.get("dashboard_mode") or dashboard.get("dashboard_mode") or preflight.get("dashboard_mode") or "")
    visual_bar_ready = _safe_bool(engine_hook.get("visual_sl_tp_progress_bar_ready"), _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready"), False))
    visual_bar = str(engine_hook.get("visual_sl_tp_progress_bar") or dashboard.get("visual_sl_tp_progress_bar") or preflight.get("visual_sl_tp_progress_bar") or "")
    telegram_payload_ready = _safe_bool(engine_hook.get("telegram_payload_ready"), _safe_bool(dashboard.get("telegram_payload_ready"), False))
    telegram_update_ready = _safe_bool(engine_hook.get("telegram_update_ready"), _safe_bool(lifecycle.get("telegram_update_ready"), False))

    fourth_trade_locked = _safe_bool(engine_hook.get("fourth_trade_locked"), _safe_bool(lifecycle.get("fourth_trade_locked"), _safe_bool(postmortem.get("fourth_trade_locked"), False)))
    stability_lock_active = _safe_bool(engine_hook.get("stability_lock_active"), _safe_bool(lifecycle.get("stability_lock_active"), _safe_bool(postmortem.get("stability_lock_active"), False)))
    fourth_trade_allowed = _safe_bool(engine_hook.get("fourth_trade_allowed"), _safe_bool(lifecycle.get("fourth_trade_allowed"), _safe_bool(postmortem.get("fourth_trade_allowed"), True)))
    reentry_detected = _safe_bool(engine_hook.get("fourth_submit_or_reentry_detected"), _safe_bool(lifecycle.get("fourth_submit_or_reentry_detected"), _safe_bool(postmortem.get("fourth_submit_or_reentry_detected"), False)))

    live_enabled = _safe_bool(engine_hook.get("live_enabled"), _safe_bool(lifecycle.get("live_enabled"), _safe_bool(paper_status.get("live_enabled"), False)))
    testnet_enabled = _safe_bool(engine_hook.get("testnet_enabled"), _safe_bool(lifecycle.get("testnet_enabled"), _safe_bool(paper_status.get("testnet_enabled"), False)))
    exchange_broker_enabled = _safe_bool(engine_hook.get("exchange_broker_enabled"), _safe_bool(lifecycle.get("exchange_broker_enabled"), _safe_bool(paper_status.get("exchange_broker_enabled"), False)))
    operational_unlock_allowed = _safe_bool(engine_hook.get("operational_unlock_allowed"), _safe_bool(lifecycle.get("operational_unlock_allowed"), False))
    promotion_ready = _safe_bool(engine_hook.get("promotion_ready"), _safe_bool(lifecycle.get("promotion_ready"), False))

    reports_ready = preflight_ready and engine_hook_ready and lifecycle_ready and dashboard_ready and postmortem_ready
    state_locked = (
        state["flat_state_confirmed"]
        and state["pending_orders_clear"]
        and state["paper_state_status_consistency"]
        and lifecycle_state == "FLAT_LOCKED"
        and fourth_trade_locked
        and stability_lock_active
        and not fourth_trade_allowed
        and not reentry_detected
    )
    safety_failed = live_enabled or testnet_enabled or exchange_broker_enabled or operational_unlock_allowed or promotion_ready

    blockers: list[str] = []
    if not preflight_ready:
        blockers.append("launcher_visibility_preflight_not_ready")
    if not engine_hook_ready:
        blockers.append("engine_read_only_artifact_hook_not_ready")
    if not lifecycle_ready:
        blockers.append("lifecycle_auto_monitor_not_ready")
    if not dashboard_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if not state["flat_state_confirmed"]:
        blockers.append("paper_state_or_status_not_flat")
    if not state["pending_orders_clear"]:
        blockers.append("pending_orders_not_clear")
    if not state["paper_state_status_consistency"]:
        blockers.append("paper_state_status_inconsistent")
    if lifecycle_state != "FLAT_LOCKED" or not fourth_trade_locked or not stability_lock_active or fourth_trade_allowed:
        blockers.append("flat_lock_not_enforced")
    if reentry_detected:
        blockers.append("fourth_submit_or_reentry_detected")
    if not env["operator_env_absent"]:
        blockers.append("lsr_v2_operator_env_active")
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if operational_unlock_allowed:
        blockers.append("operational_unlock_allowed")
    if promotion_ready:
        blockers.append("promotion_ready")

    if safety_failed:
        status = "FAIL"
        decision = FAILED_DECISION
    elif not reports_ready:
        status = "WARN"
        decision = REPORTS_MISSING_DECISION
    elif not state_locked:
        status = "WARN"
        decision = STATE_NOT_LOCKED_DECISION
    elif not env["operator_env_absent"]:
        status = "WARN"
        decision = ENV_ACTIVE_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    banner_snapshot = {
        "lifecycle_state": lifecycle_state,
        "dashboard_mode": dashboard_mode,
        "engine_hook_ready": engine_hook_ready,
        "lifecycle_auto_monitor_ready": lifecycle_ready,
        "telegram_dashboard_ready": dashboard_ready,
        "telegram_payload_ready": telegram_payload_ready,
        "telegram_update_ready": telegram_update_ready,
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "visual_sl_tp_progress_bar_ready": visual_bar_ready,
        "visual_sl_tp_progress_bar": visual_bar,
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), _safe_int(engine_hook.get("submit_execution_events_total"), 0)),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), _safe_int(engine_hook.get("close_execution_events_total"), 0)),
        "aggregate_realized_pnl": _safe_float(postmortem.get("aggregate_realized_pnl"), _safe_float(engine_hook.get("aggregate_realized_pnl"), 0.0)),
        "balance_after": _safe_float(engine_hook.get("balance_after"), _safe_float(state.get("balance_after"), 0.0)),
        "fourth_trade_allowed": fourth_trade_allowed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        **state,
    }
    banner_text = _build_banner_text(banner_snapshot)

    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "LAUNCHER_READ_ONLY_DASHBOARD_BANNER",
            "READ_ONLY",
            "NO_LAUNCHER_EXECUTION_CHANGE",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
        ] + (["LAUNCHER_BANNER_READY"] if status == "PASS" else []),
        "blockers": blockers,
        "launcher_banner_ready": status == "PASS",
        "launcher_banner_print_allowed": status == "PASS",
        "launcher_banner_text": banner_text,
        "launcher_footer_text": banner_text,
        "launcher_mutation_allowed": False,
        "launcher_execution_allowed": False,
        "launcher_scheduler_allowed": False,
        "launcher_telegram_send_allowed": False,
        "launcher_visibility_preflight_ready": preflight_ready,
        "engine_hook_ready": engine_hook_ready,
        "lifecycle_auto_monitor_ready": lifecycle_ready,
        "telegram_dashboard_ready": dashboard_ready,
        "three_trade_postmortem_ready": postmortem_ready,
        "lifecycle_state": lifecycle_state,
        "dashboard_mode": dashboard_mode,
        "telegram_payload_ready": telegram_payload_ready,
        "telegram_update_ready": telegram_update_ready,
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "visual_sl_tp_progress_bar_ready": visual_bar_ready,
        "visual_sl_tp_progress_bar": visual_bar,
        "scheduler_enabled": False,
        "scheduler_started": False,
        **state,
        **env,
        "submit_execution_events_total": banner_snapshot["submit_execution_events_total"],
        "close_execution_events_total": banner_snapshot["close_execution_events_total"],
        "aggregate_realized_pnl": banner_snapshot["aggregate_realized_pnl"],
        "balance_after": banner_snapshot["balance_after"],
        "fourth_submit_or_reentry_detected": reentry_detected,
        "fourth_trade_allowed": fourth_trade_allowed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "orders_submitted_by_launcher_banner": 0,
        "positions_opened_by_launcher_banner": 0,
        "positions_closed_by_launcher_banner": 0,
        "paper_state_modified_by_launcher_banner": False,
        "paper_status_modified_by_launcher_banner": False,
        "broker_submit_called_by_launcher_banner": False,
        "broker_close_called_by_launcher_banner": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": promotion_ready,
        "recommended_next_patch": "29.4.4t-5 — Launcher/runner visibility parity audit",
        "next_step": "validate_launcher_banner_then_prepare_visibility_parity_audit",
        "settings": asdict(settings),
        "report": str(settings.report_path),
        "jsonl": str(settings.jsonl_path),
    }
    _write_json(settings.report_path, report)
    _append_jsonl(settings.jsonl_path, report)
    return report


def render_lsr_v2_launcher_banner_from_report(report: Mapping[str, Any]) -> str:
    return str(report.get("launcher_banner_text") or "")


def emit_lsr_v2_launcher_read_only_dashboard_banner(
    *,
    data_dir: str | Path = "data",
    print_func=print,
) -> dict[str, Any]:
    """Build and print the read-only LSR-v2 launcher banner.

    The function is intentionally fail-closed and non-raising for launcher use.
    It writes only its own report/jsonl audit artifacts.
    """
    try:
        report = build_lsr_v2_launcher_read_only_dashboard_banner_report_from_files(data_dir=data_dir)
    except Exception as exc:  # pragma: no cover - defensive launcher guard
        report = {
            "prompt": PROMPT_ID,
            "event_type": EVENT_TYPE,
            "status": "WARN",
            "decision": REPORTS_MISSING_DECISION,
            "launcher_banner_ready": False,
            "launcher_banner_print_allowed": False,
            "launcher_banner_text": f"[LSR-V2 LAUNCHER DASHBOARD] unavailable read-only fail-closed: {exc}",
            "telegram_send_allowed": False,
            "telegram_network_called": False,
            "scheduler_enabled": False,
            "scheduler_started": False,
            "orders_submitted_by_launcher_banner": 0,
            "positions_opened_by_launcher_banner": 0,
            "positions_closed_by_launcher_banner": 0,
            "paper_state_modified_by_launcher_banner": False,
            "paper_status_modified_by_launcher_banner": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        }
    text = render_lsr_v2_launcher_banner_from_report(report)
    if text:
        print_func(text)
    return dict(report)
