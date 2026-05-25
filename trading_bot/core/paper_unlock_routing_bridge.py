"""Prompt 29.4.4p guarded paper-only routing bridge audit.

The bridge connects accepted guarded runtime diagnostics to an auditable
paper-only order-intent simulation. It is intentionally fail-closed and does not
submit broker orders. A later patch can consume ``would_submit=true`` candidates
for candidate-order audit / dry-run handoff.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

from config import Config
from core.calibrated_structure_shadow import _safe_float, _safe_int
from core.paper_unlock_guarded_enable import ACTIVE_DECISION, ENABLE_NAME, PROFILE_NAME
from core.paper_unlock_runtime_audit import RUNTIME_EVENT_TYPE, RuntimePaperOrderAuditSettings, guarded_enable_runtime_state

PROMPT_ID = "29.4.4p"
EVENT_TYPE = "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT"
REPORT_NAME = "paper_unlock_routing_bridge_report.json"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"
READY_DECISION = "ROUTING_BRIDGE_AUDIT_READY_DIAGNOSTIC"
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


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class GuardedPaperRoutingBridgeSettings:
    enabled: bool = True
    report_name: str = REPORT_NAME
    events_name: str = "paper_events.jsonl"
    status_name: str = "paper_status.json"
    runtime_event_type: str = RUNTIME_EVENT_TYPE
    bridge_event_type: str = EVENT_TYPE
    profile_name: str = PROFILE_NAME
    enable_name: str = ENABLE_NAME
    max_event_lines: int = 5000
    map_score_min: float = 65.0
    map_score_max: float = 79.999
    max_positions: int = 1
    risk_per_trade_pct: float = 0.0025
    emit_bridge_events: bool = True
    simulation_only: bool = True

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "GuardedPaperRoutingBridgeSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_ENABLED", True)),
            report_name=str(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            status_name=str(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_STATUS_NAME", "paper_status.json") or "paper_status.json"),
            runtime_event_type=str(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_RUNTIME_EVENT_TYPE", RUNTIME_EVENT_TYPE) or RUNTIME_EVENT_TYPE),
            bridge_event_type=str(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_EVENT_TYPE", EVENT_TYPE) or EVENT_TYPE),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            enable_name=str(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_ENABLE_NAME", ENABLE_NAME) or ENABLE_NAME),
            max_event_lines=max(100, _safe_int(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_MAX_EVENT_LINES", 5000), 5000)),
            map_score_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_MAP_SCORE_MIN", 65.0), 65.0),
            map_score_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_MAP_SCORE_MAX", 79.999), 79.999),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_MAX_POSITIONS", 1), 1)),
            risk_per_trade_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_RISK_PER_TRADE_PCT", 0.0025), 0.0025),
            emit_bridge_events=bool(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_EMIT_EVENTS", True)),
            simulation_only=bool(getattr(cfg, "PAPER_UNLOCK_ROUTING_BRIDGE_SIMULATION_ONLY", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "report_name": self.report_name,
            "events_name": self.events_name,
            "status_name": self.status_name,
            "runtime_event_type": self.runtime_event_type,
            "bridge_event_type": self.bridge_event_type,
            "profile_name": self.profile_name,
            "enable_name": self.enable_name,
            "max_event_lines": self.max_event_lines,
            "map_score_min": self.map_score_min,
            "map_score_max": self.map_score_max,
            "max_positions": self.max_positions,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "emit_bridge_events": self.emit_bridge_events,
            "simulation_only": self.simulation_only,
        }


def build_guarded_paper_routing_bridge_event(
    *,
    settings: GuardedPaperRoutingBridgeSettings | None = None,
    runtime_audit_event: Mapping[str, Any] | None = None,
    cycle_id: str = "",
    symbol: str = "",
    open_positions_count: int | None = None,
) -> dict[str, Any]:
    settings = settings or GuardedPaperRoutingBridgeSettings.from_config()
    event = runtime_audit_event if isinstance(runtime_audit_event, Mapping) else {}
    cycle_id = str(cycle_id or event.get("cycle_id") or "")
    symbol = str(symbol or event.get("symbol") or "")
    mode = str(event.get("mode") or "paper")
    side = str(event.get("side") or "").upper()
    runtime_structure_state = str(event.get("runtime_structure_state") or "").upper()
    map_score = _safe_float(event.get("map_score"), -1.0)
    open_positions = _safe_int(event.get("open_positions_count"), 0) if open_positions_count is None else int(open_positions_count or 0)

    accepted_diagnostic = bool(event.get("accepted_diagnostic"))
    paper_orders_enabled = bool(event.get("paper_orders_enabled"))
    experiment_allowed = bool(event.get("paper_unlock_experiment_allowed"))
    manual_activation_allowed = bool(event.get("manual_activation_allowed"))
    automatic_activation_allowed = bool(event.get("automatic_activation_allowed"))
    operational_unlock_allowed = bool(event.get("operational_unlock_allowed"))
    live_allowed = bool(event.get("live_allowed"))
    testnet_allowed = bool(event.get("testnet_allowed"))
    exchange_broker_allowed = bool(event.get("exchange_broker_allowed"))

    map_score_ok = settings.map_score_min <= map_score <= settings.map_score_max
    side_ok = side in {"BUY", "SELL"}
    paper_mode_ok = mode.lower() == "paper"
    confirmation_ok = runtime_structure_state == "CONFIRMATION"
    max_positions_ok = open_positions < settings.max_positions
    paper_state_ok = bool(
        paper_orders_enabled
        and experiment_allowed
        and manual_activation_allowed
        and not automatic_activation_allowed
        and not operational_unlock_allowed
        and not live_allowed
        and not testnet_allowed
        and not exchange_broker_allowed
    )

    blocked_reasons: list[str] = []
    if not paper_mode_ok:
        blocked_reasons.append("mode_not_paper")
    if not accepted_diagnostic:
        blocked_reasons.append("accepted_diagnostic_false")
    if not paper_state_ok:
        blocked_reasons.append("paper_operator_state_not_ready")
    if not side_ok:
        blocked_reasons.append("no_directional_side")
    if not map_score_ok:
        blocked_reasons.append("map_score_outside_65_79")
    if not confirmation_ok:
        blocked_reasons.append(f"structure_state_not_confirmation:{runtime_structure_state or 'NO_STRUCTURE'}")
    if not max_positions_ok:
        blocked_reasons.append("max_positions")

    would_route = bool(accepted_diagnostic and paper_state_ok and paper_mode_ok)
    would_submit = bool(would_route and side_ok and map_score_ok and confirmation_ok and max_positions_ok)
    return {
        "event_type": settings.bridge_event_type,
        "prompt": PROMPT_ID,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "candle_ts": event.get("candle_ts"),
        "ts": utc_now_iso(),
        "profile_name": settings.profile_name,
        "enable_name": settings.enable_name,
        "side": side,
        "accepted_diagnostic": accepted_diagnostic,
        "paper_orders_enabled": paper_orders_enabled,
        "paper_unlock_experiment_allowed": experiment_allowed,
        "manual_activation_allowed": manual_activation_allowed,
        "automatic_activation_allowed": automatic_activation_allowed,
        "operational_unlock_allowed": operational_unlock_allowed,
        "mode": mode,
        "paper_only_mode": paper_mode_ok,
        "live_allowed": live_allowed,
        "testnet_allowed": testnet_allowed,
        "exchange_broker_allowed": exchange_broker_allowed,
        "map_score": map_score,
        "map_score_ok": map_score_ok,
        "runtime_structure_state": runtime_structure_state,
        "confirmation_ok": confirmation_ok,
        "risk_per_trade_pct": settings.risk_per_trade_pct,
        "max_positions": settings.max_positions,
        "open_positions_count": open_positions,
        "max_positions_ok": max_positions_ok,
        "would_route": would_route,
        "would_submit": would_submit,
        "routing_mode": "paper_only",
        "submission_mode": "simulation_only" if settings.simulation_only else "paper_only_handoff_disabled",
        "orders_submitted_by_bridge": 0,
        "positions_opened_by_bridge": 0,
        "blocked_reason": None if would_submit else (blocked_reasons[0] if blocked_reasons else "simulation_only_no_submission"),
        "blocked_reasons": blocked_reasons,
        "live_blocked": not live_allowed,
        "testnet_blocked": not testnet_allowed,
        "exchange_broker_blocked": not exchange_broker_allowed,
    }


def build_paper_unlock_routing_bridge_report(base: str | Path = "data", settings: GuardedPaperRoutingBridgeSettings | None = None) -> dict[str, Any]:
    settings = settings or GuardedPaperRoutingBridgeSettings.from_config()
    runtime_settings = RuntimePaperOrderAuditSettings.from_config(Config)
    base_path = Path(base)
    events = _read_jsonl(base_path / settings.events_name, max_lines=settings.max_event_lines)
    status_payload = _read_json(base_path / settings.status_name)
    guarded_enable = guarded_enable_runtime_state(base_path, runtime_settings)
    cycle_events = [e for e in events if e.get("event_type") == CYCLE_COMPLETED_EVENT_TYPE]
    runtime_events = [e for e in events if e.get("event_type") == settings.runtime_event_type]
    bridge_events = [e for e in events if e.get("event_type") == settings.bridge_event_type]
    latest_cycle = cycle_events[-1] if cycle_events else {}
    latest_cycle_id = str(latest_cycle.get("cycle_id") or status_payload.get("active_cycle_id") or "")
    latest_runtime = [e for e in runtime_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]
    latest_bridge = [e for e in bridge_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]

    scanned = _safe_int(latest_cycle.get("scanned"), 0)
    cycle_errors = _safe_int(latest_cycle.get("errors"), 0)
    cycle_orders = _safe_int(latest_cycle.get("orders"), 0)
    would_route_events = [e for e in latest_bridge if bool(e.get("would_route"))]
    would_submit_events = [e for e in latest_bridge if bool(e.get("would_submit"))]
    blocked_events = [e for e in latest_bridge if not bool(e.get("would_submit"))]
    orders_by_bridge = sum(_safe_int(e.get("orders_submitted_by_bridge"), 0) for e in latest_bridge)

    bridge_coverage_ok = bool(latest_bridge and (not latest_runtime or len(latest_bridge) >= len(latest_runtime)) and (not scanned or len(latest_bridge) >= scanned))
    safety_checks = {
        "paper_mode_status": str(status_payload.get("mode") or "paper") == "paper",
        "operational_unlock_blocked": not bool(guarded_enable.get("operational_unlock_allowed")),
        "automatic_activation_blocked": not bool(guarded_enable.get("automatic_activation_allowed")),
        "live_blocked": not bool(guarded_enable.get("live_allowed")),
        "testnet_blocked": not bool(guarded_enable.get("testnet_allowed")),
        "exchange_broker_blocked": not bool(guarded_enable.get("exchange_broker_allowed")),
        "bridge_did_not_submit_orders": orders_by_bridge == 0,
        "bridge_did_not_open_positions": sum(_safe_int(e.get("positions_opened_by_bridge"), 0) for e in latest_bridge) == 0,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())
    cycle_completed = bool(latest_cycle)
    status = "PASS" if cycle_completed and bridge_coverage_ok and safety_ok and cycle_errors == 0 else "WARN"
    decision_status = READY_DECISION if status == "PASS" else KEEP_DECISION
    blocked_reasons: list[Any] = []
    for e in blocked_events:
        reasons = e.get("blocked_reasons") if isinstance(e.get("blocked_reasons"), list) else [e.get("blocked_reason")]
        blocked_reasons.extend([r for r in reasons if r])

    return {
        "prompt": PROMPT_ID,
        "report_type": "guarded_paper_routing_bridge_audit",
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": {
            "status": decision_status,
            "profile_name": settings.profile_name,
            "enable_name": settings.enable_name,
            "latest_cycle_id": latest_cycle_id,
            "routing_bridge_events": len(latest_bridge),
            "runtime_audit_events": len(latest_runtime),
            "would_route_count": len(would_route_events),
            "would_submit_count": len(would_submit_events),
            "blocked_count": len(blocked_events),
            "orders_submitted_by_bridge": orders_by_bridge,
            "orders_submitted": cycle_orders,
            "positions_opened": _safe_int(latest_cycle.get("open_positions"), 0),
            "routing_mode": "paper_only",
            "bridge_coverage_ok": bridge_coverage_ok,
            "safety_ok": safety_ok,
            "reason": "Guarded accepted diagnostics are connected to a paper-only routing bridge audit; bridge remains simulation-only and submits no orders." if decision_status == READY_DECISION else "Routing bridge audit is incomplete or safety checks failed; keep fail-closed.",
        },
        "settings": settings.to_dict(),
        "guarded_enable_state": guarded_enable,
        "latest_cycle": latest_cycle,
        "counts": {
            "events_read": len(events),
            "cycle_completed_events": len(cycle_events),
            "runtime_audit_events_latest_cycle": len(latest_runtime),
            "routing_bridge_events_latest_cycle": len(latest_bridge),
            "scanned": scanned,
            "signals": _safe_int(latest_cycle.get("signals"), 0),
            "orders_submitted": cycle_orders,
            "orders_submitted_by_bridge": orders_by_bridge,
            "positions_opened": _safe_int(latest_cycle.get("open_positions"), 0),
            "errors": cycle_errors,
            "would_route_count": len(would_route_events),
            "would_submit_count": len(would_submit_events),
            "blocked_count": len(blocked_events),
        },
        "routing_bridge_audit": {
            "profile_name": settings.profile_name,
            "bridge_coverage_ok": bridge_coverage_ok,
            "would_route_count": len(would_route_events),
            "would_submit_count": len(would_submit_events),
            "blocked_count": len(blocked_events),
            "blocked_reason_counts": _counts(blocked_reasons),
            "accepted_diagnostic_count": sum(1 for e in latest_bridge if bool(e.get("accepted_diagnostic"))),
            "routing_mode_counts": _counts(e.get("routing_mode") for e in latest_bridge),
            "submission_mode_counts": _counts(e.get("submission_mode") for e in latest_bridge),
        },
        "safety_checks": safety_checks,
        "sample_bridge_events_tail": latest_bridge[-10:],
        "opens_orders": False,
        "orders_submitted": cycle_orders,
        "orders_submitted_by_bridge": orders_by_bridge,
        "positions_opened": _safe_int(latest_cycle.get("open_positions"), 0),
        "paper_orders_enabled": bool(guarded_enable.get("paper_orders_enabled")),
        "paper_unlock_experiment_allowed": bool(guarded_enable.get("paper_unlock_experiment_allowed")),
        "manual_activation_allowed": bool(guarded_enable.get("manual_activation_allowed")),
        "operational_unlock_allowed": False,
        "automatic_activation_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "next_patch": "29.4.4q first guarded paper-order candidate audit, only after would_submit candidates exist.",
    }


def write_paper_unlock_routing_bridge_report(base: str | Path = "data", settings: GuardedPaperRoutingBridgeSettings | None = None) -> dict[str, Any]:
    settings = settings or GuardedPaperRoutingBridgeSettings.from_config()
    report = build_paper_unlock_routing_bridge_report(base, settings)
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
