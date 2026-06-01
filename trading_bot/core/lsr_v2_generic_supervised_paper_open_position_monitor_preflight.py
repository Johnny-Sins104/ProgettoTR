"""Generic LSR-v2 supervised paper open-position monitor preflight.

29.4.4u-30 is intentionally preflight-only, read-only, and fail-closed.
It consumes u-29's supervised paper submit execution artifact and models whether a
future paper open-position monitor could safely run after a real paper broker
submit receipt creates a real open position.

This patch does not monitor positions, does not close positions, does not submit
orders, does not call a broker, does not mutate paper_state/paper_status, does
not start schedulers, and does not send Telegram/network messages. In the
expected validation environment no real submit occurred, no broker receipt
exists, no open position exists, operator gates are absent, and runtime values
are still deferred, so monitor execution remains blocked while the monitor
preflight model is marked ready.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-30"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT_NOT_READY"
U29_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY"

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

OPEN_POSITION_MONITOR_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_submit_execution",
    "verify_submit_execution_model_ready",
    "verify_submit_execution_was_blocked",
    "verify_no_broker_submit_receipt",
    "verify_no_open_position_available",
    "verify_real_order_intent_required_but_absent",
    "verify_submit_candidate_required_but_absent",
    "verify_operator_rearm_and_submit_gates_absent",
    "verify_runtime_values_required_but_absent",
    "verify_monitor_requires_submit_receipt_before_execution",
    "verify_close_execution_still_blocked",
    "verify_single_position_policy",
    "verify_paper_only_policy",
    "verify_flat_locked_state",
    "verify_no_orders_or_positions",
    "verify_no_broker_submit_or_close",
    "verify_no_network_scheduler_or_state_mutation",
    "verify_live_testnet_exchange_disabled",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_open_position_monitor_preflight_gate",
    "publish_generic_open_position_monitor_preflight_artifact",
)

BLOCKED_UNTIL_EXPLICIT_CLOSE_PREFLIGHT_PATCH: Tuple[str, ...] = (
    "generic_open_position_monitor_real",
    "generic_position_status_reconciliation",
    "generic_unrealized_pnl_tracking",
    "generic_stop_take_profit_runtime_monitoring",
    "generic_close_preflight",
    "generic_broker_close",
    "generic_final_audit_execution",
    "generic_postmortem_execution",
    "generic_paper_state_mutation",
    "generic_paper_status_mutation",
    "telegram_network_send",
    "scheduler_start",
    "live_or_testnet_or_exchange_broker",
)

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_submit_execution.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION",
            "generic_supervised_paper_submit_execution_ready",
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
    report_name: str = "lsr_v2_generic_supervised_paper_open_position_monitor_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_open_position_monitor_preflight.jsonl"
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


def _runtime_values_present(payload: Mapping[str, Any]) -> bool:
    for field in REQUIRED_ORDER_INTENT_FIELDS:
        value = payload.get(field)
        if value in (None, "", DEFERRED_SENTINEL):
            return False
    return True


def _dry_run_payload(submit_report: Mapping[str, Any]) -> Dict[str, Any]:
    submit_map = _as_dict(submit_report.get("generic_supervised_paper_submit_execution_map", {}))
    payload = _as_dict(submit_map.get("dry_run_order_intent_payload", {}))
    if payload:
        return payload
    activation_map = _as_dict(submit_report.get("generic_order_intent_activation_map", {}))
    payload = _as_dict(activation_map.get("dry_run_order_intent_payload", {}))
    if payload:
        return payload
    scaffold_map = _as_dict(submit_report.get("generic_submit_execution_scaffold_map", {}))
    return _as_dict(scaffold_map.get("dry_run_order_intent_payload", {}))


def _build_monitor_preflight_map(submit_report: Mapping[str, Any], active_env: Mapping[str, str]) -> Dict[str, Any]:
    payload = _dry_run_payload(submit_report)
    missing_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in payload]
    runtime_values_present = _runtime_values_present(payload)
    rearm_gate_satisfied = (
        active_env.get(REARM_ENABLE_ENV) == "1"
        and active_env.get(REARM_CONFIRMATION_ENV) == REARM_CONFIRMATION_SENTINEL
        and active_env.get(REARM_MAX_POSITIONS_ENV) == "1"
    )
    submit_gate_satisfied = (
        active_env.get(SUBMIT_ENABLE_ENV) == "1"
        and active_env.get(SUBMIT_CONFIRMATION_ENV) == SUBMIT_CONFIRMATION_SENTINEL
    )
    broker_submit_receipt_available = submit_report.get("orders_submitted_by_generic_submit_execution") == 1 and submit_report.get("broker_submit_called_by_generic_submit_execution") is True
    open_position_available = submit_report.get("positions_opened_by_generic_submit_execution") == 1 and submit_report.get("open_positions_after") == 1
    monitor_allowed = (
        broker_submit_receipt_available
        and open_position_available
        and submit_report.get("paper_submit_execution_ready") is True
        and submit_report.get("generic_submit_execution_allowed") is True
        and rearm_gate_satisfied
        and submit_gate_satisfied
        and runtime_values_present
    )
    blocked_reasons: List[str] = []
    if not broker_submit_receipt_available:
        blocked_reasons.append("broker_submit_receipt_absent")
    if not open_position_available:
        blocked_reasons.append("open_position_absent")
    if submit_report.get("paper_submit_execution_ready") is not True:
        blocked_reasons.append("paper_submit_execution_not_ready")
    if submit_report.get("generic_submit_execution_allowed") is not True:
        blocked_reasons.append("submit_execution_not_allowed")
    if not rearm_gate_satisfied:
        blocked_reasons.append("operator_rearm_gate_not_satisfied")
    if not submit_gate_satisfied:
        blocked_reasons.append("operator_submit_gate_not_satisfied")
    if not runtime_values_present:
        blocked_reasons.append("runtime_values_absent_or_deferred")

    return {
        "mode": "generic_supervised_paper_open_position_monitor_preflight_only",
        "preflight_source": "29.4.4u-29",
        "preflight_only": True,
        "read_only": True,
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
        "present_contract_fields": [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload],
        "missing_contract_fields": missing_fields,
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in OPEN_POSITION_MONITOR_PREFLIGHT_STAGES
        ],
        "monitor_preflight_context": {
            "blocked_reason": "open_position_monitor_blocked_until_real_submit_receipt_and_open_position",
            "generic_open_position_monitor_preflight_ready": True,
            "paper_open_position_monitor_preflight_ready": True,
            "broker_submit_receipt_available": broker_submit_receipt_available,
            "open_position_available": open_position_available,
            "paper_position_open": False,
            "paper_order_intent_materialized": False,
            "paper_order_intent_persisted": False,
            "paper_order_intent_ready": False,
            "paper_submit_candidate_ready": False,
            "paper_submit_execution_ready": False,
            "generic_submit_execution_allowed": False,
            "generic_open_position_monitor_allowed": False,
            "paper_open_position_monitor_ready": False,
            "would_monitor_open_position": False,
            "would_reconcile_position": False,
            "would_trigger_stop_loss": False,
            "would_trigger_take_profit": False,
            "would_call_paper_broker_close": False,
            "would_close": False,
            "would_submit": False,
        },
        "open_position_monitor_gate_model": {
            "monitor_preflight_model_ready": True,
            "monitor_execution_allowed": monitor_allowed,
            "monitor_execution_blocked_reasons": blocked_reasons,
            "broker_submit_receipt_required": True,
            "broker_submit_receipt_available": broker_submit_receipt_available,
            "paper_open_position_required": True,
            "paper_open_position_available": open_position_available,
            "paper_submit_execution_ready_required": True,
            "paper_submit_execution_ready": submit_report.get("paper_submit_execution_ready") is True,
            "real_paper_order_intent_required": True,
            "real_paper_order_intent_ready": submit_report.get("paper_order_intent_ready") is True,
            "paper_order_intent_persisted_required": True,
            "paper_order_intent_persisted": submit_report.get("paper_order_intent_persisted") is True,
            "paper_submit_candidate_required": True,
            "paper_submit_candidate_ready": submit_report.get("paper_submit_candidate_ready") is True,
            "operator_rearm_gate_required": True,
            "operator_rearm_gate_satisfied": rearm_gate_satisfied,
            "operator_submit_gate_required": True,
            "operator_submit_gate_satisfied": submit_gate_satisfied,
            "runtime_values_required_before_monitor": True,
            "runtime_values_present": runtime_values_present,
            "max_open_positions": 1,
            "max_open_positions_valid": payload.get("max_open_positions") == 1,
            "paper_only": payload.get("paper_only") is True,
            "paper_only_valid": payload.get("paper_only") is True,
            "close_execution_allowed": False,
            "broker_close_allowed": False,
            "state_mutation_allowed_during_preflight": False,
            "missing_model_fields": missing_fields,
            "present_model_fields": [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload],
            "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        },
        "source_submit_execution_map": _as_dict(submit_report.get("generic_supervised_paper_submit_execution_map", {})),
        "required_future_controls_before_close_preflight": {
            "broker_submit_receipt_required_before_monitor": True,
            "open_position_required_before_monitor": True,
            "explicit_generic_open_position_monitor_patch_required": True,
            "explicit_generic_close_preflight_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "runtime_value_validation_required": True,
            "runtime_values_required": True,
            "paper_only_required": True,
            "max_open_positions": 1,
            "live_testnet_exchange_required_off": True,
        },
    }


def run_generic_supervised_paper_open_position_monitor_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_supervised_paper_submit_execution_report.json"
    submit_report = _read_json(data_path / upstream_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not submit_report:
        missing_upstream_reports.append(upstream_name)
    elif submit_report.get("decision") != U29_READY_DECISION:
        not_ready_upstream_reports.append(upstream_name)

    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    active_env = _active_lsr_env()
    monitor_map = _build_monitor_preflight_map(submit_report, active_env)
    gate_model = _as_dict(monitor_map.get("open_position_monitor_gate_model", {}))
    context = _as_dict(monitor_map.get("monitor_preflight_context", {}))

    source_counts = _as_dict(submit_report.get("candidate_detection_source_counts", {}))
    diagnostic_count = _safe_int(submit_report.get("submit_execution_diagnostic_count"), 0) or _safe_int(
        submit_report.get("order_intent_activation_diagnostic_count"), 0
    )
    upstream_diagnostic_available = submit_report.get("submit_execution_diagnostic_available") is True
    present_fields_ok = _as_list(monitor_map.get("present_contract_fields", [])) == list(REQUIRED_ORDER_INTENT_FIELDS)
    required_fields_ok = _as_list(monitor_map.get("required_contract_fields", [])) == list(REQUIRED_ORDER_INTENT_FIELDS)
    missing_fields_ok = _as_list(monitor_map.get("missing_contract_fields", [])) == []
    rearm_gate_satisfied = gate_model.get("operator_rearm_gate_satisfied") is True
    submit_gate_satisfied = gate_model.get("operator_submit_gate_satisfied") is True
    runtime_values_present = gate_model.get("runtime_values_present") is True
    broker_submit_receipt_available = gate_model.get("broker_submit_receipt_available") is True
    open_position_available = gate_model.get("paper_open_position_available") is True
    monitor_execution_allowed = gate_model.get("monitor_execution_allowed") is True

    required_readiness = {
        "submit_execution_report_ready": submit_report.get("generic_supervised_paper_submit_execution_ready") is True,
        "generic_submit_execution_model_ready": submit_report.get("generic_supervised_paper_submit_execution_model_ready") is True,
        "generic_submit_execution_patch_ready": submit_report.get("generic_submit_execution_patch_ready") is True,
        "submit_execution_diagnostic_available": upstream_diagnostic_available,
        "submit_execution_contract_shape_modelable": submit_report.get("submit_execution_contract_shape_modelable") is True,
        "open_position_monitor_preflight_model_ready": gate_model.get("monitor_preflight_model_ready") is True,
        "broker_submit_receipt_required": True,
        "broker_submit_receipt_absent": not broker_submit_receipt_available,
        "paper_open_position_required": True,
        "paper_open_position_absent": not open_position_available,
        "monitor_execution_blocked": not monitor_execution_allowed,
        "close_execution_blocked": gate_model.get("close_execution_allowed") is False,
        "broker_close_disabled": gate_model.get("broker_close_allowed") is False,
        "paper_submit_execution_not_ready": submit_report.get("paper_submit_execution_ready") is False,
        "paper_submit_candidate_not_ready": submit_report.get("paper_submit_candidate_ready") is False,
        "real_order_intent_not_ready": submit_report.get("paper_order_intent_ready") is False,
        "order_intent_not_materialized": submit_report.get("paper_order_intent_materialized") is False,
        "order_intent_not_persisted": submit_report.get("paper_order_intent_persisted") is False,
        "operator_rearm_gate_required": True,
        "operator_rearm_gate_not_satisfied": not rearm_gate_satisfied,
        "operator_submit_gate_required": True,
        "operator_submit_gate_not_satisfied": not submit_gate_satisfied,
        "runtime_values_required_before_monitor": True,
        "runtime_values_not_present": not runtime_values_present,
        "runtime_validation_deferred": submit_report.get("paper_order_intent_runtime_value_validation_deferred") is True,
        "runtime_validation_not_executed": submit_report.get("paper_order_intent_runtime_value_validation_executed") is False,
        "no_broker_call": (
            submit_report.get("broker_submit_called_by_generic_submit_execution") is False
            and submit_report.get("broker_close_called_by_generic_submit_execution") is False
        ),
        "no_submit_or_close_occurred": (
            submit_report.get("orders_submitted_by_generic_submit_execution") == 0
            and submit_report.get("positions_opened_by_generic_submit_execution") == 0
            and submit_report.get("positions_closed_by_generic_submit_execution") == 0
        ),
        "no_state_mutation": (
            submit_report.get("paper_state_modified_by_generic_submit_execution") is False
            and submit_report.get("paper_status_modified_by_generic_submit_execution") is False
        ),
        "flat_locked_state": submit_report.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": submit_report.get("open_positions_after") == 0,
        "pending_orders_clear": submit_report.get("pending_orders_after") == 0,
        "single_position_policy_ready": True,
        "paper_only_policy_ready": True,
        "no_existing_route_candidate": submit_report.get("route_candidate_available") is False,
        "no_existing_handoff_candidate": submit_report.get("handoff_candidate_available") is False,
        "operator_env_absent": len(active_env) == 0,
        "live_disabled": submit_report.get("live_enabled") is False,
        "testnet_disabled": submit_report.get("testnet_enabled") is False,
        "exchange_broker_disabled": submit_report.get("exchange_broker_enabled") is False,
        "present_contract_fields_complete": present_fields_ok,
        "required_contract_fields_complete": required_fields_ok,
        "missing_contract_fields_empty": missing_fields_ok,
        "source_markers_present": source_markers_present,
        "execution_flags_fail_closed": _all_false(submit_report, FALSE_EXECUTION_KEYS),
        "would_monitor_open_position_false": context.get("would_monitor_open_position") is False,
        "would_call_paper_broker_close_false": context.get("would_call_paper_broker_close") is False,
        "would_close_false": context.get("would_close") is False,
        "would_submit_false": context.get("would_submit") is False,
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
        "GENERIC_LSR_V2_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT",
        "PREFLIGHT_ONLY",
        "READ_ONLY",
        "NO_ORDINAL_EXPANSION",
        "NO_REAL_OPEN_POSITION_AVAILABLE",
        "NO_MONITOR_EXECUTION",
        "NO_SUBMIT",
        "NO_CLOSE",
        "NO_BROKER_CALL",
        "NO_STATE_MUTATION",
        "NO_NETWORK_SEND",
        "NO_SCHEDULER",
        "FAIL_CLOSED",
        "BROKER_SUBMIT_RECEIPT_REQUIRED",
        "OPEN_POSITION_REQUIRED",
        "GENERIC_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT_READY" if ready else "GENERIC_SUPERVISED_PAPER_OPEN_POSITION_MONITOR_PREFLIGHT_NOT_READY",
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
        "upstream_reports_present": [] if not submit_report else [upstream_name],
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "generic_supervised_paper_open_position_monitor_preflight_ready": ready,
        "generic_open_position_monitor_preflight_ready": ready,
        "paper_open_position_monitor_preflight_ready": ready,
        "generic_open_position_monitor_preflight_model_ready": gate_model.get("monitor_preflight_model_ready") is True,
        "generic_open_position_monitor_preflight_plan_ready": ready,
        "generic_open_position_monitor_preflight_map_ready": ready,
        "generic_open_position_monitor_preflight_contract_ready": ready,
        "generic_open_position_monitor_preflight_fail_closed_ready": ready,
        "generic_open_position_monitor_preflight_source_files_present": not missing_source_files,
        "generic_open_position_monitor_preflight_required_markers_present": not missing_source_markers,
        "open_position_monitor_preflight_diagnostic_available": ready,
        "open_position_monitor_preflight_diagnostic_count": diagnostic_count if ready else 0,
        "open_position_monitor_contract_shape_modelable": gate_model.get("monitor_preflight_model_ready") is True,
        "open_position_monitor_contract_missing_fields": _as_list(monitor_map.get("missing_contract_fields", [])),
        "open_position_monitor_contract_present_fields": _as_list(monitor_map.get("present_contract_fields", [])),
        "open_position_monitor_contract_required_fields": _as_list(monitor_map.get("required_contract_fields", [])),
        "generic_supervised_paper_submit_execution_ready": submit_report.get("generic_supervised_paper_submit_execution_ready") is True,
        "generic_supervised_paper_submit_execution_model_ready": submit_report.get("generic_supervised_paper_submit_execution_model_ready") is True,
        "generic_supervised_paper_submit_execution_patch_ready": submit_report.get("generic_supervised_paper_submit_execution_patch_ready") is True,
        "generic_submit_execution_patch_ready": submit_report.get("generic_submit_execution_patch_ready") is True,
        "generic_submit_execution_gate_model_ready": submit_report.get("generic_submit_execution_gate_model_ready") is True,
        "paper_submit_execution_model_ready": submit_report.get("paper_submit_execution_model_ready") is True,
        "paper_submit_execution_gate_model_ready": submit_report.get("paper_submit_execution_gate_model_ready") is True,
        "submit_execution_diagnostic_available": upstream_diagnostic_available,
        "submit_execution_diagnostic_count": diagnostic_count,
        "submit_execution_contract_shape_modelable": submit_report.get("submit_execution_contract_shape_modelable") is True,
        "generic_supervised_paper_order_intent_activation_ready": submit_report.get("generic_supervised_paper_order_intent_activation_ready") is True,
        "generic_order_intent_activation_model_ready": submit_report.get("generic_order_intent_activation_model_ready") is True,
        "order_intent_activation_diagnostic_available": submit_report.get("order_intent_activation_diagnostic_available") is True,
        "order_intent_activation_diagnostic_count": _safe_int(submit_report.get("order_intent_activation_diagnostic_count"), 0),
        "submit_candidate_audit_diagnostic_available": submit_report.get("submit_candidate_audit_diagnostic_available") is True,
        "submit_candidate_audit_diagnostic_count": _safe_int(submit_report.get("submit_candidate_audit_diagnostic_count"), 0),
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(submit_report),
        "broker_submit_receipt_available": broker_submit_receipt_available,
        "paper_open_position_required_before_monitor": True,
        "paper_open_position_available": open_position_available,
        "paper_position_open": False,
        "paper_order_intent_runtime_values_present": runtime_values_present,
        "paper_order_intent_runtime_values_required_before_monitor": True,
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
        "generic_submit_execution_allowed": False,
        "paper_broker_submit_allowed": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": rearm_gate_satisfied,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": submit_gate_satisfied,
        "generic_open_position_monitor_allowed": False,
        "paper_open_position_monitor_ready": False,
        "generic_close_execution_allowed": False,
        "paper_close_execution_ready": False,
        "broker_close_allowed": False,
        "would_materialize_order_intent_dry_run": submit_report.get("would_materialize_order_intent_dry_run") is True and ready,
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
        "would_monitor_open_position": False,
        "would_reconcile_position": False,
        "would_trigger_stop_loss": False,
        "would_trigger_take_profit": False,
        "would_call_paper_broker_close": False,
        "would_close": False,
        "paper_open_position_monitor_blocked_reason": "open_position_monitor_blocked_until_real_submit_receipt_and_open_position",
        "paper_close_execution_blocked_reason": "close_execution_not_allowed_open_position_monitor_preflight_only",
        "generic_open_position_monitor_blocked_reason": "open_position_monitor_not_allowed_without_submit_receipt_and_open_position",
        "generic_supervised_paper_open_position_monitor_preflight_map": monitor_map,
        "generic_supervised_paper_submit_execution_map": _as_dict(submit_report.get("generic_supervised_paper_submit_execution_map", {})),
        "generic_order_intent_activation_map": _as_dict(submit_report.get("generic_order_intent_activation_map", {})),
        "blocked_until_explicit_close_preflight_patch": list(BLOCKED_UNTIL_EXPLICIT_CLOSE_PREFLIGHT_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": submit_report.get("lifecycle_state", ""),
        "fourth_trade_locked": submit_report.get("fourth_trade_locked") is True,
        "stability_lock_active": submit_report.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "no_route_candidate": True,
        "no_handoff_candidate": True,
        "no_order_intent_currently_available": True,
        "paper_state_status_consistency": submit_report.get("paper_state_status_consistency") is True,
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
        "paper_state_modified_by_generic_open_position_monitor_preflight": False,
        "paper_status_modified_by_generic_open_position_monitor_preflight": False,
        "orders_submitted_by_generic_open_position_monitor_preflight": 0,
        "positions_opened_by_generic_open_position_monitor_preflight": 0,
        "positions_closed_by_generic_open_position_monitor_preflight": 0,
        "broker_submit_called_by_generic_open_position_monitor_preflight": False,
        "broker_close_called_by_generic_open_position_monitor_preflight": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "missing_generic_open_position_monitor_preflight_source_files": missing_source_files,
        "missing_generic_open_position_monitor_preflight_source_markers": missing_source_markers,
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
        "recommended_next_patch": "29.4.4u-31 — Generic LSR-v2 supervised paper close preflight",
        "next_step": "prepare_generic_supervised_paper_close_preflight_or_continue_observation",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "FALSE_EXECUTION_KEYS",
    "KEEP_DIAGNOSTIC_DECISION",
    "READY_DECISION",
    "Settings",
    "run_generic_supervised_paper_open_position_monitor_preflight",
]
