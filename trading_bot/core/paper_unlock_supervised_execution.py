"""Prompt 29.4.4s supervised paper-only order execution.

This module is the first intentionally supervised paper execution boundary for
ProgettoTR. It only authorizes a real *paper* order after the guarded runtime
path has already produced a ready candidate and a dry-run handoff event. It
never enables live, testnet, or exchange-broker execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json

from config import Config

PROMPT_ID = "29.4.4s"
EVENT_TYPE = "PAPER_SUPERVISED_ORDER_EXECUTION"
REPORT_NAME = "paper_unlock_supervised_execution_report.json"
READY_DECISION = "PAPER_SUPERVISED_EXECUTION_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"
SUPERVISED_CONFIRMATION_PHRASE = "I_UNDERSTAND_PAPER_ONLY"
HANDOFF_EVENT_TYPE = "PAPER_ORDER_HANDOFF_DRY_RUN"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in {None, ""}:
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


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


@dataclass(frozen=True)
class PaperUnlockSupervisedExecutionSettings:
    enabled: bool = True
    operator_enable: bool = False
    operator_confirmation: str = ""
    confirmation_phrase: str = SUPERVISED_CONFIRMATION_PHRASE
    event_type: str = EVENT_TYPE
    handoff_event_type: str = HANDOFF_EVENT_TYPE
    report_name: str = REPORT_NAME
    events_name: str = "paper_events.jsonl"
    status_name: str = "paper_status.json"
    max_event_lines: int = 50000
    max_positions: int = 1
    max_orders_per_cycle: int = 1
    paper_broker_adapter_name: str = "PaperBrokerAdapter"

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockSupervisedExecutionSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_ENABLED", True)),
            operator_enable=bool(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_OPERATOR_ENABLE", False)),
            operator_confirmation=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM", "") or ""),
            confirmation_phrase=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM_PHRASE", SUPERVISED_CONFIRMATION_PHRASE) or SUPERVISED_CONFIRMATION_PHRASE),
            event_type=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_EVENT_TYPE", EVENT_TYPE) or EVENT_TYPE),
            handoff_event_type=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_HANDOFF_EVENT_TYPE", HANDOFF_EVENT_TYPE) or HANDOFF_EVENT_TYPE),
            report_name=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_REPORT_NAME", REPORT_NAME) or REPORT_NAME),
            events_name=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_EVENTS_NAME", "paper_events.jsonl") or "paper_events.jsonl"),
            status_name=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_STATUS_NAME", "paper_status.json") or "paper_status.json"),
            max_event_lines=max(1000, _safe_int(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_EVENT_LINES", 50000), 50000)),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_POSITIONS", 1), 1)),
            max_orders_per_cycle=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_MAX_ORDERS_PER_CYCLE", 1), 1)),
            paper_broker_adapter_name=str(getattr(cfg, "PAPER_UNLOCK_SUPERVISED_EXECUTION_PAPER_BROKER_ADAPTER", "PaperBrokerAdapter") or "PaperBrokerAdapter"),
        )

    @property
    def confirmation_ok(self) -> bool:
        return bool(self.operator_confirmation == self.confirmation_phrase)

    @property
    def operator_authorized(self) -> bool:
        return bool(self.enabled and self.operator_enable and self.confirmation_ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "operator_enable": self.operator_enable,
            "confirmation_ok": self.confirmation_ok,
            "confirmation_phrase": self.confirmation_phrase,
            "event_type": self.event_type,
            "handoff_event_type": self.handoff_event_type,
            "report_name": self.report_name,
            "events_name": self.events_name,
            "status_name": self.status_name,
            "max_event_lines": self.max_event_lines,
            "max_positions": self.max_positions,
            "max_orders_per_cycle": self.max_orders_per_cycle,
            "paper_broker_adapter_name": self.paper_broker_adapter_name,
        }


def build_paper_supervised_execution_event(
    *,
    settings: PaperUnlockSupervisedExecutionSettings | None = None,
    handoff_event: Mapping[str, Any],
    open_positions_count: int = 0,
    order_submitted: bool = False,
    position_opened: bool = False,
    broker_submit_called: bool = False,
    order_id: str = "",
    position_id: str = "",
    error: str = "",
) -> dict[str, Any]:
    settings = settings or PaperUnlockSupervisedExecutionSettings.from_config()
    handoff = dict(handoff_event or {})
    candidate_ready = _safe_bool(handoff.get("candidate_ready"))
    would_create_order = _safe_bool(handoff.get("would_create_order"))
    mode = str(handoff.get("mode") or "paper")
    side = str(handoff.get("side") or "")
    entry_price = _safe_float(handoff.get("entry_price"), 0.0)
    stop_loss = _safe_float(handoff.get("stop_loss"), 0.0)
    take_profit = _safe_float(handoff.get("take_profit"), 0.0)
    position_size = _safe_float(handoff.get("position_size"), 0.0)
    notional = _safe_float(handoff.get("notional"), abs(position_size * entry_price))
    open_positions = max(0, int(open_positions_count))

    paper_orders_enabled = _safe_bool(handoff.get("paper_orders_enabled"))
    experiment_allowed = _safe_bool(handoff.get("paper_unlock_experiment_allowed"))
    manual_activation_allowed = _safe_bool(handoff.get("manual_activation_allowed"))
    live_allowed = _safe_bool(handoff.get("live_allowed"))
    testnet_allowed = _safe_bool(handoff.get("testnet_allowed"))
    exchange_broker_allowed = _safe_bool(handoff.get("exchange_broker_allowed"))

    blocked_reasons: list[str] = []
    if not settings.enabled:
        blocked_reasons.append("supervised_execution_disabled")
    if not settings.operator_enable:
        blocked_reasons.append("operator_enable_not_active")
    if not settings.confirmation_ok:
        blocked_reasons.append("operator_confirmation_missing")
    if mode != "paper":
        blocked_reasons.append("mode_not_paper")
    if not candidate_ready:
        blocked_reasons.append("candidate_ready_false")
    if not would_create_order:
        blocked_reasons.append("handoff_would_create_order_false")
    if not paper_orders_enabled:
        blocked_reasons.append("paper_orders_enabled_false")
    if not experiment_allowed:
        blocked_reasons.append("paper_unlock_experiment_allowed_false")
    if not manual_activation_allowed:
        blocked_reasons.append("manual_activation_allowed_false")
    if live_allowed:
        blocked_reasons.append("live_allowed_true")
    if testnet_allowed:
        blocked_reasons.append("testnet_allowed_true")
    if exchange_broker_allowed:
        blocked_reasons.append("exchange_broker_allowed_true")
    if side not in {"BUY", "SELL"}:
        blocked_reasons.append("side_invalid")
    if entry_price <= 0.0 or stop_loss <= 0.0 or take_profit <= 0.0:
        blocked_reasons.append("price_fields_invalid")
    if position_size <= 0.0 or notional <= 0.0:
        blocked_reasons.append("position_size_invalid")
    if open_positions >= settings.max_positions:
        blocked_reasons.append("max_positions")
    if error:
        blocked_reasons.append("broker_submit_error")

    supervised_submit_allowed = bool(not blocked_reasons)
    if order_submitted and not supervised_submit_allowed and not error:
        blocked_reasons.append("order_submitted_without_authorization")
        supervised_submit_allowed = False

    return {
        "event_type": settings.event_type,
        "prompt": PROMPT_ID,
        "cycle_id": str(handoff.get("cycle_id") or ""),
        "symbol": str(handoff.get("symbol") or ""),
        "candle_ts": str(handoff.get("candle_ts") or ""),
        "ts": utc_now_iso(),
        "profile_name": str(handoff.get("profile_name") or "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"),
        "enable_name": str(handoff.get("enable_name") or "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE"),
        "source_handoff_event_type": handoff.get("event_type") or settings.handoff_event_type,
        "source_candidate_event_type": handoff.get("source_candidate_event_type"),
        "side": side,
        "mode": mode,
        "paper_only_mode": True,
        "routing_mode": str(handoff.get("routing_mode") or "paper_only"),
        "submission_mode": "supervised_paper_only",
        "supervised_execution_enabled": settings.enabled,
        "operator_enable": settings.operator_enable,
        "operator_confirmation_ok": settings.confirmation_ok,
        "operator_authorized": settings.operator_authorized,
        "candidate_ready": candidate_ready,
        "would_create_order": would_create_order,
        "supervised_submit_allowed": supervised_submit_allowed,
        "would_submit_to_paper_broker": supervised_submit_allowed,
        "broker_submit_called": bool(broker_submit_called),
        "order_submitted": bool(order_submitted),
        "position_opened": bool(position_opened),
        "orders_submitted_by_supervised": 1 if order_submitted else 0,
        "positions_opened_by_supervised": 1 if position_opened else 0,
        "order_id": order_id,
        "position_id": position_id,
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "exchange_broker_adapter": "blocked",
        "paper_orders_enabled": paper_orders_enabled,
        "paper_unlock_experiment_allowed": experiment_allowed,
        "manual_activation_allowed": manual_activation_allowed,
        "automatic_activation_allowed": False,
        "operational_unlock_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "live_blocked": True,
        "testnet_blocked": True,
        "exchange_broker_blocked": True,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_per_trade_pct": _safe_float(handoff.get("risk_per_trade_pct"), 0.0025),
        "risk_amount": _safe_float(handoff.get("risk_amount"), 0.0),
        "position_size": position_size,
        "notional": notional,
        "max_positions": settings.max_positions,
        "open_positions_count": open_positions,
        "blocked_reason": None if supervised_submit_allowed else (blocked_reasons[0] if blocked_reasons else "supervised_execution_not_ready"),
        "blocked_reasons": blocked_reasons,
        "error": error,
    }


def _latest_cycle_id(events: Sequence[Mapping[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("event_type") == "CYCLE_COMPLETED":
            return str(event.get("cycle_id") or "")
    return ""


def build_paper_unlock_supervised_execution_report(
    base: str | Path = "data",
    settings: PaperUnlockSupervisedExecutionSettings | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockSupervisedExecutionSettings.from_config()
    base_path = Path(base)
    events = _iter_jsonl_events(base_path / settings.events_name, max_lines=settings.max_event_lines)
    supervised_events = [e for e in events if e.get("event_type") == settings.event_type]
    handoff_events = [e for e in events if e.get("event_type") == settings.handoff_event_type]
    candidate_ready_count = sum(1 for e in handoff_events if _safe_bool(e.get("candidate_ready")))
    would_create_order_count = sum(1 for e in handoff_events if _safe_bool(e.get("would_create_order")))
    allowed_count = sum(1 for e in supervised_events if _safe_bool(e.get("supervised_submit_allowed")))
    broker_submit_called_count = sum(1 for e in supervised_events if _safe_bool(e.get("broker_submit_called")))
    orders_by_supervised = sum(_safe_int(e.get("orders_submitted_by_supervised"), 0) for e in supervised_events)
    positions_by_supervised = sum(_safe_int(e.get("positions_opened_by_supervised"), 0) for e in supervised_events)
    unsafe_event_count = sum(
        1
        for e in supervised_events
        if _safe_bool(e.get("live_allowed")) or _safe_bool(e.get("testnet_allowed")) or _safe_bool(e.get("exchange_broker_allowed"))
    )
    unauthorized_submit_count = sum(1 for e in supervised_events if _safe_bool(e.get("order_submitted")) and not _safe_bool(e.get("supervised_submit_allowed")))
    status = "PASS" if unsafe_event_count == 0 and unauthorized_submit_count == 0 else "FAIL"
    decision_status = READY_DECISION if status == "PASS" else KEEP_DECISION
    report = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": {
            "status": decision_status,
            "latest_cycle_id": _latest_cycle_id(events),
            "supervised_execution_events": len(supervised_events),
            "supervised_submit_allowed_count": allowed_count,
            "candidate_ready_count": candidate_ready_count,
            "would_create_order_count": would_create_order_count,
            "broker_submit_called_count": broker_submit_called_count,
            "orders_submitted_by_supervised": orders_by_supervised,
            "positions_opened_by_supervised": positions_by_supervised,
            "operator_enable": settings.operator_enable,
            "operator_confirmation_ok": settings.confirmation_ok,
            "operational_unlock_allowed": False,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
        },
        "settings": settings.to_dict(),
        "supervised_execution": {
            "event_count": len(supervised_events),
            "blocked_reason_counts": _counts(reason for e in supervised_events for reason in (e.get("blocked_reasons") or [])),
            "side_counts": _counts(e.get("side") for e in supervised_events),
            "symbol_counts": _counts(e.get("symbol") for e in supervised_events),
            "sample_events_tail": supervised_events[-10:],
        },
        "safety_checks": {
            "no_live_allowed_events": unsafe_event_count == 0,
            "no_unauthorized_supervised_submits": unauthorized_submit_count == 0,
            "exchange_broker_blocked": True,
            "testnet_blocked": True,
            "live_blocked": True,
        },
        "orders_submitted_by_supervised": orders_by_supervised,
        "positions_opened_by_supervised": positions_by_supervised,
        "generated_at": utc_now_iso(),
    }
    return report


def write_paper_unlock_supervised_execution_report(
    base: str | Path = "data",
    settings: PaperUnlockSupervisedExecutionSettings | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockSupervisedExecutionSettings.from_config()
    report = build_paper_unlock_supervised_execution_report(base, settings=settings)
    path = Path(base) / settings.report_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
