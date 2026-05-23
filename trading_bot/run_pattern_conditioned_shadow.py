from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.pattern_conditioned_shadow import write_pattern_conditioned_shadow_report


def main() -> None:
    data_dir = os.getenv("PATTERN_CONDITIONED_DATA_DIR", "data")
    # When launched from trading_bot/, data lives one directory above in the
    # project root. Prefer ../data when it exists and contains runtime artifacts.
    parent_data = os.path.join("..", "data")
    if data_dir == "data" and os.path.exists(parent_data):
        if os.path.exists(os.path.join(parent_data, "paper_events.jsonl")) or not os.path.exists(os.path.join(data_dir, "paper_events.jsonl")):
            data_dir = parent_data
    report = write_pattern_conditioned_shadow_report(data_dir)
    print(json.dumps({
        "status": report.get("status"),
        "decision": (report.get("decision") or {}).get("status"),
        "counts": report.get("counts"),
        "report": (report.get("files") or {}).get("report"),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
