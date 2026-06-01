from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_second_paper_order_gate import build_lsr_v2_second_paper_order_gate_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_second_paper_order_gate import build_lsr_v2_second_paper_order_gate_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch 30.3.0G read-only second supervised paper order gate")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--max-event-lines", type=int, default=50000)
    args = parser.parse_args()
    report = build_lsr_v2_second_paper_order_gate_report_from_files(
        data_dir=args.data_dir,
        max_event_lines=args.max_event_lines,
    )
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "blockers": report.get("blockers"),
        "system_ready": report.get("system_ready"),
        "second_order_gate_ready": report.get("second_order_gate_ready"),
        "second_order_execute_enabled": report.get("second_order_execute_enabled"),
        "candidate": report.get("candidate"),
        "prerequisites": report.get("prerequisites"),
        "operator_controls": report.get("operator_controls"),
        "read_only_safety": report.get("read_only_safety"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 1 if report.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
