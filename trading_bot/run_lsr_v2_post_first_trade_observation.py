from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_post_first_trade_observation import build_lsr_v2_post_first_trade_observation_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_post_first_trade_observation import build_lsr_v2_post_first_trade_observation_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 post-first-trade observation / no-reentry stability monitor")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--duration-hours", type=float, default=0.0)
    parser.add_argument("--interval-seconds", type=float, default=300.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--run-paper-cycles", action="store_true", help="Run paper --once cycles with submit/close env vars scrubbed")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    report = build_lsr_v2_post_first_trade_observation_report_from_files(
        data_dir=args.data_dir,
        duration_hours=args.duration_hours,
        interval_seconds=args.interval_seconds,
        max_cycles=args.max_cycles,
        run_paper_cycles=args.run_paper_cycles,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "classification_labels": report.get("classification_labels"),
        "blockers": report.get("blockers"),
        "postmortem_pass": report.get("postmortem_pass"),
        "closed_trade_complete": report.get("closed_trade_complete"),
        "second_trade_allowed": report.get("second_trade_allowed"),
        "second_trade_locked": report.get("second_trade_locked"),
        "completed_observation_cycles": report.get("completed_observation_cycles"),
        "failed_observation_cycles": report.get("failed_observation_cycles"),
        "timed_out_cycles": report.get("timed_out_cycles"),
        "state_open_lsr_v2_positions": report.get("state_open_lsr_v2_positions"),
        "state_closed_lsr_v2_positions": report.get("state_closed_lsr_v2_positions"),
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "paper_state_consistency": report.get("paper_state_consistency"),
        "paper_status_consistency": report.get("paper_status_consistency"),
        "residual_open_position": report.get("residual_open_position"),
        "extra_submit_or_reentry_detected": report.get("extra_submit_or_reentry_detected"),
        "submit_execution_events_total": report.get("submit_execution_events_total"),
        "close_execution_events_total": report.get("close_execution_events_total"),
        "new_submit_cycles": report.get("new_submit_cycles"),
        "realized_pnl_total": report.get("realized_pnl_total"),
        "realized_r": report.get("realized_r"),
        "orders_submitted_by_observation": report.get("orders_submitted_by_observation"),
        "positions_opened_by_observation": report.get("positions_opened_by_observation"),
        "positions_closed_by_observation": report.get("positions_closed_by_observation"),
        "broker_submit_called_by_observation": report.get("broker_submit_called_by_observation"),
        "broker_close_called_by_observation": report.get("broker_close_called_by_observation"),
        "paper_state_modified_by_observation": report.get("paper_state_modified_by_observation"),
        "paper_status_modified_by_observation": report.get("paper_status_modified_by_observation"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "promotion_ready": report.get("promotion_ready"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
        "log_dir": report.get("log_dir"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
