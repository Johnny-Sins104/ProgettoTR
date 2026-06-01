"""Prompt 29.4.4s-10i — LSR-v2 supervised paper submit preflight.

Builds the final disabled-by-default preflight boundary after the LSR-v2 paper
broker handoff dry-run.  It verifies that promotion, operator route, order
intent and broker-payload dry-run reports are coherent, then emits a diagnostic
submit-preflight event.  It never calls the broker, never submits an order and
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

PROMPT_ID = "29.4.4s-10i"
EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT"
REPORT_NAME = "lsr_v2_supervised_paper_submit_preflight_report.json"
JSONL_NAME = "lsr_v2_supervised_paper_submit_preflight.jsonl"

HANDOFF_EVENT_TYPE = "LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN"
HANDOFF_REPORT_NAME = "lsr_v2_paper_broker_handoff_dry_run_report.json"
HANDOFF_JSONL_NAME = "lsr_v2_paper_broker_handoff_dry_run.jsonl"
ORDER_INTENT_REPORT_NAME = "lsr_v2_order_intent_audit_report.json"
OPERATOR_ROUTE_REPORT_NAME = "lsr_v2_operator_route_audit_report.json"
PROMOTION_GATE_REPORT_NAME = "lsr_v2_promotion_gate_report.json"

READY_DECISION = "LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT_READY"
SUBMIT_DISABLED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_DISABLED"
HANDOFF_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_HANDOFF_MISSING"
OPERATOR_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPERATOR_CONFIRMATION_MISSING"
REPORTS_INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_PREFLIGHT_REPORTS_INCOMPLETE"
REJECT_DECISION = "REJECT_LSR_V2_SUBMIT_PREFLIGHT_FAILED"

PROMOTION_GATE_PASS_DECISION = "LSR_V2_PAPER_SUPERVISED_CANDIDATE"
OPERATOR_ROUTE_PASS_DECISION = "LSR_V2_OPERATOR_ROUTE_AUDIT_READY_DIAGNOSTIC"
ORDER_INTENT_PASS_DECISION = "LSR_V2_ORDER_INTENT_AUDIT_READY_DIAGNOSTIC"
HANDOFF_PASS_DECISION = "LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN_READY_DIAGNOSTIC"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in {"1", "true", "yes", "y", "on", "enabled"}:
            return True
        if stripped in {"0", "false", "no", "n", "off", "disabled", ""}:
            return False
    if value is None:
        return default
    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _event_cycle(event: Mapping[str, Any]) -> str:
    return str(event.get("cycle_id") or event.get("lsr_v2_runtime_cycle_id") or "")


def _handoff_key(event: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(event), sort_keys=True, default=str)
    except Exception:
        return "|".join([
            str(event.get("event_type") or ""),
            str(event.get("cycle_id") or ""),
            str(event.get("symbol") or ""),
            str(event.get("candidate_id") or ""),
        ])


def _dedupe_handoff_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        if row.get("event_type") != HANDOFF_EVENT_TYPE:
            continue
        key = _handoff_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


@dataclass(frozen=True)
class LSRV2SupervisedPaperSubmitPreflightSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    handoff_report_name: str = HANDOFF_REPORT_NAME
    handoff_jsonl_name: str = HANDOFF_JSONL_NAME
    order_intent_report_name: str = ORDER_INTENT_REPORT_NAME
    operator_route_report_name: str = OPERATOR_ROUTE_REPORT_NAME
    promotion_gate_report_name: str = PROMOTION_GATE_REPORT_NAME
    max_event_lines: int = 50000
    profile_name: str = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    selected_overlay_id: str = "combo_loss3_dd10_side_cap"
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    submit_enabled: bool = False
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_cycle_scoped_handoff_events(
    *,
    data_dir: str | Path,
    settings: LSRV2SupervisedPaperSubmitPreflightSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    settings = settings or LSRV2SupervisedPaperSubmitPreflightSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_handoff_events(_iter_jsonl_tail(base / settings.handoff_jsonl_name, max_lines=settings.max_event_lines))
    handoff_report = _read_json(base / settings.handoff_report_name)
    order_intent_report = _read_json(base / settings.order_intent_report_name)
    operator_route_report = _read_json(base / settings.operator_route_report_name)

    cycle_id = str(requested_cycle_id or "")
    if not cycle_id:
        cycle_id = str(handoff_report.get("cycle_id") or "")
    if not cycle_id:
        cycle_id = str(order_intent_report.get("cycle_id") or "")
    if not cycle_id:
        cycle_id = str(operator_route_report.get("cycle_id") or "")
    if not cycle_id:
        for row in reversed(rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break

    selected = [row for row in rows if not cycle_id or _event_cycle(row) == cycle_id]
    historical = [row for row in rows if _event_cycle(row) and _event_cycle(row) != cycle_id]
    metadata = {
        "prompt_id": PROMPT_ID,
        "event_source": "handoff_dry_run_jsonl",
        "strict_cycle_scope": True,
        "handoff_report_decision": handoff_report.get("decision"),
        "handoff_report_cycle_id": handoff_report.get("cycle_id"),
        "order_intent_report_cycle_id": order_intent_report.get("cycle_id"),
        "operator_route_report_cycle_id": operator_route_report.get("cycle_id"),
        "historical_handoff_events": len(historical),
        "historical_would_create_paper_order_events": sum(1 for row in historical if _safe_bool(row.get("would_create_paper_order"), False)),
    }
    return cycle_id, selected, metadata


def _report_prerequisites(
    *,
    data_dir: str | Path,
    settings: LSRV2SupervisedPaperSubmitPreflightSettings,
) -> dict[str, Any]:
    base = Path(data_dir)
    promotion = _read_json(base / settings.promotion_gate_report_name)
    operator = _read_json(base / settings.operator_route_report_name)
    intent = _read_json(base / settings.order_intent_report_name)
    handoff = _read_json(base / settings.handoff_report_name)

    return {
        "promotion_gate_report_present": bool(promotion),
        "operator_route_report_present": bool(operator),
        "order_intent_report_present": bool(intent),
        "handoff_report_present": bool(handoff),
        "promotion_gate_pass": str(promotion.get("decision") or "") == PROMOTION_GATE_PASS_DECISION and _safe_bool(promotion.get("paper_supervised_candidate"), False),
        "operator_route_pass": str(operator.get("decision") or "") == OPERATOR_ROUTE_PASS_DECISION,
        "operator_enable": _safe_bool(operator.get("operator_enable"), False),
        "operator_confirmation_ok": _safe_bool(operator.get("operator_confirmation_ok"), False),
        "operator_would_route_count": _safe_int(operator.get("would_route_count"), 0),
        "order_intent_pass": str(intent.get("decision") or "") == ORDER_INTENT_PASS_DECISION,
        "would_create_order_count": _safe_int(intent.get("would_create_order_count"), 0),
        "handoff_pass": str(handoff.get("decision") or "") == HANDOFF_PASS_DECISION,
        "payload_valid_count": _safe_int(handoff.get("payload_valid_count"), 0),
        "would_create_paper_order_count": _safe_int(handoff.get("would_create_paper_order_count"), 0),
        "handoff_broker_submit_called": _safe_bool(handoff.get("broker_submit_called"), False),
        "handoff_would_submit_count": _safe_int(handoff.get("would_submit_count"), 0) + _safe_int(handoff.get("would_submit_to_paper_broker_count"), 0),
        "handoff_orders_submitted": _safe_int(handoff.get("orders_submitted_by_lsr_v2_handoff"), 0),
        "handoff_positions_opened": _safe_int(handoff.get("positions_opened_by_lsr_v2_handoff"), 0),
    }


def build_lsr_v2_supervised_paper_submit_preflight_event(
    *,
    handoff_event: Mapping[str, Any],
    settings: LSRV2SupervisedPaperSubmitPreflightSettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperSubmitPreflightSettings()
    prereq = dict(prerequisites or {})
    h = dict(handoff_event or {})
    payload = h.get("payload") if isinstance(h.get("payload"), Mapping) else {}

    payload_valid = _safe_bool(h.get("payload_valid"), False)
    would_create_paper_order = _safe_bool(h.get("would_create_paper_order"), False)
    handoff_would_submit = _safe_bool(h.get("would_submit"), False) or _safe_bool(h.get("would_submit_to_paper_broker"), False)
    broker_submit_called = _safe_bool(h.get("broker_submit_called"), False)

    blockers: list[str] = []
    if not _safe_bool(prereq.get("promotion_gate_pass"), False):
        blockers.append("promotion_gate_not_passed")
    if not _safe_bool(prereq.get("operator_route_pass"), False):
        blockers.append("operator_route_not_passed")
    if not _safe_bool(prereq.get("operator_enable"), False):
        blockers.append("operator_disabled")
    if not _safe_bool(prereq.get("operator_confirmation_ok"), False):
        blockers.append("operator_confirmation_missing")
    if _safe_int(prereq.get("operator_would_route_count"), 0) <= 0:
        blockers.append("operator_would_route_missing")
    if not _safe_bool(prereq.get("order_intent_pass"), False):
        blockers.append("order_intent_not_passed")
    if _safe_int(prereq.get("would_create_order_count"), 0) <= 0:
        blockers.append("order_intent_would_create_missing")
    if not _safe_bool(prereq.get("handoff_pass"), False):
        blockers.append("handoff_not_passed")
    if not payload_valid:
        blockers.append("handoff_payload_invalid")
    if not would_create_paper_order:
        blockers.append("handoff_would_create_paper_order_false")
    if handoff_would_submit or broker_submit_called:
        blockers.append("handoff_submit_attempt_detected")
    if _safe_int(prereq.get("handoff_orders_submitted"), 0) != 0 or _safe_int(prereq.get("handoff_positions_opened"), 0) != 0:
        blockers.append("handoff_order_or_position_detected")
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    would_prepare_submit = bool(not blockers and would_create_paper_order and payload_valid and settings.fail_closed)
    # s-10i deliberately cannot submit.  A later patch must wire the actual
    # paper broker boundary under stronger operator controls.
    would_submit_to_paper_broker = False
    blocked_reason = "paper_submit_disabled_by_default" if would_prepare_submit else (blockers[0] if blockers else "paper_submit_disabled_by_default")

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": str(h.get("cycle_id") or payload.get("cycle_id") or ""),
        "symbol": str(h.get("symbol") or payload.get("symbol") or ""),
        "timeframe": str(h.get("timeframe") or payload.get("timeframe") or ""),
        "side": str(h.get("side") or payload.get("side") or ""),
        "order_type": str(h.get("order_type") or payload.get("order_type") or ""),
        "profile_name": str(h.get("profile_name") or payload.get("profile_name") or settings.profile_name),
        "selected_overlay_id": str(h.get("selected_overlay_id") or payload.get("selected_overlay_id") or settings.selected_overlay_id),
        "source": "lsr_v2_paper_broker_handoff_dry_run",
        "source_event_type": str(h.get("event_type") or HANDOFF_EVENT_TYPE),
        "candidate_id": str(h.get("candidate_id") or payload.get("candidate_id") or ""),
        "entry_price": _safe_float(h.get("entry_price", payload.get("entry_price")), 0.0),
        "stop_loss": _safe_float(h.get("stop_loss", payload.get("stop_loss")), 0.0),
        "take_profit": _safe_float(h.get("take_profit", payload.get("take_profit")), 0.0),
        "risk_per_trade_pct": _safe_float(h.get("risk_per_trade_pct", payload.get("risk_per_trade_pct")), 0.0025),
        "risk_amount": _safe_float(h.get("risk_amount", payload.get("risk_amount")), 0.0),
        "position_size": _safe_float(h.get("position_size", payload.get("position_size")), 0.0),
        "quantity": _safe_float(h.get("quantity", payload.get("quantity")), 0.0),
        "notional": _safe_float(h.get("notional", payload.get("notional")), 0.0),
        "max_positions": _safe_int(h.get("max_positions", payload.get("max_positions")), 1),
        "payload_valid": bool(payload_valid),
        "would_create_paper_order": bool(would_create_paper_order),
        "would_prepare_submit": bool(would_prepare_submit),
        "submit_enabled": False,
        "would_submit": False,
        "would_submit_to_paper_broker": bool(would_submit_to_paper_broker),
        "broker_submit_called": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "blocked_reason": blocked_reason,
        "blocked_reasons": blockers + (["paper_submit_disabled_by_default"] if would_prepare_submit else []),
        "promotion_gate_pass": _safe_bool(prereq.get("promotion_gate_pass"), False),
        "operator_enable": _safe_bool(prereq.get("operator_enable"), False),
        "operator_confirmation_ok": _safe_bool(prereq.get("operator_confirmation_ok"), False),
        "operator_route_pass": _safe_bool(prereq.get("operator_route_pass"), False),
        "order_intent_pass": _safe_bool(prereq.get("order_intent_pass"), False),
        "handoff_pass": _safe_bool(prereq.get("handoff_pass"), False),
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_lsr_v2_submit_preflight": 0,
        "positions_opened_by_lsr_v2_submit_preflight": 0,
        "promotion_ready": False,
        "dry_run_only": True,
        "audit_only": True,
        "submit_preflight_only": True,
    }


def build_lsr_v2_submit_preflight_events(
    handoff_events: Iterable[Mapping[str, Any]],
    *,
    settings: LSRV2SupervisedPaperSubmitPreflightSettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    settings = settings or LSRV2SupervisedPaperSubmitPreflightSettings()
    events: list[dict[str, Any]] = []
    for handoff in _dedupe_handoff_events(handoff_events):
        if not _safe_bool(handoff.get("would_create_paper_order"), False):
            continue
        events.append(build_lsr_v2_supervised_paper_submit_preflight_event(
            handoff_event=handoff,
            settings=settings,
            prerequisites=prerequisites,
        ))
    return events


def summarize_lsr_v2_submit_preflight(
    *,
    cycle_id: str,
    handoff_events: Iterable[Mapping[str, Any]],
    preflight_events: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2SupervisedPaperSubmitPreflightSettings | None = None,
    prerequisites: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperSubmitPreflightSettings(data_dir=str(data_dir))
    prereq = dict(prerequisites or {})
    metadata = dict(metadata or {})
    handoff_rows = _dedupe_handoff_events(handoff_events)
    rows = [dict(e) for e in preflight_events]
    prepare_rows = [e for e in rows if _safe_bool(e.get("would_prepare_submit"), False)]
    blockers: list[str] = []
    if not handoff_rows:
        blockers.append("handoff_missing")
    missing_reports = [
        key for key in ("promotion_gate_report_present", "operator_route_report_present", "order_intent_report_present", "handoff_report_present")
        if not _safe_bool(prereq.get(key), False)
    ]
    if missing_reports:
        blockers.append("upstream_reports_incomplete")
    if not _safe_bool(prereq.get("promotion_gate_pass"), False):
        blockers.append("promotion_gate_not_passed")
    if not _safe_bool(prereq.get("operator_enable"), False) or not _safe_bool(prereq.get("operator_confirmation_ok"), False):
        blockers.append("operator_confirmation_missing")
    if not _safe_bool(prereq.get("operator_route_pass"), False) or _safe_int(prereq.get("operator_would_route_count"), 0) <= 0:
        blockers.append("operator_route_not_ready")
    if not _safe_bool(prereq.get("order_intent_pass"), False) or _safe_int(prereq.get("would_create_order_count"), 0) <= 0:
        blockers.append("order_intent_not_ready")
    if not _safe_bool(prereq.get("handoff_pass"), False) or _safe_int(prereq.get("would_create_paper_order_count"), 0) <= 0:
        blockers.append("handoff_not_ready")
    safety_violation = any([
        _safe_bool(prereq.get("handoff_broker_submit_called"), False),
        _safe_int(prereq.get("handoff_would_submit_count"), 0) != 0,
        _safe_int(prereq.get("handoff_orders_submitted"), 0) != 0,
        _safe_int(prereq.get("handoff_positions_opened"), 0) != 0,
        any(
            _safe_bool(h.get("would_submit"), False)
            or _safe_bool(h.get("would_submit_to_paper_broker"), False)
            or _safe_bool(h.get("broker_submit_called"), False)
            or _safe_int(h.get("orders_submitted_by_lsr_v2_handoff"), 0) != 0
            or _safe_int(h.get("positions_opened_by_lsr_v2_handoff"), 0) != 0
            for h in handoff_rows
        ),
        any(_safe_bool(e.get("would_submit"), False) or _safe_bool(e.get("would_submit_to_paper_broker"), False) or _safe_bool(e.get("broker_submit_called"), False) for e in rows),
    ])
    if safety_violation:
        blockers.append("safety_violation_detected")

    if not handoff_rows:
        decision = HANDOFF_MISSING_DECISION
        status = "WARN"
    elif missing_reports:
        decision = REPORTS_INCOMPLETE_DECISION
        status = "WARN"
    elif safety_violation:
        decision = REJECT_DECISION
        status = "WARN"
    elif "operator_confirmation_missing" in blockers:
        decision = OPERATOR_MISSING_DECISION
        status = "WARN"
    elif prepare_rows and not blockers:
        decision = READY_DECISION
        status = "PASS"
    elif prepare_rows:
        decision = SUBMIT_DISABLED_DECISION
        status = "PASS"
    else:
        decision = REJECT_DECISION
        status = "WARN"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in prepare_rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in prepare_rows), 10)
    safety_checks = {
        "submit_enabled_false": True,
        "would_submit_zero": True,
        "would_submit_to_paper_broker_zero": True,
        "broker_submit_called_false": True,
        "orders_submitted_zero": True,
        "positions_opened_zero": True,
        "routing_disabled": True,
        "execution_disabled": True,
        "paper_order_submission_disabled": True,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
    }
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "SUPERVISED_PAPER_SUBMIT_PREFLIGHT",
            "SUBMIT_DISABLED_BY_DEFAULT",
            "BROKER_BOUNDARY_FAIL_CLOSED",
        ] + (["SUBMIT_PREFLIGHT_READY"] if decision == READY_DECISION else ["KEEP_DIAGNOSTIC"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "handoff_dry_run_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_handoff_events": _safe_int(metadata.get("historical_handoff_events"), 0),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "handoff_dry_run_events": len(handoff_rows),
        "submit_preflight_events": len(rows),
        "would_prepare_submit_count": len(prepare_rows),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called_count": 0,
        "payload_valid_count": sum(1 for e in rows if _safe_bool(e.get("payload_valid"), False)),
        "submit_enabled": False,
        "submit_enabled_default": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "promotion_gate_pass": _safe_bool(prereq.get("promotion_gate_pass"), False),
        "operator_enable": _safe_bool(prereq.get("operator_enable"), False),
        "operator_confirmation_ok": _safe_bool(prereq.get("operator_confirmation_ok"), False),
        "operator_route_pass": _safe_bool(prereq.get("operator_route_pass"), False),
        "operator_would_route_count": _safe_int(prereq.get("operator_would_route_count"), 0),
        "order_intent_pass": _safe_bool(prereq.get("order_intent_pass"), False),
        "would_create_order_count": _safe_int(prereq.get("would_create_order_count"), 0),
        "handoff_pass": _safe_bool(prereq.get("handoff_pass"), False),
        "would_create_paper_order_count": _safe_int(prereq.get("would_create_paper_order_count"), 0),
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "broker_submit_called": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_lsr_v2_submit_preflight": 0,
        "positions_opened_by_lsr_v2_submit_preflight": 0,
        "promotion_ready": False,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


def write_lsr_v2_submit_preflight_artifacts(
    *,
    data_dir: str | Path,
    cycle_id: str,
    handoff_events: Iterable[Mapping[str, Any]],
    settings: LSRV2SupervisedPaperSubmitPreflightSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperSubmitPreflightSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    prereq = _report_prerequisites(data_dir=base, settings=settings)
    selected_handoffs = [dict(e) for e in handoff_events if not cycle_id or _event_cycle(e) == cycle_id]
    preflight_events = build_lsr_v2_submit_preflight_events(selected_handoffs, settings=settings, prerequisites=prereq)
    _write_jsonl_replace(base / settings.jsonl_name, preflight_events)
    report = summarize_lsr_v2_submit_preflight(
        cycle_id=cycle_id,
        handoff_events=selected_handoffs,
        preflight_events=preflight_events,
        data_dir=base,
        settings=settings,
        prerequisites=prereq,
        metadata=metadata,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


def build_lsr_v2_submit_preflight_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SupervisedPaperSubmitPreflightSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperSubmitPreflightSettings(data_dir=str(data_dir))
    selected_cycle_id, handoff_events, metadata = select_cycle_scoped_handoff_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    return write_lsr_v2_submit_preflight_artifacts(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        handoff_events=handoff_events,
        settings=settings,
        metadata=metadata,
    )
