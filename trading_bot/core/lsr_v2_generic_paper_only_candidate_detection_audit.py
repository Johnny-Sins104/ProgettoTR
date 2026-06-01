"""Generic LSR-v2 paper-only candidate detection audit.

29.4.4u-17 is intentionally audit-only, read-only, and fail-closed. It
performs a diagnostic, non-executing read of the generic candidate detection
sources mapped by u-16. It may report whether candidate-like evidence is
present, but it never routes, builds or submits an order intent, opens/closes a
position, calls a broker, mutates paper state/status, starts a scheduler, sends
Telegram messages, or enables live/testnet/exchange access.
"""

from __future__ import annotations

import json
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

PROMPT = "29.4.4u-17"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT_NOT_READY"

U16_READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT_READY"

AUDIT_STAGES: Tuple[str, ...] = (
    "load_generic_candidate_detection_readiness_preflight",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_route_candidate",
    "verify_no_paper_order_intent",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "scan_paper_events_jsonl_diagnostic_read",
    "scan_generic_runtime_snapshot_artifact_read",
    "scan_generic_order_lifecycle_state_read",
    "scan_generic_rearm_policy_state_read",
    "scan_paper_state_status_safety_read",
    "scan_strategy_signal_diagnostic_read",
    "publish_generic_candidate_detection_audit_artifact",
)

CANDIDATE_SOURCE_MAP: Tuple[str, ...] = (
    "paper_events_jsonl_diagnostic_read",
    "generic_runtime_snapshot_artifact_read",
    "generic_order_lifecycle_state_read",
    "generic_rearm_policy_state_read",
    "paper_state_status_safety_read",
    "strategy_signal_diagnostic_read",
)

BLOCKED_UNTIL_EXPLICIT_CANDIDATE_ROUTE_PATCH: Tuple[str, ...] = (
    "generic_candidate_detection_runtime_activation",
    "generic_candidate_route_execution",
    "generic_handoff_execution",
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
        "trading_bot/core/lsr_v2_generic_paper_only_candidate_detection_readiness_preflight.py",
        (
            "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT",
            "candidate_detection_sources",
        ),
    ),
    (
        "trading_bot/core/paper_engine.py",
        ("PaperTradingEngine",),
    ),
    (
        "trading_bot/run_paper_trading.py",
        ("no-lsr-v2-engine-read-only-artifact-hook",),
    ),
)

FALSE_EXECUTION_KEYS: Tuple[str, ...] = (
    "generic_candidate_detection_readiness_execution_allowed",
    "generic_candidate_detection_allowed",
    "generic_candidate_scan_execution_allowed",
    "generic_candidate_probe_allowed",
    "generic_route_execution_allowed",
    "generic_handoff_execution_allowed",
    "generic_submit_execution_allowed",
    "generic_close_execution_allowed",
    "paper_engine_mutation_allowed",
    "runner_mutation_allowed",
    "launcher_mutation_allowed",
    "generic_paper_state_mutation_allowed",
    "generic_paper_status_mutation_allowed",
    "paper_only_execution_allowed",
    "future_integrated_operation_allowed",
)

CANDIDATE_BOOLEAN_KEYS: Tuple[str, ...] = (
    "candidate_detected",
    "candidate_detected_diagnostic",
    "generic_candidate_detected_diagnostic",
    "candidate_ready",
    "candidate_available",
    "route_candidate_available",
    "paper_order_intent_ready",
    "would_route",
    "would_create_order",
    "would_submit",
    "paper_order_intent_validated",
)

CANDIDATE_COUNT_KEYS: Tuple[str, ...] = (
    "candidate_detected_count",
    "candidate_detected_diagnostic_count",
    "generic_candidate_detected_diagnostic_count",
    "candidate_ready_count",
    "candidate_count",
    "route_candidate_count",
    "paper_order_intent_count",
    "would_create_order_count",
    "would_submit_count",
)

