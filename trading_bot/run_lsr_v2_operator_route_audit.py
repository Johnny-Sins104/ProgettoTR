"""run_lsr_v2_operator_route_audit.py — Diagnostic-only operator route audit runner.

Reads paper_events.jsonl (preferred) or falls back to lsr_v2_runtime_bridge_audit.jsonl,
scopes to the current cycle from lsr_v2_runtime_bridge_report.json, counts candidate
and bridge events, and writes the audit artifacts.

Diagnostic only: opens no orders, submits nothing, modifies no trading state.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run operator route audit. Returns 0 on success."""
    args = argv if argv is not None else sys.argv[1:]

    data_dir = Path("data")
    for i, arg in enumerate(args):
        if arg == "--data-dir" and i + 1 < len(args):
            data_dir = Path(args[i + 1])

    # Load current cycle_id from runtime bridge report
    bridge_report_path = data_dir / "lsr_v2_runtime_bridge_report.json"
    if not bridge_report_path.exists():
        print(json.dumps({"error": "lsr_v2_runtime_bridge_report.json not found", "exit_code": 1}))
        return 1
    bridge_report = json.loads(bridge_report_path.read_text(encoding="utf-8"))
    cycle_id: str = bridge_report.get("cycle_id", "unknown")

    # Event type constants (mirrors lsr_v2_runtime_bridge constants)
    RUNTIME_CANDIDATE_EVENT_TYPE = "LSR_V2_RUNTIME_CANDIDATE_AUDIT"
    RUNTIME_BRIDGE_EVENT_TYPE = "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT"
    OPERATOR_ROUTE_READY_DECISION = "LSR_V2_OPERATOR_ROUTE_AUDIT_READY_DIAGNOSTIC"
    LSR_V2_EVENT_TYPES = {RUNTIME_CANDIDATE_EVENT_TYPE, RUNTIME_BRIDGE_EVENT_TYPE}

    paper_events_path = data_dir / "paper_events.jsonl"
    runtime_bridge_path = data_dir / "lsr_v2_runtime_bridge_audit.jsonl"

    event_source: str
    events_all: list[dict]
    runtime_jsonl_deduplicated = False

    if paper_events_path.exists():
        # Preferred: paper_events.jsonl — strict cycle scope
        event_source = "paper_events_jsonl"
        raw_lines = paper_events_path.read_text(encoding="utf-8").splitlines()
        events_all = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            try:
                events_all.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    else:
        # Fallback: lsr_v2_runtime_bridge_audit.jsonl — deduplicate rows
        event_source = "runtime_bridge_jsonl_fallback"
        if not runtime_bridge_path.exists():
            events_all = []
        else:
            raw_lines = runtime_bridge_path.read_text(encoding="utf-8").splitlines()
            seen: set[str] = set()
            deduped: list[dict] = []
            for line in raw_lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    key = json.dumps(ev, sort_keys=True)
                    if key not in seen:
                        seen.add(key)
                        deduped.append(ev)
                except json.JSONDecodeError:
                    continue
            events_all = deduped
            runtime_jsonl_deduplicated = True

    # Partition into current cycle and historical
    current_cycle_events = [e for e in events_all if e.get("cycle_id") == cycle_id]
    historical_events = [
        e for e in events_all
        if e.get("cycle_id") != cycle_id and e.get("event_type") in LSR_V2_EVENT_TYPES
    ]

    # Count metrics on current cycle
    candidate_events = [e for e in current_cycle_events if e.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE]
    bridge_events = [e for e in current_cycle_events if e.get("event_type") == RUNTIME_BRIDGE_EVENT_TYPE]
    candidate_ready_events = [e for e in candidate_events if e.get("candidate_ready") is True]
    would_route_events = [e for e in bridge_events if e.get("would_route") is True]
    would_submit_events = [e for e in bridge_events if e.get("would_submit") is True]

    report: dict = {
        "diagnostic_only": True,
        "opens_orders": False,
        "live_trading_allowed": False,
        "cycle_id": cycle_id,
        "event_source": event_source,
        "strict_cycle_scope": True,
        "runtime_candidate_events": len(candidate_events),
        "runtime_candidate_ready_events": len(candidate_ready_events),
        "runtime_bridge_events": len(bridge_events),
        "would_route_count": len(would_route_events),
        "would_submit_count": len(would_submit_events),
        "historical_lsr_v2_events": len(historical_events),
        "orders_submitted_by_lsr_v2_operator_route_audit": 0,
        "positions_opened_by_lsr_v2_operator_route_audit": 0,
        "decision": OPERATOR_ROUTE_READY_DECISION,
    }
    if event_source == "runtime_bridge_jsonl_fallback":
        report["runtime_jsonl_deduplicated"] = runtime_jsonl_deduplicated

    # Write report JSON
    report_path = data_dir / "lsr_v2_operator_route_audit_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Write events JSONL (current cycle only)
    jsonl_path = data_dir / "lsr_v2_operator_route_audit.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for ev in current_cycle_events:
            fh.write(json.dumps(ev) + "\n")

    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
