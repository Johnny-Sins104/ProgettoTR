from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_unlock_shadow_stability_review import write_paper_unlock_shadow_stability_review_report


def main() -> None:
    report = write_paper_unlock_shadow_stability_review_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    checks = report.get("stability_checks", {}) if isinstance(report.get("stability_checks"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "review_name": report.get("review_name", ""),
        "best_stability_review_variant": decision.get("best_stability_review_variant", ""),
        "selected_entries": decision.get("selected_entries", report.get("counts", {}).get("selected_entries", 0) if isinstance(report.get("counts"), dict) else 0),
        "report": report.get("files", {}).get("report", "data\\paper_unlock_shadow_stability_review_report.json") if isinstance(report.get("files"), dict) else "data\\paper_unlock_shadow_stability_review_report.json",
        "counts": report.get("counts", {}),
        "sample_ok": bool(checks.get("sample_ok", False)),
        "rolling_window_ok": bool(checks.get("rolling_window_ok", False)),
        "holdout_ok": bool(checks.get("holdout_ok", False)),
        "concentration_ok": bool(checks.get("concentration_ok", False)),
        "temporal_dispersion_ok": bool(checks.get("temporal_dispersion_ok", False)),
        "operational_unlock_allowed": bool(report.get("operational_unlock_allowed", False)),
        "paper_unlock_experiment_allowed": bool(report.get("paper_unlock_experiment_allowed", False)),
        "paper_orders_enabled": bool(report.get("paper_orders_enabled", False)),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
