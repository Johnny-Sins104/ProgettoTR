#!/usr/bin/env python3
"""Run Prompt 29.4.4s-8 LSR-v2 robustness validation suite."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lsr_v2_robustness_validation import (  # noqa: E402
    LSRV2RobustnessValidationSettings,
    run_lsr_v2_robustness_validation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 walk-forward / OOS / bootstrap validation suite (diagnostic-only)")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--trades-path", default=None)
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--min-unique-primary-trades", type=int, default=50)
    parser.add_argument("--walk-forward-folds", type=int, default=8)
    parser.add_argument("--min-walk-forward-folds", type=int, default=5)
    parser.add_argument("--embargo-trades", type=int, default=1)
    parser.add_argument("--min-walk-forward-positive-ratio", type=float, default=0.55)
    parser.add_argument("--oos-holdout-ratio", type=float, default=0.20)
    parser.add_argument("--bootstrap-iterations", type=int, default=500)
    parser.add_argument("--bootstrap-sample-fraction", type=float, default=1.0)
    parser.add_argument("--min-bootstrap-positive-ratio", type=float, default=0.60)
    parser.add_argument("--max-drawdown-r", type=float, default=25.0)
    parser.add_argument("--max-asset-pnl-share", type=float, default=0.65)
    parser.add_argument("--max-timeframe-pnl-share", type=float, default=0.75)
    parser.add_argument("--min-severe-positive-ratio", type=float, default=0.45)
    parser.add_argument("--max-cost-degradation-ratio", type=float, default=0.85)
    parser.add_argument("--random-seed", type=int, default=294408)
    args = parser.parse_args()

    settings = LSRV2RobustnessValidationSettings(
        data_dir=args.data_dir,
        trades_path=args.trades_path,
        primary_cost_model=args.primary_cost_model.strip().lower(),
        severe_cost_model=args.severe_cost_model.strip().lower(),
        min_unique_primary_trades=args.min_unique_primary_trades,
        walk_forward_folds=args.walk_forward_folds,
        min_walk_forward_folds=args.min_walk_forward_folds,
        embargo_trades=args.embargo_trades,
        min_walk_forward_positive_ratio=args.min_walk_forward_positive_ratio,
        oos_holdout_ratio=args.oos_holdout_ratio,
        bootstrap_iterations=args.bootstrap_iterations,
        bootstrap_sample_fraction=args.bootstrap_sample_fraction,
        min_bootstrap_positive_ratio=args.min_bootstrap_positive_ratio,
        max_drawdown_r=args.max_drawdown_r,
        max_asset_pnl_share=args.max_asset_pnl_share,
        max_timeframe_pnl_share=args.max_timeframe_pnl_share,
        min_severe_positive_ratio=args.min_severe_positive_ratio,
        max_cost_degradation_ratio=args.max_cost_degradation_ratio,
        random_seed=args.random_seed,
    )
    report = run_lsr_v2_robustness_validation(settings)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "classification_labels": report.get("classification_labels", []),
        "blockers": report.get("blockers", []),
        "locked_profile_name": report.get("locked_profile_name"),
        "locked_variant_id": report.get("locked_variant_id"),
        "raw_trade_rows": report.get("raw_trade_rows", 0),
        "unique_primary_trades": report.get("unique_primary_trades", 0),
        "unique_severe_trades": report.get("unique_severe_trades", 0),
        "primary_avg_r_post_cost": (report.get("primary_summary") or {}).get("avg_r_post_cost"),
        "primary_sum_r_post_cost": (report.get("primary_summary") or {}).get("sum_r_post_cost"),
        "walk_forward_positive_ratio": report.get("walk_forward_positive_ratio"),
        "walk_forward_stable": report.get("walk_forward_stable"),
        "oos_pass": report.get("oos_pass"),
        "oos_avg_r_post_cost": report.get("oos_avg_r_post_cost"),
        "oos_sum_r_post_cost": report.get("oos_sum_r_post_cost"),
        "bootstrap_pass": report.get("bootstrap_pass"),
        "bootstrap_positive_ratio": report.get("bootstrap_positive_ratio"),
        "bootstrap_median_avg_r": report.get("bootstrap_median_avg_r"),
        "cost_degradation_non_destructive": report.get("cost_degradation_non_destructive"),
        "asset_stability_ok": (report.get("asset_stability") or {}).get("asset_stability_ok"),
        "timeframe_stability_ok": (report.get("timeframe_stability") or {}).get("timeframe_stability_ok"),
        "side_stability_ok": (report.get("side_stability") or {}).get("side_stability_ok"),
        "orders_submitted_by_lsr_v2_robustness": report.get("orders_submitted_by_lsr_v2_robustness", 0),
        "positions_opened_by_lsr_v2_robustness": report.get("positions_opened_by_lsr_v2_robustness", 0),
        "promotion_ready": report.get("promotion_ready", False),
        "report": report.get("report"),
        "walk_forward_report": report.get("walk_forward_report"),
        "oos_report": report.get("oos_report"),
        "bootstrap_report": report.get("bootstrap_report"),
        "walk_forward_trades_jsonl": report.get("walk_forward_trades_jsonl"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
