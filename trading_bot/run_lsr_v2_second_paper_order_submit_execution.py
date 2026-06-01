#!/usr/bin/env python3
"""Run Patch 30.3.0I second supervised paper order execution."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_second_paper_order_submit_execution import build_lsr_v2_second_paper_order_submit_execution_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_second_paper_order_submit_execution import build_lsr_v2_second_paper_order_submit_execution_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch 30.3.0I execute one bounded second supervised paper order")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--allow-project-submitter", action="store_true")
    parser.add_argument("--no-status-sync", action="store_true")
    args = parser.parse_args()
    report = build_lsr_v2_second_paper_order_submit_execution_report_from_files(
        data_dir=args.data_dir,
        allow_project_submitter=args.allow_project_submitter,
        sync_status_after_submit=not args.no_status_sync,
    )
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "blockers": report.get("blockers"),
        "cycle_id": report.get("cycle_id"),
        "candidate_id": report.get("candidate_id"),
        "payload": report.get("payload"),
        "operator_controls": report.get("operator_controls"),
        "prerequisites": report.get("prerequisites"),
        "state_before": report.get("state_before"),
        "state_after": report.get("state_after"),
        "paper_status_sync": report.get("paper_status_sync"),
        "broker_submit_called": report.get("broker_submit_called"),
        "orders_submitted_by_second_paper_execution": report.get("orders_submitted_by_second_paper_execution"),
        "positions_opened_by_second_paper_execution": report.get("positions_opened_by_second_paper_execution"),
        "positions_closed_by_second_paper_execution": report.get("positions_closed_by_second_paper_execution"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "safety_ok": report.get("safety_ok"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 1 if report.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
