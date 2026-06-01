"""Patch 30.3.0G - second supervised paper order execution gate.

This module prepares a diagnostic, default-off gate for a future second
supervised LSR-v2 paper order.  It never submits, closes, opens, or mutates
paper state/status.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import os

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore


PROMPT_ID = "30.3.0G"
EVENT_TYPE = "LSR_V2_SECOND_PAPER_ORDER_GATE"
REPORT_NAME = "lsr_v2_second_paper_order_gate_report.json"
JSONL_NAME = "lsr_v2_second_paper_order_gate.jsonl"

FINAL_RUNTIME_AUDIT_REPORT_NAME = "lsr_v2_paper_final_runtime_audit_report.json"
PNL_REPORT_NAME = "lsr_v2_paper_realized_pnl_reconciliation_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_paper_trade_postmortem_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"
PAPER_READINESS_REPORT_NAME = "paper_readiness_report.json"

READY_DECISION = "LSR_V2_SECOND_PAPER_ORDER_GATE_READY_DEFAULT_OFF"
OPERATOR_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_ORDER_OPERATOR_CONFIRMATION_REQUIRED"
PREREQ_BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_ORDER_PREREQUISITES_BLOCKED"
STATE_BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_ORDER_STATE_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_PAPER_ORDER_GATE_FAILED"

ARM_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_ARM"
CONFIRMATION_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_CONFIRMATION"
CONFIRMATION_PHRASE = "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER"
EXECUTE_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_EXECUTE"
EXECUTE_CONFIRMATION_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_EXECUTE_CONFIRMATION"
EXECUTE_CONFIRMATION_PHRASE = "I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY"
MAX_ORDERS_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_MAX_ORDERS"


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


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    return _status_text(row, "FILLED") in {"NEW", "OPEN", "PENDING", "PLACED", "SUBMITTED", "ACCEPTED"}


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


def _latest_candidate(paper_events: list[dict[str, Any]]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for row in paper_events:
        event_type = str(row.get("event_type") or "")
        if event_type not in {"LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT", "LSR_V2_RUNTIME_CANDIDATE_AUDIT"}:
            continue
        if _safe_bool(row.get("candidate_ready"), False) or _safe_bool(row.get("runtime_candidate_ready"), False) or _safe_bool(row.get("would_route"), False):
            selected = dict(row)
    return selected


def _operator_controls() -> dict[str, Any]:
    arm = _safe_bool(os.getenv(ARM_ENV), False)
    confirmation_ok = os.getenv(CONFIRMATION_ENV, "") == CONFIRMATION_PHRASE
    execute = _safe_bool(os.getenv(EXECUTE_ENV), False)
    execute_confirmation_ok = os.getenv(EXECUTE_CONFIRMATION_ENV, "") == EXECUTE_CONFIRMATION_PHRASE
    max_orders = _safe_int(os.getenv(MAX_ORDERS_ENV), 1)
    return {
        "arm_env": ARM_ENV,
        "confirmation_env": CONFIRMATION_ENV,
        "execute_env": EXECUTE_ENV,
        "execute_confirmation_env": EXECUTE_CONFIRMATION_ENV,
        "max_orders_env": MAX_ORDERS_ENV,
        "arm": arm,
        "confirmation_ok": confirmation_ok,
        "execute_requested": execute,
        "execute_confirmation_ok": execute_confirmation_ok,
        "max_orders": max_orders,
    }


def build_lsr_v2_second_paper_order_gate_report_from_files(
    *,
    data_dir: str | Path = "data",
    max_event_lines: int = 50000,
) -> dict[str, Any]:
    base = Path(data_dir)
    final_audit = _read_json(base / FINAL_RUNTIME_AUDIT_REPORT_NAME)
    pnl_report = _read_json(base / PNL_REPORT_NAME)
    postmortem = _read_json(base / POSTMORTEM_REPORT_NAME)
    state = _read_json(base / PAPER_STATE_NAME)
    status = _read_json(base / PAPER_STATUS_NAME)
    readiness = _read_json(base / PAPER_READINESS_REPORT_NAME)
    paper_events = _iter_tail(base / PAPER_EVENTS_NAME, max_lines=max_event_lines)
    candidate = _latest_candidate(paper_events)
    operator = _operator_controls()

    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = sum(1 for row in positions if _is_position_open(row))
    pending_orders = sum(1 for row in orders if _is_order_pending(row))
    status_open_positions = _safe_int(status.get("open_positions"), open_positions)
    status_pending_orders = _safe_int(status.get("pending_orders"), pending_orders)

    final_ok = bool(final_audit) and str(final_audit.get("status") or "") in {"PASS", "WARN"} and str(final_audit.get("decision") or "") != "REJECT_LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_FAILED"
    pnl_ok = bool(pnl_report) and str(pnl_report.get("reconciliation_status") or pnl_report.get("status") or "") in {"PASS", "WARN"}
    postmortem_ok = bool(postmortem) and str(postmortem.get("status") or "") in {"PASS", "WARN"} and not _safe_bool(postmortem.get("should_block_next_order_experimentation"), False)
    flat_ok = str(final_audit.get("final_state") or "") == "FLAT" and open_positions == 0 and status_open_positions == 0
    state_status_consistent = bool(final_audit.get("paper_state_status_consistent", True)) and open_positions == status_open_positions and pending_orders == status_pending_orders
    no_pending = pending_orders == 0 and status_pending_orders == 0
    readiness_error = str(readiness.get("status") or "").upper() == "ERROR" or str(readiness.get("decision") or "").upper() == "ERROR"
    unsafe = _recursive_any_true(
        [final_audit, pnl_report, postmortem, status],
        {"live_mode_enabled", "live_enabled", "testnet_mode_enabled", "testnet_enabled", "exchange_broker_enabled", "broker_submit_real_called", "broker_close_real_called"},
    )
    levels_for_candidate = candidate.get("levels") if isinstance(candidate.get("levels"), Mapping) else {}
    candidate_entry = _safe_float(candidate.get("entry_price") or levels_for_candidate.get("entry_price"), 0.0)
    candidate_valid = bool(candidate) and (
        _safe_bool(candidate.get("candidate_ready"), False)
        or _safe_bool(candidate.get("runtime_candidate_ready"), False)
        or _safe_bool(candidate.get("would_route"), False)
    ) and candidate_entry > 0
    runtime_values_present = bool(candidate.get("cycle_id")) and bool(candidate.get("symbol")) and bool(candidate.get("side"))
    operator_ok = bool(operator["arm"] and operator["confirmation_ok"])
    execute_blocked = bool(operator["execute_requested"] or operator["execute_confirmation_ok"])
    max_orders_ok = operator["max_orders"] == 1

    blockers: list[str] = []
    if not final_ok:
        blockers.append("final_runtime_audit_missing_or_fail")
    if not pnl_ok:
        blockers.append("pnl_reconciliation_missing_or_fail")
    if not postmortem_ok:
        blockers.append("previous_trade_postmortem_missing_or_blocking")
    if not flat_ok:
        blockers.append("final_state_not_flat")
    if open_positions > 0 or status_open_positions > 0:
        blockers.append("open_positions_not_zero")
    if not no_pending:
        blockers.append("pending_orders_not_zero")
    if not state_status_consistent:
        blockers.append("paper_state_status_divergence")
    if readiness_error:
        blockers.append("paper_readiness_error")
    if unsafe:
        blockers.append("live_testnet_exchange_or_real_broker_flag_detected")
    if not operator_ok:
        blockers.append("operator_confirmation_missing")
    if not runtime_values_present:
        blockers.append("runtime_values_missing")
    if not candidate_valid:
        blockers.append("candidate_not_valid")
    if execute_blocked:
        blockers.append("execute_env_not_allowed_in_readiness_gate")
    if not max_orders_ok:
        blockers.append("max_orders_must_be_one")

    system_ready = all(
        [
            final_ok,
            pnl_ok,
            postmortem_ok,
            flat_ok,
            no_pending,
            state_status_consistent,
            not readiness_error,
            not unsafe,
            runtime_values_present,
            candidate_valid,
            max_orders_ok,
        ]
    )
    gate_ready = system_ready and operator_ok and not execute_blocked

    if unsafe or execute_blocked:
        report_status = "FAIL"
        decision = REJECT_DECISION
    elif gate_ready:
        report_status = "PASS"
        decision = READY_DECISION
    elif any(b in blockers for b in {"final_state_not_flat", "open_positions_not_zero", "pending_orders_not_zero", "paper_state_status_divergence"}):
        report_status = "WARN"
        decision = STATE_BLOCKED_DECISION
    elif "operator_confirmation_missing" in blockers and system_ready:
        report_status = "WARN"
        decision = OPERATOR_REQUIRED_DECISION
    else:
        report_status = "WARN"
        decision = PREREQ_BLOCKED_DECISION

    levels = candidate.get("levels") if isinstance(candidate.get("levels"), Mapping) else {}
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), Mapping) else {}
    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": report_status,
        "decision": decision,
        "blockers": blockers,
        "system_ready": bool(system_ready),
        "second_order_gate_ready": bool(gate_ready),
        "second_order_execute_enabled": False,
        "second_order_submit_enabled": False,
        "cycle_id": str(candidate.get("cycle_id") or final_audit.get("latest_cycle_id") or final_audit.get("cycle_id") or ""),
        "candidate": {
            "candidate_valid": bool(candidate_valid),
            "candidate_id": str(candidate.get("candidate_id") or ""),
            "event_type": str(candidate.get("event_type") or ""),
            "symbol": str(candidate.get("symbol") or ""),
            "side": str(candidate.get("side") or ""),
            "entry_price": _safe_float(candidate.get("entry_price") or levels.get("entry_price"), 0.0),
            "stop_loss": _safe_float(candidate.get("stop_loss") or levels.get("stop_loss"), 0.0),
            "take_profit": _safe_float(candidate.get("take_profit") or levels.get("take_profit"), 0.0),
            "quality_grade": str(candidate.get("quality_grade") or quality.get("grade") or ""),
        },
        "prerequisites": {
            "final_runtime_audit_ok": bool(final_ok),
            "pnl_reconciliation_ok": bool(pnl_ok),
            "previous_trade_postmortem_ok": bool(postmortem_ok),
            "flat_ok": bool(flat_ok),
            "open_positions": open_positions,
            "pending_orders": pending_orders,
            "status_open_positions": status_open_positions,
            "status_pending_orders": status_pending_orders,
            "paper_state_status_consistent": bool(state_status_consistent),
            "paper_readiness_error": bool(readiness_error),
            "runtime_values_present": bool(runtime_values_present),
        },
        "operator_controls": operator,
        "future_execution_env_gate": {
            ARM_ENV: "1",
            CONFIRMATION_ENV: CONFIRMATION_PHRASE,
            EXECUTE_ENV: "1",
            EXECUTE_CONFIRMATION_ENV: EXECUTE_CONFIRMATION_PHRASE,
            MAX_ORDERS_ENV: "1",
        },
        "safety_flags": {
            "live_mode_enabled": False,
            "testnet_mode_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_real_called": False,
            "broker_close_real_called": False,
        },
        "read_only_safety": {
            "paper_state_modified_by_gate": False,
            "paper_status_modified_by_gate": False,
            "orders_submitted_by_gate": 0,
            "positions_opened_by_gate": 0,
            "positions_closed_by_gate": 0,
            "broker_submit_called_by_gate": False,
            "broker_close_called_by_gate": False,
            "scheduler_started_by_gate": False,
        },
        "report": str(base / REPORT_NAME),
        "jsonl": str(base / JSONL_NAME),
    }
    _write_json(base / REPORT_NAME, report)
    _append_jsonl(base / JSONL_NAME, {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "status": report_status,
        "decision": decision,
        "system_ready": bool(system_ready),
        "second_order_gate_ready": bool(gate_ready),
        "cycle_id": report["cycle_id"],
        "candidate_valid": bool(candidate_valid),
        "operator_confirmation_ok": bool(operator_ok),
        "orders_submitted_by_gate": 0,
        "positions_opened_by_gate": 0,
        "positions_closed_by_gate": 0,
    })
    return report


__all__ = [
    "REPORT_NAME",
    "JSONL_NAME",
    "READY_DECISION",
    "OPERATOR_REQUIRED_DECISION",
    "PREREQ_BLOCKED_DECISION",
    "STATE_BLOCKED_DECISION",
    "REJECT_DECISION",
    "ARM_ENV",
    "CONFIRMATION_ENV",
    "CONFIRMATION_PHRASE",
    "build_lsr_v2_second_paper_order_gate_report_from_files",
]
