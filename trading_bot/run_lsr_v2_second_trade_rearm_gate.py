#!/usr/bin/env python
"""Prompt 29.4.4s-10t — LSR-v2 second-trade controlled re-arm gate runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_second_trade_rearm_gate import build_lsr_v2_second_trade_rearm_gate_report_from_files  # type: ignore
except Exception:
    from trading_bot.core.lsr_v2_second_trade_rearm_gate import build_lsr_v2_second_trade_rearm_gate_report_from_files  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 second supervised paper trade controlled re-arm gate")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id; defaults to latest paper_events cycle or eligibility cycle")
    args = parser.parse_args()

    report = build_lsr_v2_second_trade_rearm_gate_report_from_files(data_dir=Path(args.data_dir), cycle_id=str(args.cycle_id or ""))
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "second_trade_eligible": report.get("second_trade_eligible"),
        "second_trade_rearm_enabled": report.get("second_trade_rearm_enabled"),
        "second_trade_rearm_confirmation_ok": report.get("second_trade_rearm_confirmation_ok"),
        "candidate_wait_gate_ready": report.get("candidate_wait_gate_ready"),
        "second_trade_rearm_ready": report.get("second_trade_rearm_ready"),
        "runtime_candidate_events": report.get("runtime_candidate_events"),
        "runtime_candidate_ready_events": report.get("runtime_candidate_ready_events"),
        "runtime_bridge_events": report.get("runtime_bridge_events"),
        "runtime_would_route_count": report.get("runtime_would_route_count"),
        "order_intent_events": report.get("order_intent_events"),
        "handoff_dry_run_events": report.get("handoff_dry_run_events"),
        "submit_preflight_events": report.get("submit_preflight_events"),
        "submit_boundary_events": report.get("submit_boundary_events"),
        "second_trade_execute_enabled": False,
        "second_trade_submit_enabled": False,
        "paper_order_submission_enabled": False,
        "broker_submit_called_by_second_trade_rearm_gate": False,
        "orders_submitted_by_second_trade_rearm_gate": 0,
        "positions_opened_by_second_trade_rearm_gate": 0,
        "positions_closed_by_second_trade_rearm_gate": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "promotion_ready": False,
        "state_open_lsr_v2_positions": report.get("state_open_lsr_v2_positions"),
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "blockers": report.get("blockers"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
