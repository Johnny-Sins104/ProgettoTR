"""Prompt 29.4.4s-10o — LSR-v2 supervised paper close execution.

Closes exactly one already-open LSR-v2 paper position when the close preflight
has detected a TP/SL/close-required diagnostic and the operator supplies the
explicit close confirmation.  This module is paper-state only: it never opens a
new order, never re-enters, never uses live/testnet/exchange brokers, and never
submits to an exchange.
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
import shutil

PROMPT_ID = "29.4.4s-10o"
EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION"
REPORT_NAME = "lsr_v2_supervised_paper_close_execution_report.json"
JSONL_NAME = "lsr_v2_supervised_paper_close_execution.jsonl"
BACKUP_DIR_NAME = "lsr_v2_paper_close_execution_backups"

CLOSE_PREFLIGHT_REPORT_NAME = "lsr_v2_supervised_paper_close_preflight_report.json"
CLOSE_PREFLIGHT_JSONL_NAME = "lsr_v2_supervised_paper_close_preflight.jsonl"
OPEN_MONITOR_REPORT_NAME = "lsr_v2_open_position_monitor_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"
SOURCE_TAG = "lsr_v2_supervised_paper_submit_execution"

CLOSE_ENABLE_ENV = "LSR_V2_PAPER_CLOSE_ENABLE"
CLOSE_CONFIRM_ENV = "LSR_V2_PAPER_CLOSE_CONFIRMATION"
CLOSE_MAX_POSITIONS_ENV = "LSR_V2_PAPER_CLOSE_MAX_POSITIONS"
CLOSE_CONFIRMATION_PHRASE = "I_UNDERSTAND_CLOSE_ONE_PAPER_POSITION_ONLY"

CLOSED_DECISION = "LSR_V2_SINGLE_PAPER_POSITION_CLOSED"
NOT_ENABLED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_NOT_ENABLED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_CONFIRMATION_MISSING"
PREFLIGHT_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_PREFLIGHT_MISSING"
POSITION_NOT_FOUND_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_POSITION_NOT_FOUND"
STATE_INCONSISTENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_STATE_INCONSISTENT"
MAX_POSITION_CAP_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_MAX_POSITION_CAP_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_CLOSE_EXECUTION_SAFETY_FAILED"


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

def _append_jsonl(path: str | Path, row: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(row), sort_keys=True) + "\n")


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
    return str(row.get("paper_order_source") or row.get("execution_source") or row.get("source") or meta.get("paper_order_source") or meta.get("execution_source") or meta.get("source") or "")


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


def _row_order_id(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("order_id") or row.get("id") or meta.get("order_id") or "")


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_lsr_v2_position(row: Mapping[str, Any], *, cycle_id: str = "") -> bool:
    source = _row_source(row)
    meta = _metadata_of(row)
    if SOURCE_TAG in source or "LSR_V2" in source.upper():
        return True
    if str(row.get("profile_name") or meta.get("profile_name") or "") == PROFILE_NAME:
        return True
    if cycle_id and _row_cycle(row) == cycle_id:
        return True
    return False


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "")
    if status in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}:
        return False
    return _safe_bool(row.get("pending"), status not in {"", "FILLED"})


def _position_size(row: Mapping[str, Any]) -> float:
    for key in ("position_size", "size", "quantity", "amount", "qty"):
        value = _safe_float(row.get(key), 0.0)
        if value > 0:
            return value
    return 0.0


def _entry_price(row: Mapping[str, Any]) -> float:
    for key in ("entry_price", "average_price", "avg_price", "price"):
        value = _safe_float(row.get(key), 0.0)
        if value > 0:
            return value
    return 0.0


def _backup_file(path: Path, backup_dir: Path, label: str) -> str:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = backup_dir / f"{label}_{stamp}.json"
    if path.exists():
        shutil.copy2(path, out)
    else:
        out.write_text("{}\n", encoding="utf-8")
    return str(out)


@dataclass(frozen=True)
class LSRV2SupervisedPaperCloseExecutionSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    close_preflight_report_name: str = CLOSE_PREFLIGHT_REPORT_NAME
    close_preflight_jsonl_name: str = CLOSE_PREFLIGHT_JSONL_NAME
    open_monitor_report_name: str = OPEN_MONITOR_REPORT_NAME
    paper_state_name: str = PAPER_STATE_NAME
    paper_status_name: str = PAPER_STATUS_NAME
    paper_events_name: str = PAPER_EVENTS_NAME
    backup_dir_name: str = BACKUP_DIR_NAME
    max_event_lines: int = 50000
    close_enable: str = ""
    close_confirmation: str = ""
    close_max_positions: int = 1
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2SupervisedPaperCloseExecutionSettings":
        max_positions = _safe_int(os.getenv(CLOSE_MAX_POSITIONS_ENV), 1)
        if max_positions <= 0:
            max_positions = 1
        return cls(
            data_dir=data_dir,
            close_enable=str(os.getenv(CLOSE_ENABLE_ENV) or ""),
            close_confirmation=str(os.getenv(CLOSE_CONFIRM_ENV) or ""),
            close_max_positions=max_positions,
        )

    @property
    def close_enabled(self) -> bool:
        return str(self.close_enable).strip() == "1"

    @property
    def close_confirmation_ok(self) -> bool:
        return str(self.close_confirmation).strip() == CLOSE_CONFIRMATION_PHRASE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_cycle_id(data_dir: str | Path, requested_cycle_id: str = "", settings: LSRV2SupervisedPaperCloseExecutionSettings | None = None) -> str:
    settings = settings or LSRV2SupervisedPaperCloseExecutionSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    if requested_cycle_id:
        return str(requested_cycle_id)
    for name in (settings.close_preflight_report_name, settings.open_monitor_report_name):
        report = _read_json(base / name)
        if report.get("cycle_id"):
            return str(report.get("cycle_id") or "")
    for row in reversed(_iter_jsonl_tail(base / settings.close_preflight_jsonl_name, max_lines=settings.max_event_lines)):
        if row.get("cycle_id"):
            return str(row.get("cycle_id") or "")
    for row in reversed(_iter_jsonl_tail(base / settings.paper_events_name, max_lines=settings.max_event_lines)):
        if row.get("cycle_id"):
            return str(row.get("cycle_id") or "")
    return ""


def select_cycle_scoped_close_preflight_events(data_dir: str | Path, cycle_id: str, settings: LSRV2SupervisedPaperCloseExecutionSettings | None = None) -> list[dict[str, Any]]:
    settings = settings or LSRV2SupervisedPaperCloseExecutionSettings(data_dir=str(data_dir))
    rows = _iter_jsonl_tail(Path(data_dir) / settings.close_preflight_jsonl_name, max_lines=settings.max_event_lines)
    selected = [dict(r) for r in rows if r.get("event_type") == "LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT" and (not cycle_id or str(r.get("cycle_id") or "") == cycle_id)]
    if selected:
        return selected
    report = _read_json(Path(data_dir) / settings.close_preflight_report_name)
    if report and (not cycle_id or str(report.get("cycle_id") or "") == cycle_id):
        # Conservative summary fallback.  It can authorize only when all fields are explicit.
        symbols = report.get("symbols") if isinstance(report.get("symbols"), list) else []
        sides = report.get("sides") if isinstance(report.get("sides"), list) else []
        if _safe_int(report.get("would_prepare_close_count"), 0) > 0 or _safe_int(report.get("close_required_diagnostic_count"), 0) > 0:
            out: list[dict[str, Any]] = []
            for idx, symbol in enumerate(symbols or [""]):
                out.append({
                    "event_type": "LSR_V2_SUPERVISED_PAPER_CLOSE_PREFLIGHT",
                    "cycle_id": str(report.get("cycle_id") or cycle_id),
                    "symbol": str(symbol or ""),
                    "side": str((sides[idx] if idx < len(sides) else "") or ""),
                    "position_found": True,
                    "position_open": True,
                    "would_prepare_close": True,
                    "close_required_diagnostic": True,
                    "take_profit_hit_diagnostic": _safe_int(report.get("take_profit_hit_diagnostic_count"), 0) > 0,
                    "stop_hit_diagnostic": _safe_int(report.get("stop_hit_diagnostic_count"), 0) > 0,
                    "close_reason": (report.get("close_reasons") or ["CLOSE_REQUIRED_DIAGNOSTIC"])[0] if isinstance(report.get("close_reasons"), list) else "CLOSE_REQUIRED_DIAGNOSTIC",
                    "current_price": None,
                    "risk_amount": report.get("total_risk_amount"),
                    "notional": report.get("total_notional"),
                })
            return out
    return []


def _find_matching_position(event: Mapping[str, Any], positions: list[dict[str, Any]], cycle_id: str) -> tuple[str, dict[str, Any]] | tuple[str, None]:
    position_id = str(event.get("position_id") or "")
    order_id = str(event.get("order_id") or "")
    symbol = str(event.get("symbol") or "")
    side = str(event.get("side") or "").upper()
    if position_id:
        for key, pos in ((str(p.get("position_id") or p.get("id") or idx), p) for idx, p in enumerate(positions)):
            if _row_position_id(pos) == position_id:
                return key, pos
    if order_id:
        for key, pos in ((str(p.get("position_id") or p.get("id") or idx), p) for idx, p in enumerate(positions)):
            if str(pos.get("order_id") or _metadata_of(pos).get("order_id") or "") == order_id:
                return key, pos
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for idx, pos in enumerate(positions):
        key = str(pos.get("__state_key") or pos.get("position_id") or pos.get("id") or idx)
        score = 0
        if _is_position_open(pos):
            score += 3
        if _is_lsr_v2_position(pos, cycle_id=cycle_id):
            score += 4
        if cycle_id and _row_cycle(pos) == cycle_id:
            score += 3
        if symbol and _row_symbol(pos) == symbol:
            score += 2
        if side and _row_side(pos) == side:
            score += 1
        if score >= 6:
            scored.append((score, key, pos))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1], scored[0][2]
    return "", None


def _state_positions_with_keys(state: Mapping[str, Any]) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    raw = state.get("positions")
    if isinstance(raw, Mapping):
        rows = []
        for key, value in raw.items():
            row = dict(value) if isinstance(value, Mapping) else {"value": value}
            row.setdefault("position_id", str(key))
            row["__state_key"] = str(key)
            rows.append((str(key), row))
        return "dict", rows
    if isinstance(raw, list):
        rows = []
        for idx, value in enumerate(raw):
            row = dict(value) if isinstance(value, Mapping) else {"value": value}
            row.setdefault("position_id", str(row.get("position_id") or idx))
            row["__state_key"] = str(idx)
            rows.append((str(idx), row))
        return "list", rows
    return "dict", []


def _set_state_position(state: dict[str, Any], storage_kind: str, key: str, position: Mapping[str, Any]) -> None:
    if storage_kind == "list":
        positions = state.get("positions")
        if not isinstance(positions, list):
            positions = []
        idx = _safe_int(key, -1)
        if 0 <= idx < len(positions):
            clean = dict(position)
            clean.pop("__state_key", None)
            positions[idx] = clean
        state["positions"] = positions
    else:
        positions = state.get("positions")
        if not isinstance(positions, dict):
            positions = {}
        clean = dict(position)
        clean.pop("__state_key", None)
        positions[key] = clean
        state["positions"] = positions


def _close_position_payload(position: Mapping[str, Any], event: Mapping[str, Any], *, close_price: float, close_reason: str) -> dict[str, Any]:
    pos = dict(position)
    side = _row_side(pos) or str(event.get("side") or "").upper()
    entry = _entry_price(pos) or _safe_float(event.get("entry_price"), 0.0)
    size = _position_size(pos) or _safe_float(event.get("position_size"), 0.0)
    if side == "SELL":
        pnl = (entry - close_price) * size
    else:
        pnl = (close_price - entry) * size
    risk_amount = _safe_float(pos.get("risk_amount"), _safe_float(event.get("risk_amount"), 0.0))
    pos.pop("__state_key", None)
    pos.update({
        "status": "CLOSED",
        "open": False,
        "closed_at": utc_now_iso(),
        "close_price": _round(close_price),
        "exit_price": _round(close_price),
        "close_reason": close_reason,
        "paper_close_source": "lsr_v2_supervised_paper_close_execution",
        "realized_pnl": _round(pnl),
        "unrealized_pnl": 0.0,
        "risk_multiple_final": _round(pnl / risk_amount) if risk_amount > 0 else None,
    })
    meta = _metadata_of(pos)
    meta.update({
        "closed_by": PROMPT_ID,
        "close_reason": close_reason,
        "cycle_id": str(event.get("cycle_id") or _row_cycle(pos) or ""),
    })
    pos["metadata"] = meta
    return pos


def _derive_status_after_close(state: Mapping[str, Any], previous_status: Mapping[str, Any]) -> dict[str, Any]:
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    open_positions = [p for p in positions if _is_position_open(p)]
    pending_orders = [o for o in orders if _is_order_pending(o)]
    realized_pnl = _safe_float(state.get("realized_pnl"), _safe_float(previous_status.get("realized_pnl"), 0.0))
    balance = _safe_float(state.get("balance"), _safe_float(previous_status.get("balance"), 0.0))
    unrealized = round(sum(_safe_float(p.get("unrealized_pnl"), 0.0) for p in open_positions), 10)
    status = dict(previous_status)
    status.update({
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "positions": [
            {
                "position_id": _row_position_id(p),
                "symbol": _row_symbol(p),
                "side": _row_side(p),
                "status": _status_text(p, "OPEN"),
                "entry_price": p.get("entry_price"),
                "current_price": p.get("current_price") or p.get("mark_price") or p.get("price"),
                "unrealized_pnl": p.get("unrealized_pnl", 0.0),
                "notional": p.get("notional", 0.0),
            }
            for p in open_positions
        ],
        "balance": balance,
        "equity": round(balance + unrealized, 10) if balance else _safe_float(previous_status.get("equity"), 0.0),
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized,
        "updated_at": utc_now_iso(),
        "lsr_v2_close_execution": {
            "prompt_id": PROMPT_ID,
            "status": "SYNCED_AFTER_CLOSE",
            "open_positions": len(open_positions),
            "pending_orders": len(pending_orders),
        },
    })
    monitor = dict(status.get("position_monitor") if isinstance(status.get("position_monitor"), Mapping) else {})
    account = dict(monitor.get("account") if isinstance(monitor.get("account"), Mapping) else {})
    raw = dict(account.get("raw") if isinstance(account.get("raw"), Mapping) else {})
    raw.update({
        "balance": status.get("balance"),
        "equity": status.get("equity"),
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized,
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "positions": status.get("positions", []),
        "mode": raw.get("mode") or status.get("mode") or "paper",
    })
    account.update({
        "balance": status.get("balance"),
        "equity": status.get("equity"),
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized,
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "mode": account.get("mode") or status.get("mode") or "paper",
        "raw": raw,
    })
    monitor.update({
        "status": "OPEN" if open_positions else "FLAT",
        "mode": monitor.get("mode") or status.get("mode") or "paper",
        "generated_at": utc_now_iso(),
        "open_position_count": len(open_positions),
        "positions": status.get("positions", []),
        "account": account,
    })
    status["position_monitor"] = monitor
    return status


def _operator_controls(settings: LSRV2SupervisedPaperCloseExecutionSettings) -> dict[str, Any]:
    return {
        "close_enabled": bool(settings.close_enabled),
        "close_confirmation_ok": bool(settings.close_confirmation_ok),
        "close_max_positions": int(settings.close_max_positions),
    }


def build_lsr_v2_supervised_paper_close_execution_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SupervisedPaperCloseExecutionSettings | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2SupervisedPaperCloseExecutionSettings.from_env(data_dir=str(data_dir))
    base = Path(data_dir)
    selected_cycle_id = select_cycle_id(data_dir, requested_cycle_id=cycle_id, settings=settings)
    preflight_events = select_cycle_scoped_close_preflight_events(data_dir, selected_cycle_id, settings)
    state_path = base / settings.paper_state_name
    status_path = base / settings.paper_status_name
    state = _read_json(state_path)
    status = _read_json(status_path)
    storage_kind, keyed_positions = _state_positions_with_keys(state)
    positions = [p for _, p in keyed_positions]
    open_lsr_positions = [p for p in positions if _is_position_open(p) and _is_lsr_v2_position(p, cycle_id=selected_cycle_id)]
    controls = _operator_controls(settings)

    close_required = [e for e in preflight_events if _safe_bool(e.get("would_prepare_close"), False) and _safe_bool(e.get("close_required_diagnostic"), False)]
    blockers: list[str] = []
    if not preflight_events:
        blockers.append("close_preflight_missing")
    if preflight_events and not close_required:
        blockers.append("close_not_required")
    if not open_lsr_positions:
        blockers.append("matching_open_position_not_found")
    if len(open_lsr_positions) > settings.close_max_positions:
        blockers.append("max_position_cap_exceeded")
    if not settings.close_enabled:
        blockers.append("close_not_enabled")
    if settings.close_enabled and not settings.close_confirmation_ok:
        blockers.append("close_confirmation_missing")
    status_open_positions = _safe_int(status.get("open_positions"), 0)
    if "open_positions" in status and status_open_positions != len([p for p in positions if _is_position_open(p)]):
        blockers.append("paper_status_inconsistent")
    if _safe_bool(status.get("live_enabled"), False) or _safe_bool(status.get("testnet_enabled"), False) or _safe_bool(status.get("exchange_broker_enabled"), False):
        blockers.append("unsafe_status_flags")

    safety_violation = bool(
        _safe_bool(status.get("live_enabled"), False)
        or _safe_bool(status.get("testnet_enabled"), False)
        or _safe_bool(status.get("exchange_broker_enabled"), False)
        or _safe_bool(status.get("operational_unlock_allowed"), False)
    )
    closed_events: list[dict[str, Any]] = []
    backup_state_path = ""
    backup_status_path = ""
    positions_closed = 0
    total_realized = 0.0
    total_notional = 0.0
    total_risk = 0.0

    can_close = bool(
        preflight_events
        and close_required
        and open_lsr_positions
        and len(open_lsr_positions) <= settings.close_max_positions
        and settings.close_enabled
        and settings.close_confirmation_ok
        and not safety_violation
        and "paper_status_inconsistent" not in blockers
    )

    if can_close:
        backup_dir = base / settings.backup_dir_name
        backup_state_path = _backup_file(state_path, backup_dir, "paper_state")
        backup_status_path = _backup_file(status_path, backup_dir, "paper_status")
        used_positions: set[str] = set()
        for event in close_required[: settings.close_max_positions]:
            key, pos = _find_matching_position(event, positions, selected_cycle_id)
            if not pos or key in used_positions:
                continue
            used_positions.add(key)
            close_price = _safe_float(event.get("current_price"), 0.0) or _safe_float(event.get("take_profit"), 0.0) or _entry_price(pos)
            close_reason = str(event.get("close_reason") or ("TAKE_PROFIT_HIT_DIAGNOSTIC" if _safe_bool(event.get("take_profit_hit_diagnostic"), False) else "STOP_LOSS_HIT_DIAGNOSTIC" if _safe_bool(event.get("stop_hit_diagnostic"), False) else "CLOSE_REQUIRED_DIAGNOSTIC"))
            closed_pos = _close_position_payload(pos, event, close_price=close_price, close_reason=close_reason)
            _set_state_position(state, storage_kind, key, closed_pos)
            positions_closed += 1
            realized = _safe_float(closed_pos.get("realized_pnl"), 0.0)
            total_realized += realized
            total_notional += _safe_float(pos.get("notional"), _safe_float(event.get("notional"), 0.0))
            total_risk += _safe_float(pos.get("risk_amount"), _safe_float(event.get("risk_amount"), 0.0))
            closed_events.append({
                "event_type": EVENT_TYPE,
                "prompt_id": PROMPT_ID,
                "created_at": utc_now_iso(),
                "cycle_id": selected_cycle_id,
                "source": "lsr_v2_supervised_paper_close_preflight",
                "profile_name": PROFILE_NAME,
                "selected_overlay_id": SELECTED_OVERLAY_ID,
                "position_id": _row_position_id(closed_pos),
                "order_id": str(closed_pos.get("order_id") or _metadata_of(closed_pos).get("order_id") or event.get("order_id") or ""),
                "symbol": _row_symbol(closed_pos) or str(event.get("symbol") or ""),
                "side": _row_side(closed_pos) or str(event.get("side") or ""),
                "entry_price": _round(_entry_price(pos)),
                "close_price": _round(close_price),
                "stop_loss": _round(event.get("stop_loss") or pos.get("stop_loss")),
                "take_profit": _round(event.get("take_profit") or pos.get("take_profit")),
                "position_size": _round(_position_size(pos)),
                "notional": _round(pos.get("notional") or event.get("notional")),
                "risk_amount": _round(pos.get("risk_amount") or event.get("risk_amount")),
                "realized_pnl": _round(realized),
                "risk_multiple_final": closed_pos.get("risk_multiple_final"),
                "close_reason": close_reason,
                "would_close_position": True,
                "broker_close_called": True,
                "paper_close_called": True,
                "orders_submitted_by_close_execution": 0,
                "positions_closed_by_close_execution": 1,
                "positions_opened_by_close_execution": 0,
                "new_order_created_by_close_execution": False,
                "automatic_reentry_enabled": False,
                "live_enabled": False,
                "testnet_enabled": False,
                "exchange_broker_enabled": False,
                "operational_unlock_allowed": False,
            })
        # update state and status only after all close events prepared
        state["realized_pnl"] = _round(_safe_float(state.get("realized_pnl"), 0.0) + total_realized)
        # For a paper-only flat close, realize PnL into cash balance.
        if state.get("balance") is not None:
            state["balance"] = _round(_safe_float(state.get("balance"), 0.0) + total_realized)
        state["updated_at"] = utc_now_iso()
        _write_json(state_path, state)
        status_after = _derive_status_after_close(state, status)
        _write_json(status_path, status_after)
        for e in closed_events:
            _append_jsonl(base / settings.paper_events_name, e)
    _write_jsonl_replace(base / settings.jsonl_name, closed_events)

    if safety_violation:
        decision = REJECT_DECISION
        status_text = "WARN"
    elif not preflight_events:
        decision = PREFLIGHT_MISSING_DECISION
        status_text = "WARN"
    elif preflight_events and not close_required:
        decision = "KEEP_DIAGNOSTIC_LSR_V2_CLOSE_NOT_REQUIRED"
        status_text = "WARN"
    elif not open_lsr_positions:
        decision = POSITION_NOT_FOUND_DECISION
        status_text = "WARN"
    elif len(open_lsr_positions) > settings.close_max_positions:
        decision = MAX_POSITION_CAP_DECISION
        status_text = "WARN"
    elif "paper_status_inconsistent" in blockers:
        decision = STATE_INCONSISTENT_DECISION
        status_text = "WARN"
    elif not settings.close_enabled:
        decision = NOT_ENABLED_DECISION
        status_text = "WARN"
    elif settings.close_enabled and not settings.close_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status_text = "WARN"
    elif positions_closed > 0:
        decision = CLOSED_DECISION
        status_text = "PASS"
    else:
        decision = REJECT_DECISION
        status_text = "WARN"
        blockers.append("close_execution_failed_no_position_closed")

    state_after = _read_json(state_path)
    status_after = _read_json(status_path)
    after_positions = _collection_rows(state_after.get("positions"), id_field="position_id")
    after_open_lsr = [p for p in after_positions if _is_position_open(p) and _is_lsr_v2_position(p, cycle_id=selected_cycle_id)]

    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "classification_labels": ["LSR_V2_SUPERVISED_PAPER_CLOSE_EXECUTION"],
        "blockers": sorted(set(blockers)),
        "cycle_id": selected_cycle_id,
        "event_source": "close_preflight_jsonl",
        "strict_cycle_scope": True,
        "close_enabled": bool(settings.close_enabled),
        "close_confirmation_ok": bool(settings.close_confirmation_ok),
        "max_positions": int(settings.close_max_positions),
        "close_preflight_events": len(preflight_events),
        "close_required_diagnostic_count": len(close_required),
        "close_execution_events": len(closed_events),
        "positions_closed_by_lsr_v2_close_execution": int(positions_closed),
        "orders_submitted_by_lsr_v2_close_execution": 0,
        "positions_opened_by_lsr_v2_close_execution": 0,
        "broker_close_called": bool(positions_closed > 0),
        "paper_close_called": bool(positions_closed > 0),
        "new_order_created_by_close_execution": False,
        "automatic_reentry_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "paper_state_modified": bool(positions_closed > 0),
        "paper_status_modified": bool(positions_closed > 0),
        "backup_state_path": backup_state_path,
        "backup_status_path": backup_status_path,
        "open_lsr_v2_positions_before": len(open_lsr_positions),
        "open_lsr_v2_positions_after": len(after_open_lsr),
        "paper_status_open_positions_after": _safe_int(status_after.get("open_positions"), 0),
        "symbols": sorted({str(e.get("symbol") or "") for e in closed_events if e.get("symbol")}) or sorted({str(_row_symbol(p)) for p in open_lsr_positions if _row_symbol(p)}),
        "sides": sorted({str(e.get("side") or "") for e in closed_events if e.get("side")}) or sorted({str(_row_side(p)) for p in open_lsr_positions if _row_side(p)}),
        "close_reasons": sorted({str(e.get("close_reason") or "") for e in closed_events if e.get("close_reason")}) or sorted({str(e.get("close_reason") or "") for e in close_required if e.get("close_reason")}),
        "total_notional": _round(total_notional),
        "total_risk_amount": _round(total_risk),
        "realized_pnl_total": _round(total_realized),
        "safety_checks": {
            "no_new_order": True,
            "no_reentry": True,
            "max_positions_closed_one": positions_closed <= settings.close_max_positions,
            "live_disabled": True,
            "testnet_disabled": True,
            "exchange_broker_disabled": True,
            "operational_unlock_blocked": True,
        },
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
