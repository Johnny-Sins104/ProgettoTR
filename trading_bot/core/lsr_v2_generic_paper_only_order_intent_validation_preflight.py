"""Generic LSR-v2 paper-only order-intent validation preflight.

29.4.4u-22 is intentionally preflight-only, read-only, and fail-closed. It
consumes the generic order-intent candidate audit from u-21 and validates the
schema/contract readiness for a future order-intent materialization path. It
never materializes or persists a real paper_order_intent, validates a live
runtime order, submits/closes an order, opens/closes a position, starts a
scheduler, calls a broker, sends Telegram messages, or mutates
paper_state/paper_status.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-22"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT_NOT_READY"

U21_READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT_READY"

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

ORDER_INTENT_VALIDATION_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_order_intent_candidate_audit",
    "verify_order_intent_candidate_audit_ready",
    "verify_diagnostic_order_intent_candidate_context",
    "verify_contract_shape_modelable",
    "verify_required_contract_fields_present",
    "verify_contract_value_validation_still_deferred",
    "verify_flat_locked_state",
    "verify_no_route_or_handoff_candidate",
    "verify_no_existing_order_intent",
    "verify_no_order_intent_materialization",
    "verify_no_order_intent_persistence",
    "verify_validation_execution_still_blocked",
    "verify_submit_execution_still_blocked",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_order_intent_validation_contract",
    "publish_generic_order_intent_validation_preflight_artifact",
)

BLOCKED_UNTIL_EXPLICIT_ORDER_INTENT_MATERIALIZATION_PATCH: Tuple[str, ...] = (
    "generic_order_intent_materialization",
    "generic_order_intent_persistence",
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
        "trading_bot/core/lsr_v2_generic_paper_only_order_intent_candidate_audit.py",
        (
            "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT",
            "order_intent_candidate_contract_shape_modelable",
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
    report_name: str = "lsr_v2_generic_paper_only_order_intent_validation_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_order_intent_validation_preflight.jsonl"
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


def _extract_upstream_model(candidate_audit: Mapping[str, Any]) -> Dict[str, Any]:
    audit_map = _as_dict(candidate_audit.get("order_intent_candidate_audit_map", {}))
    model = _as_dict(audit_map.get("upstream_paper_order_intent_model", {}))
    if model:
        return model
    handoff_map = _as_dict(candidate_audit.get("handoff_to_order_intent_dry_run_preflight_map", {}))
    return _as_dict(handoff_map.get("paper_order_intent_model", {}))


def _validation_rule_catalog() -> Dict[str, Dict[str, Any]]:
    return {
        "symbol": {
            "required": True,
            "type": "string",
            "validator": "non_empty_market_symbol",
            "runtime_value_validation_deferred": True,
        },
        "side": {
            "required": True,
            "type": "string",
            "allowed_values": ["BUY", "SELL"],
            "validator": "buy_or_sell_side",
            "runtime_value_validation_deferred": True,
        },
        "entry_price": {
            "required": True,
            "type": "number",
            "validator": "positive_finite_entry_price",
            "runtime_value_validation_deferred": True,
        },
        "stop_loss": {
            "required": True,
            "type": "number",
            "validator": "positive_finite_stop_loss_directional_to_side",
            "runtime_value_validation_deferred": True,
        },
        "take_profit": {
            "required": True,
            "type": "number",
            "validator": "positive_finite_take_profit_directional_to_side",
            "runtime_value_validation_deferred": True,
        },
        "risk_amount": {
            "required": True,
            "type": "number",
            "validator": "positive_finite_risk_amount",
            "runtime_value_validation_deferred": True,
        },
        "position_size": {
            "required": True,
            "type": "number",
            "validator": "positive_finite_position_size",
            "runtime_value_validation_deferred": True,
        },
        "max_open_positions": {
            "required": True,
            "type": "integer",
            "required_value": 1,
            "validator": "single_position_policy",
            "runtime_value_validation_deferred": False,
        },
        "paper_only": {
            "required": True,
            "type": "boolean",
            "required_value": True,
            "validator": "paper_only_true",
            "runtime_value_validation_deferred": False,
        },
    }


def _build_validation_preflight_map(candidate_audit: Mapping[str, Any]) -> Dict[str, Any]:
    model = _extract_upstream_model(candidate_audit)
    present_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in model]
    missing_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in model]
    catalog = _validation_rule_catalog()
    strict_field_results = {
        field: {
            "present": field in model,
            "rule": catalog[field],
            "current_value": model.get(field),
            "validation_executed": False,
            "validation_result": "deferred_preflight_only" if field in model else "missing",
        }
        for field in REQUIRED_ORDER_INTENT_FIELDS
    }

    max_positions_ok = model.get("max_open_positions") == 1
    paper_only_ok = model.get("paper_only") is True
    shape_ready = len(missing_fields) == 0

    return {
        "mode": "order_intent_validation_preflight_only",
        "paper_only": True,
        "preflight_only": True,
        "read_only": True,
        "fail_closed": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "source_order_intent_model": model,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": present_fields,
        "missing_contract_fields": missing_fields,
        "contract_shape_ready": shape_ready,
        "contract_value_validation_preflight_ready": shape_ready and max_positions_ok and paper_only_ok,
        "contract_runtime_value_validation_executed": False,
        "contract_runtime_value_validation_deferred": True,
        "validation_rule_catalog": catalog,
        "field_validation_preflight_results": strict_field_results,
        "single_position_policy_preflight": {
            "required_max_open_positions": 1,
            "model_max_open_positions": model.get("max_open_positions"),
            "max_open_positions_valid": max_positions_ok,
        },
        "paper_only_policy_preflight": {
            "required_paper_only": True,
            "model_paper_only": model.get("paper_only"),
            "paper_only_valid": paper_only_ok,
        },
        "directional_price_validation_preflight": {
            "side_specific_stop_loss_take_profit_validation_modelled": True,
            "runtime_price_values_required_before_execution": True,
            "runtime_price_values_present": False,
            "validation_executed": False,
        },
        "order_intent_validation_preflight_context": {
            "paper_order_intent_contract_ready": shape_ready and max_positions_ok and paper_only_ok,
            "paper_order_intent_validated": False,
            "paper_order_intent_materialized": False,
            "paper_order_intent_persisted": False,
            "paper_order_intent_ready": False,
            "would_validate_order_intent": False,
            "would_create_order_intent": False,
            "would_create_order": False,
            "would_submit": False,
            "blocked_reason": "order_intent_runtime_validation_not_allowed_preflight_only",
        },
        "required_future_controls_before_order_intent_materialization": {
            "explicit_generic_order_intent_materialization_patch_required": True,
            "explicit_generic_order_intent_persistence_patch_required": True,
            "explicit_generic_submit_preflight_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_order_intent_persistence_deferred": True,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in ORDER_INTENT_VALIDATION_PREFLIGHT_STAGES
        ],
    }


def run_generic_paper_only_order_intent_validation_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_paper_only_order_intent_candidate_audit_report.json"
    candidate_audit = _read_json(data_path / upstream_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not candidate_audit:
        missing_upstream_reports.append(upstream_name)
    elif candidate_audit.get("status") != "PASS" or candidate_audit.get("decision") != U21_READY_DECISION:
        not_ready_upstream_reports.append(upstream_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(candidate_audit, FALSE_EXECUTION_KEYS)

    diagnostic_count = _safe_int(candidate_audit.get("order_intent_candidate_audit_diagnostic_count"), 0)
    diagnostic_available = candidate_audit.get("order_intent_candidate_audit_diagnostic_available") is True and diagnostic_count > 0
    source_counts = candidate_audit.get("candidate_detection_source_counts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}

    validation_map = _build_validation_preflight_map(candidate_audit)
    required_fields = _as_list(candidate_audit.get("order_intent_candidate_contract_required_fields", []))
    present_fields = _as_list(candidate_audit.get("order_intent_candidate_contract_present_fields", []))
    missing_fields = _as_list(candidate_audit.get("order_intent_candidate_contract_missing_fields", []))
    required_set = set(REQUIRED_ORDER_INTENT_FIELDS)
    upstream_required_fields_ok = required_set.issubset(set(str(item) for item in required_fields))
    upstream_present_fields_ok = required_set.issubset(set(str(item) for item in present_fields))
    upstream_missing_fields_ok = missing_fields == []

    required_readiness = {
        "order_intent_candidate_audit_report_ready": candidate_audit.get("generic_order_intent_candidate_audit_ready") is True,
        "order_intent_candidate_audit_diagnostic_available": diagnostic_available,
        "contract_shape_modelable": candidate_audit.get("order_intent_candidate_contract_shape_modelable") is True,
        "required_contract_fields_complete": upstream_required_fields_ok,
        "present_contract_fields_complete": upstream_present_fields_ok,
        "missing_contract_fields_empty": upstream_missing_fields_ok,
        "validation_contract_shape_ready": validation_map.get("contract_shape_ready") is True,
        "validation_contract_policy_ready": validation_map.get("contract_value_validation_preflight_ready") is True,
        "flat_locked_state": candidate_audit.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": candidate_audit.get("open_positions_after") == 0,
        "pending_orders_clear": candidate_audit.get("pending_orders_after") == 0,
        "no_existing_route_candidate": candidate_audit.get("route_candidate_available") is False,
        "no_existing_handoff_candidate": candidate_audit.get("handoff_candidate_available") is False,
        "no_existing_paper_order_intent_candidate": candidate_audit.get("paper_order_intent_candidate_ready") is False,
        "no_existing_paper_order_intent": candidate_audit.get("paper_order_intent_ready") is False,
        "no_order_intent_materialized": candidate_audit.get("paper_order_intent_materialized") is False,
        "no_order_intent_persisted": candidate_audit.get("paper_order_intent_persisted") is False,
        "would_create_order_intent_false": candidate_audit.get("would_create_order_intent") is False,
        "would_create_order_false": candidate_audit.get("would_create_order") is False,
        "would_submit_false": candidate_audit.get("would_submit") is False,
        "order_intent_candidate_materialization_blocked": candidate_audit.get("generic_order_intent_candidate_materialization_allowed") is False,
        "order_intent_validation_execution_blocked": candidate_audit.get("generic_order_intent_validation_allowed") is False,
        "order_intent_creation_blocked": candidate_audit.get("generic_order_intent_creation_allowed") is False,
        "order_intent_persistence_blocked": candidate_audit.get("generic_order_intent_persistence_allowed") is False,
        "submit_execution_blocked": candidate_audit.get("generic_submit_execution_allowed") is False,
        "operator_env_absent": len(active_env) == 0,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "source_markers_present": source_markers_present,
        "no_state_mutation": candidate_audit.get("paper_state_modified_by_generic_order_intent_candidate_audit") is False
        and candidate_audit.get("paper_status_modified_by_generic_order_intent_candidate_audit") is False,
        "no_submit_or_close_occurred": candidate_audit.get("orders_submitted_by_generic_order_intent_candidate_audit") == 0
        and candidate_audit.get("positions_opened_by_generic_order_intent_candidate_audit") == 0
        and candidate_audit.get("positions_closed_by_generic_order_intent_candidate_audit") == 0,
        "live_disabled": candidate_audit.get("live_enabled") is False,
        "testnet_disabled": candidate_audit.get("testnet_enabled") is False,
        "exchange_broker_disabled": candidate_audit.get("exchange_broker_enabled") is False,
    }

    blockers = [key for key, value in required_readiness.items() if value is not True]
    if missing_upstream_reports:
        blockers.append("order_intent_candidate_audit_report_present")
    if not_ready_upstream_reports:
        blockers.append("order_intent_candidate_audit_report_ready")
    ready = not blockers and settings.fail_closed is True

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_VALIDATION_PREFLIGHT",
            "PREFLIGHT_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "DIAGNOSTIC_ORDER_INTENT_CONTRACT_VALIDATION_ONLY",
            "NO_ORDER_INTENT_MATERIALIZATION",
            "NO_ORDER_INTENT_PERSISTENCE",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_ORDER_INTENT_VALIDATION_PREFLIGHT_READY" if ready else "GENERIC_ORDER_INTENT_VALIDATION_PREFLIGHT_BLOCKED",
        ],
        "blockers": blockers,
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "upstream_reports_present": [] if not candidate_audit else [upstream_name],
        "required_readiness": required_readiness,
        "generic_order_intent_validation_preflight_ready": ready,
        "generic_order_intent_validation_preflight_plan_ready": ready,
        "generic_order_intent_validation_preflight_contract_ready": ready,
        "generic_order_intent_validation_preflight_map_ready": ready,
        "generic_order_intent_validation_preflight_fail_closed_ready": ready,
        "order_intent_candidate_audit_ready": candidate_audit.get("generic_order_intent_candidate_audit_ready") is True,
        "order_intent_candidate_audit_diagnostic_available": diagnostic_available,
        "order_intent_candidate_audit_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(candidate_audit),
        "order_intent_candidate_contract_shape_modelable": candidate_audit.get("order_intent_candidate_contract_shape_modelable") is True,
        "order_intent_candidate_contract_required_fields": required_fields,
        "order_intent_candidate_contract_present_fields": present_fields,
        "order_intent_candidate_contract_missing_fields": missing_fields,
        "paper_order_intent_contract_ready": ready,
        "paper_order_intent_contract_validatable": ready,
        "paper_order_intent_contract_validation_preflight_ready": ready,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_validated": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_dry_run_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "would_validate_order_intent": False,
        "would_route": False,
        "would_handoff": False,
        "would_create_order_intent": False,
        "would_create_order": False,
        "would_submit": False,
        "paper_order_intent_validation_blocked_reason": "order_intent_runtime_validation_not_allowed_preflight_only",
        "paper_order_intent_materialization_blocked_reason": "order_intent_materialization_not_allowed_validation_preflight_only",
        "order_intent_validation_preflight_map": validation_map,
        "order_intent_candidate_audit_map": candidate_audit.get("order_intent_candidate_audit_map", {}),
        "blocked_until_explicit_order_intent_materialization_patch": list(BLOCKED_UNTIL_EXPLICIT_ORDER_INTENT_MATERIALIZATION_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": candidate_audit.get("lifecycle_state", ""),
        "fourth_trade_locked": candidate_audit.get("fourth_trade_locked") is True,
        "stability_lock_active": candidate_audit.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "no_route_candidate": True,
        "no_handoff_candidate": True,
        "no_order_intent_currently_available": True,
        "paper_state_status_consistency": candidate_audit.get("paper_state_status_consistency") is True,
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
        "orders_submitted_by_generic_order_intent_validation_preflight": 0,
        "positions_opened_by_generic_order_intent_validation_preflight": 0,
        "positions_closed_by_generic_order_intent_validation_preflight": 0,
        "paper_state_modified_by_generic_order_intent_validation_preflight": False,
        "paper_status_modified_by_generic_order_intent_validation_preflight": False,
        "broker_submit_called_by_generic_order_intent_validation_preflight": False,
        "broker_close_called_by_generic_order_intent_validation_preflight": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "generic_order_intent_validation_preflight_source_files_present": not missing_source_files,
        "generic_order_intent_validation_preflight_required_markers_present": not missing_source_markers,
        "source_markers_present": source_markers_present,
        "missing_generic_order_intent_validation_preflight_source_files": missing_source_files,
        "missing_generic_order_intent_validation_preflight_source_markers": missing_source_markers,
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "next_step": "prepare_generic_order_intent_materialization_dry_run_or_continue_observation",
        "recommended_next_patch": "29.4.4u-23 — Generic LSR-v2 paper-only order-intent materialization dry-run",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "READY_DECISION",
    "REQUIRED_ORDER_INTENT_FIELDS",
    "Settings",
    "run_generic_paper_only_order_intent_validation_preflight",
]
