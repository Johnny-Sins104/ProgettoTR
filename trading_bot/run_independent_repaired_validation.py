from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.independent_repaired_validation import write_independent_repaired_validation_report


def main() -> None:
    report = write_independent_repaired_validation_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    best = decision.get("best_stability_variant") if isinstance(decision.get("best_stability_variant"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "best_stability_variant": best.get("name", "") if isinstance(best, dict) else "",
        "report": report.get("files", {}).get("report", "data\\independent_repaired_validation_report.json") if isinstance(report.get("files"), dict) else "data\\independent_repaired_validation_report.json",
        "counts": report.get("counts", {}),
        "operational_unlock_allowed": bool(report.get("operational_unlock_allowed", False)),
        "paper_unlock_refinement_allowed": bool(report.get("paper_unlock_refinement_allowed", False)),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
