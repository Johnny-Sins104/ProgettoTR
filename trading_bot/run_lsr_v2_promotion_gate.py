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

from core.lsr_v2_promotion_gate import LSRV2PromotionGateSettings, run_lsr_v2_promotion_gate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prompt 29.4.4s-9 LSR-v2 promotion gate / paper-supervised readiness preflight."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--selected-validation-report-path", default=None)
    parser.add_argument("--walk-forward-report-path", default=None)
    parser.add_argument("--oos-report-path", default=None)
    parser.add_argument("--bootstrap-report-path", default=None)
    parser.add_argument("--combined-overlay-report-path", default=None)
    parser.add_argument("--operational-preflight-report-path", default=None)
    parser.add_argument("--sample-expansion-report-path", default=None)
    parser.add_argument("--min-selected-primary-trades", type=int, default=300)
    parser.add_argument("--max-primary-drawdown-r", type=float, default=15.0)
    parser.add_argument("--max-consecutive-losses", type=int, default=10)
    parser.add_argument("--min-walk-forward-positive-ratio", type=float, default=0.55)
    parser.add_argument("--min-bootstrap-positive-ratio", type=float, default=0.60)
    parser.add_argument("--max-cost-degradation-ratio", type=float, default=1.25)
    parser.add_argument("--min-severe-positive-ratio", type=float, default=0.60)
    parser.add_argument("--min-sample-expansion-trades", type=int, default=300)
    parser.add_argument("--allow-input-blockers", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = LSRV2PromotionGateSettings(
        data_dir=args.data_dir,
        selected_validation_report_path=args.selected_validation_report_path,
        walk_forward_report_path=args.walk_forward_report_path,
        oos_report_path=args.oos_report_path,
        bootstrap_report_path=args.bootstrap_report_path,
        combined_overlay_report_path=args.combined_overlay_report_path,
        operational_preflight_report_path=args.operational_preflight_report_path,
        sample_expansion_report_path=args.sample_expansion_report_path,
        min_selected_primary_trades=args.min_selected_primary_trades,
        max_primary_drawdown_r=args.max_primary_drawdown_r,
        max_consecutive_losses=args.max_consecutive_losses,
        min_walk_forward_positive_ratio=args.min_walk_forward_positive_ratio,
        min_bootstrap_positive_ratio=args.min_bootstrap_positive_ratio,
        max_cost_degradation_ratio=args.max_cost_degradation_ratio,
        min_severe_positive_ratio=args.min_severe_positive_ratio,
        min_sample_expansion_trades=args.min_sample_expansion_trades,
        require_no_input_blockers=not args.allow_input_blockers,
    )
    report = run_lsr_v2_promotion_gate(settings)
    summary_keys = [
        "status",
        "decision",
        "classification_labels",
        "blockers",
        "locked_profile_name",
        "locked_variant_id",
        "selected_overlay_id",
        "overlay_oracle",
        "paper_supervised_candidate",
        "paper_supervised_readiness_preflight_pass",
        "selected_primary_trades",
        "primary_avg_r_post_cost",
        "primary_sum_r_post_cost",
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
        "combined_overlay_decision",
        "combined_overlay_valid",
        "sample_expansion_decision",
        "sample_expansion_closed_trades",
        "orders_submitted_by_lsr_v2_promotion_gate",
        "positions_opened_by_lsr_v2_promotion_gate",
        "broker_submit_called",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "execution_enabled",
        "routing_enabled",
        "paper_order_submission_enabled",
        "promotion_ready",
        "report",
    ]
    print(json.dumps({k: report.get(k) for k in summary_keys if k in report}, indent=2, sort_keys=True))
    return 0 if report.get("status") in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
