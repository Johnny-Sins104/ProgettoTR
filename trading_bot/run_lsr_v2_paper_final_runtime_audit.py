from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_paper_final_runtime_audit import build_lsr_v2_paper_final_runtime_audit_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_paper_final_runtime_audit import build_lsr_v2_paper_final_runtime_audit_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch 30.3.0E read-only final paper runtime audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--max-event-lines", type=int, default=50000)
    args = parser.parse_args()
    report = build_lsr_v2_paper_final_runtime_audit_report_from_files(
        data_dir=args.data_dir,
        max_event_lines=args.max_event_lines,
    )
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "final_state": report.get("final_state"),
        "recommendation": report.get("recommendation"),
        "blockers": report.get("blockers"),
        "cycle_id": report.get("cycle_id"),
        "latest_cycle_id": report.get("latest_cycle_id"),
        "order_id": report.get("order_id"),
        "position_id": report.get("position_id"),
        "order_lifecycle": report.get("order_lifecycle"),
        "position_lifecycle": report.get("position_lifecycle"),
        "paper_state_status_consistent": report.get("paper_state_status_consistent"),
        "lifecycle_warnings": report.get("lifecycle_warnings"),
        "lifecycle_warning_classification": report.get("lifecycle_warning_classification"),
        "safety_flags": report.get("safety_flags"),
        "runtime_source": report.get("runtime_source"),
        "counts": report.get("counts"),
        "pnl_snapshot": report.get("pnl_snapshot"),
        "report": report.get("files", {}).get("report"),
        "jsonl": report.get("files", {}).get("jsonl"),
    }, indent=2, sort_keys=True))
    return 1 if report.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
