from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from trading_bot.core.lsr_v2_second_open_position_monitor import build_lsr_v2_second_open_position_monitor_report_from_files
except Exception:  # pragma: no cover
    from core.lsr_v2_second_open_position_monitor import build_lsr_v2_second_open_position_monitor_report_from_files  # type: ignore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 second open position monitor / SL-TP tracking audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args(argv)
    report = build_lsr_v2_second_open_position_monitor_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    keys = [
        "status", "decision", "cycle_id", "event_source", "strict_cycle_scope",
        "second_trade_position_open", "open_second_lsr_v2_position_count", "state_open_lsr_v2_positions",
        "paper_state_consistency", "paper_status_consistency", "paper_status_open_positions", "paper_status_pending_orders",
        "symbols", "sides", "current_statuses", "entry_prices", "current_prices", "stop_losses", "take_profits",
        "risk_multiple_current_avg", "risk_multiple_max_seen", "risk_multiple_min_seen", "unrealized_pnl_total",
        "stop_hit_diagnostic_count", "take_profit_hit_diagnostic_count", "close_required_diagnostic",
        "close_required_diagnostic_count", "orders_submitted_by_second_open_position_monitor",
        "positions_opened_by_second_open_position_monitor", "positions_closed_by_second_open_position_monitor",
        "broker_submit_called_by_second_open_position_monitor", "broker_close_called_by_second_open_position_monitor",
        "automatic_close_enabled", "automatic_reentry_enabled", "live_enabled", "testnet_enabled",
        "exchange_broker_enabled", "operational_unlock_allowed", "promotion_ready", "report", "jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in keys if k in report}, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if report.get("status") == "FAIL" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
