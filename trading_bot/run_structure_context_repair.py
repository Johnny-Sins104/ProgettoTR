from __future__ import annotations

import json
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.structure_context_repair import write_structure_context_repair_report


def main() -> None:
    report = write_structure_context_repair_report("data")
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    print(json.dumps({
        "status": report.get("status"),
        "decision": decision.get("status"),
        "best_repaired_variant": ((decision.get("best_repaired_variant") or {}).get("name") if isinstance(decision.get("best_repaired_variant"), dict) else ""),
        "report": report.get("files", {}).get("report", "data\\structure_context_repair_report.json") if isinstance(report.get("files"), dict) else "data\\structure_context_repair_report.json",
        "counts": report.get("counts", {}),
        "operational_unlock_allowed": bool(report.get("operational_unlock_allowed", False)),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
