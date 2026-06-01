"""Prompt 29.4.4s-10ah-2 — LSR-v2 Telegram open-position monitor bridge stale-open guard.

Read-only Telegram monitor bridge for open LSR-v2 paper positions.

The bridge reads already-produced open-position monitor reports/JSONL files and
builds a Telegram-friendly SL/TP progress bar with a moving marker:

    SL 72568.30 ┃──────●──────────┃ TP 73178.31

It never submits orders, never closes positions, never calls a broker, never
mutates paper_state/paper_status, and never enables live/testnet/exchange
execution. Actual Telegram sending is disabled by default and requires both an
explicit enable flag and confirmation phrase.  This hotfix also checks
paper_status/paper_state and close-execution reports before notifying, so
stale monitor reports for already-closed positions are not sent.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore
import asyncio
import json
import os
import urllib.error
import urllib.parse
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from .aiohttp_compat import install_aiohttp_windows_ssl_context_compat
except Exception:  # pragma: no cover - script-style fallback
    from core.aiohttp_compat import install_aiohttp_windows_ssl_context_compat  # type: ignore

try:
    install_aiohttp_windows_ssl_context_compat()
    import aiohttp
except Exception:  # pragma: no cover - optional transport fallback
    aiohttp = None

PROMPT_ID = "29.4.4s-10ah-2"
EVENT_TYPE = "LSR_V2_TELEGRAM_POSITION_MONITOR_BRIDGE"
REPORT_NAME = "lsr_v2_telegram_position_monitor_bridge_report.json"
JSONL_NAME = "lsr_v2_telegram_position_monitor_bridge.jsonl"
STATE_NAME = "lsr_v2_telegram_position_monitor_bridge_state.json"
TELEGRAM_AUDIT_NAME = "telegram_audit.jsonl"

SEND_ENABLE_ENV = "LSR_V2_TELEGRAM_POSITION_MONITOR_ENABLE"
SEND_CONFIRM_ENV = "LSR_V2_TELEGRAM_POSITION_MONITOR_CONFIRMATION"
SEND_FORCE_ENV = "LSR_V2_TELEGRAM_POSITION_MONITOR_FORCE_RESEND"
MAX_MESSAGES_ENV = "LSR_V2_TELEGRAM_POSITION_MONITOR_MAX_MESSAGES"
BAR_WIDTH_ENV = "LSR_V2_TELEGRAM_POSITION_MONITOR_BAR_WIDTH"
REQUIRED_SEND_VALUE = "1"
REQUIRED_CONFIRMATION = "I_UNDERSTAND_SEND_LSR_V2_POSITION_MONITOR"

DRY_RUN_DECISION = "LSR_V2_TELEGRAM_POSITION_MONITOR_READY_DRY_RUN"
SENT_DECISION = "LSR_V2_TELEGRAM_POSITION_MONITOR_SENT"
NO_OPEN_POSITION_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_POSITION_MONITOR_NO_OPEN_POSITION"
CONFIG_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_POSITION_MONITOR_CONFIG_MISSING"
PARTIAL_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TELEGRAM_POSITION_MONITOR_PARTIAL_SEND"
REJECT_DECISION = "REJECT_LSR_V2_TELEGRAM_POSITION_MONITOR_SAFETY_FAILED"

MONITOR_SOURCES = (
    {
        "ordinal": "FIRST",
        "report_name": "lsr_v2_open_position_monitor_report.json",
        "jsonl_name": "lsr_v2_open_position_monitor.jsonl",
    },
    {
        "ordinal": "SECOND",
        "report_name": "lsr_v2_second_open_position_monitor_report.json",
        "jsonl_name": "lsr_v2_second_open_position_monitor.jsonl",
    },
    {
        "ordinal": "THIRD",
        "report_name": "lsr_v2_third_open_position_monitor_report.json",
        "jsonl_name": "lsr_v2_third_open_position_monitor.jsonl",
    },
)

CLOSE_REPORTS = (
    {
        "ordinal": "FIRST",
        "report_name": "lsr_v2_supervised_paper_close_execution_report.json",
        "closed_decisions": {"LSR_V2_SINGLE_PAPER_POSITION_CLOSED"},
        "closed_count_keys": ("positions_closed_by_lsr_v2_close_execution",),
        "open_after_keys": ("open_lsr_v2_positions_after", "paper_status_open_positions_after"),
    },
    {
        "ordinal": "SECOND",
        "report_name": "lsr_v2_second_trade_close_execution_report.json",
        "closed_decisions": {"LSR_V2_SECOND_SINGLE_PAPER_POSITION_CLOSED"},
        "closed_count_keys": ("positions_closed_by_second_trade_close_execution",),
        "open_after_keys": ("open_second_lsr_v2_positions_after", "paper_status_open_positions_after"),
    },
    {
        "ordinal": "THIRD",
        "report_name": "lsr_v2_third_trade_close_execution_report.json",
        "closed_decisions": {"LSR_V2_THIRD_SINGLE_PAPER_POSITION_CLOSED"},
        "closed_count_keys": ("positions_closed_by_third_trade_close_execution",),
        "open_after_keys": ("open_third_lsr_v2_positions_after", "paper_status_open_positions_after"),
    },
)

PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"

Sender = Callable[[str], Mapping[str, Any] | bool | None]


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


def _fmt_num(value: Any, digits: int = 4) -> str:
    number = _safe_float(value, 0.0)
    text = f"{number:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


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


def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _iter_jsonl_tail(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=max_lines, require_event_type=False)

def _load_state(path: str | Path) -> dict[str, Any]:
    state = _read_json(path)
    if not state:
        return {"sent_keys": []}
    if not isinstance(state.get("sent_keys"), list):
        state["sent_keys"] = []
    return state


def _state_sent_keys(state: Mapping[str, Any]) -> set[str]:
    raw = state.get("sent_keys")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if str(x)}


def _update_state(path: str | Path, *, sent_keys: Iterable[str]) -> None:
    p = Path(path)
    state = _load_state(p)
    keys = sorted(_state_sent_keys(state).union({str(x) for x in sent_keys if str(x)}))
    state.update({"updated_at": utc_now_iso(), "sent_keys": keys})
    _write_json(p, state)


@dataclass(frozen=True)
class LSRV2TelegramPositionMonitorBridgeSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    state_name: str = STATE_NAME
    telegram_audit_name: str = TELEGRAM_AUDIT_NAME
    send_enable: str = ""
    send_confirmation: str = ""
    required_send_value: str = REQUIRED_SEND_VALUE
    required_send_confirmation: str = REQUIRED_CONFIRMATION
    force_resend: bool = False
    max_messages: int = 3
    bar_width: int = 24
    telegram_token: str = ""
    telegram_chat_id: str = ""
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2TelegramPositionMonitorBridgeSettings":
        max_messages = _safe_int(os.getenv(MAX_MESSAGES_ENV), 3)
        if max_messages <= 0:
            max_messages = 3
        bar_width = _safe_int(os.getenv(BAR_WIDTH_ENV), 24)
        if bar_width < 8:
            bar_width = 8
        if bar_width > 60:
            bar_width = 60
        return cls(
            data_dir=data_dir,
            send_enable=str(os.getenv(SEND_ENABLE_ENV) or ""),
            send_confirmation=str(os.getenv(SEND_CONFIRM_ENV) or ""),
            force_resend=_safe_bool(os.getenv(SEND_FORCE_ENV), False),
            max_messages=max_messages,
            bar_width=bar_width,
            telegram_token=str(os.getenv("TELEGRAM_TOKEN") or ""),
            telegram_chat_id=str(os.getenv("TELEGRAM_CHAT_ID") or ""),
        )

    @property
    def send_enabled(self) -> bool:
        return str(self.send_enable).strip() == self.required_send_value

    @property
    def send_confirmation_ok(self) -> bool:
        return str(self.send_confirmation).strip() == self.required_send_confirmation

    @property
    def telegram_configured(self) -> bool:
        return bool(str(self.telegram_token).strip() and str(self.telegram_chat_id).strip())

    @property
    def actual_send_allowed(self) -> bool:
        return bool(self.send_enabled and self.send_confirmation_ok and self.telegram_configured and self.fail_closed)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        if out.get("telegram_token"):
            out["telegram_token"] = "***"
        return out


@dataclass(frozen=True)
class LSRV2PositionMonitorNotification:
    key: str
    kind: str
    text: str
    source_report: str
    cycle_id: str
    symbol: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def progress_to_target(*, side: str, current: float, stop_loss: float, take_profit: float) -> float | None:
    side = str(side or "").upper()
    if current <= 0 or stop_loss <= 0 or take_profit <= 0 or stop_loss == take_profit:
        return None
    if side in {"SELL", "SHORT"}:
        denom = stop_loss - take_profit
        if denom <= 0:
            return None
        return max(0.0, min(1.0, (stop_loss - current) / denom))
    denom = take_profit - stop_loss
    if denom <= 0:
        return None
    return max(0.0, min(1.0, (current - stop_loss) / denom))


def progress_bar(*, side: str, current: float, stop_loss: float, take_profit: float, width: int = 24) -> tuple[str, float | None, str]:
    progress = progress_to_target(side=side, current=current, stop_loss=stop_loss, take_profit=take_profit)
    width = max(8, min(int(width or 24), 60))
    if progress is None:
        return f"SL {_fmt_num(stop_loss, 2)} ┃{'?' * width}┃ TP {_fmt_num(take_profit, 2)}", None, "UNKNOWN"
    marker = int(round(progress * width))
    marker = max(0, min(width, marker))
    left = "━" * marker
    right = "─" * (width - marker)
    if progress >= 1.0:
        status = "TAKE_PROFIT_ZONE"
    elif progress <= 0.0:
        status = "STOP_LOSS_ZONE"
    elif progress >= 0.8:
        status = "NEAR_TAKE_PROFIT"
    elif progress <= 0.2:
        status = "NEAR_STOP_LOSS"
    else:
        status = "IN_RANGE"
    return f"SL {_fmt_num(stop_loss, 2)} ┃{left}●{right}┃ TP {_fmt_num(take_profit, 2)}", progress, status


def _pct_distance(current: float, level: float) -> float | None:
    if current <= 0 or level <= 0:
        return None
    return round(abs(current - level) / current * 100.0, 4)


def _map_get(report: Mapping[str, Any], key: str, symbol: str, default: Any = 0.0) -> Any:
    value = report.get(key)
    if isinstance(value, Mapping):
        if symbol in value:
            return value.get(symbol)
        if value:
            return next(iter(value.values()))
    return default


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


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or default).upper()


def _row_cycle(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _row_symbol(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("symbol") or meta.get("symbol") or "")


def _row_source(row: Mapping[str, Any]) -> str:
    meta = _metadata_of(row)
    return str(row.get("paper_order_source") or row.get("execution_source") or row.get("source") or meta.get("paper_order_source") or meta.get("execution_source") or meta.get("source") or "")


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_lsr_v2_position(row: Mapping[str, Any], *, cycle_id: str = "", symbol: str = "") -> bool:
    source = _row_source(row).upper()
    profile = str(row.get("profile_name") or _metadata_of(row).get("profile_name") or "")
    if "LSR_V2" in source or profile == "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24":
        pass
    elif cycle_id and _row_cycle(row) == cycle_id:
        pass
    else:
        return False
    if cycle_id and _row_cycle(row) and _row_cycle(row) != cycle_id:
        return False
    if symbol and _row_symbol(row) and _row_symbol(row) != symbol:
        return False
    return True


def _closed_report_is_authoritative(report: Mapping[str, Any], source: Mapping[str, Any]) -> bool:
    if not report:
        return False
    decision = str(report.get("decision") or "")
    if decision in set(source.get("closed_decisions") or set()):
        return True
    closed_count = sum(_safe_int(report.get(str(key)), 0) for key in source.get("closed_count_keys") or ())
    if closed_count <= 0:
        return False
    open_after_values = [_safe_int(report.get(str(key)), -1) for key in source.get("open_after_keys") or () if str(key) in report]
    return not open_after_values or all(value == 0 for value in open_after_values)


def _stale_guard_context(data_dir: str | Path) -> dict[str, Any]:
    base = Path(data_dir)
    status = _read_json(base / PAPER_STATUS_NAME)
    state = _read_json(base / PAPER_STATE_NAME)
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = [row for row in positions if _is_position_open(row)]
    open_lsr_positions = [row for row in open_positions if _is_lsr_v2_position(row)]
    closed_cycles: dict[str, dict[str, Any]] = {}
    close_reports: dict[str, Any] = {}
    for source in CLOSE_REPORTS:
        report_name = str(source["report_name"])
        report = _read_json(base / report_name)
        is_closed = _closed_report_is_authoritative(report, source)
        cycle_id = str(report.get("cycle_id") or "") if report else ""
        close_reports[report_name] = {
            "present": bool(report),
            "status": str(report.get("status") or "") if report else "",
            "decision": str(report.get("decision") or "") if report else "",
            "cycle_id": cycle_id,
            "closed": bool(is_closed),
        }
        if is_closed and cycle_id:
            closed_cycles[cycle_id] = {"report_name": report_name, "decision": str(report.get("decision") or "")}
    return {
        "paper_status_present": bool(status),
        "paper_state_present": bool(state),
        "paper_status_open_positions": _safe_int(status.get("open_positions"), 0),
        "paper_status_pending_orders": _safe_int(status.get("pending_orders"), 0),
        "paper_state_open_positions": len(open_positions),
        "paper_state_open_lsr_v2_positions": len(open_lsr_positions),
        "paper_state_open_lsr_v2_cycles": sorted({str(_row_cycle(row)) for row in open_lsr_positions if _row_cycle(row)}),
        "paper_state_open_lsr_v2_symbols": sorted({str(_row_symbol(row)) for row in open_lsr_positions if _row_symbol(row)}),
        "paper_state_open_lsr_v2_cycle_symbols": sorted({
            f"{_row_cycle(row)}|{_row_symbol(row)}"
            for row in open_lsr_positions
            if _row_cycle(row) and _row_symbol(row)
        }),
        "paper_state_open_lsr_v2_position_keys": [
            str(row.get("position_id") or row.get("id") or idx) for idx, row in enumerate(open_lsr_positions)
        ],
        "closed_cycles": closed_cycles,
        "close_reports": close_reports,
        "guard_enabled": True,
    }


def _is_monitor_event_stale(event: Mapping[str, Any], guard: Mapping[str, Any]) -> tuple[bool, str]:
    cycle_id = str(event.get("cycle_id") or "")
    symbol = str(event.get("symbol") or "")
    if cycle_id and cycle_id in dict(guard.get("closed_cycles") or {}):
        source = dict(guard.get("closed_cycles") or {}).get(cycle_id) or {}
        return True, f"closed_by_{source.get('report_name') or 'close_report'}"
    # Explicit flat paper_status is authoritative for stale monitor alerts.
    if bool(guard.get("paper_status_present")) and _safe_int(guard.get("paper_status_open_positions"), 0) <= 0:
        return True, "paper_status_flat"
    if bool(guard.get("paper_state_present")):
        open_count = _safe_int(guard.get("paper_state_open_lsr_v2_positions"), 0)
        if open_count <= 0:
            return True, "paper_state_no_open_lsr_v2_position"
        open_cycles = {str(x) for x in guard.get("paper_state_open_lsr_v2_cycles") or [] if str(x)}
        open_symbols = {str(x) for x in guard.get("paper_state_open_lsr_v2_symbols") or [] if str(x)}
        open_cycle_symbols = {str(x) for x in guard.get("paper_state_open_lsr_v2_cycle_symbols") or [] if str(x)}
        if cycle_id and open_cycles and cycle_id not in open_cycles:
            return True, "paper_state_open_cycle_mismatch"
        if symbol and open_symbols and symbol not in open_symbols:
            return True, "paper_state_open_symbol_mismatch"
        if cycle_id and symbol and open_cycle_symbols and f"{cycle_id}|{symbol}" not in open_cycle_symbols:
            return True, "paper_state_open_cycle_symbol_mismatch"
    return False, ""


def _latest_monitor_events(data_dir: str | Path, source: Mapping[str, str]) -> list[dict[str, Any]]:
    base = Path(data_dir)
    rows = _iter_jsonl_tail(base / str(source["jsonl_name"]), max_lines=50000)
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        symbol = str(row.get("symbol") or "")
        cycle_id = str(row.get("cycle_id") or "")
        if not symbol:
            continue
        if not _safe_bool(row.get("position_open"), False):
            continue
        key = (cycle_id, symbol)
        selected[key] = row
    return list(selected.values())


def _events_from_report(report: Mapping[str, Any], source: Mapping[str, str]) -> list[dict[str, Any]]:
    if not report:
        return []
    open_count = _safe_int(report.get("open_lsr_v2_position_count") or report.get("open_second_lsr_v2_position_count"), 0)
    if open_count <= 0 or not _safe_bool(report.get("second_trade_position_open", report.get("position_open", True)), True):
        return []
    symbols = report.get("symbols") if isinstance(report.get("symbols"), list) else []
    sides = report.get("sides") if isinstance(report.get("sides"), list) else []
    out: list[dict[str, Any]] = []
    for idx, symbol in enumerate(symbols or [""]):
        symbol = str(symbol or "")
        if not symbol:
            continue
        side = str((sides[idx] if idx < len(sides) else "") or "BUY")
        risk = _safe_float(report.get("total_risk_amount"), 0.0)
        unrealized = _safe_float(report.get("unrealized_pnl_total"), 0.0)
        out.append({
            "event_type": "REPORT_FALLBACK_POSITION_MONITOR",
            "cycle_id": str(report.get("cycle_id") or ""),
            "symbol": symbol,
            "side": side,
            "entry_price": _safe_float(_map_get(report, "entry_prices", symbol), 0.0),
            "current_price": _safe_float(_map_get(report, "current_prices", symbol), 0.0),
            "stop_loss": _safe_float(_map_get(report, "stop_losses", symbol), 0.0),
            "take_profit": _safe_float(_map_get(report, "take_profits", symbol), 0.0),
            "unrealized_pnl": unrealized,
            "risk_amount": risk,
            "risk_multiple_current": _safe_float(report.get("risk_multiple_current_avg"), unrealized / risk if risk > 0 else 0.0),
            "take_profit_hit_diagnostic": _safe_int(report.get("take_profit_hit_diagnostic_count"), 0) > 0,
            "stop_hit_diagnostic": _safe_int(report.get("stop_hit_diagnostic_count"), 0) > 0,
            "close_required_diagnostic": _safe_bool(report.get("close_required_diagnostic"), False),
            "source_report": str(source["report_name"]),
        })
    return out


def _normalise_monitor_event(raw: Mapping[str, Any], *, source_report: str) -> dict[str, Any]:
    row = dict(raw)
    symbol = str(row.get("symbol") or "")
    side = str(row.get("side") or "BUY").upper()
    current = _safe_float(row.get("current_price") or row.get("mark_price") or row.get("last_price"), 0.0)
    entry = _safe_float(row.get("entry_price"), 0.0)
    stop = _safe_float(row.get("stop_loss"), 0.0)
    take = _safe_float(row.get("take_profit"), 0.0)
    risk_amount = _safe_float(row.get("risk_amount"), 0.0)
    unrealized = _safe_float(row.get("unrealized_pnl"), 0.0)
    risk_multiple = row.get("risk_multiple_current")
    if risk_multiple is None and risk_amount > 0:
        risk_multiple = unrealized / risk_amount
    return {
        "cycle_id": str(row.get("cycle_id") or ""),
        "symbol": symbol,
        "side": side,
        "entry_price": entry,
        "current_price": current,
        "stop_loss": stop,
        "take_profit": take,
        "unrealized_pnl": unrealized,
        "risk_amount": risk_amount,
        "risk_multiple_current": _safe_float(risk_multiple, 0.0),
        "position_age_minutes": row.get("position_age_minutes"),
        "position_age_bars": row.get("position_age_bars"),
        "take_profit_hit_diagnostic": _safe_bool(row.get("take_profit_hit_diagnostic"), False),
        "stop_hit_diagnostic": _safe_bool(row.get("stop_hit_diagnostic"), False),
        "close_required_diagnostic": _safe_bool(row.get("close_required_diagnostic"), False),
        "source_report": source_report,
    }


def build_monitor_message(event: Mapping[str, Any], *, bar_width: int = 24) -> tuple[str, dict[str, Any]]:
    symbol = str(event.get("symbol") or "")
    side = str(event.get("side") or "").upper()
    entry = _safe_float(event.get("entry_price"), 0.0)
    current = _safe_float(event.get("current_price"), 0.0)
    stop = _safe_float(event.get("stop_loss"), 0.0)
    take = _safe_float(event.get("take_profit"), 0.0)
    pnl = _safe_float(event.get("unrealized_pnl"), 0.0)
    r_mult = _safe_float(event.get("risk_multiple_current"), 0.0)
    bar, progress, zone = progress_bar(side=side, current=current, stop_loss=stop, take_profit=take, width=bar_width)
    tp_hit = _safe_bool(event.get("take_profit_hit_diagnostic"), False)
    sl_hit = _safe_bool(event.get("stop_hit_diagnostic"), False)
    close_req = _safe_bool(event.get("close_required_diagnostic"), False)
    if tp_hit:
        status = "TAKE_PROFIT_HIT_DIAGNOSTIC"
    elif sl_hit:
        status = "STOP_LOSS_HIT_DIAGNOSTIC"
    elif close_req:
        status = "CLOSE_REQUIRED_DIAGNOSTIC"
    else:
        status = zone
    dist_sl = _pct_distance(current, stop)
    dist_tp = _pct_distance(current, take)
    progress_pct = None if progress is None else round(progress * 100.0, 2)
    text = "\n".join([
        "📍 LSR-v2 PAPER POSITION MONITOR",
        f"cycle={event.get('cycle_id') or ''}",
        f"symbol={symbol} side={side}",
        f"entry={_fmt_num(entry, 4)} current={_fmt_num(current, 4)}",
        f"SL={_fmt_num(stop, 4)} TP={_fmt_num(take, 4)}",
        bar,
        f"progress_to_TP={_fmt_num(progress_pct, 2) if progress_pct is not None else 'NA'}% status={status}",
        f"distance_to_SL={_fmt_num(dist_sl, 4) if dist_sl is not None else 'NA'}% distance_to_TP={_fmt_num(dist_tp, 4) if dist_tp is not None else 'NA'}%",
        f"unrealized_pnl={_fmt_num(pnl, 6)} R={_fmt_num(r_mult, 6)}",
    ])
    details = {
        "progress_to_tp_pct": progress_pct,
        "progress_zone": zone,
        "monitor_status": status,
        "distance_to_stop_pct": dist_sl,
        "distance_to_take_profit_pct": dist_tp,
        "bar": bar,
    }
    return text, details


def build_lsr_v2_position_monitor_notifications(data_dir: str | Path, *, bar_width: int = 24) -> tuple[list[LSRV2PositionMonitorNotification], dict[str, Any]]:
    base = Path(data_dir)
    notifications: list[LSRV2PositionMonitorNotification] = []
    guard = _stale_guard_context(data_dir)
    diagnostics: dict[str, Any] = {
        "source_reports": {},
        "open_position_candidate_count": 0,
        "stale_guard": guard,
        "stale_monitor_skipped_count": 0,
        "stale_monitor_skipped_reasons": [],
        "stale_monitor_skipped_keys": [],
    }
    seen: set[tuple[str, str, str]] = set()
    for source in MONITOR_SOURCES:
        report_name = str(source["report_name"])
        report = _read_json(base / report_name)
        diagnostics["source_reports"][report_name] = {
            "present": bool(report),
            "status": str(report.get("status") or "") if report else "",
            "decision": str(report.get("decision") or "") if report else "",
            "open_positions": _safe_int(report.get("open_lsr_v2_position_count") or report.get("open_second_lsr_v2_position_count"), 0) if report else 0,
        }
        events = _latest_monitor_events(data_dir, source)
        if not events:
            events = _events_from_report(report, source)
        for raw_event in events:
            event = _normalise_monitor_event(raw_event, source_report=report_name)
            if not event.get("symbol") or _safe_float(event.get("current_price"), 0.0) <= 0:
                continue
            is_stale, stale_reason = _is_monitor_event_stale(event, guard)
            if is_stale:
                diagnostics["stale_monitor_skipped_count"] = _safe_int(diagnostics.get("stale_monitor_skipped_count"), 0) + 1
                reasons = list(diagnostics.get("stale_monitor_skipped_reasons") or [])
                reasons.append(stale_reason)
                diagnostics["stale_monitor_skipped_reasons"] = sorted(set(str(x) for x in reasons if str(x)))
                stale_keys = list(diagnostics.get("stale_monitor_skipped_keys") or [])
                stale_keys.append(f"{event.get('cycle_id') or ''}:{event.get('symbol') or ''}:{stale_reason}")
                diagnostics["stale_monitor_skipped_keys"] = stale_keys
                continue
            cycle_id = str(event.get("cycle_id") or "")
            symbol = str(event.get("symbol") or "")
            current_key = f"{_safe_float(event.get('current_price'), 0.0):.4f}"
            dedupe_key = (cycle_id, symbol, current_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            text, details = build_monitor_message(event, bar_width=bar_width)
            status = str(details.get("monitor_status") or "")
            key = f"position_monitor:{cycle_id}:{symbol}:{current_key}:{status}"
            notifications.append(LSRV2PositionMonitorNotification(
                key=key,
                kind="OPEN_POSITION_MONITOR",
                text=text,
                source_report=report_name,
                cycle_id=cycle_id,
                symbol=symbol,
            ))
    diagnostics["open_position_candidate_count"] = len(notifications)
    return notifications, diagnostics


async def _send_telegram_text_via_aiohttp(*, token: str, chat_id: str, text: str) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text[:3900]}
    try:
        async with aiohttp.ClientSession() as session:  # type: ignore[union-attr]
            async with session.post(url, json=payload, timeout=8) as resp:
                try:
                    parsed = await resp.json()
                except Exception:
                    parsed = {"raw": await resp.text()}
        return {"ok": bool(parsed.get("ok", False)), "response": parsed}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "error_type": exc.__class__.__name__}


def send_telegram_text_via_http(*, token: str, chat_id: str, text: str) -> dict[str, Any]:
    if not token or not chat_id:
        return {"ok": False, "error": "telegram_config_missing"}
    if aiohttp is not None:
        return asyncio.run(_send_telegram_text_via_aiohttp(token=token, chat_id=chat_id, text=text))
    url = f"https://api.telegram.org/bot{urllib.parse.quote(token, safe='')}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text[:3900]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 - operator configured Telegram endpoint
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"raw": raw}
        return {"ok": bool(parsed.get("ok", False)), "response": parsed}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": str(exc), "error_type": exc.__class__.__name__}
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        return {"ok": False, "error": str(exc), "error_type": exc.__class__.__name__}


def _default_sender(settings: LSRV2TelegramPositionMonitorBridgeSettings) -> Sender:
    def sender(text: str) -> Mapping[str, Any]:
        return send_telegram_text_via_http(token=settings.telegram_token, chat_id=settings.telegram_chat_id, text=text)
    return sender


def run_lsr_v2_telegram_position_monitor_bridge(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2TelegramPositionMonitorBridgeSettings | None = None,
    sender: Sender | None = None,
) -> dict[str, Any]:
    settings = settings or LSRV2TelegramPositionMonitorBridgeSettings.from_env(data_dir=str(data_dir))
    base = Path(data_dir)
    notifications, diagnostics = build_lsr_v2_position_monitor_notifications(data_dir, bar_width=settings.bar_width)
    state_path = base / settings.state_name
    state = _load_state(state_path)
    sent_before = _state_sent_keys(state)

    selected: list[LSRV2PositionMonitorNotification] = []
    skipped_duplicates: list[str] = []
    for item in notifications:
        if item.key in sent_before and not settings.force_resend:
            skipped_duplicates.append(item.key)
            continue
        selected.append(item)
    selected = selected[: max(0, int(settings.max_messages))]

    blockers: list[str] = []
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")
    if settings.send_enabled and not settings.send_confirmation_ok:
        blockers.append("send_confirmation_missing")
    if settings.send_enabled and settings.send_confirmation_ok and not settings.telegram_configured:
        blockers.append("telegram_config_missing")

    send_attempted = 0
    send_ok = 0
    send_failed = 0
    sent_keys_now: list[str] = []
    rows: list[dict[str, Any]] = []
    selected_sender = sender or _default_sender(settings)

    actual_send_allowed = settings.actual_send_allowed and not blockers
    for item in selected:
        result: Mapping[str, Any] | bool | None = None
        ok = False
        if actual_send_allowed:
            send_attempted += 1
            try:
                result = selected_sender(item.text)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                result = {"ok": False, "error": str(exc), "error_type": exc.__class__.__name__}
            ok = bool(result.get("ok", False)) if isinstance(result, Mapping) else bool(result)
            if ok:
                send_ok += 1
                sent_keys_now.append(item.key)
            else:
                send_failed += 1
        row = {
            "event_type": EVENT_TYPE,
            "prompt_id": PROMPT_ID,
            "created_at": utc_now_iso(),
            "notification_key": item.key,
            "notification_kind": item.kind,
            "cycle_id": item.cycle_id,
            "symbol": item.symbol,
            "source_report": item.source_report,
            "telegram_send_attempted": bool(actual_send_allowed),
            "telegram_send_ok": bool(ok),
            "telegram_result": result if isinstance(result, Mapping) else {"ok": bool(result)},
            "message_text": item.text,
            "orders_submitted_by_position_monitor_bridge": 0,
            "positions_opened_by_position_monitor_bridge": 0,
            "positions_closed_by_position_monitor_bridge": 0,
            "broker_submit_called_by_position_monitor_bridge": False,
            "broker_close_called_by_position_monitor_bridge": False,
            "paper_state_modified_by_position_monitor_bridge": False,
            "paper_status_modified_by_position_monitor_bridge": False,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
            "operational_unlock_allowed": False,
        }
        rows.append(row)
        _append_jsonl(base / settings.telegram_audit_name, row)

    _write_jsonl_replace(base / settings.jsonl_name, rows)
    if sent_keys_now:
        _update_state(state_path, sent_keys=sent_keys_now)

    safety_violation = any(
        _safe_int(row.get("orders_submitted_by_position_monitor_bridge"), 0) > 0
        or _safe_int(row.get("positions_opened_by_position_monitor_bridge"), 0) > 0
        or _safe_int(row.get("positions_closed_by_position_monitor_bridge"), 0) > 0
        or _safe_bool(row.get("broker_submit_called_by_position_monitor_bridge"), False)
        or _safe_bool(row.get("broker_close_called_by_position_monitor_bridge"), False)
        or _safe_bool(row.get("live_enabled"), False)
        or _safe_bool(row.get("testnet_enabled"), False)
        or _safe_bool(row.get("exchange_broker_enabled"), False)
        or _safe_bool(row.get("operational_unlock_allowed"), False)
        for row in rows
    )
    if safety_violation:
        blockers.append("position_monitor_bridge_safety_violation")

    if safety_violation:
        decision = REJECT_DECISION
        status = "FAIL"
    elif not notifications:
        decision = NO_OPEN_POSITION_DECISION
        status = "PASS"
    elif settings.send_enabled and settings.send_confirmation_ok and not settings.telegram_configured:
        decision = CONFIG_MISSING_DECISION
        status = "WARN"
    elif not settings.send_enabled:
        decision = DRY_RUN_DECISION
        status = "PASS"
    elif send_failed and send_ok:
        decision = PARTIAL_DECISION
        status = "WARN"
    elif send_failed:
        decision = PARTIAL_DECISION
        status = "WARN"
    elif send_ok:
        decision = SENT_DECISION
        status = "PASS"
    else:
        decision = DRY_RUN_DECISION if notifications else NO_OPEN_POSITION_DECISION
        status = "PASS"

    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_TELEGRAM_POSITION_MONITOR_BRIDGE",
            "OBSERVABILITY_ONLY",
            "NO_TRADING_SIDE_EFFECTS",
        ] + (["NO_OPEN_POSITION"] if not notifications else ["TELEGRAM_POSITION_MONITOR"]),
        "blockers": sorted(set(blockers)),
        "settings": settings.to_dict(),
        "source_report_diagnostics": diagnostics.get("source_reports", {}),
        "stale_guard": diagnostics.get("stale_guard", {}),
        "stale_monitor_skipped_count": _safe_int(diagnostics.get("stale_monitor_skipped_count"), 0),
        "stale_monitor_skipped_reasons": list(diagnostics.get("stale_monitor_skipped_reasons") or []),
        "stale_monitor_skipped_keys": list(diagnostics.get("stale_monitor_skipped_keys") or []),
        "open_position_candidate_count": len(notifications),
        "notification_selected_count": len(selected),
        "notification_duplicate_skipped_count": len(skipped_duplicates),
        "notification_duplicate_skipped_keys": skipped_duplicates,
        "notification_keys": [item.key for item in selected],
        "notification_symbols": [item.symbol for item in selected],
        "send_enabled": bool(settings.send_enabled),
        "send_confirmation_ok": bool(settings.send_confirmation_ok),
        "telegram_configured": bool(settings.telegram_configured),
        "actual_send_allowed": bool(actual_send_allowed),
        "force_resend": bool(settings.force_resend),
        "max_messages": int(settings.max_messages),
        "bar_width": int(settings.bar_width),
        "telegram_send_attempted_count": int(send_attempted),
        "telegram_send_ok_count": int(send_ok),
        "telegram_send_failed_count": int(send_failed),
        "orders_submitted_by_position_monitor_bridge": 0,
        "positions_opened_by_position_monitor_bridge": 0,
        "positions_closed_by_position_monitor_bridge": 0,
        "broker_submit_called_by_position_monitor_bridge": False,
        "broker_close_called_by_position_monitor_bridge": False,
        "paper_state_modified_by_position_monitor_bridge": False,
        "paper_status_modified_by_position_monitor_bridge": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "state_path": str(state_path),
        "telegram_audit_path": str(base / settings.telegram_audit_name),
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
