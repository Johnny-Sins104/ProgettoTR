"""Generic LSR-v2 paper-only submit readiness preflight.

29.4.4u-24 is intentionally preflight-only, read-only, and fail-closed. It
consumes the generic order-intent materialization dry-run from u-23 and checks
whether the dry-run payload has the shape and safety envelope required for a
future generic paper-only submit path. It does not validate live runtime order
values, does not create or persist a paper_order_intent, does not submit orders,
does not close positions, and does not mutate paper_state/paper_status.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-24"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_SUBMIT_READINESS_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_SUBMIT_READINESS_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_SUBMIT_READINESS_PREFLIGHT_NOT_READY"

U23_READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN_READY"

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
OPERATOR_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_SUBMIT_ONLY"

SUBMIT_READINESS_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_order_intent_materialization_dry_run",
    "verify_order_intent_materialization_dry_run_ready",
    "verify_dry_run_order_intent_payload_shape",
    "verify_runtime_values_still_deferred",
    "verify_no_real_order_intent_materialized",
    "verify_no_order_intent_persistence",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_paper_only_policy",
    "verify_operator_submit_gate_required_but_absent",
    "verify_no_route_handoff_or_submit_candidate",
    "verify_no_submit_or_close",
    "verify_no_broker_network_scheduler_or_state_mutation",
    "verify_live_testnet_exchange_disabled",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_submit_readiness_gate_model",
    "publish_generic_submit_readiness_preflight_artifact",
)

BLOCKED_UNTIL_EXPLICIT_SUBMIT_CANDIDATE_OR_EXECUTION_PATCH: Tuple[str, ...] = (
    "generic_order_intent_runtime_value_validation",
    "generic_order_intent_materialization_real",
    "generic_order_intent_persistence_real",
    "generic_submit_candidate_audit",
    "generic_submit_execution_scaffold",
    "generic_broker_submit",
    "generic_broker_close",
    "generic_open_position_monitor",
    "generic_paper_state_mutation",
    "generic_paper_status_mutation",
    "telegram_network_send",
    "scheduler_start",
    "live_or_testnet_or_exchange_broker",
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_paper_only_order_intent_materialization_dry_run.py",
        (
            "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_MATERIALIZATION_DRY_RUN",
            "paper_order_intent_materialization_dry_run_ready",
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
    "generic_order_intent_materialization_allowed",
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
    report_name: str = "lsr_v2_generic_paper_only_submit_readiness_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_submit_readiness_preflight.jsonl"
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


def _dry_run_payload(materialization_report: Mapping[str, Any]) -> Dict[str, Any]:
    materialization_map = _as_dict(materialization_report.get("generic_order_intent_materialization_dry_run_map", {}))
    return _as_dict(materialization_map.get("dry_run_order_intent_payload", {}))


def _runtime_values_present(payload: Mapping[str, Any]) -> bool:
    for field in REQUIRED_ORDER_INTENT_FIELDS:
        value = payload.get(field)
        if value in (None, "", DEFERRED_SENTINEL):
            return False
    return True


def _build_submit_readiness_preflight_map(materialization_report: Mapping[str, Any]) -> Dict[str, Any]:
    materialization_map = _as_dict(materialization_report.get("generic_order_intent_materialization_dry_run_map", {}))
    payload = _dry_run_payload(materialization_report)
    present_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload]
    missing_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in payload]
    max_open_positions_valid = payload.get("max_open_positions") == 1
    paper_only_valid = payload.get("paper_only") is True
    contract_ready = len(missing_fields) == 0 and max_open_positions_valid and paper_only_valid
    runtime_values_present = _runtime_values_present(payload)
    dry_run_ready = materialization_report.get("paper_order_intent_dry_run_ready") is True
    materialization_simulated = materialization_report.get("paper_order_intent_materialization_simulated") is True
    readiness_model_ready = contract_ready and dry_run_ready and materialization_simulated

    submit_gate_model = {
        "paper_only_required": True,
        "paper_only_valid": paper_only_valid,
        "max_open_positions_required": 1,
        "max_open_positions_valid": max_open_positions_valid,
        "operator_gate_required": True,
        "operator_enable_env": "LSR_V2_GENERIC_SUBMIT_ENABLE",
        "operator_confirmation_env": "LSR_V2_GENERIC_SUBMIT_CONFIRMATION",
        "operator_confirmation_required_value": OPERATOR_CONFIRMATION_SENTINEL,
        "operator_gate_satisfied": False,
        "runtime_values_required_before_submit_candidate": True,
        "runtime_values_present": runtime_values_present,
        "dry_run_order_intent_required": True,
        "dry_run_order_intent_ready": dry_run_ready,
        "real_paper_order_intent_required_before_submit_execution": True,
        "real_paper_order_intent_ready": False,
    }

    return {
        "mode": "generic_submit_readiness_preflight_only",
        "paper_only": True,
        "preflight_only": True,
        "read_only": True,
        "fail_closed": True,
        "preflight_source": "29.4.4u-23",
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "source_materialization_dry_run_map": materialization_map,
        "dry_run_order_intent_payload": payload,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": present_fields,
        "missing_contract_fields": missing_fields,
        "submit_readiness_contract_ready": contract_ready,
        "submit_readiness_preflight_model_ready": readiness_model_ready,
        "paper_submit_readiness_preflight_ready": readiness_model_ready,
        "generic_submit_readiness_gate_model_ready": readiness_model_ready,
        "paper_order_intent_dry_run_ready": dry_run_ready,
        "paper_order_intent_materialization_simulated": materialization_simulated,
        "paper_order_intent_runtime_values_present": runtime_values_present,
        "paper_order_intent_runtime_values_required_before_submit_candidate": True,
        "paper_order_intent_runtime_validation_required_before_submit_candidate": True,
        "paper_order_intent_real_materialization_required_before_submit_execution": True,
        "paper_order_intent_persistence_required_before_submit_execution": True,
        "submit_gate_model": submit_gate_model,
        "submit_readiness_preflight_context": {
            "submit_readiness_preflight_ready": readiness_model_ready,
            "paper_order_intent_dry_run_ready": dry_run_ready,
            "paper_order_intent_candidate_ready": False,
            "paper_order_intent_ready": False,
            "paper_order_intent_validated": False,
            "paper_order_intent_materialized": False,
            "paper_order_intent_persisted": False,
            "paper_order_intent_runtime_values_present": runtime_values_present,
            "paper_submit_candidate_ready": False,
            "generic_submit_execution_ready": False,
            "would_validate_order_intent": False,
            "would_create_order_intent": False,
            "would_create_order": False,
            "would_submit": False,
            "broker_submit_called": False,
            "blocked_reason": "submit_execution_not_allowed_readiness_preflight_only",
        },
        "required_future_controls_before_submit_candidate_audit": {
            "explicit_generic_submit_candidate_audit_patch_required": True,
            "explicit_generic_submit_execution_scaffold_patch_required": True,
            "explicit_generic_order_intent_activation_patch_required": True,
            "explicit_generic_order_intent_persistence_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "runtime_values_required": True,
            "runtime_value_validation_required": True,
            "real_paper_order_intent_required": True,
            "paper_order_intent_persistence_required": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in SUBMIT_READINESS_PREFLIGHT_STAGES
        ],
    }


def run_generic_paper_only_submit_readiness_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_paper_only_order_intent_materialization_dry_run_report.json"
    materialization_report = _read_json(data_path / upstream_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not materialization_report:
        missing_upstream_reports.append(upstream_name)
    elif materialization_report.get("status") != "PASS" or materialization_report.get("decision") != U23_READY_DECISION:
        not_ready_upstream_reports.append(upstream_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(materialization_report, FALSE_EXECUTION_KEYS)

    submit_map = _build_submit_readiness_preflight_map(materialization_report)
    source_counts = materialization_report.get("candidate_detection_source_counts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}

    diagnostic_count = _safe_int(materialization_report.get("order_intent_candidate_audit_diagnostic_count"), 0)
    diagnostic_available = materialization_report.get("order_intent_candidate_audit_diagnostic_available") is True and diagnostic_count > 0

    required_fields = _as_list(materialization_report.get("order_intent_candidate_contract_required_fields", []))
    present_fields = _as_list(materialization_report.get("order_intent_candidate_contract_present_fields", []))
    missing_fields = _as_list(materialization_report.get("order_intent_candidate_contract_missing_fields", []))
    required_set = set(REQUIRED_ORDER_INTENT_FIELDS)
    upstream_required_fields_ok = required_set.issubset(set(str(item) for item in required_fields))
    upstream_present_fields_ok = required_set.issubset(set(str(item) for item in present_fields))
    upstream_missing_fields_ok = missing_fields == []

    required_readiness = {
        "order_intent_materialization_dry_run_report_ready": materialization_report.get("generic_order_intent_materialization_dry_run_ready") is True,
        "order_intent_validation_preflight_ready": materialization_report.get("order_intent_validation_preflight_ready") is True,
        "order_intent_candidate_audit_diagnostic_available": diagnostic_available,
        "contract_ready": materialization_report.get("paper_order_intent_contract_ready") is True,
        "contract_validatable": materialization_report.get("paper_order_intent_contract_validatable") is True,
        "contract_validation_preflight_ready": materialization_report.get("paper_order_intent_contract_validation_preflight_ready") is True,
        "dry_run_order_intent_ready": materialization_report.get("paper_order_intent_dry_run_ready") is True,
        "materialization_dry_run_ready": materialization_report.get("paper_order_intent_materialization_dry_run_ready") is True,
        "materialization_simulated": materialization_report.get("paper_order_intent_materialization_simulated") is True,
        "would_materialize_order_intent_dry_run_true": materialization_report.get("would_materialize_order_intent_dry_run") is True,
        "submit_readiness_contract_ready": submit_map.get("submit_readiness_contract_ready") is True,
        "submit_readiness_preflight_model_ready": submit_map.get("submit_readiness_preflight_model_ready") is True,
        "single_position_policy_ready": _as_dict(submit_map.get("submit_gate_model", {})).get("max_open_positions_valid") is True,
        "paper_only_policy_ready": _as_dict(submit_map.get("submit_gate_model", {})).get("paper_only_valid") is True,
        "operator_submit_gate_required": _as_dict(submit_map.get("submit_gate_model", {})).get("operator_gate_required") is True,
        "operator_submit_gate_not_satisfied": _as_dict(submit_map.get("submit_gate_model", {})).get("operator_gate_satisfied") is False,
        "runtime_values_not_present": materialization_report.get("paper_order_intent_runtime_values_present") is False,
        "runtime_values_required_before_submit": submit_map.get("paper_order_intent_runtime_values_required_before_submit_candidate") is True,
        "runtime_validation_deferred": materialization_report.get("paper_order_intent_runtime_value_validation_deferred") is True,
        "runtime_validation_not_executed": materialization_report.get("paper_order_intent_runtime_value_validation_executed") is False,
        "order_intent_not_validated": materialization_report.get("paper_order_intent_validated") is False,
        "order_intent_not_materialized": materialization_report.get("paper_order_intent_materialized") is False,
        "order_intent_not_persisted": materialization_report.get("paper_order_intent_persisted") is False,
        "order_intent_not_ready": materialization_report.get("paper_order_intent_ready") is False,
        "would_validate_order_intent_false": materialization_report.get("would_validate_order_intent") is False,
        "would_create_order_intent_false": materialization_report.get("would_create_order_intent") is False,
        "would_create_order_false": materialization_report.get("would_create_order") is False,
        "would_submit_false": materialization_report.get("would_submit") is False,
        "flat_locked_state": materialization_report.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": materialization_report.get("open_positions_after") == 0,
        "pending_orders_clear": materialization_report.get("pending_orders_after") == 0,
        "no_existing_route_candidate": materialization_report.get("route_candidate_available") is False,
        "no_existing_handoff_candidate": materialization_report.get("handoff_candidate_available") is False,
        "order_intent_creation_blocked": materialization_report.get("generic_order_intent_creation_allowed") is False,
        "order_intent_materialization_blocked": materialization_report.get("generic_order_intent_materialization_allowed") is False,
        "order_intent_persistence_blocked": materialization_report.get("generic_order_intent_persistence_allowed") is False,
        "submit_execution_blocked": materialization_report.get("generic_submit_execution_allowed") is False,
        "operator_env_absent": len(active_env) == 0,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "source_markers_present": source_markers_present,
        "required_contract_fields_complete": upstream_required_fields_ok,
        "present_contract_fields_complete": upstream_present_fields_ok,
        "missing_contract_fields_empty": upstream_missing_fields_ok,
        "no_state_mutation": materialization_report.get("paper_state_modified_by_generic_order_intent_materialization_dry_run") is False
        and materialization_report.get("paper_status_modified_by_generic_order_intent_materialization_dry_run") is False,
        "no_submit_or_close_occurred": materialization_report.get("orders_submitted_by_generic_order_intent_materialization_dry_run") == 0
        and materialization_report.get("positions_opened_by_generic_order_intent_materialization_dry_run") == 0
        and materialization_report.get("positions_closed_by_generic_order_intent_materialization_dry_run") == 0,
        "live_disabled": materialization_report.get("live_enabled") is False,
        "testnet_disabled": materialization_report.get("testnet_enabled") is False,
        "exchange_broker_disabled": materialization_report.get("exchange_broker_enabled") is False,
    }

    blockers = [key for key, value in required_readiness.items() if value is not True]
    if missing_upstream_reports:
        blockers.append("order_intent_materialization_dry_run_report_present")
    if not_ready_upstream_reports:
        blockers.append("order_intent_materialization_dry_run_report_ready")
    ready = not blockers and settings.fail_closed is True

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_SUBMIT_READINESS_PREFLIGHT",
            "PREFLIGHT_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "DIAGNOSTIC_SUBMIT_GATE_MODEL_ONLY",
            "NO_REAL_ORDER_INTENT_CREATION",
            "NO_ORDER_INTENT_PERSISTENCE",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_SUBMIT_READINESS_PREFLIGHT_READY" if ready else "GENERIC_SUBMIT_READINESS_PREFLIGHT_BLOCKED",
        ],
        "blockers": blockers,
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "upstream_reports_present": [] if not materialization_report else [upstream_name],
        "required_readiness": required_readiness,
        "generic_submit_readiness_preflight_ready": ready,
        "generic_submit_readiness_preflight_plan_ready": ready,
        "generic_submit_readiness_preflight_contract_ready": ready,
        "generic_submit_readiness_preflight_map_ready": ready,
        "generic_submit_readiness_preflight_gate_model_ready": ready,
        "generic_submit_readiness_preflight_fail_closed_ready": ready,
        "generic_submit_readiness_preflight_source_files_present": not missing_source_files,
        "generic_submit_readiness_preflight_required_markers_present": not missing_source_markers,
        "generic_order_intent_materialization_dry_run_ready": materialization_report.get("generic_order_intent_materialization_dry_run_ready") is True,
        "order_intent_materialization_dry_run_ready": materialization_report.get("paper_order_intent_materialization_dry_run_ready") is True,
        "order_intent_validation_preflight_ready": materialization_report.get("order_intent_validation_preflight_ready") is True,
        "paper_order_intent_contract_ready": materialization_report.get("paper_order_intent_contract_ready") is True,
        "paper_order_intent_contract_validatable": materialization_report.get("paper_order_intent_contract_validatable") is True,
        "paper_order_intent_contract_validation_preflight_ready": materialization_report.get("paper_order_intent_contract_validation_preflight_ready") is True,
        "order_intent_candidate_audit_diagnostic_available": diagnostic_available,
        "order_intent_candidate_audit_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(materialization_report),
        "order_intent_candidate_contract_required_fields": required_fields,
        "order_intent_candidate_contract_present_fields": present_fields,
        "order_intent_candidate_contract_missing_fields": missing_fields,
        "paper_order_intent_dry_run_ready": materialization_report.get("paper_order_intent_dry_run_ready") is True and ready,
        "paper_order_intent_materialization_dry_run_ready": materialization_report.get("paper_order_intent_materialization_dry_run_ready") is True,
        "paper_order_intent_materialization_simulated": materialization_report.get("paper_order_intent_materialization_simulated") is True,
        "paper_order_intent_runtime_values_present": False,
        "paper_order_intent_runtime_values_required_before_submit_candidate": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_readiness_preflight_ready": ready,
        "paper_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "generic_submit_execution_scaffold_ready": False,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": False,
        "would_materialize_order_intent_dry_run": materialization_report.get("would_materialize_order_intent_dry_run") is True and ready,
        "would_validate_order_intent": False,
        "would_route": False,
        "would_handoff": False,
        "would_create_order_intent": False,
        "would_create_order": False,
        "would_submit": False,
        "would_call_paper_broker_submit": False,
        "paper_order_intent_materialization_blocked_reason": "order_intent_real_materialization_not_allowed_submit_readiness_preflight_only",
        "paper_order_intent_persistence_blocked_reason": "order_intent_persistence_not_allowed_submit_readiness_preflight_only",
        "generic_submit_execution_blocked_reason": "submit_execution_not_allowed_readiness_preflight_only",
        "generic_submit_readiness_preflight_map": submit_map,
        "generic_order_intent_materialization_dry_run_map": _as_dict(
            materialization_report.get("generic_order_intent_materialization_dry_run_map", {})
        ),
        "blocked_until_explicit_submit_candidate_or_execution_patch": list(
            BLOCKED_UNTIL_EXPLICIT_SUBMIT_CANDIDATE_OR_EXECUTION_PATCH
        ),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": materialization_report.get("lifecycle_state", ""),
        "fourth_trade_locked": materialization_report.get("fourth_trade_locked") is True,
        "stability_lock_active": materialization_report.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "no_route_candidate": True,
        "no_handoff_candidate": True,
        "no_order_intent_currently_available": True,
        "paper_state_status_consistency": materialization_report.get("paper_state_status_consistency") is True,
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
        "generic_submit_readiness_preflight_allowed": False,
        "generic_submit_candidate_audit_allowed": False,
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
        "orders_submitted_by_generic_submit_readiness_preflight": 0,
        "positions_opened_by_generic_submit_readiness_preflight": 0,
        "positions_closed_by_generic_submit_readiness_preflight": 0,
        "paper_state_modified_by_generic_submit_readiness_preflight": False,
        "paper_status_modified_by_generic_submit_readiness_preflight": False,
        "broker_submit_called_by_generic_submit_readiness_preflight": False,
        "broker_close_called_by_generic_submit_readiness_preflight": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "source_markers_present": source_markers_present,
        "missing_generic_submit_readiness_preflight_source_files": missing_source_files,
        "missing_generic_submit_readiness_preflight_source_markers": missing_source_markers,
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "next_step": "prepare_generic_submit_candidate_audit_or_continue_observation",
        "recommended_next_patch": "29.4.4u-25 — Generic LSR-v2 paper-only submit candidate audit",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "READY_DECISION",
    "REQUIRED_ORDER_INTENT_FIELDS",
    "Settings",
    "run_generic_paper_only_submit_readiness_preflight",
]
