"""Prompt 29.4.4s-10t — LSR-v2 second supervised paper trade controlled re-arm gate.

This module is a non-mutating, gate-only layer after the second-trade
eligibility gate.  It can mark the diagnostic LSR-v2 second-trade path as
controlled-rearmed only when the explicit operator re-arm environment variables
are present.  It does not submit orders, open positions, close positions,
mutate paper state, mutate paper status, or enable live/testnet/exchange
brokers.
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
import os

PROMPT_ID = "29.4.4s-10t"
EVENT_TYPE = "LSR_V2_SECOND_TRADE_REARM_GATE"
REPORT_NAME = "lsr_v2_second_trade_rearm_gate_report.json"
JSONL_NAME = "lsr_v2_second_trade_rearm_gate.jsonl"

ELIGIBILITY_REPORT_NAME = "lsr_v2_second_trade_eligibility_gate_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

RUNTIME_CANDIDATE_EVENT_TYPE = "LSR_V2_RUNTIME_CANDIDATE_AUDIT"
RUNTIME_BRIDGE_EVENT_TYPE = "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT"
ORDER_INTENT_EVENT_TYPE = "LSR_V2_PAPER_ORDER_INTENT_AUDIT"
HANDOFF_EVENT_TYPE = "LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN"
SUBMIT_PREFLIGHT_EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT"
SUBMIT_BOUNDARY_EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_BOUNDARY"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"

PASS_DECISION = "LSR_V2_SECOND_TRADE_REARM_READY_DIAGNOSTIC"
CANDIDATE_WAIT_DECISION = "LSR_V2_SECOND_TRADE_CANDIDATE_WAIT_GATE_READY"
NOT_ENABLED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_NOT_ENABLED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_REARM_CONFIRMATION_MISSING"
ELIGIBILITY_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_ELIGIBILITY_MISSING"
STATE_NOT_CLEAN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_TRADE_STATE_NOT_CLEAN"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_TRADE_REARM_SAFETY_FAILED"

REQUIRED_REARM_VALUE = "1"
REQUIRED_REARM_CONFIRMATION = "I_UNDERSTAND_SECOND_PAPER_TRADE_DIAGNOSTIC_ONLY"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "armed", "pass", "ready"}:
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


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
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


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    source = _row_source(row).lower()
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    return "lsr_v2" in source or profile == PROFILE_NAME or overlay == SELECTED_OVERLAY_ID


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or row.get("state") or row.get("position_status") or "OPEN").upper()
    closed_status = status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), not closed_status) and not closed_status


def _count_state_lsr_positions(state: Mapping[str, Any], *, open_only: bool | None = None) -> int:
    count = 0
    for row in _collection_rows(state.get("positions"), id_field="position_id"):
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


def _event_cycle(row: Mapping[str, Any]) -> str:
    return str(row.get("cycle_id") or row.get("lsr_v2_runtime_cycle_id") or "")


def _event_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(row.get("event_type") or ""),
        _event_cycle(row),
        str(row.get("symbol") or ""),
        str(row.get("candidate_id") or ""),
        str(row.get("timeframe") or ""),
    )


def _dedupe_events(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        key = _event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _latest_cycle_id(rows: list[Mapping[str, Any]]) -> str:
    for row in reversed(rows):
        if row.get("event_type") == CYCLE_COMPLETED_EVENT_TYPE and _event_cycle(row):
            return _event_cycle(row)
    for row in reversed(rows):
        if _event_cycle(row):
            return _event_cycle(row)
    return ""


def _safe_current_cycle_lsr_events(data_dir: Path, *, max_lines: int, requested_cycle_id: str = "") -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    rows = _iter_jsonl_tail(data_dir / PAPER_EVENTS_NAME, max_lines=max_lines)
    cycle_id = str(requested_cycle_id or _latest_cycle_id(rows))
    lsr_types = {
        RUNTIME_CANDIDATE_EVENT_TYPE,
        RUNTIME_BRIDGE_EVENT_TYPE,
        ORDER_INTENT_EVENT_TYPE,
        HANDOFF_EVENT_TYPE,
        SUBMIT_PREFLIGHT_EVENT_TYPE,
        SUBMIT_BOUNDARY_EVENT_TYPE,
    }
    lsr_rows = [row for row in rows if row.get("event_type") in lsr_types]
    current = _dedupe_events([row for row in lsr_rows if not cycle_id or _event_cycle(row) == cycle_id])
    historical = _dedupe_events([row for row in lsr_rows if cycle_id and _event_cycle(row) and _event_cycle(row) != cycle_id])
    return cycle_id, current, historical


def _count(rows: Iterable[Mapping[str, Any]], event_type: str) -> int:
    return sum(1 for row in rows if row.get("event_type") == event_type)


def _count_bool(rows: Iterable[Mapping[str, Any]], event_type: str, key: str) -> int:
    return sum(1 for row in rows if row.get("event_type") == event_type and _safe_bool(row.get(key), False))


@dataclass(frozen=True)
class LSRV2SecondTradeRearmSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    eligibility_report_name: str = ELIGIBILITY_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    max_event_lines: int = 50000
    profile_name: str = PROFILE_NAME
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    required_rearm_value: str = REQUIRED_REARM_VALUE
    required_rearm_confirmation: str = REQUIRED_REARM_CONFIRMATION
    rearm_enable: str = ""
    rearm_confirmation: str = ""
    max_orders: int = 1
    mode: str = "paper"

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2SecondTradeRearmSettings":
        max_orders = _safe_int(os.getenv("LSR_V2_SECOND_TRADE_MAX_ORDERS"), 1)
        if max_orders <= 0:
            max_orders = 1
        return cls(
            data_dir=data_dir,
            rearm_enable=str(os.getenv("LSR_V2_SECOND_TRADE_REARM_ENABLE") or ""),
            rearm_confirmation=str(os.getenv("LSR_V2_SECOND_TRADE_REARM_CONFIRMATION") or ""),
            max_orders=max_orders,
            mode=str(os.getenv("LSR_V2_SECOND_TRADE_REARM_MODE") or "paper"),
        )

    @property
    def rearm_enabled(self) -> bool:
        return str(self.rearm_enable).strip() == self.required_rearm_value

    @property
    def rearm_confirmation_ok(self) -> bool:
        return str(self.rearm_confirmation).strip() == self.required_rearm_confirmation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_lsr_v2_second_trade_rearm_gate_event(*, report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_type": EVENT_TYPE,
        "prompt": PROMPT_ID,
        "ts": utc_now_iso(),
        "cycle_id": report.get("cycle_id", ""),
        "decision": report.get("decision", ""),
        "status": report.get("status", ""),
        "second_trade_eligible": _safe_bool(report.get("second_trade_eligible"), False),
        "second_trade_rearm_enabled": _safe_bool(report.get("second_trade_rearm_enabled"), False),
        "second_trade_rearm_confirmation_ok": _safe_bool(report.get("second_trade_rearm_confirmation_ok"), False),
        "candidate_wait_gate_ready": _safe_bool(report.get("candidate_wait_gate_ready"), False),
        "second_trade_rearm_ready": _safe_bool(report.get("second_trade_rearm_ready"), False),
        "runtime_candidate_events": _safe_int(report.get("runtime_candidate_events"), 0),
        "runtime_candidate_ready_events": _safe_int(report.get("runtime_candidate_ready_events"), 0),
        "runtime_bridge_events": _safe_int(report.get("runtime_bridge_events"), 0),
        "runtime_would_route_count": _safe_int(report.get("runtime_would_route_count"), 0),
        "order_intent_events": _safe_int(report.get("order_intent_events"), 0),
        "handoff_dry_run_events": _safe_int(report.get("handoff_dry_run_events"), 0),
        "submit_preflight_events": _safe_int(report.get("submit_preflight_events"), 0),
        "submit_boundary_events": _safe_int(report.get("submit_boundary_events"), 0),
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "broker_submit_called": False,
        "orders_submitted_by_second_trade_rearm_gate": 0,
        "positions_opened_by_second_trade_rearm_gate": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }


def build_lsr_v2_second_trade_rearm_gate_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondTradeRearmSettings | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or LSRV2SecondTradeRearmSettings.from_env(str(base))

    eligibility = _read_json(base / settings.eligibility_report_name)
    paper_state = _read_json(base / settings.paper_state_name)
    paper_status = _read_json(base / settings.paper_status_name)
    event_cycle_id, current_events, historical_events = _safe_current_cycle_lsr_events(
        base, max_lines=settings.max_event_lines, requested_cycle_id=cycle_id
    )

    selected_cycle_id = str(cycle_id or event_cycle_id or eligibility.get("cycle_id") or "")
    if selected_cycle_id and event_cycle_id and selected_cycle_id != event_cycle_id:
        current_events = _dedupe_events([row for row in current_events if _event_cycle(row) == selected_cycle_id])

    eligibility_pass = eligibility.get("status") == "PASS" and eligibility.get("decision") == "LSR_V2_SECOND_PAPER_TRADE_ELIGIBILITY_PASS"
    second_trade_eligible = _safe_bool(eligibility.get("second_trade_eligible"), False)
    observation_pass = _safe_bool(eligibility.get("observation_pass"), False)
    four_hour_observation_pass = _safe_bool(eligibility.get("four_hour_observation_pass"), False)
    eight_hour_observation_pass = _safe_bool(eligibility.get("eight_hour_observation_pass"), False)
    no_reentry = not _safe_bool(eligibility.get("extra_submit_or_reentry_detected"), False)

    state_open_lsr = _count_state_lsr_positions(paper_state, open_only=True)
    status_open = _paper_status_open_positions(paper_status)
    status_pending = _paper_status_pending_orders(paper_status)
    clean_state = state_open_lsr == 0 and status_open == 0 and status_pending == 0
    paper_state_consistency = _safe_bool(eligibility.get("paper_state_consistency"), True) and clean_state
    paper_status_consistency = _safe_bool(eligibility.get("paper_status_consistency"), True) and clean_state

    runtime_candidate_events = _count(current_events, RUNTIME_CANDIDATE_EVENT_TYPE)
    runtime_candidate_ready_events = _count_bool(current_events, RUNTIME_CANDIDATE_EVENT_TYPE, "candidate_ready")
    runtime_bridge_events = _count(current_events, RUNTIME_BRIDGE_EVENT_TYPE)
    runtime_would_route_count = _count_bool(current_events, RUNTIME_BRIDGE_EVENT_TYPE, "would_route")
    runtime_would_submit_count = _count_bool(current_events, RUNTIME_BRIDGE_EVENT_TYPE, "would_submit")
    order_intent_events = _count(current_events, ORDER_INTENT_EVENT_TYPE)
    handoff_dry_run_events = _count(current_events, HANDOFF_EVENT_TYPE)
    submit_preflight_events = _count(current_events, SUBMIT_PREFLIGHT_EVENT_TYPE)
    submit_boundary_events = _count(current_events, SUBMIT_BOUNDARY_EVENT_TYPE)

    unsafe_flag = any(
        _safe_bool(eligibility.get(key), False)
        for key in ["live_enabled", "testnet_enabled", "exchange_broker_enabled", "operational_unlock_allowed", "promotion_ready"]
    )
    upstream_activity = any(
        _safe_int(eligibility.get(key), 0) > 0
        for key in ["orders_submitted_by_second_trade_gate", "positions_opened_by_second_trade_gate"]
    )

    blockers: list[str] = []
    if not eligibility_pass or not second_trade_eligible:
        blockers.append("second_trade_eligibility_not_pass")
    if not observation_pass:
        blockers.append("observation_not_pass")
    if not four_hour_observation_pass:
        blockers.append("four_hour_observation_not_confirmed")
    if not eight_hour_observation_pass:
        blockers.append("eight_hour_observation_not_confirmed")
    if not no_reentry:
        blockers.append("reentry_or_extra_submit_detected")
    if not clean_state:
        blockers.append("paper_state_not_clean")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if unsafe_flag:
        blockers.append("unsafe_flag_detected")
    if upstream_activity:
        blockers.append("upstream_gate_created_activity")
    if settings.max_orders != 1:
        blockers.append("max_orders_must_equal_1")

    second_trade_rearm_enabled = settings.rearm_enabled
    second_trade_rearm_confirmation_ok = settings.rearm_confirmation_ok

    if unsafe_flag or upstream_activity or settings.max_orders != 1:
        decision = REJECT_DECISION
        status = "FAIL"
    elif any(b in blockers for b in ["paper_state_not_clean", "paper_state_inconsistent", "paper_status_inconsistent"]):
        decision = STATE_NOT_CLEAN_DECISION
        status = "WARN"
    elif blockers:
        decision = ELIGIBILITY_MISSING_DECISION
        status = "WARN"
    elif not second_trade_rearm_enabled:
        decision = NOT_ENABLED_DECISION
        status = "WARN"
    elif not second_trade_rearm_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status = "WARN"
    elif runtime_candidate_ready_events > 0 or runtime_would_route_count > 0 or order_intent_events > 0:
        decision = PASS_DECISION
        status = "PASS"
    else:
        decision = CANDIDATE_WAIT_DECISION
        status = "PASS"

    candidate_wait_gate_ready = status == "PASS" and second_trade_rearm_enabled and second_trade_rearm_confirmation_ok
    second_trade_rearm_ready = decision == PASS_DECISION

    classification_labels: list[str] = []
    if status == "PASS":
        classification_labels.append("SECOND_TRADE_CONTROLLED_REARM_PASS")
        if second_trade_rearm_ready:
            classification_labels.append("RUNTIME_CANDIDATE_OR_ROUTE_VISIBLE")
        else:
            classification_labels.append("WAITING_FOR_RUNTIME_CANDIDATE")
        classification_labels.append("SECOND_TRADE_EXECUTION_STILL_DISABLED")
    elif decision == NOT_ENABLED_DECISION:
        classification_labels.append("SECOND_TRADE_REARM_DISABLED")
    elif decision == CONFIRMATION_MISSING_DECISION:
        classification_labels.append("SECOND_TRADE_REARM_CONFIRMATION_MISSING")
    elif decision == STATE_NOT_CLEAN_DECISION:
        classification_labels.append("STATE_NOT_CLEAN")
    else:
        classification_labels.append("SECOND_TRADE_REARM_BLOCKED")

    report = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": blockers,
        "cycle_id": selected_cycle_id,
        "event_source": "paper_events_jsonl",
        "strict_cycle_scope": True,
        "second_trade_eligible": bool(second_trade_eligible and eligibility_pass),
        "second_trade_rearm_enabled": bool(second_trade_rearm_enabled),
        "second_trade_rearm_confirmation_ok": bool(second_trade_rearm_confirmation_ok),
        "candidate_wait_gate_ready": bool(candidate_wait_gate_ready),
        "second_trade_rearm_ready": bool(second_trade_rearm_ready),
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "broker_submit_called_by_second_trade_rearm_gate": False,
        "orders_submitted_by_second_trade_rearm_gate": 0,
        "positions_opened_by_second_trade_rearm_gate": 0,
        "positions_closed_by_second_trade_rearm_gate": 0,
        "paper_state_modified_by_second_trade_rearm_gate": False,
        "paper_status_modified_by_second_trade_rearm_gate": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "profile_name": settings.profile_name,
        "selected_overlay_id": settings.selected_overlay_id,
        "max_orders": settings.max_orders,
        "mode": settings.mode,
        "eligibility_decision": eligibility.get("decision"),
        "eligibility_status": eligibility.get("status"),
        "observation_pass": bool(observation_pass),
        "four_hour_observation_pass": bool(four_hour_observation_pass),
        "eight_hour_observation_pass": bool(eight_hour_observation_pass),
        "completed_observation_cycles": _safe_int(eligibility.get("completed_observation_cycles"), 0),
        "new_submit_cycles": eligibility.get("new_submit_cycles") if isinstance(eligibility.get("new_submit_cycles"), list) else [],
        "extra_submit_or_reentry_detected": not no_reentry,
        "state_open_lsr_v2_positions": state_open_lsr,
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "paper_state_consistency": bool(paper_state_consistency),
        "paper_status_consistency": bool(paper_status_consistency),
        "realized_pnl_total": _round(eligibility.get("realized_pnl_total"), 10),
        "realized_r": _round(eligibility.get("realized_r"), 10),
        "runtime_candidate_events": runtime_candidate_events,
        "runtime_candidate_ready_events": runtime_candidate_ready_events,
        "runtime_bridge_events": runtime_bridge_events,
        "runtime_would_route_count": runtime_would_route_count,
        "runtime_would_submit_count": 0,
        "order_intent_events": order_intent_events,
        "handoff_dry_run_events": handoff_dry_run_events,
        "submit_preflight_events": submit_preflight_events,
        "submit_boundary_events": submit_boundary_events,
        "historical_lsr_v2_events": len(historical_events),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }

    if write_outputs:
        _write_json(base / settings.report_name, report)
        _append_jsonl(base / settings.jsonl_name, build_lsr_v2_second_trade_rearm_gate_event(report=report))
    return report
