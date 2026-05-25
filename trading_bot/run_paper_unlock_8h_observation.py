from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_observation import (
    PaperUnlockObservationSettings,
    run_paper_unlock_observation_loop,
    write_paper_unlock_observation_report,
)

REPORT_NAME = "paper_unlock_8h_dry_run_observation_report.json"


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt 29.4.4r-OBS 8h paper-only audit/dry-run observation run")
    parser.add_argument("--duration-hours", type=float, default=8.0, help="Observation duration. Default: 8h.")
    parser.add_argument("--interval-seconds", type=float, default=300.0, help="Delay between once-cycles. Default: 300s.")
    parser.add_argument("--max-cycles", type=int, default=0, help="Optional hard cap. 0 means duration-based only.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--cost-model", choices=["base", "conservative", "severe"], default="conservative")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--report-only", action="store_true", help="Only aggregate existing paper_events.jsonl, do not launch cycles.")
    parser.add_argument("--started-at", default="", help="Optional ISO UTC window start for --report-only.")
    parser.add_argument("--ended-at", default="", help="Optional ISO UTC window end for --report-only.")
    parser.add_argument("--no-paper-unlock", action="store_true", help="Run observation cycles without --paper-unlock.")
    return parser


def _settings_from_args(args: argparse.Namespace) -> PaperUnlockObservationSettings:
    base = PaperUnlockObservationSettings.from_config()
    return PaperUnlockObservationSettings(
        report_name=REPORT_NAME,
        events_name=base.events_name,
        max_event_lines=max(base.max_event_lines, 100000),
        duration_hours=args.duration_hours,
        interval_seconds=args.interval_seconds,
        max_cycles=max(0, int(args.max_cycles)),
        timeframe=args.timeframe,
        cost_model=args.cost_model,
        balance=args.balance,
        poll_seconds=args.poll_seconds,
        paper_unlock=not args.no_paper_unlock,
        log_dir_name="paper_unlock_8h_observation_logs",
        run_command_timeout_seconds=base.run_command_timeout_seconds,
    )


def _summary_payload(report: dict) -> dict:
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    return {
        "status": report.get("status"),
        "decision": decision.get("status"),
        "latest_cycle_id": decision.get("latest_cycle_id"),
        "completed_cycle_count": decision.get("completed_cycle_count"),
        "runtime_audit_events": decision.get("runtime_audit_events"),
        "runtime_accepts_diagnostic": decision.get("runtime_accepts_diagnostic"),
        "runtime_rejects": decision.get("runtime_rejects"),
        "routing_bridge_events": decision.get("routing_bridge_events"),
        "would_submit_count": decision.get("would_submit_count"),
        "candidate_order_audit_events": decision.get("candidate_order_audit_events"),
        "candidate_ready_count": decision.get("candidate_ready_count"),
        "handoff_dry_run_events": decision.get("handoff_dry_run_events"),
        "would_create_order_count": decision.get("would_create_order_count"),
        "broker_submit_called_count": decision.get("broker_submit_called_count"),
        "legacy_order_leakage_detected": decision.get("legacy_order_leakage_detected"),
        "unauthorized_orders_count": decision.get("unauthorized_orders_count"),
        "unauthorized_positions_opened_count": decision.get("unauthorized_positions_opened_count"),
        "blocked_legacy_order_attempts": decision.get("blocked_legacy_order_attempts"),
        "handoff_coverage_ok": decision.get("handoff_coverage_ok"),
        "orders_submitted": decision.get("orders_submitted"),
        "positions_opened": decision.get("positions_opened"),
        "orders_submitted_by_bridge": decision.get("orders_submitted_by_bridge"),
        "orders_submitted_by_candidate_audit": decision.get("orders_submitted_by_candidate_audit"),
        "orders_submitted_by_handoff": decision.get("orders_submitted_by_handoff"),
        "positions_opened_by_handoff": decision.get("positions_opened_by_handoff"),
        "operational_unlock_allowed": decision.get("operational_unlock_allowed"),
        "report": "data\\paper_unlock_8h_dry_run_observation_report.json",
    }


def main() -> None:
    args = build_parser().parse_args()
    settings = _settings_from_args(args)

    if args.report_only:
        report = write_paper_unlock_observation_report(
            "data",
            started_at=_parse_dt(args.started_at),
            ended_at=_parse_dt(args.ended_at),
            settings=settings,
        )
    else:
        report = run_paper_unlock_observation_loop(
            Path("."),
            settings=settings,
            duration_hours=args.duration_hours,
            interval_seconds=args.interval_seconds,
            max_cycles=max(0, int(args.max_cycles)),
            symbols=args.symbols,
        )
    print(json.dumps(_summary_payload(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
