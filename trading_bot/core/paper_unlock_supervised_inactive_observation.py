"""Prompt 29.4.4s-OBS supervised inactive observation / candidate exposure monitor.

This module wraps the existing paper unlock observation harness with a stricter
inactive-supervision contract. It is intended to observe candidate exposure after
29.4.4s is installed while operator execution remains disabled. It must not
submit orders, open positions, call an exchange broker, enable testnet/live, or
reactivate legacy paper execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from config import Config
from core.paper_unlock_observation import (
    PaperUnlockObservationSettings,
    build_paper_unlock_observation_report,
    run_paper_unlock_observation_loop,
)
from core.paper_unlock_supervised_execution import PaperUnlockSupervisedExecutionSettings

PROMPT_ID = "29.4.4s-OBS"
REPORT_NAME = "paper_unlock_supervised_inactive_observation_report.json"
LOG_DIR_NAME = "paper_unlock_supervised_inactive_observation_logs"
READY_DECISION = "PAPER_SUPERVISED_INACTIVE_OBSERVATION_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


@dataclass(frozen=True)
class PaperUnlockSupervisedInactiveObservationSettings:
    report_name: str = REPORT_NAME
    events_name: str = "paper_events.jsonl"
    max_event_lines: int = 100000
    duration_hours: float = 4.0
    interval_seconds: float = 300.0
    max_cycles: int = 0
    timeframe: str = "5m"
    cost_model: str = "conservative"
    balance: float = 1000.0
    poll_seconds: float = 60.0
    paper_unlock: bool = True
    log_dir_name: str = LOG_DIR_NAME
    run_command_timeout_seconds: float = 900.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockSupervisedInactiveObservationSettings":
        base = PaperUnlockObservationSettings.from_config(cfg)
        return cls(
            report_name=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_EVENTS_NAME", base.events_name) or base.events_name),
            max_event_lines=max(1000, _safe_int(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_MAX_EVENT_LINES", max(base.max_event_lines, 100000)), max(base.max_event_lines, 100000))),
            duration_hours=max(0.01, float(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_DURATION_HOURS", base.duration_hours) or base.duration_hours)),
            interval_seconds=max(1.0, float(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_INTERVAL_SECONDS", base.interval_seconds) or base.interval_seconds)),
            max_cycles=max(0, _safe_int(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_MAX_CYCLES", base.max_cycles), base.max_cycles)),
            timeframe=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_TIMEFRAME", base.timeframe) or base.timeframe),
            cost_model=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_COST_MODEL", base.cost_model) or base.cost_model),
            balance=float(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_BALANCE", base.balance) or base.balance),
            poll_seconds=max(1.0, float(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_POLL_SECONDS", base.poll_seconds) or base.poll_seconds)),
            paper_unlock=bool(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_PAPER_UNLOCK", base.paper_unlock)),
            log_dir_name=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_LOG_DIR", LOG_DIR_NAME) or LOG_DIR_NAME),
            run_command_timeout_seconds=max(30.0, float(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_INACTIVE_OBSERVATION_COMMAND_TIMEOUT_SECONDS", base.run_command_timeout_seconds) or base.run_command_timeout_seconds)),
        )

    def to_observation_settings(self) -> PaperUnlockObservationSettings:
        return PaperUnlockObservationSettings(
            report_name=self.report_name,
            events_name=self.events_name,
            max_event_lines=self.max_event_lines,
            duration_hours=self.duration_hours,
            interval_seconds=self.interval_seconds,
            max_cycles=self.max_cycles,
            timeframe=self.timeframe,
            cost_model=self.cost_model,
            balance=self.balance,
            poll_seconds=self.poll_seconds,
            paper_unlock=self.paper_unlock,
            log_dir_name=self.log_dir_name,
            run_command_timeout_seconds=self.run_command_timeout_seconds,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_name": self.report_name,
            "events_name": self.events_name,
            "max_event_lines": self.max_event_lines,
            "duration_hours": self.duration_hours,
            "interval_seconds": self.interval_seconds,
            "max_cycles": self.max_cycles,
            "timeframe": self.timeframe,
            "cost_model": self.cost_model,
            "balance": self.balance,
            "poll_seconds": self.poll_seconds,
            "paper_unlock": self.paper_unlock,
            "log_dir_name": self.log_dir_name,
            "run_command_timeout_seconds": self.run_command_timeout_seconds,
        }


def _decision_from_base(base_report: dict[str, Any]) -> dict[str, Any]:
    decision = base_report.get("decision", {})
    return decision if isinstance(decision, dict) else {}


def build_paper_unlock_supervised_inactive_observation_report(
    base: str | Path = "data",
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    settings: PaperUnlockSupervisedInactiveObservationSettings | None = None,
    run_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockSupervisedInactiveObservationSettings.from_config()
    supervised_settings = PaperUnlockSupervisedExecutionSettings.from_config()
    base_report = build_paper_unlock_observation_report(
        base,
        started_at=started_at,
        ended_at=ended_at,
        settings=settings.to_observation_settings(),
        run_log=run_log,
    )
    decision = _decision_from_base(base_report)
    supervised_section = base_report.get("supervised_execution", {}) if isinstance(base_report.get("supervised_execution"), dict) else {}

    completed_cycle_count = _safe_int(decision.get("completed_cycle_count"), 0)
    candidate_ready_count = _safe_int(decision.get("candidate_ready_count"), 0)
    would_create_order_count = _safe_int(decision.get("would_create_order_count"), 0)
    supervised_events = _safe_int(decision.get("supervised_execution_events"), 0)
    supervised_allowed = _safe_int(decision.get("supervised_submit_allowed_count"), 0)
    supervised_broker_submit = _safe_int(decision.get("supervised_broker_submit_called_count"), 0)
    all_broker_submit = _safe_int(decision.get("broker_submit_called_count"), 0)
    supervised_orders = _safe_int(decision.get("orders_submitted_by_supervised"), 0)
    supervised_positions = _safe_int(decision.get("positions_opened_by_supervised"), 0)
    cycle_orders = _safe_int(decision.get("orders_submitted"), 0)
    cycle_positions = _safe_int(decision.get("positions_opened"), 0)
    unauthorized_orders = _safe_int(decision.get("unauthorized_orders_count"), 0)
    unauthorized_positions = _safe_int(decision.get("unauthorized_positions_opened_count"), 0)

    base_safety = base_report.get("safety_checks", {}) if isinstance(base_report.get("safety_checks"), dict) else {}
    inactive_checks = {
        "base_observation_passed": base_report.get("status") == "PASS",
        "completed_cycle_count_positive": completed_cycle_count > 0,
        "operator_enable_inactive": not bool(supervised_settings.operator_enable),
        "operator_confirmation_not_ok": not bool(supervised_settings.confirmation_ok),
        "supervised_submit_allowed_zero": supervised_allowed == 0,
        "supervised_broker_submit_not_called": supervised_broker_submit == 0,
        "broker_submit_not_called": all_broker_submit == 0,
        "orders_submitted_by_supervised_zero": supervised_orders == 0,
        "positions_opened_by_supervised_zero": supervised_positions == 0,
        "cycle_orders_zero": cycle_orders == 0,
        "cycle_positions_zero": cycle_positions == 0,
        "legacy_order_leakage_not_detected": not _safe_bool(decision.get("legacy_order_leakage_detected")),
        "unauthorized_orders_zero": unauthorized_orders == 0,
        "unauthorized_positions_zero": unauthorized_positions == 0,
        "live_blocked": bool(base_safety.get("live_blocked", True)),
        "testnet_blocked": bool(base_safety.get("testnet_blocked", True)),
        "exchange_broker_blocked": bool(base_safety.get("exchange_broker_blocked", True)),
    }
    inactive_ready = all(bool(v) for v in inactive_checks.values())
    status = "PASS" if inactive_ready else "WARN"
    decision_status = READY_DECISION if status == "PASS" else KEEP_DECISION

    out_decision = dict(decision)
    out_decision.update(
        {
            "status": decision_status,
            "supervised_inactive_ready": inactive_ready,
            "operator_enable": bool(supervised_settings.operator_enable),
            "operator_confirmation_ok": bool(supervised_settings.confirmation_ok),
            "candidate_exposure_count": candidate_ready_count,
            "would_create_order_count": would_create_order_count,
            "supervised_execution_events": supervised_events,
            "supervised_submit_allowed_count": supervised_allowed,
            "supervised_broker_submit_called_count": supervised_broker_submit,
            "broker_submit_called_count": all_broker_submit,
            "orders_submitted_by_supervised": supervised_orders,
            "positions_opened_by_supervised": supervised_positions,
            "orders_submitted": cycle_orders,
            "positions_opened": cycle_positions,
        }
    )

    return {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": out_decision,
        "settings": settings.to_dict(),
        "supervised_execution_settings": supervised_settings.to_dict(),
        "window": base_report.get("window", {}),
        "cycle_summary": base_report.get("cycle_summary", {}),
        "candidate_exposure_monitor": {
            "candidate_ready_count": candidate_ready_count,
            "would_create_order_count": would_create_order_count,
            "handoff_dry_run_events": _safe_int(decision.get("handoff_dry_run_events"), 0),
            "supervised_execution_events": supervised_events,
            "supervised_blocked_reason_counts": supervised_section.get("blocked_reason_counts", {}),
            "sample_supervised_events_tail": base_report.get("sample_supervised_events_tail", []),
        },
        "inactive_safety_checks": inactive_checks,
        "base_observation_decision": decision,
        "runtime_audit": base_report.get("runtime_audit", {}),
        "routing_bridge": base_report.get("routing_bridge", {}),
        "candidate_order_audit": base_report.get("candidate_order_audit", {}),
        "handoff_dry_run": base_report.get("handoff_dry_run", {}),
        "supervised_execution": supervised_section,
        "paper_order_leakage_guard": base_report.get("paper_order_leakage_guard", {}),
        "run_log": base_report.get("run_log", run_log or []),
        "orders_submitted": cycle_orders,
        "positions_opened": cycle_positions,
        "orders_submitted_by_supervised": supervised_orders,
        "positions_opened_by_supervised": supervised_positions,
        "operational_unlock_allowed": False,
        "automatic_activation_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "generated_at": utc_now_iso(),
        "next_patch": "Wait for candidate_ready/would_create_order exposure, then review manually before enabling supervised paper execution; lifecycle audit remains 29.4.4t after a real supervised paper order.",
    }


def write_paper_unlock_supervised_inactive_observation_report(
    base: str | Path = "data",
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    settings: PaperUnlockSupervisedInactiveObservationSettings | None = None,
    run_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockSupervisedInactiveObservationSettings.from_config()
    report = build_paper_unlock_supervised_inactive_observation_report(
        base,
        started_at=started_at,
        ended_at=ended_at,
        settings=settings,
        run_log=run_log,
    )
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def run_paper_unlock_supervised_inactive_observation_loop(
    root: str | Path = ".",
    *,
    settings: PaperUnlockSupervisedInactiveObservationSettings | None = None,
    duration_hours: float | None = None,
    interval_seconds: float | None = None,
    max_cycles: int | None = None,
    symbols: str = "",
) -> dict[str, Any]:
    settings = settings or PaperUnlockSupervisedInactiveObservationSettings.from_config()
    obs_report = run_paper_unlock_observation_loop(
        root,
        settings=settings.to_observation_settings(),
        duration_hours=settings.duration_hours if duration_hours is None else duration_hours,
        interval_seconds=settings.interval_seconds if interval_seconds is None else interval_seconds,
        max_cycles=settings.max_cycles if max_cycles is None else max_cycles,
        symbols=symbols,
    )
    window = obs_report.get("window", {}) if isinstance(obs_report.get("window"), dict) else {}
    started_at_raw = window.get("started_at")
    ended_at_raw = window.get("ended_at")

    def _parse(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return None

    run_log = obs_report.get("run_log", []) if isinstance(obs_report.get("run_log"), list) else []
    return write_paper_unlock_supervised_inactive_observation_report(
        Path(root) / "data",
        started_at=_parse(started_at_raw),
        ended_at=_parse(ended_at_raw),
        settings=settings,
        run_log=run_log,
    )
