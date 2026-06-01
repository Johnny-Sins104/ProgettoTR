from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _bootstrap_imports() -> None:
    here = Path(__file__).resolve()
    root = here.parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_bootstrap_imports()

try:
    from trading_bot.core.lsr_v2_second_trade_position_lifecycle import (  # type: ignore
        build_lsr_v2_second_trade_position_lifecycle_report_from_files,
    )
except Exception:  # pragma: no cover
    from core.lsr_v2_second_trade_position_lifecycle import (  # type: ignore
        build_lsr_v2_second_trade_position_lifecycle_report_from_files,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LSR-v2 second trade position lifecycle audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="")
    args = parser.parse_args()
    report = build_lsr_v2_second_trade_position_lifecycle_report_from_files(
        data_dir=args.data_dir,
        cycle_id=args.cycle_id,
    )
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "second_trade_execution_events": report.get("second_trade_execution_events"),
        "lifecycle_events": report.get("lifecycle_events"),
        "matching_order_count": report.get("matching_order_count"),
        "matching_position_count": report.get("matching_position_count"),
        "second_trade_position_open": report.get("second_trade_position_open"),
        "open_lsr_v2_position_count": report.get("open_lsr_v2_position_count"),
        "closed_lsr_v2_position_count": report.get("closed_lsr_v2_position_count"),
        "state_open_lsr_v2_positions": report.get("state_open_lsr_v2_positions"),
        "paper_status_open_positions": report.get("paper_status_open_positions"),
        "paper_status_pending_orders": report.get("paper_status_pending_orders"),
        "paper_state_consistency": report.get("paper_state_consistency"),
        "paper_status_consistency": report.get("paper_status_consistency"),
        "third_submit_or_reentry_detected": report.get("third_submit_or_reentry_detected"),
        "duplicate_position_check": report.get("duplicate_position_check"),
        "max_positions_check": report.get("max_positions_check"),
        "symbols": report.get("symbols"),
        "sides": report.get("sides"),
        "current_statuses": report.get("current_statuses"),
        "total_risk_amount": report.get("total_risk_amount"),
        "total_notional": report.get("total_notional"),
        "orders_submitted_by_second_trade_lifecycle_audit": report.get("orders_submitted_by_second_trade_lifecycle_audit"),
        "positions_opened_by_second_trade_lifecycle_audit": report.get("positions_opened_by_second_trade_lifecycle_audit"),
        "positions_closed_by_second_trade_lifecycle_audit": report.get("positions_closed_by_second_trade_lifecycle_audit"),
        "broker_submit_called_by_second_trade_lifecycle_audit": report.get("broker_submit_called_by_second_trade_lifecycle_audit"),
        "broker_close_called_by_second_trade_lifecycle_audit": report.get("broker_close_called_by_second_trade_lifecycle_audit"),
        "automatic_close_enabled": report.get("automatic_close_enabled"),
        "automatic_reentry_enabled": report.get("automatic_reentry_enabled"),
        "live_enabled": report.get("live_enabled"),
        "testnet_enabled": report.get("testnet_enabled"),
        "exchange_broker_enabled": report.get("exchange_broker_enabled"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "promotion_ready": report.get("promotion_ready"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
