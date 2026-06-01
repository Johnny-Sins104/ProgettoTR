"""Generic LSR-v2 paper-only candidate detection readiness preflight.

29.4.4u-16 is intentionally readiness/preflight-only, read-only, and
fail-closed. It prepares the generic, non-ordinal LSR-v2 paper-only candidate
readiness surface after the runtime snapshot parity lock. It does not perform
candidate detection, route a candidate, build an order intent, submit, close,
call a broker, mutate state, start a scheduler, send Telegram messages, or
enable live/testnet/exchange access.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

PROMPT = "29.4.4u-16"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT_NOT_READY"

U15_READY_DECISION = "LSR_V2_GENERIC_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK_READY"

READINESS_STAGES: Tuple[str, ...] = (
    "load_engine_runner_adapter_visibility_parity_lock",
    "verify_flat_locked_state",
    "verify_single_position_policy",
    "verify_no_route_candidate",
    "verify_no_paper_order_intent",
    "verify_no_operator_env",
    "verify_execution_flags_fail_closed",
    "verify_source_markers",
    "map_generic_candidate_detection_sources",
    "map_generic_candidate_detection_gate_model",
    "map_generic_candidate_detection_safety_outputs",
    "prepare_future_generic_candidate_detection_audit",
)

CANDIDATE_SOURCE_MAP: Tuple[str, ...] = (
    "paper_events_jsonl_diagnostic_read",
    "generic_runtime_snapshot_artifact_read",
    "generic_order_lifecycle_state_read",
    "generic_rearm_policy_state_read",
    "paper_state_status_safety_read",
    "strategy_signal_diagnostic_read",
)

BLOCKED_UNTIL_EXPLICIT_CANDIDATE_DETECTION_PATCH: Tuple[str, ...] = (
    "generic_candidate_detection_runtime_activation",
    "generic_candidate_scan_execution",
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
        "trading_bot/core/lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock.py",
        ("GENERIC_LSR_V2_RUNTIME_SNAPSHOT_ENGINE_RUNNER_ADAPTER_VISIBILITY_PARITY_LOCK", "adapter_visibility_parity_locked"),
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
    "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_execution_allowed",
    "generic_runtime_snapshot_engine_runner_adapter_visibility_parity_audit_execution_allowed",
    "generic_runtime_snapshot_footer_banner_engine_runner_read_only_adapter_execution_allowed",
    "generic_candidate_detection_allowed",
    "generic_route_execution_allowed",
    "generic_handoff_execution_allowed",
    "generic_submit_execution_allowed",
    "generic_close_execution_allowed",
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
    report_name: str = "lsr_v2_generic_paper_only_candidate_detection_readiness_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_only_candidate_detection_readiness_preflight.jsonl"
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


def _bool(data: Mapping[str, Any], key: str, default: bool = False) -> bool:
    return data.get(key, default) is True


def _int(data: Mapping[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return default


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


def _candidate_readiness_map() -> Dict[str, Any]:
    return {
        "mode": "candidate_detection_readiness_preflight_only",
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
            for stage in READINESS_STAGES
        ],
        "required_future_controls": {
            "generic_rearm_operator_gate_required": True,
            "max_open_positions": 1,
            "flat_state_required": True,
            "pending_orders_required": 0,
            "paper_only_required": True,
            "live_testnet_exchange_required_off": True,
        },
    }


def run_generic_paper_only_candidate_detection_readiness_preflight(settings: Settings | None = None) -> Dict[str, Any]:
    settings = settings or Settings()
    data_path = settings.data_path
    lock_report_name = "lsr_v2_generic_runtime_snapshot_engine_runner_adapter_visibility_parity_lock_report.json"
    lock = _read_json(data_path / lock_report_name)

    missing_upstream_reports: List[str] = []
    not_ready_upstream_reports: List[str] = []
    if not lock:
        missing_upstream_reports.append(lock_report_name)
    elif lock.get("status") != "PASS" or lock.get("decision") != U15_READY_DECISION:
        not_ready_upstream_reports.append(lock_report_name)

    active_env = _active_lsr_env()
    source_markers_present, missing_source_files, missing_source_markers = _source_marker_audit(settings.project_root)

    open_positions_after = _int(lock, "open_positions_after", 0)
    pending_orders_after = _int(lock, "pending_orders_after", 0)
    route_candidate_available = _bool(lock, "route_candidate_available", False)
    paper_order_intent_ready = _bool(lock, "paper_order_intent_ready", False)
    lifecycle_state = str(lock.get("lifecycle_state", "UNKNOWN"))

    readiness_checks: Dict[str, bool] = {
        "parity_lock_ready": not missing_upstream_reports and not not_ready_upstream_reports,
        "adapter_visibility_parity_locked": _bool(lock, "adapter_visibility_parity_locked", False),
        "flat_locked_state": lifecycle_state == "FLAT_LOCKED",
        "flat_positions": open_positions_after == 0,
        "pending_orders_clear": pending_orders_after == 0,
        "no_route_candidate": not route_candidate_available,
        "no_paper_order_intent": not paper_order_intent_ready,
        "operator_env_absent": not active_env,
        "execution_flags_fail_closed": _all_false(lock, FALSE_EXECUTION_KEYS),
        "source_markers_present": source_markers_present,
        "no_submit_or_close_occurred": _int(lock, "orders_submitted_by_engine_runner_adapter_visibility_parity_lock", 0) == 0
        and _int(lock, "positions_opened_by_engine_runner_adapter_visibility_parity_lock", 0) == 0
        and _int(lock, "positions_closed_by_engine_runner_adapter_visibility_parity_lock", 0) == 0,
        "no_state_mutation": lock.get("paper_state_modified_by_engine_runner_adapter_visibility_parity_lock") is False
        and lock.get("paper_status_modified_by_engine_runner_adapter_visibility_parity_lock") is False,
        "live_disabled": lock.get("live_enabled") is False,
        "testnet_disabled": lock.get("testnet_enabled") is False,
        "exchange_broker_disabled": lock.get("exchange_broker_enabled") is False,
    }

    blockers = [key for key, value in readiness_checks.items() if not value]
    ready = not blockers
    status = "PASS" if ready else "WARN"
    decision = READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION

    candidate_readiness_map = _candidate_readiness_map()
    generated_at = _utc_now()

    report: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": generated_at,
        "status": status,
        "decision": decision,
        "report": str(data_path / settings.report_name),
        "jsonl": str(data_path / settings.jsonl_name),
        "blockers": blockers,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ONLY_CANDIDATE_DETECTION_READINESS_PREFLIGHT",
            "READINESS_PREFLIGHT_ONLY",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "NO_CANDIDATE_SCAN_EXECUTION",
            "NO_ROUTE_EXECUTION",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_BROKER_CALL",
            "NO_STATE_MUTATION",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
        ] + (["GENERIC_CANDIDATE_DETECTION_READINESS_PREFLIGHT_READY"] if ready else ["KEEP_DIAGNOSTIC"]),
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "missing_upstream_reports": missing_upstream_reports,
        "not_ready_upstream_reports": not_ready_upstream_reports,
        "upstream_reports_present": ([] if missing_upstream_reports else [lock_report_name] if lock else []),
        "required_readiness": readiness_checks,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env.keys()),
        "operator_env_absent": not active_env,
        "generic_candidate_detection_readiness_ready": ready,
        "generic_candidate_detection_readiness_preflight_ready": ready,
        "generic_candidate_detection_preflight_ready": ready,
        "generic_candidate_detection_plan_ready": ready,
        "generic_candidate_detection_contract_ready": ready,
        "generic_candidate_detection_map_ready": ready,
        "generic_candidate_detection_source_map_ready": ready,
        "generic_candidate_detection_gate_model_ready": ready,
        "generic_candidate_detection_fail_closed_ready": ready,
        "generic_candidate_detection_readiness_map": candidate_readiness_map,
        "candidate_detection_sources": list(CANDIDATE_SOURCE_MAP),
        "candidate_detection_scan_deferred": True,
        "candidate_detection_scan_executed": False,
        "candidate_detected_diagnostic": False,
        "candidate_detected_diagnostic_count": 0,
        "route_candidate_available": route_candidate_available,
        "paper_order_intent_ready": paper_order_intent_ready,
        "no_route_candidate": not route_candidate_available,
        "no_order_intent_currently_available": not paper_order_intent_ready,
        "lifecycle_state": lifecycle_state,
        "fourth_trade_locked": _bool(lock, "fourth_trade_locked", True),
        "stability_lock_active": _bool(lock, "stability_lock_active", True),
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "paper_state_status_consistency": _bool(lock, "paper_state_status_consistency", True),
        "source_markers_present": source_markers_present,
        "generic_candidate_detection_required_markers_present": source_markers_present,
        "generic_candidate_detection_source_files_present": not missing_source_files,
        "missing_generic_candidate_detection_source_files": missing_source_files,
        "missing_generic_candidate_detection_source_markers": missing_source_markers,
        "blocked_until_explicit_candidate_detection_patch": list(BLOCKED_UNTIL_EXPLICIT_CANDIDATE_DETECTION_PATCH),
        "next_step": "prepare_generic_candidate_detection_audit_or_wait_for_real_candidate_window",
        "recommended_next_patch": "29.4.4u-17 — Generic LSR-v2 paper-only candidate detection audit",
        # Explicit fail-closed execution/mutation/network flags.
        "generic_candidate_detection_readiness_execution_allowed": False,
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
        "generic_lsr_v2_paper_cycle_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "paper_engine_mutation_allowed": False,
        "runner_mutation_allowed": False,
        "launcher_mutation_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "broker_submit_called_by_generic_candidate_detection_readiness_preflight": False,
        "broker_close_called_by_generic_candidate_detection_readiness_preflight": False,
        "orders_submitted_by_generic_candidate_detection_readiness_preflight": 0,
        "positions_opened_by_generic_candidate_detection_readiness_preflight": 0,
        "positions_closed_by_generic_candidate_detection_readiness_preflight": 0,
        "paper_state_modified_by_generic_candidate_detection_readiness_preflight": False,
        "paper_status_modified_by_generic_candidate_detection_readiness_preflight": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
    }

    _write_json(data_path / settings.report_name, report)
    _append_jsonl(data_path / settings.jsonl_name, report)
    return report


if __name__ == "__main__":
    print(json.dumps(run_generic_paper_only_candidate_detection_readiness_preflight(), indent=2, sort_keys=True))
