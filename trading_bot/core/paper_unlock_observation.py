"""Prompt 29.4.4r-OBS audit/dry-run observation run.

This module supports a bounded multi-cycle observation run after the first guarded
paper-order candidate audit. It is deliberately audit-only: it never submits
orders, never opens positions, never enables live/testnet/exchange broker, and
never changes signal, gate, routing, or risk logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json
import os
import subprocess
import sys
import time

from config import Config
from core.paper_order_leakage_guard import (
    PaperOrderLeakageGuardSettings,
    summarize_order_leakage_events,
)

PROMPT_ID = "29.4.4r-OBS"
REPORT_NAME = "paper_unlock_4h_observation_report.json"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"
RUNTIME_AUDIT_EVENT_TYPE = "GUARDED_PAPER_RUNTIME_AUDIT"
ROUTING_BRIDGE_EVENT_TYPE = "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT"
CANDIDATE_AUDIT_EVENT_TYPE = "GUARDED_PAPER_ORDER_CANDIDATE_AUDIT"
HANDOFF_DRY_RUN_EVENT_TYPE = "PAPER_ORDER_HANDOFF_DRY_RUN"
SUPERVISED_EXECUTION_EVENT_TYPE = "PAPER_SUPERVISED_ORDER_EXECUTION"
READY_DECISION = "PAPER_UNLOCK_DRY_RUN_OBSERVATION_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        p = Path(path)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _iter_jsonl_events(path: str | Path, *, max_lines: int = 50000) -> Iterable[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    if max_lines > 0 and len(lines) > max_lines:
        lines = lines[-max_lines:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("event_type"):
            out.append(item)
    return out


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


def _counts(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value if value not in {None, ""} else "-")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _extend_reasons(target: list[str], value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            if item not in {None, ""}:
                target.append(str(item))
    elif value not in {None, ""}:
        target.append(str(value))


def _event_in_window(event: Mapping[str, Any], *, started_at: datetime | None, ended_at: datetime | None) -> bool:
    ts = _parse_ts(event.get("ts"))
    if started_at is not None and ts is not None and ts < started_at.astimezone(timezone.utc):
        return False
    if ended_at is not None and ts is not None and ts > ended_at.astimezone(timezone.utc):
        return False
    return True


@dataclass(frozen=True)
class PaperUnlockObservationSettings:
    report_name: str = REPORT_NAME
    events_name: str = "paper_events.jsonl"
    max_event_lines: int = 50000
    duration_hours: float = 4.0
    interval_seconds: float = 300.0
    max_cycles: int = 0
    timeframe: str = "5m"
    cost_model: str = "conservative"
    balance: float = 1000.0
    poll_seconds: float = 60.0
    paper_unlock: bool = True
    log_dir_name: str = "paper_unlock_observation_logs"
    run_command_timeout_seconds: float = 900.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockObservationSettings":
        return cls(
            report_name=str(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            max_event_lines=max(1000, _safe_int(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_MAX_EVENT_LINES", 50000), 50000)),
            duration_hours=max(0.01, _safe_float(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_DURATION_HOURS", 4.0), 4.0)),
            interval_seconds=max(1.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_INTERVAL_SECONDS", 300.0), 300.0)),
            max_cycles=max(0, _safe_int(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_MAX_CYCLES", 0), 0)),
            timeframe=str(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_TIMEFRAME", "5m") or "5m"),
            cost_model=str(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_COST_MODEL", "conservative") or "conservative"),
            balance=_safe_float(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_BALANCE", 1000.0), 1000.0),
            poll_seconds=max(1.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_POLL_SECONDS", 60.0), 60.0)),
            paper_unlock=bool(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_PAPER_UNLOCK", True)),
            log_dir_name=str(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_LOG_DIR", "paper_unlock_observation_logs") or "paper_unlock_observation_logs"),
            run_command_timeout_seconds=max(30.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_OBSERVATION_COMMAND_TIMEOUT_SECONDS", 900.0), 900.0)),
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


def filter_events_for_window(
    events: Sequence[Mapping[str, Any]],
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> list[dict[str, Any]]:
    return [dict(e) for e in events if _event_in_window(e, started_at=started_at, ended_at=ended_at)]


def build_paper_unlock_observation_report(
    base: str | Path = "data",
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    settings: PaperUnlockObservationSettings | None = None,
    run_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockObservationSettings.from_config()
    base_path = Path(base)
    events = list(_iter_jsonl_events(base_path / settings.events_name, max_lines=settings.max_event_lines))
    events = filter_events_for_window(events, started_at=started_at, ended_at=ended_at)

    cycles = [e for e in events if e.get("event_type") == CYCLE_COMPLETED_EVENT_TYPE]
    runtime_events = [e for e in events if e.get("event_type") == RUNTIME_AUDIT_EVENT_TYPE]
    bridge_events = [e for e in events if e.get("event_type") == ROUTING_BRIDGE_EVENT_TYPE]
    candidate_events = [e for e in events if e.get("event_type") == CANDIDATE_AUDIT_EVENT_TYPE]
    handoff_events = [e for e in events if e.get("event_type") == HANDOFF_DRY_RUN_EVENT_TYPE]
    supervised_events = [e for e in events if e.get("event_type") == SUPERVISED_EXECUTION_EVENT_TYPE]
    leakage_guard_summary = summarize_order_leakage_events(
        events,
        settings=PaperOrderLeakageGuardSettings.from_config(),
    )
    legacy_order_leakage_detected = bool(leakage_guard_summary.get("legacy_order_leakage_detected"))
    unauthorized_orders_count = _safe_int(leakage_guard_summary.get("unauthorized_orders_count"), 0)
    unauthorized_positions_count = _safe_int(leakage_guard_summary.get("unauthorized_positions_opened_count"), 0)
    blocked_legacy_order_attempts = _safe_int(leakage_guard_summary.get("blocked_legacy_order_attempts"), 0)

    cycle_ids = [str(e.get("cycle_id") or "") for e in cycles if e.get("cycle_id")]
    latest_cycle_id = cycle_ids[-1] if cycle_ids else ""
    unique_cycle_ids = sorted(set(cycle_ids))
    completed_cycle_count = len(cycles)

    runtime_accepts = sum(1 for e in runtime_events if _safe_bool(e.get("accepted_diagnostic")))
    runtime_rejects = len(runtime_events) - runtime_accepts
    would_route_count = sum(1 for e in bridge_events if _safe_bool(e.get("would_route")))
    would_submit_count = sum(1 for e in bridge_events if _safe_bool(e.get("would_submit")))
    candidate_ready_count = sum(1 for e in candidate_events if _safe_bool(e.get("candidate_ready")))
    candidate_rejected_count = sum(1 for e in candidate_events if not _safe_bool(e.get("candidate_ready")))
    handoff_dry_run_count = len(handoff_events)
    would_create_order_count = sum(1 for e in handoff_events if _safe_bool(e.get("would_create_order")))
    handoff_broker_submit_called_count = sum(1 for e in handoff_events if _safe_bool(e.get("broker_submit_called")))
    supervised_execution_count = len(supervised_events)
    supervised_submit_allowed_count = sum(1 for e in supervised_events if _safe_bool(e.get("supervised_submit_allowed")))
    supervised_broker_submit_called_count = sum(1 for e in supervised_events if _safe_bool(e.get("broker_submit_called")))

    runtime_reasons: list[str] = []
    bridge_reasons: list[str] = []
    candidate_reasons: list[str] = []
    handoff_reasons: list[str] = []
    supervised_reasons: list[str] = []
    for e in runtime_events:
        _extend_reasons(runtime_reasons, e.get("reject_reasons") if "reject_reasons" in e else e.get("reject_reason"))
        _extend_reasons(runtime_reasons, e.get("blocked_reasons") if "blocked_reasons" in e else None)
    for e in bridge_events:
        _extend_reasons(bridge_reasons, e.get("blocked_reasons"))
        _extend_reasons(bridge_reasons, e.get("blocked_reason"))
    for e in candidate_events:
        _extend_reasons(candidate_reasons, e.get("blocked_reasons"))
        _extend_reasons(candidate_reasons, e.get("blocked_reason"))
    for e in handoff_events:
        _extend_reasons(handoff_reasons, e.get("blocked_reasons"))
        _extend_reasons(handoff_reasons, e.get("blocked_reason"))
    for e in supervised_events:
        _extend_reasons(supervised_reasons, e.get("blocked_reasons"))
        _extend_reasons(supervised_reasons, e.get("blocked_reason"))

    orders_submitted = sum(_safe_int(e.get("orders"), 0) for e in cycles)
    max_open_positions = max([_safe_int(e.get("open_positions"), 0) for e in cycles] or [0])
    cycle_errors = sum(_safe_int(e.get("errors"), 0) for e in cycles)
    orders_by_bridge = sum(_safe_int(e.get("orders_submitted_by_bridge"), 0) for e in bridge_events)
    positions_by_bridge = sum(_safe_int(e.get("positions_opened_by_bridge"), 0) for e in bridge_events)
    orders_by_candidate = sum(_safe_int(e.get("orders_submitted_by_candidate_audit"), 0) for e in candidate_events)
    positions_by_candidate = sum(_safe_int(e.get("positions_opened_by_candidate_audit"), 0) for e in candidate_events)
    orders_by_handoff = sum(_safe_int(e.get("orders_submitted_by_handoff"), 0) for e in handoff_events)
    positions_by_handoff = sum(_safe_int(e.get("positions_opened_by_handoff"), 0) for e in handoff_events)
    orders_by_supervised = sum(_safe_int(e.get("orders_submitted_by_supervised"), 0) for e in supervised_events)
    positions_by_supervised = sum(_safe_int(e.get("positions_opened_by_supervised"), 0) for e in supervised_events)
    broker_submit_called_count = handoff_broker_submit_called_count + supervised_broker_submit_called_count

    safety_checks = {
        "operational_unlock_blocked": all(not _safe_bool(e.get("operational_unlock_allowed")) for e in bridge_events + candidate_events + handoff_events + supervised_events) if (bridge_events or candidate_events or handoff_events or supervised_events) else True,
        "live_blocked": all(not _safe_bool(e.get("live_allowed")) for e in bridge_events + candidate_events + handoff_events + supervised_events) if (bridge_events or candidate_events or handoff_events or supervised_events) else True,
        "testnet_blocked": all(not _safe_bool(e.get("testnet_allowed")) for e in bridge_events + candidate_events + handoff_events + supervised_events) if (bridge_events or candidate_events or handoff_events or supervised_events) else True,
        "exchange_broker_blocked": all(not _safe_bool(e.get("exchange_broker_allowed")) for e in bridge_events + candidate_events + handoff_events + supervised_events) if (bridge_events or candidate_events or handoff_events or supervised_events) else True,
        "bridge_did_not_submit_orders": orders_by_bridge == 0,
        "bridge_did_not_open_positions": positions_by_bridge == 0,
        "candidate_audit_did_not_submit_orders": orders_by_candidate == 0,
        "candidate_audit_did_not_open_positions": positions_by_candidate == 0,
        "handoff_dry_run_did_not_submit_orders": orders_by_handoff == 0,
        "handoff_dry_run_did_not_open_positions": positions_by_handoff == 0,
        "handoff_broker_submit_not_called": handoff_broker_submit_called_count == 0,
        "handoff_dry_run_broker_submit_not_called": handoff_broker_submit_called_count == 0,
        "supervised_orders_match_cycle_orders": orders_by_supervised == orders_submitted,
        "supervised_positions_match_cycle_positions": positions_by_supervised == max_open_positions,
        "cycle_orders_zero_or_supervised": orders_submitted == 0 or orders_submitted == orders_by_supervised,
        "cycle_open_positions_zero_or_supervised": max_open_positions == 0 or max_open_positions == positions_by_supervised,
        "legacy_order_leakage_not_detected": not legacy_order_leakage_detected,
        "unauthorized_paper_orders_zero": unauthorized_orders_count == 0,
        "unauthorized_positions_opened_zero": unauthorized_positions_count == 0,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    handoff_coverage_ok = bool(candidate_ready_count == 0 or handoff_dry_run_count >= candidate_ready_count)
    observation_ready = bool(completed_cycle_count > 0 and len(runtime_events) >= completed_cycle_count and len(bridge_events) >= completed_cycle_count and handoff_coverage_ok and safety_ok and cycle_errors == 0)
    status = "PASS" if observation_ready else "WARN"

    if started_at and ended_at:
        elapsed_seconds = max(0.0, (ended_at.astimezone(timezone.utc) - started_at.astimezone(timezone.utc)).total_seconds())
    elif cycles:
        first_ts = _parse_ts(cycles[0].get("ts"))
        last_ts = _parse_ts(cycles[-1].get("ts"))
        elapsed_seconds = max(0.0, ((last_ts or utc_now()) - (first_ts or utc_now())).total_seconds())
    else:
        elapsed_seconds = 0.0

    decision = {
        "status": READY_DECISION if status == "PASS" else KEEP_DECISION,
        "latest_cycle_id": latest_cycle_id,
        "completed_cycle_count": completed_cycle_count,
        "runtime_audit_events": len(runtime_events),
        "runtime_accepts_diagnostic": runtime_accepts,
        "runtime_rejects": runtime_rejects,
        "routing_bridge_events": len(bridge_events),
        "would_route_count": would_route_count,
        "would_submit_count": would_submit_count,
        "candidate_order_audit_events": len(candidate_events),
        "candidate_ready_count": candidate_ready_count,
        "candidate_rejected_count": candidate_rejected_count,
        "handoff_dry_run_events": handoff_dry_run_count,
        "would_create_order_count": would_create_order_count,
        "supervised_execution_events": supervised_execution_count,
        "supervised_submit_allowed_count": supervised_submit_allowed_count,
        "broker_submit_called_count": broker_submit_called_count,
        "handoff_broker_submit_called_count": handoff_broker_submit_called_count,
        "supervised_broker_submit_called_count": supervised_broker_submit_called_count,
        "legacy_order_leakage_detected": legacy_order_leakage_detected,
        "unauthorized_orders_count": unauthorized_orders_count,
        "unauthorized_positions_opened_count": unauthorized_positions_count,
        "blocked_legacy_order_attempts": blocked_legacy_order_attempts,
        "handoff_coverage_ok": handoff_coverage_ok,
        "orders_submitted": orders_submitted,
        "positions_opened": max_open_positions,
        "orders_submitted_by_bridge": orders_by_bridge,
        "positions_opened_by_bridge": positions_by_bridge,
        "orders_submitted_by_candidate_audit": orders_by_candidate,
        "positions_opened_by_candidate_audit": positions_by_candidate,
        "orders_submitted_by_handoff": orders_by_handoff,
        "positions_opened_by_handoff": positions_by_handoff,
        "orders_submitted_by_supervised": orders_by_supervised,
        "positions_opened_by_supervised": positions_by_supervised,
        "operational_unlock_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
    }

    return {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": decision,
        "settings": settings.to_dict(),
        "window": {
            "started_at": started_at.isoformat() if started_at else None,
            "ended_at": ended_at.isoformat() if ended_at else None,
            "elapsed_seconds": round(elapsed_seconds, 4),
            "elapsed_hours": round(elapsed_seconds / 3600.0, 6),
        },
        "cycle_summary": {
            "completed_cycle_count": completed_cycle_count,
            "unique_cycle_count": len(unique_cycle_ids),
            "latest_cycle_id": latest_cycle_id,
            "cycle_ids_tail": cycle_ids[-20:],
            "scanned_total": sum(_safe_int(e.get("scanned"), 0) for e in cycles),
            "signals_total": sum(_safe_int(e.get("signals"), 0) for e in cycles),
            "orders_total": orders_submitted,
            "errors_total": cycle_errors,
            "max_open_positions": max_open_positions,
            "avg_elapsed_seconds": round(sum(_safe_float(e.get("elapsed_seconds"), 0.0) for e in cycles) / completed_cycle_count, 4) if completed_cycle_count else 0.0,
        },
        "runtime_audit": {
            "runtime_audit_events": len(runtime_events),
            "runtime_accepts_diagnostic": runtime_accepts,
            "runtime_rejects": runtime_rejects,
            "map_score_counts": _counts(e.get("map_score") for e in runtime_events),
            "structure_state_counts": _counts(e.get("runtime_structure_state") or e.get("structure_state") for e in runtime_events),
            "side_counts": _counts(e.get("side") for e in runtime_events),
            "reject_reason_counts": _counts(runtime_reasons),
        },
        "routing_bridge": {
            "routing_bridge_events": len(bridge_events),
            "would_route_count": would_route_count,
            "would_submit_count": would_submit_count,
            "blocked_reason_counts": _counts(bridge_reasons),
            "side_counts": _counts(e.get("side") for e in bridge_events),
            "structure_state_counts": _counts(e.get("runtime_structure_state") for e in bridge_events),
            "map_score_counts": _counts(e.get("map_score") for e in bridge_events),
        },
        "candidate_order_audit": {
            "candidate_order_audit_events": len(candidate_events),
            "candidate_ready_count": candidate_ready_count,
            "candidate_rejected_count": candidate_rejected_count,
            "blocked_reason_counts": _counts(candidate_reasons),
            "side_counts": _counts(e.get("side") for e in candidate_events),
            "submission_mode_counts": _counts(e.get("submission_mode") for e in candidate_events),
        },
        "handoff_dry_run": {
            "handoff_dry_run_events": handoff_dry_run_count,
            "would_create_order_count": would_create_order_count,
            "broker_submit_called_count": handoff_broker_submit_called_count,
            "handoff_coverage_ok": handoff_coverage_ok,
            "blocked_reason_counts": _counts(handoff_reasons),
            "side_counts": _counts(e.get("side") for e in handoff_events),
            "submission_mode_counts": _counts(e.get("submission_mode") for e in handoff_events),
            "paper_broker_adapter_counts": _counts(e.get("paper_broker_adapter") for e in handoff_events),
        },
        "supervised_execution": {
            "supervised_execution_events": supervised_execution_count,
            "supervised_submit_allowed_count": supervised_submit_allowed_count,
            "broker_submit_called_count": supervised_broker_submit_called_count,
            "orders_submitted_by_supervised": orders_by_supervised,
            "positions_opened_by_supervised": positions_by_supervised,
            "blocked_reason_counts": _counts(supervised_reasons),
            "side_counts": _counts(e.get("side") for e in supervised_events),
            "submission_mode_counts": _counts(e.get("submission_mode") for e in supervised_events),
            "paper_broker_adapter_counts": _counts(e.get("paper_broker_adapter") for e in supervised_events),
        },
        "paper_order_leakage_guard": leakage_guard_summary,
        "safety_checks": safety_checks,
        "run_log": run_log or [],
        "sample_bridge_events_tail": bridge_events[-10:],
        "sample_candidate_events_tail": candidate_events[-10:],
        "sample_handoff_events_tail": handoff_events[-10:],
        "sample_supervised_events_tail": supervised_events[-10:],
        "orders_submitted": orders_submitted,
        "positions_opened": max_open_positions,
        "orders_submitted_by_bridge": orders_by_bridge,
        "positions_opened_by_bridge": positions_by_bridge,
        "orders_submitted_by_candidate_audit": orders_by_candidate,
        "positions_opened_by_candidate_audit": positions_by_candidate,
        "orders_submitted_by_handoff": orders_by_handoff,
        "positions_opened_by_handoff": positions_by_handoff,
        "orders_submitted_by_supervised": orders_by_supervised,
        "positions_opened_by_supervised": positions_by_supervised,
        "operational_unlock_allowed": False,
        "automatic_activation_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "next_patch": "29.4.4t position lifecycle monitoring / supervised paper lifecycle audit after controlled 29.4.4s validation.",
    }


def write_paper_unlock_observation_report(
    base: str | Path = "data",
    *,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
    settings: PaperUnlockObservationSettings | None = None,
    run_log: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockObservationSettings.from_config()
    report = build_paper_unlock_observation_report(base, started_at=started_at, ended_at=ended_at, settings=settings, run_log=run_log)
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _paper_once_command(settings: PaperUnlockObservationSettings, symbols: str = "") -> list[str]:
    cmd = [
        sys.executable,
        "trading_bot/run_paper_trading.py",
        "--mode",
        "paper",
        "--timeframe",
        settings.timeframe,
        "--cost-model",
        settings.cost_model,
        "--balance",
        str(settings.balance),
        "--poll-seconds",
        str(settings.poll_seconds),
        "--once",
    ]
    if settings.paper_unlock:
        cmd.append("--paper-unlock")
    else:
        cmd.append("--no-paper-unlock")
    if symbols.strip():
        cmd.extend(["--symbols", symbols.strip()])
    return cmd


def run_paper_unlock_observation_loop(
    project_root: str | Path = ".",
    *,
    settings: PaperUnlockObservationSettings | None = None,
    duration_hours: float | None = None,
    interval_seconds: float | None = None,
    max_cycles: int | None = None,
    symbols: str = "",
    report_every_cycle: bool = True,
) -> dict[str, Any]:
    settings = settings or PaperUnlockObservationSettings.from_config()
    duration_hours = settings.duration_hours if duration_hours is None else max(0.01, float(duration_hours))
    interval_seconds = settings.interval_seconds if interval_seconds is None else max(1.0, float(interval_seconds))
    max_cycles = settings.max_cycles if max_cycles is None else max(0, int(max_cycles))

    root = Path(project_root)
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir = data_dir / settings.log_dir_name
    log_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    deadline = time.monotonic() + duration_hours * 3600.0
    run_log: list[dict[str, Any]] = []
    cycle_index = 0

    while time.monotonic() < deadline:
        if max_cycles and cycle_index >= max_cycles:
            break
        cycle_index += 1
        cycle_started_at = utc_now()
        log_path = log_dir / f"obs_cycle_{cycle_index:04d}_{cycle_started_at.strftime('%Y%m%dT%H%M%SZ')}.txt"
        cmd = _paper_once_command(settings, symbols=symbols)
        print(f"[OBS CYCLE START] index={cycle_index} command={' '.join(cmd)}", flush=True)
        returncode = -1
        timed_out = False
        try:
            with log_path.open("w", encoding="utf-8") as stream:
                completed = subprocess.run(
                    cmd,
                    cwd=str(root),
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=settings.run_command_timeout_seconds,
                    check=False,
                    env=os.environ.copy(),
                )
            returncode = int(completed.returncode)
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = 124
        cycle_ended_at = utc_now()
        entry = {
            "cycle_index": cycle_index,
            "started_at": cycle_started_at.isoformat(),
            "ended_at": cycle_ended_at.isoformat(),
            "elapsed_seconds": round((cycle_ended_at - cycle_started_at).total_seconds(), 4),
            "returncode": returncode,
            "timed_out": timed_out,
            "log_path": str(log_path),
        }
        run_log.append(entry)
        print(
            f"[OBS CYCLE DONE] index={cycle_index} returncode={returncode} timed_out={timed_out} "
            f"elapsed_seconds={entry['elapsed_seconds']:.4f} log={log_path}",
            flush=True,
        )
        if report_every_cycle:
            write_paper_unlock_observation_report(data_dir, started_at=started_at, ended_at=utc_now(), settings=settings, run_log=run_log)
        if returncode not in {0, 130}:
            print(f"[OBS CYCLE WARN] index={cycle_index} nonzero_returncode={returncode}", flush=True)
        if max_cycles and cycle_index >= max_cycles:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sleep_for = min(interval_seconds, remaining)
        print(f"[OBS SLEEP] seconds={sleep_for:.2f}", flush=True)
        time.sleep(sleep_for)

    return write_paper_unlock_observation_report(data_dir, started_at=started_at, ended_at=utc_now(), settings=settings, run_log=run_log)
