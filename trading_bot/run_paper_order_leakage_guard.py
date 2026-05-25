from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_order_leakage_guard import PaperOrderLeakageGuardSettings, write_paper_order_leakage_guard_report


def main() -> None:
    report = write_paper_order_leakage_guard_report(Path("data"), PaperOrderLeakageGuardSettings.from_config())
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "decision": decision.get("status"),
                "latest_cycle_id": decision.get("latest_cycle_id"),
                "legacy_order_leakage_detected": decision.get("legacy_order_leakage_detected"),
                "unauthorized_orders_count": decision.get("unauthorized_orders_count"),
                "unauthorized_positions_opened_count": decision.get("unauthorized_positions_opened_count"),
                "blocked_legacy_order_attempts": decision.get("blocked_legacy_order_attempts"),
                "cycle_orders_total": decision.get("cycle_orders_total"),
                "max_open_positions": decision.get("max_open_positions"),
                "allowed_order_source": decision.get("allowed_order_source"),
                "fail_closed": decision.get("fail_closed"),
                "orders_submitted": report.get("orders_submitted"),
                "positions_opened": report.get("positions_opened"),
                "report": str(Path("data") / PaperOrderLeakageGuardSettings.from_config().report_name),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
