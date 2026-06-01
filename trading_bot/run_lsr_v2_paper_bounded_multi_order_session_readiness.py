from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from core.lsr_v2_paper_bounded_multi_order_session import build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files
except Exception:
    from trading_bot.core.lsr_v2_paper_bounded_multi_order_session import build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch 30.3.0H bounded multi-order supervised paper session readiness")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--max-event-lines", type=int, default=50000)
    args = parser.parse_args()
    report = build_lsr_v2_paper_bounded_multi_order_session_readiness_report_from_files(
        data_dir=args.data_dir,
        max_event_lines=args.max_event_lines,
    )
    print(json.dumps({
        "status": report.get("status"),
        "decision": report.get("decision"),
        "blockers": report.get("blockers"),
        "system_ready": report.get("system_ready"),
        "multi_order_session_ready": report.get("multi_order_session_ready"),
        "multi_order_execute_enabled": report.get("multi_order_execute_enabled"),
        "session_orders": report.get("session_orders"),
        "max_orders_per_session": report.get("max_orders_per_session"),
        "open_positions": report.get("open_positions"),
        "max_open_positions": report.get("max_open_positions"),
        "cooldown_satisfied": report.get("cooldown_satisfied"),
        "duplicate_cycle_id": report.get("duplicate_cycle_id"),
        "candidate": report.get("candidate"),
        "session_controls": report.get("session_controls"),
        "read_only_safety": report.get("read_only_safety"),
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }, indent=2, sort_keys=True))
    return 1 if report.get("status") == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
