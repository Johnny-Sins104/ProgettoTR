"""Generic LSR-v2 runtime snapshot engine-runner adapter visibility parity audit.

29.4.4u-14 is intentionally audit-only, read-only, and fail-closed. It audits
parity between the generic runtime snapshot read-only adapter payloads exposed to
Paper Engine, paper runner, launcher/banner, console visibility, and safety
surfaces. It never enables candidate detection, routing, handoff, submit, close,
state mutation, scheduler activity, Telegram network sends, live, testnet, or
exchange broker access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-14"
EVENT_TYPE = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT"
READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT_NOT_READY"

U13_READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_READY"
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
    ("engine_runner_read_only_adapter_hook", "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json", U13_READY_DECISION),
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
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.py",
        ("GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK", "generic_engine_runner_read_only_adapter_payload"),
    ),
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

PARITY_AUDIT_STAGES: Tuple[str, ...] = (
    "load_engine_runner_read_only_adapter_hook",
    "load_engine_runner_adapter_preflight",
    "load_footer_banner_read_only_wiring_hook",
    "load_runtime_snapshot_artifact",
    "verify_source_markers",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_operator_env",
    "audit_engine_adapter_payload",
    "audit_paper_runner_adapter_payload",
    "audit_launcher_adapter_payload",
    "audit_console_visibility_adapter_payload",
    "audit_adapter_safety_payload",
    "audit_engine_runner_launcher_console_parity",
    "publish_visibility_parity_audit_artifact",
)

BLOCKED_UNTIL_EXPLICIT_PARITY_AUDIT_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "visibility_parity_runtime_activation",
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
    report_name: str = "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_report.json"
    jsonl_name: str = "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit.jsonl"
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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def _safe_upstream_bool(reports: Mapping[str, Mapping[str, Any]], key: str, field: str, default: bool = False) -> bool:
    return _as_bool(reports.get(key, {}).get(field, default))


def _payload_marker(payload: Mapping[str, Any]) -> str:
    return str(payload.get("generic_lsr_v2_runtime_snapshot", ""))


def _audit_payload_parity(adapter_payload: Mapping[str, Any]) -> Dict[str, Any]:
    engine_payload = _mapping(adapter_payload.get("engine_read_only_adapter_payload"))
    runner_payload = _mapping(adapter_payload.get("paper_runner_adapter_payload"))
    launcher_payload = _mapping(adapter_payload.get("launcher_adapter_payload"))
    console_payload = _mapping(adapter_payload.get("console_visibility_adapter_payload"))
    safety_payload = _mapping(adapter_payload.get("adapter_safety_payload"))
    contracts = _mapping(adapter_payload.get("contracts"))

    engine_marker = _payload_marker(engine_payload)
    runner_marker = _payload_marker(runner_payload)
    launcher_marker = _payload_marker(launcher_payload)
    marker_values = [engine_marker, runner_marker, launcher_marker]
    expected_marker = "READY_READ_ONLY"

    runtime_visible = _as_bool(adapter_payload.get("runtime_snapshot_visible_read_only"))
    console_runtime_visible = _as_bool(console_payload.get("runtime_snapshot_visible"))
    lifecycle_state = str(runner_payload.get("lifecycle_state", launcher_payload.get("lifecycle_state", "")))
    launcher_lifecycle_state = str(launcher_payload.get("lifecycle_state", lifecycle_state))
    route_candidate_available = _as_bool(runner_payload.get("route_candidate_available", False))
    paper_order_intent_ready = _as_bool(runner_payload.get("paper_order_intent_ready", False))
    open_positions_after = _as_int(runner_payload.get("open_positions_after"), 0)
    pending_orders_after = _as_int(runner_payload.get("pending_orders_after"), 0)

    engine_contract = _mapping(contracts.get("engine_read_only_adapter"))
    runner_contract = _mapping(contracts.get("paper_runner_adapter"))
    launcher_contract = _mapping(contracts.get("launcher_adapter"))
    console_contract = _mapping(contracts.get("console_visibility_adapter"))
    contract_execution_flags = [
        _as_bool(engine_contract.get("execution_allowed")),
        _as_bool(runner_contract.get("execution_allowed")),
        _as_bool(launcher_contract.get("execution_allowed")),
        _as_bool(console_contract.get("execution_allowed")),
    ]
    contract_mutation_flags = [
        _as_bool(engine_contract.get("paper_engine_mutation_allowed")),
        _as_bool(runner_contract.get("runner_mutation_allowed")),
        _as_bool(launcher_contract.get("launcher_mutation_allowed")),
        _as_bool(console_contract.get("mutation_allowed")),
    ]

    safety_orders = _as_int(safety_payload.get("orders_submitted"), 0)
    safety_positions_opened = _as_int(safety_payload.get("positions_opened"), 0)
    safety_positions_closed = _as_int(safety_payload.get("positions_closed"), 0)
    safety_disabled = (
        not _as_bool(safety_payload.get("live_enabled"))
        and not _as_bool(safety_payload.get("testnet_enabled"))
        and not _as_bool(safety_payload.get("exchange_broker_enabled"))
        and not _as_bool(safety_payload.get("telegram_network_called"))
        and not _as_bool(safety_payload.get("telegram_send_allowed"))
        and safety_orders == 0
        and safety_positions_opened == 0
        and safety_positions_closed == 0
        and not _as_bool(safety_payload.get("paper_state_mutation_allowed"))
        and not _as_bool(safety_payload.get("paper_status_mutation_allowed"))
    )

    engine_ok = (
        engine_marker == expected_marker
        and runtime_visible
        and not _as_bool(engine_payload.get("execution_enabled"))
        and not _as_bool(engine_payload.get("paper_engine_mutation_allowed"))
    )
    runner_ok = (
        runner_marker == expected_marker
        and lifecycle_state == "FLAT_LOCKED"
        and not route_candidate_available
        and not paper_order_intent_ready
        and open_positions_after == 0
        and pending_orders_after == 0
        and not _as_bool(runner_payload.get("generic_submit_execution_allowed"))
        and not _as_bool(runner_payload.get("generic_close_execution_allowed"))
    )
    launcher_ok = (
        launcher_marker == expected_marker
        and launcher_lifecycle_state == "FLAT_LOCKED"
        and not _as_bool(launcher_payload.get("live_enabled"))
        and not _as_bool(launcher_payload.get("testnet_enabled"))
        and not _as_bool(launcher_payload.get("exchange_broker_enabled"))
        and not _as_bool(launcher_payload.get("telegram_send_allowed"))
        and _as_bool(launcher_payload.get("visibility_parity_ok", True))
    )
    console_ok = (
        console_runtime_visible
        and _as_bool(console_payload.get("paper_only", True))
        and not _as_bool(console_payload.get("execution_enabled"))
    )
    contracts_ok = not any(contract_execution_flags) and not any(contract_mutation_flags)
    markers_ok = all(marker == expected_marker for marker in marker_values)
    lifecycle_ok = lifecycle_state == launcher_lifecycle_state == "FLAT_LOCKED"
    parity_ok = engine_ok and runner_ok and launcher_ok and console_ok and safety_disabled and contracts_ok and markers_ok and lifecycle_ok

    mismatches: List[str] = []
    if not engine_ok:
        mismatches.append("engine_adapter_payload_mismatch")
    if not runner_ok:
        mismatches.append("paper_runner_adapter_payload_mismatch")
    if not launcher_ok:
        mismatches.append("launcher_adapter_payload_mismatch")
    if not console_ok:
        mismatches.append("console_visibility_adapter_payload_mismatch")
    if not safety_disabled:
        mismatches.append("adapter_safety_payload_mismatch")
    if not contracts_ok:
        mismatches.append("adapter_contract_execution_or_mutation_enabled")
    if not markers_ok:
        mismatches.append("runtime_snapshot_marker_mismatch")
    if not lifecycle_ok:
        mismatches.append("lifecycle_state_mismatch")

    return {
        "engine_adapter_visibility_parity_ok": engine_ok,
        "paper_runner_adapter_visibility_parity_ok": runner_ok,
        "launcher_adapter_visibility_parity_ok": launcher_ok,
        "console_visibility_adapter_parity_ok": console_ok,
        "adapter_safety_payload_parity_ok": safety_disabled,
        "adapter_contract_parity_ok": contracts_ok,
        "runtime_snapshot_marker_parity_ok": markers_ok,
        "lifecycle_state_parity_ok": lifecycle_ok,
        "engine_runner_launcher_console_parity_ok": parity_ok,
        "adapter_parity_mismatches": mismatches,
        "adapter_marker_values": {
            "engine": engine_marker,
            "paper_runner": runner_marker,
            "launcher": launcher_marker,
        },
        "runner_footer_payload": dict(runner_payload),
        "launcher_banner_payload": dict(launcher_payload),
        "console_visibility_payload": dict(console_payload),
        "adapter_safety_payload": dict(safety_payload),
        "open_positions_after_from_adapter": open_positions_after,
        "pending_orders_after_from_adapter": pending_orders_after,
        "route_candidate_available_from_adapter": route_candidate_available,
        "paper_order_intent_ready_from_adapter": paper_order_intent_ready,
    }


def run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit(
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

    u13_report = reports.get("engine_runner_read_only_adapter_hook", {})
    adapter_payload = _mapping(u13_report.get("generic_engine_runner_read_only_adapter_payload"))
    parity = _audit_payload_parity(adapter_payload)

    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    status_consistent = flat_state_confirmed
    operator_env_absent = not active_env
    source_markers_present = not missing_source_files and not missing_source_markers
    upstream_reports_ready = not missing_reports and not_ready_reports == []
    runtime_snapshot_visible_read_only = _as_bool(u13_report.get("runtime_snapshot_visible_read_only", adapter_payload.get("runtime_snapshot_visible_read_only", False)))
    route_candidate_available = _as_bool(u13_report.get("route_candidate_available", parity.get("route_candidate_available_from_adapter", False)))
    paper_order_intent_ready = _as_bool(u13_report.get("paper_order_intent_ready", parity.get("paper_order_intent_ready_from_adapter", False)))
    lifecycle_state = str(u13_report.get("lifecycle_state", "FLAT_LOCKED"))
    fourth_trade_locked = _as_bool(u13_report.get("fourth_trade_locked", True))
    stability_lock_active = _as_bool(u13_report.get("stability_lock_active", True))

    blockers: List[str] = []
    if missing_reports:
        blockers.append("missing_upstream_reports")
    if not_ready_reports:
        blockers.append("upstream_reports_not_ready")
    if missing_source_files:
        blockers.append("missing_source_files")
    if missing_source_markers:
        blockers.append("missing_source_markers")
    if not adapter_payload:
        blockers.append("missing_read_only_adapter_payload")
    if parity.get("adapter_parity_mismatches"):
        blockers.append("adapter_visibility_parity_mismatch")
    if not flat_state_confirmed:
        blockers.append("paper_state_status_not_flat")
    if active_env:
        blockers.append("active_lsr_v2_operator_env_present")
    if route_candidate_available:
        blockers.append("route_candidate_present_unexpected_for_visibility_parity_audit")
    if paper_order_intent_ready:
        blockers.append("paper_order_intent_present_unexpected_for_visibility_parity_audit")
    if not runtime_snapshot_visible_read_only:
        blockers.append("runtime_snapshot_not_visible_read_only")

    ready = not blockers

    payload: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT",
            "AUDIT_ONLY",
            "READ_ONLY",
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
            "GENERIC_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT_READY" if ready else "KEEP_DIAGNOSTIC",
        ],
        "blockers": blockers,
        "blocked_until_explicit_parity_audit_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_PARITY_AUDIT_IMPLEMENTATION_PATCH),
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_plan_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_contract_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_map_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_artifact_ready": ready,
        "engine_runner_read_only_adapter_hook_ready": _safe_upstream_bool(reports, "engine_runner_read_only_adapter_hook", "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_hook_ready", True),
        "adapter_payload_bridge_ready": _safe_upstream_bool(reports, "engine_runner_read_only_adapter_hook", "adapter_payload_bridge_ready", True),
        "engine_read_only_adapter_hook_ready": _safe_upstream_bool(reports, "engine_runner_read_only_adapter_hook", "engine_read_only_adapter_hook_ready", True),
        "paper_runner_adapter_hook_ready": _safe_upstream_bool(reports, "engine_runner_read_only_adapter_hook", "paper_runner_adapter_hook_ready", True),
        "launcher_adapter_hook_ready": _safe_upstream_bool(reports, "engine_runner_read_only_adapter_hook", "launcher_adapter_hook_ready", True),
        "console_visibility_adapter_hook_ready": _safe_upstream_bool(reports, "engine_runner_read_only_adapter_hook", "console_visibility_adapter_hook_ready", True),
        "runtime_snapshot_visible_read_only": runtime_snapshot_visible_read_only,
        **parity,
        "generic_engine_runner_adapter_visibility_parity_audit_allowed": False,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed": False,
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_execution_allowed": False,
        "engine_read_only_adapter_execution_allowed": False,
        "paper_runner_adapter_execution_allowed": False,
        "launcher_adapter_execution_allowed": False,
        "console_visibility_adapter_execution_allowed": False,
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
        "broker_submit_called_by_engine_runner_adapter_visibility_parity_audit": False,
        "broker_close_called_by_engine_runner_adapter_visibility_parity_audit": False,
        "orders_submitted_by_engine_runner_adapter_visibility_parity_audit": 0,
        "positions_opened_by_engine_runner_adapter_visibility_parity_audit": 0,
        "positions_closed_by_engine_runner_adapter_visibility_parity_audit": 0,
        "paper_state_modified_by_engine_runner_adapter_visibility_parity_audit": False,
        "paper_status_modified_by_engine_runner_adapter_visibility_parity_audit": False,
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
        "generic_engine_runner_adapter_visibility_parity_required_markers_present": source_markers_present,
        "generic_engine_runner_adapter_visibility_parity_source_files_present": not missing_source_files,
        "missing_engine_runner_adapter_visibility_parity_source_files": missing_source_files,
        "missing_engine_runner_adapter_visibility_parity_source_markers": missing_source_markers,
        "upstream_reports_present": [filename for _, filename, _ in REQUIRED_UPSTREAM_REPORTS if filename not in missing_reports],
        "missing_upstream_reports": missing_reports,
        "not_ready_upstream_reports": not_ready_reports,
        "upstream_reports_ready": upstream_reports_ready,
        "required_readiness": {
            "engine_runner_read_only_adapter_hook_ready": not ("lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json" in missing_reports),
            "adapter_payload_bridge_ready": _safe_upstream_bool(reports, "engine_runner_read_only_adapter_hook", "adapter_payload_bridge_ready", True),
            "runtime_snapshot_visible_read_only": runtime_snapshot_visible_read_only,
            "adapter_payload_parity_ok": bool(parity.get("engine_runner_launcher_console_parity_ok")),
            "flat_state_confirmed": flat_state_confirmed,
            "no_route_candidate": not route_candidate_available,
            "no_order_intent_currently_available": not paper_order_intent_ready,
            "no_submit_or_close_occurred": True,
            "operator_env_absent": operator_env_absent,
            "ordinal_expansion_blocked": True,
            "source_markers_present": source_markers_present,
            "live_disabled": True,
            "testnet_disabled": True,
            "exchange_broker_disabled": True,
            "network_scheduler_disabled": True,
            "upstream_reports_ready": upstream_reports_ready,
        },
        "parity_audit_stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in PARITY_AUDIT_STAGES
        ],
        "next_step": "prepare_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-15 — Generic LSR-v2 runtime snapshot engine-runner adapter visibility parity lock",
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
    "run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit",
]
