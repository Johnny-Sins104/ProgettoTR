"""Prompt 29.4.4s-10aj — LSR-v2 third paper trade rearm gate.

This module is a non-mutating, diagnostic-only gate after the third-trade
eligibility gate.  It can mark the third LSR-v2 paper-trade path as
operator-rearmed only when the explicit manual rearm environment variables are
present and the upstream eligibility/observation/postmortem state remains clean.

It never submits orders, opens positions, closes positions, mutates paper
state/status, enables live/testnet/exchange brokers, or allows operational
unlock.  Later route/handoff/submit gates must still be introduced separately.
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

PROMPT_ID = "29.4.4s-10aj"
EVENT_TYPE = "LSR_V2_THIRD_TRADE_REARM_GATE"
REPORT_NAME = "lsr_v2_third_trade_rearm_gate_report.json"
JSONL_NAME = "lsr_v2_third_trade_rearm_gate.jsonl"

ELIGIBILITY_REPORT_NAME = "lsr_v2_third_trade_eligibility_gate_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

# Runtime/diagnostic events that may be visible in paper_events.jsonl.  The
# current rearm gate does not require them; it only exposes their counts so the
# next route-preflight patch can be cycle-scoped.
RUNTIME_CANDIDATE_EVENT_TYPE = "LSR_V2_RUNTIME_CANDIDATE_AUDIT"
RUNTIME_BRIDGE_EVENT_TYPE = "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT"
ORDER_INTENT_EVENT_TYPE = "LSR_V2_PAPER_ORDER_INTENT_AUDIT"
HANDOFF_EVENT_TYPE = "LSR_V2_PAPER_BROKER_HANDOFF_DRY_RUN"
SUBMIT_PREFLIGHT_EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_PREFLIGHT"
SUBMIT_BOUNDARY_EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_BOUNDARY"
CYCLE_COMPLETED_EVENT_TYPE = "CYCLE_COMPLETED"

ELIGIBILITY_PASS_DECISION = "LSR_V2_THIRD_PAPER_TRADE_ELIGIBILITY_PASS"
PASS_DECISION = "LSR_V2_THIRD_TRADE_REARM_READY_DIAGNOSTIC"
NOT_ENABLED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_REARM_NOT_ENABLED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_REARM_CONFIRMATION_MISSING"
ELIGIBILITY_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_ELIGIBILITY_MISSING"
STATE_NOT_CLEAN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_STATE_NOT_CLEAN"
THIRD_TRADE_NOT_LOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_NOT_LOCKED"
REENTRY_DETECTED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_REENTRY_DETECTED"
MAX_ORDER_CAP_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_MAX_ORDER_CAP_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_THIRD_TRADE_REARM_SAFETY_FAILED"

REQUIRED_REARM_VALUE = "1"
REQUIRED_REARM_CONFIRMATION = "I_UNDERSTAND_THIRD_PAPER_TRADE_DIAGNOSTIC_ONLY"
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
    text = " ".join([
        _row_source(row),
        str(row.get("profile_name") or meta.get("profile_name") or ""),
        str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
        str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
    ]).lower()
    return "lsr_v2" in text or "retest_limit" in text or PROFILE_NAME.lower() in text or SELECTED_OVERLAY_ID.lower() in text


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    closed_status = status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), not closed_status) and not closed_status


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}:
        return False
    return _safe_bool(row.get("pending"), status not in {"", "FILLED", "EXECUTED", "COMPLETE", "COMPLETED", "CLOSED"})


def _paper_status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_position_count") or monitor.get("open_positions"), 0)
    return 0


def _paper_status_pending_orders(status: Mapping[str, Any]) -> int:
    return _safe_int(status.get("pending_orders"), 0)


def _state_cleanliness(state: Mapping[str, Any], status: Mapping[str, Any]) -> dict[str, Any]:
    positions = [p for p in _collection_rows(state.get("positions"), id_field="position_id") if _is_lsr_v2_row(p)]
    open_lsr = [p for p in positions if _is_position_open(p)]
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    pending = [o for o in orders if _is_order_pending(o)]
    status_open = _paper_status_open_positions(status)
    status_pending = _paper_status_pending_orders(status)
    return {
        "state_lsr_v2_position_count": len(positions),
        "state_open_lsr_v2_positions": len(open_lsr),
        "state_pending_order_count": len(pending),
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "paper_state_consistency": len(open_lsr) == 0 and len(pending) == 0,
        "paper_status_consistency": status_open == 0 and status_pending == 0,
        "residual_open_position": bool(len(open_lsr) > 0 or status_open > 0),
        "pending_order_detected": bool(len(pending) > 0 or status_pending > 0),
    }


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
class LSRV2ThirdTradeRearmSettings:
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
    def from_env(cls, data_dir: str = "data") -> "LSRV2ThirdTradeRearmSettings":
        max_orders = _safe_int(os.getenv("LSR_V2_THIRD_TRADE_MAX_ORDERS"), 1)
        if max_orders <= 0:
            max_orders = 1
        return cls(
            data_dir=data_dir,
            rearm_enable=str(os.getenv("LSR_V2_THIRD_TRADE_REARM_ENABLE") or ""),
            rearm_confirmation=str(os.getenv("LSR_V2_THIRD_TRADE_REARM_CONFIRMATION") or ""),
            max_orders=max_orders,
            mode=str(os.getenv("LSR_V2_THIRD_TRADE_REARM_MODE") or "paper"),
        )

    @property
    def rearm_enabled(self) -> bool:
        return str(self.rearm_enable).strip() == self.required_rearm_value

    @property
    def rearm_confirmation_ok(self) -> bool:
        return str(self.rearm_confirmation).strip() == self.required_rearm_confirmation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _eligibility_pass(report: Mapping[str, Any]) -> bool:
    return bool(
        str(report.get("status") or "").upper() == "PASS"
        and str(report.get("decision") or "") == ELIGIBILITY_PASS_DECISION
        and _safe_bool(report.get("third_trade_eligible"), False)
        and _safe_bool(report.get("third_trade_gate_ready"), False)
    )


def build_lsr_v2_third_trade_rearm_gate_event(*, report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_type": EVENT_TYPE,
        "prompt": PROMPT_ID,
        "ts": utc_now_iso(),
        "cycle_id": report.get("cycle_id", ""),
        "decision": report.get("decision", ""),
        "status": report.get("status", ""),
        "third_trade_eligible": _safe_bool(report.get("third_trade_eligible"), False),
        "third_trade_rearm_enabled": _safe_bool(report.get("third_trade_rearm_enabled"), False),
        "third_trade_rearm_confirmation_ok": _safe_bool(report.get("third_trade_rearm_confirmation_ok"), False),
        "third_trade_rearm_ready": _safe_bool(report.get("third_trade_rearm_ready"), False),
        "candidate_wait_gate_ready": _safe_bool(report.get("candidate_wait_gate_ready"), False),
        "runtime_candidate_events": _safe_int(report.get("runtime_candidate_events"), 0),
        "runtime_candidate_ready_events": _safe_int(report.get("runtime_candidate_ready_events"), 0),
        "runtime_bridge_events": _safe_int(report.get("runtime_bridge_events"), 0),
        "runtime_would_route_count": _safe_int(report.get("runtime_would_route_count"), 0),
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "broker_submit_called": False,
        "orders_submitted_by_third_trade_rearm_gate": 0,
        "positions_opened_by_third_trade_rearm_gate": 0,
        "positions_closed_by_third_trade_rearm_gate": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
    }


def build_lsr_v2_third_trade_rearm_gate_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2ThirdTradeRearmSettings | None = None,
    write_outputs: bool = True,
) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or LSRV2ThirdTradeRearmSettings.from_env(str(base))

    eligibility = _read_json(base / settings.eligibility_report_name)
    paper_state = _read_json(base / settings.paper_state_name)
    paper_status = _read_json(base / settings.paper_status_name)
    event_cycle_id, current_events, historical_events = _safe_current_cycle_lsr_events(
        base, max_lines=settings.max_event_lines, requested_cycle_id=cycle_id
    )

    eligibility_cycles = eligibility.get("cycle_ids") if isinstance(eligibility.get("cycle_ids"), list) else []
    latest_eligibility_cycle = str((eligibility_cycles or [""])[-1] or eligibility.get("cycle_id") or "")
    selected_cycle_id = str(cycle_id or event_cycle_id or latest_eligibility_cycle or "")
    if selected_cycle_id and event_cycle_id and selected_cycle_id != event_cycle_id:
        current_events = _dedupe_events([row for row in current_events if _event_cycle(row) == selected_cycle_id])

    eligibility_pass = _eligibility_pass(eligibility)
    third_trade_eligible = _safe_bool(eligibility.get("third_trade_eligible"), False)
    four_hour_observation_pass = _safe_bool(eligibility.get("four_hour_observation_pass"), False)
    eight_hour_observation_pass = _safe_bool(eligibility.get("eight_hour_observation_pass"), False)
    third_locked_before = _safe_bool(eligibility.get("third_trade_locked"), False) or _safe_bool(eligibility.get("third_trade_locked_before_gate"), False)
    third_allowed_before = _safe_bool(eligibility.get("third_trade_allowed"), False) or _safe_bool(eligibility.get("third_trade_allowed_before_gate"), False)
    third_submit_or_reentry = _safe_bool(eligibility.get("third_submit_or_reentry_detected"), False)
    telemetry_ready = _safe_bool(eligibility.get("telegram_position_monitor_ready"), False)

    clean = _state_cleanliness(paper_state, paper_status)
    state_clean = bool(clean["paper_state_consistency"] and clean["paper_status_consistency"] and not clean["residual_open_position"] and not clean["pending_order_detected"])

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
        for key in ["orders_submitted_by_third_trade_gate", "positions_opened_by_third_trade_gate"]
    )

    blockers: list[str] = []
    if not eligibility_pass or not third_trade_eligible:
        blockers.append("third_trade_eligibility_not_pass")
    if not four_hour_observation_pass:
        blockers.append("four_hour_observation_not_confirmed")
    if not eight_hour_observation_pass:
        blockers.append("eight_hour_observation_not_confirmed")
    if not third_locked_before or third_allowed_before:
        blockers.append("third_trade_not_locked")
    if third_submit_or_reentry:
        blockers.append("third_submit_or_reentry_detected")
    if not telemetry_ready:
        blockers.append("telegram_position_monitor_not_ready")
    if not state_clean:
        blockers.append("paper_state_not_clean")
    if unsafe_flag:
        blockers.append("unsafe_flag_detected")
    if upstream_activity:
        blockers.append("upstream_gate_created_activity")
    if settings.max_orders != 1:
        blockers.append("max_orders_must_equal_1")
    if str(settings.mode).lower() != "paper":
        blockers.append("mode_not_paper")

    if unsafe_flag or upstream_activity:
        decision = REJECT_DECISION
        status = "FAIL"
    elif settings.max_orders != 1:
        decision = MAX_ORDER_CAP_DECISION
        status = "WARN"
    elif str(settings.mode).lower() != "paper":
        decision = REJECT_DECISION
        status = "FAIL"
    elif third_submit_or_reentry:
        decision = REENTRY_DETECTED_DECISION
        status = "WARN"
    elif not eligibility_pass or not third_trade_eligible:
        decision = ELIGIBILITY_MISSING_DECISION
        status = "WARN"
    elif not third_locked_before or third_allowed_before:
        decision = THIRD_TRADE_NOT_LOCKED_DECISION
        status = "WARN"
    elif not state_clean:
        decision = STATE_NOT_CLEAN_DECISION
        status = "WARN"
    elif not settings.rearm_enabled:
        decision = NOT_ENABLED_DECISION
        status = "WARN"
    elif not settings.rearm_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status = "WARN"
    else:
        decision = PASS_DECISION
        status = "PASS"

    candidate_wait_gate_ready = bool(status == "PASS" and settings.rearm_enabled and settings.rearm_confirmation_ok)
    third_trade_rearm_ready = bool(decision == PASS_DECISION)

    if status == "PASS":
        classification_labels = [
            "THIRD_TRADE_CONTROLLED_REARM_PASS",
            "THIRD_TRADE_EXECUTION_STILL_DISABLED",
            "PAPER_ONLY_DIAGNOSTIC_REARM",
        ]
        if runtime_candidate_ready_events > 0 or runtime_would_route_count > 0 or order_intent_events > 0:
            classification_labels.append("RUNTIME_CANDIDATE_OR_ROUTE_VISIBLE")
        else:
            classification_labels.append("WAITING_FOR_RUNTIME_CANDIDATE")
    elif decision == NOT_ENABLED_DECISION:
        classification_labels = ["THIRD_TRADE_REARM_DISABLED"]
    elif decision == CONFIRMATION_MISSING_DECISION:
        classification_labels = ["THIRD_TRADE_REARM_CONFIRMATION_MISSING"]
    elif decision == STATE_NOT_CLEAN_DECISION:
        classification_labels = ["STATE_NOT_CLEAN"]
    else:
        classification_labels = ["THIRD_TRADE_REARM_BLOCKED"]

    report = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": sorted(set(blockers)),
        "cycle_id": selected_cycle_id,
        "event_source": "paper_events_jsonl",
        "strict_cycle_scope": True,
        "third_trade_eligible": bool(third_trade_eligible and eligibility_pass),
        "third_trade_rearm_enabled": bool(settings.rearm_enabled),
        "third_trade_rearm_confirmation_ok": bool(settings.rearm_confirmation_ok),
        "candidate_wait_gate_ready": bool(candidate_wait_gate_ready),
        "third_trade_rearm_ready": bool(third_trade_rearm_ready),
        "third_trade_locked": True,
        "third_trade_allowed": False,
        "third_trade_execute_enabled": False,
        "third_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "broker_submit_called_by_third_trade_rearm_gate": False,
        "broker_close_called_by_third_trade_rearm_gate": False,
        "orders_submitted_by_third_trade_rearm_gate": 0,
        "positions_opened_by_third_trade_rearm_gate": 0,
        "positions_closed_by_third_trade_rearm_gate": 0,
        "paper_state_modified_by_third_trade_rearm_gate": False,
        "paper_status_modified_by_third_trade_rearm_gate": False,
        "automatic_reentry_enabled": False,
        "automatic_close_enabled": False,
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
        "four_hour_observation_pass": bool(four_hour_observation_pass),
        "eight_hour_observation_pass": bool(eight_hour_observation_pass),
        "completed_observation_cycles": _safe_int(eligibility.get("completed_observation_cycles"), 0),
        "failed_observation_cycles": _safe_int(eligibility.get("failed_observation_cycles"), 0),
        "timed_out_cycles": _safe_int(eligibility.get("timed_out_cycles"), 0),
        "third_submit_or_reentry_detected": bool(third_submit_or_reentry),
        "third_trade_locked_before_gate": bool(third_locked_before),
        "third_trade_allowed_before_gate": bool(third_allowed_before),
        "telegram_position_monitor_ready": bool(telemetry_ready),
        "state_open_lsr_v2_positions": clean["state_open_lsr_v2_positions"],
        "state_pending_order_count": clean["state_pending_order_count"],
        "paper_status_open_positions": clean["paper_status_open_positions"],
        "paper_status_pending_orders": clean["paper_status_pending_orders"],
        "paper_state_consistency": bool(clean["paper_state_consistency"]),
        "paper_status_consistency": bool(clean["paper_status_consistency"]),
        "residual_open_position": bool(clean["residual_open_position"]),
        "pending_order_detected": bool(clean["pending_order_detected"]),
        "total_realized_pnl": _round(eligibility.get("total_realized_pnl"), 10),
        "average_realized_r": _round(eligibility.get("average_realized_r"), 10),
        "total_risk_amount": _round(eligibility.get("total_risk_amount"), 10),
        "runtime_candidate_events": runtime_candidate_events,
        "runtime_candidate_ready_events": runtime_candidate_ready_events,
        "runtime_bridge_events": runtime_bridge_events,
        "runtime_would_route_count": runtime_would_route_count,
        "runtime_would_submit_count": 0,  # rearm gate never allows submit
        "order_intent_events": order_intent_events,
        "handoff_dry_run_events": handoff_dry_run_events,
        "submit_preflight_events": submit_preflight_events,
        "submit_boundary_events": submit_boundary_events,
        "historical_lsr_v2_events": len(historical_events),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "next_step": "third_trade_route_preflight" if third_trade_rearm_ready else "operator_rearm_or_resolve_blockers",
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }

    if write_outputs:
        _write_json(base / settings.report_name, report)
        _append_jsonl(base / settings.jsonl_name, build_lsr_v2_third_trade_rearm_gate_event(report=report))
    return report
