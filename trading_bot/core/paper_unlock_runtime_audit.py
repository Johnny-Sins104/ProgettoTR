"""Prompt 29.4.4o runtime paper-order audit / first controlled paper-cycle monitoring.

This module audits the operator-controlled guarded paper-only enable path during
runtime.  It deliberately does not route orders by itself.  Its purpose is to
make the runtime distinction explicit between the legacy BTC_ONLY_40_Q60 unlock
path and the guarded MAP_SCORE_65_79_REPAIRED_STABILITY_V1 paper-only profile.

Safety boundaries:
- paper-only mode is required;
- live/testnet/exchange broker remain blocked;
- operational unlock remains false;
- this module never submits orders and never opens positions;
- acceptance is diagnostic unless a later, separate routing patch wires the
  guarded profile into the order path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

from config import Config
from core.jsonl_utils import iter_jsonl_tail
from core.calibrated_structure_shadow import _safe_float, _safe_int
from core.paper_unlock_guarded_enable import ACTIVE_DECISION, ENABLE_NAME, PROFILE_NAME, REPORT_NAME as GUARDED_ENABLE_REPORT_NAME

REPORT_NAME = "paper_unlock_runtime_audit_report.json"
PROMPT_ID = "29.4.4o"
RUNTIME_EVENT_TYPE = "GUARDED_PAPER_RUNTIME_AUDIT"
LEGACY_UNLOCK_EVENT_TYPE = "PAPER_UNLOCK_EVALUATED"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"
READY_DECISION = "RUNTIME_PAPER_ORDER_AUDIT_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"
PROFILE_NAME = PROFILE_NAME
ENABLE_NAME = ENABLE_NAME
LEGACY_PROFILE = "BTC_ONLY_40_Q60"


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
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)



def _counts(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value if value not in {None, ""} else "-")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class RuntimePaperOrderAuditSettings:
    enabled: bool = True
    report_name: str = REPORT_NAME
    guarded_enable_report_name: str = GUARDED_ENABLE_REPORT_NAME
    events_name: str = "paper_events.jsonl"
    status_name: str = "paper_status.json"
    profile_name: str = PROFILE_NAME
    enable_name: str = ENABLE_NAME
    legacy_profile: str = LEGACY_PROFILE
    max_event_lines: int = 5000
    map_score_min: float = 65.0
    map_score_max: float = 79.999
    require_paper_orders_enabled: bool = True
    require_experiment_allowed: bool = True
    require_manual_activation: bool = True
    require_operator_controlled_decision: bool = True
    require_confirmation_only: bool = True
    emit_runtime_events: bool = True

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "RuntimePaperOrderAuditSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_ENABLED", True)),
            report_name=str(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            guarded_enable_report_name=str(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_GUARDED_ENABLE_REPORT_NAME", GUARDED_ENABLE_REPORT_NAME) or GUARDED_ENABLE_REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            status_name=str(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_STATUS_NAME", "paper_status.json") or "paper_status.json"),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            enable_name=str(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_ENABLE_NAME", ENABLE_NAME) or ENABLE_NAME),
            legacy_profile=str(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_LEGACY_PROFILE", LEGACY_PROFILE) or LEGACY_PROFILE),
            max_event_lines=max(100, _safe_int(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_MAX_EVENT_LINES", 5000), 5000)),
            map_score_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_MAP_SCORE_MIN", 65.0), 65.0),
            map_score_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_MAP_SCORE_MAX", 79.999), 79.999),
            require_paper_orders_enabled=bool(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_PAPER_ORDERS_ENABLED", True)),
            require_experiment_allowed=bool(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_EXPERIMENT_ALLOWED", True)),
            require_manual_activation=bool(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_MANUAL_ACTIVATION", True)),
            require_operator_controlled_decision=bool(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_OPERATOR_CONTROLLED_DECISION", True)),
            require_confirmation_only=bool(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_REQUIRE_CONFIRMATION_ONLY", True)),
            emit_runtime_events=bool(getattr(cfg, "PAPER_UNLOCK_RUNTIME_AUDIT_EMIT_EVENTS", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "report_name": self.report_name,
            "guarded_enable_report_name": self.guarded_enable_report_name,
            "events_name": self.events_name,
            "status_name": self.status_name,
            "profile_name": self.profile_name,
            "enable_name": self.enable_name,
            "legacy_profile": self.legacy_profile,
            "max_event_lines": self.max_event_lines,
            "map_score_min": self.map_score_min,
            "map_score_max": self.map_score_max,
            "require_paper_orders_enabled": self.require_paper_orders_enabled,
            "require_experiment_allowed": self.require_experiment_allowed,
            "require_manual_activation": self.require_manual_activation,
            "require_operator_controlled_decision": self.require_operator_controlled_decision,
            "require_confirmation_only": self.require_confirmation_only,
            "emit_runtime_events": self.emit_runtime_events,
        }


def guarded_enable_runtime_state(base: str | Path, settings: RuntimePaperOrderAuditSettings | None = None) -> dict[str, Any]:
    settings = settings or RuntimePaperOrderAuditSettings.from_config()
    payload = _read_json(Path(base) / settings.guarded_enable_report_name)
    decision = _safe_dict(payload.get("decision"))
    status = str(payload.get("status") or "")
    decision_status = str(decision.get("status") or payload.get("decision") or "")
    state = {
        "status": status,
        "decision_status": decision_status,
        "enable_name": decision.get("enable_name") or payload.get("enable_name"),
        "profile_name": decision.get("profile_name") or payload.get("profile_name"),
        "paper_orders_enabled": bool(payload.get("paper_orders_enabled")),
        "paper_unlock_experiment_allowed": bool(payload.get("paper_unlock_experiment_allowed")),
        "manual_activation_allowed": bool(payload.get("manual_activation_allowed")),
        "automatic_activation_allowed": bool(payload.get("automatic_activation_allowed")),
        "operational_unlock_allowed": bool(payload.get("operational_unlock_allowed")),
        "live_allowed": bool(payload.get("live_allowed")),
        "testnet_allowed": bool(payload.get("testnet_allowed")),
        "exchange_broker_allowed": bool(payload.get("exchange_broker_allowed")),
        "orders_submitted": _safe_int(payload.get("orders_submitted"), 0),
        "positions_opened": _safe_int(payload.get("positions_opened"), 0),
    }
    state["operator_controlled_active"] = bool(
        status == "PASS"
        and decision_status == ACTIVE_DECISION
        and state["paper_orders_enabled"]
        and state["paper_unlock_experiment_allowed"]
        and state["manual_activation_allowed"]
        and not state["automatic_activation_allowed"]
        and not state["operational_unlock_allowed"]
        and not state["live_allowed"]
        and not state["testnet_allowed"]
        and not state["exchange_broker_allowed"]
    )
    return state


def _runtime_state_from_payload(payload: Mapping[str, Any] | None, settings: RuntimePaperOrderAuditSettings) -> dict[str, Any]:
    payload = payload if isinstance(payload, Mapping) else {}
    decision = _safe_dict(payload.get("decision"))
    status = str(payload.get("status") or "")
    decision_status = str(decision.get("status") or payload.get("decision_status") or payload.get("decision") or "")
    return {
        "status": status,
        "decision_status": decision_status,
        "enable_name": decision.get("enable_name") or payload.get("enable_name") or settings.enable_name,
        "profile_name": decision.get("profile_name") or payload.get("profile_name") or settings.profile_name,
        "paper_orders_enabled": bool(payload.get("paper_orders_enabled")),
        "paper_unlock_experiment_allowed": bool(payload.get("paper_unlock_experiment_allowed")),
        "manual_activation_allowed": bool(payload.get("manual_activation_allowed")),
        "automatic_activation_allowed": bool(payload.get("automatic_activation_allowed")),
        "operational_unlock_allowed": bool(payload.get("operational_unlock_allowed")),
        "live_allowed": bool(payload.get("live_allowed")),
        "testnet_allowed": bool(payload.get("testnet_allowed")),
        "exchange_broker_allowed": bool(payload.get("exchange_broker_allowed")),
        "orders_submitted": _safe_int(payload.get("orders_submitted"), 0),
        "positions_opened": _safe_int(payload.get("positions_opened"), 0),
    }


def classify_runtime_structure_state(structure_diagnostic: Mapping[str, Any] | None) -> str:
    sd = structure_diagnostic if isinstance(structure_diagnostic, Mapping) else {}
    if not sd:
        return "NO_STRUCTURE"
    summary = str(sd.get("confirmation_summary") or "").upper()
    if not summary or summary == "NO_STRUCTURAL_CONFIRMATION":
        return "NO_STRUCTURE"
    if "WAIT" in summary or "NEAR_LIQUIDITY_WAIT" in summary:
        return "WAIT"
    if any(token in summary for token in ("BOS", "CHOCH", "MSS", "RETEST")) and bool(sd.get("confirmation_close")):
        return "CONFIRMATION"
    if any(token in summary for token in ("BOS", "CHOCH", "MSS", "RETEST")):
        return "CONTEXT"
    return "CONTEXT"


def build_guarded_runtime_audit_event(
    *,
    settings: RuntimePaperOrderAuditSettings | None = None,
    guarded_enable_state: Mapping[str, Any] | None = None,
    cycle_id: str = "",
    symbol: str = "",
    candle_ts: str = "",
    mode: str = "paper",
    signal_diagnostic: Mapping[str, Any] | None = None,
    scenario_diagnostic: Mapping[str, Any] | None = None,
    pattern_diagnostic: Mapping[str, Any] | None = None,
    structure_diagnostic: Mapping[str, Any] | None = None,
    legacy_unlock_decision: Mapping[str, Any] | None = None,
    duplicate_candle: bool = False,
    open_positions_count: int = 0,
) -> dict[str, Any]:
    settings = settings or RuntimePaperOrderAuditSettings.from_config()
    state = _runtime_state_from_payload(guarded_enable_state, settings) if guarded_enable_state is not None else {}
    signal_diagnostic = signal_diagnostic if isinstance(signal_diagnostic, Mapping) else {}
    scenario_diagnostic = scenario_diagnostic if isinstance(scenario_diagnostic, Mapping) else {}
    pattern_diagnostic = pattern_diagnostic if isinstance(pattern_diagnostic, Mapping) else {}
    structure_diagnostic = structure_diagnostic if isinstance(structure_diagnostic, Mapping) else {}
    legacy_unlock_decision = legacy_unlock_decision if isinstance(legacy_unlock_decision, Mapping) else {}

    paper_only_mode = str(mode or "").lower() == "paper"
    operator_state_ok = bool(
        state.get("status") == "PASS"
        and state.get("decision_status") == ACTIVE_DECISION
        and (not settings.require_paper_orders_enabled or bool(state.get("paper_orders_enabled")))
        and (not settings.require_experiment_allowed or bool(state.get("paper_unlock_experiment_allowed")))
        and (not settings.require_manual_activation or bool(state.get("manual_activation_allowed")))
        and not bool(state.get("automatic_activation_allowed"))
        and not bool(state.get("operational_unlock_allowed"))
        and not bool(state.get("live_allowed"))
        and not bool(state.get("testnet_allowed"))
        and not bool(state.get("exchange_broker_allowed"))
    )
    map_score = _safe_float(structure_diagnostic.get("map_score"), -1.0)
    map_score_ok = settings.map_score_min <= map_score <= settings.map_score_max
    runtime_state = classify_runtime_structure_state(structure_diagnostic)
    confirmation_ok = runtime_state == "CONFIRMATION" if settings.require_confirmation_only else runtime_state in {"CONFIRMATION", "CONTEXT"}
    side = str(signal_diagnostic.get("intended_side") or scenario_diagnostic.get("directional_bias") or pattern_diagnostic.get("pattern_bias") or "").upper()
    side_ok = side in {"BUY", "SELL"}
    flat_ok = open_positions_count < 1
    legacy_profile = str(legacy_unlock_decision.get("profile") or "")

    reject_reasons: list[str] = []
    if not paper_only_mode:
        reject_reasons.append("mode_not_paper")
    if not operator_state_ok:
        reject_reasons.append("operator_enable_not_active")
    if duplicate_candle:
        reject_reasons.append("duplicate_candle")
    if not flat_ok:
        reject_reasons.append("max_positions")
    if not side_ok:
        reject_reasons.append("no_directional_side")
    if not map_score_ok:
        reject_reasons.append("map_score_outside_65_79")
    if not confirmation_ok:
        reject_reasons.append(f"structure_state_not_confirmation:{runtime_state}")

    accepted_diagnostic = not reject_reasons
    return {
        "event_type": RUNTIME_EVENT_TYPE,
        "prompt": PROMPT_ID,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "candle_ts": candle_ts,
        "ts": utc_now_iso(),
        "profile_name": settings.profile_name,
        "enable_name": settings.enable_name,
        "legacy_unlock_profile": legacy_profile or settings.legacy_profile,
        "legacy_unlock_accepted": bool(legacy_unlock_decision.get("accepted")),
        "mode": mode,
        "paper_only_mode": paper_only_mode,
        "operator_state_ok": operator_state_ok,
        "paper_orders_enabled": bool(state.get("paper_orders_enabled")),
        "paper_unlock_experiment_allowed": bool(state.get("paper_unlock_experiment_allowed")),
        "manual_activation_allowed": bool(state.get("manual_activation_allowed")),
        "automatic_activation_allowed": bool(state.get("automatic_activation_allowed")),
        "operational_unlock_allowed": bool(state.get("operational_unlock_allowed")),
        "live_allowed": bool(state.get("live_allowed")),
        "testnet_allowed": bool(state.get("testnet_allowed")),
        "exchange_broker_allowed": bool(state.get("exchange_broker_allowed")),
        "side": side,
        "side_ok": side_ok,
        "duplicate_candle": bool(duplicate_candle),
        "open_positions_count": int(open_positions_count or 0),
        "runtime_structure_state": runtime_state,
        "confirmation_summary": structure_diagnostic.get("confirmation_summary"),
        "confirmation_close": bool(structure_diagnostic.get("confirmation_close")),
        "map_score": map_score,
        "map_score_ok": map_score_ok,
        "price_location": structure_diagnostic.get("price_location"),
        "structure_bias": structure_diagnostic.get("structure_bias"),
        "scenario": scenario_diagnostic.get("scenario"),
        "scenario_directional_bias": scenario_diagnostic.get("directional_bias"),
        "scenario_alignment": scenario_diagnostic.get("scenario_alignment"),
        "candlestick_bias": pattern_diagnostic.get("pattern_bias"),
        "candlestick_score": pattern_diagnostic.get("pattern_score"),
        "candlestick_patterns": pattern_diagnostic.get("patterns"),
        "signal_filter": signal_diagnostic.get("dominant_filter"),
        "signal_diagnostic_reason": signal_diagnostic.get("diagnostic_reason"),
        "accepted_diagnostic": accepted_diagnostic,
        "routing_enabled": False,
        "orders_submitted_by_audit": 0,
        "positions_opened_by_audit": 0,
        "reject_reasons": reject_reasons,
        "primary_reject_reason": reject_reasons[0] if reject_reasons else "eligible_diagnostic_only",
    }


def build_runtime_audit_report(base: str | Path, settings: RuntimePaperOrderAuditSettings | None = None) -> dict[str, Any]:
    settings = settings or RuntimePaperOrderAuditSettings.from_config()
    base_path = Path(base)
    events = _read_jsonl(base_path / settings.events_name, max_lines=settings.max_event_lines)
    status_payload = _read_json(base_path / settings.status_name)
    guarded_enable = guarded_enable_runtime_state(base_path, settings)
    runtime_events = [e for e in events if e.get("event_type") == RUNTIME_EVENT_TYPE]
    legacy_events = [e for e in events if e.get("event_type") == LEGACY_UNLOCK_EVENT_TYPE]
    cycle_events = [e for e in events if e.get("event_type") == CYCLE_COMPLETED_EVENT_TYPE]
    order_events = [e for e in events if str(e.get("event_type") or "") in {"PAPER_ORDER_CONFIRMED", "ORDER_SUBMITTED", "ORDER_FILLED"}]
    latest_cycle = cycle_events[-1] if cycle_events else {}
    latest_cycle_id = str(latest_cycle.get("cycle_id") or status_payload.get("active_cycle_id") or "")
    latest_runtime = [e for e in runtime_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]
    latest_legacy = [e for e in legacy_events if not latest_cycle_id or e.get("cycle_id") == latest_cycle_id]

    runtime_accepts = [e for e in latest_runtime if bool(e.get("accepted_diagnostic"))]
    runtime_rejects = [e for e in latest_runtime if not bool(e.get("accepted_diagnostic"))]
    reject_reasons = []
    for e in runtime_rejects:
        reasons = e.get("reject_reasons") if isinstance(e.get("reject_reasons"), list) else [e.get("primary_reject_reason")]
        reject_reasons.extend([r for r in reasons if r])

    legacy_profiles = []
    legacy_reasons = []
    for e in latest_legacy:
        decision = _safe_dict(e.get("decision"))
        legacy_profiles.append(decision.get("profile") or "-")
        legacy_reasons.append(e.get("reason") or decision.get("reason") or "-")

    safety_checks = {
        "paper_mode_status": str(status_payload.get("mode") or "paper") == "paper",
        "guarded_operator_active_or_fail_closed": bool(guarded_enable.get("operator_controlled_active") or not guarded_enable.get("paper_orders_enabled")),
        "operational_unlock_blocked": not bool(guarded_enable.get("operational_unlock_allowed")),
        "automatic_activation_blocked": not bool(guarded_enable.get("automatic_activation_allowed")),
        "live_blocked": not bool(guarded_enable.get("live_allowed")),
        "testnet_blocked": not bool(guarded_enable.get("testnet_allowed")),
        "exchange_broker_blocked": not bool(guarded_enable.get("exchange_broker_allowed")),
        "audit_did_not_submit_orders": len(order_events) == _safe_int(latest_cycle.get("orders"), 0),
    }
    runtime_audit_present = bool(latest_runtime)
    cycle_completed = bool(latest_cycle)
    cycle_errors = _safe_int(latest_cycle.get("errors"), 0)
    cycle_orders = _safe_int(latest_cycle.get("orders"), 0)
    scanned = _safe_int(latest_cycle.get("scanned"), 0)
    runtime_coverage_ok = bool(runtime_audit_present and (not scanned or len(latest_runtime) >= scanned))
    safety_ok = all(bool(v) for v in safety_checks.values())
    status = "PASS" if cycle_completed and runtime_coverage_ok and safety_ok and cycle_errors == 0 else "WARN"
    decision_status = READY_DECISION if status == "PASS" else KEEP_DECISION

    reason = (
        "Runtime guarded paper-order audit is present for the latest paper cycle; legacy unlock and guarded profile routing are explicitly separated; no live/testnet execution is allowed."
        if decision_status == READY_DECISION
        else "Runtime guarded paper-order audit is incomplete or safety/coverage checks did not pass; keep paper routing diagnostic-only."
    )
    next_patch = (
        "29.4.4p guarded profile runtime routing review / paper-only acceptance path hardening, still no live/testnet."
        if decision_status == READY_DECISION and not runtime_accepts
        else "Continue supervised paper-only monitoring; only consider routing hardening after guarded runtime accept/reject reasons are stable."
    )

    return {
        "prompt": PROMPT_ID,
        "report_type": "runtime_paper_order_audit",
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": {
            "status": decision_status,
            "profile_name": settings.profile_name,
            "enable_name": settings.enable_name,
            "latest_cycle_id": latest_cycle_id,
            "runtime_audit_events": len(latest_runtime),
            "legacy_unlock_events": len(latest_legacy),
            "runtime_accepts_diagnostic": len(runtime_accepts),
            "runtime_rejects": len(runtime_rejects),
            "runtime_coverage_ok": runtime_coverage_ok,
            "safety_ok": safety_ok,
            "orders_submitted": cycle_orders,
            "positions_opened": _safe_int(latest_cycle.get("open_positions"), 0),
            "reason": reason,
            "next_patch": next_patch,
        },
        "settings": settings.to_dict(),
        "guarded_enable_state": guarded_enable,
        "latest_cycle": latest_cycle,
        "counts": {
            "events_read": len(events),
            "cycle_completed_events": len(cycle_events),
            "runtime_audit_events_total": len(runtime_events),
            "runtime_audit_events_latest_cycle": len(latest_runtime),
            "legacy_unlock_events_latest_cycle": len(latest_legacy),
            "scanned": scanned,
            "signals": _safe_int(latest_cycle.get("signals"), 0),
            "orders_submitted": cycle_orders,
            "positions_opened": _safe_int(latest_cycle.get("open_positions"), 0),
            "errors": cycle_errors,
            "no_signal": _safe_int(latest_cycle.get("no_signal"), 0),
        },
        "runtime_profile_audit": {
            "profile_name": settings.profile_name,
            "legacy_profile": settings.legacy_profile,
            "runtime_audit_present": runtime_audit_present,
            "runtime_coverage_ok": runtime_coverage_ok,
            "accepted_diagnostic_count": len(runtime_accepts),
            "rejected_count": len(runtime_rejects),
            "reject_reason_counts": _counts(reject_reasons),
            "structure_state_counts": _counts(e.get("runtime_structure_state") for e in latest_runtime),
            "map_score_ok_count": sum(1 for e in latest_runtime if bool(e.get("map_score_ok"))),
            "operator_state_ok_count": sum(1 for e in latest_runtime if bool(e.get("operator_state_ok"))),
            "routing_enabled_count": sum(1 for e in latest_runtime if bool(e.get("routing_enabled"))),
        },
        "legacy_unlock_audit": {
            "legacy_profile_counts": _counts(legacy_profiles),
            "legacy_reason_counts": _counts(legacy_reasons),
            "legacy_events_latest_cycle": len(latest_legacy),
            "legacy_and_guarded_separated": bool(latest_legacy and latest_runtime),
        },
        "safety_checks": safety_checks,
        "sample_runtime_events_tail": latest_runtime[-10:],
        "opens_orders": False,
        "orders_submitted": cycle_orders,
        "positions_opened": _safe_int(latest_cycle.get("open_positions"), 0),
        "paper_orders_enabled": bool(guarded_enable.get("paper_orders_enabled")),
        "paper_unlock_experiment_allowed": bool(guarded_enable.get("paper_unlock_experiment_allowed")),
        "manual_activation_allowed": bool(guarded_enable.get("manual_activation_allowed")),
        "operational_unlock_allowed": False,
        "automatic_activation_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "next_patch": next_patch,
    }


def write_runtime_audit_report(base: str | Path = "data", settings: RuntimePaperOrderAuditSettings | None = None) -> dict[str, Any]:
    settings = settings or RuntimePaperOrderAuditSettings.from_config()
    report = build_runtime_audit_report(base, settings)
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


# Backward-compatible explicit name for patch reports/tests.
def write_paper_unlock_runtime_audit_report(base: str | Path = "data", settings: RuntimePaperOrderAuditSettings | None = None) -> dict[str, Any]:
    return write_runtime_audit_report(base, settings)
