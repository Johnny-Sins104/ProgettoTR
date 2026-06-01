from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from core.lsr_v2_open_position_monitor import build_lsr_v2_open_position_monitor_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_open_position_monitor import build_lsr_v2_open_position_monitor_report_from_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run LSR-v2 open position monitor / SL-TP tracking audit.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args(argv)
    report = build_lsr_v2_open_position_monitor_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    summary_keys = [
        "status",
        "decision",
        "cycle_id",
        "event_source",
        "strict_cycle_scope",
        "monitor_events",
        "open_lsr_v2_position_count",
        "state_open_lsr_v2_positions",
        "paper_status_open_positions",
        "paper_state_consistency",
        "paper_status_consistency",
        "symbols",
        "sides",
        "current_statuses",
        "current_prices",
        "entry_prices",
        "stop_losses",
        "take_profits",
        "unrealized_pnl_total",
        "risk_multiple_current_avg",
        "risk_multiple_min_seen",
        "risk_multiple_max_seen",
        "stop_hit_diagnostic_count",
        "take_profit_hit_diagnostic_count",
        "close_required_diagnostic_count",
        "close_required_diagnostic",
        "total_notional",
        "total_risk_amount",
        "orders_submitted_by_open_position_monitor",
        "positions_opened_by_open_position_monitor",
        "broker_submit_called_by_open_position_monitor",
        "automatic_close_enabled",
        "automatic_reentry_enabled",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "report",
        "jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in summary_keys if k in report}, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
