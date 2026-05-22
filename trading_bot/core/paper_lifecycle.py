"""Prompt 29.1 paper lifecycle reconciliation utilities.

This module audits the local paper runtime files produced by the paper engine:

- data/paper_state.json
- data/paper_events.jsonl
- data/paper_status.json

It is intentionally exchange-free and deterministic.  The goal is not to prove
strategy quality; the goal is to prove that state, lifecycle events and exported
status remain internally coherent across cycles, shutdowns and restarts.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re


CYCLE_ID_RE = re.compile(r"pc_(\d+)_[0-9a-fA-F]+")


@dataclass(frozen=True)
class PaperRuntimePaths:
    data_dir: Path

    @property
    def state_path(self) -> Path:
        return self.data_dir / "paper_state.json"

    @property
    def events_path(self) -> Path:
        return self.data_dir / "paper_events.jsonl"

    @property
    def status_path(self) -> Path:
        return self.data_dir / "paper_status.json"

    @property
    def report_path(self) -> Path:
        return self.data_dir / "paper_lifecycle_report.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"__read_error__": str(exc)}


def read_events(events_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not events_path.exists():
        return events
    for line_no, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
            if isinstance(event, dict):
                event["__line_no__"] = line_no
                events.append(event)
        except Exception:
            events.append({"event_type": "__INVALID_JSON__", "raw": raw[:500], "__line_no__": line_no})
    return events


def max_cycle_sequence(events_path: Path) -> int:
    max_seq = 0
    for event in read_events(events_path):
        cycle_id = str(event.get("cycle_id") or "")
        match = CYCLE_ID_RE.fullmatch(cycle_id)
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return max_seq


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "").upper()


def _order_ids_from_events(events: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for event in events:
        if event.get("order_id"):
            ids.append(str(event["order_id"]))
        order = event.get("order")
        if isinstance(order, dict) and order.get("order_id"):
            ids.append(str(order["order_id"]))
    return ids


def _position_ids_from_events(events: list[dict[str, Any]], event_names: set[str]) -> set[str]:
    ids: set[str] = set()
    for event in events:
        if _event_type(event) not in event_names:
            continue
        if event.get("position_id"):
            ids.add(str(event["position_id"]))
        position = event.get("position")
        if isinstance(position, dict) and position.get("position_id"):
            ids.add(str(position["position_id"]))
    return ids


def build_lifecycle_report(data_dir: str | Path) -> dict[str, Any]:
    paths = PaperRuntimePaths(Path(data_dir))
    state = _read_json(paths.state_path)
    status = _read_json(paths.status_path)
    events = read_events(paths.events_path)
    event_counts = Counter(_event_type(e) for e in events)

    warnings: list[str] = []
    errors: list[str] = []

    for name, payload in (("state", state), ("status", status)):
        if payload.get("__read_error__"):
            errors.append(f"{name}_json_read_error: {payload['__read_error__']}")

    cycle_events: dict[str, list[str]] = defaultdict(list)
    for event in events:
        cycle_id = event.get("cycle_id")
        if cycle_id:
            cycle_events[str(cycle_id)].append(_event_type(event))

    started_cycle_ids = [str(e.get("cycle_id")) for e in events if _event_type(e) == "CYCLE_STARTED" and e.get("cycle_id")]
    completed_cycle_ids = [str(e.get("cycle_id")) for e in events if _event_type(e) == "CYCLE_COMPLETED" and e.get("cycle_id")]
    interrupted_cycle_ids = sorted(set(started_cycle_ids) - set(completed_cycle_ids))

    cycle_id_counts = Counter(started_cycle_ids)
    duplicate_cycle_ids = sorted([cycle_id for cycle_id, count in cycle_id_counts.items() if count > 1])
    cycle_sequences = []
    for cycle_id in started_cycle_ids:
        match = CYCLE_ID_RE.fullmatch(cycle_id)
        if match:
            cycle_sequences.append(int(match.group(1)))
    duplicate_cycle_sequences = sorted([seq for seq, count in Counter(cycle_sequences).items() if count > 1])
    if interrupted_cycle_ids:
        warnings.append(f"interrupted_cycles_detected: {interrupted_cycle_ids[:10]}")
    if duplicate_cycle_ids:
        errors.append(f"duplicate_cycle_id: {duplicate_cycle_ids[:10]}")
    if duplicate_cycle_sequences:
        warnings.append(f"duplicate_cycle_sequence: {duplicate_cycle_sequences[:10]}")

    submitted_order_ids = [
        str(event.get("order_id"))
        for event in events
        if _event_type(event) in {"PAPER_ORDER_SUBMITTED", "ORDER_SUBMITTED"} and event.get("order_id")
    ]
    duplicate_order_ids = sorted([order_id for order_id, count in Counter(submitted_order_ids).items() if count > 1])
    state_orders = state.get("orders", {}) if isinstance(state.get("orders"), dict) else {}
    if duplicate_order_ids:
        errors.append(f"duplicate_order_id: {duplicate_order_ids[:10]}")

    positions = state.get("positions", {}) if isinstance(state.get("positions"), dict) else {}
    opened_position_ids = _position_ids_from_events(events, {"POSITION_OPENED", "POSITION_OPENED"})
    closed_position_ids = _position_ids_from_events(events, {"POSITION_CLOSED", "POSITION_CLOSED"})
    # Compatibility with Prompt 29 lower-case historical events.
    opened_position_ids |= _position_ids_from_events(events, {"POSITION_OPENED"})
    closed_position_ids |= _position_ids_from_events(events, {"POSITION_CLOSED"})

    for position_id, position in positions.items():
        status_value = str(position.get("status", "")).upper()
        if status_value == "OPEN" and position_id not in opened_position_ids:
            warnings.append(f"open_position_missing_open_event: {position_id}")
        if status_value == "CLOSED" and position_id not in closed_position_ids:
            warnings.append(f"closed_position_missing_close_event: {position_id}")

    for order_id, order in state_orders.items():
        order_status = str(order.get("status", "")).upper()
        if order_status == "FILLED":
            has_fill_event = any(
                (
                    (str(event.get("order_id") or "") == order_id)
                    or (isinstance(event.get("order"), dict) and str(event["order"].get("order_id") or "") == order_id)
                )
                and _event_type(event) in {"ORDER_FILLED", "PAPER_ORDER_FILLED", "ORDER_FILLED"}
                for event in events
            )
            if not has_fill_event:
                warnings.append(f"filled_order_missing_fill_event: {order_id}")

    state_balance = state.get("balance")
    status_balance = status.get("balance")
    if isinstance(state_balance, (int, float)) and isinstance(status_balance, (int, float)):
        if abs(float(state_balance) - float(status_balance)) > 1e-6:
            warnings.append(f"balance_mismatch_state_status: state={state_balance} status={status_balance}")

    state_open_positions = sum(1 for p in positions.values() if str(p.get("status", "")).upper() == "OPEN")
    status_open_positions = status.get("open_positions")
    if isinstance(status_open_positions, int) and state_open_positions != status_open_positions:
        warnings.append(f"open_positions_mismatch_state_status: state={state_open_positions} status={status_open_positions}")

    lifecycle_status = "PASS"
    if warnings:
        lifecycle_status = "WARN"
    if errors:
        lifecycle_status = "FAIL"

    report = {
        "generated_at": utc_now_iso(),
        "status": lifecycle_status,
        "files": {
            "state": str(paths.state_path),
            "events": str(paths.events_path),
            "status": str(paths.status_path),
        },
        "cycles": {
            "started": len(started_cycle_ids),
            "completed": len(completed_cycle_ids),
            "interrupted": len(interrupted_cycle_ids),
            "interrupted_cycle_ids": interrupted_cycle_ids[:50],
            "duplicate_cycle_ids": duplicate_cycle_ids[:50],
            "duplicate_cycle_sequences": duplicate_cycle_sequences[:50],
            "max_cycle_sequence": max_cycle_sequence(paths.events_path),
        },
        "events": {
            "total": len(events),
            "by_type": dict(sorted(event_counts.items())),
            "per_cycle": {cycle_id: dict(Counter(types)) for cycle_id, types in list(cycle_events.items())[-50:]},
        },
        "orders": {
            "state_total": len(state_orders),
            "created_or_submitted_events": event_counts.get("PAPER_ORDER_SUBMITTED", 0) + event_counts.get("ORDER_SUBMITTED", 0),
            "filled_events": event_counts.get("ORDER_FILLED", 0) + event_counts.get("PAPER_ORDER_FILLED", 0),
            "rejected_events": event_counts.get("SIGNAL_REJECTED", 0) + event_counts.get("ORDER_REJECTED", 0),
            "duplicate_order_ids": duplicate_order_ids[:50],
        },
        "positions": {
            "state_total": len(positions),
            "open": state_open_positions,
            "closed": sum(1 for p in positions.values() if str(p.get("status", "")).upper() == "CLOSED"),
            "opened_events": event_counts.get("POSITION_OPENED", 0),
            "closed_events": event_counts.get("POSITION_CLOSED", 0),
        },
        "reconciliation": {
            "warnings": warnings,
            "errors": errors,
            "mismatch_count": len(warnings) + len(errors),
        },
        "final_status": {
            "balance": status.get("balance", state.get("balance")),
            "equity": status.get("equity"),
            "open_positions": status.get("open_positions", state_open_positions),
            "kill_switch": status.get("kill_switch", state.get("kill_switch")),
            "is_paused": status.get("is_paused", state.get("is_paused")),
        },
    }
    return report


def write_lifecycle_report(data_dir: str | Path) -> dict[str, Any]:
    paths = PaperRuntimePaths(Path(data_dir))
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    report = build_lifecycle_report(paths.data_dir)
    paths.report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
