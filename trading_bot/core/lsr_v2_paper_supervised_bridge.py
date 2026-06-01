"""Prompt 29.4.4s-10 — LSR-v2 paper-supervised bridge scaffold / fail-closed runtime audit.

This module connects the LSR-v2 paper-supervised-candidate decision to a
runtime-style bridge audit.  It is intentionally fail-closed: it can emit
``LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT`` diagnostics and a report, but it never
routes to a broker, never submits a paper order, never opens a position, and
never mutates paper state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore
import json
import os

try:  # pragma: no cover - available in full project/runtime
    from config import Config  # type: ignore
except Exception:  # pragma: no cover - tests can run without project config
    class Config:  # type: ignore
        pass

try:
    from .lsr_v2_promotion_gate import PASS_DECISION as PROMOTION_PASS_DECISION
    from .lsr_v2_promotion_gate import REPORT_NAME as PROMOTION_GATE_REPORT_NAME
    from .lsr_v2_combined_risk_overlay import LOCKED_PROFILE_NAME, LOCKED_VARIANT_ID
    from .lsr_v2_selected_overlay_validation import SELECTED_OVERLAY_ID
except Exception:  # pragma: no cover - stripped contexts
    PROMOTION_PASS_DECISION = "LSR_V2_PAPER_SUPERVISED_CANDIDATE"
    PROMOTION_GATE_REPORT_NAME = "lsr_v2_promotion_gate_report.json"
    LOCKED_PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    LOCKED_VARIANT_ID = "retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24"
    SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"

PROMPT_ID = "29.4.4s-10f"
EVENT_TYPE = "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT"
REPORT_NAME = "lsr_v2_paper_supervised_bridge_report.json"
JSONL_NAME = "lsr_v2_paper_supervised_bridge_audit.jsonl"
CANDIDATE_AUDIT_JSONL_NAME = "lsr_v2_candidate_audit.jsonl"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"

READY_DECISION = "LSR_V2_PAPER_SUPERVISED_BRIDGE_READY_DIAGNOSTIC"
NO_CANDIDATES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_NO_CANDIDATES"
PROMOTION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_PROMOTION_GATE_MISSING"
FAIL_CLOSED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_FAIL_CLOSED"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_ERROR"

CONFIRMATION_PHRASE = "I_UNDERSTAND_PAPER_ONLY"
LEGACY_CONFIRMATION_PHRASE = "I_UNDERSTAND_LSR_V2_PAPER_SUPERVISED_ONLY"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


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
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _env_or_attr(cfg: Any, *names: str, default: Any = None) -> Any:
    """Read operator/config settings with environment variable precedence.

    s-10f introduces short operator env aliases while keeping the previous
    bridge-prefixed Config attributes backward compatible.
    """
    for name in names:
        if name in os.environ:
            return os.environ.get(name)
    for name in names:
        if hasattr(cfg, name):
            return getattr(cfg, name)
    return default


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"_non_object_json": payload}
    except Exception as exc:
        return {"_read_error": str(exc)}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _write_jsonl(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _counts(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value if value not in {None, ""} else "-")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _nested_get(mapping: Mapping[str, Any], *path: str, default: Any = None) -> Any:
    cur: Any = mapping
    for key in path:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


@dataclass(frozen=True)
class LSRV2PaperSupervisedBridgeSettings:
    enabled: bool = True
    emit_bridge_events: bool = True
    fail_closed: bool = True
    operator_enable: bool = False
    operator_confirmation: str = ""
    confirmation_phrase: str = CONFIRMATION_PHRASE
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    bridge_jsonl_name: str = JSONL_NAME
    candidate_jsonl_name: str = CANDIDATE_AUDIT_JSONL_NAME
    promotion_gate_report_name: str = PROMOTION_GATE_REPORT_NAME
    events_name: str = "paper_events.jsonl"
    max_event_lines: int = 50000
    max_candidate_events: int = 500
    profile_name: str = LOCKED_PROFILE_NAME
    locked_variant_id: str = LOCKED_VARIANT_ID
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    event_type: str = EVENT_TYPE

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "LSRV2PaperSupervisedBridgeSettings":
        return cls(
            enabled=_safe_bool(_env_or_attr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_ENABLED", default=True), True),
            emit_bridge_events=_safe_bool(_env_or_attr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_EMIT_EVENTS", default=True), True),
            fail_closed=_safe_bool(_env_or_attr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_FAIL_CLOSED", default=True), True),
            operator_enable=_safe_bool(_env_or_attr(cfg, "LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE", "LSR_V2_PAPER_SUPERVISED_BRIDGE_OPERATOR_ENABLE", default=False), False),
            operator_confirmation=str(_env_or_attr(cfg, "LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION", "LSR_V2_PAPER_SUPERVISED_BRIDGE_CONFIRM", default="") or ""),
            confirmation_phrase=str(_env_or_attr(cfg, "LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION_PHRASE", "LSR_V2_PAPER_SUPERVISED_BRIDGE_CONFIRM_PHRASE", default=CONFIRMATION_PHRASE) or CONFIRMATION_PHRASE),
            data_dir=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_DATA_DIR", "data") or "data"),
            report_name=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            bridge_jsonl_name=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_JSONL_NAME", JSONL_NAME) or JSONL_NAME),
            candidate_jsonl_name=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_CANDIDATE_JSONL_NAME", CANDIDATE_AUDIT_JSONL_NAME) or CANDIDATE_AUDIT_JSONL_NAME),
            promotion_gate_report_name=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_PROMOTION_REPORT_NAME", PROMOTION_GATE_REPORT_NAME) or PROMOTION_GATE_REPORT_NAME),
            events_name=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            max_event_lines=max(100, _safe_int(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_MAX_EVENT_LINES", 50000), 50000)),
            max_candidate_events=max(1, _safe_int(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_MAX_CANDIDATE_EVENTS", 500), 500)),
            profile_name=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_PROFILE_NAME", LOCKED_PROFILE_NAME) or LOCKED_PROFILE_NAME),
            locked_variant_id=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_VARIANT_ID", LOCKED_VARIANT_ID) or LOCKED_VARIANT_ID),
            selected_overlay_id=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_OVERLAY_ID", SELECTED_OVERLAY_ID) or SELECTED_OVERLAY_ID),
            event_type=str(getattr(cfg, "LSR_V2_PAPER_SUPERVISED_BRIDGE_EVENT_TYPE", EVENT_TYPE) or EVENT_TYPE),
        )

    @property
    def operator_confirmation_ok(self) -> bool:
        allowed = {str(self.confirmation_phrase or CONFIRMATION_PHRASE), CONFIRMATION_PHRASE, LEGACY_CONFIRMATION_PHRASE}
        return bool(str(self.operator_confirmation or "") in allowed)

    @property
    def operator_authorized(self) -> bool:
        return bool(self.operator_enable and self.operator_confirmation_ok)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["operator_confirmation_ok"] = self.operator_confirmation_ok
        payload["operator_authorized"] = self.operator_authorized
        payload["operator_confirmation"] = "***" if self.operator_confirmation else ""
        return payload


def promotion_gate_passed(report: Mapping[str, Any]) -> bool:
    return bool(
        report.get("status") == "PASS"
        and report.get("decision") == PROMOTION_PASS_DECISION
        and _safe_bool(report.get("paper_supervised_candidate"), False)
        and _safe_bool(report.get("paper_supervised_readiness_preflight_pass"), False)
        and not _safe_bool(report.get("execution_enabled"), False)
        and not _safe_bool(report.get("routing_enabled"), False)
        and not _safe_bool(report.get("paper_order_submission_enabled"), False)
        and not _safe_bool(report.get("live_enabled"), False)
        and not _safe_bool(report.get("testnet_enabled"), False)
        and not _safe_bool(report.get("exchange_broker_enabled"), False)
    )


def _candidate_ready(candidate: Mapping[str, Any]) -> bool:
    quality_grade = str(_nested_get(candidate, "quality", "grade", default="") or "")
    return bool(
        _safe_bool(candidate.get("candidate_ready"), False)
        and str(candidate.get("event_type") or "") in {"LSR_V2_CANDIDATE_AUDIT", "LSR_V2_RUNTIME_CANDIDATE_AUDIT"}
        and str(candidate.get("archetype") or "") in {"LIQUIDITY_SWEEP_REVERSAL_V2", ""}
        and quality_grade in {"A", "", "QUALITY_A"}
    )


def _candidate_prices(candidate: Mapping[str, Any]) -> tuple[float, float, float]:
    levels = candidate.get("levels") if isinstance(candidate.get("levels"), Mapping) else {}
    return (
        _safe_float(levels.get("entry_price"), 0.0),
        _safe_float(levels.get("stop_loss"), 0.0),
        _safe_float(levels.get("take_profit"), 0.0),
    )


def build_lsr_v2_paper_supervised_bridge_event(
    *,
    settings: LSRV2PaperSupervisedBridgeSettings | None = None,
    promotion_gate_report: Mapping[str, Any] | None = None,
    candidate_event: Mapping[str, Any] | None = None,
    cycle_id: str = "",
    symbol: str = "",
    mode: str = "paper",
    open_positions_count: int = 0,
) -> dict[str, Any]:
    """Build one fail-closed bridge audit event.

    ``would_submit`` is intentionally hard-coded to ``False``.  The event can
    only describe whether the candidate would be eligible for supervised review.
    """
    settings = settings or LSRV2PaperSupervisedBridgeSettings.from_config()
    promotion = dict(promotion_gate_report or {})
    candidate = dict(candidate_event or {})
    candidate_ready = _candidate_ready(candidate)
    promotion_ok = promotion_gate_passed(promotion)
    paper_supervised_candidate = _safe_bool(promotion.get("paper_supervised_candidate"), False)
    paper_mode_ok = str(mode or candidate.get("mode") or "paper").lower() == "paper"
    entry_price, stop_loss, take_profit = _candidate_prices(candidate)
    price_fields_ok = bool(entry_price > 0.0 and stop_loss > 0.0 and take_profit > 0.0)
    side = str(candidate.get("side") or "").upper()
    side_ok = side in {"BUY", "SELL"}
    symbol_out = str(symbol or candidate.get("symbol") or "")

    live_enabled = _safe_bool(promotion.get("live_enabled"), False)
    testnet_enabled = _safe_bool(promotion.get("testnet_enabled"), False)
    exchange_broker_enabled = _safe_bool(promotion.get("exchange_broker_enabled"), False)
    broker_submit_called = _safe_bool(promotion.get("broker_submit_called"), False)
    safety_ok = bool(not live_enabled and not testnet_enabled and not exchange_broker_enabled and not broker_submit_called)

    blocked_reasons: list[str] = []
    if not settings.enabled:
        blocked_reasons.append("lsr_v2_bridge_disabled")
    if not promotion:
        blocked_reasons.append("promotion_gate_missing")
    elif not promotion_ok:
        blocked_reasons.append("promotion_gate_not_pass")
    if not paper_supervised_candidate:
        blocked_reasons.append("paper_supervised_candidate_false")
    if not settings.operator_enable:
        blocked_reasons.append("operator_disabled")
    if not settings.operator_confirmation_ok:
        blocked_reasons.append("operator_confirmation_missing")
    if not candidate:
        blocked_reasons.append("no_lsr_v2_candidate")
    elif not candidate_ready:
        blocked_reasons.append("lsr_v2_candidate_not_ready")
    if not paper_mode_ok:
        blocked_reasons.append("mode_not_paper")
    if not side_ok:
        blocked_reasons.append("side_invalid")
    if not price_fields_ok:
        blocked_reasons.append("price_fields_invalid")
    if int(open_positions_count or 0) > 0:
        blocked_reasons.append("open_positions_not_zero")
    if not safety_ok:
        blocked_reasons.append("safety_invariant_failed")
    if not settings.fail_closed:
        blocked_reasons.append("fail_closed_setting_disabled")

    would_route = bool(
        settings.enabled
        and promotion_ok
        and paper_supervised_candidate
        and settings.operator_authorized
        and candidate_ready
        and paper_mode_ok
        and side_ok
        and price_fields_ok
        and int(open_positions_count or 0) == 0
        and safety_ok
    )
    # Deliberately never true in this scaffold.
    would_submit = False
    blocked_reason = "paper_supervised_bridge_fail_closed" if would_route else (blocked_reasons[0] if blocked_reasons else "paper_supervised_bridge_fail_closed")
    if would_route and "paper_supervised_bridge_fail_closed" not in blocked_reasons:
        blocked_reasons.append("paper_supervised_bridge_fail_closed")

    return {
        "event_type": settings.event_type,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": str(cycle_id or candidate.get("cycle_id") or ""),
        "symbol": symbol_out,
        "timeframe": str(candidate.get("timeframe") or ""),
        "mode": "paper" if paper_mode_ok else str(mode or ""),
        "profile_name": settings.profile_name,
        "locked_variant_id": settings.locked_variant_id,
        "selected_overlay_id": settings.selected_overlay_id,
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "candidate_event_type": str(candidate.get("event_type") or ""),
        "candidate_ready": candidate_ready,
        "quality_grade": _nested_get(candidate, "quality", "grade", default=None),
        "side": side,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "paper_supervised_candidate": paper_supervised_candidate,
        "promotion_gate_pass": promotion_ok,
        "promotion_gate_decision": promotion.get("decision"),
        "operator_enable": bool(settings.operator_enable),
        "operator_confirmation_ok": bool(settings.operator_confirmation_ok),
        "operator_authorized": bool(settings.operator_authorized),
        "fail_closed": bool(settings.fail_closed),
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "would_route": would_route,
        "would_submit": would_submit,
        "blocked_reason": blocked_reason,
        "blocked_reasons": blocked_reasons,
        "open_positions_count": int(open_positions_count or 0),
        "orders_submitted_by_lsr_v2_bridge": 0,
        "positions_opened_by_lsr_v2_bridge": 0,
        "broker_submit_called": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "audit_only": True,
    }


def _load_candidate_events(base_path: Path, settings: LSRV2PaperSupervisedBridgeSettings) -> list[dict[str, Any]]:
    rows = _iter_jsonl_tail(base_path / settings.candidate_jsonl_name, max_lines=settings.max_event_lines)
    candidates = [r for r in rows if str(r.get("event_type") or "") == "LSR_V2_CANDIDATE_AUDIT"]
    candidates = candidates[-settings.max_candidate_events :]
    return candidates


def _load_latest_cycle_id(base_path: Path, settings: LSRV2PaperSupervisedBridgeSettings) -> str:
    rows = _iter_jsonl_tail(base_path / settings.events_name, max_lines=settings.max_event_lines)
    cycle_events = [r for r in rows if str(r.get("event_type") or "") == CYCLE_COMPLETED_EVENT_TYPE]
    if cycle_events:
        return str(cycle_events[-1].get("cycle_id") or "")
    return ""


def build_lsr_v2_paper_supervised_bridge_report(
    base: str | Path = "data",
    settings: LSRV2PaperSupervisedBridgeSettings | None = None,
    *,
    write_bridge_jsonl: bool = True,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperSupervisedBridgeSettings.from_config()
    base_path = Path(base)
    promotion_path = base_path / settings.promotion_gate_report_name
    promotion = _read_json(promotion_path)
    promotion_ok = promotion_gate_passed(promotion)
    candidate_events = _load_candidate_events(base_path, settings)
    ready_candidates = [c for c in candidate_events if _candidate_ready(c)]
    latest_cycle_id = _load_latest_cycle_id(base_path, settings)

    bridge_events = [
        build_lsr_v2_paper_supervised_bridge_event(
            settings=settings,
            promotion_gate_report=promotion,
            candidate_event=c,
            cycle_id=latest_cycle_id,
            symbol=str(c.get("symbol") or ""),
            mode="paper",
            open_positions_count=0,
        )
        for c in ready_candidates
    ]
    if write_bridge_jsonl:
        _write_jsonl(base_path / settings.bridge_jsonl_name, bridge_events)

    would_route_events = [e for e in bridge_events if _safe_bool(e.get("would_route"), False)]
    would_submit_events = [e for e in bridge_events if _safe_bool(e.get("would_submit"), False)]
    blocked_reasons: list[Any] = []
    for event in bridge_events:
        reasons = event.get("blocked_reasons") if isinstance(event.get("blocked_reasons"), list) else [event.get("blocked_reason")]
        blocked_reasons.extend([r for r in reasons if r])

    blockers: list[str] = []
    if not promotion:
        blockers.append("promotion_gate_missing")
    elif not promotion_ok:
        blockers.append("promotion_gate_not_pass")
    if not candidate_events:
        blockers.append("no_lsr_v2_candidate_events")
    elif not ready_candidates:
        blockers.append("no_lsr_v2_candidate_ready_events")
    if would_submit_events:
        blockers.append("would_submit_true_safety_violation")
    if any(_safe_bool(e.get("broker_submit_called"), False) for e in bridge_events):
        blockers.append("broker_submit_called_safety_violation")

    safety_checks = {
        "promotion_gate_pass": bool(promotion_ok),
        "paper_supervised_candidate": _safe_bool(promotion.get("paper_supervised_candidate"), False),
        "bridge_fail_closed": bool(settings.fail_closed),
        "routing_disabled": True,
        "execution_disabled": True,
        "paper_order_submission_disabled": True,
        "would_submit_zero": len(would_submit_events) == 0,
        "broker_submit_called_false": not any(_safe_bool(e.get("broker_submit_called"), False) for e in bridge_events),
        "orders_submitted_zero": sum(_safe_int(e.get("orders_submitted_by_lsr_v2_bridge"), 0) for e in bridge_events) == 0,
        "positions_opened_zero": sum(_safe_int(e.get("positions_opened_by_lsr_v2_bridge"), 0) for e in bridge_events) == 0,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
    }
    safety_ok = all(bool(v) for v in safety_checks.values())

    if not promotion:
        decision = PROMOTION_MISSING_DECISION
    elif not candidate_events or not ready_candidates:
        decision = NO_CANDIDATES_DECISION
    elif safety_ok:
        decision = READY_DECISION
    else:
        decision = FAIL_CLOSED_DECISION
    status = "PASS" if decision == READY_DECISION else "WARN"
    labels: list[str] = []
    if decision == READY_DECISION:
        labels = ["BRIDGE_READY_DIAGNOSTIC", "FAIL_CLOSED", "EXECUTION_STILL_DISABLED"]
        if would_route_events:
            labels.append("WOULD_ROUTE_PRESENT")
        else:
            labels.append("NO_OPERATOR_ROUTE_DEFAULT")
    else:
        labels = ["BRIDGE_KEEP_DIAGNOSTIC", "FAIL_CLOSED"]

    report: dict[str, Any] = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "latest_cycle_id": latest_cycle_id,
        "profile_name": settings.profile_name,
        "locked_variant_id": settings.locked_variant_id,
        "selected_overlay_id": settings.selected_overlay_id,
        "promotion_gate_report": str(promotion_path),
        "promotion_gate_decision": promotion.get("decision"),
        "promotion_gate_pass": promotion_ok,
        "paper_supervised_candidate": _safe_bool(promotion.get("paper_supervised_candidate"), False),
        "operator_enable": bool(settings.operator_enable),
        "operator_confirmation_ok": bool(settings.operator_confirmation_ok),
        "operator_authorized": bool(settings.operator_authorized),
        "candidate_events": len(candidate_events),
        "candidate_ready_events": len(ready_candidates),
        "bridge_events": len(bridge_events),
        "would_route_count": len(would_route_events),
        "would_submit_count": len(would_submit_events),
        "blocked_reason_counts": _counts(blocked_reasons),
        "safety_checks": safety_checks,
        "safety_ok": safety_ok,
        "execution_enabled": False,
        "routing_enabled": False,
        "paper_order_submission_enabled": False,
        "broker_submit_called": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "orders_submitted_by_lsr_v2_bridge": 0,
        "positions_opened_by_lsr_v2_bridge": 0,
        "promotion_ready": False,
        "paper_supervised_bridge_ready": decision == READY_DECISION,
        "audit_only": True,
        "bridge_jsonl": str(base_path / settings.bridge_jsonl_name),
        "report": str(base_path / settings.report_name),
        "settings": settings.to_dict(),
        "sample_bridge_events_tail": bridge_events[-10:],
    }
    return report


def prepare_lsr_v2_runtime_bridge_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return a paper-runtime-safe copy of one LSR-v2 bridge audit event.

    The runtime copy preserves the bridge diagnostics but force-pins every
    execution/routing/broker field to fail-closed values.
    """
    payload = dict(event)
    payload["runtime_integration_prompt_id"] = "29.4.4s-10f"
    payload["runtime_bridge_integration"] = True
    payload["would_submit"] = False
    payload["routing_enabled"] = False
    payload["execution_enabled"] = False
    payload["paper_order_submission_enabled"] = False
    payload["broker_submit_called"] = False
    payload["live_enabled"] = False
    payload["testnet_enabled"] = False
    payload["exchange_broker_enabled"] = False
    payload["orders_submitted_by_lsr_v2_runtime_bridge"] = 0
    payload["positions_opened_by_lsr_v2_runtime_bridge"] = 0
    payload["orders_submitted_by_lsr_v2_bridge"] = 0
    payload["positions_opened_by_lsr_v2_bridge"] = 0
    return payload


