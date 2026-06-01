"""Prompt 29.4.4s-5 equity forensics from trade-level telemetry.

Reads the diagnostic trade-level JSONL export and derives an equity/drawdown
view suitable for research.  No runtime gate, broker, order, or paper state is
changed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import math

from core.jsonl_utils import iter_jsonl_tail
from core.trade_level_telemetry import TRADE_JSONL_NAME, _safe_float

PROMPT_ID = "29.4.4s-5"
EQUITY_REPORT_NAME = "equity_forensics_report.json"
READY_DECISION = "EQUITY_FORENSICS_READY_DIAGNOSTIC"
NO_TELEMETRY_DECISION = "KEEP_DIAGNOSTIC_NO_TRADE_LEVEL_TELEMETRY"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@dataclass(frozen=True)
class EquityForensicsSettings:
    data_dir: str = "data"
    trade_jsonl_name: str = TRADE_JSONL_NAME
    report_name: str = EQUITY_REPORT_NAME
    starting_equity: float = 1000.0
    max_trade_lines: int = 250000

    @classmethod
    def default(cls) -> "EquityForensicsSettings":
        return cls()


def _closed_trade_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    closed = [r for r in rows if r.get("row_type") == "closed_trade"]
    return sorted(closed, key=lambda r: str(r.get("closed_at") or r.get("source_event_ts") or ""))


def build_equity_curve(rows: list[dict[str, Any]], *, starting_equity: float = 1000.0) -> list[dict[str, Any]]:
    equity = float(starting_equity)
    peak = equity
    curve: list[dict[str, Any]] = []
    for idx, row in enumerate(_closed_trade_rows(rows), start=1):
        pnl = _safe_float(row.get("net_pnl"), 0.0)
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(0.0, peak - equity)
        drawdown_pct = drawdown / peak * 100.0 if peak > 0 else 0.0
        curve.append({
            "trade_index": idx,
            "closed_at": row.get("closed_at") or row.get("source_event_ts"),
            "position_id": row.get("position_id"),
            "symbol": row.get("symbol"),
            "side": row.get("side"),
            "archetype": row.get("archetype"),
            "net_pnl": round(pnl, 8),
            "r_multiple": row.get("r_multiple"),
            "equity": round(equity, 8),
            "peak_equity": round(peak, 8),
            "drawdown": round(drawdown, 8),
            "drawdown_pct": round(drawdown_pct, 8),
        })
    return curve


def _streaks(curve: list[dict[str, Any]]) -> dict[str, Any]:
    max_win = 0
    max_loss = 0
    cur_win = 0
    cur_loss = 0
    for row in curve:
        pnl = _safe_float(row.get("net_pnl"), 0.0)
        if pnl > 0:
            cur_win += 1
            cur_loss = 0
        elif pnl < 0:
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = 0
            cur_loss = 0
        max_win = max(max_win, cur_win)
        max_loss = max(max_loss, cur_loss)
    return {"max_win_streak": max_win, "max_loss_streak": max_loss}


def build_equity_forensics_report(
    rows: list[dict[str, Any]],
    *,
    settings: EquityForensicsSettings | None = None,
) -> dict[str, Any]:
    settings = settings or EquityForensicsSettings.default()
    curve = build_equity_curve(rows, starting_equity=settings.starting_equity)
    closed_count = len(curve)
    final_equity = curve[-1]["equity"] if curve else float(settings.starting_equity)
    max_dd_pct = max((_safe_float(r.get("drawdown_pct"), 0.0) for r in curve), default=0.0)
    max_dd_abs = max((_safe_float(r.get("drawdown"), 0.0) for r in curve), default=0.0)
    pnl_values = [_safe_float(r.get("net_pnl"), 0.0) for r in curve]
    total_pnl = sum(pnl_values)
    abs_pnls = sorted((abs(x) for x in pnl_values), reverse=True)
    top_10_count = max(1, int(math.ceil(len(abs_pnls) * 0.10))) if abs_pnls else 0
    top_10_sum = sum(abs_pnls[:top_10_count]) if abs_pnls else 0.0
    total_abs = sum(abs_pnls)
    top_10_concentration = top_10_sum / total_abs if total_abs > 0 else 0.0
    return {
        "prompt": PROMPT_ID,
        "status": "PASS" if rows or closed_count == 0 else "WARN",
        "decision": READY_DECISION,
        "ts": utc_now_iso(),
        "data_dir": settings.data_dir,
        "trade_jsonl": str(Path(settings.data_dir) / settings.trade_jsonl_name),
        "report": str(Path(settings.data_dir) / settings.report_name),
        "settings": asdict(settings),
        "closed_trades": closed_count,
        "starting_equity": round(float(settings.starting_equity), 8),
        "final_equity": round(float(final_equity), 8),
        "net_pnl": round(total_pnl, 8),
        "net_return_pct": round((final_equity - settings.starting_equity) / settings.starting_equity * 100.0, 8) if settings.starting_equity > 0 else None,
        "max_drawdown": round(max_dd_abs, 8),
        "max_drawdown_pct": round(max_dd_pct, 8),
        "top_10_abs_pnl_concentration": round(top_10_concentration, 8),
        "streaks": _streaks(curve),
        "equity_curve": curve,
        "promotion_ready": False,
        "promotion_blockers": [
            "equity_forensics_is_diagnostic_only",
            "requires_lsr_v2_or_strategy_specific_multi_window_oos_validation",
        ],
        "safety_note": (
            "Diagnostic only: derives equity/drawdown from exported rows. It does not mutate paper state, "
            "route signals, call brokers, submit orders, open positions, or enable live/testnet/exchange broker."
        ),
    }


def write_equity_forensics_report(settings: EquityForensicsSettings | None = None) -> dict[str, Any]:
    settings = settings or EquityForensicsSettings.default()
    data_dir = Path(settings.data_dir)
    trade_jsonl = data_dir / settings.trade_jsonl_name
    if not trade_jsonl.exists():
        report = {
            "prompt": PROMPT_ID,
            "status": "WARN",
            "decision": NO_TELEMETRY_DECISION,
            "ts": utc_now_iso(),
            "data_dir": str(data_dir),
            "trade_jsonl": str(trade_jsonl),
            "report": str(data_dir / settings.report_name),
            "closed_trades": 0,
            "promotion_ready": False,
            "orders_submitted_by_equity_forensics": 0,
            "positions_opened_by_equity_forensics": 0,
            "safety_note": "Diagnostic only; no broker/order/position state is changed.",
        }
        _write_json(data_dir / settings.report_name, report)
        return report
    rows = iter_jsonl_tail(trade_jsonl, max_lines=settings.max_trade_lines, require_event_type=False)
    report = build_equity_forensics_report(rows, settings=settings)
    report["orders_submitted_by_equity_forensics"] = 0
    report["positions_opened_by_equity_forensics"] = 0
    _write_json(data_dir / settings.report_name, report)
    return report
