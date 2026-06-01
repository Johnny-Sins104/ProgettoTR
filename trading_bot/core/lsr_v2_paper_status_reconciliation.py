"""Prompt 29.4.4s-10l-1 — LSR-v2 paper status reconciliation.

Reconciles the read-only paper status summary with the active paper state after
an LSR-v2 supervised paper-only submit.  The module is audit-only by default.
It can update ``paper_status.json`` only when an explicit operator sync env is
provided.  It never submits, closes, opens, re-enters, or mutates
``paper_state.json``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import os
import shutil

PROMPT_ID = "29.4.4s-10l-1"
EVENT_TYPE = "LSR_V2_PAPER_STATUS_RECONCILIATION_AUDIT"
REPORT_NAME = "lsr_v2_paper_status_reconciliation_report.json"
JSONL_NAME = "lsr_v2_paper_status_reconciliation.jsonl"
BACKUP_DIR_NAME = "paper_status_reconciliation_backups"

PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
LIFECYCLE_REPORT_NAME = "lsr_v2_paper_position_lifecycle_report.json"

READY_DECISION = "LSR_V2_PAPER_STATUS_RECONCILIATION_READY"
OUT_OF_SYNC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_STATUS_OUT_OF_SYNC"
SYNC_AVAILABLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_STATUS_SYNC_AVAILABLE"
SYNC_APPLIED_DECISION = "LSR_V2_PAPER_STATUS_SYNC_APPLIED"
REJECT_DECISION = "REJECT_LSR_V2_STATUS_RECONCILIATION_FAILED"

SYNC_ENABLE_ENV = "LSR_V2_PAPER_STATUS_SYNC_ENABLE"
SYNC_CONFIRMATION_ENV = "LSR_V2_PAPER_STATUS_SYNC_CONFIRMATION"
SYNC_CONFIRMATION_PHRASE = "I_UNDERSTAND_SYNC_PAPER_STATUS_ONLY"

LSR_SOURCE_TAG = "lsr_v2_supervised_paper_submit_execution"
PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "open"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null", "closed", "cancelled", "canceled"}:
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


def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _collection_rows(value: Any, *, id_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, raw in value.items():
            if isinstance(raw, Mapping):
                row = dict(raw)
            else:
                row = {"value": raw}
            row.setdefault(id_field, str(key))
            rows.append(row)
    elif isinstance(value, list):
        for idx, raw in enumerate(value):
            if isinstance(raw, Mapping):
                row = dict(raw)
            else:
                row = {"value": raw}
            row.setdefault(id_field, str(row.get(id_field) or idx))
            rows.append(row)
    return rows


def _metadata_of(row: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        return metadata
    meta = row.get("meta")
    if isinstance(meta, Mapping):
        return meta
    return {}


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "FILLED")
    return status in {"NEW", "OPEN", "PENDING", "PLACED", "SUBMITTED", "ACCEPTED"}


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
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
    meta = _metadata_of(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("symbol") or meta.get("symbol") or "")


def _row_side(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("side") or row.get("direction") or meta.get("side") or "").upper()


def _row_id(row: Mapping[str, Any], *fields: str) -> str:
    meta = _metadata_of(row)
    for field in fields:
        value = row.get(field) or meta.get(field)
        if value not in {None, ""}:
            return str(value)
    return ""


def _entry_price(row: Mapping[str, Any]) -> float:
    return _safe_float(row.get("entry_price") or row.get("entry") or row.get("price") or row.get("avg_entry_price"), 0.0)


def _position_size(row: Mapping[str, Any]) -> float:
    return _safe_float(row.get("position_size") or row.get("qty") or row.get("quantity") or row.get("size"), 0.0)


def _current_price(row: Mapping[str, Any], fallback: float = 0.0) -> float:
    return _safe_float(row.get("current_price") or row.get("mark_price") or row.get("last_price") or row.get("price"), fallback)


def _is_lsr_v2_position(row: Mapping[str, Any], cycle_id: str = "") -> bool:
    if LSR_SOURCE_TAG in _row_source(row):
        return True
    if cycle_id and _row_cycle(row) == cycle_id:
        return True
    profile = str(row.get("profile_name") or _metadata_of(row).get("profile_name") or "")
    return profile == PROFILE_NAME


def summarize_position(row: Mapping[str, Any]) -> dict[str, Any]:
    entry = _entry_price(row)
    current = _current_price(row, entry)
    side = _row_side(row)
    size = _position_size(row)
    unrealized = _safe_float(row.get("unrealized_pnl"), 0.0)
    if row.get("unrealized_pnl") is None and entry > 0 and current > 0 and size > 0:
        unrealized = (entry - current) * size if side == "SELL" else (current - entry) * size
    return {
        "position_id": _row_id(row, "position_id", "id"),
        "order_id": _row_id(row, "order_id"),
        "cycle_id": _row_cycle(row),
        "symbol": _row_symbol(row),
        "side": side,
        "status": _status_text(row, "OPEN"),
        "open": _is_position_open(row),
        "entry_price": _round(entry),
        "current_price": _round(current),
        "stop_loss": _round(row.get("stop_loss")),
        "take_profit": _round(row.get("take_profit")),
        "position_size": _round(size),
        "notional": _round(row.get("notional")),
        "risk_amount": _round(row.get("risk_amount")),
        "risk_per_trade_pct": _safe_float(row.get("risk_per_trade_pct"), 0.0),
        "unrealized_pnl": _round(unrealized),
        "source": _row_source(row),
    }


@dataclass(frozen=True)
class LSRV2PaperStatusReconciliationSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    lifecycle_report_name: str = LIFECYCLE_REPORT_NAME
    backup_dir_name: str = BACKUP_DIR_NAME
    sync_enable_env: str = SYNC_ENABLE_ENV
    sync_confirmation_env: str = SYNC_CONFIRMATION_ENV
    sync_confirmation_phrase: str = SYNC_CONFIRMATION_PHRASE
    max_positions: int = 1
    fail_closed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def operator_sync_controls(settings: LSRV2PaperStatusReconciliationSettings | None = None) -> tuple[bool, bool]:
    settings = settings or LSRV2PaperStatusReconciliationSettings()
    enabled = _safe_bool(os.getenv(settings.sync_enable_env), False)
    confirmation_ok = os.getenv(settings.sync_confirmation_env, "") == settings.sync_confirmation_phrase
    return enabled, confirmation_ok


def derive_status_summary(
    *,
    state: Mapping[str, Any],
    previous_status: Mapping[str, Any],
    cycle_id: str = "",
) -> dict[str, Any]:
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = [p for p in positions if _is_position_open(p)]
    pending_orders = [o for o in orders if _is_order_pending(o)]
    position_summaries = [summarize_position(p) for p in open_positions]
    lsr_positions = [p for p in open_positions if _is_lsr_v2_position(p, cycle_id=cycle_id)]
    balance = _safe_float(previous_status.get("balance"), _safe_float(state.get("balance"), 0.0))
    realized_pnl = _safe_float(previous_status.get("realized_pnl"), _safe_float(state.get("realized_pnl"), 0.0))
    unrealized_pnl = round(sum(_safe_float(p.get("unrealized_pnl"), 0.0) for p in position_summaries), 10)
    equity = _safe_float(previous_status.get("equity"), 0.0)
    if equity <= 0:
        equity = round(balance + unrealized_pnl, 10)
    status_out = dict(previous_status)
    status_out.update({
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "positions": position_summaries,
        "balance": balance,
        "equity": equity,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "updated_at": utc_now_iso(),
        "lsr_v2_status_reconciliation": {
            "prompt_id": PROMPT_ID,
            "cycle_id": cycle_id,
            "status": "SYNCED_FROM_PAPER_STATE",
            "paper_state_open_positions": len(open_positions),
            "lsr_v2_open_positions": len(lsr_positions),
            "paper_status_modified_by": PROMPT_ID,
        },
    })
    position_monitor = dict(status_out.get("position_monitor") if isinstance(status_out.get("position_monitor"), Mapping) else {})
    account = dict(position_monitor.get("account") if isinstance(position_monitor.get("account"), Mapping) else {})
    raw = dict(account.get("raw") if isinstance(account.get("raw"), Mapping) else {})
    raw.update({
        "balance": balance,
        "equity": equity,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "positions": position_summaries,
        "mode": raw.get("mode") or previous_status.get("mode") or "paper",
    })
    account.update({
        "balance": balance,
        "equity": equity,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "mode": account.get("mode") or previous_status.get("mode") or "paper",
        "raw": raw,
    })
    position_monitor.update({
        "status": "OPEN" if open_positions else "FLAT",
        "mode": position_monitor.get("mode") or previous_status.get("mode") or "paper",
        "generated_at": utc_now_iso(),
        "open_position_count": len(open_positions),
        "positions": position_summaries,
        "account": account,
    })
    status_out["position_monitor"] = position_monitor
    return status_out


def analyze_reconciliation(
    *,
    state: Mapping[str, Any],
    status: Mapping[str, Any],
    cycle_id: str = "",
    settings: LSRV2PaperStatusReconciliationSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperStatusReconciliationSettings()
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = [p for p in positions if _is_position_open(p)]
    pending_orders = [o for o in orders if _is_order_pending(o)]
    lsr_positions = [p for p in open_positions if _is_lsr_v2_position(p, cycle_id=cycle_id)]
    status_open_positions = _safe_int(status.get("open_positions"), 0)
    status_pending_orders = _safe_int(status.get("pending_orders"), 0)
    monitor = status.get("position_monitor") if isinstance(status.get("position_monitor"), Mapping) else {}
    monitor_open_positions = _safe_int(monitor.get("open_position_count"), status_open_positions) if isinstance(monitor, Mapping) else status_open_positions
    status_positions = status.get("positions")
    status_position_count = len(status_positions) if isinstance(status_positions, list) else status_open_positions
    open_positions_match = status_open_positions == len(open_positions)
    pending_orders_match = status_pending_orders == len(pending_orders)
    monitor_match = monitor_open_positions == len(open_positions)
    status_positions_match = status_position_count == len(open_positions)
    duplicate_position_check = len(lsr_positions) <= settings.max_positions
    max_positions_check = len(lsr_positions) <= settings.max_positions
    sync_required = not (open_positions_match and pending_orders_match and monitor_match and status_positions_match)
    safety_ok = duplicate_position_check and max_positions_check
    return {
        "state_open_positions": len(open_positions),
        "state_pending_orders": len(pending_orders),
        "state_lsr_v2_open_positions": len(lsr_positions),
        "status_open_positions_before": status_open_positions,
        "status_pending_orders_before": status_pending_orders,
        "status_position_count_before": status_position_count,
        "position_monitor_open_positions_before": monitor_open_positions,
        "open_positions_match": open_positions_match,
        "pending_orders_match": pending_orders_match,
        "position_monitor_match": monitor_match,
        "status_positions_match": status_positions_match,
        "sync_required": sync_required,
        "duplicate_position_check": duplicate_position_check,
        "max_positions_check": max_positions_check,
        "safety_ok": safety_ok,
        "symbols": sorted({str(_row_symbol(p)) for p in lsr_positions if _row_symbol(p)}),
        "sides": sorted({str(_row_side(p)) for p in lsr_positions if _row_side(p)}),
        "total_notional": round(sum(_safe_float(p.get("notional"), 0.0) for p in lsr_positions), 10),
        "total_risk_amount": round(sum(_safe_float(p.get("risk_amount"), 0.0) for p in lsr_positions), 10),
        "position_summaries": [summarize_position(p) for p in lsr_positions],
    }


def _backup_status(status_path: Path, backup_dir: Path) -> str:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"paper_status_{stamp}.json"
    if status_path.exists():
        shutil.copy2(status_path, backup_path)
    else:
        backup_path.write_text("{}\n", encoding="utf-8")
    return str(backup_path)


def build_lsr_v2_paper_status_reconciliation_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    sync_enabled: bool | None = None,
    sync_confirmation_ok: bool | None = None,
    settings: LSRV2PaperStatusReconciliationSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2PaperStatusReconciliationSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    state_path = base / settings.paper_state_name
    status_path = base / settings.paper_status_name
    lifecycle = _read_json(base / settings.lifecycle_report_name)
    selected_cycle_id = str(cycle_id or lifecycle.get("cycle_id") or "")
    state = _read_json(state_path)
    status = _read_json(status_path)
    if sync_enabled is None or sync_confirmation_ok is None:
        env_enabled, env_confirm = operator_sync_controls(settings)
        if sync_enabled is None:
            sync_enabled = env_enabled
        if sync_confirmation_ok is None:
            sync_confirmation_ok = env_confirm
    analysis = analyze_reconciliation(state=state, status=status, cycle_id=selected_cycle_id, settings=settings)
    blockers: list[str] = []
    if not state_path.exists():
        blockers.append("paper_state_missing")
    if not status_path.exists():
        blockers.append("paper_status_missing")
    if not analysis["duplicate_position_check"]:
        blockers.append("duplicate_lsr_v2_positions_detected")
    if not analysis["max_positions_check"]:
        blockers.append("max_positions_exceeded")
    if analysis["sync_required"]:
        blockers.append("paper_status_out_of_sync")
    if sync_enabled and not sync_confirmation_ok:
        blockers.append("sync_confirmation_missing")

    paper_status_modified = False
    backup_path = ""
    status_after = dict(status)
    status_open_after = analysis["status_open_positions_before"]
    pending_after = analysis["status_pending_orders_before"]
    monitor_after = analysis["position_monitor_open_positions_before"]

    if not analysis["safety_ok"]:
        decision = REJECT_DECISION
        status_text = "WARN"
    elif analysis["sync_required"] and sync_enabled and sync_confirmation_ok:
        backup_path = _backup_status(status_path, base / settings.backup_dir_name)
        status_after = derive_status_summary(state=state, previous_status=status, cycle_id=selected_cycle_id)
        _write_json(status_path, status_after)
        paper_status_modified = True
        status_open_after = _safe_int(status_after.get("open_positions"), 0)
        pending_after = _safe_int(status_after.get("pending_orders"), 0)
        monitor = status_after.get("position_monitor") if isinstance(status_after.get("position_monitor"), Mapping) else {}
        monitor_after = _safe_int(monitor.get("open_position_count"), status_open_after) if isinstance(monitor, Mapping) else status_open_after
        decision = SYNC_APPLIED_DECISION
        status_text = "PASS"
        blockers = [b for b in blockers if b not in {"paper_status_out_of_sync"}]
    elif analysis["sync_required"] and sync_enabled and not sync_confirmation_ok:
        decision = OUT_OF_SYNC_DECISION
        status_text = "WARN"
    elif analysis["sync_required"]:
        decision = SYNC_AVAILABLE_DECISION
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
        "sync_enabled": bool(sync_enabled),
        "sync_confirmation_ok": bool(sync_confirmation_ok),
        "paper_status_modified": bool(paper_status_modified),
        "backup_path": backup_path,
        "orders_submitted_by_status_reconciliation": 0,
        "positions_opened_by_status_reconciliation": 0,
        "broker_submit_called_by_status_reconciliation": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        **{k: v for k, v in analysis.items() if k != "position_summaries"},
    }
    _write_jsonl_replace(base / settings.jsonl_name, [event])

    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_PAPER_STATUS_RECONCILIATION",
            "PAPER_STATE_PRIMARY",
        ] + (["STATUS_SYNC_APPLIED"] if paper_status_modified else []) + (["STATUS_OUT_OF_SYNC"] if analysis["sync_required"] and not paper_status_modified else ["STATUS_CONSISTENT"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": selected_cycle_id,
        "sync_enabled": bool(sync_enabled),
        "sync_confirmation_ok": bool(sync_confirmation_ok),
        "paper_status_modified": bool(paper_status_modified),
        "backup_path": backup_path,
        "paper_state_path": str(state_path),
        "paper_status_path": str(status_path),
        "state_open_positions": analysis["state_open_positions"],
        "state_pending_orders": analysis["state_pending_orders"],
        "state_lsr_v2_open_positions": analysis["state_lsr_v2_open_positions"],
        "status_open_positions_before": analysis["status_open_positions_before"],
        "status_open_positions_after": status_open_after,
        "status_pending_orders_before": analysis["status_pending_orders_before"],
        "status_pending_orders_after": pending_after,
        "position_monitor_open_positions_before": analysis["position_monitor_open_positions_before"],
        "position_monitor_open_positions_after": monitor_after,
        "open_positions_match": analysis["open_positions_match"],
        "pending_orders_match": analysis["pending_orders_match"],
        "position_monitor_match": analysis["position_monitor_match"],
        "status_positions_match": analysis["status_positions_match"],
        "sync_required_before": analysis["sync_required"],
        "sync_required_after": bool(
            status_open_after != analysis["state_open_positions"]
            or pending_after != analysis["state_pending_orders"]
            or monitor_after != analysis["state_open_positions"]
        ),
        "duplicate_position_check": analysis["duplicate_position_check"],
        "max_positions_check": analysis["max_positions_check"],
        "symbols": analysis["symbols"],
        "sides": analysis["sides"],
        "total_notional": analysis["total_notional"],
        "total_risk_amount": analysis["total_risk_amount"],
        "position_summaries": analysis["position_summaries"],
        "orders_submitted_by_status_reconciliation": 0,
        "positions_opened_by_status_reconciliation": 0,
        "broker_submit_called_by_status_reconciliation": False,
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "safety_checks": {
            "no_new_order_by_status_reconciliation": True,
            "no_new_position_by_status_reconciliation": True,
            "no_broker_submit_by_status_reconciliation": True,
            "no_automatic_close": True,
            "no_automatic_reentry": True,
            "live_disabled": True,
            "testnet_disabled": True,
            "exchange_broker_disabled": True,
            "operational_unlock_blocked": True,
            "paper_state_not_modified": True,
            "backup_before_sync": bool((not paper_status_modified) or backup_path),
        },
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
