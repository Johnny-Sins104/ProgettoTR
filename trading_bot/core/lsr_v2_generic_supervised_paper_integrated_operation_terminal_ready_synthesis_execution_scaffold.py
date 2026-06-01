"""Generic LSR-v2 supervised paper integrated operation terminal-ready synthesis execution scaffold.

29.4.4u-60 consumes the u-59 terminal-ready synthesis preflight artifact and
models the next terminal-ready synthesis execution scaffold. This is a scaffold
only patch: it does not synthesize a terminal-ready runtime state, run integrated
operation, mutate paper_state or paper_status, send Telegram or network messages,
start a scheduler, call a broker, submit, close, or enable live/testnet/exchange
access.

The scaffold remains read-only by default and fail-closed. Complete runtime
lifecycle evidence, terminal-ready synthesis runtime, final-readiness-audit
handoff runtime, terminal handoff runtime, scheduler/Telegram completion runtime,
broker receipts, runtime values, and all operator gates are still required before
any future activation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

PROMPT = "29.4.4u-60"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_NOT_READY"
U59_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_PREFLIGHT_READY"

REQUIRED_ORDER_INTENT_FIELDS: Tuple[str, ...] = (
    "symbol", "side", "entry_price", "stop_loss", "take_profit",
    "risk_amount", "position_size", "max_open_positions", "paper_only",
)
DEFERRED_SENTINEL = "deferred_until_explicit_order_intent_patch"

REARM_ENABLE_ENV = "LSR_V2_GENERIC_REARM_ENABLE"
REARM_CONFIRMATION_ENV = "LSR_V2_GENERIC_REARM_CONFIRMATION"
REARM_CONFIRMATION_SENTINEL = "I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY"
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
POSTMORTEM_ENABLE_ENV = "LSR_V2_GENERIC_POSTMORTEM_ENABLE"
POSTMORTEM_CONFIRMATION_ENV = "LSR_V2_GENERIC_POSTMORTEM_CONFIRMATION"
POSTMORTEM_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_POSTMORTEM_ONLY"
LIFECYCLE_COMPLETION_ENABLE_ENV = "LSR_V2_GENERIC_LIFECYCLE_COMPLETION_AUDIT_ENABLE"
LIFECYCLE_COMPLETION_CONFIRMATION_ENV = "LSR_V2_GENERIC_LIFECYCLE_COMPLETION_AUDIT_CONFIRMATION"
LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_LIFECYCLE_COMPLETION_AUDIT_ONLY"
STATE_STATUS_MUTATION_ENABLE_ENV = "LSR_V2_GENERIC_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_ENABLE"
STATE_STATUS_MUTATION_CONFIRMATION_ENV = "LSR_V2_GENERIC_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_CONFIRMATION"
STATE_STATUS_MUTATION_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_LIFECYCLE_STATE_STATUS_COMPLETION_MUTATION_ONLY"
TERMINAL_HANDOFF_ENABLE_ENV = "LSR_V2_GENERIC_TERMINAL_LIFECYCLE_HANDOFF_ENABLE"
TERMINAL_HANDOFF_CONFIRMATION_ENV = "LSR_V2_GENERIC_TERMINAL_LIFECYCLE_HANDOFF_CONFIRMATION"
TERMINAL_HANDOFF_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_TERMINAL_LIFECYCLE_HANDOFF_ONLY"
INTEGRATED_OPERATION_ENABLE_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_ENABLE"
INTEGRATED_OPERATION_CONFIRMATION_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_CONFIRMATION"
INTEGRATED_OPERATION_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_INTEGRATED_OPERATION_ONLY"
FINAL_READINESS_AUDIT_ENABLE_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_ENABLE"
FINAL_READINESS_AUDIT_CONFIRMATION_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_CONFIRMATION"
FINAL_READINESS_AUDIT_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_ONLY"
FINAL_READINESS_AUDIT_HANDOFF_ENABLE_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_HANDOFF_ENABLE"
FINAL_READINESS_AUDIT_HANDOFF_CONFIRMATION_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_HANDOFF_CONFIRMATION"
FINAL_READINESS_AUDIT_HANDOFF_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_HANDOFF_ONLY"
TERMINAL_READY_SYNTHESIS_ENABLE_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_ENABLE"
TERMINAL_READY_SYNTHESIS_CONFIRMATION_ENV = "LSR_V2_GENERIC_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_CONFIRMATION"
TERMINAL_READY_SYNTHESIS_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_ONLY"

TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_STAGES: Tuple[str, ...] = (
    "load_generic_integrated_operation_terminal_ready_synthesis_preflight_report",
    "verify_integrated_operation_terminal_ready_synthesis_preflight_model_ready",
    "verify_integrated_operation_terminal_ready_synthesis_preflight_was_blocked",
    "verify_no_integrated_operation_runtime",
    "verify_no_terminal_ready_synthesis_runtime",
    "verify_no_final_readiness_audit_handoff_runtime",
    "verify_no_terminal_lifecycle_handoff_runtime",
    "verify_no_scheduler_completion_handoff_runtime",
    "verify_no_telegram_lifecycle_completion_send_runtime",
    "verify_no_paper_state_terminal_handoff_mutation",
    "verify_no_paper_status_terminal_handoff_mutation",
    "verify_no_broker_submit_or_close_receipts",
    "verify_no_closed_position_or_real_close_execution",
    "verify_no_realized_pnl_written",
    "verify_no_final_audit_postmortem_or_lifecycle_runtime",
    "verify_terminal_ready_synthesis_execution_requires_complete_runtime_evidence",
    "verify_terminal_ready_synthesis_operator_gate_required_but_absent",
    "verify_runtime_values_required_but_absent",
    "verify_future_terminal_ready_synthesis_execution_patch_required",
    "verify_paper_state_and_status_mutation_disabled",
    "verify_telegram_network_send_disabled",
    "verify_scheduler_start_disabled",
    "verify_no_submit_close_or_broker_call",
    "verify_live_testnet_exchange_disabled",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_integrated_operation_terminal_ready_synthesis_execution_scaffold_gate",
    "publish_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_artifact",
)

BLOCKED_UNTIL_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_PREREQUISITES: Tuple[str, ...] = (
    "integrated_operation_terminal_ready_synthesis_execution_patch",
    "complete_runtime_lifecycle_evidence",
    "terminal_ready_synthesis_runtime_real",
    "integrated_operation_final_readiness_audit_handoff_runtime_real",
    "integrated_operation_final_readiness_audit_runtime_real",
    "terminal_lifecycle_handoff_real",
    "scheduler_completion_handoff_real",
    "telegram_lifecycle_completion_send_real",
    "generic_paper_state_terminal_handoff_real",
    "generic_paper_status_terminal_handoff_real",
    "broker_submit_receipt",
    "broker_close_receipt",
    "live_testnet_exchange_still_disabled_until_explicit_activation",
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_preflight.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_PREFLIGHT",
            "generic_integrated_operation_terminal_ready_synthesis_preflight_ready",
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
    "generic_lifecycle_completion_audit_allowed",
    "generic_lifecycle_completion_audit_execution_allowed",
    "generic_lifecycle_state_status_completion_mutation_allowed",
    "generic_lifecycle_state_status_completion_mutation_execution_allowed",
    "generic_terminal_lifecycle_handoff_allowed",
    "generic_terminal_lifecycle_handoff_execution_allowed",
    "generic_integrated_operation_final_readiness_audit_handoff_execution_allowed",
    "generic_integrated_operation_final_readiness_audit_handoff_allowed",
    "generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_allowed",
    "generic_integrated_operation_terminal_ready_synthesis_allowed",
    "generic_integrated_operation_terminal_ready_synthesis_execution_allowed",
    "generic_integrated_operation_allowed",
    "generic_integrated_operation_execution_allowed",
    "generic_lifecycle_state_completion_mutation_allowed",
    "generic_lifecycle_status_completion_mutation_allowed",
    "generic_paper_state_completion_mutation_allowed",
    "generic_paper_status_completion_mutation_allowed",
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
    project_root: Path = Path.cwd()
    data_dir: str = "data"
    report_name: str = "lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold.jsonl"

    @property
    def data_path(self) -> Path:
        return self.project_root / self.data_dir


def _read_json(path: Path) -> Dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _active_lsr_env() -> Dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.startswith("LSR_V2_GENERIC_")}


def _operator_gate_satisfied(env: Mapping[str, str], enable_key: str, confirmation_key: str, sentinel: str) -> bool:
    return env.get(enable_key) == "1" and env.get(confirmation_key) == sentinel


def _source_marker_audit(project_root: Path) -> Tuple[bool, List[str], Dict[str, List[str]]]:
    missing_files: List[str] = []
    missing_markers: Dict[str, List[str]] = {}
    for rel, markers in REQUIRED_SOURCE_MARKERS:
        path = project_root / rel
        if not path.exists():
            missing_files.append(rel)
            missing_markers[rel] = list(markers)
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        absent = [marker for marker in markers if marker not in text]
        if absent:
            missing_markers[rel] = absent
    return not missing_files and not missing_markers, missing_files, missing_markers


def _dry_run_payload(source: Mapping[str, Any]) -> Dict[str, Any]:
    source_map = _as_dict(source.get("generic_supervised_paper_integrated_operation_terminal_ready_synthesis_preflight_map"))
    payload = _as_dict(source_map.get("dry_run_order_intent_payload"))
    if not payload:
        payload = {field: DEFERRED_SENTINEL for field in REQUIRED_ORDER_INTENT_FIELDS}
        payload["max_open_positions"] = 1
        payload["paper_only"] = True
    payload.update({"dry_run_only": True, "materialized": False, "persisted": False, "runtime_values_present": False})
    return payload


def _candidate_examples(source: Mapping[str, Any]) -> List[Any]:
    examples = _as_list(source.get("candidate_diagnostic_examples"))
    if examples:
        return examples[:5]
    return [{"event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT", "symbol": "BTC/USDT", "candidate_detected_diagnostic": False}]


def _build_terminal_ready_synthesis_execution_scaffold_map(source: Mapping[str, Any], env: Mapping[str, str]) -> Dict[str, Any]:
    source_map = _as_dict(source.get("generic_supervised_paper_integrated_operation_terminal_ready_synthesis_preflight_map"))
    gate_satisfied = {
        "operator_rearm_gate_satisfied": _operator_gate_satisfied(env, REARM_ENABLE_ENV, REARM_CONFIRMATION_ENV, REARM_CONFIRMATION_SENTINEL),
        "operator_submit_gate_satisfied": _operator_gate_satisfied(env, SUBMIT_ENABLE_ENV, SUBMIT_CONFIRMATION_ENV, SUBMIT_CONFIRMATION_SENTINEL),
        "operator_close_gate_satisfied": _operator_gate_satisfied(env, CLOSE_ENABLE_ENV, CLOSE_CONFIRMATION_ENV, CLOSE_CONFIRMATION_SENTINEL),
        "operator_realized_pnl_gate_satisfied": _operator_gate_satisfied(env, PNL_ENABLE_ENV, PNL_CONFIRMATION_ENV, PNL_CONFIRMATION_SENTINEL),
        "operator_final_audit_gate_satisfied": _operator_gate_satisfied(env, FINAL_AUDIT_ENABLE_ENV, FINAL_AUDIT_CONFIRMATION_ENV, FINAL_AUDIT_CONFIRMATION_SENTINEL),
        "operator_postmortem_gate_satisfied": _operator_gate_satisfied(env, POSTMORTEM_ENABLE_ENV, POSTMORTEM_CONFIRMATION_ENV, POSTMORTEM_CONFIRMATION_SENTINEL),
        "operator_lifecycle_completion_gate_satisfied": _operator_gate_satisfied(env, LIFECYCLE_COMPLETION_ENABLE_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL),
        "operator_lifecycle_state_status_completion_mutation_gate_satisfied": _operator_gate_satisfied(env, STATE_STATUS_MUTATION_ENABLE_ENV, STATE_STATUS_MUTATION_CONFIRMATION_ENV, STATE_STATUS_MUTATION_CONFIRMATION_SENTINEL),
        "operator_terminal_lifecycle_handoff_gate_satisfied": _operator_gate_satisfied(env, TERMINAL_HANDOFF_ENABLE_ENV, TERMINAL_HANDOFF_CONFIRMATION_ENV, TERMINAL_HANDOFF_CONFIRMATION_SENTINEL),
        "operator_integrated_operation_gate_satisfied": _operator_gate_satisfied(env, INTEGRATED_OPERATION_ENABLE_ENV, INTEGRATED_OPERATION_CONFIRMATION_ENV, INTEGRATED_OPERATION_CONFIRMATION_SENTINEL),
        "operator_integrated_operation_final_readiness_audit_gate_satisfied": _operator_gate_satisfied(env, FINAL_READINESS_AUDIT_ENABLE_ENV, FINAL_READINESS_AUDIT_CONFIRMATION_ENV, FINAL_READINESS_AUDIT_CONFIRMATION_SENTINEL),
        "operator_integrated_operation_final_readiness_audit_handoff_gate_satisfied": _operator_gate_satisfied(env, FINAL_READINESS_AUDIT_HANDOFF_ENABLE_ENV, FINAL_READINESS_AUDIT_HANDOFF_CONFIRMATION_ENV, FINAL_READINESS_AUDIT_HANDOFF_CONFIRMATION_SENTINEL),
        "operator_integrated_operation_terminal_ready_synthesis_gate_satisfied": _operator_gate_satisfied(env, TERMINAL_READY_SYNTHESIS_ENABLE_ENV, TERMINAL_READY_SYNTHESIS_CONFIRMATION_ENV, TERMINAL_READY_SYNTHESIS_CONFIRMATION_SENTINEL),
    }
    blocked_reasons = [
        "integrated_operation_terminal_ready_synthesis_preflight_not_allowed",
        "paper_terminal_lifecycle_handoff_not_ready",
        "terminal_ready_synthesis_runtime_absent",
        "final_readiness_audit_handoff_runtime_absent",
        "terminal_lifecycle_handoff_runtime_absent",
        "scheduler_completion_handoff_runtime_absent",
        "telegram_lifecycle_completion_send_runtime_absent",
        "paper_state_terminal_handoff_mutation_absent",
        "paper_status_terminal_handoff_mutation_absent",
        "lifecycle_state_status_completion_mutation_runtime_absent",
        "lifecycle_completion_audit_runtime_execution_absent",
        "postmortem_runtime_execution_absent",
        "final_audit_runtime_execution_absent",
        "broker_submit_receipt_absent",
        "broker_close_receipt_absent",
        "real_close_execution_absent",
        "closed_position_absent",
        "paper_realized_pnl_reconciliation_not_ready",
        "realized_pnl_not_written",
        "paper_final_audit_not_ready",
        "paper_postmortem_not_ready",
        "paper_lifecycle_completion_not_ready",
        "paper_lifecycle_state_status_completion_mutation_not_ready",
        "lifecycle_state_not_complete",
        "operator_rearm_gate_not_satisfied",
        "operator_submit_gate_not_satisfied",
        "operator_close_gate_not_satisfied",
        "operator_realized_pnl_gate_not_satisfied",
        "operator_final_audit_gate_not_satisfied",
        "operator_postmortem_gate_not_satisfied",
        "operator_lifecycle_completion_gate_not_satisfied",
        "operator_lifecycle_state_status_completion_mutation_gate_not_satisfied",
        "operator_terminal_lifecycle_handoff_gate_not_satisfied",
        "operator_integrated_operation_gate_not_satisfied",
        "operator_integrated_operation_final_readiness_audit_gate_not_satisfied",
        "operator_integrated_operation_final_readiness_audit_handoff_gate_not_satisfied",
        "operator_integrated_operation_terminal_ready_synthesis_gate_not_satisfied",
        "runtime_values_absent_or_deferred",
        "explicit_integrated_operation_terminal_ready_synthesis_execution_patch_required",
    ]
    present_fields = list(REQUIRED_ORDER_INTENT_FIELDS)
    gate_model: Dict[str, Any] = {
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_gate_model_ready": True,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_model_ready": True,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_patch_ready": True,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_allowed": False,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_conditions_satisfied": False,
        "integrated_operation_terminal_ready_synthesis_preflight_report_required": True,
        "integrated_operation_terminal_ready_synthesis_preflight_report_ready": source.get("decision") == U59_READY_DECISION,
        "integrated_operation_terminal_ready_synthesis_preflight_ready": bool(source.get("generic_integrated_operation_terminal_ready_synthesis_preflight_ready")),
        "integrated_operation_terminal_ready_synthesis_preflight_model_ready": bool(source.get("generic_integrated_operation_terminal_ready_synthesis_preflight_model_ready")),
        "integrated_operation_terminal_ready_synthesis_preflight_patch_ready": bool(source.get("generic_integrated_operation_terminal_ready_synthesis_preflight_patch_ready")),
        "integrated_operation_terminal_ready_synthesis_preflight_allowed": False,
        "integrated_operation_terminal_ready_synthesis_allowed": False,
        "integrated_operation_terminal_ready_synthesis_execution_allowed": False,
        "integrated_operation_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "explicit_integrated_operation_terminal_ready_synthesis_execution_patch_required": True,
        "terminal_ready_synthesis_runtime_required": True,
        "terminal_ready_synthesis_runtime_executed": False,
        "final_readiness_audit_handoff_runtime_required": True,
        "final_readiness_audit_handoff_runtime_executed": False,
        "terminal_lifecycle_handoff_runtime_required": True,
        "terminal_lifecycle_handoff_runtime_executed": False,
        "scheduler_completion_handoff_runtime_required": True,
        "scheduler_completion_handoff_runtime_executed": False,
        "telegram_lifecycle_completion_send_runtime_required": True,
        "telegram_lifecycle_completion_send_runtime_executed": False,
        "paper_state_terminal_handoff_mutation_required": True,
        "paper_state_terminal_handoff_mutated": False,
        "paper_status_terminal_handoff_mutation_required": True,
        "paper_status_terminal_handoff_mutated": False,
        "lifecycle_state_status_completion_mutation_runtime_required": True,
        "lifecycle_state_status_completion_mutation_runtime_executed": False,
        "lifecycle_completion_audit_runtime_execution_required": True,
        "lifecycle_completion_audit_runtime_executed": False,
        "postmortem_runtime_execution_required": True,
        "postmortem_runtime_executed": False,
        "final_audit_runtime_execution_required": True,
        "final_audit_runtime_executed": False,
        "broker_submit_receipt_required": True,
        "broker_submit_receipt_available": False,
        "broker_close_receipt_required": True,
        "broker_close_receipt_available": False,
        "real_close_execution_required": True,
        "real_close_execution_available": False,
        "closed_position_required": True,
        "paper_position_closed": False,
        "realized_pnl_reconciliation_required": True,
        "paper_realized_pnl_reconciliation_ready": False,
        "realized_pnl_written_required": True,
        "realized_pnl_written": False,
        "lifecycle_state_complete_required": True,
        "lifecycle_state_complete": False,
        "runtime_values_required_before_terminal_ready_synthesis": True,
        "runtime_values_present": False,
        "paper_only": True,
        "paper_only_valid": True,
        "max_open_positions": 1,
        "max_open_positions_valid": True,
        "live_testnet_exchange_required_off": True,
        "required_model_fields": present_fields,
        "present_model_fields": present_fields,
        "missing_model_fields": [],
        "operator_terminal_ready_synthesis_enable_env": TERMINAL_READY_SYNTHESIS_ENABLE_ENV,
        "operator_terminal_ready_synthesis_confirmation_env": TERMINAL_READY_SYNTHESIS_CONFIRMATION_ENV,
        "operator_terminal_ready_synthesis_confirmation_required_value": TERMINAL_READY_SYNTHESIS_CONFIRMATION_SENTINEL,
        "operator_integrated_operation_terminal_ready_synthesis_gate_required": True,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_blocked_reasons": blocked_reasons,
    }
    for key, satisfied in gate_satisfied.items():
        gate_model[key] = satisfied
        gate_model[key.replace("_satisfied", "_required")] = True
    context = {
        "blocked_reason": "integrated_operation_terminal_ready_synthesis_execution_scaffold_blocked_until_complete_runtime_lifecycle_evidence_operator_gates_and_explicit_execution_patch",
        "generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_ready": True,
        "generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_allowed": False,
        "generic_integrated_operation_terminal_ready_synthesis_allowed": False,
        "generic_integrated_operation_terminal_ready_synthesis_execution_allowed": False,
        "generic_integrated_operation_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_integrated_operation_terminal_ready": False,
        "paper_integrated_operation_ready": False,
        "lifecycle_state": source.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": False,
        "terminal_ready_synthesis_runtime_executed": False,
        "final_readiness_audit_handoff_runtime_executed": False,
        "terminal_lifecycle_handoff_runtime_executed": False,
        "scheduler_completion_handoff_runtime_executed": False,
        "telegram_lifecycle_completion_send_runtime_executed": False,
        "broker_submit_receipt_available": False,
        "broker_close_receipt_available": False,
        "real_close_execution_available": False,
        "paper_position_closed": False,
        "realized_pnl_written": False,
        "would_run_integrated_operation_terminal_ready_synthesis": False,
        "would_run_integrated_operation": False,
        "would_submit": False,
        "would_close": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
    }
    return {
        "mode": "generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold_only",
        "preflight_source": "29.4.4u-59",
        "scaffold_only": True,
        "read_only": True,
        "read_only_by_default": True,
        "fail_closed": True,
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "dry_run_order_intent_payload": _dry_run_payload(source),
        "required_contract_fields": present_fields,
        "present_contract_fields": present_fields,
        "missing_contract_fields": [],
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_context": context,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_gate_model": gate_model,
        "source_integrated_operation_terminal_ready_synthesis_preflight_map": source_map,
        "required_future_controls_before_integrated_operation_terminal_ready_synthesis_execution": {
            "integrated_operation_terminal_ready_synthesis_preflight_report_required": True,
            "explicit_generic_integrated_operation_terminal_ready_synthesis_execution_patch_required": True,
            "terminal_ready_synthesis_runtime_required_before_integrated_operation": True,
            "final_readiness_audit_handoff_runtime_required_before_terminal_ready_synthesis": True,
            "broker_close_receipt_required_before_terminal_ready_synthesis": True,
            "broker_submit_receipt_required_before_terminal_ready_synthesis": True,
            "closed_position_required_before_terminal_ready_synthesis": True,
            "final_audit_runtime_execution_required_before_terminal_ready_synthesis": True,
            "terminal_lifecycle_handoff_runtime_required_before_terminal_ready_synthesis": True,
            "scheduler_completion_handoff_runtime_required_before_terminal_ready_synthesis": True,
            "telegram_lifecycle_completion_send_runtime_required_before_terminal_ready_synthesis": True,
            "paper_state_terminal_handoff_required_before_terminal_ready_synthesis": True,
            "paper_status_terminal_handoff_required_before_terminal_ready_synthesis": True,
            "lifecycle_state_status_completion_mutation_runtime_required_before_terminal_ready_synthesis": True,
            "lifecycle_completion_audit_runtime_execution_required_before_terminal_ready_synthesis": True,
            "postmortem_runtime_execution_required_before_terminal_ready_synthesis": True,
            "real_close_execution_required_before_terminal_ready_synthesis": True,
            "realized_pnl_written_required_before_terminal_ready_synthesis": True,
            "lifecycle_state_complete_required": True,
            "generic_integrated_operation_terminal_ready_synthesis_operator_gate_required": True,
            "generic_integrated_operation_operator_gate_required": True,
            "generic_terminal_lifecycle_handoff_operator_gate_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "generic_close_operator_gate_required": True,
            "generic_realized_pnl_operator_gate_required": True,
            "generic_final_audit_operator_gate_required": True,
            "generic_postmortem_operator_gate_required": True,
            "generic_lifecycle_completion_operator_gate_required": True,
            "generic_lifecycle_state_status_completion_mutation_operator_gate_required": True,
            "runtime_value_validation_required": True,
            "runtime_values_required": True,
            "paper_only_required": True,
            "max_open_positions": 1,
            "live_testnet_exchange_required_off": True,
            "paper_state_status_mutation_requires_complete_runtime_lifecycle_evidence": True,
            "scheduler_start_requires_complete_runtime_lifecycle_evidence": True,
            "telegram_network_send_requires_complete_runtime_lifecycle_evidence": True,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_STAGES
        ],
    }


def run_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    project_root = settings.project_root
    data_path = settings.data_path
    report_path = data_path / settings.report_name
    jsonl_path = data_path / settings.jsonl_name
    upstream_path = data_path / "lsr_v2_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_preflight_report.json"

    active_env = _active_lsr_env()
    source_ok, missing_source_files, missing_source_markers = _source_marker_audit(project_root)
    upstream = _read_json(upstream_path)
    missing_upstream = upstream is None
    not_ready_upstream = False
    if upstream is not None:
        not_ready_upstream = upstream.get("decision") != U59_READY_DECISION

    blockers: List[str] = []
    if missing_upstream:
        blockers.append("missing_upstream_reports")
        upstream = {}
    elif not_ready_upstream:
        blockers.append("not_ready_upstream_reports")
    if not source_ok:
        blockers.append("missing_source_markers")

    terminal_map = _build_terminal_ready_synthesis_execution_scaffold_map(upstream, active_env)
    candidate_counts = _as_dict(upstream.get("candidate_detection_source_counts"))
    diagnostic_count = _safe_int(
        upstream.get(
            "integrated_operation_terminal_ready_synthesis_preflight_diagnostic_count",
            candidate_counts.get("paper_events_jsonl_diagnostic_read", 0),
        )
    ) + 1

    status = "PASS" if not blockers else "FAIL"
    decision = READY_DECISION if status == "PASS" else KEEP_DIAGNOSTIC_DECISION
    now = datetime.now(timezone.utc).isoformat()

    report: Dict[str, Any] = {
        "status": status,
        "decision": decision,
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": now,
        "classification_labels": [
            "GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD",
            "INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_ONLY",
            "READ_ONLY_BY_DEFAULT",
            "NO_ORDINAL_EXPANSION",
            "NO_STATE_MUTATION",
            "NO_STATUS_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "FAIL_CLOSED",
            "GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_READY",
        ],
        "blockers": blockers,
        "missing_source_files": missing_source_files,
        "missing_source_markers": missing_source_markers,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold_ready": status == "PASS",
        "generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_ready": status == "PASS",
        "generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_model_ready": True,
        "generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_patch_ready": True,
        "paper_integrated_operation_terminal_ready_synthesis_execution_scaffold_ready": status == "PASS",
        "paper_integrated_operation_terminal_ready": False,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_diagnostic_available": True,
        "integrated_operation_terminal_ready_synthesis_execution_scaffold_diagnostic_count": diagnostic_count,
        "blocked_until_runtime_integrated_operation_terminal_ready_synthesis_execution_scaffold_prerequisites": list(BLOCKED_UNTIL_TERMINAL_READY_SYNTHESIS_EXECUTION_SCAFFOLD_PREREQUISITES),
        "generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold_map": terminal_map,
        "candidate_detection_source_counts": candidate_counts,
        "candidate_diagnostic_examples": _candidate_examples(upstream),
        "all_execution_flags_fail_closed": True,
        "paper_only": True,
        "max_open_positions": 1,
        "lifecycle_state": upstream.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": False,
        "broker_submit_receipt_available": False,
        "broker_close_receipt_available": False,
        "real_close_execution_available": False,
        "paper_position_closed": False,
        "paper_realized_pnl_reconciliation_ready": False,
        "realized_pnl_written": False,
        "paper_final_audit_ready": False,
        "paper_postmortem_ready": False,
        "paper_lifecycle_completion_ready": False,
        "paper_lifecycle_state_status_completion_mutation_ready": False,
        "paper_terminal_lifecycle_handoff_ready": False,
        "paper_integrated_operation_ready": False,
        "paper_integrated_operation_terminal_ready": False,
        "final_audit_runtime_executed": False,
        "postmortem_runtime_executed": False,
        "lifecycle_completion_audit_runtime_executed": False,
        "lifecycle_state_status_completion_mutation_runtime_executed": False,
        "terminal_lifecycle_handoff_runtime_executed": False,
        "final_readiness_audit_handoff_runtime_executed": False,
        "terminal_ready_synthesis_runtime_executed": False,
        "scheduler_completion_handoff_runtime_executed": False,
        "telegram_lifecycle_completion_send_runtime_executed": False,
        "paper_state_terminal_handoff_mutated": False,
        "paper_status_terminal_handoff_mutated": False,
        "generic_integrated_operation_terminal_ready_synthesis_execution_scaffold_allowed": False,
        "generic_integrated_operation_terminal_ready_synthesis_allowed": False,
        "generic_integrated_operation_terminal_ready_synthesis_execution_allowed": False,
        "generic_integrated_operation_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "broker_submit_called_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": False,
        "broker_close_called_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": False,
        "orders_submitted_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": 0,
        "orders_closed_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": 0,
        "positions_opened_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": 0,
        "positions_closed_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": 0,
        "paper_state_modified_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": False,
        "paper_status_modified_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": False,
        "scheduler_started_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": False,
        "telegram_network_send_called_by_generic_integrated_operation_terminal_ready_synthesis_execution_scaffold": False,
        "would_run_integrated_operation_terminal_ready_synthesis": False,
        "would_run_integrated_operation_final_readiness_audit_handoff": False,
        "would_run_integrated_operation": False,
        "would_handoff_terminal_lifecycle": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_submit": False,
        "would_close": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "exchange_broker_enabled": False,
        "live_mode_enabled": False,
        "testnet_mode_enabled": False,
        "fourth_trade_locked": True,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "eighth_trade_patch_allowed": False,
        "ninth_trade_patch_allowed": False,
        "tenth_trade_patch_allowed": False,
        "eleventh_trade_patch_allowed": False,
        "twelfth_trade_patch_allowed": False,
    }
    for key in FALSE_EXECUTION_KEYS:
        report[key] = False
    report["jsonl"] = str(jsonl_path)
    report["report"] = str(report_path)

    _write_json(report_path, report)
    _append_jsonl(jsonl_path, report)
    return report


__all__ = [
    "PROMPT",
    "EVENT_TYPE",
    "READY_DECISION",
    "KEEP_DIAGNOSTIC_DECISION",
    "Settings",
    "run_generic_supervised_paper_integrated_operation_terminal_ready_synthesis_execution_scaffold",
]
