from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_bounded_cadence import write_paper_unlock_bounded_cadence_report


def main() -> None:
    report = write_paper_unlock_bounded_cadence_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    best = decision.get("best_bounded_cadence_variant", {}) if isinstance(decision.get("best_bounded_cadence_variant"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "collection_name": report.get("collection_name", ""),
        "best_bounded_cadence_variant": best.get("name", ""),
        "best_selected_entries": best.get("selected_entries", 0),
        "report": report.get("files", {}).get("report", "data\\paper_unlock_bounded_cadence_report.json") if isinstance(report.get("files"), dict) else "data\\paper_unlock_bounded_cadence_report.json",
        "counts": report.get("counts", {}),
        "operational_unlock_allowed": bool(report.get("operational_unlock_allowed", False)),
        "paper_unlock_experiment_allowed": bool(report.get("paper_unlock_experiment_allowed", False)),
        "paper_orders_enabled": bool(report.get("paper_orders_enabled", False)),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
