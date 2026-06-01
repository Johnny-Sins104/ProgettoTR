from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.edge_strategy_discovery import (
    EdgeDiscoverySettings,
    build_edge_strategy_discovery_report,
    run_backtest_matrix,
)


def _parse_windows(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part.endswith("k"):
            out.append(int(float(part[:-1]) * 1000))
        else:
            out.append(int(float(part)))
    return tuple(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt 29.4.4s-3 edge strategy discovery + breakeven drag pruning")
    parser.add_argument("--run-backtests", action="store_true", help="Run the configured backtest matrix before analysis")
    parser.add_argument("--windows", default="10000,12000,15000,18000,20000", help="Comma-separated candles/windows")
    parser.add_argument("--balance", type=float, default=100.0)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--min-windows", type=int, default=3)
    parser.add_argument("--min-positive-windows", type=int, default=3)
    parser.add_argument("--min-total-trades", type=int, default=20)
    parser.add_argument("--min-window-trades", type=int, default=3)
    parser.add_argument("--min-weighted-avg-r", type=float, default=0.05)
    parser.add_argument("--max-negative-window-avg-r", type=float, default=-0.10)
    parser.add_argument("--max-breakeven-drag-ratio", type=float, default=0.45)
    parser.add_argument("--max-breakeven-drag-avg-r", type=float, default=0.0)
    parser.add_argument("--min-prune-trades", type=int, default=20)
    args = parser.parse_args()

    windows = _parse_windows(args.windows)
    labels = tuple(f"{w // 1000}k" if w % 1000 == 0 else str(w) for w in windows)
    settings = EdgeDiscoverySettings(
        labels=labels,
        candle_windows=windows,
        balance=args.balance,
        timeout_seconds=args.timeout_seconds,
        min_windows=args.min_windows,
        min_positive_windows=args.min_positive_windows,
        min_total_trades=args.min_total_trades,
        min_window_trades=args.min_window_trades,
        min_weighted_avg_r=args.min_weighted_avg_r,
        max_negative_window_avg_r=args.max_negative_window_avg_r,
        max_breakeven_drag_ratio=args.max_breakeven_drag_ratio,
        max_breakeven_drag_avg_r=args.max_breakeven_drag_avg_r,
        min_prune_trades=args.min_prune_trades,
    )
    if args.run_backtests:
        report = run_backtest_matrix(settings, project_root=ROOT)
    else:
        report = build_edge_strategy_discovery_report(settings)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
