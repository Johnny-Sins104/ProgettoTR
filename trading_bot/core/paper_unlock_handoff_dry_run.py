"""Prompt 29.4.4r paper order submission dry-run / simulated broker handoff.

This module is an audit-only layer after the guarded paper-order candidate audit.
It prepares a paper-broker handoff diagnostic only when a candidate event is
already marked ``candidate_ready=true``. It never calls a broker, never submits
orders, never opens positions, and keeps live/testnet/exchange-broker execution
blocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

from config import Config
from core.calibrated_structure_shadow import _safe_float, _safe_int
from core.paper_unlock_guarded_enable import ENABLE_NAME, PROFILE_NAME
from core.paper_unlock_candidate_audit import EVENT_TYPE as CANDIDATE_EVENT_TYPE

PROMPT_ID = "29.4.4r"
EVENT_TYPE = "PAPER_ORDER_HANDOFF_DRY_RUN"
REPORT_NAME = "paper_unlock_handoff_dry_run_report.json"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"
READY_DECISION = "PAPER_ORDER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        p = Path(path)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_jsonl(path: str | Path, *, max_lines: int = 5000) -> list[dict[str, Any]]:
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
        if isinstance(item, dict):
            out.append(item)
    return out


def _counts(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value if value not in {None, ""} else "-")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


@dataclass(frozen=True)
class PaperOrderHandoffDryRunSettings:
    enabled: bool = True
    report_name: str = REPORT_NAME
    events_name: str = "paper_events.jsonl"
    status_name: str = "paper_status.json"
    candidate_event_type: str = CANDIDATE_EVENT_TYPE
    handoff_event_type: str = EVENT_TYPE
    profile_name: str = PROFILE_NAME
    enable_name: str = ENABLE_NAME
    max_event_lines: int = 5000
    emit_handoff_events: bool = True
    dry_run_only: bool = True
    paper_broker_adapter_name: str = "PaperBrokerAdapter"

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperOrderHandoffDryRunSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLED", True)),
            report_name=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            status_name=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_STATUS_NAME", "paper_status.json") or "paper_status.json"),
            candidate_event_type=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_CANDIDATE_EVENT_TYPE", CANDIDATE_EVENT_TYPE) or CANDIDATE_EVENT_TYPE),
            handoff_event_type=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_EVENT_TYPE", EVENT_TYPE) or EVENT_TYPE),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            enable_name=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLE_NAME", ENABLE_NAME) or ENABLE_NAME),
            max_event_lines=max(100, _safe_int(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_MAX_EVENT_LINES", 5000), 5000)),
            emit_handoff_events=bool(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_EMIT_EVENTS", True)),
            dry_run_only=bool(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_ONLY", True)),
            paper_broker_adapter_name=str(getattr(cfg, "PAPER_UNLOCK_HANDOFF_DRY_RUN_PAPER_BROKER_ADAPTER", "PaperBrokerAdapter") or "PaperBrokerAdapter"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "report_name": self.report_name,
            "events_name": self.events_name,
            "status_name": self.status_name,
            "candidate_event_type": self.candidate_event_type,
            "handoff_event_type": self.handoff_event_type,
            "profile_name": self.profile_name,
            "enable_name": self.enable_name,
            "max_event_lines": self.max_event_lines,
            "emit_handoff_events": self.emit_handoff_events,
            "dry_run_only": self.dry_run_only,
            "paper_broker_adapter_name": self.paper_broker_adapter_name,
        }


def build_paper_order_handoff_dry_run_event(
    *,
    settings: PaperOrderHandoffDryRunSettings | None = None,
    candidate_event: Mapping[str, Any] | None = None,
    open_positions_count: int | None = None,
) -> dict[str, Any]:
    """Build a simulated paper-broker handoff event without order submission."""
    settings = settings or PaperOrderHandoffDryRunSettings.from_config()
    candidate = candidate_event if isinstance(candidate_event, Mapping) else {}
    open_positions = _safe_int(candidate.get("open_positions_count") if open_positions_count is None else open_positions_count, 0)
    candidate_ready = _safe_bool(candidate.get("candidate_ready"))
    audit_only = _safe_bool(candidate.get("audit_only", True))
    paper_only_mode = _safe_bool(candidate.get("paper_only_mode", str(candidate.get("mode") or "paper").lower() == "paper"))
    paper_orders_enabled = _safe_bool(candidate.get("paper_orders_enabled"))
    experiment_allowed = _safe_bool(candidate.get("paper_unlock_experiment_allowed"))
    manual_activation_allowed = _safe_bool(candidate.get("manual_activation_allowed"))
    automatic_activation_allowed = _safe_bool(candidate.get("automatic_activation_allowed"))
    operational_unlock_allowed = _safe_bool(candidate.get("operational_unlock_allowed"))
    live_allowed = _safe_bool(candidate.get("live_allowed"))
    testnet_allowed = _safe_bool(candidate.get("testnet_allowed"))
    exchange_broker_allowed = _safe_bool(candidate.get("exchange_broker_allowed"))
    side = str(candidate.get("side") or "").upper()
    side_ok = side in {"BUY", "SELL"}
    entry_price = _safe_float(candidate.get("entry_price"), 0.0)
    position_size = _safe_float(candidate.get("position_size"), 0.0)
    risk_amount = _safe_float(candidate.get("risk_amount"), 0.0)
    notional = _safe_float(candidate.get("notional"), 0.0)

    safety_ok = bool(
        paper_only_mode
        and paper_orders_enabled
        and experiment_allowed
        and manual_activation_allowed
        and not automatic_activation_allowed
        and not operational_unlock_allowed
        and not live_allowed
        and not testnet_allowed
        and not exchange_broker_allowed
    )

    blocked_reasons: list[str] = []
    if not candidate_ready:
        blocked_reasons.append("candidate_ready_false")
    if not safety_ok:
        blocked_reasons.append("paper_safety_state_not_ready")
    if not audit_only:
        blocked_reasons.append("candidate_not_audit_only")
    if not side_ok:
        blocked_reasons.append("no_directional_side")
    if entry_price <= 0.0:
        blocked_reasons.append("entry_price_invalid")
    if position_size <= 0.0 or risk_amount <= 0.0 or notional <= 0.0:
        blocked_reasons.append("candidate_size_invalid")

    would_create_order = bool(not blocked_reasons)
    return {
        "event_type": settings.handoff_event_type,
        "prompt": PROMPT_ID,
        "cycle_id": str(candidate.get("cycle_id") or ""),
        "symbol": str(candidate.get("symbol") or ""),
        "candle_ts": str(candidate.get("candle_ts") or ""),
        "ts": utc_now_iso(),
        "profile_name": settings.profile_name,
        "enable_name": settings.enable_name,
        "source_candidate_event_type": candidate.get("event_type") or settings.candidate_event_type,
        "side": side,
        "mode": str(candidate.get("mode") or "paper"),
        "paper_only_mode": True,
        "routing_mode": str(candidate.get("routing_mode") or "paper_only"),
        "submission_mode": "handoff_dry_run_only",
        "dry_run_only": True,
        "candidate_ready": candidate_ready,
        "would_create_order": would_create_order,
        "would_submit_to_paper_broker": False,
        "broker_submit_called": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "exchange_broker_adapter": "blocked",
        "paper_orders_enabled": paper_orders_enabled,
        "paper_unlock_experiment_allowed": experiment_allowed,
        "manual_activation_allowed": manual_activation_allowed,
        "automatic_activation_allowed": automatic_activation_allowed,
        "operational_unlock_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "live_blocked": True,
        "testnet_blocked": True,
        "exchange_broker_blocked": True,
        "entry_price": entry_price,
        "stop_loss": _safe_float(candidate.get("stop_loss"), 0.0),
        "take_profit": _safe_float(candidate.get("take_profit"), 0.0),
        "risk_per_trade_pct": _safe_float(candidate.get("risk_per_trade_pct"), 0.0025),
        "risk_amount": risk_amount,
        "position_size": position_size,
        "notional": notional,
        "max_positions": _safe_int(candidate.get("max_positions"), 1),
        "open_positions_count": open_positions,
        "blocked_reason": None if would_create_order else (blocked_reasons[0] if blocked_reasons else "handoff_not_ready"),
        "blocked_reasons": blocked_reasons,
        "orders_submitted_by_handoff": 0,
        "positions_opened_by_handoff": 0,
    }


def build_paper_unlock_handoff_dry_run_report(base: str | Path = "data", settings: PaperOrderHandoffDryRunSettings | None = None) -> dict[str, Any]:
    settings = settings or PaperOrderHandoffDryRunSettings.from_config()
    base_path = Path(base)
    events = _read_jsonl(base_path / settings.events_name, max_lines=settings.max_event_lines)
    status_payload = _read_json(base_path / settings.status_name)
    cycle_events = [e for e in events if e.get("event_type") == CYCLE_COMPLETED_EVENT_TYPE]
    candidate_events = [e for e in events if e.get("event_type") == settings.candidate_event_type]
    handoff_events = [e for e in events if e.get("event_type") == settings.handoff_event_type]
    latest_cycle = cycle_events[-1] if cycle_events else {}
    latest_cycle_id = str(latest_cycle.get("cycle_id") or status_payload.get("active_cycle_id") or "")
    latest_candidates = [e for e in candidate_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]
    latest_handoffs = [e for e in handoff_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]
    ready_candidates = [e for e in latest_candidates if _safe_bool(e.get("candidate_ready"))]
    create_order_events = [e for e in latest_handoffs if _safe_bool(e.get("would_create_order"))]
    expected_handoff_events = len(ready_candidates)
    handoff_coverage_ok = bool(expected_handoff_events == 0 or len(latest_handoffs) >= expected_handoff_events)
    orders_by_handoff = sum(_safe_int(e.get("orders_submitted_by_handoff"), 0) for e in latest_handoffs)
    positions_by_handoff = sum(_safe_int(e.get("positions_opened_by_handoff"), 0) for e in latest_handoffs)
    cycle_orders = _safe_int(latest_cycle.get("orders"), 0)
    cycle_positions = _safe_int(latest_cycle.get("open_positions"), 0)
    cycle_errors = _safe_int(latest_cycle.get("errors"), 0)
    safety_checks = {
        "paper_mode_status": str(status_payload.get("mode") or "paper") == "paper",
        "operational_unlock_blocked": all(not _safe_bool(e.get("operational_unlock_allowed")) for e in latest_handoffs) if latest_handoffs else True,
        "live_blocked": all(not _safe_bool(e.get("live_allowed")) for e in latest_handoffs) if latest_handoffs else True,
        "testnet_blocked": all(not _safe_bool(e.get("testnet_allowed")) for e in latest_handoffs) if latest_handoffs else True,
        "exchange_broker_blocked": all(not _safe_bool(e.get("exchange_broker_allowed")) for e in latest_handoffs) if latest_handoffs else True,
        "broker_submit_not_called": all(not _safe_bool(e.get("broker_submit_called")) for e in latest_handoffs) if latest_handoffs else True,
        "handoff_did_not_submit_orders": orders_by_handoff == 0,
        "handoff_did_not_open_positions": positions_by_handoff == 0,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    status = "PASS" if latest_cycle and handoff_coverage_ok and safety_ok and cycle_errors == 0 else "WARN"
    decision_status = READY_DECISION if status == "PASS" else KEEP_DECISION
    blocked_reasons: list[Any] = []
    for e in latest_handoffs:
        reasons = e.get("blocked_reasons") if isinstance(e.get("blocked_reasons"), list) else [e.get("blocked_reason")]
        blocked_reasons.extend(r for r in reasons if r)

    decision = {
        "status": decision_status,
        "profile_name": settings.profile_name,
        "latest_cycle_id": latest_cycle_id,
        "candidate_order_audit_events": len(latest_candidates),
        "candidate_ready_count": expected_handoff_events,
        "handoff_dry_run_events": len(latest_handoffs),
        "handoff_coverage_ok": handoff_coverage_ok,
        "would_create_order_count": len(create_order_events),
        "orders_submitted_by_handoff": orders_by_handoff,
        "positions_opened_by_handoff": positions_by_handoff,
        "orders_submitted": cycle_orders,
        "positions_opened": cycle_positions,
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
        "cycle_summary": {
            "latest_cycle_id": latest_cycle_id,
            "scanned": _safe_int(latest_cycle.get("scanned"), 0),
            "signals": _safe_int(latest_cycle.get("signals"), 0),
            "orders": cycle_orders,
            "open_positions": cycle_positions,
            "errors": cycle_errors,
        },
        "handoff_dry_run": {
            "handoff_coverage_ok": handoff_coverage_ok,
            "candidate_order_audit_events": len(latest_candidates),
            "candidate_ready_count": expected_handoff_events,
            "handoff_dry_run_events": len(latest_handoffs),
            "would_create_order_count": len(create_order_events),
            "blocked_reason_counts": _counts(blocked_reasons),
            "side_counts": _counts(e.get("side") for e in latest_handoffs),
            "submission_mode_counts": _counts(e.get("submission_mode") for e in latest_handoffs),
        },
        "safety_checks": safety_checks,
        "sample_handoff_events_tail": latest_handoffs[-10:],
        "opens_orders": False,
        "orders_submitted": cycle_orders,
        "positions_opened": cycle_positions,
        "orders_submitted_by_handoff": orders_by_handoff,
        "positions_opened_by_handoff": positions_by_handoff,
        "paper_orders_enabled": any(_safe_bool(e.get("paper_orders_enabled")) for e in latest_candidates),
        "paper_unlock_experiment_allowed": any(_safe_bool(e.get("paper_unlock_experiment_allowed")) for e in latest_candidates),
        "manual_activation_allowed": any(_safe_bool(e.get("manual_activation_allowed")) for e in latest_candidates),
        "operational_unlock_allowed": False,
        "automatic_activation_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "next_patch": "29.4.4s first real paper-only order execution, supervised, only after dry-run handoff coverage is stable.",
    }


def write_paper_unlock_handoff_dry_run_report(base: str | Path = "data", settings: PaperOrderHandoffDryRunSettings | None = None) -> dict[str, Any]:
    settings = settings or PaperOrderHandoffDryRunSettings.from_config()
    report = build_paper_unlock_handoff_dry_run_report(base, settings)
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
