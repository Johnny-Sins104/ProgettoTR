"""Generic LSR-v2 supervised paper final-audit execution gate.

29.4.4u-37 is a controlled paper-only final-audit execution gate/model. It
consumes u-36's final-audit execution scaffold artifact and evaluates the full
set of conditions that would be required before a real paper final audit could
ever be attempted after a supervised paper trade lifecycle.

The expected validation state still has no submit receipt, no close receipt, no
real close execution, no closed paper position, no realized-PnL reconciliation,
no realized-PnL write, no runtime values, and no operator gates. Therefore this
patch must return a PASS/ready diagnostic for the final-audit execution model
while keeping actual final audit execution, postmortem, broker calls, state
mutation, Telegram/network sending, scheduler startup, and live/testnet/exchange
access blocked.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-37"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_NOT_READY"
U36_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_SCAFFOLD_READY"

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
CLOSE_ENABLE_ENV = "LSR_V2_GENERIC_CLOSE_ENABLE"
CLOSE_CONFIRMATION_ENV = "LSR_V2_GENERIC_CLOSE_CONFIRMATION"
CLOSE_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_CLOSE_ONLY"
PNL_ENABLE_ENV = "LSR_V2_GENERIC_REALIZED_PNL_RECONCILIATION_ENABLE"
PNL_CONFIRMATION_ENV = "LSR_V2_GENERIC_REALIZED_PNL_RECONCILIATION_CONFIRMATION"
PNL_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_REALIZED_PNL_RECONCILIATION_ONLY"
FINAL_AUDIT_ENABLE_ENV = "LSR_V2_GENERIC_FINAL_AUDIT_ENABLE"
FINAL_AUDIT_CONFIRMATION_ENV = "LSR_V2_GENERIC_FINAL_AUDIT_CONFIRMATION"
FINAL_AUDIT_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_FINAL_AUDIT_ONLY"

FINAL_AUDIT_EXECUTION_STAGES: Tuple[str, ...] = (
    "load_generic_final_audit_execution_scaffold",
    "verify_final_audit_execution_scaffold_ready",
    "verify_final_audit_execution_scaffold_was_blocked",
    "verify_no_broker_submit_receipt",
    "verify_no_broker_close_receipt",
    "verify_no_real_close_execution_available",
    "verify_no_closed_position_available",
    "verify_no_realized_pnl_written",
    "verify_final_audit_requires_realized_pnl_close_receipt_and_gates",
    "verify_final_audit_operator_gate_required_but_absent",
    "verify_runtime_values_required_but_absent",
    "verify_final_audit_execution_guard_disabled",
    "verify_postmortem_guard_disabled",
    "verify_state_mutation_disabled",
    "verify_single_position_policy",
    "verify_paper_only_policy",
    "verify_flat_locked_state",
    "verify_no_orders_or_positions",
    "verify_no_broker_submit_or_close",
    "verify_no_network_scheduler_or_state_mutation",
    "verify_live_testnet_exchange_disabled",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_supervised_paper_final_audit_execution_gate",
    "publish_generic_supervised_paper_final_audit_execution_artifact",
)

BLOCKED_UNTIL_POSTMORTEM_PATCH: Tuple[str, ...] = (
    "generic_postmortem_execution",
    "generic_paper_state_mutation",
    "generic_paper_status_mutation",
    "telegram_network_send",
    "scheduler_start",
    "live_or_testnet_or_exchange_broker",
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_final_audit_execution_scaffold.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_SCAFFOLD",
            "generic_final_audit_execution_scaffold_ready",
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
    "generic_order_intent_activation_allowed",
    "generic_order_intent_activation_execution_allowed",
    "generic_order_intent_persistence_allowed",
    "generic_submit_readiness_preflight_allowed",
    "generic_submit_candidate_audit_allowed",
    "generic_submit_candidate_creation_allowed",
    "generic_submit_execution_allowed",
    "generic_open_position_monitor_allowed",
    "generic_close_execution_allowed",
    "generic_realized_pnl_reconciliation_allowed",
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
    report_name: str = "lsr_v2_generic_supervised_paper_final_audit_execution_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_final_audit_execution.jsonl"
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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _all_false(payload: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return all(payload.get(key) is False for key in keys)


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


def _candidate_examples(payload: Mapping[str, Any], limit: int = 5) -> List[Any]:
    examples = payload.get("candidate_diagnostic_examples", [])
    return examples[:limit] if isinstance(examples, list) else []


def _runtime_values_present(payload: Mapping[str, Any]) -> bool:
    for field in REQUIRED_ORDER_INTENT_FIELDS:
        value = payload.get(field)
        if value in (None, "", DEFERRED_SENTINEL):
            return False
    return True


def _dry_run_payload(scaffold_report: Mapping[str, Any]) -> Dict[str, Any]:
    scaffold_map = _as_dict(scaffold_report.get("generic_supervised_paper_final_audit_execution_scaffold_map", {}))
    payload = _as_dict(scaffold_map.get("dry_run_order_intent_payload", {}))
    if payload:
        return payload
    preflight_map = _as_dict(scaffold_report.get("generic_supervised_paper_final_audit_preflight_map", {}))
    return _as_dict(preflight_map.get("dry_run_order_intent_payload", {}))


def _operator_gate_states(active_env: Mapping[str, str]) -> Dict[str, bool]:
    return {
        "rearm": active_env.get(REARM_ENABLE_ENV) == "1"
        and active_env.get(REARM_CONFIRMATION_ENV) == REARM_CONFIRMATION_SENTINEL
        and active_env.get(REARM_MAX_POSITIONS_ENV) == "1",
        "submit": active_env.get(SUBMIT_ENABLE_ENV) == "1"
        and active_env.get(SUBMIT_CONFIRMATION_ENV) == SUBMIT_CONFIRMATION_SENTINEL,
        "close": active_env.get(CLOSE_ENABLE_ENV) == "1"
        and active_env.get(CLOSE_CONFIRMATION_ENV) == CLOSE_CONFIRMATION_SENTINEL,
        "pnl": active_env.get(PNL_ENABLE_ENV) == "1"
        and active_env.get(PNL_CONFIRMATION_ENV) == PNL_CONFIRMATION_SENTINEL,
        "final_audit": active_env.get(FINAL_AUDIT_ENABLE_ENV) == "1"
        and active_env.get(FINAL_AUDIT_CONFIRMATION_ENV) == FINAL_AUDIT_CONFIRMATION_SENTINEL,
    }


def _build_final_audit_execution_map(scaffold_report: Mapping[str, Any], active_env: Mapping[str, str]) -> Dict[str, Any]:
    source_map = _as_dict(scaffold_report.get("generic_supervised_paper_final_audit_execution_scaffold_map", {}))
    source_gate = _as_dict(source_map.get("final_audit_execution_scaffold_gate_model", {}))
    payload = _dry_run_payload(scaffold_report)
    present_contract_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload]
    missing_contract_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in payload]

    runtime_values_present = _runtime_values_present(payload) and source_gate.get("runtime_values_present") is True
    gate_states = _operator_gate_states(active_env)
    scaffold_ready = scaffold_report.get("generic_final_audit_execution_scaffold_ready") is True
    scaffold_model_ready = scaffold_report.get("generic_final_audit_execution_scaffold_model_ready") is True
    broker_submit_receipt_available = scaffold_report.get("broker_submit_receipt_available") is True
    broker_close_receipt_available = scaffold_report.get("broker_close_receipt_available") is True
    real_close_execution_available = scaffold_report.get("real_close_execution_available") is True
    paper_position_closed = scaffold_report.get("paper_position_closed") is True
    paper_realized_pnl_reconciliation_ready = scaffold_report.get("paper_realized_pnl_reconciliation_ready") is True
    realized_pnl_written = scaffold_report.get("realized_pnl_written") is True or scaffold_report.get("would_write_realized_pnl") is True

    final_audit_execution_conditions_satisfied = all(
        [
            scaffold_ready,
            scaffold_model_ready,
            broker_submit_receipt_available,
            broker_close_receipt_available,
            real_close_execution_available,
            paper_position_closed,
            paper_realized_pnl_reconciliation_ready,
            realized_pnl_written,
            gate_states["rearm"],
            gate_states["submit"],
            gate_states["close"],
            gate_states["pnl"],
            gate_states["final_audit"],
            runtime_values_present,
            not missing_contract_fields,
            payload.get("paper_only") is True,
            payload.get("max_open_positions") == 1,
        ]
    )

    blocked_reasons: List[str] = []
    if not scaffold_ready:
        blocked_reasons.append("final_audit_execution_scaffold_not_ready")
    if not scaffold_model_ready:
        blocked_reasons.append("final_audit_execution_scaffold_model_not_ready")
    if not broker_submit_receipt_available:
        blocked_reasons.append("broker_submit_receipt_absent")
    if not broker_close_receipt_available:
        blocked_reasons.append("broker_close_receipt_absent")
    if not real_close_execution_available:
        blocked_reasons.append("real_close_execution_absent")
    if not paper_position_closed:
        blocked_reasons.append("closed_position_absent")
    if not paper_realized_pnl_reconciliation_ready:
        blocked_reasons.append("paper_realized_pnl_reconciliation_not_ready")
    if not realized_pnl_written:
        blocked_reasons.append("realized_pnl_not_written")
    if not gate_states["rearm"]:
        blocked_reasons.append("operator_rearm_gate_not_satisfied")
    if not gate_states["submit"]:
        blocked_reasons.append("operator_submit_gate_not_satisfied")
    if not gate_states["close"]:
        blocked_reasons.append("operator_close_gate_not_satisfied")
    if not gate_states["pnl"]:
        blocked_reasons.append("operator_realized_pnl_gate_not_satisfied")
    if not gate_states["final_audit"]:
        blocked_reasons.append("operator_final_audit_gate_not_satisfied")
    if not runtime_values_present:
        blocked_reasons.append("runtime_values_absent_or_deferred")
    if missing_contract_fields:
        blocked_reasons.append("contract_fields_missing")
    if payload.get("paper_only") is not True:
        blocked_reasons.append("paper_only_policy_not_satisfied")
    if payload.get("max_open_positions") != 1:
        blocked_reasons.append("max_open_positions_policy_not_satisfied")

    gate_model = {
        "final_audit_execution_model_ready": True,
        "final_audit_execution_gate_model_ready": True,
        "final_audit_execution_conditions_satisfied": final_audit_execution_conditions_satisfied,
        "final_audit_execution_allowed": final_audit_execution_conditions_satisfied,
        "final_audit_execution_blocked_reasons": blocked_reasons,
        "final_audit_execution_scaffold_required": True,
        "final_audit_execution_scaffold_ready": scaffold_ready,
        "final_audit_execution_scaffold_model_ready": scaffold_model_ready,
        "broker_submit_receipt_required": True,
        "broker_submit_receipt_available": broker_submit_receipt_available,
        "broker_close_receipt_required": True,
        "broker_close_receipt_available": broker_close_receipt_available,
        "real_close_execution_required": True,
        "real_close_execution_available": real_close_execution_available,
        "closed_position_required": True,
        "paper_position_closed": paper_position_closed,
        "realized_pnl_reconciliation_required": True,
        "paper_realized_pnl_reconciliation_ready": paper_realized_pnl_reconciliation_ready,
        "realized_pnl_written_required": True,
        "realized_pnl_written": realized_pnl_written,
        "operator_rearm_gate_required": True,
        "operator_rearm_gate_satisfied": gate_states["rearm"],
        "operator_submit_gate_required": True,
        "operator_submit_gate_satisfied": gate_states["submit"],
        "operator_close_gate_required": True,
        "operator_close_gate_satisfied": gate_states["close"],
        "operator_realized_pnl_gate_required": True,
        "operator_realized_pnl_gate_satisfied": gate_states["pnl"],
        "operator_final_audit_gate_required": True,
        "operator_final_audit_gate_satisfied": gate_states["final_audit"],
        "operator_final_audit_enable_env": FINAL_AUDIT_ENABLE_ENV,
        "operator_final_audit_confirmation_env": FINAL_AUDIT_CONFIRMATION_ENV,
        "operator_final_audit_confirmation_required_value": FINAL_AUDIT_CONFIRMATION_SENTINEL,
        "runtime_values_required_before_final_audit_execution": True,
        "runtime_values_present": runtime_values_present,
        "paper_only": payload.get("paper_only") is True,
        "paper_only_valid": payload.get("paper_only") is True,
        "max_open_positions": payload.get("max_open_positions"),
        "max_open_positions_valid": payload.get("max_open_positions") == 1,
        "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_model_fields": present_contract_fields,
        "missing_model_fields": missing_contract_fields,
        "postmortem_execution_allowed": False,
        "state_mutation_allowed_after_final_audit": False,
    }

    context = {
        "blocked_reason": "final_audit_execution_blocked_by_missing_realized_pnl_close_receipt_or_gates",
        "generic_supervised_paper_final_audit_execution_ready": True,
        "generic_final_audit_execution_model_ready": True,
        "paper_final_audit_execution_model_ready": True,
        "final_audit_execution_scaffold_ready": scaffold_ready,
        "generic_final_audit_execution_allowed": final_audit_execution_conditions_satisfied,
        "paper_final_audit_ready": False,
        "broker_submit_receipt_available": broker_submit_receipt_available,
        "broker_close_receipt_available": broker_close_receipt_available,
        "real_close_execution_available": real_close_execution_available,
        "paper_position_closed": paper_position_closed,
        "paper_realized_pnl_reconciliation_ready": paper_realized_pnl_reconciliation_ready,
        "realized_pnl_written": realized_pnl_written,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_reconcile_realized_pnl": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_submit": False,
        "would_close": False,
    }

    return {
        "mode": "generic_supervised_paper_final_audit_execution_controlled",
        "preflight_source": "29.4.4u-36",
        "final_audit_execution_patch": True,
        "read_only": True,
        "read_only_by_default": True,
        "fail_closed": True,
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "dry_run_order_intent_payload": payload,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": present_contract_fields,
        "missing_contract_fields": missing_contract_fields,
        "final_audit_execution_gate_model": gate_model,
        "final_audit_execution_context": context,
        "source_final_audit_execution_scaffold_map": source_map,
        "required_future_controls_before_postmortem": {
            "explicit_generic_postmortem_patch_required": True,
            "final_audit_execution_report_required": True,
            "broker_close_receipt_required_before_postmortem": True,
            "realized_pnl_written_required_before_postmortem": True,
            "generic_final_audit_operator_gate_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_only_required": True,
            "max_open_positions": 1,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in FINAL_AUDIT_EXECUTION_STAGES
        ],
    }


def run_generic_supervised_paper_final_audit_execution(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_supervised_paper_final_audit_execution_scaffold_report.json"
    scaffold_report = _read_json(data_path / upstream_name)
    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)

    missing_upstream_reports = [] if scaffold_report else [upstream_name]
    upstream_ready = (
        scaffold_report.get("decision") == U36_READY_DECISION
        and scaffold_report.get("generic_supervised_paper_final_audit_execution_scaffold_ready") is True
    )
    not_ready_upstream_reports = [] if not scaffold_report or upstream_ready else [upstream_name]

    execution_map = _build_final_audit_execution_map(scaffold_report, active_env)
    gate_model = _as_dict(execution_map.get("final_audit_execution_gate_model", {}))
    context = _as_dict(execution_map.get("final_audit_execution_context", {}))
    payload = _as_dict(execution_map.get("dry_run_order_intent_payload", {}))
    present_fields_ok = _as_list(execution_map.get("present_contract_fields", [])) == list(REQUIRED_ORDER_INTENT_FIELDS)
    required_fields_ok = _as_list(execution_map.get("required_contract_fields", [])) == list(REQUIRED_ORDER_INTENT_FIELDS)
    missing_fields_ok = _as_list(execution_map.get("missing_contract_fields", [])) == []

    diagnostic_count = _safe_int(scaffold_report.get("final_audit_execution_scaffold_diagnostic_count"), 0)
    source_counts = _as_dict(scaffold_report.get("candidate_detection_source_counts", {}))
    if not diagnostic_count:
        diagnostic_count = sum(_safe_int(v) for v in source_counts.values())
    diagnostic_available = scaffold_report.get("final_audit_execution_scaffold_diagnostic_available") is True or diagnostic_count > 0

    required_readiness = {
        "u36_final_audit_execution_scaffold_report_present": bool(scaffold_report),
        "u36_final_audit_execution_scaffold_ready": upstream_ready,
        "source_markers_present": source_markers_present,
        "final_audit_execution_model_ready": gate_model.get("final_audit_execution_model_ready") is True,
        "final_audit_execution_gate_model_ready": gate_model.get("final_audit_execution_gate_model_ready") is True,
        "present_contract_fields_complete": present_fields_ok,
        "required_contract_fields_complete": required_fields_ok,
        "missing_contract_fields_empty": missing_fields_ok,
        "paper_only_policy_ready": payload.get("paper_only") is True,
        "single_position_policy_ready": payload.get("max_open_positions") == 1,
        "execution_disabled": execution_map.get("execution_enabled") is False,
        "mutation_disabled": execution_map.get("mutation_enabled") is False,
        "broker_disabled": execution_map.get("broker_submit_enabled") is False and execution_map.get("broker_close_enabled") is False,
        "scheduler_disabled": execution_map.get("scheduler_enabled") is False,
        "telegram_network_disabled": execution_map.get("telegram_network_send_enabled") is False,
        "live_testnet_exchange_disabled": True,
        "execution_flags_fail_closed": _all_false(scaffold_report, FALSE_EXECUTION_KEYS),
        "final_audit_currently_blocked": gate_model.get("final_audit_execution_conditions_satisfied") is False,
        "would_run_final_audit_false": context.get("would_run_final_audit") is False,
        "would_run_postmortem_false": context.get("would_run_postmortem") is False,
    }

    blockers = [key for key, ok in required_readiness.items() if not ok]
    if missing_upstream_reports:
        blockers.append("missing_upstream_reports")
    if not_ready_upstream_reports:
        blockers.append("not_ready_upstream_reports")
    if not source_markers_present and "missing_source_markers" not in blockers:
        blockers.append("missing_source_markers")
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    ready = not blockers and settings.fail_closed is True
    status = "PASS" if ready else "KEEP_DIAGNOSTIC"
    decision = READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION

    gate_states = _operator_gate_states(active_env)
    classification_labels = [
        "GENERIC_LSR_V2_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION",
        "FINAL_AUDIT_EXECUTION_CONTROLLED",
        "READ_ONLY_BY_DEFAULT",
        "NO_ORDINAL_EXPANSION",
        "NO_FINAL_AUDIT_RUNTIME_EXECUTION",
        "NO_POSTMORTEM",
        "NO_SUBMIT",
        "NO_CLOSE",
        "NO_BROKER_CALL",
        "NO_STATE_MUTATION",
        "NO_NETWORK_SEND",
        "NO_SCHEDULER",
        "FAIL_CLOSED",
        "GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_READY" if ready else "GENERIC_SUPERVISED_PAPER_FINAL_AUDIT_EXECUTION_NOT_READY",
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
        "upstream_reports_present": [] if not scaffold_report else [upstream_name],
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "generic_supervised_paper_final_audit_execution_ready": ready,
        "generic_final_audit_execution_model_ready": gate_model.get("final_audit_execution_model_ready") is True,
        "generic_final_audit_execution_patch_ready": ready,
        "generic_final_audit_execution_gate_model_ready": gate_model.get("final_audit_execution_gate_model_ready") is True,
        "paper_final_audit_execution_model_ready": gate_model.get("final_audit_execution_model_ready") is True,
        "final_audit_execution_diagnostic_available": ready and diagnostic_available,
        "final_audit_execution_diagnostic_count": diagnostic_count if ready else 0,
        "final_audit_execution_contract_shape_modelable": gate_model.get("final_audit_execution_model_ready") is True,
        "final_audit_execution_contract_missing_fields": _as_list(execution_map.get("missing_contract_fields", [])),
        "final_audit_execution_contract_present_fields": _as_list(execution_map.get("present_contract_fields", [])),
        "final_audit_execution_contract_required_fields": _as_list(execution_map.get("required_contract_fields", [])),
        "generic_supervised_paper_final_audit_execution_scaffold_ready": scaffold_report.get("generic_supervised_paper_final_audit_execution_scaffold_ready") is True,
        "generic_final_audit_execution_scaffold_ready": scaffold_report.get("generic_final_audit_execution_scaffold_ready") is True,
        "generic_final_audit_execution_scaffold_model_ready": scaffold_report.get("generic_final_audit_execution_scaffold_model_ready") is True,
        "generic_final_audit_execution_scaffold_patch_ready": scaffold_report.get("generic_final_audit_execution_scaffold_patch_ready") is True,
        "paper_final_audit_execution_scaffold_ready": scaffold_report.get("paper_final_audit_execution_scaffold_ready") is True,
        "final_audit_execution_scaffold_diagnostic_available": diagnostic_available,
        "final_audit_execution_scaffold_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(scaffold_report),
        "broker_submit_receipt_available": scaffold_report.get("broker_submit_receipt_available") is True,
        "broker_close_receipt_available": scaffold_report.get("broker_close_receipt_available") is True,
        "real_close_execution_available": scaffold_report.get("real_close_execution_available") is True,
        "paper_position_closed": scaffold_report.get("paper_position_closed") is True,
        "realized_pnl_written": scaffold_report.get("realized_pnl_written") is True or scaffold_report.get("would_write_realized_pnl") is True,
        "paper_position_open": False,
        "paper_open_position_available": False,
        "paper_open_position_monitor_ready": False,
        "close_trigger_available": False,
        "paper_order_intent_runtime_values_present": gate_model.get("runtime_values_present") is True,
        "paper_order_intent_runtime_values_required_before_final_audit_execution": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "paper_close_execution_ready": False,
        "paper_realized_pnl_reconciliation_ready": False,
        "paper_final_audit_ready": False,
        "generic_submit_execution_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_realized_pnl_reconciliation_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "broker_close_allowed": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": gate_states["rearm"],
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": gate_states["submit"],
        "generic_close_operator_gate_required": True,
        "generic_close_operator_gate_satisfied": gate_states["close"],
        "generic_realized_pnl_operator_gate_required": True,
        "generic_realized_pnl_operator_gate_satisfied": gate_states["pnl"],
        "generic_final_audit_operator_gate_required": True,
        "generic_final_audit_operator_gate_satisfied": gate_states["final_audit"],
        "would_reconcile_realized_pnl": False,
        "would_write_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_submit": False,
        "would_close": False,
        "would_call_paper_broker_submit": False,
        "would_call_paper_broker_close": False,
        "generic_supervised_paper_final_audit_execution_map": execution_map,
        "generic_supervised_paper_final_audit_execution_scaffold_map": _as_dict(scaffold_report.get("generic_supervised_paper_final_audit_execution_scaffold_map", {})),
        "generic_supervised_paper_final_audit_preflight_map": _as_dict(scaffold_report.get("generic_supervised_paper_final_audit_preflight_map", {})),
        "generic_supervised_paper_realized_pnl_reconciliation_preflight_map": _as_dict(scaffold_report.get("generic_supervised_paper_realized_pnl_reconciliation_preflight_map", {})),
        "generic_supervised_paper_close_execution_map": _as_dict(scaffold_report.get("generic_supervised_paper_close_execution_map", {})),
        "blocked_until_postmortem_patch": list(BLOCKED_UNTIL_POSTMORTEM_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": scaffold_report.get("lifecycle_state", ""),
        "fourth_trade_locked": scaffold_report.get("fourth_trade_locked") is True,
        "stability_lock_active": scaffold_report.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "paper_state_status_consistency": scaffold_report.get("paper_state_status_consistency") is True,
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
        "generic_order_intent_activation_allowed": False,
        "generic_order_intent_activation_execution_allowed": False,
        "generic_order_intent_materialization_allowed": False,
        "generic_order_intent_persistence_allowed": False,
        "generic_submit_readiness_preflight_allowed": False,
        "generic_submit_candidate_audit_allowed": False,
        "generic_submit_candidate_creation_allowed": False,
        "generic_open_position_monitor_allowed": False,
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
        "eighth_trade_patch_allowed": False,
        "ninth_trade_patch_allowed": False,
        "paper_state_modified_by_generic_final_audit_execution": False,
        "paper_status_modified_by_generic_final_audit_execution": False,
        "orders_submitted_by_generic_final_audit_execution": 0,
        "positions_opened_by_generic_final_audit_execution": 0,
        "positions_closed_by_generic_final_audit_execution": 0,
        "broker_submit_called_by_generic_final_audit_execution": False,
        "broker_close_called_by_generic_final_audit_execution": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "missing_generic_final_audit_execution_source_files": missing_source_files,
        "missing_generic_final_audit_execution_source_markers": missing_source_markers,
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
        "recommended_next_patch": "29.4.4u-38 — Generic LSR-v2 supervised paper postmortem preflight",
        "next_step": "prepare_postmortem_preflight_or_continue_observation",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "FALSE_EXECUTION_KEYS",
    "KEEP_DIAGNOSTIC_DECISION",
    "READY_DECISION",
    "Settings",
    "run_generic_supervised_paper_final_audit_execution",
]
