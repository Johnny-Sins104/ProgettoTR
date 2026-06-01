"""Generic LSR-v2 paper-only order-intent candidate audit.

29.4.4u-21 is intentionally audit-only, read-only, and fail-closed. It
consumes the generic handoff-to-order-intent dry-run preflight from u-20 and
checks whether the diagnostic order-intent context is modelable for a future
validation/materialization path. It never creates or persists a real
paper_order_intent, submits/closes an order, opens/closes a position, starts a
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

PROMPT = "29.4.4u-21"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT_NOT_READY"

U20_READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_HANDOFF_TO_ORDER_INTENT_DRY_RUN_PREFLIGHT_READY"

ORDER_INTENT_CANDIDATE_AUDIT_STAGES: Tuple[str, ...] = (
    "load_generic_handoff_to_order_intent_dry_run_preflight",
    "verify_handoff_to_order_intent_dry_run_preflight_ready",
    "verify_order_intent_dry_run_diagnostic_context",
    "verify_flat_locked_state",
    "verify_no_route_or_handoff_candidate",
    "verify_no_existing_order_intent",
    "verify_order_intent_creation_still_blocked",
    "verify_order_intent_persistence_still_blocked",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "audit_diagnostic_order_intent_modelability",
    "map_order_intent_candidate_audit_contract",
    "publish_generic_order_intent_candidate_audit_artifact",
)

BLOCKED_UNTIL_EXPLICIT_ORDER_INTENT_VALIDATION_PATCH: Tuple[str, ...] = (
    "generic_order_intent_contract_validation",
    "generic_order_intent_materialization",
    "generic_order_intent_persistence",
    "generic_submit_preflight",
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
        "trading_bot/core/lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight.py",
        (
            "GENERIC_LSR_V2_PAPER_ONLY_HANDOFF_TO_ORDER_INTENT_DRY_RUN_PREFLIGHT",
            "order_intent_dry_run_preflight_diagnostic_count",
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
    report_name: str = "lsr_v2_generic_paper_only_order_intent_candidate_audit_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_order_intent_candidate_audit.jsonl"
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


def _candidate_examples(payload: Mapping[str, Any], limit: int = 5) -> List[Any]:
    examples = payload.get("candidate_diagnostic_examples", [])
    if isinstance(examples, list):
        return examples[:limit]
    return []


def _audit_order_intent_modelability(dry_run_preflight: Mapping[str, Any]) -> Dict[str, Any]:
    diagnostic_count = _safe_int(dry_run_preflight.get("order_intent_dry_run_preflight_diagnostic_count"), 0)
    handoff_to_intent_map = _as_dict(dry_run_preflight.get("handoff_to_order_intent_dry_run_preflight_map", {}))
    model = _as_dict(handoff_to_intent_map.get("paper_order_intent_model", {}))
    order_context = _as_dict(handoff_to_intent_map.get("order_intent_dry_run_context", {}))

    required_contract_fields = (
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
    present_model_fields = [field for field in required_contract_fields if field in model]
    missing_model_fields = [field for field in required_contract_fields if field not in model]

    return {
        "mode": "order_intent_candidate_audit_only",
        "paper_only": True,
        "audit_only": True,
        "read_only": True,
        "fail_closed": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "diagnostic_order_intent_context_available": diagnostic_count > 0,
        "order_intent_candidate_audit_diagnostic_count": diagnostic_count,
        "candidate_diagnostic_examples": _candidate_examples(dry_run_preflight),
        "candidate_detection_source_counts": dry_run_preflight.get("candidate_detection_source_counts", {}),
        "upstream_order_intent_dry_run_context": order_context,
        "upstream_paper_order_intent_model": model,
        "order_intent_candidate_contract_audit": {
            "required_contract_fields": list(required_contract_fields),
            "present_model_fields": present_model_fields,
            "missing_model_fields": missing_model_fields,
            "contract_shape_modelable": len(missing_model_fields) == 0,
            "contract_value_validation_deferred": True,
            "symbol_validation_deferred": True,
            "side_validation_deferred": True,
            "entry_price_validation_deferred": True,
            "stop_loss_validation_deferred": True,
            "take_profit_validation_deferred": True,
            "risk_amount_validation_deferred": True,
            "position_size_validation_deferred": True,
            "max_open_positions": model.get("max_open_positions", 1),
            "paper_only": model.get("paper_only") is True,
        },
        "order_intent_candidate_audit_context": {
            "paper_order_intent_candidate_ready": False,
            "paper_order_intent_ready": False,
            "paper_order_intent_dry_run_ready": False,
            "paper_order_intent_materialized": False,
            "paper_order_intent_persisted": False,
            "would_create_order_intent": False,
            "would_create_order": False,
            "would_submit": False,
            "blocked_reason": "order_intent_candidate_materialization_not_allowed_audit_only",
        },
        "required_future_controls_before_order_intent_validation": {
            "explicit_generic_order_intent_validation_patch_required": True,
            "explicit_generic_order_intent_materialization_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
            "paper_order_intent_persistence_deferred": True,
        },
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in ORDER_INTENT_CANDIDATE_AUDIT_STAGES
        ],
    }


def run_generic_paper_only_order_intent_candidate_audit(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    upstream_name = "lsr_v2_generic_paper_only_handoff_to_order_intent_dry_run_preflight_report.json"
    dry_run_preflight = _read_json(data_path / upstream_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not dry_run_preflight:
        missing_upstream_reports.append(upstream_name)
    elif dry_run_preflight.get("status") != "PASS" or dry_run_preflight.get("decision") != U20_READY_DECISION:
        not_ready_upstream_reports.append(upstream_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(dry_run_preflight, FALSE_EXECUTION_KEYS)

    diagnostic_count = _safe_int(dry_run_preflight.get("order_intent_dry_run_preflight_diagnostic_count"), 0)
    diagnostic_available = dry_run_preflight.get("order_intent_dry_run_preflight_diagnostic_available") is True and diagnostic_count > 0
    source_counts = dry_run_preflight.get("candidate_detection_source_counts", {})
    if not isinstance(source_counts, dict):
        source_counts = {}

    required_readiness = {
        "handoff_to_order_intent_dry_run_preflight_ready": dry_run_preflight.get("generic_handoff_to_order_intent_dry_run_preflight_ready") is True,
        "order_intent_dry_run_preflight_diagnostic_available": diagnostic_available,
        "flat_locked_state": dry_run_preflight.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": dry_run_preflight.get("open_positions_after") == 0,
        "pending_orders_clear": dry_run_preflight.get("pending_orders_after") == 0,
        "no_existing_route_candidate": dry_run_preflight.get("route_candidate_available") is False,
        "no_existing_handoff_candidate": dry_run_preflight.get("handoff_candidate_available") is False,
        "no_existing_paper_order_intent": dry_run_preflight.get("paper_order_intent_ready") is False,
        "no_existing_paper_order_intent_dry_run": dry_run_preflight.get("paper_order_intent_dry_run_ready") is False,
        "would_create_order_intent_false": dry_run_preflight.get("would_create_order_intent") is False,
        "would_create_order_false": dry_run_preflight.get("would_create_order") is False,
        "would_submit_false": dry_run_preflight.get("would_submit") is False,
        "order_intent_creation_blocked": dry_run_preflight.get("generic_order_intent_creation_allowed") is False,
        "order_intent_persistence_blocked": dry_run_preflight.get("generic_order_intent_persistence_allowed") is False,
        "submit_execution_blocked": dry_run_preflight.get("generic_submit_execution_allowed") is False,
        "operator_env_absent": len(active_env) == 0,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "source_markers_present": source_markers_present,
        "no_state_mutation": dry_run_preflight.get("paper_state_modified_by_generic_handoff_to_order_intent_dry_run_preflight") is False
        and dry_run_preflight.get("paper_status_modified_by_generic_handoff_to_order_intent_dry_run_preflight") is False,
        "no_submit_or_close_occurred": dry_run_preflight.get("orders_submitted_by_generic_handoff_to_order_intent_dry_run_preflight") == 0
        and dry_run_preflight.get("positions_opened_by_generic_handoff_to_order_intent_dry_run_preflight") == 0
        and dry_run_preflight.get("positions_closed_by_generic_handoff_to_order_intent_dry_run_preflight") == 0,
        "live_disabled": dry_run_preflight.get("live_enabled") is False,
        "testnet_disabled": dry_run_preflight.get("testnet_enabled") is False,
        "exchange_broker_disabled": dry_run_preflight.get("exchange_broker_enabled") is False,
    }

    blockers = [key for key, value in required_readiness.items() if value is not True]
    if missing_upstream_reports:
        blockers.append("handoff_to_order_intent_dry_run_preflight_report_present")
    if not_ready_upstream_reports:
        blockers.append("handoff_to_order_intent_dry_run_preflight_report_ready")
    ready = not blockers and settings.fail_closed is True

    candidate_audit_map = _audit_order_intent_modelability(dry_run_preflight)
    contract_audit = _as_dict(candidate_audit_map.get("order_intent_candidate_contract_audit", {}))

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_ORDER_INTENT_CANDIDATE_AUDIT",
            "AUDIT_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "DIAGNOSTIC_ORDER_INTENT_CANDIDATE_MAP_ONLY",
            "NO_ORDER_INTENT_CREATION",
            "NO_ORDER_INTENT_PERSISTENCE",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_ORDER_INTENT_CANDIDATE_AUDIT_READY" if ready else "GENERIC_ORDER_INTENT_CANDIDATE_AUDIT_BLOCKED",
        ],
        "blockers": blockers,
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "upstream_reports_present": [] if not dry_run_preflight else [upstream_name],
        "required_readiness": required_readiness,
        "generic_order_intent_candidate_audit_ready": ready,
        "generic_order_intent_candidate_audit_plan_ready": ready,
        "generic_order_intent_candidate_audit_contract_ready": ready,
        "generic_order_intent_candidate_audit_map_ready": ready,
        "generic_order_intent_candidate_audit_fail_closed_ready": ready,
        "handoff_to_order_intent_dry_run_preflight_ready": dry_run_preflight.get("generic_handoff_to_order_intent_dry_run_preflight_ready") is True,
        "order_intent_dry_run_preflight_diagnostic_available": diagnostic_available,
        "order_intent_dry_run_preflight_diagnostic_count": diagnostic_count,
        "order_intent_candidate_audit_diagnostic_available": diagnostic_available,
        "order_intent_candidate_audit_diagnostic_count": diagnostic_count,
        "candidate_detection_source_counts": source_counts,
        "candidate_diagnostic_examples": _candidate_examples(dry_run_preflight),
        "order_intent_candidate_contract_shape_modelable": contract_audit.get("contract_shape_modelable") is True,
        "order_intent_candidate_contract_value_validation_deferred": True,
        "order_intent_candidate_contract_required_fields": contract_audit.get("required_contract_fields", []),
        "order_intent_candidate_contract_present_fields": contract_audit.get("present_model_fields", []),
        "order_intent_candidate_contract_missing_fields": contract_audit.get("missing_model_fields", []),
        "route_candidate_available": False,
        "route_preflight_candidate_available": False,
        "handoff_candidate_available": False,
        "paper_order_intent_candidate_ready": False,
        "paper_order_intent_ready": False,
        "paper_order_intent_dry_run_ready": False,
        "paper_order_intent_materialized": False,
        "paper_order_intent_persisted": False,
        "would_route": False,
        "would_handoff": False,
        "would_create_order_intent": False,
        "would_create_order": False,
        "would_submit": False,
        "paper_order_intent_candidate_blocked_reason": "order_intent_candidate_materialization_not_allowed_audit_only",
        "paper_order_intent_blocked_reason": "order_intent_creation_not_allowed_audit_only",
        "handoff_to_order_intent_dry_run_preflight_map": dry_run_preflight.get("handoff_to_order_intent_dry_run_preflight_map", {}),
        "order_intent_candidate_audit_map": candidate_audit_map,
        "blocked_until_explicit_order_intent_validation_patch": list(BLOCKED_UNTIL_EXPLICIT_ORDER_INTENT_VALIDATION_PATCH),
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": len(active_env) == 0,
        "lifecycle_state": dry_run_preflight.get("lifecycle_state", ""),
        "fourth_trade_locked": dry_run_preflight.get("fourth_trade_locked") is True,
        "stability_lock_active": dry_run_preflight.get("stability_lock_active") is True,
        "open_positions_after": 0,
        "pending_orders_after": 0,
        "no_route_candidate": True,
        "no_handoff_candidate": True,
        "no_order_intent_currently_available": True,
        "paper_state_status_consistency": dry_run_preflight.get("paper_state_status_consistency") is True,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_candidate_creation_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_candidate_creation_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_order_intent_candidate_materialization_allowed": False,
        "generic_order_intent_validation_allowed": False,
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
        "orders_submitted_by_generic_order_intent_candidate_audit": 0,
        "positions_opened_by_generic_order_intent_candidate_audit": 0,
        "positions_closed_by_generic_order_intent_candidate_audit": 0,
        "paper_state_modified_by_generic_order_intent_candidate_audit": False,
        "paper_status_modified_by_generic_order_intent_candidate_audit": False,
        "broker_submit_called_by_generic_order_intent_candidate_audit": False,
        "broker_close_called_by_generic_order_intent_candidate_audit": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "generic_order_intent_candidate_audit_source_files_present": not missing_source_files,
        "generic_order_intent_candidate_audit_required_markers_present": not missing_source_markers,
        "source_markers_present": source_markers_present,
        "missing_generic_order_intent_candidate_audit_source_files": missing_source_files,
        "missing_generic_order_intent_candidate_audit_source_markers": missing_source_markers,
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "next_step": "prepare_generic_order_intent_validation_preflight_or_continue_observation",
        "recommended_next_patch": "29.4.4u-22 — Generic LSR-v2 paper-only order-intent validation preflight",
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "READY_DECISION",
    "Settings",
    "run_generic_paper_only_order_intent_candidate_audit",
]
