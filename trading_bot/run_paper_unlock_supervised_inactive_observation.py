from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_supervised_inactive_observation import (
    PaperUnlockSupervisedInactiveObservationSettings,
    run_paper_unlock_supervised_inactive_observation_loop,
    write_paper_unlock_supervised_inactive_observation_report,
)


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prompt 29.4.4s-OBS supervised inactive observation / candidate exposure monitor")
    parser.add_argument("--duration-hours", type=float, default=4.0, help="Observation duration. Default: 4h.")
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


def _settings_from_args(args: argparse.Namespace) -> PaperUnlockSupervisedInactiveObservationSettings:
    base = PaperUnlockSupervisedInactiveObservationSettings.from_config()
    return PaperUnlockSupervisedInactiveObservationSettings(
        report_name=base.report_name,
        events_name=base.events_name,
        max_event_lines=base.max_event_lines,
        duration_hours=args.duration_hours,
        interval_seconds=args.interval_seconds,
        max_cycles=max(0, int(args.max_cycles)),
        timeframe=args.timeframe,
        cost_model=args.cost_model,
        balance=args.balance,
        poll_seconds=args.poll_seconds,
        paper_unlock=not args.no_paper_unlock,
        log_dir_name=base.log_dir_name,
        run_command_timeout_seconds=base.run_command_timeout_seconds,
    )


def _summary_payload(report: dict) -> dict:
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    return {
        "status": report.get("status"),
        "decision": decision.get("status"),
        "latest_cycle_id": decision.get("latest_cycle_id"),
        "completed_cycle_count": decision.get("completed_cycle_count"),
        "candidate_ready_count": decision.get("candidate_ready_count"),
        "would_create_order_count": decision.get("would_create_order_count"),
        "candidate_exposure_count": decision.get("candidate_exposure_count"),
        "supervised_execution_events": decision.get("supervised_execution_events"),
        "supervised_submit_allowed_count": decision.get("supervised_submit_allowed_count"),
        "supervised_broker_submit_called_count": decision.get("supervised_broker_submit_called_count"),
        "broker_submit_called_count": decision.get("broker_submit_called_count"),
        "orders_submitted_by_supervised": decision.get("orders_submitted_by_supervised"),
        "positions_opened_by_supervised": decision.get("positions_opened_by_supervised"),
        "orders_submitted": decision.get("orders_submitted"),
        "positions_opened": decision.get("positions_opened"),
        "operator_enable": decision.get("operator_enable"),
        "operator_confirmation_ok": decision.get("operator_confirmation_ok"),
        "legacy_order_leakage_detected": decision.get("legacy_order_leakage_detected"),
        "unauthorized_orders_count": decision.get("unauthorized_orders_count"),
        "unauthorized_positions_opened_count": decision.get("unauthorized_positions_opened_count"),
        "blocked_legacy_order_attempts": decision.get("blocked_legacy_order_attempts"),
        "report": "data\\paper_unlock_supervised_inactive_observation_report.json",
    }


def main() -> None:
    args = build_parser().parse_args()
    settings = _settings_from_args(args)
    if args.report_only:
        report = write_paper_unlock_supervised_inactive_observation_report(
            "data",
            started_at=_parse_dt(args.started_at),
            ended_at=_parse_dt(args.ended_at),
            settings=settings,
        )
    else:
        report = run_paper_unlock_supervised_inactive_observation_loop(
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
