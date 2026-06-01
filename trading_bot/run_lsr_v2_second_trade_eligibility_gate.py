from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_second_trade_eligibility_gate import build_lsr_v2_second_trade_eligibility_gate_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_second_trade_eligibility_gate import build_lsr_v2_second_trade_eligibility_gate_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 second supervised paper trade eligibility gate")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--min-4h-cycles", type=int, default=40)
    parser.add_argument("--min-8h-cycles", type=int, default=80)
    args = parser.parse_args()

    report = build_lsr_v2_second_trade_eligibility_gate_report_from_files(
        data_dir=args.data_dir,
        min_4h_cycles=args.min_4h_cycles,
        min_8h_cycles=args.min_8h_cycles,
    )
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "classification_labels": report.get("classification_labels"),
        "blockers": report.get("blockers"),
        "cycle_id": report.get("cycle_id"),
        "observation_pass": report.get("observation_pass"),
        "postmortem_pass": report.get("postmortem_pass"),
        "closed_trade_final_audit_pass": report.get("closed_trade_final_audit_pass"),
        "completed_observation_cycles": report.get("completed_observation_cycles"),
        "four_hour_observation_pass": report.get("four_hour_observation_pass"),
        "eight_hour_observation_pass": report.get("eight_hour_observation_pass"),
        "failed_observation_cycles": report.get("failed_observation_cycles"),
        "timed_out_cycles": report.get("timed_out_cycles"),
        "new_submit_cycles": report.get("new_submit_cycles"),
        "extra_submit_or_reentry_detected": report.get("extra_submit_or_reentry_detected"),
        "second_trade_locked": report.get("second_trade_locked"),
        "second_trade_eligible": report.get("second_trade_eligible"),
        "second_trade_execute_enabled": report.get("second_trade_execute_enabled"),
        "second_trade_submit_enabled": report.get("second_trade_submit_enabled"),
        "state_open_lsr_v2_positions": report.get("state_open_lsr_v2_positions"),
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "paper_state_consistency": report.get("paper_state_consistency"),
        "paper_status_consistency": report.get("paper_status_consistency"),
        "realized_pnl_total": report.get("realized_pnl_total"),
        "realized_r": report.get("realized_r"),
        "broker_submit_called_by_second_trade_gate": report.get("broker_submit_called_by_second_trade_gate"),
        "orders_submitted_by_second_trade_gate": report.get("orders_submitted_by_second_trade_gate"),
        "positions_opened_by_second_trade_gate": report.get("positions_opened_by_second_trade_gate"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "promotion_ready": report.get("promotion_ready"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
