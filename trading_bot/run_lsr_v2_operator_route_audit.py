#!/usr/bin/env python
"""Prompt 29.4.4s-10f-1 — LSR-v2 strict cycle-scoped operator-route audit.

Reads cycle-scoped LSR-v2 runtime bridge events and writes an operator route
preflight report. The current paper cycle is resolved from ``paper_events.jsonl``
first; ``lsr_v2_runtime_bridge_audit.jsonl`` is only a de-duplicated fallback
because it can contain repeated rows from incremental report refreshes.

This runner never submits orders, never opens positions and never enables
runtime execution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

try:
    from core.lsr_v2_runtime_bridge import (  # type: ignore
        BRIDGE_EVENT_TYPE,
        RUNTIME_CANDIDATE_EVENT_TYPE,
        LSRV2RuntimeBridgeSettings,
        _dedupe_runtime_events,
        _filter_runtime_events_for_cycle,
        _iter_jsonl_tail,
        _read_json,
        write_lsr_v2_operator_route_audit_artifacts,
    )
except Exception:
    from trading_bot.core.lsr_v2_runtime_bridge import (  # type: ignore
        BRIDGE_EVENT_TYPE,
        RUNTIME_CANDIDATE_EVENT_TYPE,
        LSRV2RuntimeBridgeSettings,
        _dedupe_runtime_events,
        _filter_runtime_events_for_cycle,
        _iter_jsonl_tail,
        _read_json,
        write_lsr_v2_operator_route_audit_artifacts,
    )

PROMPT_ID = "29.4.4s-10f-1"
PAPER_EVENTS_NAME = "paper_events.jsonl"


def _event_cycle(event: Mapping[str, Any]) -> str:
    return str(event.get("cycle_id") or event.get("lsr_v2_runtime_cycle_id") or "")


def _is_lsr_v2_runtime_event(event: Mapping[str, Any]) -> bool:
    event_type = event.get("event_type")
    if event_type == RUNTIME_CANDIDATE_EVENT_TYPE:
        return True
    return event_type == BRIDGE_EVENT_TYPE and bool(event.get("runtime_cycle_scoped", False))


def _latest_completed_cycle_from_paper_events(rows: Iterable[Mapping[str, Any]]) -> str:
    latest = ""
    for row in rows:
        if row.get("event_type") == "CYCLE_COMPLETED" and _event_cycle(row):
            latest = _event_cycle(row)
    return latest


def _latest_lsr_cycle_from_events(rows: Iterable[Mapping[str, Any]]) -> str:
    latest = ""
    for row in rows:
        if _is_lsr_v2_runtime_event(row) and _event_cycle(row):
            latest = _event_cycle(row)
    return latest


def _count_runtime_events(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    rows_list = [dict(r) for r in rows if _is_lsr_v2_runtime_event(r)]
    return {
        "events": len(rows_list),
        "candidate_events": sum(1 for r in rows_list if r.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE),
        "bridge_events": sum(1 for r in rows_list if r.get("event_type") == BRIDGE_EVENT_TYPE),
    }


def _select_current_cycle_events(
    *,
    data_dir: Path,
    settings: LSRV2RuntimeBridgeSettings,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Return strict cycle-scoped events and source diagnostics.

    ``paper_events.jsonl`` is authoritative for the just-completed paper cycle.
    The runtime bridge JSONL remains a fallback and is exact-deduplicated.
    """
    paper_events = _iter_jsonl_tail(data_dir / PAPER_EVENTS_NAME, max_lines=settings.max_event_lines)
    runtime_events = _iter_jsonl_tail(data_dir / settings.runtime_jsonl_name, max_lines=settings.max_event_lines)
    runtime_report = _read_json(data_dir / settings.runtime_report_name)

    cycle_id = str(requested_cycle_id or "")
    if not cycle_id:
        cycle_id = _latest_completed_cycle_from_paper_events(paper_events)
    if not cycle_id:
        cycle_id = str(runtime_report.get("cycle_id") or runtime_report.get("lsr_v2_runtime_cycle_id") or "")
    if not cycle_id:
        cycle_id = _latest_lsr_cycle_from_events(paper_events)
    if not cycle_id:
        cycle_id = _latest_lsr_cycle_from_events(runtime_events)

    paper_current = _filter_runtime_events_for_cycle(paper_events, cycle_id)
    runtime_current = _filter_runtime_events_for_cycle(runtime_events, cycle_id)

    if paper_current:
        selected = paper_current
        source = "paper_events_jsonl"
    else:
        selected = runtime_current
        source = "runtime_bridge_jsonl_fallback"

    historical_rows = [r for r in _dedupe_runtime_events([r for r in paper_events + runtime_events if _is_lsr_v2_runtime_event(r)]) if _event_cycle(r) and _event_cycle(r) != cycle_id]
    diagnostics = {
        "prompt_id": PROMPT_ID,
        "event_source": source,
        "paper_events_current_cycle": _count_runtime_events(paper_current),
        "runtime_jsonl_current_cycle": _count_runtime_events(runtime_current),
        "historical_lsr_v2_events": len(historical_rows),
        "historical_lsr_v2_candidate_events": sum(1 for r in historical_rows if r.get("event_type") == RUNTIME_CANDIDATE_EVENT_TYPE),
        "historical_lsr_v2_bridge_events": sum(1 for r in historical_rows if r.get("event_type") == BRIDGE_EVENT_TYPE),
        "runtime_jsonl_deduplicated": True,
        "strict_cycle_scope": True,
    }
    return cycle_id, selected, diagnostics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LSR-v2 strict cycle-scoped operator-controlled would-route audit")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--cycle-id", default="", help="Optional cycle_id. Defaults to latest CYCLE_COMPLETED in paper_events.jsonl.")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    settings = LSRV2RuntimeBridgeSettings(data_dir=str(data_dir))
    cycle_id, events, diagnostics = _select_current_cycle_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=str(args.cycle_id or ""),
    )

    report = write_lsr_v2_operator_route_audit_artifacts(
        data_dir=data_dir,
        cycle_id=cycle_id,
        events=events,
        settings=settings,
        metadata=diagnostics,
    )
    # force safety-facing summary fields to stdout
    summary = {
        "status": report.get("status"),
        "decision": report.get("decision"),
        "cycle_id": report.get("cycle_id"),
        "event_source": report.get("event_source"),
        "strict_cycle_scope": report.get("strict_cycle_scope"),
        "historical_lsr_v2_events": report.get("historical_lsr_v2_events"),
        "operator_enable": report.get("operator_enable"),
        "operator_confirmation_ok": report.get("operator_confirmation_ok"),
        "runtime_candidate_events": report.get("runtime_candidate_events"),
        "runtime_candidate_ready_events": report.get("runtime_candidate_ready_events"),
        "runtime_bridge_events": report.get("runtime_bridge_events"),
        "would_route_count": report.get("would_route_count"),
        "would_submit_count": 0,
        "orders_submitted_by_lsr_v2_operator_route_audit": 0,
        "positions_opened_by_lsr_v2_operator_route_audit": 0,
        "broker_submit_called": False,
        "execution_enabled": False,
        "routing_enabled": False,
        "paper_order_submission_enabled": False,
        "promotion_ready": False,
        "report": report.get("report"),
        "jsonl": report.get("jsonl"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if str(report.get("status")) == "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
