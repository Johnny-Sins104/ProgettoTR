#!/usr/bin/env python
"""Prompt 29.4.4s-10x — LSR-v2 second trade submit boundary runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_second_trade_submit_boundary import (  # type: ignore
        LSRV2SecondTradeSubmitBoundarySettings,
        build_lsr_v2_second_trade_submit_boundary_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_second_trade_submit_boundary import (  # type: ignore
        LSRV2SecondTradeSubmitBoundarySettings,
        build_lsr_v2_second_trade_submit_boundary_report_from_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 second paper trade submit boundary")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id. Defaults to latest second-trade submit-preflight report cycle.")
    args = parser.parse_args(argv)

    settings = LSRV2SecondTradeSubmitBoundarySettings.from_env(data_dir=str(Path(args.data_dir)))
    report = build_lsr_v2_second_trade_submit_boundary_report_from_files(
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
        "submit_preflight_pass": report.get("submit_preflight_pass"),
        "submit_preflight_events": report.get("submit_preflight_events"),
        "submit_boundary_events": report.get("submit_boundary_events"),
        "second_trade_submit_ready_count": report.get("second_trade_submit_ready_count"),
        "second_trade_submit_armed": report.get("second_trade_submit_armed"),
        "second_trade_submit_confirmation_ok": report.get("second_trade_submit_confirmation_ok"),
        "second_trade_submit_enabled": False,
        "second_trade_execute_enabled": False,
        "paper_order_submission_enabled": False,
        "routing_enabled": False,
        "execution_enabled": False,
        "would_submit_count": 0,
        "would_submit_to_paper_broker_count": 0,
        "broker_submit_called": False,
        "broker_submit_called_by_second_trade_submit_boundary": False,
        "orders_submitted_by_second_trade_submit_boundary": 0,
        "positions_opened_by_second_trade_submit_boundary": 0,
        "positions_closed_by_second_trade_submit_boundary": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "state_open_lsr_v2_positions": report.get("state_open_lsr_v2_positions"),
        "max_orders": report.get("max_orders"),
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "promotion_ready": False,
        "blockers": report.get("blockers"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
