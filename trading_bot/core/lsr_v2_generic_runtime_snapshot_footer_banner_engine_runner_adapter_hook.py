"""Generic LSR-v2 runtime snapshot footer/banner engine-runner read-only adapter hook.

29.4.4u-13 is intentionally read-only and fail-closed. It converts the
validated engine-runner adapter preflight into a reusable read-only adapter
payload hook between the footer/banner wiring hook, Paper Engine, paper runner,
Python launcher, Windows launcher, and console visibility. It never enables
candidate detection, routing, handoff, submit, close, state mutation, scheduler
activity, Telegram network sends, live, testnet, or exchange broker access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-13"
EVENT_TYPE = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK"
READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_NOT_READY"

U12_READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_ADAPTER_PREFLIGHT_READY"
U11_READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_READ_ONLY_WIRING_HOOK_READY"
U10_READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT_READY"
U9_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT_READY"
U8_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK_READY"
U7_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT_READY"
U6_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT_READY"
U5_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_INTEGRATION_PREFLIGHT_READY"
U4_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY"
U3_READY_DECISION = "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY"
U2_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY"
T5_READY_DECISION = "LSR_V2_LAUNCHER_RUNNER_VISIBILITY_PARITY_AUDIT_READY"
T4_READY_DECISION = "LSR_V2_LAUNCHER_READ_ONLY_DASHBOARD_BANNER_READY"
T1_READY_DECISION = "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_READY"

REQUIRED_UPSTREAM_REPORTS: Tuple[Tuple[str, str, str], ...] = (
    ("engine_runner_adapter_preflight", "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_report.json", U12_READY_DECISION),
    ("footer_banner_read_only_wiring_hook", "lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook_report.json", U11_READY_DECISION),
    ("footer_banner_wiring_preflight", "lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight_report.json", U10_READY_DECISION),
    ("runtime_snapshot_visibility_preflight", "lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight_report.json", U9_READY_DECISION),
    ("generic_runtime_snapshot_hook", "lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json", U8_READY_DECISION),
    ("generic_runner_launcher_hook_preflight", "lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight_report.json", U7_READY_DECISION),
    ("generic_cycle_engine_hook_preflight", "lsr_v2_generic_paper_cycle_engine_hook_preflight_report.json", U6_READY_DECISION),
    ("generic_cycle_integration_preflight", "lsr_v2_generic_paper_cycle_integration_preflight_report.json", U5_READY_DECISION),
    ("generic_rearm_policy", "lsr_v2_supervised_rearm_policy_draft_report.json", U4_READY_DECISION),
    ("generic_order_lifecycle", "lsr_v2_paper_order_lifecycle_draft_report.json", U3_READY_DECISION),
    ("generic_cycle_controller", "lsr_v2_paper_cycle_controller_draft_report.json", U2_READY_DECISION),
    ("launcher_runner_visibility_parity", "lsr_v2_launcher_runner_visibility_parity_audit_report.json", T5_READY_DECISION),
    ("launcher_read_only_banner", "lsr_v2_launcher_read_only_dashboard_banner_report.json", T4_READY_DECISION),
    ("engine_read_only_artifact_hook", "lsr_v2_engine_read_only_artifact_hook_report.json", T1_READY_DECISION),
    ("lifecycle_auto_monitor", "lsr_v2_trade_lifecycle_auto_monitor_report.json", "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"),
    ("telegram_dashboard", "lsr_v2_telegram_trade_dashboard_report.json", "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"),
    ("three_trade_postmortem", "lsr_v2_three_trade_postmortem_stability_lock_report.json", "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"),
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight.py",
        ("GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_ADAPTER_PREFLIGHT", "generic_engine_runner_adapter_map"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook.py",
        ("GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_READ_ONLY_WIRING_HOOK", "generic_runtime_snapshot_footer_banner_read_only_wiring_payload"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK", "generic_runtime_snapshot"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_engine_hook_preflight.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_ENGINE_HOOK_PREFLIGHT", "generic_paper_cycle_engine_hook_map"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT", "generic_paper_cycle_runner_launcher_hook_map"),
    ),
    (
        "trading_bot/core/paper_engine.py",
        ("PaperTradingEngine",),
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

READ_ONLY_ADAPTER_STAGES: Tuple[str, ...] = (
    "load_engine_runner_adapter_preflight",
    "load_footer_banner_read_only_wiring_hook",
    "load_runtime_snapshot_artifact",
    "verify_engine_runner_adapter_source_markers",
    "verify_paper_engine_source_markers",
    "verify_runner_source_markers",
    "verify_launcher_source_markers",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_operator_env",
    "build_engine_read_only_adapter_payload",
    "build_paper_runner_adapter_payload",
    "build_launcher_adapter_payload",
    "build_console_visibility_adapter_payload",
    "build_adapter_safety_payload",
    "verify_engine_runner_launcher_read_only_parity",
    "publish_read_only_engine_runner_adapter_artifact",
)

BLOCKED_UNTIL_EXPLICIT_ADAPTER_RUNTIME_PATCH: Tuple[str, ...] = (
    "engine_runner_read_only_adapter_activation",
    "paper_engine_runtime_snapshot_adapter_mutation",
    "paper_runner_runtime_snapshot_adapter_mutation",
    "launcher_runtime_snapshot_adapter_mutation",
    "console_runtime_snapshot_adapter_mutation",
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
    report_name: str = "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json"
    jsonl_name: str = "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.jsonl"
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
    return {key: value for key, value in os.environ.items() if key.startswith("LSR_V2") and value not in ("", None)}


def _load_upstream_reports(data_path: Path) -> Tuple[Dict[str, Mapping[str, Any]], List[str], List[str]]:
    reports: Dict[str, Mapping[str, Any]] = {}
    missing: List[str] = []
    not_ready: List[str] = []
    for key, filename, expected_decision in REQUIRED_UPSTREAM_REPORTS:
        path = data_path / filename
        payload = _read_json(path, {})
        if not payload:
            missing.append(filename)
            reports[key] = {}
            continue
        reports[key] = payload
        if payload.get("status") != "PASS" or payload.get("decision") != expected_decision:
            not_ready.append(filename)
    return reports, missing, not_ready


def _check_source_markers(project_root: Path) -> Tuple[List[str], Dict[str, List[str]]]:
    missing_files: List[str] = []
    missing_markers: Dict[str, List[str]] = {}
    for relative_path, markers in REQUIRED_SOURCE_MARKERS:
        path = project_root / relative_path
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            missing_files.append(relative_path)
            continue
        absent = [marker for marker in markers if marker not in text]
        if absent:
            missing_markers[relative_path] = absent
    return missing_files, missing_markers


def _safe_map_get(mapping: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = mapping
    for part in path:
        if not isinstance(current, Mapping):
            return default
        current = current.get(part)
    return default if current is None else current


def _safe_upstream_bool(reports: Mapping[str, Mapping[str, Any]], key: str, field: str, default: bool = False) -> bool:
    return _as_bool(reports.get(key, {}).get(field, default))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _build_read_only_adapter_payload(
    *,
    adapter_preflight_map: Mapping[str, Any],
    read_only_wiring_payload: Mapping[str, Any],
    runtime_snapshot: Mapping[str, Any],
) -> Dict[str, Any]:
    bridge = _mapping(adapter_preflight_map.get("adapter_payload_bridge"))
    runner_footer_payload = dict(_mapping(bridge.get("runner_footer_payload") or read_only_wiring_payload.get("runner_footer_payload")))
    launcher_banner_payload = dict(_mapping(bridge.get("launcher_banner_payload") or read_only_wiring_payload.get("launcher_banner_payload")))
    console_visibility_payload = dict(_mapping(bridge.get("console_visibility_payload") or read_only_wiring_payload.get("console_visibility_payload")))
    safety_payload = dict(_mapping(bridge.get("safety_payload") or read_only_wiring_payload.get("safety_payload")))
    runtime_sections = list(bridge.get("runtime_snapshot_sections") or read_only_wiring_payload.get("runtime_snapshot_sections") or runtime_snapshot.get("runtime_snapshot_sections", []))
    return {
        "mode": "engine_runner_read_only_adapter_hook",
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "engine_adapter_enabled": True,
        "paper_runner_adapter_enabled": True,
        "launcher_adapter_enabled": True,
        "console_visibility_adapter_enabled": True,
        "runtime_snapshot_visible_read_only": _as_bool(bridge.get("runtime_snapshot_visible_read_only", read_only_wiring_payload.get("runtime_snapshot_visible_read_only", True))),
        "runtime_snapshot_sections": runtime_sections,
        "engine_read_only_adapter_payload": {
            "generic_lsr_v2_runtime_snapshot": "READY_READ_ONLY",
            "runtime_snapshot_visible_read_only": True,
            "paper_engine_mutation_allowed": False,
            "execution_enabled": False,
            "paper_only": True,
        },
        "paper_runner_adapter_payload": runner_footer_payload,
        "launcher_adapter_payload": launcher_banner_payload,
        "console_visibility_adapter_payload": console_visibility_payload,
        "adapter_safety_payload": safety_payload,
        "contracts": {
            "engine_read_only_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "paper_engine_mutation_allowed": False,
                "reads_runtime_snapshot_artifact": True,
            },
            "paper_runner_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "runner_mutation_allowed": False,
                "reads_footer_payload": True,
            },
            "launcher_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "launcher_mutation_allowed": False,
                "reads_banner_payload": True,
            },
            "console_visibility_adapter": {
                "enabled_read_only": True,
                "execution_allowed": False,
                "mutation_allowed": False,
                "reads_console_payload": True,
            },
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in READ_ONLY_ADAPTER_STAGES
        ],
    }


def run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    reports, missing_reports, not_ready_reports = _load_upstream_reports(data_path)
    missing_source_files, missing_source_markers = _check_source_markers(settings.project_root)
    paper_state = _read_json(data_path / "paper_state.json", {})
    paper_status = _read_json(data_path / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(paper_state, paper_status)
    active_env = _active_lsr_v2_env()

    u12_report = reports.get("engine_runner_adapter_preflight", {})
    u11_report = reports.get("footer_banner_read_only_wiring_hook", {})
    u8_report = reports.get("generic_runtime_snapshot_hook", {})
    adapter_preflight_map = _mapping(u12_report.get("generic_engine_runner_adapter_map"))
    read_only_wiring_payload = _mapping(u11_report.get("generic_runtime_snapshot_footer_banner_read_only_wiring_payload"))
    runtime_snapshot = _mapping(u8_report.get("generic_runtime_snapshot"))

    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    status_consistent = flat_state_confirmed
    operator_env_absent = not active_env
    source_markers_present = not missing_source_files and not missing_source_markers
    upstream_reports_ready = not missing_reports and not_ready_reports == []

    route_candidate_available = _as_bool(
        u12_report.get(
            "route_candidate_available",
            _safe_map_get(runtime_snapshot, "generic_cycle_state", "route_candidate_available", default=False),
        )
    )
    paper_order_intent_ready = _as_bool(
        u12_report.get(
            "paper_order_intent_ready",
            _safe_map_get(runtime_snapshot, "generic_cycle_state", "paper_order_intent_ready", default=False),
        )
    )
    lifecycle_state = str(
        u12_report.get(
            "lifecycle_state",
            _safe_map_get(runtime_snapshot, "generic_cycle_state", "lifecycle_state", default="FLAT_LOCKED"),
        )
    )
    fourth_trade_locked = _as_bool(
        u12_report.get(
            "fourth_trade_locked",
            _safe_map_get(runtime_snapshot, "generic_cycle_state", "fourth_trade_locked", default=True),
        )
    )
    stability_lock_active = _as_bool(
        u12_report.get(
            "stability_lock_active",
            _safe_map_get(runtime_snapshot, "generic_cycle_state", "stability_lock_active", default=True),
        )
    )
    runtime_snapshot_visible_read_only = _as_bool(
        u12_report.get("runtime_snapshot_visible_read_only", u11_report.get("runtime_snapshot_visible_read_only", True))
    )

    blockers: List[str] = []
    if missing_reports:
        blockers.append("missing_upstream_reports")
    if not_ready_reports:
        blockers.append("upstream_reports_not_ready")
    if missing_source_files:
        blockers.append("missing_source_files")
    if missing_source_markers:
        blockers.append("missing_source_markers")
    if not flat_state_confirmed:
        blockers.append("paper_state_status_not_flat")
    if active_env:
        blockers.append("active_lsr_v2_operator_env_present")
    if route_candidate_available:
        blockers.append("route_candidate_present_unexpected_for_read_only_adapter_hook")
    if paper_order_intent_ready:
        blockers.append("paper_order_intent_present_unexpected_for_read_only_adapter_hook")
    if not runtime_snapshot_visible_read_only:
        blockers.append("runtime_snapshot_not_visible_read_only")

    ready = not blockers
    adapter_payload = _build_read_only_adapter_payload(
        adapter_preflight_map=adapter_preflight_map,
        read_only_wiring_payload=read_only_wiring_payload,
        runtime_snapshot=runtime_snapshot,
    )

    payload: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK",
            "READ_ONLY",
            "ADAPTER_HOOK_ONLY",
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
            "GENERIC_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_READY" if ready else "KEEP_DIAGNOSTIC",
        ],
        "blockers": blockers,
        "blocked_until_explicit_adapter_runtime_patch": list(BLOCKED_UNTIL_EXPLICIT_ADAPTER_RUNTIME_PATCH),
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_hook_ready": ready,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_hook_plan_ready": ready,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_hook_contract_ready": ready,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_hook_map_ready": ready,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_artifact_ready": ready,
        "engine_read_only_adapter_hook_ready": ready,
        "paper_runner_adapter_hook_ready": ready,
        "launcher_adapter_hook_ready": ready,
        "console_visibility_adapter_hook_ready": ready,
        "adapter_payload_bridge_ready": ready,
        "engine_runner_launcher_read_only_adapter_parity_ready": ready,
        "footer_banner_read_only_wiring_hook_ready": _safe_upstream_bool(reports, "footer_banner_read_only_wiring_hook", "generic_runtime_snapshot_footer_banner_read_only_wiring_hook_ready", True),
        "engine_runner_adapter_preflight_ready": _safe_upstream_bool(reports, "engine_runner_adapter_preflight", "generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_ready", True),
        "runtime_snapshot_visible_read_only": runtime_snapshot_visible_read_only,
        "generic_runtime_snapshot_artifact_ready": _safe_upstream_bool(reports, "generic_runtime_snapshot_hook", "generic_runtime_snapshot_artifact_ready", True),
        "generic_cycle_engine_hook_ready": _safe_upstream_bool(reports, "generic_cycle_engine_hook_preflight", "generic_cycle_engine_hook_preflight_ready", True),
        "generic_runner_launcher_hook_ready": _safe_upstream_bool(reports, "generic_runner_launcher_hook_preflight", "generic_runner_launcher_hook_preflight_ready", True),
        "generic_paper_cycle_integration_ready": _safe_upstream_bool(reports, "generic_cycle_integration_preflight", "generic_cycle_integration_preflight_ready", True),
        "generic_controller_ready": _safe_upstream_bool(reports, "generic_cycle_controller", "generic_cycle_controller_draft_ready", True),
        "generic_order_lifecycle_ready": _safe_upstream_bool(reports, "generic_order_lifecycle", "generic_order_lifecycle_draft_ready", True),
        "generic_rearm_policy_ready": _safe_upstream_bool(reports, "generic_rearm_policy", "generic_supervised_rearm_policy_draft_ready", True),
        "launcher_visibility_ready": _safe_upstream_bool(reports, "engine_runner_adapter_preflight", "launcher_visibility_ready", True),
        "runner_visibility_ready": _safe_upstream_bool(reports, "engine_runner_adapter_preflight", "runner_visibility_ready", True),
        "visibility_parity_ok": _safe_upstream_bool(reports, "engine_runner_adapter_preflight", "visibility_parity_ok", True),
        "generic_engine_runner_read_only_adapter_required_markers_present": source_markers_present,
        "generic_engine_runner_read_only_adapter_source_files_present": not missing_source_files,
        "missing_engine_runner_read_only_adapter_source_files": missing_source_files,
        "missing_engine_runner_read_only_adapter_source_markers": missing_source_markers,
        "upstream_reports_present": [filename for _, filename, _ in REQUIRED_UPSTREAM_REPORTS if filename not in missing_reports],
        "missing_upstream_reports": missing_reports,
        "not_ready_upstream_reports": not_ready_reports,
        "upstream_reports_ready": upstream_reports_ready,
        "generic_engine_runner_read_only_adapter_payload": adapter_payload,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_allowed": False,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_execution_allowed": False,
        "generic_runtime_snapshot_footer_banner_engine_runner_adapter_execution_allowed": False,
        "engine_read_only_adapter_execution_allowed": False,
        "paper_runner_adapter_execution_allowed": False,
        "launcher_adapter_execution_allowed": False,
        "console_visibility_adapter_execution_allowed": False,
        "generic_runtime_snapshot_footer_banner_read_only_wiring_execution_allowed": False,
        "generic_runtime_snapshot_visibility_execution_allowed": False,
        "generic_runtime_snapshot_hook_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_open_position_monitor_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "broker_submit_called_by_engine_runner_read_only_adapter_hook": False,
        "broker_close_called_by_engine_runner_read_only_adapter_hook": False,
        "orders_submitted_by_engine_runner_read_only_adapter_hook": 0,
        "positions_opened_by_engine_runner_read_only_adapter_hook": 0,
        "positions_closed_by_engine_runner_read_only_adapter_hook": 0,
        "paper_state_modified_by_engine_runner_read_only_adapter_hook": False,
        "paper_status_modified_by_engine_runner_read_only_adapter_hook": False,
        "paper_state_status_consistency": status_consistent,
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "lifecycle_state": lifecycle_state,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "route_candidate_available": route_candidate_available,
        "paper_order_intent_ready": paper_order_intent_ready,
        "no_route_candidate": not route_candidate_available,
        "no_order_intent_currently_available": not paper_order_intent_ready,
        "operator_env_absent": operator_env_absent,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "required_readiness": {
            "engine_runner_adapter_preflight_ready": not ("lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_preflight_report.json" in missing_reports),
            "footer_banner_read_only_wiring_hook_ready": not ("lsr_v2_generic_runtime_snapshot_footer_banner_wiring_hook_report.json" in missing_reports),
            "runtime_snapshot_hook_ready": not ("lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json" in missing_reports),
            "flat_state_confirmed": flat_state_confirmed,
            "no_route_candidate": not route_candidate_available,
            "no_order_intent_currently_available": not paper_order_intent_ready,
            "no_submit_or_close_occurred": True,
            "operator_env_absent": operator_env_absent,
            "ordinal_expansion_blocked": True,
            "source_markers_present": source_markers_present,
            "visibility_parity_ok": _safe_upstream_bool(reports, "engine_runner_adapter_preflight", "visibility_parity_ok", True),
            "live_disabled": True,
            "testnet_disabled": True,
            "exchange_broker_disabled": True,
            "network_scheduler_disabled": True,
            "upstream_reports_ready": upstream_reports_ready,
        },
        "next_step": "prepare_generic_engine_runner_adapter_visibility_parity_audit_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-14 — Generic LSR-v2 runtime snapshot engine-runner adapter visibility parity audit",
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
    }

    _write_json(data_path / settings.report_name, payload)
    _append_jsonl(data_path / settings.jsonl_name, payload)
    return payload


__all__ = [
    "READY_DECISION",
    "KEEP_DIAGNOSTIC_DECISION",
    "Settings",
    "run_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook",
]
