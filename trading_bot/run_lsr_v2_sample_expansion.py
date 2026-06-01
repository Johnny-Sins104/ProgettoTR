#!/usr/bin/env python3
"""Run Prompt 29.4.4s-7e LSR-v2 sample expansion audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lsr_v2_backtest_matrix import parse_windows  # noqa: E402
from core.lsr_v2_sample_expansion import (  # noqa: E402
    LSRV2SampleExpansionSettings,
    parse_symbols,
    parse_timeframes,
    run_lsr_v2_sample_expansion,
)


def _parse_costs(raw: str) -> tuple[str, ...]:
    out = []
    for token in str(raw or "").split(","):
        token = token.strip().lower()
        if token:
            out.append(token)
    return tuple(dict.fromkeys(out)) or ("base", "conservative", "severe")


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 sample expansion / data horizon robustness audit (diagnostic-only)")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--input-path", default=None)
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT")
    parser.add_argument("--timeframes", default="5m,15m")
    parser.add_argument("--windows", default="10k,12k,15k,18k,20k,30k,50k,100k,150k")
    parser.add_argument("--cost-models", default="base,conservative,severe")
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--max-rows", type=int, default=250000)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--preferred-closed-trades", type=int, default=50)
    parser.add_argument("--min-positive-windows", type=int, default=3)
    parser.add_argument("--min-severe-positive-windows", type=int, default=3)
    parser.add_argument("--max-top-trade-concentration", type=float, default=0.45)
    parser.add_argument("--max-trade-rows-to-write", type=int, default=250000)
    parser.add_argument("--allow-timeframe-fallback", action="store_true")
    parser.add_argument("--no-strict-timeframe", action="store_true")
    args = parser.parse_args()

    settings = LSRV2SampleExpansionSettings(
        data_dir=args.data_dir,
        input_path=args.input_path,
        symbols=parse_symbols(args.symbols),
        timeframes=parse_timeframes(args.timeframes),
        windows=parse_windows(args.windows),
        cost_models=_parse_costs(args.cost_models),
        primary_cost_model=args.primary_cost_model.strip().lower(),
        severe_cost_model=args.severe_cost_model.strip().lower(),
        max_rows=args.max_rows,
        min_closed_trades=args.min_closed_trades,
        preferred_closed_trades=args.preferred_closed_trades,
        min_positive_windows=args.min_positive_windows,
        min_severe_positive_windows=args.min_severe_positive_windows,
        max_top_trade_concentration=args.max_top_trade_concentration,
        max_trade_rows_to_write=args.max_trade_rows_to_write,
        strict_timeframe=not args.no_strict_timeframe,
        allow_timeframe_fallback=bool(args.allow_timeframe_fallback),
    )
    report = run_lsr_v2_sample_expansion(settings)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "classification_labels": report.get("classification_labels", []),
        "blockers": report.get("blockers", []),
        "locked_profile_name": report.get("locked_profile_name"),
        "locked_variant_id": report.get("locked_variant_id"),
        "requested_symbols": report.get("requested_symbols"),
        "requested_timeframes": report.get("requested_timeframes"),
        "datasets_analyzed": report.get("datasets_analyzed"),
        "datasets_with_trades": report.get("datasets_with_trades"),
        "input_rows_total": report.get("input_rows_total"),
        "closed_trades": report.get("closed_trades"),
        "positive_primary_windows": report.get("positive_primary_windows"),
        "positive_severe_windows": report.get("positive_severe_windows"),
        "avg_r_post_cost": report.get("avg_r_post_cost"),
        "sum_r_post_cost": report.get("sum_r_post_cost"),
        "top_3_positive_concentration": report.get("top_3_positive_concentration"),
        "asset_count_with_trades": report.get("asset_count_with_trades"),
        "timeframe_count_with_trades": report.get("timeframe_count_with_trades"),
        "orders_submitted_by_lsr_v2_sample_expansion": report.get("orders_submitted_by_lsr_v2_sample_expansion", 0),
        "positions_opened_by_lsr_v2_sample_expansion": report.get("positions_opened_by_lsr_v2_sample_expansion", 0),
        "promotion_ready": report.get("promotion_ready", False),
        "report": report.get("report"),
        "by_asset_report": report.get("by_asset_report"),
        "by_timeframe_report": report.get("by_timeframe_report"),
        "trades_jsonl": report.get("trades_jsonl"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