def load_lsr_v2_paper_supervised_bridge_events(
    base: str | Path = "data",
    settings: LSRV2PaperSupervisedBridgeSettings | None = None,
) -> list[dict[str, Any]]:
    """Load the latest generated LSR-v2 bridge audit events.

    This is used by the paper runtime integration to mirror the fail-closed
    bridge diagnostics into ``paper_events.jsonl`` after the report has been
    generated.  It is read-only and never submits or routes orders.
    """
    settings = settings or LSRV2PaperSupervisedBridgeSettings.from_config()
    base_path = Path(base)
    rows = _iter_jsonl_tail(base_path / settings.bridge_jsonl_name, max_lines=settings.max_candidate_events)
    return [r for r in rows if str(r.get("event_type") or "") == settings.event_type]


def write_lsr_v2_paper_supervised_bridge_report(
    base: str | Path = "data",
    settings: LSRV2PaperSupervisedBridgeSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperSupervisedBridgeSettings.from_config()
    try:
        report = build_lsr_v2_paper_supervised_bridge_report(base, settings, write_bridge_jsonl=bool(settings.emit_bridge_events))
    except Exception as exc:  # pragma: no cover - defensive safety net
        base_path = Path(base)
        report = {
            "prompt_id": PROMPT_ID,
            "generated_at": utc_now_iso(),
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": ["BRIDGE_ERROR", "FAIL_CLOSED"],
            "blockers": [f"bridge_error:{type(exc).__name__}:{exc}"],
            "paper_supervised_bridge_ready": False,
            "promotion_ready": False,
            "execution_enabled": False,
            "routing_enabled": False,
            "paper_order_submission_enabled": False,
            "broker_submit_called": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "orders_submitted_by_lsr_v2_bridge": 0,
            "positions_opened_by_lsr_v2_bridge": 0,
            "audit_only": True,
            "report": str(base_path / (settings.report_name if settings else REPORT_NAME)),
        }
    _write_json(Path(base) / (settings.report_name if settings else REPORT_NAME), report)
    return report
