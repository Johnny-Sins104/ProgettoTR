"""Prompt 29.4.4s-10r — LSR-v2 post-first-trade observation / no-reentry stability monitor.

This module observes the system after the first supervised LSR-v2 paper-only
trade has been opened, closed, final-audited, and postmortem-locked. It is
read-only by default and during observation it does not submit, close, mutate
paper state/status, re-enter, or enable live/testnet/exchange brokers.
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

PROMPT_ID = "29.4.4s-10r"
EVENT_TYPE = "LSR_V2_POST_FIRST_TRADE_OBSERVATION"
REPORT_NAME = "lsr_v2_post_first_trade_observation_report.json"
JSONL_NAME = "lsr_v2_post_first_trade_observation.jsonl"
LOG_DIR_NAME = "lsr_v2_post_first_trade_observation_logs"

PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"
POSTMORTEM_REPORT_NAME = "lsr_v2_first_paper_trade_postmortem_report.json"
POSTMORTEM_JSONL_NAME = "lsr_v2_first_paper_trade_postmortem.jsonl"
SUBMIT_EXEC_REPORT_NAME = "lsr_v2_supervised_paper_submit_execution_report.json"
SUBMIT_EXEC_JSONL_NAME = "lsr_v2_supervised_paper_submit_execution.jsonl"
CLOSE_EXEC_REPORT_NAME = "lsr_v2_supervised_paper_close_execution_report.json"
CLOSE_EXEC_JSONL_NAME = "lsr_v2_supervised_paper_close_execution.jsonl"
FINAL_AUDIT_REPORT_NAME = "lsr_v2_closed_trade_final_audit_report.json"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"

PASS_DECISION = "LSR_V2_POST_FIRST_TRADE_OBSERVATION_PASS"
IN_PROGRESS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OBSERVATION_IN_PROGRESS"
REENTRY_DETECTED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_REENTRY_DETECTED"
NEW_SUBMIT_DETECTED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_NEW_SUBMIT_DETECTED"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_STATE_INCONSISTENT"
REJECT_DECISION = "REJECT_LSR_V2_POST_TRADE_OBSERVATION_FAILED"

# Environment switches that must not leak into the observation loop.
SUBMIT_OR_CLOSE_ENV_PREFIXES = (
    "LSR_V2_PAPER_SUBMIT_",
    "LSR_V2_PAPER_CLOSE_",
)
SUBMIT_OR_CLOSE_ENV_KEYS = {
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


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 100000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

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


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_lsr_v2_row(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    meta = _metadata(row)
    source = _row_source(row).lower()
    profile = str(row.get("profile_name") or meta.get("profile_name") or "")
    overlay = str(row.get("selected_overlay_id") or meta.get("selected_overlay_id") or "")
    source_ok = "lsr_v2" in source or profile == PROFILE_NAME or overlay == SELECTED_OVERLAY_ID
    if not source_ok:
        return False
    row_cycle = _row_cycle(row)
    if cycle_id and row_cycle and row_cycle != cycle_id:
        return False
    return True


def _paper_status_open_positions(status: Mapping[str, Any]) -> int:
    if "open_positions" in status:
        return _safe_int(status.get("open_positions"), 0)
    monitor = status.get("position_monitor")
    if isinstance(monitor, Mapping):
        return _safe_int(monitor.get("open_position_count"), 0)
    return 0


def _paper_status_pending_orders(status: Mapping[str, Any]) -> int:
    return _safe_int(status.get("pending_orders"), 0)


def _state_position_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    return _collection_rows(state.get("positions"), id_field="position_id")


def _count_state_positions(state: Mapping[str, Any], *, cycle_id: str = "", open_only: bool | None = None) -> int:
    count = 0
    for row in _state_position_rows(state):
        if not _is_lsr_v2_row(row, cycle_id=cycle_id):
            continue
        if open_only is True and not _is_position_open(row):
            continue
        if open_only is False and _is_position_open(row):
            continue
        count += 1
    return count


def _latest_row(rows: list[dict[str, Any]], *, cycle_id: str = "") -> dict[str, Any]:
    if cycle_id:
        scoped = [r for r in rows if str(r.get("cycle_id") or "") == cycle_id]
        if scoped:
            return dict(scoped[-1])
    return dict(rows[-1]) if rows else {}


def _infer_cycle_id(*payloads: Mapping[str, Any]) -> str:
    for payload in payloads:
        cycle = str(payload.get("cycle_id") or "")
        if cycle:
            return cycle
    return ""


def _event_type(row: Mapping[str, Any]) -> str:
    return str(row.get("event_type") or row.get("type") or "")


def _unique_positive_execution_cycles(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    cycles: set[str] = set()
    for row in rows:
        event_ok = _event_type(row) in {"LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION", ""}
        if not event_ok:
            continue
        submitted = _safe_int(row.get("orders_submitted_by_lsr_v2_execution"), 0)
        opened = _safe_int(row.get("positions_opened_by_lsr_v2_execution"), 0)
        decision = str(row.get("decision") or "")
        broker_called = _safe_bool(row.get("broker_submit_called"), False)
        if submitted > 0 or opened > 0 or broker_called or decision == "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED":
            cycles.add(str(row.get("cycle_id") or "unknown"))
    return cycles


def _positive_close_cycles(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    cycles: set[str] = set()
    for row in rows:
        event_ok = _event_type(row) in {"LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION", ""}
        if not event_ok:
            continue
        closed = _safe_int(row.get("positions_closed_by_lsr_v2_close_execution"), 0)
        decision = str(row.get("decision") or "")
        broker_called = _safe_bool(row.get("broker_close_called"), False) or _safe_bool(row.get("paper_close_called"), False)
        if closed > 0 or broker_called or decision == "LSR_V2_SINGLE_PAPER_POSITION_CLOSED":
            cycles.add(str(row.get("cycle_id") or "unknown"))
    return cycles


def _unsafe_flags(*payloads: Mapping[str, Any]) -> bool:
    for payload in payloads:
        if _safe_bool(payload.get("live_enabled"), False):
            return True
        if _safe_bool(payload.get("testnet_enabled"), False):
            return True
        if _safe_bool(payload.get("exchange_broker_enabled"), False):
            return True
        if _safe_bool(payload.get("operational_unlock_allowed"), False):
            return True
        if _safe_bool(payload.get("promotion_ready"), False):
            return True
    return False


def _build_sanitized_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    base = dict(os.environ if env is None else env)
    for key in list(base.keys()):
        if key in SUBMIT_OR_CLOSE_ENV_KEYS or any(key.startswith(prefix) for prefix in SUBMIT_OR_CLOSE_ENV_PREFIXES):
            base.pop(key, None)
    return base


def _default_paper_command(project_root: Path) -> list[str]:
    script = project_root / "trading_bot" / "run_paper_trading.py"
    if not script.exists():
        script = project_root / "run_paper_trading.py"
    return [
        sys.executable,
        str(script),
        "--mode",
        "paper",
        "--timeframe",
        "5m",
        "--cost-model",
        "conservative",
        "--once",
        "--paper-unlock",
    ]


def _run_paper_cycle(*, data_dir: Path, project_root: Path, cycle_index: int, timeout_seconds: int = 900) -> dict[str, Any]:
    log_dir = data_dir / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"cycle_{cycle_index:04d}_stdout.txt"
    stderr_path = log_dir / f"cycle_{cycle_index:04d}_stderr.txt"
    cmd = _default_paper_command(project_root)
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(project_root),
            env=_build_sanitized_env(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        timed_out = False
        returncode = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="ignore")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="ignore")
    elapsed = round(time.time() - started, 4)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    return {
        "cycle_index": cycle_index,
        "cmd": " ".join(cmd),
        "returncode": returncode,
        "timed_out": timed_out,
        "elapsed_seconds": elapsed,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }


def _run_observation_cycles(
    *,
    data_dir: Path,
    project_root: Path,
    duration_hours: float = 0.0,
    interval_seconds: float = 300.0,
    max_cycles: int = 0,
    run_paper_cycles: bool = False,
    timeout_seconds: int = 900,
) -> list[dict[str, Any]]:
    if not run_paper_cycles:
        return []
    if max_cycles <= 0 and duration_hours <= 0:
        max_cycles = 1
    deadline = time.time() + max(0.0, duration_hours) * 3600.0 if duration_hours > 0 else None
    logs: list[dict[str, Any]] = []
    cycle_index = 0
    while True:
        if max_cycles > 0 and cycle_index >= max_cycles:
            break
        if deadline is not None and time.time() >= deadline:
            break
        cycle_index += 1
        logs.append(_run_paper_cycle(data_dir=data_dir, project_root=project_root, cycle_index=cycle_index, timeout_seconds=timeout_seconds))
        if max_cycles > 0 and cycle_index >= max_cycles:
            break
        if deadline is not None and time.time() + max(0.0, interval_seconds) >= deadline:
            break
        if interval_seconds > 0:
            time.sleep(interval_seconds)
    return logs


def build_lsr_v2_post_first_trade_observation_report_from_files(
    *,
    data_dir: str | Path = "data",
    project_root: str | Path | None = None,
    duration_hours: float = 0.0,
    interval_seconds: float = 300.0,
    max_cycles: int = 0,
    run_paper_cycles: bool = False,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    data = Path(data_dir)
    if project_root is None:
        # run script lives in trading_bot; when data_dir is relative, current working directory is project root.
        project = Path.cwd()
    else:
        project = Path(project_root)
    data.mkdir(parents=True, exist_ok=True)

    observation_cycle_logs = _run_observation_cycles(
        data_dir=data,
        project_root=project,
        duration_hours=duration_hours,
        interval_seconds=interval_seconds,
        max_cycles=max_cycles,
        run_paper_cycles=run_paper_cycles,
        timeout_seconds=timeout_seconds,
    )

    postmortem = _read_json(data / POSTMORTEM_REPORT_NAME)
    final_audit = _read_json(data / FINAL_AUDIT_REPORT_NAME)
    submit_report = _read_json(data / SUBMIT_EXEC_REPORT_NAME)
    close_report = _read_json(data / CLOSE_EXEC_REPORT_NAME)
    state = _read_json(data / PAPER_STATE_NAME)
    status_payload = _read_json(data / PAPER_STATUS_NAME)

    cycle_id = _infer_cycle_id(postmortem, final_audit, close_report, submit_report)
    postmortem_rows = _iter_jsonl_tail(data / POSTMORTEM_JSONL_NAME)
    if not postmortem and postmortem_rows:
        postmortem = _latest_row(postmortem_rows, cycle_id=cycle_id)
        cycle_id = _infer_cycle_id(postmortem, final_audit, close_report, submit_report)

    submit_rows = _iter_jsonl_tail(data / SUBMIT_EXEC_JSONL_NAME)
    close_rows = _iter_jsonl_tail(data / CLOSE_EXEC_JSONL_NAME)
    paper_events = _iter_jsonl_tail(data / PAPER_EVENTS_NAME)

    submit_cycles = _unique_positive_execution_cycles(submit_rows)
    close_cycles = _positive_close_cycles(close_rows)
    if _safe_int(submit_report.get("orders_submitted_by_lsr_v2_execution"), 0) > 0 or _safe_bool(submit_report.get("broker_submit_called"), False):
        submit_cycles.add(str(submit_report.get("cycle_id") or cycle_id or "unknown"))
    if _safe_int(close_report.get("positions_closed_by_lsr_v2_close_execution"), 0) > 0 or _safe_bool(close_report.get("broker_close_called"), False):
        close_cycles.add(str(close_report.get("cycle_id") or cycle_id or "unknown"))

    allowed_first_cycle = str(postmortem.get("cycle_id") or final_audit.get("cycle_id") or cycle_id or "")
    new_submit_cycles = sorted(c for c in submit_cycles if allowed_first_cycle and c != allowed_first_cycle)
    if not allowed_first_cycle and submit_cycles:
        new_submit_cycles = sorted(submit_cycles)

    state_open_lsr_v2_positions = _count_state_positions(state, open_only=True)
    state_closed_lsr_v2_positions = _count_state_positions(state, open_only=False)
    paper_status_open_positions = _paper_status_open_positions(status_payload)
    paper_status_pending_orders = _paper_status_pending_orders(status_payload)
    position_monitor = status_payload.get("position_monitor") if isinstance(status_payload.get("position_monitor"), Mapping) else {}
    position_monitor_open_positions = _safe_int(position_monitor.get("open_position_count"), paper_status_open_positions) if isinstance(position_monitor, Mapping) else paper_status_open_positions

    postmortem_pass = str(postmortem.get("decision") or "") == "LSR_V2_FIRST_PAPER_TRADE_POSTMORTEM_PASS"
    closed_trade_complete = _safe_bool(postmortem.get("closed_trade_complete"), False) or _safe_bool(final_audit.get("closed_trade_complete"), False)
    second_trade_allowed = _safe_bool(postmortem.get("second_trade_allowed"), False)
    residual_open_position = state_open_lsr_v2_positions > 0 or _safe_bool(postmortem.get("residual_open_position"), False)
    extra_submit_or_reentry_detected = bool(new_submit_cycles) or _safe_bool(postmortem.get("extra_submit_or_reentry_detected"), False)
    state_consistency = state_open_lsr_v2_positions == paper_status_open_positions == position_monitor_open_positions
    status_consistency = paper_status_open_positions == position_monitor_open_positions and paper_status_pending_orders == 0
    unsafe_flag_detected = _unsafe_flags(postmortem, final_audit, submit_report, close_report, status_payload)

    completed_observation_cycles = len([r for r in observation_cycle_logs if _safe_int(r.get("returncode"), -1) == 0 and not _safe_bool(r.get("timed_out"), False)])
    timed_out_cycles = len([r for r in observation_cycle_logs if _safe_bool(r.get("timed_out"), False)])
    failed_observation_cycles = len([r for r in observation_cycle_logs if _safe_int(r.get("returncode"), 0) != 0 or _safe_bool(r.get("timed_out"), False)])

    blockers: list[str] = []
    labels: list[str] = []
    if not postmortem:
        blockers.append("postmortem_report_missing")
    if not postmortem_pass:
        blockers.append("postmortem_not_pass")
    if not closed_trade_complete:
        blockers.append("closed_trade_not_complete")
    if second_trade_allowed:
        blockers.append("second_trade_allowed_not_locked")
    if residual_open_position:
        blockers.append("residual_open_position")
    if extra_submit_or_reentry_detected:
        blockers.append("new_submit_or_reentry_detected")
    if not state_consistency:
        blockers.append("paper_state_status_inconsistent")
    if not status_consistency:
        blockers.append("paper_status_inconsistent")
    if paper_status_pending_orders > 0:
        blockers.append("paper_status_pending_orders_nonzero")
    if unsafe_flag_detected:
        blockers.append("unsafe_flag_detected")
    if failed_observation_cycles > 0:
        blockers.append("observation_cycle_failed_or_timed_out")

    if unsafe_flag_detected:
        decision = REJECT_DECISION
        status = "FAIL"
        labels.append("SAFETY_FLAG_FAILED")
    elif extra_submit_or_reentry_detected:
        decision = NEW_SUBMIT_DETECTED_DECISION
        status = "WARN"
        labels.append("NEW_SUBMIT_OR_REENTRY_DETECTED")
    elif residual_open_position:
        decision = REENTRY_DETECTED_DECISION
        status = "WARN"
        labels.append("RESIDUAL_OR_REENTRY_POSITION_DETECTED")
    elif not state_consistency or not status_consistency or paper_status_pending_orders > 0:
        decision = STATE_INCONSISTENT_DECISION
        status = "WARN"
        labels.append("STATE_STATUS_INCONSISTENT")
    elif not postmortem_pass or not closed_trade_complete:
        decision = IN_PROGRESS_DECISION
        status = "WARN"
        labels.append("POSTMORTEM_OR_CLOSED_TRADE_INCOMPLETE")
    elif failed_observation_cycles > 0:
        decision = IN_PROGRESS_DECISION
        status = "WARN"
        labels.append("OBSERVATION_CYCLE_FAILURE")
    else:
        decision = PASS_DECISION
        status = "PASS"
        labels.extend(["POST_FIRST_TRADE_OBSERVATION_PASS", "NO_REENTRY_DETECTED", "SECOND_TRADE_LOCKED"])

    realized_pnl_total = _round(postmortem.get("realized_pnl_total") or final_audit.get("realized_pnl_total"), 10)
    realized_r = _round(postmortem.get("realized_r") or final_audit.get("realized_r"), 10)

    report_path = data / REPORT_NAME
    jsonl_path = data / JSONL_NAME
    log_dir_path = data / LOG_DIR_NAME
    report: dict[str, Any] = {
        "prompt": PROMPT_ID,
        "event_type": EVENT_TYPE,
        "created_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "cycle_id": cycle_id,
        "postmortem_pass": postmortem_pass,
        "closed_trade_complete": closed_trade_complete,
        "second_trade_allowed": False,
        "second_trade_locked": not second_trade_allowed,
        "next_step_observation_required": _safe_bool(postmortem.get("next_step_observation_required"), True),
        "run_paper_cycles": bool(run_paper_cycles),
        "requested_duration_hours": _round(duration_hours, 4),
        "interval_seconds": _round(interval_seconds, 4),
        "requested_max_cycles": _safe_int(max_cycles, 0),
        "completed_observation_cycles": completed_observation_cycles,
        "failed_observation_cycles": failed_observation_cycles,
        "timed_out_cycles": timed_out_cycles,
        "observation_cycle_logs": observation_cycle_logs,
        "submit_execution_cycles": sorted(submit_cycles),
        "close_execution_cycles": sorted(close_cycles),
        "new_submit_cycles": new_submit_cycles,
        "submit_execution_events_total": len(submit_cycles),
        "close_execution_events_total": len(close_cycles),
        "state_open_lsr_v2_positions": state_open_lsr_v2_positions,
        "state_closed_lsr_v2_positions": state_closed_lsr_v2_positions,
        "paper_status_open_positions": paper_status_open_positions,
        "paper_status_pending_orders": paper_status_pending_orders,
        "position_monitor_open_positions": position_monitor_open_positions,
        "paper_state_consistency": state_consistency,
        "paper_status_consistency": status_consistency,
        "residual_open_position": residual_open_position,
        "extra_submit_or_reentry_detected": extra_submit_or_reentry_detected,
        "realized_pnl_total": realized_pnl_total,
        "realized_r": realized_r,
        "orders_submitted_by_observation": 0,
        "positions_opened_by_observation": 0,
        "positions_closed_by_observation": 0,
        "broker_submit_called_by_observation": False,
        "broker_close_called_by_observation": False,
        "paper_state_modified_by_observation": False,
        "paper_status_modified_by_observation": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "report": str(report_path),
        "jsonl": str(jsonl_path),
        "log_dir": str(log_dir_path),
        "event_source": "postmortem_and_paper_state",
    }
    _write_json(report_path, report)
    _append_jsonl(jsonl_path, report)
    return report


__all__ = [
    "PASS_DECISION",
    "IN_PROGRESS_DECISION",
    "REENTRY_DETECTED_DECISION",
    "NEW_SUBMIT_DETECTED_DECISION",
    "STATE_INCONSISTENT_DECISION",
    "REJECT_DECISION",
    "build_lsr_v2_post_first_trade_observation_report_from_files",
]
