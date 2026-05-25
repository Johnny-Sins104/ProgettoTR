"""Prompt 29.4.4q first guarded paper-order candidate audit.

This module audits order candidates produced by the guarded paper-only routing
bridge. It is intentionally non-invasive: it never submits broker orders, never
opens positions, and never enables live/testnet/exchange execution. Candidate
records are diagnostic-only and are emitted only when the bridge already marked
``would_submit=true``.
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
from core.paper_unlock_routing_bridge import EVENT_TYPE as BRIDGE_EVENT_TYPE

PROMPT_ID = "29.4.4q"
EVENT_TYPE = "GUARDED_PAPER_ORDER_CANDIDATE_AUDIT"
REPORT_NAME = "paper_unlock_candidate_audit_report.json"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"
READY_DECISION = "PAPER_ORDER_CANDIDATE_AUDIT_READY_DIAGNOSTIC"
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
class GuardedPaperOrderCandidateAuditSettings:
    enabled: bool = True
    report_name: str = REPORT_NAME
    events_name: str = "paper_events.jsonl"
    status_name: str = "paper_status.json"
    bridge_event_type: str = BRIDGE_EVENT_TYPE
    candidate_event_type: str = EVENT_TYPE
    profile_name: str = PROFILE_NAME
    enable_name: str = ENABLE_NAME
    max_event_lines: int = 5000
    max_positions: int = 1
    risk_per_trade_pct: float = 0.0025
    rr: float = 2.0
    emit_candidate_events: bool = True
    audit_only: bool = True

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "GuardedPaperOrderCandidateAuditSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLED", True)),
            report_name=str(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            status_name=str(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_STATUS_NAME", "paper_status.json") or "paper_status.json"),
            bridge_event_type=str(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_BRIDGE_EVENT_TYPE", BRIDGE_EVENT_TYPE) or BRIDGE_EVENT_TYPE),
            candidate_event_type=str(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_EVENT_TYPE", EVENT_TYPE) or EVENT_TYPE),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            enable_name=str(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLE_NAME", ENABLE_NAME) or ENABLE_NAME),
            max_event_lines=max(100, _safe_int(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_MAX_EVENT_LINES", 5000), 5000)),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_MAX_POSITIONS", 1), 1)),
            risk_per_trade_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_RISK_PER_TRADE_PCT", 0.0025), 0.0025),
            rr=max(0.1, _safe_float(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_RR", 2.0), 2.0)),
            emit_candidate_events=bool(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_EMIT_EVENTS", True)),
            audit_only=bool(getattr(cfg, "PAPER_UNLOCK_CANDIDATE_AUDIT_ONLY", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "report_name": self.report_name,
            "events_name": self.events_name,
            "status_name": self.status_name,
            "bridge_event_type": self.bridge_event_type,
            "candidate_event_type": self.candidate_event_type,
            "profile_name": self.profile_name,
            "enable_name": self.enable_name,
            "max_event_lines": self.max_event_lines,
            "max_positions": self.max_positions,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "rr": self.rr,
            "emit_candidate_events": self.emit_candidate_events,
            "audit_only": self.audit_only,
        }


def _candidate_prices(side: str, entry_price: float, atr: float, rr: float) -> tuple[float, float, float]:
    stop_distance = abs(float(atr or 0.0))
    if stop_distance <= 0.0:
        stop_distance = max(0.00000001, abs(entry_price) * 0.01)
    if side == "BUY":
        stop_loss = entry_price - Config.ATR_MULT * stop_distance
        take_profit = entry_price + Config.ATR_MULT * stop_distance * rr
    else:
        stop_loss = entry_price + Config.ATR_MULT * stop_distance
        take_profit = entry_price - Config.ATR_MULT * stop_distance * rr
    return float(stop_loss), float(take_profit), abs(entry_price - stop_loss)


def build_guarded_paper_order_candidate_audit_event(
    *,
    settings: GuardedPaperOrderCandidateAuditSettings | None = None,
    routing_bridge_event: Mapping[str, Any] | None = None,
    cycle_id: str = "",
    symbol: str = "",
    candle_ts: str = "",
    entry_price: float = 0.0,
    atr: float = 0.0,
    account_balance: float = 1000.0,
    equity: float | None = None,
    open_positions_count: int = 0,
    duplicate_candle: bool = False,
    duplicate_order: bool = False,
    daily_entry_count: int = 0,
    weekly_entry_count: int = 0,
    max_daily_entries: int = 6,
    max_weekly_entries: int = 30,
) -> dict[str, Any]:
    """Build a guarded candidate-order audit event without order submission."""
    settings = settings or GuardedPaperOrderCandidateAuditSettings.from_config()
    bridge = routing_bridge_event if isinstance(routing_bridge_event, Mapping) else {}
    cycle_id = str(cycle_id or bridge.get("cycle_id") or "")
    symbol = str(symbol or bridge.get("symbol") or "")
    candle_ts = str(candle_ts or bridge.get("candle_ts") or "")
    side = str(bridge.get("side") or "").upper()
    mode = str(bridge.get("mode") or "paper")
    entry_price = _safe_float(entry_price, 0.0)
    account_balance = _safe_float(account_balance, 0.0)
    equity = account_balance if equity is None else _safe_float(equity, account_balance)
    open_positions_count = _safe_int(open_positions_count, 0)
    max_daily_entries = max(0, _safe_int(max_daily_entries, 6))
    max_weekly_entries = max(0, _safe_int(max_weekly_entries, 30))
    daily_entry_count = max(0, _safe_int(daily_entry_count, 0))
    weekly_entry_count = max(0, _safe_int(weekly_entry_count, 0))

    would_submit_from_bridge = _safe_bool(bridge.get("would_submit"))
    would_route_from_bridge = _safe_bool(bridge.get("would_route"))
    paper_orders_enabled = _safe_bool(bridge.get("paper_orders_enabled"))
    experiment_allowed = _safe_bool(bridge.get("paper_unlock_experiment_allowed"))
    manual_activation_allowed = _safe_bool(bridge.get("manual_activation_allowed"))
    operational_unlock_allowed = _safe_bool(bridge.get("operational_unlock_allowed"))
    live_allowed = _safe_bool(bridge.get("live_allowed"))
    testnet_allowed = _safe_bool(bridge.get("testnet_allowed"))
    exchange_broker_allowed = _safe_bool(bridge.get("exchange_broker_allowed"))
    automatic_activation_allowed = _safe_bool(bridge.get("automatic_activation_allowed"))
    paper_only_mode = mode.lower() == "paper"
    side_ok = side in {"BUY", "SELL"}
    max_positions_ok = open_positions_count < settings.max_positions
    daily_cadence_ok = max_daily_entries <= 0 or daily_entry_count < max_daily_entries
    weekly_cadence_ok = max_weekly_entries <= 0 or weekly_entry_count < max_weekly_entries
    duplicate_candle_block = bool(duplicate_candle)
    duplicate_order_block = bool(duplicate_order)
    paper_safety_ok = bool(
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

    stop_loss, take_profit, per_unit_risk = _candidate_prices(side if side_ok else "BUY", entry_price, atr, settings.rr)
    risk_amount = max(0.0, float(equity or account_balance) * settings.risk_per_trade_pct)
    quantity = 0.0
    if entry_price > 0.0 and per_unit_risk > 0.0:
        risk_qty = risk_amount / per_unit_risk
        notional_cap_qty = max(0.0, float(equity or account_balance) / entry_price)
        quantity = max(0.0, min(risk_qty, notional_cap_qty))
    notional = abs(quantity * entry_price)

    blocked_reasons: list[str] = []
    if not would_submit_from_bridge:
        blocked_reasons.append("bridge_would_submit_false")
    if not would_route_from_bridge:
        blocked_reasons.append("bridge_would_route_false")
    if not paper_safety_ok:
        blocked_reasons.append("paper_safety_state_not_ready")
    if not side_ok:
        blocked_reasons.append("no_directional_side")
    if entry_price <= 0.0:
        blocked_reasons.append("entry_price_invalid")
    if risk_amount <= 0.0 or quantity <= 0.0:
        blocked_reasons.append("position_size_invalid")
    if not max_positions_ok:
        blocked_reasons.append("max_positions")
    if duplicate_candle_block:
        blocked_reasons.append("duplicate_candle")
    if duplicate_order_block:
        blocked_reasons.append("duplicate_order")
    if not daily_cadence_ok:
        blocked_reasons.append("daily_cadence_limit")
    if not weekly_cadence_ok:
        blocked_reasons.append("weekly_cadence_limit")

    candidate_ready = bool(not blocked_reasons)
    return {
        "event_type": settings.candidate_event_type,
        "prompt": PROMPT_ID,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "candle_ts": candle_ts,
        "ts": utc_now_iso(),
        "profile_name": settings.profile_name,
        "enable_name": settings.enable_name,
        "source_bridge_event_type": bridge.get("event_type") or settings.bridge_event_type,
        "side": side,
        "mode": mode,
        "paper_only_mode": paper_only_mode,
        "routing_mode": bridge.get("routing_mode") or "paper_only",
        "submission_mode": "candidate_audit_only",
        "audit_only": True,
        "would_route_from_bridge": would_route_from_bridge,
        "would_submit_from_bridge": would_submit_from_bridge,
        "candidate_ready": candidate_ready,
        "candidate_rejected": not candidate_ready,
        "blocked_reason": None if candidate_ready else (blocked_reasons[0] if blocked_reasons else "candidate_not_ready"),
        "blocked_reasons": blocked_reasons,
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
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_per_trade_pct": settings.risk_per_trade_pct,
        "risk_amount": risk_amount,
        "position_size": quantity,
        "notional": notional,
        "per_unit_risk": per_unit_risk,
        "rr": settings.rr,
        "atr": _safe_float(atr, 0.0),
        "max_positions": settings.max_positions,
        "open_positions_count": open_positions_count,
        "max_positions_ok": max_positions_ok,
        "duplicate_candle_block": duplicate_candle_block,
        "duplicate_order_block": duplicate_order_block,
        "daily_entry_count": daily_entry_count,
        "weekly_entry_count": weekly_entry_count,
        "max_daily_entries": max_daily_entries,
        "max_weekly_entries": max_weekly_entries,
        "daily_cadence_ok": daily_cadence_ok,
        "weekly_cadence_ok": weekly_cadence_ok,
        "orders_submitted_by_candidate_audit": 0,
        "positions_opened_by_candidate_audit": 0,
    }


def build_paper_unlock_candidate_audit_report(base: str | Path = "data", settings: GuardedPaperOrderCandidateAuditSettings | None = None) -> dict[str, Any]:
    settings = settings or GuardedPaperOrderCandidateAuditSettings.from_config()
    base_path = Path(base)
    events = _read_jsonl(base_path / settings.events_name, max_lines=settings.max_event_lines)
    status_payload = _read_json(base_path / settings.status_name)
    cycle_events = [e for e in events if e.get("event_type") == CYCLE_COMPLETED_EVENT_TYPE]
    bridge_events = [e for e in events if e.get("event_type") == settings.bridge_event_type]
    candidate_events = [e for e in events if e.get("event_type") == settings.candidate_event_type]
    latest_cycle = cycle_events[-1] if cycle_events else {}
    latest_cycle_id = str(latest_cycle.get("cycle_id") or status_payload.get("active_cycle_id") or "")
    latest_bridge = [e for e in bridge_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]
    latest_candidates = [e for e in candidate_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]
    would_submit_events = [e for e in latest_bridge if _safe_bool(e.get("would_submit"))]
    candidate_ready_events = [e for e in latest_candidates if _safe_bool(e.get("candidate_ready"))]
    rejected_candidates = [e for e in latest_candidates if not _safe_bool(e.get("candidate_ready"))]
    orders_by_candidate_audit = sum(_safe_int(e.get("orders_submitted_by_candidate_audit"), 0) for e in latest_candidates)
    positions_by_candidate_audit = sum(_safe_int(e.get("positions_opened_by_candidate_audit"), 0) for e in latest_candidates)
    cycle_orders = _safe_int(latest_cycle.get("orders"), 0)
    cycle_positions = _safe_int(latest_cycle.get("open_positions"), 0)
    cycle_errors = _safe_int(latest_cycle.get("errors"), 0)
    expected_candidate_events = len(would_submit_events)
    candidate_coverage_ok = bool(expected_candidate_events == 0 or len(latest_candidates) >= expected_candidate_events)
    safety_checks = {
        "paper_mode_status": str(status_payload.get("mode") or "paper") == "paper",
        "operational_unlock_blocked": all(not _safe_bool(e.get("operational_unlock_allowed")) for e in latest_candidates) if latest_candidates else True,
        "live_blocked": all(not _safe_bool(e.get("live_allowed")) for e in latest_candidates) if latest_candidates else True,
        "testnet_blocked": all(not _safe_bool(e.get("testnet_allowed")) for e in latest_candidates) if latest_candidates else True,
        "exchange_broker_blocked": all(not _safe_bool(e.get("exchange_broker_allowed")) for e in latest_candidates) if latest_candidates else True,
        "candidate_audit_did_not_submit_orders": orders_by_candidate_audit == 0,
        "candidate_audit_did_not_open_positions": positions_by_candidate_audit == 0,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    status = "PASS" if latest_cycle and candidate_coverage_ok and safety_ok and cycle_errors == 0 else "WARN"
    decision_status = READY_DECISION if status == "PASS" else KEEP_DECISION
    blocked_reasons: list[Any] = []
    for e in rejected_candidates:
        reasons = e.get("blocked_reasons") if isinstance(e.get("blocked_reasons"), list) else [e.get("blocked_reason")]
        blocked_reasons.extend(r for r in reasons if r)

    decision = {
        "status": decision_status,
        "profile_name": settings.profile_name,
        "latest_cycle_id": latest_cycle_id,
        "routing_bridge_events": len(latest_bridge),
        "would_submit_count": expected_candidate_events,
        "candidate_order_audit_events": len(latest_candidates),
        "candidate_ready_count": len(candidate_ready_events),
        "candidate_rejected_count": len(rejected_candidates),
        "candidate_coverage_ok": candidate_coverage_ok,
        "orders_submitted_by_candidate_audit": orders_by_candidate_audit,
        "positions_opened_by_candidate_audit": positions_by_candidate_audit,
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
        "candidate_order_audit": {
            "candidate_coverage_ok": candidate_coverage_ok,
            "would_submit_count": expected_candidate_events,
            "candidate_order_audit_events": len(latest_candidates),
            "candidate_ready_count": len(candidate_ready_events),
            "candidate_rejected_count": len(rejected_candidates),
            "blocked_reason_counts": _counts(blocked_reasons),
            "side_counts": _counts(e.get("side") for e in latest_candidates),
            "submission_mode_counts": _counts(e.get("submission_mode") for e in latest_candidates),
        },
        "safety_checks": safety_checks,
        "sample_candidate_events_tail": latest_candidates[-10:],
        "opens_orders": False,
        "orders_submitted": cycle_orders,
        "positions_opened": cycle_positions,
        "orders_submitted_by_candidate_audit": orders_by_candidate_audit,
        "positions_opened_by_candidate_audit": positions_by_candidate_audit,
        "paper_orders_enabled": any(_safe_bool(e.get("paper_orders_enabled")) for e in latest_bridge),
        "paper_unlock_experiment_allowed": any(_safe_bool(e.get("paper_unlock_experiment_allowed")) for e in latest_bridge),
        "manual_activation_allowed": any(_safe_bool(e.get("manual_activation_allowed")) for e in latest_bridge),
        "operational_unlock_allowed": False,
        "automatic_activation_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "next_patch": "29.4.4r paper order submission dry-run / simulated broker handoff, only after candidate audit coverage is stable.",
    }


def write_paper_unlock_candidate_audit_report(base: str | Path = "data", settings: GuardedPaperOrderCandidateAuditSettings | None = None) -> dict[str, Any]:
    settings = settings or GuardedPaperOrderCandidateAuditSettings.from_config()
    report = build_paper_unlock_candidate_audit_report(base, settings)
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
