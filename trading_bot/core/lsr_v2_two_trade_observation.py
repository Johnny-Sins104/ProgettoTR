"""Prompt 29.4.4s-10af — LSR-v2 two-trade postmortem observation / third-trade lock monitor.

Read-only observation layer after two supervised paper-only LSR-v2 trades have
been opened, closed, and postmortem-audited. It verifies that the third trade
remains locked, no new submit/re-entry occurs, no residual exposure exists, and
paper state/status remain consistent. The optional observation loop may launch
paper once-cycles with all LSR-v2 submit/close/rearm environment switches
removed from the child process. This module never submits, closes, mutates paper
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
import os
import subprocess
import sys
import time

PROMPT_ID = "29.4.4s-10af"
EVENT_TYPE = "LSR_V2_TWO_TRADE_OBSERVATION"
REPORT_NAME = "lsr_v2_two_trade_observation_report.json"
JSONL_NAME = "lsr_v2_two_trade_observation.jsonl"
LOG_DIR_NAME = "lsr_v2_two_trade_observation_logs"

TWO_TRADE_POSTMORTEM_REPORT_NAME = "lsr_v2_two_trade_paper_cycle_postmortem_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

PASS_DECISION = "LSR_V2_TWO_TRADE_OBSERVATION_PASS"
IN_PROGRESS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TWO_TRADE_OBSERVATION_IN_PROGRESS"
THIRD_SUBMIT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_SUBMIT_OR_REENTRY_DETECTED"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TWO_TRADE_STATE_INCONSISTENT"
FAILED_DECISION = "REJECT_LSR_V2_TWO_TRADE_OBSERVATION_FAILED"

POSTMORTEM_PASS_DECISION = "LSR_V2_TWO_TRADE_PAPER_CYCLE_POSTMORTEM_PASS"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"

# Observation must not inherit any manual route/submit/close/rearm switches.
DANGEROUS_ENV_PREFIXES = (
    "LSR_V2_PAPER_SUBMIT_",
    "LSR_V2_PAPER_CLOSE_",
    "LSR_V2_SECOND_TRADE_",
    "LSR_V2_THIRD_TRADE_",
)
DANGEROUS_ENV_KEYS = {
    "LSR_V2_PAPER_SUPERVISED_OPERATOR_ENABLE",
    "LSR_V2_PAPER_SUPERVISED_OPERATOR_CONFIRMATION",
}


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


def _is_lsr_v2_row(row: Mapping[str, Any]) -> bool:
    meta = _metadata(row)
    text = " ".join([
        _row_source(row),
        str(row.get("profile_name") or meta.get("profile_name") or ""),
        str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or ""),
        str(row.get("trade_sequence") or meta.get("trade_sequence") or ""),
    ]).lower()
    return "lsr_v2" in text or "retest_limit" in text or PROFILE_NAME.lower() in text or SELECTED_OVERLAY_ID.lower() in text


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


def _count_submit_like_events(rows: Iterable[Mapping[str, Any]]) -> int:
    needles = (
        "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED",
        "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED",
        "LSR_V2_THIRD_SINGLE_PAPER_ORDER_EXECUTED",
        "PAPER_ORDER_FILLED",
        "POSITION_OPENED",
    )
    count = 0
    for row in rows:
        et = str(row.get("event_type") or "")
        decision = str(row.get("decision") or "")
        source = _row_source(row).lower()
        if (et in needles or decision in needles) and ("lsr_v2" in source or "LSR_V2" in et or "LSR_V2" in decision):
            count += 1
    return count


def _sanitized_child_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env.keys()):
        if key in DANGEROUS_ENV_KEYS or any(key.startswith(prefix) for prefix in DANGEROUS_ENV_PREFIXES):
            env.pop(key, None)
    return env


def _project_root_from_data_dir(data_dir: Path) -> Path:
    # In the normal layout data_dir is <project>/data. In tests, this still
    # resolves safely and subprocess execution can be disabled.
    return data_dir.resolve().parent


def _run_paper_once_cycle(data_dir: Path, *, cycle_index: int, timeout_seconds: int = 900) -> dict[str, Any]:
    root = _project_root_from_data_dir(data_dir)
    log_dir = data_dir / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"cycle_{cycle_index:04d}.log"
    cmd = [
        sys.executable,
        "trading_bot/run_paper_trading.py",
        "--mode",
        "paper",
        "--timeframe",
        "5m",
        "--cost-model",
        "conservative",
        "--once",
        "--paper-unlock",
    ]
    started = utc_now_iso()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            env=_sanitized_child_env(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        log_path.write_text((proc.stdout or "") + ("\n[STDERR]\n" + proc.stderr if proc.stderr else ""), encoding="utf-8")
        return {
            "cycle_index": cycle_index,
            "started_at": started,
            "completed_at": utc_now_iso(),
            "returncode": proc.returncode,
            "timed_out": False,
            "log_path": str(log_path),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        log_path.write_text(stdout + ("\n[STDERR]\n" + stderr if stderr else "") + "\n[TIMEOUT]\n", encoding="utf-8")
        return {
            "cycle_index": cycle_index,
            "started_at": started,
            "completed_at": utc_now_iso(),
            "returncode": None,
            "timed_out": True,
            "log_path": str(log_path),
        }


def build_lsr_v2_two_trade_observation_report_from_files(
    *,
    data_dir: str | Path = "data",
    completed_observation_cycles: int = 0,
    failed_observation_cycles: int = 0,
    timed_out_cycles: int = 0,
    cycle_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data = Path(data_dir)
    postmortem = _read_json(data / TWO_TRADE_POSTMORTEM_REPORT_NAME)
    state = _read_json(data / PAPER_STATE_NAME)
    status = _read_json(data / PAPER_STATUS_NAME)
    paper_events = _iter_jsonl_tail(data / PAPER_EVENTS_NAME)

    postmortem_pass = _report_pass(postmortem, decision=POSTMORTEM_PASS_DECISION)
    submit_total = _safe_int(postmortem.get("submit_execution_events_total"), 0)
    close_total = _safe_int(postmortem.get("close_execution_events_total"), 0)
    third_trade_locked = _safe_bool(postmortem.get("third_trade_locked"), False)
    third_trade_allowed = _safe_bool(postmortem.get("third_trade_allowed"), False)
    postmortem_third_detected = _safe_bool(postmortem.get("third_submit_or_reentry_detected"), False)

    positions = [row for row in _state_positions(state) if _is_lsr_v2_row(row)]
    open_positions = [row for row in positions if _is_position_open(row)]
    paper_status_open = _paper_status_open_positions(status)
    paper_status_pending = _paper_status_pending_orders(status)

    event_submit_like = _count_submit_like_events(paper_events)
    # paper_events may not contain the dedicated submit execution audit events;
    # when it does, anything beyond the two known supervised submits is treated
    # as third submit/re-entry evidence.
    paper_event_third_submit_detected = event_submit_like > 2

    residual_open_position = len(open_positions) > 0 or paper_status_open > 0
    paper_state_consistency = len(open_positions) == 0
    paper_status_consistency = paper_status_open == 0 and paper_status_pending == 0
    extra_submit_or_reentry_detected = postmortem_third_detected or paper_event_third_submit_detected or submit_total > 2 or residual_open_position

    live_enabled = _safe_bool(postmortem.get("live_enabled"), False)
    testnet_enabled = _safe_bool(postmortem.get("testnet_enabled"), False)
    exchange_broker_enabled = _safe_bool(postmortem.get("exchange_broker_enabled"), False)
    operational_unlock_allowed = _safe_bool(postmortem.get("operational_unlock_allowed"), False)

    blockers: list[str] = []
    if not postmortem_pass:
        blockers.append("two_trade_postmortem_not_pass")
    if submit_total != 2:
        blockers.append("submit_execution_count_not_two")
    if close_total != 2:
        blockers.append("close_execution_count_not_two")
    if third_trade_allowed or not third_trade_locked:
        blockers.append("third_trade_not_locked")
    if residual_open_position:
        blockers.append("residual_open_position")
    if not paper_state_consistency:
        blockers.append("paper_state_inconsistent")
    if not paper_status_consistency:
        blockers.append("paper_status_inconsistent")
    if extra_submit_or_reentry_detected:
        blockers.append("third_submit_or_reentry_detected")
    if failed_observation_cycles:
        blockers.append("failed_observation_cycles")
    if timed_out_cycles:
        blockers.append("timed_out_cycles")
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
    elif extra_submit_or_reentry_detected:
        decision = THIRD_SUBMIT_DECISION
        status_text = "WARN"
    elif not paper_state_consistency or not paper_status_consistency:
        decision = STATE_INCONSISTENT_DECISION
        status_text = "WARN"
    elif not postmortem_pass or third_trade_allowed or not third_trade_locked or failed_observation_cycles or timed_out_cycles:
        decision = IN_PROGRESS_DECISION
        status_text = "WARN"
    else:
        decision = PASS_DECISION
        status_text = "PASS"

    labels: list[str] = []
    if decision == PASS_DECISION:
        labels = ["TWO_TRADE_OBSERVATION_PASS", "NO_REENTRY_DETECTED", "THIRD_TRADE_LOCKED", "NO_RESIDUAL_POSITION"]
    else:
        if extra_submit_or_reentry_detected:
            labels.append("THIRD_SUBMIT_OR_REENTRY_DETECTED")
        if residual_open_position:
            labels.append("RESIDUAL_POSITION_PRESENT")
        if not postmortem_pass:
            labels.append("TWO_TRADE_POSTMORTEM_REQUIRED")

    report = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "ts": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "cycle_ids": list(postmortem.get("cycle_ids") or []),
        "postmortem_pass": postmortem_pass,
        "two_trade_postmortem_complete": _safe_bool(postmortem.get("two_trade_postmortem_complete"), False),
        "submit_execution_events_total": submit_total,
        "close_execution_events_total": close_total,
        "total_realized_pnl": _round(postmortem.get("total_realized_pnl")),
        "average_realized_r": _round(postmortem.get("average_realized_r")),
        "total_risk_amount": _round(postmortem.get("total_risk_amount")),
        "pnl_reconciliation_ok": _safe_bool(postmortem.get("pnl_reconciliation_ok"), False),
        "state_open_lsr_v2_positions": len(open_positions),
        "paper_status_open_positions": paper_status_open,
        "paper_status_pending_orders": paper_status_pending,
        "paper_state_consistency": paper_state_consistency,
        "paper_status_consistency": paper_status_consistency,
        "residual_open_position": residual_open_position,
        "third_trade_allowed": False,
        "third_trade_locked": third_trade_locked and not third_trade_allowed,
        "third_submit_or_reentry_detected": extra_submit_or_reentry_detected,
        "paper_event_submit_like_count": event_submit_like,
        "new_submit_cycles": [] if not extra_submit_or_reentry_detected else ["UNKNOWN_THIRD_SUBMIT_OR_RESIDUAL_EXPOSURE"],
        "completed_observation_cycles": completed_observation_cycles,
        "failed_observation_cycles": failed_observation_cycles,
        "timed_out_cycles": timed_out_cycles,
        "cycle_results": cycle_results or [],
        "orders_submitted_by_two_trade_observation": 0,
        "positions_opened_by_two_trade_observation": 0,
        "positions_closed_by_two_trade_observation": 0,
        "broker_submit_called_by_two_trade_observation": False,
        "broker_close_called_by_two_trade_observation": False,
        "paper_state_modified_by_two_trade_observation": False,
        "paper_status_modified_by_two_trade_observation": False,
        "automatic_reentry_enabled": False,
        "automatic_close_enabled": False,
        "live_enabled": live_enabled,
        "testnet_enabled": testnet_enabled,
        "exchange_broker_enabled": exchange_broker_enabled,
        "operational_unlock_allowed": operational_unlock_allowed,
        "promotion_ready": False,
        "next_step_observation_required": False,
        "report": str(data / REPORT_NAME),
        "jsonl": str(data / JSONL_NAME),
        "log_dir": str(data / LOG_DIR_NAME),
    }
    _write_json(data / REPORT_NAME, report)
    _append_jsonl(data / JSONL_NAME, report)
    return report


def run_two_trade_observation(
    *,
    data_dir: str | Path = "data",
    run_paper_cycles: bool = False,
    max_cycles: int = 0,
    duration_hours: float = 0.0,
    interval_seconds: float = 300.0,
    cycle_timeout_seconds: int = 900,
) -> dict[str, Any]:
    data = Path(data_dir)
    if not run_paper_cycles:
        return build_lsr_v2_two_trade_observation_report_from_files(data_dir=data)

    start = time.monotonic()
    completed = 0
    failed = 0
    timed_out = 0
    results: list[dict[str, Any]] = []
    cycle_index = 0
    while True:
        if max_cycles and cycle_index >= max_cycles:
            break
        if duration_hours and (time.monotonic() - start) >= duration_hours * 3600.0:
            break
        cycle_index += 1
        result = _run_paper_once_cycle(data, cycle_index=cycle_index, timeout_seconds=cycle_timeout_seconds)
        results.append(result)
        if result.get("timed_out"):
            timed_out += 1
        elif _safe_int(result.get("returncode"), -1) == 0:
            completed += 1
        else:
            failed += 1

        interim = build_lsr_v2_two_trade_observation_report_from_files(
            data_dir=data,
            completed_observation_cycles=completed,
            failed_observation_cycles=failed,
            timed_out_cycles=timed_out,
            cycle_results=results,
        )
        # Stop early if a true safety issue appears.
        if interim.get("decision") in {THIRD_SUBMIT_DECISION, STATE_INCONSISTENT_DECISION, FAILED_DECISION}:
            return interim
        if max_cycles and cycle_index >= max_cycles:
            break
        if duration_hours and (time.monotonic() - start) >= duration_hours * 3600.0:
            break
        if interval_seconds > 0:
            time.sleep(interval_seconds)

    return build_lsr_v2_two_trade_observation_report_from_files(
        data_dir=data,
        completed_observation_cycles=completed,
        failed_observation_cycles=failed,
        timed_out_cycles=timed_out,
        cycle_results=results,
    )
