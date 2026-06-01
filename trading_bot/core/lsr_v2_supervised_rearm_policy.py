"""Generic LSR-v2 supervised re-arm policy draft.

29.4.4u-4 is intentionally read-only and fail-closed. It drafts the
future reusable re-arm policy for the generic LSR-v2 paper-cycle controller.
It does not detect candidates, route, submit, close, mutate paper state,
start a scheduler, or send Telegram messages.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

PROMPT = "29.4.4u-4"
EVENT_TYPE = "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT"
READY_DECISION = "LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_SUPERVISED_REARM_POLICY_DRAFT_NOT_READY"

U3_READY_DECISION = "LSR_V2_GENERIC_PAPER_ORDER_LIFECYCLE_DRAFT_READY"
U2_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_CONTROLLER_DRAFT_READY"
U1_READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"

GENERIC_REARM_ENABLE_ENV = "LSR_V2_GENERIC_REARM_ENABLE"
GENERIC_REARM_CONFIRMATION_ENV = "LSR_V2_GENERIC_REARM_CONFIRMATION"
GENERIC_REARM_MAX_POSITIONS_ENV = "LSR_V2_GENERIC_REARM_MAX_POSITIONS"
GENERIC_REARM_CONFIRMATION_PHRASE = "I_UNDERSTAND_REARM_GENERIC_PAPER_TRADE_ONLY"

REQUIRED_UPSTREAM_REPORTS: Tuple[Tuple[str, str, str], ...] = (
    ("generic_order_lifecycle", "lsr_v2_paper_order_lifecycle_draft_report.json", U3_READY_DECISION),
    ("generic_cycle_controller", "lsr_v2_paper_cycle_controller_draft_report.json", U2_READY_DECISION),
    ("generic_refactor_preflight", "lsr_v2_generic_paper_cycle_refactor_preflight_report.json", U1_READY_DECISION),
    ("fourth_submit_execution", "lsr_v2_fourth_trade_submit_execution_report.json", "LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY"),
    ("fourth_submit_preflight", "lsr_v2_fourth_trade_submit_preflight_report.json", "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"),
    ("fourth_handoff_dry_run", "lsr_v2_fourth_trade_handoff_dry_run_report.json", "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"),
    ("fourth_route_preflight", "lsr_v2_fourth_trade_route_preflight_report.json", "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"),
    ("lifecycle_auto_monitor", "lsr_v2_trade_lifecycle_auto_monitor_report.json", "LSR_V2_TRADE_LIFECYCLE_AUTO_MONITOR_READY"),
    ("telegram_dashboard", "lsr_v2_telegram_trade_dashboard_report.json", "LSR_V2_TELEGRAM_TRADE_DASHBOARD_READY"),
    ("three_trade_postmortem", "lsr_v2_three_trade_postmortem_stability_lock_report.json", "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"),
)

REARM_POLICY_STATES: Tuple[str, ...] = (
    "FLAT_LOCKED",
    "COOLDOWN_CHECK",
    "OPERATOR_REARM_PREFLIGHT",
    "REARM_READY_DIAGNOSTIC",
    "CANDIDATE_DIAGNOSTIC_ALLOWED_BY_POLICY",
    "REARM_BLOCKED_FAIL_CLOSED",
)

REARM_POLICY_TRANSITIONS: Tuple[Tuple[str, str, str], ...] = (
    ("FLAT_LOCKED", "cooldown_policy_check", "COOLDOWN_CHECK"),
    ("COOLDOWN_CHECK", "cooldown_complete_and_flat", "OPERATOR_REARM_PREFLIGHT"),
    ("OPERATOR_REARM_PREFLIGHT", "operator_rearm_controls_valid", "REARM_READY_DIAGNOSTIC"),
    ("REARM_READY_DIAGNOSTIC", "future_detection_patch_present", "CANDIDATE_DIAGNOSTIC_ALLOWED_BY_POLICY"),
    ("OPERATOR_REARM_PREFLIGHT", "controls_missing_or_unsafe", "REARM_BLOCKED_FAIL_CLOSED"),
)

BLOCKED_UNTIL_EXPLICIT_REARM_POLICY_IMPLEMENTATION_PATCH: Tuple[str, ...] = (
    "generic_rearm_policy_activation",
    "generic_candidate_detection_execution",
    "generic_route_execution",
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
    report_name: str = "lsr_v2_supervised_rearm_policy_draft_report.json"
    jsonl_name: str = "lsr_v2_supervised_rearm_policy_draft.jsonl"
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


def _build_rearm_policy_state_model() -> Dict[str, Any]:
    return {
        "states": list(REARM_POLICY_STATES),
        "initial_state": "FLAT_LOCKED",
        "terminal_state": "CANDIDATE_DIAGNOSTIC_ALLOWED_BY_POLICY",
        "fail_closed_state": "REARM_BLOCKED_FAIL_CLOSED",
        "transitions": [
            {"from": start, "on": event, "to": end, "execution_enabled": False, "mutation_enabled": False}
            for start, event, end in REARM_POLICY_TRANSITIONS
        ],
        "execution_enabled": False,
        "mutation_enabled": False,
        "candidate_detection_enabled": False,
        "route_execution_enabled": False,
        "broker_submit_enabled": False,
        "broker_close_enabled": False,
        "paper_state_mutation_enabled": False,
        "paper_status_mutation_enabled": False,
        "scheduler_enabled": False,
        "telegram_network_send_enabled": False,
    }


def _build_operator_gate_model() -> Dict[str, Any]:
    return {
        "enable_env_name": GENERIC_REARM_ENABLE_ENV,
        "confirmation_env_name": GENERIC_REARM_CONFIRMATION_ENV,
        "confirmation_phrase": GENERIC_REARM_CONFIRMATION_PHRASE,
        "max_positions_env_name": GENERIC_REARM_MAX_POSITIONS_ENV,
        "required_max_positions": 1,
        "operator_confirmation_required": True,
        "operator_enable_required": True,
        "max_positions_check_required": True,
        "execution_allowed": False,
        "activation_patch_required": True,
    }


def _build_cooldown_policy_model() -> Dict[str, Any]:
    return {
        "cooldown_after_close_required": True,
        "cooldown_complete_required_before_rearm": True,
        "flat_state_required": True,
        "pending_orders_required_zero": True,
        "open_positions_required_zero": True,
        "max_open_positions": 1,
        "single_position_policy": True,
        "paper_only": True,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "execution_allowed": False,
    }


def run_supervised_rearm_policy_draft(settings: Optional[Settings] = None) -> Dict[str, Any]:
    if settings is None:
        settings = Settings()

    data_dir = settings.data_path
    reports, present_reports, missing_reports, upstream_ready = _load_upstream_reports(settings)
    paper_state = _read_json(data_dir / "paper_state.json", {})
    paper_status = _read_json(data_dir / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(paper_state, paper_status)
    active_env = _active_lsr_v2_env()

    u3 = reports.get("generic_order_lifecycle", {})
    u2 = reports.get("generic_cycle_controller", {})
    u1 = reports.get("generic_refactor_preflight", {})
    t17 = reports.get("fourth_submit_execution", {})
    postmortem = reports.get("three_trade_postmortem", {})
    dashboard = reports.get("telegram_dashboard", {})

    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    fourth_trade_locked = _as_bool(t17.get("fourth_trade_locked", u3.get("fourth_trade_locked", u2.get("fourth_trade_locked", postmortem.get("fourth_trade_locked", True)))))
    stability_lock_active = _as_bool(t17.get("stability_lock_active", u3.get("stability_lock_active", u2.get("stability_lock_active", postmortem.get("stability_lock_active", True)))))
    generic_order_lifecycle_ready = upstream_ready.get("generic_order_lifecycle", False)
    generic_cycle_controller_ready = upstream_ready.get("generic_cycle_controller", False)
    ordinal_expansion_blocked = (
        u3.get("ordinal_trade_patch_expansion_allowed") is False
        and u3.get("fifth_trade_patch_allowed") is False
        and u3.get("sixth_trade_patch_allowed") is False
        and u3.get("seventh_trade_patch_allowed") is False
    )
    if not ordinal_expansion_blocked:
        ordinal_expansion_blocked = (
            u2.get("ordinal_trade_patch_expansion_allowed") is False
            and u2.get("fifth_trade_patch_allowed") is False
            and u2.get("sixth_trade_patch_allowed") is False
            and u2.get("seventh_trade_patch_allowed") is False
        )
    no_order_intent = not _as_bool(t17.get("paper_order_intent_ready", u3.get("paper_order_intent_ready", False)))
    no_route_candidate = not _as_bool(t17.get("route_candidate_available", u3.get("route_candidate_available", False)))
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

    enable_value = os.environ.get(GENERIC_REARM_ENABLE_ENV, "")
    confirmation_value = os.environ.get(GENERIC_REARM_CONFIRMATION_ENV, "")
    max_positions_value = os.environ.get(GENERIC_REARM_MAX_POSITIONS_ENV, "")
    operator_enable_requested = str(enable_value).strip() == "1"
    operator_confirmation_ok = str(confirmation_value).strip() == GENERIC_REARM_CONFIRMATION_PHRASE
    operator_max_positions_ok = str(max_positions_value).strip() == "1"
    operator_controls_valid_for_future_patch = operator_enable_requested and operator_confirmation_ok and operator_max_positions_ok

    required_readiness = {
        "generic_order_lifecycle_ready": generic_order_lifecycle_ready,
        "generic_cycle_controller_ready": generic_cycle_controller_ready,
        "generic_refactor_preflight_ready": upstream_ready.get("generic_refactor_preflight", False),
        "upstream_reports_ready": all(upstream_ready.values()),
        "flat_state_confirmed": flat_state_confirmed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": not active_env,
        "ordinal_expansion_blocked": ordinal_expansion_blocked,
        "no_order_intent_currently_available": no_order_intent,
        "no_fourth_route_candidate": no_route_candidate,
        "no_submit_occurred": no_submit_occurred,
        "no_close_occurred": no_close_occurred,
        "live_disabled": not live_enabled,
        "testnet_disabled": not testnet_enabled,
        "exchange_broker_disabled": not exchange_broker_enabled,
    }

    blockers: List[str] = []
    if missing_reports:
        blockers.append("missing_upstream_reports")
    if not all(upstream_ready.values()):
        blockers.append("upstream_reports_not_ready")
    if not generic_order_lifecycle_ready:
        blockers.append("generic_order_lifecycle_not_ready")
    if not generic_cycle_controller_ready:
        blockers.append("generic_cycle_controller_not_ready")
    if not flat_state_confirmed:
        blockers.append("paper_state_not_flat")
    if not fourth_trade_locked:
        blockers.append("fourth_trade_not_locked")
    if not stability_lock_active:
        blockers.append("stability_lock_not_active")
    if active_env:
        blockers.append("active_lsr_v2_operator_env_present")
    if not ordinal_expansion_blocked:
        blockers.append("ordinal_expansion_not_blocked")
    if live_enabled or testnet_enabled or exchange_broker_enabled:
        blockers.append("live_testnet_or_exchange_enabled")
    if not no_submit_occurred or not no_close_occurred:
        blockers.append("unexpected_submit_or_close_detected")

    ready = not blockers

    policy_contract = {
        "trade_ordinal": "N",
        "cycle_id_required": True,
        "paper_only": True,
        "max_open_positions": 1,
        "single_position_policy": True,
        "operator_rearm_confirmation_required": True,
        "operator_submit_confirmation_required": True,
        "operator_close_confirmation_required": True,
        "cooldown_after_close_required": True,
        "flat_state_required_before_rearm": True,
        "pending_orders_required_zero": True,
        "order_lifecycle_required": True,
        "ordinal_module_generation_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
    }

    result: Dict[str, Any] = {
        "prompt": PROMPT,
        "generated_at": _utc_now(),
        "event_type": EVENT_TYPE,
        "status": "PASS" if ready else "WARN",
        "decision": READY_DECISION if ready else KEEP_DIAGNOSTIC_DECISION,
        "classification_labels": [
            "GENERIC_LSR_V2_SUPERVISED_REARM_POLICY_DRAFT",
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
        ] + (["GENERIC_REARM_POLICY_DRAFT_READY"] if ready else []),
        "blockers": blockers,
        "blocked_until_explicit_rearm_policy_implementation_patch": list(BLOCKED_UNTIL_EXPLICIT_REARM_POLICY_IMPLEMENTATION_PATCH),
        "generic_supervised_rearm_policy_draft_ready": ready,
        "generic_supervised_rearm_policy_plan_ready": ready,
        "generic_rearm_policy_contract_ready": ready,
        "generic_rearm_policy_state_model_ready": ready,
        "generic_rearm_operator_gate_model_ready": ready,
        "generic_cooldown_policy_model_ready": ready,
        "generic_single_position_policy_ready": ready,
        "generic_order_lifecycle_ready": generic_order_lifecycle_ready,
        "generic_cycle_controller_ready": generic_cycle_controller_ready,
        "generic_refactor_preflight_ready": upstream_ready.get("generic_refactor_preflight", False),
        "generic_rearm_policy_contract": policy_contract,
        "generic_rearm_policy_state_model": _build_rearm_policy_state_model(),
        "generic_rearm_operator_gate_model": _build_operator_gate_model(),
        "generic_cooldown_policy_model": _build_cooldown_policy_model(),
        "generic_rearm_required_envs_present": bool(enable_value and confirmation_value and max_positions_value),
        "generic_rearm_enable_env_name": GENERIC_REARM_ENABLE_ENV,
        "generic_rearm_enable_env_value": enable_value,
        "generic_rearm_enable_requested": operator_enable_requested,
        "generic_rearm_confirmation_env_name": GENERIC_REARM_CONFIRMATION_ENV,
        "generic_rearm_confirmation_env_value_present": bool(confirmation_value),
        "generic_rearm_confirmation_phrase": GENERIC_REARM_CONFIRMATION_PHRASE,
        "generic_rearm_confirmation_ok": operator_confirmation_ok,
        "generic_rearm_max_positions_env_name": GENERIC_REARM_MAX_POSITIONS_ENV,
        "generic_rearm_max_positions_env_value": max_positions_value,
        "generic_rearm_max_positions": 1,
        "generic_rearm_max_positions_ok": operator_max_positions_ok,
        "generic_rearm_controls_valid_for_future_patch": operator_controls_valid_for_future_patch,
        "generic_rearm_policy_execution_allowed": False,
        "generic_rearm_allowed": False,
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_handoff_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_open_position_monitor_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_final_audit_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "generic_order_lifecycle_execution_allowed": False,
        "generic_order_intent_execution_allowed": False,
        "generic_paper_state_mutation_allowed": False,
        "generic_paper_status_mutation_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "paper_order_intent_ready": not no_order_intent,
        "paper_order_intent": t17.get("paper_order_intent", {}),
        "route_candidate_available": not no_route_candidate,
        "no_order_intent_currently_available": no_order_intent,
        "no_fourth_route_candidate": no_route_candidate,
        "lifecycle_state": t17.get("lifecycle_state", u3.get("lifecycle_state", "FLAT_LOCKED")),
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "flat_state_confirmed": flat_state_confirmed,
        "open_positions_after": open_positions_after,
        "pending_orders_after": pending_orders_after,
        "paper_status_open_positions_after": open_positions_after,
        "paper_status_pending_orders_after": pending_orders_after,
        "operator_env_absent": not active_env,
        "active_lsr_v2_operator_env_count": len(active_env),
        "active_lsr_v2_operator_env_keys": sorted(active_env.keys()),
        "orders_submitted_by_generic_rearm_policy_draft": 0,
        "positions_opened_by_generic_rearm_policy_draft": 0,
        "positions_closed_by_generic_rearm_policy_draft": 0,
        "broker_submit_called_by_generic_rearm_policy_draft": False,
        "broker_close_called_by_generic_rearm_policy_draft": False,
        "paper_state_modified_by_generic_rearm_policy_draft": False,
        "paper_status_modified_by_generic_rearm_policy_draft": False,
        "paper_state_status_consistency": True,
        "scheduler_enabled": False,
        "scheduler_started": False,
        "telegram_dashboard_ready": upstream_ready.get("telegram_dashboard", False),
        "telegram_payload_ready": _as_bool(dashboard.get("telegram_payload_ready", False)),
        "telegram_network_called": False,
        "telegram_send_allowed": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "required_readiness": required_readiness,
        "upstream_readiness": upstream_ready,
        "upstream_reports_present": present_reports,
        "missing_upstream_reports": missing_reports,
        "recommended_next_patch": "29.4.4u-5 — Generic LSR-v2 paper cycle integration preflight",
        "next_step": "prepare_generic_cycle_integration_preflight_or_wait_for_real_candidate",
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

    _write_json(data_dir / settings.report_name, result)
    _append_jsonl(data_dir / settings.jsonl_name, result)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    _ = argv
    result = run_supervised_rearm_policy_draft()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
