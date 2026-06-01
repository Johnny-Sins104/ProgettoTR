"""Prompt 29.4.4s-10j — LSR-v2 first supervised paper submit boundary.

This module is the single-order supervised paper submit boundary after the
LSR-v2 submit preflight.  It remains disabled by default and requires explicit
operator arming plus confirmation before it can mark a payload as submit-ready.

The standalone runner never calls a real broker.  Actual submission is possible
only through the ``paper_submitter`` callable passed explicitly by integration
code/tests.  This keeps the patch fail-closed while defining the final boundary
that a later supervised runtime handoff can wire to a paper-only broker.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore
import json
import os

PROMPT_ID = "29.4.4s-10j"
EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_BOUNDARY"
REPORT_NAME = "lsr_v2_supervised_paper_submit_report.json"
JSONL_NAME = "lsr_v2_supervised_paper_submit.jsonl"

PREFLIGHT_EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT"
PREFLIGHT_REPORT_NAME = "lsr_v2_supervised_paper_submit_preflight_report.json"
PREFLIGHT_JSONL_NAME = "lsr_v2_supervised_paper_submit_preflight.jsonl"

READY_ARMED_DECISION = "LSR_V2_SINGLE_PAPER_SUBMIT_READY_ARMED"
EXECUTED_DECISION = "LSR_V2_SINGLE_PAPER_SUBMIT_EXECUTED"
NOT_ARMED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_NOT_ARMED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_CONFIRMATION_MISSING"
PREFLIGHT_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_PREFLIGHT_MISSING"
CAP_EXCEEDED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_MAX_ORDER_CAP_BLOCKED"
NO_SUBMITTER_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMITTER_NOT_WIRED"
REJECT_DECISION = "REJECT_LSR_V2_SUBMIT_SAFETY_FAILED"

REQUIRED_ARM_VALUE = "1"
REQUIRED_CONFIRMATION = "I_UNDERSTAND_SINGLE_PAPER_ORDER"

PaperSubmitter = Callable[[Mapping[str, Any]], Mapping[str, Any] | bool | None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "armed"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null"}:
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


def _preflight_key(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("cycle_id") or ""),
        str(event.get("symbol") or ""),
        str(event.get("candidate_id") or ""),
        str(event.get("timeframe") or ""),
    )


def _dedupe_preflight_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        if row.get("event_type") != PREFLIGHT_EVENT_TYPE:
            continue
        key = _preflight_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


@dataclass(frozen=True)
class LSRV2SupervisedPaperSubmitSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    preflight_report_name: str = PREFLIGHT_REPORT_NAME
    preflight_jsonl_name: str = PREFLIGHT_JSONL_NAME
    max_event_lines: int = 50000
    profile_name: str = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
    selected_overlay_id: str = "combo_loss3_dd10_side_cap"
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    required_arm_value: str = REQUIRED_ARM_VALUE
    required_confirmation: str = REQUIRED_CONFIRMATION
    submit_arm: str = ""
    submit_confirmation: str = ""
    max_orders: int = 1
    mode: str = "paper"
    fail_closed: bool = True
    # The CLI uses dry_run_submitter_only=True and never supplies a submitter.
    # Integration code may pass a paper_submitter explicitly for a supervised
    # paper-only order in a future patch.
    dry_run_submitter_only: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2SupervisedPaperSubmitSettings":
        max_orders = _safe_int(os.getenv("LSR_V2_PAPER_SUBMIT_MAX_ORDERS"), 1)
        if max_orders <= 0:
            max_orders = 1
        return cls(
            data_dir=data_dir,
            submit_arm=str(os.getenv("LSR_V2_PAPER_SUBMIT_ARM") or ""),
            submit_confirmation=str(os.getenv("LSR_V2_PAPER_SUBMIT_CONFIRMATION") or ""),
            max_orders=max_orders,
            mode=str(os.getenv("LSR_V2_PAPER_SUBMIT_MODE") or "paper"),
        )

    @property
    def submit_armed(self) -> bool:
        return str(self.submit_arm).strip() == self.required_arm_value

    @property
    def submit_confirmation_ok(self) -> bool:
        return str(self.submit_confirmation).strip() == self.required_confirmation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_cycle_scoped_submit_preflight_events(
    *,
    data_dir: str | Path,
    settings: LSRV2SupervisedPaperSubmitSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    settings = settings or LSRV2SupervisedPaperSubmitSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_preflight_events(_iter_jsonl_tail(base / settings.preflight_jsonl_name, max_lines=settings.max_event_lines))
    preflight_report = _read_json(base / settings.preflight_report_name)
    cycle_id = str(requested_cycle_id or preflight_report.get("cycle_id") or "")
    if not cycle_id:
        for row in reversed(rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break

    selected = [row for row in rows if not cycle_id or _event_cycle(row) == cycle_id]
    historical = [row for row in rows if _event_cycle(row) and _event_cycle(row) != cycle_id]
    metadata = {
        "prompt_id": PROMPT_ID,
        "event_source": "submit_preflight_jsonl",
        "strict_cycle_scope": True,
        "preflight_report_decision": preflight_report.get("decision"),
        "preflight_report_cycle_id": preflight_report.get("cycle_id"),
        "historical_submit_preflight_events": len(historical),
        "historical_prepare_submit_events": sum(1 for row in historical if _safe_bool(row.get("would_prepare_submit"), False)),
    }
    return cycle_id, selected, metadata


def _payload_from_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    payload = preflight.get("payload") if isinstance(preflight.get("payload"), Mapping) else {}
    return {
        "source": "lsr_v2_supervised_paper_submit_preflight",
        "profile_name": str(preflight.get("profile_name") or payload.get("profile_name") or "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"),
        "selected_overlay_id": str(preflight.get("selected_overlay_id") or payload.get("selected_overlay_id") or "combo_loss3_dd10_side_cap"),
        "cycle_id": str(preflight.get("cycle_id") or payload.get("cycle_id") or ""),
        "symbol": str(preflight.get("symbol") or payload.get("symbol") or ""),
        "timeframe": str(preflight.get("timeframe") or payload.get("timeframe") or ""),
        "side": str(preflight.get("side") or payload.get("side") or "").upper(),
        "order_type": str(preflight.get("order_type") or payload.get("order_type") or "LIMIT").upper(),
        "entry_price": _safe_float(preflight.get("entry_price", payload.get("entry_price")), 0.0),
        "stop_loss": _safe_float(preflight.get("stop_loss", payload.get("stop_loss")), 0.0),
        "take_profit": _safe_float(preflight.get("take_profit", payload.get("take_profit")), 0.0),
        "risk_per_trade_pct": _safe_float(preflight.get("risk_per_trade_pct", payload.get("risk_per_trade_pct")), 0.0025),
        "risk_amount": _safe_float(preflight.get("risk_amount", payload.get("risk_amount")), 0.0),
        "quantity": _safe_float(preflight.get("quantity", payload.get("quantity")), _safe_float(preflight.get("position_size", payload.get("position_size")), 0.0)),
        "position_size": _safe_float(preflight.get("position_size", payload.get("position_size")), _safe_float(preflight.get("quantity", payload.get("quantity")), 0.0)),
        "notional": _safe_float(preflight.get("notional", payload.get("notional")), 0.0),
        "max_positions": _safe_int(preflight.get("max_positions", payload.get("max_positions")), 1),
        "candidate_id": str(preflight.get("candidate_id") or payload.get("candidate_id") or ""),
        "paper_broker_adapter": str(preflight.get("paper_broker_adapter") or payload.get("paper_broker_adapter") or "PaperBrokerAdapter"),
    }


def _payload_valid(payload: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not payload.get("symbol"):
        reasons.append("symbol_missing")
    side = str(payload.get("side") or "")
    if side not in {"BUY", "SELL"}:
        reasons.append("side_invalid")
    if _safe_float(payload.get("entry_price"), 0.0) <= 0:
        reasons.append("entry_price_invalid")
    if _safe_float(payload.get("stop_loss"), 0.0) <= 0:
        reasons.append("stop_loss_invalid")
    if _safe_float(payload.get("take_profit"), 0.0) <= 0:
        reasons.append("take_profit_invalid")
    if _safe_float(payload.get("quantity"), 0.0) <= 0:
        reasons.append("quantity_invalid")
    if _safe_float(payload.get("risk_amount"), 0.0) <= 0:
        reasons.append("risk_amount_invalid")
    if _safe_float(payload.get("notional"), 0.0) <= 0:
        reasons.append("notional_invalid")
    entry = _safe_float(payload.get("entry_price"), 0.0)
    stop = _safe_float(payload.get("stop_loss"), 0.0)
    take = _safe_float(payload.get("take_profit"), 0.0)
    if side == "BUY" and stop >= entry:
        reasons.append("buy_stop_not_below_entry")
    if side == "BUY" and take <= entry:
        reasons.append("buy_take_profit_not_above_entry")
    if side == "SELL" and stop <= entry:
        reasons.append("sell_stop_not_above_entry")
    if side == "SELL" and take >= entry:
        reasons.append("sell_take_profit_not_below_entry")
    return not reasons, reasons


def _preflight_safety_ok(preflight: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not _safe_bool(preflight.get("would_prepare_submit"), False):
        reasons.append("would_prepare_submit_false")
    if _safe_bool(preflight.get("would_submit"), False) or _safe_bool(preflight.get("would_submit_to_paper_broker"), False):
        reasons.append("upstream_would_submit_detected")
    if _safe_bool(preflight.get("broker_submit_called"), False):
        reasons.append("upstream_broker_submit_called")
    if _safe_int(preflight.get("orders_submitted_by_lsr_v2_submit_preflight"), 0) != 0:
        reasons.append("upstream_orders_submitted_nonzero")
    if _safe_int(preflight.get("positions_opened_by_lsr_v2_submit_preflight"), 0) != 0:
        reasons.append("upstream_positions_opened_nonzero")
    for field in ("live_enabled", "testnet_enabled", "exchange_broker_enabled", "operational_unlock_allowed"):
        if _safe_bool(preflight.get(field), False):
            reasons.append(f"{field}_true")
    return not reasons, reasons


def build_lsr_v2_supervised_paper_submit_event(
    *,
    preflight_event: Mapping[str, Any],
    settings: LSRV2SupervisedPaperSubmitSettings | None = None,
    index: int = 0,
    paper_submitter: PaperSubmitter | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperSubmitSettings()
    pre = dict(preflight_event or {})
    payload = _payload_from_preflight(pre)
    payload_ok, payload_reasons = _payload_valid(payload)
    safety_ok, safety_reasons = _preflight_safety_ok(pre)

    blockers: list[str] = []
    if str(settings.mode).lower() != "paper":
        blockers.append("mode_not_paper")
    if not payload_ok:
        blockers.extend([f"payload_{reason}" for reason in payload_reasons])
    if not safety_ok:
        blockers.extend(safety_reasons)
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")
    if not settings.submit_armed:
        blockers.append("submit_not_armed")
    if not settings.submit_confirmation_ok:
        blockers.append("submit_confirmation_missing")
    if index >= max(settings.max_orders, 0):
        blockers.append("max_order_cap_exceeded")

    submit_ready = bool(
        payload_ok
        and safety_ok
        and settings.fail_closed
        and str(settings.mode).lower() == "paper"
        and settings.submit_armed
        and settings.submit_confirmation_ok
        and index < max(settings.max_orders, 0)
    )

    submit_result: Mapping[str, Any] | bool | None = None
    broker_submit_called = False
    order_submitted = False
    position_opened = False
    submit_error = ""
    if submit_ready and paper_submitter is not None:
        try:
            broker_submit_called = True
            submit_result = paper_submitter(payload)
            if isinstance(submit_result, Mapping):
                order_submitted = _safe_bool(submit_result.get("order_submitted"), _safe_bool(submit_result.get("submitted"), False))
                position_opened = _safe_bool(submit_result.get("position_opened"), False)
            else:
                order_submitted = bool(submit_result)
        except Exception as exc:  # pragma: no cover - defensive path
            submit_error = f"{type(exc).__name__}: {exc}"
            broker_submit_called = True
            order_submitted = False
            position_opened = False
            blockers.append("paper_submitter_exception")

    if not submit_ready:
        if "submit_not_armed" in blockers:
            blocked_reason = "submit_not_armed"
        elif "submit_confirmation_missing" in blockers:
            blocked_reason = "submit_confirmation_missing"
        elif "max_order_cap_exceeded" in blockers:
            blocked_reason = "max_order_cap_exceeded"
        else:
            blocked_reason = blockers[0] if blockers else "submit_not_ready"
    elif paper_submitter is None:
        blocked_reason = "paper_submitter_not_wired"
    elif order_submitted:
        blocked_reason = "submitted_to_paper_broker"
    else:
        blocked_reason = submit_error or "paper_submitter_returned_not_submitted"

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": payload.get("cycle_id", ""),
        "symbol": payload.get("symbol", ""),
        "timeframe": payload.get("timeframe", ""),
        "side": payload.get("side", ""),
        "order_type": payload.get("order_type", ""),
        "profile_name": payload.get("profile_name", settings.profile_name),
        "selected_overlay_id": payload.get("selected_overlay_id", settings.selected_overlay_id),
        "source": "lsr_v2_supervised_paper_submit_preflight",
        "source_event_type": str(pre.get("event_type") or PREFLIGHT_EVENT_TYPE),
        "candidate_id": payload.get("candidate_id", ""),
        "payload": payload,
        "payload_valid": bool(payload_ok),
        "payload_invalid_reasons": payload_reasons,
        "entry_price": payload.get("entry_price"),
        "stop_loss": payload.get("stop_loss"),
        "take_profit": payload.get("take_profit"),
        "risk_per_trade_pct": payload.get("risk_per_trade_pct"),
        "risk_amount": payload.get("risk_amount"),
        "position_size": payload.get("position_size"),
        "quantity": payload.get("quantity"),
        "notional": payload.get("notional"),
        "max_positions": payload.get("max_positions"),
        "submit_armed": bool(settings.submit_armed),
        "submit_confirmation_ok": bool(settings.submit_confirmation_ok),
        "submit_enabled": bool(submit_ready),
        "submit_ready": bool(submit_ready),
        "would_submit": bool(submit_ready and paper_submitter is not None),
        "would_submit_to_paper_broker": bool(submit_ready and paper_submitter is not None),
        "broker_submit_called": bool(broker_submit_called),
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "order_submitted": bool(order_submitted),
        "position_opened": bool(position_opened),
        "submit_result": dict(submit_result) if isinstance(submit_result, Mapping) else submit_result,
        "submit_error": submit_error,
        "blocked_reason": blocked_reason,
        "blocked_reasons": sorted(set(blockers)),
        "routing_enabled": False,
        "execution_enabled": bool(submit_ready and paper_submitter is not None),
        "paper_order_submission_enabled": bool(submit_ready and paper_submitter is not None),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_lsr_v2_submit": 1 if order_submitted else 0,
        "positions_opened_by_lsr_v2_submit": 1 if position_opened else 0,
        "max_orders": settings.max_orders,
        "single_order_gate": True,
        "audit_only": paper_submitter is None,
    }


def build_lsr_v2_supervised_paper_submit_events(
    preflight_events: Iterable[Mapping[str, Any]],
    *,
    settings: LSRV2SupervisedPaperSubmitSettings | None = None,
    paper_submitter: PaperSubmitter | None = None,
) -> list[dict[str, Any]]:
    settings = settings or LSRV2SupervisedPaperSubmitSettings()
    eligible = [dict(e) for e in _dedupe_preflight_events(preflight_events) if _safe_bool(e.get("would_prepare_submit"), False)]
    events: list[dict[str, Any]] = []
    for idx, preflight in enumerate(eligible):
        events.append(build_lsr_v2_supervised_paper_submit_event(
            preflight_event=preflight,
            settings=settings,
            index=idx,
            paper_submitter=paper_submitter,
        ))
    return events


def summarize_lsr_v2_supervised_paper_submit(
    *,
    cycle_id: str,
    preflight_events: Iterable[Mapping[str, Any]],
    submit_events: Iterable[Mapping[str, Any]],
    data_dir: str | Path = "data",
    settings: LSRV2SupervisedPaperSubmitSettings | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperSubmitSettings(data_dir=str(data_dir))
    metadata = dict(metadata or {})
    preflight_rows = _dedupe_preflight_events(preflight_events)
    submit_rows = [dict(e) for e in submit_events]
    ready_rows = [e for e in submit_rows if _safe_bool(e.get("submit_ready"), False)]
    would_submit_rows = [e for e in submit_rows if _safe_bool(e.get("would_submit"), False)]
    submitted_rows = [e for e in submit_rows if _safe_int(e.get("orders_submitted_by_lsr_v2_submit"), 0) > 0]
    position_rows = [e for e in submit_rows if _safe_int(e.get("positions_opened_by_lsr_v2_submit"), 0) > 0]

    blockers: list[str] = []
    if not preflight_rows:
        blockers.append("submit_preflight_missing")
    if not settings.submit_armed:
        blockers.append("submit_not_armed")
    if not settings.submit_confirmation_ok:
        blockers.append("submit_confirmation_missing")
    if settings.max_orders > 1:
        blockers.append("max_orders_above_single_order_gate")
    safety_violation_reasons = {
        "upstream_would_submit_detected",
        "upstream_broker_submit_called",
        "upstream_orders_submitted_nonzero",
        "upstream_positions_opened_nonzero",
        "live_enabled_true",
        "testnet_enabled_true",
        "exchange_broker_enabled_true",
        "operational_unlock_allowed_true",
        "paper_submitter_exception",
    }
    safety_violation = any(
        _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        or bool(set(e.get("blocked_reasons") or []) & safety_violation_reasons)
        for e in submit_rows
    )
    if safety_violation:
        blockers.append("safety_violation_detected")
    if len(submitted_rows) > 1:
        blockers.append("more_than_one_order_submitted")

    if not preflight_rows:
        decision = PREFLIGHT_MISSING_DECISION
        status = "WARN"
    elif safety_violation or len(submitted_rows) > 1:
        decision = REJECT_DECISION
        status = "WARN"
    elif not settings.submit_armed:
        decision = NOT_ARMED_DECISION
        status = "WARN"
    elif not settings.submit_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status = "WARN"
    elif settings.max_orders > 1:
        decision = CAP_EXCEEDED_DECISION
        status = "WARN"
    elif submitted_rows:
        decision = EXECUTED_DECISION
        status = "PASS"
    elif ready_rows:
        decision = READY_ARMED_DECISION
        status = "PASS"
    else:
        decision = NO_SUBMITTER_DECISION
        status = "WARN"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in ready_rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in ready_rows), 10)
    safety_checks = {
        "mode_paper": str(settings.mode).lower() == "paper",
        "single_order_gate": settings.max_orders == 1,
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
        "submitted_orders_lte_one": len(submitted_rows) <= 1,
    }
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_SUPERVISED_PAPER_SUBMIT_BOUNDARY",
            "SINGLE_ORDER_GATE",
        ] + (["ARMED_READY"] if decision == READY_ARMED_DECISION else []) + (["PAPER_SUBMIT_EXECUTED"] if decision == EXECUTED_DECISION else ["KEEP_DIAGNOSTIC"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "submit_preflight_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_submit_preflight_events": _safe_int(metadata.get("historical_submit_preflight_events"), 0),
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "submit_preflight_events": len(preflight_rows),
        "submit_boundary_events": len(submit_rows),
        "submit_ready_count": len(ready_rows),
        "would_submit_count": len(would_submit_rows),
        "would_submit_to_paper_broker_count": len(would_submit_rows),
        "broker_submit_called_count": sum(1 for e in submit_rows if _safe_bool(e.get("broker_submit_called"), False)),
        "orders_submitted_by_lsr_v2_submit": len(submitted_rows),
        "positions_opened_by_lsr_v2_submit": len(position_rows),
        "submit_armed": bool(settings.submit_armed),
        "submit_confirmation_ok": bool(settings.submit_confirmation_ok),
        "submit_enabled": bool(settings.submit_armed and settings.submit_confirmation_ok and settings.max_orders == 1),
        "submit_enabled_default": False,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "max_orders": settings.max_orders,
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "broker_submit_called": bool(any(_safe_bool(e.get("broker_submit_called"), False) for e in submit_rows)),
        "routing_enabled": False,
        "execution_enabled": bool(would_submit_rows),
        "paper_order_submission_enabled": bool(would_submit_rows),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


def build_lsr_v2_supervised_paper_submit_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SupervisedPaperSubmitSettings | None = None,
    paper_submitter: PaperSubmitter | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperSubmitSettings(data_dir=str(data_dir))
    selected_cycle_id, preflight_events, metadata = select_cycle_scoped_submit_preflight_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    submit_events = build_lsr_v2_supervised_paper_submit_events(
        preflight_events,
        settings=settings,
        paper_submitter=paper_submitter,
    )
    base = Path(data_dir)
    _write_jsonl_replace(base / settings.jsonl_name, submit_events)
    report = summarize_lsr_v2_supervised_paper_submit(
        cycle_id=selected_cycle_id,
        preflight_events=preflight_events,
        submit_events=submit_events,
        data_dir=base,
        settings=settings,
        metadata=metadata,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
