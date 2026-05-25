from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_routing_bridge import write_paper_unlock_routing_bridge_report


def main() -> None:
    report = write_paper_unlock_routing_bridge_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "profile_name": decision.get("profile_name"),
        "latest_cycle_id": decision.get("latest_cycle_id"),
        "routing_bridge_events": decision.get("routing_bridge_events"),
        "runtime_audit_events": decision.get("runtime_audit_events"),
        "would_route_count": decision.get("would_route_count"),
        "would_submit_count": decision.get("would_submit_count"),
        "orders_submitted_by_bridge": decision.get("orders_submitted_by_bridge"),
        "orders_submitted": decision.get("orders_submitted"),
        "positions_opened": decision.get("positions_opened"),
        "routing_mode": decision.get("routing_mode"),
        "operational_unlock_allowed": report.get("operational_unlock_allowed"),
        "paper_orders_enabled": report.get("paper_orders_enabled"),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed"),
        "report": "data\\paper_unlock_routing_bridge_report.json",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
