"""Patch 30.3.0I - execute one bounded second supervised paper order.

The execution path is paper-only, default-off, and consumes the 30.3.0G/H
readiness artifacts.  It never wires live, testnet, or exchange brokers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
import json
import os

try:
    from .lsr_v2_paper_status_reconciliation import build_lsr_v2_paper_status_reconciliation_report_from_files
except Exception:  # pragma: no cover - script-style fallback
    from core.lsr_v2_paper_status_reconciliation import build_lsr_v2_paper_status_reconciliation_report_from_files  # type: ignore


PROMPT_ID = "30.3.0I"
EVENT_TYPE = "LSR_V2_SECOND_PAPER_ORDER_SUBMIT_EXECUTION"
REPORT_NAME = "lsr_v2_second_paper_order_submit_execution_report.json"
JSONL_NAME = "lsr_v2_second_paper_order_submit_execution.jsonl"

SECOND_GATE_REPORT_NAME = "lsr_v2_second_paper_order_gate_report.json"
MULTI_ORDER_READINESS_REPORT_NAME = "lsr_v2_paper_bounded_multi_order_session_readiness_report.json"
FINAL_RUNTIME_AUDIT_REPORT_NAME = "lsr_v2_paper_final_runtime_audit_report.json"
PNL_RECONCILIATION_REPORT_NAME = "lsr_v2_paper_realized_pnl_reconciliation_report.json"
PAPER_STATE_NAME = "paper_state.json"
PAPER_STATUS_NAME = "paper_status.json"
PAPER_EVENTS_NAME = "paper_events.jsonl"

EXECUTED_DECISION = "LSR_V2_SECOND_SINGLE_PAPER_ORDER_EXECUTED"
NOT_ARMED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_EXECUTION_NOT_ARMED"
CONFIRMATION_MISSING_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_EXECUTION_CONFIRMATION_MISSING"
PREREQ_BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_EXECUTION_PREREQUISITES_BLOCKED"
STATE_BLOCKED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_EXECUTION_STATE_BLOCKED"
SUBMITTER_NOT_AVAILABLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_SUBMITTER_NOT_AVAILABLE"
MAX_ORDER_CAP_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SECOND_PAPER_MAX_ORDER_CAP_BLOCKED"
REJECT_DECISION = "REJECT_LSR_V2_SECOND_PAPER_ORDER_EXECUTION_FAILED"

ARM_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_ARM"
CONFIRMATION_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_CONFIRMATION"
CONFIRMATION_PHRASE = "I_UNDERSTAND_SECOND_SINGLE_PAPER_ORDER"
EXECUTE_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_EXECUTE"
EXECUTE_CONFIRMATION_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_EXECUTE_CONFIRMATION"
EXECUTE_CONFIRMATION_PHRASE = "I_UNDERSTAND_EXECUTE_SECOND_PAPER_ORDER_ONLY"
MAX_ORDERS_ENV = "LSR_V2_SECOND_PAPER_SUBMIT_MAX_ORDERS"
INITIAL_BALANCE_ENV = "LSR_V2_PAPER_INITIAL_BALANCE"
FEE_RATE_ENV = "LSR_V2_PAPER_FEE_RATE"
RISK_PCT_ENV = "LSR_V2_SECOND_PAPER_RISK_PER_TRADE_PCT"

PaperSubmitter = Callable[[Mapping[str, Any]], Mapping[str, Any] | bool | None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"__read_error__": str(exc)}
    return data if isinstance(data, dict) else {}


def _write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_jsonl(path: str | Path, payload: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(payload), sort_keys=True) + "\n")


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled", "pass", "ready"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "", "none", "null"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


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
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _collection_rows(value: Any, *, id_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, raw in value.items():
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(key))
            rows.append(row)
    elif isinstance(value, list):
        for idx, raw in enumerate(value):
            row = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            row.setdefault(id_field, str(row.get(id_field) or idx))
            rows.append(row)
    return rows


def _metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    meta = row.get("metadata")
    return meta if isinstance(meta, Mapping) else {}


def _status_text(row: Mapping[str, Any], default: str = "") -> str:
    return str(row.get("status") or row.get("state") or row.get("position_status") or row.get("order_status") or default).upper()


def _is_position_open(row: Mapping[str, Any]) -> bool:
    status = _status_text(row, "OPEN")
    default_open = status not in {"CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FILLED_CLOSED", "EXPIRED"}
    return _safe_bool(row.get("open"), default_open) and default_open


def _is_order_pending(row: Mapping[str, Any]) -> bool:
    return _status_text(row, "FILLED") in {"NEW", "OPEN", "PENDING", "PLACED", "SUBMITTED", "ACCEPTED"}


def _recursive_any_true(payloads: list[Any], keys: set[str]) -> bool:
    for payload in payloads:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                if key in keys and _safe_bool(value, False):
                    return True
                if isinstance(value, (Mapping, list)) and _recursive_any_true([value], keys):
                    return True
        elif isinstance(payload, list) and _recursive_any_true(list(payload), keys):
            return True
    return False


def _cycle_id(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("cycle_id") or meta.get("cycle_id") or "")


def _source(row: Mapping[str, Any]) -> str:
    meta = _metadata(row)
    return str(row.get("execution_source") or row.get("paper_order_source") or meta.get("execution_source") or meta.get("paper_order_source") or "")


@dataclass(frozen=True)
class LSRV2SecondPaperOrderSubmitExecutionSettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    arm: str = ""
    confirmation: str = ""
    execute_arm: str = ""
    execute_confirmation: str = ""
    max_orders: int = 1
    initial_balance: float = 1000.0
    fee_rate: float = 0.002
    risk_per_trade_pct: float = 0.0025
    mode: str = "paper"
    paper_broker_adapter_name: str = "PaperBrokerAdapter"
    fail_closed: bool = True

    @classmethod
    def from_env(cls, data_dir: str = "data") -> "LSRV2SecondPaperOrderSubmitExecutionSettings":
        max_orders = _safe_int(os.getenv(MAX_ORDERS_ENV), 1)
        if max_orders <= 0:
            max_orders = 1
        initial_balance = _safe_float(os.getenv(INITIAL_BALANCE_ENV), 1000.0)
        if initial_balance <= 0:
            initial_balance = 1000.0
        fee_rate = _safe_float(os.getenv(FEE_RATE_ENV), 0.002)
        if fee_rate < 0:
            fee_rate = 0.002
        risk = _safe_float(os.getenv(RISK_PCT_ENV), 0.0025)
        if risk <= 0:
            risk = 0.0025
        return cls(
            data_dir=str(data_dir),
            arm=str(os.getenv(ARM_ENV) or ""),
            confirmation=str(os.getenv(CONFIRMATION_ENV) or ""),
            execute_arm=str(os.getenv(EXECUTE_ENV) or ""),
            execute_confirmation=str(os.getenv(EXECUTE_CONFIRMATION_ENV) or ""),
            max_orders=max_orders,
            initial_balance=initial_balance,
            fee_rate=fee_rate,
            risk_per_trade_pct=risk,
        )

    @property
    def arm_ok(self) -> bool:
        return self.arm.strip() == "1"

    @property
    def confirmation_ok(self) -> bool:
        return self.confirmation.strip() == CONFIRMATION_PHRASE

    @property
    def execute_armed(self) -> bool:
        return self.execute_arm.strip() == "1"

    @property
    def execute_confirmation_ok(self) -> bool:
        return self.execute_confirmation.strip() == EXECUTE_CONFIRMATION_PHRASE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _latest_open_position_for_order(state: Mapping[str, Any], order_id: str) -> dict[str, Any]:
    for row in _collection_rows(state.get("positions"), id_field="position_id"):
        meta = _metadata(row)
        if str(meta.get("source_order_id") or row.get("source_order_id") or "") == order_id:
            return row
    return {}


def _state_metrics(state: Mapping[str, Any], status: Mapping[str, Any]) -> dict[str, Any]:
    orders = _collection_rows(state.get("orders"), id_field="order_id")
    positions = _collection_rows(state.get("positions"), id_field="position_id")
    open_positions = [row for row in positions if _is_position_open(row)]
    pending_orders = [row for row in orders if _is_order_pending(row)]
    status_open = _safe_int(status.get("open_positions"), len(open_positions))
    status_pending = _safe_int(status.get("pending_orders"), len(pending_orders))
    return {
        "order_count": len(orders),
        "position_count": len(positions),
        "open_positions": len(open_positions),
        "pending_orders": len(pending_orders),
        "paper_status_open_positions": status_open,
        "paper_status_pending_orders": status_pending,
        "state_status_consistent": len(open_positions) == status_open and len(pending_orders) == status_pending,
        "kill_switch": _safe_bool(state.get("kill_switch"), False) or _safe_bool(status.get("kill_switch"), False),
    }


def _candidate_from_reports(second_gate: Mapping[str, Any], multi_readiness: Mapping[str, Any]) -> dict[str, Any]:
    candidate = multi_readiness.get("candidate") if isinstance(multi_readiness.get("candidate"), Mapping) else {}
    if not candidate:
        candidate = second_gate.get("candidate") if isinstance(second_gate.get("candidate"), Mapping) else {}
    return dict(candidate)


def _order_payload(
    *,
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    settings: LSRV2SecondPaperOrderSubmitExecutionSettings,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    symbol = str(candidate.get("symbol") or "")
    side = str(candidate.get("side") or "").upper()
    cycle_id = str(candidate.get("cycle_id") or "")
    candidate_id = str(candidate.get("candidate_id") or "")
    entry = _safe_float(candidate.get("entry_price"), 0.0)
    stop = _safe_float(candidate.get("stop_loss"), 0.0)
    take = _safe_float(candidate.get("take_profit"), 0.0)
    balance = _safe_float(state.get("balance"), settings.initial_balance)
    if balance <= 0:
        balance = settings.initial_balance
    risk_amount = balance * settings.risk_per_trade_pct
    stop_distance = abs(entry - stop)
    quantity = risk_amount / stop_distance if stop_distance > 0 else 0.0
    notional = quantity * entry if quantity > 0 and entry > 0 else 0.0
    if symbol != "BTC/USDT":
        blockers.append("symbol_not_allowed")
    if side not in {"BUY", "SELL"}:
        blockers.append("side_invalid")
    if entry <= 0 or stop <= 0 or take <= 0:
        blockers.append("candidate_levels_invalid")
    if stop_distance <= 0:
        blockers.append("stop_distance_invalid")
    if quantity <= 0 or notional <= 0:
        blockers.append("quantity_invalid")
    return {
        "cycle_id": cycle_id,
        "candidate_id": candidate_id,
        "symbol": symbol,
        "timeframe": "5m",
        "side": side,
        "order_type": "MARKET",
        "entry_price": entry,
        "stop_loss": stop,
        "take_profit": take,
        "risk_per_trade_pct": settings.risk_per_trade_pct,
        "risk_amount": risk_amount,
        "quantity": quantity,
        "position_size": quantity,
        "notional": notional,
        "max_positions": 1,
        "profile_name": "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24",
        "selected_overlay_id": "combo_loss3_dd10_side_cap",
    }, blockers


def build_project_paper_submitter(
    *,
    data_dir: str | Path,
    settings: LSRV2SecondPaperOrderSubmitExecutionSettings,
) -> tuple[PaperSubmitter | None, str]:
    try:
        try:
            from .paper_broker import PaperBroker
            from .broker_adapter import PaperBrokerAdapter
        except Exception:
            from core.paper_broker import PaperBroker  # type: ignore
            from core.broker_adapter import PaperBrokerAdapter  # type: ignore
    except Exception as exc:
        return None, f"paper_broker_import_failed:{type(exc).__name__}:{exc}"

    base = Path(data_dir)
    broker = PaperBroker(
        initial_balance=float(settings.initial_balance),
        fee_rate=float(settings.fee_rate),
        state_path=base / PAPER_STATE_NAME,
        events_path=base / PAPER_EVENTS_NAME,
    )
    last_prices: dict[str, float] = {}
    adapter = PaperBrokerAdapter(broker, last_prices=last_prices, leverage_for_display=1.0)

    def submitter(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        symbol = str(payload.get("symbol") or "")
        side = str(payload.get("side") or "").upper()
        price = _safe_float(payload.get("entry_price"), 0.0)
        qty = _safe_float(payload.get("quantity") or payload.get("position_size"), 0.0)
        last_prices[symbol] = price
        metadata = {
            "cycle_id": str(payload.get("cycle_id") or ""),
            "candidate_id": str(payload.get("candidate_id") or ""),
            "paper_order_source": "lsr_v2_second_paper_order_submit_execution",
            "execution_source": "lsr_v2_second_paper_order_submit_execution",
            "profile_name": str(payload.get("profile_name") or ""),
            "selected_overlay_id": str(payload.get("selected_overlay_id") or ""),
            "risk_per_trade_pct": _safe_float(payload.get("risk_per_trade_pct"), settings.risk_per_trade_pct),
            "risk_amount": _safe_float(payload.get("risk_amount"), 0.0),
            "second_single_order_gate": True,
            "bounded_multi_order_session": True,
            "live_enabled": False,
            "testnet_enabled": False,
            "exchange_broker_enabled": False,
        }
        order = adapter.place_order(
            symbol=symbol,
            side=side,  # type: ignore[arg-type]
            qty=qty,
            price=price,
            stop_loss=_safe_float(payload.get("stop_loss"), 0.0),
            take_profit=_safe_float(payload.get("take_profit"), 0.0),
            metadata=metadata,
        )
        state_after = _read_json(base / PAPER_STATE_NAME)
        position = _latest_open_position_for_order(state_after, str(getattr(order, "order_id", "")))
        return {
            "order_submitted": True,
            "position_opened": bool(position),
            "order_id": str(getattr(order, "order_id", "")),
            "position_id": str(position.get("position_id") or ""),
            "paper_broker_adapter": settings.paper_broker_adapter_name,
        }

    return submitter, ""


def build_lsr_v2_second_paper_order_submit_execution_report_from_files(
    *,
    data_dir: str | Path = "data",
    settings: LSRV2SecondPaperOrderSubmitExecutionSettings | None = None,
    paper_submitter: PaperSubmitter | None = None,
    allow_project_submitter: bool = False,
    sync_status_after_submit: bool = True,
) -> dict[str, Any]:
    settings = settings or LSRV2SecondPaperOrderSubmitExecutionSettings.from_env(data_dir=str(data_dir))
    base = Path(data_dir)
    second_gate = _read_json(base / SECOND_GATE_REPORT_NAME)
    multi_readiness = _read_json(base / MULTI_ORDER_READINESS_REPORT_NAME)
    final_audit = _read_json(base / FINAL_RUNTIME_AUDIT_REPORT_NAME)
    pnl_report = _read_json(base / PNL_RECONCILIATION_REPORT_NAME)
    state_before = _read_json(base / PAPER_STATE_NAME)
    status_before = _read_json(base / PAPER_STATUS_NAME)
    metrics_before = _state_metrics(state_before, status_before)
    candidate = _candidate_from_reports(second_gate, multi_readiness)
    payload, payload_blockers = _order_payload(candidate=candidate, state=state_before, settings=settings)

    unsafe = _recursive_any_true(
        [second_gate, multi_readiness, final_audit, pnl_report, state_before, status_before],
        {"live_mode_enabled", "live_enabled", "testnet_mode_enabled", "testnet_enabled", "exchange_broker_enabled", "broker_submit_real_called", "broker_close_real_called"},
    )
    gate_ok = str(second_gate.get("status") or "") == "PASS" and _safe_bool(second_gate.get("second_order_gate_ready"), False)
    readiness_ok = str(multi_readiness.get("status") or "") == "PASS" and _safe_bool(multi_readiness.get("multi_order_session_ready"), False)
    final_ok = str(final_audit.get("status") or "") in {"PASS", "WARN"} and str(final_audit.get("decision") or "") != "REJECT_LSR_V2_PAPER_FINAL_RUNTIME_AUDIT_FAILED"
    pnl_ok = str(pnl_report.get("reconciliation_status") or pnl_report.get("status") or "") in {"PASS", "WARN"}
    state_clean = (
        metrics_before["open_positions"] == 0
        and metrics_before["pending_orders"] == 0
        and metrics_before["paper_status_open_positions"] == 0
        and metrics_before["paper_status_pending_orders"] == 0
        and metrics_before["state_status_consistent"]
        and not metrics_before["kill_switch"]
    )
    max_orders_ok = settings.max_orders == 1
    arm_ok = settings.arm_ok and settings.confirmation_ok
    execute_ok = settings.execute_armed and settings.execute_confirmation_ok

    blockers: list[str] = []
    if not gate_ok:
        blockers.append("second_order_gate_not_ready")
    if not readiness_ok:
        blockers.append("multi_order_session_not_ready")
    if not final_ok:
        blockers.append("final_runtime_audit_missing_or_fail")
    if not pnl_ok:
        blockers.append("pnl_reconciliation_missing_or_fail")
    if not state_clean:
        blockers.append("paper_state_not_clean")
    if metrics_before["open_positions"] > 0 or metrics_before["paper_status_open_positions"] > 0:
        blockers.append("open_positions_not_zero")
    if metrics_before["pending_orders"] > 0 or metrics_before["paper_status_pending_orders"] > 0:
        blockers.append("pending_orders_not_zero")
    if not metrics_before["state_status_consistent"]:
        blockers.append("paper_state_status_divergence")
    if metrics_before["kill_switch"]:
        blockers.append("kill_switch_enabled")
    if not max_orders_ok:
        blockers.append("max_orders_must_be_one")
    if not settings.arm_ok:
        blockers.append("submit_arm_missing")
    if not settings.confirmation_ok:
        blockers.append("submit_confirmation_missing")
    if not settings.execute_armed:
        blockers.append("execute_not_armed")
    if not settings.execute_confirmation_ok:
        blockers.append("execute_confirmation_missing")
    if unsafe:
        blockers.append("live_testnet_exchange_or_real_broker_flag_detected")
    blockers.extend(payload_blockers)

    submitter_error = ""
    submitter_to_use = paper_submitter
    submitted = False
    opened = False
    order_id = ""
    position_id = ""
    submitter_called = False

    if gate_ok and readiness_ok and final_ok and pnl_ok and state_clean and max_orders_ok and arm_ok and execute_ok and not unsafe and not payload_blockers:
        if submitter_to_use is None and allow_project_submitter:
            submitter_to_use, submitter_error = build_project_paper_submitter(data_dir=data_dir, settings=settings)
        if submitter_to_use is None:
            blockers.append("paper_submitter_not_available")
        else:
            submitter_called = True
            result = submitter_to_use(payload)
            result_map = result if isinstance(result, Mapping) else {}
            submitted = bool(result is True or _safe_bool(result_map.get("order_submitted"), False))
            opened = bool(_safe_bool(result_map.get("position_opened"), submitted))
            order_id = str(result_map.get("order_id") or "")
            position_id = str(result_map.get("position_id") or "")
            if not submitted:
                blockers.append("paper_order_not_submitted")
            if not opened:
                blockers.append("paper_position_not_opened")

    status_sync_report: dict[str, Any] = {}
    if submitted and opened and sync_status_after_submit:
        status_sync_report = build_lsr_v2_paper_status_reconciliation_report_from_files(
            data_dir=data_dir,
            cycle_id=str(payload.get("cycle_id") or ""),
            sync_enabled=True,
            sync_confirmation_ok=True,
        )

    state_after = _read_json(base / PAPER_STATE_NAME)
    status_after = _read_json(base / PAPER_STATUS_NAME)
    metrics_after = _state_metrics(state_after, status_after)
    safety_violation = unsafe or (1 if submitted else 0) > 1 or metrics_after["open_positions"] > 1 or metrics_after["paper_status_open_positions"] > 1

    if safety_violation:
        decision = REJECT_DECISION
        status_text = "FAIL"
    elif submitted and opened:
        decision = EXECUTED_DECISION
        status_text = "PASS"
    elif not settings.execute_armed:
        decision = NOT_ARMED_DECISION
        status_text = "WARN"
    elif not settings.execute_confirmation_ok:
        decision = CONFIRMATION_MISSING_DECISION
        status_text = "WARN"
    elif not max_orders_ok:
        decision = MAX_ORDER_CAP_DECISION
        status_text = "WARN"
    elif not state_clean:
        decision = STATE_BLOCKED_DECISION
        status_text = "WARN"
    elif "paper_submitter_not_available" in blockers:
        decision = SUBMITTER_NOT_AVAILABLE_DECISION
        status_text = "WARN"
    elif not gate_ok or not readiness_ok or not final_ok or not pnl_ok or payload_blockers:
        decision = PREREQ_BLOCKED_DECISION
        status_text = "WARN"
    else:
        decision = CONFIRMATION_MISSING_DECISION if not arm_ok else PREREQ_BLOCKED_DECISION
        status_text = "WARN"

    event = {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "cycle_id": payload.get("cycle_id"),
        "candidate_id": payload.get("candidate_id"),
        "symbol": payload.get("symbol"),
        "side": payload.get("side"),
        "entry_price": payload.get("entry_price"),
        "stop_loss": payload.get("stop_loss"),
        "take_profit": payload.get("take_profit"),
        "quantity": payload.get("quantity"),
        "risk_amount": payload.get("risk_amount"),
        "notional": payload.get("notional"),
        "order_id": order_id,
        "position_id": position_id,
        "submitter_called": bool(submitter_called),
        "orders_submitted_by_second_paper_execution": 1 if submitted else 0,
        "positions_opened_by_second_paper_execution": 1 if opened else 0,
        "positions_closed_by_second_paper_execution": 0,
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "broker_submit_real_called": False,
    }
    _append_jsonl(base / settings.jsonl_name, event)

    report = {
        "prompt_id": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status_text,
        "decision": decision,
        "blockers": sorted(set(blockers)),
        "cycle_id": str(payload.get("cycle_id") or ""),
        "candidate_id": str(payload.get("candidate_id") or ""),
        "candidate": dict(candidate),
        "payload": payload,
        "operator_controls": {
            "arm_env": ARM_ENV,
            "confirmation_env": CONFIRMATION_ENV,
            "execute_env": EXECUTE_ENV,
            "execute_confirmation_env": EXECUTE_CONFIRMATION_ENV,
            "max_orders_env": MAX_ORDERS_ENV,
            "arm": bool(settings.arm_ok),
            "confirmation_ok": bool(settings.confirmation_ok),
            "execute_armed": bool(settings.execute_armed),
            "execute_confirmation_ok": bool(settings.execute_confirmation_ok),
            "max_orders": int(settings.max_orders),
        },
        "prerequisites": {
            "second_order_gate_ok": bool(gate_ok),
            "multi_order_session_ready": bool(readiness_ok),
            "final_runtime_audit_ok": bool(final_ok),
            "pnl_reconciliation_ok": bool(pnl_ok),
            "paper_state_clean": bool(state_clean),
            "max_orders_ok": bool(max_orders_ok),
            "candidate_payload_valid": not payload_blockers,
        },
        "state_before": metrics_before,
        "state_after": metrics_after,
        "paper_status_sync": {
            "enabled": bool(sync_status_after_submit and submitted and opened),
            "status": status_sync_report.get("status"),
            "decision": status_sync_report.get("decision"),
            "paper_status_modified": status_sync_report.get("paper_status_modified"),
            "sync_required_after": status_sync_report.get("sync_required_after"),
            "report": status_sync_report.get("report"),
        },
        "paper_broker_adapter": settings.paper_broker_adapter_name,
        "submitter_error": submitter_error,
        "broker_submit_called": bool(submitter_called),
        "orders_submitted_by_second_paper_execution": 1 if submitted else 0,
        "positions_opened_by_second_paper_execution": 1 if opened else 0,
        "positions_closed_by_second_paper_execution": 0,
        "paper_state_modified_by_second_paper_execution": bool(submitted),
        "paper_status_modified_by_second_paper_execution": bool(status_sync_report.get("paper_status_modified", False)),
        "automatic_close_enabled": False,
        "automatic_reentry_enabled": False,
        "routing_enabled": False,
        "execution_enabled": bool(submitted),
        "live_enabled": False,
        "testnet_enabled": False,
        "exchange_broker_enabled": False,
        "operational_unlock_allowed": False,
        "safety_checks": {
            "mode_paper": settings.mode == "paper",
            "single_order_gate": settings.max_orders == 1,
            "orders_submitted_lte_one": (1 if submitted else 0) <= 1,
            "positions_opened_lte_one": (1 if opened else 0) <= 1,
            "no_close_by_execution": True,
            "no_automatic_reentry": True,
            "live_disabled": True,
            "testnet_disabled": True,
            "exchange_broker_disabled": True,
            "real_broker_not_called": True,
        },
        "safety_ok": not safety_violation,
        "promotion_ready": False,
        "report": str(base / settings.report_name),
        "jsonl": str(base / settings.jsonl_name),
    }
    _write_json(base / settings.report_name, report)
    return _read_json(base / settings.report_name)


__all__ = [
    "REPORT_NAME",
    "JSONL_NAME",
    "EXECUTED_DECISION",
    "NOT_ARMED_DECISION",
    "CONFIRMATION_MISSING_DECISION",
    "PREREQ_BLOCKED_DECISION",
    "STATE_BLOCKED_DECISION",
    "SUBMITTER_NOT_AVAILABLE_DECISION",
    "MAX_ORDER_CAP_DECISION",
    "REJECT_DECISION",
    "ARM_ENV",
    "CONFIRMATION_ENV",
    "CONFIRMATION_PHRASE",
    "EXECUTE_ENV",
    "EXECUTE_CONFIRMATION_ENV",
    "EXECUTE_CONFIRMATION_PHRASE",
    "MAX_ORDERS_ENV",
    "LSRV2SecondPaperOrderSubmitExecutionSettings",
    "build_lsr_v2_second_paper_order_submit_execution_report_from_files",
]
