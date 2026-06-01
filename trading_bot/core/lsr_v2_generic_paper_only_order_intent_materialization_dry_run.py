"""Generic LSR-v2 paper-only order-intent materialization dry-run.

29.4.4u-23 is intentionally dry-run-only, read-only, and fail-closed. It
consumes the generic order-intent validation preflight from u-22 and simulates
how a future paper_order_intent could be materialized, without creating,
persisting, submitting, closing, or mutating paper_state/paper_status. Runtime
order values remain deferred until an explicit activation patch provides a real
candidate and operator gate.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-23"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN_NOT_READY"

U22_READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT_READY"

REQUIRED_ORDER_INTENT_FIELDS: Tuple[str, ...] = (
    "symbol",
    "side",
    "entry_price",
    "stop_loss",
    "take_profit",
    "risk_amount",
    "position_size",
    "max_open_positions",
    "paper_only",
)

DEFERRED_SENTINEL = "deferred_until_explicit_order_intent_patch"

ORDER_INTENT_MATERIALIZATION_DRY_RUN_STAGES: Tuple[str, ...] = (
    "load_generic_order_intent_validation_preflight",
    "verify_order_intent_validation_preflight_ready",
    "verify_contract_ready_and_validatable",
    "verify_runtime_value_validation_still_deferred",
    "verify_flat_locked_state",
    "verify_no_route_or_handoff_candidate",
    "verify_no_existing_order_intent",
    "verify_no_order_intent_materialization",
    "verify_no_order_intent_persistence",
    "verify_no_real_order_intent_creation",
    "verify_no_submit_or_close",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "simulate_order_intent_materialization_payload",
    "map_materialization_dry_run_gate_model",
    "publish_generic_order_intent_materialization_dry_run_artifact",
)

BLOCKED_UNTIL_EXPLICIT_ORDER_INTENT_ACTIVATION_PATCH: Tuple[str, ...] = (
    "generic_order_intent_runtime_value_validation",
    "generic_order_intent_materialization_real",
    "generic_order_intent_persistence_real",
    "generic_submit_readiness_preflight",
    "generic_submit_candidate_audit",
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
        "trading_bot/core/lsr_v2_generic_paper_only_order_intent_validation_preflight.py",
        (
            "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT",
            "paper_order_intent_contract_validatable",
        ),
    ),
    ("trading_bot/core/paper_engine.py", ("PaperTradingEngine",)),
    ("trading_bot/run_paper_trading.py", ("argparse",)),
)

FALSE_EXECUTION_KEYS: Tuple[str, ...] = (
    "generic_candidate_detection_allowed",
    "generic_candidate_scan_execution_allowed",
    "generic_candidate_probe_allowed",
    "generic_route_candidate_creation_allowed",
    "generic_route_execution_allowed",
    "generic_handoff_candidate_creation_allowed",
    "generic_handoff_execution_allowed",
    "generic_order_intent_candidate_materialization_allowed",
    "generic_order_intent_validation_allowed",
    "generic_order_intent_validation_execution_allowed",
    "generic_order_intent_creation_allowed",
    "generic_order_intent_dry_run_execution_allowed",
    "generic_order_intent_persistence_allowed",
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
    report_name: str = "lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_order_intent_materialization_dry_run.jsonl"
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
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _candidate_examples(payload: Mapping[str, Any], limit: int = 5) -> List[Any]:
    examples = payload.get("candidate_diagnostic_examples", [])
    if isinstance(examples, list):
        return examples[:limit]
    return []


def _source_model(validation_preflight: Mapping[str, Any]) -> Dict[str, Any]:
    validation_map = _as_dict(validation_preflight.get("order_intent_validation_preflight_map", {}))
    model = _as_dict(validation_map.get("source_order_intent_model", {}))
    if model:
        return model
    candidate_map = _as_dict(validation_preflight.get("order_intent_candidate_audit_map", {}))
    return _as_dict(candidate_map.get("upstream_paper_order_intent_model", {}))


def _runtime_values_present(model: Mapping[str, Any]) -> bool:
    for field in REQUIRED_ORDER_INTENT_FIELDS:
        value = model.get(field)
        if value in (None, "", DEFERRED_SENTINEL):
            return False
    return True


def _build_materialization_dry_run_map(validation_preflight: Mapping[str, Any]) -> Dict[str, Any]:
    model = _source_model(validation_preflight)
    present_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in model]
    missing_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in model]
    contract_ready = len(missing_fields) == 0 and model.get("max_open_positions") == 1 and model.get("paper_only") is True
    runtime_values_present = _runtime_values_present(model)

    dry_run_payload = {
        "symbol": model.get("symbol", DEFERRED_SENTINEL),
        "side": model.get("side", DEFERRED_SENTINEL),
        "entry_price": model.get("entry_price", DEFERRED_SENTINEL),
        "stop_loss": model.get("stop_loss", DEFERRED_SENTINEL),
        "take_profit": model.get("take_profit", DEFERRED_SENTINEL),
        "risk_amount": model.get("risk_amount", DEFERRED_SENTINEL),
        "position_size": model.get("position_size", DEFERRED_SENTINEL),
        "max_open_positions": model.get("max_open_positions", 1),
        "paper_only": model.get("paper_only") is True,
        "materialized": False,
        "persisted": False,
        "dry_run_only": True,
        "runtime_values_present": runtime_values_present,
    }

    return {
        "mode": "order_intent_materialization_dry_run_only",
        "paper_only": True,
        "dry_run_only": True,
        "preflight_source": "29.4.4u-22",
        "read_only": True,
        "fail_closed": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "source_order_intent_model": model,
        "dry_run_order_intent_payload": dry_run_payload,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": present_fields,
        "missing_contract_fields": missing_fields,
        "contract_ready_for_dry_run_materialization": contract_ready,
        "paper_order_intent_dry_run_ready": contract_ready,
        "paper_order_intent_materialization_dry_run_ready": contract_ready,
        "paper_order_intent_materialization_simulated": contract_ready,
        "paper_order_intent_runtime_values_present": runtime_values_present,
        "paper_order_intent_runtime_values_required_before_real_materialization": True,
        "paper_order_intent_runtime_validation_required_before_real_materialization": True,
        "materialization_dry_run_context": {
            "paper_order_intent_dry_run_ready": contract_ready,
            "paper_order_intent_materialization_simulated": contract_ready,
            "paper_order_intent_runtime_values_present": runtime_values_present,
            "paper_order_intent_validated": False,
            "paper_order_intent_materialized": False,
            "paper_order_intent_persisted": False,
            "paper_order_intent_ready": False,
            "would_materialize_order_intent_dry_run": contract_ready,
            "would_validate_order_intent": False,
            "would_create_order_intent": False,
            "would_create_order": False,
            "would_submit": False,
            "blocked_reason": "order_intent_creation_not_allowed_materialization_dry_run_only",
        },
        "required_future_controls_before_real_order_intent_creation": {
            "explicit_generic_order_intent_activation_patch_required": True,
            "explicit_generic_order_intent_persistence_patch_required": True,
            "explicit_generic_submit_readiness_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "runtime_values_required": True,
            "runtime_value_validation_required": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_order_intent_persistence_deferred": True,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in ORDER_INTENT_MATERIALIZATION_DRY_RUN_STAGES
        ],
    }


def run_generic_paper_only_order_intent_materialization_dry_run(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json"
    validation_preflight = _read_json(data_path / upstream_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not validation_preflight:
        missing_upstream_reports.append(upstream_name)
    elif validation_preflight.get("status") != "PASS" or validation_preflight.get("decision") != U22_READY_DECISION:
        not_ready_upstream_reports.append(upstream_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(validation_preflight, FALSE_EXECUTION_KEYS)

    materialization_map = _build_materialization_dry_run_map(validation_preflight)
    validation_map = _as_dict(validation_preflight.get("order_intent_validation_preflight_map", {}))
    source_counts = validation_preflight.get("candidate_detection_source_counts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}

    diagnostic_count = _safe_int(validation_preflight.get("order_intent_candidate_audit_diagnostic_count"), 0)
    diagnostic_available = validation_preflight.get("order_intent_candidate_audit_diagnostic_available") is True and diagnostic_count > 0

    required_fields = _as_list(validation_preflight.get("order_intent_candidate_contract_required_fields", []))
    present_fields = _as_list(validation_preflight.get("order_intent_candidate_contract_present_fields", []))
    missing_fields = _as_list(validation_preflight.get("order_intent_candidate_contract_missing_fields", []))
    required_set = set(REQUIRED_ORDER_INTENT_FIELDS)
    upstream_required_fields_ok = required_set.issubset(set(str(item) for item in required_fields))
    upstream_present_fields_ok = required_set.issubset(set(str(item) for item in present_fields))
    upstream_missing_fields_ok = missing_fields == []

    required_readiness = {
        "order_intent_validation_preflight_report_ready": validation_preflight.get("generic_order_intent_validation_preflight_ready") is True,
        "order_intent_candidate_audit_diagnostic_available": diagnostic_available,
        "contract_ready": validation_preflight.get("paper_order_intent_contract_ready") is True,
        "contract_validatable": validation_preflight.get("paper_order_intent_contract_validatable") is True,
        "contract_validation_preflight_ready": validation_preflight.get("paper_order_intent_contract_validation_preflight_ready") is True,
        "required_contract_fields_complete": upstream_required_fields_ok,
        "present_contract_fields_complete": upstream_present_fields_ok,
        "missing_contract_fields_empty": upstream_missing_fields_ok,
        "materialization_dry_run_contract_ready": materialization_map.get("contract_ready_for_dry_run_materialization") is True,
        "runtime_validation_deferred": validation_preflight.get("paper_order_intent_runtime_value_validation_deferred") is True,
        "runtime_validation_not_executed": validation_preflight.get("paper_order_intent_runtime_value_validation_executed") is False,
        "order_intent_not_validated": validation_preflight.get("paper_order_intent_validated") is False,
        "order_intent_not_materialized": validation_preflight.get("paper_order_intent_materialized") is False,
        "order_intent_not_persisted": validation_preflight.get("paper_order_intent_persisted") is False,
        "order_intent_not_ready": validation_preflight.get("paper_order_intent_ready") is False,
        "would_validate_order_intent_false": validation_preflight.get("would_validate_order_intent") is False,
        "would_create_order_intent_false": validation_preflight.get("would_create_order_intent") is False,
        "would_create_order_false": validation_preflight.get("would_create_order") is False,
        "would_submit_false": validation_preflight.get("would_submit") is False,
        "flat_locked_state": validation_preflight.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": validation_preflight.get("open_positions_after") == 0,
        "pending_orders_clear": validation_preflight.get("pending_orders_after") == 0,
        "no_existing_route_candidate": validation_preflight.get("route_candidate_available") is False,
        "no_existing_handoff_candidate": validation_preflight.get("handoff_candidate_available") is False,
        "validation_execution_blocked": validation_preflight.get("generic_order_intent_validation_execution_allowed") is False,
        "order_intent_creation_blocked": validation_preflight.get("generic_order_intent_creation_allowed") is False,
        "order_intent_persistence_blocked": validation_preflight.get("generic_order_intent_persistence_allowed") is False,
        "submit_execution_blocked": validation_preflight.get("generic_submit_execution_allowed") is False,
        "operator_env_absent": len(active_env) == 0,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "source_markers_present": source_markers_present,
        "no_state_mutation": validation_preflight.get("paper_state_modified_by_generic_order_intent_validation_preflight") is False
        and validation_preflight.get("paper_status_modified_by_generic_order_intent_validation_preflight") is False,
        "no_submit_or_close_occurred": validation_preflight.get("orders_submitted_by_generic_order_intent_validation_preflight") == 0
        and validation_preflight.get("positions_opened_by_generic_order_intent_validation_preflight") == 0
        and validation_preflight.get("positions_closed_by_generic_order_intent_validation_preflight") == 0,
        "live_disabled": validation_preflight.get("live_enabled") is False,
        "testnet_disabled": validation_preflight.get("testnet_enabled") is False,
        "exchange_broker_disabled": validation_preflight.get("exchange_broker_enabled") is False,
    }

    blockers = [key for key, value in required_readiness.items() if value is not True]
    if missing_upstream_reports:
        blockers.append("order_intent_validation_preflight_report_present")
    if not_ready_upstream_reports:
        blockers.append("order_intent_validation_preflight_report_ready")
    ready = not blockers and settings.fail_closed is True

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN",
            "DRY_RUN_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "DIAGNOSTIC_ORDER_INTENT_MATERIALIZATION_SIMULATION_ONLY",
            "NO_REAL_ORDER_INTENT_CREATION",
            "NO_ORDER_INTENT_PERSISTENCE",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_ORDER_INTENT_MATERIALIZATION_DRY_RUN_READY" if ready else "GENERIC_ORDER_INTENT_MATERIALIZATION_DRY_RUN_BLOCKED",
        ],
        "blockers": blockers,
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "upstream_reports_present": [] if not validation_preflight else [upstream_name],
        "required_readiness": required_readiness,
        "generic_order_intent_materialization_dry_run_ready": ready,
        "generic_order_intent_materialization_dry_run_plan_ready": ready,
        "generic_order_intent_materialization_dry_run_contract_ready": ready,
        "generic_order_intent_materialization_dry_run_map_ready": ready,
        "generic_order_intent_materialization_dry_run_fail_closed_ready": ready,
        "generic_order_intent_materialization_dry_run_source_files_present": not missing_source_files,
        "generic_order_intent_materialization_dry_run_required_markers_present": not missing_source_markers,
        "order_intent_validation_preflight_ready": validation_preflight.get("generic_order_intent_validation_preflight_ready") is True,
        "paper_order_intent_contract_ready": validation_preflight.get("paper_order_intent_contract_ready") is True,
        "paper_order_intent_contract_validatable": validation_preflight.get("paper_order_intent_contract_validatable") is True,
        "paper_order_intent_contract_validation_preflight_ready": validation_preflight.get("paper_order_intent_contract_validation_preflight_ready") is True,
        "order_intent_candidate_audit_diagnostic_available": diagnostic_available,
        "order_intent_candidate_audit_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(validation_preflight),
        "order_intent_candidate_contract_required_fields": required_fields,
        "order_intent_candidate_contract_present_fields": present_fields,
        "order_intent_candidate_contract_missing_fields": missing_fields,
        "paper_order_intent_dry_run_ready": ready,
        "paper_order_intent_materialization_dry_run_ready": ready,
        "paper_order_intent_materialization_simulated": ready,
        "paper_order_intent_runtime_values_present": materialization_map.get("paper_order_intent_runtime_values_present") is True,
        "paper_order_intent_runtime_values_required_before_real_materialization": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "would_materialize_order_intent_dry_run": ready,
        "would_validate_order_intent": False,
        "would_route": False,
        "would_handoff": False,
        "would_create_order_intent": False,
        "would_create_order": False,
        "would_submit": False,
        "paper_order_intent_materialization_blocked_reason": "order_intent_real_materialization_not_allowed_dry_run_only",
        "paper_order_intent_persistence_blocked_reason": "order_intent_persistence_not_allowed_dry_run_only",
        "generic_order_intent_materialization_dry_run_map": materialization_map,
        "order_intent_validation_preflight_map": validation_map,
        "blocked_until_explicit_order_intent_activation_patch": list(BLOCKED_UNTIL_EXPLICIT_ORDER_INTENT_ACTIVATION_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": validation_preflight.get("lifecycle_state", ""),
        "fourth_trade_locked": validation_preflight.get("fourth_trade_locked") is True,
        "stability_lock_active": validation_preflight.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "no_route_candidate": True,
        "no_handoff_candidate": True,
        "no_order_intent_currently_available": True,
        "paper_state_status_consistency": validation_preflight.get("paper_state_status_consistency") is True,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_candidate_creation_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_candidate_creation_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_order_intent_candidate_materialization_allowed": False,
        "generic_order_intent_validation_allowed": False,
        "generic_order_intent_validation_execution_allowed": False,
        "generic_order_intent_materialization_allowed": False,
        "generic_order_intent_creation_allowed": False,
        "generic_order_intent_dry_run_execution_allowed": False,
        "generic_order_intent_persistence_allowed": False,
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
        "orders_submitted_by_generic_order_intent_materialization_dry_run": 0,
        "positions_opened_by_generic_order_intent_materialization_dry_run": 0,
        "positions_closed_by_generic_order_intent_materialization_dry_run": 0,
        "paper_state_modified_by_generic_order_intent_materialization_dry_run": False,
        "paper_status_modified_by_generic_order_intent_materialization_dry_run": False,
        "broker_submit_called_by_generic_order_intent_materialization_dry_run": False,
        "broker_close_called_by_generic_order_intent_materialization_dry_run": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "source_markers_present": source_markers_present,
        "missing_generic_order_intent_materialization_dry_run_source_files": missing_source_files,
        "missing_generic_order_intent_materialization_dry_run_source_markers": missing_source_markers,
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "next_step": "prepare_generic_submit_readiness_preflight_or_continue_observation",
        "recommended_next_patch": "29.4.4u-24 — Generic LSR-v2 paper-only submit readiness preflight",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "READY_DECISION",
    "REQUIRED_ORDER_INTENT_FIELDS",
    "Settings",
    "run_generic_paper_only_order_intent_materialization_dry_run",
]
