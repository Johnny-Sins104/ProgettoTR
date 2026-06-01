"""Prompt 29.4.4s-10k — LSR-v2 first supervised paper-only submit.

This module adds the final one-shot paper-only execution boundary after the
LSR-v2 supervised submit boundary.  It is disabled by default and requires two
separate manual confirmations:

* the existing submit boundary arm/confirmation from 29.4.4s-10j;
* an additional execute arm/confirmation from this patch.

When those controls are present, the paper state is clean, and a paper-only
submitter is explicitly supplied, at most one order can be submitted.  The
standalone runner wires a PaperBrokerAdapter submitter only when the execute
controls are present.  Live, testnet and exchange broker execution remain hard
blocked.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import json
import os

try:  # project import when run from repository root
    from core.lsr_v2_supervised_paper_submit import (  # type: ignore
        LSRV2SupervisedPaperSubmitSettings,
        PREFLIGHT_EVENT_TYPE,
        READY_ARMED_DECISION,
        EXECUTED_DECISION as BOUNDARY_EXECUTED_DECISION,
        build_lsr_v2_supervised_paper_submit_event,
        select_cycle_scoped_submit_preflight_events,
        _safe_bool,
        _safe_float,
        _safe_int,
    )
except Exception:  # package import in tests
    from trading_bot.core.lsr_v2_supervised_paper_submit import (  # type: ignore
        LSRV2SupervisedPaperSubmitSettings,
        PREFLIGHT_EVENT_TYPE,
        READY_ARMED_DECISION,
        EXECUTED_DECISION as BOUNDARY_EXECUTED_DECISION,
        build_lsr_v2_supervised_paper_submit_event,
        select_cycle_scoped_submit_preflight_events,
        _safe_bool,
        _safe_float,
        _safe_int,
    )

PROMPT_ID = "29.4.4s-10k"
EVENT_TYPE = "LSR_V2_SUPERVISED_PAPER_SUBMIT_EXECUTION"
REPORT_NAME = "lsr_v2_supervised_paper_submit_execution_report.json"
JSONL_NAME = "lsr_v2_supervised_paper_submit_execution.jsonl"

EXECUTE_ENV = "LSR_V2_PAPER_SUBMIT_EXECUTE"
EXECUTE_CONFIRM_ENV = "LSR_V2_PAPER_SUBMIT_EXECUTE_CONFIRMATION"
REQUIRED_EXECUTE_VALUE = "1"
REQUIRED_EXECUTE_CONFIRMATION = "I_UNDERSTAND_EXECUTE_ONE_PAPER_ORDER_ONLY"

EXECUTED_DECISION = "LSR_V2_SINGLE_PAPER_ORDER_EXECUTED"
NOT_ARMED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_EXECUTION_NOT_ARMED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_EXECUTION_CONFIRMATION_MISSING"
PREFLIGHT_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SUBMIT_PREFLIGHT_MISSING"
STATE_NOT_CLEAN_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_PAPER_STATE_NOT_CLEAN"
SUBMITTER_NOT_AVAILABLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_PAPER_SUBMITTER_NOT_AVAILABLE"
MAX_ORDER_CAP_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_EXECUTION_MAX_ORDER_CAP_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_EXECUTION_SAFETY_FAILED"

PaperSubmitter = Callable[[Mapping[str, Any]], Mapping[str, Any] | bool | None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl_replace(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), sort_keys=True) + "\n")
            count += 1
    return count


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class LSRV2SupervisedPaperSubmitExecutionSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
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
    def from_env(cls, data_dir: str = "data") -> "LSRV2SupervisedPaperSubmitExecutionSettings":
        max_orders = _safe_int(os.getenv("LSR_V2_PAPER_SUBMIT_MAX_ORDERS"), 1)
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
            mode=str(os.getenv("LSR_V2_PAPER_SUBMIT_MODE") or "paper"),
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


def read_paper_state_cleanliness(data_dir: str | Path) -> tuple[bool, dict[str, Any]]:
    """Return whether the active paper state is clean enough for one-shot submit."""
    base = Path(data_dir)
    state = _read_json(base / "paper_state.json")
    status = _read_json(base / "paper_status.json")
    # Missing state is acceptable: PaperBroker can initialize a clean state.
    orders = _as_mapping(state.get("orders"))
    positions = _as_mapping(state.get("positions"))
    open_positions = _safe_int(status.get("open_positions"), 0)
    pending_orders = _safe_int(status.get("pending_orders"), 0)

    active_orders = []
    for oid, order in orders.items():
        row = _as_mapping(order)
        order_status = str(row.get("status") or row.get("state") or "").upper()
        if order_status not in {"", "CLOSED", "CANCELLED", "REJECTED", "FILLED_CLOSED"}:
            active_orders.append(str(oid))
    active_positions = []
    for pid, pos in positions.items():
        row = _as_mapping(pos)
        position_status = str(row.get("status") or row.get("state") or "OPEN").upper()
        is_open = _safe_bool(row.get("open"), position_status not in {"CLOSED", "CANCELLED"})
        if is_open and position_status not in {"CLOSED", "CANCELLED"}:
            active_positions.append(str(pid))

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


def build_project_paper_submitter(
    *,
    data_dir: str | Path,
    settings: LSRV2SupervisedPaperSubmitExecutionSettings | None = None,
) -> tuple[PaperSubmitter | None, str]:
    """Build a PaperBrokerAdapter submitter from the installed project.

    The function imports project broker classes lazily so unit tests and minimal
    contexts can run without the complete runtime.  It never imports or wires an
    exchange broker.
    """
    settings = settings or LSRV2SupervisedPaperSubmitExecutionSettings(data_dir=str(data_dir))
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
            "paper_order_source": "lsr_v2_supervised_paper_submit_execution",
            "execution_source": "lsr_v2_supervised_paper_submit_execution",
            "profile_name": str(payload.get("profile_name") or ""),
            "selected_overlay_id": str(payload.get("selected_overlay_id") or ""),
            "candidate_id": str(payload.get("candidate_id") or ""),
            "risk_per_trade_pct": _safe_float(payload.get("risk_per_trade_pct"), 0.0025),
            "risk_amount": _safe_float(payload.get("risk_amount"), 0.0),
            "single_order_gate": True,
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


def _clone_submit_boundary_settings(
    *,
    data_dir: str | Path,
    execution_settings: LSRV2SupervisedPaperSubmitExecutionSettings,
) -> LSRV2SupervisedPaperSubmitSettings:
    base = LSRV2SupervisedPaperSubmitSettings.from_env(data_dir=str(data_dir))
    return LSRV2SupervisedPaperSubmitSettings(
        **{
            **base.to_dict(),
            "data_dir": str(data_dir),
            "report_name": REPORT_NAME,
            "jsonl_name": JSONL_NAME,
            "max_orders": int(execution_settings.max_orders),
            "mode": str(execution_settings.mode),
        }
    )


def _convert_boundary_event(
    event: Mapping[str, Any], *, execution_settings: LSRV2SupervisedPaperSubmitExecutionSettings, paper_state: Mapping[str, Any], submitter_error: str = "") -> dict[str, Any]:
    row = dict(event)
    row["event_type"] = EVENT_TYPE
    row["prompt_id"] = PROMPT_ID
    row["execute_armed"] = bool(execution_settings.execute_armed)
    row["execute_confirmation_ok"] = bool(execution_settings.execute_confirmation_ok)
    row["paper_state_clean"] = bool(paper_state.get("paper_state_clean"))
    row["paper_state_blockers"] = list(paper_state.get("paper_state_blockers") or [])
    row["submitter_error"] = submitter_error
    row["live_enabled"] = False
    row["testnet_enabled"] = False
    row["exchange_broker_enabled"] = False
    row["operational_unlock_allowed"] = False
    row["max_orders"] = int(execution_settings.max_orders)
    row["single_order_gate"] = True
    return row


def build_lsr_v2_supervised_paper_submit_execution_report_from_files(
    *,
    data_dir: str | Path = "data",
    cycle_id: str = "",
    execution_settings: LSRV2SupervisedPaperSubmitExecutionSettings | None = None,
    paper_submitter: PaperSubmitter | None = None,
    allow_project_submitter: bool = False,
) -> dict[str, Any]:
    execution_settings = execution_settings or LSRV2SupervisedPaperSubmitExecutionSettings.from_env(data_dir=str(data_dir))
    submit_settings = _clone_submit_boundary_settings(data_dir=data_dir, execution_settings=execution_settings)
    base = Path(data_dir)
    selected_cycle_id, preflight_events, metadata = select_cycle_scoped_submit_preflight_events(
        data_dir=data_dir,
        settings=submit_settings,
        requested_cycle_id=cycle_id,
    )
    paper_state_clean, paper_state_meta = read_paper_state_cleanliness(data_dir)

    submitter_error = ""
    submitter_to_use: PaperSubmitter | None = None
    execute_controls_ok = bool(execution_settings.execute_armed and execution_settings.execute_confirmation_ok)
    submit_controls_ok = bool(submit_settings.submit_armed and submit_settings.submit_confirmation_ok)
    basic_safety_ok = bool(
        str(execution_settings.mode).lower() == "paper"
        and execution_settings.max_orders == 1
        and execution_settings.fail_closed
        and paper_state_clean
    )
    if execute_controls_ok and submit_controls_ok and basic_safety_ok:
        submitter_to_use = paper_submitter
        if submitter_to_use is None and allow_project_submitter:
            submitter_to_use, submitter_error = build_project_paper_submitter(data_dir=data_dir, settings=execution_settings)

    boundary_events = []
    for idx, preflight in enumerate(preflight_events):
        boundary = build_lsr_v2_supervised_paper_submit_event(
            preflight_event=preflight,
            settings=submit_settings,
            index=idx,
            paper_submitter=submitter_to_use,
        )
        converted = _convert_boundary_event(boundary, execution_settings=execution_settings, paper_state=paper_state_meta, submitter_error=submitter_error)
        # If execution-specific guards failed, make them explicit and keep any
        # inherited submit result blocked before a submitter can be used.
        blockers = set(converted.get("blocked_reasons") or [])
        if not execution_settings.execute_armed:
            blockers.add("execute_not_armed")
        if not execution_settings.execute_confirmation_ok:
            blockers.add("execute_confirmation_missing")
        if not paper_state_clean:
            blockers.update(paper_state_meta.get("paper_state_blockers") or ["paper_state_not_clean"])
        if execute_controls_ok and submit_controls_ok and basic_safety_ok and submitter_to_use is None:
            blockers.add("paper_submitter_not_available")
        converted["blocked_reasons"] = sorted(blockers)
        if blockers and not _safe_bool(converted.get("order_submitted"), False):
            converted["blocked_reason"] = sorted(blockers)[0]
        boundary_events.append(converted)

    _write_jsonl_replace(base / execution_settings.jsonl_name, boundary_events)
    report = summarize_lsr_v2_supervised_paper_submit_execution(
        data_dir=data_dir,
        cycle_id=selected_cycle_id,
        preflight_events=preflight_events,
        execution_events=boundary_events,
        execution_settings=execution_settings,
        submit_settings=submit_settings,
        metadata=metadata,
        paper_state=paper_state_meta,
    )
    _write_json(base / execution_settings.report_name, report)
    return _read_json(base / execution_settings.report_name)


def summarize_lsr_v2_supervised_paper_submit_execution(
    *,
    data_dir: str | Path,
    cycle_id: str,
    preflight_events: Iterable[Mapping[str, Any]],
    execution_events: Iterable[Mapping[str, Any]],
    execution_settings: LSRV2SupervisedPaperSubmitExecutionSettings,
    submit_settings: LSRV2SupervisedPaperSubmitSettings,
    metadata: Mapping[str, Any] | None = None,
    paper_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
    paper_state = dict(paper_state or {})
    preflight_rows = [dict(e) for e in preflight_events if dict(e).get("event_type") == PREFLIGHT_EVENT_TYPE]
    rows = [dict(e) for e in execution_events]
    ready_rows = [e for e in rows if _safe_bool(e.get("submit_ready"), False)]
    would_submit_rows = [e for e in rows if _safe_bool(e.get("would_submit"), False)]
    submitted_rows = [e for e in rows if _safe_int(e.get("orders_submitted_by_lsr_v2_submit"), 0) > 0]
    position_rows = [e for e in rows if _safe_int(e.get("positions_opened_by_lsr_v2_submit"), 0) > 0]
    broker_called = any(_safe_bool(e.get("broker_submit_called"), False) for e in rows)

    blockers: list[str] = []
    if not preflight_rows:
        blockers.append("submit_preflight_missing")
    if not submit_settings.submit_armed or not execution_settings.execute_armed:
        blockers.append("execution_not_armed")
    if not submit_settings.submit_confirmation_ok or not execution_settings.execute_confirmation_ok:
        blockers.append("execution_confirmation_missing")
    if execution_settings.max_orders != 1:
        blockers.append("max_orders_not_one")
    if not _safe_bool(paper_state.get("paper_state_clean"), False):
        blockers.append("paper_state_not_clean")
        blockers.extend(str(b) for b in paper_state.get("paper_state_blockers") or [])
    if any("paper_submitter_not_available" in set(e.get("blocked_reasons") or []) for e in rows):
        blockers.append("paper_submitter_not_available")
    safety_violation = any(
        _safe_bool(e.get("live_enabled"), False)
        or _safe_bool(e.get("testnet_enabled"), False)
        or _safe_bool(e.get("exchange_broker_enabled"), False)
        or _safe_bool(e.get("operational_unlock_allowed"), False)
        or _safe_int(e.get("orders_submitted_by_lsr_v2_submit"), 0) > 1
        for e in rows
    )
    if len(submitted_rows) > 1:
        safety_violation = True
        blockers.append("more_than_one_order_submitted")
    if safety_violation:
        blockers.append("safety_violation_detected")

    if not preflight_rows:
        decision = PREFLIGHT_MISSING_DECISION
        status = "WARN"
    elif safety_violation:
        decision = REJECT_DECISION
        status = "WARN"
    elif not submit_settings.submit_armed or not execution_settings.execute_armed:
        decision = NOT_ARMED_DECISION
        status = "WARN"
    elif not submit_settings.submit_confirmation_ok or not execution_settings.execute_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status = "WARN"
    elif execution_settings.max_orders != 1:
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
        # Should only happen when the execution is armed but the submitter is not wired.
        decision = SUBMITTER_NOT_AVAILABLE_DECISION
        status = "WARN"
    else:
        decision = REJECT_DECISION if rows else PREFLIGHT_MISSING_DECISION
        status = "WARN"

    total_risk = round(sum(_safe_float(e.get("risk_amount"), 0.0) for e in submitted_rows or ready_rows), 10)
    total_notional = round(sum(_safe_float(e.get("notional"), 0.0) for e in submitted_rows or ready_rows), 10)
    safety_checks = {
        "mode_paper": str(execution_settings.mode).lower() == "paper",
        "single_order_gate": execution_settings.max_orders == 1,
        "paper_state_clean": _safe_bool(paper_state.get("paper_state_clean"), False),
        "live_disabled": True,
        "testnet_disabled": True,
        "exchange_broker_disabled": True,
        "operational_unlock_blocked": True,
        "submitted_orders_lte_one": len(submitted_rows) <= 1,
    }
    return {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "classification_labels": [
            "LSR_V2_FIRST_SUPERVISED_PAPER_ONLY_SUBMIT",
            "SINGLE_ORDER_EXECUTION_BOUNDARY",
        ] + (["PAPER_ORDER_EXECUTED"] if decision == EXECUTED_DECISION else ["KEEP_DIAGNOSTIC"]),
        "blockers": sorted(set(blockers)),
        "cycle_id": str(cycle_id or ""),
        "event_source": str(metadata.get("event_source") or "submit_preflight_jsonl"),
        "strict_cycle_scope": bool(metadata.get("strict_cycle_scope", True)),
        "historical_submit_preflight_events": _safe_int(metadata.get("historical_submit_preflight_events"), 0),
        "profile_name": submit_settings.profile_name,
        "selected_overlay_id": submit_settings.selected_overlay_id,
        "submit_preflight_events": len(preflight_rows),
        "execution_events": len(rows),
        "execute_armed": bool(execution_settings.execute_armed),
        "execute_confirmation_ok": bool(execution_settings.execute_confirmation_ok),
        "submit_armed": bool(submit_settings.submit_armed),
        "submit_confirmation_ok": bool(submit_settings.submit_confirmation_ok),
        "submit_ready_count": len(ready_rows),
        "would_submit_count": len(would_submit_rows),
        "would_submit_to_paper_broker_count": len(would_submit_rows),
        "broker_submit_called": bool(broker_called),
        "broker_submit_called_count": sum(1 for e in rows if _safe_bool(e.get("broker_submit_called"), False)),
        "orders_submitted_by_lsr_v2_execution": len(submitted_rows),
        "positions_opened_by_lsr_v2_execution": len(position_rows),
        "paper_order_submission_enabled": bool(would_submit_rows),
        "routing_enabled": False,
        "execution_enabled": bool(would_submit_rows),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "max_orders": int(execution_settings.max_orders),
        "paper_broker_adapter": execution_settings.paper_broker_adapter_name,
        "paper_state_clean": _safe_bool(paper_state.get("paper_state_clean"), False),
        "paper_state": dict(paper_state),
        "total_risk_amount": total_risk,
        "total_notional": total_notional,
        "safety_checks": safety_checks,
        "safety_ok": bool(all(safety_checks.values()) and not safety_violation),
        "promotion_ready": False,
        "report": str(Path(data_dir) / execution_settings.report_name),
        "jsonl": str(Path(data_dir) / execution_settings.jsonl_name),
    }
