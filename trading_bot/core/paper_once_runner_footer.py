from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from core.paper_once_console_summary import print_paper_once_console_summary


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    try:
        # Support isoformat parsing
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _iter_jsonl_events(events_path: str | Path):
    path = Path(events_path)
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                yield json.loads(line_str)
            except Exception:
                continue


def read_latest_cycle_completed(
    events_path: str | Path,
    *,
    started_at: datetime | None = None,
) -> dict[str, Any] | None:
    latest_cycle = None
    started_at_utc = _parse_ts(started_at)
    for event in _iter_jsonl_events(events_path):
        if event.get("event_type") != "CYCLE_COMPLETED":
            continue
        ts_val = event.get("ts")
        if started_at_utc is not None:
            event_ts = _parse_ts(ts_val)
            if event_ts is None or event_ts < started_at_utc:
                continue
        latest_cycle = event
    return latest_cycle


def collect_cycle_audit_counts(
    events_path: str | Path,
    cycle_id: str,
) -> dict[str, Any]:
    counts = {
        "runtime_audit_events": 0,
        "runtime_accepts_diagnostic": 0,
        "runtime_rejects": 0,
        "routing_bridge_events": 0,
        "would_route_count": 0,
        "would_submit_count": 0,
        "orders_submitted_by_bridge": 0,
        "positions_opened_by_bridge": 0,
    }
    flags = {}
    for event in _iter_jsonl_events(events_path):
        if event.get("cycle_id") != cycle_id:
            continue
        event_type = event.get("event_type")
        
        for flag_name in [
            "paper_orders_enabled",
            "paper_unlock_experiment_allowed",
            "manual_activation_allowed",
            "operational_unlock_allowed",
            "live_allowed",
            "testnet_allowed",
            "exchange_broker_allowed",
        ]:
            if flag_name in event:
                flags[flag_name] = event[flag_name]

        if event_type == "GUARDED_PAPER_RUNTIME_AUDIT":
            counts["runtime_audit_events"] += 1
            if event.get("accepted_diagnostic") is True:
                counts["runtime_accepts_diagnostic"] += 1
            else:
                counts["runtime_rejects"] += 1
        elif event_type == "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT":
            counts["routing_bridge_events"] += 1
            if event.get("would_route") is True:
                counts["would_route_count"] += 1
            if event.get("would_submit") is True:
                counts["would_submit_count"] += 1
            
            counts["orders_submitted_by_bridge"] += int(event.get("orders_submitted_by_bridge") or 0)
            counts["positions_opened_by_bridge"] += int(event.get("positions_opened_by_bridge") or 0)
            
    return {"counts": counts, "flags": flags}


def print_runner_once_footer_from_events(
    events_path: str | Path,
    *,
    started_at: datetime | None = None,
    stream: TextIO | None = None,
    force: bool = False,
) -> bool:
    cycle_event = read_latest_cycle_completed(events_path, started_at=started_at)
    if cycle_event is None:
        return False

    cycle_id = cycle_event.get("cycle_id") or ""
    audit_data = collect_cycle_audit_counts(events_path, cycle_id)
    
    summary = {}
    # Reconstruct from CYCLE_COMPLETED
    for field_name in [
        "cycle_id", "scanned", "signals", "orders", "open_positions", 
        "errors", "elapsed_seconds", "no_signal", "balance", "equity", 
        "pending_orders", "drawdown_pct", "realized_pnl", "unrealized_pnl"
    ]:
        if field_name in cycle_event:
            summary[field_name] = cycle_event[field_name]

    # Reconstruct from collected flags and audit counts
    summary.update(audit_data["flags"])
    
    # Fallback default values
    summary.setdefault("operational_unlock_allowed", False)
    summary.setdefault("live_allowed", False)
    summary.setdefault("testnet_allowed", False)
    summary.setdefault("exchange_broker_allowed", False)
    summary.setdefault("orders_submitted_by_bridge", 0)
    summary.setdefault("positions_opened_by_bridge", 0)
    summary.setdefault("routing_mode", summary.get("routing_mode", "paper_only"))
    summary.setdefault("submission_mode", summary.get("submission_mode", "simulation_only"))
    summary.setdefault("footer_source", "runner_event_fallback")
    summary.setdefault("prompt", "29.4.4o-3c")
    
    runtime_audit = {
        "decision": {
            "runtime_audit_events": audit_data["counts"]["runtime_audit_events"],
            "runtime_accepts_diagnostic": audit_data["counts"]["runtime_accepts_diagnostic"],
            "runtime_rejects": audit_data["counts"]["runtime_rejects"],
        },
        "paper_orders_enabled": summary.get("paper_orders_enabled", False),
        "paper_unlock_experiment_allowed": summary.get("paper_unlock_experiment_allowed", False),
        "operational_unlock_allowed": summary.get("operational_unlock_allowed", False),
        "manual_activation_allowed": summary.get("manual_activation_allowed", "unknown"),
        "live_allowed": summary.get("live_allowed", False),
        "testnet_allowed": summary.get("testnet_allowed", False),
        "exchange_broker_allowed": summary.get("exchange_broker_allowed", False),
    }

    routing_bridge = {
        "decision": {
            "routing_bridge_events": audit_data["counts"]["routing_bridge_events"],
            "would_route_count": audit_data["counts"]["would_route_count"],
            "would_submit_count": audit_data["counts"]["would_submit_count"],
            "orders_submitted_by_bridge": audit_data["counts"]["orders_submitted_by_bridge"],
            "positions_opened_by_bridge": audit_data["counts"]["positions_opened_by_bridge"],
        },
        "paper_orders_enabled": summary.get("paper_orders_enabled", False),
        "paper_unlock_experiment_allowed": summary.get("paper_unlock_experiment_allowed", False),
        "operational_unlock_allowed": summary.get("operational_unlock_allowed", False),
        "manual_activation_allowed": summary.get("manual_activation_allowed", "unknown"),
        "live_allowed": summary.get("live_allowed", False),
        "testnet_allowed": summary.get("testnet_allowed", False),
        "exchange_broker_allowed": summary.get("exchange_broker_allowed", False),
    }

    print_paper_once_console_summary(
        summary,
        runtime_audit=runtime_audit,
        routing_bridge=routing_bridge,
        stream=stream,
        flush=True,
    )
    return True
