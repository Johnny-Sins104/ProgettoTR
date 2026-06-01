from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_three_trade_postmortem_stability_lock import build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_three_trade_postmortem_stability_lock import build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 three-trade postmortem / stability lock")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    report = build_lsr_v2_three_trade_postmortem_stability_lock_report_from_files(data_dir=args.data_dir)
    keys = [
        "status",
        "decision",
        "classification_labels",
        "blockers",
        "cycle_ids",
        "three_trade_postmortem_complete",
        "three_trade_lifecycle_complete",
        "three_trade_reports_complete",
        "first_closed_trade_final_audit_pass",
        "first_trade_postmortem_pass",
        "second_closed_trade_final_audit_pass",
        "two_trade_postmortem_pass",
        "third_submit_execution_pass",
        "third_lifecycle_ready",
        "third_close_preflight_ready",
        "third_closed_trade_final_audit_pass",
        "submit_execution_events_total",
        "close_execution_events_total",
        "first_realized_pnl",
        "second_realized_pnl",
        "third_realized_pnl",
        "realized_pnl_sum_from_final_audits",
        "realized_pnl_after",
        "aggregate_realized_pnl",
        "balance_after",
        "total_risk_amount",
        "total_realized_r_from_final_audits",
        "pnl_reconciliation_ok",
        "open_positions_after",
        "open_lsr_v2_positions_after",
        "pending_orders_after",
        "paper_status_open_positions_after",
        "paper_status_pending_orders_after",
        "flat_state_confirmed",
        "paper_state_status_consistency",
        "operator_env_absent",
        "fourth_submit_or_reentry_detected",
        "fourth_trade_allowed",
        "fourth_trade_locked",
        "stability_lock_active",
        "next_step",
        "orders_submitted_by_three_trade_postmortem",
        "positions_opened_by_three_trade_postmortem",
        "positions_closed_by_three_trade_postmortem",
        "broker_submit_called_by_three_trade_postmortem",
        "broker_close_called_by_three_trade_postmortem",
        "paper_state_modified_by_three_trade_postmortem",
        "paper_status_modified_by_three_trade_postmortem",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "report",
        "jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in keys}, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
