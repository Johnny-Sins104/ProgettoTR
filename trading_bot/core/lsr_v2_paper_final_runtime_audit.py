"""Patch 30.3.0E - final paper runtime lifecycle audit.

This audit is deliberately read-only.  It reconstructs the first supervised
LSR-v2 paper trade from persisted local runtime artifacts and classifies
missing tail lifecycle events without mutating paper state or status.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore


PROMPT_ID = "30.3.0E"
EVENT_TYPE = "LSR_V2_PAPER_FINAL_RUNTIME_AUDIT"
REPORT_NAME = "lsr_v2_paper_final_runtime_audit_report.json"
JSONL_NAME = "lsr_v2_paper_final_runtime_audit.jsonl"

PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"
PAPER_LIFECYCLE_REPORT_NAME = "paper_lifecycle_report.json"
PAPER_READINESS_REPORT_NAME = "paper_readiness_report.json"

SUBMIT_REPORT_NAME = "lsr_v2_supervised_paper_submit_execution_report.json"
SUBMIT_JSONL_NAME = "lsr_v2_supervised_paper_submit_execution.jsonl"
STATUS_RECONCILIATION_REPORT_NAME = "lsr_v2_paper_status_reconciliation_report.json"
OPEN_MONITOR_REPORT_NAME = "lsr_v2_open_position_monitor_report.json"
POSITION_LIFECYCLE_REPORT_NAME = "lsr_v2_paper_position_lifecycle_report.json"
TELEGRAM_AUDIT_NAME = "telegram_audit.jsonl"

PASS_DECISION = "LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_PASS"
WARN_DECISION = "LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_WARN_NON_BLOCKING"
OPEN_POSITION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OPEN_POSITION_MONITOR_REQUIRED"
REJECT_DECISION = "REJECT_LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_FAILED"

SOURCE_TAG = "lsr_v2_supervised_paper_submit_execution"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"__read_error__": str(exc)}
    return data if isinstance(data, dict) else {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(payload), sort_keys=True) + "\n")


def _iter_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)


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


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("metadata")
    if isinstance(raw, Mapping):
        return raw
    raw = row.get("meta")
    return raw if isinstance(raw, Mapping) else {}


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


def _row_id(row: Mapping[str, Any], *fields: str) -> str:
    meta = _metadata(row)
    for field in fields:
        value = row.get(field) or meta.get(field)
        if value not in {None, ""}:
            return str(value)
    return ""


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(
        row.get("paper_order_source")
        or row.get("execution_source")
        or row.get("source")
        or meta.get("paper_order_source")
        or meta.get("execution_source")
        or meta.get("source")
        or ""
    )


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("symbol") or meta.get("symbol") or "")


def _row_side(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    text = str(row.get("side") or row.get("direction") or meta.get("side") or "").upper()
    if text == "LONG":
        return "BUY"
    if text == "SHORT":
        return "SELL"
    return text


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    return _status_text(row, "FILLED") in {"NEW", "OPEN", "PENDING", "PLACED", "SUBMITTED", "ACCEPTED"}


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    source = _row_source(row).lower()
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    return (
        "lsr_v2" in source
        or SOURCE_TAG in source
        or profile == PROFILE_NAME
        or overlay == SELECTED_OVERLAY_ID
        or bool(_row_cycle(row))
    )


def _event_type(row: Mapping[str, Any]) -> str:
    return str(row.get("event_type") or "").upper()


def _contains_identifier(row: Mapping[str, Any], identifier: str) -> bool:
    if not identifier:
        return False
    if any(str(row.get(field) or "") == identifier for field in ("order_id", "position_id", "id")):
        return True
    for key in ("order", "position", "submit_result", "payload"):
        raw = row.get(key)
        if isinstance(raw, Mapping) and any(str(raw.get(field) or "") == identifier for field in ("order_id", "position_id", "id")):
            return True
    return False


def _find_event(rows: Iterable[Mapping[str, Any]], identifier: str, event_types: set[str]) -> dict[str, Any]:
    for row in rows:
        if _event_type(row) in event_types and _contains_identifier(row, identifier):
            return dict(row)
    return {}


def _find_alias_event(rows: Iterable[Mapping[str, Any]], identifier: str, event_type_tokens: tuple[str, ...]) -> dict[str, Any]:
    for row in rows:
        etype = _event_type(row)
        if any(token in etype for token in event_type_tokens) and _contains_identifier(row, identifier):
            return dict(row)
    return {}


def _latest_event_with_cycle(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    latest = {}
    for row in rows:
        if row.get("cycle_id"):
            latest = dict(row)
    return latest


def _recursive_any_true(payloads: Iterable[Any], keys: set[str]) -> bool:
    for payload in payloads:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                if key in keys and _safe_bool(value, False):
                    return True
                if isinstance(value, (Mapping, list)) and _recursive_any_true([value], keys):
                    return True
        elif isinstance(payload, list):
            if _recursive_any_true(payload, keys):
                return True
    return False


def _paper_adapter(payload: Mapping[str, Any]) -> str:
    adapter = str(payload.get("paper_broker_adapter") or "")
    if adapter:
        return adapter
    paper_state = payload.get("paper_state")
    if isinstance(paper_state, Mapping):
        adapter = str(paper_state.get("paper_broker_adapter") or "")
    return adapter


def _real_broker_called(payloads: Iterable[Mapping[str, Any]], call_keys: set[str]) -> bool:
    for payload in payloads:
        called = any(_safe_bool(payload.get(key), False) for key in call_keys)
        if not called:
            continue
        if _safe_bool(payload.get("exchange_broker_enabled"), False):
            return True
        adapter = _paper_adapter(payload)
        if adapter and adapter != "PaperBrokerAdapter":
            return True
    return False


def _state_status_consistency(
    *,
    orders: list[dict[str, Any]],
    positions: list[dict[str, Any]],
    state: Mapping[str, Any],
    status: Mapping[str, Any],
    tolerance: float = 1e-6,
) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    state_open_positions = sum(1 for row in positions if _is_position_open(row))
    state_pending_orders = sum(1 for row in orders if _is_order_pending(row))
    status_open_positions = _safe_int(status.get("open_positions"), state_open_positions)
    status_pending_orders = _safe_int(status.get("pending_orders"), state_pending_orders)
    if state_open_positions != status_open_positions:
        warnings.append(f"open_positions_mismatch_state_status: state={state_open_positions} status={status_open_positions}")
    if state_pending_orders != status_pending_orders:
        warnings.append(f"pending_orders_mismatch_state_status: state={state_pending_orders} status={status_pending_orders}")
    state_balance = state.get("balance")
    status_balance = status.get("balance")
    if isinstance(state_balance, (int, float)) and isinstance(status_balance, (int, float)):
        if abs(float(state_balance) - float(status_balance)) > tolerance:
            warnings.append(f"balance_mismatch_state_status: state={state_balance} status={status_balance}")
    state_unrealized = 0.0 if state_open_positions == 0 else _safe_float(state.get("unrealized_pnl"), 0.0)
    status_unrealized = _safe_float(status.get("unrealized_pnl"), state_unrealized)
    if abs(state_unrealized - status_unrealized) > tolerance and state_open_positions == 0:
        warnings.append(f"unrealized_pnl_mismatch_state_status: state={state_unrealized} status={status_unrealized}")
    return not warnings, warnings


def _classify_lifecycle_warnings(
    *,
    lifecycle_warnings: list[str],
    orders_by_id: Mapping[str, Mapping[str, Any]],
    positions_by_id: Mapping[str, Mapping[str, Any]],
    paper_events: list[dict[str, Any]],
    submit_events: list[dict[str, Any]],
    telegram_events: list[dict[str, Any]],
) -> dict[str, Any]:
    classification: dict[str, list[str]] = {
        "true_missing_event": [],
        "tail_window_incomplete": [],
        "event_type_alias_mismatch": [],
        "state_derived_close_accepted": [],
        "state_derived_fill_accepted": [],
    }
    for warning in lifecycle_warnings:
        if warning.startswith("closed_position_missing_close_event:"):
            position_id = warning.split(":", 1)[1].strip()
            position = positions_by_id.get(position_id, {})
            canonical = _find_event(paper_events, position_id, {"POSITION_CLOSED", "PAPER_POSITION_CLOSED"})
            alias = _find_alias_event(telegram_events, position_id, ("POSITION_CLOSE", "POSITION_CLOSED", "SL_NOTIFICATION", "TP_NOTIFICATION"))
            if canonical:
                classification["event_type_alias_mismatch"].append(warning)
            elif _status_text(position) == "CLOSED":
                classification["tail_window_incomplete"].append(warning)
                classification["state_derived_close_accepted"].append(warning)
                if alias:
                    classification["event_type_alias_mismatch"].append(warning)
            else:
                classification["true_missing_event"].append(warning)
        elif warning.startswith("filled_order_missing_fill_event:"):
            order_id = warning.split(":", 1)[1].strip()
            order = orders_by_id.get(order_id, {})
            canonical = _find_event(paper_events, order_id, {"ORDER_FILLED", "PAPER_ORDER_FILLED"})
            alias = _find_alias_event(submit_events, order_id, ("SUBMIT_EXECUTION", "PAPER_SUBMIT"))
            if canonical:
                classification["event_type_alias_mismatch"].append(warning)
            elif _status_text(order) == "FILLED":
                classification["tail_window_incomplete"].append(warning)
                classification["state_derived_fill_accepted"].append(warning)
                if alias:
                    classification["event_type_alias_mismatch"].append(warning)
            else:
                classification["true_missing_event"].append(warning)
        else:
            classification["true_missing_event"].append(warning)
    return {
        **classification,
        "non_blocking": not classification["true_missing_event"],
    }


def build_lsr_v2_paper_final_runtime_audit_report_from_files(
    *,
    data_dir: str | Path = "data",
    max_event_lines: int = 50000,
) -> dict[str, Any]:
    base = Path(data_dir)
    state = _read_json(base / PAPER_STATE_NAME)
    status = _read_json(base / PAPER_STATUS_NAME)
    readiness = _read_json(base / PAPER_READINESS_REPORT_NAME)
    lifecycle_report = _read_json(base / PAPER_LIFECYCLE_REPORT_NAME)
    submit_report = _read_json(base / SUBMIT_REPORT_NAME)
    status_reconciliation_report = _read_json(base / STATUS_RECONCILIATION_REPORT_NAME)
    open_monitor_report = _read_json(base / OPEN_MONITOR_REPORT_NAME)
    position_lifecycle_report = _read_json(base / POSITION_LIFECYCLE_REPORT_NAME)
    paper_events = _iter_tail(base / PAPER_EVENTS_NAME, max_lines=max_event_lines)
    submit_events = _iter_tail(base / SUBMIT_JSONL_NAME, max_lines=max_event_lines)
    telegram_events = _iter_tail(base / TELEGRAM_AUDIT_NAME, max_lines=max_event_lines)

    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    orders_by_id = {_row_id(row, "order_id", "id"): row for row in orders if _row_id(row, "order_id", "id")}
    positions_by_id = {_row_id(row, "position_id", "id"): row for row in positions if _row_id(row, "position_id", "id")}
    lsr_orders = [row for row in orders if _is_lsr_v2_row(row)]
    lsr_positions = [row for row in positions if _is_lsr_v2_row(row)]

    selected_order = lsr_orders[0] if lsr_orders else (orders[0] if orders else {})
    selected_position = lsr_positions[0] if lsr_positions else (positions[0] if positions else {})
    order_id = _row_id(selected_order, "order_id", "id")
    position_id = _row_id(selected_position, "position_id", "id")
    cycle_id = (
        _row_cycle(selected_position)
        or _row_cycle(selected_order)
        or str(submit_report.get("cycle_id") or "")
        or str(position_lifecycle_report.get("cycle_id") or "")
        or str(_latest_event_with_cycle(paper_events).get("cycle_id") or "")
    )

    state_open_positions = sum(1 for row in positions if _is_position_open(row))
    state_pending_orders = sum(1 for row in orders if _is_order_pending(row))
    status_open_positions = _safe_int(status.get("open_positions"), state_open_positions)
    status_pending_orders = _safe_int(status.get("pending_orders"), state_pending_orders)
    if state_open_positions > 0 or status_open_positions > 0:
        final_state = "OPEN_POSITION"
    elif any(payload.get("__read_error__") for payload in (state, status)):
        final_state = "ERROR"
    else:
        final_state = "FLAT"

    canonical_fill_event = _find_event(paper_events, order_id, {"ORDER_FILLED", "PAPER_ORDER_FILLED"})
    alias_fill_event = _find_alias_event(submit_events, order_id, ("SUBMIT_EXECUTION", "PAPER_SUBMIT"))
    canonical_close_event = _find_event(paper_events, position_id, {"POSITION_CLOSED", "PAPER_POSITION_CLOSED"})
    alias_close_event = _find_alias_event(telegram_events, position_id, ("POSITION_CLOSE", "POSITION_CLOSED", "SL_NOTIFICATION", "TP_NOTIFICATION"))

    lifecycle_warnings = []
    raw_lifecycle_warnings = lifecycle_report.get("reconciliation", {}).get("warnings") if isinstance(lifecycle_report.get("reconciliation"), Mapping) else lifecycle_report.get("warnings")
    if isinstance(raw_lifecycle_warnings, list):
        lifecycle_warnings = [str(item) for item in raw_lifecycle_warnings]
    classification = _classify_lifecycle_warnings(
        lifecycle_warnings=lifecycle_warnings,
        orders_by_id=orders_by_id,
        positions_by_id=positions_by_id,
        paper_events=paper_events,
        submit_events=submit_events,
        telegram_events=telegram_events,
    )

    paper_state_status_consistent, state_status_warnings = _state_status_consistency(
        orders=orders,
        positions=positions,
        state=state,
        status=status,
    )

    safety_payloads = [status, readiness, submit_report, status_reconciliation_report, open_monitor_report, position_lifecycle_report]
    live_mode_enabled = _recursive_any_true(safety_payloads, {"live_enabled", "live_mode_enabled", "live_execution_enabled"})
    testnet_mode_enabled = _recursive_any_true(safety_payloads, {"testnet_enabled", "testnet_mode_enabled"})
    exchange_broker_enabled = _recursive_any_true(safety_payloads, {"exchange_broker_enabled", "exchange_broker_allowed"})
    broker_submit_real_called = _real_broker_called(
        [p for p in safety_payloads if isinstance(p, Mapping)],
        {"broker_submit_real_called", "exchange_broker_submit_called", "real_broker_submit_called"},
    )
    broker_close_real_called = _real_broker_called(
        [p for p in safety_payloads if isinstance(p, Mapping)],
        {"broker_close_real_called", "exchange_broker_close_called", "real_broker_close_called"},
    )

    extra_orders = len(orders) > 1 or len(lsr_orders) > 1
    extra_positions = len(positions) > 1 or len(lsr_positions) > 1
    order_filled = _status_text(selected_order) == "FILLED"
    position_opened = bool(selected_position)
    position_closed = _status_text(selected_position) == "CLOSED"
    close_reason = str(selected_position.get("close_reason") or "")
    runtime_source = str(status.get("market_data_mode") or "")
    if not runtime_source:
        for event in reversed(paper_events):
            if event.get("market_data_mode"):
                runtime_source = str(event.get("market_data_mode"))
                break
            if _event_type(event) == "MARKET_DATA_CACHE_USED" and event.get("mode"):
                runtime_source = str(event.get("mode"))
                break

    blockers: list[str] = []
    if state.get("__read_error__"):
        blockers.append("paper_state_read_error")
    if status.get("__read_error__"):
        blockers.append("paper_status_read_error")
    if not paper_state_status_consistent:
        blockers.append("paper_state_status_divergence")
    if extra_orders:
        blockers.append("extra_order_detected")
    if extra_positions:
        blockers.append("extra_position_detected")
    if orders and not order_filled:
        blockers.append("selected_order_not_filled")
    if positions and not (position_opened and (position_closed or _is_position_open(selected_position))):
        blockers.append("selected_position_invalid_status")
    if live_mode_enabled:
        blockers.append("live_mode_enabled")
    if testnet_mode_enabled:
        blockers.append("testnet_mode_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if broker_submit_real_called:
        blockers.append("broker_submit_real_called")
    if broker_close_real_called:
        blockers.append("broker_close_real_called")
    if classification["true_missing_event"]:
        blockers.append("true_missing_lifecycle_event")

    if blockers:
        audit_status = "FAIL"
        decision = REJECT_DECISION
        recommendation = "stop_and_fix"
    elif final_state == "OPEN_POSITION":
        audit_status = "WARN"
        decision = OPEN_POSITION_DECISION
        recommendation = "open_position_monitor_required"
    elif lifecycle_warnings:
        audit_status = "WARN"
        decision = WARN_DECISION
        recommendation = "proceed_to_pnl_reconciliation"
    else:
        audit_status = "PASS"
        decision = PASS_DECISION
        recommendation = "proceed_to_pnl_reconciliation"

    last_event = dict(paper_events[-1]) if paper_events else {}
    last_cycle_event = _latest_event_with_cycle(paper_events)
    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": audit_status,
        "decision": decision,
        "final_state": final_state,
        "recommendation": recommendation,
        "blockers": sorted(set(blockers)),
        "cycle_id": cycle_id,
        "latest_cycle_id": str(last_cycle_event.get("cycle_id") or cycle_id),
        "latest_paper_event_type": str(last_event.get("event_type") or ""),
        "order_id": order_id,
        "position_id": position_id,
        "symbol": _row_symbol(selected_position) or _row_symbol(selected_order),
        "side": _row_side(selected_position) or _row_side(selected_order),
        "order_lifecycle": {
            "submitted": bool(submit_report.get("orders_submitted_by_lsr_v2_execution") or alias_fill_event or order_id),
            "filled": bool(order_filled),
            "status": _status_text(selected_order),
            "fill_event_found": bool(canonical_fill_event),
            "fill_event_source": "paper_events" if canonical_fill_event else "paper_state" if order_filled else "",
            "alias_event_found": bool(alias_fill_event),
            "alias_event_source": "lsr_v2_supervised_paper_submit_execution.jsonl" if alias_fill_event else "",
        },
        "position_lifecycle": {
            "opened": bool(position_opened),
            "closed": bool(position_closed),
            "status": _status_text(selected_position),
            "close_event_found": bool(canonical_close_event),
            "close_event_source": "paper_events" if canonical_close_event else "paper_state" if position_closed else "",
            "alias_event_found": bool(alias_close_event),
            "alias_event_source": "telegram_audit.jsonl" if alias_close_event else "",
            "close_reason": close_reason,
        },
        "paper_state_status_consistent": bool(paper_state_status_consistent),
        "paper_state_status_warnings": state_status_warnings,
        "lifecycle_warnings": lifecycle_warnings,
        "lifecycle_warning_classification": classification,
        "safety_flags": {
            "live_mode_enabled": bool(live_mode_enabled),
            "testnet_mode_enabled": bool(testnet_mode_enabled),
            "exchange_broker_enabled": bool(exchange_broker_enabled),
            "broker_submit_real_called": bool(broker_submit_real_called),
            "broker_close_real_called": bool(broker_close_real_called),
        },
        "runtime_source": runtime_source,
        "runtime": {
            "market_data_mode": runtime_source,
            "mode": str(status.get("mode") or "paper"),
            "max_cycles_reached": any(_event_type(event) == "MAX_CYCLES_REACHED" for event in paper_events),
        },
        "counts": {
            "orders_submitted": len(orders),
            "positions_opened": len(positions),
            "positions_closed": sum(1 for row in positions if _status_text(row) == "CLOSED"),
            "open_positions": state_open_positions,
            "pending_orders": state_pending_orders,
            "status_open_positions": status_open_positions,
            "status_pending_orders": status_pending_orders,
            "lsr_v2_orders": len(lsr_orders),
            "lsr_v2_positions": len(lsr_positions),
        },
        "pnl_snapshot": {
            "realized_pnl": _round(state.get("realized_pnl")),
            "unrealized_pnl": _round(status.get("unrealized_pnl")),
            "position_realized_pnl": _round(selected_position.get("realized_pnl")),
            "fees_paid": _round(selected_position.get("fees_paid")),
            "balance": _round(state.get("balance")),
            "equity": _round(status.get("equity")),
        },
        "trade": {
            "entry_price": _round(selected_position.get("entry_price") or selected_order.get("filled_price") or selected_order.get("requested_price")),
            "exit_price": _round(selected_position.get("exit_price")),
            "stop_loss": _round(selected_position.get("stop_loss") or selected_order.get("stop_loss")),
            "take_profit": _round(selected_position.get("take_profit") or selected_order.get("take_profit")),
            "quantity": _round(selected_position.get("qty") or selected_order.get("qty")),
            "close_reason": close_reason,
        },
        "read_only_safety": {
            "paper_state_modified_by_audit": False,
            "paper_status_modified_by_audit": False,
            "orders_submitted_by_audit": 0,
            "positions_opened_by_audit": 0,
            "positions_closed_by_audit": 0,
            "scheduler_started_by_audit": False,
            "broker_submit_called_by_audit": False,
            "broker_close_called_by_audit": False,
            "live_enabled_by_audit": False,
            "testnet_enabled_by_audit": False,
            "exchange_broker_enabled_by_audit": False,
        },
        "files": {
            "paper_state": str(base / PAPER_STATE_NAME),
            "paper_status": str(base / PAPER_STATUS_NAME),
            "paper_events": str(base / PAPER_EVENTS_NAME),
            "paper_lifecycle_report": str(base / PAPER_LIFECYCLE_REPORT_NAME),
            "report": str(base / REPORT_NAME),
            "jsonl": str(base / JSONL_NAME),
        },
    }
    _write_json(base / REPORT_NAME, report)
    _append_jsonl(base / JSONL_NAME, {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "status": audit_status,
        "decision": decision,
        "final_state": final_state,
        "cycle_id": cycle_id,
        "order_id": order_id,
        "position_id": position_id,
        "paper_state_status_consistent": bool(paper_state_status_consistent),
        "lifecycle_warning_count": len(lifecycle_warnings),
        "true_missing_lifecycle_event_count": len(classification["true_missing_event"]),
        "recommendation": recommendation,
        "live_mode_enabled": bool(live_mode_enabled),
        "testnet_mode_enabled": bool(testnet_mode_enabled),
        "exchange_broker_enabled": bool(exchange_broker_enabled),
        "broker_submit_real_called": bool(broker_submit_real_called),
        "broker_close_real_called": bool(broker_close_real_called),
        "orders_submitted_by_audit": 0,
        "positions_opened_by_audit": 0,
        "positions_closed_by_audit": 0,
    })
    return report


__all__ = [
    "EVENT_TYPE",
    "REPORT_NAME",
    "JSONL_NAME",
    "PASS_DECISION",
    "WARN_DECISION",
    "OPEN_POSITION_DECISION",
    "REJECT_DECISION",
    "build_lsr_v2_paper_final_runtime_audit_report_from_files",
]
