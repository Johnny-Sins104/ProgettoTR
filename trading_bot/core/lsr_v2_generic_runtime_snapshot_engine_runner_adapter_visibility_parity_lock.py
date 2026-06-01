"""Generic LSR-v2 runtime snapshot engine-runner adapter visibility parity lock.

29.4.4u-15 is intentionally lock-only, read-only, and fail-closed. It freezes
(the diagnostic/audit sense of "lock", not runtime activation) the adapter
visibility parity proven by 29.4.4u-14 before any later runtime integration step.
It never enables candidate detection, routing, handoff, submit, close, broker
calls, state mutation, scheduler activity, Telegram network sends, live, testnet,
or exchange broker access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-15"
EVENT_TYPE = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK"
READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_NOT_READY"

U14_READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT_READY"
U13_READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK_READY"

PARITY_FIELDS: Tuple[str, ...] = (
    "engine_adapter_visibility_parity_ok",
    "paper_runner_adapter_visibility_parity_ok",
    "launcher_adapter_visibility_parity_ok",
    "console_visibility_adapter_parity_ok",
    "adapter_safety_payload_parity_ok",
    "adapter_contract_parity_ok",
    "runtime_snapshot_marker_parity_ok",
    "lifecycle_state_parity_ok",
    "engine_runner_launcher_console_parity_ok",
)

LOCK_STAGES: Tuple[str, ...] = (
    "load_engine_runner_adapter_visibility_parity_audit",
    "load_engine_runner_read_only_adapter_hook",
    "verify_adapter_parity_no_mismatches",
    "verify_flat_locked_state",
    "verify_no_route_candidate",
    "verify_no_paper_order_intent",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "freeze_adapter_marker_values",
    "freeze_adapter_safety_payload",
    "publish_visibility_parity_lock_artifact",
)

BLOCKED_UNTIL_EXPLICIT_PARITY_LOCK_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "visibility_parity_lock_runtime_activation",
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

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit.py",
        ("GENERIC_LSR_V2_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_AUDIT", "adapter_parity_mismatches"),
    ),
    (
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook.py",
        ("GENERIC_LSR_V2_RUNTIME_SNAPSHOT_FOOTER_BANNER_ENGINE_RUNNER_READ_ONLY_ADAPTER_HOOK", "generic_engine_runner_read_only_adapter_payload"),
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

@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_report.json"
    jsonl_name: str = "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock.jsonl"
    fail_closed: bool = True

    @property
    def data_path(self) -> Path:
        return self.project_root / self.data_dir


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def _bool(data: Mapping[str, Any], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    return value is True


def _int(data: Mapping[str, Any], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _active_lsr_env() -> Dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.startswith("LSR_V2") and v not in (None, "")}


def _source_marker_audit(project_root: Path) -> Tuple[bool, List[str], Dict[str, List[str]]]:
    missing_files: List[str] = []
    missing_markers: Dict[str, List[str]] = {}
    for rel, markers in REQUIRED_SOURCE_MARKERS:
        path = project_root / rel
        if not path.exists():
            missing_files.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            missing_files.append(rel)
            continue
        missing = [marker for marker in markers if marker not in text]
        if missing:
            missing_markers[rel] = missing
    return not missing_files and not missing_markers, missing_files, missing_markers


def _parity_summary(audit: Mapping[str, Any]) -> Dict[str, bool]:
    return {field: _bool(audit, field, False) for field in PARITY_FIELDS}


def _all_false(audit: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return all(audit.get(key) is False for key in keys)


def run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    audit_report_name = "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_report.json"
    adapter_hook_report_name = "lsr_v2_generic_runtime_snapshot_footer_banner_engine_runner_adapter_hook_report.json"

    audit = _read_json(data_path / audit_report_name)
    adapter_hook = _read_json(data_path / adapter_hook_report_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []

    if not audit:
        missing_upstream_reports.append(audit_report_name)
    elif audit.get("decision") != U14_READY_DECISION or audit.get("status") != "PASS":
        not_ready_upstream_reports.append(audit_report_name)

    if not adapter_hook:
        missing_upstream_reports.append(adapter_hook_report_name)
    elif adapter_hook.get("decision") != U13_READY_DECISION or adapter_hook.get("status") != "PASS":
        not_ready_upstream_reports.append(adapter_hook_report_name)

    parity = _parity_summary(audit)
    mismatches = audit.get("adapter_parity_mismatches", [])
    if not isinstance(mismatches, list):
        mismatches = ["adapter_parity_mismatches_not_list"]

    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    active_env = _active_lsr_env()

    open_positions_after = _int(audit, "open_positions_after", 0)
    pending_orders_after = _int(audit, "pending_orders_after", 0)
    route_candidate_available = _bool(audit, "route_candidate_available", False)
    paper_order_intent_ready = _bool(audit, "paper_order_intent_ready", False)
    lifecycle_state = str(audit.get("lifecycle_state", "UNKNOWN"))
    adapter_marker_values = audit.get("adapter_marker_values", {}) if isinstance(audit.get("adapter_marker_values"), dict) else {}
    adapter_safety_payload = audit.get("adapter_safety_payload", {}) if isinstance(audit.get("adapter_safety_payload"), dict) else {}

    false_execution_keys = (
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed",
        "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_execution_allowed",
        "engine_read_only_adapter_execution_allowed",
        "paper_runner_adapter_execution_allowed",
        "launcher_adapter_execution_allowed",
        "console_visibility_adapter_execution_allowed",
        "generic_submit_execution_allowed",
        "generic_close_execution_allowed",
        "paper_engine_mutation_allowed",
        "runner_mutation_allowed",
        "launcher_mutation_allowed",
        "paper_only_execution_allowed",
        "future_integrated_operation_allowed",
    )

    readiness_checks: Dict[str, bool] = {
        "parity_audit_ready": not missing_upstream_reports and not not_ready_upstream_reports,
        "all_adapter_parity_ok": all(parity.values()),
        "no_adapter_parity_mismatches": not mismatches,
        "flat_locked_state": lifecycle_state == "FLAT_LOCKED",
        "no_route_candidate": not route_candidate_available,
        "no_paper_order_intent": not paper_order_intent_ready,
        "flat_positions": open_positions_after == 0,
        "pending_orders_clear": pending_orders_after == 0,
        "operator_env_absent": not active_env,
        "source_markers_present": source_markers_present,
        "execution_flags_fail_closed": _all_false(audit, false_execution_keys),
        "live_disabled": audit.get("live_enabled") is False,
        "testnet_disabled": audit.get("testnet_enabled") is False,
        "exchange_broker_disabled": audit.get("exchange_broker_enabled") is False,
        "no_submit_or_close_occurred": _int(audit, "orders_submitted_by_engine_runner_adapter_visibility_parity_audit", 0) == 0
        and _int(audit, "positions_opened_by_engine_runner_adapter_visibility_parity_audit", 0) == 0
        and _int(audit, "positions_closed_by_engine_runner_adapter_visibility_parity_audit", 0) == 0,
        "no_state_mutation": audit.get("paper_state_modified_by_engine_runner_adapter_visibility_parity_audit") is False
        and audit.get("paper_status_modified_by_engine_runner_adapter_visibility_parity_audit") is False,
    }

    blockers = [key for key, ok in readiness_checks.items() if not ok]
    ready = not blockers

    lock_payload = {
        "lock_mode": "audit_only_read_only_fail_closed",
        "locked_from_prompt": "29.4.4u-14",
        "locked_from_decision": audit.get("decision", ""),
        "adapter_marker_values": adapter_marker_values,
        "adapter_safety_payload": adapter_safety_payload,
        "adapter_parity_fields": parity,
        "adapter_parity_mismatches": mismatches,
        "lifecycle_state": lifecycle_state,
        "route_candidate_available": route_candidate_available,
        "paper_order_intent_ready": paper_order_intent_ready,
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "runtime_snapshot_visible_read_only": _bool(audit, "runtime_snapshot_visible_read_only", False),
        "visibility_parity_ok": all(parity.values()) and not mismatches,
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "paper_only": True,
        "ordinal_module_generation_allowed": False,
    }

    payload: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK",
            "LOCK_ONLY",
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
            "GENERIC_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_READY" if ready else "GENERIC_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_NOT_READY",
        ],
        "blockers": blockers,
        "blocked_until_explicit_parity_lock_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_PARITY_LOCK_IMPLEMENTATION_PATCH),
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_plan_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_contract_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_map_ready": ready,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_artifact_ready": ready,
        "adapter_visibility_parity_locked": ready,
        "engine_adapter_visibility_parity_locked": ready and parity.get("engine_adapter_visibility_parity_ok", False),
        "paper_runner_adapter_visibility_parity_locked": ready and parity.get("paper_runner_adapter_visibility_parity_ok", False),
        "launcher_adapter_visibility_parity_locked": ready and parity.get("launcher_adapter_visibility_parity_ok", False),
        "console_visibility_adapter_parity_locked": ready and parity.get("console_visibility_adapter_parity_ok", False),
        "adapter_safety_payload_locked": ready and parity.get("adapter_safety_payload_parity_ok", False),
        "adapter_contract_parity_locked": ready and parity.get("adapter_contract_parity_ok", False),
        "runtime_snapshot_marker_parity_locked": ready and parity.get("runtime_snapshot_marker_parity_ok", False),
        "lifecycle_state_parity_locked": ready and parity.get("lifecycle_state_parity_ok", False),
        "engine_runner_launcher_console_parity_locked": ready and parity.get("engine_runner_launcher_console_parity_ok", False),
        "adapter_parity_mismatches": mismatches,
        "adapter_marker_values": adapter_marker_values,
        "adapter_safety_payload": adapter_safety_payload,
        "parity_lock_payload": lock_payload,
        **parity,
        "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_execution_allowed": False,
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
        "broker_submit_called_by_engine_runner_adapter_visibility_parity_lock": False,
        "broker_close_called_by_engine_runner_adapter_visibility_parity_lock": False,
        "orders_submitted_by_engine_runner_adapter_visibility_parity_lock": 0,
        "positions_opened_by_engine_runner_adapter_visibility_parity_lock": 0,
        "positions_closed_by_engine_runner_adapter_visibility_parity_lock": 0,
        "paper_state_modified_by_engine_runner_adapter_visibility_parity_lock": False,
        "paper_status_modified_by_engine_runner_adapter_visibility_parity_lock": False,
        "paper_state_status_consistency": _bool(audit, "paper_state_status_consistency", True),
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "lifecycle_state": lifecycle_state,
        "fourth_trade_locked": _bool(audit, "fourth_trade_locked", True),
        "stability_lock_active": _bool(audit, "stability_lock_active", True),
        "route_candidate_available": route_candidate_available,
        "paper_order_intent_ready": paper_order_intent_ready,
        "no_route_candidate": not route_candidate_available,
        "no_order_intent_currently_available": not paper_order_intent_ready,
        "operator_env_absent": not active_env,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "generic_engine_runner_adapter_visibility_parity_lock_required_markers_present": source_markers_present,
        "generic_engine_runner_adapter_visibility_parity_lock_source_files_present": not missing_source_files,
        "missing_engine_runner_adapter_visibility_parity_lock_source_files": missing_source_files,
        "missing_engine_runner_adapter_visibility_parity_lock_source_markers": missing_source_markers,
        "upstream_reports_present": [name for name in (audit_report_name, adapter_hook_report_name) if name not in missing_upstream_reports],
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "upstream_reports_ready": not missing_upstream_reports and not not_ready_upstream_reports,
        "required_readiness": readiness_checks,
        "parity_lock_stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in LOCK_STAGES
        ],
        "next_step": "prepare_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_followup_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-16 — Generic LSR-v2 paper-only candidate detection readiness preflight",
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
    "run_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock",
]
