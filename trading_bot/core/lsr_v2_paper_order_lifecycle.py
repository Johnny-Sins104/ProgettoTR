"""Generic LSR-v2 paper order lifecycle draft.

29.4.4u-3 is intentionally read-only and fail-closed.  It drafts the
future reusable paper order/position lifecycle model used by the generic
LSR-v2 paper-cycle controller.  It does not detect candidates, route,
submit, close, mutate paper state, start a scheduler, or send Telegram
messages.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PROMPT = "29.4.4u-3"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_NOT_READY"

U2_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY"

REQUIRED_UPSTREAM_REPORTS: Tuple[Tuple[str, str, str], ...] = (
    ("generic_cycle_controller", "lsr_v2_paper_cycle_controller_draft_report.json", U2_READY_DECISION),
    ("generic_refactor_preflight", "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"),
    ("fourth_submit_execution", "lsr_v2_fourth_trade_submit_execution_report.json", "LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY"),
    ("fourth_submit_preflight", "lsr_v2_fourth_trade_submit_preflight_report.json", "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"),
    ("fourth_handoff_dry_run", "lsr_v2_fourth_trade_handoff_dry_run_report.json", "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"),
    ("fourth_route_preflight", "lsr_v2_fourth_trade_route_preflight_report.json", "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"),
    ("lifecycle_auto_monitor", "lsr_v2_trade_lifecycle_auto_monitor_report.json", "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"),
    ("telegram_dashboard", "lsr_v2_telegram_trade_dashboard_report.json", "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"),
    ("three_trade_postmortem", "lsr_v2_three_trade_postmortem_stability_lock_report.json", "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"),
)

ORDER_LIFECYCLE_STATES: Tuple[str, ...] = (
    "NO_ORDER_INTENT",
    "ORDER_INTENT_DIAGNOSTIC",
    "ORDER_INTENT_VALIDATED",
    "PAPER_SUBMIT_GUARDED",
    "PAPER_POSITION_OPEN",
    "PAPER_POSITION_MONITORING",
    "CLOSE_REQUIRED_DIAGNOSTIC",
    "PAPER_CLOSE_GUARDED",
    "PAPER_POSITION_CLOSED",
    "FINAL_AUDIT_READY",
    "POSTMORTEM_READY",
)

ORDER_LIFECYCLE_TRANSITIONS: Tuple[Tuple[str, str, str], ...] = (
    ("NO_ORDER_INTENT", "paper_order_intent_ready", "ORDER_INTENT_DIAGNOSTIC"),
    ("ORDER_INTENT_DIAGNOSTIC", "submit_preflight_valid_order_intent", "ORDER_INTENT_VALIDATED"),
    ("ORDER_INTENT_VALIDATED", "operator_submit_controls_valid", "PAPER_SUBMIT_GUARDED"),
    ("PAPER_SUBMIT_GUARDED", "paper_position_opened", "PAPER_POSITION_OPEN"),
    ("PAPER_POSITION_OPEN", "monitoring_started", "PAPER_POSITION_MONITORING"),
    ("PAPER_POSITION_MONITORING", "close_required_diagnostic", "CLOSE_REQUIRED_DIAGNOSTIC"),
    ("CLOSE_REQUIRED_DIAGNOSTIC", "operator_close_controls_valid", "PAPER_CLOSE_GUARDED"),
    ("PAPER_CLOSE_GUARDED", "paper_position_closed", "PAPER_POSITION_CLOSED"),
    ("PAPER_POSITION_CLOSED", "final_audit_pass", "FINAL_AUDIT_READY"),
    ("FINAL_AUDIT_READY", "postmortem_pass", "POSTMORTEM_READY"),
)

ORDER_LIFECYCLE_FIELDS: Tuple[str, ...] = (
    "paper_order_intent",
    "paper_submit_result",
    "paper_position_opened",
    "paper_position_monitoring",
    "close_required_diagnostic",
    "paper_close_result",
    "final_audit_result",
    "postmortem_result",
)

BLOCKED_UNTIL_EXPLICIT_ORDER_LIFECYCLE_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_order_lifecycle_activation",
    "generic_order_intent_execution",
    "generic_broker_submit",
    "generic_broker_close",
    "paper_state_mutation",
    "paper_status_mutation",
    "telegram_network_send",
    "scheduler_start",
    "live_or_testnet_or_exchange_broker",
)


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(".")
    data_dir: str = "data"
    report_name: str = "lsr_v2_paper_order_lifecycle_draft_report.json"
    jsonl_name: str = "lsr_v2_paper_order_lifecycle_draft.jsonl"
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


def _build_order_lifecycle_model() -> Dict[str, Any]:
    return {
        "states": list(ORDER_LIFECYCLE_STATES),
        "initial_state": "NO_ORDER_INTENT",
        "terminal_state": "POSTMORTEM_READY",
        "fields": list(ORDER_LIFECYCLE_FIELDS),
        "transitions": [
            {"from": start, "on": event, "to": end, "execution_enabled": False, "mutation_enabled": False}
            for start, event, end in ORDER_LIFECYCLE_TRANSITIONS
        ],
        "execution_enabled": False,
        "mutation_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "paper_state_mutation_enabled": False,
        "paper_status_mutation_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
    }


def run_order_lifecycle_draft(settings: Optional[Settings] = None) -> Dict[str, Any]:
    if settings is None:
        settings = Settings()

    data_dir = settings.data_path
    reports, present_reports, missing_reports, upstream_ready = _load_upstream_reports(settings)
    paper_state = _read_json(data_dir / "paper_state.json", {})
    paper_status = _read_json(data_dir / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(paper_state, paper_status)
    active_env = _active_lsr_v2_env()

    u2 = reports.get("generic_cycle_controller", {})
    u1 = reports.get("generic_refactor_preflight", {})
    t17 = reports.get("fourth_submit_execution", {})
    postmortem = reports.get("three_trade_postmortem", {})
    dashboard = reports.get("telegram_dashboard", {})

    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    fourth_trade_locked = _as_bool(t17.get("fourth_trade_locked", u2.get("fourth_trade_locked", postmortem.get("fourth_trade_locked", True))))
    stability_lock_active = _as_bool(t17.get("stability_lock_active", u2.get("stability_lock_active", postmortem.get("stability_lock_active", True))))
    generic_controller_ready = upstream_ready.get("generic_cycle_controller", False)
    ordinal_expansion_blocked = (
        u2.get("ordinal_trade_patch_expansion_allowed") is False
        and u2.get("fifth_trade_patch_allowed") is False
        and u2.get("sixth_trade_patch_allowed") is False
        and u2.get("seventh_trade_patch_allowed") is False
    )
    no_order_intent = not _as_bool(t17.get("paper_order_intent_ready", u2.get("paper_order_intent_ready", False)))
    no_route_candidate = not _as_bool(t17.get("route_candidate_available", u2.get("route_candidate_available", False)))
    no_submit_occurred = (
        _as_int(t17.get("orders_submitted_by_submit_execution"), 0) == 0
        and _as_int(t17.get("positions_opened_by_submit_execution"), 0) == 0
        and not _as_bool(t17.get("broker_submit_called", False))
        and not _as_bool(t17.get("broker_submit_called_by_submit_execution", False))
    )
    no_close_occurred = (
        _as_int(t17.get("positions_closed_by_submit_execution"), 0) == 0
        and not _as_bool(t17.get("broker_close_called", False))
        and not _as_bool(t17.get("broker_close_called_by_submit_execution", False))
    )
    live_enabled = _as_bool(t17.get("live_enabled", False)) or _as_bool(os.environ.get("LIVE_ENABLED"))
    testnet_enabled = _as_bool(t17.get("testnet_enabled", False)) or _as_bool(os.environ.get("TESTNET_ENABLED"))
    exchange_broker_enabled = _as_bool(t17.get("exchange_broker_enabled", False)) or _as_bool(os.environ.get("EXCHANGE_BROKER_ENABLED"))

    required_readiness = {
        "generic_cycle_controller_ready": generic_controller_ready,
        "upstream_reports_ready": all(upstream_ready.values()),
        "flat_state_confirmed": flat_state_confirmed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": len(active_env) == 0,
        "no_order_intent_currently_available": no_order_intent,
        "no_fourth_route_candidate": no_route_candidate,
        "no_submit_occurred": no_submit_occurred,
        "no_close_occurred": no_close_occurred,
        "ordinal_expansion_blocked": ordinal_expansion_blocked,
        "live_disabled": not live_enabled,
        "testnet_disabled": not testnet_enabled,
        "exchange_broker_disabled": not exchange_broker_enabled,
    }

    blockers: List[str] = []
    if missing_reports:
        blockers.append("missing_upstream_reports")
    if not all(upstream_ready.values()):
        blockers.append("upstream_reports_not_ready")
    if not flat_state_confirmed:
        blockers.append("paper_state_not_flat")
    if not fourth_trade_locked or not stability_lock_active:
        blockers.append("stability_or_fourth_lock_not_confirmed")
    if active_env:
        blockers.append("active_lsr_v2_operator_env_present")
    if live_enabled or testnet_enabled or exchange_broker_enabled:
        blockers.append("live_testnet_or_exchange_enabled")
    if not ordinal_expansion_blocked:
        blockers.append("ordinal_expansion_not_blocked")
    if not no_submit_occurred or not no_close_occurred:
        blockers.append("unexpected_submit_or_close_detected")

    order_lifecycle_model = _build_order_lifecycle_model()
    lifecycle_contract = {
        "trade_ordinal": "N",
        "cycle_id_required": True,
        "paper_only": True,
        "single_position_policy": True,
        "max_open_positions": 1,
        "operator_submit_confirmation_required": True,
        "operator_close_confirmation_required": True,
        "cooldown_after_close_required": True,
        "paper_order_intent_required_for_submit": True,
        "final_audit_required_after_close": True,
        "postmortem_required_after_audit": True,
        "ordinal_module_generation_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
    }

    ready = not blockers
    status = "PASS" if ready else "WARN"
    decision = READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION

    payload: Dict[str, Any] = {
        "prompt": PROMPT,
        "event_type": EVENT_TYPE,
        "generated_at": _utc_now(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_ORDER_LIFECYCLE_DRAFT",
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
        ] + (["GENERIC_ORDER_LIFECYCLE_DRAFT_READY"] if ready else []),
        "blockers": blockers,
        "blocked_until_explicit_order_lifecycle_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_ORDER_LIFECYCLE_IMPLEMENTATION_PATCH),
        "generic_order_lifecycle_draft_ready": ready,
        "generic_order_lifecycle_plan_ready": True,
        "generic_order_lifecycle_contract_ready": True,
        "generic_order_lifecycle_state_model_ready": True,
        "generic_paper_order_intent_model_ready": True,
        "generic_paper_submit_result_model_ready": True,
        "generic_paper_position_lifecycle_model_ready": True,
        "generic_paper_close_result_model_ready": True,
        "generic_final_audit_result_model_ready": True,
        "generic_postmortem_result_model_ready": True,
        "generic_order_lifecycle_contract": lifecycle_contract,
        "generic_order_lifecycle_state_model": order_lifecycle_model,
        "generic_cycle_controller_ready": generic_controller_ready,
        "generic_cycle_controller_draft_ready": _as_bool(u2.get("generic_cycle_controller_draft_ready", False)),
        "generic_trade_state_machine_ready": _as_bool(u2.get("generic_trade_state_machine_ready", False)),
        "generic_trade_cycle_contract_ready": _as_bool(u2.get("generic_trade_cycle_contract_ready", False)),
        "generic_refactor_preflight_ready": upstream_ready.get("generic_refactor_preflight", False),
        "fourth_submit_execution_scaffold_ready": upstream_ready.get("fourth_submit_execution", False),
        "submit_execution_diagnostic": t17.get("submit_execution_diagnostic", ""),
        "route_candidate_available": not no_route_candidate,
        "paper_order_intent_ready": not no_order_intent,
        "paper_order_intent": t17.get("paper_order_intent", {}),
        "no_fourth_route_candidate": no_route_candidate,
        "no_order_intent_currently_available": no_order_intent,
        "lifecycle_state": t17.get("lifecycle_state", u2.get("lifecycle_state", "FLAT_LOCKED")),
        "flat_state_confirmed": flat_state_confirmed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": len(active_env) == 0,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env.keys()),
        "open_positions_after": open_positions_after,
        "paper_status_open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "paper_status_pending_orders_after": pending_orders_after,
        "pending_orders_clear": pending_orders_after == 0,
        "paper_state_status_consistency": True,
        "upstream_readiness": upstream_ready,
        "upstream_reports_present": present_reports,
        "missing_upstream_reports": missing_reports,
        "required_readiness": required_readiness,
        "telegram_dashboard_ready": upstream_ready.get("telegram_dashboard", False),
        "telegram_payload_ready": _as_bool(dashboard.get("telegram_payload_ready", True)),
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_order_lifecycle_execution_allowed": False,
        "generic_order_intent_execution_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_open_position_monitor_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "broker_submit_called_by_generic_order_lifecycle_draft": False,
        "broker_close_called_by_generic_order_lifecycle_draft": False,
        "orders_submitted_by_generic_order_lifecycle_draft": 0,
        "positions_opened_by_generic_order_lifecycle_draft": 0,
        "positions_closed_by_generic_order_lifecycle_draft": 0,
        "paper_state_modified_by_generic_order_lifecycle_draft": False,
        "paper_status_modified_by_generic_order_lifecycle_draft": False,
        "settings": {
            "project_root": str(settings.project_root),
            "data_dir": settings.data_dir,
            "report_name": settings.report_name,
            "jsonl_name": settings.jsonl_name,
            "fail_closed": settings.fail_closed,
        },
        "jsonl": str(settings.data_path / settings.jsonl_name),
        "report": str(settings.data_path / settings.report_name),
        "recommended_next_patch": "29.4.4u-4 — Generic LSR-v2 supervised re-arm policy draft",
        "next_step": "prepare_generic_supervised_rearm_policy_draft_or_wait_for_real_candidate",
    }

    _write_json(settings.data_path / settings.report_name, payload)
    _append_jsonl(settings.data_path / settings.jsonl_name, payload)
    return payload


def main() -> int:
    result = run_order_lifecycle_draft()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
