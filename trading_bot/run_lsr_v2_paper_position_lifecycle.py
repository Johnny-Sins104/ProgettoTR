#!/usr/bin/env python3
"""Run Prompt 29.4.4s-10l LSR-v2 paper position lifecycle audit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_paper_position_lifecycle import build_lsr_v2_paper_position_lifecycle_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_paper_position_lifecycle import build_lsr_v2_paper_position_lifecycle_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 paper position lifecycle audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_paper_position_lifecycle_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    summary_keys = [
        "status",
        "decision",
        "cycle_id",
        "event_source",
        "strict_cycle_scope",
        "execution_events",
        "lifecycle_events",
        "matching_order_count",
        "matching_position_count",
        "open_lsr_v2_position_count",
        "closed_lsr_v2_position_count",
        "active_lsr_v2_state_positions",
        "paper_status_open_positions",
        "duplicate_position_check",
        "max_positions_check",
        "paper_state_consistency",
        "paper_status_consistency",
        "symbols",
        "sides",
        "current_statuses",
        "total_risk_amount",
        "total_notional",
        "orders_submitted_by_lifecycle_audit",
        "positions_opened_by_lifecycle_audit",
        "broker_submit_called_by_lifecycle_audit",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "automatic_close_enabled",
        "automatic_reentry_enabled",
        "promotion_ready",
        "report",
        "jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in summary_keys if k in report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
