"""Prompt 29.4.4s-10ag — LSR-v2 third supervised paper-trade eligibility gate.

Read-only gate after two supervised paper-only LSR-v2 trades and the post
second-trade observation window.  It determines whether a *third* paper trade
may be evaluated by later supervised gates, while keeping all submit/execution
paths disabled.  The module never opens orders, closes positions, mutates paper
state/status, or enables live/testnet/exchange brokers.
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

PROMPT_ID = "29.4.4s-10ag"
EVENT_TYPE = "LSR_V2_THIRD_TRADE_ELIGIBILITY_GATE"
REPORT_NAME = "lsr_v2_third_trade_eligibility_gate_report.json"
JSONL_NAME = "lsr_v2_third_trade_eligibility_gate.jsonl"

TWO_TRADE_POSTMORTEM_REPORT_NAME = "lsr_v2_two_trade_paper_cycle_postmortem_report.json"
TWO_TRADE_OBSERVATION_REPORT_NAME = "lsr_v2_two_trade_observation_report.json"
TELEGRAM_POSITION_MONITOR_REPORT_NAME = "lsr_v2_telegram_position_monitor_bridge_report.json"
TELEGRAM_NOTIFICATION_BRIDGE_REPORT_NAME = "lsr_v2_telegram_notification_bridge_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

PASS_DECISION = "LSR_V2_THIRD_PAPER_TRADE_ELIGIBILITY_PASS"
POSTMORTEM_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_POSTMORTEM_MISSING"
OBSERVATION_INSUFFICIENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_OBSERVATION_INSUFFICIENT"
STATE_NOT_CLEAN_DECISION_CANONICAL = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_STATE_NOT_CLEAN"
TELEGRAM_NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_TELEGRAM_MONITOR_NOT_READY"
THIRD_TRADE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_NOT_LOCKED"
REENTRY_DETECTED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_REENTRY_DETECTED"
FAILED_DECISION = "REJECT_LSR_V2_THIRD_TRADE_ELIGIBILITY_SAFETY_FAILED"

POSTMORTEM_PASS_DECISION = "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS"
OBSERVATION_PASS_DECISION = "LSR_V2_TWO_TRADE_OBSERVATION_PASS"
TELEGRAM_NO_OPEN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_POSITION_MONITOR_NO_OPEN_POSITION"
TELEGRAM_MONITOR_SENT_DECISION = "LSR_V2_TELEGRAM_POSITION_MONITOR_SENT"
TELEGRAM_MONITOR_DRY_RUN_DECISION = "LSR_V2_TELEGRAM_POSITION_MONITOR_READY_DRY_RUN"

DEFAULT_MIN_4H_CYCLES = 40
DEFAULT_MIN_8H_CYCLES = 80
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


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


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 100000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

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


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}:
        return False
    return _safe_bool(row.get("pending"), status not in {"", "FILLED", "EXECUTED", "COMPLETE", "COMPLETED"})


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    text = " ".join([
        _row_source(row),
        str(row.get("profile_name") or meta.get("profile_name") or ""),
        str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
        str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
    ]).lower()
    return "lsr_v2" in text or "retest_limit" in text or PROFILE_NAME.lower() in text or SELECTED_OVERLAY_ID.lower() in text


def _report_pass(report: Mapping[str, Any], *, decision: str = "") -> bool:
    if not report:
        return False
    if str(report.get("status") or "").upper() != "PASS":
        return False
    if decision and str(report.get("decision") or "") != decision:
        return False
    return True


def _paper_status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_positions") or monitor.get("open_position_count"), 0)
    return 0


def _paper_status_pending_orders(status: Mapping[str, Any]) -> int:
    return _safe_int(status.get("pending_orders"), 0)


def _event_submit_like_count(rows: Iterable[Mapping[str, Any]]) -> int:
    needles = {
        "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED",
        "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
        "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED",
        "PAPER_ORDER_FILLED",
        "POSITION_OPENED",
    }
    count = 0
    for row in rows:
        event_type = str(row.get("event_type") or "")
        decision = str(row.get("decision") or "")
        source = _row_source(row).lower()
        if (event_type in needles or decision in needles) and ("lsr_v2" in source or "LSR_V2" in event_type or "LSR_V2" in decision):
            count += 1
    return count


def _telegram_position_monitor_ready(report: Mapping[str, Any]) -> bool:
    if not report:
        return False
    if str(report.get("status") or "").upper() != "PASS":
        return False
    decision = str(report.get("decision") or "")
    allowed_decisions = {TELEGRAM_NO_OPEN_DECISION, TELEGRAM_MONITOR_SENT_DECISION, TELEGRAM_MONITOR_DRY_RUN_DECISION}
    if decision not in allowed_decisions:
        return False
    stale_guard = report.get("stale_guard")
    if isinstance(stale_guard, Mapping) and stale_guard:
        return _safe_bool(stale_guard.get("guard_enabled"), False)
    # Older monitor bridge reports without stale_guard are not sufficient for
    # third-trade eligibility because stale-open filtering is mandatory now.
    return False


def _telegram_event_bridge_ready(report: Mapping[str, Any]) -> bool:
    if not report:
        return False
    if str(report.get("status") or "").upper() not in {"PASS", "WARN"}:
        return False
    decision = str(report.get("decision") or "")
    # Config-missing WARN is acceptable for eligibility: event Telegram is
    # observability-only and may be disabled in a fresh shell; the position
    # monitor guard is the mandatory piece before opening the next paper trade.
    return decision in {
        "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_READY_DRY_RUN",
        "LSR_V2_TELEGRAM_NOTIFICATION_BRIDGE_SENT",
        "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_CONFIG_MISSING",
    }


def _state_cleanliness(state: Mapping[str, Any], status: Mapping[str, Any]) -> dict[str, Any]:
    positions = [p for p in _collection_rows(state.get("positions"), id_field="position_id") if _is_lsr_v2_row(p)]
    open_lsr = [p for p in positions if _is_position_open(p)]
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    pending_orders = [o for o in orders if _is_order_pending(o)]
    status_open = _paper_status_open_positions(status)
    status_pending = _paper_status_pending_orders(status)
    return {
        "state_open_lsr_v2_positions": len(open_lsr),
        "state_lsr_v2_position_count": len(positions),
        "state_pending_order_count": len(pending_orders),
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "paper_state_consistency": len(open_lsr) == 0 and len(pending_orders) == 0,
        "paper_status_consistency": status_open == 0 and status_pending == 0,
        "residual_open_position": bool(len(open_lsr) > 0 or status_open > 0),
        "pending_order_detected": bool(len(pending_orders) > 0 or status_pending > 0),
    }


def build_lsr_v2_third_trade_eligibility_gate_report_from_files(
    *,
    data_dir: str | Path = "data",
    min_4h_cycles: int = DEFAULT_MIN_4H_CYCLES,
    min_8h_cycles: int = DEFAULT_MIN_8H_CYCLES,
) -> dict[str, Any]:
    data = Path(data_dir)
    postmortem = _read_json(data / TWO_TRADE_POSTMORTEM_REPORT_NAME)
    observation = _read_json(data / TWO_TRADE_OBSERVATION_REPORT_NAME)
    telegram_monitor = _read_json(data / TELEGRAM_POSITION_MONITOR_REPORT_NAME)
    telegram_bridge = _read_json(data / TELEGRAM_NOTIFICATION_BRIDGE_REPORT_NAME)
    state = _read_json(data / PAPER_STATE_NAME)
    status = _read_json(data / PAPER_STATUS_NAME)
    paper_events = _iter_jsonl_tail(data / PAPER_EVENTS_NAME)

    postmortem_pass = _report_pass(postmortem, decision=POSTMORTEM_PASS_DECISION)
    observation_pass = _report_pass(observation, decision=OBSERVATION_PASS_DECISION)
    completed_cycles = _safe_int(observation.get("completed_observation_cycles"), 0)
    failed_cycles = _safe_int(observation.get("failed_observation_cycles"), 0)
    timed_out_cycles = _safe_int(observation.get("timed_out_cycles"), 0)
    four_hour_pass = bool(observation_pass and completed_cycles >= max(0, int(min_4h_cycles)) and failed_cycles == 0 and timed_out_cycles == 0)
    eight_hour_pass = bool(observation_pass and completed_cycles >= max(0, int(min_8h_cycles)) and failed_cycles == 0 and timed_out_cycles == 0)

    clean = _state_cleanliness(state, status)
    paper_event_submit_like_count = _event_submit_like_count(paper_events)
    # Two historical supervised submits are expected.  Anything above two is
    # evidence of a third submit/re-entry outside this eligibility gate.
    third_submit_from_events = paper_event_submit_like_count > 2

    postmortem_third_detected = _safe_bool(postmortem.get("third_submit_or_reentry_detected"), False)
    observation_third_detected = _safe_bool(observation.get("third_submit_or_reentry_detected"), False)
    third_submit_or_reentry_detected = bool(postmortem_third_detected or observation_third_detected or third_submit_from_events)
    third_trade_locked_before = bool(_safe_bool(observation.get("third_trade_locked"), False) and _safe_bool(postmortem.get("third_trade_locked"), False))
    third_trade_allowed_before = bool(_safe_bool(observation.get("third_trade_allowed"), False) or _safe_bool(postmortem.get("third_trade_allowed"), False))

    telegram_monitor_ready = _telegram_position_monitor_ready(telegram_monitor)
    telegram_event_bridge_ready = _telegram_event_bridge_ready(telegram_bridge)

    unsafe_flags = {
        "live_enabled": bool(_safe_bool(postmortem.get("live_enabled"), False) or _safe_bool(observation.get("live_enabled"), False) or _safe_bool(status.get("live_enabled"), False)),
        "testnet_enabled": bool(_safe_bool(postmortem.get("testnet_enabled"), False) or _safe_bool(observation.get("testnet_enabled"), False) or _safe_bool(status.get("testnet_enabled"), False)),
        "exchange_broker_enabled": bool(_safe_bool(postmortem.get("exchange_broker_enabled"), False) or _safe_bool(observation.get("exchange_broker_enabled"), False) or _safe_bool(status.get("exchange_broker_enabled"), False)),
        "operational_unlock_allowed": bool(_safe_bool(postmortem.get("operational_unlock_allowed"), False) or _safe_bool(observation.get("operational_unlock_allowed"), False) or _safe_bool(status.get("operational_unlock_allowed"), False)),
    }
    safety_violation = any(unsafe_flags.values())

    blockers: list[str] = []
    if not postmortem_pass:
        blockers.append("two_trade_postmortem_not_pass")
    if not observation_pass:
        blockers.append("two_trade_observation_not_pass")
    if not four_hour_pass:
        blockers.append("four_hour_observation_not_pass")
    if not eight_hour_pass:
        blockers.append("eight_hour_observation_not_pass")
    if failed_cycles:
        blockers.append("failed_observation_cycles")
    if timed_out_cycles:
        blockers.append("timed_out_cycles")
    if not third_trade_locked_before or third_trade_allowed_before:
        blockers.append("third_trade_not_locked")
    if clean["residual_open_position"]:
        blockers.append("residual_open_position")
    if clean["pending_order_detected"]:
        blockers.append("pending_order_detected")
    if not clean["paper_state_consistency"]:
        blockers.append("paper_state_inconsistent")
    if not clean["paper_status_consistency"]:
        blockers.append("paper_status_inconsistent")
    if third_submit_or_reentry_detected:
        blockers.append("third_submit_or_reentry_detected")
    if not telegram_monitor_ready:
        blockers.append("telegram_position_monitor_not_ready")
    for name, enabled in unsafe_flags.items():
        if enabled:
            blockers.append(name)

    if safety_violation:
        decision = FAILED_DECISION
        status_text = "FAIL"
    elif third_submit_or_reentry_detected:
        decision = REENTRY_DETECTED_DECISION
        status_text = "WARN"
    elif not postmortem_pass:
        decision = POSTMORTEM_MISSING_DECISION
        status_text = "WARN"
    elif not observation_pass or not four_hour_pass or not eight_hour_pass or failed_cycles or timed_out_cycles:
        decision = OBSERVATION_INSUFFICIENT_DECISION
        status_text = "WARN"
    elif not third_trade_locked_before or third_trade_allowed_before:
        decision = THIRD_TRADE_NOT_LOCKED_DECISION
        status_text = "WARN"
    elif clean["residual_open_position"] or clean["pending_order_detected"] or not clean["paper_state_consistency"] or not clean["paper_status_consistency"]:
        decision = STATE_NOT_CLEAN_DECISION_CANONICAL
        status_text = "WARN"
    elif not telegram_monitor_ready:
        decision = TELEGRAM_NOT_READY_DECISION
        status_text = "WARN"
    else:
        decision = PASS_DECISION
        status_text = "PASS"

    eligible = decision == PASS_DECISION
    labels: list[str] = []
    if eligible:
        labels = [
            "THIRD_PAPER_TRADE_ELIGIBILITY_PASS",
            "TWO_TRADE_POSTMORTEM_PASS",
            "FOUR_HOUR_OBSERVATION_PASS",
            "EIGHT_HOUR_OBSERVATION_PASS",
            "NO_RESIDUAL_POSITION",
            "TELEGRAM_MONITOR_READY",
            "EXECUTION_STILL_DISABLED",
        ]
    else:
        if not eight_hour_pass:
            labels.append("OBSERVATION_REQUIRED")
        if clean["residual_open_position"]:
            labels.append("RESIDUAL_POSITION_PRESENT")
        if third_submit_or_reentry_detected:
            labels.append("THIRD_SUBMIT_OR_REENTRY_DETECTED")
        if not telegram_monitor_ready:
            labels.append("TELEGRAM_MONITOR_REQUIRED")

    report = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "ts": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": labels,
        "blockers": sorted(set(blockers)),
        "cycle_ids": list(postmortem.get("cycle_ids") or observation.get("cycle_ids") or []),
        "two_trade_postmortem_pass": postmortem_pass,
        "two_trade_postmortem_complete": _safe_bool(postmortem.get("two_trade_postmortem_complete"), False),
        "two_trade_observation_pass": observation_pass,
        "completed_observation_cycles": completed_cycles,
        "failed_observation_cycles": failed_cycles,
        "timed_out_cycles": timed_out_cycles,
        "min_4h_observation_cycles": int(min_4h_cycles),
        "min_8h_observation_cycles": int(min_8h_cycles),
        "four_hour_observation_pass": four_hour_pass,
        "eight_hour_observation_pass": eight_hour_pass,
        "submit_execution_events_total": _safe_int(observation.get("submit_execution_events_total") or postmortem.get("submit_execution_events_total"), 0),
        "close_execution_events_total": _safe_int(observation.get("close_execution_events_total") or postmortem.get("close_execution_events_total"), 0),
        "total_realized_pnl": _round(observation.get("total_realized_pnl") if "total_realized_pnl" in observation else postmortem.get("total_realized_pnl")),
        "average_realized_r": _round(observation.get("average_realized_r") if "average_realized_r" in observation else postmortem.get("average_realized_r")),
        "total_risk_amount": _round(observation.get("total_risk_amount") if "total_risk_amount" in observation else postmortem.get("total_risk_amount")),
        "pnl_reconciliation_ok": bool(_safe_bool(observation.get("pnl_reconciliation_ok"), False) or _safe_bool(postmortem.get("pnl_reconciliation_ok"), False)),
        "state_open_lsr_v2_positions": clean["state_open_lsr_v2_positions"],
        "state_pending_order_count": clean["state_pending_order_count"],
        "paper_status_open_positions": clean["paper_status_open_positions"],
        "paper_status_pending_orders": clean["paper_status_pending_orders"],
        "paper_state_consistency": clean["paper_state_consistency"],
        "paper_status_consistency": clean["paper_status_consistency"],
        "residual_open_position": clean["residual_open_position"],
        "pending_order_detected": clean["pending_order_detected"],
        "paper_event_submit_like_count": paper_event_submit_like_count,
        "third_submit_or_reentry_detected": third_submit_or_reentry_detected,
        "third_trade_locked_before_gate": third_trade_locked_before,
        "third_trade_allowed_before_gate": third_trade_allowed_before,
        "third_trade_eligible": eligible,
        "third_trade_gate_ready": eligible,
        "third_trade_allowed": False,
        "third_trade_locked": True,
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "telegram_position_monitor_ready": telegram_monitor_ready,
        "telegram_position_monitor_decision": str(telegram_monitor.get("decision") or ""),
        "telegram_event_bridge_ready": telegram_event_bridge_ready,
        "telegram_event_bridge_decision": str(telegram_bridge.get("decision") or ""),
        "orders_submitted_by_third_trade_gate": 0,
        "positions_opened_by_third_trade_gate": 0,
        "positions_closed_by_third_trade_gate": 0,
        "broker_submit_called_by_third_trade_gate": False,
        "broker_close_called_by_third_trade_gate": False,
        "paper_state_modified_by_third_trade_gate": False,
        "paper_status_modified_by_third_trade_gate": False,
        "automatic_reentry_enabled": False,
        "automatic_close_enabled": False,
        "live_enabled": unsafe_flags["live_enabled"],
        "testnet_enabled": unsafe_flags["testnet_enabled"],
        "exchange_broker_enabled": unsafe_flags["exchange_broker_enabled"],
        "operational_unlock_allowed": unsafe_flags["operational_unlock_allowed"],
        "promotion_ready": False,
        "next_step": "third_trade_rearm_gate" if eligible else "resolve_blockers_before_third_trade",
        "report": str(data / REPORT_NAME),
        "jsonl": str(data / JSONL_NAME),
    }
    _write_json(data / REPORT_NAME, report)
    _append_jsonl(data / JSONL_NAME, report)
    return report
