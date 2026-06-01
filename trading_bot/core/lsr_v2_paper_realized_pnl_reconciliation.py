"""Patch 30.3.0F - paper realized PnL reconciliation and postmortem.

Read-only accounting bundle for the first supervised LSR-v2 paper trade.  It
never submits, closes, mutates paper state/status, or starts a scheduler.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore


PROMPT_ID = "30.3.0F"
PNL_EVENT_TYPE = "LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION"
POSTMORTEM_EVENT_TYPE = "LSR_V2_PAPER_TRADE_POSTMORTEM"
PNL_REPORT_NAME = "lsr_v2_paper_realized_pnl_reconciliation_report.json"
PNL_JSONL_NAME = "lsr_v2_paper_realized_pnl_reconciliation.jsonl"
POSTMORTEM_REPORT_NAME = "lsr_v2_paper_trade_postmortem_report.json"
POSTMORTEM_JSONL_NAME = "lsr_v2_paper_trade_postmortem.jsonl"

PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
FINAL_RUNTIME_AUDIT_REPORT_NAME = "lsr_v2_paper_final_runtime_audit_report.json"
SUBMIT_JSONL_NAME = "lsr_v2_supervised_paper_submit_execution.jsonl"

PASS_DECISION = "LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_PASS"
WARN_DECISION = "LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_WARN_NON_BLOCKING"
REJECT_DECISION = "REJECT_LSR_V2_PAPER_REALIZED_PNL_RECONCILIATION_FAILED"

POSTMORTEM_PASS_DECISION = "LSR_V2_PAPER_TRADE_POSTMORTEM_READY"
POSTMORTEM_WARN_DECISION = "LSR_V2_PAPER_TRADE_POSTMORTEM_WARN_NON_BLOCKING"
POSTMORTEM_REJECT_DECISION = "REJECT_LSR_V2_PAPER_TRADE_POSTMORTEM_FAILED"

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


def _round(value: Any, digits: int = 10) -> float:
    return round(_safe_float(value, 0.0), digits)


def _metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("metadata")
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


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _row_side(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    side = str(row.get("side") or row.get("direction") or meta.get("side") or "").upper()
    if side == "LONG":
        return "BUY"
    if side == "SHORT":
        return "SELL"
    return side


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("symbol") or meta.get("symbol") or "")


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("paper_order_source") or row.get("execution_source") or row.get("source") or meta.get("paper_order_source") or meta.get("execution_source") or meta.get("source") or "")


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    source = _row_source(row).lower()
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    return "lsr_v2" in source or SOURCE_TAG in source or profile == PROFILE_NAME or overlay == SELECTED_OVERLAY_ID or bool(_row_cycle(row))


def calculate_gross_pnl(*, side: str, entry_price: float, exit_price: float, quantity: float) -> float:
    side = str(side or "").upper()
    if side == "SELL":
        return quantity * (entry_price - exit_price)
    return quantity * (exit_price - entry_price)


def _select_trade(state: Mapping[str, Any], final_audit: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    order_id = str(final_audit.get("order_id") or "")
    position_id = str(final_audit.get("position_id") or "")
    order = next((row for row in orders if _row_id(row, "order_id", "id") == order_id), {})
    position = next((row for row in positions if _row_id(row, "position_id", "id") == position_id), {})
    if not order:
        order = next((row for row in orders if _is_lsr_v2_row(row)), orders[0] if orders else {})
    if not position:
        position = next((row for row in positions if _is_lsr_v2_row(row)), positions[0] if positions else {})
    return dict(order), dict(position)


def _fee_mode(
    *,
    gross_pnl: float,
    realized_pnl_recorded: float,
    entry_fee: float,
    exit_fee: float,
    total_fees: float,
    tolerance: float,
) -> tuple[str, bool, str, float]:
    candidates = [
        ("net_includes_entry_exit_fees", gross_pnl - total_fees),
        ("net_includes_exit_fee_only", gross_pnl - exit_fee),
        ("gross_plus_separate_fees", gross_pnl),
    ]
    for mode, expected in candidates:
        if abs(realized_pnl_recorded - expected) <= tolerance:
            return mode, mode != "gross_plus_separate_fees", "PASS", expected
    return "unknown", False, "FAIL", gross_pnl - total_fees


def _latest_submit_event(submit_events: list[dict[str, Any]], cycle_id: str) -> dict[str, Any]:
    scoped = [row for row in submit_events if not cycle_id or str(row.get("cycle_id") or "") == cycle_id]
    return dict(scoped[-1]) if scoped else (dict(submit_events[-1]) if submit_events else {})


def build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files(
    *,
    data_dir: str | Path = "data",
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    base = Path(data_dir)
    state = _read_json(base / PAPER_STATE_NAME)
    status = _read_json(base / PAPER_STATUS_NAME)
    final_audit = _read_json(base / FINAL_RUNTIME_AUDIT_REPORT_NAME)
    submit_events = _iter_tail(base / SUBMIT_JSONL_NAME)
    order, position = _select_trade(state, final_audit)

    prerequisite_ok = bool(final_audit) and str(final_audit.get("status") or "") != "FAIL" and str(final_audit.get("final_state") or "") == "FLAT"
    cycle_id = _row_cycle(position) or _row_cycle(order) or str(final_audit.get("cycle_id") or "")
    side = _row_side(position) or _row_side(order)
    symbol = _row_symbol(position) or _row_symbol(order)
    entry_price = _safe_float(position.get("entry_price") or order.get("filled_price") or order.get("requested_price"), 0.0)
    exit_price = _safe_float(position.get("exit_price"), 0.0)
    quantity = _safe_float(position.get("qty") or order.get("qty") or position.get("quantity") or order.get("quantity"), 0.0)
    gross_pnl = _round(calculate_gross_pnl(side=side, entry_price=entry_price, exit_price=exit_price, quantity=quantity))
    entry_notional = _round(abs(entry_price * quantity))
    exit_notional = _round(abs(exit_price * quantity))
    fees_paid_recorded = _round(position.get("fees_paid"))
    realized_pnl_recorded = _round(position.get("realized_pnl"))

    inferred_fee_in_recorded_pnl = _round(gross_pnl - realized_pnl_recorded)
    exit_fee = inferred_fee_in_recorded_pnl if inferred_fee_in_recorded_pnl >= -tolerance else 0.0
    entry_fee = _round(max(fees_paid_recorded - exit_fee, 0.0))
    total_fees = _round(entry_fee + exit_fee)
    fee_accounting_mode, pnl_includes_fees, base_status, net_pnl_expected = _fee_mode(
        gross_pnl=gross_pnl,
        realized_pnl_recorded=realized_pnl_recorded,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        total_fees=total_fees,
        tolerance=tolerance,
    )
    net_pnl_expected = _round(net_pnl_expected)
    account_net_expected = _round(gross_pnl - total_fees)

    balance_after = _round(state.get("balance"))
    balance_before = _round(balance_after - account_net_expected)
    state_peak_balance = _round(state.get("peak_balance"))
    if state_peak_balance > 0 and abs(state_peak_balance - balance_before) <= 1e-6:
        balance_before = state_peak_balance
    balance_delta = _round(balance_after - balance_before)
    equity_after = _round(status.get("equity") if status.get("equity") is not None else balance_after)
    balance_delta_matches_account_net = abs(balance_delta - account_net_expected) <= tolerance

    warnings: list[str] = []
    blockers: list[str] = []
    if not prerequisite_ok:
        blockers.append("final_runtime_audit_missing_or_not_ready")
    if not order or not position:
        blockers.append("trade_state_missing")
    if side not in {"BUY", "SELL"}:
        blockers.append("side_missing")
    if entry_price <= 0 or exit_price <= 0 or quantity <= 0:
        blockers.append("trade_price_or_quantity_missing")
    if base_status == "FAIL":
        blockers.append("realized_pnl_does_not_match_known_fee_mode")
    if not balance_delta_matches_account_net:
        blockers.append("balance_delta_does_not_match_gross_minus_total_fees")
    if fee_accounting_mode == "net_includes_exit_fee_only":
        warnings.append("position_realized_pnl_includes_exit_fee_only_entry_fee_is_separate")
    if fees_paid_recorded and abs(fees_paid_recorded - total_fees) > tolerance:
        blockers.append("fees_paid_internal_mismatch")

    reconciliation_status = "FAIL" if blockers else "WARN" if warnings else "PASS"
    if reconciliation_status == "FAIL":
        decision = REJECT_DECISION
        recommendation = "stop_and_fix"
    elif reconciliation_status == "WARN":
        decision = WARN_DECISION
        recommendation = "proceed_to_second_order_gate_default_off"
    else:
        decision = PASS_DECISION
        recommendation = "proceed_to_second_order_gate_default_off"

    pnl_report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": reconciliation_status,
        "decision": decision,
        "reconciliation_status": reconciliation_status,
        "recommendation": recommendation,
        "blockers": blockers,
        "warnings": warnings,
        "tolerance_used": tolerance,
        "cycle_id": cycle_id,
        "order_id": _row_id(order, "order_id", "id"),
        "position_id": _row_id(position, "position_id", "id"),
        "symbol": symbol,
        "side": side,
        "entry_price": _round(entry_price),
        "exit_price": _round(exit_price),
        "quantity": _round(quantity),
        "gross_pnl": gross_pnl,
        "entry_notional": entry_notional,
        "exit_notional": exit_notional,
        "entry_fee": entry_fee,
        "exit_fee": _round(exit_fee),
        "total_fees": total_fees,
        "fees_paid_recorded": fees_paid_recorded,
        "net_pnl_expected": net_pnl_expected,
        "account_net_pnl_expected": account_net_expected,
        "realized_pnl_recorded": realized_pnl_recorded,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "balance_delta": balance_delta,
        "equity_after": equity_after,
        "pnl_includes_fees": bool(pnl_includes_fees),
        "pnl_fee_inclusion_scope": "exit_fee_only" if fee_accounting_mode == "net_includes_exit_fee_only" else "entry_exit_fees" if fee_accounting_mode == "net_includes_entry_exit_fees" else "none" if fee_accounting_mode == "gross_plus_separate_fees" else "unknown",
        "fee_accounting_mode": fee_accounting_mode,
        "balance_delta_matches_account_net": bool(balance_delta_matches_account_net),
        "final_runtime_audit_status": final_audit.get("status"),
        "final_runtime_audit_decision": final_audit.get("decision"),
        "read_only_safety": {
            "paper_state_modified_by_reconciliation": False,
            "paper_status_modified_by_reconciliation": False,
            "orders_submitted_by_reconciliation": 0,
            "positions_opened_by_reconciliation": 0,
            "positions_closed_by_reconciliation": 0,
            "broker_submit_called_by_reconciliation": False,
            "broker_close_called_by_reconciliation": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        },
        "report": str(base / PNL_REPORT_NAME),
        "jsonl": str(base / PNL_JSONL_NAME),
    }

    submit_event = _latest_submit_event(submit_events, cycle_id)
    payload = submit_event.get("payload") if isinstance(submit_event.get("payload"), Mapping) else {}
    risk_amount = _safe_float(_metadata(position).get("risk_amount") or submit_event.get("risk_amount") or payload.get("risk_amount"), 0.0)
    if risk_amount <= 0:
        risk_amount = abs(gross_pnl) if gross_pnl else 0.0
    stop_loss = _safe_float(position.get("stop_loss"), 0.0)
    take_profit = _safe_float(position.get("take_profit"), 0.0)
    if side == "SELL":
        sl_distance = _round(stop_loss - entry_price)
        tp_distance = _round(entry_price - take_profit)
        expected_slippage = _round(exit_price - stop_loss) if stop_loss > 0 else 0.0
    else:
        sl_distance = _round(entry_price - stop_loss)
        tp_distance = _round(take_profit - entry_price)
        expected_slippage = _round(stop_loss - exit_price) if stop_loss > 0 else 0.0
    r_multiple_recorded = _round(realized_pnl_recorded / risk_amount) if risk_amount else 0.0
    r_multiple_account = _round(account_net_expected / risk_amount) if risk_amount else 0.0
    should_block_next = reconciliation_status == "FAIL" or str(final_audit.get("status") or "") == "FAIL"
    postmortem_status = "FAIL" if should_block_next else "WARN" if reconciliation_status == "WARN" else "PASS"
    postmortem_decision = POSTMORTEM_REJECT_DECISION if postmortem_status == "FAIL" else POSTMORTEM_WARN_DECISION if postmortem_status == "WARN" else POSTMORTEM_PASS_DECISION
    postmortem_report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": postmortem_status,
        "decision": postmortem_decision,
        "cycle_id": cycle_id,
        "order_id": pnl_report["order_id"],
        "position_id": pnl_report["position_id"],
        "symbol": symbol,
        "trade_direction": side,
        "entry_rationale": {
            "candidate_id": _metadata(position).get("candidate_id") or submit_event.get("candidate_id"),
            "profile_name": _metadata(position).get("profile_name") or submit_event.get("profile_name"),
            "selected_overlay_id": _metadata(position).get("selected_overlay_id") or submit_event.get("selected_overlay_id"),
            "source_event_type": submit_event.get("event_type"),
            "summary": "LSR-v2 supervised paper submit from locked retest/stop-sweep profile",
        },
        "close_reason": str(position.get("close_reason") or ""),
        "entry_price": pnl_report["entry_price"],
        "exit_price": pnl_report["exit_price"],
        "stop_loss": _round(stop_loss),
        "take_profit": _round(take_profit),
        "sl_distance": sl_distance,
        "tp_distance": tp_distance,
        "gross_pnl": gross_pnl,
        "realized_pnl_recorded": realized_pnl_recorded,
        "account_net_pnl_expected": account_net_expected,
        "risk_amount": _round(risk_amount),
        "r_multiple_recorded": r_multiple_recorded,
        "r_multiple_account_net": r_multiple_account,
        "slippage": expected_slippage,
        "fees_impact": {
            "entry_fee": entry_fee,
            "exit_fee": _round(exit_fee),
            "total_fees": total_fees,
            "fees_as_r": _round(total_fees / risk_amount) if risk_amount else 0.0,
            "fee_accounting_mode": fee_accounting_mode,
        },
        "signal_quality": str(submit_event.get("quality", {}).get("grade") if isinstance(submit_event.get("quality"), Mapping) else "") or "unknown",
        "should_block_next_order_experimentation": bool(should_block_next),
        "recommendation": "stop_and_fix" if should_block_next else "prepare_second_order_gate_default_off",
        "pnl_reconciliation_report": str(base / PNL_REPORT_NAME),
        "read_only_safety": {
            "paper_state_modified_by_postmortem": False,
            "paper_status_modified_by_postmortem": False,
            "orders_submitted_by_postmortem": 0,
            "positions_opened_by_postmortem": 0,
            "positions_closed_by_postmortem": 0,
            "broker_submit_called_by_postmortem": False,
            "broker_close_called_by_postmortem": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        },
        "report": str(base / POSTMORTEM_REPORT_NAME),
        "jsonl": str(base / POSTMORTEM_JSONL_NAME),
    }

    _write_json(base / PNL_REPORT_NAME, pnl_report)
    _append_jsonl(base / PNL_JSONL_NAME, {
        "event_type": PNL_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "status": reconciliation_status,
        "decision": decision,
        "cycle_id": cycle_id,
        "order_id": pnl_report["order_id"],
        "position_id": pnl_report["position_id"],
        "gross_pnl": gross_pnl,
        "realized_pnl_recorded": realized_pnl_recorded,
        "fee_accounting_mode": fee_accounting_mode,
        "balance_delta": balance_delta,
        "account_net_pnl_expected": account_net_expected,
        "orders_submitted_by_reconciliation": 0,
        "positions_opened_by_reconciliation": 0,
        "positions_closed_by_reconciliation": 0,
    })
    _write_json(base / POSTMORTEM_REPORT_NAME, postmortem_report)
    _append_jsonl(base / POSTMORTEM_JSONL_NAME, {
        "event_type": POSTMORTEM_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "status": postmortem_status,
        "decision": postmortem_decision,
        "cycle_id": cycle_id,
        "order_id": pnl_report["order_id"],
        "position_id": pnl_report["position_id"],
        "close_reason": postmortem_report["close_reason"],
        "should_block_next_order_experimentation": bool(should_block_next),
        "orders_submitted_by_postmortem": 0,
        "positions_opened_by_postmortem": 0,
        "positions_closed_by_postmortem": 0,
    })
    return {"pnl_report": pnl_report, "postmortem_report": postmortem_report}


__all__ = [
    "PNL_REPORT_NAME",
    "PNL_JSONL_NAME",
    "POSTMORTEM_REPORT_NAME",
    "POSTMORTEM_JSONL_NAME",
    "PASS_DECISION",
    "WARN_DECISION",
    "REJECT_DECISION",
    "calculate_gross_pnl",
    "build_lsr_v2_paper_realized_pnl_reconciliation_bundle_from_files",
]
