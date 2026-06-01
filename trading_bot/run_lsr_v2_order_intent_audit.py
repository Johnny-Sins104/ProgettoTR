#!/usr/bin/env python
"""Prompt 29.4.4s-10g — LSR-v2 paper order intent audit runner.

Reads the latest cycle-scoped LSR-v2 runtime bridge events and writes a
fail-closed order-intent preflight report.  It never submits orders or calls a
broker.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from core.lsr_v2_order_intent_audit import (  # type: ignore
        LSRV2OrderIntentAuditSettings,
        build_lsr_v2_order_intent_report_from_files,
    )
except Exception:
    from trading_bot.core.lsr_v2_order_intent_audit import (  # type: ignore
        LSRV2OrderIntentAuditSettings,
        build_lsr_v2_order_intent_report_from_files,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 fail-closed paper order intent audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id. Defaults to latest CYCLE_COMPLETED in paper_events.jsonl.")
    parser.add_argument("--account-equity", type=float, default=1000.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.0025)
    args = parser.parse_args(argv)

    settings = LSRV2OrderIntentAuditSettings(
        data_dir=str(Path(args.data_dir)),
        account_equity=float(args.account_equity),
        risk_per_trade_pct=float(args.risk_per_trade_pct),
    )
    report = build_lsr_v2_order_intent_report_from_files(
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
        "runtime_candidate_events": report.get("runtime_candidate_events"),
        "runtime_candidate_ready_events": report.get("runtime_candidate_ready_events"),
        "runtime_bridge_events": report.get("runtime_bridge_events"),
        "would_route_count": report.get("would_route_count"),
        "order_intent_events": report.get("order_intent_events"),
        "would_create_order_count": report.get("would_create_order_count"),
        "would_submit_count": 0,
        "risk_per_trade_pct": report.get("risk_per_trade_pct"),
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "orders_submitted_by_lsr_v2_order_intent": 0,
        "positions_opened_by_lsr_v2_order_intent": 0,
        "broker_submit_called": False,
        "execution_enabled": False,
        "routing_enabled": False,
        "paper_order_submission_enabled": False,
        "promotion_ready": False,
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
