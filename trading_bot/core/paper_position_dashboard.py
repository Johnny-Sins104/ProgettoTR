"""Telegram single-message paper position dashboard utilities.

Patch 30.3.0J keeps paper position monitoring paper-only and notification-only:
it formats a fixed TP/SL dashboard with a moving marker, but it never places,
closes, routes, or mutates paper trading state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:  # package import
    from .broker_adapter import AccountSnapshot, PositionSnapshot
except Exception:  # pragma: no cover - script-style fallback
    from broker_adapter import AccountSnapshot, PositionSnapshot  # type: ignore


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def _fmt_qty(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _fmt_money(value: float) -> str:
    return f"{float(value):+.2f}"


def utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def progress_to_take_profit(*, side: str, current: float, stop_loss: float | None, take_profit: float | None) -> float:
    """Return 0..1 progress from SL boundary to TP boundary.

    The rendered bar always places SL on the left and TP on the right.  For BUY,
    price rising moves the marker right.  For SELL, price falling moves it right.
    """
    if stop_loss is None or take_profit is None:
        return 0.5
    sl = _safe_float(stop_loss)
    tp = _safe_float(take_profit)
    cur = _safe_float(current)
    if sl == tp:
        return 0.5
    if str(side).upper() == "SELL":
        denom = sl - tp
        if denom == 0:
            return 0.5
        raw = (sl - cur) / denom
    else:
        denom = tp - sl
        if denom == 0:
            return 0.5
        raw = (cur - sl) / denom
    return max(0.0, min(1.0, float(raw)))


def progress_bar(*, side: str, current: float, stop_loss: float | None, take_profit: float | None, width: int = 20) -> tuple[str, float, str]:
    width = max(5, min(60, int(width or 20)))
    progress = progress_to_take_profit(side=side, current=current, stop_loss=stop_loss, take_profit=take_profit)
    marker_idx = max(0, min(width - 1, int(round(progress * (width - 1)))))
    cells = ["="] * width
    cells[marker_idx] = "●"
    if progress >= 1.0:
        state = "TP_HIT_OR_BEYOND"
    elif progress <= 0.0:
        state = "SL_HIT_OR_BEYOND"
    elif progress >= 0.80:
        state = "NEAR_TAKE_PROFIT"
    elif progress <= 0.20:
        state = "NEAR_STOP_LOSS"
    else:
        state = "IN_RANGE"
    return f"SL {_fmt_price(stop_loss)}  [{''.join(cells)}]  TP {_fmt_price(take_profit)}", progress, state


def _position_value(position: Any, name: str, default: Any = None) -> Any:
    if isinstance(position, dict):
        return position.get(name, default)
    return getattr(position, name, default)


def format_live_position_dashboard(
    *,
    account: AccountSnapshot | Any,
    position: PositionSnapshot | Any,
    width: int = 20,
    now_label: str | None = None,
    status: str = "OPEN",
) -> str:
    side = str(_position_value(position, "side", "")).upper() or "-"
    direction = "BUY/LONG" if side == "BUY" else "SELL/SHORT" if side == "SELL" else side
    symbol = str(_position_value(position, "symbol", "-"))
    entry = _safe_float(_position_value(position, "entry_price", 0.0))
    mark = _safe_float(_position_value(position, "mark_price", _position_value(position, "exit_price", entry)))
    qty = _safe_float(_position_value(position, "qty", 0.0))
    stop_loss_raw = _position_value(position, "stop_loss", None)
    take_profit_raw = _position_value(position, "take_profit", None)
    stop_loss = None if stop_loss_raw is None else _safe_float(stop_loss_raw)
    take_profit = None if take_profit_raw is None else _safe_float(take_profit_raw)
    pnl = _safe_float(_position_value(position, "unrealized_pnl", _position_value(position, "realized_pnl", 0.0)))
    pnl_pct = _safe_float(_position_value(position, "unrealized_pnl_pct", 0.0))
    equity = _safe_float(getattr(account, "equity", 0.0) if not isinstance(account, dict) else account.get("equity", 0.0))
    reason = str(_position_value(position, "reason", "") or "-")
    bar, progress, state = progress_bar(side=side, current=mark, stop_loss=stop_loss, take_profit=take_profit, width=width)
    distance_tp = abs(mark - take_profit) if take_profit is not None else 0.0
    distance_sl = abs(stop_loss - mark) if stop_loss is not None else 0.0
    label = now_label or utc_now_label()
    text = (
        "📈 PAPER LIVE POSITION\n\n"
        f"{symbol} {direction}\n"
        f"Entry: {_fmt_price(entry)}\n"
        f"Now:   {_fmt_price(mark)}\n\n"
        f"{bar}\n\n"
        f"Distance TP: {_fmt_price(distance_tp)}\n"
        f"Distance SL: {_fmt_price(distance_sl)}\n"
        f"Progress: {progress * 100:.1f}% ({state})\n"
        f"Qty: {_fmt_qty(qty)}\n"
        f"PnL: {_fmt_money(pnl)} USDT ({pnl_pct:+.2f}%)\n"
        f"Equity: {equity:.2f} USDT\n"
        f"Reason: {reason}\n"
        f"Status: {status}\n"
        f"Last update: {label}"
    )
    return text[:3900]


def format_closed_position_dashboard(
    *,
    account: AccountSnapshot | Any,
    position: Any,
    width: int = 20,
    now_label: str | None = None,
) -> str:
    side = str(_position_value(position, "side", "")).upper() or "-"
    symbol = str(_position_value(position, "symbol", "-"))
    entry = _safe_float(_position_value(position, "entry_price", 0.0))
    exit_price = _safe_float(_position_value(position, "exit_price", _position_value(position, "mark_price", entry)))
    stop_loss_raw = _position_value(position, "stop_loss", None)
    take_profit_raw = _position_value(position, "take_profit", None)
    stop_loss = None if stop_loss_raw is None else _safe_float(stop_loss_raw)
    take_profit = None if take_profit_raw is None else _safe_float(take_profit_raw)
    realized = _safe_float(_position_value(position, "realized_pnl", 0.0))
    reason = str(_position_value(position, "close_reason", "CLOSED") or "CLOSED").upper()
    equity = _safe_float(getattr(account, "equity", 0.0) if not isinstance(account, dict) else account.get("equity", 0.0))
    bar, progress, state = progress_bar(side=side, current=exit_price, stop_loss=stop_loss, take_profit=take_profit, width=width)
    label = now_label or utc_now_label()
    text = (
        "⚪ PAPER POSITION CLOSED\n\n"
        f"{symbol} {side}\n"
        f"Entry: {_fmt_price(entry)}\n"
        f"Exit:  {_fmt_price(exit_price)}\n\n"
        f"{bar}\n\n"
        f"Close reason: {reason}\n"
        f"Progress: {progress * 100:.1f}% ({state})\n"
        f"Realized PnL: {_fmt_money(realized)} USDT\n"
        f"Equity: {equity:.2f} USDT\n"
        "Status: CLOSED\n"
        f"Last update: {label}"
    )
    return text[:3900]
