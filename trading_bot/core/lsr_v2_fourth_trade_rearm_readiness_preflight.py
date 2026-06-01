"""Prompt 29.4.4t-8 — LSR-v2 paper-only fourth-trade re-arm readiness preflight.

Read-only readiness preflight for a future explicit paper-only fourth-trade
re-arm patch.  This module verifies that the validated three-trade LSR-v2 cycle
is flat/locked, that candidate lifecycle/handoff artifacts are ready, and that
all operator controls are absent.  It intentionally keeps all execution and
re-arm permissions disabled: no candidate routing, no submit, no close, no
scheduler, no Telegram network send, no paper state/status mutation, and no
live/testnet/exchange broker.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

PROMPT_ID = "29.4.4t-8"
EVENT_TYPE = "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT"
REPORT_NAME = "lsr_v2_fourth_trade_rearm_readiness_preflight_report.json"
JSONL_NAME = "lsr_v2_fourth_trade_rearm_readiness_preflight.jsonl"

CANDIDATE_HOOK_REPORT_NAME = "lsr_v2_candidate_lifecycle_hook_preflight_report.json"
HANDOFF_REPORT_NAME = "lsr_v2_launcher_runner_read_only_handoff_preflight_report.json"
PARITY_REPORT_NAME = "lsr_v2_launcher_runner_visibility_parity_audit_report.json"
ENGINE_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_trade_lifecycle_auto_monitor_report.json"
DASHBOARD_REPORT_NAME = "lsr_v2_telegram_trade_dashboard_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

CANDIDATE_HOOK_PASS_DECISION = "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT_READY"
HANDOFF_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT_READY"
PARITY_PASS_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
ENGINE_HOOK_PASS_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"
LIFECYCLE_PASS_DECISION = "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"
DASHBOARD_PASS_DECISION = "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"
POSTMORTEM_PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"

PASS_DECISION = "LSR_V2_FOURTH_TRADE_REARM_READINESS_PREFLIGHT_READY"
REPORTS_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_REARM_REPORTS_NOT_READY"
SOURCE_MARKERS_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_REARM_SOURCE_MARKERS_MISSING"
STATE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_REARM_STATE_NOT_LOCKED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_REARM_OPERATOR_ENV_ACTIVE"
FAILED_DECISION = "REJECT_LSR_V2_FOURTH_REARM_READINESS_PREFLIGHT_SAFETY_FAILED"

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
    "ROUTE",
)

_SOURCE_MARKERS: dict[str, tuple[str, ...]] = {
    "trading_bot/core/lsr_v2_candidate_lifecycle_hook_preflight.py": (
        "LSR_V2_CANDIDATE_LIFECYCLE_HOOK_PREFLIGHT",
        "candidate_lifecycle_hook_allowed",
    ),
    "trading_bot/core/lsr_v2_launcher_runner_read_only_handoff_preflight.py": (
        "LSR_V2_LAUNCHER_RUNNER_READ_ONLY_HANDOFF_PREFLIGHT",
        "fourth_trade_rearm_allowed",
    ),
    "trading_bot/core/lsr_v2_engine_read_only_artifact_hook.py": (
        "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK",
        "paper_engine_hook_read_only",
    ),
    "trading_bot/core/lsr_v2_trade_lifecycle_auto_monitor.py": (
        "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR",
        "lifecycle_state",
    ),
    "trading_bot/core/lsr_v2_three_trade_postmortem_stability_lock.py": (
        "LSR_V2_THREE_TRADE_POSTMORTEM",
        "fourth_trade_locked",
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
            text = ""
        missing = [marker for marker in markers if marker not in text]
        if missing:
            missing_markers[rel] = missing
    return {
        "rearm_source_files_present": not missing_files,
        "rearm_required_markers_present": not missing_markers,
        "missing_rearm_source_files": missing_files,
        "missing_rearm_source_markers": missing_markers,
    }


def _safety_flags(*reports: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "live_enabled": any(_safe_bool(r.get("live_enabled")) for r in reports),
        "testnet_enabled": any(_safe_bool(r.get("testnet_enabled")) for r in reports),
        "exchange_broker_enabled": any(_safe_bool(r.get("exchange_broker_enabled")) for r in reports),
        "operational_unlock_allowed": any(_safe_bool(r.get("operational_unlock_allowed")) for r in reports),
        "promotion_ready": any(_safe_bool(r.get("promotion_ready")) for r in reports),
        "telegram_network_called": any(_safe_bool(r.get("telegram_network_called")) for r in reports),
        "telegram_send_allowed": any(_safe_bool(r.get("telegram_send_allowed")) for r in reports),
        "scheduler_enabled": any(_safe_bool(r.get("scheduler_enabled")) for r in reports),
        "scheduler_started": any(_safe_bool(r.get("scheduler_started")) for r in reports),
    }


def build_lsr_v2_fourth_trade_rearm_readiness_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path = ".",
    now: str | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    data = Path(data_dir)
    candidate = _read_json(data / CANDIDATE_HOOK_REPORT_NAME)
    handoff = _read_json(data / HANDOFF_REPORT_NAME)
    parity = _read_json(data / PARITY_REPORT_NAME)
    engine_hook = _read_json(data / ENGINE_HOOK_REPORT_NAME)
    lifecycle = _read_json(data / LIFECYCLE_REPORT_NAME)
    dashboard = _read_json(data / DASHBOARD_REPORT_NAME)
    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)

    env = _operator_env_controls()
    state = _state_status_snapshot(paper_state, paper_status)
    sources = _source_marker_snapshot(project_root)
    safety = _safety_flags(candidate, handoff, parity, engine_hook, lifecycle, dashboard, postmortem)

    reports_ready = {
        "candidate_lifecycle_hook_preflight_ready": _pass_report(candidate, CANDIDATE_HOOK_PASS_DECISION)
        and _safe_bool(candidate.get("candidate_lifecycle_hook_preflight_ready")),
        "read_only_handoff_preflight_ready": _pass_report(handoff, HANDOFF_PASS_DECISION)
        and _safe_bool(handoff.get("read_only_handoff_preflight_ready")),
        "parity_audit_ready": _pass_report(parity, PARITY_PASS_DECISION)
        and _safe_bool(parity.get("launcher_runner_visibility_parity_ok")),
        "engine_hook_ready": _pass_report(engine_hook, ENGINE_HOOK_PASS_DECISION)
        and _safe_bool(engine_hook.get("engine_artifact_hook_ready")),
        "lifecycle_auto_monitor_ready": _pass_report(lifecycle, LIFECYCLE_PASS_DECISION)
        and _safe_bool(lifecycle.get("lifecycle_auto_monitor_ready")),
        "telegram_dashboard_ready": _pass_report(dashboard, DASHBOARD_PASS_DECISION)
        and _safe_bool(dashboard.get("dashboard_ready")),
        "three_trade_postmortem_ready": _pass_report(postmortem, POSTMORTEM_PASS_DECISION)
        and _safe_bool(postmortem.get("three_trade_postmortem_complete")),
    }

    lifecycle_state = str(lifecycle.get("lifecycle_state") or dashboard.get("lifecycle_state") or postmortem.get("lifecycle_state") or "").upper()
    fourth_locked = (
        _safe_bool(candidate.get("fourth_trade_locked"), True)
        and _safe_bool(handoff.get("fourth_trade_locked"), True)
        and _safe_bool(parity.get("fourth_trade_locked"), True)
        and _safe_bool(lifecycle.get("fourth_trade_locked"), True)
        and _safe_bool(dashboard.get("fourth_trade_locked"), True)
        and _safe_bool(postmortem.get("fourth_trade_locked"), True)
    )
    fourth_allowed = any(
        _safe_bool(r.get("fourth_trade_allowed"))
        for r in (candidate, handoff, parity, lifecycle, dashboard, postmortem)
    )
    stability_lock = (
        _safe_bool(candidate.get("stability_lock_active"), True)
        and _safe_bool(handoff.get("stability_lock_active"), True)
        and _safe_bool(parity.get("stability_lock_active"), True)
        and _safe_bool(lifecycle.get("stability_lock_active"), True)
        and _safe_bool(dashboard.get("stability_lock_active"), True)
        and _safe_bool(postmortem.get("stability_lock_active"), True)
    )

    blockers: list[str] = []
    if not all(reports_ready.values()):
        blockers.append("required_readiness_reports_not_ready")
    if not sources["rearm_source_files_present"]:
        blockers.append("rearm_source_files_missing")
    if not sources["rearm_required_markers_present"]:
        blockers.append("rearm_required_markers_missing")
    if lifecycle_state != "FLAT_LOCKED" or not fourth_locked or fourth_allowed or not stability_lock:
        blockers.append("three_trade_state_not_flat_locked_or_fourth_lock_invalid")
    if not state["flat_state_confirmed"] or not state["pending_orders_clear"] or not state["paper_state_status_consistency"]:
        blockers.append("paper_state_or_status_not_flat")
    if not env["operator_env_absent"]:
        blockers.append("operator_env_active")
    for key, value in safety.items():
        if value:
            blockers.append(key)

    fatal_safety = any(safety[k] for k in ("live_enabled", "testnet_enabled", "exchange_broker_enabled"))
    if fatal_safety:
        status = "FAIL"
        decision = FAILED_DECISION
    elif not all(reports_ready.values()):
        status = "WARN"
        decision = REPORTS_NOT_READY_DECISION
    elif not sources["rearm_source_files_present"] or not sources["rearm_required_markers_present"]:
        status = "WARN"
        decision = SOURCE_MARKERS_MISSING_DECISION
    elif "three_trade_state_not_flat_locked_or_fourth_lock_invalid" in blockers or "paper_state_or_status_not_flat" in blockers:
        status = "WARN"
        decision = STATE_NOT_LOCKED_DECISION
    elif not env["operator_env_absent"]:
        status = "WARN"
        decision = ENV_ACTIVE_DECISION
    elif blockers:
        status = "FAIL"
        decision = FAILED_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    ready = status == "PASS" and decision == PASS_DECISION
    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": now or utc_now_iso(),
        "status": status,
        "decision": decision,
        "blockers": blockers,
        "classification_labels": [
            "FOURTH_TRADE_REARM_READINESS_PREFLIGHT",
            "READ_ONLY",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
        ] + (["FOURTH_REARM_READINESS_PREFLIGHT_READY"] if ready else []),
        **reports_ready,
        **state,
        **sources,
        **env,
        **safety,
        "rearm_readiness_preflight_ready": ready,
        "fourth_trade_rearm_readiness_ready": ready,
        "fourth_trade_rearm_plan_ready": True,
        "fourth_trade_rearm_allowed": False,
        "fourth_trade_rearm_operator_gate_allowed": False,
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
        "fourth_trade_locked": fourth_locked,
        "stability_lock_active": stability_lock,
        "fourth_submit_or_reentry_detected": False,
        "lifecycle_state": lifecycle_state,
        "dashboard_mode": str(dashboard.get("dashboard_mode") or postmortem.get("dashboard_mode") or ""),
        "telegram_payload_ready": _safe_bool(dashboard.get("telegram_payload_ready")),
        "telegram_update_ready": _safe_bool(dashboard.get("telegram_update_ready")) or _safe_bool(lifecycle.get("telegram_update_ready")),
        "visual_sl_tp_progress_bar_ready": _safe_bool(dashboard.get("visual_sl_tp_progress_bar_ready")) or _safe_bool(lifecycle.get("visual_sl_tp_progress_bar_ready")),
        "visual_sl_tp_progress_bar": str(dashboard.get("visual_sl_tp_progress_bar") or lifecycle.get("visual_sl_tp_progress_bar") or ""),
        "submit_execution_events_total": _safe_int(postmortem.get("submit_execution_events_total"), _safe_int(lifecycle.get("submit_execution_events_total"), 0)),
        "close_execution_events_total": _safe_int(postmortem.get("close_execution_events_total"), _safe_int(lifecycle.get("close_execution_events_total"), 0)),
        "aggregate_realized_pnl": _safe_float(postmortem.get("aggregate_realized_pnl"), _safe_float(lifecycle.get("aggregate_realized_pnl"), 0.0)),
        "balance_after": state["balance_after"] or _safe_float(postmortem.get("balance_after"), _safe_float(lifecycle.get("balance_after"), 0.0)),
        "blocked_until_explicit_unlock_patch": [
            "fourth_trade_rearm",
            "candidate_detection",
            "candidate_routing_execution",
            "broker_submit",
            "broker_close",
            "telegram_network_send",
            "scheduler_start",
            "paper_engine_candidate_execution_hook",
        ],
        "rearm_readiness_inputs": [
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
        "next_step": "validate_rearm_readiness_then_prepare_operator_rearm_gate_preflight",
        "recommended_next_patch": "29.4.4t-9 — LSR-v2 paper-only fourth-trade operator re-arm gate preflight",
        "orders_submitted_by_fourth_rearm_readiness_preflight": 0,
        "positions_opened_by_fourth_rearm_readiness_preflight": 0,
        "positions_closed_by_fourth_rearm_readiness_preflight": 0,
        "broker_submit_called_by_fourth_rearm_readiness_preflight": False,
        "broker_close_called_by_fourth_rearm_readiness_preflight": False,
        "paper_state_modified_by_fourth_rearm_readiness_preflight": False,
        "paper_status_modified_by_fourth_rearm_readiness_preflight": False,
        "report": str(Path(data_dir) / REPORT_NAME),
        "jsonl": str(Path(data_dir) / JSONL_NAME),
        "settings": {
            "data_dir": str(data_dir),
            "project_root": str(project_root),
            "report_name": REPORT_NAME,
            "jsonl_name": JSONL_NAME,
            "fail_closed": True,
        },
    }

    if write_report:
        _write_json(Path(data_dir) / REPORT_NAME, report)
        _append_jsonl(Path(data_dir) / JSONL_NAME, report)
    return report


def main() -> int:
    report = build_lsr_v2_fourth_trade_rearm_readiness_preflight_report_from_files()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


__all__ = [
    "PASS_DECISION",
    "REPORTS_NOT_READY_DECISION",
    "SOURCE_MARKERS_MISSING_DECISION",
    "STATE_NOT_LOCKED_DECISION",
    "ENV_ACTIVE_DECISION",
    "FAILED_DECISION",
    "build_lsr_v2_fourth_trade_rearm_readiness_preflight_report_from_files",
]
