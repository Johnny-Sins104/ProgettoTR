"""Generic LSR-v2 paper-only route-to-handoff dry-run preflight.

29.4.4u-19 is intentionally dry-run/preflight-only, read-only, and
fail-closed. It consumes the generic candidate route preflight produced by
u-18 and prepares a non-executing bridge map for a future route-to-handoff
stage. It never creates a route candidate, creates a paper order intent,
submits/closes an order, opens/closes a position, starts a scheduler, calls a
broker, sends Telegram messages, or mutates paper_state/paper_status.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-19"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT_NOT_READY"

U18_READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_ROUTE_PREFLIGHT_READY"

HANDOFF_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_candidate_route_preflight",
    "verify_route_preflight_ready",
    "verify_diagnostic_route_context",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_route_execution",
    "verify_no_paper_order_intent",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_route_preflight_to_handoff_dry_run_context",
    "map_handoff_dry_run_gate_model",
    "map_handoff_dry_run_safety_outputs",
    "publish_generic_route_to_handoff_dry_run_preflight_artifact",
)

BLOCKED_UNTIL_EXPLICIT_HANDOFF_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_route_to_handoff_runtime_activation",
    "generic_handoff_execution",
    "generic_order_intent_creation",
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
        "trading_bot/core/lsr_v2_generic_paper_only_candidate_route_preflight.py",
        (
            "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_ROUTE_PREFLIGHT",
            "candidate_route_preflight_diagnostic_count",
        ),
    ),
    (
        "trading_bot/core/paper_engine.py",
        ("PaperTradingEngine",),
    ),
    (
        "trading_bot/run_paper_trading.py",
        ("no-lsr-v2-engine-read-only-artifact-hook",),
    ),
)

FALSE_EXECUTION_KEYS: Tuple[str, ...] = (
    "generic_candidate_route_preflight_execution_allowed",
    "generic_candidate_detection_allowed",
    "generic_candidate_scan_execution_allowed",
    "generic_candidate_probe_allowed",
    "generic_route_candidate_creation_allowed",
    "generic_route_execution_allowed",
    "generic_handoff_execution_allowed",
    "generic_order_intent_creation_allowed",
    "generic_submit_execution_allowed",
    "generic_open_position_monitor_allowed",
    "generic_close_execution_allowed",
    "generic_final_audit_execution_allowed",
    "generic_postmortem_execution_allowed",
    "generic_paper_state_mutation_allowed",
    "generic_paper_status_mutation_allowed",
    "paper_engine_mutation_allowed",
    "runner_mutation_allowed",
    "launcher_mutation_allowed",
    "paper_only_execution_allowed",
    "future_integrated_operation_allowed",
)


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_generic_paper_only_route_to_handoff_dry_run_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_route_to_handoff_dry_run_preflight.jsonl"
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
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
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


def _all_false(payload: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return all(payload.get(key) is False for key in keys)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _handoff_dry_run_map(route_preflight: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostic_count = _safe_int(route_preflight.get("candidate_route_preflight_diagnostic_count"), 0)
    route_map = route_preflight.get("candidate_route_preflight_map", {})
    if not isinstance(route_map, dict):
        route_map = {}
    return {
        "mode": "route_to_handoff_dry_run_preflight_only",
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "candidate_route_preflight_diagnostic_available": route_preflight.get("candidate_route_preflight_diagnostic_available") is True,
        "candidate_route_preflight_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": route_preflight.get("candidate_detection_source_counts", {}),
        "candidate_diagnostic_examples": route_preflight.get("candidate_diagnostic_examples", []),
        "route_preflight_context": route_map.get("route_preflight_context", {}),
        "handoff_dry_run_context": {
            "diagnostic_route_preflight_available": diagnostic_count > 0,
            "route_candidate_available": False,
            "handoff_candidate_available": False,
            "paper_order_intent_ready": False,
            "would_handoff": False,
            "would_create_order": False,
            "would_submit": False,
            "blocked_reason": "handoff_execution_not_allowed_dry_run_preflight_only",
        },
        "required_future_controls_before_handoff_execution": {
            "explicit_generic_handoff_or_order_intent_patch_required": True,
            "explicit_generic_route_execution_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_order_intent_creation_deferred": True,
        },
        "diagnostic_outputs": {
            "handoff_dry_run_preflight_diagnostic_available": "boolean",
            "handoff_dry_run_preflight_diagnostic_count": "integer",
            "handoff_candidate_available": "false_until_handoff_execution_patch",
            "paper_order_intent_ready": "false_until_order_intent_creation_patch",
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in HANDOFF_PREFLIGHT_STAGES
        ],
    }


def run_generic_paper_only_route_to_handoff_dry_run_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    route_report_name = "lsr_v2_generic_paper_only_candidate_route_preflight_report.json"
    route_preflight = _read_json(data_path / route_report_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not route_preflight:
        missing_upstream_reports.append(route_report_name)
    elif route_preflight.get("status") != "PASS" or route_preflight.get("decision") != U18_READY_DECISION:
        not_ready_upstream_reports.append(route_report_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(route_preflight, FALSE_EXECUTION_KEYS)

    diagnostic_count = _safe_int(route_preflight.get("candidate_route_preflight_diagnostic_count"), 0)
    diagnostic_available = route_preflight.get("candidate_route_preflight_diagnostic_available") is True and diagnostic_count > 0
    source_counts = route_preflight.get("candidate_detection_source_counts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}

    required_readiness = {
        "candidate_route_preflight_ready": route_preflight.get("generic_candidate_route_preflight_ready") is True,
        "candidate_route_preflight_diagnostic_available": diagnostic_available,
        "flat_locked_state": route_preflight.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": route_preflight.get("open_positions_after") == 0,
        "pending_orders_clear": route_preflight.get("pending_orders_after") == 0,
        "no_existing_route_candidate": route_preflight.get("route_candidate_available") is False,
        "no_route_preflight_candidate": route_preflight.get("route_preflight_candidate_available") is False,
        "no_paper_order_intent": route_preflight.get("paper_order_intent_ready") is False,
        "operator_env_absent": len(active_env) == 0,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "source_markers_present": source_markers_present,
        "no_state_mutation": route_preflight.get("paper_state_modified_by_generic_candidate_route_preflight") is False
        and route_preflight.get("paper_status_modified_by_generic_candidate_route_preflight") is False,
        "no_submit_or_close_occurred": route_preflight.get("orders_submitted_by_generic_candidate_route_preflight") == 0
        and route_preflight.get("positions_opened_by_generic_candidate_route_preflight") == 0
        and route_preflight.get("positions_closed_by_generic_candidate_route_preflight") == 0,
        "live_disabled": route_preflight.get("live_enabled") is False,
        "testnet_disabled": route_preflight.get("testnet_enabled") is False,
        "exchange_broker_disabled": route_preflight.get("exchange_broker_enabled") is False,
    }

    blockers = [key for key, value in required_readiness.items() if value is not True]
    if missing_upstream_reports:
        blockers.append("candidate_route_preflight_report_present")
    if not_ready_upstream_reports:
        blockers.append("candidate_route_preflight_report_ready")
    ready = not blockers and settings.fail_closed is True

    handoff_map = _handoff_dry_run_map(route_preflight)

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT",
            "DRY_RUN_PREFLIGHT_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "DIAGNOSTIC_ROUTE_TO_HANDOFF_MAP_ONLY",
            "NO_HANDOFF_EXECUTION",
            "NO_ORDER_INTENT_CREATION",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT_READY" if ready else "GENERIC_ROUTE_TO_HANDOFF_DRY_RUN_PREFLIGHT_BLOCKED",
        ],
        "blockers": blockers,
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "upstream_reports_present": [] if not route_preflight else [route_report_name],
        "required_readiness": required_readiness,
        "generic_route_to_handoff_dry_run_preflight_ready": ready,
        "generic_route_to_handoff_dry_run_preflight_plan_ready": ready,
        "generic_route_to_handoff_dry_run_preflight_contract_ready": ready,
        "generic_route_to_handoff_dry_run_preflight_map_ready": ready,
        "generic_handoff_dry_run_preflight_gate_model_ready": ready,
        "generic_handoff_dry_run_preflight_fail_closed_ready": ready,
        "route_preflight_ready": route_preflight.get("generic_candidate_route_preflight_ready") is True,
        "candidate_route_preflight_diagnostic_available": diagnostic_available,
        "candidate_route_preflight_diagnostic_count": diagnostic_count,
        "handoff_dry_run_preflight_diagnostic_available": diagnostic_available,
        "handoff_dry_run_preflight_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": route_preflight.get("candidate_diagnostic_examples", []),
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "paper_order_intent_ready": False,
        "would_route": False,
        "would_handoff": False,
        "would_create_order": False,
        "would_submit": False,
        "route_preflight_blocked_reason": "route_execution_not_allowed_preflight_only",
        "handoff_dry_run_blocked_reason": "handoff_execution_not_allowed_dry_run_preflight_only",
        "paper_order_intent_blocked_reason": "paper_order_intent_creation_deferred_to_future_order_intent_patch",
        "candidate_route_preflight_map": route_preflight.get("candidate_route_preflight_map", {}),
        "route_to_handoff_dry_run_preflight_map": handoff_map,
        "blocked_until_explicit_handoff_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_HANDOFF_IMPLEMENTATION_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": route_preflight.get("lifecycle_state", ""),
        "fourth_trade_locked": route_preflight.get("fourth_trade_locked") is True,
        "stability_lock_active": route_preflight.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "no_route_candidate": True,
        "no_order_intent_currently_available": True,
        "paper_state_status_consistency": route_preflight.get("paper_state_status_consistency") is True,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_candidate_creation_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_candidate_creation_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_order_intent_creation_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_open_position_monitor_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
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
        "orders_submitted_by_generic_route_to_handoff_dry_run_preflight": 0,
        "positions_opened_by_generic_route_to_handoff_dry_run_preflight": 0,
        "positions_closed_by_generic_route_to_handoff_dry_run_preflight": 0,
        "paper_state_modified_by_generic_route_to_handoff_dry_run_preflight": False,
        "paper_status_modified_by_generic_route_to_handoff_dry_run_preflight": False,
        "broker_submit_called_by_generic_route_to_handoff_dry_run_preflight": False,
        "broker_close_called_by_generic_route_to_handoff_dry_run_preflight": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "generic_route_to_handoff_dry_run_preflight_source_files_present": not missing_source_files,
        "generic_route_to_handoff_dry_run_preflight_required_markers_present": not missing_source_markers,
        "source_markers_present": source_markers_present,
        "missing_generic_route_to_handoff_dry_run_preflight_source_files": missing_source_files,
        "missing_generic_route_to_handoff_dry_run_preflight_source_markers": missing_source_markers,
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "next_step": "prepare_generic_order_intent_dry_run_preflight_or_continue_observation",
        "recommended_next_patch": "29.4.4u-20 — Generic LSR-v2 paper-only handoff-to-order-intent dry-run preflight",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report
