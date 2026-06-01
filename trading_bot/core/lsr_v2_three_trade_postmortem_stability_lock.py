"""Prompt 29.4.4s-10au — LSR-v2 three-trade postmortem / stability lock.

Audit-only consolidation for the first three supervised paper-only LSR-v2
trades. It verifies that the third closed-trade final audit is reconciled,
that no residual paper exposure or pending order remains, that operator envs are
not armed, and that a fourth/re-entry path remains locked until a future explicit
phase is defined. This module never submits, closes, mutates paper state/status,
or enables live/testnet/exchange brokers; it writes only its own JSON/JSONL audit
artifacts.
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

PROMPT_ID = "29.4.4s-10au"
EVENT_TYPE = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK"
REPORT_NAME = "lsr_v2_three_trade_postmortem_stability_lock_report.json"
JSONL_NAME = "lsr_v2_three_trade_postmortem_stability_lock.jsonl"

FIRST_FINAL_AUDIT_REPORT_NAME = "lsr_v2_closed_trade_final_audit_report.json"
FIRST_POSTMORTEM_REPORT_NAME = "lsr_v2_first_paper_trade_postmortem_report.json"
SECOND_FINAL_AUDIT_REPORT_NAME = "lsr_v2_second_closed_trade_final_audit_report.json"
TWO_TRADE_POSTMORTEM_REPORT_NAME = "lsr_v2_two_trade_paper_cycle_postmortem_report.json"
THIRD_SUBMIT_EXECUTION_REPORT_NAME = "lsr_v2_third_trade_submit_execution_report.json"
THIRD_LIFECYCLE_REPORT_NAME = "lsr_v2_third_trade_position_lifecycle_report.json"
THIRD_CLOSE_PREFLIGHT_REPORT_NAME = "lsr_v2_third_trade_close_preflight_report.json"
THIRD_CLOSE_EXECUTION_REPORT_NAME = "lsr_v2_third_trade_close_execution_report.json"
THIRD_FINAL_AUDIT_REPORT_NAME = "lsr_v2_third_closed_trade_final_audit_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

FIRST_FINAL_PASS_DECISION = "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS"
FIRST_POSTMORTEM_PASS_DECISION = "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS"
SECOND_FINAL_PASS_DECISION = "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS"
TWO_TRADE_PASS_DECISION = "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS"
THIRD_SUBMIT_EXECUTED_DECISION = "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED"
THIRD_LIFECYCLE_PASS_DECISION = "LSR_V2_THIRD_TRADE_POSITION_LIFECYCLE_READY"
THIRD_CLOSE_PREFLIGHT_PASS_DECISION = "LSR_V2_THIRD_TRADE_CLOSE_PREFLIGHT_READY"
THIRD_CLOSE_EXECUTED_DECISION = "LSR_V2_THIRD_SINGLE_PAPER_POSITION_CLOSED"
THIRD_FINAL_PASS_DECISION = "LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT_READY"

PASS_DECISION = "LSR_V2_THREE_TRADE_POSTMORTEM_STABILITY_LOCK_READY"
INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_POSTMORTEM_INCOMPLETE"
STATE_NOT_FLAT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_STATE_NOT_FLAT"
PNL_RECONCILIATION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_PNL_RECONCILIATION_REQUIRED"
ENV_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THREE_TRADE_OPERATOR_ENV_STILL_ACTIVE"
FOURTH_OR_REENTRY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FOURTH_TRADE_OR_REENTRY_DETECTED"
FAILED_DECISION = "REJECT_LSR_V2_THREE_TRADE_POSTMORTEM_SAFETY_FAILED"

LSR_V2_OPERATOR_ENV_PREFIX = "LSR_V2_"
_OPERATOR_ENV_MARKERS = (
    "ARM",
    "EXECUTE",
    "ENABLE",
    "CONFIRMATION",
    "MAX_POSITIONS",
)


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


def _append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), sort_keys=True) + "\n")


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _metadata(row: Mapping[str, Any]) -> dict[str, Any]:
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
    meta = _metadata(row)
    return str(
        row.get("paper_order_source")
        or row.get("paper_close_source")
        or row.get("execution_source")
        or row.get("source")
        or meta.get("paper_order_source")
        or meta.get("paper_close_source")
        or meta.get("execution_source")
        or meta.get("source")
        or meta.get("closed_by")
        or ""
    )


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_pending_order(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED", "FILLED"}:
        return False
    return _safe_bool(row.get("pending"), status not in {""})


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    text = " ".join(
        [
            _row_source(row),
            str(row.get("profile_name") or meta.get("profile_name") or ""),
            str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
            str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
        ]
    ).lower()
    return "lsr_v2" in text or "retest_limit" in text


def _report_pass(report: Mapping[str, Any], *, decision: str = "") -> bool:
    if not report:
        return False
    if str(report.get("status") or "").upper() != "PASS":
        return False
    return bool(not decision or str(report.get("decision") or "") == decision)


def _env_operator_controls() -> dict[str, Any]:
    active: dict[str, str] = {}
    for key, value in os.environ.items():
        if not key.startswith(LSR_V2_OPERATOR_ENV_PREFIX):
            continue
        upper = key.upper()
        if not any(marker in upper for marker in _OPERATOR_ENV_MARKERS):
            continue
        active[key] = "<set>" if value else ""
    return {
        "active_lsr_v2_operator_env_count": len(active),
        "active_lsr_v2_operator_env_names": sorted(active),
        "active_lsr_v2_operator_env_values_redacted": {k: active[k] for k in sorted(active)},
        "lsr_v2_operator_env_absent": len(active) == 0,
    }


def _count_event_types(rows: Iterable[Mapping[str, Any]], names: set[str]) -> int:
    total = 0
    for row in rows:
        if str(row.get("event_type") or "") in names or str(row.get("decision") or "") in names:
            total += 1
    return total


def _submit_count_from_third_report(report: Mapping[str, Any]) -> int:
    if _report_pass(report, decision=THIRD_SUBMIT_EXECUTED_DECISION):
        return 1
    for key in (
        "positions_opened_by_third_trade_execution",
        "orders_submitted_by_third_trade_execution",
        "execution_events",
        "broker_submit_called_count",
    ):
        count = _safe_int(report.get(key), 0)
        if count > 0:
            return 1
    return 0


def _close_count_from_third_final(report: Mapping[str, Any]) -> int:
    if _report_pass(report, decision=THIRD_FINAL_PASS_DECISION):
        return max(1, _safe_int(report.get("close_execution_events"), 0))
    return _safe_int(report.get("close_execution_events"), 0)


@dataclass(frozen=True)
class LSRV2ThreeTradePostmortemStabilityLockSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    first_final_audit_report_name: str = FIRST_FINAL_AUDIT_REPORT_NAME
    first_postmortem_report_name: str = FIRST_POSTMORTEM_REPORT_NAME
    second_final_audit_report_name: str = SECOND_FINAL_AUDIT_REPORT_NAME
    two_trade_postmortem_report_name: str = TWO_TRADE_POSTMORTEM_REPORT_NAME
    third_submit_execution_report_name: str = THIRD_SUBMIT_EXECUTION_REPORT_NAME
    third_lifecycle_report_name: str = THIRD_LIFECYCLE_REPORT_NAME
    third_close_preflight_report_name: str = THIRD_CLOSE_PREFLIGHT_REPORT_NAME
    third_close_execution_report_name: str = THIRD_CLOSE_EXECUTION_REPORT_NAME
    third_final_audit_report_name: str = THIRD_FINAL_AUDIT_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    max_event_lines: int = 50000
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2ThreeTradePostmortemStabilityLockSettings":
        return cls(data_dir=data_dir)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2ThreeTradePostmortemStabilityLockSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2ThreeTradePostmortemStabilityLockSettings.from_env(data_dir=str(data_dir))
    data = Path(data_dir)

    first_final = _read_json(data / settings.first_final_audit_report_name)
    first_postmortem = _read_json(data / settings.first_postmortem_report_name)
    second_final = _read_json(data / settings.second_final_audit_report_name)
    two_trade_postmortem = _read_json(data / settings.two_trade_postmortem_report_name)
    third_submit = _read_json(data / settings.third_submit_execution_report_name)
    third_lifecycle = _read_json(data / settings.third_lifecycle_report_name)
    third_close_preflight = _read_json(data / settings.third_close_preflight_report_name)
    third_close_execution = _read_json(data / settings.third_close_execution_report_name)
    third_final = _read_json(data / settings.third_final_audit_report_name)
    state = _read_json(data / settings.paper_state_name)
    status = _read_json(data / settings.paper_status_name)
    paper_events = _iter_jsonl_tail(data / settings.paper_events_name, max_lines=settings.max_event_lines)
    env = _env_operator_controls()

    first_final_pass = _report_pass(first_final, decision=FIRST_FINAL_PASS_DECISION)
    first_postmortem_pass = _report_pass(first_postmortem, decision=FIRST_POSTMORTEM_PASS_DECISION)
    second_final_pass = _report_pass(second_final, decision=SECOND_FINAL_PASS_DECISION)
    two_trade_postmortem_pass = _report_pass(two_trade_postmortem, decision=TWO_TRADE_PASS_DECISION)
    third_submit_executed = _report_pass(third_submit, decision=THIRD_SUBMIT_EXECUTED_DECISION)
    third_lifecycle_ready = _report_pass(third_lifecycle, decision=THIRD_LIFECYCLE_PASS_DECISION)
    third_close_preflight_ready = _report_pass(third_close_preflight, decision=THIRD_CLOSE_PREFLIGHT_PASS_DECISION)
    third_close_executed_report = _report_pass(third_close_execution, decision=THIRD_CLOSE_EXECUTED_DECISION)
    third_final_pass = _report_pass(third_final, decision=THIRD_FINAL_PASS_DECISION)

    first_pnl = _round(first_final.get("realized_pnl_total") or first_postmortem.get("realized_pnl_total"))
    second_pnl = _round(second_final.get("realized_pnl_total"))
    third_pnl = _round(third_final.get("realized_pnl_total"))
    first_risk = _round(first_final.get("total_risk_amount") or first_postmortem.get("total_risk_amount"))
    second_risk = _round(second_final.get("total_risk_amount"))
    third_risk = _round(third_submit.get("total_risk_amount") or third_close_preflight.get("total_risk_amount") or third_final.get("total_risk_amount"))
    total_risk = _round(first_risk + second_risk + third_risk)
    realized_pnl_sum_from_audits = _round(first_pnl + second_pnl + third_pnl)
    realized_pnl_after = _round(third_final.get("realized_pnl_after") if third_final else state.get("realized_pnl"))
    balance_after = _round(third_final.get("balance_after") if third_final else state.get("balance"))
    aggregate_realized_pnl = realized_pnl_after if realized_pnl_after != 0.0 else realized_pnl_sum_from_audits
    total_realized_r_from_audits = _round(realized_pnl_sum_from_audits / total_risk, 10) if total_risk > 0 else 0.0

    positions = _collection_rows(state.get("positions"), id_field="position_id")
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    open_positions = [row for row in positions if _is_position_open(row)]
    open_lsr_v2_positions = [row for row in open_positions if _is_lsr_v2_row(row)]
    pending_orders = [row for row in orders if _is_pending_order(row)]

    status_open_positions = _safe_int(status.get("open_positions"), len(open_positions))
    status_pending_orders = _safe_int(status.get("pending_orders"), len(pending_orders))
    flat_state_confirmed = bool(not open_positions and not open_lsr_v2_positions and status_open_positions == 0 and status_pending_orders == 0)
    paper_state_status_consistency = bool(status_open_positions == len(open_positions) and status_pending_orders == len(pending_orders))

    submit_total_from_two_trade = _safe_int(two_trade_postmortem.get("submit_execution_events_total"), 0)
    close_total_from_two_trade = _safe_int(two_trade_postmortem.get("close_execution_events_total"), 0)
    if submit_total_from_two_trade <= 0:
        submit_total_from_two_trade = _safe_int(first_final.get("submit_execution_events"), 0) + _safe_int(second_final.get("submit_execution_events"), 0)
    if close_total_from_two_trade <= 0:
        close_total_from_two_trade = _safe_int(first_final.get("close_execution_events"), 0) + _safe_int(second_final.get("close_execution_events"), 0)
    third_submit_count = _submit_count_from_third_report(third_submit)
    third_close_count = _close_count_from_third_final(third_final) or _safe_int(third_close_execution.get("close_execution_events"), 0)
    submit_execution_events_total = submit_total_from_two_trade + third_submit_count
    close_execution_events_total = close_total_from_two_trade + third_close_count

    cycle_ids = [
        str(first_final.get("cycle_id") or first_postmortem.get("cycle_id") or ""),
        str(second_final.get("cycle_id") or ""),
        str(third_final.get("cycle_id") or third_close_execution.get("cycle_id") or third_submit.get("cycle_id") or ""),
    ]
    cycle_ids = [c for c in cycle_ids if c]

    event_submit_like = _count_event_types(
        paper_events,
        {
            "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED",
            "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
            "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED",
            "LSR_V2_THIRD_TRADE_SUBMIT_EXECUTION",
        },
    )
    event_close_like = _count_event_types(
        paper_events,
        {
            "LSR_V2_PAPER_POSITION_CLOSED",
            "LSR_V2_SECOND_TRADE_CLOSE_EXECUTION",
            "LSR_V2_THIRD_TRADE_CLOSE_EXECUTION",
            "LSR_V2_THIRD_SINGLE_PAPER_POSITION_CLOSED",
        },
    )
    event_submit_over_expected = bool(event_submit_like > 3)

    fourth_submit_or_reentry_detected = bool(
        not flat_state_confirmed
        or pending_orders
        or _safe_bool(third_lifecycle.get("fourth_submit_or_reentry_detected"), False)
        or _safe_bool(third_final.get("new_order_created_after_close"), False)
        or _safe_bool(third_final.get("automatic_reentry_enabled"), False)
        or _safe_bool(third_final.get("no_submit_or_reentry"), True) is False
        or event_submit_over_expected
    )

    live_enabled = bool(
        _safe_bool(first_final.get("live_enabled"), False)
        or _safe_bool(second_final.get("live_enabled"), False)
        or _safe_bool(third_submit.get("live_enabled"), False)
        or _safe_bool(third_final.get("live_enabled"), False)
        or _safe_bool(status.get("live_enabled"), False)
    )
    testnet_enabled = bool(
        _safe_bool(first_final.get("testnet_enabled"), False)
        or _safe_bool(second_final.get("testnet_enabled"), False)
        or _safe_bool(third_submit.get("testnet_enabled"), False)
        or _safe_bool(third_final.get("testnet_enabled"), False)
        or _safe_bool(status.get("testnet_enabled"), False)
    )
    exchange_broker_enabled = bool(
        _safe_bool(first_final.get("exchange_broker_enabled"), False)
        or _safe_bool(second_final.get("exchange_broker_enabled"), False)
        or _safe_bool(third_submit.get("exchange_broker_enabled"), False)
        or _safe_bool(third_final.get("exchange_broker_enabled"), False)
        or _safe_bool(status.get("exchange_broker_enabled"), False)
    )
    operational_unlock_allowed = bool(
        _safe_bool(first_final.get("operational_unlock_allowed"), False)
        or _safe_bool(second_final.get("operational_unlock_allowed"), False)
        or _safe_bool(third_submit.get("operational_unlock_allowed"), False)
        or _safe_bool(third_final.get("operational_unlock_allowed"), False)
        or _safe_bool(status.get("operational_unlock_allowed"), False)
    )

    pnl_reconciliation_ok = bool(first_pnl > 0 and second_pnl > 0 and third_pnl > 0 and aggregate_realized_pnl > 0 and total_risk > 0)
    three_trade_reports_complete = bool(
        first_final_pass
        and first_postmortem_pass
        and second_final_pass
        and two_trade_postmortem_pass
        and third_submit_executed
        and third_lifecycle_ready
        and third_close_preflight_ready
        and third_final_pass
    )
    three_trade_lifecycle_complete = bool(
        three_trade_reports_complete
        and submit_execution_events_total == 3
        and close_execution_events_total >= 3
        and pnl_reconciliation_ok
        and flat_state_confirmed
        and paper_state_status_consistency
        and not fourth_submit_or_reentry_detected
    )
    safety_ok = bool(not live_enabled and not testnet_enabled and not exchange_broker_enabled and not operational_unlock_allowed)
    operator_env_absent = bool(env["lsr_v2_operator_env_absent"])

    blockers: list[str] = []
    if not first_final_pass:
        blockers.append("first_closed_trade_final_audit_not_pass")
    if not first_postmortem_pass:
        blockers.append("first_trade_postmortem_not_pass")
    if not second_final_pass:
        blockers.append("second_closed_trade_final_audit_not_pass")
    if not two_trade_postmortem_pass:
        blockers.append("two_trade_postmortem_not_pass")
    if not third_submit_executed:
        blockers.append("third_submit_execution_not_pass")
    if not third_lifecycle_ready:
        blockers.append("third_lifecycle_not_pass")
    if not third_close_preflight_ready:
        blockers.append("third_close_preflight_not_pass")
    if not third_final_pass:
        blockers.append("third_closed_trade_final_audit_not_pass")
    if submit_execution_events_total != 3:
        blockers.append("submit_execution_count_not_three")
    if close_execution_events_total < 3:
        blockers.append("close_execution_count_less_than_three")
    if not flat_state_confirmed:
        blockers.append("paper_state_or_status_not_flat")
    if not paper_state_status_consistency:
        blockers.append("paper_state_status_inconsistent")
    if not pnl_reconciliation_ok:
        blockers.append("pnl_reconciliation_required")
    if not operator_env_absent:
        blockers.append("lsr_v2_operator_env_still_present")
    if fourth_submit_or_reentry_detected:
        blockers.append("fourth_submit_or_reentry_detected")
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if operational_unlock_allowed:
        blockers.append("operational_unlock_allowed")

    if not safety_ok:
        decision = FAILED_DECISION
        status_text = "FAIL" if settings.fail_closed else "WARN"
    elif not operator_env_absent:
        decision = ENV_ACTIVE_DECISION
        status_text = "WARN"
    elif fourth_submit_or_reentry_detected:
        decision = FOURTH_OR_REENTRY_DECISION
        status_text = "WARN"
    elif not flat_state_confirmed or not paper_state_status_consistency:
        decision = STATE_NOT_FLAT_DECISION
        status_text = "WARN"
    elif not three_trade_reports_complete or submit_execution_events_total != 3 or close_execution_events_total < 3:
        decision = INCOMPLETE_DECISION
        status_text = "WARN"
    elif not pnl_reconciliation_ok:
        decision = PNL_RECONCILIATION_DECISION
        status_text = "WARN"
    elif not three_trade_lifecycle_complete:
        decision = INCOMPLETE_DECISION
        status_text = "WARN"
    else:
        decision = PASS_DECISION
        status_text = "PASS"

    classification_labels: list[str] = ["AUDIT_ONLY", "NO_STATE_MUTATION", "NO_REENTRY"]
    if decision == PASS_DECISION:
        classification_labels += ["THREE_TRADE_POSTMORTEM_READY", "STABILITY_LOCK_ACTIVE", "FOURTH_TRADE_LOCKED"]
    else:
        if not three_trade_reports_complete:
            classification_labels.append("THREE_TRADE_REPORTS_INCOMPLETE")
        if not flat_state_confirmed:
            classification_labels.append("STATE_NOT_FLAT")
        if fourth_submit_or_reentry_detected:
            classification_labels.append("FOURTH_OR_REENTRY_DETECTED")

    report = {
        "prompt": PROMPT_ID,
        "prompt_id": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": classification_labels,
        "blockers": sorted(set(blockers)),
        "cycle_ids": cycle_ids,
        "first_trade_cycle_id": cycle_ids[0] if len(cycle_ids) >= 1 else "",
        "second_trade_cycle_id": cycle_ids[1] if len(cycle_ids) >= 2 else "",
        "third_trade_cycle_id": cycle_ids[2] if len(cycle_ids) >= 3 else "",
        "three_trade_postmortem_complete": decision == PASS_DECISION,
        "three_trade_lifecycle_complete": bool(three_trade_lifecycle_complete),
        "three_trade_reports_complete": bool(three_trade_reports_complete),
        "first_closed_trade_final_audit_pass": bool(first_final_pass),
        "first_trade_postmortem_pass": bool(first_postmortem_pass),
        "second_closed_trade_final_audit_pass": bool(second_final_pass),
        "two_trade_postmortem_pass": bool(two_trade_postmortem_pass),
        "third_submit_execution_pass": bool(third_submit_executed),
        "third_lifecycle_ready": bool(third_lifecycle_ready),
        "third_close_preflight_ready": bool(third_close_preflight_ready),
        "third_close_execution_report_pass": bool(third_close_executed_report),
        "third_closed_trade_final_audit_pass": bool(third_final_pass),
        "submit_execution_events_total": int(submit_execution_events_total),
        "close_execution_events_total": int(close_execution_events_total),
        "paper_events_submit_like_count": int(event_submit_like),
        "paper_events_close_like_count": int(event_close_like),
        "first_realized_pnl": first_pnl,
        "second_realized_pnl": second_pnl,
        "third_realized_pnl": third_pnl,
        "realized_pnl_sum_from_final_audits": realized_pnl_sum_from_audits,
        "realized_pnl_after": realized_pnl_after,
        "aggregate_realized_pnl": aggregate_realized_pnl,
        "balance_after": balance_after,
        "first_risk_amount": first_risk,
        "second_risk_amount": second_risk,
        "third_risk_amount": third_risk,
        "total_risk_amount": total_risk,
        "total_realized_r_from_final_audits": total_realized_r_from_audits,
        "pnl_reconciliation_ok": bool(pnl_reconciliation_ok),
        "open_positions_after": len(open_positions),
        "open_lsr_v2_positions_after": len(open_lsr_v2_positions),
        "pending_orders_after": len(pending_orders),
        "paper_status_open_positions_after": int(status_open_positions),
        "paper_status_pending_orders_after": int(status_pending_orders),
        "flat_state_confirmed": bool(flat_state_confirmed),
        "paper_state_status_consistency": bool(paper_state_status_consistency),
        "operator_env_controls": env,
        "operator_env_absent": bool(operator_env_absent),
        "fourth_submit_or_reentry_detected": bool(fourth_submit_or_reentry_detected),
        "fourth_trade_allowed": False,
        "fourth_trade_locked": True,
        "automatic_reentry_enabled": False,
        "automatic_close_enabled": False,
        "stability_lock_active": True,
        "next_step": "no_reentry_until_new_explicit_observation_or_unlock_patch",
        "recommended_next_patch": "29.4.4s-10av — LSR-v2 post-three-trade observation plan / cooldown monitor",
        "orders_submitted_by_three_trade_postmortem": 0,
        "positions_opened_by_three_trade_postmortem": 0,
        "positions_closed_by_three_trade_postmortem": 0,
        "broker_submit_called_by_three_trade_postmortem": False,
        "broker_close_called_by_three_trade_postmortem": False,
        "paper_state_modified_by_three_trade_postmortem": False,
        "paper_status_modified_by_three_trade_postmortem": False,
        "paper_events_modified_by_three_trade_postmortem": False,
        "live_enabled": bool(live_enabled),
        "testnet_enabled": bool(testnet_enabled),
        "exchange_broker_enabled": bool(exchange_broker_enabled),
        "operational_unlock_allowed": bool(operational_unlock_allowed),
        "promotion_ready": False,
        "safety_checks": {
            "audit_only": True,
            "no_state_mutation": True,
            "no_status_mutation": True,
            "no_order_submit": True,
            "no_position_open": True,
            "no_position_close": True,
            "no_reentry": not bool(fourth_submit_or_reentry_detected),
            "fourth_trade_locked": True,
            "flat_state": bool(flat_state_confirmed),
            "operator_env_absent": bool(operator_env_absent),
            "live_disabled": not bool(live_enabled),
            "testnet_disabled": not bool(testnet_enabled),
            "exchange_broker_disabled": not bool(exchange_broker_enabled),
            "operational_unlock_blocked": not bool(operational_unlock_allowed),
        },
        "settings": settings.to_dict(),
        "report": str(data / settings.report_name),
        "jsonl": str(data / settings.jsonl_name),
    }
    _write_json(data / settings.report_name, report)
    _append_jsonl(data / settings.jsonl_name, report)
    return report
