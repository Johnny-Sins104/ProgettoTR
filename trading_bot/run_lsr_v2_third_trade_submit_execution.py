#!/usr/bin/env python
"""Prompt 29.4.4s-10ao — LSR-v2 third supervised paper submit execution runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_third_trade_submit_execution import (  # type: ignore
        LSRV2ThirdTradeSubmitExecutionSettings,
        build_lsr_v2_third_trade_submit_execution_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_third_trade_submit_execution import (  # type: ignore
        LSRV2ThirdTradeSubmitExecutionSettings,
        build_lsr_v2_third_trade_submit_execution_report_from_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 third supervised paper-only submit execution")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id. Defaults to latest third-trade submit-boundary cycle.")
    args = parser.parse_args(argv)

    settings = LSRV2ThirdTradeSubmitExecutionSettings.from_env(data_dir=str(Path(args.data_dir)))
    allow_project_submitter = bool(settings.execute_armed and settings.execute_confirmation_ok)
    report = build_lsr_v2_third_trade_submit_execution_report_from_files(
        data_dir=args.data_dir,
        cycle_id=str(args.cycle_id or ""),
        settings=settings,
        allow_project_submitter=allow_project_submitter,
    )
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "boundary_report_ready": report.get("boundary_report_ready"),
        "third_trade_submit_ready_count": report.get("third_trade_submit_ready_count"),
        "third_trade_submit_armed": report.get("third_trade_submit_armed"),
        "third_trade_submit_confirmation_ok": report.get("third_trade_submit_confirmation_ok"),
        "third_trade_execute_armed": report.get("third_trade_execute_armed"),
        "third_trade_execute_confirmation_ok": report.get("third_trade_execute_confirmation_ok"),
        "execution_events": report.get("execution_events"),
        "would_submit_count": report.get("would_submit_count"),
        "would_submit_to_paper_broker_count": report.get("would_submit_to_paper_broker_count"),
        "broker_submit_called": report.get("broker_submit_called"),
        "broker_submit_called_by_third_trade_execution": report.get("broker_submit_called_by_third_trade_execution"),
        "orders_submitted_by_third_trade_execution": report.get("orders_submitted_by_third_trade_execution"),
        "positions_opened_by_third_trade_execution": report.get("positions_opened_by_third_trade_execution"),
        "positions_closed_by_third_trade_execution": report.get("positions_closed_by_third_trade_execution"),
        "paper_order_submission_enabled": report.get("paper_order_submission_enabled"),
        "routing_enabled": report.get("routing_enabled"),
        "execution_enabled": report.get("execution_enabled"),
        "third_trade_execute_enabled": report.get("third_trade_execute_enabled"),
        "third_trade_submit_enabled": report.get("third_trade_submit_enabled"),
        "paper_state_clean": report.get("paper_state_clean"),
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "max_orders": report.get("max_orders"),
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "promotion_ready": report.get("promotion_ready"),
        "blockers": report.get("blockers"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
