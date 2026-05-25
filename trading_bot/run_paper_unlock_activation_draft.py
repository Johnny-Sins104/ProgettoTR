from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_activation_draft import write_paper_unlock_activation_draft_report


def main() -> None:
    report = write_paper_unlock_activation_draft_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    prereq = report.get("stability_prerequisite", {}) if isinstance(report.get("stability_prerequisite"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "draft_name": report.get("draft_name", ""),
        "profile_name": report.get("profile_name", ""),
        "best_stability_review_variant": decision.get("best_stability_review_variant", ""),
        "selected_entries": decision.get("selected_entries", 0),
        "interlocks_ready": bool(decision.get("interlocks_ready", False)),
        "stability_prerequisite_ok": bool(prereq.get("passes_stability_prerequisite", False)),
        "report": report.get("files", {}).get("report", "data\\paper_unlock_activation_draft_report.json") if isinstance(report.get("files"), dict) else "data\\paper_unlock_activation_draft_report.json",
        "operational_unlock_allowed": bool(report.get("operational_unlock_allowed", False)),
        "paper_unlock_experiment_allowed": bool(report.get("paper_unlock_experiment_allowed", False)),
        "paper_orders_enabled": bool(report.get("paper_orders_enabled", False)),
        "profile_activation_allowed": bool(report.get("profile_activation_allowed", False)),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
