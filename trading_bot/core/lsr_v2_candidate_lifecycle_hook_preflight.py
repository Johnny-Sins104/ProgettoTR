"""Prompt 29.4.4t-7 — LSR-v2 Paper Engine candidate lifecycle hook preflight.

Read-only preflight for the next architectural step: preparing a future Paper
Engine hook that can observe LSR-v2 candidate lifecycle artifacts without
routing, submitting, closing, re-arming, scheduling, sending Telegram messages,
or mutating paper state/status.  This patch intentionally keeps the fourth
trade locked and paper-only execution disabled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t-7"
EVENT_TYPE = "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT"
REPORT_NAME = "lsr_v2_candidate_lifecycle_hook_preflight_report.json"
JSONL_NAME = "lsr_v2_candidate_lifecycle_hook_preflight.jsonl"

HANDOFF_REPORT_NAME = "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json"
PARITY_REPORT_NAME = "lsr_v2_launcher_runner_visibility_parity_audit_report.json"
ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

HANDOFF_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY"
PARITY_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY"
REPORTS_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CANDIDATE_LIFECYCLE_REPORTS_NOT_READY"
SOURCE_MARKERS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CANDIDATE_LIFECYCLE_SOURCE_MARKERS_MISSING"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CANDIDATE_LIFECYCLE_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CANDIDATE_LIFECYCLE_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = (
    "ARM",
    "EXECUTE",
    "ENABLE",
    "CONFIRMATION",
    "MAX_POSITIONS",
    "REARM",
    "UNLOCK",
    "SUBMIT",
    "CLOSE",
)

_SOURCE_MARKERS: dict[str, tuple[str, ...]] = {
    "trading_bot/core/paper_engine.py": (
        "lsr_v2_engine_read_only_artifact_hook",
        "write_lsr_v2_engine_read_only_artifact_hook_report",
    ),
    "trading_bot/run_paper_trading.py": (
        "no-lsr-v2-engine-read-only-artifact-hook",
    ),
    "trading_bot/core/lsr_v2_engine_read_only_artifact_hook.py": (
        "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK",
        "paper_engine_hook_read_only",
    ),
    "trading_bot/core/lsr_v2_trade_lifecycle_auto_monitor.py": (
        "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR",
        "lifecycle_state",
    ),
    "trading_bot/core/lsr_v2_launcher_runner_read_only_handoff_preflight.py": (
        "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT",
        "future_integrated_operation_allowed",
    ),
    "trading_bot/core/liquidity_sweep_reversal_v2.py": (
        "LIQUIDITY",
        "SWEEP",
        "REVERSAL",
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


def _source_marker_snapshot(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root)
    missing_files: list[str] = []
    missing_markers: dict[str, list[str]] = {}
    for rel, markers in _SOURCE_MARKERS.items():
        path = root / rel
        if not path.exists():
            missing_files.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            missing_files.append(rel)
            continue
        absent = [marker for marker in markers if marker not in text]
        if absent:
            missing_markers[rel] = absent
    return {
        "candidate_lifecycle_source_files_present": not missing_files,
        "candidate_lifecycle_required_markers_present": not missing_markers and not missing_files,
        "missing_candidate_lifecycle_source_files": missing_files,
        "missing_candidate_lifecycle_source_markers": missing_markers,
    }


def build_lsr_v2_candidate_lifecycle_hook_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    write: bool = True,
) -> dict[str, Any]:
    data_path = Path(data_dir)
    project_path = Path(project_root)

    handoff = _read_json(data_path / HANDOFF_REPORT_NAME)
    parity = _read_json(data_path / PARITY_REPORT_NAME)
    engine_hook = _read_json(data_path / ENGINE_HOOK_REPORT_NAME)
    lifecycle = _read_json(data_path / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data_path / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data_path / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data_path / PAPER_STATE_NAME)
    paper_status = _read_json(data_path / PAPER_STATUS_NAME)

    env = _operator_env_controls()
    state = _state_status_snapshot(paper_state, paper_status)
    sources = _source_marker_snapshot(project_path)

    handoff_ready = _pass_report(handoff, HANDOFF_PASS_DECISION) and _safe_bool(handoff.get("read_only_handoff_preflight_ready"), False)
    parity_ready = _pass_report(parity, PARITY_PASS_DECISION) and _safe_bool(parity.get("launcher_runner_visibility_parity_ok"), False)
    engine_hook_ready = _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION) and _safe_bool(engine_hook.get("engine_artifact_hook_ready"), False)
    lifecycle_ready = _pass_report(lifecycle, LIFECYCLE_PASS_DECISION) and _safe_bool(lifecycle.get("lifecycle_auto_monitor_ready"), False)
    dashboard_ready = _pass_report(dashboard, DASHBOARD_PASS_DECISION) and _safe_bool(dashboard.get("dashboard_ready"), False)
    postmortem_ready = _pass_report(postmortem, POSTMORTEM_PASS_DECISION) and _safe_bool(postmortem.get("three_trade_postmortem_complete"), False)

    lifecycle_state = str(
        lifecycle.get("lifecycle_state")
        or engine_hook.get("lifecycle_state")
        or dashboard.get("lifecycle_state")
        or handoff.get("lifecycle_state")
        or "UNKNOWN"
    )
    dashboard_mode = str(dashboard.get("dashboard_mode") or handoff.get("dashboard_mode") or "UNKNOWN")

    fourth_locked = all(
        _safe_bool(source.get("fourth_trade_locked"), False)
        for source in (handoff, parity, engine_hook, lifecycle, dashboard, postmortem)
        if source
    )
    stability_lock = all(
        _safe_bool(source.get("stability_lock_active"), False)
        for source in (handoff, parity, engine_hook, lifecycle, dashboard, postmortem)
        if source
    )
    fourth_allowed = any(
        _safe_bool(source.get("fourth_trade_allowed"), False)
        for source in (handoff, parity, engine_hook, lifecycle, dashboard, postmortem)
        if source
    )
    reentry_detected = any(
        _safe_bool(source.get("fourth_submit_or_reentry_detected"), False)
        for source in (handoff, parity, engine_hook, lifecycle, dashboard, postmortem)
        if source
    )
    telegram_send_allowed = any(
        _safe_bool(source.get("telegram_send_allowed"), False)
        for source in (handoff, parity, engine_hook, lifecycle, dashboard)
        if source
    )
    telegram_network_called = any(
        _safe_bool(source.get("telegram_network_called"), False)
        for source in (handoff, parity, engine_hook, lifecycle, dashboard)
        if source
    )
    scheduler_started = any(
        _safe_bool(source.get("scheduler_started"), False)
        for source in (handoff, parity, engine_hook, lifecycle, dashboard)
        if source
    )
    live_enabled = any(_safe_bool(source.get("live_enabled"), False) for source in (handoff, parity, engine_hook, lifecycle, dashboard, postmortem) if source)
    testnet_enabled = any(_safe_bool(source.get("testnet_enabled"), False) for source in (handoff, parity, engine_hook, lifecycle, dashboard, postmortem) if source)
    exchange_broker_enabled = any(_safe_bool(source.get("exchange_broker_enabled"), False) for source in (handoff, parity, engine_hook, lifecycle, dashboard, postmortem) if source)

    blockers: list[str] = []
    if not handoff_ready:
        blockers.append("read_only_handoff_preflight_not_ready")
    if not parity_ready:
        blockers.append("visibility_parity_not_ready")
    if not engine_hook_ready:
        blockers.append("engine_artifact_hook_not_ready")
    if not lifecycle_ready:
        blockers.append("lifecycle_auto_monitor_not_ready")
    if not dashboard_ready:
        blockers.append("telegram_dashboard_not_ready")
    if not postmortem_ready:
        blockers.append("three_trade_postmortem_not_ready")
    if not sources["candidate_lifecycle_required_markers_present"]:
        blockers.append("candidate_lifecycle_required_markers_missing")
    if not state["flat_state_confirmed"] or not state["pending_orders_clear"] or not state["paper_state_status_consistency"]:
        blockers.append("paper_state_or_status_not_flat")
    if lifecycle_state != "FLAT_LOCKED":
        blockers.append("lifecycle_state_not_flat_locked")
    if not fourth_locked:
        blockers.append("fourth_trade_not_locked")
    if not stability_lock:
        blockers.append("stability_lock_not_active")
    if fourth_allowed:
        blockers.append("fourth_trade_allowed_unexpected")
    if reentry_detected:
        blockers.append("fourth_submit_or_reentry_detected")
    if not env["operator_env_absent"]:
        blockers.append("operator_env_active")
    if telegram_send_allowed:
        blockers.append("telegram_send_allowed")
    if telegram_network_called:
        blockers.append("telegram_network_called")
    if scheduler_started:
        blockers.append("scheduler_started")
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")

    safety_failed = live_enabled or testnet_enabled or exchange_broker_enabled or telegram_send_allowed or telegram_network_called or scheduler_started
    reports_ready = handoff_ready and parity_ready and engine_hook_ready and lifecycle_ready and dashboard_ready and postmortem_ready
    source_ready = bool(sources["candidate_lifecycle_required_markers_present"])
    state_ready = bool(state["flat_state_confirmed"] and state["pending_orders_clear"] and state["paper_state_status_consistency"] and lifecycle_state == "FLAT_LOCKED")
    locks_ready = fourth_locked and stability_lock and not fourth_allowed and not reentry_detected
    env_ready = bool(env["operator_env_absent"])
    preflight_ready = reports_ready and source_ready and state_ready and locks_ready and env_ready and not safety_failed

    if safety_failed:
        status = "FAIL"
        decision = FAILED_DECISION
    elif not reports_ready:
        status = "WARN"
        decision = REPORTS_NOT_READY_DECISION
    elif not source_ready:
        status = "WARN"
        decision = SOURCE_MARKERS_MISSING_DECISION
    elif not state_ready or not locks_ready:
        status = "WARN"
        decision = STATE_NOT_LOCKED_DECISION
    elif not env_ready:
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
        "blockers": blockers,
        "classification_labels": [
            "PAPER_ENGINE_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT",
            "READ_ONLY",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            *( ["CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY"] if preflight_ready else []),
        ],
        "candidate_lifecycle_hook_preflight_ready": preflight_ready,
        "candidate_lifecycle_hook_plan_ready": reports_ready and source_ready,
        "candidate_lifecycle_hook_allowed": False,
        "engine_candidate_lifecycle_hook_allowed": False,
        "future_candidate_detection_allowed": False,
        "candidate_routing_execution_allowed": False,
        "candidate_submit_execution_allowed": False,
        "fourth_trade_rearm_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_engine_mutation_allowed": False,
        "paper_engine_candidate_hook_mutation_allowed": False,
        "handoff_preflight_ready": handoff_ready,
        "parity_audit_ready": parity_ready,
        "engine_hook_ready": engine_hook_ready,
        "lifecycle_auto_monitor_ready": lifecycle_ready,
        "telegram_dashboard_ready": dashboard_ready,
        "three_trade_postmortem_ready": postmortem_ready,
        "lifecycle_state": lifecycle_state,
        "dashboard_mode": dashboard_mode,
        "fourth_trade_allowed": fourth_allowed,
        "fourth_trade_locked": fourth_locked,
        "stability_lock_active": stability_lock,
        "fourth_submit_or_reentry_detected": reentry_detected,
        "telegram_payload_ready": _safe_bool(dashboard.get("telegram_payload_ready"), _safe_bool(lifecycle.get("telegram_payload_ready"), False)),
        "telegram_update_ready": _safe_bool(lifecycle.get("telegram_update_ready"), _safe_bool(dashboard.get("telegram_update_ready"), False)),
        "telegram_send_allowed": telegram_send_allowed,
        "telegram_network_called": telegram_network_called,
        "scheduler_enabled": any(_safe_bool(source.get("scheduler_enabled"), False) for source in (handoff, engine_hook, lifecycle, dashboard) if source),
        "scheduler_started": scheduler_started,
        "visual_sl_tp_progress_bar_ready": _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready"), _safe_bool(lifecycle.get("visual_sl_tp_progress_bar_ready"), False)),
        "visual_sl_tp_progress_bar": str(dashboard.get("visual_sl_tp_progress_bar") or lifecycle.get("visual_sl_tp_progress_bar") or ""),
        "submit_execution_events_total": max(
            _safe_int(postmortem.get("submit_execution_events_total"), 0),
            _safe_int(handoff.get("submit_execution_events_total"), 0),
            _safe_int(lifecycle.get("submit_execution_events_total"), 0),
        ),
        "close_execution_events_total": max(
            _safe_int(postmortem.get("close_execution_events_total"), 0),
            _safe_int(handoff.get("close_execution_events_total"), 0),
            _safe_int(lifecycle.get("close_execution_events_total"), 0),
        ),
        "aggregate_realized_pnl": _safe_float(postmortem.get("aggregate_realized_pnl"), _safe_float(handoff.get("aggregate_realized_pnl"), 0.0)),
        "balance_after": _safe_float(postmortem.get("balance_after"), _safe_float(handoff.get("balance_after"), state["balance_after"])),
        **state,
        **env,
        **sources,
        "orders_submitted_by_candidate_lifecycle_hook_preflight": 0,
        "positions_opened_by_candidate_lifecycle_hook_preflight": 0,
        "positions_closed_by_candidate_lifecycle_hook_preflight": 0,
        "broker_submit_called_by_candidate_lifecycle_hook_preflight": False,
        "broker_close_called_by_candidate_lifecycle_hook_preflight": False,
        "paper_state_modified_by_candidate_lifecycle_hook_preflight": False,
        "paper_status_modified_by_candidate_lifecycle_hook_preflight": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "candidate_lifecycle_hook_inputs": [
            "read_only_handoff_preflight_report",
            "visibility_parity_audit_report",
            "engine_read_only_artifact_hook_report",
            "lifecycle_auto_monitor_report",
            "telegram_dashboard_report",
            "three_trade_postmortem_report",
            "paper_state",
            "paper_status",
            "paper_engine_source",
            "run_paper_trading_source",
            "lsr_v2_candidate_source",
        ],
        "blocked_until_explicit_unlock_patch": [
            "fourth_trade_rearm",
            "candidate_routing_execution",
            "broker_submit",
            "broker_close",
            "telegram_network_send",
            "scheduler_start",
            "paper_engine_candidate_execution_hook",
        ],
        "next_step": "validate_candidate_lifecycle_hook_preflight_then_prepare_rearm_readiness_preflight",
        "recommended_next_patch": "29.4.4t-8 — LSR-v2 paper-only fourth-trade re-arm readiness preflight",
        "jsonl": str(data_path / JSONL_NAME),
        "report": str(data_path / REPORT_NAME),
    }

    if write:
        _write_json(data_path / REPORT_NAME, report)
        _append_jsonl(data_path / JSONL_NAME, report)
    return report


def run_lsr_v2_candidate_lifecycle_hook_preflight(
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
) -> dict[str, Any]:
    return build_lsr_v2_candidate_lifecycle_hook_preflight_report_from_files(
        data_dir=data_dir,
        project_root=project_root,
        write=True,
    )
