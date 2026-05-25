from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_handoff_dry_run import write_paper_unlock_handoff_dry_run_report


def main() -> None:
    report = write_paper_unlock_handoff_dry_run_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "profile_name": decision.get("profile_name"),
        "latest_cycle_id": decision.get("latest_cycle_id"),
        "candidate_order_audit_events": decision.get("candidate_order_audit_events"),
        "candidate_ready_count": decision.get("candidate_ready_count"),
        "handoff_dry_run_events": decision.get("handoff_dry_run_events"),
        "handoff_coverage_ok": decision.get("handoff_coverage_ok"),
        "would_create_order_count": decision.get("would_create_order_count"),
        "orders_submitted_by_handoff": decision.get("orders_submitted_by_handoff"),
        "positions_opened_by_handoff": decision.get("positions_opened_by_handoff"),
        "orders_submitted": decision.get("orders_submitted"),
        "positions_opened": decision.get("positions_opened"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "paper_orders_enabled": report.get("paper_orders_enabled"),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed"),
        "report": "data\\paper_unlock_handoff_dry_run_report.json",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
