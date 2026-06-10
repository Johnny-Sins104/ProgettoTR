from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.strategy_runtime.selected_strategy_shadow_diagnostics import build_selected_strategy_shadow_stats
from trading_bot.strategy_runtime.selected_strategy_shadow_journal import (
    append_shadow_event,
    build_shadow_journal_event,
    journal_path,
    read_shadow_events,
)
from trading_bot.strategy_runtime.strategy_shadow_report import build_shadow_report


def selected_strategy_shadow_report_path(data_dir: Path) -> Path:
    return data_dir / "selected_strategy_shadow_signal_report.json"


def build_and_write_journal_report(
    *,
    data_dir: Path,
    asset: str = "XRP/USDT",
    timeframe: str = "5m",
    max_rows: int = 500,
) -> dict:
    shadow = build_shadow_report(data_dir=data_dir, asset=asset, timeframe=timeframe, max_rows=max_rows)
    event = build_shadow_journal_event(
        execution_report={
            "active_strategy": shadow.get("active_strategy"),
            "active_strategy_label": shadow.get("active_strategy_label"),
            "signal": shadow.get("signal"),
        },
        asset=asset,
        timeframe=timeframe,
    )
    append_result = append_shadow_event(data_dir, event)
    if append_result.get("status") != "OK":
        report = {
            "status": "FAIL",
            "decision": "SELECTED_STRATEGY_SHADOW_SIGNAL_JOURNAL_BLOCKED",
            "reason": append_result.get("reason", "shadow_journal_not_writable"),
            "shadow_journal_available": False,
            "shadow_events_recorded": len(read_shadow_events(data_dir)),
            "latest_shadow_signal_available": False,
            "selected_strategy_only_confirmed": shadow.get("single_strategy_execution_confirmed") is True,
            "outcome_tracking_scaffold_available": True,
            "shadow_only": True,
            "would_trade": False,
            "can_trade": False,
            "paper_trading_activation_allowed": False,
            "broker_submit_allowed": False,
            "broker_close_allowed": False,
            "live_trading_allowed": False,
            "testnet_allowed": False,
            "would_submit": False,
            "would_close": False,
        }
        return report

    events = read_shadow_events(data_dir)
    stats = build_selected_strategy_shadow_stats(data_dir, strategy=str(event.get("active_strategy")))
    report = {
        "status": "PASS",
        "decision": "SELECTED_STRATEGY_SHADOW_SIGNAL_JOURNAL_READY",
        "active_strategy": event.get("active_strategy"),
        "active_strategy_label": event.get("active_strategy_label"),
        "shadow_journal_available": journal_path(data_dir).exists(),
        "shadow_events_recorded": len(events),
        "latest_shadow_signal_available": True,
        "latest_signal": event.get("signal"),
        "latest_score": event.get("score"),
        "latest_shadow_event": event,
        "selected_strategy_shadow_stats": stats,
        "outcome_tracking_status": "SCAFFOLD_ONLY",
        "outcome_tracking_scaffold": event.get("outcome_tracking"),
        "selected_strategy_only_confirmed": shadow.get("single_strategy_execution_confirmed") is True,
        "outcome_tracking_scaffold_available": True,
        "shadow_only": True,
        "would_trade": False,
        "can_trade": False,
        "paper_trading_activation_allowed": False,
        "broker_submit_allowed": False,
        "broker_close_allowed": False,
        "live_trading_allowed": False,
        "testnet_allowed": False,
        "would_submit": False,
        "would_close": False,
    }
    output = selected_strategy_shadow_report_path(data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def runner_view(report: dict) -> dict:
    keys = [
        "status",
        "decision",
        "active_strategy",
        "shadow_journal_available",
        "shadow_events_recorded",
        "latest_shadow_signal_available",
        "selected_strategy_only_confirmed",
        "outcome_tracking_scaffold_available",
        "shadow_only",
        "paper_trading_activation_allowed",
        "broker_submit_allowed",
        "broker_close_allowed",
        "live_trading_allowed",
        "testnet_allowed",
        "would_submit",
        "would_close",
    ]
    return {key: report.get(key) for key in keys}


def main() -> int:
    parser = argparse.ArgumentParser(description="Append selected-strategy shadow signal to diagnostic journal.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--asset", default="XRP/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--max-rows", type=int, default=500)
    args = parser.parse_args()
    report = build_and_write_journal_report(
        data_dir=Path(args.data_dir),
        asset=args.asset,
        timeframe=args.timeframe,
        max_rows=args.max_rows,
    )
    print(json.dumps(runner_view(report), indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
