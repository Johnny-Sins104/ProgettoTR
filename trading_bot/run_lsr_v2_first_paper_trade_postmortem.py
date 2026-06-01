from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_first_paper_trade_postmortem import build_lsr_v2_first_paper_trade_postmortem_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_first_paper_trade_postmortem import build_lsr_v2_first_paper_trade_postmortem_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 first paper trade postmortem / one-trade stability lock")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_first_paper_trade_postmortem_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "classification_labels": report.get("classification_labels"),
        "blockers": report.get("blockers"),
        "closed_trade_complete": report.get("closed_trade_complete"),
        "postmortem_complete": report.get("postmortem_complete"),
        "next_step_observation_required": report.get("next_step_observation_required"),
        "second_trade_allowed": report.get("second_trade_allowed"),
        "submit_execution_events": report.get("submit_execution_events"),
        "close_execution_events": report.get("close_execution_events"),
        "realized_pnl_total": report.get("realized_pnl_total"),
        "realized_r": report.get("realized_r"),
        "pnl_reconciliation_ok": report.get("pnl_reconciliation_ok"),
        "state_open_lsr_v2_positions": report.get("state_open_lsr_v2_positions"),
        "state_closed_lsr_v2_positions": report.get("state_closed_lsr_v2_positions"),
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "residual_open_position": report.get("residual_open_position"),
        "extra_submit_or_reentry_detected": report.get("extra_submit_or_reentry_detected"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "orders_submitted_by_postmortem": report.get("orders_submitted_by_postmortem"),
        "positions_opened_by_postmortem": report.get("positions_opened_by_postmortem"),
        "positions_closed_by_postmortem": report.get("positions_closed_by_postmortem"),
        "broker_submit_called_by_postmortem": report.get("broker_submit_called_by_postmortem"),
        "broker_close_called_by_postmortem": report.get("broker_close_called_by_postmortem"),
        "paper_state_modified_by_postmortem": report.get("paper_state_modified_by_postmortem"),
        "paper_status_modified_by_postmortem": report.get("paper_status_modified_by_postmortem"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
