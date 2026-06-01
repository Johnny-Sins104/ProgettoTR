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

from core.lsr_v2_trade_forensics import LSRV2TradeForensicsSettings, parse_windows, run_lsr_v2_trade_forensics


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt 29.4.4s-7b LSR-v2 trade forensics / cost-failure attribution")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--windows", default="10000,12000,15000,18000,20000,30000,50000")
    parser.add_argument("--primary-windows", default="10000,12000,15000,18000,20000")
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--min-closed-trades", type=int, default=30)
    parser.add_argument("--preferred-closed-trades", type=int, default=50)
    parser.add_argument("--min-positive-windows", type=int, default=3)
    parser.add_argument("--breakeven-r-abs", type=float, default=0.10)
    parser.add_argument("--max-top1-positive-concentration", type=float, default=0.45)
    parser.add_argument("--max-top3-positive-concentration", type=float, default=0.80)
    parser.add_argument("--max-top5-positive-concentration", type=float, default=0.90)
    parser.add_argument("--max-top1-net-contribution", type=float, default=0.65)
    parser.add_argument("--severe-degradation-warn-r", type=float, default=3.0)
    parser.add_argument("--cost-flip-warn-ratio", type=float, default=0.20)
    args = parser.parse_args()

    settings = LSRV2TradeForensicsSettings(
        data_dir=args.data_dir,
        windows=parse_windows(args.windows),
        primary_windows=parse_windows(args.primary_windows),
        primary_cost_model=str(args.primary_cost_model).strip().lower(),
        severe_cost_model=str(args.severe_cost_model).strip().lower(),
        min_closed_trades=args.min_closed_trades,
        preferred_closed_trades=args.preferred_closed_trades,
        min_positive_windows=args.min_positive_windows,
        breakeven_r_abs=args.breakeven_r_abs,
        max_top1_positive_concentration=args.max_top1_positive_concentration,
        max_top3_positive_concentration=args.max_top3_positive_concentration,
        max_top5_positive_concentration=args.max_top5_positive_concentration,
        max_top1_net_contribution=args.max_top1_net_contribution,
        severe_degradation_warn_r=args.severe_degradation_warn_r,
        cost_flip_warn_ratio=args.cost_flip_warn_ratio,
    )
    report = run_lsr_v2_trade_forensics(settings)
    primary = report.get("primary_summary") if isinstance(report.get("primary_summary"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "trades_loaded": report.get("trades_loaded", 0),
        "primary_cost_model": report.get("primary_cost_model"),
        "primary_closed_trades": report.get("primary_closed_trades", 0),
        "positive_primary_windows": report.get("positive_primary_windows", 0),
        "sum_r_post_cost": primary.get("sum_r_post_cost"),
        "avg_r_post_cost": primary.get("avg_r_post_cost"),
        "top_1_positive_concentration": primary.get("top_1_positive_concentration"),
        "top_3_positive_concentration": primary.get("top_3_positive_concentration"),
        "classification_labels": report.get("classification_labels", []),
        "blockers": report.get("blockers", []),
        "orders_submitted_by_lsr_v2_forensics": report.get("orders_submitted_by_lsr_v2_forensics", 0),
        "positions_opened_by_lsr_v2_forensics": report.get("positions_opened_by_lsr_v2_forensics", 0),
        "promotion_ready": report.get("promotion_ready", False),
        "report": report.get("report"),
        "by_window_report": report.get("by_window_report"),
        "cost_failure_report": report.get("cost_failure_report"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
