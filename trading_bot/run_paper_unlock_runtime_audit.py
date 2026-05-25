from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_runtime_audit import write_paper_unlock_runtime_audit_report


def main() -> None:
    report = write_paper_unlock_runtime_audit_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "profile_name": decision.get("profile_name"),
        "latest_cycle_id": decision.get("latest_cycle_id"),
        "runtime_audit_events": decision.get("runtime_audit_events"),
        "legacy_unlock_events": decision.get("legacy_unlock_events"),
        "runtime_accepts_diagnostic": decision.get("runtime_accepts_diagnostic"),
        "orders_submitted": report.get("orders_submitted"),
        "positions_opened": report.get("positions_opened"),
        "paper_orders_enabled": report.get("paper_orders_enabled"),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "report": "data\\paper_unlock_runtime_audit_report.json",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
