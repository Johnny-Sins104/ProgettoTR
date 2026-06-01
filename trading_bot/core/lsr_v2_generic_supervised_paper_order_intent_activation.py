"""Generic LSR-v2 supervised paper-only order-intent activation gate.

29.4.4u-28 is intentionally controlled, read-only, and fail-closed by
normal validation defaults. It consumes u-27's order-intent activation preflight
artifact and evaluates whether a future real paper_order_intent activation could
be allowed under the explicit re-arm gate and complete runtime values.

This patch does not submit orders, does not call a broker, does not create a
submit candidate, does not mutate paper_state/paper_status, and does not touch
live/testnet/exchange paths. In the expected local validation environment the
operator gate is absent and runtime values are still deferred, so no real order
intent is materialized or persisted.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-28"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_READY"
KEEP_DIAGNOSTIC_DECISION = (
    "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_NOT_READY"
)

U27_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_PREFLIGHT_READY"

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
REARM_ENABLE_ENV = "LSR_V2_GENERIC_REARM_ENABLE"
REARM_CONFIRMATION_ENV = "LSR_V2_GENERIC_REARM_CONFIRMATION"
REARM_CONFIRMATION_SENTINEL = "I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY"
REARM_MAX_POSITIONS_ENV = "LSR_V2_GENERIC_REARM_MAX_POSITIONS"
SUBMIT_ENABLE_ENV = "LSR_V2_GENERIC_SUBMIT_ENABLE"
SUBMIT_CONFIRMATION_ENV = "LSR_V2_GENERIC_SUBMIT_CONFIRMATION"
SUBMIT_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_SUBMIT_ONLY"

ACTIVATION_STAGES: Tuple[str, ...] = (
    "load_generic_order_intent_activation_preflight",
    "verify_order_intent_activation_preflight_ready",
    "verify_activation_contract_shape_modelable",
    "verify_dry_run_order_intent_payload_shape",
    "verify_operator_rearm_gate",
    "verify_runtime_values_for_real_activation",
    "verify_single_position_policy",
    "verify_paper_only_policy",
    "verify_flat_locked_state",
    "verify_no_existing_order_intent",
    "verify_no_order_intent_materialized_or_persisted",
    "verify_no_submit_candidate_or_submit_execution",
    "verify_no_broker_network_scheduler_or_state_mutation",
    "verify_live_testnet_exchange_disabled",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_supervised_order_intent_activation_gate",
    "publish_generic_order_intent_activation_artifact",
)

BLOCKED_UNTIL_EXPLICIT_SUBMIT_EXECUTION_PATCH: Tuple[str, ...] = (
    "generic_order_intent_runtime_value_validation",
    "generic_order_intent_materialization_real_with_runtime_values",
    "generic_order_intent_persistence_real",
    "generic_submit_candidate_creation_real",
    "generic_supervised_submit_execution_activation",
    "generic_paper_broker_submit",
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
        "trading_bot/core/lsr_v2_generic_supervised_paper_order_intent_activation_preflight.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION_PREFLIGHT",
            "generic_supervised_paper_order_intent_activation_preflight_ready",
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
    "generic_order_intent_activation_allowed",
    "generic_submit_readiness_preflight_allowed",
    "generic_submit_candidate_audit_allowed",
    "generic_submit_candidate_creation_allowed",
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
    report_name: str = "lsr_v2_generic_supervised_paper_order_intent_activation_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_order_intent_activation.jsonl"
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


def _dry_run_payload(preflight_report: Mapping[str, Any]) -> Dict[str, Any]:
    activation_map = _as_dict(preflight_report.get("generic_order_intent_activation_preflight_map", {}))
    payload = _as_dict(activation_map.get("dry_run_order_intent_payload", {}))
    if payload:
        return payload
    scaffold_map = _as_dict(preflight_report.get("generic_submit_execution_scaffold_map", {}))
    return _as_dict(scaffold_map.get("dry_run_order_intent_payload", {}))


def _runtime_values_present(payload: Mapping[str, Any]) -> bool:
    for field in REQUIRED_ORDER_INTENT_FIELDS:
        value = payload.get(field)
        if value in (None, "", DEFERRED_SENTINEL):
            return False
    return True


def _numeric_runtime_values_valid(payload: Mapping[str, Any]) -> bool:
    for field in ("entry_price", "stop_loss", "take_profit", "risk_amount", "position_size"):
        try:
            if float(payload.get(field)) <= 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _directional_prices_valid(payload: Mapping[str, Any]) -> bool:
    side = payload.get("side")
    try:
        entry = float(payload.get("entry_price"))
        stop = float(payload.get("stop_loss"))
        target = float(payload.get("take_profit"))
    except (TypeError, ValueError):
        return False
    if side == "BUY":
        return stop < entry < target
    if side == "SELL":
        return target < entry < stop
    return False


def _rearm_gate_satisfied(active_env: Mapping[str, str]) -> bool:
    return (
        active_env.get(REARM_ENABLE_ENV) == "1"
        and active_env.get(REARM_CONFIRMATION_ENV) == REARM_CONFIRMATION_SENTINEL
        and active_env.get(REARM_MAX_POSITIONS_ENV) == "1"
    )


def _build_activation_map(
    preflight_report: Mapping[str, Any], active_env: Mapping[str, str]
) -> Dict[str, Any]:
    preflight_map = _as_dict(preflight_report.get("generic_order_intent_activation_preflight_map", {}))
    payload = _dry_run_payload(preflight_report)
    present_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload]
    missing_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in payload]
    runtime_values_present = _runtime_values_present(payload)
    numeric_values_valid = _numeric_runtime_values_valid(payload) if runtime_values_present else False
    directional_prices_valid = _directional_prices_valid(payload) if numeric_values_valid else False
    max_open_positions_valid = payload.get("max_open_positions") == 1
    paper_only_valid = payload.get("paper_only") is True
    preflight_ready = preflight_report.get("generic_supervised_paper_order_intent_activation_preflight_ready") is True
    contract_shape_modelable = preflight_report.get("order_intent_activation_contract_shape_modelable") is True
    rearm_gate_satisfied = _rearm_gate_satisfied(active_env)
    activation_model_ready = (
        preflight_ready
        and contract_shape_modelable
        and len(missing_fields) == 0
        and max_open_positions_valid
        and paper_only_valid
    )
    activation_allowed = (
        activation_model_ready
        and rearm_gate_satisfied
        and runtime_values_present
        and numeric_values_valid
        and directional_prices_valid
    )

    activation_blocked_reasons: List[str] = []
    if not activation_model_ready:
        activation_blocked_reasons.append("activation_model_not_ready")
    if not rearm_gate_satisfied:
        activation_blocked_reasons.append("operator_rearm_gate_not_satisfied")
    if not runtime_values_present:
        activation_blocked_reasons.append("runtime_values_absent_or_deferred")
    elif not numeric_values_valid:
        activation_blocked_reasons.append("runtime_numeric_values_invalid")
    elif not directional_prices_valid:
        activation_blocked_reasons.append("directional_stop_take_profit_invalid")

    return {
        "mode": "generic_supervised_paper_order_intent_activation_controlled",
        "paper_only": True,
        "activation_patch": True,
        "read_only": True,
        "fail_closed": True,
        "preflight_source": "29.4.4u-27",
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "source_order_intent_activation_preflight_map": preflight_map,
        "dry_run_order_intent_payload": payload,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": present_fields,
        "missing_contract_fields": missing_fields,
        "activation_gate_model": {
            "activation_model_ready": activation_model_ready,
            "activation_allowed": activation_allowed,
            "activation_blocked_reasons": activation_blocked_reasons,
            "operator_rearm_gate_required": True,
            "operator_rearm_gate_satisfied": rearm_gate_satisfied,
            "operator_rearm_enable_env": REARM_ENABLE_ENV,
            "operator_rearm_confirmation_env": REARM_CONFIRMATION_ENV,
            "operator_rearm_confirmation_required_value": REARM_CONFIRMATION_SENTINEL,
            "operator_rearm_max_positions_env": REARM_MAX_POSITIONS_ENV,
            "operator_rearm_max_positions_required_value": "1",
            "operator_submit_gate_required_later": True,
            "operator_submit_enable_env": SUBMIT_ENABLE_ENV,
            "operator_submit_confirmation_env": SUBMIT_CONFIRMATION_ENV,
            "operator_submit_confirmation_required_value": SUBMIT_CONFIRMATION_SENTINEL,
            "runtime_values_present": runtime_values_present,
            "runtime_values_required_before_real_activation": True,
            "runtime_numeric_values_valid": numeric_values_valid,
            "directional_stop_take_profit_validation_ready": True,
            "directional_stop_take_profit_valid": directional_prices_valid,
            "max_open_positions": 1,
            "max_open_positions_valid": max_open_positions_valid,
            "paper_only": True,
            "paper_only_valid": paper_only_valid,
            "real_order_intent_activation_allowed": activation_allowed,
            "paper_order_intent_materialization_allowed": activation_allowed,
            "paper_order_intent_persistence_allowed": False,
            "submit_candidate_creation_allowed": False,
            "submit_execution_allowed": False,
            "broker_submit_allowed": False,
            "missing_model_fields": missing_fields,
            "present_model_fields": present_fields,
            "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        },
        "activation_context": {
            "generic_supervised_paper_order_intent_activation_ready": activation_model_ready,
            "generic_order_intent_activation_model_ready": activation_model_ready,
            "generic_order_intent_activation_allowed": activation_allowed,
            "paper_order_intent_activation_ready": activation_allowed,
            "paper_order_intent_dry_run_ready": preflight_report.get("paper_order_intent_dry_run_ready") is True,
            "paper_order_intent_candidate_ready": False,
            "paper_order_intent_ready": False,
            "paper_order_intent_validated": False,
            "paper_order_intent_materialized": False,
            "paper_order_intent_persisted": False,
            "paper_order_intent_runtime_values_present": runtime_values_present,
            "paper_submit_candidate_ready": False,
            "generic_submit_candidate_ready": False,
            "paper_submit_execution_ready": False,
            "generic_submit_execution_allowed": False,
            "paper_broker_submit_allowed": False,
            "would_validate_order_intent": False,
            "would_activate_order_intent": activation_allowed,
            "would_create_order_intent": activation_allowed,
            "would_materialize_order_intent_real": activation_allowed,
            "would_persist_order_intent": False,
            "would_prepare_submit_candidate": False,
            "would_call_paper_broker_submit": False,
            "would_submit": False,
            "broker_submit_called": False,
            "blocked_reason": "none" if activation_allowed else "order_intent_activation_blocked_by_gate_or_runtime_values",
        },
        "required_future_controls_before_submit_execution": {
            "explicit_generic_order_intent_persistence_patch_required": True,
            "explicit_generic_submit_candidate_creation_patch_required": True,
            "explicit_generic_submit_execution_activation_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required_later": True,
            "runtime_values_required": True,
            "runtime_value_validation_required": True,
            "paper_order_intent_persistence_required_before_submit": True,
            "paper_submit_candidate_required_before_submit": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
        },
        "stages": [
            {
                "stage": stage,
                "execution_allowed": False,
                "state_mutation_allowed": False,
            }
            for stage in ACTIVATION_STAGES
        ],
    }


def run_generic_supervised_paper_order_intent_activation(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_supervised_paper_order_intent_activation_preflight_report.json"
    preflight_report = _read_json(data_path / upstream_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not preflight_report:
        missing_upstream_reports.append(upstream_name)
    elif preflight_report.get("status") != "PASS" or preflight_report.get("decision") != U27_READY_DECISION:
        not_ready_upstream_reports.append(upstream_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(preflight_report, FALSE_EXECUTION_KEYS)
    activation_map = _build_activation_map(preflight_report, active_env)
    activation_gate = _as_dict(activation_map.get("activation_gate_model", {}))
    activation_context = _as_dict(activation_map.get("activation_context", {}))

    diagnostic_count = _safe_int(preflight_report.get("order_intent_activation_preflight_diagnostic_count"), 0)
    upstream_diagnostic_available = (
        preflight_report.get("order_intent_activation_preflight_diagnostic_available") is True
        and diagnostic_count > 0
    )
    source_counts = preflight_report.get("candidate_detection_source_counts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}

    required_fields = _as_list(preflight_report.get("order_intent_activation_contract_required_fields", []))
    present_fields = _as_list(preflight_report.get("order_intent_activation_contract_present_fields", []))
    missing_fields = _as_list(preflight_report.get("order_intent_activation_contract_missing_fields", []))
    required_set = set(REQUIRED_ORDER_INTENT_FIELDS)
    upstream_required_fields_ok = required_set.issubset(set(str(item) for item in required_fields))
    upstream_present_fields_ok = required_set.issubset(set(str(item) for item in present_fields))
    upstream_missing_fields_ok = missing_fields == []
    gate_satisfied = activation_gate.get("operator_rearm_gate_satisfied") is True
    runtime_values_present = activation_gate.get("runtime_values_present") is True
    activation_allowed = activation_gate.get("activation_allowed") is True

    required_readiness = {
        "activation_preflight_report_ready": preflight_report.get("generic_supervised_paper_order_intent_activation_preflight_ready") is True,
        "generic_order_intent_activation_preflight_ready": preflight_report.get("generic_order_intent_activation_preflight_ready") is True,
        "paper_order_intent_activation_preflight_ready": preflight_report.get("paper_order_intent_activation_preflight_ready") is True,
        "order_intent_activation_preflight_diagnostic_available": upstream_diagnostic_available,
        "order_intent_activation_contract_shape_modelable": preflight_report.get("order_intent_activation_contract_shape_modelable") is True,
        "activation_model_ready": activation_gate.get("activation_model_ready") is True,
        "operator_rearm_gate_required": True,
        "operator_rearm_gate_not_satisfied": not gate_satisfied,
        "runtime_values_required_before_activation": True,
        "runtime_values_not_present": not runtime_values_present,
        "runtime_validation_deferred": preflight_report.get("paper_order_intent_runtime_value_validation_deferred") is True,
        "runtime_validation_not_executed": preflight_report.get("paper_order_intent_runtime_value_validation_executed") is False,
        "order_intent_not_validated": preflight_report.get("paper_order_intent_validated") is False,
        "order_intent_not_ready": preflight_report.get("paper_order_intent_ready") is False,
        "order_intent_not_materialized": preflight_report.get("paper_order_intent_materialized") is False,
        "order_intent_not_persisted": preflight_report.get("paper_order_intent_persisted") is False,
        "order_intent_activation_blocked": not activation_allowed,
        "order_intent_persistence_blocked": True,
        "generic_submit_execution_scaffold_ready": preflight_report.get("generic_submit_execution_scaffold_ready") is True,
        "paper_submit_execution_scaffold_ready": preflight_report.get("paper_submit_execution_scaffold_ready") is True,
        "paper_submit_candidate_not_ready": preflight_report.get("paper_submit_candidate_ready") is False,
        "generic_submit_candidate_not_ready": preflight_report.get("generic_submit_candidate_ready") is False,
        "paper_submit_execution_not_ready": preflight_report.get("paper_submit_execution_ready") is False,
        "submit_execution_blocked": preflight_report.get("generic_submit_execution_allowed") is False,
        "no_broker_call": (
            preflight_report.get("broker_submit_called_by_generic_order_intent_activation_preflight") is False
            and preflight_report.get("broker_close_called_by_generic_order_intent_activation_preflight") is False
        ),
        "no_submit_or_close_occurred": (
            preflight_report.get("orders_submitted_by_generic_order_intent_activation_preflight") == 0
            and preflight_report.get("positions_opened_by_generic_order_intent_activation_preflight") == 0
            and preflight_report.get("positions_closed_by_generic_order_intent_activation_preflight") == 0
        ),
        "no_state_mutation": (
            preflight_report.get("paper_state_modified_by_generic_order_intent_activation_preflight") is False
            and preflight_report.get("paper_status_modified_by_generic_order_intent_activation_preflight") is False
        ),
        "flat_locked_state": preflight_report.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": preflight_report.get("open_positions_after") == 0,
        "pending_orders_clear": preflight_report.get("pending_orders_after") == 0,
        "single_position_policy_ready": True,
        "paper_only_policy_ready": True,
        "no_existing_route_candidate": preflight_report.get("route_candidate_available") is False,
        "no_existing_handoff_candidate": preflight_report.get("handoff_candidate_available") is False,
        "operator_env_absent": len(active_env) == 0,
        "live_disabled": preflight_report.get("live_enabled") is False,
        "testnet_disabled": preflight_report.get("testnet_enabled") is False,
        "exchange_broker_disabled": preflight_report.get("exchange_broker_enabled") is False,
        "present_contract_fields_complete": upstream_present_fields_ok,
        "required_contract_fields_complete": upstream_required_fields_ok,
        "missing_contract_fields_empty": upstream_missing_fields_ok,
        "source_markers_present": source_markers_present,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "would_activate_order_intent_false": activation_context.get("would_activate_order_intent") is False,
        "would_materialize_order_intent_real_false": activation_context.get("would_materialize_order_intent_real") is False,
        "would_persist_order_intent_false": activation_context.get("would_persist_order_intent") is False,
        "would_call_paper_broker_submit_false": activation_context.get("would_call_paper_broker_submit") is False,
        "would_submit_false": activation_context.get("would_submit") is False,
    }

    blockers = [key for key, ok in required_readiness.items() if not ok]
    if missing_upstream_reports:
        blockers.append("missing_upstream_reports")
    if not_ready_upstream_reports:
        blockers.append("not_ready_upstream_reports")
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    ready = not blockers
    status = "PASS" if ready else "KEEP_DIAGNOSTIC"
    decision = READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION

    classification_labels = [
        "GENERIC_LSR_V2_SUPERVISED_PAPER_ORDER_INTENT_ACTIVATION",
        "CONTROLLED_ACTIVATION_GATE",
        "READ_ONLY_BY_DEFAULT",
        "NO_ORDINAL_EXPANSION",
        "NO_SUBMIT",
        "NO_CLOSE",
        "NO_BROKER_CALL",
        "NO_STATE_MUTATION",
        "NO_NETWORK_SEND",
        "NO_SCHEDULER",
        "FAIL_CLOSED",
        "OPERATOR_REARM_GATE_REQUIRED",
        "RUNTIME_VALUES_REQUIRED",
        "GENERIC_ORDER_INTENT_ACTIVATION_READY" if ready else "GENERIC_ORDER_INTENT_ACTIVATION_NOT_READY",
    ]

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": blockers,
        "required_readiness": required_readiness,
        "upstream_reports_present": [] if not preflight_report else [upstream_name],
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "generic_supervised_paper_order_intent_activation_ready": ready,
        "generic_order_intent_activation_patch_ready": ready,
        "generic_order_intent_activation_model_ready": activation_gate.get("activation_model_ready") is True,
        "generic_order_intent_activation_map_ready": ready,
        "generic_order_intent_activation_plan_ready": ready,
        "generic_order_intent_activation_contract_ready": ready,
        "generic_order_intent_activation_fail_closed_ready": ready,
        "generic_order_intent_activation_source_files_present": not missing_source_files,
        "generic_order_intent_activation_required_markers_present": not missing_source_markers,
        "order_intent_activation_diagnostic_available": ready,
        "order_intent_activation_diagnostic_count": diagnostic_count if ready else 0,
        "order_intent_activation_contract_shape_modelable": activation_gate.get("activation_model_ready") is True,
        "order_intent_activation_contract_missing_fields": _as_list(activation_map.get("missing_contract_fields", [])),
        "order_intent_activation_contract_present_fields": _as_list(activation_map.get("present_contract_fields", [])),
        "order_intent_activation_contract_required_fields": _as_list(activation_map.get("required_contract_fields", [])),
        "generic_supervised_paper_order_intent_activation_preflight_ready": (
            preflight_report.get("generic_supervised_paper_order_intent_activation_preflight_ready") is True
        ),
        "generic_order_intent_activation_preflight_ready": preflight_report.get("generic_order_intent_activation_preflight_ready") is True,
        "paper_order_intent_activation_preflight_ready": preflight_report.get("paper_order_intent_activation_preflight_ready") is True,
        "order_intent_activation_preflight_diagnostic_available": upstream_diagnostic_available,
        "order_intent_activation_preflight_diagnostic_count": diagnostic_count,
        "order_intent_activation_preflight_contract_shape_modelable": preflight_report.get("order_intent_activation_contract_shape_modelable") is True,
        "generic_supervised_paper_submit_execution_scaffold_ready": preflight_report.get("generic_supervised_paper_submit_execution_scaffold_ready") is True,
        "generic_submit_execution_scaffold_ready": preflight_report.get("generic_submit_execution_scaffold_ready") is True,
        "paper_submit_execution_scaffold_ready": preflight_report.get("paper_submit_execution_scaffold_ready") is True,
        "submit_execution_scaffold_diagnostic_available": preflight_report.get("submit_execution_scaffold_diagnostic_available") is True,
        "submit_execution_scaffold_diagnostic_count": _safe_int(preflight_report.get("submit_execution_scaffold_diagnostic_count"), 0),
        "submit_execution_scaffold_contract_shape_modelable": preflight_report.get("submit_execution_scaffold_contract_shape_modelable") is True,
        "submit_candidate_audit_diagnostic_available": preflight_report.get("submit_candidate_audit_diagnostic_available") is True,
        "submit_candidate_audit_diagnostic_count": _safe_int(preflight_report.get("submit_candidate_audit_diagnostic_count"), 0),
        "submit_candidate_contract_shape_modelable": preflight_report.get("submit_candidate_contract_shape_modelable") is True,
        "generic_submit_candidate_audit_ready": preflight_report.get("generic_submit_candidate_audit_ready") is True,
        "paper_submit_candidate_audit_ready": preflight_report.get("paper_submit_candidate_audit_ready") is True,
        "generic_submit_readiness_preflight_ready": preflight_report.get("generic_submit_readiness_preflight_ready") is True,
        "paper_submit_readiness_preflight_ready": preflight_report.get("paper_submit_readiness_preflight_ready") is True,
        "generic_order_intent_materialization_dry_run_ready": preflight_report.get("generic_order_intent_materialization_dry_run_ready") is True,
        "order_intent_materialization_dry_run_ready": preflight_report.get("order_intent_materialization_dry_run_ready") is True,
        "order_intent_validation_preflight_ready": preflight_report.get("order_intent_validation_preflight_ready") is True,
        "paper_order_intent_contract_ready": preflight_report.get("paper_order_intent_contract_ready") is True,
        "paper_order_intent_contract_validatable": preflight_report.get("paper_order_intent_contract_validatable") is True,
        "paper_order_intent_contract_validation_preflight_ready": preflight_report.get("paper_order_intent_contract_validation_preflight_ready") is True,
        "order_intent_candidate_audit_diagnostic_available": preflight_report.get("order_intent_candidate_audit_diagnostic_available") is True,
        "order_intent_candidate_audit_diagnostic_count": _safe_int(preflight_report.get("order_intent_candidate_audit_diagnostic_count"), 0),
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(preflight_report),
        "paper_order_intent_dry_run_ready": preflight_report.get("paper_order_intent_dry_run_ready") is True and ready,
        "paper_order_intent_materialization_dry_run_ready": preflight_report.get("paper_order_intent_materialization_dry_run_ready") is True,
        "paper_order_intent_materialization_simulated": preflight_report.get("paper_order_intent_materialization_simulated") is True,
        "paper_order_intent_runtime_values_present": runtime_values_present,
        "paper_order_intent_runtime_values_required_before_real_activation": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_activation_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "generic_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "generic_submit_execution_ready": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": gate_satisfied,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": False,
        "paper_broker_submit_allowed": False,
        "generic_order_intent_activation_allowed": False,
        "generic_order_intent_materialization_allowed": False,
        "generic_order_intent_persistence_allowed": False,
        "would_materialize_order_intent_dry_run": preflight_report.get("would_materialize_order_intent_dry_run") is True and ready,
        "would_validate_order_intent": False,
        "would_activate_order_intent": False,
        "would_route": False,
        "would_handoff": False,
        "would_create_order_intent": False,
        "would_materialize_order_intent_real": False,
        "would_persist_order_intent": False,
        "would_create_order": False,
        "would_prepare_submit_candidate": False,
        "would_call_paper_broker_submit": False,
        "would_submit": False,
        "paper_order_intent_activation_blocked_reason": activation_context.get(
            "blocked_reason", "order_intent_activation_blocked_by_gate_or_runtime_values"
        ),
        "paper_order_intent_materialization_blocked_reason": "order_intent_real_materialization_not_allowed_without_runtime_values_and_gate",
        "paper_order_intent_persistence_blocked_reason": "order_intent_persistence_not_allowed_activation_patch_only",
        "paper_submit_candidate_blocked_reason": "submit_candidate_materialization_not_allowed_before_real_order_intent",
        "paper_submit_execution_blocked_reason": "submit_execution_not_allowed_before_real_order_intent_and_submit_candidate",
        "generic_submit_execution_blocked_reason": "submit_execution_not_allowed_order_intent_activation_patch_only",
        "generic_order_intent_activation_map": activation_map,
        "generic_order_intent_activation_preflight_map": _as_dict(preflight_report.get("generic_order_intent_activation_preflight_map", {})),
        "generic_submit_execution_scaffold_map": _as_dict(preflight_report.get("generic_submit_execution_scaffold_map", {})),
        "blocked_until_explicit_submit_execution_patch": list(BLOCKED_UNTIL_EXPLICIT_SUBMIT_EXECUTION_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": preflight_report.get("lifecycle_state", ""),
        "fourth_trade_locked": preflight_report.get("fourth_trade_locked") is True,
        "stability_lock_active": preflight_report.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "no_route_candidate": True,
        "no_handoff_candidate": True,
        "no_order_intent_currently_available": True,
        "paper_state_status_consistency": preflight_report.get("paper_state_status_consistency") is True,
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
        "generic_order_intent_creation_allowed": False,
        "generic_order_intent_dry_run_execution_allowed": False,
        "generic_order_intent_activation_execution_allowed": False,
        "generic_submit_readiness_preflight_allowed": False,
        "generic_submit_candidate_audit_allowed": False,
        "generic_submit_candidate_creation_allowed": False,
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
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "paper_state_modified_by_generic_order_intent_activation": False,
        "paper_status_modified_by_generic_order_intent_activation": False,
        "orders_submitted_by_generic_order_intent_activation": 0,
        "positions_opened_by_generic_order_intent_activation": 0,
        "positions_closed_by_generic_order_intent_activation": 0,
        "broker_submit_called_by_generic_order_intent_activation": False,
        "broker_close_called_by_generic_order_intent_activation": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "missing_generic_order_intent_activation_source_files": missing_source_files,
        "missing_generic_order_intent_activation_source_markers": missing_source_markers,
        "source_markers_present": source_markers_present,
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "jsonl": str(data_path / settings.jsonl_name),
        "report": str(data_path / settings.report_name),
        "recommended_next_patch": "29.4.4u-29 — Generic LSR-v2 supervised paper-only submit execution",
        "next_step": "prepare_generic_supervised_paper_submit_execution_or_continue_observation",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "KEEP_DIAGNOSTIC_DECISION",
    "READY_DECISION",
    "Settings",
    "run_generic_supervised_paper_order_intent_activation",
]
