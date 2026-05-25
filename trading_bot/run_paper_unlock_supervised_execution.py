from __future__ import annotations

import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.paper_unlock_supervised_execution import write_paper_unlock_supervised_execution_report


def main() -> int:
    report = write_paper_unlock_supervised_execution_report("data")
    decision = report.get("decision", {}) if isinstance(report, dict) else {}
    payload = {
        "status": report.get("status"),
        "decision": decision.get("status"),
        "latest_cycle_id": decision.get("latest_cycle_id"),
        "supervised_execution_events": decision.get("supervised_execution_events"),
        "supervised_submit_allowed_count": decision.get("supervised_submit_allowed_count"),
        "candidate_ready_count": decision.get("candidate_ready_count"),
        "would_create_order_count": decision.get("would_create_order_count"),
        "broker_submit_called_count": decision.get("broker_submit_called_count"),
        "orders_submitted_by_supervised": decision.get("orders_submitted_by_supervised"),
        "positions_opened_by_supervised": decision.get("positions_opened_by_supervised"),
        "operator_enable": decision.get("operator_enable"),
        "operator_confirmation_ok": decision.get("operator_confirmation_ok"),
        "operational_unlock_allowed": decision.get("operational_unlock_allowed"),
        "report": "data\\paper_unlock_supervised_execution_report.json",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
