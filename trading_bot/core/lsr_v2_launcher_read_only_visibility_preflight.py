"""Prompt 29.4.4t-3 — LSR-v2 launcher read-only visibility preflight.

Audit-only preflight for exposing the already validated LSR-v2 dashboard/lifecycle
artifact snapshot through the Windows launcher path. This module deliberately does
not edit the launcher, start schedulers, send Telegram messages, submit/close
orders, or mutate paper_state/paper_status. It only verifies that launcher files
and read-only artifacts are present, flat/locked, and safe for a later visibility
wiring patch.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t-3"
EVENT_TYPE = "LSR_V2_LAUNCHER_READ_ONLY_VISIBILITY_PREFLIGHT"
REPORT_NAME = "lsr_v2_launcher_read_only_visibility_preflight_report.json"
JSONL_NAME = "lsr_v2_launcher_read_only_visibility_preflight.jsonl"

ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
INTEGRATION_PREFLIGHT_REPORT_NAME = "lsr_v2_paper_engine_integration_preflight_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
INTEGRATION_PREFLIGHT_PASS_DECISION = "LSR_V2_PAPER_ENGINE_INTEGRATION_PREFLIGHT_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_VISIBILITY_PREFLIGHT_READY"
REPORTS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_VISIBILITY_REPORTS_NOT_READY"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_VISIBILITY_STATE_NOT_LOCKED"
SOURCE_MARKERS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_VISIBILITY_SOURCE_MARKERS_MISSING"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LAUNCHER_VISIBILITY_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_LAUNCHER_VISIBILITY_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = ("ARM", "EXECUTE", "ENABLE", "CONFIRMATION", "MAX_POSITIONS")

SOURCE_TARGETS = {
    "launcher_py": "trading_bot/avvia_bot_live.py",
    "launcher_bat": "avvia_bot_live.bat",
    "paper_runner": "trading_bot/run_paper_trading.py",
}

REQUIRED_SOURCE_MARKERS = {
    "launcher_py": ("paper_main", "--live", "--mode=live", "disabled"),
    "launcher_bat": ("avvia_bot_live.py", "--mode paper", "--cost-model conservative"),
    "paper_runner": ("PaperTradingEngine", "--once", "lsr-v2"),
}

LAUNCHER_VISIBILITY_PLAN = [
    {
        "phase": "29.4.4t-3",
        "name": "launcher read-only visibility preflight",
        "target": "avvia_bot_live.py / avvia_bot_live.bat",
        "action": "verify launcher can safely surface LSR-v2 read-only dashboard/lifecycle artifacts later",
        "safety": "no launcher mutation, no live/testnet, no Telegram send, no scheduler",
    },
    {
        "phase": "29.4.4t-4",
        "name": "launcher read-only banner/footer wiring",
        "target": "avvia_bot_live.py / avvia_bot_live.bat",
        "action": "print LSR-v2 flat/locked dashboard snapshot from existing artifacts before/after paper runner start",
        "safety": "visibility only; still routes to paper mode and refuses live",
    },
    {
        "phase": "29.4.4t-5",
        "name": "temporary runner deprecation map",
        "target": "isolated LSR-v2 runners",
        "action": "map diagnostic runners to engine/launcher-managed read-only artifacts before removing any scaffolds",
        "safety": "no removal until parity reports pass",
    },
]


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


def _inspect_launcher_sources(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    targets: dict[str, Any] = {}
    missing_files: list[str] = []
    missing_markers: dict[str, list[str]] = {}
    for name, rel in SOURCE_TARGETS.items():
        path = root / rel
        exists = path.exists()
        text = ""
        if exists:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                text = ""
        else:
            missing_files.append(rel)
        markers = list(REQUIRED_SOURCE_MARKERS.get(name, ()))
        absent = [marker for marker in markers if marker.lower() not in text.lower()]
        if absent:
            missing_markers[name] = absent
        lower = text.lower()
        targets[name] = {
            "path": rel,
            "exists": exists,
            "required_markers": markers,
            "missing_markers": absent,
            "lsr_v2_mentions": lower.count("lsr_v2") + lower.count("lsr-v2"),
            "paper_mode_marker_present": "--mode paper" in lower or "--mode" in lower,
            "live_refusal_marker_present": ("--live" in lower and "disabled" in lower) or "live real-money execution is disabled" in lower,
        }
    return {
        "launcher_source_targets": targets,
        "launcher_source_files_present": len(missing_files) == 0,
        "missing_launcher_source_files": missing_files,
        "launcher_required_markers_present": len(missing_markers) == 0,
        "missing_launcher_source_markers": missing_markers,
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
class LauncherVisibilityPreflightSettings:
    data_dir: str = "data"
    project_root: str = "."
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    fail_closed: bool = True

    @property
    def report_path(self) -> Path:
        return Path(self.data_dir) / self.report_name

    @property
    def jsonl_path(self) -> Path:
        return Path(self.data_dir) / self.jsonl_name


def _pass_report(report: Mapping[str, Any], decision: str) -> bool:
    return report.get("status") == "PASS" and report.get("decision") == decision


def build_lsr_v2_launcher_read_only_visibility_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    report_name: str = REPORT_NAME,
    jsonl_name: str = JSONL_NAME,
) -> dict[str, Any]:
    settings = LauncherVisibilityPreflightSettings(
        data_dir=str(data_dir),
        project_root=str(project_root),
        report_name=report_name,
        jsonl_name=jsonl_name,
    )
    data = Path(data_dir)
    engine_hook = _read_json(data / ENGINE_HOOK_REPORT_NAME)
    integration = _read_json(data / INTEGRATION_PREFLIGHT_REPORT_NAME)
    lifecycle = _read_json(data / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)

    env = _operator_env_controls()
    sources = _inspect_launcher_sources(project_root)
    snapshot = _state_status_snapshot(paper_state, paper_status)

    engine_hook_ready = _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION)
    integration_preflight_ready = _pass_report(integration, INTEGRATION_PREFLIGHT_PASS_DECISION)
    lifecycle_ready = _pass_report(lifecycle, LIFECYCLE_PASS_DECISION)
    dashboard_ready = _pass_report(dashboard, DASHBOARD_PASS_DECISION)
    postmortem_ready = _pass_report(postmortem, POSTMORTEM_PASS_DECISION)

    lifecycle_state = str(engine_hook.get("lifecycle_state") or lifecycle.get("lifecycle_state") or "")
    dashboard_mode = str(engine_hook.get("dashboard_mode") or dashboard.get("dashboard_mode") or "")
    telegram_payload_ready = _safe_bool(engine_hook.get("telegram_payload_ready"), _safe_bool(dashboard.get("telegram_payload_ready"), False))
    telegram_update_ready = _safe_bool(engine_hook.get("telegram_update_ready"), _safe_bool(lifecycle.get("telegram_update_ready"), False))
    visual_bar_ready = _safe_bool(engine_hook.get("visual_sl_tp_progress_bar_ready"), _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready"), False))
    visual_bar = str(engine_hook.get("visual_sl_tp_progress_bar") or dashboard.get("visual_sl_tp_progress_bar") or "")

    fourth_trade_locked = _safe_bool(engine_hook.get("fourth_trade_locked"), _safe_bool(lifecycle.get("fourth_trade_locked"), _safe_bool(postmortem.get("fourth_trade_locked"), False)))
    stability_lock_active = _safe_bool(engine_hook.get("stability_lock_active"), _safe_bool(lifecycle.get("stability_lock_active"), _safe_bool(postmortem.get("stability_lock_active"), False)))
    fourth_trade_allowed = _safe_bool(engine_hook.get("fourth_trade_allowed"), _safe_bool(lifecycle.get("fourth_trade_allowed"), _safe_bool(postmortem.get("fourth_trade_allowed"), True)))
    reentry_detected = _safe_bool(engine_hook.get("fourth_submit_or_reentry_detected"), _safe_bool(lifecycle.get("fourth_submit_or_reentry_detected"), _safe_bool(postmortem.get("fourth_submit_or_reentry_detected"), False)))

    live_enabled = _safe_bool(engine_hook.get("live_enabled"), _safe_bool(lifecycle.get("live_enabled"), _safe_bool(paper_status.get("live_enabled"), False)))
    testnet_enabled = _safe_bool(engine_hook.get("testnet_enabled"), _safe_bool(lifecycle.get("testnet_enabled"), _safe_bool(paper_status.get("testnet_enabled"), False)))
    exchange_broker_enabled = _safe_bool(engine_hook.get("exchange_broker_enabled"), _safe_bool(lifecycle.get("exchange_broker_enabled"), _safe_bool(paper_status.get("exchange_broker_enabled"), False)))
    operational_unlock_allowed = _safe_bool(engine_hook.get("operational_unlock_allowed"), _safe_bool(lifecycle.get("operational_unlock_allowed"), False))
    promotion_ready = _safe_bool(engine_hook.get("promotion_ready"), _safe_bool(lifecycle.get("promotion_ready"), False))

    blockers: list[str] = []
    if not engine_hook_ready:
        blockers.append("engine_read_only_artifact_hook_not_ready")
    if not integration_preflight_ready:
        blockers.append("integration_preflight_not_ready")
    if not lifecycle_ready:
        blockers.append("lifecycle_auto_monitor_not_ready")
    if not dashboard_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if not snapshot["flat_state_confirmed"]:
        blockers.append("paper_state_or_status_not_flat")
    if not snapshot["pending_orders_clear"]:
        blockers.append("pending_orders_not_clear")
    if not snapshot["paper_state_status_consistency"]:
        blockers.append("paper_state_status_inconsistent")
    if not fourth_trade_locked or not stability_lock_active or fourth_trade_allowed:
        blockers.append("stability_lock_not_enforced")
    if reentry_detected:
        blockers.append("fourth_submit_or_reentry_detected")
    if not env["operator_env_absent"]:
        blockers.append("lsr_v2_operator_env_active")
    if not sources["launcher_source_files_present"]:
        blockers.append("launcher_source_files_missing")
    if not sources["launcher_required_markers_present"]:
        blockers.append("launcher_source_markers_missing")
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

    reports_ready = engine_hook_ready and integration_preflight_ready and lifecycle_ready and dashboard_ready and postmortem_ready
    state_locked = snapshot["flat_state_confirmed"] and snapshot["pending_orders_clear"] and snapshot["paper_state_status_consistency"] and fourth_trade_locked and stability_lock_active and not fourth_trade_allowed and not reentry_detected
    sources_ready = sources["launcher_source_files_present"] and sources["launcher_required_markers_present"]
    safety_failed = live_enabled or testnet_enabled or exchange_broker_enabled or operational_unlock_allowed or promotion_ready

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
    elif not sources_ready:
        status = "WARN"
        decision = SOURCE_MARKERS_MISSING_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "LAUNCHER_VISIBILITY_PREFLIGHT",
            "READ_ONLY",
            "NO_LAUNCHER_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
        ] + (["LAUNCHER_VISIBILITY_READY"] if status == "PASS" else []),
        "blockers": blockers,
        "launcher_visibility_preflight_ready": status == "PASS",
        "launcher_visibility_allowed": False,
        "launcher_mutation_allowed": False,
        "launcher_execution_allowed": False,
        "launcher_console_wiring_allowed": False,
        "engine_hook_ready": engine_hook_ready,
        "integration_preflight_ready": integration_preflight_ready,
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
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), _safe_int(engine_hook.get("submit_execution_events_total"), 0)),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), _safe_int(engine_hook.get("close_execution_events_total"), 0)),
        "aggregate_realized_pnl": _safe_float(postmortem.get("aggregate_realized_pnl"), _safe_float(engine_hook.get("aggregate_realized_pnl"), 0.0)),
        "balance_after": _safe_float(engine_hook.get("balance_after"), _safe_float(snapshot.get("balance_after"), 0.0)),
        **snapshot,
        **env,
        **sources,
        "fourth_submit_or_reentry_detected": reentry_detected,
        "fourth_trade_allowed": fourth_trade_allowed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "orders_submitted_by_launcher_visibility_preflight": 0,
        "positions_opened_by_launcher_visibility_preflight": 0,
        "positions_closed_by_launcher_visibility_preflight": 0,
        "paper_state_modified_by_launcher_visibility_preflight": False,
        "paper_status_modified_by_launcher_visibility_preflight": False,
        "broker_submit_called_by_launcher_visibility_preflight": False,
        "broker_close_called_by_launcher_visibility_preflight": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": promotion_ready,
        "launcher_visibility_plan": LAUNCHER_VISIBILITY_PLAN,
        "recommended_next_patch": "29.4.4t-4 — Launcher read-only dashboard banner/footer wiring",
        "next_step": "prepare_launcher_read_only_banner_after_preflight_pass",
        "settings": asdict(settings),
        "report": str(settings.report_path),
        "jsonl": str(settings.jsonl_path),
    }
    _write_json(settings.report_path, report)
    _append_jsonl(settings.jsonl_path, report)
    return report
