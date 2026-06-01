"""Generic LSR-v2 supervised paper terminal lifecycle handoff execution.

29.4.4u-49 consumes u-48's terminal lifecycle handoff preflight artifact and
adds the scaffold gate for a future terminal handoff execution patch. This patch
is intentionally read-only by default and fail-closed. It must not hand off the
terminal lifecycle, mutate paper_state/paper_status, send Telegram/network
messages, start a scheduler, call a broker, submit, close, or enable live/testnet
exchange access.

The expected validation state still has no complete runtime lifecycle evidence:
no submit/close receipts, no real close execution, no closed paper position, no
realized-PnL write, no final-audit/postmortem/lifecycle-completion runtime, no
state/status mutation runtime, no terminal handoff runtime, no runtime values,
and no operator gates. The scaffold therefore reports PASS/ready for modelling
while preserving every runtime block.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

PROMPT = "29.4.4u-49"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_NOT_READY"
U48_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_SCAFFOLD_READY"

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

TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_STAGES: Tuple[str, ...] = (
    "load_generic_terminal_lifecycle_handoff_execution_scaffold_report",
    "verify_terminal_lifecycle_handoff_execution_scaffold_model_ready",
    "verify_terminal_lifecycle_handoff_execution_scaffold_was_blocked",
    "verify_no_terminal_lifecycle_handoff_runtime",
    "verify_no_scheduler_completion_handoff_runtime",
    "verify_no_telegram_lifecycle_completion_send_runtime",
    "verify_no_paper_state_terminal_handoff_mutation",
    "verify_no_paper_status_terminal_handoff_mutation",
    "verify_no_real_submit_receipt",
    "verify_no_real_close_receipt",
    "verify_no_closed_position",
    "verify_no_realized_pnl_written",
    "verify_no_final_audit_runtime_execution",
    "verify_no_postmortem_runtime_execution",
    "verify_no_lifecycle_completion_audit_runtime_execution",
    "verify_no_lifecycle_state_status_completion_mutation_runtime",
    "verify_terminal_handoff_execution_requires_complete_runtime_evidence",
    "verify_terminal_lifecycle_handoff_operator_gate_required_but_absent",
    "verify_runtime_values_required_but_absent",
    "verify_paper_state_mutation_disabled",
    "verify_paper_status_mutation_disabled",
    "verify_telegram_network_send_disabled",
    "verify_scheduler_start_disabled",
    "verify_single_position_policy",
    "verify_paper_only_policy",
    "verify_flat_locked_state",
    "verify_no_orders_or_positions",
    "verify_no_broker_submit_or_close",
    "verify_live_testnet_exchange_disabled",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_terminal_lifecycle_handoff_execution_gate",
    "publish_generic_terminal_lifecycle_handoff_execution_artifact",
)

BLOCKED_UNTIL_RUNTIME_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_PREREQUISITES: Tuple[str, ...] = (
    "terminal_lifecycle_handoff_real",
    "scheduler_completion_handoff_real",
    "telegram_lifecycle_completion_send_real",
    "generic_paper_state_terminal_handoff_real",
    "generic_paper_status_terminal_handoff_real",
    "live_or_testnet_or_exchange_broker",
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_SCAFFOLD",
            "generic_terminal_lifecycle_handoff_execution_scaffold_ready",
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
    "generic_terminal_lifecycle_handoff_execution_allowed",
    "generic_terminal_lifecycle_handoff_execution_allowed",
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
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution.jsonl"
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
    return {key: value for key, value in os.environ.items() if key.startswith("LSR_V2")}


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _operator_gate(active_env: Mapping[str, str], enable_env: str, confirmation_env: str, sentinel: str) -> bool:
    return active_env.get(enable_env) == "1" and active_env.get(confirmation_env) == sentinel


def _all_false(payload: Mapping[str, Any], keys: Tuple[str, ...]) -> bool:
    return all(payload.get(key) is False for key in keys)


def _source_marker_audit(project_root: Path) -> Tuple[bool, List[str], Dict[str, List[str]]]:
    missing_files: List[str] = []
    missing_markers: Dict[str, List[str]] = {}
    for rel_path, markers in REQUIRED_SOURCE_MARKERS:
        path = project_root / rel_path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            missing_files.append(rel_path)
            continue
        absent = [marker for marker in markers if marker not in text]
        if absent:
            missing_markers[rel_path] = absent
    return not missing_files and not missing_markers, missing_files, missing_markers


def _dry_run_order_intent_payload(source_map: Mapping[str, Any]) -> Dict[str, Any]:
    payload = _as_dict(source_map.get("dry_run_order_intent_payload", {}))
    if not payload:
        payload = {field: DEFERRED_SENTINEL for field in REQUIRED_ORDER_INTENT_FIELDS}
        payload["max_open_positions"] = 1
        payload["paper_only"] = True
    payload.setdefault("dry_run_only", True)
    payload.setdefault("materialized", False)
    payload.setdefault("persisted", False)
    payload.setdefault("runtime_values_present", False)
    payload["max_open_positions"] = 1
    payload["paper_only"] = True
    return dict(payload)


def _candidate_examples(upstream: Mapping[str, Any]) -> List[Dict[str, Any]]:
    examples = upstream.get("candidate_diagnostic_examples")
    if isinstance(examples, list):
        return [example for example in examples if isinstance(example, dict)][:5]
    return []


def _contract_fields_from_source(source_gate: Mapping[str, Any]) -> Tuple[List[str], List[str], List[str]]:
    required = list(source_gate.get("required_model_fields") or REQUIRED_ORDER_INTENT_FIELDS)
    present = list(source_gate.get("present_model_fields") or REQUIRED_ORDER_INTENT_FIELDS)
    missing = [field for field in required if field not in present]
    return required, present, missing


def _build_terminal_lifecycle_handoff_execution_map(
    u48_report: Mapping[str, Any], active_env: Mapping[str, str]
) -> Dict[str, Any]:
    source_map = _as_dict(u48_report.get("generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold_map", {}))
    source_gate = _as_dict(source_map.get("terminal_lifecycle_handoff_execution_scaffold_gate_model", {}))

    u48_report_ready = u48_report.get("generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold_ready") is True
    u48_model_ready = u48_report.get("generic_terminal_lifecycle_handoff_execution_scaffold_model_ready") is True
    u48_patch_ready = u48_report.get("generic_terminal_lifecycle_handoff_execution_scaffold_patch_ready") is True
    u48_gate_model_ready = source_gate.get("terminal_lifecycle_handoff_execution_scaffold_gate_model_ready") is True
    u48_conditions_satisfied = source_gate.get("terminal_lifecycle_handoff_execution_scaffold_conditions_satisfied") is True
    u48_allowed = source_gate.get("terminal_lifecycle_handoff_execution_allowed") is True

    broker_submit_receipt = u48_report.get("broker_submit_receipt_available") is True
    broker_close_receipt = u48_report.get("broker_close_receipt_available") is True
    real_close_execution = u48_report.get("real_close_execution_available") is True
    paper_position_closed = u48_report.get("paper_position_closed") is True
    pnl_ready = u48_report.get("paper_realized_pnl_reconciliation_ready") is True
    pnl_written = u48_report.get("realized_pnl_written") is True
    final_audit_runtime = u48_report.get("final_audit_runtime_executed") is True
    postmortem_runtime = u48_report.get("postmortem_runtime_executed") is True
    lifecycle_completion_runtime = u48_report.get("lifecycle_completion_audit_runtime_executed") is True
    lifecycle_state_complete = u48_report.get("lifecycle_state_complete") is True
    paper_lifecycle_completion_ready = u48_report.get("paper_lifecycle_completion_ready") is True
    state_status_mutation_ready = u48_report.get("paper_lifecycle_state_status_completion_mutation_ready") is True
    terminal_handoff_ready = u48_report.get("paper_terminal_lifecycle_handoff_ready") is True
    runtime_values_present = source_gate.get("runtime_values_present") is True

    rearm_gate = _operator_gate(active_env, REARM_ENABLE_ENV, REARM_CONFIRMATION_ENV, REARM_CONFIRMATION_SENTINEL)
    submit_gate = _operator_gate(active_env, SUBMIT_ENABLE_ENV, SUBMIT_CONFIRMATION_ENV, SUBMIT_CONFIRMATION_SENTINEL)
    close_gate = _operator_gate(active_env, CLOSE_ENABLE_ENV, CLOSE_CONFIRMATION_ENV, CLOSE_CONFIRMATION_SENTINEL)
    pnl_gate = _operator_gate(active_env, PNL_ENABLE_ENV, PNL_CONFIRMATION_ENV, PNL_CONFIRMATION_SENTINEL)
    final_audit_gate = _operator_gate(active_env, FINAL_AUDIT_ENABLE_ENV, FINAL_AUDIT_CONFIRMATION_ENV, FINAL_AUDIT_CONFIRMATION_SENTINEL)
    postmortem_gate = _operator_gate(active_env, POSTMORTEM_ENABLE_ENV, POSTMORTEM_CONFIRMATION_ENV, POSTMORTEM_CONFIRMATION_SENTINEL)
    lifecycle_completion_gate = _operator_gate(active_env, LIFECYCLE_COMPLETION_ENABLE_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL)
    state_status_mutation_gate = _operator_gate(active_env, STATE_STATUS_MUTATION_ENABLE_ENV, STATE_STATUS_MUTATION_CONFIRMATION_ENV, STATE_STATUS_MUTATION_CONFIRMATION_SENTINEL)
    terminal_gate = _operator_gate(active_env, TERMINAL_HANDOFF_ENABLE_ENV, TERMINAL_HANDOFF_CONFIRMATION_ENV, TERMINAL_HANDOFF_CONFIRMATION_SENTINEL)

    conditions = [
        (u48_report_ready, "terminal_lifecycle_handoff_execution_scaffold_report_not_ready"),
        (u48_model_ready, "terminal_lifecycle_handoff_execution_scaffold_model_not_ready"),
        (u48_patch_ready, "terminal_lifecycle_handoff_execution_scaffold_patch_not_ready"),
        (u48_gate_model_ready, "terminal_lifecycle_handoff_execution_scaffold_gate_model_not_ready"),
        (u48_conditions_satisfied, "terminal_lifecycle_handoff_execution_scaffold_conditions_not_satisfied"),
        (u48_allowed, "terminal_lifecycle_handoff_execution_scaffold_not_allowed"),
        (broker_submit_receipt, "broker_submit_receipt_absent"),
        (broker_close_receipt, "broker_close_receipt_absent"),
        (real_close_execution, "real_close_execution_absent"),
        (paper_position_closed, "closed_position_absent"),
        (pnl_ready, "paper_realized_pnl_reconciliation_not_ready"),
        (pnl_written, "realized_pnl_not_written"),
        (final_audit_runtime, "final_audit_runtime_execution_absent"),
        (postmortem_runtime, "postmortem_runtime_execution_absent"),
        (lifecycle_completion_runtime, "lifecycle_completion_audit_runtime_execution_absent"),
        (state_status_mutation_ready, "lifecycle_state_status_completion_mutation_runtime_absent"),
        (terminal_handoff_ready, "paper_terminal_lifecycle_handoff_not_ready"),
        (paper_lifecycle_completion_ready, "paper_lifecycle_completion_not_ready"),
        (lifecycle_state_complete, "lifecycle_state_not_complete"),
        (rearm_gate, "operator_rearm_gate_not_satisfied"),
        (submit_gate, "operator_submit_gate_not_satisfied"),
        (close_gate, "operator_close_gate_not_satisfied"),
        (pnl_gate, "operator_realized_pnl_gate_not_satisfied"),
        (final_audit_gate, "operator_final_audit_gate_not_satisfied"),
        (postmortem_gate, "operator_postmortem_gate_not_satisfied"),
        (lifecycle_completion_gate, "operator_lifecycle_completion_gate_not_satisfied"),
        (state_status_mutation_gate, "operator_lifecycle_state_status_completion_mutation_gate_not_satisfied"),
        (terminal_gate, "operator_terminal_lifecycle_handoff_gate_not_satisfied"),
        (runtime_values_present, "runtime_values_absent_or_deferred"),
    ]
    blocked_reasons = [reason for passed, reason in conditions if not passed]
    scaffold_allowed = False
    scaffold_conditions_satisfied = False
    required, present, missing = _contract_fields_from_source(source_gate)

    gate_model = {
        "terminal_lifecycle_handoff_execution_gate_model_ready": True,
        "terminal_lifecycle_handoff_execution_model_ready": True,
        "terminal_lifecycle_handoff_execution_allowed": scaffold_allowed,
        "terminal_lifecycle_handoff_execution_conditions_satisfied": scaffold_conditions_satisfied,
        "terminal_lifecycle_handoff_execution_blocked_reasons": blocked_reasons,
        "terminal_lifecycle_handoff_preflight_report_required": True,
        "terminal_lifecycle_handoff_preflight_report_ready": u48_report_ready,
        "terminal_lifecycle_handoff_preflight_model_ready": u48_model_ready,
        "terminal_lifecycle_handoff_preflight_patch_ready": u48_patch_ready,
        "terminal_lifecycle_handoff_execution_scaffold_gate_model_ready": u48_gate_model_ready,
        "terminal_lifecycle_handoff_execution_scaffold_conditions_satisfied": u48_conditions_satisfied,
        "terminal_lifecycle_handoff_preflight_allowed": u48_allowed,
        "broker_submit_receipt_required": True,
        "broker_submit_receipt_available": broker_submit_receipt,
        "broker_close_receipt_required": True,
        "broker_close_receipt_available": broker_close_receipt,
        "real_close_execution_required": True,
        "real_close_execution_available": real_close_execution,
        "closed_position_required": True,
        "paper_position_closed": paper_position_closed,
        "realized_pnl_written_required": True,
        "realized_pnl_written": pnl_written,
        "paper_realized_pnl_reconciliation_ready": pnl_ready,
        "final_audit_runtime_execution_required": True,
        "final_audit_runtime_executed": final_audit_runtime,
        "postmortem_runtime_execution_required": True,
        "postmortem_runtime_executed": postmortem_runtime,
        "lifecycle_completion_audit_runtime_execution_required": True,
        "lifecycle_completion_audit_runtime_executed": lifecycle_completion_runtime,
        "lifecycle_state_status_completion_mutation_runtime_required": True,
        "paper_lifecycle_state_status_completion_mutation_ready": state_status_mutation_ready,
        "paper_terminal_lifecycle_handoff_ready": terminal_handoff_ready,
        "paper_lifecycle_completion_ready": paper_lifecycle_completion_ready,
        "lifecycle_state_complete_required": True,
        "lifecycle_state_complete": lifecycle_state_complete,
        "runtime_values_required_before_terminal_lifecycle_handoff_execution": True,
        "runtime_values_present": runtime_values_present,
        "operator_rearm_gate_required": True,
        "operator_rearm_gate_satisfied": rearm_gate,
        "operator_submit_gate_required": True,
        "operator_submit_gate_satisfied": submit_gate,
        "operator_close_gate_required": True,
        "operator_close_gate_satisfied": close_gate,
        "operator_realized_pnl_gate_required": True,
        "operator_realized_pnl_gate_satisfied": pnl_gate,
        "operator_final_audit_gate_required": True,
        "operator_final_audit_gate_satisfied": final_audit_gate,
        "operator_postmortem_gate_required": True,
        "operator_postmortem_gate_satisfied": postmortem_gate,
        "operator_lifecycle_completion_gate_required": True,
        "operator_lifecycle_completion_gate_satisfied": lifecycle_completion_gate,
        "operator_lifecycle_state_status_completion_mutation_gate_required": True,
        "operator_lifecycle_state_status_completion_mutation_gate_satisfied": state_status_mutation_gate,
        "operator_terminal_lifecycle_handoff_gate_required": True,
        "operator_terminal_lifecycle_handoff_gate_satisfied": terminal_gate,
        "operator_terminal_lifecycle_handoff_enable_env": TERMINAL_HANDOFF_ENABLE_ENV,
        "operator_terminal_lifecycle_handoff_confirmation_env": TERMINAL_HANDOFF_CONFIRMATION_ENV,
        "operator_terminal_lifecycle_handoff_confirmation_required_value": TERMINAL_HANDOFF_CONFIRMATION_SENTINEL,
        "paper_only": True,
        "paper_only_valid": True,
        "max_open_positions": 1,
        "max_open_positions_valid": True,
        "required_model_fields": required,
        "present_model_fields": present,
        "missing_model_fields": missing,
        "state_terminal_handoff_mutation_allowed": False,
        "status_terminal_handoff_mutation_allowed": False,
        "paper_state_mutation_allowed_after_terminal_handoff": False,
        "paper_status_mutation_allowed_after_terminal_handoff": False,
        "telegram_network_send_allowed_after_terminal_handoff": False,
        "scheduler_start_allowed_after_terminal_handoff": False,
    }

    context = {
        "blocked_reason": "terminal_lifecycle_handoff_execution_blocked_until_complete_runtime_lifecycle_evidence_and_explicit_execution_patch",
        "generic_terminal_lifecycle_handoff_execution_ready": True,
        "paper_terminal_lifecycle_handoff_execution_ready": True,
        "generic_terminal_lifecycle_handoff_execution_allowed": False,
        "generic_terminal_lifecycle_handoff_execution_allowed": False,
        "paper_terminal_lifecycle_handoff_ready": False,
        "broker_submit_receipt_available": broker_submit_receipt,
        "broker_close_receipt_available": broker_close_receipt,
        "real_close_execution_available": real_close_execution,
        "paper_position_closed": paper_position_closed,
        "paper_realized_pnl_reconciliation_ready": pnl_ready,
        "realized_pnl_written": pnl_written,
        "paper_final_audit_ready": u48_report.get("paper_final_audit_ready") is True,
        "paper_postmortem_ready": u48_report.get("paper_postmortem_ready") is True,
        "paper_lifecycle_completion_ready": paper_lifecycle_completion_ready,
        "paper_lifecycle_state_status_completion_mutation_ready": state_status_mutation_ready,
        "final_audit_runtime_executed": final_audit_runtime,
        "postmortem_runtime_executed": postmortem_runtime,
        "lifecycle_completion_audit_runtime_executed": lifecycle_completion_runtime,
        "lifecycle_state": u48_report.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": lifecycle_state_complete,
        "would_handoff_terminal_lifecycle": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "would_reconcile_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_run_lifecycle_completion_audit": False,
        "would_submit": False,
        "would_close": False,
    }

    return {
        "mode": "generic_supervised_paper_terminal_lifecycle_handoff_execution_controlled",
        "preflight_source": "29.4.4u-48",
        "paper_only": True,
        "read_only": True,
        "read_only_by_default": True,
        "fail_closed": True,
        "execution_enabled": False,
                "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "dry_run_order_intent_payload": _dry_run_order_intent_payload(source_map),
        "source_terminal_lifecycle_handoff_preflight_map": source_map,
        "terminal_lifecycle_handoff_execution_patch": True,
        "terminal_lifecycle_handoff_execution_gate_model": gate_model,
        "terminal_lifecycle_handoff_execution_context": context,
        "required_future_controls_before_terminal_lifecycle_handoff_execution_activation": {
            "terminal_lifecycle_handoff_preflight_report_required": True,
            "broker_submit_receipt_required_before_terminal_handoff": True,
            "broker_close_receipt_required_before_terminal_handoff": True,
            "real_close_execution_required_before_terminal_handoff": True,
            "closed_position_required_before_terminal_handoff": True,
            "realized_pnl_written_required_before_terminal_handoff": True,
            "final_audit_runtime_execution_required_before_terminal_handoff": True,
            "postmortem_runtime_execution_required_before_terminal_handoff": True,
            "lifecycle_completion_audit_runtime_execution_required_before_terminal_handoff": True,
            "lifecycle_state_status_completion_mutation_runtime_required_before_terminal_handoff": True,
            "lifecycle_state_complete_required": True,
            "runtime_value_validation_required": True,
            "runtime_values_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "generic_close_operator_gate_required": True,
            "generic_realized_pnl_operator_gate_required": True,
            "generic_final_audit_operator_gate_required": True,
            "generic_postmortem_operator_gate_required": True,
            "generic_lifecycle_completion_operator_gate_required": True,
            "generic_lifecycle_state_status_completion_mutation_operator_gate_required": True,
            "generic_terminal_lifecycle_handoff_operator_gate_required": True,
            "paper_only_required": True,
            "max_open_positions": 1,
            "paper_state_status_mutation_requires_complete_runtime_lifecycle_evidence": True,
            "telegram_network_send_requires_complete_runtime_lifecycle_evidence": True,
            "scheduler_start_requires_complete_runtime_lifecycle_evidence": True,
            "live_testnet_exchange_required_off": True,
        },
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "missing_contract_fields": [],
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_STAGES
        ],
    }


def run_generic_supervised_paper_terminal_lifecycle_handoff_execution(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    active_env = _active_lsr_env()
    upstream_path = data_path / "lsr_v2_generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold_report.json"
    upstream = _read_json(upstream_path)
    upstream_present = bool(upstream)
    upstream_ready = upstream.get("decision") == U48_READY_DECISION and upstream.get(
        "generic_supervised_paper_terminal_lifecycle_handoff_execution_scaffold_ready"
    ) is True
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)

    blockers: List[str] = []
    if not upstream_present:
        blockers.append("missing_upstream_reports")
    elif not upstream_ready:
        blockers.append("not_ready_upstream_reports")
    if not source_markers_present:
        blockers.append("missing_source_markers")

    handoff_map = _build_terminal_lifecycle_handoff_execution_map(upstream, active_env)
    gate = _as_dict(handoff_map.get("terminal_lifecycle_handoff_execution_gate_model", {}))
    ready = not blockers and bool(settings.fail_closed)

    diagnostic_count = _safe_int(upstream.get("terminal_lifecycle_handoff_preflight_diagnostic_count"), 0)
    diagnostic_available = upstream.get("terminal_lifecycle_handoff_preflight_diagnostic_available") is True
    contract_present = list(gate.get("present_model_fields", list(REQUIRED_ORDER_INTENT_FIELDS)))
    contract_required = list(gate.get("required_model_fields", list(REQUIRED_ORDER_INTENT_FIELDS)))
    contract_missing = [field for field in contract_required if field not in contract_present]
    contract_shape_modelable = not contract_missing

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "FAIL",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION",
            "TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_CONTROLLED",
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
            "GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_READY" if ready else "GENERIC_SUPERVISED_PAPER_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_NOT_READY",
        ],
        "blockers": blockers,
        "generic_supervised_paper_terminal_lifecycle_handoff_execution_ready": ready,
        "generic_terminal_lifecycle_handoff_execution_ready": ready,
        "generic_terminal_lifecycle_handoff_execution_model_ready": ready,
        "generic_terminal_lifecycle_handoff_execution_patch_ready": ready,
        "paper_terminal_lifecycle_handoff_execution_ready": ready,
        "terminal_lifecycle_handoff_execution_diagnostic_available": diagnostic_available if ready else False,
        "terminal_lifecycle_handoff_execution_diagnostic_count": diagnostic_count if ready else 0,
        "terminal_lifecycle_handoff_preflight_diagnostic_available": diagnostic_available,
        "terminal_lifecycle_handoff_preflight_diagnostic_count": diagnostic_count,
        "terminal_lifecycle_handoff_execution_contract_required_fields": contract_required,
        "terminal_lifecycle_handoff_execution_contract_present_fields": contract_present,
        "terminal_lifecycle_handoff_execution_contract_missing_fields": contract_missing,
        "terminal_lifecycle_handoff_execution_contract_shape_modelable": contract_shape_modelable,
        "generic_supervised_paper_terminal_lifecycle_handoff_execution_map": handoff_map,
        "blocked_until_runtime_terminal_lifecycle_handoff_execution_prerequisites": list(
            BLOCKED_UNTIL_RUNTIME_TERMINAL_LIFECYCLE_HANDOFF_EXECUTION_PREREQUISITES
        ),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": not active_env,
        "source_markers_present": source_markers_present,
        "missing_source_files": missing_source_files,
        "missing_source_markers": missing_source_markers,
        "candidate_detection_source_counts": _as_dict(upstream.get("candidate_detection_source_counts", {})),
        "candidate_diagnostic_examples": _candidate_examples(upstream),
        "read_only_verified": True,
        "no_ordinal_expansion": True,
        "u48_terminal_lifecycle_handoff_preflight_report_present": upstream_present,
        "u48_terminal_lifecycle_handoff_preflight_ready": upstream_ready,
        "generic_terminal_lifecycle_handoff_execution_scaffold_ready": upstream.get("generic_terminal_lifecycle_handoff_execution_scaffold_ready") is True,
        "generic_terminal_lifecycle_handoff_execution_scaffold_model_ready": upstream.get("generic_terminal_lifecycle_handoff_execution_scaffold_model_ready") is True,
        "generic_terminal_lifecycle_handoff_execution_scaffold_patch_ready": upstream.get("generic_terminal_lifecycle_handoff_execution_scaffold_patch_ready") is True,
        "broker_submit_receipt_available": upstream.get("broker_submit_receipt_available") is True,
        "broker_close_receipt_available": upstream.get("broker_close_receipt_available") is True,
        "real_close_execution_available": upstream.get("real_close_execution_available") is True,
        "paper_position_closed": upstream.get("paper_position_closed") is True,
        "paper_realized_pnl_reconciliation_ready": upstream.get("paper_realized_pnl_reconciliation_ready") is True,
        "realized_pnl_written": upstream.get("realized_pnl_written") is True,
        "paper_final_audit_ready": upstream.get("paper_final_audit_ready") is True,
        "paper_postmortem_ready": upstream.get("paper_postmortem_ready") is True,
        "paper_lifecycle_completion_ready": upstream.get("paper_lifecycle_completion_ready") is True,
        "paper_lifecycle_state_status_completion_mutation_ready": upstream.get("paper_lifecycle_state_status_completion_mutation_ready") is True,
        "paper_terminal_lifecycle_handoff_ready": False,
        "final_audit_runtime_executed": upstream.get("final_audit_runtime_executed") is True,
        "postmortem_runtime_executed": upstream.get("postmortem_runtime_executed") is True,
        "lifecycle_completion_audit_runtime_executed": upstream.get("lifecycle_completion_audit_runtime_executed") is True,
        "generic_lifecycle_completion_audit_allowed": False,
        "generic_lifecycle_completion_audit_execution_allowed": False,
        "generic_lifecycle_state_status_completion_mutation_allowed": False,
        "generic_lifecycle_state_status_completion_mutation_execution_allowed": False,
        "generic_terminal_lifecycle_handoff_execution_allowed": False,
        "generic_terminal_lifecycle_handoff_execution_allowed": False,
        "generic_lifecycle_state_completion_mutation_allowed": False,
        "generic_lifecycle_status_completion_mutation_allowed": False,
        "generic_paper_state_completion_mutation_allowed": False,
        "generic_paper_status_completion_mutation_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "would_handoff_terminal_lifecycle": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "would_submit": False,
        "would_close": False,
        "would_reconcile_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_run_lifecycle_completion_audit": False,
        "orders_submitted_by_generic_terminal_lifecycle_handoff_execution": 0,
        "orders_closed_by_generic_terminal_lifecycle_handoff_execution": 0,
        "positions_opened_by_generic_terminal_lifecycle_handoff_execution": 0,
        "positions_closed_by_generic_terminal_lifecycle_handoff_execution": 0,
        "paper_state_modified_by_generic_terminal_lifecycle_handoff_execution": False,
        "paper_status_modified_by_generic_terminal_lifecycle_handoff_execution": False,
        "telegram_sent_by_generic_terminal_lifecycle_handoff_execution": False,
        "scheduler_started_by_generic_terminal_lifecycle_handoff_execution": False,
        "broker_submit_allowed": False,
        "broker_close_allowed": False,
        "broker_submit_called_by_upstream_terminal_lifecycle_handoff_preflight": upstream.get("broker_submit_called_by_generic_terminal_lifecycle_handoff_preflight") is True,
        "broker_close_called_by_upstream_terminal_lifecycle_handoff_preflight": upstream.get("broker_close_called_by_generic_terminal_lifecycle_handoff_preflight") is True,
        "broker_submit_called_by_generic_terminal_lifecycle_handoff_execution": False,
        "broker_close_called_by_generic_terminal_lifecycle_handoff_execution": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "lifecycle_state": upstream.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": upstream.get("lifecycle_state_complete") is True,
        "fourth_trade_locked": upstream.get("fourth_trade_locked", True) is True,
        "fifth_trade_patch_allowed": False,
        "eighth_trade_patch_allowed": False,
        "stability_lock_active": upstream.get("stability_lock_active", True) is True,
    }
    for key in FALSE_EXECUTION_KEYS:
        report.setdefault(key, False)
    report["all_execution_flags_fail_closed"] = _all_false(report, FALSE_EXECUTION_KEYS)

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "READY_DECISION",
    "Settings",
    "run_generic_supervised_paper_terminal_lifecycle_handoff_execution",
]
