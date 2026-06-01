"""Generic LSR-v2 supervised paper lifecycle completion audit preflight.

29.4.4u-41 is a preflight-only, read-only, fail-closed lifecycle completion
checkpoint. It consumes u-40's supervised paper postmortem execution artifact and
models the future requirements for declaring one complete supervised paper
lifecycle as auditable/completed.

The expected validation state still has no real submit/close receipts, no real
close execution, no closed paper position, no realized-PnL write, no final audit
runtime execution, no postmortem runtime execution, no runtime values, and no
operator gates. Therefore this patch must return a PASS/ready diagnostic for the
lifecycle-completion preflight model while keeping lifecycle completion,
paper-state/status mutation, Telegram/network sending, scheduler startup,
broker calls, and live/testnet/exchange access blocked.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-41"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT_NOT_READY"
U40_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_READY"

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
POSTMORTEM_ENABLE_ENV = "LSR_V2_GENERIC_POSTMORTEM_ENABLE"
POSTMORTEM_CONFIRMATION_ENV = "LSR_V2_GENERIC_POSTMORTEM_CONFIRMATION"
POSTMORTEM_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_POSTMORTEM_ONLY"
LIFECYCLE_COMPLETION_ENABLE_ENV = "LSR_V2_GENERIC_LIFECYCLE_COMPLETION_AUDIT_ENABLE"
LIFECYCLE_COMPLETION_CONFIRMATION_ENV = "LSR_V2_GENERIC_LIFECYCLE_COMPLETION_AUDIT_CONFIRMATION"
LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_LIFECYCLE_COMPLETION_AUDIT_ONLY"

LIFECYCLE_COMPLETION_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_postmortem_execution_report",
    "verify_postmortem_execution_model_ready",
    "verify_postmortem_runtime_execution_was_blocked",
    "verify_no_lifecycle_completion_runtime_audit",
    "verify_no_real_submit_receipt",
    "verify_no_real_close_receipt",
    "verify_no_closed_position",
    "verify_no_realized_pnl_written",
    "verify_no_final_audit_runtime_execution",
    "verify_no_postmortem_runtime_execution",
    "verify_lifecycle_completion_requires_complete_runtime_evidence",
    "verify_lifecycle_completion_operator_gate_required_but_absent",
    "verify_runtime_values_required_but_absent",
    "verify_state_status_mutation_disabled",
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
    "map_lifecycle_completion_audit_preflight_gate",
    "publish_generic_lifecycle_completion_audit_preflight_artifact",
)

BLOCKED_UNTIL_EXPLICIT_LIFECYCLE_COMPLETION_AUDIT_EXECUTION_PATCH: Tuple[str, ...] = (
    "generic_lifecycle_completion_audit_execution_real",
    "generic_paper_state_completion_mutation",
    "generic_paper_status_completion_mutation",
    "telegram_lifecycle_completion_send",
    "scheduler_completion_handoff",
    "live_or_testnet_or_exchange_broker",
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_postmortem_execution.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_POSTMORTEM_EXECUTION",
            "generic_postmortem_execution_ready",
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
    report_name: str = "lsr_v2_generic_supervised_paper_lifecycle_completion_audit_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_lifecycle_completion_audit_preflight.jsonl"
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


def _dry_run_payload(postmortem_report: Mapping[str, Any]) -> Dict[str, Any]:
    source_map = _as_dict(postmortem_report.get("generic_supervised_paper_postmortem_execution_map", {}))
    payload = _as_dict(source_map.get("dry_run_order_intent_payload", {}))
    if payload:
        return payload
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
        "runtime_values_present": False,
        "dry_run_only": True,
        "materialized": False,
        "persisted": False,
    }


def _runtime_values_present(payload: Mapping[str, Any]) -> bool:
    for field in REQUIRED_ORDER_INTENT_FIELDS:
        value = payload.get(field)
        if value in (None, "", DEFERRED_SENTINEL):
            return False
    return True


def _operator_gates(active_env: Mapping[str, str]) -> Dict[str, bool]:
    return {
        "rearm": (
            active_env.get(REARM_ENABLE_ENV) == "1"
            and active_env.get(REARM_CONFIRMATION_ENV) == REARM_CONFIRMATION_SENTINEL
            and active_env.get(REARM_MAX_POSITIONS_ENV) == "1"
        ),
        "submit": active_env.get(SUBMIT_ENABLE_ENV) == "1" and active_env.get(SUBMIT_CONFIRMATION_ENV) == SUBMIT_CONFIRMATION_SENTINEL,
        "close": active_env.get(CLOSE_ENABLE_ENV) == "1" and active_env.get(CLOSE_CONFIRMATION_ENV) == CLOSE_CONFIRMATION_SENTINEL,
        "pnl": active_env.get(PNL_ENABLE_ENV) == "1" and active_env.get(PNL_CONFIRMATION_ENV) == PNL_CONFIRMATION_SENTINEL,
        "final_audit": active_env.get(FINAL_AUDIT_ENABLE_ENV) == "1" and active_env.get(FINAL_AUDIT_CONFIRMATION_ENV) == FINAL_AUDIT_CONFIRMATION_SENTINEL,
        "postmortem": active_env.get(POSTMORTEM_ENABLE_ENV) == "1" and active_env.get(POSTMORTEM_CONFIRMATION_ENV) == POSTMORTEM_CONFIRMATION_SENTINEL,
        "lifecycle_completion": (
            active_env.get(LIFECYCLE_COMPLETION_ENABLE_ENV) == "1"
            and active_env.get(LIFECYCLE_COMPLETION_CONFIRMATION_ENV) == LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL
        ),
    }


def _build_lifecycle_completion_audit_preflight_map(postmortem_report: Mapping[str, Any], active_env: Mapping[str, str]) -> Dict[str, Any]:
    source_map = _as_dict(postmortem_report.get("generic_supervised_paper_postmortem_execution_map", {}))
    source_gate = _as_dict(source_map.get("postmortem_execution_gate_model", {}))
    payload = _dry_run_payload(postmortem_report)
    present_contract_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload]
    missing_contract_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in payload]
    runtime_values_present = _runtime_values_present(payload)
    gate_states = _operator_gates(active_env)

    postmortem_report_ready = postmortem_report.get("generic_supervised_paper_postmortem_execution_ready") is True
    postmortem_model_ready = postmortem_report.get("generic_postmortem_execution_model_ready") is True
    postmortem_patch_ready = postmortem_report.get("generic_postmortem_execution_patch_ready") is True
    postmortem_gate_model_ready = source_gate.get("postmortem_execution_gate_model_ready") is True
    postmortem_conditions_satisfied = source_gate.get("postmortem_execution_conditions_satisfied") is True
    postmortem_runtime_executed = postmortem_report.get("paper_postmortem_ready") is True and postmortem_report.get("would_run_postmortem") is True

    broker_submit_receipt_available = postmortem_report.get("broker_submit_receipt_available") is True
    broker_close_receipt_available = postmortem_report.get("broker_close_receipt_available") is True
    real_close_execution_available = postmortem_report.get("real_close_execution_available") is True
    paper_position_closed = postmortem_report.get("paper_position_closed") is True
    realized_pnl_written = postmortem_report.get("realized_pnl_written") is True
    paper_realized_pnl_ready = postmortem_report.get("paper_realized_pnl_reconciliation_ready") is True
    final_audit_runtime_executed = postmortem_report.get("final_audit_runtime_executed") is True
    paper_final_audit_ready = postmortem_report.get("paper_final_audit_ready") is True
    lifecycle_state_complete = postmortem_report.get("lifecycle_state") == "PAPER_LIFECYCLE_COMPLETE"

    completion_conditions_satisfied = all(
        (
            postmortem_report_ready,
            postmortem_model_ready,
            postmortem_patch_ready,
            postmortem_gate_model_ready,
            postmortem_conditions_satisfied,
            postmortem_runtime_executed,
            broker_submit_receipt_available,
            broker_close_receipt_available,
            real_close_execution_available,
            paper_position_closed,
            realized_pnl_written,
            paper_realized_pnl_ready,
            final_audit_runtime_executed,
            paper_final_audit_ready,
            lifecycle_state_complete,
            gate_states["rearm"],
            gate_states["submit"],
            gate_states["close"],
            gate_states["pnl"],
            gate_states["final_audit"],
            gate_states["postmortem"],
            gate_states["lifecycle_completion"],
            runtime_values_present,
            payload.get("paper_only") is True,
            payload.get("max_open_positions") == 1,
            not missing_contract_fields,
        )
    )

    blocked_reasons: List[str] = []
    checks = (
        (postmortem_report_ready, "postmortem_execution_report_not_ready"),
        (postmortem_model_ready, "postmortem_execution_model_not_ready"),
        (postmortem_patch_ready, "postmortem_execution_patch_not_ready"),
        (postmortem_gate_model_ready, "postmortem_execution_gate_model_not_ready"),
        (postmortem_conditions_satisfied, "postmortem_execution_conditions_not_satisfied"),
        (postmortem_runtime_executed, "postmortem_runtime_execution_absent"),
        (broker_submit_receipt_available, "broker_submit_receipt_absent"),
        (broker_close_receipt_available, "broker_close_receipt_absent"),
        (real_close_execution_available, "real_close_execution_absent"),
        (paper_position_closed, "closed_position_absent"),
        (realized_pnl_written, "realized_pnl_not_written"),
        (paper_realized_pnl_ready, "paper_realized_pnl_reconciliation_not_ready"),
        (final_audit_runtime_executed, "final_audit_runtime_execution_absent"),
        (paper_final_audit_ready, "paper_final_audit_not_ready"),
        (lifecycle_state_complete, "lifecycle_state_not_complete"),
        (gate_states["rearm"], "operator_rearm_gate_not_satisfied"),
        (gate_states["submit"], "operator_submit_gate_not_satisfied"),
        (gate_states["close"], "operator_close_gate_not_satisfied"),
        (gate_states["pnl"], "operator_realized_pnl_gate_not_satisfied"),
        (gate_states["final_audit"], "operator_final_audit_gate_not_satisfied"),
        (gate_states["postmortem"], "operator_postmortem_gate_not_satisfied"),
        (gate_states["lifecycle_completion"], "operator_lifecycle_completion_gate_not_satisfied"),
        (runtime_values_present, "runtime_values_absent_or_deferred"),
        (payload.get("paper_only") is True, "paper_only_policy_not_satisfied"),
        (payload.get("max_open_positions") == 1, "max_open_positions_policy_not_satisfied"),
        (not missing_contract_fields, "contract_fields_missing"),
    )
    blocked_reasons.extend(reason for ok, reason in checks if not ok)
    blocked_reasons.append("explicit_lifecycle_completion_audit_execution_patch_required")

    gate_model = {
        "lifecycle_completion_audit_preflight_model_ready": True,
        "lifecycle_completion_audit_preflight_gate_model_ready": True,
        "future_lifecycle_completion_audit_conditions_satisfied": completion_conditions_satisfied,
        "lifecycle_completion_audit_allowed": False,
        "lifecycle_completion_audit_blocked_reasons": blocked_reasons,
        "postmortem_execution_report_required": True,
        "postmortem_execution_report_ready": postmortem_report_ready,
        "postmortem_execution_model_ready": postmortem_model_ready,
        "postmortem_execution_patch_ready": postmortem_patch_ready,
        "postmortem_execution_gate_model_ready": postmortem_gate_model_ready,
        "postmortem_execution_conditions_satisfied": postmortem_conditions_satisfied,
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
        "realized_pnl_written_required": True,
        "realized_pnl_written": realized_pnl_written,
        "paper_realized_pnl_reconciliation_ready": paper_realized_pnl_ready,
        "paper_final_audit_ready": paper_final_audit_ready,
        "lifecycle_state_complete_required": True,
        "lifecycle_state_complete": lifecycle_state_complete,
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
        "operator_postmortem_gate_required": True,
        "operator_postmortem_gate_satisfied": gate_states["postmortem"],
        "operator_lifecycle_completion_gate_required": True,
        "operator_lifecycle_completion_gate_satisfied": gate_states["lifecycle_completion"],
        "operator_lifecycle_completion_enable_env": LIFECYCLE_COMPLETION_ENABLE_ENV,
        "operator_lifecycle_completion_confirmation_env": LIFECYCLE_COMPLETION_CONFIRMATION_ENV,
        "operator_lifecycle_completion_confirmation_required_value": LIFECYCLE_COMPLETION_CONFIRMATION_SENTINEL,
        "runtime_values_required_before_lifecycle_completion_audit": True,
        "runtime_values_present": runtime_values_present,
        "paper_only": payload.get("paper_only") is True,
        "paper_only_valid": payload.get("paper_only") is True,
        "max_open_positions": payload.get("max_open_positions"),
        "max_open_positions_valid": payload.get("max_open_positions") == 1,
        "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_model_fields": present_contract_fields,
        "missing_model_fields": missing_contract_fields,
        "state_mutation_allowed_during_preflight": False,
        "status_mutation_allowed_during_preflight": False,
        "telegram_network_send_allowed_during_preflight": False,
        "scheduler_start_allowed_during_preflight": False,
    }

    context = {
        "blocked_reason": "lifecycle_completion_audit_blocked_until_complete_runtime_lifecycle_evidence",
        "generic_lifecycle_completion_audit_preflight_ready": True,
        "generic_lifecycle_completion_audit_preflight_model_ready": True,
        "paper_lifecycle_completion_audit_preflight_ready": True,
        "generic_lifecycle_completion_audit_allowed": False,
        "paper_lifecycle_completion_ready": False,
        "postmortem_runtime_executed": postmortem_runtime_executed,
        "final_audit_runtime_executed": final_audit_runtime_executed,
        "broker_submit_receipt_available": broker_submit_receipt_available,
        "broker_close_receipt_available": broker_close_receipt_available,
        "real_close_execution_available": real_close_execution_available,
        "paper_position_closed": paper_position_closed,
        "paper_realized_pnl_reconciliation_ready": paper_realized_pnl_ready,
        "realized_pnl_written": realized_pnl_written,
        "paper_final_audit_ready": paper_final_audit_ready,
        "lifecycle_state": postmortem_report.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": lifecycle_state_complete,
        "would_submit": False,
        "would_close": False,
        "would_reconcile_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_run_lifecycle_completion_audit": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
    }

    return {
        "mode": "generic_supervised_paper_lifecycle_completion_audit_preflight_only",
        "preflight_source": "29.4.4u-40",
        "lifecycle_completion_audit_preflight_patch": True,
        "preflight_only": True,
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
        "dry_run_order_intent_payload": payload,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": present_contract_fields,
        "missing_contract_fields": missing_contract_fields,
        "lifecycle_completion_audit_preflight_gate_model": gate_model,
        "lifecycle_completion_audit_preflight_context": context,
        "source_postmortem_execution_map": source_map,
        "required_future_controls_before_lifecycle_completion_audit_execution": {
            "explicit_generic_lifecycle_completion_audit_execution_patch_required": True,
            "postmortem_runtime_execution_required_before_completion": True,
            "final_audit_runtime_execution_required_before_completion": True,
            "broker_submit_receipt_required_before_completion": True,
            "broker_close_receipt_required_before_completion": True,
            "real_close_execution_required_before_completion": True,
            "closed_position_required_before_completion": True,
            "realized_pnl_written_required_before_completion": True,
            "lifecycle_state_complete_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "generic_close_operator_gate_required": True,
            "generic_realized_pnl_operator_gate_required": True,
            "generic_final_audit_operator_gate_required": True,
            "generic_postmortem_operator_gate_required": True,
            "generic_lifecycle_completion_operator_gate_required": True,
            "runtime_value_validation_required": True,
            "runtime_values_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_only_required": True,
            "max_open_positions": 1,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in LIFECYCLE_COMPLETION_PREFLIGHT_STAGES
        ],
    }


def run_generic_supervised_paper_lifecycle_completion_audit_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_supervised_paper_postmortem_execution_report.json"
    postmortem_report = _read_json(data_path / upstream_name)
    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)

    upstream_present = bool(postmortem_report)
    upstream_ready = (
        postmortem_report.get("decision") == U40_READY_DECISION
        and postmortem_report.get("generic_supervised_paper_postmortem_execution_ready") is True
        and postmortem_report.get("generic_postmortem_execution_ready") is True
    )

    blockers: List[str] = []
    if not upstream_present:
        blockers.append("missing_upstream_reports")
    elif not upstream_ready:
        blockers.append("not_ready_upstream_reports")
    if not source_markers_present:
        blockers.append("missing_source_markers")

    ready = not blockers
    diagnostic_count = _safe_int(postmortem_report.get("postmortem_execution_diagnostic_count"), 0)
    diagnostic_available = postmortem_report.get("postmortem_execution_diagnostic_available") is True and diagnostic_count > 0
    lifecycle_map = _build_lifecycle_completion_audit_preflight_map(postmortem_report, active_env)
    gate = _as_dict(lifecycle_map.get("lifecycle_completion_audit_preflight_gate_model", {}))

    report: Dict[str, Any] = {
        "event_type": EVENT_TYPE,
        "prompt": PROMPT,
        "status": "PASS" if ready else "KEEP_DIAGNOSTIC",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "generated_at": _utc_now(),
        "blockers": blockers,
        "classification_labels": [
            "GENERIC_LSR_V2_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT",
            "LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT_ONLY",
            "READ_ONLY_BY_DEFAULT",
            "NO_ORDINAL_EXPANSION",
            "NO_LIFECYCLE_COMPLETION_RUNTIME_AUDIT",
            "NO_POSTMORTEM_RUNTIME_EXECUTION",
            "NO_FINAL_AUDIT_RUNTIME_EXECUTION",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT_READY" if ready else "GENERIC_SUPERVISED_PAPER_LIFECYCLE_COMPLETION_AUDIT_PREFLIGHT_NOT_READY",
        ],
        "u40_postmortem_execution_report_present": upstream_present,
        "u40_postmortem_execution_ready": upstream_ready,
        "source_markers_present": source_markers_present,
        "missing_source_files": missing_source_files,
        "missing_source_markers": missing_source_markers,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "generic_supervised_paper_lifecycle_completion_audit_preflight_ready": ready,
        "generic_lifecycle_completion_audit_preflight_ready": ready,
        "generic_lifecycle_completion_audit_preflight_model_ready": ready,
        "generic_lifecycle_completion_audit_preflight_patch_ready": ready,
        "paper_lifecycle_completion_audit_preflight_ready": ready,
        "lifecycle_completion_audit_preflight_diagnostic_available": diagnostic_available if ready else False,
        "lifecycle_completion_audit_preflight_diagnostic_count": diagnostic_count if ready else 0,
        "lifecycle_completion_audit_preflight_contract_shape_modelable": ready and not lifecycle_map.get("missing_contract_fields"),
        "lifecycle_completion_audit_preflight_contract_required_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "lifecycle_completion_audit_preflight_contract_present_fields": lifecycle_map.get("present_contract_fields", []),
        "lifecycle_completion_audit_preflight_contract_missing_fields": lifecycle_map.get("missing_contract_fields", []),
        "generic_supervised_paper_lifecycle_completion_audit_preflight_map": lifecycle_map,
        "candidate_detection_source_counts": postmortem_report.get("candidate_detection_source_counts", {}),
        "candidate_diagnostic_examples": _candidate_examples(postmortem_report),
        "postmortem_execution_diagnostic_available": postmortem_report.get("postmortem_execution_diagnostic_available") is True,
        "postmortem_execution_diagnostic_count": diagnostic_count,
        "generic_postmortem_execution_ready": postmortem_report.get("generic_postmortem_execution_ready") is True,
        "generic_postmortem_execution_model_ready": postmortem_report.get("generic_postmortem_execution_model_ready") is True,
        "generic_postmortem_execution_patch_ready": postmortem_report.get("generic_postmortem_execution_patch_ready") is True,
        "final_audit_runtime_executed": postmortem_report.get("final_audit_runtime_executed") is True,
        "postmortem_runtime_executed": gate.get("postmortem_runtime_executed") is True,
        "broker_submit_receipt_available": postmortem_report.get("broker_submit_receipt_available") is True,
        "broker_close_receipt_available": postmortem_report.get("broker_close_receipt_available") is True,
        "real_close_execution_available": postmortem_report.get("real_close_execution_available") is True,
        "paper_position_closed": postmortem_report.get("paper_position_closed") is True,
        "paper_realized_pnl_reconciliation_ready": postmortem_report.get("paper_realized_pnl_reconciliation_ready") is True,
        "realized_pnl_written": postmortem_report.get("realized_pnl_written") is True,
        "paper_final_audit_ready": postmortem_report.get("paper_final_audit_ready") is True,
        "paper_postmortem_ready": postmortem_report.get("paper_postmortem_ready") is True,
        "paper_lifecycle_completion_ready": False,
        "generic_lifecycle_completion_audit_allowed": False,
        "generic_lifecycle_completion_audit_execution_allowed": False,
        "generic_lifecycle_completion_operator_gate_required": True,
        "generic_lifecycle_completion_operator_gate_satisfied": gate.get("operator_lifecycle_completion_gate_satisfied") is True,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": gate.get("operator_rearm_gate_satisfied") is True,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": gate.get("operator_submit_gate_satisfied") is True,
        "generic_close_operator_gate_required": True,
        "generic_close_operator_gate_satisfied": gate.get("operator_close_gate_satisfied") is True,
        "generic_realized_pnl_operator_gate_required": True,
        "generic_realized_pnl_operator_gate_satisfied": gate.get("operator_realized_pnl_gate_satisfied") is True,
        "generic_final_audit_operator_gate_required": True,
        "generic_final_audit_operator_gate_satisfied": gate.get("operator_final_audit_gate_satisfied") is True,
        "generic_postmortem_operator_gate_required": True,
        "generic_postmortem_operator_gate_satisfied": gate.get("operator_postmortem_gate_satisfied") is True,
        "blocked_until_explicit_lifecycle_completion_audit_execution_patch": list(BLOCKED_UNTIL_EXPLICIT_LIFECYCLE_COMPLETION_AUDIT_EXECUTION_PATCH),
        "would_submit": False,
        "would_close": False,
        "would_reconcile_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_run_lifecycle_completion_audit": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "broker_submit_allowed": False,
        "broker_close_allowed": False,
        "broker_submit_called_by_generic_lifecycle_completion_audit_preflight": False,
        "broker_close_called_by_generic_lifecycle_completion_audit_preflight": False,
        "telegram_network_called_by_generic_lifecycle_completion_audit_preflight": False,
        "scheduler_started_by_generic_lifecycle_completion_audit_preflight": False,
        "orders_submitted_by_generic_lifecycle_completion_audit_preflight": 0,
        "positions_opened_by_generic_lifecycle_completion_audit_preflight": 0,
        "positions_closed_by_generic_lifecycle_completion_audit_preflight": 0,
        "paper_state_modified_by_generic_lifecycle_completion_audit_preflight": False,
        "paper_status_modified_by_generic_lifecycle_completion_audit_preflight": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "lifecycle_state": postmortem_report.get("lifecycle_state", "FLAT_LOCKED"),
        "lifecycle_state_complete": gate.get("lifecycle_state_complete") is True,
        "fourth_trade_locked": postmortem_report.get("fourth_trade_locked", True) is True,
        "stability_lock_active": postmortem_report.get("stability_lock_active", True) is True,
        "no_ordinal_expansion": True,
        "fifth_trade_patch_allowed": False,
        "eighth_trade_patch_allowed": False,
    }

    for key in FALSE_EXECUTION_KEYS:
        report[key] = False

    report["all_execution_flags_fail_closed"] = _all_false(report, FALSE_EXECUTION_KEYS)
    report["read_only_verified"] = (
        report["would_submit"] is False
        and report["would_close"] is False
        and report["would_run_lifecycle_completion_audit"] is False
        and report["would_mutate_paper_state"] is False
        and report["would_send_telegram"] is False
        and report["would_start_scheduler"] is False
    )

    if ready:
        _write_json(data_path / settings.report_name, report)
        _append_jsonl(data_path / settings.jsonl_name, report)
    return report


def main() -> None:
    report = run_generic_supervised_paper_lifecycle_completion_audit_preflight(Settings(project_root=Path.cwd()))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
