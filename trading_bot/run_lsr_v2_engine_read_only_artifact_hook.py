from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_engine_read_only_artifact_hook import build_lsr_v2_engine_read_only_artifact_hook_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_engine_read_only_artifact_hook import build_lsr_v2_engine_read_only_artifact_hook_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 engine read-only dashboard/lifecycle artifact hook")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    report = build_lsr_v2_engine_read_only_artifact_hook_report_from_files(data_dir=args.data_dir)
    keys = [
        "status",
        "decision",
        "classification_labels",
        "blockers",
        "engine_artifact_hook_ready",
        "paper_engine_hook_read_only",
        "paper_engine_artifact_hook_active",
        "integration_preflight_ready",
        "lifecycle_auto_monitor_ready",
        "telegram_dashboard_ready",
        "three_trade_postmortem_ready",
        "dashboard_mode",
        "lifecycle_state",
        "telegram_payload_ready",
        "telegram_update_ready",
        "telegram_network_called",
        "telegram_send_allowed",
        "scheduler_enabled",
        "scheduler_started",
        "visual_sl_tp_progress_bar_ready",
        "visual_sl_tp_progress_bar",
        "visual_sl_tp_progress_pct",
        "progress_state",
        "submit_execution_events_total",
        "close_execution_events_total",
        "aggregate_realized_pnl",
        "balance_after",
        "flat_state_confirmed",
        "paper_state_status_consistency",
        "operator_env_absent",
        "fourth_trade_allowed",
        "fourth_trade_locked",
        "stability_lock_active",
        "open_positions_after",
        "paper_status_open_positions_after",
        "paper_status_pending_orders_after",
        "orders_submitted_by_engine_artifact_hook",
        "positions_opened_by_engine_artifact_hook",
        "positions_closed_by_engine_artifact_hook",
        "paper_state_modified_by_engine_artifact_hook",
        "paper_status_modified_by_engine_artifact_hook",
        "broker_submit_called_by_engine_artifact_hook",
        "broker_close_called_by_engine_artifact_hook",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "recommended_next_patch",
        "report",
        "jsonl",
    ]
    slim = {key: report.get(key) for key in keys if key in report}
    print(json.dumps(slim, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
