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

from core.lsr_v2_backtest_matrix import LSRV2BacktestSettings, parse_windows, run_lsr_v2_backtest_matrix


def _parse_cost_models(raw: str) -> tuple[str, ...]:
    vals = [x.strip().lower() for x in str(raw or "").split(",") if x.strip()]
    return tuple(vals) or ("base", "conservative", "severe")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt 29.4.4s-7 LSR-v2 backtest matrix / cost stress grid")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--input-path", default=None)
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--max-rows", type=int, default=250000)
    parser.add_argument("--windows", default="10000,12000,15000,18000,20000,30000,50000")
    parser.add_argument("--cost-models", default="base,conservative,severe")
    parser.add_argument("--max-holding-bars", type=int, default=48)
    parser.add_argument("--starting-equity", type=float, default=1000.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.0025)
    parser.add_argument("--allow-overlap", action="store_true", help="Allow overlapping simulated trades. Default is one-position-at-time diagnostic simulation.")
    parser.add_argument("--allow-timeframe-fallback", action="store_true")
    parser.add_argument("--no-strict-timeframe", action="store_true")
    parser.add_argument("--pool-lookback", type=int, default=20)
    parser.add_argument("--confirmation-window", type=int, default=4)
    parser.add_argument("--retest-window", type=int, default=6)
    parser.add_argument("--min-sweep-bps", type=float, default=2.0)
    parser.add_argument("--retest-tolerance-bps", type=float, default=8.0)
    parser.add_argument("--stop-buffer-bps", type=float, default=2.0)
    parser.add_argument("--target-rr", type=float, default=2.0)
    parser.add_argument("--min-rr", type=float, default=1.5)
    parser.add_argument("--max-cost-to-r", type=float, default=0.35)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--min-positive-windows", type=int, default=3)
    parser.add_argument("--require-volume-confirmation", action="store_true")
    args = parser.parse_args()

    windows = parse_windows(args.windows)
    settings = LSRV2BacktestSettings(
        data_dir=args.data_dir,
        input_path=args.input_path,
        symbol=args.symbol,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
        windows=windows,
        primary_windows=tuple(w for w in windows if w in (10000, 12000, 15000, 18000, 20000)) or windows[:5],
        cost_models=_parse_cost_models(args.cost_models),
        max_holding_bars=args.max_holding_bars,
        starting_equity=args.starting_equity,
        risk_per_trade_pct=args.risk_per_trade_pct,
        one_position_at_time=not bool(args.allow_overlap),
        strict_timeframe=not bool(args.no_strict_timeframe),
        allow_timeframe_fallback=bool(args.allow_timeframe_fallback),
        pool_lookback=args.pool_lookback,
        confirmation_window=args.confirmation_window,
        retest_window=args.retest_window,
        min_sweep_bps=args.min_sweep_bps,
        retest_tolerance_bps=args.retest_tolerance_bps,
        stop_buffer_bps=args.stop_buffer_bps,
        target_rr=args.target_rr,
        min_rr=args.min_rr,
        max_cost_to_r=args.max_cost_to_r,
        min_closed_trades=args.min_closed_trades,
        min_positive_windows=args.min_positive_windows,
        require_volume_confirmation=bool(args.require_volume_confirmation),
    )
    report = run_lsr_v2_backtest_matrix(settings)
    criteria = report.get("criteria") if isinstance(report.get("criteria"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "input_rows": report.get("input_rows"),
        "input_path": report.get("input_path"),
        "requested_timeframe": report.get("requested_timeframe"),
        "detected_timeframe": report.get("detected_timeframe"),
        "timeframe_match": report.get("timeframe_match"),
        "windows": report.get("windows"),
        "total_simulated_trade_rows": report.get("total_simulated_trade_rows", 0),
        "primary_cost_model": criteria.get("primary_cost_model"),
        "closed_trades": criteria.get("closed_trades", 0),
        "positive_windows": criteria.get("positive_windows", 0),
        "weighted_avg_r_post_cost": criteria.get("weighted_avg_r_post_cost"),
        "net_sum_r_post_cost": criteria.get("net_sum_r_post_cost"),
        "severe_cost_survival": criteria.get("severe_cost_survival"),
        "research_ready": criteria.get("research_ready", False),
        "blockers": criteria.get("blockers", []),
        "orders_submitted_by_lsr_v2_backtest": report.get("orders_submitted_by_lsr_v2_backtest", 0),
        "positions_opened_by_lsr_v2_backtest": report.get("positions_opened_by_lsr_v2_backtest", 0),
        "promotion_ready": report.get("promotion_ready", False),
        "report": report.get("report"),
        "cost_stress_report": report.get("cost_stress_report"),
        "trade_files": report.get("trade_files", {}),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