CANDIDATE_TEXT_TOKENS: Tuple[str, ...] = (
    "GENERIC_LSR_V2_CANDIDATE",
    "LSR_V2_CANDIDATE",
    "CANDIDATE_DETECTED",
    "CANDIDATE_READY",
    "ORDER_INTENT_VALIDATED",
)


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_generic_paper_only_candidate_detection_audit_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_candidate_detection_audit.jsonl"
    max_event_lines: int = 50000
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
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


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


def _recent_jsonl_records(path: Path, max_lines: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    lines: Deque[str] = deque(maxlen=max_lines)
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    lines.append(line)
    except OSError:
        return []
    records: List[Dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _value_truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value > 0
    if isinstance(value, str):
        return value.upper() in {"TRUE", "YES", "READY", "PASS", "DETECTED"}
    return False


def _payload_has_candidate_evidence(payload: Mapping[str, Any]) -> bool:
    for key in CANDIDATE_BOOLEAN_KEYS:
        if _value_truthy(payload.get(key)):
            return True
    for key in CANDIDATE_COUNT_KEYS:
        if _safe_int(payload.get(key), 0) > 0:
            return True
    event_type = str(payload.get("event_type", ""))
    decision = str(payload.get("decision", ""))
    labels = " ".join(str(item) for item in payload.get("classification_labels", []) if item is not None)
    text = f"{event_type} {decision} {labels}".upper()
    return any(token in text for token in CANDIDATE_TEXT_TOKENS)


def _extract_candidate_summary(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "event_type": payload.get("event_type", ""),
        "decision": payload.get("decision", ""),
        "symbol": payload.get("symbol", payload.get("symbols", "")),
        "side": payload.get("side", payload.get("sides", "")),
        "cycle_id": payload.get("cycle_id", ""),
        "candidate_detected_diagnostic": payload.get("candidate_detected_diagnostic", payload.get("candidate_detected", False)),
        "route_candidate_available": payload.get("route_candidate_available", False),
        "paper_order_intent_ready": payload.get("paper_order_intent_ready", False),
    }


def _scan_records(records: Iterable[Mapping[str, Any]], max_examples: int = 5) -> Tuple[int, List[Dict[str, Any]]]:
    count = 0
    examples: List[Dict[str, Any]] = []
    for payload in records:
        if _payload_has_candidate_evidence(payload):
            count += 1
            if len(examples) < max_examples:
                examples.append(_extract_candidate_summary(payload))
    return count, examples


def _scan_report_payload(payload: Mapping[str, Any]) -> Tuple[int, List[Dict[str, Any]]]:
    if not payload:
        return 0, []
    count = 1 if _payload_has_candidate_evidence(payload) else 0
    return count, [_extract_candidate_summary(payload)] if count else []


def _candidate_audit_map() -> Dict[str, Any]:
    return {
        "mode": "candidate_detection_audit_only",
        "paper_only": True,
        "execution_enabled": False,
        "mutation_enabled": False,
        "scheduler_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "telegram_network_send_enabled": False,
        "ordinal_module_generation_allowed": False,
        "candidate_detection_sources": list(CANDIDATE_SOURCE_MAP),
        "stages": [
            {"stage": stage, "execution_allowed": False, "state_mutation_allowed": False}
            for stage in AUDIT_STAGES
        ],
        "diagnostic_outputs": {
            "candidate_detected_diagnostic": "boolean",
            "candidate_detected_diagnostic_count": "integer",
            "candidate_detection_source_counts": "map",
            "candidate_diagnostic_examples": "bounded_list",
        },
        "required_future_controls_before_route": {
            "explicit_generic_route_preflight_patch_required": True,
            "generic_rearm_operator_gate_required": True,
            "max_open_positions": 1,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
        },
    }


def run_generic_paper_only_candidate_detection_audit(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    readiness_report_name = "lsr_v2_generic_paper_only_candidate_detection_readiness_preflight_report.json"
    readiness = _read_json(data_path / readiness_report_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not readiness:
        missing_upstream_reports.append(readiness_report_name)
    elif readiness.get("status") != "PASS" or readiness.get("decision") != U16_READY_DECISION:
        not_ready_upstream_reports.append(readiness_report_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)
    execution_flags_fail_closed = _all_false(readiness, FALSE_EXECUTION_KEYS)

    candidate_source_counts: Dict[str, int] = {source: 0 for source in CANDIDATE_SOURCE_MAP}
    candidate_examples: List[Dict[str, Any]] = []
    sources_present: List[str] = []

    paper_events_records = _recent_jsonl_records(data_path / "paper_events.jsonl", settings.max_event_lines)
    if paper_events_records:
        sources_present.append("paper_events_jsonl_diagnostic_read")
    paper_event_count, examples = _scan_records(paper_events_records)
    candidate_source_counts["paper_events_jsonl_diagnostic_read"] = paper_event_count
    candidate_examples.extend(examples)

    report_sources: Tuple[Tuple[str, str], ...] = (
        ("generic_runtime_snapshot_artifact_read", "lsr_v2_generic_paper_cycle_runtime_snapshot_hook_report.json"),
        ("generic_order_lifecycle_state_read", "lsr_v2_paper_order_lifecycle_draft_report.json"),
        ("generic_rearm_policy_state_read", "lsr_v2_supervised_rearm_policy_draft_report.json"),
        ("strategy_signal_diagnostic_read", "lsr_v2_fourth_trade_candidate_detection_audit_report.json"),
    )
    optional_source_reports_present: List[str] = []
    for source_name, report_name in report_sources:
        payload = _read_json(data_path / report_name)
        if payload:
            optional_source_reports_present.append(report_name)
            sources_present.append(source_name)
        count, examples = _scan_report_payload(payload)
        candidate_source_counts[source_name] = count
        candidate_examples.extend(examples)

    paper_state = _read_json(data_path / "paper_state.json")
    paper_status = _read_json(data_path / "paper_status.json")
    if paper_state or paper_status:
        sources_present.append("paper_state_status_safety_read")
    safety_count, safety_examples = _scan_records([paper_state, paper_status])
    candidate_source_counts["paper_state_status_safety_read"] = safety_count
    candidate_examples.extend(safety_examples)

    total_candidate_count = sum(candidate_source_counts.values())
    candidate_examples = candidate_examples[:5]
    candidate_detected = total_candidate_count > 0

    required_readiness = {
        "candidate_detection_readiness_ready": bool(readiness.get("generic_candidate_detection_readiness_ready") is True),
        "flat_locked_state": readiness.get("lifecycle_state") == "FLAT_LOCKED",
        "flat_positions": _safe_int(readiness.get("open_positions_after"), 0) == 0,
        "pending_orders_clear": _safe_int(readiness.get("pending_orders_after"), 0) == 0,
        "no_route_candidate": readiness.get("route_candidate_available") is False,
        "no_paper_order_intent": readiness.get("paper_order_intent_ready") is False,
        "operator_env_absent": not active_env,
        "execution_flags_fail_closed": execution_flags_fail_closed,
        "source_markers_present": source_markers_present,
        "live_disabled": readiness.get("live_enabled") is False,
        "testnet_disabled": readiness.get("testnet_enabled") is False,
        "exchange_broker_disabled": readiness.get("exchange_broker_enabled") is False,
        "no_state_mutation": readiness.get("paper_state_modified_by_generic_candidate_detection_readiness_preflight") is False
        and readiness.get("paper_status_modified_by_generic_candidate_detection_readiness_preflight") is False,
        "no_submit_or_close_occurred": _safe_int(readiness.get("orders_submitted_by_generic_candidate_detection_readiness_preflight"), 0) == 0
        and _safe_int(readiness.get("positions_opened_by_generic_candidate_detection_readiness_preflight"), 0) == 0
        and _safe_int(readiness.get("positions_closed_by_generic_candidate_detection_readiness_preflight"), 0) == 0,
    }

    blockers = [name for name, ok in required_readiness.items() if not ok]
    if missing_upstream_reports:
        blockers.append("candidate_detection_readiness_report_present")
    if not_ready_upstream_reports:
        blockers.append("candidate_detection_readiness_report_ready")

    status = "PASS" if not blockers else "WARN"
    decision = READY_DECISION if status == "PASS" else KEEP_DIAGNOSTIC_DECISION

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": status,
        "decision": decision,
        "blockers": blockers,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_DETECTION_AUDIT",
            "AUDIT_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "DIAGNOSTIC_CANDIDATE_SCAN_ONLY",
            "NO_ROUTE_EXECUTION",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
            "GENERIC_CANDIDATE_DETECTION_AUDIT_READY" if status == "PASS" else "GENERIC_CANDIDATE_DETECTION_AUDIT_NOT_READY",
        ],
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "max_event_lines": settings.max_event_lines,
            "fail_closed": settings.fail_closed,
        },
        "generic_candidate_detection_audit_ready": status == "PASS",
        "generic_candidate_detection_audit_plan_ready": True,
        "generic_candidate_detection_audit_contract_ready": True,
        "generic_candidate_detection_audit_map_ready": True,
        "generic_candidate_detection_diagnostic_scan_ready": True,
        "generic_candidate_detection_source_map_ready": True,
        "generic_candidate_detection_fail_closed_ready": True,
        "candidate_detection_diagnostic_scan_executed": True,
        "candidate_detection_scan_executed": False,
        "candidate_detection_scan_deferred": False,
        "candidate_detection_sources": list(CANDIDATE_SOURCE_MAP),
        "candidate_detection_sources_present": sources_present,
        "candidate_detection_source_counts": candidate_source_counts,
        "candidate_detected_diagnostic": candidate_detected,
        "candidate_detected_diagnostic_count": total_candidate_count,
        "candidate_diagnostic_examples": candidate_examples,
        "optional_source_reports_present": optional_source_reports_present,
        "generic_candidate_detection_audit_map": _candidate_audit_map(),
        "required_readiness": required_readiness,
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "missing_generic_candidate_detection_audit_source_files": missing_source_files,
        "missing_generic_candidate_detection_audit_source_markers": missing_source_markers,
        "generic_candidate_detection_audit_source_files_present": not missing_source_files,
        "generic_candidate_detection_audit_required_markers_present": source_markers_present,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env),
        "operator_env_absent": not active_env,
        "lifecycle_state": readiness.get("lifecycle_state", ""),
        "fourth_trade_locked": readiness.get("fourth_trade_locked", True),
        "stability_lock_active": readiness.get("stability_lock_active", True),
        "route_candidate_available": readiness.get("route_candidate_available", False),
        "paper_order_intent_ready": readiness.get("paper_order_intent_ready", False),
        "no_route_candidate": readiness.get("route_candidate_available") is False,
        "no_order_intent_currently_available": readiness.get("paper_order_intent_ready") is False,
        "open_positions_after": _safe_int(readiness.get("open_positions_after"), 0),
        "pending_orders_after": _safe_int(readiness.get("pending_orders_after"), 0),
        "paper_state_status_consistency": readiness.get("paper_state_status_consistency", True),
        "source_markers_present": source_markers_present,
        "upstream_reports_present": [readiness_report_name] if readiness else [],
        "blocked_until_explicit_candidate_route_patch": list(BLOCKED_UNTIL_EXPLICIT_CANDIDATE_ROUTE_PATCH),
        "next_step": "prepare_generic_candidate_route_preflight_if_candidate_detected_or_continue_observation",
        "recommended_next_patch": "29.4.4u-18 — Generic LSR-v2 paper-only candidate route preflight",
        # execution/mutation/safety interlocks intentionally false
        "generic_candidate_detection_audit_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_candidate_scan_execution_allowed": False,
        "generic_candidate_probe_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
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
        "orders_submitted_by_generic_candidate_detection_audit": 0,
        "positions_opened_by_generic_candidate_detection_audit": 0,
        "positions_closed_by_generic_candidate_detection_audit": 0,
        "paper_state_modified_by_generic_candidate_detection_audit": False,
        "paper_status_modified_by_generic_candidate_detection_audit": False,
        "broker_submit_called_by_generic_candidate_detection_audit": False,
        "broker_close_called_by_generic_candidate_detection_audit": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


__all__ = [
    "KEEP_DIAGNOSTIC_DECISION",
    "READY_DECISION",
    "Settings",
    "run_generic_paper_only_candidate_detection_audit",
]
