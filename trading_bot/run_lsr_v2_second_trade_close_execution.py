from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_second_trade_close_execution import build_lsr_v2_second_trade_close_execution_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_second_trade_close_execution import build_lsr_v2_second_trade_close_execution_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 second supervised paper close execution / single-position TP close")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_second_trade_close_execution_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "close_enabled": report.get("close_enabled"),
        "close_confirmation_ok": report.get("close_confirmation_ok"),
        "max_positions": report.get("max_positions"),
        "close_preflight_events": report.get("close_preflight_events"),
        "close_required_diagnostic_count": report.get("close_required_diagnostic_count"),
        "close_execution_events": report.get("close_execution_events"),
        "positions_closed_by_second_trade_close_execution": report.get("positions_closed_by_second_trade_close_execution"),
        "orders_submitted_by_second_trade_close_execution": report.get("orders_submitted_by_second_trade_close_execution"),
        "positions_opened_by_second_trade_close_execution": report.get("positions_opened_by_second_trade_close_execution"),
        "broker_close_called": report.get("broker_close_called"),
        "paper_close_called": report.get("paper_close_called"),
        "paper_state_modified": report.get("paper_state_modified"),
        "paper_status_modified": report.get("paper_status_modified"),
        "backup_state_path": report.get("backup_state_path"),
        "backup_status_path": report.get("backup_status_path"),
        "open_second_lsr_v2_positions_before": report.get("open_second_lsr_v2_positions_before"),
        "open_second_lsr_v2_positions_after": report.get("open_second_lsr_v2_positions_after"),
        "paper_status_open_positions_after": report.get("paper_status_open_positions_after"),
        "symbols": report.get("symbols"),
        "sides": report.get("sides"),
        "close_reasons": report.get("close_reasons"),
        "total_notional": report.get("total_notional"),
        "total_risk_amount": report.get("total_risk_amount"),
        "realized_pnl_total": report.get("realized_pnl_total"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "promotion_ready": report.get("promotion_ready"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
