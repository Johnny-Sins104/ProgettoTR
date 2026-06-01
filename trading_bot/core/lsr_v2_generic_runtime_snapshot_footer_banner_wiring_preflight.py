"""Generic LSR-v2 runtime snapshot footer/banner wiring preflight.

29.4.4u-10 is intentionally read-only and fail-closed. It verifies that the
validated generic runtime snapshot visibility plan can be wired into runner
footer and launcher/banner surfaces in a future patch. It never enables
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

PROMPT = "29.4.4u-10"
EVENT_TYPE = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT_NOT_READY"

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
        "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_visibility_preflight.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_VISIBILITY_PREFLIGHT", "generic_runtime_visibility_map"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_runtime_snapshot_hook.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_RUNTIME_SNAPSHOT_HOOK", "generic_runtime_snapshot"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_paper_cycle_runner_launcher_hook_preflight.py",
        ("GENERIC_LSR_V2_PAPER_CYCLE_RUNNER_LAUNCHER_HOOK_PREFLIGHT", "generic_paper_cycle_runner_launcher_hook_map"),
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

FOOTER_BANNER_WIRING_STAGES: Tuple[str, ...] = (
    "load_runtime_snapshot_visibility_preflight",
    "load_runtime_snapshot_artifact",
    "load_runner_launcher_hook_preflight",
    "load_existing_runner_footer_visibility",
    "load_existing_launcher_banner_visibility",
    "verify_footer_banner_source_markers",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_operator_env",
    "map_runner_footer_fields",
    "map_launcher_banner_fields",
    "map_console_visibility_fields",
    "map_footer_banner_safety_fields",
    "map_footer_banner_parity",
    "prepare_future_footer_banner_wiring",
)

BLOCKED_UNTIL_EXPLICIT_WIRING_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "runtime_snapshot_footer_banner_wiring_activation",
    "paper_runner_runtime_snapshot_footer_wiring",
    "launcher_runtime_snapshot_banner_wiring",
    "console_runtime_snapshot_visibility_wiring",
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
    report_name: str = "lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_runtime_snapshot_footer_banner_wiring_preflight.jsonl"
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


def _footer_banner_wiring_map() -> Dict[str, Any]:
    return {
        "mode": "footer_banner_wiring_preflight_only",
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "runner_footer_wiring_enabled": False,
        "launcher_banner_wiring_enabled": False,
        "console_visibility_wiring_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "runtime_snapshot_sections": (
            "generic_cycle_state",
            "generic_rearm_policy_state",
            "generic_order_lifecycle_state",
            "runner_launcher_visibility_state",
            "engine_hook_state",
            "safety_state",
        ),
        "runner_footer_fields": {
            "lifecycle_state": "FLAT_LOCKED",
            "fourth_trade_locked": True,
            "route_candidate_available": False,
            "paper_order_intent_ready": False,
            "open_positions_after": 0,
            "pending_orders_after": 0,
            "generic_rearm_allowed": False,
            "generic_submit_execution_allowed": False,
            "generic_close_execution_allowed": False,
            "stability_lock_active": True,
        },
        "launcher_banner_fields": {
            "lifecycle_state": "FLAT_LOCKED",
            "runner_visibility_ready": True,
            "launcher_visibility_ready": True,
            "visibility_parity_ok": True,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "telegram_send_allowed": False,
        },
        "console_visibility_fields": {
            "runtime_snapshot_visible": False,
            "runner_footer_wiring_preflight_ready": True,
            "launcher_banner_wiring_preflight_ready": True,
            "paper_only": True,
            "execution_enabled": False,
        },
        "safety_fields": {
            "orders_submitted": 0,
            "positions_opened": 0,
            "positions_closed": 0,
            "paper_state_mutation_allowed": False,
            "paper_status_mutation_allowed": False,
            "telegram_network_called": False,
            "telegram_send_allowed": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in FOOTER_BANNER_WIRING_STAGES
        ],
    }


def run_generic_runtime_snapshot_footer_banner_wiring_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    project_root = Path(settings.project_root)
    data_path = settings.data_path
    reports, missing_reports, not_ready_reports = _load_upstream_reports(data_path)
    missing_sources, missing_markers = _check_source_markers(project_root)
    state = _read_json(data_path / "paper_state.json", {})
    status = _read_json(data_path / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(state, status)
    active_env = _active_lsr_v2_env()

    visibility_report = reports.get("runtime_snapshot_visibility_preflight", {})
    runtime_snapshot_report = reports.get("generic_runtime_snapshot_hook", {})
    runtime_snapshot = runtime_snapshot_report.get("generic_runtime_snapshot", {}) if isinstance(runtime_snapshot_report, Mapping) else {}

    route_candidate_available = _as_bool(visibility_report.get("route_candidate_available", False))
    paper_order_intent_ready = _as_bool(visibility_report.get("paper_order_intent_ready", False))
    lifecycle_state = str(visibility_report.get("lifecycle_state") or runtime_snapshot.get("generic_cycle_state", {}).get("lifecycle_state") or "FLAT_LOCKED")
    fourth_trade_locked = _as_bool(visibility_report.get("fourth_trade_locked", runtime_snapshot.get("generic_cycle_state", {}).get("fourth_trade_locked", True)))
    stability_lock_active = _as_bool(visibility_report.get("stability_lock_active", runtime_snapshot.get("generic_cycle_state", {}).get("stability_lock_active", True)))
    runner_visibility_ready = _as_bool(visibility_report.get("runner_visibility_ready", True))
    launcher_visibility_ready = _as_bool(visibility_report.get("launcher_visibility_ready", True))
    visibility_parity_ok = _as_bool(visibility_report.get("visibility_parity_ok", True))

    live_enabled = _as_bool(visibility_report.get("live_enabled", False))
    testnet_enabled = _as_bool(visibility_report.get("testnet_enabled", False))
    exchange_broker_enabled = _as_bool(visibility_report.get("exchange_broker_enabled", False))
    telegram_network_called = _as_bool(visibility_report.get("telegram_network_called", False))
    telegram_send_allowed = _as_bool(visibility_report.get("telegram_send_allowed", False))
    scheduler_started = _as_bool(visibility_report.get("scheduler_started", False))

    blockers: List[str] = []
    if missing_reports:
        blockers.append("missing_upstream_reports")
    if not_ready_reports:
        blockers.append("not_ready_upstream_reports")
    if missing_sources:
        blockers.append("missing_source_files")
    if missing_markers:
        blockers.append("missing_source_markers")
    if active_env:
        blockers.append("active_lsr_v2_operator_env_present")
    if open_positions_after != 0 or pending_orders_after != 0:
        blockers.append("paper_state_status_not_flat")
    if live_enabled or testnet_enabled or exchange_broker_enabled:
        blockers.append("live_testnet_or_exchange_enabled")
    if telegram_network_called or telegram_send_allowed or scheduler_started:
        blockers.append("network_or_scheduler_not_disabled")
    if not runner_visibility_ready or not launcher_visibility_ready or not visibility_parity_ok:
        blockers.append("visibility_not_ready")

    status_value = "PASS" if not blockers else "WARN"
    decision = READY_DECISION if status_value == "PASS" else KEEP_DIAGNOSTIC_DECISION
    ready = status_value == "PASS"
    wiring_map = _footer_banner_wiring_map()

    result: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": status_value,
        "decision": decision,
        "classification_labels": [
            "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_WIRING_PREFLIGHT",
            "READ_ONLY",
            "WIRING_PREFLIGHT_ONLY",
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
            "GENERIC_FOOTER_BANNER_WIRING_PREFLIGHT_READY" if ready else "KEEP_DIAGNOSTIC",
        ],
        "blockers": blockers,
        "blocked_until_explicit_wiring_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_WIRING_IMPLEMENTATION_PATCH),
        "generic_runtime_snapshot_footer_banner_wiring_preflight_ready": ready,
        "generic_runtime_snapshot_footer_banner_wiring_plan_ready": ready,
        "generic_runtime_snapshot_footer_banner_wiring_contract_ready": ready,
        "generic_runtime_snapshot_footer_banner_wiring_map_ready": ready,
        "runner_footer_wiring_preflight_ready": ready,
        "launcher_banner_wiring_preflight_ready": ready,
        "console_visibility_wiring_preflight_ready": ready,
        "runtime_snapshot_visibility_preflight_ready": reports.get("runtime_snapshot_visibility_preflight", {}).get("decision") == U9_READY_DECISION,
        "generic_runtime_snapshot_artifact_ready": _as_bool(visibility_report.get("generic_runtime_snapshot_artifact_ready", False)) or _as_bool(runtime_snapshot_report.get("generic_runtime_snapshot_artifact_ready", False)),
        "runtime_snapshot_footer_fields_ready": _as_bool(visibility_report.get("runtime_snapshot_footer_fields_ready", ready)),
        "runtime_snapshot_banner_fields_ready": _as_bool(visibility_report.get("runtime_snapshot_banner_fields_ready", ready)),
        "runtime_snapshot_safety_fields_ready": _as_bool(visibility_report.get("runtime_snapshot_safety_fields_ready", ready)),
        "runtime_snapshot_footer_banner_parity_ready": ready and visibility_parity_ok,
        "generic_runtime_snapshot_footer_banner_wiring_map": wiring_map,
        "generic_runtime_snapshot_footer_banner_wiring_allowed": False,
        "generic_runtime_snapshot_footer_banner_wiring_execution_allowed": False,
        "generic_runtime_snapshot_visibility_execution_allowed": False,
        "generic_runtime_snapshot_hook_execution_allowed": False,
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
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
        "lifecycle_state": lifecycle_state,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "route_candidate_available": route_candidate_available,
        "paper_order_intent_ready": paper_order_intent_ready,
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "operator_env_absent": not bool(active_env),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "runner_visibility_ready": runner_visibility_ready,
        "launcher_visibility_ready": launcher_visibility_ready,
        "visibility_parity_ok": visibility_parity_ok,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "telegram_network_called": telegram_network_called,
        "telegram_send_allowed": telegram_send_allowed,
        "scheduler_enabled": False,
        "scheduler_started": scheduler_started,
        "broker_submit_called_by_generic_footer_banner_wiring_preflight": False,
        "broker_close_called_by_generic_footer_banner_wiring_preflight": False,
        "orders_submitted_by_generic_footer_banner_wiring_preflight": 0,
        "positions_opened_by_generic_footer_banner_wiring_preflight": 0,
        "positions_closed_by_generic_footer_banner_wiring_preflight": 0,
        "paper_state_modified_by_generic_footer_banner_wiring_preflight": False,
        "paper_status_modified_by_generic_footer_banner_wiring_preflight": False,
        "paper_state_status_consistency": open_positions_after == 0 and pending_orders_after == 0,
        "missing_upstream_reports": missing_reports,
        "not_ready_upstream_reports": not_ready_reports,
        "upstream_reports_present": [filename for _, filename, _ in REQUIRED_UPSTREAM_REPORTS if filename not in missing_reports],
        "missing_footer_banner_wiring_source_files": missing_sources,
        "missing_footer_banner_wiring_source_markers": missing_markers,
        "generic_footer_banner_wiring_source_files_present": not missing_sources,
        "generic_footer_banner_wiring_required_markers_present": not missing_markers,
        "required_readiness": {
            "runtime_snapshot_visibility_preflight_ready": reports.get("runtime_snapshot_visibility_preflight", {}).get("decision") == U9_READY_DECISION,
            "runtime_snapshot_hook_ready": reports.get("generic_runtime_snapshot_hook", {}).get("decision") == U8_READY_DECISION,
            "runner_launcher_hook_ready": reports.get("generic_runner_launcher_hook_preflight", {}).get("decision") == U7_READY_DECISION,
            "launcher_visibility_ready": launcher_visibility_ready,
            "runner_visibility_ready": runner_visibility_ready,
            "visibility_parity_ok": visibility_parity_ok,
            "flat_state_confirmed": open_positions_after == 0 and pending_orders_after == 0,
            "operator_env_absent": not bool(active_env),
            "no_route_candidate": not route_candidate_available,
            "no_order_intent_currently_available": not paper_order_intent_ready,
            "no_submit_or_close_occurred": True,
            "source_markers_present": not missing_sources and not missing_markers,
            "live_disabled": not live_enabled,
            "testnet_disabled": not testnet_enabled,
            "exchange_broker_disabled": not exchange_broker_enabled,
            "network_scheduler_disabled": not telegram_network_called and not telegram_send_allowed and not scheduler_started,
            "ordinal_expansion_blocked": True,
        },
        "settings": {
            "project_root": str(project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "jsonl": str(data_path / settings.jsonl_name),
        "report": str(data_path / settings.report_name),
        "next_step": "prepare_runtime_snapshot_footer_banner_wiring_read_only_hook_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-11 — Generic LSR-v2 runtime snapshot footer/banner read-only wiring hook",
    }

    _write_json(data_path / settings.report_name, result)
    _append_jsonl(data_path / settings.jsonl_name, result)
    return result


def main() -> None:
    print(json.dumps(run_generic_runtime_snapshot_footer_banner_wiring_preflight(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
