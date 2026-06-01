from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_supervised_paper_close_preflight import build_lsr_v2_supervised_paper_close_preflight_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_supervised_paper_close_preflight import build_lsr_v2_supervised_paper_close_preflight_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 supervised paper close preflight / TP-hit close boundary")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_supervised_paper_close_preflight_report_from_files(data_dir=args.data_dir, cycle_id=args.cycle_id)
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "monitor_events": report.get("monitor_events"),
        "close_preflight_events": report.get("close_preflight_events"),
        "open_lsr_v2_position_count": report.get("open_lsr_v2_position_count"),
        "close_required_diagnostic_count": report.get("close_required_diagnostic_count"),
        "take_profit_hit_diagnostic_count": report.get("take_profit_hit_diagnostic_count"),
        "stop_hit_diagnostic_count": report.get("stop_hit_diagnostic_count"),
        "would_prepare_close_count": report.get("would_prepare_close_count"),
        "would_close_position_count": report.get("would_close_position_count"),
        "close_enabled": report.get("close_enabled"),
        "close_confirmation_ok": report.get("close_confirmation_ok"),
        "broker_close_called": report.get("broker_close_called"),
        "orders_submitted_by_close_preflight": report.get("orders_submitted_by_close_preflight"),
        "positions_closed_by_close_preflight": report.get("positions_closed_by_close_preflight"),
        "automatic_close_enabled": report.get("automatic_close_enabled"),
        "automatic_reentry_enabled": report.get("automatic_reentry_enabled"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "promotion_ready": report.get("promotion_ready"),
        "symbols": report.get("symbols"),
        "close_reasons": report.get("close_reasons"),
        "total_notional": report.get("total_notional"),
        "total_risk_amount": report.get("total_risk_amount"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
