from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_telegram_trade_dashboard import build_lsr_v2_telegram_trade_dashboard_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_telegram_trade_dashboard import build_lsr_v2_telegram_trade_dashboard_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 Telegram trade dashboard with visual SL/TP progress bar")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    report = build_lsr_v2_telegram_trade_dashboard_report_from_files(data_dir=args.data_dir)
    keys = [
        "status",
        "decision",
        "classification_labels",
        "blockers",
        "dashboard_ready",
        "telegram_payload_ready",
        "telegram_send_allowed",
        "telegram_network_called",
        "telegram_message_key",
        "dashboard_mode",
        "visual_sl_tp_progress_bar_ready",
        "visual_sl_tp_progress_bar",
        "visual_sl_tp_progress_pct",
        "entry_to_tp_progress_pct",
        "distance_to_take_profit",
        "distance_to_stop_loss",
        "progress_state",
        "three_trade_postmortem_ready",
        "submit_execution_events_total",
        "close_execution_events_total",
        "aggregate_realized_pnl",
        "realized_pnl_after",
        "balance_after",
        "pnl_reconciliation_ok",
        "flat_state_confirmed",
        "paper_state_status_consistency",
        "operator_env_absent",
        "fourth_submit_or_reentry_detected",
        "fourth_trade_allowed",
        "fourth_trade_locked",
        "stability_lock_active",
        "open_positions_after",
        "paper_status_open_positions_after",
        "paper_status_pending_orders_after",
        "orders_submitted_by_telegram_dashboard",
        "positions_opened_by_telegram_dashboard",
        "positions_closed_by_telegram_dashboard",
        "paper_state_modified_by_telegram_dashboard",
        "paper_status_modified_by_telegram_dashboard",
        "broker_submit_called_by_telegram_dashboard",
        "broker_close_called_by_telegram_dashboard",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "recommended_next_patch",
        "report",
        "jsonl",
        "telegram_message_text",
    ]
    print(json.dumps({k: report.get(k) for k in keys}, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
