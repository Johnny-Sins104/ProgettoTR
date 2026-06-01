"""Prompt 29.4.4t-2 paper runner footer / console visibility consolidation.

This module is console/read-only glue for ``run_paper_trading.py --once``.
It reconstructs the once-cycle footer from ``paper_events.jsonl`` when the
engine-side footer is missed by the watchdog hard-exit path.  The t-2 change adds LSR-v2 dashboard/lifecycle artifact footer visibility by
loading the read-only engine artifact hook report from the same ``data``
directory. Missing or hostile reports are represented fail-closed in the
footer instead of being omitted or trusted blindly.

It never submits orders, never calls a broker, and never mutates paper state.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, TextIO

try:
    from .jsonl_utils import iter_jsonl_tail
except Exception:  # pragma: no cover - script-style fallback
    from core.jsonl_utils import iter_jsonl_tail  # type: ignore

try:  # package import in tests/full project
    from .paper_once_console_summary import print_paper_once_console_summary
except Exception:  # pragma: no cover - script-style fallback
    from paper_once_console_summary import print_paper_once_console_summary  # type: ignore

PROMPT_ID = "29.4.4t-2"
LSR_V2_BRIDGE_REPORT_NAME = "lsr_v2_paper_supervised_bridge_report.json"
LSR_V2_RUNTIME_BRIDGE_REPORT_NAME = "lsr_v2_runtime_bridge_report.json"
RUNTIME_AUDIT_REPORT_NAME = "paper_unlock_runtime_audit_report.json"
ROUTING_BRIDGE_REPORT_NAME = "paper_unlock_routing_bridge_report.json"
LSR_V2_ENGINE_ARTIFACT_HOOK_REPORT_NAME = "lsr_v2_engine_read_only_artifact_hook_report.json"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "y"}:
            return True
        if lowered in {"0", "false", "no", "off", "n"}:
            return False
    if value is None:
        return default
    return bool(value)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        raw = str(value).strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _json_load(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    return iter_jsonl_tail(path, max_lines=50000, require_event_type=False)

def _after_started(event: Mapping[str, Any], started_at: datetime | None) -> bool:
    if started_at is None:
        return True
    started = started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    started = started.astimezone(timezone.utc)
    ts = _parse_ts(event.get("ts") or event.get("timestamp") or event.get("created_at"))
    if ts is None:
        return True
    return ts >= started


def read_latest_cycle_completed(events_path: str | Path, *, started_at: datetime | None = None) -> dict[str, Any] | None:
    """Return the latest CYCLE_COMPLETED event visible to the runner fallback."""
    latest: dict[str, Any] | None = None
    for event in _iter_jsonl(Path(events_path)):
        if event.get("event_type") != "CYCLE_COMPLETED":
            continue
        if not _after_started(event, started_at):
            continue
        latest = dict(event)
    return latest


def _count_runtime_audit_events(events_path: Path, *, started_at: datetime | None = None) -> dict[str, int]:
    runtime_events = 0
    accepts = 0
    rejects = 0
    for event in _iter_jsonl(events_path):
        if event.get("event_type") != "GUARDED_PAPER_RUNTIME_AUDIT":
            continue
        if not _after_started(event, started_at):
            continue
        runtime_events += 1
        accepted = _safe_bool(event.get("runtime_accept_diagnostic", event.get("accept_diagnostic", event.get("accepted", False))))
        if accepted:
            accepts += 1
        else:
            rejects += 1
    return {
        "runtime_audit_events": runtime_events,
        "runtime_accepts_diagnostic": accepts,
        "runtime_rejects": rejects,
    }


def _count_routing_bridge_events(events_path: Path, *, started_at: datetime | None = None) -> dict[str, int]:
    events = 0
    would_route = 0
    would_submit = 0
    orders = 0
    positions = 0
    for event in _iter_jsonl(events_path):
        if event.get("event_type") != "GUARDED_PAPER_ROUTING_BRIDGE_AUDIT":
            continue
        if not _after_started(event, started_at):
            continue
        events += 1
        would_route += 1 if _safe_bool(event.get("would_route"), False) else 0
        would_submit += 1 if _safe_bool(event.get("would_submit"), False) else 0
        orders += _safe_int(event.get("orders_submitted_by_bridge"), 0)
        positions += _safe_int(event.get("positions_opened_by_bridge"), 0)
    return {
        "routing_bridge_events": events,
        "would_route_count": would_route,
        "would_submit_count": would_submit,
        "orders_submitted_by_bridge": orders,
        "positions_opened_by_bridge": positions,
    }


def _load_runtime_audit_summary(data_dir: Path, events_path: Path, *, started_at: datetime | None = None) -> dict[str, Any]:
    report = _json_load(data_dir / RUNTIME_AUDIT_REPORT_NAME)
    counts = _count_runtime_audit_events(events_path, started_at=started_at)
    decision_payload = {
        "runtime_audit_events": _safe_int(report.get("runtime_audit_events"), counts["runtime_audit_events"]),
        "runtime_accepts_diagnostic": _safe_int(report.get("runtime_accepts_diagnostic"), counts["runtime_accepts_diagnostic"]),
        "runtime_rejects": _safe_int(report.get("runtime_rejects"), counts["runtime_rejects"]),
    }
    return {
        "decision": decision_payload,
        "paper_orders_enabled": report.get("paper_orders_enabled", False),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed", False),
        "manual_activation_allowed": report.get("manual_activation_allowed", False),
        "operational_unlock_allowed": report.get("operational_unlock_allowed", False),
        "live_allowed": report.get("live_allowed", False),
        "testnet_allowed": report.get("testnet_allowed", False),
        "exchange_broker_allowed": report.get("exchange_broker_allowed", False),
    }


def _load_routing_bridge_summary(data_dir: Path, events_path: Path, *, started_at: datetime | None = None) -> dict[str, Any]:
    report = _json_load(data_dir / ROUTING_BRIDGE_REPORT_NAME)
    counts = _count_routing_bridge_events(events_path, started_at=started_at)
    decision_payload = {
        "routing_bridge_events": _safe_int(report.get("routing_bridge_events"), counts["routing_bridge_events"]),
        "would_route_count": _safe_int(report.get("would_route_count"), counts["would_route_count"]),
        "would_submit_count": _safe_int(report.get("would_submit_count"), counts["would_submit_count"]),
        "orders_submitted_by_bridge": _safe_int(report.get("orders_submitted_by_bridge"), counts["orders_submitted_by_bridge"]),
        "positions_opened_by_bridge": _safe_int(report.get("positions_opened_by_bridge"), counts["positions_opened_by_bridge"]),
    }
    return {
        "decision": decision_payload,
        "paper_orders_enabled": report.get("paper_orders_enabled", False),
        "paper_unlock_experiment_allowed": report.get("paper_unlock_experiment_allowed", False),
        "manual_activation_allowed": report.get("manual_activation_allowed", False),
        "operational_unlock_allowed": report.get("operational_unlock_allowed", False),
        "live_allowed": report.get("live_allowed", False),
        "testnet_allowed": report.get("testnet_allowed", False),
        "exchange_broker_allowed": report.get("exchange_broker_allowed", False),
    }


def load_lsr_v2_bridge_footer_summary(data_dir: str | Path) -> dict[str, Any]:
    """Load or synthesize fail-closed LSR-v2 footer metrics.

    The synthesis path is intentional: omitting LSR-v2 lines in the hard-exit
    footer makes operator verification ambiguous. Missing reports therefore
    produce explicit zero metrics and a diagnostic decision, never execution.
    """
    data_dir = Path(data_dir)
    report = _json_load(data_dir / LSR_V2_BRIDGE_REPORT_NAME)
    if not report:
        report = {
            "status": "WARN",
            "decision": "KEEP_DIAGNOSTIC_LSR_V2_BRIDGE_REPORT_MISSING",
            "bridge_events": 0,
            "candidate_ready_events": 0,
            "would_route_count": 0,
            "would_submit_count": 0,
            "orders_submitted_by_lsr_v2_bridge": 0,
            "positions_opened_by_lsr_v2_bridge": 0,
        }
    # Force-pin fail-closed invariants before presentation.
    report = dict(report)
    report["would_submit_count"] = 0
    report["orders_submitted_by_lsr_v2_bridge"] = 0
    report["positions_opened_by_lsr_v2_bridge"] = 0
    report["broker_submit_called"] = False
    report["paper_order_submission_enabled"] = False
    report["execution_enabled"] = False
    report["routing_enabled"] = False
    report["promotion_ready"] = False
    return report


def _count_lsr_v2_runtime_bridge_events(
    events_path: Path,
    *,
    cycle_id: str | None = None,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Count cycle-scoped LSR-v2 runtime events directly from paper_events.jsonl.

    This is the hard-exit watchdog source of truth. The JSON report may be
    written after the runner fallback footer, while broker events are appended
    immediately during ``evaluate_symbol``.
    """
    candidate_events = 0
    bridge_events = 0
    candidate_ready = 0
    would_route = 0
    would_submit = 0
    orders = 0
    positions = 0
    operator_enable = False
    operator_confirmation_ok = False
    operator_authorized = False
    latest_cycle = str(cycle_id or "")
    for event in _iter_jsonl(events_path):
        if not _after_started(event, started_at):
            continue
        event_cycle = str(event.get("cycle_id") or "")
        if cycle_id and event_cycle != str(cycle_id):
            continue
        event_type = event.get("event_type")
        is_candidate = event_type == "LSR_V2_RUNTIME_CANDIDATE_AUDIT"
        is_bridge = event_type == "LSR_V2_PAPER_SUPERVISED_BRIDGE_AUDIT" and _safe_bool(event.get("runtime_cycle_scoped"), False)
        if not is_candidate and not is_bridge:
            continue
        if event_cycle:
            latest_cycle = event_cycle
        if is_candidate:
            candidate_events += 1
            if _safe_bool(event.get("candidate_ready"), False):
                candidate_ready += 1
        if is_bridge:
            bridge_events += 1
            would_route += 1 if _safe_bool(event.get("would_route"), False) else 0
            would_submit += 1 if _safe_bool(event.get("would_submit"), False) else 0
            orders += _safe_int(event.get("orders_submitted_by_lsr_v2_runtime_bridge"), 0)
            positions += _safe_int(event.get("positions_opened_by_lsr_v2_runtime_bridge"), 0)
            operator_enable = operator_enable or _safe_bool(event.get("operator_enable"), False)
            operator_confirmation_ok = operator_confirmation_ok or _safe_bool(event.get("operator_confirmation_ok"), False)
            operator_authorized = operator_authorized or _safe_bool(event.get("operator_authorized"), False)
    return {
        "cycle_id": latest_cycle,
        "runtime_bridge_events": bridge_events,
        "runtime_candidate_events": candidate_events,
        "runtime_candidate_ready_events": candidate_ready,
        "runtime_would_route_count": would_route,
        "runtime_would_submit_count": would_submit,
        "orders_submitted_by_lsr_v2_runtime_bridge": orders,
        "positions_opened_by_lsr_v2_runtime_bridge": positions,
        "operator_enable": bool(operator_enable),
        "operator_confirmation_ok": bool(operator_confirmation_ok),
        "operator_authorized": bool(operator_authorized),
        "lsr_v2_operator_enable": bool(operator_enable),
        "lsr_v2_operator_confirmation_ok": bool(operator_confirmation_ok),
    }


