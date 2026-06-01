#!/usr/bin/env python
"""Prompt 29.4.4s-10v — LSR-v2 second-trade paper broker handoff dry-run runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_second_trade_handoff_dry_run import (  # type: ignore
        LSRV2SecondTradeHandoffDryRunSettings,
        build_lsr_v2_second_trade_handoff_dry_run_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_second_trade_handoff_dry_run import (  # type: ignore
        LSRV2SecondTradeHandoffDryRunSettings,
        build_lsr_v2_second_trade_handoff_dry_run_report_from_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 second paper trade handoff dry-run payload audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id. Defaults to latest second-trade route report cycle.")
    args = parser.parse_args(argv)

    settings = LSRV2SecondTradeHandoffDryRunSettings(data_dir=str(Path(args.data_dir)))
    report = build_lsr_v2_second_trade_handoff_dry_run_report_from_files(
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
        "second_trade_eligible": report.get("second_trade_eligible"),
        "second_trade_rearm_ready": report.get("second_trade_rearm_ready"),
        "second_trade_route_preflight_ready": report.get("second_trade_route_preflight_ready"),
        "second_trade_order_intent_ready": report.get("second_trade_order_intent_ready"),
        "second_trade_order_intent_events": report.get("second_trade_order_intent_events"),
        "creatable_order_intents": report.get("creatable_order_intents"),
        "handoff_dry_run_events": report.get("handoff_dry_run_events"),
        "payload_valid_count": report.get("payload_valid_count"),
        "payload_invalid_count": report.get("payload_invalid_count"),
        "would_create_paper_order_count": report.get("would_create_paper_order_count"),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_second_trade_handoff": False,
        "paper_broker_adapter": report.get("paper_broker_adapter"),
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "orders_submitted_by_second_trade_handoff": 0,
        "positions_opened_by_second_trade_handoff": 0,
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "paper_order_submission_enabled": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "blockers": report.get("blockers"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
