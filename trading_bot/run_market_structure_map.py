from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.market_structure_map import write_market_structure_map_report


def main() -> None:
    report = write_market_structure_map_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    counts = report.get("counts", {}) if isinstance(report.get("counts"), dict) else {}
    print(json.dumps({
        "hotfix": report.get("hotfix"),
        "status": report.get("status"),
        "decision": decision.get("status"),
        "focus_symbol": decision.get("focus_symbol"),
        "focus_latest": decision.get("focus_latest"),
        "counts": counts,
        "report": "data\\market_structure_map_report.json",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
