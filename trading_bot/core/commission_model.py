"""Shared commission helpers for paper/live/backtest calculations."""
from __future__ import annotations


def notional_fee(size: float, price: float, rate: float) -> float:
    """Return one-side fee on absolute notional."""
    return abs(float(size)) * abs(float(price)) * float(rate)


def round_trip_commission(size: float, entry_price: float, exit_price: float, rate: float) -> float:
    """Return entry plus exit commission for a closed position."""
    return notional_fee(size, entry_price, rate) + notional_fee(size, exit_price, rate)
