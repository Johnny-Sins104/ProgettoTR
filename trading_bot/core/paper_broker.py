"""Prompt 29 — deterministic paper broker for ProgettoTR.

The broker is deliberately exchange-free: it simulates market/pending orders,
position state, execution fees and realized PnL locally.  It is suitable for
paper trading and operator drills, not for real-money execution.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
import json
import uuid

Side = Literal["BUY", "SELL"]
OrderStatus = Literal["PENDING", "FILLED", "CANCELED", "REJECTED"]
PositionStatus = Literal["OPEN", "CLOSED"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PaperOrder:
    order_id: str
    symbol: str
    side: Side
    qty: float
    order_type: str
    requested_price: float
    status: OrderStatus = "PENDING"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    filled_price: float | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperPosition:
    position_id: str
    symbol: str
    side: Side
    qty: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: str
    status: PositionStatus = "OPEN"
    closed_at: str | None = None
    exit_price: float | None = None
    close_reason: str = ""
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class PaperBroker:
    def __init__(
        self,
        *,
        initial_balance: float = 1000.0,
        fee_rate: float = 0.0004,
        state_path: str | Path = "data/paper_state.json",
        events_path: str | Path = "data/paper_events.jsonl",
    ) -> None:
        self.initial_balance = float(initial_balance)
        self.balance = float(initial_balance)
        self.fee_rate = float(fee_rate)
        self.state_path = Path(state_path)
        self.events_path = Path(events_path)
        self.orders: dict[str, PaperOrder] = {}
        self.positions: dict[str, PaperPosition] = {}
        self.realized_pnl = 0.0
        self.peak_balance = self.balance
        self.is_paused = False
        self.kill_switch = False
        self.ensure_event_log()
        self.state_loaded = False
        self.state_load_error: str | None = None
        self.restored_at: str | None = None
        self.load()

    def load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.balance = float(data.get("balance", self.initial_balance))
            self.realized_pnl = float(data.get("realized_pnl", 0.0))
            self.peak_balance = float(data.get("peak_balance", self.balance))
            self.is_paused = bool(data.get("is_paused", False))
            self.kill_switch = bool(data.get("kill_switch", False))
            self.orders = {k: PaperOrder(**v) for k, v in data.get("orders", {}).items()}
            self.positions = {k: PaperPosition(**v) for k, v in data.get("positions", {}).items()}
            self.state_loaded = True
            self.restored_at = utc_now_iso()
        except Exception as exc:
            # Corrupt paper state should not crash the launcher.  Keep a fresh state,
            # but expose the failure to the lifecycle report through an audit event.
            self.orders = {}
            self.positions = {}
            self.state_load_error = str(exc)
            self.emit("STATE_RESTORE_FAILED", error=str(exc))

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": utc_now_iso(),
            "initial_balance": self.initial_balance,
            "balance": self.balance,
            "realized_pnl": self.realized_pnl,
            "peak_balance": self.peak_balance,
            "drawdown_pct": self.drawdown_pct,
            "is_paused": self.is_paused,
            "kill_switch": self.kill_switch,
            "state_loaded": self.state_loaded,
            "restored_at": self.restored_at,
            "orders": {k: asdict(v) for k, v in self.orders.items()},
            "positions": {k: asdict(v) for k, v in self.positions.items()},
        }
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def ensure_event_log(self) -> None:
        """Create the paper event log even when a cycle produces no orders.

        Prompt 29.0.1 requires a persistent audit trail for engine startup,
        no-signal scans and completed cycles.  Touching the file here makes
        `type data\\paper_events.jsonl` safe immediately after a smoke test.
        """
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self.events_path.touch(exist_ok=True)

    def emit(self, event_type: str, **payload: Any) -> None:
        self.ensure_event_log()
        event = {"ts": utc_now_iso(), "event_type": event_type, **payload}
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")

    @property
    def open_positions(self) -> list[PaperPosition]:
        return [p for p in self.positions.values() if p.status == "OPEN"]

    @property
    def pending_orders(self) -> list[PaperOrder]:
        return [o for o in self.orders.values() if o.status == "PENDING"]

    @property
    def drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return max(0.0, (self.peak_balance - self.balance) / self.peak_balance * 100.0)

    def place_market_order(
        self,
        *,
        symbol: str,
        side: Side,
        qty: float,
        price: float,
        stop_loss: float,
        take_profit: float,
        metadata: dict[str, Any] | None = None,
    ) -> PaperOrder:
        order = PaperOrder(
            order_id="po_" + uuid.uuid4().hex[:16],
            symbol=symbol,
            side=side,
            qty=float(qty),
            order_type="MARKET",
            requested_price=float(price),
            status="FILLED",
            filled_price=float(price),
            metadata=metadata or {},
        )
        self.orders[order.order_id] = order
        cycle_id = str(order.metadata.get("cycle_id") or "")
        self.emit("PAPER_ORDER_SUBMITTED", order=asdict(order), order_id=order.order_id, symbol=order.symbol, side=order.side, cycle_id=cycle_id)
        self._open_position_from_order(order, stop_loss=stop_loss, take_profit=take_profit)
        self.emit("ORDER_FILLED", order=asdict(order), order_id=order.order_id, symbol=order.symbol, side=order.side, cycle_id=cycle_id)
        self.save()
        return order

    def _open_position_from_order(self, order: PaperOrder, *, stop_loss: float, take_profit: float) -> PaperPosition:
        entry = float(order.filled_price or order.requested_price)
        entry_fee = abs(order.qty * entry) * self.fee_rate
        self.balance -= entry_fee
        self.realized_pnl -= entry_fee
        position = PaperPosition(
            position_id="pp_" + uuid.uuid4().hex[:16],
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
            entry_price=entry,
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            opened_at=utc_now_iso(),
            fees_paid=entry_fee,
            metadata={**order.metadata, "source_order_id": order.order_id},
        )
        self.positions[position.position_id] = position
        self.emit("POSITION_OPENED", position=asdict(position), position_id=position.position_id, order_id=order.order_id, symbol=position.symbol, side=position.side, cycle_id=str(order.metadata.get("cycle_id") or ""))
        return position

    def mark_to_market(self, prices: dict[str, float]) -> dict[str, Any]:
        unrealized = 0.0
        positions = []
        for p in self.open_positions:
            price = float(prices.get(p.symbol, p.entry_price))
            pnl = self._gross_pnl(p, price)
            unrealized += pnl
            positions.append({"symbol": p.symbol, "side": p.side, "qty": p.qty, "entry": p.entry_price, "mark": price, "unrealized_pnl": pnl})
        equity = self.balance + unrealized
        self.peak_balance = max(self.peak_balance, equity)
        return {"balance": self.balance, "equity": equity, "unrealized_pnl": unrealized, "positions": positions, "drawdown_pct": self.drawdown_pct}

    def update_stops(self, symbol: str, high: float, low: float, last: float) -> list[PaperPosition]:
        closed: list[PaperPosition] = []
        for p in list(self.open_positions):
            if p.symbol != symbol:
                continue
            exit_price = None
            reason = ""
            if p.side == "BUY":
                if low <= p.stop_loss:
                    exit_price = p.stop_loss
                    reason = "SL"
                elif high >= p.take_profit:
                    exit_price = p.take_profit
                    reason = "TP"
            else:
                if high >= p.stop_loss:
                    exit_price = p.stop_loss
                    reason = "SL"
                elif low <= p.take_profit:
                    exit_price = p.take_profit
                    reason = "TP"
            if exit_price is not None:
                closed.append(self.close_position(p.position_id, exit_price=exit_price, reason=reason))
        self.save()
        return closed

    def close_position(self, position_id: str, *, exit_price: float, reason: str = "MANUAL") -> PaperPosition:
        p = self.positions[position_id]
        if p.status == "CLOSED":
            return p
        gross = self._gross_pnl(p, float(exit_price))
        exit_fee = abs(p.qty * float(exit_price)) * self.fee_rate
        net = gross - exit_fee
        p.status = "CLOSED"
        p.closed_at = utc_now_iso()
        p.exit_price = float(exit_price)
        p.close_reason = reason
        p.realized_pnl = net
        p.fees_paid += exit_fee
        self.balance += net
        self.realized_pnl += net
        self.peak_balance = max(self.peak_balance, self.balance)
        self.emit("POSITION_CLOSED", position=asdict(p), position_id=p.position_id, symbol=p.symbol, side=p.side, reason=reason)
        self.save()
        return p

    def close_all(self, prices: dict[str, float], reason: str = "KILL_SWITCH") -> list[PaperPosition]:
        closed = []
        for p in list(self.open_positions):
            closed.append(self.close_position(p.position_id, exit_price=float(prices.get(p.symbol, p.entry_price)), reason=reason))
        return closed

    def _gross_pnl(self, p: PaperPosition, price: float) -> float:
        if p.side == "BUY":
            return p.qty * (price - p.entry_price)
        return p.qty * (p.entry_price - price)

    def snapshot(self, prices: dict[str, float] | None = None) -> dict[str, Any]:
        mtm = self.mark_to_market(prices or {})
        return {
            "mode": "paper",
            "balance": self.balance,
            "equity": mtm["equity"],
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": mtm["unrealized_pnl"],
            "drawdown_pct": mtm["drawdown_pct"],
            "open_positions": len(self.open_positions),
            "pending_orders": len(self.pending_orders),
            "is_paused": self.is_paused,
            "kill_switch": self.kill_switch,
            "positions": mtm["positions"],
        }
