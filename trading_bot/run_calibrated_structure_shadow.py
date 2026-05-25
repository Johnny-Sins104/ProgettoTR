from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.calibrated_structure_shadow import write_calibrated_structure_shadow_report


def main() -> None:
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data"
    report = write_calibrated_structure_shadow_report(data_dir)
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    counts = report.get("counts", {}) if isinstance(report.get("counts"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "candidate_profile": ((decision.get("candidate_profile") or {}).get("name") if isinstance(decision.get("candidate_profile"), dict) else ""),
        "report": report.get("files", {}).get("report"),
        "counts": {
            "scenario_pattern_evaluation_rows": counts.get("scenario_pattern_evaluation_rows", 0),
            "candidate_rows_pre_structure": counts.get("candidate_rows_pre_structure", 0),
            "structured_candidate_rows": counts.get("structured_candidate_rows", 0),
            "orders_submitted": counts.get("orders_submitted", 0),
            "positions_opened": counts.get("positions_opened", 0),
        },
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
