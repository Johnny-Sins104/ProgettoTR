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

from core.lsr_v2_combined_risk_overlay import (  # noqa: E402
    LSRV2CombinedRiskOverlaySettings,
    run_lsr_v2_combined_risk_overlay,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prompt 29.4.4s-8d — LSR-v2 combined risk overlay / operational viability preflight."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--trades-path", default=None)
    parser.add_argument("--risk-overlay-report-path", default=None)
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--max-drawdown-r", type=float, default=15.0)
    parser.add_argument("--max-consecutive-losses-limit", type=int, default=10)
    parser.add_argument("--min-profit-retention-ratio", type=float, default=0.50)
    parser.add_argument("--min-trades-kept", type=int, default=300)
    parser.add_argument("--max-cost-degradation-ratio", type=float, default=1.25)
    parser.add_argument("--min-severe-positive-ratio", type=float, default=0.60)
    parser.add_argument("--max-trade-rows-to-write", type=int, default=300000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = LSRV2CombinedRiskOverlaySettings(
        data_dir=args.data_dir,
        trades_path=args.trades_path,
        risk_overlay_report_path=args.risk_overlay_report_path,
        primary_cost_model=args.primary_cost_model,
        severe_cost_model=args.severe_cost_model,
        max_drawdown_r=args.max_drawdown_r,
        max_consecutive_losses_limit=args.max_consecutive_losses_limit,
        min_profit_retention_ratio=args.min_profit_retention_ratio,
        min_trades_kept=args.min_trades_kept,
        max_cost_degradation_ratio=args.max_cost_degradation_ratio,
        min_severe_positive_ratio=args.min_severe_positive_ratio,
        max_trade_rows_to_write=args.max_trade_rows_to_write,
    )
    report = run_lsr_v2_combined_risk_overlay(settings)
    summary_keys = [
        "status",
        "decision",
        "classification_labels",
        "blockers",
        "locked_profile_name",
        "locked_variant_id",
        "raw_trade_rows",
        "primary_trade_count",
        "severe_trade_count",
        "variant_count",
        "valid_combined_overlay_count",
        "baseline_sum_r_post_cost",
        "baseline_avg_r_post_cost",
        "baseline_max_drawdown_r",
        "baseline_max_consecutive_losses",
        "best_combined_overlay_id",
        "best_combined_overlay_valid",
        "best_combined_overlay_trades_kept",
        "best_combined_overlay_trades_filtered",
        "best_combined_overlay_sum_r_post_cost",
        "best_combined_overlay_avg_r_post_cost",
        "best_combined_overlay_max_drawdown_r",
        "best_combined_overlay_max_consecutive_losses",
        "best_combined_overlay_profit_retention_ratio",
        "best_combined_overlay_drawdown_reduction_ratio",
        "best_combined_overlay_cost_degradation_ratio",
        "best_combined_overlay_severe_positive_ratio",
        "orders_submitted_by_lsr_v2_combined_overlay",
        "positions_opened_by_lsr_v2_combined_overlay",
        "promotion_ready",
        "report",
        "variants_report",
        "trades_jsonl",
        "operational_viability_preflight_report",
    ]
    print(json.dumps({k: report.get(k) for k in summary_keys if k in report}, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
