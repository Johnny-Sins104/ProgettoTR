from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_two_trade_paper_cycle_postmortem import build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_two_trade_paper_cycle_postmortem import build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 two-trade paper cycle postmortem / third-trade lock")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    report = build_lsr_v2_two_trade_paper_cycle_postmortem_report_from_files(data_dir=args.data_dir)
    keys = [
        "status", "decision", "classification_labels", "blockers", "cycle_ids",
        "two_trade_postmortem_complete", "first_closed_trade_final_audit_pass",
        "first_trade_postmortem_pass", "post_first_trade_observation_pass",
        "second_closed_trade_final_audit_pass", "submit_execution_events_total",
        "close_execution_events_total", "first_realized_pnl", "second_realized_pnl",
        "total_realized_pnl", "first_realized_r", "second_realized_r",
        "total_realized_r", "average_realized_r", "total_risk_amount",
        "pnl_reconciliation_ok", "state_open_lsr_v2_positions",
        "state_closed_lsr_v2_positions", "paper_state_closed_history_complete",
        "paper_state_closed_history_source_is_authoritative", "paper_status_open_positions",
        "paper_status_pending_orders", "paper_state_consistency",
        "paper_status_consistency", "residual_open_position",
        "third_submit_or_reentry_detected", "third_trade_allowed", "third_trade_locked",
        "next_step_observation_required", "orders_submitted_by_two_trade_postmortem",
        "positions_opened_by_two_trade_postmortem", "positions_closed_by_two_trade_postmortem",
        "broker_submit_called_by_two_trade_postmortem", "broker_close_called_by_two_trade_postmortem",
        "paper_state_modified_by_two_trade_postmortem", "paper_status_modified_by_two_trade_postmortem",
        "automatic_reentry_enabled", "automatic_close_enabled", "live_enabled", "testnet_enabled",
        "exchange_broker_enabled", "operational_unlock_allowed", "promotion_ready", "report", "jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in keys}, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
