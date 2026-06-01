from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_third_closed_trade_final_audit import build_lsr_v2_third_closed_trade_final_audit_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_third_closed_trade_final_audit import build_lsr_v2_third_closed_trade_final_audit_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 third closed trade final audit / post-close reconciliation")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_third_closed_trade_final_audit_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "close_execution_report_present": report.get("close_execution_report_present"),
        "close_execution_report_decision": report.get("close_execution_report_decision"),
        "close_execution_events": report.get("close_execution_events"),
        "closed_trade_confirmed": report.get("closed_trade_confirmed"),
        "flat_state_confirmed": report.get("flat_state_confirmed"),
        "paper_state_status_consistency": report.get("paper_state_status_consistency"),
        "open_positions_after": report.get("open_positions_after"),
        "open_third_lsr_v2_positions_after": report.get("open_third_lsr_v2_positions_after"),
        "paper_status_open_positions_after": report.get("paper_status_open_positions_after"),
        "pending_orders_after": report.get("pending_orders_after"),
        "paper_status_pending_orders_after": report.get("paper_status_pending_orders_after"),
        "backups_present": report.get("backups_present"),
        "backup_state_exists": report.get("backup_state_exists"),
        "backup_status_exists": report.get("backup_status_exists"),
        "close_env_absent": report.get("close_env_absent"),
        "no_submit_or_reentry": report.get("no_submit_or_reentry"),
        "positions_closed_by_final_audit": report.get("positions_closed_by_final_audit"),
        "orders_submitted_by_final_audit": report.get("orders_submitted_by_final_audit"),
        "positions_opened_by_final_audit": report.get("positions_opened_by_final_audit"),
        "paper_state_modified_by_final_audit": report.get("paper_state_modified_by_final_audit"),
        "paper_status_modified_by_final_audit": report.get("paper_status_modified_by_final_audit"),
        "realized_pnl_total": report.get("realized_pnl_total"),
        "balance_after": report.get("balance_after"),
        "realized_pnl_after": report.get("realized_pnl_after"),
        "symbols": report.get("symbols"),
        "sides": report.get("sides"),
        "close_reasons": report.get("close_reasons"),
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
