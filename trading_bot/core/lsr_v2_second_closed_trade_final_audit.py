"""Prompt 29.4.4s-10ad — LSR-v2 second closed paper trade final audit.

Non-mutating final audit for the second supervised paper-only LSR-v2 trade.  It
reconstructs submit -> close -> post-close state, validates realized outcome, and
checks that no third submit / re-entry / residual exposure exists.  It never
opens, closes, submits, or mutates paper state/status.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore
import json

PROMPT_ID = "29.4.4s-10ad"
EVENT_TYPE = "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT"
REPORT_NAME = "lsr_v2_second_closed_trade_final_audit_report.json"
JSONL_NAME = "lsr_v2_second_closed_trade_final_audit.jsonl"

SUBMIT_EXEC_REPORT_NAME = "lsr_v2_second_trade_submit_execution_report.json"
SUBMIT_EXEC_JSONL_NAME = "lsr_v2_second_trade_submit_execution.jsonl"
CLOSE_EXEC_REPORT_NAME = "lsr_v2_second_trade_close_execution_report.json"
CLOSE_EXEC_JSONL_NAME = "lsr_v2_second_trade_close_execution.jsonl"
LIFECYCLE_REPORT_NAME = "lsr_v2_second_trade_position_lifecycle_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SECOND_SOURCE_TAG = "lsr_v2_second_trade_submit_execution"

PASS_DECISION = "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS"
STATE_INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_CLOSED_TRADE_STATE_INCOMPLETE"
RESIDUAL_POSITION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_RESIDUAL_OPEN_POSITION"
PNL_RECONCILIATION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PNL_RECONCILIATION_REQUIRED"
THIRD_SUBMIT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_OR_REENTRY_DETECTED"
FAILED_DECISION = "REJECT_LSR_V2_SECOND_CLOSED_TRADE_AUDIT_FAILED"

SUBMIT_EXECUTED_DECISION = "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED"
CLOSE_EXECUTED_DECISION = "LSR_V2_SECOND_SINGLE_PAPER_POSITION_CLOSED"


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


def _metadata_of(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    return dict(raw) if isinstance(raw, Mapping) else {}


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


def _is_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_lsr_second(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    source = _row_source(row)
    meta = _metadata_of(row)
    if SECOND_SOURCE_TAG in source or "SECOND" in source.upper() and "LSR" in source.upper():
        return True
    if str(row.get("profile_name") or meta.get("profile_name") or "") == PROFILE_NAME and str(row.get("trade_sequence") or meta.get("trade_sequence") or "").upper() == "SECOND":
        return True
    if cycle_id and _row_cycle(row) == cycle_id:
        return True
    return False


def _event_cycle_filter(rows: Iterable[Mapping[str, Any]], cycle_id: str) -> list[dict[str, Any]]:
    if not cycle_id:
        return [dict(r) for r in rows]
    return [dict(r) for r in rows if str(r.get("cycle_id") or _metadata_of(r).get("cycle_id") or "") == cycle_id]


def _dedupe_events(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        key = (
            row.get("event_type"),
            row.get("cycle_id"),
            row.get("symbol"),
            row.get("side"),
            row.get("order_id"),
            row.get("position_id"),
            row.get("decision"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _submit_executed(row: Mapping[str, Any]) -> bool:
    return (
        row.get("decision") == SUBMIT_EXECUTED_DECISION
        or _safe_int(row.get("orders_submitted_by_second_trade_execution"), 0) > 0
        or _safe_int(row.get("positions_opened_by_second_trade_execution"), 0) > 0
        or _safe_bool(row.get("broker_submit_called"), False)
        or _safe_bool(row.get("broker_submit_called_by_second_trade_execution"), False)
    )


def _close_executed(row: Mapping[str, Any]) -> bool:
    return (
        row.get("decision") == CLOSE_EXECUTED_DECISION
        or _safe_int(row.get("positions_closed_by_second_trade_close_execution"), 0) > 0
        or _safe_bool(row.get("broker_close_called"), False)
        or _safe_bool(row.get("broker_close_called_by_second_trade_close_execution"), False)
    )


def _state_counts(state: Mapping[str, Any], *, cycle_id: str) -> dict[str, Any]:
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    lsr_orders = [r for r in orders if _is_lsr_second(r, cycle_id=cycle_id)]
    lsr_positions = [r for r in positions if _is_lsr_second(r, cycle_id=cycle_id)]
    open_positions = [r for r in lsr_positions if _is_open(r)]
    closed_positions = [r for r in lsr_positions if not _is_open(r)]
    symbols = sorted({s for s in (_row_symbol(r) for r in lsr_positions + lsr_orders) if s})
    sides = sorted({s for s in (_row_side(r) for r in lsr_positions + lsr_orders) if s})
    return {
        "matching_order_count": len(lsr_orders),
        "matching_position_count": len(lsr_positions),
        "state_open_second_lsr_v2_positions": len(open_positions),
        "state_closed_second_lsr_v2_positions": len(closed_positions),
        "symbols": symbols,
        "sides": sides,
    }


def _status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_positions") or monitor.get("open_position_count"), 0)
    return 0


def _status_pending_orders(status: Mapping[str, Any]) -> int:
    if "pending_orders" in status:
        return _safe_int(status.get("pending_orders"), 0)
    return 0


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "")
        if text:
            return text
    return ""


def build_lsr_v2_second_closed_trade_final_audit_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
) -> dict[str, Any]:
    data = Path(data_dir)
    submit_report = _read_json(data / SUBMIT_EXEC_REPORT_NAME)
    close_report = _read_json(data / CLOSE_EXEC_REPORT_NAME)
    lifecycle_report = _read_json(data / LIFECYCLE_REPORT_NAME)
    state = _read_json(data / PAPER_STATE_NAME)
    status = _read_json(data / PAPER_STATUS_NAME)

    submit_rows_all = _dedupe_events(_iter_jsonl_tail(data / SUBMIT_EXEC_JSONL_NAME))
    close_rows_all = _dedupe_events(_iter_jsonl_tail(data / CLOSE_EXEC_JSONL_NAME))

    cycle_id = _first_nonempty(
        cycle_id,
        close_report.get("cycle_id"),
        (close_rows_all[-1].get("cycle_id") if close_rows_all else ""),
        submit_report.get("cycle_id"),
        (submit_rows_all[-1].get("cycle_id") if submit_rows_all else ""),
        lifecycle_report.get("cycle_id"),
    )

    submit_rows = _event_cycle_filter(submit_rows_all, cycle_id)
    close_rows = _event_cycle_filter(close_rows_all, cycle_id)
    executed_submit_rows = [r for r in submit_rows if _submit_executed(r)]
    executed_close_rows = [r for r in close_rows if _close_executed(r)]

    submit_report_executed = _submit_executed(submit_report)
    close_report_executed = _close_executed(close_report)
    submit_execution_events = max(len(executed_submit_rows), 1 if submit_report_executed else 0)
    close_execution_events = max(len(executed_close_rows), 1 if close_report_executed else 0)

    state_counts = _state_counts(state, cycle_id=cycle_id)
    status_open = _status_open_positions(status)
    status_pending = _status_pending_orders(status)

    realized_pnl = _round(
        close_report.get("realized_pnl_total")
        if close_report.get("realized_pnl_total") not in (None, "")
        else (executed_close_rows[-1].get("realized_pnl_total") if executed_close_rows else 0.0)
    )
    total_risk = _round(
        close_report.get("total_risk_amount")
        if close_report.get("total_risk_amount") not in (None, "")
        else submit_report.get("total_risk_amount")
    )
    total_notional = _round(
        close_report.get("total_notional")
        if close_report.get("total_notional") not in (None, "")
        else submit_report.get("total_notional")
    )
    realized_r = _round(realized_pnl / total_risk, 10) if total_risk > 0 else 0.0

    residual_open_position = state_counts["state_open_second_lsr_v2_positions"] > 0 or status_open > 0
    paper_state_consistency = state_counts["matching_position_count"] >= 1 and state_counts["state_open_second_lsr_v2_positions"] == 0
    paper_status_consistency = status_open == 0 and status_pending == 0
    pnl_reconciliation_ok = close_report_executed and abs(realized_pnl) > 0 and (total_risk > 0) and (realized_r != 0)
    second_trade_complete = submit_execution_events == 1 and close_execution_events == 1 and paper_state_consistency and paper_status_consistency and pnl_reconciliation_ok

    submit_multiple_detected = submit_execution_events > 1
    close_multiple_detected = close_execution_events > 1
    third_submit_or_reentry_detected = submit_multiple_detected or state_counts["state_open_second_lsr_v2_positions"] > 0

    blockers: list[str] = []
    if submit_execution_events < 1:
        blockers.append("second_submit_execution_missing")
    if close_execution_events < 1:
        blockers.append("second_close_execution_missing")
    if submit_multiple_detected:
        blockers.append("multiple_second_submit_executions_detected")
    if close_multiple_detected:
        blockers.append("multiple_second_close_executions_detected")
    if residual_open_position:
        blockers.append("residual_open_position")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if not pnl_reconciliation_ok:
        blockers.append("pnl_reconciliation_required")

    live_enabled = _safe_bool(submit_report.get("live_enabled"), False) or _safe_bool(close_report.get("live_enabled"), False)
    testnet_enabled = _safe_bool(submit_report.get("testnet_enabled"), False) or _safe_bool(close_report.get("testnet_enabled"), False)
    exchange_broker_enabled = _safe_bool(submit_report.get("exchange_broker_enabled"), False) or _safe_bool(close_report.get("exchange_broker_enabled"), False)
    operational_unlock_allowed = _safe_bool(submit_report.get("operational_unlock_allowed"), False) or _safe_bool(close_report.get("operational_unlock_allowed"), False)
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if operational_unlock_allowed:
        blockers.append("operational_unlock_allowed")

    if live_enabled or testnet_enabled or exchange_broker_enabled or operational_unlock_allowed:
        decision = FAILED_DECISION
        status_text = "FAIL"
    elif third_submit_or_reentry_detected:
        decision = THIRD_SUBMIT_DECISION
        status_text = "WARN"
    elif residual_open_position:
        decision = RESIDUAL_POSITION_DECISION
        status_text = "WARN"
    elif not pnl_reconciliation_ok:
        decision = PNL_RECONCILIATION_DECISION
        status_text = "WARN"
    elif not second_trade_complete:
        decision = STATE_INCOMPLETE_DECISION
        status_text = "WARN"
    else:
        decision = PASS_DECISION
        status_text = "PASS"

    labels: list[str] = []
    if decision == PASS_DECISION:
        labels = ["SECOND_CLOSED_TRADE_AUDIT_PASS", "NO_RESIDUAL_POSITION", "REALIZED_PNL_RECONCILED", "THIRD_TRADE_NOT_ALLOWED"]
    else:
        if residual_open_position:
            labels.append("RESIDUAL_POSITION_PRESENT")
        if not pnl_reconciliation_ok:
            labels.append("PNL_RECONCILIATION_REQUIRED")
        if third_submit_or_reentry_detected:
            labels.append("THIRD_SUBMIT_OR_REENTRY_DETECTED")

    report = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "ts": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "cycle_id": cycle_id,
        "second_closed_trade_complete": bool(second_trade_complete),
        "submit_executed": submit_execution_events == 1,
        "submit_execution_events": submit_execution_events,
        "submit_multiple_detected": submit_multiple_detected,
        "close_executed": close_execution_events == 1,
        "close_execution_events": close_execution_events,
        "close_multiple_detected": close_multiple_detected,
        "close_reasons": close_report.get("close_reasons") or (executed_close_rows[-1].get("close_reasons") if executed_close_rows else []),
        "realized_pnl_total": realized_pnl,
        "realized_r": realized_r,
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "pnl_reconciliation_ok": pnl_reconciliation_ok,
        "residual_open_position": residual_open_position,
        "state_open_second_lsr_v2_positions": state_counts["state_open_second_lsr_v2_positions"],
        "state_closed_second_lsr_v2_positions": state_counts["state_closed_second_lsr_v2_positions"],
        "matching_order_count": state_counts["matching_order_count"],
        "matching_position_count": state_counts["matching_position_count"],
        "paper_state_consistency": paper_state_consistency,
        "paper_status_consistency": paper_status_consistency,
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "symbols": state_counts["symbols"],
        "sides": state_counts["sides"],
        "third_submit_or_reentry_detected": third_submit_or_reentry_detected,
        "third_trade_allowed": False,
        "next_step_observation_required": decision == PASS_DECISION,
        "orders_submitted_by_second_final_audit": 0,
        "positions_opened_by_second_final_audit": 0,
        "positions_closed_by_second_final_audit": 0,
        "broker_submit_called_by_second_final_audit": False,
        "broker_close_called_by_second_final_audit": False,
        "paper_state_modified_by_second_final_audit": False,
        "paper_status_modified_by_second_final_audit": False,
        "automatic_reentry_enabled": False,
        "automatic_close_enabled": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": False,
        "report": str(data / REPORT_NAME),
        "jsonl": str(data / JSONL_NAME),
    }

    _write_json(data / REPORT_NAME, report)
    _append_jsonl(data / JSONL_NAME, report)
    return report
