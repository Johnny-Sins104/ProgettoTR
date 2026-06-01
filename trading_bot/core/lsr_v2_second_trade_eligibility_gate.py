"""Prompt 29.4.4s-10s — LSR-v2 second supervised paper trade eligibility gate.

This module is a read-only gate that decides whether the system may prepare a
second supervised paper-only LSR-v2 trade after the first paper trade completed,
was postmortem-audited, and passed a no-reentry observation window.

It does not submit orders, open positions, close positions, mutate paper state,
mutate paper status, or enable live/testnet/exchange brokers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json

PROMPT_ID = "29.4.4s-10s"
EVENT_TYPE = "LSR_V2_SECOND_PAPER_TRADE_ELIGIBILITY_GATE"
REPORT_NAME = "lsr_v2_second_trade_eligibility_gate_report.json"
JSONL_NAME = "lsr_v2_second_trade_eligibility_gate.jsonl"

OBSERVATION_REPORT_NAME = "lsr_v2_post_first_trade_observation_report.json"
POSTMORTEM_REPORT_NAME = "lsr_v2_first_paper_trade_postmortem_report.json"
FINAL_AUDIT_REPORT_NAME = "lsr_v2_closed_trade_final_audit_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"

PASS_DECISION = "LSR_V2_SECOND_PAPER_TRADE_ELIGIBILITY_PASS"
SECOND_TRADE_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_LOCKED"
OBSERVATION_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OBSERVATION_REQUIRED"
STATE_NOT_CLEAN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_STATE_NOT_CLEAN"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_TRADE_ELIGIBILITY_FAILED"

DEFAULT_MIN_4H_CYCLES = 40
DEFAULT_MIN_8H_CYCLES = 80


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
    return str(
        row.get("paper_order_source")
        or row.get("execution_source")
        or row.get("source")
        or meta.get("paper_order_source")
        or meta.get("execution_source")
        or meta.get("source")
        or ""
    )


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or row.get("state") or row.get("position_status") or "OPEN").upper()
    closed_status = status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), not closed_status) and not closed_status


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    source = _row_source(row).lower()
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    return "lsr_v2" in source or profile == PROFILE_NAME or overlay == SELECTED_OVERLAY_ID


def _state_position_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _collection_rows(state.get("positions"), id_field="position_id")


def _count_state_lsr_positions(state: Mapping[str, Any], *, open_only: bool | None = None) -> int:
    count = 0
    for row in _state_position_rows(state):
        if not _is_lsr_v2_row(row):
            continue
        is_open = _is_position_open(row)
        if open_only is True and not is_open:
            continue
        if open_only is False and is_open:
            continue
        count += 1
    return count


def _paper_status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_position_count"), 0)
    return 0


def _paper_status_pending_orders(status: Mapping[str, Any]) -> int:
    return _safe_int(status.get("pending_orders"), 0)


def _any_true(payloads: list[Mapping[str, Any]], keys: list[str]) -> bool:
    for payload in payloads:
        for key in keys:
            if _safe_bool(payload.get(key), False):
                return True
    return False


def _build_report(
    *,
    data_dir: Path,
    min_4h_cycles: int = DEFAULT_MIN_4H_CYCLES,
    min_8h_cycles: int = DEFAULT_MIN_8H_CYCLES,
    write_outputs: bool = True,
) -> dict[str, Any]:
    observation = _read_json(data_dir / OBSERVATION_REPORT_NAME)
    postmortem = _read_json(data_dir / POSTMORTEM_REPORT_NAME)
    final_audit = _read_json(data_dir / FINAL_AUDIT_REPORT_NAME)
    paper_state = _read_json(data_dir / PAPER_STATE_NAME)
    paper_status = _read_json(data_dir / PAPER_STATUS_NAME)

    cycle_id = str(
        observation.get("cycle_id")
        or postmortem.get("cycle_id")
        or final_audit.get("cycle_id")
        or ""
    )

    completed_cycles = _safe_int(observation.get("completed_observation_cycles"), 0)
    failed_cycles = _safe_int(observation.get("failed_observation_cycles"), 0)
    timed_out_cycles = _safe_int(observation.get("timed_out_cycles"), 0)
    new_submit_cycles = observation.get("new_submit_cycles")
    if not isinstance(new_submit_cycles, list):
        new_submit_cycles = []

    state_open_lsr = _count_state_lsr_positions(paper_state, open_only=True)
    state_closed_lsr = _count_state_lsr_positions(paper_state, open_only=False)
    status_open = _paper_status_open_positions(paper_status)
    status_pending = _paper_status_pending_orders(paper_status)

    observation_pass = observation.get("status") == "PASS" and observation.get("decision") == "LSR_V2_POST_FIRST_TRADE_OBSERVATION_PASS"
    postmortem_pass = postmortem.get("status") == "PASS" and postmortem.get("decision") == "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS"
    final_audit_pass = final_audit.get("status") == "PASS" and final_audit.get("decision") == "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS"
    four_hour_observation_pass = completed_cycles >= min_4h_cycles
    eight_hour_observation_pass = completed_cycles >= min_8h_cycles
    no_failed_cycles = failed_cycles == 0 and timed_out_cycles == 0
    no_new_submit_cycles = len(new_submit_cycles) == 0
    no_reentry_detected = not _safe_bool(observation.get("extra_submit_or_reentry_detected"), False)
    second_trade_locked = _safe_bool(observation.get("second_trade_locked"), True) and not _safe_bool(observation.get("second_trade_allowed"), False)
    realized_r = _safe_float(observation.get("realized_r", postmortem.get("realized_r", final_audit.get("realized_r"))), 0.0)
    realized_pnl_total = _round(observation.get("realized_pnl_total", postmortem.get("realized_pnl_total", final_audit.get("realized_pnl_total"))), 10)

    report_state_open = _safe_int(observation.get("state_open_lsr_v2_positions", postmortem.get("state_open_lsr_v2_positions", 0)), 0)
    report_status_open = _safe_int(observation.get("paper_status_open_positions", postmortem.get("paper_status_open_positions", 0)), 0)
    report_status_pending = _safe_int(observation.get("paper_status_pending_orders", postmortem.get("paper_status_pending_orders", 0)), 0)

    clean_state = (
        state_open_lsr == 0
        and status_open == 0
        and status_pending == 0
        and report_state_open == 0
        and report_status_open == 0
        and report_status_pending == 0
        and not _safe_bool(observation.get("residual_open_position", False), False)
    )
    paper_state_consistency = _safe_bool(observation.get("paper_state_consistency"), True) and clean_state
    paper_status_consistency = _safe_bool(observation.get("paper_status_consistency"), True) and clean_state

    payloads = [observation, postmortem, final_audit]
    unsafe_flag_detected = _any_true(payloads, [
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "broker_submit_called_by_observation",
        "broker_close_called_by_observation",
        "broker_submit_called_by_postmortem",
        "broker_close_called_by_postmortem",
        "broker_submit_called_by_final_audit",
        "broker_close_called_by_final_audit",
    ])
    observation_mutated_state = _any_true(payloads, [
        "paper_state_modified_by_observation",
        "paper_status_modified_by_observation",
        "paper_state_modified_by_postmortem",
        "paper_status_modified_by_postmortem",
        "paper_state_modified_by_final_audit",
        "paper_status_modified_by_final_audit",
    ])
    observation_created_activity = any([
        _safe_int(observation.get("orders_submitted_by_observation"), 0) > 0,
        _safe_int(observation.get("positions_opened_by_observation"), 0) > 0,
        _safe_int(observation.get("positions_closed_by_observation"), 0) > 0,
        _safe_int(postmortem.get("orders_submitted_by_postmortem"), 0) > 0,
        _safe_int(postmortem.get("positions_opened_by_postmortem"), 0) > 0,
        _safe_int(postmortem.get("positions_closed_by_postmortem"), 0) > 0,
    ])

    blockers: list[str] = []
    if not observation_pass:
        blockers.append("observation_not_pass")
    if not postmortem_pass:
        blockers.append("postmortem_not_pass")
    if not final_audit_pass:
        blockers.append("closed_trade_final_audit_not_pass")
    if not four_hour_observation_pass:
        blockers.append("four_hour_observation_not_confirmed")
    if not eight_hour_observation_pass:
        blockers.append("eight_hour_observation_not_confirmed")
    if not no_failed_cycles:
        blockers.append("observation_failed_or_timed_out_cycles")
    if not no_new_submit_cycles:
        blockers.append("new_submit_cycles_detected")
    if not no_reentry_detected:
        blockers.append("reentry_detected")
    if not second_trade_locked:
        blockers.append("second_trade_not_locked")
    if not clean_state:
        blockers.append("paper_state_not_clean")
    if not paper_state_consistency or not paper_status_consistency:
        blockers.append("paper_state_status_inconsistent")
    if realized_r <= 0:
        blockers.append("realized_r_not_positive")
    if unsafe_flag_detected:
        blockers.append("unsafe_flag_detected")
    if observation_mutated_state:
        blockers.append("gate_or_observation_mutated_state")
    if observation_created_activity:
        blockers.append("gate_or_observation_created_activity")

    second_trade_eligible = False
    second_trade_execute_enabled = False
    status = "WARN"
    if unsafe_flag_detected or observation_mutated_state or observation_created_activity:
        decision = REJECT_DECISION
        status = "FAIL"
    elif not clean_state or not paper_state_consistency or not paper_status_consistency:
        decision = STATE_NOT_CLEAN_DECISION
    elif not observation_pass or not postmortem_pass or not final_audit_pass or not four_hour_observation_pass or not eight_hour_observation_pass or not no_failed_cycles:
        decision = OBSERVATION_REQUIRED_DECISION
    elif not no_new_submit_cycles or not no_reentry_detected or not second_trade_locked:
        decision = SECOND_TRADE_LOCKED_DECISION
    elif realized_r <= 0:
        decision = REJECT_DECISION
        status = "FAIL"
    else:
        decision = PASS_DECISION
        status = "PASS"
        second_trade_eligible = True

    labels: list[str] = []
    if decision == PASS_DECISION:
        labels = [
            "SECOND_PAPER_TRADE_ELIGIBILITY_PASS",
            "FOUR_HOUR_OBSERVATION_PASS",
            "EIGHT_HOUR_OBSERVATION_PASS",
            "SECOND_TRADE_EXECUTION_STILL_DISABLED",
        ]
    else:
        if not eight_hour_observation_pass or not observation_pass:
            labels.append("OBSERVATION_REQUIRED")
        if not clean_state:
            labels.append("STATE_NOT_CLEAN")
        if not no_new_submit_cycles or not no_reentry_detected:
            labels.append("REENTRY_OR_NEW_SUBMIT_DETECTED")
        if unsafe_flag_detected:
            labels.append("UNSAFE_FLAG_DETECTED")
        if not labels:
            labels.append("SECOND_TRADE_ELIGIBILITY_BLOCKED")

    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "created_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "cycle_id": cycle_id,
        "profile_name": PROFILE_NAME,
        "selected_overlay_id": SELECTED_OVERLAY_ID,
        "observation_pass": observation_pass,
        "postmortem_pass": postmortem_pass,
        "closed_trade_final_audit_pass": final_audit_pass,
        "completed_observation_cycles": completed_cycles,
        "min_4h_cycles": min_4h_cycles,
        "min_8h_cycles": min_8h_cycles,
        "four_hour_observation_pass": four_hour_observation_pass,
        "eight_hour_observation_pass": eight_hour_observation_pass,
        "failed_observation_cycles": failed_cycles,
        "timed_out_cycles": timed_out_cycles,
        "new_submit_cycles": new_submit_cycles,
        "extra_submit_or_reentry_detected": not no_reentry_detected,
        "second_trade_locked": second_trade_locked,
        "second_trade_allowed_before_gate": _safe_bool(observation.get("second_trade_allowed"), False),
        "second_trade_eligible": second_trade_eligible,
        "second_trade_execute_enabled": second_trade_execute_enabled,
        "second_trade_submit_enabled": False,
        "broker_submit_called_by_second_trade_gate": False,
        "broker_close_called_by_second_trade_gate": False,
        "orders_submitted_by_second_trade_gate": 0,
        "positions_opened_by_second_trade_gate": 0,
        "positions_closed_by_second_trade_gate": 0,
        "paper_state_modified_by_second_trade_gate": False,
        "paper_status_modified_by_second_trade_gate": False,
        "state_open_lsr_v2_positions": state_open_lsr,
        "state_closed_lsr_v2_positions": state_closed_lsr,
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "paper_state_consistency": paper_state_consistency,
        "paper_status_consistency": paper_status_consistency,
        "paper_state_clean": clean_state,
        "paper_status_clean": status_open == 0 and status_pending == 0,
        "residual_open_position": not clean_state,
        "submit_execution_events_total": _safe_int(observation.get("submit_execution_events_total", postmortem.get("submit_execution_events", 0)), 0),
        "close_execution_events_total": _safe_int(observation.get("close_execution_events_total", postmortem.get("close_execution_events", 0)), 0),
        "realized_pnl_total": realized_pnl_total,
        "realized_r": _round(realized_r, 10),
        "realized_r_positive": realized_r > 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "automatic_activation_allowed": False,
        "report": str(data_dir / REPORT_NAME),
        "jsonl": str(data_dir / JSONL_NAME),
    }

    if write_outputs:
        _write_json(data_dir / REPORT_NAME, report)
        _append_jsonl(data_dir / JSONL_NAME, report)
    return report


def build_lsr_v2_second_trade_eligibility_gate_report_from_files(
    *,
    data_dir: str | Path = "data",
    min_4h_cycles: int = DEFAULT_MIN_4H_CYCLES,
    min_8h_cycles: int = DEFAULT_MIN_8H_CYCLES,
    write_outputs: bool = True,
) -> dict[str, Any]:
    """Build the read-only second paper trade eligibility gate report."""
    return _build_report(
        data_dir=Path(data_dir),
        min_4h_cycles=min_4h_cycles,
        min_8h_cycles=min_8h_cycles,
        write_outputs=write_outputs,
    )


__all__ = [
    "PASS_DECISION",
    "SECOND_TRADE_LOCKED_DECISION",
    "OBSERVATION_REQUIRED_DECISION",
    "STATE_NOT_CLEAN_DECISION",
    "REJECT_DECISION",
    "build_lsr_v2_second_trade_eligibility_gate_report_from_files",
]
