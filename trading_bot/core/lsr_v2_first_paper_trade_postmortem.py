"""Prompt 29.4.4s-10q — LSR-v2 first paper trade postmortem / one-trade stability lock.

This module freezes and audits the first completed LSR-v2 supervised paper-only
trade lifecycle after the final closed-trade audit. It is deliberately read-only:
it never submits orders, closes positions, mutates paper state/status, re-enters,
or enables live/testnet/exchange brokers.
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

PROMPT_ID = "29.4.4s-10q"
EVENT_TYPE = "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM"
REPORT_NAME = "lsr_v2_first_paper_trade_postmortem_report.json"
JSONL_NAME = "lsr_v2_first_paper_trade_postmortem.jsonl"

PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

FINAL_AUDIT_REPORT_NAME = "lsr_v2_closed_trade_final_audit_report.json"
FINAL_AUDIT_JSONL_NAME = "lsr_v2_closed_trade_final_audit.jsonl"
SUBMIT_EXEC_REPORT_NAME = "lsr_v2_supervised_paper_submit_execution_report.json"
SUBMIT_EXEC_JSONL_NAME = "lsr_v2_supervised_paper_submit_execution.jsonl"
CLOSE_EXEC_REPORT_NAME = "lsr_v2_supervised_paper_close_execution_report.json"
CLOSE_EXEC_JSONL_NAME = "lsr_v2_supervised_paper_close_execution.jsonl"
OPEN_MONITOR_REPORT_NAME = "lsr_v2_open_position_monitor_report.json"
CLOSE_PREFLIGHT_REPORT_NAME = "lsr_v2_supervised_paper_close_preflight_report.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_paper_position_lifecycle_report.json"
STATUS_RECONCILIATION_REPORT_NAME = "lsr_v2_paper_status_reconciliation_report.json"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"

PASS_DECISION = "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS"
INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSTMORTEM_INCOMPLETE"
RESIDUAL_POSITION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSTMORTEM_RESIDUAL_OPEN_POSITION"
PNL_RECONCILIATION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSTMORTEM_PNL_RECONCILIATION_REQUIRED"
EXTRA_SUBMIT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSTMORTEM_EXTRA_SUBMIT_OR_REENTRY_DETECTED"
REJECT_DECISION = "REJECT_LSR_V2_POSTMORTEM_SAFETY_FAILED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "ready"}:
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


def _round(value: Any, digits: int = 10) -> float:
    return round(_safe_float(value, 0.0), digits)


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _collection_rows(value: Any, *, id_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, raw in value.items():
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(key))
            rows.append(row)
    elif isinstance(value, list):
        for idx, raw in enumerate(value):
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(row.get(id_field) or idx))
            rows.append(row)
    return rows


def _metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("paper_order_source") or row.get("execution_source") or row.get("source") or meta.get("paper_order_source") or meta.get("execution_source") or meta.get("source") or "")


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_lsr_v2_row(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    meta = _metadata(row)
    source = _row_source(row).lower()
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    source_ok = "lsr_v2" in source or "paper_submit_execution" in source or profile == PROFILE_NAME or overlay == SELECTED_OVERLAY_ID
    if not source_ok:
        return False
    row_cycle = _row_cycle(row)
    if cycle_id and row_cycle and row_cycle != cycle_id:
        return False
    return True


def _paper_status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_position_count"), 0)
    return 0


def _paper_status_pending_orders(status: Mapping[str, Any]) -> int:
    return _safe_int(status.get("pending_orders"), 0)


def _state_position_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _collection_rows(state.get("positions"), id_field="position_id")


def _count_state_positions(state: Mapping[str, Any], *, cycle_id: str = "", open_only: bool | None = None) -> int:
    count = 0
    for row in _state_position_rows(state):
        if not _is_lsr_v2_row(row, cycle_id=cycle_id):
            continue
        if open_only is True and not _is_position_open(row):
            continue
        if open_only is False and _is_position_open(row):
            continue
        count += 1
    return count


def _latest_row(rows: list[dict[str, Any]], *, cycle_id: str = "") -> dict[str, Any]:
    if cycle_id:
        scoped = [r for r in rows if str(r.get("cycle_id") or "") == cycle_id]
        if scoped:
            return dict(scoped[-1])
    return dict(rows[-1]) if rows else {}


def _infer_cycle_id(*payloads: Mapping[str, Any]) -> str:
    for payload in payloads:
        cycle = str(payload.get("cycle_id") or "")
        if cycle:
            return cycle
    return ""


def _count_events(rows: Iterable[Mapping[str, Any]], event_type: str, *, cycle_id: str = "") -> int:
    return len([r for r in rows if str(r.get("event_type") or "") == event_type and (not cycle_id or str(r.get("cycle_id") or "") == cycle_id)])


def _has_unsafe_flag(*payloads: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "live_enabled": any(_safe_bool(p.get("live_enabled"), False) or _safe_bool(p.get("live_allowed"), False) for p in payloads),
        "testnet_enabled": any(_safe_bool(p.get("testnet_enabled"), False) or _safe_bool(p.get("testnet_allowed"), False) for p in payloads),
        "exchange_broker_enabled": any(_safe_bool(p.get("exchange_broker_enabled"), False) or _safe_bool(p.get("exchange_broker_allowed"), False) for p in payloads),
        "operational_unlock_allowed": any(_safe_bool(p.get("operational_unlock_allowed"), False) for p in payloads),
        "automatic_activation_allowed": any(_safe_bool(p.get("automatic_activation_allowed"), False) for p in payloads),
        "automatic_reentry_enabled": any(_safe_bool(p.get("automatic_reentry_enabled"), False) for p in payloads),
    }


@dataclass
class FirstPaperTradePostmortemEvent:
    event_type: str
    timestamp: str
    prompt: str
    cycle_id: str
    profile_name: str
    selected_overlay_id: str
    closed_trade_complete: bool
    postmortem_complete: bool
    next_step_observation_required: bool
    second_trade_allowed: bool
    realized_pnl_total: float
    realized_r: float
    state_open_lsr_v2_positions: int
    state_closed_lsr_v2_positions: int
    paper_status_open_positions: int
    paper_status_pending_orders: int
    submit_execution_events: int
    close_execution_events: int
    extra_submit_or_reentry_detected: bool
    residual_open_position: bool
    live_enabled: bool
    testnet_enabled: bool
    exchange_broker_enabled: bool
    operational_unlock_allowed: bool
    automatic_activation_allowed: bool
    broker_submit_called_by_postmortem: bool
    broker_close_called_by_postmortem: bool
    orders_submitted_by_postmortem: int
    positions_opened_by_postmortem: int
    positions_closed_by_postmortem: int


def _make_event(report: Mapping[str, Any]) -> FirstPaperTradePostmortemEvent:
    return FirstPaperTradePostmortemEvent(
        event_type=EVENT_TYPE,
        timestamp=utc_now_iso(),
        prompt=PROMPT_ID,
        cycle_id=str(report.get("cycle_id") or ""),
        profile_name=PROFILE_NAME,
        selected_overlay_id=SELECTED_OVERLAY_ID,
        closed_trade_complete=_safe_bool(report.get("closed_trade_complete"), False),
        postmortem_complete=_safe_bool(report.get("postmortem_complete"), False),
        next_step_observation_required=True,
        second_trade_allowed=False,
        realized_pnl_total=_round(report.get("realized_pnl_total")),
        realized_r=_round(report.get("realized_r")),
        state_open_lsr_v2_positions=_safe_int(report.get("state_open_lsr_v2_positions"), 0),
        state_closed_lsr_v2_positions=_safe_int(report.get("state_closed_lsr_v2_positions"), 0),
        paper_status_open_positions=_safe_int(report.get("paper_status_open_positions"), 0),
        paper_status_pending_orders=_safe_int(report.get("paper_status_pending_orders"), 0),
        submit_execution_events=_safe_int(report.get("submit_execution_events"), 0),
        close_execution_events=_safe_int(report.get("close_execution_events"), 0),
        extra_submit_or_reentry_detected=_safe_bool(report.get("extra_submit_or_reentry_detected"), False),
        residual_open_position=_safe_bool(report.get("residual_open_position"), False),
        live_enabled=False,
        testnet_enabled=False,
        exchange_broker_enabled=False,
        operational_unlock_allowed=False,
        automatic_activation_allowed=False,
        broker_submit_called_by_postmortem=False,
        broker_close_called_by_postmortem=False,
        orders_submitted_by_postmortem=0,
        positions_opened_by_postmortem=0,
        positions_closed_by_postmortem=0,
    )


def build_lsr_v2_first_paper_trade_postmortem_report_from_files(
    data_dir: str | Path = "data",
    *,
    cycle_id: str = "",
) -> dict[str, Any]:
    data = Path(data_dir)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)
    paper_events = _iter_jsonl_tail(data / PAPER_EVENTS_NAME)

    final_report = _read_json(data / FINAL_AUDIT_REPORT_NAME)
    submit_report = _read_json(data / SUBMIT_EXEC_REPORT_NAME)
    close_report = _read_json(data / CLOSE_EXEC_REPORT_NAME)
    monitor_report = _read_json(data / OPEN_MONITOR_REPORT_NAME)
    close_preflight_report = _read_json(data / CLOSE_PREFLIGHT_REPORT_NAME)
    lifecycle_report = _read_json(data / LIFECYCLE_REPORT_NAME)
    reconciliation_report = _read_json(data / STATUS_RECONCILIATION_REPORT_NAME)

    final_events = _iter_jsonl_tail(data / FINAL_AUDIT_JSONL_NAME)
    submit_events = _iter_jsonl_tail(data / SUBMIT_EXEC_JSONL_NAME)
    close_events = _iter_jsonl_tail(data / CLOSE_EXEC_JSONL_NAME)

    inferred_cycle_id = cycle_id or _infer_cycle_id(final_report, close_report, lifecycle_report, submit_report, close_preflight_report)
    if not inferred_cycle_id:
        cycle_completed = [r for r in paper_events if str(r.get("event_type") or "") == "CYCLE_COMPLETED"]
        inferred_cycle_id = str(cycle_completed[-1].get("cycle_id") or "") if cycle_completed else ""

    final_event = _latest_row(final_events, cycle_id=inferred_cycle_id)

    missing_reports = []
    required = {
        FINAL_AUDIT_REPORT_NAME: final_report,
        SUBMIT_EXEC_REPORT_NAME: submit_report,
        CLOSE_EXEC_REPORT_NAME: close_report,
        LIFECYCLE_REPORT_NAME: lifecycle_report,
    }
    for name, payload in required.items():
        if not payload:
            missing_reports.append(name)

    submit_execution_events = max(
        _safe_int(final_report.get("submit_execution_events"), 0),
        _safe_int(submit_report.get("execution_events"), 0),
        _count_events(submit_events, "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION", cycle_id=inferred_cycle_id),
    )
    close_execution_events = max(
        _safe_int(final_report.get("close_execution_events"), 0),
        _safe_int(close_report.get("close_execution_events"), 0),
        _count_events(close_events, "LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION", cycle_id=inferred_cycle_id),
    )

    closed_trade_complete = _safe_bool(final_report.get("closed_trade_complete"), False) or _safe_bool(final_event.get("closed_trade_complete"), False)
    submit_executed = _safe_bool(final_report.get("submit_executed"), False) or submit_execution_events == 1
    close_executed = _safe_bool(final_report.get("close_executed"), False) or close_execution_events == 1

    state_open = _count_state_positions(paper_state, cycle_id=inferred_cycle_id, open_only=True)
    state_closed = max(_count_state_positions(paper_state, cycle_id=inferred_cycle_id, open_only=False), _safe_int(final_report.get("state_closed_lsr_v2_positions"), 0), _safe_int(lifecycle_report.get("closed_lsr_v2_position_count"), 0))
    status_open = _paper_status_open_positions(paper_status)
    status_pending = _paper_status_pending_orders(paper_status)

    residual_open_position = _safe_bool(final_report.get("residual_open_position"), False) or state_open > 0 or status_open > 0
    paper_state_consistency = _safe_bool(final_report.get("paper_state_consistency"), True) and _safe_bool(lifecycle_report.get("paper_state_consistency"), True) and state_open == 0
    paper_status_consistency = _safe_bool(final_report.get("paper_status_consistency"), True) and _safe_bool(lifecycle_report.get("paper_status_consistency"), True) and status_open == 0 and status_pending == 0

    realized_pnl_total = _round(final_report.get("realized_pnl_total") if "realized_pnl_total" in final_report else close_report.get("realized_pnl_total"))
    total_risk_amount = _round(final_report.get("total_risk_amount") if "total_risk_amount" in final_report else close_report.get("total_risk_amount"))
    realized_r = _round(final_report.get("realized_r") if "realized_r" in final_report else (realized_pnl_total / total_risk_amount if total_risk_amount else 0.0))
    total_notional = _round(final_report.get("total_notional") if "total_notional" in final_report else close_report.get("total_notional"))

    pnl_reconciliation_ok = _safe_bool(final_report.get("pnl_reconciliation_ok"), realized_pnl_total != 0.0 and bool(total_risk_amount)) and bool(total_risk_amount) and abs(realized_r - _round(realized_pnl_total / total_risk_amount)) < 1e-6

    extra_submit_or_reentry_detected = (
        _safe_bool(final_report.get("extra_submit_or_reentry_detected"), False)
        or submit_execution_events != 1
        or close_execution_events != 1
        or state_closed != 1
    )

    unsafe_flags = _has_unsafe_flag(final_report, submit_report, close_report, monitor_report, close_preflight_report, lifecycle_report, reconciliation_report)

    blockers: list[str] = []
    if missing_reports:
        blockers.append("required_reports_missing")
    if not closed_trade_complete or not submit_executed or not close_executed:
        blockers.append("closed_trade_chain_incomplete")
    if residual_open_position:
        blockers.append("residual_open_position")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if not pnl_reconciliation_ok:
        blockers.append("pnl_reconciliation_required")
    if extra_submit_or_reentry_detected:
        blockers.append("extra_submit_or_reentry_detected")
    if any(unsafe_flags.values()):
        blockers.append("unsafe_flag_detected")

    if any(unsafe_flags.values()):
        status = "FAIL"
        decision = REJECT_DECISION
    elif missing_reports or not closed_trade_complete or not submit_executed or not close_executed:
        status = "WARN"
        decision = INCOMPLETE_DECISION
    elif residual_open_position or not paper_state_consistency or not paper_status_consistency:
        status = "WARN"
        decision = RESIDUAL_POSITION_DECISION
    elif not pnl_reconciliation_ok:
        status = "WARN"
        decision = PNL_RECONCILIATION_DECISION
    elif extra_submit_or_reentry_detected:
        status = "WARN"
        decision = EXTRA_SUBMIT_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    labels = []
    if status == "PASS":
        labels.extend(["FIRST_PAPER_TRADE_POSTMORTEM_PASS", "NEXT_STEP_OBSERVATION_REQUIRED", "SECOND_TRADE_LOCKED"])
    else:
        if residual_open_position:
            labels.append("RESIDUAL_POSITION_DETECTED")
        if not pnl_reconciliation_ok:
            labels.append("PNL_RECONCILIATION_REQUIRED")
        if extra_submit_or_reentry_detected:
            labels.append("EXTRA_SUBMIT_OR_REENTRY_DETECTED")
        if any(unsafe_flags.values()):
            labels.append("SAFETY_FLAG_FAILED")

    report: dict[str, Any] = {
        "status": status,
        "decision": decision,
        "prompt": PROMPT_ID,
        "cycle_id": inferred_cycle_id,
        "profile_name": PROFILE_NAME,
        "selected_overlay_id": SELECTED_OVERLAY_ID,
        "classification_labels": labels,
        "blockers": blockers,
        "missing_reports": missing_reports,
        "closed_trade_complete": closed_trade_complete,
        "postmortem_complete": status == "PASS",
        "next_step_observation_required": True,
        "observation_recommended_hours_first": 4,
        "observation_recommended_hours_second": 8,
        "second_trade_allowed": False,
        "automatic_activation_allowed": False,
        "submit_rearmed": False,
        "reentry_allowed": False,
        "submit_executed": submit_executed,
        "submit_execution_events": submit_execution_events,
        "close_executed": close_executed,
        "close_execution_events": close_execution_events,
        "close_reasons": close_report.get("close_reasons") or final_report.get("close_reasons") or [],
        "realized_pnl_total": realized_pnl_total,
        "realized_r": realized_r,
        "total_risk_amount": total_risk_amount,
        "total_notional": total_notional,
        "pnl_reconciliation_ok": pnl_reconciliation_ok,
        "state_open_lsr_v2_positions": state_open,
        "state_closed_lsr_v2_positions": state_closed,
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "paper_state_consistency": paper_state_consistency,
        "paper_status_consistency": paper_status_consistency,
        "residual_open_position": residual_open_position,
        "extra_submit_or_reentry_detected": extra_submit_or_reentry_detected,
        "operator_confirmations_used": {
            "paper_supervised_operator_confirmation": "I_UNDERSTAND_PAPER_ONLY",
            "paper_submit_confirmation": "I_UNDERSTAND_SINGLE_PAPER_ORDER",
            "paper_submit_execute_confirmation": "I_UNDERSTAND_EXECUTE_ONE_PAPER_ORDER_ONLY",
            "paper_close_confirmation": "I_UNDERSTAND_CLOSE_ONE_PAPER_POSITION_ONLY",
        },
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "orders_submitted_by_postmortem": 0,
        "positions_opened_by_postmortem": 0,
        "positions_closed_by_postmortem": 0,
        "broker_submit_called_by_postmortem": False,
        "broker_close_called_by_postmortem": False,
        "paper_state_modified_by_postmortem": False,
        "paper_status_modified_by_postmortem": False,
        "report": str(data / REPORT_NAME),
        "jsonl": str(data / JSONL_NAME),
    }

    event = asdict(_make_event(report))
    _append_jsonl(data / JSONL_NAME, event)
    _write_json(data / REPORT_NAME, report)
    return report
