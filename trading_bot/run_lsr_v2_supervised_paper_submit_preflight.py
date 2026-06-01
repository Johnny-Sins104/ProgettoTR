#!/usr/bin/env python
"""Prompt 29.4.4s-10i — LSR-v2 supervised paper submit preflight runner.

Reads the latest strict cycle-scoped LSR-v2 handoff dry-run and upstream
preflight reports, then writes a disabled-by-default supervised submit boundary
report. It never calls the broker and never submits paper orders.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_supervised_paper_submit_preflight import (  # type: ignore
        build_lsr_v2_submit_preflight_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_supervised_paper_submit_preflight import (  # type: ignore
        build_lsr_v2_submit_preflight_report_from_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 supervised paper submit preflight, disabled by default")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id; defaults to latest handoff/order-intent cycle")
    args = parser.parse_args()

    report = build_lsr_v2_submit_preflight_report_from_files(data_dir=Path(args.data_dir), cycle_id=str(args.cycle_id or ""))
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "handoff_dry_run_events": report.get("handoff_dry_run_events"),
        "submit_preflight_events": report.get("submit_preflight_events"),
        "would_prepare_submit_count": report.get("would_prepare_submit_count"),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "submit_enabled": False,
        "broker_submit_called": False,
        "paper_order_submission_enabled": False,
        "execution_enabled": False,
        "routing_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "operator_enable": report.get("operator_enable"),
        "operator_confirmation_ok": report.get("operator_confirmation_ok"),
        "orders_submitted_by_lsr_v2_submit_preflight": 0,
        "positions_opened_by_lsr_v2_submit_preflight": 0,
        "promotion_ready": False,
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
