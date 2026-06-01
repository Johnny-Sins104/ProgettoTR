"""Prompt 29.4.4s-10ae-1 — LSR-v2 two-trade paper cycle postmortem / third-trade lock.

Read-only aggregation audit for the first two supervised paper-only LSR-v2
trades. It verifies both closed-trade audits, reconciles combined realized
outcome, confirms there is no residual exposure or third submit/re-entry, and
locks any third trade pending a fresh observation phase. It never submits,
closes, mutates paper state/status, or enables live/testnet/exchange brokers.
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

PROMPT_ID = "29.4.4s-10ae-1"
EVENT_TYPE = "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM"
REPORT_NAME = "lsr_v2_two_trade_paper_cycle_postmortem_report.json"
JSONL_NAME = "lsr_v2_two_trade_paper_cycle_postmortem.jsonl"

FIRST_POSTMORTEM_REPORT_NAME = "lsr_v2_first_paper_trade_postmortem_report.json"
FIRST_FINAL_AUDIT_REPORT_NAME = "lsr_v2_closed_trade_final_audit_report.json"
SECOND_FINAL_AUDIT_REPORT_NAME = "lsr_v2_second_closed_trade_final_audit_report.json"
POST_FIRST_OBSERVATION_REPORT_NAME = "lsr_v2_post_first_trade_observation_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

PASS_DECISION = "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS"
INCOMPLETE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TWO_TRADE_POSTMORTEM_INCOMPLETE"
RESIDUAL_POSITION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TWO_TRADE_RESIDUAL_OPEN_POSITION"
PNL_RECONCILIATION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TWO_TRADE_PNL_RECONCILIATION_REQUIRED"
THIRD_SUBMIT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_TRADE_OR_REENTRY_DETECTED"
FAILED_DECISION = "REJECT_LSR_V2_TWO_TRADE_POSTMORTEM_SAFETY_FAILED"

FIRST_PASS_DECISION = "LSR_V2_CLOSED_TRADE_FINAL_AUDIT_PASS"
FIRST_POSTMORTEM_PASS_DECISION = "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS"
SECOND_PASS_DECISION = "LSR_V2_SECOND_CLOSED_TRADE_FINAL_AUDIT_PASS"


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
    return str(row.get("paper_order_source") or row.get("execution_source") or row.get("source") or meta.get("paper_order_source") or meta.get("execution_source") or meta.get("source") or "")


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_lsr_v2_position(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    text = " ".join([
        _row_source(row),
        str(row.get("profile_name") or meta.get("profile_name") or ""),
        str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
        str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
    ]).lower()
    return "lsr_v2" in text or "lrs_v2" in text or "retest_limit" in text


def _state_positions(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _collection_rows(state.get("positions"), id_field="position_id")


def _paper_status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_positions") or monitor.get("open_position_count"), 0)
    return 0


def _paper_status_pending_orders(status: Mapping[str, Any]) -> int:
    return _safe_int(status.get("pending_orders"), 0)


def _report_pass(report: Mapping[str, Any], *, decision: str = "") -> bool:
    if not report:
        return False
    if str(report.get("status") or "").upper() != "PASS":
        return False
    if decision and report.get("decision") != decision:
        return False
    return True


def _event_type_count(rows: Iterable[Mapping[str, Any]], needles: set[str]) -> int:
    count = 0
    for row in rows:
        et = str(row.get("event_type") or "")
        decision = str(row.get("decision") or "")
        if et in needles or decision in needles:
            count += 1
    return count


def build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(
    *,
    data_dir: str | Path = "data",
) -> dict[str, Any]:
    data = Path(data_dir)
    first_postmortem = _read_json(data / FIRST_POSTMORTEM_REPORT_NAME)
    first_final = _read_json(data / FIRST_FINAL_AUDIT_REPORT_NAME)
    second_final = _read_json(data / SECOND_FINAL_AUDIT_REPORT_NAME)
    observation = _read_json(data / POST_FIRST_OBSERVATION_REPORT_NAME)
    state = _read_json(data / PAPER_STATE_NAME)
    status = _read_json(data / PAPER_STATUS_NAME)
    paper_events = _iter_jsonl_tail(data / PAPER_EVENTS_NAME)

    first_final_pass = _report_pass(first_final, decision=FIRST_PASS_DECISION)
    first_postmortem_pass = _report_pass(first_postmortem, decision=FIRST_POSTMORTEM_PASS_DECISION)
    second_final_pass = _report_pass(second_final, decision=SECOND_PASS_DECISION)
    observation_pass = _report_pass(observation, decision="LSR_V2_POST_FIRST_TRADE_OBSERVATION_PASS") or _safe_bool(observation.get("observation_pass"), False)

    first_pnl = _round(first_final.get("realized_pnl_total") if first_final else first_postmortem.get("realized_pnl_total"))
    second_pnl = _round(second_final.get("realized_pnl_total"))
    first_r = _round(first_final.get("realized_r") if first_final else first_postmortem.get("realized_r"))
    second_r = _round(second_final.get("realized_r"))
    first_risk = _round(first_final.get("total_risk_amount") if first_final else first_postmortem.get("total_risk_amount"))
    second_risk = _round(second_final.get("total_risk_amount"))
    total_risk = _round(first_risk + second_risk)
    total_realized_pnl = _round(first_pnl + second_pnl)
    total_realized_r = _round(total_realized_pnl / total_risk, 10) if total_risk > 0 else 0.0
    average_realized_r = _round((first_r + second_r) / 2.0, 10) if (first_r or second_r) else 0.0

    positions = [row for row in _state_positions(state) if _is_lsr_v2_position(row)]
    open_positions = [row for row in positions if _is_position_open(row)]
    closed_positions = [row for row in positions if not _is_position_open(row)]
    paper_status_open = _paper_status_open_positions(status)
    paper_status_pending = _paper_status_pending_orders(status)

    submit_total = _safe_int(first_final.get("submit_execution_events"), 0) + _safe_int(second_final.get("submit_execution_events"), 0)
    close_total = _safe_int(first_final.get("close_execution_events"), 0) + _safe_int(second_final.get("close_execution_events"), 0)
    # Event-log check is only a guardrail; reports are the authoritative cycle-scoped source.
    event_submit_like = _event_type_count(paper_events, {"LSR_V2_SINGLE_PAPER_ORDER_EXECUTED", "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED"})

    residual_open_position = len(open_positions) > 0 or paper_status_open > 0
    # Prompt 29.4.4s-10ae-1 hotfix: paper_state is not the authoritative
    # closed-trade ledger. Some PaperBrokerAdapter schemas retain only the latest
    # closed LSR-v2 position in paper_state, while the cycle-scoped final audit
    # reports and close execution JSONL files retain both realized outcomes. For
    # two-trade postmortem, paper_state is therefore used only as a residual
    # exposure guard: no open LSR-v2 positions may remain. Closed-history
    # completeness is reported diagnostically but no longer blocks PASS when the
    # two final audits reconcile.
    closed_position_history_complete = len(closed_positions) >= 2
    paper_state_consistency = len(open_positions) == 0
    paper_status_consistency = paper_status_open == 0 and paper_status_pending == 0
    pnl_reconciliation_ok = first_pnl > 0 and second_pnl > 0 and total_realized_pnl > 0 and total_risk > 0 and total_realized_r > 0
    two_trade_complete = first_final_pass and first_postmortem_pass and second_final_pass and submit_total == 2 and close_total == 2 and pnl_reconciliation_ok and paper_state_consistency and paper_status_consistency

    third_submit_or_reentry_detected = (
        _safe_bool(first_postmortem.get("extra_submit_or_reentry_detected"), False)
        or _safe_bool(second_final.get("third_submit_or_reentry_detected"), False)
        or submit_total > 2
        or event_submit_like > 2
        or residual_open_position
    )

    live_enabled = _safe_bool(first_final.get("live_enabled"), False) or _safe_bool(second_final.get("live_enabled"), False) or _safe_bool(observation.get("live_enabled"), False)
    testnet_enabled = _safe_bool(first_final.get("testnet_enabled"), False) or _safe_bool(second_final.get("testnet_enabled"), False) or _safe_bool(observation.get("testnet_enabled"), False)
    exchange_broker_enabled = _safe_bool(first_final.get("exchange_broker_enabled"), False) or _safe_bool(second_final.get("exchange_broker_enabled"), False) or _safe_bool(observation.get("exchange_broker_enabled"), False)
    operational_unlock_allowed = _safe_bool(first_final.get("operational_unlock_allowed"), False) or _safe_bool(second_final.get("operational_unlock_allowed"), False) or _safe_bool(observation.get("operational_unlock_allowed"), False)

    blockers: list[str] = []
    if not first_final_pass:
        blockers.append("first_closed_trade_final_audit_not_pass")
    if not first_postmortem_pass:
        blockers.append("first_trade_postmortem_not_pass")
    if not second_final_pass:
        blockers.append("second_closed_trade_final_audit_not_pass")
    if submit_total != 2:
        blockers.append("submit_execution_count_not_two")
    if close_total != 2:
        blockers.append("close_execution_count_not_two")
    if residual_open_position:
        blockers.append("residual_open_position")
    if not paper_state_consistency:
        blockers.append("paper_state_residual_open_position")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if not pnl_reconciliation_ok:
        blockers.append("pnl_reconciliation_required")
    if third_submit_or_reentry_detected:
        blockers.append("third_submit_or_reentry_detected")
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
    elif not two_trade_complete:
        decision = INCOMPLETE_DECISION
        status_text = "WARN"
    else:
        decision = PASS_DECISION
        status_text = "PASS"

    labels: list[str] = []
    if decision == PASS_DECISION:
        labels = ["TWO_TRADE_POSTMORTEM_PASS", "NO_RESIDUAL_POSITION", "REALIZED_PNL_RECONCILED", "THIRD_TRADE_LOCKED", "NEXT_STEP_OBSERVATION_REQUIRED"]
    else:
        if residual_open_position:
            labels.append("RESIDUAL_POSITION_PRESENT")
        if third_submit_or_reentry_detected:
            labels.append("THIRD_SUBMIT_OR_REENTRY_DETECTED")
        if not pnl_reconciliation_ok:
            labels.append("PNL_RECONCILIATION_REQUIRED")

    cycle_ids = [str(x) for x in [first_final.get("cycle_id") or first_postmortem.get("cycle_id"), second_final.get("cycle_id")] if x]
    report = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "ts": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "cycle_ids": cycle_ids,
        "first_trade_cycle_id": cycle_ids[0] if cycle_ids else "",
        "second_trade_cycle_id": cycle_ids[1] if len(cycle_ids) > 1 else "",
        "two_trade_postmortem_complete": decision == PASS_DECISION,
        "first_closed_trade_final_audit_pass": first_final_pass,
        "first_trade_postmortem_pass": first_postmortem_pass,
        "post_first_trade_observation_pass": observation_pass,
        "second_closed_trade_final_audit_pass": second_final_pass,
        "submit_execution_events_total": submit_total,
        "close_execution_events_total": close_total,
        "first_realized_pnl": first_pnl,
        "second_realized_pnl": second_pnl,
        "total_realized_pnl": total_realized_pnl,
        "first_realized_r": first_r,
        "second_realized_r": second_r,
        "total_realized_r": total_realized_r,
        "average_realized_r": average_realized_r,
        "total_risk_amount": total_risk,
        "pnl_reconciliation_ok": pnl_reconciliation_ok,
        "state_open_lsr_v2_positions": len(open_positions),
        "state_closed_lsr_v2_positions": len(closed_positions),
        "paper_state_closed_history_complete": closed_position_history_complete,
        "paper_state_closed_history_source_is_authoritative": False,
        "paper_state_closed_history_note": "paper_state may retain only the latest closed LSR-v2 position; final audit reports are authoritative for closed-trade count",
        "paper_status_open_positions": paper_status_open,
        "paper_status_pending_orders": paper_status_pending,
        "paper_state_consistency": paper_state_consistency,
        "paper_status_consistency": paper_status_consistency,
        "residual_open_position": residual_open_position,
        "third_submit_or_reentry_detected": third_submit_or_reentry_detected,
        "third_trade_allowed": False,
        "third_trade_locked": True,
        "next_step_observation_required": decision == PASS_DECISION,
        "recommended_observation_hours_first": 4,
        "recommended_observation_hours_second": 8,
        "orders_submitted_by_two_trade_postmortem": 0,
        "positions_opened_by_two_trade_postmortem": 0,
        "positions_closed_by_two_trade_postmortem": 0,
        "broker_submit_called_by_two_trade_postmortem": False,
        "broker_close_called_by_two_trade_postmortem": False,
        "paper_state_modified_by_two_trade_postmortem": False,
        "paper_status_modified_by_two_trade_postmortem": False,
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
