#!/usr/bin/env python3
"""Run Prompt 29.4.4s-10l-1 LSR-v2 paper status reconciliation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_paper_status_reconciliation import build_lsr_v2_paper_status_reconciliation_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_paper_status_reconciliation import build_lsr_v2_paper_status_reconciliation_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 paper status reconciliation")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_paper_status_reconciliation_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    summary_keys = [
        "status",
        "decision",
        "cycle_id",
        "sync_enabled",
        "sync_confirmation_ok",
        "paper_status_modified",
        "backup_path",
        "state_open_positions",
        "state_pending_orders",
        "state_lsr_v2_open_positions",
        "status_open_positions_before",
        "status_open_positions_after",
        "status_pending_orders_before",
        "status_pending_orders_after",
        "position_monitor_open_positions_before",
        "position_monitor_open_positions_after",
        "sync_required_before",
        "sync_required_after",
        "duplicate_position_check",
        "max_positions_check",
        "symbols",
        "sides",
        "total_risk_amount",
        "total_notional",
        "orders_submitted_by_status_reconciliation",
        "positions_opened_by_status_reconciliation",
        "broker_submit_called_by_status_reconciliation",
        "automatic_close_enabled",
        "automatic_reentry_enabled",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "report",
        "jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in summary_keys if k in report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
