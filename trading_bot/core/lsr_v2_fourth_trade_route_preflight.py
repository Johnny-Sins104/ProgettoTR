"""Prompt 29.4.4t-14 — LSR-v2 fourth-trade route preflight.

Read-only/fail-closed route preflight for a future fourth LSR-v2 paper trade.
The module verifies the validated candidate detection audit and upstream safety
artifacts, then decides whether a route would be possible diagnostically.

It never routes, never submits, never opens/closes positions, never starts a
scheduler, never sends Telegram traffic, never touches live/testnet/exchange
brokers, and never mutates paper_state or paper_status.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import argparse
import json
import os

PROMPT_ID = "29.4.4t-14"
EVENT_TYPE = "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT"
REPORT_NAME = "lsr_v2_fourth_trade_route_preflight_report.json"
JSONL_NAME = "lsr_v2_fourth_trade_route_preflight.jsonl"

T13_REPORT_NAME = "lsr_v2_fourth_trade_candidate_detection_audit_report.json"
T12_REPORT_NAME = "lsr_v2_fourth_trade_unlock_activation_candidate_preflight_report.json"
T11_REPORT_NAME = "lsr_v2_fourth_trade_operator_unlock_activation_preflight_report.json"
T10_REPORT_NAME = "lsr_v2_fourth_trade_operator_unlock_draft_report.json"
T9_REPORT_NAME = "lsr_v2_fourth_trade_operator_rearm_gate_preflight_report.json"
T8_REPORT_NAME = "lsr_v2_fourth_trade_rearm_readiness_preflight_report.json"
T7_REPORT_NAME = "lsr_v2_candidate_lifecycle_hook_preflight_report.json"
T6_REPORT_NAME = "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json"
T5_REPORT_NAME = "lsr_v2_launcher_runner_visibility_parity_audit_report.json"
ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

T13_PASS_DECISION = "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY"
T12_PASS_DECISION = "LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT_READY"
T11_PASS_DECISION = "LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_ACTIVATION_PREFLIGHT_READY"
T10_PASS_DECISION = "LSR_V2_FOURTH_TRADE_OPERATOR_UNLOCK_DRAFT_READY"
T9_PASS_DECISION = "LSR_V2_FOURTH_TRADE_OPERATOR_REARM_GATE_PREFLIGHT_READY"
T8_PASS_DECISION = "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY"
T7_PASS_DECISION = "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY"
T6_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY"
T5_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"
REPORTS_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_ROUTE_PREFLIGHT_REPORTS_NOT_READY"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_ROUTE_PREFLIGHT_STATE_NOT_LOCKED"
SOURCE_MARKERS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_ROUTE_PREFLIGHT_SOURCE_MARKERS_MISSING"
ENV_INVALID_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_ROUTE_PREFLIGHT_OPERATOR_ENV_INVALID"
FAILED_DECISION = "REJECT_LSR_V2_FOURTH_ROUTE_PREFLIGHT_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = (
    "ARM", "EXECUTE", "ENABLE", "CONFIRMATION", "MAX_POSITIONS", "REARM",
    "UNLOCK", "SUBMIT", "CLOSE", "ROUTE", "CANDIDATE",
)

_SOURCE_MARKERS: dict[str, tuple[str, ...]] = {
    "trading_bot/core/lsr_v2_fourth_trade_candidate_detection_audit.py": (
        "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT",
        "fourth_trade_candidate_detected_diagnostic",
        "candidate_routing_execution_allowed",
    ),
    "trading_bot/core/lsr_v2_fourth_trade_unlock_activation_candidate_preflight.py": (
        "LSR_V2_FOURTH_TRADE_UNLOCK_ACTIVATION_CANDIDATE_PREFLIGHT",
        "candidate_detection_preflight_ready",
    ),
    "trading_bot/core/lsr_v2_candidate_lifecycle_hook_preflight.py": (
        "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT",
        "candidate_lifecycle_hook_preflight_ready",
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


def _required_reports(data_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        "candidate_detection_audit": _read_json(data_dir / T13_REPORT_NAME),
        "unlock_activation_candidate_preflight": _read_json(data_dir / T12_REPORT_NAME),
        "unlock_activation_preflight": _read_json(data_dir / T11_REPORT_NAME),
        "unlock_draft": _read_json(data_dir / T10_REPORT_NAME),
        "operator_gate": _read_json(data_dir / T9_REPORT_NAME),
        "rearm_readiness": _read_json(data_dir / T8_REPORT_NAME),
        "candidate_hook": _read_json(data_dir / T7_REPORT_NAME),
        "handoff": _read_json(data_dir / T6_REPORT_NAME),
        "parity": _read_json(data_dir / T5_REPORT_NAME),
        "engine_hook": _read_json(data_dir / ENGINE_HOOK_REPORT_NAME),
        "lifecycle": _read_json(data_dir / LIFECYCLE_REPORT_NAME),
        "dashboard": _read_json(data_dir / DASHBOARD_REPORT_NAME),
        "postmortem": _read_json(data_dir / POSTMORTEM_REPORT_NAME),
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
        "route_preflight_source_files_present": not missing_files,
        "route_preflight_required_markers_present": not missing_files and not missing_markers,
        "missing_route_preflight_source_files": missing_files,
        "missing_route_preflight_source_markers": missing_markers,
    }


def _operator_env_controls(env_map: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env_map if env_map is not None else os.environ
    active: dict[str, str] = {}
    for key, value in source.items():
        upper = str(key).upper()
        if not upper.startswith(LSR_V2_OPERATOR_ENV_PREFIX):
            continue
        if not any(marker in upper for marker in _OPERATOR_ENV_MARKERS):
            continue
        if str(value).strip() in {"", "0", "false", "False", "no", "NO", "off", "OFF"}:
            continue
        active[upper] = str(value)
    return {
        "active_lsr_v2_operator_env_count": len(active),
        "active_lsr_v2_operator_env_keys": sorted(active),
        "operator_env_absent": not active,
        "route_preflight_operator_env_currently_active": bool(active),
    }


def _state_status_snapshot(paper_state: Mapping[str, Any], paper_status: Mapping[str, Any]) -> dict[str, Any]:
    positions = _collection_rows(paper_state.get("positions"), id_field="position_id")
    orders = _collection_rows(paper_state.get("orders"), id_field="order_id")
    open_positions = [row for row in positions if _is_open_position(row)]
    open_lsr_v2 = [row for row in open_positions if _is_lsr_v2_row(row)]
    pending_orders = [row for row in orders if _is_pending_order(row)]
    pending_lsr_v2 = [row for row in pending_orders if _is_lsr_v2_row(row)]
    status_open = _safe_int(paper_status.get("open_positions"), len(open_positions))
    status_pending = _safe_int(paper_status.get("pending_orders"), len(pending_orders))
    return {
        "open_positions_after": len(open_positions),
        "open_lsr_v2_positions_after": len(open_lsr_v2),
        "pending_orders_after": len(pending_orders),
        "pending_lsr_v2_orders_after": len(pending_lsr_v2),
        "paper_status_open_positions_after": status_open,
        "paper_status_pending_orders_after": status_pending,
        "pending_orders_clear": len(pending_orders) == 0 and status_pending == 0,
        "flat_state_confirmed": len(open_positions) == 0 and status_open == 0,
        "paper_state_status_consistency": len(open_positions) == status_open and len(pending_orders) == status_pending,
        "balance_after": _safe_float(paper_state.get("balance") or paper_status.get("balance"), 0.0),
        "realized_pnl_after": _safe_float(paper_state.get("realized_pnl") or paper_status.get("realized_pnl"), 0.0),
    }


def _candidate_from_detection_report(t13: Mapping[str, Any]) -> dict[str, Any]:
    latest = t13.get("candidate_detection_latest_candidate")
    if not isinstance(latest, Mapping):
        latest = {}
    fourth_specific = _safe_bool(t13.get("fourth_trade_candidate_detected_diagnostic"), False)
    if not fourth_specific:
        return {}
    return {
        "cycle_id": str(latest.get("cycle_id") or ""),
        "symbol": str(latest.get("symbol") or ""),
        "side": str(latest.get("side") or ""),
        "event_type": str(latest.get("event_type") or ""),
        "decision": str(latest.get("decision") or ""),
        "source_jsonl": str(latest.get("source_jsonl") or ""),
        "trade_ordinal": _safe_int(latest.get("trade_ordinal"), 4),
    }


def _route_readiness_from_candidate(t13: Mapping[str, Any]) -> dict[str, Any]:
    general_candidate = _safe_bool(t13.get("candidate_detected_diagnostic"), False)
    general_count = _safe_int(t13.get("candidate_detected_diagnostic_count"), 0)
    fourth_candidate = _safe_bool(t13.get("fourth_trade_candidate_detected_diagnostic"), False)
    fourth_count = _safe_int(t13.get("fourth_trade_candidate_detected_diagnostic_count"), 0)
    latest_fourth_candidate = _candidate_from_detection_report(t13)

    route_candidate_available = fourth_candidate and fourth_count > 0 and bool(latest_fourth_candidate)
    would_route = route_candidate_available
    blocked_reason = ""
    if not route_candidate_available:
        blocked_reason = "no_fourth_specific_candidate"
    elif not str(latest_fourth_candidate.get("symbol") or ""):
        blocked_reason = "candidate_symbol_missing"
        would_route = False
    elif not str(latest_fourth_candidate.get("side") or ""):
        blocked_reason = "candidate_side_missing"
        would_route = False

    return {
        "candidate_detected_diagnostic": general_candidate,
        "candidate_detected_diagnostic_count": general_count,
        "fourth_trade_candidate_detected_diagnostic": fourth_candidate,
        "fourth_trade_candidate_detected_diagnostic_count": fourth_count,
        "route_candidate_available": route_candidate_available,
        "route_candidate": latest_fourth_candidate,
        "would_route": would_route,
        "would_submit": False,
        "route_blocked_reason": blocked_reason,
        "route_decision_diagnostic": "WOULD_ROUTE_DIAGNOSTIC" if would_route else "NO_ROUTE_DIAGNOSTIC",
    }


def build_lsr_v2_fourth_trade_route_preflight_report(
    *,
    reports: Mapping[str, Mapping[str, Any]],
    paper_state: Mapping[str, Any],
    paper_status: Mapping[str, Any],
    source_audit: Mapping[str, Any],
    env: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    env = dict(env or _operator_env_controls())
    t13 = reports.get("candidate_detection_audit", {})
    t12 = reports.get("unlock_activation_candidate_preflight", {})
    t11 = reports.get("unlock_activation_preflight", {})
    t10 = reports.get("unlock_draft", {})
    t9 = reports.get("operator_gate", {})
    t8 = reports.get("rearm_readiness", {})
    t7 = reports.get("candidate_hook", {})
    t6 = reports.get("handoff", {})
    t5 = reports.get("parity", {})
    engine_hook = reports.get("engine_hook", {})
    lifecycle = reports.get("lifecycle", {})
    dashboard = reports.get("dashboard", {})
    postmortem = reports.get("postmortem", {})

    report_readiness = {
        "candidate_detection_audit_ready": _pass_report(t13, T13_PASS_DECISION) and _safe_bool(t13.get("candidate_detection_audit_ready"), False),
        "unlock_activation_candidate_preflight_ready": _pass_report(t12, T12_PASS_DECISION) and _safe_bool(t12.get("unlock_activation_candidate_preflight_ready"), False),
        "operator_unlock_activation_preflight_ready": _pass_report(t11, T11_PASS_DECISION) and _safe_bool(t11.get("operator_unlock_activation_preflight_ready"), False),
        "operator_unlock_draft_ready": _pass_report(t10, T10_PASS_DECISION) and _safe_bool(t10.get("operator_unlock_draft_ready"), False),
        "operator_rearm_gate_preflight_ready": _pass_report(t9, T9_PASS_DECISION) and _safe_bool(t9.get("operator_rearm_gate_preflight_ready"), False),
        "rearm_readiness_preflight_ready": _pass_report(t8, T8_PASS_DECISION) and _safe_bool(t8.get("rearm_readiness_preflight_ready"), False),
        "candidate_lifecycle_hook_preflight_ready": _pass_report(t7, T7_PASS_DECISION) and _safe_bool(t7.get("candidate_lifecycle_hook_preflight_ready"), False),
        "read_only_handoff_preflight_ready": _pass_report(t6, T6_PASS_DECISION) and _safe_bool(t6.get("read_only_handoff_preflight_ready"), False),
        "parity_audit_ready": _pass_report(t5, T5_PASS_DECISION) and _safe_bool(t5.get("visibility_parity_audit_ready"), False),
        "engine_hook_ready": _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION) and _safe_bool(engine_hook.get("engine_artifact_hook_ready"), False),
        "lifecycle_auto_monitor_ready": _pass_report(lifecycle, LIFECYCLE_PASS_DECISION) and _safe_bool(lifecycle.get("lifecycle_auto_monitor_ready"), False),
        "telegram_dashboard_ready": _pass_report(dashboard, DASHBOARD_PASS_DECISION) and _safe_bool(dashboard.get("dashboard_ready"), False),
        "three_trade_postmortem_ready": _pass_report(postmortem, POSTMORTEM_PASS_DECISION) and _safe_bool(postmortem.get("three_trade_postmortem_complete"), False),
    }
    state = _state_status_snapshot(paper_state, paper_status)
    route_model = _route_readiness_from_candidate(t13)

    inherited = [t13, t12, t11, t10, t9, t8, t7, t6, t5, engine_hook, lifecycle, dashboard, postmortem]
    live_enabled = any(_safe_bool(item.get("live_enabled"), False) for item in inherited)
    testnet_enabled = any(_safe_bool(item.get("testnet_enabled"), False) for item in inherited)
    exchange_broker_enabled = any(_safe_bool(item.get("exchange_broker_enabled"), False) for item in inherited)
    telegram_network_called = any(_safe_bool(item.get("telegram_network_called"), False) for item in inherited)
    telegram_send_allowed = any(_safe_bool(item.get("telegram_send_allowed"), False) for item in inherited)
    scheduler_enabled = any(_safe_bool(item.get("scheduler_enabled"), False) for item in inherited)
    scheduler_started = any(_safe_bool(item.get("scheduler_started"), False) for item in inherited)
    fourth_trade_locked = all(_safe_bool(item.get("fourth_trade_locked"), True) for item in inherited)
    stability_lock_active = all(_safe_bool(item.get("stability_lock_active"), True) for item in inherited)
    fourth_trade_allowed = any(_safe_bool(item.get("fourth_trade_allowed"), False) for item in inherited)
    fourth_submit_or_reentry_detected = any(_safe_bool(item.get("fourth_submit_or_reentry_detected"), False) for item in inherited)
    env_active = _safe_bool(env.get("route_preflight_operator_env_currently_active"), False)

    blockers: list[str] = []
    if not all(report_readiness.values()):
        blockers.append("required_route_preflight_reports_not_ready")
    if not _safe_bool(source_audit.get("route_preflight_required_markers_present"), False):
        blockers.append("route_preflight_required_markers_missing")
    if not state["flat_state_confirmed"] or not state["pending_orders_clear"] or not state["paper_state_status_consistency"]:
        blockers.append("paper_state_or_status_not_flat")
    if not fourth_trade_locked or not stability_lock_active or fourth_trade_allowed or fourth_submit_or_reentry_detected:
        blockers.append("three_trade_state_not_flat_locked_or_fourth_lock_invalid")
    if env_active:
        blockers.append("operator_env_active_for_route_preflight")
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
        status = "FAIL"; decision = FAILED_DECISION
    elif "operator_env_active_for_route_preflight" in blockers:
        status = "WARN"; decision = ENV_INVALID_DECISION
    elif "route_preflight_required_markers_missing" in blockers:
        status = "WARN"; decision = SOURCE_MARKERS_MISSING_DECISION
    elif "paper_state_or_status_not_flat" in blockers or "three_trade_state_not_flat_locked_or_fourth_lock_invalid" in blockers:
        status = "WARN"; decision = STATE_NOT_LOCKED_DECISION
    elif "required_route_preflight_reports_not_ready" in blockers:
        status = "WARN"; decision = REPORTS_NOT_READY_DECISION
    elif blockers:
        status = "FAIL"; decision = FAILED_DECISION
    else:
        status = "PASS"; decision = PASS_DECISION

    preflight_ready = status == "PASS"
    would_route = _safe_bool(route_model.get("would_route"), False)

    return {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "blockers": blockers,
        "classification_labels": [
            "FOURTH_TRADE_ROUTE_PREFLIGHT",
            "ROUTE_PREFLIGHT_ONLY",
            "READ_ONLY",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_ROUTE_EXECUTION",
            "NO_SUBMIT",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
        ] + (["WOULD_ROUTE_DIAGNOSTIC_ONLY"] if would_route else ["NO_ROUTE_DIAGNOSTIC"]),
        **report_readiness,
        **state,
        **source_audit,
        **env,
        **route_model,
        "route_preflight_ready": preflight_ready,
        "candidate_route_preflight_ready": preflight_ready,
        "candidate_routing_preflight_ready": preflight_ready,
        "candidate_route_preflight_allowed": False,
        "candidate_routing_allowed": False,
        "candidate_routing_execution_allowed": False,
        "candidate_submit_execution_allowed": False,
        "candidate_detection_allowed": False,
        "future_candidate_detection_allowed": False,
        "fourth_trade_candidate_route_preflight_allowed": False,
        "fourth_trade_rearm_allowed": False,
        "fourth_trade_allowed": False,
        "future_fourth_trade_unlock_allowed": False,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "candidate_lifecycle_hook_allowed": False,
        "engine_candidate_lifecycle_hook_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_engine_mutation_allowed": False,
        "paper_engine_candidate_hook_mutation_allowed": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "telegram_network_called": telegram_network_called,
        "telegram_send_allowed": telegram_send_allowed,
        "scheduler_enabled": scheduler_enabled,
        "scheduler_started": scheduler_started,
        "broker_submit_called_by_route_preflight": False,
        "broker_close_called_by_route_preflight": False,
        "orders_submitted_by_route_preflight": 0,
        "positions_opened_by_route_preflight": 0,
        "positions_closed_by_route_preflight": 0,
        "paper_state_modified_by_route_preflight": False,
        "paper_status_modified_by_route_preflight": False,
        "submit_execution_events_total": _safe_int(t13.get("submit_execution_events_total") or 3, 3),
        "close_execution_events_total": _safe_int(t13.get("close_execution_events_total") or 3, 3),
        "aggregate_realized_pnl": _safe_float(t13.get("aggregate_realized_pnl") or postmortem.get("aggregate_realized_pnl"), 0.0),
        "balance_after": _safe_float(state.get("balance_after") or t13.get("balance_after"), 0.0),
        "realized_pnl_after": _safe_float(state.get("realized_pnl_after"), 0.0),
        "lifecycle_state": str(lifecycle.get("lifecycle_state") or t13.get("lifecycle_state") or ""),
        "dashboard_mode": str(dashboard.get("dashboard_mode") or t13.get("dashboard_mode") or ""),
        "visual_sl_tp_progress_bar_ready": _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready"), False),
        "visual_sl_tp_progress_bar": str(dashboard.get("visual_sl_tp_progress_bar") or t13.get("visual_sl_tp_progress_bar") or ""),
        "telegram_payload_ready": _safe_bool(dashboard.get("telegram_payload_ready"), False),
        "telegram_update_ready": _safe_bool(dashboard.get("telegram_update_ready"), False),
        "blocked_until_explicit_handoff_dry_run_patch": [
            "candidate_handoff_dry_run",
            "candidate_routing_execution",
            "broker_submit",
            "broker_close",
            "telegram_network_send",
            "scheduler_start",
            "paper_engine_candidate_execution_hook",
        ],
        "route_preflight_inputs": [
            "candidate_detection_audit_report",
            "unlock_activation_candidate_preflight_report",
            "operator_unlock_activation_preflight_report",
            "operator_unlock_draft_report",
            "operator_rearm_gate_preflight_report",
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
        ],
        "next_step": "validate_route_preflight_then_prepare_handoff_dry_run_or_wait_for_fourth_candidate",
        "recommended_next_patch": "29.4.4t-15 — LSR-v2 fourth-trade handoff dry-run",
    }


def build_lsr_v2_fourth_trade_route_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(data_dir)
    reports = _required_reports(root)
    paper_state = _read_json(root / PAPER_STATE_NAME)
    paper_status = _read_json(root / PAPER_STATUS_NAME)
    source_audit = _source_marker_audit(project_root)
    report = build_lsr_v2_fourth_trade_route_preflight_report(
        reports=reports,
        paper_state=paper_state,
        paper_status=paper_status,
        source_audit=source_audit,
    )
    report["settings"] = {
        "data_dir": str(root),
        "project_root": str(project_root),
        "report_name": REPORT_NAME,
        "jsonl_name": JSONL_NAME,
        "fail_closed": True,
    }
    report["report"] = str(root / REPORT_NAME)
    report["jsonl"] = str(root / JSONL_NAME)
    if write_report:
        _write_json(root / REPORT_NAME, report)
        _append_jsonl(root / JSONL_NAME, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=PROMPT_ID)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    report = build_lsr_v2_fourth_trade_route_preflight_report_from_files(
        data_dir=args.data_dir,
        project_root=args.project_root,
        write_report=not args.no_write,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
