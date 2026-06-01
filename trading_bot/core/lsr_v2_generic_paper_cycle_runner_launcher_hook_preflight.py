"""Generic LSR-v2 paper-cycle runner/launcher hook preflight.

29.4.4u-7 is intentionally read-only and fail-closed. It verifies that the
validated generic LSR-v2 paper-cycle engine-hook preflight can be surfaced by
runner and launcher flows through future read-only visibility hooks, without
enabling candidate detection, routing, handoff, submit, close, state mutation,
scheduler activity, Telegram network sends, live, testnet, or exchange broker
access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PROMPT = "29.4.4u-7"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_NOT_READY"

U6_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT_READY"
U5_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY"
U4_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY"
U3_READY_DECISION = "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY"
U2_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY"
U1_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"
T5_READY_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
T4_READY_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY"
T2_READY_DECISION = "PAPER_ONCE_CONSOLE_SUMMARY_READY"
T1_READY_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"

REQUIRED_UPSTREAM_REPORTS: Tuple[Tuple[str, str, str], ...] = (
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

OPTIONAL_UPSTREAM_REPORTS: Tuple[Tuple[str, str, str], ...] = (
    ("paper_once_console_summary", "paper_once_console_summary_report.json", T2_READY_DECISION),
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
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
    (
        "trading_bot/core/paper_engine.py",
        ("PaperTradingEngine", "write_lsr_v2_engine_read_only_artifact_hook_report"),
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
)

RUNNER_LAUNCHER_HOOK_STAGES: Tuple[str, ...] = (
    "load_generic_cycle_engine_hook_preflight",
    "load_generic_cycle_integration_preflight",
    "load_existing_runner_footer_visibility",
    "load_existing_launcher_banner_visibility",
    "verify_run_paper_trading_source_markers",
    "verify_avvia_bot_live_source_markers",
    "verify_avvia_bot_live_bat_source_markers",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_operator_env",
    "map_runner_footer_generic_cycle_snapshot",
    "map_launcher_banner_generic_cycle_snapshot",
    "map_runner_launcher_safety_snapshot",
    "prepare_future_runner_read_only_generic_cycle_hook",
    "prepare_future_launcher_read_only_generic_cycle_hook",
)

BLOCKED_UNTIL_EXPLICIT_RUNNER_LAUNCHER_HOOK_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_runner_hook_activation",
    "generic_launcher_hook_activation",
    "paper_runner_generic_cycle_runtime_hook",
    "launcher_generic_cycle_runtime_hook",
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
    report_name: str = "lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.jsonl"
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
    present: List[str] = []
    missing: List[str] = []
    readiness: Dict[str, bool] = {}
    for key, filename, expected_decision in specs:
        payload = _read_json(settings.data_path / filename, {})
        reports[key] = payload
        if payload:
            present.append(filename)
        else:
            missing.append(filename)
        readiness[key] = _decision_is_ready(payload, expected_decision)
    return reports, present, missing, readiness


def _check_source_markers(project_root: Path) -> Tuple[bool, List[str], Dict[str, List[str]]]:
    missing_files: List[str] = []
    missing_markers: Dict[str, List[str]] = {}
    for relative, markers in REQUIRED_SOURCE_MARKERS:
        path = project_root / relative
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            missing_files.append(relative)
            continue
        missing = [marker for marker in markers if marker not in content]
        if missing:
            missing_markers[relative] = missing
    return not missing_files and not missing_markers, missing_files, missing_markers


def _build_runner_launcher_hook_map() -> Dict[str, Any]:
    return {
        "mode": "preflight_only",
        "paper_only": True,
        "runner_hook_enabled": False,
        "launcher_hook_enabled": False,
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "source_integration_points": {
            "paper_runner": "trading_bot/run_paper_trading.py",
            "python_launcher": "trading_bot/avvia_bot_live.py",
            "windows_launcher": "avvia_bot_live.bat",
            "generic_engine_hook_preflight": "core/lsr_v2_generic_paper_cycle_engine_hook_preflight.py",
            "generic_cycle_controller": "core/lsr_v2_paper_cycle_controller.py",
            "generic_order_lifecycle": "core/lsr_v2_paper_order_lifecycle.py",
            "generic_rearm_policy": "core/lsr_v2_supervised_rearm_policy.py",
            "existing_launcher_banner": "core/lsr_v2_launcher_read_only_dashboard_banner.py",
            "existing_runner_footer": "core/paper_once_runner_footer.py",
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in RUNNER_LAUNCHER_HOOK_STAGES
        ],
    }


def run_generic_paper_cycle_runner_launcher_hook_preflight(settings: Optional[Settings] = None) -> Dict[str, Any]:
    if settings is None:
        settings = Settings()

    data_dir = settings.data_path
    reports, present_reports, missing_reports, upstream_ready = _load_reports(settings, REQUIRED_UPSTREAM_REPORTS)
    optional_reports, optional_present, _optional_missing, optional_ready = _load_reports(settings, OPTIONAL_UPSTREAM_REPORTS)

    paper_state = _read_json(data_dir / "paper_state.json", {})
    paper_status = _read_json(data_dir / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(paper_state, paper_status)
    active_env = _active_lsr_v2_env()
    source_markers_present, missing_source_files, missing_source_markers = _check_source_markers(settings.project_root)

    u6 = reports.get("generic_cycle_engine_hook_preflight", {})
    u5 = reports.get("generic_cycle_integration_preflight", {})
    u4 = reports.get("generic_rearm_policy", {})
    u3 = reports.get("generic_order_lifecycle", {})
    u2 = reports.get("generic_cycle_controller", {})
    parity = reports.get("launcher_runner_visibility_parity", {})
    launcher_banner = reports.get("launcher_read_only_banner", {})
    engine_hook = reports.get("engine_read_only_artifact_hook", {})
    dashboard = reports.get("telegram_dashboard", {})
    postmortem = reports.get("three_trade_postmortem", {})

    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    fourth_trade_locked = _as_bool(
        u6.get("fourth_trade_locked", u5.get("fourth_trade_locked", u4.get("fourth_trade_locked", postmortem.get("fourth_trade_locked", True))))
    )
    stability_lock_active = _as_bool(
        u6.get("stability_lock_active", u5.get("stability_lock_active", u4.get("stability_lock_active", postmortem.get("stability_lock_active", True))))
    )

    ordinal_expansion_blocked = (
        u6.get("ordinal_trade_patch_expansion_allowed") is False
        and u5.get("ordinal_trade_patch_expansion_allowed") is False
        and u4.get("ordinal_trade_patch_expansion_allowed") is False
        and u3.get("ordinal_trade_patch_expansion_allowed") is False
        and u2.get("ordinal_trade_patch_expansion_allowed") is False
        and u6.get("fifth_trade_patch_allowed") is False
        and u6.get("sixth_trade_patch_allowed") is False
        and u6.get("seventh_trade_patch_allowed") is False
    )

    no_order_intent = not _as_bool(u6.get("paper_order_intent_ready", u5.get("paper_order_intent_ready", u3.get("paper_order_intent_ready", False))))
    no_route_candidate = not _as_bool(u6.get("route_candidate_available", u5.get("route_candidate_available", False)))
    no_submit_or_close = (
        _as_int(u6.get("orders_submitted_by_generic_cycle_engine_hook_preflight"), 0) == 0
        and _as_int(u6.get("positions_opened_by_generic_cycle_engine_hook_preflight"), 0) == 0
        and _as_int(u6.get("positions_closed_by_generic_cycle_engine_hook_preflight"), 0) == 0
        and not _as_bool(u6.get("broker_submit_called_by_generic_cycle_engine_hook_preflight", False))
        and not _as_bool(u6.get("broker_close_called_by_generic_cycle_engine_hook_preflight", False))
    )

    launcher_visibility_ready = upstream_ready.get("launcher_read_only_banner", False) and _as_bool(
        launcher_banner.get("launcher_banner_ready", True)
    )
    runner_visibility_ready = upstream_ready.get("launcher_runner_visibility_parity", False) and _as_bool(
        parity.get("launcher_runner_visibility_parity_ok", True)
    )
    visibility_parity_ok = _as_bool(parity.get("launcher_runner_visibility_parity_ok", True)) and not _as_bool(
        parity.get("visibility_mismatch_detected", False)
    )

    live_enabled = _as_bool(u6.get("live_enabled", False)) or _as_bool(engine_hook.get("live_enabled", False)) or _as_bool(os.environ.get("LIVE_ENABLED"))
    testnet_enabled = _as_bool(u6.get("testnet_enabled", False)) or _as_bool(engine_hook.get("testnet_enabled", False)) or _as_bool(os.environ.get("TESTNET_ENABLED"))
    exchange_broker_enabled = _as_bool(u6.get("exchange_broker_enabled", False)) or _as_bool(engine_hook.get("exchange_broker_enabled", False)) or _as_bool(os.environ.get("EXCHANGE_BROKER_ENABLED"))

    required_readiness = {
        "generic_cycle_engine_hook_ready": upstream_ready.get("generic_cycle_engine_hook_preflight", False),
        "generic_cycle_integration_ready": upstream_ready.get("generic_cycle_integration_preflight", False),
        "generic_rearm_policy_ready": upstream_ready.get("generic_rearm_policy", False),
        "generic_order_lifecycle_ready": upstream_ready.get("generic_order_lifecycle", False),
        "generic_cycle_controller_ready": upstream_ready.get("generic_cycle_controller", False),
        "launcher_visibility_ready": launcher_visibility_ready,
        "runner_visibility_ready": runner_visibility_ready,
        "visibility_parity_ok": visibility_parity_ok,
        "engine_read_only_artifact_hook_ready": upstream_ready.get("engine_read_only_artifact_hook", False),
        "upstream_reports_ready": all(upstream_ready.values()),
        "source_markers_present": source_markers_present,
        "flat_state_confirmed": flat_state_confirmed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": not active_env,
        "ordinal_expansion_blocked": ordinal_expansion_blocked,
        "no_order_intent_currently_available": no_order_intent,
        "no_route_candidate": no_route_candidate,
        "no_submit_or_close_occurred": no_submit_or_close,
        "live_disabled": not live_enabled,
        "testnet_disabled": not testnet_enabled,
        "exchange_broker_disabled": not exchange_broker_enabled,
    }

    blockers: List[str] = []
    if missing_reports:
        blockers.append("missing_upstream_reports")
    if not all(upstream_ready.values()):
        blockers.append("upstream_reports_not_ready")
    if not source_markers_present:
        blockers.append("generic_runner_launcher_hook_source_markers_missing")
    if not launcher_visibility_ready:
        blockers.append("launcher_visibility_not_ready")
    if not runner_visibility_ready:
        blockers.append("runner_visibility_not_ready")
    if not visibility_parity_ok:
        blockers.append("visibility_parity_mismatch")
    if not flat_state_confirmed:
        blockers.append("paper_state_not_flat")
    if not fourth_trade_locked:
        blockers.append("fourth_trade_not_locked")
    if not stability_lock_active:
        blockers.append("stability_lock_not_active")
    if active_env:
        blockers.append("active_lsr_v2_operator_env_present")
    if not ordinal_expansion_blocked:
        blockers.append("ordinal_expansion_not_blocked")
    if not no_submit_or_close:
        blockers.append("unexpected_submit_or_close_detected")
    if live_enabled or testnet_enabled or exchange_broker_enabled:
        blockers.append("live_testnet_or_exchange_enabled")

    ready = not blockers
    runner_launcher_map = _build_runner_launcher_hook_map()

    result: Dict[str, Any] = {
        "prompt": PROMPT,
        "generated_at": _utc_now(),
        "event_type": EVENT_TYPE,
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT",
            "READ_ONLY",
            "PREFLIGHT_ONLY",
            "NO_ORDINAL_EXPANSION",
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
        ] + (["GENERIC_RUNNER_LAUNCHER_HOOK_PREFLIGHT_READY"] if ready else []),
        "blockers": blockers,
        "blocked_until_explicit_runner_launcher_hook_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_RUNNER_LAUNCHER_HOOK_IMPLEMENTATION_PATCH),
        "generic_runner_launcher_hook_preflight_ready": ready,
        "generic_runner_launcher_hook_plan_ready": ready,
        "generic_runner_launcher_hook_contract_ready": ready,
        "generic_runner_launcher_hook_map_ready": ready,
        "generic_runner_launcher_source_files_present": not missing_source_files,
        "generic_runner_launcher_required_markers_present": not missing_source_markers,
        "missing_generic_runner_launcher_source_files": missing_source_files,
        "missing_generic_runner_launcher_source_markers": missing_source_markers,
        "generic_paper_cycle_runner_launcher_hook_map": runner_launcher_map,
        "generic_cycle_engine_hook_ready": upstream_ready.get("generic_cycle_engine_hook_preflight", False),
        "generic_paper_cycle_integration_ready": upstream_ready.get("generic_cycle_integration_preflight", False),
        "generic_controller_ready": upstream_ready.get("generic_cycle_controller", False),
        "generic_order_lifecycle_ready": upstream_ready.get("generic_order_lifecycle", False),
        "generic_rearm_policy_ready": upstream_ready.get("generic_rearm_policy", False),
        "engine_read_only_artifact_hook_ready": upstream_ready.get("engine_read_only_artifact_hook", False),
        "launcher_visibility_ready": launcher_visibility_ready,
        "runner_visibility_ready": runner_visibility_ready,
        "visibility_parity_ok": visibility_parity_ok,
        "paper_once_console_summary_optional_ready": optional_ready.get("paper_once_console_summary", False),
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_runner_launcher_hook_allowed": False,
        "generic_runner_launcher_hook_execution_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "paper_engine_mutation_allowed": False,
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
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "paper_order_intent_ready": not no_order_intent,
        "route_candidate_available": not no_route_candidate,
        "no_order_intent_currently_available": no_order_intent,
        "no_route_candidate": no_route_candidate,
        "lifecycle_state": u6.get("lifecycle_state", "FLAT_LOCKED"),
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "flat_state_confirmed": flat_state_confirmed,
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "paper_status_open_positions_after": open_positions_after,
        "paper_status_pending_orders_after": pending_orders_after,
        "operator_env_absent": not active_env,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env.keys()),
        "orders_submitted_by_generic_runner_launcher_hook_preflight": 0,
        "positions_opened_by_generic_runner_launcher_hook_preflight": 0,
        "positions_closed_by_generic_runner_launcher_hook_preflight": 0,
        "broker_submit_called_by_generic_runner_launcher_hook_preflight": False,
        "broker_close_called_by_generic_runner_launcher_hook_preflight": False,
        "paper_state_modified_by_generic_runner_launcher_hook_preflight": False,
        "paper_status_modified_by_generic_runner_launcher_hook_preflight": False,
        "runner_modified_by_generic_runner_launcher_hook_preflight": False,
        "launcher_modified_by_generic_runner_launcher_hook_preflight": False,
        "paper_state_status_consistency": True,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "telegram_dashboard_ready": upstream_ready.get("telegram_dashboard", False),
        "telegram_payload_ready": _as_bool(dashboard.get("telegram_payload_ready", False)),
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "required_readiness": required_readiness,
        "upstream_readiness": upstream_ready,
        "optional_upstream_readiness": optional_ready,
        "upstream_reports_present": present_reports,
        "optional_upstream_reports_present": optional_present,
        "missing_upstream_reports": missing_reports,
        "recommended_next_patch": "29.4.4u-8 — Generic LSR-v2 paper cycle read-only runtime snapshot hook",
        "next_step": "prepare_generic_cycle_read_only_runtime_snapshot_hook_or_wait_for_real_candidate",
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_dir / settings.report_name),
        "jsonl": str(data_dir / settings.jsonl_name),
    }

    _write_json(data_dir / settings.report_name, result)
    _append_jsonl(data_dir / settings.jsonl_name, result)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    _ = argv
    result = run_generic_paper_cycle_runner_launcher_hook_preflight()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
