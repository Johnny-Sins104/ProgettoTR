from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


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


def _positions(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw = state.get("positions")
    if isinstance(raw, dict):
        rows = [p for p in raw.values() if isinstance(p, dict)]
    elif isinstance(raw, list):
        rows = [p for p in raw if isinstance(p, dict)]
    else:
        rows = []
    return sorted(rows, key=lambda p: str(p.get("closed_at") or p.get("opened_at") or ""))


def _risk_amount(position: dict[str, Any]) -> float:
    metadata = position.get("metadata") if isinstance(position.get("metadata"), dict) else {}
    risk = _safe_float(metadata.get("risk_amount"), 0.0)
    if risk > 0:
        return risk
    entry = _safe_float(position.get("entry_price"))
    stop = _safe_float(position.get("stop_loss"))
    qty = abs(_safe_float(position.get("qty")))
    return abs(entry - stop) * qty


def _bucket(position: dict[str, Any]) -> str:
    metadata = position.get("metadata") if isinstance(position.get("metadata"), dict) else {}
    source = str(metadata.get("execution_source") or metadata.get("paper_order_source") or "")
    candidate = str(metadata.get("candidate_id") or "")
    reason = str(position.get("close_reason") or "")
    if source == "lsr_v2_paper_supervised_runtime_bridge":
        return "paper_live_runtime"
    if reason == "SWITCH_TO_PAPER_LIVE":
        return "neutral_switch"
    if "2024-" in candidate or _safe_float(position.get("entry_price")) > 90000:
        return "replay_or_legacy"
    return "paper_other"


def build_report(data_dir: Path) -> dict[str, Any]:
    state = _read_json(data_dir / "paper_state.json")
    closed = [p for p in _positions(state) if str(p.get("status") or "").upper() == "CLOSED"]
    open_positions = [p for p in _positions(state) if str(p.get("status") or "").upper() == "OPEN"]
    rows: list[dict[str, Any]] = []
    for p in closed:
        pnl = _safe_float(p.get("realized_pnl"))
        risk = _risk_amount(p)
        rows.append({
            "position_id": p.get("position_id"),
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "opened_at": p.get("opened_at"),
            "closed_at": p.get("closed_at"),
            "entry_price": _safe_float(p.get("entry_price")),
            "exit_price": _safe_float(p.get("exit_price")),
            "close_reason": str(p.get("close_reason") or "UNKNOWN"),
            "realized_pnl": pnl,
            "risk_amount": risk,
            "r_multiple": pnl / risk if risk > 0 else 0.0,
            "bucket": _bucket(p),
        })
    gross_profit = sum(r["realized_pnl"] for r in rows if r["realized_pnl"] > 0)
    gross_loss = abs(sum(r["realized_pnl"] for r in rows if r["realized_pnl"] < 0))
    wins = [r for r in rows if r["realized_pnl"] > 0]
    losses = [r for r in rows if r["realized_pnl"] < 0]
    by_reason: dict[str, int] = {}
    by_bucket: dict[str, dict[str, Any]] = {}
    equity = _safe_float(state.get("initial_balance"), 1000.0)
    peak = equity
    max_drawdown = 0.0
    for r in rows:
        by_reason[r["close_reason"]] = by_reason.get(r["close_reason"], 0) + 1
        bucket = by_bucket.setdefault(r["bucket"], {"trades": 0, "pnl": 0.0, "wins": 0, "losses": 0})
        bucket["trades"] += 1
        bucket["pnl"] += r["realized_pnl"]
        bucket["wins"] += int(r["realized_pnl"] > 0)
        bucket["losses"] += int(r["realized_pnl"] < 0)
        equity += r["realized_pnl"]
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * 100.0)
    return {
        "initial_balance": _safe_float(state.get("initial_balance"), 1000.0),
        "current_balance": _safe_float(state.get("balance")),
        "state_realized_pnl": _safe_float(state.get("realized_pnl")),
        "closed_trades": len(rows),
        "open_trades": len(open_positions),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len([r for r in rows if r["realized_pnl"] == 0]),
        "win_rate_pct": (len(wins) / len(rows) * 100.0) if rows else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "expectancy": sum(r["realized_pnl"] for r in rows) / len(rows) if rows else 0.0,
        "average_r": sum(r["r_multiple"] for r in rows) / len(rows) if rows else 0.0,
        "max_drawdown_pct_from_trade_sequence": max_drawdown,
        "close_reasons": by_reason,
        "buckets": by_bucket,
        "kill_switch": bool(state.get("kill_switch")),
        "is_paused": bool(state.get("is_paused")),
        "trades": rows,
    }


def format_report(report: dict[str, Any]) -> str:
    pf = report.get("profit_factor")
    pf_label = "-" if pf is None else f"{float(pf):.2f}"
    lines = [
        "PAPER PERFORMANCE REPORT",
        f"closed_trades={report['closed_trades']}",
        f"open_trades={report['open_trades']}",
        f"wins={report['wins']} losses={report['losses']} breakeven={report['breakeven']}",
        f"win_rate={report['win_rate_pct']:.2f}%",
        f"gross_profit={report['gross_profit']:+.2f}",
        f"gross_loss={report['gross_loss']:.2f}",
        f"profit_factor={pf_label}",
        f"expectancy={report['expectancy']:+.2f}",
        f"average_r={report['average_r']:+.2f}",
        f"max_drawdown_trade_seq={report['max_drawdown_pct_from_trade_sequence']:.2f}%",
        f"state_realized_pnl={report['state_realized_pnl']:+.2f}",
        f"current_balance={report['current_balance']:.2f}",
        f"kill_switch={report['kill_switch']} is_paused={report['is_paused']}",
        "",
        "close_reasons:",
    ]
    for key, value in sorted(report["close_reasons"].items()):
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("buckets:")
    for key, value in sorted(report["buckets"].items()):
        lines.append(
            f"  {key}: trades={value['trades']} pnl={value['pnl']:+.2f} wins={value['wins']} losses={value['losses']}"
        )
    lines.append("")
    lines.append("trades:")
    for r in report["trades"][-20:]:
        lines.append(
            f"  {r['position_id']} {r['symbol']} {r['side']} {r['close_reason']} "
            f"pnl={r['realized_pnl']:+.2f} R={r['r_multiple']:+.2f} bucket={r['bucket']}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize paper trading performance.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    args = parser.parse_args()
    report = build_report(Path(args.data_dir))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
