#!/usr/bin/env python
"""Prompt 29.4.4s-10k — first supervised LSR-v2 paper-only submit runner.

The runner is disabled by default.  It wires PaperBrokerAdapter only when:

* LSR_V2_PAPER_SUBMIT_ARM=1
* LSR_V2_PAPER_SUBMIT_CONFIRMATION=I_UNDERSTAND_SINGLE_PAPER_ORDER
* LSR_V2_PAPER_SUBMIT_EXECUTE=1
* LSR_V2_PAPER_SUBMIT_EXECUTE_CONFIRMATION=I_UNDERSTAND_EXECUTE_ONE_PAPER_ORDER_ONLY
* LSR_V2_PAPER_SUBMIT_MAX_ORDERS=1

No live/testnet/exchange broker path is ever wired.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_supervised_paper_submit_execution import (  # type: ignore
        LSRV2SupervisedPaperSubmitExecutionSettings,
        build_lsr_v2_supervised_paper_submit_execution_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_supervised_paper_submit_execution import (  # type: ignore
        LSRV2SupervisedPaperSubmitExecutionSettings,
        build_lsr_v2_supervised_paper_submit_execution_report_from_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 first supervised paper-only submit boundary")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    settings = LSRV2SupervisedPaperSubmitExecutionSettings.from_env(data_dir=str(data_dir))
    allow_project_submitter = bool(settings.execute_armed and settings.execute_confirmation_ok)
    report = build_lsr_v2_supervised_paper_submit_execution_report_from_files(
        data_dir=data_dir,
        cycle_id=str(args.cycle_id or ""),
        execution_settings=settings,
        paper_submitter=None,
        allow_project_submitter=allow_project_submitter,
    )
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "submit_preflight_events": report.get("submit_preflight_events"),
        "execution_events": report.get("execution_events"),
        "submit_armed": report.get("submit_armed"),
        "submit_confirmation_ok": report.get("submit_confirmation_ok"),
        "execute_armed": report.get("execute_armed"),
        "execute_confirmation_ok": report.get("execute_confirmation_ok"),
        "submit_ready_count": report.get("submit_ready_count"),
        "would_submit_count": report.get("would_submit_count"),
        "would_submit_to_paper_broker_count": report.get("would_submit_to_paper_broker_count"),
        "broker_submit_called": report.get("broker_submit_called"),
        "orders_submitted_by_lsr_v2_execution": report.get("orders_submitted_by_lsr_v2_execution"),
        "positions_opened_by_lsr_v2_execution": report.get("positions_opened_by_lsr_v2_execution"),
        "paper_state_clean": report.get("paper_state_clean"),
        "routing_enabled": report.get("routing_enabled"),
        "execution_enabled": report.get("execution_enabled"),
        "paper_order_submission_enabled": report.get("paper_order_submission_enabled"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "promotion_ready": report.get("promotion_ready"),
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
