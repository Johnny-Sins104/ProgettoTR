from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SUMMARY: dict[str, Any] = {
    "report_type": "clean_bot_frequency_audit",
    "diagnostic_only": True,
    "target": "3-4 trades/day without historical loss after realistic costs",
    "target_status": "NOT_FOUND_ON_AVAILABLE_5M_DATA",
    "available_data": "5m OHLCV caches for BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT",
    "tested_families": [
        "short breakout long-only",
        "short breakout long/short paper-style",
        "RSI/Bollinger mean reversion long-only",
        "RSI/Bollinger mean reversion long/short paper-style",
        "EMA pullback long-only",
        "EMA pullback long/short paper-style",
        "simple ML return filter trained on first half and validated on second half",
        "multi-asset active trend breakout",
    ],
    "accepted_profiles": {
        "conservative": {
            "symbol": "XRP/USDT",
            "trades": 126,
            "estimated_trades_per_month": 7.4,
            "return_pct": 77.43,
            "profit_factor": 1.63,
            "max_drawdown_pct": 12.81,
        },
        "active": {
            "symbol": "XRP/USDT",
            "trades": 224,
            "estimated_trades_per_month": 13.0,
            "return_pct": 66.16,
            "profit_factor": 1.33,
            "max_drawdown_pct": 18.31,
        },
        "aggressive": {
            "symbol": "XRP/USDT",
            "status": "paper_observation_only",
            "trades": 250,
            "estimated_trades_per_month": 14.5,
            "return_pct": 71.01,
            "profit_factor": 1.31,
            "max_drawdown_pct": 26.35,
            "severe_cost_return_pct": 20.34,
            "severe_cost_profit_factor": 1.09,
            "severe_cost_max_drawdown_pct": 34.07,
            "rationale": "Higher frequency than active by using a tighter 3 ATR stop; drawdown is materially higher.",
        },
    },
    "rejected_findings": [
        "Profiles near 35-40 trades/month on XRP were historically negative after 13 bps round-trip costs.",
        "Short-horizon ML filters looked profitable in the training half but were negative in the second half.",
        "Adding BTC, SOL, or BNB to the active profile increased trade count but degraded portfolio expectancy.",
        "ETH active was close to flat, but too weak to add as a frequency booster.",
    ],
    "next_data_needed_for_true_scalping": [
        "1m or tick/order-book data",
        "maker/taker fee model",
        "spread and slippage model",
        "latency/partial-fill assumptions",
    ],
}


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "CLEAN BOT FREQUENCY AUDIT",
        f"target={report['target']}",
        f"target_status={report['target_status']}",
        "",
        "accepted_profiles:",
    ]
    for name, row in report["accepted_profiles"].items():
        if "severe_cost_profit_factor" in row:
            lines.append(
                f"  {name}: {row['symbol']} {row['status']} trades={row['trades']} "
                f"est_month={row['estimated_trades_per_month']} return={row['return_pct']:+.2f}% "
                f"pf={row['profit_factor']:.2f} dd={row['max_drawdown_pct']:.2f}% "
                f"severe_pf={row['severe_cost_profit_factor']:.2f}"
            )
        else:
            lines.append(
                f"  {name}: {row['symbol']} trades={row['trades']} "
                f"est_month={row['estimated_trades_per_month']} return={row['return_pct']:+.2f}% "
                f"pf={row['profit_factor']:.2f} dd={row['max_drawdown_pct']:.2f}%"
            )
    lines.append("")
    lines.append("rejected_findings:")
    for item in report["rejected_findings"]:
        lines.append(f"  - {item}")
    lines.append("")
    lines.append("next_data_needed_for_true_scalping:")
    for item in report["next_data_needed_for_true_scalping"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize clean bot high-frequency strategy audit.")
    parser.add_argument("--output", default="data/clean_bot_frequency_audit.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(SUMMARY, indent=2, sort_keys=True), encoding="utf-8")
    if args.json:
        print(json.dumps(SUMMARY, indent=2, sort_keys=True))
    else:
        print(format_report(SUMMARY))
        print(f"report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
