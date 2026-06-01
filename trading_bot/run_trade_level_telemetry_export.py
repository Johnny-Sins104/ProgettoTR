from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "trading_bot") not in sys.path:
    sys.path.insert(0, str(ROOT / "trading_bot"))

from core.equity_forensics import EquityForensicsSettings, write_equity_forensics_report
from core.trade_level_telemetry import TradeTelemetrySettings, export_trade_level_telemetry


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt 29.4.4s-5 trade-level telemetry + equity forensics export")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--event-log-name", default="paper_events.jsonl")
    parser.add_argument("--max-event-lines", type=int, default=250000)
    parser.add_argument("--fee-rate", type=float, default=0.0004)
    parser.add_argument("--spread-bps", type=float, default=0.0)
    parser.add_argument("--slippage-bps", type=float, default=0.0)
    parser.add_argument("--starting-equity", type=float, default=1000.0)
    parser.add_argument("--exclude-open-positions", action="store_true")
    args = parser.parse_args()

    telemetry_settings = TradeTelemetrySettings(
        data_dir=args.data_dir,
        event_log_name=args.event_log_name,
        max_event_lines=args.max_event_lines,
        fee_rate_default=args.fee_rate,
        spread_bps_default=args.spread_bps,
        slippage_bps_default=args.slippage_bps,
        include_open_positions=not bool(args.exclude_open_positions),
    )
    telemetry = export_trade_level_telemetry(telemetry_settings)
    equity = write_equity_forensics_report(
        EquityForensicsSettings(
            data_dir=args.data_dir,
            starting_equity=args.starting_equity,
            max_trade_lines=args.max_event_lines,
        )
    )
    summary = {
        "status": telemetry.get("status"),
        "decision": telemetry.get("decision"),
        "closed_trades": telemetry.get("closed_trades"),
        "trade_level_rows": telemetry.get("trade_level_rows"),
        "events_scanned": telemetry.get("events_scanned"),
        "trade_jsonl": telemetry.get("trade_jsonl"),
        "trade_level_report": telemetry.get("report"),
        "equity_forensics_report": equity.get("report"),
        "equity_max_drawdown_pct": equity.get("max_drawdown_pct"),
        "orders_submitted_by_telemetry": telemetry.get("orders_submitted_by_telemetry", 0),
        "positions_opened_by_telemetry": telemetry.get("positions_opened_by_telemetry", 0),
        "promotion_ready": False,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
