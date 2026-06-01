#!/usr/bin/env python
"""Prompt 29.4.4s-10h — LSR-v2 paper broker handoff dry-run runner.

Reads the latest cycle-scoped LSR-v2 order-intent audit and writes a fail-closed
paper-broker payload/schema report.  It never calls PaperBrokerAdapter and never
submits or opens paper positions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_paper_broker_handoff_dry_run import (  # type: ignore
        LSRV2PaperBrokerHandoffDryRunSettings,
        build_lsr_v2_paper_broker_handoff_dry_run_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_paper_broker_handoff_dry_run import (  # type: ignore
        LSRV2PaperBrokerHandoffDryRunSettings,
        build_lsr_v2_paper_broker_handoff_dry_run_report_from_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 paper broker handoff dry-run payload audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id. Defaults to latest LSR-v2 order-intent report cycle.")
    args = parser.parse_args(argv)

    settings = LSRV2PaperBrokerHandoffDryRunSettings(data_dir=str(Path(args.data_dir)))
    report = build_lsr_v2_paper_broker_handoff_dry_run_report_from_files(
        data_dir=args.data_dir,
        cycle_id=str(args.cycle_id or ""),
        settings=settings,
    )
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "order_intent_events": report.get("order_intent_events"),
        "creatable_order_intents": report.get("creatable_order_intents"),
        "handoff_dry_run_events": report.get("handoff_dry_run_events"),
        "payload_valid_count": report.get("payload_valid_count"),
        "payload_invalid_count": report.get("payload_invalid_count"),
        "would_create_paper_order_count": report.get("would_create_paper_order_count"),
        "would_submit_to_paper_broker_count": 0,
        "would_submit_count": 0,
        "broker_submit_called": False,
        "paper_broker_adapter": report.get("paper_broker_adapter"),
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "orders_submitted_by_lsr_v2_handoff": 0,
        "positions_opened_by_lsr_v2_handoff": 0,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
