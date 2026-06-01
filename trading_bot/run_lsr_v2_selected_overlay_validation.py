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

from core.lsr_v2_selected_overlay_validation import (  # noqa: E402
    LSRV2SelectedOverlayValidationSettings,
    run_lsr_v2_selected_overlay_validation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prompt 29.4.4s-8e — LSR-v2 selected overlay robustness validation / anti-overfit lock."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--combined-trades-path", default=None)
    parser.add_argument("--sample-trades-path", default=None)
    parser.add_argument("--selected-overlay-id", default="combo_loss3_dd10_side_cap")
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--min-unique-primary-trades", type=int, default=300)
    parser.add_argument("--walk-forward-folds", type=int, default=8)
    parser.add_argument("--min-walk-forward-positive-ratio", type=float, default=0.55)
    parser.add_argument("--oos-holdout-ratio", type=float, default=0.20)
    parser.add_argument("--bootstrap-iterations", type=int, default=500)
    parser.add_argument("--max-drawdown-r", type=float, default=15.0)
    parser.add_argument("--max-consecutive-losses-limit", type=int, default=10)
    parser.add_argument("--max-cost-degradation-ratio", type=float, default=1.25)
    parser.add_argument("--min-severe-positive-ratio", type=float, default=0.60)
    parser.add_argument("--max-trade-rows-to-write", type=int, default=300000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = LSRV2SelectedOverlayValidationSettings(
        data_dir=args.data_dir,
        combined_trades_path=args.combined_trades_path,
        sample_trades_path=args.sample_trades_path,
        selected_overlay_id=args.selected_overlay_id,
        primary_cost_model=args.primary_cost_model,
        severe_cost_model=args.severe_cost_model,
        min_unique_primary_trades=args.min_unique_primary_trades,
        walk_forward_folds=args.walk_forward_folds,
        min_walk_forward_positive_ratio=args.min_walk_forward_positive_ratio,
        oos_holdout_ratio=args.oos_holdout_ratio,
        bootstrap_iterations=args.bootstrap_iterations,
        max_drawdown_r=args.max_drawdown_r,
        max_consecutive_losses_limit=args.max_consecutive_losses_limit,
        max_cost_degradation_ratio=args.max_cost_degradation_ratio,
        min_severe_positive_ratio=args.min_severe_positive_ratio,
        max_trade_rows_to_write=args.max_trade_rows_to_write,
    )
    report = run_lsr_v2_selected_overlay_validation(settings)
    summary_keys = [
        "status",
        "decision",
        "classification_labels",
        "blockers",
        "locked_profile_name",
        "locked_variant_id",
        "selected_overlay_id",
        "overlay_oracle",
        "raw_combined_trade_rows",
        "raw_sample_trade_rows",
        "selected_primary_trades",
        "paired_severe_trades",
        "primary_sum_r_post_cost",
        "primary_avg_r_post_cost",
        "primary_max_drawdown_r",
        "max_consecutive_losses",
        "walk_forward_stable",
        "walk_forward_positive_ratio",
        "oos_pass",
        "oos_avg_r_post_cost",
        "oos_sum_r_post_cost",
        "bootstrap_pass",
        "bootstrap_positive_ratio",
        "bootstrap_median_avg_r",
        "cost_degradation_non_destructive",
        "cost_degradation_ratio",
        "severe_positive_ratio",
        "asset_stability_ok",
        "timeframe_stability_ok",
        "side_stability_ok",
        "orders_submitted_by_lsr_v2_selected_overlay_validation",
        "positions_opened_by_lsr_v2_selected_overlay_validation",
        "promotion_ready",
        "report",
        "walk_forward_report",
        "oos_report",
        "bootstrap_report",
        "trades_jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in summary_keys if k in report}, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
