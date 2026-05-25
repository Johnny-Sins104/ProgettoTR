"""Prompt 29.4.4r-1 legacy paper order leakage audit and fail-closed guard.

This module is deliberately paper-safety only.  It does not submit orders, does
not open positions, and does not enable live/testnet/exchange broker execution.
It blocks legacy paper order attempts that are not sourced from the guarded
candidate/handoff path and produces a diagnostic report over paper_events.jsonl.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json

from config import Config

PROMPT_ID = "29.4.4r-1"
LEAKAGE_EVENT_TYPE = "LEGACY_PAPER_ORDER_LEAKAGE_AUDIT"
BLOCKED_EVENT_TYPE = "LEGACY_PAPER_ORDER_BLOCKED"
REPORT_NAME = "paper_order_leakage_guard_report.json"
READY_DECISION = "LEGACY_PAPER_ORDER_GUARD_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"
ORDER_EVENT_TYPES = {"PAPER_ORDER_SUBMITTED", "PAPER_ORDER_CONFIRMED", "ORDER_FILLED"}
POSITION_EVENT_TYPES = {"POSITION_OPENED"}
CYCLE_EVENT_TYPE = "CYCLE_COMPLETED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


def _iter_jsonl_events(path: str | Path, *, max_lines: int = 50000) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    if max_lines > 0 and len(lines) > max_lines:
        lines = lines[-max_lines:]
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("event_type"):
            out.append(item)
    return out


def _counts(values: Iterable[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        key = str(value if value not in {None, ""} else "-")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _nested_mapping(event: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = event.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _event_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    order = _nested_mapping(event, "order")
    position = _nested_mapping(event, "position")
    metadata = event.get("metadata")
    if isinstance(metadata, Mapping):
        return dict(metadata)
    for source in (order, position):
        nested = source.get("metadata")
        if isinstance(nested, Mapping):
            return dict(nested)
    return {}


def _order_id(event: Mapping[str, Any]) -> str:
    order = _nested_mapping(event, "order")
    return str(event.get("order_id") or order.get("order_id") or "")


def _position_id(event: Mapping[str, Any]) -> str:
    position = _nested_mapping(event, "position")
    return str(event.get("position_id") or position.get("position_id") or "")


def _event_cycle_id(event: Mapping[str, Any]) -> str:
    metadata = _event_metadata(event)
    return str(event.get("cycle_id") or metadata.get("cycle_id") or "")


def _event_symbol(event: Mapping[str, Any]) -> str:
    order = _nested_mapping(event, "order")
    position = _nested_mapping(event, "position")
    return str(event.get("symbol") or order.get("symbol") or position.get("symbol") or "")


def _event_side(event: Mapping[str, Any]) -> str:
    order = _nested_mapping(event, "order")
    position = _nested_mapping(event, "position")
    return str(event.get("side") or order.get("side") or position.get("side") or "")


def _source_reason(metadata: Mapping[str, Any]) -> str:
    combination = str(metadata.get("combination") or metadata.get("reason") or metadata.get("setup_archetype") or metadata.get("archetype") or "").strip()
    if not combination:
        return "unknown"
    return combination


def _event_source_path(event: Mapping[str, Any]) -> str:
    metadata = _event_metadata(event)
    if _safe_bool(metadata.get("guarded_supervised_execution")):
        return "guarded_supervised_execution"
    if _safe_bool(metadata.get("paper_unlock")):
        return "paper_unlock_legacy_execution"
    source = str(metadata.get("paper_order_source") or metadata.get("execution_source") or "").strip()
    if source:
        return source
    reason = _source_reason(metadata)
    if "ScoreOnly" in reason or "Meta_OK" in reason:
        return "legacy_score_meta"
    return "legacy_or_unknown"


@dataclass(frozen=True)
class PaperOrderLeakageGuardSettings:
    enabled: bool = True
    fail_closed: bool = True
    allow_supervised_guarded_execution: bool = False
    report_name: str = REPORT_NAME
    events_name: str = "paper_events.jsonl"
    status_name: str = "paper_status.json"
    max_event_lines: int = 50000
    event_type: str = LEAKAGE_EVENT_TYPE
    blocked_event_type: str = BLOCKED_EVENT_TYPE
    allowed_order_source: str = "NONE"

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperOrderLeakageGuardSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_ENABLED", True)),
            fail_closed=bool(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_FAIL_CLOSED", True)),
            allow_supervised_guarded_execution=bool(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_ALLOW_SUPERVISED", False)),
            report_name=str(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            status_name=str(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_STATUS_NAME", "paper_status.json") or "paper_status.json"),
            max_event_lines=max(1000, _safe_int(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_MAX_EVENT_LINES", 50000), 50000)),
            event_type=str(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_EVENT_TYPE", LEAKAGE_EVENT_TYPE) or LEAKAGE_EVENT_TYPE),
            blocked_event_type=str(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_BLOCKED_EVENT_TYPE", BLOCKED_EVENT_TYPE) or BLOCKED_EVENT_TYPE),
            allowed_order_source=str(getattr(cfg, "PAPER_ORDER_LEAKAGE_GUARD_ALLOWED_SOURCE", "NONE") or "NONE"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "fail_closed": self.fail_closed,
            "allow_supervised_guarded_execution": self.allow_supervised_guarded_execution,
            "report_name": self.report_name,
            "events_name": self.events_name,
            "status_name": self.status_name,
            "max_event_lines": self.max_event_lines,
            "event_type": self.event_type,
            "blocked_event_type": self.blocked_event_type,
            "allowed_order_source": self.allowed_order_source,
        }


def is_order_source_authorized(*, settings: PaperOrderLeakageGuardSettings, metadata: Mapping[str, Any] | None = None) -> bool:
    """Return whether a paper order source is allowed in the current patch.

    In 29.4.4r-1 the default is intentionally NONE: no paper order may be
    created by the legacy engine or by the guarded dry-run path. A later
    supervised paper execution patch must opt in explicitly with a separate flag.
    """
    metadata = dict(metadata or {})
    if not settings.enabled:
        return True
    if not settings.fail_closed:
        return True
    if settings.allow_supervised_guarded_execution and _safe_bool(metadata.get("guarded_supervised_execution")):
        return True
    return False


def should_block_paper_order_attempt(*, settings: PaperOrderLeakageGuardSettings, metadata: Mapping[str, Any] | None = None) -> bool:
    return bool(settings.enabled and settings.fail_closed and not is_order_source_authorized(settings=settings, metadata=metadata))


def build_legacy_paper_order_blocked_event(
    *,
    settings: PaperOrderLeakageGuardSettings,
    cycle_id: str,
    symbol: str,
    side: str,
    score: Any = None,
    confidence: Mapping[str, Any] | None = None,
    combination: str = "",
    candle_ts: str = "",
    entry_price: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    qty: float | None = None,
    notional: float | None = None,
    risk_amount: float | None = None,
    paper_unlock: bool = False,
    unlock_profile: str | None = None,
    source_path: str = "legacy_score_meta",
    blocked_reason: str = "paper_order_source_not_authorized",
) -> dict[str, Any]:
    confidence = dict(confidence or {})
    return {
        "event_type": settings.blocked_event_type,
        "prompt": PROMPT_ID,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "side": side,
        "score": score,
        "confidence": confidence,
        "combination": combination,
        "candle_ts": candle_ts,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "qty": qty,
        "notional": notional,
        "risk_amount": risk_amount,
        "paper_unlock": bool(paper_unlock),
        "unlock_profile": unlock_profile,
        "source_path": source_path,
        "allowed_order_source": settings.allowed_order_source,
        "would_have_submitted": True,
        "order_submitted": False,
        "position_opened": False,
        "blocked": True,
        "blocked_reason": blocked_reason,
        "blocked_reasons": [blocked_reason, "fail_closed_legacy_paper_order_guard"],
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "operational_unlock_allowed": False,
        "broker_submit_called": False,
    }


def summarize_order_leakage_events(
    events: Sequence[Mapping[str, Any]],
    *,
    settings: PaperOrderLeakageGuardSettings | None = None,
) -> dict[str, Any]:
    settings = settings or PaperOrderLeakageGuardSettings.from_config()
    order_events = [dict(e) for e in events if e.get("event_type") in ORDER_EVENT_TYPES]
    position_events = [dict(e) for e in events if e.get("event_type") in POSITION_EVENT_TYPES]
    blocked_events = [dict(e) for e in events if e.get("event_type") == settings.blocked_event_type]
    leakage_events = [dict(e) for e in events if e.get("event_type") == settings.event_type]

    unauthorized_order_ids: set[str] = set()
    unauthorized_order_samples: list[dict[str, Any]] = []
    source_paths: list[str] = []
    source_reasons: list[str] = []
    affected_cycles: set[str] = set()
    affected_symbols: list[str] = []
    affected_sides: list[str] = []

    for event in order_events:
        metadata = _event_metadata(event)
        if is_order_source_authorized(settings=settings, metadata=metadata):
            continue
        order_id = _order_id(event) or f"event:{len(unauthorized_order_samples)}"
        unauthorized_order_ids.add(order_id)
        source_path = _event_source_path(event)
        reason = _source_reason(metadata)
        cycle_id = _event_cycle_id(event)
        symbol = _event_symbol(event)
        side = _event_side(event)
        if cycle_id:
            affected_cycles.add(cycle_id)
        if symbol:
            affected_symbols.append(symbol)
        if side:
            affected_sides.append(side)
        source_paths.append(source_path)
        source_reasons.append(reason)
        if len(unauthorized_order_samples) < 20:
            unauthorized_order_samples.append(
                {
                    "event_type": event.get("event_type"),
                    "ts": event.get("ts"),
                    "cycle_id": cycle_id,
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "source_path": source_path,
                    "source_reason": reason,
                    "metadata": metadata,
                }
            )

    unauthorized_position_ids: set[str] = set()
    unauthorized_position_samples: list[dict[str, Any]] = []
    for event in position_events:
        metadata = _event_metadata(event)
        if is_order_source_authorized(settings=settings, metadata=metadata):
            continue
        position_id = _position_id(event) or f"event:{len(unauthorized_position_samples)}"
        unauthorized_position_ids.add(position_id)
        cycle_id = _event_cycle_id(event)
        symbol = _event_symbol(event)
        side = _event_side(event)
        if cycle_id:
            affected_cycles.add(cycle_id)
        if symbol:
            affected_symbols.append(symbol)
        if side:
            affected_sides.append(side)
        source_paths.append(_event_source_path(event))
        source_reasons.append(_source_reason(metadata))
        if len(unauthorized_position_samples) < 20:
            unauthorized_position_samples.append(
                {
                    "event_type": event.get("event_type"),
                    "ts": event.get("ts"),
                    "cycle_id": cycle_id,
                    "position_id": position_id,
                    "symbol": symbol,
                    "side": side,
                    "source_path": _event_source_path(event),
                    "source_reason": _source_reason(metadata),
                    "metadata": metadata,
                }
            )

    blocked_attempts = len(blocked_events)
    legacy_order_leakage_detected = bool(unauthorized_order_ids or unauthorized_position_ids)
    return {
        "legacy_order_leakage_detected": legacy_order_leakage_detected,
        "unauthorized_order_event_count": len(order_events),
        "unauthorized_orders_count": len(unauthorized_order_ids),
        "unauthorized_positions_opened_count": len(unauthorized_position_ids),
        "blocked_legacy_order_attempts": blocked_attempts,
        "blocked_event_count": blocked_attempts,
        "leakage_audit_event_count": len(leakage_events),
        "source_path_counts": _counts(source_paths),
        "source_reason_counts": _counts(source_reasons),
        "symbol_counts": _counts(affected_symbols),
        "side_counts": _counts(affected_sides),
        "affected_cycles": sorted(affected_cycles),
        "affected_cycles_tail": sorted(affected_cycles)[-20:],
        "unauthorized_order_samples": unauthorized_order_samples,
        "unauthorized_position_samples": unauthorized_position_samples,
        "blocked_samples_tail": blocked_events[-20:],
    }


def build_paper_order_leakage_guard_report(
    base: str | Path = "data",
    *,
    settings: PaperOrderLeakageGuardSettings | None = None,
) -> dict[str, Any]:
    settings = settings or PaperOrderLeakageGuardSettings.from_config()
    base_path = Path(base)
    events = _iter_jsonl_events(base_path / settings.events_name, max_lines=settings.max_event_lines)
    summary = summarize_order_leakage_events(events, settings=settings)
    cycles = [e for e in events if e.get("event_type") == CYCLE_EVENT_TYPE]
    latest_cycle_id = str(cycles[-1].get("cycle_id") or "") if cycles else ""
    cycle_orders_total = sum(_safe_int(e.get("orders"), 0) for e in cycles)
    max_open_positions = max([_safe_int(e.get("open_positions"), 0) for e in cycles] or [0])

    current_window_clear = bool(
        summary["unauthorized_orders_count"] == 0
        and summary["unauthorized_positions_opened_count"] == 0
        and cycle_orders_total == 0
        and max_open_positions == 0
    )
    # If the guard is actively blocking attempts, the patch is still doing its job:
    # blocked attempts are diagnostic, not leakage. Historical unauthorized events
    # from before r-1 keep the report in WARN until state/logs are reset or the
    # report window is narrowed.
    status = "PASS" if current_window_clear else "WARN"
    decision_status = READY_DECISION if status == "PASS" else KEEP_DECISION
    report = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": {
            "status": decision_status,
            "latest_cycle_id": latest_cycle_id,
            "legacy_order_leakage_detected": bool(summary["legacy_order_leakage_detected"]),
            "unauthorized_orders_count": summary["unauthorized_orders_count"],
            "unauthorized_positions_opened_count": summary["unauthorized_positions_opened_count"],
            "blocked_legacy_order_attempts": summary["blocked_legacy_order_attempts"],
            "cycle_orders_total": cycle_orders_total,
            "max_open_positions": max_open_positions,
            "allowed_order_source": settings.allowed_order_source,
            "fail_closed": settings.fail_closed,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "operational_unlock_allowed": False,
        },
        "settings": settings.to_dict(),
        "leakage_summary": summary,
        "safety_checks": {
            "fail_closed_enabled": bool(settings.fail_closed),
            "legacy_order_leakage_detected_false": not bool(summary["legacy_order_leakage_detected"]),
            "no_unauthorized_orders": summary["unauthorized_orders_count"] == 0,
            "no_unauthorized_positions": summary["unauthorized_positions_opened_count"] == 0,
            "cycle_orders_zero": cycle_orders_total == 0,
            "cycle_open_positions_zero": max_open_positions == 0,
            "live_blocked": True,
            "testnet_blocked": True,
            "exchange_broker_blocked": True,
        },
        "orders_submitted": cycle_orders_total,
        "positions_opened": max_open_positions,
        "generated_at": utc_now_iso(),
    }
    return report


def write_paper_order_leakage_guard_report(
    base: str | Path = "data",
    settings: PaperOrderLeakageGuardSettings | None = None,
) -> dict[str, Any]:
    settings = settings or PaperOrderLeakageGuardSettings.from_config()
    report = build_paper_order_leakage_guard_report(base, settings=settings)
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
