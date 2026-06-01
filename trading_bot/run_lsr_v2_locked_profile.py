#!/usr/bin/env python3
"""Run Prompt 29.4.4s-7d LSR-v2 locked profile validation preflight."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lsr_v2_backtest_matrix import parse_windows  # noqa: E402
from core.lsr_v2_locked_profile import LSRV2LockedProfileSettings, run_lsr_v2_locked_profile  # noqa: E402


def _parse_costs(raw: str) -> tuple[str, ...]:
    out = []
    for token in str(raw or "").split(","):
        token = token.strip().lower()
        if token:
            out.append(token)
    return tuple(dict.fromkeys(out)) or ("base", "conservative", "severe")


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 locked profile validation preflight (diagnostic-only)")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--input-path", default=None)
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--windows", default="10k,12k,15k,18k,20k,30k,50k")
    parser.add_argument("--primary-windows", default="10k,12k,15k,18k,20k")
    parser.add_argument("--cost-models", default="base,conservative,severe")
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--max-rows", type=int, default=250000)
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--preferred-closed-trades", type=int, default=50)
    parser.add_argument("--min-positive-windows", type=int, default=3)
    parser.add_argument("--min-severe-positive-windows", type=int, default=3)
    parser.add_argument("--max-top-trade-concentration", type=float, default=0.45)
    parser.add_argument("--max-cost-to-edge-ratio", type=float, default=0.75)
    parser.add_argument("--max-trade-rows-to-write", type=int, default=100000)
    parser.add_argument("--allow-timeframe-fallback", action="store_true")
    parser.add_argument("--no-strict-timeframe", action="store_true")
    args = parser.parse_args()

    settings = LSRV2LockedProfileSettings(
        data_dir=args.data_dir,
        input_path=args.input_path,
        symbol=args.symbol,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
        windows=parse_windows(args.windows),
        primary_windows=parse_windows(args.primary_windows),
        cost_models=_parse_costs(args.cost_models),
        primary_cost_model=args.primary_cost_model.strip().lower(),
        severe_cost_model=args.severe_cost_model.strip().lower(),
        min_closed_trades=args.min_closed_trades,
        preferred_closed_trades=args.preferred_closed_trades,
        min_positive_windows=args.min_positive_windows,
        min_severe_positive_windows=args.min_severe_positive_windows,
        max_top_trade_concentration=args.max_top_trade_concentration,
        max_cost_to_edge_ratio=args.max_cost_to_edge_ratio,
        max_trade_rows_to_write=args.max_trade_rows_to_write,
        strict_timeframe=not args.no_strict_timeframe,
        allow_timeframe_fallback=bool(args.allow_timeframe_fallback),
    )
    report = run_lsr_v2_locked_profile(settings)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "classification_labels": report.get("classification_labels", []),
        "blockers": report.get("blockers", []),
        "locked_profile_name": report.get("locked_profile_name"),
        "locked_variant_id": report.get("locked_variant_id"),
        "requested_timeframe": report.get("requested_timeframe"),
        "detected_timeframe": report.get("detected_timeframe"),
        "timeframe_match": report.get("timeframe_match"),
        "input_path": report.get("input_path"),
        "input_rows": report.get("input_rows"),
        "primary_closed_trades": report.get("primary_closed_trades"),
        "primary_positive_windows": report.get("primary_positive_windows"),
        "severe_positive_windows": report.get("severe_positive_windows"),
        "primary_avg_r_post_cost": report.get("primary_avg_r_post_cost"),
        "primary_sum_r_post_cost": report.get("primary_sum_r_post_cost"),
        "top_1_positive_concentration": report.get("top_1_positive_concentration"),
        "top_3_positive_concentration": report.get("top_3_positive_concentration"),
        "cost_drilldown_summary": report.get("cost_drilldown_summary", {}),
        "orders_submitted_by_lsr_v2_locked_profile": report.get("orders_submitted_by_lsr_v2_locked_profile"),
        "positions_opened_by_lsr_v2_locked_profile": report.get("positions_opened_by_lsr_v2_locked_profile"),
        "promotion_ready": report.get("promotion_ready"),
        "report": report.get("report"),
        "trades_jsonl": report.get("trades_jsonl"),
        "cost_drilldown_report": report.get("cost_drilldown_report"),
        "window_stability_report": report.get("window_stability_report"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
