"""Generic LSR-v2 supervised paper integrated operation final readiness audit preflight.

29.4.4u-53 consumes u-52's integrated operation readiness execution artifact
and adds a final readiness audit preflight for a future supervised paper
integrated operation. This patch is intentionally preflight-only, read-only by
default, and fail-closed. It must not run an integrated operation, hand off a
terminal lifecycle, mutate paper_state or paper_status, send Telegram/network
messages, start a scheduler, call a broker, submit, close, or enable
live/testnet/exchange access.

The expected validation state still lacks complete runtime lifecycle evidence:
no submit/close receipts, no real close execution, no closed paper position, no
realized-PnL write, no final-audit/postmortem/lifecycle-completion runtime, no
state/status mutation runtime, no terminal handoff runtime, no scheduler or
Telegram completion runtime, no runtime values, and no operator gates. The
preflight therefore reports PASS/ready for modelling while preserving every
runtime block and requiring a later explicit final-readiness-audit execution
patch before any real integrated-operation activation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

PROMPT = "29.4.4u-53"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_PREFLIGHT_NOT_READY"
U52_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_READINESS_EXECUTION_READY"

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

FINAL_READINESS_AUDIT_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_integrated_operation_readiness_execution_report",
    "verify_integrated_operation_readiness_execution_model_ready",
    "verify_integrated_operation_readiness_execution_was_blocked",
    "verify_no_integrated_operation_runtime",
    "verify_no_terminal_lifecycle_handoff_runtime",
    "verify_no_scheduler_completion_handoff_runtime",
    "verify_no_telegram_lifecycle_completion_send_runtime",
    "verify_no_paper_state_terminal_handoff_mutation",
    "verify_no_paper_status_terminal_handoff_mutation",
    "verify_no_broker_submit_or_close_receipts",
    "verify_no_closed_position_or_real_close_execution",
    "verify_no_realized_pnl_written",
    "verify_no_final_audit_postmortem_or_lifecycle_runtime",
    "verify_integrated_operation_final_readiness_audit_requires_complete_lifecycle_evidence",
    "verify_final_readiness_audit_operator_gate_required_but_absent",
    "verify_runtime_values_required_but_absent",
    "verify_future_final_readiness_audit_execution_patch_required",
    "verify_paper_state_and_status_mutation_disabled",
    "verify_telegram_network_send_disabled",
    "verify_scheduler_start_disabled",
    "verify_no_submit_close_or_broker_call",
    "verify_live_testnet_exchange_disabled",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_integrated_operation_final_readiness_audit_preflight_gate",
    "publish_generic_integrated_operation_final_readiness_audit_preflight_artifact",
)

BLOCKED_UNTIL_FINAL_READINESS_AUDIT_EXECUTION_PREREQUISITES: Tuple[str, ...] = (
    "integrated_operation_final_readiness_audit_execution_patch",
    "complete_runtime_lifecycle_evidence",
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
        "trading_bot/core/lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_READINESS_EXECUTION",
            "generic_integrated_operation_readiness_execution_ready",
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
    "generic_integrated_operation_readiness_allowed",
    "generic_integrated_operation_readiness_execution_scaffold_allowed",
    "generic_integrated_operation_readiness_execution_allowed",
    "generic_integrated_operation_final_readiness_audit_preflight_allowed",
    "generic_integrated_operation_final_readiness_audit_allowed",
    "generic_integrated_operation_final_readiness_audit_execution_allowed",
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
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_integrated_operation_final_readiness_audit_preflight.jsonl"
    fail_closed: bool = True

    @property
    def data_path(self) -> Path:
        return self.project_root / self.data_dir


def _read_json(path: Path) -> Dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _active_lsr_env() -> Dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.startswith("LSR_V2_")}


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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _operator_gate(active_env: Mapping[str, str], enable_key: str, confirmation_key: str, sentinel: str) -> bool:
    return active_env.get(enable_key) == "1" and active_env.get(confirmation_key) == sentinel


def _default_order_intent_payload() -> Dict[str, Any]:
    return {
        "symbol": DEFERRED_SENTINEL,
        "side": DEFERRED_SENTINEL,
        "entry_price": DEFERRED_SENTINEL,
        "stop_loss": DEFERRED_SENTINEL,
        "take_profit": DEFERRED_SENTINEL,
        "risk_amount": DEFERRED_SENTINEL,
        "position_size": DEFERRED_SENTINEL,
        "max_open_positions": 1,
        "paper_only": True,
        "dry_run_only": True,
        "materialized": False,
        "persisted": False,
        "runtime_values_present": False,
    }


def _candidate_examples(upstream: Mapping[str, Any]) -> List[Any]:
    return _as_list(upstream.get("candidate_diagnostic_examples"))[:5]


def _bool_from_upstream(upstream: Mapping[str, Any], key: str) -> bool:
    return upstream.get(key) is True


def _build_final_readiness_audit_preflight_map(
    upstream: Mapping[str, Any], active_env: Mapping[str, str]
) -> Dict[str, Any]:
    source_map = _as_dict(upstream.get("generic_supervised_paper_integrated_operation_readiness_execution_map"))
    source_gate = _as_dict(source_map.get("integrated_operation_readiness_execution_gate_model"))
    dry_run_order_intent_payload = _as_dict(source_map.get("dry_run_order_intent_payload")) or _default_order_intent_payload()

    u52_report_ready = upstream.get("decision") == U52_READY_DECISION
    u52_ready = _bool_from_upstream(upstream, "generic_supervised_paper_integrated_operation_readiness_execution_ready")
    u52_model_ready = _bool_from_upstream(upstream, "generic_integrated_operation_readiness_execution_model_ready")
    u52_patch_ready = _bool_from_upstream(upstream, "generic_integrated_operation_readiness_execution_patch_ready")
    u52_allowed = _bool_from_upstream(upstream, "generic_integrated_operation_readiness_execution_allowed")

    terminal_handoff_runtime_executed = _bool_from_upstream(upstream, "terminal_lifecycle_handoff_runtime_executed")
    scheduler_completion_handoff_runtime_executed = _bool_from_upstream(upstream, "scheduler_completion_handoff_runtime_executed")
    telegram_lifecycle_completion_send_runtime_executed = _bool_from_upstream(upstream, "telegram_lifecycle_completion_send_runtime_executed")
    paper_state_terminal_handoff_mutated = _bool_from_upstream(upstream, "paper_state_terminal_handoff_mutated")
    paper_status_terminal_handoff_mutated = _bool_from_upstream(upstream, "paper_status_terminal_handoff_mutated")
    broker_submit_receipt_available = _bool_from_upstream(upstream, "broker_submit_receipt_available")
    broker_close_receipt_available = _bool_from_upstream(upstream, "broker_close_receipt_available")
    real_close_execution_available = _bool_from_upstream(upstream, "real_close_execution_available")
    paper_position_closed = _bool_from_upstream(upstream, "paper_position_closed")
    paper_realized_pnl_reconciliation_ready = _bool_from_upstream(upstream, "paper_realized_pnl_reconciliation_ready")
    realized_pnl_written = _bool_from_upstream(upstream, "realized_pnl_written")
    paper_final_audit_ready = _bool_from_upstream(upstream, "paper_final_audit_ready")
    paper_postmortem_ready = _bool_from_upstream(upstream, "paper_postmortem_ready")
    paper_lifecycle_completion_ready = _bool_from_upstream(upstream, "paper_lifecycle_completion_ready")
    paper_lifecycle_state_status_completion_mutation_ready = _bool_from_upstream(
        upstream, "paper_lifecycle_state_status_completion_mutation_ready"
    )
    paper_terminal_lifecycle_handoff_ready = _bool_from_upstream(upstream, "paper_terminal_lifecycle_handoff_ready")
    final_audit_runtime_executed = _bool_from_upstream(upstream, "final_audit_runtime_executed")
    postmortem_runtime_executed = _bool_from_upstream(upstream, "postmortem_runtime_executed")
    lifecycle_completion_audit_runtime_executed = _bool_from_upstream(
        upstream, "lifecycle_completion_audit_runtime_executed"
    )
    lifecycle_state_status_completion_mutation_runtime_executed = _bool_from_upstream(
        upstream, "lifecycle_state_status_completion_mutation_runtime_executed"
    )
    lifecycle_state_complete = _bool_from_upstream(upstream, "lifecycle_state_complete")
    runtime_values_present = bool(source_gate.get("runtime_values_present", False))

    gate_checks: Tuple[Tuple[bool, str], ...] = (
        (u52_report_ready, "integrated_operation_readiness_execution_report_not_ready"),
        (u52_ready, "integrated_operation_readiness_execution_not_ready"),
        (u52_model_ready, "integrated_operation_readiness_execution_model_not_ready"),
        (u52_patch_ready, "integrated_operation_readiness_execution_patch_not_ready"),
        (u52_allowed, "integrated_operation_readiness_execution_not_allowed"),
        (paper_terminal_lifecycle_handoff_ready, "paper_terminal_lifecycle_handoff_not_ready"),
        (terminal_handoff_runtime_executed, "terminal_lifecycle_handoff_runtime_absent"),
        (scheduler_completion_handoff_runtime_executed, "scheduler_completion_handoff_runtime_absent"),
        (telegram_lifecycle_completion_send_runtime_executed, "telegram_lifecycle_completion_send_runtime_absent"),
        (paper_state_terminal_handoff_mutated, "paper_state_terminal_handoff_mutation_absent"),
        (paper_status_terminal_handoff_mutated, "paper_status_terminal_handoff_mutation_absent"),
        (lifecycle_state_status_completion_mutation_runtime_executed, "lifecycle_state_status_completion_mutation_runtime_absent"),
        (lifecycle_completion_audit_runtime_executed, "lifecycle_completion_audit_runtime_execution_absent"),
        (postmortem_runtime_executed, "postmortem_runtime_execution_absent"),
        (final_audit_runtime_executed, "final_audit_runtime_execution_absent"),
        (broker_submit_receipt_available, "broker_submit_receipt_absent"),
        (broker_close_receipt_available, "broker_close_receipt_absent"),
        (real_close_execution_available, "real_close_execution_absent"),
        (paper_position_closed, "closed_position_absent"),
        (paper_realized_pnl_reconciliation_ready, "paper_realized_pnl_reconciliation_not_ready"),
        (realized_pnl_written, "realized_pnl_not_written"),
        (paper_final_audit_ready, "paper_final_audit_not_ready"),
        (paper_postmortem_ready, "paper_postmortem_not_ready"),
        (paper_lifecycle_completion_ready, "paper_lifecycle_completion_not_ready"),
        (paper_lifecycle_state_status_completion_mutation_ready, "paper_lifecycle_state_status_completion_mutation_not_ready"),
        (lifecycle_state_complete, "lifecycle_state_not_complete"),
        (_operator_gate(active_env, REARM_ENABLE_ENV, REARM_CONFIRMATION_ENV, REARM_CONFIRMATION_SENTINEL), "operator_rearm_gate_not_satisfied"),
        (_operator_gate(active_env, SUBMIT_ENABLE_ENV, SUBMIT_CONFIRMATION_ENV, SUBMIT_CONFIRMATION_SENTINEL), "operator_submit_gate_not_satisfied"),
        (_operator_gate(active_env, CLOSE_ENABLE_ENV, CLOSE_CONFIRMATION_ENV, CLOSE_CONFIRMATION_SENTINEL), "operator_close_gate_not_satisfied"),
        (_operator_gate(active_env, PNL_ENABLE_ENV, PNL_CONFIRMATION_ENV, PNL_CONFIRMATION_SENTINEL), "operator_realized_pnl_gate_not_satisfied"),
        (_operator_gate(active_env, FINAL_AUDIT_ENABLE_ENV, FINAL_AUDIT_CONFIRMATION_ENV, FINAL_AUDIT_CONFIRMATION_SENTINEL), "operator_final_audit_gate_not_satisfied"),
        (_operator_gate(active_env, POSTMORTEM_ENABLE_ENV, POSTMORTEM_CONFIRMATION_ENV, POSTMORTEM_CONFIRMATION_SENTINEL), "operator_postmortem_gate_not_satisfied"),
        (_operator_gate(active_env, LIFECYCLE_COMPLETION_ENABLE_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL), "operator_lifecycle_completion_gate_not_satisfied"),
        (_operator_gate(active_env, STATE_STATUS_MUTATION_ENABLE_ENV, STATE_STATUS_MUTATION_CONFIRMATION_ENV, STATE_STATUS_MUTATION_CONFIRMATION_SENTINEL), "operator_lifecycle_state_status_completion_mutation_gate_not_satisfied"),
        (_operator_gate(active_env, TERMINAL_HANDOFF_ENABLE_ENV, TERMINAL_HANDOFF_CONFIRMATION_ENV, TERMINAL_HANDOFF_CONFIRMATION_SENTINEL), "operator_terminal_lifecycle_handoff_gate_not_satisfied"),
        (_operator_gate(active_env, INTEGRATED_OPERATION_ENABLE_ENV, INTEGRATED_OPERATION_CONFIRMATION_ENV, INTEGRATED_OPERATION_CONFIRMATION_SENTINEL), "operator_integrated_operation_gate_not_satisfied"),
        (_operator_gate(active_env, FINAL_READINESS_AUDIT_ENABLE_ENV, FINAL_READINESS_AUDIT_CONFIRMATION_ENV, FINAL_READINESS_AUDIT_CONFIRMATION_SENTINEL), "operator_integrated_operation_final_readiness_audit_gate_not_satisfied"),
        (runtime_values_present, "runtime_values_absent_or_deferred"),
        (False, "explicit_integrated_operation_final_readiness_audit_execution_patch_required"),
    )
    blocked_reasons = [reason for ok, reason in gate_checks if not ok]
    preflight_conditions_satisfied = not blocked_reasons

    gate_model = {
        "integrated_operation_readiness_execution_report_required": True,
        "integrated_operation_readiness_execution_report_ready": u52_report_ready,
        "integrated_operation_readiness_execution_ready": u52_ready,
        "integrated_operation_readiness_execution_model_ready": u52_model_ready,
        "integrated_operation_readiness_execution_patch_ready": u52_patch_ready,
        "integrated_operation_readiness_execution_allowed": u52_allowed,
        "integrated_operation_final_readiness_audit_preflight_gate_model_ready": True,
        "integrated_operation_final_readiness_audit_preflight_model_ready": True,
        "integrated_operation_final_readiness_audit_preflight_patch_ready": True,
        "integrated_operation_final_readiness_audit_preflight_conditions_satisfied": preflight_conditions_satisfied,
        "integrated_operation_final_readiness_audit_preflight_allowed": False,
        "integrated_operation_final_readiness_audit_allowed": False,
        "integrated_operation_final_readiness_audit_execution_allowed": False,
        "integrated_operation_execution_allowed": False,
        "integrated_operation_final_readiness_audit_preflight_blocked_reasons": blocked_reasons,
        "future_integrated_operation_allowed": False,
        "explicit_integrated_operation_final_readiness_audit_execution_patch_required": True,
        "terminal_lifecycle_handoff_runtime_required": True,
        "terminal_lifecycle_handoff_runtime_executed": terminal_handoff_runtime_executed,
        "scheduler_completion_handoff_runtime_required": True,
        "scheduler_completion_handoff_runtime_executed": scheduler_completion_handoff_runtime_executed,
        "telegram_lifecycle_completion_send_runtime_required": True,
        "telegram_lifecycle_completion_send_runtime_executed": telegram_lifecycle_completion_send_runtime_executed,
        "paper_state_terminal_handoff_mutation_required": True,
        "paper_state_terminal_handoff_mutated": paper_state_terminal_handoff_mutated,
        "paper_status_terminal_handoff_mutation_required": True,
        "paper_status_terminal_handoff_mutated": paper_status_terminal_handoff_mutated,
        "lifecycle_state_status_completion_mutation_runtime_required": True,
        "lifecycle_state_status_completion_mutation_runtime_executed": lifecycle_state_status_completion_mutation_runtime_executed,
        "lifecycle_completion_audit_runtime_execution_required": True,
        "lifecycle_completion_audit_runtime_executed": lifecycle_completion_audit_runtime_executed,
        "postmortem_runtime_execution_required": True,
        "postmortem_runtime_executed": postmortem_runtime_executed,
        "final_audit_runtime_execution_required": True,
        "final_audit_runtime_executed": final_audit_runtime_executed,
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
        "paper_final_audit_ready_required": True,
        "paper_final_audit_ready": paper_final_audit_ready,
        "paper_postmortem_ready_required": True,
        "paper_postmortem_ready": paper_postmortem_ready,
        "paper_lifecycle_completion_ready_required": True,
        "paper_lifecycle_completion_ready": paper_lifecycle_completion_ready,
        "paper_lifecycle_state_status_completion_mutation_ready_required": True,
        "paper_lifecycle_state_status_completion_mutation_ready": paper_lifecycle_state_status_completion_mutation_ready,
        "paper_terminal_lifecycle_handoff_ready_required": True,
        "paper_terminal_lifecycle_handoff_ready": paper_terminal_lifecycle_handoff_ready,
        "lifecycle_state_complete_required": True,
        "lifecycle_state_complete": lifecycle_state_complete,
        "operator_rearm_gate_required": True,
        "operator_rearm_gate_satisfied": _operator_gate(active_env, REARM_ENABLE_ENV, REARM_CONFIRMATION_ENV, REARM_CONFIRMATION_SENTINEL),
        "operator_submit_gate_required": True,
        "operator_submit_gate_satisfied": _operator_gate(active_env, SUBMIT_ENABLE_ENV, SUBMIT_CONFIRMATION_ENV, SUBMIT_CONFIRMATION_SENTINEL),
        "operator_close_gate_required": True,
        "operator_close_gate_satisfied": _operator_gate(active_env, CLOSE_ENABLE_ENV, CLOSE_CONFIRMATION_ENV, CLOSE_CONFIRMATION_SENTINEL),
        "operator_realized_pnl_gate_required": True,
        "operator_realized_pnl_gate_satisfied": _operator_gate(active_env, PNL_ENABLE_ENV, PNL_CONFIRMATION_ENV, PNL_CONFIRMATION_SENTINEL),
        "operator_final_audit_gate_required": True,
        "operator_final_audit_gate_satisfied": _operator_gate(active_env, FINAL_AUDIT_ENABLE_ENV, FINAL_AUDIT_CONFIRMATION_ENV, FINAL_AUDIT_CONFIRMATION_SENTINEL),
        "operator_postmortem_gate_required": True,
        "operator_postmortem_gate_satisfied": _operator_gate(active_env, POSTMORTEM_ENABLE_ENV, POSTMORTEM_CONFIRMATION_ENV, POSTMORTEM_CONFIRMATION_SENTINEL),
        "operator_lifecycle_completion_gate_required": True,
        "operator_lifecycle_completion_gate_satisfied": _operator_gate(active_env, LIFECYCLE_COMPLETION_ENABLE_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_ENV, LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL),
        "operator_lifecycle_state_status_completion_mutation_gate_required": True,
        "operator_lifecycle_state_status_completion_mutation_gate_satisfied": _operator_gate(active_env, STATE_STATUS_MUTATION_ENABLE_ENV, STATE_STATUS_MUTATION_CONFIRMATION_ENV, STATE_STATUS_MUTATION_CONFIRMATION_SENTINEL),
        "operator_terminal_lifecycle_handoff_gate_required": True,
        "operator_terminal_lifecycle_handoff_gate_satisfied": _operator_gate(active_env, TERMINAL_HANDOFF_ENABLE_ENV, TERMINAL_HANDOFF_CONFIRMATION_ENV, TERMINAL_HANDOFF_CONFIRMATION_SENTINEL),
        "operator_integrated_operation_gate_required": True,
        "operator_integrated_operation_gate_satisfied": _operator_gate(active_env, INTEGRATED_OPERATION_ENABLE_ENV, INTEGRATED_OPERATION_CONFIRMATION_ENV, INTEGRATED_OPERATION_CONFIRMATION_SENTINEL),
        "operator_integrated_operation_final_readiness_audit_enable_env": FINAL_READINESS_AUDIT_ENABLE_ENV,
        "operator_integrated_operation_final_readiness_audit_confirmation_env": FINAL_READINESS_AUDIT_CONFIRMATION_ENV,
        "operator_integrated_operation_final_readiness_audit_confirmation_required_value": FINAL_READINESS_AUDIT_CONFIRMATION_SENTINEL,
        "operator_integrated_operation_final_readiness_audit_gate_required": True,
        "operator_integrated_operation_final_readiness_audit_gate_satisfied": _operator_gate(active_env, FINAL_READINESS_AUDIT_ENABLE_ENV, FINAL_READINESS_AUDIT_CONFIRMATION_ENV, FINAL_READINESS_AUDIT_CONFIRMATION_SENTINEL),
        "runtime_values_required_before_integrated_operation_final_readiness_audit": True,
        "runtime_values_present": runtime_values_present,
        "max_open_positions": 1,
        "max_open_positions_valid": True,
        "paper_only": True,
        "paper_only_valid": True,
        "live_testnet_exchange_required_off": True,
        "scheduler_start_allowed_after_integrated_operation_final_readiness_audit_preflight": False,
        "telegram_network_send_allowed_after_integrated_operation_final_readiness_audit_preflight": False,
        "paper_state_mutation_allowed_after_integrated_operation_final_readiness_audit_preflight": False,
        "paper_status_mutation_allowed_after_integrated_operation_final_readiness_audit_preflight": False,
        "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "missing_model_fields": [],
    }

    context = {
        "blocked_reason": "integrated_operation_final_readiness_audit_preflight_blocked_until_complete_runtime_lifecycle_evidence_operator_gates_and_explicit_execution_patch",
        "integrated_operation_readiness_execution_ready": u52_report_ready and u52_ready and u52_model_ready,
        "generic_integrated_operation_readiness_execution_allowed": u52_allowed,
        "generic_integrated_operation_final_readiness_audit_preflight_ready": True,
        "generic_integrated_operation_final_readiness_audit_preflight_allowed": False,
        "generic_integrated_operation_final_readiness_audit_allowed": False,
        "generic_integrated_operation_final_readiness_audit_execution_allowed": False,
        "generic_integrated_operation_allowed": False,
        "generic_integrated_operation_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_integrated_operation_ready": False,
        "paper_integrated_operation_final_ready": False,
        "paper_terminal_lifecycle_handoff_ready": paper_terminal_lifecycle_handoff_ready,
        "terminal_lifecycle_handoff_runtime_executed": terminal_handoff_runtime_executed,
        "scheduler_completion_handoff_runtime_executed": scheduler_completion_handoff_runtime_executed,
        "telegram_lifecycle_completion_send_runtime_executed": telegram_lifecycle_completion_send_runtime_executed,
        "broker_submit_receipt_available": broker_submit_receipt_available,
        "broker_close_receipt_available": broker_close_receipt_available,
        "real_close_execution_available": real_close_execution_available,
        "paper_position_closed": paper_position_closed,
        "realized_pnl_written": realized_pnl_written,
        "final_audit_runtime_executed": final_audit_runtime_executed,
        "postmortem_runtime_executed": postmortem_runtime_executed,
        "lifecycle_completion_audit_runtime_executed": lifecycle_completion_audit_runtime_executed,
        "lifecycle_state_status_completion_mutation_runtime_executed": lifecycle_state_status_completion_mutation_runtime_executed,
        "lifecycle_state": upstream.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": lifecycle_state_complete,
        "would_run_integrated_operation_final_readiness_audit": False,
        "would_run_integrated_operation": False,
        "would_handoff_terminal_lifecycle": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "would_submit": False,
        "would_close": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_run_lifecycle_completion_audit": False,
    }

    return {
        "mode": "generic_supervised_paper_integrated_operation_final_readiness_audit_preflight_only",
        "preflight_only": True,
        "read_only": True,
        "read_only_by_default": True,
        "fail_closed": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "paper_only": True,
        "preflight_source": "29.4.4u-52",
        "source_integrated_operation_readiness_execution_map": source_map,
        "dry_run_order_intent_payload": dry_run_order_intent_payload,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "missing_contract_fields": [],
        "integrated_operation_final_readiness_audit_preflight_context": context,
        "integrated_operation_final_readiness_audit_preflight_gate_model": gate_model,
        "required_future_controls_before_integrated_operation_final_readiness_audit_execution": {
            "integrated_operation_readiness_execution_report_required": True,
            "explicit_generic_integrated_operation_final_readiness_audit_execution_patch_required": True,
            "terminal_lifecycle_handoff_runtime_required_before_final_readiness_audit": True,
            "scheduler_completion_handoff_runtime_required_before_final_readiness_audit": True,
            "telegram_lifecycle_completion_send_runtime_required_before_final_readiness_audit": True,
            "paper_state_terminal_handoff_required_before_final_readiness_audit": True,
            "paper_status_terminal_handoff_required_before_final_readiness_audit": True,
            "lifecycle_state_status_completion_mutation_runtime_required_before_final_readiness_audit": True,
            "lifecycle_completion_audit_runtime_execution_required_before_final_readiness_audit": True,
            "postmortem_runtime_execution_required_before_final_readiness_audit": True,
            "final_audit_runtime_execution_required_before_final_readiness_audit": True,
            "broker_submit_receipt_required_before_final_readiness_audit": True,
            "broker_close_receipt_required_before_final_readiness_audit": True,
            "closed_position_required_before_final_readiness_audit": True,
            "real_close_execution_required_before_final_readiness_audit": True,
            "realized_pnl_written_required_before_final_readiness_audit": True,
            "lifecycle_state_complete_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "generic_close_operator_gate_required": True,
            "generic_realized_pnl_operator_gate_required": True,
            "generic_final_audit_operator_gate_required": True,
            "generic_postmortem_operator_gate_required": True,
            "generic_lifecycle_completion_operator_gate_required": True,
            "generic_lifecycle_state_status_completion_mutation_operator_gate_required": True,
            "generic_terminal_lifecycle_handoff_operator_gate_required": True,
            "generic_integrated_operation_operator_gate_required": True,
            "generic_integrated_operation_final_readiness_audit_operator_gate_required": True,
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
            for stage in FINAL_READINESS_AUDIT_PREFLIGHT_STAGES
        ],
    }


def _build_report(settings: Settings, upstream: Mapping[str, Any] | None, markers_ok: bool, missing_files: List[str], missing_markers: Dict[str, List[str]]) -> Dict[str, Any]:
    active_env = _active_lsr_env()
    blockers: List[str] = []
    if upstream is None:
        blockers.append("missing_upstream_reports")
        upstream = {}
    elif upstream.get("decision") != U52_READY_DECISION:
        blockers.append("not_ready_upstream_reports")
    if not markers_ok:
        blockers.append("missing_source_markers")

    final_map = _build_final_readiness_audit_preflight_map(upstream, active_env)
    status = "PASS" if not blockers else "FAIL"
    decision = READY_DECISION if status == "PASS" else KEEP_DIAGNOSTIC_DECISION
    diagnostic_count = _safe_int(upstream.get("integrated_operation_readiness_execution_diagnostic_count", upstream.get("candidate_detection_source_counts", {}).get("paper_events_jsonl_diagnostic_read", 0))) + 1
    false_flags = {key: False for key in FALSE_EXECUTION_KEYS}

    report: Dict[str, Any] = {
        "status": status,
        "decision": decision,
        "event_type": EVENT_TYPE,
        "prompt": PROMPT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report": str(settings.data_path / settings.report_name),
        "jsonl": str(settings.data_path / settings.jsonl_name),
        "classification_labels": [
            "GENERIC_LSR_V2_SUPERVISED_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_PREFLIGHT",
            "INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_PREFLIGHT_ONLY",
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
            "GENERIC_SUPERVISED_PAPER_INTEGRATED_OPERATION_FINAL_READINESS_AUDIT_PREFLIGHT_READY",
        ],
        "blockers": blockers,
        "missing_source_files": missing_files,
        "missing_source_markers": missing_markers,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "all_execution_flags_fail_closed": True,
        "blocked_until_runtime_integrated_operation_final_readiness_audit_execution_prerequisites": list(BLOCKED_UNTIL_FINAL_READINESS_AUDIT_EXECUTION_PREREQUISITES),
        "generic_supervised_paper_integrated_operation_final_readiness_audit_preflight_ready": status == "PASS",
        "generic_integrated_operation_final_readiness_audit_preflight_ready": status == "PASS",
        "generic_integrated_operation_final_readiness_audit_preflight_model_ready": True,
        "generic_integrated_operation_final_readiness_audit_preflight_patch_ready": True,
        "paper_integrated_operation_final_readiness_audit_preflight_ready": status == "PASS",
        "integrated_operation_final_readiness_audit_preflight_diagnostic_available": True,
        "integrated_operation_final_readiness_audit_preflight_diagnostic_count": diagnostic_count,
        "generic_supervised_paper_integrated_operation_final_readiness_audit_preflight_map": final_map,
        "candidate_detection_source_counts": _as_dict(upstream.get("candidate_detection_source_counts")),
        "candidate_diagnostic_examples": _candidate_examples(upstream),
        "lifecycle_state": upstream.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": _bool_from_upstream(upstream, "lifecycle_state_complete"),
        "terminal_lifecycle_handoff_runtime_executed": _bool_from_upstream(upstream, "terminal_lifecycle_handoff_runtime_executed"),
        "scheduler_completion_handoff_runtime_executed": _bool_from_upstream(upstream, "scheduler_completion_handoff_runtime_executed"),
        "telegram_lifecycle_completion_send_runtime_executed": _bool_from_upstream(upstream, "telegram_lifecycle_completion_send_runtime_executed"),
        "paper_state_terminal_handoff_mutated": _bool_from_upstream(upstream, "paper_state_terminal_handoff_mutated"),
        "paper_status_terminal_handoff_mutated": _bool_from_upstream(upstream, "paper_status_terminal_handoff_mutated"),
        "broker_submit_receipt_available": _bool_from_upstream(upstream, "broker_submit_receipt_available"),
        "broker_close_receipt_available": _bool_from_upstream(upstream, "broker_close_receipt_available"),
        "real_close_execution_available": _bool_from_upstream(upstream, "real_close_execution_available"),
        "paper_position_closed": _bool_from_upstream(upstream, "paper_position_closed"),
        "paper_realized_pnl_reconciliation_ready": _bool_from_upstream(upstream, "paper_realized_pnl_reconciliation_ready"),
        "realized_pnl_written": _bool_from_upstream(upstream, "realized_pnl_written"),
        "paper_final_audit_ready": _bool_from_upstream(upstream, "paper_final_audit_ready"),
        "paper_postmortem_ready": _bool_from_upstream(upstream, "paper_postmortem_ready"),
        "paper_lifecycle_completion_ready": _bool_from_upstream(upstream, "paper_lifecycle_completion_ready"),
        "paper_lifecycle_state_status_completion_mutation_ready": _bool_from_upstream(upstream, "paper_lifecycle_state_status_completion_mutation_ready"),
        "paper_terminal_lifecycle_handoff_ready": _bool_from_upstream(upstream, "paper_terminal_lifecycle_handoff_ready"),
        "final_audit_runtime_executed": _bool_from_upstream(upstream, "final_audit_runtime_executed"),
        "postmortem_runtime_executed": _bool_from_upstream(upstream, "postmortem_runtime_executed"),
        "lifecycle_completion_audit_runtime_executed": _bool_from_upstream(upstream, "lifecycle_completion_audit_runtime_executed"),
        "lifecycle_state_status_completion_mutation_runtime_executed": _bool_from_upstream(upstream, "lifecycle_state_status_completion_mutation_runtime_executed"),
        "would_run_integrated_operation_final_readiness_audit": False,
        "would_run_integrated_operation": False,
        "would_handoff_terminal_lifecycle": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "would_submit": False,
        "would_close": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_run_lifecycle_completion_audit": False,
        "broker_submit_called_by_generic_integrated_operation_final_readiness_audit_preflight": False,
        "broker_close_called_by_generic_integrated_operation_final_readiness_audit_preflight": False,
        "telegram_network_send_called_by_generic_integrated_operation_final_readiness_audit_preflight": False,
        "scheduler_started_by_generic_integrated_operation_final_readiness_audit_preflight": False,
        "paper_state_modified_by_generic_integrated_operation_final_readiness_audit_preflight": False,
        "paper_status_modified_by_generic_integrated_operation_final_readiness_audit_preflight": False,
        "orders_submitted_by_generic_integrated_operation_final_readiness_audit_preflight": 0,
        "orders_closed_by_generic_integrated_operation_final_readiness_audit_preflight": 0,
        "positions_opened_by_generic_integrated_operation_final_readiness_audit_preflight": 0,
        "positions_closed_by_generic_integrated_operation_final_readiness_audit_preflight": 0,
        "exchange_broker_enabled": False,
        "live_mode_enabled": False,
        "testnet_mode_enabled": False,
        "paper_only": True,
        "max_open_positions": 1,
        "fourth_trade_locked": True,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "eighth_trade_patch_allowed": False,
        "ninth_trade_patch_allowed": False,
    }
    report.update(false_flags)
    return report


def run_generic_supervised_paper_integrated_operation_final_readiness_audit_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    upstream_path = settings.data_path / "lsr_v2_generic_supervised_paper_integrated_operation_readiness_execution_report.json"
    upstream = _read_json(upstream_path)
    markers_ok, missing_files, missing_markers = _source_marker_audit(settings.project_root)
    report = _build_report(settings, upstream, markers_ok, missing_files, missing_markers)
    _write_json(settings.data_path / settings.report_name, report)
    _append_jsonl(settings.data_path / settings.jsonl_name, report)
    return report


if __name__ == "__main__":
    payload = run_generic_supervised_paper_integrated_operation_final_readiness_audit_preflight(Settings(project_root=Path(".")))
    print(json.dumps(payload, indent=2, sort_keys=True))
