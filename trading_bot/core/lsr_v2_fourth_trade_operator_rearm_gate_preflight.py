"""Prompt 29.4.4t-9 — LSR-v2 paper-only fourth-trade operator re-arm gate preflight.

Read-only/operator-gate preflight for a future explicit paper-only fourth-trade
re-arm patch. This module verifies that the validated fourth-trade re-arm
readiness preflight is complete, models the operator controls that a later
unlock patch must require, and intentionally keeps every execution permission
disabled: no candidate detection, no routing, no submit, no close, no scheduler,
no Telegram network send, no paper state/status mutation, and no live/testnet/
exchange broker.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t-9"
EVENT_TYPE = "LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT"
REPORT_NAME = "lsr_v2_fourth_trade_operator_rearm_gate_preflight_report.json"
JSONL_NAME = "lsr_v2_fourth_trade_operator_rearm_gate_preflight.jsonl"

REARM_READINESS_REPORT_NAME = "lsr_v2_fourth_trade_rearm_readiness_preflight_report.json"
CANDIDATE_HOOK_REPORT_NAME = "lsr_v2_candidate_lifecycle_hook_preflight_report.json"
HANDOFF_REPORT_NAME = "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json"
PARITY_REPORT_NAME = "lsr_v2_launcher_runner_visibility_parity_audit_report.json"
ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

REARM_READINESS_PASS_DECISION = "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY"
CANDIDATE_HOOK_PASS_DECISION = "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY"
HANDOFF_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY"
PARITY_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_READY"
REPORTS_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPERATOR_REARM_GATE_REPORTS_NOT_READY"
SOURCE_MARKERS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPERATOR_REARM_GATE_SOURCE_MARKERS_MISSING"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPERATOR_REARM_GATE_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPERATOR_REARM_GATE_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_OPERATOR_REARM_GATE_PREFLIGHT_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
OPERATOR_REARM_ENABLE_ENV = "LSR_V2_FOURTH_TRADE_REARM_ENABLE"
OPERATOR_REARM_CONFIRMATION_ENV = "LSR_V2_FOURTH_TRADE_REARM_CONFIRMATION"
OPERATOR_REARM_MAX_POSITIONS_ENV = "LSR_V2_FOURTH_TRADE_REARM_MAX_POSITIONS"
OPERATOR_REARM_CONFIRMATION_PHRASE = "I_UNDERSTAND_REARM_FOURTH_PAPER_TRADE_ONLY"
OPERATOR_REARM_MAX_POSITIONS = 1

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
    "ROUTE",
)

_SOURCE_MARKERS: dict[str, tuple[str, ...]] = {
    "trading_bot/core/lsr_v2_fourth_trade_rearm_readiness_preflight.py": (
        "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT",
        "fourth_trade_rearm_readiness_ready",
    ),
    "trading_bot/core/lsr_v2_candidate_lifecycle_hook_preflight.py": (
        "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT",
        "candidate_lifecycle_hook_allowed",
    ),
    "trading_bot/core/lsr_v2_launcher_runner_read_only_handoff_preflight.py": (
        "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT",
        "paper_only_execution_allowed",
    ),
    "trading_bot/core/lsr_v2_engine_read_only_artifact_hook.py": (
        "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK",
        "paper_engine_hook_read_only",
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
    text = " ".join([
        _row_source(row),
        str(row.get("profile_name") or meta.get("profile_name") or ""),
        str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
        str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
    ]).upper()
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
        "operator_rearm_env_currently_active": any(key in active for key in {
            OPERATOR_REARM_ENABLE_ENV,
            OPERATOR_REARM_CONFIRMATION_ENV,
            OPERATOR_REARM_MAX_POSITIONS_ENV,
        }),
        "operator_rearm_enable_env_value": active.get(OPERATOR_REARM_ENABLE_ENV, ""),
        "operator_rearm_confirmation_env_value_present": OPERATOR_REARM_CONFIRMATION_ENV in active,
    }


def _state_status_snapshot(paper_state: Mapping[str, Any], paper_status: Mapping[str, Any]) -> dict[str, Any]:
    positions = _collection_rows(paper_state.get("positions"), id_field="position_id")
    orders = _collection_rows(paper_state.get("orders"), id_field="order_id")
    open_lsr_positions = [row for row in positions if _is_lsr_v2_row(row) and _is_open_position(row)]
    pending_lsr_orders = [row for row in orders if _is_lsr_v2_row(row) and _is_pending_order(row)]
    open_positions_after = _safe_int(paper_status.get("open_positions"), len([row for row in positions if _is_open_position(row)]))
    pending_orders_after = _safe_int(paper_status.get("pending_orders"), len([row for row in orders if _is_pending_order(row)]))
    return {
        "open_lsr_v2_positions_after": len(open_lsr_positions),
        "pending_lsr_v2_orders_after": len(pending_lsr_orders),
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "paper_status_open_positions_after": open_positions_after,
        "paper_status_pending_orders_after": pending_orders_after,
        "pending_orders_clear": pending_orders_after == 0 and len(pending_lsr_orders) == 0,
        "flat_state_confirmed": open_positions_after == 0 and pending_orders_after == 0 and len(open_lsr_positions) == 0,
        "paper_state_status_consistency": (open_positions_after == len([row for row in positions if _is_open_position(row)]))
        and (pending_orders_after == len([row for row in orders if _is_pending_order(row)])),
        "balance_after": _safe_float(paper_state.get("balance") or paper_status.get("equity"), 0.0),
        "realized_pnl_after": _safe_float(paper_state.get("realized_pnl"), 0.0),
    }


def _source_marker_audit(project_root: str | Path) -> dict[str, Any]:
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
            text = ""
        miss = [marker for marker in markers if marker not in text]
        if miss:
            missing_markers[rel] = miss
    return {
        "operator_gate_source_files_present": not missing_files,
        "operator_gate_required_markers_present": not missing_files and not missing_markers,
        "missing_operator_gate_source_files": missing_files,
        "missing_operator_gate_source_markers": missing_markers,
    }


def _required_reports(data_dir: str | Path) -> dict[str, dict[str, Any]]:
    root = Path(data_dir)
    return {
        "rearm_readiness": _read_json(root / REARM_READINESS_REPORT_NAME),
        "candidate_hook": _read_json(root / CANDIDATE_HOOK_REPORT_NAME),
        "handoff": _read_json(root / HANDOFF_REPORT_NAME),
        "parity": _read_json(root / PARITY_REPORT_NAME),
        "engine_hook": _read_json(root / ENGINE_HOOK_REPORT_NAME),
        "lifecycle": _read_json(root / LIFECYCLE_REPORT_NAME),
        "dashboard": _read_json(root / DASHBOARD_REPORT_NAME),
        "postmortem": _read_json(root / POSTMORTEM_REPORT_NAME),
    }


def build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report(
    *,
    reports: Mapping[str, Mapping[str, Any]],
    paper_state: Mapping[str, Any],
    paper_status: Mapping[str, Any],
    source_audit: Mapping[str, Any],
    env_controls: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    env = dict(env_controls or _operator_env_controls())
    state = _state_status_snapshot(paper_state, paper_status)
    rearm = reports.get("rearm_readiness", {})
    candidate_hook = reports.get("candidate_hook", {})
    handoff = reports.get("handoff", {})
    parity = reports.get("parity", {})
    engine_hook = reports.get("engine_hook", {})
    lifecycle = reports.get("lifecycle", {})
    dashboard = reports.get("dashboard", {})
    postmortem = reports.get("postmortem", {})

    report_readiness = {
        "rearm_readiness_preflight_ready": _pass_report(rearm, REARM_READINESS_PASS_DECISION)
        and _safe_bool(rearm.get("rearm_readiness_preflight_ready"), False),
        "candidate_lifecycle_hook_preflight_ready": _pass_report(candidate_hook, CANDIDATE_HOOK_PASS_DECISION)
        and _safe_bool(candidate_hook.get("candidate_lifecycle_hook_preflight_ready"), False),
        "read_only_handoff_preflight_ready": _pass_report(handoff, HANDOFF_PASS_DECISION)
        and _safe_bool(handoff.get("read_only_handoff_preflight_ready"), False),
        "parity_audit_ready": _pass_report(parity, PARITY_PASS_DECISION)
        and _safe_bool(parity.get("launcher_runner_visibility_parity_ok"), False),
        "engine_hook_ready": _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION)
        and _safe_bool(engine_hook.get("engine_artifact_hook_ready"), False),
        "lifecycle_auto_monitor_ready": _pass_report(lifecycle, LIFECYCLE_PASS_DECISION)
        and _safe_bool(lifecycle.get("lifecycle_auto_monitor_ready"), False),
        "telegram_dashboard_ready": _pass_report(dashboard, DASHBOARD_PASS_DECISION)
        and _safe_bool(dashboard.get("dashboard_ready"), False),
        "three_trade_postmortem_ready": _pass_report(postmortem, POSTMORTEM_PASS_DECISION)
        and _safe_bool(postmortem.get("three_trade_postmortem_complete"), False),
    }

    inherited = [rearm, candidate_hook, handoff, parity, engine_hook, lifecycle, dashboard, postmortem]
    live_enabled = any(_safe_bool(item.get("live_enabled"), False) for item in inherited)
    testnet_enabled = any(_safe_bool(item.get("testnet_enabled"), False) for item in inherited)
    exchange_broker_enabled = any(_safe_bool(item.get("exchange_broker_enabled"), False) for item in inherited)
    telegram_network_called = any(_safe_bool(item.get("telegram_network_called"), False) for item in inherited)
    telegram_send_allowed = any(_safe_bool(item.get("telegram_send_allowed"), False) for item in inherited)
    scheduler_started = any(_safe_bool(item.get("scheduler_started"), False) for item in inherited)
    scheduler_enabled = any(_safe_bool(item.get("scheduler_enabled"), False) for item in inherited)

    fourth_trade_locked = all(_safe_bool(item.get("fourth_trade_locked"), True) for item in inherited)
    stability_lock_active = all(_safe_bool(item.get("stability_lock_active"), True) for item in inherited)
    fourth_trade_allowed = any(_safe_bool(item.get("fourth_trade_allowed"), False) for item in inherited)
    fourth_submit_or_reentry_detected = any(_safe_bool(item.get("fourth_submit_or_reentry_detected"), False) for item in inherited)

    aggregate_realized_pnl = _safe_float(
        rearm.get("aggregate_realized_pnl")
        or postmortem.get("aggregate_realized_pnl")
        or dashboard.get("aggregate_realized_pnl"),
        0.0,
    )
    balance_after = _safe_float(
        state.get("balance_after")
        or rearm.get("balance_after")
        or postmortem.get("balance_after"),
        0.0,
    )

    blockers: list[str] = []
    if not all(report_readiness.values()):
        blockers.append("required_operator_gate_reports_not_ready")
    if not _safe_bool(source_audit.get("operator_gate_required_markers_present"), False):
        blockers.append("operator_gate_required_markers_missing")
    if not state["flat_state_confirmed"] or not state["pending_orders_clear"] or not state["paper_state_status_consistency"]:
        blockers.append("paper_state_or_status_not_flat")
    if not fourth_trade_locked or not stability_lock_active or fourth_trade_allowed or fourth_submit_or_reentry_detected:
        blockers.append("three_trade_state_not_flat_locked_or_fourth_lock_invalid")
    if not env.get("operator_env_absent", False):
        blockers.append("operator_env_active_before_unlock_patch")
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if telegram_network_called or telegram_send_allowed:
        blockers.append("telegram_network_or_send_enabled")
    if scheduler_enabled or scheduler_started:
        blockers.append("scheduler_enabled_or_started")

    hard_fail = any(key in blockers for key in ("live_enabled", "testnet_enabled", "exchange_broker_enabled"))
    if hard_fail:
        status = "FAIL"
        decision = FAILED_DECISION
    elif "operator_env_active_before_unlock_patch" in blockers:
        status = "WARN"
        decision = ENV_ACTIVE_DECISION
    elif "operator_gate_required_markers_missing" in blockers:
        status = "WARN"
        decision = SOURCE_MARKERS_MISSING_DECISION
    elif "paper_state_or_status_not_flat" in blockers or "three_trade_state_not_flat_locked_or_fourth_lock_invalid" in blockers:
        status = "WARN"
        decision = STATE_NOT_LOCKED_DECISION
    elif "required_operator_gate_reports_not_ready" in blockers:
        status = "WARN"
        decision = REPORTS_NOT_READY_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    operator_gate_preflight_ready = status == "PASS"

    payload: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "blockers": blockers,
        "classification_labels": [
            "FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT",
            "READ_ONLY",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
        ] + (["OPERATOR_REARM_GATE_PREFLIGHT_READY"] if operator_gate_preflight_ready else []),
        **report_readiness,
        **source_audit,
        **state,
        **env,
        "operator_rearm_gate_preflight_ready": operator_gate_preflight_ready,
        "operator_rearm_gate_plan_ready": True,
        "operator_rearm_gate_allowed": False,
        "operator_rearm_enable_env_name": OPERATOR_REARM_ENABLE_ENV,
        "operator_rearm_confirmation_env_name": OPERATOR_REARM_CONFIRMATION_ENV,
        "operator_rearm_max_positions_env_name": OPERATOR_REARM_MAX_POSITIONS_ENV,
        "operator_rearm_confirmation_phrase": OPERATOR_REARM_CONFIRMATION_PHRASE,
        "operator_rearm_max_positions": OPERATOR_REARM_MAX_POSITIONS,
        "operator_rearm_confirmation_ok": False,
        "operator_rearm_enable_allowed": False,
        "operator_rearm_submit_allowed": False,
        "operator_rearm_requires_explicit_unlock_patch": True,
        "fourth_trade_rearm_operator_gate_allowed": False,
        "fourth_trade_rearm_allowed": False,
        "future_fourth_trade_unlock_allowed": False,
        "future_candidate_detection_allowed": False,
        "candidate_lifecycle_hook_allowed": False,
        "engine_candidate_lifecycle_hook_allowed": False,
        "candidate_routing_execution_allowed": False,
        "candidate_submit_execution_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_engine_mutation_allowed": False,
        "paper_engine_candidate_hook_mutation_allowed": False,
        "fourth_trade_allowed": False,
        "fourth_trade_locked": bool(fourth_trade_locked),
        "stability_lock_active": bool(stability_lock_active),
        "fourth_submit_or_reentry_detected": bool(fourth_submit_or_reentry_detected),
        "lifecycle_state": str(lifecycle.get("lifecycle_state") or rearm.get("lifecycle_state") or "FLAT_LOCKED"),
        "dashboard_mode": str(dashboard.get("dashboard_mode") or rearm.get("dashboard_mode") or "POST_THREE_TRADE_FLAT_LOCKED"),
        "telegram_payload_ready": _safe_bool(dashboard.get("telegram_payload_ready") or lifecycle.get("telegram_payload_ready"), False),
        "telegram_update_ready": _safe_bool(lifecycle.get("telegram_update_ready") or dashboard.get("telegram_update_ready"), False),
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "broker_submit_called_by_operator_rearm_gate_preflight": False,
        "broker_close_called_by_operator_rearm_gate_preflight": False,
        "orders_submitted_by_operator_rearm_gate_preflight": 0,
        "positions_opened_by_operator_rearm_gate_preflight": 0,
        "positions_closed_by_operator_rearm_gate_preflight": 0,
        "paper_state_modified_by_operator_rearm_gate_preflight": False,
        "paper_status_modified_by_operator_rearm_gate_preflight": False,
        "submit_execution_events_total": _safe_int(rearm.get("submit_execution_events_total") or postmortem.get("submit_execution_events_total"), 3),
        "close_execution_events_total": _safe_int(rearm.get("close_execution_events_total") or postmortem.get("close_execution_events_total"), 3),
        "aggregate_realized_pnl": aggregate_realized_pnl,
        "balance_after": balance_after,
        "realized_pnl_after": _safe_float(state.get("realized_pnl_after"), aggregate_realized_pnl),
        "visual_sl_tp_progress_bar_ready": _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready"), False),
        "visual_sl_tp_progress_bar": str(dashboard.get("visual_sl_tp_progress_bar") or ""),
        "operator_rearm_gate_inputs": [
            "fourth_trade_rearm_readiness_preflight_report",
            "candidate_lifecycle_hook_preflight_report",
            "read_only_handoff_preflight_report",
            "visibility_parity_audit_report",
            "engine_read_only_artifact_hook_report",
            "lifecycle_auto_monitor_report",
            "telegram_dashboard_report",
            "three_trade_postmortem_report",
            "paper_state",
            "paper_status",
            "operator_rearm_env_model",
        ],
        "blocked_until_explicit_unlock_patch": [
            "operator_rearm_gate_activation",
            "fourth_trade_rearm",
            "candidate_detection",
            "candidate_routing_execution",
            "broker_submit",
            "broker_close",
            "telegram_network_send",
            "scheduler_start",
            "paper_engine_candidate_execution_hook",
        ],
        "next_step": "validate_operator_rearm_gate_preflight_then_prepare_guarded_operator_unlock_draft",
        "recommended_next_patch": "29.4.4t-10 — LSR-v2 guarded paper-only fourth-trade operator unlock draft",
    }
    return payload


def build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    write_report: bool = False,
) -> dict[str, Any]:
    data_root = Path(data_dir)
    reports = _required_reports(data_root)
    paper_state = _read_json(data_root / PAPER_STATE_NAME)
    paper_status = _read_json(data_root / PAPER_STATUS_NAME)
    source_audit = _source_marker_audit(project_root)
    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report(
        reports=reports,
        paper_state=paper_state,
        paper_status=paper_status,
        source_audit=source_audit,
    )
    report["settings"] = {
        "data_dir": str(data_root),
        "project_root": str(project_root),
        "report_name": REPORT_NAME,
        "jsonl_name": JSONL_NAME,
        "fail_closed": True,
    }
    report["report"] = str(data_root / REPORT_NAME)
    report["jsonl"] = str(data_root / JSONL_NAME)
    if write_report:
        _write_json(data_root / REPORT_NAME, report)
        _append_jsonl(data_root / JSONL_NAME, report)
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="LSR-v2 fourth-trade operator re-arm gate preflight")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    report = build_lsr_v2_fourth_trade_operator_rearm_gate_preflight_report_from_files(
        data_dir=args.data_dir,
        project_root=args.project_root,
        write_report=not args.no_write,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
