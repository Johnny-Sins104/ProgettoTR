"""Generic LSR-v2 supervised paper postmortem execution scaffold.

29.4.4u-39 is intentionally scaffold-only, read-only, and fail-closed. It
consumes u-38's supervised paper postmortem preflight artifact and models the
future requirements for running a real paper postmortem after a complete
supervised paper lifecycle.

The expected validation state still has no submit receipt, no close receipt, no
real close execution, no closed paper position, no realized-PnL write, no real
final audit runtime execution, no runtime values, and no operator gates.
Therefore this patch must return a PASS/ready diagnostic for the postmortem
execution scaffold while keeping postmortem execution, paper state/status
mutation, Telegram/network sending, scheduler startup, broker calls, and
live/testnet/exchange access blocked.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-39"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_SCAFFOLD"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_SCAFFOLD_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_SCAFFOLD_NOT_READY"
U38_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_POSTMORTEM_PREFLIGHT_READY"

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

POSTMORTEM_EXECUTION_SCAFFOLD_STAGES: Tuple[str, ...] = (
    "load_generic_postmortem_preflight",
    "verify_postmortem_preflight_ready",
    "verify_postmortem_execution_was_blocked",
    "verify_no_real_postmortem_execution_available",
    "verify_no_final_audit_runtime_execution",
    "verify_no_broker_close_receipt",
    "verify_no_realized_pnl_written",
    "verify_postmortem_execution_requires_final_audit_close_receipt_and_realized_pnl",
    "verify_postmortem_operator_gate_required_but_absent",
    "verify_runtime_values_required_but_absent",
    "verify_postmortem_execution_guard_disabled",
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
    "map_postmortem_execution_scaffold_gate",
    "publish_generic_postmortem_execution_scaffold_artifact",
)

BLOCKED_UNTIL_EXPLICIT_POSTMORTEM_EXECUTION_PATCH: Tuple[str, ...] = (
    "generic_postmortem_execution_real",
    "generic_paper_state_mutation",
    "generic_paper_status_mutation",
    "telegram_network_send",
    "scheduler_start",
    "live_or_testnet_or_exchange_broker",
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_postmortem_preflight.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_POSTMORTEM_PREFLIGHT",
            "generic_postmortem_preflight_ready",
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
    report_name: str = "lsr_v2_generic_supervised_paper_postmortem_execution_scaffold_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_postmortem_execution_scaffold.jsonl"
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


def _dry_run_payload(preflight_report: Mapping[str, Any]) -> Dict[str, Any]:
    preflight_map = _as_dict(preflight_report.get("generic_supervised_paper_postmortem_preflight_map", {}))
    payload = _as_dict(preflight_map.get("dry_run_order_intent_payload", {}))
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
        "dry_run_only": True,
        "materialized": False,
        "persisted": False,
        "runtime_values_present": False,
    }


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
        "postmortem": active_env.get(POSTMORTEM_ENABLE_ENV) == "1"
        and active_env.get(POSTMORTEM_CONFIRMATION_ENV) == POSTMORTEM_CONFIRMATION_SENTINEL,
    }


def _build_postmortem_execution_scaffold_map(preflight_report: Mapping[str, Any], active_env: Mapping[str, str]) -> Dict[str, Any]:
    source_map = _as_dict(preflight_report.get("generic_supervised_paper_postmortem_preflight_map", {}))
    source_gate = _as_dict(source_map.get("postmortem_preflight_gate_model", {}))
    payload = _dry_run_payload(preflight_report)
    present_contract_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload]
    missing_contract_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in payload]
    gate_states = _operator_gate_states(active_env)

    preflight_report_ready = preflight_report.get("generic_supervised_paper_postmortem_preflight_ready") is True
    preflight_model_ready = preflight_report.get("generic_postmortem_preflight_model_ready") is True
    preflight_gate_model_ready = source_gate.get("postmortem_gate_model_ready") is True
    preflight_conditions_satisfied = source_gate.get("postmortem_conditions_satisfied") is True
    preflight_execution_allowed = preflight_report.get("generic_postmortem_execution_allowed") is True
    final_audit_runtime_executed = preflight_report.get("final_audit_runtime_executed") is True
    broker_submit_receipt_available = preflight_report.get("broker_submit_receipt_available") is True
    broker_close_receipt_available = preflight_report.get("broker_close_receipt_available") is True
    real_close_execution_available = preflight_report.get("real_close_execution_available") is True
    paper_position_closed = preflight_report.get("paper_position_closed") is True
    paper_realized_pnl_reconciliation_ready = preflight_report.get("paper_realized_pnl_reconciliation_ready") is True
    realized_pnl_written = preflight_report.get("realized_pnl_written") is True or preflight_report.get("would_write_realized_pnl") is True
    paper_final_audit_ready = preflight_report.get("paper_final_audit_ready") is True
    runtime_values_present = _runtime_values_present(payload) and source_gate.get("runtime_values_present") is True

    future_conditions_satisfied = all(
        [
            preflight_report_ready,
            preflight_model_ready,
            preflight_gate_model_ready,
            preflight_conditions_satisfied,
            preflight_execution_allowed,
            final_audit_runtime_executed,
            broker_submit_receipt_available,
            broker_close_receipt_available,
            real_close_execution_available,
            paper_position_closed,
            paper_realized_pnl_reconciliation_ready,
            realized_pnl_written,
            paper_final_audit_ready,
            gate_states["rearm"],
            gate_states["submit"],
            gate_states["close"],
            gate_states["pnl"],
            gate_states["final_audit"],
            gate_states["postmortem"],
            runtime_values_present,
            not missing_contract_fields,
            payload.get("paper_only") is True,
            payload.get("max_open_positions") == 1,
        ]
    )

    blocked_reasons: List[str] = []
    if not preflight_report_ready:
        blocked_reasons.append("postmortem_preflight_report_not_ready")
    if not preflight_model_ready:
        blocked_reasons.append("postmortem_preflight_model_not_ready")
    if not preflight_gate_model_ready:
        blocked_reasons.append("postmortem_preflight_gate_model_not_ready")
    if not preflight_conditions_satisfied:
        blocked_reasons.append("postmortem_preflight_conditions_not_satisfied")
    if not preflight_execution_allowed:
        blocked_reasons.append("postmortem_preflight_execution_not_allowed")
    if not final_audit_runtime_executed:
        blocked_reasons.append("final_audit_runtime_execution_absent")
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
    if not paper_final_audit_ready:
        blocked_reasons.append("paper_final_audit_not_ready")
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
    if not gate_states["postmortem"]:
        blocked_reasons.append("operator_postmortem_gate_not_satisfied")
    if not runtime_values_present:
        blocked_reasons.append("runtime_values_absent_or_deferred")
    if missing_contract_fields:
        blocked_reasons.append("contract_fields_missing")
    if payload.get("paper_only") is not True:
        blocked_reasons.append("paper_only_policy_not_satisfied")
    if payload.get("max_open_positions") != 1:
        blocked_reasons.append("max_open_positions_policy_not_satisfied")
    blocked_reasons.append("explicit_postmortem_execution_patch_required")

    gate_model = {
        "postmortem_execution_scaffold_model_ready": True,
        "postmortem_execution_scaffold_gate_model_ready": True,
        "future_postmortem_execution_conditions_satisfied": future_conditions_satisfied,
        "postmortem_execution_allowed": False,
        "postmortem_execution_scaffold_blocked_reasons": blocked_reasons,
        "postmortem_preflight_report_required": True,
        "postmortem_preflight_report_ready": preflight_report_ready,
        "postmortem_preflight_model_ready": preflight_model_ready,
        "postmortem_preflight_gate_model_ready": preflight_gate_model_ready,
        "postmortem_preflight_conditions_satisfied": preflight_conditions_satisfied,
        "postmortem_preflight_execution_allowed": preflight_execution_allowed,
        "explicit_postmortem_execution_patch_required": True,
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
        "operator_postmortem_enable_env": POSTMORTEM_ENABLE_ENV,
        "operator_postmortem_confirmation_env": POSTMORTEM_CONFIRMATION_ENV,
        "operator_postmortem_confirmation_required_value": POSTMORTEM_CONFIRMATION_SENTINEL,
        "runtime_values_required_before_postmortem_execution": True,
        "runtime_values_present": runtime_values_present,
        "paper_only": payload.get("paper_only") is True,
        "paper_only_valid": payload.get("paper_only") is True,
        "max_open_positions": payload.get("max_open_positions"),
        "max_open_positions_valid": payload.get("max_open_positions") == 1,
        "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_model_fields": present_contract_fields,
        "missing_model_fields": missing_contract_fields,
        "state_mutation_allowed_after_postmortem": False,
        "status_mutation_allowed_after_postmortem": False,
        "telegram_network_send_allowed_after_postmortem": False,
        "scheduler_start_allowed_after_postmortem": False,
    }

    context = {
        "blocked_reason": "postmortem_execution_scaffold_blocked_until_real_final_audit_realized_pnl_close_receipt_and_explicit_execution_patch",
        "generic_supervised_paper_postmortem_execution_scaffold_ready": True,
        "generic_postmortem_execution_scaffold_model_ready": True,
        "paper_postmortem_execution_scaffold_ready": True,
        "generic_postmortem_execution_allowed": False,
        "paper_postmortem_ready": False,
        "final_audit_runtime_executed": final_audit_runtime_executed,
        "broker_submit_receipt_available": broker_submit_receipt_available,
        "broker_close_receipt_available": broker_close_receipt_available,
        "real_close_execution_available": real_close_execution_available,
        "paper_position_closed": paper_position_closed,
        "paper_realized_pnl_reconciliation_ready": paper_realized_pnl_reconciliation_ready,
        "realized_pnl_written": realized_pnl_written,
        "paper_final_audit_ready": paper_final_audit_ready,
        "would_close": False,
        "would_submit": False,
        "would_reconcile_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
    }

    return {
        "mode": "generic_supervised_paper_postmortem_execution_scaffold_only",
        "preflight_source": "29.4.4u-38",
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
        "dry_run_order_intent_payload": payload,
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": present_contract_fields,
        "missing_contract_fields": missing_contract_fields,
        "postmortem_execution_scaffold_gate_model": gate_model,
        "postmortem_execution_scaffold_context": context,
        "source_postmortem_preflight_map": source_map,
        "required_future_controls_before_postmortem_execution_activation": {
            "explicit_generic_postmortem_execution_patch_required": True,
            "final_audit_execution_report_required": True,
            "final_audit_runtime_execution_required_before_postmortem": True,
            "broker_close_receipt_required_before_postmortem": True,
            "broker_submit_receipt_required_before_postmortem": True,
            "realized_pnl_written_required_before_postmortem": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "generic_close_operator_gate_required": True,
            "generic_realized_pnl_operator_gate_required": True,
            "generic_final_audit_operator_gate_required": True,
            "generic_postmortem_operator_gate_required": True,
            "paper_state_status_mutation_requires_explicit_execution_patch": True,
            "telegram_network_send_requires_explicit_execution_patch": True,
            "scheduler_start_requires_explicit_execution_patch": True,
            "runtime_value_validation_required": True,
            "runtime_values_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_only_required": True,
            "max_open_positions": 1,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in POSTMORTEM_EXECUTION_SCAFFOLD_STAGES
        ],
    }


def run_generic_supervised_paper_postmortem_execution_scaffold(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_supervised_paper_postmortem_preflight_report.json"
    preflight_report = _read_json(data_path / upstream_name)
    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)

    missing_upstream_reports = [] if preflight_report else [upstream_name]
    upstream_ready = (
        preflight_report.get("decision") == U38_READY_DECISION
        and preflight_report.get("generic_supervised_paper_postmortem_preflight_ready") is True
    )
    not_ready_upstream_reports = [] if not preflight_report or upstream_ready else [upstream_name]

    scaffold_map = _build_postmortem_execution_scaffold_map(preflight_report, active_env)
    gate_model = _as_dict(scaffold_map.get("postmortem_execution_scaffold_gate_model", {}))
    context = _as_dict(scaffold_map.get("postmortem_execution_scaffold_context", {}))
    payload = _as_dict(scaffold_map.get("dry_run_order_intent_payload", {}))
    present_fields_ok = _as_list(scaffold_map.get("present_contract_fields", [])) == list(REQUIRED_ORDER_INTENT_FIELDS)
    required_fields_ok = _as_list(scaffold_map.get("required_contract_fields", [])) == list(REQUIRED_ORDER_INTENT_FIELDS)
    missing_fields_ok = _as_list(scaffold_map.get("missing_contract_fields", [])) == []

    diagnostic_count = _safe_int(preflight_report.get("postmortem_preflight_diagnostic_count"), 0)
    source_counts = _as_dict(preflight_report.get("candidate_detection_source_counts", {}))
    if not diagnostic_count:
        diagnostic_count = sum(_safe_int(v) for v in source_counts.values())
    diagnostic_available = preflight_report.get("postmortem_preflight_diagnostic_available") is True or diagnostic_count > 0

    required_readiness = {
        "u38_postmortem_preflight_report_present": bool(preflight_report),
        "u38_postmortem_preflight_ready": upstream_ready,
        "source_markers_present": source_markers_present,
        "postmortem_execution_scaffold_model_ready": gate_model.get("postmortem_execution_scaffold_model_ready") is True,
        "postmortem_execution_scaffold_gate_model_ready": gate_model.get("postmortem_execution_scaffold_gate_model_ready") is True,
        "present_contract_fields_complete": present_fields_ok,
        "required_contract_fields_complete": required_fields_ok,
        "missing_contract_fields_empty": missing_fields_ok,
        "paper_only_policy_ready": payload.get("paper_only") is True,
        "single_position_policy_ready": payload.get("max_open_positions") == 1,
        "execution_disabled": scaffold_map.get("execution_enabled") is False,
        "mutation_disabled": scaffold_map.get("mutation_enabled") is False,
        "broker_disabled": scaffold_map.get("broker_submit_enabled") is False and scaffold_map.get("broker_close_enabled") is False,
        "scheduler_disabled": scaffold_map.get("scheduler_enabled") is False,
        "telegram_network_disabled": scaffold_map.get("telegram_network_send_enabled") is False,
        "live_testnet_exchange_disabled": True,
        "execution_flags_fail_closed": _all_false(preflight_report, FALSE_EXECUTION_KEYS),
        "postmortem_currently_blocked": gate_model.get("future_postmortem_execution_conditions_satisfied") is False,
        "would_run_postmortem_false": context.get("would_run_postmortem") is False,
        "would_mutate_state_false": context.get("would_mutate_paper_state") is False,
        "would_send_telegram_false": context.get("would_send_telegram") is False,
        "would_start_scheduler_false": context.get("would_start_scheduler") is False,
    }

    blockers = [key for key, ok in required_readiness.items() if not ok]
    if missing_upstream_reports:
        blockers.append("missing_upstream_reports")
    if not_ready_upstream_reports:
        blockers.append("not_ready_upstream_reports")
    if not source_markers_present:
        blockers.append("missing_source_markers")
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    ready = not blockers and settings.fail_closed is True
    status = "PASS" if ready else "KEEP_DIAGNOSTIC"
    decision = READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION
    gate_states = _operator_gate_states(active_env)

    classification_labels = [
        "GENERIC_LSR_V2_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_SCAFFOLD",
        "POSTMORTEM_EXECUTION_SCAFFOLD_ONLY",
        "READ_ONLY_BY_DEFAULT",
        "NO_ORDINAL_EXPANSION",
        "NO_POSTMORTEM_RUNTIME_EXECUTION",
        "NO_FINAL_AUDIT_RUNTIME_EXECUTION",
        "NO_SUBMIT",
        "NO_CLOSE",
        "NO_BROKER_CALL",
        "NO_STATE_MUTATION",
        "NO_NETWORK_SEND",
        "NO_SCHEDULER",
        "FAIL_CLOSED",
        "GENERIC_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_SCAFFOLD_READY" if ready else "GENERIC_SUPERVISED_PAPER_POSTMORTEM_EXECUTION_SCAFFOLD_NOT_READY",
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
        "generic_supervised_paper_postmortem_execution_scaffold_ready": ready,
        "generic_postmortem_execution_scaffold_ready": ready,
        "generic_postmortem_execution_scaffold_model_ready": gate_model.get("postmortem_execution_scaffold_model_ready") is True,
        "generic_postmortem_execution_scaffold_patch_ready": ready,
        "paper_postmortem_execution_scaffold_ready": ready,
        "postmortem_execution_scaffold_diagnostic_available": ready and diagnostic_available,
        "postmortem_execution_scaffold_diagnostic_count": diagnostic_count if ready else 0,
        "postmortem_execution_scaffold_contract_shape_modelable": gate_model.get("postmortem_execution_scaffold_model_ready") is True,
        "postmortem_execution_scaffold_contract_missing_fields": _as_list(scaffold_map.get("missing_contract_fields", [])),
        "postmortem_execution_scaffold_contract_present_fields": _as_list(scaffold_map.get("present_contract_fields", [])),
        "postmortem_execution_scaffold_contract_required_fields": _as_list(scaffold_map.get("required_contract_fields", [])),
        "generic_supervised_paper_postmortem_preflight_ready": preflight_report.get("generic_supervised_paper_postmortem_preflight_ready") is True,
        "generic_postmortem_preflight_ready": preflight_report.get("generic_postmortem_preflight_ready") is True,
        "generic_postmortem_preflight_model_ready": preflight_report.get("generic_postmortem_preflight_model_ready") is True,
        "generic_postmortem_preflight_patch_ready": preflight_report.get("generic_postmortem_preflight_patch_ready") is True,
        "postmortem_preflight_diagnostic_available": diagnostic_available,
        "postmortem_preflight_diagnostic_count": diagnostic_count,
        "final_audit_execution_diagnostic_available": preflight_report.get("final_audit_execution_diagnostic_available") is True,
        "final_audit_execution_diagnostic_count": _safe_int(preflight_report.get("final_audit_execution_diagnostic_count"), diagnostic_count),
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(preflight_report),
        "broker_submit_receipt_available": preflight_report.get("broker_submit_receipt_available") is True,
        "broker_close_receipt_available": preflight_report.get("broker_close_receipt_available") is True,
        "real_close_execution_available": preflight_report.get("real_close_execution_available") is True,
        "paper_position_closed": preflight_report.get("paper_position_closed") is True,
        "realized_pnl_written": preflight_report.get("realized_pnl_written") is True or preflight_report.get("would_write_realized_pnl") is True,
        "paper_realized_pnl_reconciliation_ready": preflight_report.get("paper_realized_pnl_reconciliation_ready") is True,
        "paper_final_audit_ready": preflight_report.get("paper_final_audit_ready") is True,
        "final_audit_runtime_executed": preflight_report.get("final_audit_runtime_executed") is True,
        "paper_position_open": False,
        "paper_open_position_available": False,
        "paper_open_position_monitor_ready": False,
        "close_trigger_available": False,
        "paper_order_intent_runtime_values_present": gate_model.get("runtime_values_present") is True,
        "paper_order_intent_runtime_values_required_before_postmortem_execution": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "paper_close_execution_ready": False,
        "paper_postmortem_ready": False,
        "generic_submit_execution_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_realized_pnl_reconciliation_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
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
        "generic_postmortem_operator_gate_required": True,
        "generic_postmortem_operator_gate_satisfied": gate_states["postmortem"],
        "would_reconcile_realized_pnl": False,
        "would_write_realized_pnl": False,
        "would_run_final_audit": False,
        "would_run_postmortem": False,
        "would_mutate_paper_state": False,
        "would_mutate_paper_status": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
        "would_submit": False,
        "would_close": False,
        "would_call_paper_broker_submit": False,
        "would_call_paper_broker_close": False,
        "generic_supervised_paper_postmortem_execution_scaffold_map": scaffold_map,
        "generic_supervised_paper_postmortem_preflight_map": _as_dict(preflight_report.get("generic_supervised_paper_postmortem_preflight_map", {})),
        "generic_supervised_paper_final_audit_execution_map": _as_dict(preflight_report.get("generic_supervised_paper_final_audit_execution_map", {})),
        "generic_supervised_paper_final_audit_execution_scaffold_map": _as_dict(preflight_report.get("generic_supervised_paper_final_audit_execution_scaffold_map", {})),
        "generic_supervised_paper_final_audit_preflight_map": _as_dict(preflight_report.get("generic_supervised_paper_final_audit_preflight_map", {})),
        "generic_supervised_paper_realized_pnl_reconciliation_preflight_map": _as_dict(preflight_report.get("generic_supervised_paper_realized_pnl_reconciliation_preflight_map", {})),
        "generic_supervised_paper_close_execution_map": _as_dict(preflight_report.get("generic_supervised_paper_close_execution_map", {})),
        "blocked_until_explicit_postmortem_execution_patch": list(BLOCKED_UNTIL_EXPLICIT_POSTMORTEM_EXECUTION_PATCH),
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
        "paper_state_status_consistency": preflight_report.get("paper_state_status_consistency") is True,
        "source_markers_present": source_markers_present,
        "missing_source_files": missing_source_files,
        "missing_source_markers": missing_source_markers,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "eighth_trade_patch_allowed": False,
        "ninth_trade_patch_allowed": False,
        "tenth_trade_patch_allowed": False,
        "paper_state_modified_by_generic_postmortem_execution_scaffold": False,
        "paper_status_modified_by_generic_postmortem_execution_scaffold": False,
        "orders_submitted_by_generic_postmortem_execution_scaffold": 0,
        "positions_opened_by_generic_postmortem_execution_scaffold": 0,
        "positions_closed_by_generic_postmortem_execution_scaffold": 0,
        "broker_submit_called_by_generic_postmortem_execution_scaffold": False,
        "broker_close_called_by_generic_postmortem_execution_scaffold": False,
        "telegram_network_called_by_generic_postmortem_execution_scaffold": False,
        "scheduler_started_by_generic_postmortem_execution_scaffold": False,
    }
    for key in FALSE_EXECUTION_KEYS:
        report[key] = False

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


def main() -> None:
    report = run_generic_supervised_paper_postmortem_execution_scaffold()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