def load_lsr_v2_runtime_bridge_footer_summary(
    data_dir: str | Path,
    *,
    events_path: str | Path | None = None,
    cycle_id: str | None = None,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    """Load cycle-scoped LSR-v2 runtime bridge footer metrics.

    Prompt 29.4.4t-2 keeps ``paper_events.jsonl`` the primary source for the
    watchdog footer. The JSON report remains a secondary fallback for normal
    shutdowns.
    """
    data_dir = Path(data_dir)
    report = _json_load(data_dir / LSR_V2_RUNTIME_BRIDGE_REPORT_NAME)
    counts = (
        _count_lsr_v2_runtime_bridge_events(Path(events_path), cycle_id=cycle_id, started_at=started_at)
        if events_path is not None
        else {
            "cycle_id": str(cycle_id or ""),
            "runtime_bridge_events": 0,
            "runtime_candidate_events": 0,
            "runtime_candidate_ready_events": 0,
            "runtime_would_route_count": 0,
            "runtime_would_submit_count": 0,
            "orders_submitted_by_lsr_v2_runtime_bridge": 0,
            "positions_opened_by_lsr_v2_runtime_bridge": 0,
            "operator_enable": False,
            "operator_confirmation_ok": False,
            "operator_authorized": False,
            "lsr_v2_operator_enable": False,
            "lsr_v2_operator_confirmation_ok": False,
        }
    )
    has_event_log_counts = _safe_int(counts.get("runtime_bridge_events"), 0) > 0 or _safe_int(counts.get("runtime_candidate_events"), 0) > 0
    if has_event_log_counts:
        base = dict(report) if report else {}
        base.update(counts)
        base["decision"] = "LSR_V2_RUNTIME_CYCLE_BRIDGE_READY_DIAGNOSTIC"
        base["status"] = "PASS"
    elif report:
        base = dict(report)
    else:
        base = {
            "status": "WARN",
            "decision": "KEEP_DIAGNOSTIC_LSR_V2_RUNTIME_BRIDGE_REPORT_MISSING",
            "cycle_id": str(cycle_id or ""),
            "runtime_bridge_events": 0,
            "runtime_candidate_events": 0,
            "runtime_candidate_ready_events": 0,
            "runtime_would_route_count": 0,
            "runtime_would_submit_count": 0,
            "orders_submitted_by_lsr_v2_runtime_bridge": 0,
            "positions_opened_by_lsr_v2_runtime_bridge": 0,
            "standalone_bridge_events": 0,
            "lsr_v2_bridge_report_cycle_id": "",
            "lsr_v2_bridge_report_stale": True,
        }

    standalone = _json_load(data_dir / LSR_V2_BRIDGE_REPORT_NAME)
    standalone_cycle = str(standalone.get("latest_cycle_id") or standalone.get("cycle_id") or "") if standalone else ""
    current_cycle = str(base.get("cycle_id") or cycle_id or "")
    base.setdefault("standalone_bridge_events", _safe_int(standalone.get("bridge_events"), 0) if standalone else 0)
    if standalone:
        base["lsr_v2_bridge_report_cycle_id"] = standalone_cycle
        base["lsr_v2_bridge_report_stale"] = bool(current_cycle and standalone_cycle != current_cycle)
    else:
        base.setdefault("lsr_v2_bridge_report_cycle_id", "")
        base.setdefault("lsr_v2_bridge_report_stale", bool(base.get("lsr_v2_bridge_report_stale", False)))

    # Force-pin fail-closed invariants before presentation.
    base["runtime_would_submit_count"] = 0
    base["would_submit_count"] = 0
    base["orders_submitted_by_lsr_v2_runtime_bridge"] = 0
    base["positions_opened_by_lsr_v2_runtime_bridge"] = 0
    base["broker_submit_called"] = False
    base["paper_order_submission_enabled"] = False
    base["execution_enabled"] = False
    base["routing_enabled"] = False
    base["promotion_ready"] = False
    return base


def load_lsr_v2_engine_artifact_hook_footer_summary(data_dir: str | Path) -> dict[str, Any]:
    """Load read-only LSR-v2 dashboard/lifecycle artifact status for once footers.

    Prompt 29.4.4t-2 is console visibility only. Missing reports are surfaced
    explicitly and all execution/network counters are force-pinned fail-closed.
    """
    data_dir = Path(data_dir)
    report = _json_load(data_dir / LSR_V2_ENGINE_ARTIFACT_HOOK_REPORT_NAME)
    if report:
        base = dict(report)
    else:
        base = {
            "status": "WARN",
            "decision": "KEEP_DIAGNOSTIC_LSR_V2_ENGINE_ARTIFACT_HOOK_REPORT_MISSING",
            "engine_artifact_hook_ready": False,
            "paper_engine_hook_read_only": True,
            "telegram_dashboard_ready": False,
            "lifecycle_auto_monitor_ready": False,
            "three_trade_postmortem_ready": False,
            "lifecycle_state": "UNKNOWN",
            "telegram_payload_ready": False,
            "telegram_update_ready": False,
            "visual_sl_tp_progress_bar_ready": False,
            "visual_sl_tp_progress_bar": "",
            "fourth_trade_locked": False,
            "stability_lock_active": False,
            "telegram_send_allowed": False,
            "telegram_network_called": False,
        }

    # Footer safety pins. This formatter must never present executable state as
    # active, even if a malformed report claims otherwise.
    base["telegram_send_allowed"] = False
    base["telegram_network_called"] = False
    base["scheduler_enabled"] = False
    base["scheduler_started"] = False
    base["orders_submitted_by_engine_artifact_hook"] = 0
    base["positions_opened_by_engine_artifact_hook"] = 0
    base["positions_closed_by_engine_artifact_hook"] = 0
    base["broker_submit_called_by_engine_artifact_hook"] = False
    base["broker_close_called_by_engine_artifact_hook"] = False
    base["paper_state_modified_by_engine_artifact_hook"] = False
    base["paper_status_modified_by_engine_artifact_hook"] = False
    base["live_enabled"] = False
    base["testnet_enabled"] = False
    base["exchange_broker_enabled"] = False
    base["operational_unlock_allowed"] = False
    base["promotion_ready"] = False
    return base


def print_runner_once_footer_from_events(
    events_path: str | Path,
    *,
    started_at: datetime | None = None,
    stream: TextIO | None = None,
    force: bool = False,
) -> bool:
    """Print the once footer from persisted events and local diagnostic reports.

    Returns True when a completed cycle was found and a footer was printed.
    ``force`` is accepted for backward compatibility with the watchdog caller.
    """
    del force  # footer print is idempotent from caller perspective; no state here
    events_path = Path(events_path)
    cycle_event = read_latest_cycle_completed(events_path, started_at=started_at)
    if not cycle_event:
        return False

    data_dir = events_path.parent
    summary = dict(cycle_event)
    summary["prompt"] = PROMPT_ID
    summary["footer_source"] = "runner_event_fallback"

    runtime_audit = _load_runtime_audit_summary(data_dir, events_path, started_at=started_at)
    routing_bridge = _load_routing_bridge_summary(data_dir, events_path, started_at=started_at)
    lsr_v2_bridge = load_lsr_v2_bridge_footer_summary(data_dir)
    lsr_v2_runtime_bridge = load_lsr_v2_runtime_bridge_footer_summary(data_dir, events_path=events_path, cycle_id=str(cycle_event.get("cycle_id") or ""), started_at=started_at)
    lsr_v2_engine_artifact_hook = load_lsr_v2_engine_artifact_hook_footer_summary(data_dir)

    print_paper_once_console_summary(
        summary,
        runtime_audit=runtime_audit,
        routing_bridge=routing_bridge,
        lsr_v2_bridge=lsr_v2_bridge,
        lsr_v2_runtime_bridge=lsr_v2_runtime_bridge,
        lsr_v2_engine_artifact_hook=lsr_v2_engine_artifact_hook,
        stream=stream,
        flush=True,
    )
    return True
