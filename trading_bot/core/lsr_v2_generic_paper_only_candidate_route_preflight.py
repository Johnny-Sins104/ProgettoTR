"""Generic LSR-v2 paper-only candidate route preflight.

29.4.4u-18 is intentionally preflight-only, read-only, and fail-closed.
It consumes the diagnostic candidate evidence produced by u-17 and prepares a
non-executing generic route preflight map. It never performs route execution,
creates a paper order intent, submits/closes an order, opens/closes a position,
starts a scheduler, calls a broker, sends Telegram messages, or mutates
paper_state/paper_status.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-18"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_ROUTE_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_ROUTE_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_ROUTE_PREFLIGHT_NOT_READY"

U17_READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT_READY"

ROUTE_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_candidate_detection_audit",
    "verify_diagnostic_candidate_evidence",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_existing_route_candidate",
    "verify_no_paper_order_intent",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_candidate_diagnostic_to_route_preflight_context",
    "map_route_preflight_gate_model",
    "map_route_preflight_safety_outputs",
    "publish_generic_candidate_route_preflight_artifact",
)

BLOCKED_UNTIL_EXPLICIT_ROUTE_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_candidate_route_runtime_activation",
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
        "trading_bot/core/lsr_v2_generic_paper_only_candidate_detection_audit.py",
        (
            "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT",
            "candidate_detection_source_counts",
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
    "generic_candidate_detection_audit_execution_allowed",
    "generic_candidate_detection_allowed",
    "generic_candidate_scan_execution_allowed",
    "generic_candidate_probe_allowed",
    "generic_route_execution_allowed",
    "generic_handoff_execution_allowed",
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
    report_name: str = "lsr_v2_generic_paper_only_candidate_route_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_candidate_route_preflight.jsonl"
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


def _candidate_route_preflight_map(candidate_audit: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostic_count = _safe_int(candidate_audit.get("candidate_detected_diagnostic_count"), 0)
    return {
        "mode": "candidate_route_preflight_only",
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "candidate_detected_diagnostic": candidate_audit.get("candidate_detected_diagnostic") is True,
        "candidate_detected_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": candidate_audit.get("candidate_detection_source_counts", {}),
        "candidate_diagnostic_examples": candidate_audit.get("candidate_diagnostic_examples", []),
        "route_preflight_context": {
            "diagnostic_candidates_available": diagnostic_count > 0,
            "route_candidate_available": False,
            "paper_order_intent_ready": False,
            "would_route": False,
            "would_create_order": False,
            "would_submit": False,
            "blocked_reason": "route_execution_not_allowed_preflight_only",
        },
        "required_future_controls_before_route_execution": {
            "explicit_generic_route_execution_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_order_intent_creation_deferred": True,
        },
        "diagnostic_outputs": {
            "candidate_route_preflight_diagnostic_available": "boolean",
            "candidate_route_preflight_diagnostic_count": "integer",
            "route_candidate_available": "false_until_route_execution_patch",
            "paper_order_intent_ready": "false_until_handoff_or_order_intent_patch",
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in ROUTE_PREFLIGHT_STAGES
        ],
    }


def run_generic_paper_only_candidate_route_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    audit_report_name = "lsr_v2_generic_paper_only_candidate_detection_audit_report.json"
    candidate_audit = _read_json(data_path / audit_report_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not candidate_audit:
        missing_upstream_reports.append(audit_report_name)
    elif candidate_audit.get("status") != "PASS" or candidate_audit.get("decision") != U17_READY_DECISION:
        not_ready_upstream_reports.append(audit_report_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(candidate_audit, FALSE_EXECUTION_KEYS)

    diagnostic_count = _safe_int(candidate_audit.get("candidate_detected_diagnostic_count"), 0)
    diagnostic_available = candidate_audit.get("candidate_detected_diagnostic") is True and diagnostic_count > 0
    candidate_source_counts = candidate_audit.get("candidate_detection_source_counts", {})
    if not isinstance(candidate_source_counts, dict):
        candidate_source_counts = {}

    required_readiness = {
        "candidate_detection_audit_ready": bool(candidate_audit.get("generic_candidate_detection_audit_ready") is True),
        "candidate_detection_diagnostic_scan_done": candidate_audit.get("candidate_detection_diagnostic_scan_executed") is True,
        "flat_locked_state": candidate_audit.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": _safe_int(candidate_audit.get("open_positions_after"), 0) == 0,
        "pending_orders_clear": _safe_int(candidate_audit.get("pending_orders_after"), 0) == 0,
        "no_existing_route_candidate": candidate_audit.get("route_candidate_available") is False,
        "no_paper_order_intent": candidate_audit.get("paper_order_intent_ready") is False,
        "operator_env_absent": not active_env,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "source_markers_present": source_markers_present,
        "live_disabled": candidate_audit.get("live_enabled") is False,
        "testnet_disabled": candidate_audit.get("testnet_enabled") is False,
        "exchange_broker_disabled": candidate_audit.get("exchange_broker_enabled") is False,
        "no_state_mutation": candidate_audit.get("paper_state_modified_by_generic_candidate_detection_audit") is False
        and candidate_audit.get("paper_status_modified_by_generic_candidate_detection_audit") is False,
        "no_submit_or_close_occurred": _safe_int(candidate_audit.get("orders_submitted_by_generic_candidate_detection_audit"), 0) == 0
        and _safe_int(candidate_audit.get("positions_opened_by_generic_candidate_detection_audit"), 0) == 0
        and _safe_int(candidate_audit.get("positions_closed_by_generic_candidate_detection_audit"), 0) == 0,
    }

    blockers = [name for name, ok in required_readiness.items() if not ok]
    if missing_upstream_reports:
        blockers.append("candidate_detection_audit_report_present")
    if not_ready_upstream_reports:
        blockers.append("candidate_detection_audit_report_ready")

    status = "PASS" if not blockers else "WARN"
    decision = READY_DECISION if status == "PASS" else KEEP_DIAGNOSTIC_DECISION

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": status,
        "decision": decision,
        "blockers": blockers,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_ROUTE_PREFLIGHT",
            "PREFLIGHT_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "DIAGNOSTIC_CANDIDATE_ROUTE_MAP_ONLY",
            "NO_ROUTE_EXECUTION",
            "NO_ORDER_INTENT_CREATION",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_CANDIDATE_ROUTE_PREFLIGHT_READY" if status == "PASS" else "GENERIC_CANDIDATE_ROUTE_PREFLIGHT_NOT_READY",
        ],
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "generic_candidate_route_preflight_ready": status == "PASS",
        "generic_candidate_route_preflight_plan_ready": True,
        "generic_candidate_route_preflight_contract_ready": True,
        "generic_candidate_route_preflight_map_ready": True,
        "generic_candidate_route_preflight_gate_model_ready": True,
        "generic_candidate_route_preflight_fail_closed_ready": True,
        "candidate_route_preflight_diagnostic_available": diagnostic_available,
        "candidate_route_preflight_diagnostic_count": diagnostic_count,
        "candidate_detected_diagnostic": candidate_audit.get("candidate_detected_diagnostic") is True,
        "candidate_detected_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": candidate_source_counts,
        "candidate_diagnostic_examples": candidate_audit.get("candidate_diagnostic_examples", []),
        "candidate_route_preflight_map": _candidate_route_preflight_map(candidate_audit),
        "required_readiness": required_readiness,
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "missing_generic_candidate_route_preflight_source_files": missing_source_files,
        "missing_generic_candidate_route_preflight_source_markers": missing_source_markers,
        "generic_candidate_route_preflight_source_files_present": not missing_source_files,
        "generic_candidate_route_preflight_required_markers_present": source_markers_present,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": not active_env,
        "lifecycle_state": candidate_audit.get("lifecycle_state", ""),
        "fourth_trade_locked": candidate_audit.get("fourth_trade_locked", True),
        "stability_lock_active": candidate_audit.get("stability_lock_active", True),
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "paper_order_intent_ready": False,
        "no_route_candidate": True,
        "no_order_intent_currently_available": True,
        "would_route": False,
        "would_create_order": False,
        "would_submit": False,
        "route_preflight_blocked_reason": "route_execution_not_allowed_preflight_only",
        "paper_order_intent_blocked_reason": "paper_order_intent_creation_deferred_to_future_handoff_patch",
        "open_positions_after": _safe_int(candidate_audit.get("open_positions_after"), 0),
        "pending_orders_after": _safe_int(candidate_audit.get("pending_orders_after"), 0),
        "paper_state_status_consistency": candidate_audit.get("paper_state_status_consistency", True),
        "source_markers_present": source_markers_present,
        "upstream_reports_present": [audit_report_name] if candidate_audit else [],
        "blocked_until_explicit_route_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_ROUTE_IMPLEMENTATION_PATCH),
        "next_step": "prepare_generic_handoff_dry_run_preflight_only_if_route_preflight_is_promoted_later_or_continue_observation",
        "recommended_next_patch": "29.4.4u-19 — Generic LSR-v2 paper-only route-to-handoff dry-run preflight",
        # execution/mutation/safety interlocks intentionally false
        "generic_candidate_route_preflight_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_route_candidate_creation_allowed": False,
        "generic_order_intent_creation_allowed": False,
        "generic_handoff_execution_allowed": False,
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
        "orders_submitted_by_generic_candidate_route_preflight": 0,
        "positions_opened_by_generic_candidate_route_preflight": 0,
        "positions_closed_by_generic_candidate_route_preflight": 0,
        "paper_state_modified_by_generic_candidate_route_preflight": False,
        "paper_status_modified_by_generic_candidate_route_preflight": False,
        "broker_submit_called_by_generic_candidate_route_preflight": False,
        "broker_close_called_by_generic_candidate_route_preflight": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "EVENT_TYPE",
    "READY_DECISION",
    "Settings",
    "run_generic_paper_only_candidate_route_preflight",
]
