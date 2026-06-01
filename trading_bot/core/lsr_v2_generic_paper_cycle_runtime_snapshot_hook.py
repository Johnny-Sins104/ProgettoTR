"""Generic LSR-v2 paper-cycle read-only runtime snapshot hook.

29.4.4u-8 is intentionally read-only and fail-closed. It consolidates the
validated generic controller, order lifecycle, re-arm policy, engine hook, and
runner/launcher hook preflights into one runtime snapshot artifact. It never
enables candidate detection, routing, handoff, submit, close, state mutation,
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

PROMPT = "29.4.4u-8"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK"
READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_NOT_READY"

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
        "trading_bot/core/paper_engine.py",
        ("PaperTradingEngine", "write_lsr_v2_engine_read_only_artifact_hook_report"),
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

RUNTIME_SNAPSHOT_STAGES: Tuple[str, ...] = (
    "load_generic_runner_launcher_hook_preflight",
    "load_generic_cycle_engine_hook_preflight",
    "load_generic_cycle_integration_preflight",
    "load_generic_cycle_controller",
    "load_generic_order_lifecycle",
    "load_generic_rearm_policy",
    "load_existing_engine_artifact_hook",
    "load_existing_runner_launcher_visibility",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_operator_env",
    "snapshot_generic_cycle_state",
    "snapshot_generic_rearm_policy_state",
    "snapshot_generic_order_lifecycle_state",
    "snapshot_runner_launcher_visibility_state",
    "snapshot_engine_hook_state",
    "snapshot_paper_state_status_safety",
    "publish_read_only_runtime_snapshot_artifact",
)

BLOCKED_UNTIL_EXPLICIT_RUNTIME_HOOK_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_runtime_snapshot_hook_activation",
    "paper_engine_generic_cycle_runtime_hook",
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
    report_name: str = "lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_cycle_runtime_snapshot_hook.jsonl"
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


def _stage_list() -> List[Dict[str, Any]]:
    return [
        {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
        for stage in RUNTIME_SNAPSHOT_STAGES
    ]


def _build_runtime_snapshot(
    *,
    reports: Mapping[str, Any],
    open_positions_after: int,
    pending_orders_after: int,
    active_env: Mapping[str, str],
    live_enabled: bool,
    testnet_enabled: bool,
    exchange_broker_enabled: bool,
) -> Dict[str, Any]:
    u7 = reports.get("generic_runner_launcher_hook_preflight", {}) or {}
    u6 = reports.get("generic_cycle_engine_hook_preflight", {}) or {}
    u5 = reports.get("generic_cycle_integration_preflight", {}) or {}
    u4 = reports.get("generic_rearm_policy", {}) or {}
    u3 = reports.get("generic_order_lifecycle", {}) or {}
    u2 = reports.get("generic_cycle_controller", {}) or {}
    t5 = reports.get("launcher_runner_visibility_parity", {}) or {}
    t4 = reports.get("launcher_read_only_banner", {}) or {}
    engine = reports.get("engine_read_only_artifact_hook", {}) or {}

    return {
        "mode": "read_only_runtime_snapshot",
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "engine_hook_enabled": False,
        "runner_hook_enabled": False,
        "launcher_hook_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "generic_cycle_state": {
            "lifecycle_state": u7.get("lifecycle_state", u6.get("lifecycle_state", "FLAT_LOCKED")),
            "fourth_trade_locked": _as_bool(u7.get("fourth_trade_locked", u6.get("fourth_trade_locked", True))),
            "stability_lock_active": _as_bool(u7.get("stability_lock_active", u6.get("stability_lock_active", True))),
            "route_candidate_available": _as_bool(u7.get("route_candidate_available", u6.get("route_candidate_available", False))),
            "paper_order_intent_ready": _as_bool(u7.get("paper_order_intent_ready", u6.get("paper_order_intent_ready", False))),
            "open_positions_after": open_positions_after,
            "pending_orders_after": pending_orders_after,
        },
        "generic_rearm_policy_state": {
            "ready": _as_bool(u7.get("generic_rearm_policy_ready", True)),
            "generic_rearm_allowed": False,
            "generic_rearm_policy_execution_allowed": False,
            "operator_env_absent": not active_env,
            "operator_env_keys": sorted(active_env.keys()),
            "cooldown_required": True,
            "max_open_positions": 1,
        },
        "generic_order_lifecycle_state": {
            "ready": _as_bool(u7.get("generic_order_lifecycle_ready", True)),
            "paper_order_intent_ready": _as_bool(u3.get("paper_order_intent_ready", False)),
            "generic_order_lifecycle_execution_allowed": False,
            "generic_submit_execution_allowed": False,
            "generic_close_execution_allowed": False,
            "generic_paper_state_mutation_allowed": False,
            "generic_paper_status_mutation_allowed": False,
        },
        "runner_launcher_visibility_state": {
            "runner_visibility_ready": _as_bool(u7.get("runner_visibility_ready", True)),
            "launcher_visibility_ready": _as_bool(u7.get("launcher_visibility_ready", True)),
            "visibility_parity_ok": _as_bool(u7.get("visibility_parity_ok", t5.get("launcher_runner_visibility_parity_ok", True))),
            "launcher_banner_ready": _as_bool(t4.get("launcher_banner_ready", True)),
            "runner_mutation_allowed": False,
            "launcher_mutation_allowed": False,
        },
        "engine_hook_state": {
            "engine_read_only_artifact_hook_ready": _as_bool(u7.get("engine_read_only_artifact_hook_ready", engine.get("engine_artifact_hook_ready", True))),
            "generic_cycle_engine_hook_ready": _as_bool(u7.get("generic_cycle_engine_hook_ready", True)),
            "paper_engine_mutation_allowed": False,
        },
        "safety_state": {
            "live_enabled": live_enabled,
            "testnet_enabled": testnet_enabled,
            "exchange_broker_enabled": exchange_broker_enabled,
            "paper_state_mutation_allowed": False,
            "paper_status_mutation_allowed": False,
            "telegram_network_called": False,
            "telegram_send_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "positions_closed": 0,
        },
        "stages": _stage_list(),
    }


def run_generic_paper_cycle_runtime_snapshot_hook(settings: Optional[Settings] = None) -> Dict[str, Any]:
    if settings is None:
        settings = Settings()

    data_dir = settings.data_path
    reports, present_reports, missing_reports, upstream_ready = _load_reports(settings, REQUIRED_UPSTREAM_REPORTS)
    paper_state = _read_json(data_dir / "paper_state.json", {})
    paper_status = _read_json(data_dir / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(paper_state, paper_status)
    active_env = _active_lsr_v2_env()
    source_markers_present, missing_source_files, missing_source_markers = _check_source_markers(settings.project_root)

    u7 = reports.get("generic_runner_launcher_hook_preflight", {}) or {}
    u6 = reports.get("generic_cycle_engine_hook_preflight", {}) or {}
    u5 = reports.get("generic_cycle_integration_preflight", {}) or {}
    u4 = reports.get("generic_rearm_policy", {}) or {}
    u3 = reports.get("generic_order_lifecycle", {}) or {}
    u2 = reports.get("generic_cycle_controller", {}) or {}
    postmortem = reports.get("three_trade_postmortem", {}) or {}
    engine = reports.get("engine_read_only_artifact_hook", {}) or {}
    dashboard = reports.get("telegram_dashboard", {}) or {}
    lifecycle = reports.get("lifecycle_auto_monitor", {}) or {}

    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    fourth_trade_locked = _as_bool(u7.get("fourth_trade_locked", u6.get("fourth_trade_locked", postmortem.get("fourth_trade_locked", True))))
    stability_lock_active = _as_bool(u7.get("stability_lock_active", u6.get("stability_lock_active", postmortem.get("stability_lock_active", True))))
    ordinal_expansion_blocked = (
        u7.get("ordinal_trade_patch_expansion_allowed") is False
        and u6.get("ordinal_trade_patch_expansion_allowed") is False
        and u5.get("ordinal_trade_patch_expansion_allowed") is False
        and u4.get("ordinal_trade_patch_expansion_allowed") is False
        and u3.get("ordinal_trade_patch_expansion_allowed") is False
        and u2.get("ordinal_trade_patch_expansion_allowed") is False
        and u7.get("fifth_trade_patch_allowed") is False
        and u7.get("sixth_trade_patch_allowed") is False
        and u7.get("seventh_trade_patch_allowed") is False
    )

    no_order_intent = not _as_bool(u7.get("paper_order_intent_ready", u6.get("paper_order_intent_ready", u5.get("paper_order_intent_ready", False))))
    no_route_candidate = not _as_bool(u7.get("route_candidate_available", u6.get("route_candidate_available", False)))
    no_submit_or_close = (
        _as_int(u7.get("orders_submitted_by_generic_runner_launcher_hook_preflight"), 0) == 0
        and _as_int(u7.get("positions_opened_by_generic_runner_launcher_hook_preflight"), 0) == 0
        and _as_int(u7.get("positions_closed_by_generic_runner_launcher_hook_preflight"), 0) == 0
        and not _as_bool(u7.get("broker_submit_called_by_generic_runner_launcher_hook_preflight", False))
        and not _as_bool(u7.get("broker_close_called_by_generic_runner_launcher_hook_preflight", False))
    )

    live_enabled = _as_bool(u7.get("live_enabled", False)) or _as_bool(engine.get("live_enabled", False)) or _as_bool(os.environ.get("LIVE_ENABLED"))
    testnet_enabled = _as_bool(u7.get("testnet_enabled", False)) or _as_bool(engine.get("testnet_enabled", False)) or _as_bool(os.environ.get("TESTNET_ENABLED"))
    exchange_broker_enabled = _as_bool(u7.get("exchange_broker_enabled", False)) or _as_bool(engine.get("exchange_broker_enabled", False)) or _as_bool(os.environ.get("EXCHANGE_BROKER_ENABLED"))

    runtime_snapshot = _build_runtime_snapshot(
        reports=reports,
        open_positions_after=open_positions_after,
        pending_orders_after=pending_orders_after,
        active_env=active_env,
        live_enabled=live_enabled,
        testnet_enabled=testnet_enabled,
        exchange_broker_enabled=exchange_broker_enabled,
    )

    required_readiness = {
        "generic_runner_launcher_hook_ready": upstream_ready.get("generic_runner_launcher_hook_preflight", False),
        "generic_cycle_engine_hook_ready": upstream_ready.get("generic_cycle_engine_hook_preflight", False),
        "generic_cycle_integration_ready": upstream_ready.get("generic_cycle_integration_preflight", False),
        "generic_rearm_policy_ready": upstream_ready.get("generic_rearm_policy", False),
        "generic_order_lifecycle_ready": upstream_ready.get("generic_order_lifecycle", False),
        "generic_cycle_controller_ready": upstream_ready.get("generic_cycle_controller", False),
        "generic_refactor_preflight_ready": upstream_ready.get("generic_refactor_preflight", False),
        "launcher_runner_visibility_parity_ready": upstream_ready.get("launcher_runner_visibility_parity", False),
        "launcher_read_only_banner_ready": upstream_ready.get("launcher_read_only_banner", False),
        "engine_read_only_artifact_hook_ready": upstream_ready.get("engine_read_only_artifact_hook", False),
        "lifecycle_auto_monitor_ready": upstream_ready.get("lifecycle_auto_monitor", False),
        "telegram_dashboard_ready": upstream_ready.get("telegram_dashboard", False),
        "three_trade_postmortem_ready": upstream_ready.get("three_trade_postmortem", False),
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
        blockers.append("runtime_snapshot_source_markers_missing")
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

    result: Dict[str, Any] = {
        "prompt": PROMPT,
        "generated_at": _utc_now(),
        "event_type": EVENT_TYPE,
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK",
            "READ_ONLY",
            "RUNTIME_SNAPSHOT_ONLY",
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
            "GENERIC_RUNTIME_SNAPSHOT_HOOK_READY" if ready else "GENERIC_RUNTIME_SNAPSHOT_HOOK_BLOCKED_DIAGNOSTIC",
        ],
        "blockers": blockers,
        "blocked_until_explicit_runtime_hook_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_RUNTIME_HOOK_IMPLEMENTATION_PATCH),
        "generic_runtime_snapshot_hook_ready": ready,
        "generic_runtime_snapshot_hook_plan_ready": True,
        "generic_runtime_snapshot_contract_ready": True,
        "generic_runtime_snapshot_map_ready": True,
        "generic_runtime_snapshot_artifact_ready": ready,
        "generic_cycle_state_snapshot_ready": ready,
        "generic_rearm_policy_state_snapshot_ready": ready,
        "generic_order_lifecycle_state_snapshot_ready": ready,
        "generic_runner_launcher_state_snapshot_ready": ready,
        "generic_engine_hook_state_snapshot_ready": ready,
        "generic_safety_snapshot_ready": ready,
        "generic_runtime_snapshot": runtime_snapshot,
        "required_readiness": required_readiness,
        "upstream_readiness": upstream_ready,
        "upstream_reports_present": present_reports,
        "missing_upstream_reports": missing_reports,
        "generic_runtime_snapshot_required_markers_present": source_markers_present,
        "generic_runtime_snapshot_source_files_present": not missing_source_files,
        "missing_generic_runtime_snapshot_source_files": missing_source_files,
        "missing_generic_runtime_snapshot_source_markers": missing_source_markers,
        "generic_runner_launcher_hook_ready": upstream_ready.get("generic_runner_launcher_hook_preflight", False),
        "generic_cycle_engine_hook_ready": upstream_ready.get("generic_cycle_engine_hook_preflight", False),
        "generic_paper_cycle_integration_ready": upstream_ready.get("generic_cycle_integration_preflight", False),
        "generic_controller_ready": upstream_ready.get("generic_cycle_controller", False),
        "generic_order_lifecycle_ready": upstream_ready.get("generic_order_lifecycle", False),
        "generic_rearm_policy_ready": upstream_ready.get("generic_rearm_policy", False),
        "launcher_visibility_ready": upstream_ready.get("launcher_read_only_banner", False),
        "runner_visibility_ready": upstream_ready.get("launcher_runner_visibility_parity", False),
        "engine_read_only_artifact_hook_ready": upstream_ready.get("engine_read_only_artifact_hook", False),
        "telegram_dashboard_ready": upstream_ready.get("telegram_dashboard", False),
        "telegram_payload_ready": _as_bool(dashboard.get("telegram_payload_ready", True)),
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "telegram_update_ready": _as_bool(dashboard.get("telegram_update_ready", False)),
        "lifecycle_auto_monitor_ready": upstream_ready.get("lifecycle_auto_monitor", False),
        "lifecycle_state": u7.get("lifecycle_state", lifecycle.get("lifecycle_state", "FLAT_LOCKED")),
        "flat_state_confirmed": flat_state_confirmed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": not active_env,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env.keys()),
        "route_candidate_available": False,
        "paper_order_intent_ready": False,
        "no_route_candidate": no_route_candidate,
        "no_order_intent_currently_available": no_order_intent,
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "paper_status_open_positions_after": open_positions_after,
        "paper_status_pending_orders_after": pending_orders_after,
        "paper_state_status_consistency": flat_state_confirmed,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_runtime_snapshot_hook_allowed": False,
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
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_state_modified_by_generic_runtime_snapshot_hook": False,
        "paper_status_modified_by_generic_runtime_snapshot_hook": False,
        "orders_submitted_by_generic_runtime_snapshot_hook": 0,
        "positions_opened_by_generic_runtime_snapshot_hook": 0,
        "positions_closed_by_generic_runtime_snapshot_hook": 0,
        "broker_submit_called_by_generic_runtime_snapshot_hook": False,
        "broker_close_called_by_generic_runtime_snapshot_hook": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "next_step": "prepare_generic_runtime_snapshot_visibility_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-9 — Generic LSR-v2 paper cycle runtime snapshot visibility preflight",
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
    result = run_generic_paper_cycle_runtime_snapshot_hook()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
