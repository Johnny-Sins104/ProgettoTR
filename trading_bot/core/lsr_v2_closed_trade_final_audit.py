"""Prompt 29.4.4s-10p — LSR-v2 closed paper trade final audit.

Reconstructs the first supervised LSR-v2 paper-only trade lifecycle after close:
submit execution -> open monitor TP diagnostic -> close preflight -> close
execution -> post-close lifecycle/status consistency.  This module is strictly
read-only: it never submits, closes, re-enters, mutates paper state/status, or
uses live/testnet/exchange brokers.
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

PROMPT_ID = "29.4.4s-10p"
EVENT_TYPE = "LSR_V2_CLOSED_TRADE_FINAL_AUDIT"
REPORT_NAME = "lsr_v2_closed_trade_final_audit_report.json"
JSONL_NAME = "lsr_v2_closed_trade_final_audit.jsonl"

PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

SUBMIT_EXEC_REPORT_NAME = "lsr_v2_supervised_paper_submit_execution_report.json"
SUBMIT_EXEC_JSONL_NAME = "lsr_v2_supervised_paper_submit_execution.jsonl"
SUBMIT_BOUNDARY_REPORT_NAME = "lsr_v2_supervised_paper_submit_report.json"
SUBMIT_PREFLIGHT_REPORT_NAME = "lsr_v2_supervised_paper_submit_preflight_report.json"
HANDOFF_REPORT_NAME = "lsr_v2_paper_broker_handoff_dry_run_report.json"
ORDER_INTENT_REPORT_NAME = "lsr_v2_order_intent_audit_report.json"

OPEN_MONITOR_REPORT_NAME = "lsr_v2_open_position_monitor_report.json"
OPEN_MONITOR_JSONL_NAME = "lsr_v2_open_position_monitor.jsonl"
LIFECYCLE_REPORT_NAME = "lsr_v2_paper_position_lifecycle_report.json"
LIFECYCLE_JSONL_NAME = "lsr_v2_paper_position_lifecycle.jsonl"
CLOSE_PREFLIGHT_REPORT_NAME = "lsr_v2_supervised_paper_close_preflight_report.json"
CLOSE_PREFLIGHT_JSONL_NAME = "lsr_v2_supervised_paper_close_preflight.jsonl"
CLOSE_EXEC_REPORT_NAME = "lsr_v2_supervised_paper_close_execution_report.json"
CLOSE_EXEC_JSONL_NAME = "lsr_v2_supervised_paper_close_execution.jsonl"
STATUS_RECONCILIATION_REPORT_NAME = "lsr_v2_paper_status_reconciliation_report.json"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"
SOURCE_TAG = "lsr_v2_supervised_paper_submit_execution"

PASS_DECISION = "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS"
INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CLOSED_TRADE_STATE_INCOMPLETE"
RESIDUAL_POSITION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_RESIDUAL_OPEN_POSITION"
PNL_RECONCILIATION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_PNL_RECONCILIATION_REQUIRED"
EXTRA_SUBMIT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_EXTRA_SUBMIT_OR_REENTRY_DETECTED"
REJECT_DECISION = "REJECT_LSR_V2_CLOSED_TRADE_AUDIT_FAILED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "ready", "open"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null", "closed"}:
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


def _metadata_of(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("paper_order_source") or row.get("execution_source") or row.get("source") or meta.get("paper_order_source") or meta.get("execution_source") or meta.get("source") or "")


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("symbol") or meta.get("symbol") or "")


def _row_side(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    side = str(row.get("side") or row.get("direction") or meta.get("side") or "").upper()
    if side == "LONG":
        return "BUY"
    if side == "SHORT":
        return "SELL"
    return side


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_lsr_v2_position(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    source = _row_source(row)
    meta = _metadata_of(row)
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    src_ok = any(token in source.lower() for token in ("lsr_v2", "paper_submit_execution")) or profile == PROFILE_NAME or overlay == SELECTED_OVERLAY_ID
    if not src_ok:
        return False
    if cycle_id and _row_cycle(row) and _row_cycle(row) != cycle_id:
        return False
    return True


def _latest_row(rows: list[dict[str, Any]], *, cycle_id: str = "") -> dict[str, Any]:
    if cycle_id:
        scoped = [r for r in rows if str(r.get("cycle_id") or "") == cycle_id]
        if scoped:
            return dict(scoped[-1])
    return dict(rows[-1]) if rows else {}


def _latest_event(rows: list[dict[str, Any]], event_type: str, *, cycle_id: str = "") -> dict[str, Any]:
    filtered = [r for r in rows if str(r.get("event_type") or "") == event_type]
    return _latest_row(filtered, cycle_id=cycle_id)


def _infer_cycle_id(*payloads: Mapping[str, Any]) -> str:
    for payload in payloads:
        val = str(payload.get("cycle_id") or "")
        if val:
            return val
    return ""


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


def _state_order_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _collection_rows(state.get("orders"), id_field="order_id")


def _count_lsr_v2_positions(state: Mapping[str, Any], *, cycle_id: str = "", open_only: bool | None = None) -> int:
    count = 0
    for row in _state_position_rows(state):
        if not _is_lsr_v2_position(row, cycle_id=cycle_id):
            continue
        if open_only is True and not _is_position_open(row):
            continue
        if open_only is False and _is_position_open(row):
            continue
        count += 1
    return count


def _sum_report_values(*payloads: Mapping[str, Any], keys: Iterable[str]) -> float:
    for key in keys:
        for payload in payloads:
            if key in payload and payload.get(key) is not None:
                return _round(payload.get(key))
    return 0.0


def _bool_false(payload: Mapping[str, Any], key: str, default: bool = False) -> bool:
    return _safe_bool(payload.get(key), default)


@dataclass
class ClosedTradeAuditEvent:
    event_type: str
    timestamp: str
    prompt: str
    cycle_id: str
    profile_name: str
    selected_overlay_id: str
    symbol: str
    side: str
    submit_executed: bool
    close_executed: bool
    close_reason: str
    realized_pnl: float
    realized_r: float
    entry_price: float
    close_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    notional: float
    risk_amount: float
    residual_open_position: bool
    extra_submit_or_reentry_detected: bool
    live_enabled: bool
    testnet_enabled: bool
    exchange_broker_enabled: bool
    operational_unlock_allowed: bool
    broker_submit_called_by_final_audit: bool
    broker_close_called_by_final_audit: bool
    orders_submitted_by_final_audit: int
    positions_opened_by_final_audit: int
    positions_closed_by_final_audit: int


def _make_event(report: Mapping[str, Any]) -> ClosedTradeAuditEvent:
    return ClosedTradeAuditEvent(
        event_type=EVENT_TYPE,
        timestamp=utc_now_iso(),
        prompt=PROMPT_ID,
        cycle_id=str(report.get("cycle_id") or ""),
        profile_name=PROFILE_NAME,
        selected_overlay_id=SELECTED_OVERLAY_ID,
        symbol=(report.get("symbols") or [""])[0] if isinstance(report.get("symbols"), list) else str(report.get("symbol") or ""),
        side=(report.get("sides") or [""])[0] if isinstance(report.get("sides"), list) else str(report.get("side") or ""),
        submit_executed=_safe_int(report.get("submit_execution_events"), 0) > 0,
        close_executed=_safe_int(report.get("close_execution_events"), 0) > 0,
        close_reason=(report.get("close_reasons") or [""])[0] if isinstance(report.get("close_reasons"), list) else str(report.get("close_reason") or ""),
        realized_pnl=_round(report.get("realized_pnl_total")),
        realized_r=_round(report.get("realized_r")),
        entry_price=_round(report.get("entry_price")),
        close_price=_round(report.get("close_price")),
        stop_loss=_round(report.get("stop_loss")),
        take_profit=_round(report.get("take_profit")),
        position_size=_round(report.get("position_size")),
        notional=_round(report.get("total_notional")),
        risk_amount=_round(report.get("total_risk_amount")),
        residual_open_position=_safe_bool(report.get("residual_open_position"), False),
        extra_submit_or_reentry_detected=_safe_bool(report.get("extra_submit_or_reentry_detected"), False),
        live_enabled=False,
        testnet_enabled=False,
        exchange_broker_enabled=False,
        operational_unlock_allowed=False,
        broker_submit_called_by_final_audit=False,
        broker_close_called_by_final_audit=False,
        orders_submitted_by_final_audit=0,
        positions_opened_by_final_audit=0,
        positions_closed_by_final_audit=0,
    )


def build_lsr_v2_closed_trade_final_audit_report_from_files(
    data_dir: str | Path = "data",
    *,
    cycle_id: str = "",
) -> dict[str, Any]:
    data = Path(data_dir)
    paper_state = _read_json(data / PAPER_STATE_NAME)
    paper_status = _read_json(data / PAPER_STATUS_NAME)
    paper_events = _iter_jsonl_tail(data / PAPER_EVENTS_NAME)

    submit_report = _read_json(data / SUBMIT_EXEC_REPORT_NAME)
    submit_boundary_report = _read_json(data / SUBMIT_BOUNDARY_REPORT_NAME)
    submit_preflight_report = _read_json(data / SUBMIT_PREFLIGHT_REPORT_NAME)
    handoff_report = _read_json(data / HANDOFF_REPORT_NAME)
    order_intent_report = _read_json(data / ORDER_INTENT_REPORT_NAME)

    monitor_report = _read_json(data / OPEN_MONITOR_REPORT_NAME)
    lifecycle_report = _read_json(data / LIFECYCLE_REPORT_NAME)
    close_preflight_report = _read_json(data / CLOSE_PREFLIGHT_REPORT_NAME)
    close_report = _read_json(data / CLOSE_EXEC_REPORT_NAME)
    reconciliation_report = _read_json(data / STATUS_RECONCILIATION_REPORT_NAME)

    submit_events = _iter_jsonl_tail(data / SUBMIT_EXEC_JSONL_NAME)
    monitor_events = _iter_jsonl_tail(data / OPEN_MONITOR_JSONL_NAME)
    lifecycle_events = _iter_jsonl_tail(data / LIFECYCLE_JSONL_NAME)
    close_preflight_events = _iter_jsonl_tail(data / CLOSE_PREFLIGHT_JSONL_NAME)
    close_events = _iter_jsonl_tail(data / CLOSE_EXEC_JSONL_NAME)

    inferred_cycle_id = cycle_id or _infer_cycle_id(close_report, lifecycle_report, monitor_report, submit_report, close_preflight_report)
    if not inferred_cycle_id:
        inferred_cycle_id = str(_latest_event(paper_events, "CYCLE_COMPLETED").get("cycle_id") or "")

    submit_event = _latest_row(submit_events, cycle_id=inferred_cycle_id)
    monitor_event = _latest_row(monitor_events, cycle_id=inferred_cycle_id)
    lifecycle_event = _latest_row(lifecycle_events, cycle_id=inferred_cycle_id)
    close_preflight_event = _latest_row(close_preflight_events, cycle_id=inferred_cycle_id)
    close_event = _latest_row(close_events, cycle_id=inferred_cycle_id)

    submit_executed = _safe_int(submit_report.get("orders_submitted_by_lsr_v2_execution"), 0) == 1 or _safe_int(submit_event.get("orders_submitted_by_lsr_v2_execution"), 0) == 1 or _safe_bool(submit_event.get("broker_submit_called"), False)
    close_executed = _safe_int(close_report.get("positions_closed_by_lsr_v2_close_execution"), 0) == 1 or _safe_int(close_event.get("positions_closed_by_lsr_v2_close_execution"), 0) == 1 or _safe_bool(close_event.get("paper_close_called"), False)

    submit_execution_events = max(
        _safe_int(submit_report.get("execution_events"), 0),
        len([e for e in submit_events if not inferred_cycle_id or str(e.get("cycle_id") or "") == inferred_cycle_id]),
    )
    close_execution_events_count = max(
        _safe_int(close_report.get("close_execution_events"), 0),
        len([e for e in close_events if not inferred_cycle_id or str(e.get("cycle_id") or "") == inferred_cycle_id]),
    )

    state_open_lsr_v2_positions = _count_lsr_v2_positions(paper_state, cycle_id=inferred_cycle_id, open_only=True)
    state_closed_lsr_v2_positions = _count_lsr_v2_positions(paper_state, cycle_id=inferred_cycle_id, open_only=False)
    state_all_lsr_v2_positions = _count_lsr_v2_positions(paper_state, cycle_id=inferred_cycle_id, open_only=None)
    status_open_positions = _paper_status_open_positions(paper_status)
    status_pending_orders = _paper_status_pending_orders(paper_status)

    lifecycle_open = _safe_int(lifecycle_report.get("open_lsr_v2_position_count"), 0)
    lifecycle_closed = _safe_int(lifecycle_report.get("closed_lsr_v2_position_count"), 0)
    monitor_open = _safe_int(monitor_report.get("open_lsr_v2_position_count"), 0)
    close_after_open = _safe_int(close_report.get("open_lsr_v2_positions_after"), state_open_lsr_v2_positions)

    residual_open_position = any(v > 0 for v in [state_open_lsr_v2_positions, status_open_positions, lifecycle_open, monitor_open, close_after_open])
    paper_state_consistency = _safe_bool(lifecycle_report.get("paper_state_consistency"), True) and state_open_lsr_v2_positions == 0
    paper_status_consistency = _safe_bool(lifecycle_report.get("paper_status_consistency"), status_open_positions == 0) and status_open_positions == 0
    state_status_flat = status_open_positions == 0 and status_pending_orders == 0

    realized_pnl_total = _sum_report_values(close_report, close_event, lifecycle_report, keys=["realized_pnl_total", "realized_pnl", "pnl", "closed_pnl"])
    total_risk_amount = _sum_report_values(close_report, close_event, submit_report, submit_event, close_preflight_report, monitor_report, keys=["total_risk_amount", "risk_amount"])
    total_notional = _sum_report_values(close_report, close_event, submit_report, submit_event, close_preflight_report, monitor_report, keys=["total_notional", "notional"])
    realized_r = _round(realized_pnl_total / total_risk_amount) if total_risk_amount else 0.0

    entry_price = _sum_report_values(close_report, close_event, monitor_report, monitor_event, submit_report, submit_event, keys=["entry_price"])
    close_price = _sum_report_values(close_report, close_event, monitor_report, monitor_event, keys=["close_price", "exit_price", "current_price"])
    stop_loss = _sum_report_values(close_report, close_event, monitor_report, monitor_event, submit_report, submit_event, keys=["stop_loss"])
    take_profit = _sum_report_values(close_report, close_event, monitor_report, monitor_event, submit_report, submit_event, keys=["take_profit"])
    position_size = _sum_report_values(close_report, close_event, monitor_report, monitor_event, submit_report, submit_event, keys=["position_size", "size", "quantity"])

    symbols = []
    sides = []
    for payload in [close_report, close_event, lifecycle_report, lifecycle_event, submit_report, submit_event, monitor_report, monitor_event]:
        raw_symbols = payload.get("symbols")
        if isinstance(raw_symbols, list):
            symbols.extend(str(x) for x in raw_symbols if x)
        elif payload.get("symbol"):
            symbols.append(str(payload.get("symbol")))
        raw_sides = payload.get("sides")
        if isinstance(raw_sides, list):
            sides.extend(str(x) for x in raw_sides if x)
        elif payload.get("side"):
            sides.append(str(payload.get("side")))
    symbols = sorted(set(symbols))
    sides = sorted(set(sides))

    close_reasons: list[str] = []
    for payload in [close_report, close_event, close_preflight_report, close_preflight_event, monitor_report, monitor_event]:
        raw = payload.get("close_reasons")
        if isinstance(raw, list):
            close_reasons.extend(str(x) for x in raw if x)
        elif payload.get("close_reason"):
            close_reasons.append(str(payload.get("close_reason")))
        if _safe_bool(payload.get("take_profit_hit_diagnostic"), False) or _safe_int(payload.get("take_profit_hit_diagnostic_count"), 0) > 0:
            close_reasons.append("TAKE_PROFIT_HIT_DIAGNOSTIC")
        if _safe_bool(payload.get("stop_hit_diagnostic"), False) or _safe_int(payload.get("stop_hit_diagnostic_count"), 0) > 0:
            close_reasons.append("STOP_HIT_DIAGNOSTIC")
    close_reasons = sorted(set(close_reasons))

    upstream_safety_flags = {
        "submit_live_enabled": _bool_false(submit_report, "live_enabled", False),
        "submit_testnet_enabled": _bool_false(submit_report, "testnet_enabled", False),
        "submit_exchange_broker_enabled": _bool_false(submit_report, "exchange_broker_enabled", False),
        "close_live_enabled": _bool_false(close_report, "live_enabled", False),
        "close_testnet_enabled": _bool_false(close_report, "testnet_enabled", False),
        "close_exchange_broker_enabled": _bool_false(close_report, "exchange_broker_enabled", False),
    }

    extra_submit_or_reentry_detected = (
        _safe_int(submit_report.get("orders_submitted_by_lsr_v2_execution"), 0) > 1
        or _safe_int(submit_report.get("positions_opened_by_lsr_v2_execution"), 0) > 1
        or _safe_int(submit_boundary_report.get("submit_ready_count"), 0) > 1
        or submit_execution_events > 1
        or state_all_lsr_v2_positions > 1
    )
    close_multiple_detected = _safe_int(close_report.get("positions_closed_by_lsr_v2_close_execution"), 0) > 1 or close_execution_events_count > 1

    reports_present = {
        "submit_execution_report": bool(submit_report),
        "close_execution_report": bool(close_report),
        "close_preflight_report": bool(close_preflight_report),
        "open_position_monitor_report": bool(monitor_report),
        "lifecycle_report": bool(lifecycle_report),
        "paper_state": bool(paper_state),
        "paper_status": bool(paper_status),
    }
    missing_required_reports = [k for k, present in reports_present.items() if not present and k in {"submit_execution_report", "close_execution_report", "paper_state", "paper_status"}]

    pnl_reconciliation_ok = close_executed and total_risk_amount > 0 and realized_pnl_total != 0 and realized_r != 0
    closed_trade_complete = submit_executed and close_executed and not residual_open_position and paper_state_consistency and paper_status_consistency and state_status_flat

    blockers: list[str] = []
    if missing_required_reports:
        blockers.append("required_reports_missing")
    if not submit_executed:
        blockers.append("submit_execution_not_found")
    if not close_executed:
        blockers.append("close_execution_not_found")
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
    if close_multiple_detected:
        blockers.append("multiple_close_events_detected")
    if any(upstream_safety_flags.values()):
        blockers.append("unsafe_upstream_flag_detected")

    if any(upstream_safety_flags.values()):
        status = "FAIL"
        decision = REJECT_DECISION
    elif missing_required_reports or not submit_executed or not close_executed:
        status = "WARN"
        decision = INCOMPLETE_DECISION
    elif residual_open_position:
        status = "WARN"
        decision = RESIDUAL_POSITION_DECISION
    elif not pnl_reconciliation_ok:
        status = "WARN"
        decision = PNL_RECONCILIATION_DECISION
    elif extra_submit_or_reentry_detected or close_multiple_detected:
        status = "WARN"
        decision = EXTRA_SUBMIT_DECISION
    elif not paper_state_consistency or not paper_status_consistency:
        status = "WARN"
        decision = INCOMPLETE_DECISION
    else:
        status = "PASS"
        decision = PASS_DECISION

    classification_labels: list[str] = []
    if decision == PASS_DECISION:
        classification_labels.extend(["CLOSED_TRADE_AUDIT_PASS", "NO_RESIDUAL_POSITION", "REALIZED_PNL_RECONCILED"])
    if residual_open_position:
        classification_labels.append("RESIDUAL_OPEN_POSITION")
    if not pnl_reconciliation_ok:
        classification_labels.append("PNL_RECONCILIATION_REQUIRED")
    if extra_submit_or_reentry_detected:
        classification_labels.append("EXTRA_SUBMIT_OR_REENTRY_DETECTED")
    if close_multiple_detected:
        classification_labels.append("MULTIPLE_CLOSE_EVENTS_DETECTED")

    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": blockers,
        "cycle_id": inferred_cycle_id,
        "profile_name": PROFILE_NAME,
        "selected_overlay_id": SELECTED_OVERLAY_ID,
        "strict_cycle_scope": True,
        "reports_present": reports_present,
        "missing_required_reports": missing_required_reports,
        "submit_execution_events": submit_execution_events,
        "submit_executed": submit_executed,
        "orders_submitted_by_lsr_v2_execution": min(1, _safe_int(submit_report.get("orders_submitted_by_lsr_v2_execution"), _safe_int(submit_event.get("orders_submitted_by_lsr_v2_execution"), 0))),
        "positions_opened_by_lsr_v2_execution": min(1, _safe_int(submit_report.get("positions_opened_by_lsr_v2_execution"), _safe_int(submit_event.get("positions_opened_by_lsr_v2_execution"), 0))),
        "close_preflight_events": max(_safe_int(close_preflight_report.get("close_preflight_events"), 0), len([e for e in close_preflight_events if not inferred_cycle_id or str(e.get("cycle_id") or "") == inferred_cycle_id])),
        "close_execution_events": close_execution_events_count,
        "close_executed": close_executed,
        "positions_closed_by_lsr_v2_close_execution": min(1, _safe_int(close_report.get("positions_closed_by_lsr_v2_close_execution"), _safe_int(close_event.get("positions_closed_by_lsr_v2_close_execution"), 0))),
        "closed_trade_complete": closed_trade_complete,
        "symbols": symbols,
        "sides": sides,
        "close_reasons": close_reasons,
        "entry_price": _round(entry_price),
        "close_price": _round(close_price),
        "stop_loss": _round(stop_loss),
        "take_profit": _round(take_profit),
        "position_size": _round(position_size),
        "total_notional": _round(total_notional),
        "total_risk_amount": _round(total_risk_amount),
        "realized_pnl_total": _round(realized_pnl_total),
        "realized_r": _round(realized_r),
        "pnl_reconciliation_ok": pnl_reconciliation_ok,
        "state_open_lsr_v2_positions": state_open_lsr_v2_positions,
        "state_closed_lsr_v2_positions": state_closed_lsr_v2_positions,
        "state_all_lsr_v2_positions": state_all_lsr_v2_positions,
        "paper_status_open_positions": status_open_positions,
        "paper_status_pending_orders": status_pending_orders,
        "paper_state_consistency": paper_state_consistency,
        "paper_status_consistency": paper_status_consistency,
        "state_status_flat": state_status_flat,
        "lifecycle_open_lsr_v2_position_count": lifecycle_open,
        "lifecycle_closed_lsr_v2_position_count": lifecycle_closed,
        "monitor_open_lsr_v2_position_count": monitor_open,
        "residual_open_position": residual_open_position,
        "extra_submit_or_reentry_detected": extra_submit_or_reentry_detected,
        "close_multiple_detected": close_multiple_detected,
        "paper_state_modified_by_final_audit": False,
        "paper_status_modified_by_final_audit": False,
        "broker_submit_called_by_final_audit": False,
        "broker_close_called_by_final_audit": False,
        "orders_submitted_by_final_audit": 0,
        "positions_opened_by_final_audit": 0,
        "positions_closed_by_final_audit": 0,
        "automatic_reentry_enabled": False,
        "automatic_close_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "event_source": "closed_trade_reports_and_state",
        "report": str(data / REPORT_NAME),
        "jsonl": str(data / JSONL_NAME),
        "generated_at": utc_now_iso(),
    }

    event = asdict(_make_event(report))
    _write_json(data / REPORT_NAME, report)
    _append_jsonl(data / JSONL_NAME, event)
    return report


__all__ = [
    "EVENT_TYPE",
    "REPORT_NAME",
    "JSONL_NAME",
    "PASS_DECISION",
    "INCOMPLETE_DECISION",
    "RESIDUAL_POSITION_DECISION",
    "PNL_RECONCILIATION_DECISION",
    "EXTRA_SUBMIT_DECISION",
    "REJECT_DECISION",
    "build_lsr_v2_closed_trade_final_audit_report_from_files",
]
