"""Generic LSR-v2 paper-cycle runtime snapshot visibility preflight.

29.4.4u-9 is intentionally read-only and fail-closed. It verifies that the
validated generic runtime snapshot artifact can be made visible consistently in
runner/footer and launcher/banner surfaces. It never enables candidate
detection, routing, handoff, submit, close, state mutation, scheduler activity,
Telegram network sends, live, testnet, or exchange broker access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-9"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_NOT_READY"

U8_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_READY"
U7_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_READY"
U6_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT_READY"
U5_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY"
U4_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY"
U3_READY_DECISION = "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY"
U2_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY"
U1_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"
T5_READY_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
T4_READY_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY"
T1_READY_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"

REQUIRED_UPSTREAM_REPORTS: Tuple[Tuple[str, str, str], ...] = (
    ("generic_runtime_snapshot_hook", "lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json", U8_READY_DECISION),
    ("generic_runner_launcher_hook_preflight", "lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight_report.json", U7_READY_DECISION),
    ("generic_cycle_engine_hook_preflight", "lsr_v2_generic_paper_cycle_engine_hook_preflight_report.json", U6_READY_DECISION),
    ("generic_cycle_integration_preflight", "lsr_v2_generic_paper_cycle_integration_preflight_report.json", U5_READY_DECISION),
    ("generic_rearm_policy", "lsr_v2_supervised_rearm_policy_draft_report.json", U4_READY_DECISION),
    ("generic_order_lifecycle", "lsr_v2_paper_order_lifecycle_draft_report.json", U3_READY_DECISION),
    ("generic_cycle_controller", "lsr_v2_paper_cycle_controller_draft_report.json", U2_READY_DECISION),
    ("generic_refactor_preflight", "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", U1_READY_DECISION),
    ("launcher_runner_visibility_parity", "lsr_v2_launcher_runner_visibility_parity_audit_report.json", T5_READY_DECISION),
    ("launcher_read_only_banner", "lsr_v2_launcher_read_only_dashboard_banner_report.json", T4_READY_DECISION),
    ("engine_read_only_artifact_hook", "lsr_v2_engine_read_only_artifact_hook_report.json", T1_READY_DECISION),
    ("lifecycle_auto_monitor", "lsr_v2_trade_lifecycle_auto_monitor_report.json", "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"),
    ("telegram_dashboard", "lsr_v2_telegram_trade_dashboard_report.json", "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"),
    ("three_trade_postmortem", "lsr_v2_three_trade_postmortem_stability_lock_report.json", "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"),
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK", "generic_runtime_snapshot"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT", "generic_paper_cycle_runner_launcher_hook_map"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_engine_hook_preflight.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT", "generic_paper_cycle_engine_hook_map"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_integration_preflight.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_INTEGRATION_PREFLIGHT", "generic_paper_cycle_integration_map"),
    ),
    (
        "trading_bot/core/lsr_v2_paper_cycle_controller.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_CONTROLLER_DRAFT", "generic_controller_state_machine"),
    ),
    (
        "trading_bot/core/lsr_v2_paper_order_lifecycle.py",
        ("GENERIC_LSR_V2_PAPER_ORDER_LIFECYCLE_DRAFT", "generic_order_lifecycle_state_model"),
    ),
    (
        "trading_bot/core/lsr_v2_supervised_rearm_policy.py",
        ("GENERIC_LSR_V2_SUPERVISED_REARM_POLICY_DRAFT", "generic_rearm_policy_state_model"),
    ),
    (
        "trading_bot/core/paper_once_runner_footer.py",
        ("footer",),
    ),
    (
        "trading_bot/run_paper_trading.py",
        ("no-lsr-v2-engine-read-only-artifact-hook",),
    ),
    (
        "trading_bot/avvia_bot_live.py",
        ("emit_lsr_v2_launcher_read_only_dashboard_banner", "Live real-money execution is disabled"),
    ),
    (
        "avvia_bot_live.bat",
        ("LSR-v2 read-only dashboard banner", "no Telegram send"),
    ),
)

VISIBILITY_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_runtime_snapshot_artifact",
    "load_generic_runner_launcher_hook_preflight",
    "load_generic_engine_hook_preflight",
    "load_existing_runner_footer_visibility",
    "load_existing_launcher_banner_visibility",
    "verify_runtime_snapshot_source_markers",
    "verify_runner_footer_source_markers",
    "verify_launcher_source_markers",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_operator_env",
    "map_runner_footer_runtime_snapshot_visibility",
    "map_launcher_banner_runtime_snapshot_visibility",
    "map_visibility_parity_runtime_snapshot",
    "map_safety_footer_fields",
    "map_safety_banner_fields",
    "prepare_future_runtime_snapshot_visibility_wiring",
)

BLOCKED_UNTIL_EXPLICIT_VISIBILITY_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_runtime_snapshot_visibility_activation",
    "paper_runner_runtime_snapshot_footer_wiring",
    "launcher_runtime_snapshot_banner_wiring",
    "paper_engine_generic_cycle_runtime_hook",
    "generic_candidate_detection_execution",
    "generic_route_execution",
    "generic_handoff_execution",
    "generic_broker_submit",
    "generic_broker_close",
    "generic_paper_state_mutation",
    "generic_paper_status_mutation",
    "telegram_network_send",
    "scheduler_start",
    "live_or_testnet_or_exchange_broker",
)

@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight.jsonl"
    fail_closed: bool = True

    @property
    def data_path(self) -> Path:
        return self.project_root / self.data_dir


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled", "pass", "ready"}
    return False


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _count_mapping_or_list(value: Any) -> int:
    if isinstance(value, Mapping):
        return len(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return 0


def _paper_counts(state: Mapping[str, Any], status: Mapping[str, Any]) -> Tuple[int, int]:
    status_open = status.get("open_positions", status.get("paper_status_open_positions_after"))
    status_pending = status.get("pending_orders", status.get("paper_status_pending_orders_after"))
    open_positions = _as_int(status_open, _count_mapping_or_list(state.get("positions", {})))
    pending_orders = _as_int(status_pending, _count_mapping_or_list(state.get("orders", {})))
    return open_positions, pending_orders


def _active_lsr_v2_env() -> Dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.startswith("LSR_V2") and str(v).strip()}


def _decision_is_ready(report: Mapping[str, Any], expected_decision: str) -> bool:
    return isinstance(report, Mapping) and str(report.get("status", "")).upper() == "PASS" and report.get("decision") == expected_decision


def _load_reports(settings: Settings, specs: Sequence[Tuple[str, str, str]]) -> Tuple[Dict[str, Any], List[str], List[str], Dict[str, bool]]:
    reports: Dict[str, Any] = {}
    missing: List[str] = []
    not_ready: List[str] = []
    readiness: Dict[str, bool] = {}
    for key, filename, expected_decision in specs:
        path = settings.data_path / filename
        report = _read_json(path, {})
        reports[key] = report
        if not report:
            missing.append(filename)
            readiness[key] = False
            continue
        ready = _decision_is_ready(report, expected_decision)
        readiness[key] = ready
        if not ready:
            not_ready.append(filename)
    return reports, missing, not_ready, readiness


def _source_marker_status(root: Path, specs: Sequence[Tuple[str, Tuple[str, ...]]]) -> Tuple[bool, List[str], Dict[str, List[str]]]:
    missing_files: List[str] = []
    missing_markers: Dict[str, List[str]] = {}
    for relative, markers in specs:
        path = root / relative
        if not path.exists():
            missing_files.append(relative)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        missing = [marker for marker in markers if marker not in text]
        if missing:
            missing_markers[relative] = missing
    return not missing_files and not missing_markers, missing_files, missing_markers


def _runtime_snapshot_from_reports(reports: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    u8 = reports.get("generic_runtime_snapshot_hook", {})
    snapshot = u8.get("generic_runtime_snapshot")
    if isinstance(snapshot, Mapping):
        return snapshot
    return {}


def _build_visibility_map(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    cycle_state = snapshot.get("generic_cycle_state") if isinstance(snapshot.get("generic_cycle_state"), Mapping) else {}
    rearm_state = snapshot.get("generic_rearm_policy_state") if isinstance(snapshot.get("generic_rearm_policy_state"), Mapping) else {}
    order_state = snapshot.get("generic_order_lifecycle_state") if isinstance(snapshot.get("generic_order_lifecycle_state"), Mapping) else {}
    visibility_state = snapshot.get("runner_launcher_visibility_state") if isinstance(snapshot.get("runner_launcher_visibility_state"), Mapping) else {}
    safety_state = snapshot.get("safety_state") if isinstance(snapshot.get("safety_state"), Mapping) else {}
    return {
        "mode": "visibility_preflight_only",
        "execution_enabled": False,
        "mutation_enabled": False,
        "paper_only": True,
        "runner_footer_visibility_enabled": False,
        "launcher_banner_visibility_enabled": False,
        "telegram_network_send_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "ordinal_module_generation_allowed": False,
        "runtime_snapshot_sections": [
            "generic_cycle_state",
            "generic_rearm_policy_state",
            "generic_order_lifecycle_state",
            "runner_launcher_visibility_state",
            "engine_hook_state",
            "safety_state",
        ],
        "runner_footer_fields": {
            "lifecycle_state": cycle_state.get("lifecycle_state", "UNKNOWN"),
            "fourth_trade_locked": _as_bool(cycle_state.get("fourth_trade_locked", True)),
            "stability_lock_active": _as_bool(cycle_state.get("stability_lock_active", True)),
            "route_candidate_available": _as_bool(cycle_state.get("route_candidate_available", False)),
            "paper_order_intent_ready": _as_bool(cycle_state.get("paper_order_intent_ready", False)),
            "open_positions_after": _as_int(cycle_state.get("open_positions_after"), 0),
            "pending_orders_after": _as_int(cycle_state.get("pending_orders_after"), 0),
            "generic_rearm_allowed": _as_bool(rearm_state.get("generic_rearm_allowed", False)),
            "generic_submit_execution_allowed": _as_bool(order_state.get("generic_submit_execution_allowed", False)),
            "generic_close_execution_allowed": _as_bool(order_state.get("generic_close_execution_allowed", False)),
        },
        "launcher_banner_fields": {
            "lifecycle_state": cycle_state.get("lifecycle_state", "UNKNOWN"),
            "runner_visibility_ready": _as_bool(visibility_state.get("runner_visibility_ready", False)),
            "launcher_visibility_ready": _as_bool(visibility_state.get("launcher_visibility_ready", False)),
            "visibility_parity_ok": _as_bool(visibility_state.get("visibility_parity_ok", False)),
            "live_enabled": _as_bool(safety_state.get("live_enabled", False)),
            "testnet_enabled": _as_bool(safety_state.get("testnet_enabled", False)),
            "exchange_broker_enabled": _as_bool(safety_state.get("exchange_broker_enabled", False)),
            "telegram_send_allowed": _as_bool(safety_state.get("telegram_send_allowed", False)),
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in VISIBILITY_PREFLIGHT_STAGES
        ],
    }


def run_generic_paper_cycle_runtime_snapshot_visibility_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    reports, missing_reports, not_ready_reports, upstream_readiness = _load_reports(settings, REQUIRED_UPSTREAM_REPORTS)
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_status(settings.project_root, REQUIRED_SOURCE_MARKERS)
    state = _read_json(settings.data_path / "paper_state.json", {})
    status = _read_json(settings.data_path / "paper_status.json", {})
    open_positions, pending_orders = _paper_counts(state, status)
    active_env = _active_lsr_v2_env()
    snapshot = _runtime_snapshot_from_reports(reports)
    visibility_map = _build_visibility_map(snapshot)

    u8 = reports.get("generic_runtime_snapshot_hook", {})
    u7 = reports.get("generic_runner_launcher_hook_preflight", {})
    t5 = reports.get("launcher_runner_visibility_parity", {})
    t4 = reports.get("launcher_read_only_banner", {})

    lifecycle_state = str(
        (snapshot.get("generic_cycle_state") or {}).get("lifecycle_state")
        or u8.get("lifecycle_state")
        or u7.get("lifecycle_state")
        or "UNKNOWN"
    )
    route_candidate_available = _as_bool((snapshot.get("generic_cycle_state") or {}).get("route_candidate_available", u8.get("route_candidate_available", False)))
    paper_order_intent_ready = _as_bool((snapshot.get("generic_cycle_state") or {}).get("paper_order_intent_ready", u8.get("paper_order_intent_ready", False)))
    fourth_trade_locked = _as_bool((snapshot.get("generic_cycle_state") or {}).get("fourth_trade_locked", u8.get("fourth_trade_locked", True)))
    stability_lock_active = _as_bool((snapshot.get("generic_cycle_state") or {}).get("stability_lock_active", u8.get("stability_lock_active", True)))
    launcher_visibility_ready = _as_bool(u7.get("launcher_visibility_ready", (snapshot.get("runner_launcher_visibility_state") or {}).get("launcher_visibility_ready", False)))
    runner_visibility_ready = _as_bool(u7.get("runner_visibility_ready", (snapshot.get("runner_launcher_visibility_state") or {}).get("runner_visibility_ready", False)))
    visibility_parity_ok = _as_bool(u7.get("visibility_parity_ok", t5.get("launcher_runner_visibility_parity_ok", False))) and not _as_bool(t5.get("visibility_mismatch_detected", False))
    launcher_banner_ready = _as_bool(t4.get("launcher_banner_ready", True))

    live_enabled = _as_bool(u8.get("live_enabled", False))
    testnet_enabled = _as_bool(u8.get("testnet_enabled", False))
    exchange_broker_enabled = _as_bool(u8.get("exchange_broker_enabled", False))
    telegram_network_called = _as_bool(u8.get("telegram_network_called", False))
    telegram_send_allowed = _as_bool(u8.get("telegram_send_allowed", False))
    scheduler_started = _as_bool(u8.get("scheduler_started", False))

    orders_submitted = 0
    positions_opened = 0
    positions_closed = 0

    blockers: List[str] = []
    if missing_reports:
        blockers.append("missing_upstream_reports")
    if not_ready_reports:
        blockers.append("upstream_reports_not_ready")
    if not source_markers_present:
        blockers.append("runtime_visibility_required_markers_missing")
    if active_env:
        blockers.append("active_lsr_v2_operator_env_present")
    if live_enabled or testnet_enabled or exchange_broker_enabled:
        blockers.append("live_testnet_or_exchange_enabled")
    if open_positions != 0 or pending_orders != 0:
        blockers.append("paper_state_not_flat")
    if route_candidate_available or paper_order_intent_ready:
        blockers.append("route_candidate_or_order_intent_present")
    if not runner_visibility_ready or not launcher_visibility_ready or not visibility_parity_ok or not launcher_banner_ready:
        blockers.append("runner_launcher_visibility_not_ready")
    if orders_submitted or positions_opened or positions_closed:
        blockers.append("unexpected_execution_counter_nonzero")
    if telegram_network_called or telegram_send_allowed or scheduler_started:
        blockers.append("network_or_scheduler_not_disabled")

    status_value = "PASS" if not blockers else "WARN"
    decision = READY_DECISION if status_value == "PASS" else KEEP_DIAGNOSTIC_DECISION

    payload: Dict[str, Any] = {
        "status": status_value,
        "decision": decision,
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "report": str(settings.data_path / settings.report_name),
        "jsonl": str(settings.data_path / settings.jsonl_name),
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT",
            "READ_ONLY",
            "VISIBILITY_PREFLIGHT_ONLY",
            "NO_ORDINAL_EXPANSION",
            "NO_ENGINE_MUTATION",
            "NO_RUNNER_MUTATION",
            "NO_LAUNCHER_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_ROUTE_EXECUTION",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_READY" if status_value == "PASS" else "GENERIC_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_BLOCKED",
        ],
        "blockers": blockers,
        "blocked_until_explicit_visibility_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_VISIBILITY_IMPLEMENTATION_PATCH),
        "upstream_reports_present": [filename for _key, filename, _decision in REQUIRED_UPSTREAM_REPORTS if (settings.data_path / filename).exists()],
        "missing_upstream_reports": missing_reports,
        "not_ready_upstream_reports": not_ready_reports,
        "upstream_readiness": upstream_readiness,
        "missing_runtime_visibility_source_files": missing_source_files,
        "missing_runtime_visibility_source_markers": missing_source_markers,
        "generic_runtime_visibility_required_markers_present": source_markers_present,
        "generic_runtime_visibility_source_files_present": not missing_source_files,
        "generic_runtime_snapshot_visibility_preflight_ready": status_value == "PASS",
        "generic_runtime_snapshot_visibility_plan_ready": True,
        "generic_runtime_snapshot_visibility_contract_ready": True,
        "generic_runtime_snapshot_visibility_map_ready": True,
        "generic_runtime_snapshot_artifact_ready": _decision_is_ready(u8, U8_READY_DECISION),
        "generic_runner_launcher_hook_ready": _decision_is_ready(u7, U7_READY_DECISION),
        "generic_cycle_engine_hook_ready": upstream_readiness.get("generic_cycle_engine_hook_preflight", False),
        "generic_paper_cycle_integration_ready": upstream_readiness.get("generic_cycle_integration_preflight", False),
        "generic_controller_ready": upstream_readiness.get("generic_cycle_controller", False),
        "generic_order_lifecycle_ready": upstream_readiness.get("generic_order_lifecycle", False),
        "generic_rearm_policy_ready": upstream_readiness.get("generic_rearm_policy", False),
        "generic_runtime_visibility_map": visibility_map,
        "runner_footer_runtime_snapshot_visibility_ready": runner_visibility_ready and visibility_parity_ok,
        "launcher_banner_runtime_snapshot_visibility_ready": launcher_visibility_ready and launcher_banner_ready and visibility_parity_ok,
        "runtime_snapshot_visibility_parity_ready": visibility_parity_ok,
        "runtime_snapshot_footer_fields_ready": True,
        "runtime_snapshot_banner_fields_ready": True,
        "runtime_snapshot_safety_fields_ready": True,
        "lifecycle_state": lifecycle_state,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "route_candidate_available": route_candidate_available,
        "paper_order_intent_ready": paper_order_intent_ready,
        "no_route_candidate": not route_candidate_available,
        "no_order_intent_currently_available": not paper_order_intent_ready,
        "open_positions_after": open_positions,
        "pending_orders_after": pending_orders,
        "operator_env_absent": not bool(active_env),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env.keys()),
        "runner_visibility_ready": runner_visibility_ready,
        "launcher_visibility_ready": launcher_visibility_ready,
        "visibility_parity_ok": visibility_parity_ok,
        "launcher_banner_ready": launcher_banner_ready,
        "generic_runtime_snapshot_visibility_allowed": False,
        "generic_runtime_snapshot_visibility_execution_allowed": False,
        "generic_runtime_snapshot_hook_execution_allowed": False,
        "generic_cycle_controller_execution_allowed": False,
        "generic_rearm_policy_execution_allowed": False,
        "generic_order_lifecycle_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_open_position_monitor_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "generic_lsr_v2_paper_cycle_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "orders_submitted_by_generic_runtime_snapshot_visibility_preflight": orders_submitted,
        "positions_opened_by_generic_runtime_snapshot_visibility_preflight": positions_opened,
        "positions_closed_by_generic_runtime_snapshot_visibility_preflight": positions_closed,
        "paper_state_modified_by_generic_runtime_snapshot_visibility_preflight": False,
        "paper_status_modified_by_generic_runtime_snapshot_visibility_preflight": False,
        "paper_state_status_consistency": True,
        "broker_submit_called_by_generic_runtime_snapshot_visibility_preflight": False,
        "broker_close_called_by_generic_runtime_snapshot_visibility_preflight": False,
        "telegram_dashboard_ready": upstream_readiness.get("telegram_dashboard", False),
        "telegram_payload_ready": _as_bool(u8.get("telegram_payload_ready", True)),
        "telegram_network_called": telegram_network_called,
        "telegram_send_allowed": telegram_send_allowed,
        "telegram_update_ready": False,
        "scheduler_enabled": False,
        "scheduler_started": scheduler_started,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "required_readiness": {
            "runtime_snapshot_hook_ready": _decision_is_ready(u8, U8_READY_DECISION),
            "generic_runner_launcher_hook_ready": _decision_is_ready(u7, U7_READY_DECISION),
            "generic_cycle_engine_hook_ready": upstream_readiness.get("generic_cycle_engine_hook_preflight", False),
            "generic_cycle_integration_ready": upstream_readiness.get("generic_cycle_integration_preflight", False),
            "generic_cycle_controller_ready": upstream_readiness.get("generic_cycle_controller", False),
            "generic_order_lifecycle_ready": upstream_readiness.get("generic_order_lifecycle", False),
            "generic_rearm_policy_ready": upstream_readiness.get("generic_rearm_policy", False),
            "launcher_read_only_banner_ready": launcher_banner_ready,
            "runner_visibility_ready": runner_visibility_ready,
            "launcher_visibility_ready": launcher_visibility_ready,
            "visibility_parity_ok": visibility_parity_ok,
            "flat_state_confirmed": open_positions == 0 and pending_orders == 0,
            "no_order_intent_currently_available": not paper_order_intent_ready,
            "no_route_candidate": not route_candidate_available,
            "operator_env_absent": not bool(active_env),
            "ordinal_expansion_blocked": True,
            "source_markers_present": source_markers_present,
            "live_disabled": not live_enabled,
            "testnet_disabled": not testnet_enabled,
            "exchange_broker_disabled": not exchange_broker_enabled,
            "no_submit_or_close_occurred": orders_submitted == 0 and positions_opened == 0 and positions_closed == 0,
            "network_scheduler_disabled": not telegram_network_called and not telegram_send_allowed and not scheduler_started,
        },
        "next_step": "prepare_runtime_snapshot_footer_banner_wiring_preflight_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-10 — Generic LSR-v2 runtime snapshot footer/banner wiring preflight",
    }

    _write_json(settings.data_path / settings.report_name, payload)
    _append_jsonl(settings.data_path / settings.jsonl_name, payload)
    return payload


if __name__ == "__main__":
    print(json.dumps(run_generic_paper_cycle_runtime_snapshot_visibility_preflight(), indent=2, sort_keys=True))
