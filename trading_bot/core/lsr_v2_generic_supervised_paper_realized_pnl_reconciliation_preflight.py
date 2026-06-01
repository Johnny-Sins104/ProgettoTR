"""Generic LSR-v2 supervised paper realized-PnL reconciliation preflight.

29.4.4u-34 is intentionally preflight-only, read-only, and fail-closed. It
consumes u-33's supervised paper close execution artifact and models the future
requirements for reconciling realized PnL after a real paper close.

The expected validation state still has no broker submit receipt, no open paper
position, no close trigger, no broker close receipt, no real close execution, no
runtime values, and no operator gates. Therefore this patch must return a
PASS/ready diagnostic for the reconciliation preflight model while keeping real
PnL reconciliation, final audit, postmortem, broker calls, state mutation,
scheduler startup, Telegram/network sending, and live/testnet/exchange access
blocked.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-34"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT_NOT_READY"
U33_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_CLOSE_EXECUTION_READY"

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
CLOSE_MAX_POSITIONS_ENV = "LSR_V2_GENERIC_CLOSE_MAX_POSITIONS"
PNL_ENABLE_ENV = "LSR_V2_GENERIC_REALIZED_PNL_RECONCILIATION_ENABLE"
PNL_CONFIRMATION_ENV = "LSR_V2_GENERIC_REALIZED_PNL_RECONCILIATION_CONFIRMATION"
PNL_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_REALIZED_PNL_RECONCILIATION_ONLY"

REALIZED_PNL_RECONCILIATION_PREFLIGHT_STAGES: Tuple[str, ...] = (
    "load_generic_close_execution",
    "verify_close_execution_ready",
    "verify_close_execution_was_blocked",
    "verify_no_broker_close_receipt",
    "verify_no_real_close_execution_available",
    "verify_no_closed_position_available",
    "verify_realized_pnl_reconciliation_requires_close_receipt",
    "verify_realized_pnl_operator_gate_required_but_absent",
    "verify_runtime_values_required_but_absent",
    "verify_pnl_reconciliation_guard_disabled",
    "verify_final_audit_and_postmortem_blocked",
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
    "map_realized_pnl_reconciliation_preflight_gate",
    "publish_generic_realized_pnl_reconciliation_preflight_artifact",
)

BLOCKED_UNTIL_EXPLICIT_FINAL_AUDIT_PATCH: Tuple[str, ...] = (
    "generic_realized_pnl_reconciliation_real",
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
        "trading_bot/core/lsr_v2_generic_supervised_paper_close_execution.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION",
            "generic_supervised_paper_close_execution_ready",
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
    report_name: str = "lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_supervised_paper_realized_pnl_reconciliation_preflight.jsonl"
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


def _dry_run_payload(close_report: Mapping[str, Any]) -> Dict[str, Any]:
    close_map = _as_dict(close_report.get("generic_supervised_paper_close_execution_map", {}))
    payload = _as_dict(close_map.get("dry_run_order_intent_payload", {}))
    if payload:
        return payload
    scaffold_map = _as_dict(close_report.get("generic_supervised_paper_close_execution_scaffold_map", {}))
    return _as_dict(scaffold_map.get("dry_run_order_intent_payload", {}))


def _gate_status(active_env: Mapping[str, str]) -> Tuple[bool, bool, bool, bool]:
    rearm = (
        active_env.get(REARM_ENABLE_ENV) == "1"
        and active_env.get(REARM_CONFIRMATION_ENV) == REARM_CONFIRMATION_SENTINEL
        and active_env.get(REARM_MAX_POSITIONS_ENV) == "1"
    )
    submit = active_env.get(SUBMIT_ENABLE_ENV) == "1" and active_env.get(SUBMIT_CONFIRMATION_ENV) == SUBMIT_CONFIRMATION_SENTINEL
    close = (
        active_env.get(CLOSE_ENABLE_ENV) == "1"
        and active_env.get(CLOSE_CONFIRMATION_ENV) == CLOSE_CONFIRMATION_SENTINEL
        and active_env.get(CLOSE_MAX_POSITIONS_ENV) == "1"
    )
    pnl = active_env.get(PNL_ENABLE_ENV) == "1" and active_env.get(PNL_CONFIRMATION_ENV) == PNL_CONFIRMATION_SENTINEL
    return rearm, submit, close, pnl


def _build_realized_pnl_preflight_map(close_report: Mapping[str, Any], active_env: Mapping[str, str]) -> Dict[str, Any]:
    payload = _dry_run_payload(close_report)
    missing_fields = [field for field in REQUIRED_ORDER_INTENT_FIELDS if field not in payload]
    runtime_values_present = _runtime_values_present(payload)
    rearm_gate_satisfied, submit_gate_satisfied, close_gate_satisfied, pnl_gate_satisfied = _gate_status(active_env)

    close_execution_ready = close_report.get("generic_supervised_paper_close_execution_ready") is True
    close_execution_allowed = close_report.get("generic_close_execution_allowed") is True
    broker_submit_receipt_available = close_report.get("broker_submit_receipt_available") is True
    broker_close_receipt_available = close_report.get("broker_close_receipt_available") is True
    broker_close_called = close_report.get("broker_close_called_by_generic_close_execution") is True
    real_close_execution_available = close_execution_allowed and broker_close_called and broker_close_receipt_available
    position_closed = _safe_int(close_report.get("positions_closed_by_generic_close_execution"), 0) > 0
    state_mutation_allowed = close_report.get("generic_paper_state_mutation_allowed") is True

    reconciliation_allowed = (
        close_execution_ready
        and real_close_execution_available
        and broker_submit_receipt_available
        and broker_close_receipt_available
        and position_closed
        and rearm_gate_satisfied
        and submit_gate_satisfied
        and close_gate_satisfied
        and pnl_gate_satisfied
        and runtime_values_present
    )

    blocked_reasons: List[str] = []
    if not close_execution_ready:
        blocked_reasons.append("close_execution_report_not_ready")
    if not close_execution_allowed:
        blocked_reasons.append("real_close_execution_not_allowed")
    if not broker_submit_receipt_available:
        blocked_reasons.append("broker_submit_receipt_absent")
    if not broker_close_receipt_available:
        blocked_reasons.append("broker_close_receipt_absent")
    if not broker_close_called:
        blocked_reasons.append("broker_close_not_called")
    if not position_closed:
        blocked_reasons.append("closed_position_absent")
    if not rearm_gate_satisfied:
        blocked_reasons.append("operator_rearm_gate_not_satisfied")
    if not submit_gate_satisfied:
        blocked_reasons.append("operator_submit_gate_not_satisfied")
    if not close_gate_satisfied:
        blocked_reasons.append("operator_close_gate_not_satisfied")
    if not pnl_gate_satisfied:
        blocked_reasons.append("operator_realized_pnl_gate_not_satisfied")
    if not runtime_values_present:
        blocked_reasons.append("runtime_values_absent_or_deferred")
    if state_mutation_allowed:
        blocked_reasons.append("state_mutation_unexpectedly_allowed")

    return {
        "mode": "generic_supervised_paper_realized_pnl_reconciliation_preflight_only",
        "preflight_source": "29.4.4u-33",
        "realized_pnl_reconciliation_preflight_patch": True,
        "preflight_only": True,
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
        "present_contract_fields": [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload],
        "missing_contract_fields": missing_fields,
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in REALIZED_PNL_RECONCILIATION_PREFLIGHT_STAGES
        ],
        "realized_pnl_reconciliation_preflight_context": {
            "blocked_reason": "realized_pnl_reconciliation_blocked_until_real_close_receipt_and_closed_position",
            "generic_supervised_paper_realized_pnl_reconciliation_preflight_ready": True,
            "generic_realized_pnl_reconciliation_preflight_ready": True,
            "paper_realized_pnl_reconciliation_preflight_ready": True,
            "close_execution_ready": close_execution_ready,
            "real_close_execution_available": real_close_execution_available,
            "broker_submit_receipt_available": broker_submit_receipt_available,
            "broker_close_receipt_available": broker_close_receipt_available,
            "paper_position_closed": position_closed,
            "generic_realized_pnl_reconciliation_allowed": False,
            "paper_realized_pnl_reconciliation_ready": False,
            "would_reconcile_realized_pnl": False,
            "would_write_realized_pnl": False,
            "would_run_final_audit": False,
            "would_run_postmortem": False,
            "would_mutate_paper_state": False,
            "would_mutate_paper_status": False,
            "would_submit": False,
            "would_close": False,
        },
        "realized_pnl_reconciliation_gate_model": {
            "realized_pnl_reconciliation_preflight_model_ready": True,
            "realized_pnl_reconciliation_allowed": reconciliation_allowed,
            "realized_pnl_reconciliation_blocked_reasons": blocked_reasons,
            "close_execution_report_required": True,
            "close_execution_ready": close_execution_ready,
            "real_close_execution_required": True,
            "real_close_execution_available": real_close_execution_available,
            "broker_submit_receipt_required": True,
            "broker_submit_receipt_available": broker_submit_receipt_available,
            "broker_close_receipt_required": True,
            "broker_close_receipt_available": broker_close_receipt_available,
            "closed_position_required": True,
            "paper_position_closed": position_closed,
            "operator_rearm_gate_required": True,
            "operator_rearm_gate_satisfied": rearm_gate_satisfied,
            "operator_submit_gate_required": True,
            "operator_submit_gate_satisfied": submit_gate_satisfied,
            "operator_close_gate_required": True,
            "operator_close_gate_satisfied": close_gate_satisfied,
            "operator_realized_pnl_gate_required": True,
            "operator_realized_pnl_gate_satisfied": pnl_gate_satisfied,
            "runtime_values_required_before_realized_pnl_reconciliation": True,
            "runtime_values_present": runtime_values_present,
            "max_open_positions": 1,
            "max_open_positions_valid": payload.get("max_open_positions") == 1,
            "paper_only": payload.get("paper_only") is True,
            "paper_only_valid": payload.get("paper_only") is True,
            "state_mutation_allowed_during_preflight": False,
            "final_audit_execution_allowed": False,
            "postmortem_execution_allowed": False,
            "missing_model_fields": missing_fields,
            "present_model_fields": [field for field in REQUIRED_ORDER_INTENT_FIELDS if field in payload],
            "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        },
        "source_close_execution_map": _as_dict(close_report.get("generic_supervised_paper_close_execution_map", {})),
        "required_future_controls_before_final_audit": {
            "broker_close_receipt_required_before_final_audit": True,
            "realized_pnl_reconciliation_required_before_final_audit": True,
            "explicit_generic_final_audit_preflight_patch_required": True,
            "generic_realized_pnl_operator_gate_required": True,
            "generic_close_operator_gate_required": True,
            "generic_rearm_operator_gate_required": True,
            "generic_submit_operator_gate_required": True,
            "live_testnet_exchange_required_off": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "runtime_value_validation_required": True,
            "runtime_values_required": True,
        },
    }


def run_generic_supervised_paper_realized_pnl_reconciliation_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_supervised_paper_close_execution_report.json"
    close_report = _read_json(data_path / upstream_name)
    active_env = _active_lsr_env()
    preflight_map = _build_realized_pnl_preflight_map(close_report, active_env)
    gate_model = _as_dict(preflight_map.get("realized_pnl_reconciliation_gate_model", {}))
    context = _as_dict(preflight_map.get("realized_pnl_reconciliation_preflight_context", {}))

    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    payload = _dry_run_payload(close_report)
    present_fields_ok = set(preflight_map.get("present_contract_fields", [])) == set(REQUIRED_ORDER_INTENT_FIELDS)
    required_fields_ok = set(preflight_map.get("required_contract_fields", [])) == set(REQUIRED_ORDER_INTENT_FIELDS)
    missing_fields_ok = preflight_map.get("missing_contract_fields", []) == []
    diagnostic_count = _safe_int(close_report.get("close_execution_diagnostic_count"), 0)
    diagnostic_available = close_report.get("close_execution_diagnostic_available") is True

    missing_upstream_reports: List[str] = [] if close_report else [upstream_name]
    not_ready_upstream_reports: List[str] = []
    if close_report and (
        close_report.get("status") != "PASS"
        or close_report.get("decision") != U33_READY_DECISION
        or close_report.get("generic_supervised_paper_close_execution_ready") is not True
    ):
        not_ready_upstream_reports.append(upstream_name)

    broker_submit_receipt_available = close_report.get("broker_submit_receipt_available") is True
    broker_close_receipt_available = close_report.get("broker_close_receipt_available") is True
    broker_close_called = close_report.get("broker_close_called_by_generic_close_execution") is True
    real_close_execution_available = gate_model.get("real_close_execution_available") is True
    paper_position_closed = gate_model.get("paper_position_closed") is True
    reconciliation_allowed = gate_model.get("realized_pnl_reconciliation_allowed") is True
    rearm_gate_satisfied = gate_model.get("operator_rearm_gate_satisfied") is True
    submit_gate_satisfied = gate_model.get("operator_submit_gate_satisfied") is True
    close_gate_satisfied = gate_model.get("operator_close_gate_satisfied") is True
    pnl_gate_satisfied = gate_model.get("operator_realized_pnl_gate_satisfied") is True
    runtime_values_present = gate_model.get("runtime_values_present") is True
    source_counts = _as_dict(close_report.get("candidate_detection_source_counts", {}))

    required_readiness = {
        "upstream_close_execution_ready": close_report.get("generic_supervised_paper_close_execution_ready") is True,
        "realized_pnl_reconciliation_preflight_model_ready": gate_model.get("realized_pnl_reconciliation_preflight_model_ready") is True,
        "realized_pnl_reconciliation_blocked_until_real_close_receipt": not reconciliation_allowed,
        "broker_submit_receipt_absent": not broker_submit_receipt_available,
        "broker_close_receipt_absent": not broker_close_receipt_available,
        "broker_close_not_called": not broker_close_called,
        "real_close_execution_absent": not real_close_execution_available,
        "closed_position_absent": not paper_position_closed,
        "operator_rearm_gate_required": True,
        "operator_rearm_gate_not_satisfied": not rearm_gate_satisfied,
        "operator_submit_gate_required": True,
        "operator_submit_gate_not_satisfied": not submit_gate_satisfied,
        "operator_close_gate_required": True,
        "operator_close_gate_not_satisfied": not close_gate_satisfied,
        "operator_realized_pnl_gate_required": True,
        "operator_realized_pnl_gate_not_satisfied": not pnl_gate_satisfied,
        "runtime_values_required_before_realized_pnl_reconciliation": True,
        "runtime_values_not_present": not runtime_values_present,
        "runtime_validation_deferred": close_report.get("paper_order_intent_runtime_value_validation_deferred") is True,
        "runtime_validation_not_executed": close_report.get("paper_order_intent_runtime_value_validation_executed") is False,
        "no_broker_call": (
            close_report.get("broker_submit_called_by_generic_close_execution") is False
            and close_report.get("broker_close_called_by_generic_close_execution") is False
        ),
        "no_submit_or_close_occurred": (
            close_report.get("orders_submitted_by_generic_close_execution") == 0
            and close_report.get("positions_opened_by_generic_close_execution") == 0
            and close_report.get("positions_closed_by_generic_close_execution") == 0
        ),
        "no_state_mutation": (
            close_report.get("paper_state_modified_by_generic_close_execution") is False
            and close_report.get("paper_status_modified_by_generic_close_execution") is False
        ),
        "realized_pnl_reconciliation_still_blocked": close_report.get("would_reconcile_realized_pnl") is False,
        "final_audit_execution_blocked": close_report.get("generic_final_audit_execution_allowed") is False,
        "postmortem_execution_blocked": close_report.get("generic_postmortem_execution_allowed") is False,
        "flat_locked_state": close_report.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": close_report.get("open_positions_after") == 0,
        "pending_orders_clear": close_report.get("pending_orders_after") == 0,
        "single_position_policy_ready": True,
        "paper_only_policy_ready": payload.get("paper_only") is True,
        "operator_env_absent": len(active_env) == 0,
        "live_disabled": close_report.get("live_enabled") is False,
        "testnet_disabled": close_report.get("testnet_enabled") is False,
        "exchange_broker_disabled": close_report.get("exchange_broker_enabled") is False,
        "present_contract_fields_complete": present_fields_ok,
        "required_contract_fields_complete": required_fields_ok,
        "missing_contract_fields_empty": missing_fields_ok,
        "source_markers_present": source_markers_present,
        "execution_flags_fail_closed": _all_false(close_report, FALSE_EXECUTION_KEYS),
        "would_reconcile_realized_pnl_false": context.get("would_reconcile_realized_pnl") is False,
        "would_run_final_audit_false": context.get("would_run_final_audit") is False,
        "would_run_postmortem_false": context.get("would_run_postmortem") is False,
        "would_submit_false": context.get("would_submit") is False,
        "would_close_false": context.get("would_close") is False,
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
        "GENERIC_LSR_V2_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT",
        "REALIZED_PNL_RECONCILIATION_PREFLIGHT_ONLY",
        "READ_ONLY_BY_DEFAULT",
        "NO_ORDINAL_EXPANSION",
        "NO_REAL_CLOSE_EXECUTION_AVAILABLE",
        "NO_BROKER_CLOSE_RECEIPT_AVAILABLE",
        "NO_REALIZED_PNL_RECONCILIATION",
        "NO_FINAL_AUDIT",
        "NO_POSTMORTEM",
        "NO_SUBMIT",
        "NO_CLOSE",
        "NO_BROKER_CALL",
        "NO_STATE_MUTATION",
        "NO_NETWORK_SEND",
        "NO_SCHEDULER",
        "FAIL_CLOSED",
        "GENERIC_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT_READY" if ready else "GENERIC_SUPERVISED_PAPER_REALIZED_PNL_RECONCILIATION_PREFLIGHT_NOT_READY",
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
        "upstream_reports_present": [] if not close_report else [upstream_name],
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "generic_supervised_paper_realized_pnl_reconciliation_preflight_ready": ready,
        "generic_realized_pnl_reconciliation_preflight_ready": ready,
        "paper_realized_pnl_reconciliation_preflight_ready": ready,
        "generic_realized_pnl_reconciliation_preflight_model_ready": gate_model.get("realized_pnl_reconciliation_preflight_model_ready") is True,
        "generic_realized_pnl_reconciliation_preflight_patch_ready": ready,
        "realized_pnl_reconciliation_preflight_diagnostic_available": ready,
        "realized_pnl_reconciliation_preflight_diagnostic_count": diagnostic_count if ready else 0,
        "realized_pnl_reconciliation_contract_shape_modelable": gate_model.get("realized_pnl_reconciliation_preflight_model_ready") is True,
        "realized_pnl_reconciliation_contract_missing_fields": _as_list(preflight_map.get("missing_contract_fields", [])),
        "realized_pnl_reconciliation_contract_present_fields": _as_list(preflight_map.get("present_contract_fields", [])),
        "realized_pnl_reconciliation_contract_required_fields": _as_list(preflight_map.get("required_contract_fields", [])),
        "generic_supervised_paper_close_execution_ready": close_report.get("generic_supervised_paper_close_execution_ready") is True,
        "generic_close_execution_patch_ready": close_report.get("generic_close_execution_patch_ready") is True,
        "generic_close_execution_gate_model_ready": close_report.get("generic_close_execution_gate_model_ready") is True,
        "close_execution_diagnostic_available": diagnostic_available,
        "close_execution_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(close_report),
        "broker_submit_receipt_available": broker_submit_receipt_available,
        "broker_close_receipt_available": broker_close_receipt_available,
        "real_close_execution_available": real_close_execution_available,
        "paper_position_closed": paper_position_closed,
        "paper_position_open": False,
        "paper_open_position_available": False,
        "paper_open_position_monitor_ready": False,
        "close_trigger_available": False,
        "paper_order_intent_runtime_values_present": runtime_values_present,
        "paper_order_intent_runtime_values_required_before_realized_pnl_reconciliation": True,
        "paper_order_intent_runtime_value_validation_executed": False,
        "paper_order_intent_runtime_value_validation_deferred": True,
        "paper_order_intent_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "paper_submit_candidate_ready": False,
        "paper_submit_execution_ready": False,
        "paper_close_execution_ready": False,
        "generic_submit_execution_allowed": False,
        "generic_close_execution_allowed": False,
        "broker_close_allowed": False,
        "generic_rearm_operator_gate_required": True,
        "generic_rearm_operator_gate_satisfied": rearm_gate_satisfied,
        "generic_submit_operator_gate_required": True,
        "generic_submit_operator_gate_satisfied": submit_gate_satisfied,
        "generic_close_operator_gate_required": True,
        "generic_close_operator_gate_satisfied": close_gate_satisfied,
        "generic_realized_pnl_operator_gate_required": True,
        "generic_realized_pnl_operator_gate_satisfied": pnl_gate_satisfied,
        "generic_realized_pnl_reconciliation_allowed": False,
        "paper_realized_pnl_reconciliation_ready": False,
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
        "generic_supervised_paper_realized_pnl_reconciliation_preflight_map": preflight_map,
        "generic_supervised_paper_close_execution_map": _as_dict(close_report.get("generic_supervised_paper_close_execution_map", {})),
        "generic_supervised_paper_close_execution_scaffold_map": _as_dict(close_report.get("generic_supervised_paper_close_execution_scaffold_map", {})),
        "blocked_until_explicit_final_audit_patch": list(BLOCKED_UNTIL_EXPLICIT_FINAL_AUDIT_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": close_report.get("lifecycle_state", ""),
        "fourth_trade_locked": close_report.get("fourth_trade_locked") is True,
        "stability_lock_active": close_report.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "paper_state_status_consistency": close_report.get("paper_state_status_consistency") is True,
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
        "paper_state_modified_by_generic_realized_pnl_reconciliation_preflight": False,
        "paper_status_modified_by_generic_realized_pnl_reconciliation_preflight": False,
        "orders_submitted_by_generic_realized_pnl_reconciliation_preflight": 0,
        "positions_opened_by_generic_realized_pnl_reconciliation_preflight": 0,
        "positions_closed_by_generic_realized_pnl_reconciliation_preflight": 0,
        "broker_submit_called_by_generic_realized_pnl_reconciliation_preflight": False,
        "broker_close_called_by_generic_realized_pnl_reconciliation_preflight": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "missing_generic_realized_pnl_reconciliation_preflight_source_files": missing_source_files,
        "missing_generic_realized_pnl_reconciliation_preflight_source_markers": missing_source_markers,
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
        "recommended_next_patch": "29.4.4u-35 — Generic LSR-v2 supervised paper final audit preflight",
        "next_step": "prepare_final_audit_preflight_or_continue_observation",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "FALSE_EXECUTION_KEYS",
    "KEEP_DIAGNOSTIC_DECISION",
    "READY_DECISION",
    "Settings",
    "run_generic_supervised_paper_realized_pnl_reconciliation_preflight",
]
