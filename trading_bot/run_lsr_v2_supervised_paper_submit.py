#!/usr/bin/env python
"""Prompt 29.4.4s-10j — LSR-v2 supervised paper submit boundary runner.

Reads the latest LSR-v2 submit preflight and evaluates the single-order gate.
The CLI never wires a real paper broker submitter, so even when armed it can
only return READY_ARMED.  A later supervised runtime patch may inject a
paper-only submitter explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from core.lsr_v2_supervised_paper_submit import (  # type: ignore
        LSRV2SupervisedPaperSubmitSettings,
        build_lsr_v2_supervised_paper_submit_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_supervised_paper_submit import (  # type: ignore
        LSRV2SupervisedPaperSubmitSettings,
        build_lsr_v2_supervised_paper_submit_report_from_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 supervised paper submit boundary, disabled by default")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id; defaults to latest submit-preflight cycle")
    args = parser.parse_args(argv)

    settings = LSRV2SupervisedPaperSubmitSettings.from_env(data_dir=str(Path(args.data_dir)))
    report = build_lsr_v2_supervised_paper_submit_report_from_files(
        data_dir=Path(args.data_dir),
        cycle_id=str(args.cycle_id or ""),
        settings=settings,
        paper_submitter=None,
    )
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "submit_preflight_events": report.get("submit_preflight_events"),
        "submit_boundary_events": report.get("submit_boundary_events"),
        "submit_ready_count": report.get("submit_ready_count"),
        "submit_armed": report.get("submit_armed"),
        "submit_confirmation_ok": report.get("submit_confirmation_ok"),
        "max_orders": report.get("max_orders"),
        "would_submit_count": report.get("would_submit_count"),
        "would_submit_to_paper_broker_count": report.get("would_submit_to_paper_broker_count"),
        "broker_submit_called": report.get("broker_submit_called"),
        "orders_submitted_by_lsr_v2_submit": report.get("orders_submitted_by_lsr_v2_submit"),
        "positions_opened_by_lsr_v2_submit": report.get("positions_opened_by_lsr_v2_submit"),
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
