"""Prompt 29.4.4s-10at-1 — LSR-v2 third closed trade final audit hotfix.

Audit-only post-close reconciliation for the third supervised LSR-v2 paper trade.
It verifies that the 29.4.4s-10as close execution left the paper account flat,
that the close was recorded exactly in paper-only state, that backups exist, that no
new order/re-entry was produced, and that close operator environment variables are
not still armed.  This module never opens, closes, submits, or mutates paper state;
it writes only its own JSON/JSONL audit artifacts.
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

PROMPT_ID = "29.4.4s-10at-1"
EVENT_TYPE = "LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT"
REPORT_NAME = "lsr_v2_third_closed_trade_final_audit_report.json"
JSONL_NAME = "lsr_v2_third_closed_trade_final_audit.jsonl"

CLOSE_EXECUTION_REPORT_NAME = "lsr_v2_third_trade_close_execution_report.json"
CLOSE_EXECUTION_JSONL_NAME = "lsr_v2_third_trade_close_execution.jsonl"
CLOSE_PREFLIGHT_REPORT_NAME = "lsr_v2_third_trade_close_preflight_report.json"
OPEN_MONITOR_REPORT_NAME = "lsr_v2_third_open_position_monitor_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SOURCE_TAG = "lsr_v2_third_trade_submit_execution"
CLOSE_SOURCE_TAG = "lsr_v2_third_trade_close_execution"
CLOSE_EVENT_TYPE = "LSR_V2_THIRD_TRADE_CLOSE_EXECUTION"
CLOSED_DECISION = "LSR_V2_THIRD_SINGLE_PAPER_POSITION_CLOSED"
BACKUP_DIR_NAME = "lsr_v2_third_trade_close_execution_backups"

CLOSE_ENABLE_ENV = "LSR_V2_THIRD_TRADE_CLOSE_ENABLE"
CLOSE_CONFIRM_ENV = "LSR_V2_THIRD_TRADE_CLOSE_CONFIRMATION"
CLOSE_MAX_POSITIONS_ENV = "LSR_V2_THIRD_TRADE_CLOSE_MAX_POSITIONS"

READY_DECISION = "LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT_READY"
MISSING_CLOSE_REPORT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_FINAL_AUDIT_CLOSE_REPORT_MISSING"
NOT_CLOSED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_FINAL_AUDIT_CLOSE_NOT_CONFIRMED"
STATE_NOT_FLAT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_FINAL_AUDIT_STATE_NOT_FLAT"
ENV_STILL_ACTIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_FINAL_AUDIT_CLOSE_ENV_STILL_ACTIVE"
BACKUP_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_THIRD_FINAL_AUDIT_BACKUP_MISSING"
SAFETY_FAILED_DECISION = "REJECT_LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT_SAFETY_FAILED"


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


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _metadata_of(row: Mapping[str, Any]) -> dict[str, Any]:
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
    meta = _metadata_of(row)
    return str(row.get("paper_order_source") or row.get("paper_close_source") or row.get("execution_source") or row.get("source") or meta.get("paper_order_source") or meta.get("paper_close_source") or meta.get("execution_source") or meta.get("source") or meta.get("closed_by") or "")


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("symbol") or meta.get("symbol") or "")


def _row_side(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    side = str(row.get("side") or row.get("direction") or meta.get("side") or "").upper()
    if side == "LONG":
        return "BUY"
    if side == "SHORT":
        return "SELL"
    return side


def _row_position_id(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("position_id") or row.get("id") or meta.get("position_id") or "")


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_third_lsr_v2_position(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    source = _row_source(row)
    meta = _metadata_of(row)
    if CLOSE_SOURCE_TAG in source or SOURCE_TAG in source:
        return True
    if str(row.get("profile_name") or meta.get("profile_name") or "") == PROFILE_NAME:
        return True
    if str(meta.get("trade_sequence") or row.get("trade_sequence") or "").upper() == "THIRD":
        return True
    if _safe_int(row.get("trade_ordinal") or meta.get("trade_ordinal"), 0) == 3:
        return True
    if cycle_id and _row_cycle(row) == cycle_id:
        return True
    return False


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}:
        return False
    return _safe_bool(row.get("pending"), status not in {"", "FILLED"})


def _resolve_reported_path(raw: Any, *, project_root: Path, data_dir: Path) -> tuple[str, bool]:
    text = str(raw or "").strip()
    if not text:
        return "", False
    normalized = text.replace("\\", "/")
    candidates = []
    p = Path(normalized)
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(project_root / normalized)
        candidates.append(data_dir / normalized)
        candidates.append(data_dir / Path(normalized).name)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate), True
    return str(candidates[0]) if candidates else text, False


@dataclass(frozen=True)
class LSRV2ThirdClosedTradeFinalAuditSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    close_execution_report_name: str = CLOSE_EXECUTION_REPORT_NAME
    close_execution_jsonl_name: str = CLOSE_EXECUTION_JSONL_NAME
    close_preflight_report_name: str = CLOSE_PREFLIGHT_REPORT_NAME
    open_monitor_report_name: str = OPEN_MONITOR_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    max_event_lines: int = 50000
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2ThirdClosedTradeFinalAuditSettings":
        return cls(data_dir=data_dir)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_controls() -> dict[str, Any]:
    values = {
        CLOSE_ENABLE_ENV: os.getenv(CLOSE_ENABLE_ENV),
        CLOSE_CONFIRM_ENV: os.getenv(CLOSE_CONFIRM_ENV),
        CLOSE_MAX_POSITIONS_ENV: os.getenv(CLOSE_MAX_POSITIONS_ENV),
    }
    return {
        "close_enable_present": values[CLOSE_ENABLE_ENV] is not None,
        "close_confirmation_present": values[CLOSE_CONFIRM_ENV] is not None,
        "close_max_positions_present": values[CLOSE_MAX_POSITIONS_ENV] is not None,
        "close_enable_value": "<set>" if values[CLOSE_ENABLE_ENV] is not None else "",
        "close_confirmation_value": "<set>" if values[CLOSE_CONFIRM_ENV] is not None else "",
        "close_max_positions_value": str(values[CLOSE_MAX_POSITIONS_ENV] or ""),
        "any_close_env_present": any(v is not None for v in values.values()),
    }


def select_third_closed_trade_cycle_id(data_dir: str | Path, requested_cycle_id: str = "", settings: LSRV2ThirdClosedTradeFinalAuditSettings | None = None) -> str:
    settings = settings or LSRV2ThirdClosedTradeFinalAuditSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    if requested_cycle_id:
        return str(requested_cycle_id)
    for name in (settings.close_execution_report_name, settings.close_preflight_report_name, settings.open_monitor_report_name):
        report = _read_json(base / name)
        if report.get("cycle_id"):
            return str(report.get("cycle_id") or "")
    for name in (settings.close_execution_jsonl_name, settings.paper_events_name):
        for row in reversed(_iter_jsonl_tail(base / name, max_lines=settings.max_event_lines)):
            if row.get("cycle_id"):
                return str(row.get("cycle_id") or "")
    return ""


def _close_events(data_dir: Path, cycle_id: str, settings: LSRV2ThirdClosedTradeFinalAuditSettings) -> list[dict[str, Any]]:
    rows = _iter_jsonl_tail(data_dir / settings.close_execution_jsonl_name, max_lines=settings.max_event_lines)
    selected = [dict(r) for r in rows if r.get("event_type") == CLOSE_EVENT_TYPE and (not cycle_id or str(r.get("cycle_id") or "") == cycle_id)]
    if selected:
        return selected
    rows = _iter_jsonl_tail(data_dir / settings.paper_events_name, max_lines=settings.max_event_lines)
    return [dict(r) for r in rows if r.get("event_type") == CLOSE_EVENT_TYPE and (not cycle_id or str(r.get("cycle_id") or "") == cycle_id)]


def _is_successful_close_event(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("event_type") == CLOSE_EVENT_TYPE
        and _safe_int(row.get("positions_closed_by_third_trade_close_execution"), 0) == 1
        and _safe_int(row.get("orders_submitted_by_third_trade_close_execution"), 0) == 0
        and _safe_int(row.get("positions_opened_by_third_trade_close_execution"), 0) == 0
        and _safe_bool(row.get("automatic_reentry_enabled"), False) is False
        and _safe_bool(row.get("live_enabled"), False) is False
        and _safe_bool(row.get("testnet_enabled"), False) is False
        and _safe_bool(row.get("exchange_broker_enabled"), False) is False
        and _safe_bool(row.get("operational_unlock_allowed"), False) is False
    )


def _successful_close_events(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows if _is_successful_close_event(r)]


def _resolve_backup_paths_from_dir(data_dir: Path) -> tuple[str, bool, str, bool]:
    backup_dir = data_dir / BACKUP_DIR_NAME
    state_files = sorted(backup_dir.glob("paper_state_*.json")) if backup_dir.exists() else []
    status_files = sorted(backup_dir.glob("paper_status_*.json")) if backup_dir.exists() else []
    state_path = str(state_files[-1]) if state_files else ""
    status_path = str(status_files[-1]) if status_files else ""
    return state_path, bool(state_files), status_path, bool(status_files)


def build_lsr_v2_third_closed_trade_final_audit_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2ThirdClosedTradeFinalAuditSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2ThirdClosedTradeFinalAuditSettings.from_env(data_dir=str(data_dir))
    base = Path(data_dir)
    project_root = base.parent if base.name else Path.cwd()
    selected_cycle_id = select_third_closed_trade_cycle_id(base, requested_cycle_id=cycle_id, settings=settings)

    close_report = _read_json(base / settings.close_execution_report_name)
    close_events = _close_events(base, selected_cycle_id, settings)
    state = _read_json(base / settings.paper_state_name)
    status = _read_json(base / settings.paper_status_name)
    env = _env_controls()

    positions = _collection_rows(state.get("positions"), id_field="position_id")
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    open_positions = [p for p in positions if _is_position_open(p)]
    open_third_positions = [p for p in open_positions if _is_third_lsr_v2_position(p, cycle_id=selected_cycle_id)]
    pending_orders = [o for o in orders if _is_order_pending(o)]

    status_open_positions = _safe_int(status.get("open_positions"), len(open_positions))
    status_pending_orders = _safe_int(status.get("pending_orders"), len(pending_orders))
    state_status_consistent = bool(status_open_positions == len(open_positions) and status_pending_orders == len(pending_orders))

    close_report_present = bool(close_report)
    close_report_closed = bool(
        str(close_report.get("decision") or "") == CLOSED_DECISION
        and _safe_int(close_report.get("positions_closed_by_third_trade_close_execution"), 0) == 1
        and _safe_int(close_report.get("open_third_lsr_v2_positions_after"), -1) == 0
        and _safe_int(close_report.get("paper_status_open_positions_after"), -1) == 0
    )
    close_event_count = len(close_events)
    successful_events = _successful_close_events(close_events)
    close_event_closed = bool(successful_events)
    close_event_present = bool(close_event_count >= 1)
    closed_trade_confirmed = bool(close_report_closed or close_event_closed)

    event_positions_closed = sum(_safe_int(e.get("positions_closed_by_third_trade_close_execution"), 0) for e in successful_events)
    event_orders_submitted = sum(_safe_int(e.get("orders_submitted_by_third_trade_close_execution"), 0) for e in close_events)
    event_positions_opened = sum(_safe_int(e.get("positions_opened_by_third_trade_close_execution"), 0) for e in close_events)
    event_reentry_enabled = any(_safe_bool(e.get("automatic_reentry_enabled"), False) for e in close_events)
    positions_closed_source = _safe_int(close_report.get("positions_closed_by_third_trade_close_execution"), 0) if close_report_closed else event_positions_closed
    orders_submitted_source = _safe_int(close_report.get("orders_submitted_by_third_trade_close_execution"), 0) if close_report_closed else event_orders_submitted
    positions_opened_source = _safe_int(close_report.get("positions_opened_by_third_trade_close_execution"), 0) if close_report_closed else event_positions_opened

    realized_from_events = sum(_safe_float(e.get("realized_pnl"), 0.0) for e in successful_events or close_events)
    realized_pnl_total = _safe_float(close_report.get("realized_pnl_total"), realized_from_events) if close_report_closed else realized_from_events
    if realized_pnl_total == 0.0 and realized_from_events != 0.0:
        realized_pnl_total = realized_from_events

    backup_state_resolved, backup_state_exists = _resolve_reported_path(close_report.get("backup_state_path"), project_root=project_root, data_dir=base)
    backup_status_resolved, backup_status_exists = _resolve_reported_path(close_report.get("backup_status_path"), project_root=project_root, data_dir=base)
    if not (backup_state_exists and backup_status_exists):
        scanned_state_path, scanned_state_exists, scanned_status_path, scanned_status_exists = _resolve_backup_paths_from_dir(base)
        if not backup_state_exists and scanned_state_exists:
            backup_state_resolved, backup_state_exists = scanned_state_path, True
        if not backup_status_exists and scanned_status_exists:
            backup_status_resolved, backup_status_exists = scanned_status_path, True
    backups_present = bool(backup_state_exists and backup_status_exists)

    live_enabled = _safe_bool(status.get("live_enabled"), False) or _safe_bool(close_report.get("live_enabled"), False) or any(_safe_bool(e.get("live_enabled"), False) for e in close_events)
    testnet_enabled = _safe_bool(status.get("testnet_enabled"), False) or _safe_bool(close_report.get("testnet_enabled"), False) or any(_safe_bool(e.get("testnet_enabled"), False) for e in close_events)
    exchange_broker_enabled = _safe_bool(status.get("exchange_broker_enabled"), False) or _safe_bool(close_report.get("exchange_broker_enabled"), False) or any(_safe_bool(e.get("exchange_broker_enabled"), False) for e in close_events)
    operational_unlock_allowed = _safe_bool(status.get("operational_unlock_allowed"), False) or _safe_bool(close_report.get("operational_unlock_allowed"), False) or any(_safe_bool(e.get("operational_unlock_allowed"), False) for e in close_events)

    no_submit_or_reentry = bool(
        orders_submitted_source == 0
        and positions_opened_source == 0
        and _safe_bool(close_report.get("automatic_reentry_enabled"), False) is False
        and event_reentry_enabled is False
        and not pending_orders
    )
    flat_state = bool(not open_positions and not open_third_positions and status_open_positions == 0 and status_pending_orders == 0)
    safety_ok = bool(
        not live_enabled
        and not testnet_enabled
        and not exchange_broker_enabled
        and not operational_unlock_allowed
        and no_submit_or_reentry
    )

    blockers: list[str] = []
    if not close_report_present:
        blockers.append("close_execution_report_missing")
    if close_report_present and not close_report_closed and not close_event_closed:
        blockers.append("close_execution_not_confirmed_closed")
    if not close_event_present and not close_report_closed:
        blockers.append("close_execution_event_missing")
    if not flat_state:
        blockers.append("paper_state_or_status_not_flat")
    if not state_status_consistent:
        blockers.append("paper_state_status_inconsistent")
    if env["any_close_env_present"]:
        blockers.append("close_operator_env_still_present")
    if not backups_present:
        blockers.append("close_execution_backup_missing")
    if not no_submit_or_reentry:
        blockers.append("submit_or_reentry_detected")
    if live_enabled:
        blockers.append("live_enabled")
    if testnet_enabled:
        blockers.append("testnet_enabled")
    if exchange_broker_enabled:
        blockers.append("exchange_broker_enabled")
    if operational_unlock_allowed:
        blockers.append("operational_unlock_allowed")

    if not safety_ok:
        decision = SAFETY_FAILED_DECISION
        status_text = "WARN"
    elif env["any_close_env_present"]:
        decision = ENV_STILL_ACTIVE_DECISION
        status_text = "WARN"
    elif not close_report_present:
        decision = MISSING_CLOSE_REPORT_DECISION
        status_text = "WARN"
    elif not closed_trade_confirmed:
        decision = NOT_CLOSED_DECISION
        status_text = "WARN"
    elif not flat_state or not state_status_consistent:
        decision = STATE_NOT_FLAT_DECISION
        status_text = "WARN"
    elif not backups_present:
        decision = BACKUP_MISSING_DECISION
        status_text = "WARN"
    else:
        decision = READY_DECISION
        status_text = "PASS"

    event = {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": selected_cycle_id,
        "decision": decision,
        "status": status_text,
        "closed_trade_confirmed": bool(closed_trade_confirmed),
        "flat_state_confirmed": bool(flat_state),
        "state_status_consistent": bool(state_status_consistent),
        "backups_present": bool(backups_present),
        "close_env_absent": not bool(env["any_close_env_present"]),
        "no_submit_or_reentry": bool(no_submit_or_reentry),
        "realized_pnl_total": _round(realized_pnl_total),
        "open_positions_after": len(open_positions),
        "open_third_lsr_v2_positions_after": len(open_third_positions),
        "pending_orders_after": len(pending_orders),
        "orders_submitted_by_final_audit": 0,
        "positions_opened_by_final_audit": 0,
        "positions_closed_by_final_audit": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
    }
    _write_jsonl_replace(base / settings.jsonl_name, [event])

    symbols = sorted({str(e.get("symbol") or "") for e in close_events if e.get("symbol")})
    sides = sorted({str(e.get("side") or "") for e in close_events if e.get("side")})
    close_reasons = sorted({str(e.get("close_reason") or "") for e in close_events if e.get("close_reason")})

    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": ["LSR_V2_THIRD_CLOSED_TRADE_FINAL_AUDIT", "AUDIT_ONLY", "NO_REENTRY"],
        "blockers": sorted(set(blockers)),
        "cycle_id": selected_cycle_id,
        "event_source": "third_trade_close_execution_report_and_jsonl",
        "strict_cycle_scope": True,
        "close_execution_report_present": bool(close_report_present),
        "close_execution_report_decision": str(close_report.get("decision") or ""),
        "close_execution_report_status": str(close_report.get("status") or ""),
        "close_execution_events": int(close_event_count),
        "closed_trade_confirmed": bool(closed_trade_confirmed),
        "closed_trade_confirmed_from_report": bool(close_report_closed),
        "closed_trade_confirmed_from_event_log": bool(close_event_closed),
        "positions_closed_by_close_execution": int(positions_closed_source),
        "orders_submitted_by_close_execution": int(orders_submitted_source),
        "positions_opened_by_close_execution": int(positions_opened_source),
        "positions_closed_by_final_audit": 0,
        "orders_submitted_by_final_audit": 0,
        "positions_opened_by_final_audit": 0,
        "paper_state_modified_by_final_audit": False,
        "paper_status_modified_by_final_audit": False,
        "paper_events_modified_by_final_audit": False,
        "open_positions_after": len(open_positions),
        "open_third_lsr_v2_positions_after": len(open_third_positions),
        "paper_status_open_positions_after": status_open_positions,
        "pending_orders_after": len(pending_orders),
        "paper_status_pending_orders_after": status_pending_orders,
        "flat_state_confirmed": bool(flat_state),
        "paper_state_status_consistency": bool(state_status_consistent),
        "backup_state_path": str(close_report.get("backup_state_path") or backup_state_resolved or ""),
        "backup_status_path": str(close_report.get("backup_status_path") or backup_status_resolved or ""),
        "backup_state_resolved_path": backup_state_resolved,
        "backup_status_resolved_path": backup_status_resolved,
        "backup_state_exists": bool(backup_state_exists),
        "backup_status_exists": bool(backup_status_exists),
        "backups_present": bool(backups_present),
        "close_env_controls": env,
        "close_env_absent": not bool(env["any_close_env_present"]),
        "no_submit_or_reentry": bool(no_submit_or_reentry),
        "new_order_created_after_close": False,
        "automatic_reentry_enabled": False,
        "broker_submit_called_by_final_audit": False,
        "broker_close_called_by_final_audit": False,
        "paper_close_called_by_final_audit": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "symbols": symbols,
        "sides": sides,
        "close_reasons": close_reasons,
        "realized_pnl_total": _round(realized_pnl_total),
        "balance_after": _round(state.get("balance")),
        "realized_pnl_after": _round(state.get("realized_pnl")),
        "safety_checks": {
            "audit_only": True,
            "no_state_mutation": True,
            "no_status_mutation": True,
            "no_order_submit": True,
            "no_reentry": True,
            "flat_state": bool(flat_state),
            "close_env_absent": not bool(env["any_close_env_present"]),
            "live_disabled": not bool(live_enabled),
            "testnet_disabled": not bool(testnet_enabled),
            "exchange_broker_disabled": not bool(exchange_broker_enabled),
            "operational_unlock_blocked": not bool(operational_unlock_allowed),
        },
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
