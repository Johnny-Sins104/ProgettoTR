from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.clean_bot.backtest import run_backtest
from trading_bot.clean_bot.models import BacktestSettings
from trading_bot.clean_bot.strategies import strategy_profile


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _fmt_float(value: Any, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "-"


def format_report(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    pf = metrics.get("profit_factor")
    pf_text = "-" if pf is None else _fmt_float(pf)
    profile = report.get("profile", "-")
    lines = [
        "CLEAN BOT BACKTEST",
        f"symbol={report['settings']['symbol']} timeframe={report['settings']['timeframe']} cost={report['settings']['cost_model']} profile={profile}",
        f"starting_balance={_fmt_float(report['settings']['starting_balance'])} risk_per_trade={float(report['settings']['risk_per_trade_pct']) * 100:.2f}%",
        f"rows_loaded={report['rows_loaded']} rows_tested={report['rows_tested']}",
        f"closed_trades={metrics['closed_trades']} wins={metrics['wins']} losses={metrics['losses']} win_rate={metrics['win_rate_pct']:.2f}%",
        f"net_pnl={metrics['net_pnl']:+.2f} return={metrics['return_pct']:+.2f}% ending_balance={metrics['ending_balance']:.2f}",
        f"profit_factor={pf_text} average_r={metrics['average_r']:+.2f} max_drawdown={metrics['max_drawdown_pct']:.2f}%",
        "",
        "by_strategy:",
    ]
    for name, row in sorted(metrics["by_strategy"].items()):
        lines.append(
            f"  {name}: trades={row['trades']} pnl={row['pnl']:+.2f} "
            f"win_rate={row.get('win_rate_pct', 0.0):.2f}% avg_r={row.get('avg_r', 0.0):+.2f}"
        )
    lines.append("")
    lines.append("last_trades:")
    for trade in report["trades"][-10:]:
        lines.append(
            f"  {trade['strategy']} {trade['side']} {trade['exit_reason']} "
            f"entry={trade['entry_price']:.4f} exit={trade['exit_price']:.4f} pnl={trade['net_pnl']:+.2f} R={trade['r_multiple']:+.2f}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run clean bot shadow/backtest laboratory.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--balance", type=float, default=100.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    parser.add_argument("--cost-model", choices=["base", "conservative", "severe"], default="conservative")
    parser.add_argument("--profile", choices=["active", "aggressive", "conservative"], default="conservative")
    parser.add_argument("--max-rows", type=int, default=50000)
    parser.add_argument("--max-hold-bars", type=int, default=36)
    parser.add_argument("--output", default="data/clean_bot_backtest_report.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    settings = BacktestSettings(
        symbol=args.symbol,
        timeframe=args.timeframe,
        starting_balance=args.balance,
        risk_per_trade_pct=args.risk_per_trade_pct,
        cost_model=args.cost_model,
        max_rows=args.max_rows,
        max_hold_bars=args.max_hold_bars,
    )
    report = run_backtest(data_dir=Path(args.data_dir), settings=settings, strategies=strategy_profile(args.profile))
    report["profile"] = args.profile
    _write_json(Path(args.output), report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
        print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
