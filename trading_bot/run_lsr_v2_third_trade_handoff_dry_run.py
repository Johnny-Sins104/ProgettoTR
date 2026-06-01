#!/usr/bin/env python
"""Prompt 29.4.4s-10al — LSR-v2 third-trade handoff dry-run runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_third_trade_handoff_dry_run import build_lsr_v2_third_trade_handoff_dry_run_report_from_files  # type: ignore
except Exception:
    from trading_bot.core.lsr_v2_third_trade_handoff_dry_run import build_lsr_v2_third_trade_handoff_dry_run_report_from_files  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 third supervised paper trade handoff dry-run")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id; defaults to route preflight report cycle")
    args = parser.parse_args()

    report = build_lsr_v2_third_trade_handoff_dry_run_report_from_files(
        data_dir=Path(args.data_dir),
        cycle_id=str(args.cycle_id or ""),
    )
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "third_trade_eligible": report.get("third_trade_eligible"),
        "third_trade_rearm_ready": report.get("third_trade_rearm_ready"),
        "third_trade_route_preflight_ready": report.get("third_trade_route_preflight_ready"),
        "third_trade_order_intent_ready": report.get("third_trade_order_intent_ready"),
        "third_trade_order_intent_events": report.get("third_trade_order_intent_events"),
        "creatable_order_intents": report.get("creatable_order_intents"),
        "handoff_dry_run_events": report.get("handoff_dry_run_events"),
        "payload_valid_count": report.get("payload_valid_count"),
        "payload_invalid_count": report.get("payload_invalid_count"),
        "would_create_paper_order_count": report.get("would_create_paper_order_count"),
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_third_trade_handoff": False,
        "paper_broker_adapter": report.get("paper_broker_adapter"),
        "third_trade_submit_enabled": False,
        "third_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "orders_submitted_by_third_trade_handoff": 0,
        "positions_opened_by_third_trade_handoff": 0,
        "positions_closed_by_third_trade_handoff": 0,
        "paper_state_modified_by_third_trade_handoff": False,
        "paper_status_modified_by_third_trade_handoff": False,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "blockers": report.get("blockers"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
