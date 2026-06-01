from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_closed_trade_final_audit import build_lsr_v2_closed_trade_final_audit_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_closed_trade_final_audit import build_lsr_v2_closed_trade_final_audit_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 closed paper trade final audit / realized outcome report")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_closed_trade_final_audit_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "classification_labels": report.get("classification_labels"),
        "blockers": report.get("blockers"),
        "submit_execution_events": report.get("submit_execution_events"),
        "close_execution_events": report.get("close_execution_events"),
        "submit_executed": report.get("submit_executed"),
        "close_executed": report.get("close_executed"),
        "closed_trade_complete": report.get("closed_trade_complete"),
        "symbols": report.get("symbols"),
        "sides": report.get("sides"),
        "close_reasons": report.get("close_reasons"),
        "total_notional": report.get("total_notional"),
        "total_risk_amount": report.get("total_risk_amount"),
        "realized_pnl_total": report.get("realized_pnl_total"),
        "realized_r": report.get("realized_r"),
        "pnl_reconciliation_ok": report.get("pnl_reconciliation_ok"),
        "state_open_lsr_v2_positions": report.get("state_open_lsr_v2_positions"),
        "state_closed_lsr_v2_positions": report.get("state_closed_lsr_v2_positions"),
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "paper_state_consistency": report.get("paper_state_consistency"),
        "paper_status_consistency": report.get("paper_status_consistency"),
        "residual_open_position": report.get("residual_open_position"),
        "extra_submit_or_reentry_detected": report.get("extra_submit_or_reentry_detected"),
        "close_multiple_detected": report.get("close_multiple_detected"),
        "paper_state_modified_by_final_audit": report.get("paper_state_modified_by_final_audit"),
        "paper_status_modified_by_final_audit": report.get("paper_status_modified_by_final_audit"),
        "broker_submit_called_by_final_audit": report.get("broker_submit_called_by_final_audit"),
        "broker_close_called_by_final_audit": report.get("broker_close_called_by_final_audit"),
        "orders_submitted_by_final_audit": report.get("orders_submitted_by_final_audit"),
        "positions_opened_by_final_audit": report.get("positions_opened_by_final_audit"),
        "positions_closed_by_final_audit": report.get("positions_closed_by_final_audit"),
        "automatic_reentry_enabled": report.get("automatic_reentry_enabled"),
        "automatic_close_enabled": report.get("automatic_close_enabled"),
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
