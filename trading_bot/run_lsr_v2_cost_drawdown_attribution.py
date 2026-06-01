#!/usr/bin/env python3
"""Run Prompt 29.4.4s-8b LSR-v2 cost/drawdown attribution audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.lsr_v2_cost_drawdown_attribution import (  # noqa: E402
    LSRV2CostDrawdownAttributionSettings,
    run_lsr_v2_cost_drawdown_attribution,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 cost degradation and drawdown attribution audit (diagnostic-only)")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--trades-path", default=None)
    parser.add_argument("--robustness-report-path", default=None)
    parser.add_argument("--primary-cost-model", default="conservative")
    parser.add_argument("--severe-cost-model", default="severe")
    parser.add_argument("--max-drawdown-r", type=float, default=25.0)
    parser.add_argument("--min-severe-positive-ratio", type=float, default=0.45)
    parser.add_argument("--max-cost-degradation-ratio", type=float, default=0.85)
    parser.add_argument("--min-segment-depth-r", type=float, default=2.0)
    parser.add_argument("--max-drawdown-segment-share", type=float, default=0.65)
    parser.add_argument("--max-group-loss-share", type=float, default=0.60)
    parser.add_argument("--max-consecutive-losses-limit", type=int, default=8)
    parser.add_argument("--min-primary-trades", type=int, default=50)
    args = parser.parse_args()

    settings = LSRV2CostDrawdownAttributionSettings(
        data_dir=args.data_dir,
        trades_path=args.trades_path,
        robustness_report_path=args.robustness_report_path,
        primary_cost_model=args.primary_cost_model.strip().lower(),
        severe_cost_model=args.severe_cost_model.strip().lower(),
        max_drawdown_r=args.max_drawdown_r,
        min_severe_positive_ratio=args.min_severe_positive_ratio,
        max_cost_degradation_ratio=args.max_cost_degradation_ratio,
        min_segment_depth_r=args.min_segment_depth_r,
        max_drawdown_segment_share=args.max_drawdown_segment_share,
        max_group_loss_share=args.max_group_loss_share,
        max_consecutive_losses_limit=args.max_consecutive_losses_limit,
        min_primary_trades=args.min_primary_trades,
    )
    report = run_lsr_v2_cost_drawdown_attribution(settings)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "classification_labels": report.get("classification_labels", []),
        "blockers": report.get("blockers", []),
        "locked_profile_name": report.get("locked_profile_name"),
        "locked_variant_id": report.get("locked_variant_id"),
        "raw_trade_rows": report.get("raw_trade_rows", 0),
        "primary_trade_count": report.get("primary_trade_count", 0),
        "severe_trade_count": report.get("severe_trade_count", 0),
        "primary_sum_r_post_cost": report.get("primary_sum_r_post_cost"),
        "primary_avg_r_post_cost": report.get("primary_avg_r_post_cost"),
        "primary_max_drawdown_r": report.get("primary_max_drawdown_r"),
        "cost_degradation_non_destructive": report.get("cost_degradation_non_destructive"),
        "cost_degradation_ratio": report.get("cost_degradation_ratio"),
        "severe_positive_ratio": report.get("severe_positive_ratio"),
        "max_drawdown_above_limit": report.get("max_drawdown_above_limit"),
        "drawdown_clustered": report.get("drawdown_clustered"),
        "max_consecutive_losses": report.get("max_consecutive_losses"),
        "risk_overlay_candidate_count": report.get("risk_overlay_candidate_count"),
        "orders_submitted_by_lsr_v2_cost_drawdown_attribution": report.get("orders_submitted_by_lsr_v2_cost_drawdown_attribution", 0),
        "positions_opened_by_lsr_v2_cost_drawdown_attribution": report.get("positions_opened_by_lsr_v2_cost_drawdown_attribution", 0),
        "promotion_ready": report.get("promotion_ready", False),
        "report": report.get("report"),
        "cost_degradation_report": report.get("cost_degradation_report"),
        "drawdown_attribution_report": report.get("drawdown_attribution_report"),
        "drawdown_segments_jsonl": report.get("drawdown_segments_jsonl"),
        "risk_overlay_preflight_report": report.get("risk_overlay_preflight_report"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
