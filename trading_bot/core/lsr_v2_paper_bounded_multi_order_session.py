"""Patch 30.3.0H - bounded multi-order supervised paper session readiness."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import os
import re

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore


PROMPT_ID = "30.3.0H"
EVENT_TYPE = "LSR_V2_PAPER_BOUNDED_MULTI_ORDER_SESSION_READINESS"
REPORT_NAME = "lsr_v2_paper_bounded_multi_order_session_readiness_report.json"
JSONL_NAME = "lsr_v2_paper_bounded_multi_order_session_readiness.jsonl"

FINAL_RUNTIME_AUDIT_REPORT_NAME = "lsr_v2_paper_final_runtime_audit_report.json"
PNL_REPORT_NAME = "lsr_v2_paper_realized_pnl_reconciliation_report.json"
SECOND_GATE_REPORT_NAME = "lsr_v2_second_paper_order_gate_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"
PAPER_READINESS_REPORT_NAME = "paper_readiness_report.json"

READY_DECISION = "LSR_V2_PAPER_BOUNDED_MULTI_ORDER_SESSION_READY_DEFAULT_OFF"
OPERATOR_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_MULTI_ORDER_OPERATOR_CONFIRMATION_REQUIRED"
BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_MULTI_ORDER_SESSION_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_PAPER_BOUNDED_MULTI_ORDER_SESSION_FAILED"

ARM_ENV = "LSR_V2_PAPER_MULTI_ORDER_ARM"
CONFIRMATION_ENV = "LSR_V2_PAPER_MULTI_ORDER_CONFIRMATION"
CONFIRMATION_PHRASE = "I_UNDERSTAND_BOUNDED_MULTI_PAPER_ORDER_SESSION"
MAX_ORDERS_ENV = "LSR_V2_PAPER_MULTI_ORDER_MAX_ORDERS"
MAX_OPEN_POSITIONS_ENV = "LSR_V2_PAPER_MULTI_ORDER_MAX_OPEN_POSITIONS"
REQUIRE_FLAT_ENV = "LSR_V2_PAPER_MULTI_ORDER_REQUIRE_FLAT_BEFORE_NEXT"
COOLDOWN_ENV = "LSR_V2_PAPER_MULTI_ORDER_COOLDOWN_CYCLES"

CYCLE_RE = re.compile(r"pc_(\d+)_")


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


def _metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = row.get("metadata")
    return raw if isinstance(raw, Mapping) else {}


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    return _status_text(row, "FILLED") in {"NEW", "OPEN", "PENDING", "PLACED", "SUBMITTED", "ACCEPTED"}


def _cycle_id(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _cycle_seq(cycle_id: str) -> int:
    match = CYCLE_RE.match(str(cycle_id or ""))
    return int(match.group(1)) if match else 0


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


def _latest_candidate(events: list[dict[str, Any]]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for row in events:
        if str(row.get("event_type") or "") not in {"LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT", "LSR_V2_RUNTIME_CANDIDATE_AUDIT"}:
            continue
        if _safe_bool(row.get("candidate_ready"), False) or _safe_bool(row.get("runtime_candidate_ready"), False) or _safe_bool(row.get("would_route"), False):
            selected = dict(row)
    return selected


def _operator_controls() -> dict[str, Any]:
    return {
        "arm": _safe_bool(os.getenv(ARM_ENV), False),
        "confirmation_ok": os.getenv(CONFIRMATION_ENV, "") == CONFIRMATION_PHRASE,
        "max_orders_per_session": _safe_int(os.getenv(MAX_ORDERS_ENV), 2),
        "max_open_positions": _safe_int(os.getenv(MAX_OPEN_POSITIONS_ENV), 1),
        "require_flat_before_next": _safe_bool(os.getenv(REQUIRE_FLAT_ENV), True),
        "cooldown_cycles_after_close": _safe_int(os.getenv(COOLDOWN_ENV), 3),
    }


def build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(
    *,
    data_dir: str | Path = "data",
    max_event_lines: int = 50000,
) -> dict[str, Any]:
    base = Path(data_dir)
    final_audit = _read_json(base / FINAL_RUNTIME_AUDIT_REPORT_NAME)
    pnl_report = _read_json(base / PNL_REPORT_NAME)
    second_gate = _read_json(base / SECOND_GATE_REPORT_NAME)
    state = _read_json(base / PAPER_STATE_NAME)
    status = _read_json(base / PAPER_STATUS_NAME)
    readiness = _read_json(base / PAPER_READINESS_REPORT_NAME)
    events = _iter_tail(base / PAPER_EVENTS_NAME, max_lines=max_event_lines)
    candidate = _latest_candidate(events)
    operator = _operator_controls()

    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = sum(1 for row in positions if _is_position_open(row))
    pending_orders = sum(1 for row in orders if _is_order_pending(row))
    status_open_positions = _safe_int(status.get("open_positions"), open_positions)
    status_pending_orders = _safe_int(status.get("pending_orders"), pending_orders)
    session_orders = len(orders)
    existing_cycle_ids = {_cycle_id(row) for row in orders if _cycle_id(row)}
    candidate_cycle_id = str(candidate.get("cycle_id") or "")
    latest_cycle_seq = max([_cycle_seq(str(row.get("cycle_id") or "")) for row in events] + [_cycle_seq(candidate_cycle_id), 0])
    last_order_cycle_seq = max([_cycle_seq(cycle) for cycle in existing_cycle_ids] + [0])
    cycles_since_last_order = latest_cycle_seq - last_order_cycle_seq if latest_cycle_seq and last_order_cycle_seq else 999999

    final_ok = bool(final_audit) and str(final_audit.get("status") or "") in {"PASS", "WARN"}
    lifecycle_warn_blocking = bool(final_audit.get("lifecycle_warning_classification", {}).get("true_missing_event")) if isinstance(final_audit.get("lifecycle_warning_classification"), Mapping) else False
    pnl_ok = bool(pnl_report) and str(pnl_report.get("reconciliation_status") or pnl_report.get("status") or "") in {"PASS", "WARN"}
    second_gate_ok = bool(second_gate) and str(second_gate.get("status") or "") == "PASS" and _safe_bool(second_gate.get("second_order_gate_ready"), False)
    state_status_consistent = open_positions == status_open_positions and pending_orders == status_pending_orders and _safe_bool(final_audit.get("paper_state_status_consistent"), True)
    flat_required_ok = (not operator["require_flat_before_next"]) or (open_positions == 0 and status_open_positions == 0)
    max_open_ok = open_positions < operator["max_open_positions"] and status_open_positions < operator["max_open_positions"]
    max_orders_ok = session_orders < operator["max_orders_per_session"]
    cooldown_ok = cycles_since_last_order >= operator["cooldown_cycles_after_close"]
    duplicate_cycle = bool(candidate_cycle_id and candidate_cycle_id in existing_cycle_ids)
    kill_switch = _safe_bool(state.get("kill_switch"), False) or _safe_bool(status.get("kill_switch"), False)
    readiness_error = str(readiness.get("status") or "").upper() == "ERROR" or str(readiness.get("decision") or "").upper() == "ERROR"
    unsafe = _recursive_any_true([final_audit, pnl_report, second_gate, status], {"live_mode_enabled", "live_enabled", "testnet_mode_enabled", "testnet_enabled", "exchange_broker_enabled", "broker_submit_real_called", "broker_close_real_called"})
    candidate_levels = candidate.get("levels") if isinstance(candidate.get("levels"), Mapping) else {}
    candidate_valid = bool(candidate) and _safe_float(candidate.get("entry_price") or candidate_levels.get("entry_price"), 0.0) > 0 and bool(candidate.get("symbol")) and bool(candidate.get("side"))
    operator_ok = operator["arm"] and operator["confirmation_ok"]

    blockers: list[str] = []
    if not final_ok:
        blockers.append("final_runtime_audit_missing_or_fail")
    if lifecycle_warn_blocking:
        blockers.append("lifecycle_audit_blocking_warn")
    if not pnl_ok:
        blockers.append("pnl_unreconciled_or_fail")
    if not second_gate_ok:
        blockers.append("second_order_gate_not_ready")
    if not state_status_consistent:
        blockers.append("paper_state_status_divergence")
    if not flat_required_ok:
        blockers.append("require_flat_before_next_blocked")
    if not max_open_ok:
        blockers.append("max_open_positions_reached")
    if not max_orders_ok:
        blockers.append("max_orders_per_session_reached")
    if duplicate_cycle:
        blockers.append("duplicate_cycle_id")
    if not cooldown_ok:
        blockers.append("cooldown_not_satisfied")
    if kill_switch:
        blockers.append("kill_switch_enabled")
    if readiness_error:
        blockers.append("paper_readiness_error")
    if unsafe:
        blockers.append("live_testnet_exchange_or_real_broker_flag_detected")
    if not operator_ok:
        blockers.append("operator_confirmation_missing")
    if not candidate_valid:
        blockers.append("candidate_not_valid")

    system_ready = all([
        final_ok,
        not lifecycle_warn_blocking,
        pnl_ok,
        second_gate_ok,
        state_status_consistent,
        flat_required_ok,
        max_open_ok,
        max_orders_ok,
        not duplicate_cycle,
        cooldown_ok,
        not kill_switch,
        not readiness_error,
        not unsafe,
        candidate_valid,
    ])
    readiness_ok = system_ready and operator_ok

    if unsafe:
        report_status = "FAIL"
        decision = REJECT_DECISION
    elif readiness_ok:
        report_status = "PASS"
        decision = READY_DECISION
    elif system_ready and not operator_ok:
        report_status = "WARN"
        decision = OPERATOR_REQUIRED_DECISION
    else:
        report_status = "WARN"
        decision = BLOCKED_DECISION

    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": report_status,
        "decision": decision,
        "blockers": blockers,
        "system_ready": bool(system_ready),
        "multi_order_session_ready": bool(readiness_ok),
        "multi_order_execute_enabled": False,
        "session_controls": operator,
        "session_orders": session_orders,
        "max_orders_per_session": operator["max_orders_per_session"],
        "open_positions": open_positions,
        "status_open_positions": status_open_positions,
        "max_open_positions": operator["max_open_positions"],
        "pending_orders": pending_orders,
        "status_pending_orders": status_pending_orders,
        "require_flat_before_next": operator["require_flat_before_next"],
        "cooldown_cycles_after_close": operator["cooldown_cycles_after_close"],
        "cycles_since_last_order": cycles_since_last_order,
        "cooldown_satisfied": bool(cooldown_ok),
        "duplicate_cycle_id": bool(duplicate_cycle),
        "candidate": {
            "candidate_valid": bool(candidate_valid),
            "cycle_id": candidate_cycle_id,
            "candidate_id": str(candidate.get("candidate_id") or ""),
            "symbol": str(candidate.get("symbol") or ""),
            "side": str(candidate.get("side") or ""),
            "entry_price": _safe_float(candidate.get("entry_price") or candidate_levels.get("entry_price"), 0.0),
            "stop_loss": _safe_float(candidate.get("stop_loss") or candidate_levels.get("stop_loss"), 0.0),
            "take_profit": _safe_float(candidate.get("take_profit") or candidate_levels.get("take_profit"), 0.0),
        },
        "prerequisites": {
            "final_runtime_audit_ok": bool(final_ok),
            "pnl_reconciliation_ok": bool(pnl_ok),
            "second_order_gate_ok": bool(second_gate_ok),
            "paper_state_status_consistent": bool(state_status_consistent),
            "kill_switch": bool(kill_switch),
            "paper_readiness_error": bool(readiness_error),
        },
        "safety_flags": {
            "live_mode_enabled": False,
            "testnet_mode_enabled": False,
            "exchange_broker_enabled": False,
            "broker_submit_real_called": False,
            "broker_close_real_called": False,
        },
        "read_only_safety": {
            "paper_state_modified_by_readiness": False,
            "paper_status_modified_by_readiness": False,
            "orders_submitted_by_readiness": 0,
            "positions_opened_by_readiness": 0,
            "positions_closed_by_readiness": 0,
            "broker_submit_called_by_readiness": False,
            "broker_close_called_by_readiness": False,
            "scheduler_started_by_readiness": False,
        },
        "future_execution_env_gate": {
            ARM_ENV: "1",
            CONFIRMATION_ENV: CONFIRMATION_PHRASE,
            MAX_ORDERS_ENV: "2",
            MAX_OPEN_POSITIONS_ENV: "1",
            REQUIRE_FLAT_ENV: "1",
            COOLDOWN_ENV: "3",
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
        "multi_order_session_ready": bool(readiness_ok),
        "session_orders": session_orders,
        "open_positions": open_positions,
        "candidate_cycle_id": candidate_cycle_id,
        "orders_submitted_by_readiness": 0,
        "positions_opened_by_readiness": 0,
        "positions_closed_by_readiness": 0,
    })
    return report


__all__ = [
    "REPORT_NAME",
    "JSONL_NAME",
    "READY_DECISION",
    "OPERATOR_REQUIRED_DECISION",
    "BLOCKED_DECISION",
    "REJECT_DECISION",
    "ARM_ENV",
    "CONFIRMATION_ENV",
    "CONFIRMATION_PHRASE",
    "build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files",
]
