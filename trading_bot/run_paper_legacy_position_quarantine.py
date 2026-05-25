from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_legacy_position_quarantine import (
    LegacyPositionQuarantineSettings,
    quarantine_legacy_positions,
    reset_legacy_paper_state,
    write_legacy_position_quarantine_report,
)


def _summary(report: dict) -> dict:
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    legacy = report.get("legacy_summary", {}) if isinstance(report.get("legacy_summary"), dict) else {}
    return {
        "status": report.get("status"),
        "decision": decision.get("status"),
        "mode": decision.get("mode"),
        "legacy_contamination_detected": decision.get("legacy_contamination_detected"),
        "legacy_orders_count": decision.get("legacy_orders_count"),
        "legacy_positions_count": decision.get("legacy_positions_count"),
        "legacy_open_positions_count": decision.get("legacy_open_positions_count"),
        "legacy_closed_positions_count": decision.get("legacy_closed_positions_count"),
        "current_open_positions": decision.get("current_open_positions"),
        "legacy_realized_pnl": legacy.get("legacy_realized_pnl"),
        "legacy_unrealized_pnl": legacy.get("legacy_unrealized_pnl"),
        "paper_account_realized_pnl": legacy.get("paper_account_realized_pnl"),
        "paper_account_unrealized_pnl": legacy.get("paper_account_unrealized_pnl"),
        "affected_symbols": legacy.get("affected_symbols"),
        "clean_state_ready": decision.get("clean_state_ready"),
        "quarantine_applied": decision.get("quarantine_applied"),
        "reset_applied": decision.get("reset_applied"),
        "backup_dir": decision.get("backup_dir"),
        "report": str(Path("data") / LegacyPositionQuarantineSettings.from_config().report_name),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="29.4.4r-2 legacy paper position quarantine / clean-state preflight")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--report-only", action="store_true", help="write diagnostic report only; default")
    group.add_argument("--quarantine", action="store_true", help="mark legacy orders/positions as quarantined, preserving open/closed status")
    group.add_argument("--reset-paper-state", action="store_true", help="backup and reset active paper state/log to a clean state")
    parser.add_argument("--confirm-reset", action="store_true", help="required with --reset-paper-state")
    args = parser.parse_args()

    settings = LegacyPositionQuarantineSettings.from_config()
    base = Path("data")
    if args.reset_paper_state:
        if not args.confirm_reset:
            raise SystemExit("--reset-paper-state requires --confirm-reset")
        report = reset_legacy_paper_state(base, settings, confirm_reset=True)
    elif args.quarantine:
        report = quarantine_legacy_positions(base, settings)
    else:
        report = write_legacy_position_quarantine_report(base, settings, mode="report_only")
    print(json.dumps(_summary(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
