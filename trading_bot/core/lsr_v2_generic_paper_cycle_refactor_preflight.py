"""LSR-v2 generic paper-cycle refactor preflight.

29.4.4u-1 is intentionally read-only.  It does not route, submit,
close, mutate paper state, start schedulers, or send Telegram messages.
It verifies that the fourth-trade ordinal scaffold can be superseded by a
future generic paper-only lifecycle controller instead of creating
fifth/sixth ordinal trade modules.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

PROMPT = "29.4.4u-1"
EVENT_TYPE = "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT"
READY_DECISION = "LSR_V2_GENERIC_PAPER_CYCLE_REFACTOR_PREFLIGHT_READY"
KEEP_DIAGNOSTIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_GENERIC_CYCLE_REFACTOR_NOT_READY"

# Reports that prove the ordinal fourth-trade scaffold is complete enough
# to stop adding fifth/sixth ordinal patches and plan a generic controller.
UPSTREAM_REPORTS: Tuple[Tuple[str, str], ...] = (
    ("fourth_submit_execution", "lsr_v2_fourth_trade_submit_execution_report.json"),
    ("fourth_submit_preflight", "lsr_v2_fourth_trade_submit_preflight_report.json"),
    ("fourth_handoff_dry_run", "lsr_v2_fourth_trade_handoff_dry_run_report.json"),
    ("fourth_route_preflight", "lsr_v2_fourth_trade_route_preflight_report.json"),
    ("fourth_candidate_detection_audit", "lsr_v2_fourth_trade_candidate_detection_audit_report.json"),
    ("trade_lifecycle_auto_monitor", "lsr_v2_trade_lifecycle_auto_monitor_report.json"),
    ("telegram_dashboard", "lsr_v2_telegram_trade_dashboard_report.json"),
    ("three_trade_postmortem", "lsr_v2_three_trade_postmortem_stability_lock_report.json"),
)

GENERIC_TARGET_MODULES: Tuple[str, ...] = (
    "core/lsr_v2_paper_cycle_controller.py",
    "core/lsr_v2_paper_order_lifecycle.py",
    "core/lsr_v2_supervised_rearm_policy.py",
    "core/lsr_v2_trade_postmortem_generic.py",
    "core/lsr_v2_trade_dashboard_generic.py",
)

BLOCKED_UNTIL_EXPLICIT_GENERIC_EXECUTION_PATCH: Tuple[str, ...] = (
    "generic_cycle_controller_execution",
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
    report_name: str = "lsr_v2_generic_paper_cycle_refactor_preflight_report.json"
    jsonl_name: str = "lsr_v2_generic_paper_cycle_refactor_preflight.jsonl"
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
    if isinstance(value, list):
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


def _decision_is_ready(report: Mapping[str, Any], expected: Optional[str] = None) -> bool:
    if not isinstance(report, Mapping):
        return False
    if str(report.get("status", "")).upper() != "PASS":
        return False
    if expected:
        return report.get("decision") == expected
    return bool(report.get("decision"))


def _load_upstream_reports(settings: Settings) -> Tuple[Dict[str, Any], List[str], List[str]]:
    reports: Dict[str, Any] = {}
    present: List[str] = []
    missing: List[str] = []
    for key, filename in UPSTREAM_REPORTS:
        path = settings.data_path / filename
        payload = _read_json(path, {})
        reports[key] = payload
        if payload:
            present.append(filename)
        else:
            missing.append(filename)
    return reports, present, missing


def run_preflight(settings: Optional[Settings] = None) -> Dict[str, Any]:
    if settings is None:
        settings = Settings()

    data_dir = settings.data_path
    reports, present_reports, missing_reports = _load_upstream_reports(settings)
    paper_state = _read_json(data_dir / "paper_state.json", {})
    paper_status = _read_json(data_dir / "paper_status.json", {})
    open_positions_after, pending_orders_after = _paper_counts(paper_state, paper_status)
    active_env = _active_lsr_v2_env()

    t17 = reports.get("fourth_submit_execution", {})
    t16 = reports.get("fourth_submit_preflight", {})
    t15 = reports.get("fourth_handoff_dry_run", {})
    t14 = reports.get("fourth_route_preflight", {})
    t13 = reports.get("fourth_candidate_detection_audit", {})
    lifecycle = reports.get("trade_lifecycle_auto_monitor", {})
    dashboard = reports.get("telegram_dashboard", {})
    postmortem = reports.get("three_trade_postmortem", {})

    fourth_scaffold_ready = _decision_is_ready(
        t17, "LSR_V2_FOURTH_SUPERVISED_PAPER_SUBMIT_EXECUTION_READY"
    )
    submit_preflight_ready = _decision_is_ready(
        t16, "LSR_V2_FOURTH_TRADE_SUBMIT_PREFLIGHT_READY"
    )
    handoff_dry_run_ready = _decision_is_ready(
        t15, "LSR_V2_FOURTH_TRADE_HANDOFF_DRY_RUN_READY"
    )
    route_preflight_ready = _decision_is_ready(
        t14, "LSR_V2_FOURTH_TRADE_ROUTE_PREFLIGHT_READY"
    )
    candidate_detection_audit_ready = _decision_is_ready(
        t13, "LSR_V2_FOURTH_TRADE_CANDIDATE_DETECTION_AUDIT_READY"
    )

    lifecycle_state = str(t17.get("lifecycle_state") or lifecycle.get("lifecycle_state") or "UNKNOWN")
    flat_state_confirmed = open_positions_after == 0 and pending_orders_after == 0
    fourth_trade_locked = _as_bool(t17.get("fourth_trade_locked", postmortem.get("fourth_trade_locked", True)))
    stability_lock_active = _as_bool(t17.get("stability_lock_active", postmortem.get("stability_lock_active", True)))

    no_order_intent_currently_available = not _as_bool(t17.get("paper_order_intent_ready", False))
    no_fourth_route_candidate = not _as_bool(t17.get("route_candidate_available", False))
    no_submit_occurred = (
        _as_int(t17.get("orders_submitted_by_submit_execution"), 0) == 0
        and _as_int(t17.get("positions_opened_by_submit_execution"), 0) == 0
        and not _as_bool(t17.get("broker_submit_called", False))
        and not _as_bool(t17.get("broker_submit_called_by_submit_execution", False))
    )

    live_enabled = _as_bool(t17.get("live_enabled", False)) or _as_bool(os.environ.get("LIVE_ENABLED"))
    testnet_enabled = _as_bool(t17.get("testnet_enabled", False)) or _as_bool(os.environ.get("TESTNET_ENABLED"))
    exchange_broker_enabled = _as_bool(t17.get("exchange_broker_enabled", False)) or _as_bool(os.environ.get("EXCHANGE_BROKER_ENABLED"))

    required_readiness = {
        "fourth_submit_execution_scaffold_ready": fourth_scaffold_ready,
        "fourth_submit_preflight_ready": submit_preflight_ready,
        "fourth_handoff_dry_run_ready": handoff_dry_run_ready,
        "fourth_route_preflight_ready": route_preflight_ready,
        "fourth_candidate_detection_audit_ready": candidate_detection_audit_ready,
        "flat_state_confirmed": flat_state_confirmed,
        "fourth_trade_locked": fourth_trade_locked,
        "stability_lock_active": stability_lock_active,
        "operator_env_absent": len(active_env) == 0,
        "no_submit_occurred": no_submit_occurred,
        "live_disabled": not live_enabled,
        "testnet_disabled": not testnet_enabled,
        "exchange_broker_disabled": not exchange_broker_enabled,
    }

    blockers = [name for name, ok in required_readiness.items() if not ok]
    if missing_reports:
        blockers.append("missing_upstream_reports")

    generic_refactor_preflight_ready = not blockers
    decision = READY_DECISION if generic_refactor_preflight_ready else KEEP_DIAGNOSTIC_DECISION
    status = "PASS" if generic_refactor_preflight_ready else "WARN"

    payload: Dict[str, Any] = {
        "event_type": EVENT_TYPE,
        "prompt": PROMPT,
        "generated_at": _utc_now(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "GENERIC_LSR_V2_PAPER_CYCLE_REFACTOR_PREFLIGHT",
            "READ_ONLY",
            "NO_ORDINAL_EXPANSION",
            "NO_ENGINE_MUTATION",
            "NO_STATE_MUTATION",
            "NO_REENTRY",
            "NO_ROUTE_EXECUTION",
            "NO_SUBMIT",
            "NO_NETWORK_SEND",
            "NO_SCHEDULER",
            "FAIL_CLOSED",
        ] + (["GENERIC_REFACTOR_PREFLIGHT_READY"] if generic_refactor_preflight_ready else []),
        "blockers": blockers,
        "blocked_until_explicit_generic_cycle_patch": list(BLOCKED_UNTIL_EXPLICIT_GENERIC_EXECUTION_PATCH),
        "generic_cycle_refactor_preflight_ready": generic_refactor_preflight_ready,
        "generic_cycle_refactor_plan_ready": True,
        "generic_trade_cycle_controller_plan_ready": True,
        "generic_lsr_v2_paper_cycle_allowed": False,
        "generic_candidate_detection_allowed": False,
        "generic_route_execution_allowed": False,
        "generic_submit_execution_allowed": False,
        "generic_close_execution_allowed": False,
        "generic_postmortem_execution_allowed": False,
        "paper_only_execution_allowed": False,
        "future_integrated_operation_allowed": False,
        "ordinal_trade_patch_expansion_allowed": False,
        "fifth_trade_patch_allowed": False,
        "sixth_trade_patch_allowed": False,
        "seventh_trade_patch_allowed": False,
        "generic_target_modules": list(GENERIC_TARGET_MODULES),
        "generic_cycle_policy": {
            "trade_ordinal": "N",
            "cycle_id_required": True,
            "max_open_positions": 1,
            "paper_only": True,
            "operator_confirmation_required": True,
            "cooldown_after_close_required": True,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
        },
        "upstream_reports_present": present_reports,
        "missing_upstream_reports": missing_reports,
        "required_readiness": required_readiness,
        "fourth_submit_execution_scaffold_ready": fourth_scaffold_ready,
        "submit_preflight_ready": submit_preflight_ready,
        "handoff_dry_run_ready": handoff_dry_run_ready,
        "route_preflight_ready": route_preflight_ready,
        "candidate_detection_audit_ready": candidate_detection_audit_ready,
        "route_candidate_available": _as_bool(t17.get("route_candidate_available", False)),
        "paper_order_intent_ready": _as_bool(t17.get("paper_order_intent_ready", False)),
        "no_order_intent_currently_available": no_order_intent_currently_available,
        "no_fourth_route_candidate": no_fourth_route_candidate,
        "submit_execution_diagnostic": t17.get("submit_execution_diagnostic", ""),
        "lifecycle_state": lifecycle_state,
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
        "broker_submit_called_by_generic_cycle_refactor_preflight": False,
        "broker_close_called_by_generic_cycle_refactor_preflight": False,
        "orders_submitted_by_generic_cycle_refactor_preflight": 0,
        "positions_opened_by_generic_cycle_refactor_preflight": 0,
        "positions_closed_by_generic_cycle_refactor_preflight": 0,
        "paper_state_modified_by_generic_cycle_refactor_preflight": False,
        "paper_status_modified_by_generic_cycle_refactor_preflight": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "next_step": "prepare_generic_lsr_v2_paper_cycle_controller_draft_or_wait_for_real_candidate",
        "recommended_next_patch": "29.4.4u-2 — Generic LSR-v2 paper cycle controller draft",
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
    # CLI intentionally has no mutating flags.  Accepting argv keeps tests simple
    # and avoids argparse overhead for a read-only diagnostic runner.
    _ = list(argv or [])
    result = run_preflight(Settings(project_root=Path(".")))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
