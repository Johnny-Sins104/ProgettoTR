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

from core.lsr_v2_risk_overlay_ablation import (  # noqa: E402
    LSRV2RiskOverlayAblationSettings,
    run_lsr_v2_risk_overlay_ablation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prompt 29.4.4s-8c — LSR-v2 risk overlay ablation / drawdown control preflight."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--trades-path", default=None)
    parser.add_argument("--attribution-report-path", default=None)
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--max-drawdown-r", type=float, default=25.0)
    parser.add_argument("--max-consecutive-losses-limit", type=int, default=10)
    parser.add_argument("--min-profit-retention-ratio", type=float, default=0.50)
    parser.add_argument("--min-drawdown-reduction-ratio", type=float, default=0.40)
    parser.add_argument("--min-trades-kept-ratio", type=float, default=0.20)
    parser.add_argument("--max-cost-degradation-ratio", type=float, default=0.85)
    parser.add_argument("--min-severe-positive-ratio", type=float, default=0.45)
    parser.add_argument("--max-trade-rows-to-write", type=int, default=250_000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = LSRV2RiskOverlayAblationSettings(
        data_dir=args.data_dir,
        trades_path=args.trades_path,
        attribution_report_path=args.attribution_report_path,
        primary_cost_model=args.primary_cost_model,
        severe_cost_model=args.severe_cost_model,
        max_drawdown_r=args.max_drawdown_r,
        max_consecutive_losses_limit=args.max_consecutive_losses_limit,
        min_profit_retention_ratio=args.min_profit_retention_ratio,
        min_drawdown_reduction_ratio=args.min_drawdown_reduction_ratio,
        min_trades_kept_ratio=args.min_trades_kept_ratio,
        max_cost_degradation_ratio=args.max_cost_degradation_ratio,
        min_severe_positive_ratio=args.min_severe_positive_ratio,
        max_trade_rows_to_write=args.max_trade_rows_to_write,
    )
    report = run_lsr_v2_risk_overlay_ablation(settings)
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
        "valid_overlay_count",
        "baseline_sum_r_post_cost",
        "baseline_avg_r_post_cost",
        "baseline_max_drawdown_r",
        "baseline_max_consecutive_losses",
        "best_overlay_id",
        "best_overlay_family",
        "best_overlay_valid",
        "best_overlay_oracle",
        "best_overlay_trades_kept",
        "best_overlay_trades_filtered",
        "best_overlay_sum_r_post_cost",
        "best_overlay_avg_r_post_cost",
        "best_overlay_max_drawdown_r",
        "best_overlay_max_consecutive_losses",
        "best_overlay_profit_retention_ratio",
        "best_overlay_drawdown_reduction_ratio",
        "best_overlay_cost_degradation_ratio",
        "best_overlay_severe_positive_ratio",
        "orders_submitted_by_lsr_v2_risk_overlay_ablation",
        "positions_opened_by_lsr_v2_risk_overlay_ablation",
        "promotion_ready",
        "report",
        "variants_report",
        "trades_jsonl",
        "selection_report",
    ]
    print(json.dumps({k: report.get(k) for k in summary_keys if k in report}, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
