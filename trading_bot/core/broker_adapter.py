"""Prompt 29.4 broker adapter abstractions for ProgettoTR.

This module defines the execution boundary used by the paper engine today and
by future testnet/live execution later.  It deliberately keeps real-money live
execution blocked: ``ExchangeBrokerAdapter`` is a design skeleton until Prompt
30.x adds sandbox/testnet support and risk governance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable
import json

Side = Literal["BUY", "SELL"]
OrderStatus = Literal["PENDING", "FILLED", "CANCELED", "REJECTED", "UNKNOWN"]
PositionStatus = Literal["OPEN", "CLOSED", "UNKNOWN"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AccountSnapshot:
    mode: str
    balance: float
    equity: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    drawdown_pct: float = 0.0
    open_positions: int = 0
    pending_orders: int = 0
    kill_switch: bool = False
    is_paused: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PositionSnapshot:
    position_id: str
    symbol: str
    side: Side | str
    qty: float
    entry_price: float
    mark_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    status: PositionStatus | str = "OPEN"
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    notional: float = 0.0
    margin_estimate: float = 0.0
    opened_at: str = ""
    reason: str = ""
    score: float | None = None
    regime: str = ""
    archetype: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: str
    symbol: str
    side: Side | str
    qty: float
    status: OrderStatus | str
    order_type: str = ""
    requested_price: float = 0.0
    filled_price: float | None = None
    reason: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionSnapshot:
    mode: str
    account: AccountSnapshot
    positions: list[PositionSnapshot]
    open_orders: list[OrderSnapshot]
    reconciled_at: str = field(default_factory=utc_now_iso)
    reconciliation_status: str = "PASS"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LiveExecutionBlocked(RuntimeError):
    """Raised when code tries to use real-money live execution before unlock."""


@runtime_checkable
class BrokerAdapter(Protocol):
    """Common execution interface for paper, testnet and future live brokers."""

    mode: str

    def get_balance(self) -> AccountSnapshot:
        ...

    def get_positions(self) -> list[PositionSnapshot]:
        ...

    def place_order(
        self,
        *,
        symbol: str,
        side: Side,
        qty: float,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OrderSnapshot:
        ...

    def cancel_order(self, order_id: str) -> OrderSnapshot:
        ...

    def close_position(self, position_id: str, *, price: float, reason: str = "MANUAL") -> PositionSnapshot:
        ...

    def fetch_open_orders(self) -> list[OrderSnapshot]:
        ...

    def reconcile(self) -> ExecutionSnapshot:
        ...


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _metadata_reason(metadata: dict[str, Any]) -> str:
    parts: list[str] = []
    score = metadata.get("score")
    if score is not None:
        parts.append(f"Score {score}")
    regime = metadata.get("regime") or metadata.get("market_regime")
    if regime:
        parts.append(str(regime).upper())
    archetype = metadata.get("setup_archetype") or metadata.get("archetype") or metadata.get("combination")
    if archetype:
        parts.append(str(archetype))
    return " | ".join(parts)


class PaperBrokerAdapter:
    """Adapter that exposes ``PaperBroker`` through the common broker interface."""

    mode = "paper"

    def __init__(self, broker: Any, *, last_prices: dict[str, float] | None = None, leverage_for_display: float = 1.0) -> None:
        self.broker = broker
        self.last_prices = last_prices if last_prices is not None else {}
        self.leverage_for_display = max(1.0, float(leverage_for_display or 1.0))

    def get_balance(self) -> AccountSnapshot:
        raw = self.broker.snapshot(self.last_prices)
        return AccountSnapshot(
            mode="paper",
            balance=_safe_float(raw.get("balance")),
            equity=_safe_float(raw.get("equity")),
            realized_pnl=_safe_float(raw.get("realized_pnl")),
            unrealized_pnl=_safe_float(raw.get("unrealized_pnl")),
            drawdown_pct=_safe_float(raw.get("drawdown_pct")),
            open_positions=int(raw.get("open_positions") or 0),
            pending_orders=int(raw.get("pending_orders") or 0),
            kill_switch=bool(raw.get("kill_switch")),
            is_paused=bool(raw.get("is_paused")),
            raw=raw,
        )

    def get_positions(self) -> list[PositionSnapshot]:
        out: list[PositionSnapshot] = []
        for p in getattr(self.broker, "open_positions", []):
            metadata = dict(getattr(p, "metadata", {}) or {})
            mark = _safe_float(self.last_prices.get(p.symbol), _safe_float(getattr(p, "entry_price", 0.0)))
            qty = _safe_float(getattr(p, "qty", 0.0))
            entry = _safe_float(getattr(p, "entry_price", 0.0))
            side = str(getattr(p, "side", ""))
            if side == "BUY":
                pnl = qty * (mark - entry)
            else:
                pnl = qty * (entry - mark)
            notional = abs(qty * mark)
            base = abs(qty * entry) or 1.0
            pnl_pct = pnl / base * 100.0
            tp = _safe_float(getattr(p, "take_profit", 0.0)) or None
            # TP1 is a display-only midpoint between entry and final TP.  The
            # paper broker still executes against the original single TP until
            # staged exits are introduced in a later execution prompt.
            tp1 = None
            if tp is not None and entry > 0:
                tp1 = entry + (tp - entry) * 0.5
            out.append(
                PositionSnapshot(
                    position_id=str(getattr(p, "position_id", "")),
                    symbol=str(getattr(p, "symbol", "")),
                    side=side,
                    qty=qty,
                    entry_price=entry,
                    mark_price=mark,
                    stop_loss=_safe_float(getattr(p, "stop_loss", 0.0)) or None,
                    take_profit=tp,
                    take_profit_1=tp1,
                    take_profit_2=tp,
                    status=str(getattr(p, "status", "OPEN")),
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=pnl_pct,
                    notional=notional,
                    margin_estimate=notional / self.leverage_for_display,
                    opened_at=str(getattr(p, "opened_at", "")),
                    reason=_metadata_reason(metadata),
                    score=_safe_float(metadata.get("score"), 0.0) if metadata.get("score") is not None else None,
                    regime=str(metadata.get("regime") or metadata.get("market_regime") or ""),
                    archetype=str(metadata.get("setup_archetype") or metadata.get("archetype") or metadata.get("combination") or ""),
                    metadata=metadata,
                )
            )
        return out

    def place_order(
        self,
        *,
        symbol: str,
        side: Side,
        qty: float,
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OrderSnapshot:
        if price is None or stop_loss is None or take_profit is None:
            raise ValueError("PaperBrokerAdapter.place_order requires price, stop_loss and take_profit.")
        order = self.broker.place_market_order(
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata=metadata or {},
        )
        return self._order_snapshot(order)

    def cancel_order(self, order_id: str) -> OrderSnapshot:
        order = self.broker.orders.get(order_id)
        if order is None:
            raise KeyError(f"Unknown paper order: {order_id}")
        if order.status == "PENDING":
            order.status = "CANCELED"
            order.updated_at = utc_now_iso()
            order.reason = order.reason or "adapter_cancel"
            self.broker.emit("PAPER_ORDER_CANCELLED", order_id=order.order_id, symbol=order.symbol, side=order.side)
            self.broker.save()
        return self._order_snapshot(order)

    def close_position(self, position_id: str, *, price: float, reason: str = "MANUAL") -> PositionSnapshot:
        position = self.broker.close_position(position_id, exit_price=price, reason=reason)
        metadata = dict(getattr(position, "metadata", {}) or {})
        return PositionSnapshot(
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            qty=float(position.qty),
            entry_price=float(position.entry_price),
            mark_price=float(price),
            stop_loss=float(position.stop_loss),
            take_profit=float(position.take_profit),
            take_profit_1=float(position.entry_price) + (float(position.take_profit) - float(position.entry_price)) * 0.5,
            take_profit_2=float(position.take_profit),
            status=position.status,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            notional=abs(float(position.qty) * float(price)),
            margin_estimate=abs(float(position.qty) * float(price)) / self.leverage_for_display,
            opened_at=position.opened_at,
            reason=_metadata_reason(metadata),
            score=_safe_float(metadata.get("score"), 0.0) if metadata.get("score") is not None else None,
            regime=str(metadata.get("regime") or metadata.get("market_regime") or ""),
            archetype=str(metadata.get("setup_archetype") or metadata.get("archetype") or metadata.get("combination") or ""),
            metadata=metadata,
        )

    def fetch_open_orders(self) -> list[OrderSnapshot]:
        return [self._order_snapshot(order) for order in getattr(self.broker, "pending_orders", [])]

    def reconcile(self) -> ExecutionSnapshot:
        warnings: list[str] = []
        errors: list[str] = []
        account = self.get_balance()
        positions = self.get_positions()
        open_orders = self.fetch_open_orders()
        if account.open_positions != len(positions):
            warnings.append(f"open_position_count_mismatch: account={account.open_positions} adapter={len(positions)}")
        status = "PASS" if not errors and not warnings else ("FAIL" if errors else "WARN")
        return ExecutionSnapshot(mode="paper", account=account, positions=positions, open_orders=open_orders, reconciliation_status=status, warnings=warnings, errors=errors)

    def _order_snapshot(self, order: Any) -> OrderSnapshot:
        return OrderSnapshot(
            order_id=str(getattr(order, "order_id", "")),
            symbol=str(getattr(order, "symbol", "")),
            side=str(getattr(order, "side", "")),
            qty=_safe_float(getattr(order, "qty", 0.0)),
            status=str(getattr(order, "status", "UNKNOWN")),
            order_type=str(getattr(order, "order_type", "")),
            requested_price=_safe_float(getattr(order, "requested_price", 0.0)),
            filled_price=(None if getattr(order, "filled_price", None) is None else _safe_float(getattr(order, "filled_price"))),
            reason=str(getattr(order, "reason", "")),
            created_at=str(getattr(order, "created_at", "")),
            updated_at=str(getattr(order, "updated_at", "")),
            metadata=dict(getattr(order, "metadata", {}) or {}),
        )


class ExchangeBrokerAdapter:
    """Future exchange/testnet adapter skeleton.

    Prompt 29.4 is architecture-only.  Real-money live methods intentionally
    raise ``LiveExecutionBlocked``.  Prompt 30.0 may extend this class for
    sandbox/testnet operations without changing the paper engine interface.
    """

    def __init__(self, *, mode: str = "blocked", config: dict[str, Any] | None = None) -> None:
        self.mode = mode
        self.config = config or {}
        self.created_at = utc_now_iso()

    def _blocked(self) -> None:
        raise LiveExecutionBlocked(
            "ExchangeBrokerAdapter is a Prompt 29.4 skeleton. Real live execution remains blocked until 30.x readiness gates."
        )

    def get_balance(self) -> AccountSnapshot:
        self._blocked()

    def get_positions(self) -> list[PositionSnapshot]:
        self._blocked()

    def place_order(self, **_: Any) -> OrderSnapshot:
        self._blocked()

    def cancel_order(self, order_id: str) -> OrderSnapshot:
        self._blocked()

    def close_position(self, position_id: str, *, price: float, reason: str = "MANUAL") -> PositionSnapshot:
        self._blocked()

    def fetch_open_orders(self) -> list[OrderSnapshot]:
        self._blocked()

    def reconcile(self) -> ExecutionSnapshot:
        self._blocked()

    def write_design_stub(self, path: str | Path = "data/exchange_broker_adapter_stub.json") -> None:
        payload = {
            "generated_at": utc_now_iso(),
            "mode": self.mode,
            "status": "BLOCKED_DESIGN_STUB",
            "live_execution_enabled": False,
            "next_prompt": "30.0 Live execution sandbox / testnet",
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def execution_snapshot_to_dict(snapshot: ExecutionSnapshot) -> dict[str, Any]:
    return asdict(snapshot)
