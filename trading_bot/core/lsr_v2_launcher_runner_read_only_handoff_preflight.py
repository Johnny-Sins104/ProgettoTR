"""Prompt 29.4.4t-6 — LSR-v2 launcher/runner read-only handoff consolidation preflight.

Read-only preflight for consolidating LSR-v2 launcher and runner visibility into
one future handoff model.  This module reads existing validated artifacts and
source files only.  It does not mutate launcher/runner/engine code,
paper_state/paper_status, start schedulers, send Telegram messages, call brokers,
submit orders, close positions, unlock re-entry, or allow a fourth trade.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t-6-1"
EVENT_TYPE = "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT"
REPORT_NAME = "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json"
JSONL_NAME = "lsr_v2_launcher_runner_read_only_handoff_preflight.jsonl"

PARITY_REPORT_NAME = "lsr_v2_launcher_runner_visibility_parity_audit_report.json"
LAUNCHER_BANNER_REPORT_NAME = "lsr_v2_launcher_read_only_dashboard_banner_report.json"
ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

PARITY_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
LAUNCHER_BANNER_PASS_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY"
ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY"
REPORTS_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_READ_ONLY_HANDOFF_REPORTS_NOT_READY"
SOURCE_MARKERS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_READ_ONLY_HANDOFF_SOURCE_MARKERS_MISSING"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_READ_ONLY_HANDOFF_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_READ_ONLY_HANDOFF_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_READ_ONLY_HANDOFF_PREFLIGHT_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = ("ARM", "EXECUTE", "ENABLE", "CONFIRMATION", "MAX_POSITIONS", "REARM")

_SOURCE_MARKERS: dict[str, tuple[str, ...]] = {
    "trading_bot/avvia_bot_live.py": (
        "lsr_v2_launcher_read_only_dashboard_banner",
        "LSR-V2 LAUNCHER DASHBOARD",
    ),
    "avvia_bot_live.bat": (
        "LSR-v2",
        "read-only",
    ),
    # Hotfix 29.4.4t-6-1: some validated runner files expose the CLI hook
    # through the argparse flag only, without a literal "run_paper_trading"
    # symbol in source text.  The flag is the stable handoff marker.
    "trading_bot/run_paper_trading.py": (
        "no-lsr-v2-engine-read-only-artifact-hook",
    ),
    "trading_bot/core/paper_engine.py": (
        "lsr_v2_engine_read_only_artifact_hook",
        "write_lsr_v2_engine_read_only_artifact_hook_report",
    ),
    "trading_bot/core/paper_once_runner_footer.py": (
        "load_lsr_v2_engine_artifact_hook_footer_summary",
        "LSR_V2_ENGINE_ARTIFACT_HOOK_REPORT_NAME",
    ),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "ready", "pass", "open"}:
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
        if not any(marker in upper for marker in _OPERATOR_ENV_MARKERS):
            continue
        if str(value).strip() in {"", "0", "false", "False", "no", "NO", "off", "OFF"}:
            continue
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


def _scan_source_markers(project_root: Path) -> dict[str, Any]:
    missing_files: list[str] = []
    missing_markers: dict[str, list[str]] = {}
    for rel, markers in _SOURCE_MARKERS.items():
        path = project_root / rel
        if not path.exists():
            missing_files.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        missing = [marker for marker in markers if marker not in text]
        if missing:
            missing_markers[rel] = missing
    return {
        "handoff_source_files_present": not missing_files,
        "handoff_required_markers_present": not missing_markers,
        "missing_handoff_source_files": missing_files,
        "missing_handoff_source_markers": missing_markers,
    }


@dataclass(frozen=True)
class LauncherRunnerReadOnlyHandoffPreflightSettings:
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


def _handoff_plan() -> dict[str, Any]:
    return {
        "handoff_plan_ready": True,
        "handoff_plan_phase": "READ_ONLY_CONSOLIDATION_PREFLIGHT",
        "handoff_inputs": [
            "launcher_banner_report",
            "runner_footer_model",
            "engine_read_only_artifact_hook_report",
            "lifecycle_auto_monitor_report",
            "telegram_dashboard_report",
            "three_trade_postmortem_report",
            "paper_state",
            "paper_status",
        ],
        "future_handoff_targets": [
            "avvia_bot_live.py launcher visibility path",
            "run_paper_trading.py --once footer path",
            "paper_engine.py artifact hook path",
        ],
        "blocked_until_explicit_unlock_patch": [
            "fourth_trade_rearm",
            "candidate_routing_execution",
            "broker_submit",
            "broker_close",
            "telegram_network_send",
            "scheduler_start",
        ],
    }


def build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    report_name: str = REPORT_NAME,
    jsonl_name: str = JSONL_NAME,
) -> dict[str, Any]:
    settings = LauncherRunnerReadOnlyHandoffPreflightSettings(
        data_dir=str(data_dir), project_root=str(project_root), report_name=report_name, jsonl_name=jsonl_name
    )
    data = Path(data_dir)
    root = Path(project_root)

    parity = _read_json(data / PARITY_REPORT_NAME)
    launcher = _read_json(data / LAUNCHER_BANNER_REPORT_NAME)
    engine_hook = _read_json(data / ENGINE_HOOK_REPORT_NAME)
    lifecycle = _read_json(data / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)

    env = _operator_env_controls()
    state = _state_status_snapshot(paper_state, paper_status)
    source = _scan_source_markers(root)
    plan = _handoff_plan()

    parity_ready = _pass_report(parity, PARITY_PASS_DECISION) and _safe_bool(parity.get("launcher_runner_visibility_parity_ok"), False)
    launcher_ready = _pass_report(launcher, LAUNCHER_BANNER_PASS_DECISION)
    engine_hook_ready = _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION)
    lifecycle_ready = _pass_report(lifecycle, LIFECYCLE_PASS_DECISION)
    dashboard_ready = _pass_report(dashboard, DASHBOARD_PASS_DECISION)
    postmortem_ready = _pass_report(postmortem, POSTMORTEM_PASS_DECISION)
    reports_ready = parity_ready and launcher_ready and engine_hook_ready and lifecycle_ready and dashboard_ready and postmortem_ready

    lifecycle_state = str(parity.get("lifecycle_state") or lifecycle.get("lifecycle_state") or engine_hook.get("lifecycle_state") or "")
    fourth_locked = _safe_bool(parity.get("fourth_trade_locked"), _safe_bool(postmortem.get("fourth_trade_locked"), False))
    fourth_allowed = _safe_bool(parity.get("fourth_trade_allowed"), _safe_bool(postmortem.get("fourth_trade_allowed"), True))
    stability_lock_active = _safe_bool(parity.get("stability_lock_active"), _safe_bool(postmortem.get("stability_lock_active"), False))
    reentry_detected = _safe_bool(parity.get("fourth_submit_or_reentry_detected"), False)

    live_enabled = _safe_bool(parity.get("live_enabled"), _safe_bool(paper_status.get("live_enabled"), False))
    testnet_enabled = _safe_bool(parity.get("testnet_enabled"), _safe_bool(paper_status.get("testnet_enabled"), False))
    exchange_broker_enabled = _safe_bool(parity.get("exchange_broker_enabled"), _safe_bool(paper_status.get("exchange_broker_enabled"), False))
    operational_unlock_allowed = _safe_bool(parity.get("operational_unlock_allowed"), False)
    promotion_ready = _safe_bool(parity.get("promotion_ready"), False)
    telegram_send_allowed = _safe_bool(parity.get("telegram_send_allowed"), False)
    telegram_network_called = _safe_bool(parity.get("telegram_network_called"), False)
    scheduler_started = _safe_bool(parity.get("scheduler_started"), False)

    state_locked = (
        lifecycle_state == "FLAT_LOCKED"
        and fourth_locked
        and not fourth_allowed
        and stability_lock_active
        and not reentry_detected
        and state["flat_state_confirmed"]
        and state["pending_orders_clear"]
        and state["paper_state_status_consistency"]
    )
    safety_failed = (
        live_enabled
        or testnet_enabled
        or exchange_broker_enabled
        or operational_unlock_allowed
        or promotion_ready
        or telegram_send_allowed
        or telegram_network_called
        or scheduler_started
    )

    blockers: list[str] = []
    if not parity_ready:
        blockers.append("visibility_parity_not_ready")
    if not launcher_ready:
        blockers.append("launcher_banner_not_ready")
    if not engine_hook_ready:
        blockers.append("engine_artifact_hook_not_ready")
    if not lifecycle_ready:
        blockers.append("lifecycle_auto_monitor_not_ready")
    if not dashboard_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if not source["handoff_source_files_present"]:
        blockers.append("handoff_source_files_missing")
    if not source["handoff_required_markers_present"]:
        blockers.append("handoff_required_markers_missing")
    if not state["flat_state_confirmed"]:
        blockers.append("paper_state_or_status_not_flat")
    if not state["pending_orders_clear"]:
        blockers.append("pending_orders_not_clear")
    if not state["paper_state_status_consistency"]:
        blockers.append("paper_state_status_inconsistent")
    if lifecycle_state != "FLAT_LOCKED" or not fourth_locked or fourth_allowed or not stability_lock_active:
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
    if telegram_send_allowed or telegram_network_called:
        blockers.append("telegram_send_or_network_active")
    if scheduler_started:
        blockers.append("scheduler_started")

    if safety_failed:
        status = "FAIL"
        decision = FAILED_DECISION
    elif not reports_ready:
        status = "WARN"
        decision = REPORTS_NOT_READY_DECISION
    elif not source["handoff_source_files_present"] or not source["handoff_required_markers_present"]:
        status = "WARN"
        decision = SOURCE_MARKERS_MISSING_DECISION
    elif not state_locked:
        status = "WARN"
        decision = STATE_NOT_LOCKED_DECISION
    elif not env["operator_env_absent"]:
        status = "WARN"
        decision = ENV_ACTIVE_DECISION
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
            "LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT",
            "READ_ONLY",
            "NO_LAUNCHER_MUTATION",
            "NO_RUNNER_MUTATION",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
        ] + (["READ_ONLY_HANDOFF_PREFLIGHT_READY"] if status == "PASS" else []),
        "blockers": blockers,
        "read_only_handoff_preflight_ready": status == "PASS",
        "handoff_consolidation_preflight_ready": status == "PASS",
        "handoff_consolidation_allowed": False,
        "launcher_handoff_allowed": False,
        "runner_handoff_allowed": False,
        "paper_engine_handoff_allowed": False,
        "engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "future_integrated_operation_allowed": False,
        "fourth_trade_rearm_allowed": False,
        "paper_only_execution_allowed": False,
        **plan,
        "parity_audit_ready": parity_ready,
        "launcher_runner_visibility_parity_ok": _safe_bool(parity.get("launcher_runner_visibility_parity_ok"), False),
        "visibility_mismatch_detected": _safe_bool(parity.get("visibility_mismatch_detected"), True),
        "launcher_banner_ready": launcher_ready,
        "runner_footer_ready": _safe_bool(parity.get("runner_footer_ready"), False),
        "engine_hook_ready": engine_hook_ready,
        "integration_preflight_ready": _safe_bool(engine_hook.get("integration_preflight_ready"), False),
        "lifecycle_auto_monitor_ready": lifecycle_ready,
        "telegram_dashboard_ready": dashboard_ready,
        "three_trade_postmortem_ready": postmortem_ready,
        "lifecycle_state": lifecycle_state,
        "dashboard_mode": str(parity.get("dashboard_mode") or launcher.get("dashboard_mode") or dashboard.get("dashboard_mode") or ""),
        "telegram_payload_ready": _safe_bool(parity.get("telegram_payload_ready"), _safe_bool(dashboard.get("telegram_payload_ready"), False)),
        "telegram_update_ready": _safe_bool(parity.get("telegram_update_ready"), _safe_bool(lifecycle.get("telegram_update_ready"), False)),
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "visual_sl_tp_progress_bar_ready": _safe_bool(parity.get("visual_sl_tp_progress_bar_ready"), False),
        "visual_sl_tp_progress_bar": str(parity.get("visual_sl_tp_progress_bar") or ""),
        **state,
        **env,
        **source,
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), _safe_int(parity.get("submit_execution_events_total"), 0)),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), _safe_int(parity.get("close_execution_events_total"), 0)),
        "aggregate_realized_pnl": _safe_float(postmortem.get("aggregate_realized_pnl"), _safe_float(parity.get("aggregate_realized_pnl"), 0.0)),
        "balance_after": _safe_float(state.get("balance_after"), _safe_float(postmortem.get("balance_after"), 0.0)),
        "fourth_submit_or_reentry_detected": reentry_detected,
        "fourth_trade_allowed": fourth_allowed,
        "fourth_trade_locked": fourth_locked,
        "stability_lock_active": stability_lock_active,
        "orders_submitted_by_read_only_handoff_preflight": 0,
        "positions_opened_by_read_only_handoff_preflight": 0,
        "positions_closed_by_read_only_handoff_preflight": 0,
        "paper_state_modified_by_read_only_handoff_preflight": False,
        "paper_status_modified_by_read_only_handoff_preflight": False,
        "broker_submit_called_by_read_only_handoff_preflight": False,
        "broker_close_called_by_read_only_handoff_preflight": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": promotion_ready,
        "recommended_next_patch": "29.4.4t-7 — Paper Engine LSR-v2 candidate lifecycle hook preflight",
        "next_step": "validate_read_only_handoff_then_prepare_candidate_lifecycle_hook_preflight",
        "settings": asdict(settings),
        "report": str(settings.report_path),
        "jsonl": str(settings.jsonl_path),
    }
    _write_json(settings.report_path, report)
    _append_jsonl(settings.jsonl_path, report)
    return report


def run_lsr_v2_launcher_runner_read_only_handoff_preflight(*, data_dir: str | Path = "data", project_root: str | Path = ".") -> dict[str, Any]:
    return build_lsr_v2_launcher_runner_read_only_handoff_preflight_report_from_files(data_dir=data_dir, project_root=project_root)
