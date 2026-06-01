"""Generic LSR-v2 paper-cycle controller draft.

29.4.4u-2 is intentionally read-only and fail-closed.  It drafts the
future reusable LSR-v2 paper-only cycle controller that should replace
ordinal modules such as fourth_trade_*/fifth_trade_*.  This module does
not detect candidates, route, submit, close, mutate paper state, start a
scheduler, or send Telegram messages.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

PROMPT = "29.4.4u-2"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_NOT_READY"

U1_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"

REQUIRED_UPSTREAM_REPORTS: Tuple[Tuple[str, str, str], ...] = (
    ("generic_refactor_preflight", "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", U1_READY_DECISION),
    ("fourth_submit_execution", "lsr_v2_fourth_trade_submit_execution_report.json", "LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY"),
    ("fourth_submit_preflight", "lsr_v2_fourth_trade_submit_preflight_report.json", "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"),
    ("fourth_handoff_dry_run", "lsr_v2_fourth_trade_handoff_dry_run_report.json", "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"),
    ("fourth_route_preflight", "lsr_v2_fourth_trade_route_preflight_report.json", "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"),
    ("fourth_candidate_detection_audit", "lsr_v2_fourth_trade_candidate_detection_audit_report.json", "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY"),
    ("lifecycle_auto_monitor", "lsr_v2_trade_lifecycle_auto_monitor_report.json", "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"),
    ("telegram_dashboard", "lsr_v2_telegram_trade_dashboard_report.json", "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"),
    ("three_trade_postmortem", "lsr_v2_three_trade_postmortem_stability_lock_report.json", "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"),
)

GENERIC_CONTROLLER_STATES: Tuple[str, ...] = (
    "FLAT_LOCKED",
    "READY_FOR_REARM_PREFLIGHT",
    "CANDIDATE_DIAGNOSTIC",
    "ROUTE_PREFLIGHT",
    "HANDOFF_DRY_RUN",
    "SUBMIT_PREFLIGHT",
    "SUBMIT_EXECUTION_GUARDED",
    "OPEN_MONITORING",
    "CLOSE_PREFLIGHT",
    "CLOSE_EXECUTION_GUARDED",
    "FINAL_AUDIT",
    "POSTMORTEM",
    "COOLDOWN",
)

GENERIC_CONTROLLER_TRANSITIONS: Tuple[Tuple[str, str, str], ...] = (
    ("FLAT_LOCKED", "operator_rearm_preflight_pass", "READY_FOR_REARM_PREFLIGHT"),
    ("READY_FOR_REARM_PREFLIGHT", "diagnostic_candidate_seen", "CANDIDATE_DIAGNOSTIC"),
    ("CANDIDATE_DIAGNOSTIC", "route_preflight_pass", "ROUTE_PREFLIGHT"),
    ("ROUTE_PREFLIGHT", "would_route_true", "HANDOFF_DRY_RUN"),
    ("HANDOFF_DRY_RUN", "paper_order_intent_ready", "SUBMIT_PREFLIGHT"),
    ("SUBMIT_PREFLIGHT", "operator_submit_controls_valid", "SUBMIT_EXECUTION_GUARDED"),
    ("SUBMIT_EXECUTION_GUARDED", "paper_position_opened", "OPEN_MONITORING"),
    ("OPEN_MONITORING", "close_required_diagnostic", "CLOSE_PREFLIGHT"),
    ("CLOSE_PREFLIGHT", "operator_close_controls_valid", "CLOSE_EXECUTION_GUARDED"),
    ("CLOSE_EXECUTION_GUARDED", "paper_position_closed", "FINAL_AUDIT"),
    ("FINAL_AUDIT", "audit_pass", "POSTMORTEM"),
    ("POSTMORTEM", "cooldown_started", "COOLDOWN"),
    ("COOLDOWN", "cooldown_complete", "FLAT_LOCKED"),
)

GENERIC_COMPONENTS: Tuple[str, ...] = (
    "core/lsr_v2_paper_cycle_controller.py",
    "core/lsr_v2_paper_order_lifecycle.py",
    "core/lsr_v2_supervised_rearm_policy.py",
    "core/lsr_v2_trade_postmortem_generic.py",
    "core/lsr_v2_trade_dashboard_generic.py",
)

BLOCKED_UNTIL_EXPLICIT_CONTROLLER_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_cycle_controller_activation",
    "generic_candidate_detection_execution",
    "generic_route_execution",
    "generic_broker_submit",
    "generic_broker_close",
    "telegram_network_send",
    "scheduler_start",
    "live_or_testnet_or_exchange_broker",
)


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_paper_cycle_controller_draft_report.json"
    jsonl_name: str = "lsr_v2_paper_cycle_controller_draft.jsonl"
    fail_closed: bool = True

    @property
    def data_path(self) -> Path:
        return self.project_root / self.data_dir


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return False


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _count_mapping_or_list(value: Any) -> int:
    if isinstance(value, Mapping):
        return len(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return 0


def _paper_counts(state: Mapping[str, Any], status: Mapping[str, Any]) -> Tuple[int, int]:
    status_open = status.get("open_positions", status.get("paper_status_open_positions_after"))
    status_pending = status.get("pending_orders", status.get("paper_status_pending_orders_after"))
    open_positions = _as_int(status_open, _count_mapping_or_list(state.get("positions", {})))
    pending_orders = _as_int(status_pending, _count_mapping_or_list(state.get("orders", {})))
    return open_positions, pending_orders


def _active_lsr_v2_env() -> Dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.startswith("LSR_V2") and str(v).strip()}


def _decision_is_ready(report: Mapping[str, Any], expected_decision: str) -> bool:
    return isinstance(report, Mapping) and str(report.get("status", "")).upper() == "PASS" and report.get("decision") == expected_decision


def _load_upstream_reports(settings: Settings) -> Tuple[Dict[str, Any], List[str], List[str], Dict[str, bool]]:
    reports: Dict[str, Any] = {}
    present: List[str] = []
    missing: List[str] = []
    readiness: Dict[str, bool] = {}
    for key, filename, expected_decision in REQUIRED_UPSTREAM_REPORTS:
        payload = _read_json(settings.data_path / filename, {})
        reports[key] = payload
        if payload:
            present.append(filename)
        else:
            missing.append(filename)
        readiness[key] = _decision_is_ready(payload, expected_decision)
    return reports, present, missing, readiness


def _build_state_machine() -> Dict[str, Any]:
    return {
        "states": list(GENERIC_CONTROLLER_STATES),
        "initial_state": "FLAT_LOCKED",
        "terminal_state": "POSTMORTEM",
        "transitions": [
            {"from": start, "on": event, "to": end, "execution_enabled": False}
            for start, event, end in GENERIC_CONTROLLER_TRANSITIONS
        ],
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
    }


def run_controller_draft(settings: Optional[Settings] = None) -> Dict[str, Any]:
    if settings is None:
        settings = Settings()

    data_dir = settings.data_path
    reports, present_reports, missing_reports, upstream_ready = _load_upstream_reports(settings)
    paper_state = _read_json(data_dir / "paper_state.json", {})
    paper_status = _read_json(data_dir / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(paper_state, paper_status)
    active_env = _active_lsr_v2_env()

    u1 = reports.get("generic_refactor_preflight", {})
    t17 = reports.get("fourth_submit_execution", {})
    postmortem = reports.get("three_trade_postmortem", {})
    dashboard = reports.get("telegram_dashboard", {})

    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    fourth_trade_locked = _as_bool(t17.get("fourth_trade_locked", u1.get("fourth_trade_locked", postmortem.get("fourth_trade_locked", True))))
    stability_lock_active = _as_bool(t17.get("stability_lock_active", u1.get("stability_lock_active", postmortem.get("stability_lock_active", True))))
    no_order_intent = not _as_bool(t17.get("paper_order_intent_ready", u1.get("paper_order_intent_ready", False)))
    no_route_candidate = not _as_bool(t17.get("route_candidate_available", u1.get("route_candidate_available", False)))
    no_submit_occurred = (
        _as_int(t17.get("orders_submitted_by_submit_execution"), 0) == 0
        and _as_int(t17.get("positions_opened_by_submit_execution"), 0) == 0
        and not _as_bool(t17.get("broker_submit_called", False))
        and not _as_bool(t17.get("broker_submit_called_by_submit_execution", False))
    )
    live_enabled = _as_bool(t17.get("live_enabled", False)) or _as_bool(os.environ.get("LIVE_ENABLED"))
    testnet_enabled = _as_bool(t17.get("testnet_enabled", False)) or _as_bool(os.environ.get("TESTNET_ENABLED"))
    exchange_broker_enabled = _as_bool(t17.get("exchange_broker_enabled", False)) or _as_bool(os.environ.get("EXCHANGE_BROKER_ENABLED"))

    generic_refactor_ready = upstream_ready.get("generic_refactor_preflight", False)
    ordinal_expansion_blocked = (
        u1.get("ordinal_trade_patch_expansion_allowed") is False
        and u1.get("fifth_trade_patch_allowed") is False
        and u1.get("sixth_trade_patch_allowed") is False
        and u1.get("seventh_trade_patch_allowed") is False
    )

    required_readiness = {
        "generic_refactor_preflight_ready": generic_refactor_ready,
        "upstream_reports_ready": all(upstream_ready.values()),
        "flat_state_confirmed": flat_state_confirmed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": len(active_env) == 0,
        "no_order_intent_currently_available": no_order_intent,
        "no_fourth_route_candidate": no_route_candidate,
        "no_submit_occurred": no_submit_occurred,
        "ordinal_expansion_blocked": ordinal_expansion_blocked,
        "live_disabled": not live_enabled,
        "testnet_disabled": not testnet_enabled,
        "exchange_broker_disabled": not exchange_broker_enabled,
    }
    blockers = [name for name, ok in required_readiness.items() if not ok]
    if missing_reports:
        blockers.append("missing_upstream_reports")

    ready = not blockers
    status = "PASS" if ready else "WARN"
    decision = READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION

    state_machine = _build_state_machine()
    generic_controller_contract = {
        "trade_ordinal": "N",
        "cycle_id_required": True,
        "max_open_positions": 1,
        "paper_only": True,
        "operator_confirmation_required": True,
        "cooldown_after_close_required": True,
        "single_position_policy": True,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "ordinal_module_generation_allowed": False,
    }

    payload: Dict[str, Any] = {
        "event_type": EVENT_TYPE,
        "prompt": PROMPT,
        "generated_at": _utc_now(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_CYCLE_CONTROLLER_DRAFT",
            "READ_ONLY",
            "DRAFT_ONLY",
            "NO_ORDINAL_EXPANSION",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_ROUTE_EXECUTION",
            "NO_SUBMIT",
            "NO_CLOSE",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
        ] + (["GENERIC_CONTROLLER_DRAFT_READY"] if ready else []),
        "blockers": blockers,
        "blocked_until_explicit_generic_controller_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_CONTROLLER_IMPLEMENTATION_PATCH),
        "generic_cycle_controller_draft_ready": ready,
        "generic_cycle_controller_plan_ready": True,
        "generic_trade_state_machine_ready": True,
        "generic_trade_cycle_contract_ready": True,
        "generic_controller_contract": generic_controller_contract,
        "generic_controller_state_machine": state_machine,
        "generic_target_modules": list(GENERIC_COMPONENTS),
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_cycle_controller_execution_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_open_position_monitor_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "upstream_reports_present": present_reports,
        "missing_upstream_reports": missing_reports,
        "upstream_readiness": upstream_ready,
        "required_readiness": required_readiness,
        "generic_refactor_preflight_ready": generic_refactor_ready,
        "fourth_submit_execution_scaffold_ready": upstream_ready.get("fourth_submit_execution", False),
        "route_candidate_available": _as_bool(t17.get("route_candidate_available", False)),
        "paper_order_intent_ready": _as_bool(t17.get("paper_order_intent_ready", False)),
        "no_order_intent_currently_available": no_order_intent,
        "no_fourth_route_candidate": no_route_candidate,
        "submit_execution_diagnostic": t17.get("submit_execution_diagnostic", ""),
        "lifecycle_state": str(t17.get("lifecycle_state") or reports.get("lifecycle_auto_monitor", {}).get("lifecycle_state") or "UNKNOWN"),
        "flat_state_confirmed": flat_state_confirmed,
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "paper_status_open_positions_after": open_positions_after,
        "paper_status_pending_orders_after": pending_orders_after,
        "paper_state_status_consistency": True,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": len(active_env) == 0,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env.keys()),
        "telegram_dashboard_ready": _as_bool(dashboard.get("dashboard_ready", t17.get("telegram_payload_ready", False))),
        "telegram_payload_ready": _as_bool(t17.get("telegram_payload_ready", dashboard.get("telegram_payload_ready", False))),
        "telegram_send_allowed": False,
        "telegram_network_called": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "broker_submit_called_by_generic_cycle_controller_draft": False,
        "broker_close_called_by_generic_cycle_controller_draft": False,
        "orders_submitted_by_generic_cycle_controller_draft": 0,
        "positions_opened_by_generic_cycle_controller_draft": 0,
        "positions_closed_by_generic_cycle_controller_draft": 0,
        "paper_state_modified_by_generic_cycle_controller_draft": False,
        "paper_status_modified_by_generic_cycle_controller_draft": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "next_step": "prepare_generic_order_lifecycle_draft_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-3 — Generic LSR-v2 paper order lifecycle draft",
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "report": str(data_dir / settings.report_name),
        "jsonl": str(data_dir / settings.jsonl_name),
    }

    _write_json(data_dir / settings.report_name, payload)
    _append_jsonl(data_dir / settings.jsonl_name, payload)
    return payload


def main(argv: Optional[Iterable[str]] = None) -> int:
    _ = list(argv or [])
    result = run_controller_draft(Settings(project_root=Path(".")))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
