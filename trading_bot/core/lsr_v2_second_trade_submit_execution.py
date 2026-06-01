"""Prompt 29.4.4s-10y — LSR-v2 second supervised paper-only submit execution.

This module adds the execution boundary for the *second* LSR-v2 supervised
paper trade.  It is separate from the first-trade execution path and consumes
only the second-trade submit-boundary artifacts introduced in 29.4.4s-10x.

The boundary is disabled by default and requires:

* the second-trade submit boundary arm/confirmation from 29.4.4s-10x;
* a new execution arm/confirmation specific to the second paper trade;
* clean paper state/status with no open LSR-v2 positions and no pending orders;
* max_orders == 1 and mode == paper.

When those controls are present, the standalone runner may wire a project
PaperBrokerAdapter submitter.  Live, testnet and exchange broker execution are
hard blocked.  No batch orders, retry loop, re-entry, close, live broker, or
exchange broker path is enabled by this module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import json
import os

try:  # package import in the full project
    from .lsr_v2_second_trade_submit_boundary import (  # type: ignore
        EVENT_TYPE as BOUNDARY_EVENT_TYPE,
        JSONL_NAME as BOUNDARY_JSONL_NAME,
        REPORT_NAME as BOUNDARY_REPORT_NAME,
        READY_ARMED_DECISION as BOUNDARY_READY_ARMED_DECISION,
        LSRV2SecondTradeSubmitBoundarySettings,
        _event_cycle,
        _iter_jsonl_tail,
        _payload_from_preflight,
        _payload_valid,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
    )
except Exception:  # pragma: no cover - script-style fallback
    from lsr_v2_second_trade_submit_boundary import (  # type: ignore
        EVENT_TYPE as BOUNDARY_EVENT_TYPE,
        JSONL_NAME as BOUNDARY_JSONL_NAME,
        REPORT_NAME as BOUNDARY_REPORT_NAME,
        READY_ARMED_DECISION as BOUNDARY_READY_ARMED_DECISION,
        LSRV2SecondTradeSubmitBoundarySettings,
        _event_cycle,
        _iter_jsonl_tail,
        _payload_from_preflight,
        _payload_valid,
        _read_json,
        _safe_bool,
        _safe_float,
        _safe_int,
        _write_json,
        _write_jsonl_replace,
    )

PROMPT_ID = "29.4.4s-10y"
EVENT_TYPE = "LSR_V2_SECOND_TRADE_SUBMIT_EXECUTION"
REPORT_NAME = "lsr_v2_second_trade_submit_execution_report.json"
JSONL_NAME = "lsr_v2_second_trade_submit_execution.jsonl"

EXECUTE_ENV = "LSR_V2_SECOND_TRADE_EXECUTE"
EXECUTE_CONFIRM_ENV = "LSR_V2_SECOND_TRADE_EXECUTE_CONFIRMATION"
REQUIRED_EXECUTE_VALUE = "1"
REQUIRED_EXECUTE_CONFIRMATION = "I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY"

EXECUTED_DECISION = "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED"
NOT_ARMED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_EXECUTION_NOT_ARMED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_EXECUTION_CONFIRMATION_MISSING"
BOUNDARY_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_SUBMIT_BOUNDARY_MISSING"
STATE_NOT_CLEAN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_STATE_NOT_CLEAN"
SUBMITTER_NOT_AVAILABLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_SUBMITTER_NOT_AVAILABLE"
MAX_ORDER_CAP_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_EXECUTION_MAX_ORDER_CAP_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_EXECUTION_SAFETY_FAILED"

PaperSubmitter = Callable[[Mapping[str, Any]], Mapping[str, Any] | bool | None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class LSRV2SecondTradeSubmitExecutionSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    boundary_report_name: str = BOUNDARY_REPORT_NAME
    boundary_jsonl_name: str = BOUNDARY_JSONL_NAME
    max_event_lines: int = 50000
    execute_arm: str = ""
    execute_confirmation: str = ""
    required_execute_value: str = REQUIRED_EXECUTE_VALUE
    required_execute_confirmation: str = REQUIRED_EXECUTE_CONFIRMATION
    max_orders: int = 1
    mode: str = "paper"
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    initial_balance: float = 1000.0
    fee_rate: float = 0.002
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2SecondTradeSubmitExecutionSettings":
        max_orders = _safe_int(os.getenv("LSR_V2_SECOND_TRADE_MAX_ORDERS"), 1)
        if max_orders <= 0:
            max_orders = 1
        initial_balance = _safe_float(os.getenv("LSR_V2_PAPER_INITIAL_BALANCE"), 1000.0)
        if initial_balance <= 0:
            initial_balance = 1000.0
        fee_rate = _safe_float(os.getenv("LSR_V2_PAPER_FEE_RATE"), 0.002)
        if fee_rate < 0:
            fee_rate = 0.002
        return cls(
            data_dir=data_dir,
            execute_arm=str(os.getenv(EXECUTE_ENV) or ""),
            execute_confirmation=str(os.getenv(EXECUTE_CONFIRM_ENV) or ""),
            max_orders=max_orders,
            mode=str(os.getenv("LSR_V2_SECOND_TRADE_SUBMIT_MODE") or "paper"),
            initial_balance=initial_balance,
            fee_rate=fee_rate,
        )

    @property
    def execute_armed(self) -> bool:
        return str(self.execute_arm).strip() == self.required_execute_value

    @property
    def execute_confirmation_ok(self) -> bool:
        return str(self.execute_confirmation).strip() == self.required_execute_confirmation

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clone_boundary_settings(
    *,
    data_dir: str | Path,
    execution_settings: LSRV2SecondTradeSubmitExecutionSettings,
) -> LSRV2SecondTradeSubmitBoundarySettings:
    base = LSRV2SecondTradeSubmitBoundarySettings.from_env(data_dir=str(data_dir))
    return LSRV2SecondTradeSubmitBoundarySettings(
        **{
            **base.to_dict(),
            "data_dir": str(data_dir),
            "max_orders": int(execution_settings.max_orders),
            "mode": str(execution_settings.mode),
        }
    )


def _active_orders_and_positions_from_state(state: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    active_orders: list[str] = []
    active_positions: list[str] = []
    orders = _as_mapping(state.get("orders"))
    positions = _as_mapping(state.get("positions"))

    closed_order_states = {
        "", "CLOSED", "CANCELLED", "CANCELED", "REJECTED", "EXPIRED", "FILLED_CLOSED", "CLOSED_FILLED"
    }
    # FILLED entry orders with no open position are historical paper records and
    # must not block a later supervised paper trade.
    historical_filled_states = {"FILLED", "EXECUTED", "COMPLETE", "COMPLETED"}
    for oid, order in orders.items():
        row = _as_mapping(order)
        order_status = str(row.get("status") or row.get("state") or "").upper()
        is_open = _safe_bool(row.get("open"), False)
        pending = _safe_bool(row.get("pending"), False)
        if is_open or pending:
            active_orders.append(str(oid))
            continue
        if order_status in historical_filled_states or order_status in closed_order_states:
            continue
        # Unknown non-empty state is treated as potentially active.
        if order_status:
            active_orders.append(str(oid))

    for pid, pos in positions.items():
        row = _as_mapping(pos)
        position_status = str(row.get("status") or row.get("state") or "OPEN").upper()
        is_open = _safe_bool(row.get("open"), position_status not in {"CLOSED", "CANCELLED", "CANCELED"})
        if is_open and position_status not in {"CLOSED", "CANCELLED", "CANCELED"}:
            active_positions.append(str(pid))
    return active_orders, active_positions


def read_second_trade_paper_state_cleanliness(data_dir: str | Path) -> tuple[bool, dict[str, Any]]:
    """Return whether paper state/status is clean enough for the second submit."""
    base = Path(data_dir)
    state = _read_json(base / "paper_state.json")
    status = _read_json(base / "paper_status.json")
    active_orders, active_positions = _active_orders_and_positions_from_state(state)
    open_positions = _safe_int(status.get("open_positions"), 0)
    pending_orders = _safe_int(status.get("pending_orders"), 0)

    blockers: list[str] = []
    if active_orders:
        blockers.append("active_orders_present")
    if active_positions:
        blockers.append("active_positions_present")
    if open_positions > 0:
        blockers.append("paper_status_open_positions_nonzero")
    if pending_orders > 0:
        blockers.append("paper_status_pending_orders_nonzero")

    return not blockers, {
        "paper_state_path": str(base / "paper_state.json"),
        "paper_status_path": str(base / "paper_status.json"),
        "paper_state_exists": (base / "paper_state.json").exists(),
        "paper_status_exists": (base / "paper_status.json").exists(),
        "active_order_count": len(active_orders),
        "active_position_count": len(active_positions),
        "paper_status_open_positions": open_positions,
        "paper_status_pending_orders": pending_orders,
        "paper_state_clean": not blockers,
        "paper_state_blockers": blockers,
    }


def _boundary_event_key(event: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(event.get("event_type") or ""),
        _event_cycle(event),
        str(event.get("symbol") or ""),
        str(event.get("candidate_id") or ""),
        str(event.get("timeframe") or ""),
    )


def _dedupe_boundary_events(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for raw in events:
        row = dict(raw)
        if row.get("event_type") != BOUNDARY_EVENT_TYPE:
            continue
        key = _boundary_event_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def select_second_trade_submit_boundary_events(
    *,
    data_dir: str | Path,
    settings: LSRV2SecondTradeSubmitExecutionSettings | None = None,
    requested_cycle_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    settings = settings or LSRV2SecondTradeSubmitExecutionSettings(data_dir=str(data_dir))
    base = Path(data_dir)
    rows = _dedupe_boundary_events(_iter_jsonl_tail(base / settings.boundary_jsonl_name, max_lines=settings.max_event_lines))
    boundary_report = _read_json(base / settings.boundary_report_name)
    cycle_id = str(requested_cycle_id or boundary_report.get("cycle_id") or "")
    if not cycle_id:
        for row in reversed(rows):
            if _event_cycle(row):
                cycle_id = _event_cycle(row)
                break
    scoped = [row for row in rows if not cycle_id or _event_cycle(row) == cycle_id]
    ready = [row for row in scoped if _safe_bool(row.get("second_trade_submit_ready"), False)]
    metadata = {
        "event_source": "second_trade_submit_boundary_jsonl" if rows else "second_trade_submit_boundary_report",
        "strict_cycle_scope": True,
        "historical_second_trade_submit_boundary_events": max(0, len(rows) - len(scoped)),
        "boundary_report_present": bool(boundary_report),
        "boundary_report_decision": str(boundary_report.get("decision") or ""),
        "boundary_report_ready": str(boundary_report.get("decision") or "") == BOUNDARY_READY_ARMED_DECISION,
        "boundary_report_cycle_id": str(boundary_report.get("cycle_id") or ""),
        "scoped_boundary_events": len(scoped),
        "scoped_ready_events": len(ready),
    }
    return cycle_id, ready, metadata


def build_second_trade_project_paper_submitter(
    *,
    data_dir: str | Path,
    settings: LSRV2SecondTradeSubmitExecutionSettings | None = None,
) -> tuple[PaperSubmitter | None, str]:
    """Build a PaperBrokerAdapter submitter from the installed project.

    Imports are lazy so tests/minimal contexts can run without the complete
    runtime.  This function never wires an exchange broker.
    """
    settings = settings or LSRV2SecondTradeSubmitExecutionSettings(data_dir=str(data_dir))
    try:
        try:
            from core.paper_broker import PaperBroker  # type: ignore
            from core.broker_adapter import PaperBrokerAdapter  # type: ignore
        except Exception:
            from trading_bot.core.paper_broker import PaperBroker  # type: ignore
            from trading_bot.core.broker_adapter import PaperBrokerAdapter  # type: ignore
    except Exception as exc:
        return None, f"paper_broker_import_failed:{type(exc).__name__}:{exc}"

    base = Path(data_dir)
    broker = PaperBroker(
        initial_balance=float(settings.initial_balance),
        fee_rate=float(settings.fee_rate),
        state_path=base / "paper_state.json",
        events_path=base / "paper_events.jsonl",
    )
    last_prices: dict[str, float] = {}
    adapter = PaperBrokerAdapter(broker, last_prices=last_prices, leverage_for_display=1.0)

    def submitter(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        symbol = str(payload.get("symbol") or "")
        side = str(payload.get("side") or "").upper()
        price = _safe_float(payload.get("entry_price"), 0.0)
        qty = _safe_float(payload.get("quantity") or payload.get("position_size"), 0.0)
        stop_loss = _safe_float(payload.get("stop_loss"), 0.0)
        take_profit = _safe_float(payload.get("take_profit"), 0.0)
        last_prices[symbol] = price
        metadata = {
            "cycle_id": str(payload.get("cycle_id") or ""),
            "paper_order_source": "lsr_v2_second_trade_submit_execution",
            "execution_source": "lsr_v2_second_trade_submit_execution",
            "trade_ordinal": 2,
            "profile_name": str(payload.get("profile_name") or ""),
            "selected_overlay_id": str(payload.get("selected_overlay_id") or ""),
            "candidate_id": str(payload.get("candidate_id") or ""),
            "risk_per_trade_pct": _safe_float(payload.get("risk_per_trade_pct"), 0.0025),
            "risk_amount": _safe_float(payload.get("risk_amount"), 0.0),
            "second_trade_single_order_gate": True,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        }
        order = adapter.place_order(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata,
        )
        return {
            "order_submitted": True,
            "position_opened": True,
            "order_id": str(getattr(order, "order_id", "")),
            "paper_broker_adapter": settings.paper_broker_adapter_name,
        }

    return submitter, ""


def _payload_from_boundary(boundary_event: Mapping[str, Any]) -> dict[str, Any]:
    payload = boundary_event.get("payload")
    if isinstance(payload, Mapping):
        return dict(payload)
    # Fallback for minimal/historical rows with flattened fields.
    return {
        "cycle_id": str(boundary_event.get("cycle_id") or ""),
        "symbol": str(boundary_event.get("symbol") or ""),
        "timeframe": str(boundary_event.get("timeframe") or ""),
        "side": str(boundary_event.get("side") or ""),
        "order_type": str(boundary_event.get("order_type") or "LIMIT"),
        "profile_name": str(boundary_event.get("profile_name") or ""),
        "selected_overlay_id": str(boundary_event.get("selected_overlay_id") or ""),
        "entry_price": _safe_float(boundary_event.get("entry_price"), 0.0),
        "stop_loss": _safe_float(boundary_event.get("stop_loss"), 0.0),
        "take_profit": _safe_float(boundary_event.get("take_profit"), 0.0),
        "risk_per_trade_pct": _safe_float(boundary_event.get("risk_per_trade_pct"), 0.0025),
        "risk_amount": _safe_float(boundary_event.get("risk_amount"), 0.0),
        "position_size": _safe_float(boundary_event.get("position_size"), 0.0),
        "quantity": _safe_float(boundary_event.get("quantity"), _safe_float(boundary_event.get("position_size"), 0.0)),
        "notional": _safe_float(boundary_event.get("notional"), 0.0),
        "max_positions": _safe_int(boundary_event.get("max_positions"), 1),
        "candidate_id": str(boundary_event.get("candidate_id") or ""),
    }


def build_lsr_v2_second_trade_submit_execution_event(
    *,
    boundary_event: Mapping[str, Any],
    settings: LSRV2SecondTradeSubmitExecutionSettings | None = None,
    boundary_settings: LSRV2SecondTradeSubmitBoundarySettings | None = None,
    paper_state: Mapping[str, Any] | None = None,
    paper_submitter: PaperSubmitter | None = None,
    submitter_error: str = "",
    index: int = 0,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitExecutionSettings()
    boundary_settings = boundary_settings or LSRV2SecondTradeSubmitBoundarySettings()
    paper_state = dict(paper_state or {})
    payload = _payload_from_boundary(boundary_event)
    payload_ok, payload_reasons = _payload_valid(payload)
    boundary_ready = _safe_bool(boundary_event.get("second_trade_submit_ready"), False)
    submit_controls_ok = boundary_settings.submit_armed and boundary_settings.submit_confirmation_ok
    execute_controls_ok = settings.execute_armed and settings.execute_confirmation_ok

    blockers: list[str] = []
    if str(settings.mode).lower() != "paper":
        blockers.append("mode_not_paper")
    if not boundary_ready:
        blockers.append("second_trade_submit_boundary_not_ready")
    if not boundary_settings.submit_armed:
        blockers.append("second_trade_submit_not_armed")
    if not boundary_settings.submit_confirmation_ok:
        blockers.append("second_trade_submit_confirmation_missing")
    if not settings.execute_armed:
        blockers.append("second_trade_execute_not_armed")
    if not settings.execute_confirmation_ok:
        blockers.append("second_trade_execute_confirmation_missing")
    if settings.max_orders != 1:
        blockers.append("max_orders_not_one")
    if index >= max(settings.max_orders, 0):
        blockers.append("second_trade_max_order_cap_exceeded")
    if not _safe_bool(paper_state.get("paper_state_clean"), False):
        blockers.append("paper_state_not_clean")
        blockers.extend(str(b) for b in paper_state.get("paper_state_blockers") or [])
    if not payload_ok:
        blockers.extend([f"payload_{reason}" for reason in payload_reasons])
    if not settings.fail_closed:
        blockers.append("fail_closed_disabled")

    would_submit = bool(
        payload_ok
        and boundary_ready
        and submit_controls_ok
        and execute_controls_ok
        and str(settings.mode).lower() == "paper"
        and settings.max_orders == 1
        and index < max(settings.max_orders, 0)
        and _safe_bool(paper_state.get("paper_state_clean"), False)
        and settings.fail_closed
    )

    submit_result: Mapping[str, Any] | bool | None = None
    submit_error = ""
    if would_submit:
        if paper_submitter is None:
            blockers.append("paper_submitter_not_available")
            would_submit = False
        else:
            try:
                submit_result = paper_submitter(payload)
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                submit_error = f"paper_submitter_error:{type(exc).__name__}:{exc}"
                blockers.append("paper_submitter_error")
                would_submit = False

    result_map = submit_result if isinstance(submit_result, Mapping) else {}
    result_bool = bool(submit_result) if not isinstance(submit_result, Mapping) else False
    order_submitted = bool(_safe_bool(result_map.get("order_submitted"), False) or result_bool) and would_submit
    position_opened = bool(_safe_bool(result_map.get("position_opened"), order_submitted)) and order_submitted
    broker_called = bool(order_submitted)

    if not settings.execute_armed:
        blocked_reason = "second_trade_execute_not_armed"
    elif not settings.execute_confirmation_ok:
        blocked_reason = "second_trade_execute_confirmation_missing"
    elif not boundary_settings.submit_armed:
        blocked_reason = "second_trade_submit_not_armed"
    elif not boundary_settings.submit_confirmation_ok:
        blocked_reason = "second_trade_submit_confirmation_missing"
    elif not _safe_bool(paper_state.get("paper_state_clean"), False):
        blocked_reason = "paper_state_not_clean"
    elif index >= max(settings.max_orders, 0):
        blocked_reason = "second_trade_max_order_cap_exceeded"
    elif "paper_submitter_not_available" in blockers:
        blocked_reason = "paper_submitter_not_available"
    elif blockers:
        blocked_reason = blockers[0]
    elif order_submitted:
        blocked_reason = ""
    else:
        blocked_reason = "second_trade_submit_not_executed"

    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "cycle_id": payload.get("cycle_id", ""),
        "symbol": payload.get("symbol", ""),
        "timeframe": payload.get("timeframe", ""),
        "side": payload.get("side", ""),
        "order_type": payload.get("order_type", "LIMIT"),
        "profile_name": payload.get("profile_name", boundary_settings.profile_name),
        "selected_overlay_id": payload.get("selected_overlay_id", boundary_settings.selected_overlay_id),
        "source": "lsr_v2_second_trade_submit_boundary",
        "source_event_type": str(boundary_event.get("event_type") or BOUNDARY_EVENT_TYPE),
        "candidate_id": payload.get("candidate_id", ""),
        "trade_ordinal": 2,
        "payload": payload,
        "payload_valid": bool(payload_ok),
        "payload_invalid_reasons": payload_reasons,
        "entry_price": payload.get("entry_price"),
        "stop_loss": payload.get("stop_loss"),
        "take_profit": payload.get("take_profit"),
        "risk_per_trade_pct": payload.get("risk_per_trade_pct"),
        "risk_amount": payload.get("risk_amount"),
        "position_size": payload.get("position_size"),
        "quantity": payload.get("quantity"),
        "notional": payload.get("notional"),
        "max_positions": payload.get("max_positions"),
        "second_trade_submit_armed": bool(boundary_settings.submit_armed),
        "second_trade_submit_confirmation_ok": bool(boundary_settings.submit_confirmation_ok),
        "second_trade_submit_ready": bool(boundary_ready),
        "second_trade_execute_armed": bool(settings.execute_armed),
        "second_trade_execute_confirmation_ok": bool(settings.execute_confirmation_ok),
        "paper_state_clean": bool(paper_state.get("paper_state_clean")),
        "paper_state_blockers": list(paper_state.get("paper_state_blockers") or []),
        "second_trade_submit_enabled": bool(order_submitted),
        "second_trade_execute_enabled": bool(order_submitted),
        "submit_enabled": bool(order_submitted),
        "would_submit": bool(would_submit and order_submitted),
        "would_submit_to_paper_broker": bool(would_submit and order_submitted),
        "broker_submit_called": bool(broker_called),
        "paper_broker_adapter": str(result_map.get("paper_broker_adapter") or settings.paper_broker_adapter_name),
        "paper_submitter_error": str(submit_error or submitter_error or ""),
        "order_submitted": bool(order_submitted),
        "position_opened": bool(position_opened),
        "order_id": str(result_map.get("order_id") or ""),
        "blocked_reason": blocked_reason,
        "blocked_reasons": sorted(set(blockers)),
        "routing_enabled": False,
        "execution_enabled": bool(order_submitted),
        "paper_order_submission_enabled": bool(order_submitted),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "orders_submitted_by_second_trade_execution": 1 if order_submitted else 0,
        "positions_opened_by_second_trade_execution": 1 if position_opened else 0,
        "positions_closed_by_second_trade_execution": 0,
        "promotion_ready": False,
        "max_orders": int(settings.max_orders),
        "single_order_gate": True,
    }


def build_lsr_v2_second_trade_submit_execution_events(
    boundary_events: Iterable[Mapping[str, Any]],
    *,
    settings: LSRV2SecondTradeSubmitExecutionSettings | None = None,
    boundary_settings: LSRV2SecondTradeSubmitBoundarySettings | None = None,
    paper_state: Mapping[str, Any] | None = None,
    paper_submitter: PaperSubmitter | None = None,
    submitter_error: str = "",
) -> list[dict[str, Any]]:
    settings = settings or LSRV2SecondTradeSubmitExecutionSettings()
    boundary_settings = boundary_settings or LSRV2SecondTradeSubmitBoundarySettings()
    eligible = [dict(e) for e in _dedupe_boundary_events(boundary_events) if _safe_bool(e.get("second_trade_submit_ready"), False)]
    events: list[dict[str, Any]] = []
    for idx, boundary in enumerate(eligible):
        events.append(build_lsr_v2_second_trade_submit_execution_event(
            boundary_event=boundary,
            settings=settings,
            boundary_settings=boundary_settings,
            paper_state=paper_state,
            paper_submitter=paper_submitter,
            submitter_error=submitter_error,
            index=idx,
        ))
    return events


def summarize_lsr_v2_second_trade_submit_execution(
    *,
    data_dir: str | Path,
    cycle_id: str,
    boundary_events: Iterable[Mapping[str, Any]],
    execution_events: Iterable[Mapping[str, Any]],
    settings: LSRV2SecondTradeSubmitExecutionSettings,
    boundary_settings: LSRV2SecondTradeSubmitBoundarySettings,
    metadata: Mapping[str, Any] | None = None,
    paper_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    paper_state = dict(paper_state or {})
    boundary_rows = [dict(e) for e in boundary_events if dict(e).get("event_type") == BOUNDARY_EVENT_TYPE]
    rows = [dict(e) for e in execution_events]
    ready_rows = [e for e in rows if _safe_bool(e.get("second_trade_submit_ready"), False)]
    would_submit_rows = [e for e in rows if _safe_bool(e.get("would_submit"), False)]
    submitted_rows = [e for e in rows if _safe_int(e.get("orders_submitted_by_second_trade_execution"), 0) > 0]
    position_rows = [e for e in rows if _safe_int(e.get("positions_opened_by_second_trade_execution"), 0) > 0]
    broker_called = any(_safe_bool(e.get("broker_submit_called"), False) for e in rows)

    blockers: list[str] = []
    if not boundary_rows or not _safe_bool(metadata.get("boundary_report_ready"), False):
        blockers.append("second_trade_submit_boundary_missing_or_not_ready")
    if not boundary_settings.submit_armed or not settings.execute_armed:
        blockers.append("second_trade_execution_not_armed")
    if not boundary_settings.submit_confirmation_ok or not settings.execute_confirmation_ok:
        blockers.append("second_trade_execution_confirmation_missing")
    if settings.max_orders != 1:
        blockers.append("max_orders_not_one")
    if not _safe_bool(paper_state.get("paper_state_clean"), False):
        blockers.append("paper_state_not_clean")
        blockers.extend(str(b) for b in paper_state.get("paper_state_blockers") or [])
    if any("paper_submitter_not_available" in set(e.get("blocked_reasons") or []) for e in rows):
        blockers.append("paper_submitter_not_available")
    if any("paper_submitter_error" in set(e.get("blocked_reasons") or []) for e in rows):
        blockers.append("paper_submitter_error")
    safety_violation = any(
        _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        or _safe_int(e.get("orders_submitted_by_second_trade_execution"), 0) > 1
        or _safe_int(e.get("positions_opened_by_second_trade_execution"), 0) > 1
        or _safe_int(e.get("positions_closed_by_second_trade_execution"), 0) != 0
        for e in rows
    )
    if len(submitted_rows) > 1 or len(position_rows) > 1:
        safety_violation = True
        blockers.append("more_than_one_second_trade_order_or_position")
    if safety_violation:
        blockers.append("safety_violation_detected")

    if not boundary_rows or not _safe_bool(metadata.get("boundary_report_ready"), False):
        decision = BOUNDARY_MISSING_DECISION
        status = "WARN"
    elif safety_violation:
        decision = REJECT_DECISION
        status = "FAIL"
    elif not boundary_settings.submit_armed or not settings.execute_armed:
        decision = NOT_ARMED_DECISION
        status = "WARN"
    elif not boundary_settings.submit_confirmation_ok or not settings.execute_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status = "WARN"
    elif settings.max_orders != 1:
        decision = MAX_ORDER_CAP_DECISION
        status = "WARN"
    elif not _safe_bool(paper_state.get("paper_state_clean"), False):
        decision = STATE_NOT_CLEAN_DECISION
        status = "WARN"
    elif submitted_rows:
        decision = EXECUTED_DECISION
        status = "PASS"
    elif any("paper_submitter_not_available" in set(e.get("blocked_reasons") or []) for e in rows):
        decision = SUBMITTER_NOT_AVAILABLE_DECISION
        status = "WARN"
    elif ready_rows:
        decision = SUBMITTER_NOT_AVAILABLE_DECISION
        status = "WARN"
    else:
        decision = REJECT_DECISION if rows else BOUNDARY_MISSING_DECISION
        status = "WARN"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in submitted_rows or ready_rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in submitted_rows or ready_rows), 10)
    safety_checks = {
        "mode_paper": str(settings.mode).lower() == "paper",
        "single_order_gate": settings.max_orders == 1,
        "paper_state_clean": _safe_bool(paper_state.get("paper_state_clean"), False),
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
        "submitted_orders_lte_one": len(submitted_rows) <= 1,
        "opened_positions_lte_one": len(position_rows) <= 1,
        "no_close_by_execution": True,
    }
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_SECOND_SUPERVISED_PAPER_ONLY_SUBMIT",
            "SECOND_TRADE_SINGLE_ORDER_EXECUTION_BOUNDARY",
        ] + (["SECOND_PAPER_ORDER_EXECUTED"] if decision == EXECUTED_DECISION else ["KEEP_DIAGNOSTIC"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "second_trade_submit_boundary_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_second_trade_submit_boundary_events": _safe_int(metadata.get("historical_second_trade_submit_boundary_events"), 0),
        "boundary_report_ready": _safe_bool(metadata.get("boundary_report_ready"), False),
        "boundary_report_decision": str(metadata.get("boundary_report_decision") or ""),
        "profile_name": boundary_settings.profile_name,
        "selected_overlay_id": boundary_settings.selected_overlay_id,
        "submit_boundary_events": len(boundary_rows),
        "execution_events": len(rows),
        "second_trade_execute_armed": bool(settings.execute_armed),
        "second_trade_execute_confirmation_ok": bool(settings.execute_confirmation_ok),
        "second_trade_submit_armed": bool(boundary_settings.submit_armed),
        "second_trade_submit_confirmation_ok": bool(boundary_settings.submit_confirmation_ok),
        "second_trade_submit_ready_count": len(ready_rows),
        "would_submit_count": len(would_submit_rows),
        "would_submit_to_paper_broker_count": len(would_submit_rows),
        "broker_submit_called": bool(broker_called),
        "broker_submit_called_by_second_trade_execution": bool(broker_called),
        "broker_submit_called_count": sum(1 for e in rows if _safe_bool(e.get("broker_submit_called"), False)),
        "orders_submitted_by_second_trade_execution": len(submitted_rows),
        "positions_opened_by_second_trade_execution": len(position_rows),
        "positions_closed_by_second_trade_execution": 0,
        "paper_order_submission_enabled": bool(would_submit_rows),
        "routing_enabled": False,
        "execution_enabled": bool(would_submit_rows),
        "second_trade_execute_enabled": bool(would_submit_rows),
        "second_trade_submit_enabled": bool(would_submit_rows),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "max_orders": int(settings.max_orders),
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "paper_state_clean": _safe_bool(paper_state.get("paper_state_clean"), False),
        "paper_state": dict(paper_state),
        "paper_status_open_positions": _safe_int(paper_state.get("paper_status_open_positions"), 0),
        "paper_status_pending_orders": _safe_int(paper_state.get("paper_status_pending_orders"), 0),
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "promotion_ready": False,
        "report": str(Path(data_dir) / settings.report_name),
        "jsonl": str(Path(data_dir) / settings.jsonl_name),
    }


def build_lsr_v2_second_trade_submit_execution_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    settings: LSRV2SecondTradeSubmitExecutionSettings | None = None,
    paper_submitter: PaperSubmitter | None = None,
    allow_project_submitter: bool = False,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondTradeSubmitExecutionSettings.from_env(data_dir=str(data_dir))
    boundary_settings = _clone_boundary_settings(data_dir=data_dir, execution_settings=settings)
    selected_cycle_id, boundary_events, metadata = select_second_trade_submit_boundary_events(
        data_dir=data_dir,
        settings=settings,
        requested_cycle_id=cycle_id,
    )
    paper_state_clean, paper_state_meta = read_second_trade_paper_state_cleanliness(data_dir)

    submitter_error = ""
    submitter_to_use: PaperSubmitter | None = None
    execute_controls_ok = bool(settings.execute_armed and settings.execute_confirmation_ok)
    submit_controls_ok = bool(boundary_settings.submit_armed and boundary_settings.submit_confirmation_ok)
    basic_safety_ok = bool(
        str(settings.mode).lower() == "paper"
        and settings.max_orders == 1
        and settings.fail_closed
        and paper_state_clean
    )
    if execute_controls_ok and submit_controls_ok and basic_safety_ok:
        submitter_to_use = paper_submitter
        if submitter_to_use is None and allow_project_submitter:
            submitter_to_use, submitter_error = build_second_trade_project_paper_submitter(data_dir=data_dir, settings=settings)

    execution_events = build_lsr_v2_second_trade_submit_execution_events(
        boundary_events,
        settings=settings,
        boundary_settings=boundary_settings,
        paper_state=paper_state_meta,
        paper_submitter=submitter_to_use,
        submitter_error=submitter_error,
    )
    base = Path(data_dir)
    _write_jsonl_replace(base / settings.jsonl_name, execution_events)
    report = summarize_lsr_v2_second_trade_submit_execution(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        boundary_events=boundary_events,
        execution_events=execution_events,
        settings=settings,
        boundary_settings=boundary_settings,
        metadata=metadata,
        paper_state=paper_state_meta,
    )
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)
