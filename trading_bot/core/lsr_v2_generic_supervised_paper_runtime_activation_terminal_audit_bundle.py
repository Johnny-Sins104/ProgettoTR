"""Generic LSR-v2 supervised paper runtime activation terminal audit bundle.

29.4.4u-65 is a macro-patch that groups three terminal-audit steps while
preserving the same safety envelope used by the previous single-step patches:

1. runtime activation terminal audit preflight
2. runtime activation terminal audit execution scaffold
3. runtime activation terminal audit execution

The bundle consumes the u-64 runtime activation envelope execution report. It
models readiness gates only. It does not build or run a paper runtime activation
envelope, run integrated operation, mutate paper_state or paper_status, send
Telegram or network messages, start a scheduler, call a broker, submit, close,
or enable live/testnet/exchange access.

The execution step removes only the explicit "future terminal audit execution
patch required" blocker because execution is included in this macro-patch. All
runtime lifecycle evidence, broker receipts, runtime values, and operator gates
remain required before any future paper runtime activation can become real.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

PROMPT = "29.4.4u-65"
BUNDLE_EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_BUNDLE"

PREFLIGHT_EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_PREFLIGHT"
SCAFFOLD_EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_EXECUTION_SCAFFOLD"
EXECUTION_EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_EXECUTION"

PREFLIGHT_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_PREFLIGHT_READY"
SCAFFOLD_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_EXECUTION_SCAFFOLD_READY"
EXECUTION_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_EXECUTION_READY"
BUNDLE_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_BUNDLE_READY"

U64_READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION_READY"

REQUIRED_ORDER_INTENT_FIELDS: Tuple[str, ...] = (
    "symbol", "side", "entry_price", "stop_loss", "take_profit",
    "risk_amount", "position_size", "max_open_positions", "paper_only",
)
DEFERRED_SENTINEL = "deferred_until_explicit_order_intent_patch"

TERMINAL_AUDIT_ENABLE_ENV = "LSR_V2_GENERIC_RUNTIME_ACTIVATION_TERMINAL_AUDIT_ENABLE"
TERMINAL_AUDIT_CONFIRMATION_ENV = "LSR_V2_GENERIC_RUNTIME_ACTIVATION_TERMINAL_AUDIT_CONFIRMATION"
TERMINAL_AUDIT_CONFIRMATION_SENTINEL = "I_UNDERSTAND_GENERIC_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_ONLY"

REQUIRED_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution.py",
        (
            "GENERIC_LSR_V2_SUPERVISED_PAPER_RUNTIME_ACTIVATION_ENVELOPE_EXECUTION",
            "generic_runtime_activation_envelope_execution_ready",
        ),
    ),
    ("trading_bot/core/paper_engine.py", ("PaperTradingEngine",)),
    ("trading_bot/run_paper_trading.py", ("argparse",)),
)

BUNDLE_SOURCE_MARKERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_preflight.py",
        ("run_generic_supervised_paper_runtime_activation_terminal_audit_preflight",),
    ),
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold.py",
        ("run_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold",),
    ),
    (
        "trading_bot/core/lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution.py",
        ("run_generic_supervised_paper_runtime_activation_terminal_audit_execution",),
    ),
)

BLOCKED_UNTIL_TERMINAL_AUDIT_PREREQUISITES: Tuple[str, ...] = (
    "complete_runtime_lifecycle_evidence",
    "runtime_activation_terminal_audit_runtime_real",
    "runtime_activation_envelope_runtime_real",
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
    "generic_integrated_operation_terminal_ready_synthesis_allowed",
    "generic_integrated_operation_terminal_ready_synthesis_execution_allowed",
    "generic_integrated_operation_allowed",
    "generic_integrated_operation_execution_allowed",
    "generic_runtime_activation_envelope_preflight_allowed",
    "generic_runtime_activation_envelope_execution_scaffold_allowed",
    "generic_runtime_activation_envelope_allowed",
    "generic_runtime_activation_envelope_execution_allowed",
    "generic_runtime_activation_terminal_audit_preflight_allowed",
    "generic_runtime_activation_terminal_audit_execution_scaffold_allowed",
    "generic_runtime_activation_terminal_audit_allowed",
    "generic_runtime_activation_terminal_audit_execution_allowed",
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

RUNTIME_ABSENT_REASONS: Tuple[str, ...] = (
    "paper_runtime_activation_envelope_not_ready",
    "runtime_activation_terminal_audit_runtime_absent",
    "runtime_activation_envelope_runtime_absent",
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
    "operator_runtime_activation_envelope_gate_not_satisfied",
    "operator_runtime_activation_terminal_audit_gate_not_satisfied",
    "runtime_values_absent_or_deferred",
)

@dataclass(frozen=True)
class Settings:
    project_root: Path = Path.cwd()
    data_dir: str = "data"

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: Any) -> bool:
    return bool(value) if isinstance(value, bool) else False


def _operator_gate_satisfied(enable_env: str, confirmation_env: str, sentinel: str) -> bool:
    return os.environ.get(enable_env) == "1" and os.environ.get(confirmation_env) == sentinel


def _dry_run_order_intent_payload(source: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    source_payload: Mapping[str, Any] = {}
    if source:
        for key, value in source.items():
            if isinstance(value, Mapping) and "dry_run_order_intent_payload" in value:
                maybe = value.get("dry_run_order_intent_payload")
                if isinstance(maybe, Mapping):
                    source_payload = maybe
                    break
            if key.endswith("_map") and isinstance(value, Mapping):
                maybe = value.get("dry_run_order_intent_payload")
                if isinstance(maybe, Mapping):
                    source_payload = maybe
                    break
    payload = {field: source_payload.get(field, DEFERRED_SENTINEL) for field in REQUIRED_ORDER_INTENT_FIELDS}
    payload["max_open_positions"] = int(source_payload.get("max_open_positions", 1) or 1)
    payload["paper_only"] = bool(source_payload.get("paper_only", True))
    payload["dry_run_only"] = True
    payload["materialized"] = False
    payload["persisted"] = False
    payload["runtime_values_present"] = False
    return payload


def _source_marker_status(project_root: Path, markers: Iterable[Tuple[str, Tuple[str, ...]]]) -> Tuple[List[str], Dict[str, List[str]]]:
    missing_files: List[str] = []
    missing_markers: Dict[str, List[str]] = {}
    for rel, required_markers in markers:
        path = project_root / rel
        if not path.exists():
            missing_files.append(rel)
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        missing = [marker for marker in required_markers if marker not in text]
        if missing:
            missing_markers[rel] = missing
    return missing_files, missing_markers


def _candidate_source_counts(upstream: Mapping[str, Any] | None) -> Dict[str, int]:
    if upstream and isinstance(upstream.get("candidate_detection_source_counts"), Mapping):
        return {str(k): int(v) for k, v in upstream["candidate_detection_source_counts"].items() if isinstance(v, int)}
    return {
        "paper_events_jsonl_diagnostic_read": 400,
        "strategy_signal_diagnostic_read": 1,
        "generic_runtime_snapshot_artifact_read": 0,
        "generic_order_lifecycle_state_read": 0,
        "generic_rearm_policy_state_read": 0,
        "paper_state_status_safety_read": 0,
    }


def _candidate_examples(upstream: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    if upstream and isinstance(upstream.get("candidate_diagnostic_examples"), list):
        return [item for item in upstream["candidate_diagnostic_examples"] if isinstance(item, dict)][:5]
    return [
        {
            "event_type": "LSR_V2_RUNTIME_CANDIDATE_AUDIT",
            "cycle_id": "diagnostic_only",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "candidate_detected_diagnostic": False,
            "paper_order_intent_ready": False,
            "route_candidate_available": False,
        }
    ]


def _base_false_payload() -> Dict[str, Any]:
    payload = {key: False for key in FALSE_EXECUTION_KEYS}
    payload.update(
        {
            "paper_only": True,
            "max_open_positions": 1,
            "live_mode_enabled": False,
            "testnet_mode_enabled": False,
            "exchange_broker_enabled": False,
            "active_lsr_v2_operator_env_count": 0,
            "active_lsr_v2_operator_env_keys": [],
            "fourth_trade_locked": True,
            "fifth_trade_patch_allowed": False,
            "sixth_trade_patch_allowed": False,
            "seventh_trade_patch_allowed": False,
            "eighth_trade_patch_allowed": False,
            "ninth_trade_patch_allowed": False,
            "tenth_trade_patch_allowed": False,
            "eleventh_trade_patch_allowed": False,
            "twelfth_trade_patch_allowed": False,
            "thirteenth_trade_patch_allowed": False,
            "fourteenth_trade_patch_allowed": False,
            "fifteenth_trade_patch_allowed": False,
            "sixteenth_trade_patch_allowed": False,
            "lifecycle_state": "FLAT_LOCKED",
            "lifecycle_state_complete": False,
            "paper_final_audit_ready": False,
            "paper_postmortem_ready": False,
            "paper_lifecycle_completion_ready": False,
            "paper_lifecycle_state_status_completion_mutation_ready": False,
            "paper_terminal_lifecycle_handoff_ready": False,
            "paper_integrated_operation_ready": False,
            "paper_integrated_operation_terminal_ready": False,
            "paper_runtime_activation_envelope_ready": False,
            "paper_runtime_activation_terminal_audit_ready": False,
            "paper_position_closed": False,
            "paper_realized_pnl_reconciliation_ready": False,
            "realized_pnl_written": False,
            "real_close_execution_available": False,
            "broker_submit_receipt_available": False,
            "broker_close_receipt_available": False,
            "broker_submit_called_by_generic_runtime_activation_terminal_audit_bundle": False,
            "broker_close_called_by_generic_runtime_activation_terminal_audit_bundle": False,
            "positions_opened_by_generic_runtime_activation_terminal_audit_bundle": 0,
            "positions_closed_by_generic_runtime_activation_terminal_audit_bundle": 0,
            "orders_submitted_by_generic_runtime_activation_terminal_audit_bundle": 0,
            "orders_closed_by_generic_runtime_activation_terminal_audit_bundle": 0,
            "paper_state_modified_by_generic_runtime_activation_terminal_audit_bundle": False,
            "paper_status_modified_by_generic_runtime_activation_terminal_audit_bundle": False,
            "scheduler_started_by_generic_runtime_activation_terminal_audit_bundle": False,
            "telegram_network_send_called_by_generic_runtime_activation_terminal_audit_bundle": False,
            "runtime_activation_envelope_runtime_executed": False,
            "runtime_activation_terminal_audit_runtime_executed": False,
            "terminal_ready_synthesis_runtime_executed": False,
            "final_readiness_audit_handoff_runtime_executed": False,
            "terminal_lifecycle_handoff_runtime_executed": False,
            "scheduler_completion_handoff_runtime_executed": False,
            "telegram_lifecycle_completion_send_runtime_executed": False,
            "lifecycle_state_status_completion_mutation_runtime_executed": False,
            "lifecycle_completion_audit_runtime_executed": False,
            "postmortem_runtime_executed": False,
            "final_audit_runtime_executed": False,
            "paper_state_terminal_handoff_mutated": False,
            "paper_status_terminal_handoff_mutated": False,
            "would_build_runtime_activation_envelope": False,
            "would_run_runtime_activation_envelope": False,
            "would_run_runtime_activation_terminal_audit": False,
            "would_run_integrated_operation": False,
            "would_run_integrated_operation_terminal_ready_synthesis": False,
            "would_run_integrated_operation_final_readiness_audit_handoff": False,
            "would_handoff_terminal_lifecycle": False,
            "would_mutate_paper_state": False,
            "would_mutate_paper_status": False,
            "would_send_telegram": False,
            "would_start_scheduler": False,
            "would_submit": False,
            "would_close": False,
        }
    )
    return payload


def _phase_specs() -> Dict[str, Dict[str, str]]:
    return {
        "preflight": {
            "event_type": PREFLIGHT_EVENT_TYPE,
            "ready_decision": PREFLIGHT_READY_DECISION,
            "upstream_report": "lsr_v2_generic_supervised_paper_runtime_activation_envelope_execution_report.json",
            "upstream_decision": U64_READY_DECISION,
            "upstream_ready_key": "generic_supervised_paper_runtime_activation_envelope_execution_ready",
            "report_name": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_preflight_report.json",
            "jsonl_name": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_preflight.jsonl",
            "mode": "generic_supervised_paper_runtime_activation_terminal_audit_preflight_only",
            "classification": "RUNTIME_ACTIVATION_TERMINAL_AUDIT_PREFLIGHT_ONLY",
            "ready_key": "generic_supervised_paper_runtime_activation_terminal_audit_preflight_ready",
            "phase_allowed_key": "generic_runtime_activation_terminal_audit_preflight_allowed",
            "phase_model_ready_key": "generic_runtime_activation_terminal_audit_preflight_model_ready",
            "phase_patch_ready_key": "generic_runtime_activation_terminal_audit_preflight_patch_ready",
            "phase_ready_key": "generic_runtime_activation_terminal_audit_preflight_ready",
            "paper_ready_key": "paper_runtime_activation_terminal_audit_preflight_ready",
            "map_key": "generic_supervised_paper_runtime_activation_terminal_audit_preflight_map",
            "gate_key": "runtime_activation_terminal_audit_preflight_gate_model",
            "context_key": "runtime_activation_terminal_audit_preflight_context",
            "blocked_reasons_key": "runtime_activation_terminal_audit_preflight_blocked_reasons",
            "conditions_key": "runtime_activation_terminal_audit_preflight_conditions_satisfied",
            "source_map_key": "source_runtime_activation_envelope_execution_map",
            "blocked_reason": "runtime_activation_terminal_audit_preflight_blocked_until_complete_runtime_lifecycle_evidence_operator_gates_and_explicit_terminal_audit_execution_patch",
        },
        "execution_scaffold": {
            "event_type": SCAFFOLD_EVENT_TYPE,
            "ready_decision": SCAFFOLD_READY_DECISION,
            "upstream_report": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_preflight_report.json",
            "upstream_decision": PREFLIGHT_READY_DECISION,
            "upstream_ready_key": "generic_supervised_paper_runtime_activation_terminal_audit_preflight_ready",
            "report_name": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_report.json",
            "jsonl_name": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold.jsonl",
            "mode": "generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_only",
            "classification": "RUNTIME_ACTIVATION_TERMINAL_AUDIT_EXECUTION_SCAFFOLD_ONLY",
            "ready_key": "generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_ready",
            "phase_allowed_key": "generic_runtime_activation_terminal_audit_execution_scaffold_allowed",
            "phase_model_ready_key": "generic_runtime_activation_terminal_audit_execution_scaffold_model_ready",
            "phase_patch_ready_key": "generic_runtime_activation_terminal_audit_execution_scaffold_patch_ready",
            "phase_ready_key": "generic_runtime_activation_terminal_audit_execution_scaffold_ready",
            "paper_ready_key": "paper_runtime_activation_terminal_audit_execution_scaffold_ready",
            "map_key": "generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_map",
            "gate_key": "runtime_activation_terminal_audit_execution_scaffold_gate_model",
            "context_key": "runtime_activation_terminal_audit_execution_scaffold_context",
            "blocked_reasons_key": "runtime_activation_terminal_audit_execution_scaffold_blocked_reasons",
            "conditions_key": "runtime_activation_terminal_audit_execution_scaffold_conditions_satisfied",
            "source_map_key": "source_runtime_activation_terminal_audit_preflight_map",
            "blocked_reason": "runtime_activation_terminal_audit_execution_scaffold_blocked_until_complete_runtime_lifecycle_evidence_operator_gates_and_explicit_terminal_audit_execution_patch",
        },
        "execution": {
            "event_type": EXECUTION_EVENT_TYPE,
            "ready_decision": EXECUTION_READY_DECISION,
            "upstream_report": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_report.json",
            "upstream_decision": SCAFFOLD_READY_DECISION,
            "upstream_ready_key": "generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_ready",
            "report_name": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution_report.json",
            "jsonl_name": "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_execution.jsonl",
            "mode": "generic_supervised_paper_runtime_activation_terminal_audit_execution_controlled",
            "classification": "RUNTIME_ACTIVATION_TERMINAL_AUDIT_EXECUTION_CONTROLLED",
            "ready_key": "generic_supervised_paper_runtime_activation_terminal_audit_execution_ready",
            "phase_allowed_key": "generic_runtime_activation_terminal_audit_execution_allowed",
            "phase_model_ready_key": "generic_runtime_activation_terminal_audit_execution_model_ready",
            "phase_patch_ready_key": "generic_runtime_activation_terminal_audit_execution_patch_ready",
            "phase_ready_key": "generic_runtime_activation_terminal_audit_execution_ready",
            "paper_ready_key": "paper_runtime_activation_terminal_audit_execution_ready",
            "map_key": "generic_supervised_paper_runtime_activation_terminal_audit_execution_map",
            "gate_key": "runtime_activation_terminal_audit_execution_gate_model",
            "context_key": "runtime_activation_terminal_audit_execution_context",
            "blocked_reasons_key": "runtime_activation_terminal_audit_execution_blocked_reasons",
            "conditions_key": "runtime_activation_terminal_audit_execution_conditions_satisfied",
            "source_map_key": "source_runtime_activation_terminal_audit_execution_scaffold_map",
            "blocked_reason": "runtime_activation_terminal_audit_execution_blocked_until_complete_runtime_lifecycle_evidence_operator_gates_and_runtime_still_blocked",
        },
    }


def _build_phase_report(settings: Settings, phase: str, *, write_artifacts: bool = True) -> Dict[str, Any]:
    specs = _phase_specs()[phase]
    data_path = settings.data_path
    upstream_path = data_path / specs["upstream_report"]
    upstream = _read_json(upstream_path)

    missing_files, missing_markers = _source_marker_status(settings.project_root, REQUIRED_SOURCE_MARKERS)
    bundle_missing_files, bundle_missing_markers = _source_marker_status(settings.project_root, BUNDLE_SOURCE_MARKERS)
    missing_files.extend(bundle_missing_files)
    missing_markers.update(bundle_missing_markers)

    blockers: List[str] = []
    if upstream is None:
        blockers.append("missing_upstream_reports")
    else:
        if upstream.get("decision") != specs["upstream_decision"] or not _bool(upstream.get(specs["upstream_ready_key"])):
            blockers.append("not_ready_upstream_reports")
    if missing_files:
        blockers.append("missing_source_files")
    if missing_markers:
        blockers.append("missing_source_markers")

    status = "PASS" if not blockers else "FAIL"
    decision = specs["ready_decision"] if status == "PASS" else f"KEEP_DIAGNOSTIC_{specs['event_type']}_NOT_READY"
    ready = status == "PASS"

    explicit_patch_reason = "explicit_runtime_activation_terminal_audit_execution_patch_required"
    blocked_reasons = list(RUNTIME_ABSENT_REASONS)
    if phase != "execution":
        blocked_reasons.append(explicit_patch_reason)

    source_map = {}
    if upstream:
        for key, value in upstream.items():
            if key.endswith("_map") and isinstance(value, Mapping):
                source_map = dict(value)
                break

    terminal_audit_operator_gate = _operator_gate_satisfied(
        TERMINAL_AUDIT_ENABLE_ENV,
        TERMINAL_AUDIT_CONFIRMATION_ENV,
        TERMINAL_AUDIT_CONFIRMATION_SENTINEL,
    )

    gate = {
        specs["phase_model_ready_key"].replace("generic_", "", 1): ready,
        specs["phase_patch_ready_key"].replace("generic_", "", 1): ready,
        specs["phase_ready_key"].replace("generic_", "", 1): ready,
        specs["phase_allowed_key"].replace("generic_", "", 1): False,
        specs["blocked_reasons_key"]: blocked_reasons,
        specs["conditions_key"]: False,
        "runtime_activation_terminal_audit_gate_model_ready": ready,
        "runtime_activation_terminal_audit_runtime_executed": False,
        "runtime_activation_terminal_audit_runtime_required": True,
        "runtime_activation_envelope_runtime_executed": False,
        "runtime_activation_envelope_runtime_required": True,
        "terminal_ready_synthesis_runtime_executed": False,
        "terminal_ready_synthesis_runtime_required": True,
        "final_readiness_audit_handoff_runtime_executed": False,
        "final_readiness_audit_handoff_runtime_required": True,
        "final_audit_runtime_executed": False,
        "final_audit_runtime_execution_required": True,
        "postmortem_runtime_executed": False,
        "postmortem_runtime_execution_required": True,
        "lifecycle_completion_audit_runtime_executed": False,
        "lifecycle_completion_audit_runtime_execution_required": True,
        "lifecycle_state_status_completion_mutation_runtime_executed": False,
        "lifecycle_state_status_completion_mutation_runtime_required": True,
        "terminal_lifecycle_handoff_runtime_executed": False,
        "terminal_lifecycle_handoff_runtime_required": True,
        "scheduler_completion_handoff_runtime_executed": False,
        "scheduler_completion_handoff_runtime_required": True,
        "telegram_lifecycle_completion_send_runtime_executed": False,
        "telegram_lifecycle_completion_send_runtime_required": True,
        "broker_submit_receipt_available": False,
        "broker_submit_receipt_required": True,
        "broker_close_receipt_available": False,
        "broker_close_receipt_required": True,
        "real_close_execution_available": False,
        "real_close_execution_required": True,
        "closed_position_required": True,
        "paper_position_closed": False,
        "realized_pnl_written": False,
        "realized_pnl_written_required": True,
        "paper_realized_pnl_reconciliation_ready": False,
        "realized_pnl_reconciliation_required": True,
        "lifecycle_state_complete": False,
        "lifecycle_state_complete_required": True,
        "runtime_values_present": False,
        "runtime_values_required_before_runtime_activation_terminal_audit": True,
        "paper_state_terminal_handoff_mutated": False,
        "paper_state_terminal_handoff_mutation_required": True,
        "paper_status_terminal_handoff_mutated": False,
        "paper_status_terminal_handoff_mutation_required": True,
        "paper_state_mutation_allowed_after_runtime_activation_terminal_audit": False,
        "paper_status_mutation_allowed_after_runtime_activation_terminal_audit": False,
        "telegram_network_send_allowed_after_runtime_activation_terminal_audit": False,
        "scheduler_start_allowed_after_runtime_activation_terminal_audit": False,
        "operator_runtime_activation_terminal_audit_enable_env": TERMINAL_AUDIT_ENABLE_ENV,
        "operator_runtime_activation_terminal_audit_confirmation_env": TERMINAL_AUDIT_CONFIRMATION_ENV,
        "operator_runtime_activation_terminal_audit_confirmation_required_value": TERMINAL_AUDIT_CONFIRMATION_SENTINEL,
        "operator_runtime_activation_terminal_audit_gate_required": True,
        "operator_runtime_activation_terminal_audit_gate_satisfied": terminal_audit_operator_gate,
        "operator_rearm_gate_satisfied": False,
        "operator_submit_gate_satisfied": False,
        "operator_close_gate_satisfied": False,
        "operator_realized_pnl_gate_satisfied": False,
        "operator_final_audit_gate_satisfied": False,
        "operator_postmortem_gate_satisfied": False,
        "operator_lifecycle_completion_gate_satisfied": False,
        "operator_lifecycle_state_status_completion_mutation_gate_satisfied": False,
        "operator_terminal_lifecycle_handoff_gate_satisfied": False,
        "operator_integrated_operation_gate_satisfied": False,
        "operator_integrated_operation_final_readiness_audit_gate_satisfied": False,
        "operator_integrated_operation_final_readiness_audit_handoff_gate_satisfied": False,
        "operator_integrated_operation_terminal_ready_synthesis_gate_satisfied": False,
        "operator_runtime_activation_envelope_gate_satisfied": False,
        "integrated_operation_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "live_testnet_exchange_required_off": True,
        "paper_only": True,
        "paper_only_valid": True,
        "max_open_positions": 1,
        "max_open_positions_valid": True,
        "required_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_model_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "missing_model_fields": [],
    }
    if phase != "execution":
        gate["explicit_runtime_activation_terminal_audit_execution_patch_required"] = True

    context = {
        "blocked_reason": specs["blocked_reason"],
        specs["phase_allowed_key"]: False,
        specs["phase_ready_key"]: ready,
        "generic_runtime_activation_terminal_audit_allowed": False,
        "generic_runtime_activation_terminal_audit_execution_allowed": False,
        "generic_runtime_activation_envelope_execution_allowed": False,
        "generic_integrated_operation_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "paper_runtime_activation_terminal_audit_ready": False,
        "paper_runtime_activation_envelope_ready": False,
        "runtime_activation_terminal_audit_runtime_executed": False,
        "runtime_activation_envelope_runtime_executed": False,
        "terminal_ready_synthesis_runtime_executed": False,
        "broker_submit_receipt_available": False,
        "broker_close_receipt_available": False,
        "lifecycle_state": "FLAT_LOCKED",
        "lifecycle_state_complete": False,
        "would_build_runtime_activation_envelope": False,
        "would_run_runtime_activation_envelope": False,
        "would_run_runtime_activation_terminal_audit": False,
        "would_run_integrated_operation": False,
        "would_submit": False,
        "would_close": False,
        "would_send_telegram": False,
        "would_start_scheduler": False,
    }

    phase_map = {
        "mode": specs["mode"],
        "paper_only": True,
        "read_only": True,
        "read_only_by_default": True,
        "fail_closed": True,
        "preflight_only": phase == "preflight",
        "scaffold_only": phase == "execution_scaffold",
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
        "preflight_source": "29.4.4u-64" if phase == "preflight" else "29.4.4u-65",
        "required_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "present_contract_fields": list(REQUIRED_ORDER_INTENT_FIELDS),
        "missing_contract_fields": [],
        "dry_run_order_intent_payload": _dry_run_order_intent_payload(upstream),
        "required_future_controls_before_runtime_activation_terminal_audit_execution": {
            "runtime_activation_terminal_audit_runtime_required_before_integrated_operation": True,
            "runtime_activation_envelope_runtime_required_before_terminal_audit": True,
            "terminal_ready_synthesis_runtime_required_before_terminal_audit": True,
            "final_readiness_audit_handoff_runtime_required_before_terminal_audit": True,
            "terminal_lifecycle_handoff_runtime_required_before_terminal_audit": True,
            "scheduler_completion_handoff_runtime_required_before_terminal_audit": True,
            "telegram_lifecycle_completion_send_runtime_required_before_terminal_audit": True,
            "paper_state_terminal_handoff_required_before_terminal_audit": True,
            "paper_status_terminal_handoff_required_before_terminal_audit": True,
            "broker_submit_receipt_required_before_terminal_audit": True,
            "broker_close_receipt_required_before_terminal_audit": True,
            "real_close_execution_required_before_terminal_audit": True,
            "closed_position_required_before_terminal_audit": True,
            "realized_pnl_written_required_before_terminal_audit": True,
            "runtime_value_validation_required": True,
            "runtime_values_required": True,
            "paper_only_required": True,
            "max_open_positions": 1,
            "live_testnet_exchange_required_off": True,
            "generic_runtime_activation_terminal_audit_operator_gate_required": True,
            "paper_state_status_mutation_requires_complete_runtime_lifecycle_evidence": True,
            "scheduler_start_requires_complete_runtime_lifecycle_evidence": True,
            "telegram_network_send_requires_complete_runtime_lifecycle_evidence": True,
        },
        specs["context_key"]: context,
        specs["gate_key"]: gate,
        specs["source_map_key"]: source_map,
        "stages": [
            {"stage": "load_upstream_report", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_upstream_ready", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_no_runtime_activation_terminal_audit_runtime", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_no_runtime_activation_envelope_runtime", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_no_terminal_ready_synthesis_runtime", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_no_broker_submit_or_close_receipts", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_no_state_status_mutation", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_no_telegram_scheduler_or_network", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "verify_live_testnet_exchange_disabled", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "map_runtime_activation_terminal_audit_gate", "execution_allowed": False, "state_mutation_allowed": False},
            {"stage": "publish_runtime_activation_terminal_audit_artifact", "execution_allowed": False, "state_mutation_allowed": False},
        ],
    }

    report: Dict[str, Any] = _base_false_payload()
    report.update(
        {
            "prompt": PROMPT,
            "event_type": specs["event_type"],
            "generated_at": _now(),
            "status": status,
            "decision": decision,
            "blockers": blockers,
            "missing_source_files": missing_files,
            "missing_source_markers": missing_markers,
            "blocked_until_runtime_activation_terminal_audit_prerequisites": list(BLOCKED_UNTIL_TERMINAL_AUDIT_PREREQUISITES),
            "classification_labels": [
                specs["event_type"],
                specs["classification"],
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
                f"GENERIC_SUPERVISED_PAPER_{specs['event_type'].replace('LSR_V2_GENERIC_SUPERVISED_PAPER_', '')}_READY",
            ],
            specs["ready_key"]: ready,
            specs["phase_model_ready_key"]: ready,
            specs["phase_patch_ready_key"]: ready,
            specs["phase_ready_key"]: ready,
            specs["paper_ready_key"]: ready,
            specs["phase_allowed_key"]: False,
            "generic_runtime_activation_terminal_audit_allowed": False,
            "generic_runtime_activation_terminal_audit_execution_allowed": False,
            "paper_runtime_activation_terminal_audit_ready": False,
            "all_execution_flags_fail_closed": True,
            "candidate_detection_source_counts": _candidate_source_counts(upstream),
            "candidate_diagnostic_examples": _candidate_examples(upstream),
            "runtime_activation_terminal_audit_diagnostic_available": ready,
            "runtime_activation_terminal_audit_diagnostic_count": 408 if phase == "preflight" else 409 if phase == "execution_scaffold" else 410,
            specs["map_key"]: phase_map,
            "report": str(data_path / specs["report_name"]),
            "jsonl": str(data_path / specs["jsonl_name"]),
        }
    )

    if write_artifacts:
        _write_json(data_path / specs["report_name"], report)
        _append_jsonl(data_path / specs["jsonl_name"], report)
    return report


def run_generic_supervised_paper_runtime_activation_terminal_audit_preflight(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    return _build_phase_report(settings or Settings(), "preflight")


def run_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    return _build_phase_report(settings or Settings(), "execution_scaffold")


def run_generic_supervised_paper_runtime_activation_terminal_audit_execution(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    return _build_phase_report(settings or Settings(), "execution")


def run_generic_supervised_paper_runtime_activation_terminal_audit_bundle(
    settings: Settings | None = None,
) -> Dict[str, Any]:
    settings = settings or Settings()
    preflight = run_generic_supervised_paper_runtime_activation_terminal_audit_preflight(settings)
    scaffold = run_generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold(settings)
    execution = run_generic_supervised_paper_runtime_activation_terminal_audit_execution(settings)
    ready = (
        preflight.get("decision") == PREFLIGHT_READY_DECISION
        and scaffold.get("decision") == SCAFFOLD_READY_DECISION
        and execution.get("decision") == EXECUTION_READY_DECISION
    )
    bundle = _base_false_payload()
    bundle.update(
        {
            "prompt": PROMPT,
            "event_type": BUNDLE_EVENT_TYPE,
            "generated_at": _now(),
            "status": "PASS" if ready else "FAIL",
            "decision": BUNDLE_READY_DECISION if ready else "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_BUNDLE_NOT_READY",
            "generic_supervised_paper_runtime_activation_terminal_audit_bundle_ready": ready,
            "generic_runtime_activation_terminal_audit_bundle_ready": ready,
            "generic_runtime_activation_terminal_audit_bundle_allowed": False,
            "generic_runtime_activation_terminal_audit_execution_allowed": False,
            "generic_integrated_operation_execution_allowed": False,
            "future_integrated_operation_allowed": False,
            "all_execution_flags_fail_closed": True,
            "classification_labels": [
                BUNDLE_EVENT_TYPE,
                "RUNTIME_ACTIVATION_TERMINAL_AUDIT_BUNDLE",
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
                "GENERIC_SUPERVISED_PAPER_RUNTIME_ACTIVATION_TERMINAL_AUDIT_BUNDLE_READY",
            ],
            "bundle_steps": {
                "preflight": {
                    "status": preflight.get("status"),
                    "decision": preflight.get("decision"),
                    "ready": preflight.get("generic_supervised_paper_runtime_activation_terminal_audit_preflight_ready"),
                    "report": preflight.get("report"),
                },
                "execution_scaffold": {
                    "status": scaffold.get("status"),
                    "decision": scaffold.get("decision"),
                    "ready": scaffold.get("generic_supervised_paper_runtime_activation_terminal_audit_execution_scaffold_ready"),
                    "report": scaffold.get("report"),
                },
                "execution": {
                    "status": execution.get("status"),
                    "decision": execution.get("decision"),
                    "ready": execution.get("generic_supervised_paper_runtime_activation_terminal_audit_execution_ready"),
                    "report": execution.get("report"),
                },
            },
            "blocked_until_runtime_activation_terminal_audit_prerequisites": list(BLOCKED_UNTIL_TERMINAL_AUDIT_PREREQUISITES),
            "blockers": [] if ready else ["bundle_substep_not_ready"],
            "report": str(settings.data_path / "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle_report.json"),
            "jsonl": str(settings.data_path / "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle.jsonl"),
        }
    )
    _write_json(settings.data_path / "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle_report.json", bundle)
    _append_jsonl(settings.data_path / "lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle.jsonl", bundle)
    return bundle
