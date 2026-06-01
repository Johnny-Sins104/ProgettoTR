from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_paper_engine_integration_preflight import build_lsr_v2_paper_engine_integration_preflight_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_paper_engine_integration_preflight import build_lsr_v2_paper_engine_integration_preflight_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 Paper Engine integration planning preflight")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    args = parser.parse_args()
    report = build_lsr_v2_paper_engine_integration_preflight_report_from_files(
        data_dir=args.data_dir,
        project_root=args.project_root,
    )
    keys = [
        "status",
        "decision",
        "classification_labels",
        "blockers",
        "integration_preflight_ready",
        "engine_integration_allowed",
        "engine_mutation_allowed",
        "runner_consolidation_allowed",
        "lifecycle_auto_monitor_ready",
        "telegram_dashboard_ready",
        "three_trade_postmortem_ready",
        "lifecycle_state",
        "dashboard_mode",
        "submit_execution_events_total",
        "close_execution_events_total",
        "aggregate_realized_pnl",
        "pnl_reconciliation_ok",
        "flat_state_confirmed",
        "pending_orders_clear",
        "paper_state_status_consistency",
        "operator_env_absent",
        "source_files_present",
        "required_source_markers_present",
        "missing_source_files",
        "missing_source_markers",
        "fourth_submit_or_reentry_detected",
        "fourth_trade_allowed",
        "fourth_trade_locked",
        "stability_lock_active",
        "open_positions_after",
        "paper_status_open_positions_after",
        "paper_status_pending_orders_after",
        "telegram_send_allowed",
        "telegram_network_called",
        "scheduler_enabled",
        "scheduler_started",
        "orders_submitted_by_integration_preflight",
        "positions_opened_by_integration_preflight",
        "positions_closed_by_integration_preflight",
        "paper_state_modified_by_integration_preflight",
        "paper_status_modified_by_integration_preflight",
        "broker_submit_called_by_integration_preflight",
        "broker_close_called_by_integration_preflight",
        "live_enabled",
        "testnet_enabled",
        "exchange_broker_enabled",
        "operational_unlock_allowed",
        "promotion_ready",
        "recommended_next_patch",
        "next_step",
        "report",
        "jsonl",
    ]
    print(json.dumps({k: report.get(k) for k in keys}, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1 if str(report.get("decision", "")).startswith("REJECT") else 0


if __name__ == "__main__":
    raise SystemExit(main())
