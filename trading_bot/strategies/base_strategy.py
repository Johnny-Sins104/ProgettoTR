from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from trading_bot.strategy_runtime.strategy_signal_schema import wait_signal


def column(df: pd.DataFrame, name: str) -> pd.Series:
    candidates = (name, name.lower(), name.upper(), name.capitalize())
    for candidate in candidates:
        if candidate in df.columns:
            return pd.to_numeric(df[candidate], errors="coerce")
    raise KeyError(f"missing_column:{name}")


def f(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if out == out else default
    except Exception:
        return default


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = column(df, "High")
    low = column(df, "Low")
    close = column(df, "Close")
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    close = column(df, "Close")
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def real_vwap(df: pd.DataFrame) -> pd.Series:
    high = column(df, "High")
    low = column(df, "Low")
    close = column(df, "Close")
    volume = column(df, "Volume")
    typical = (high + low + close) / 3.0
    cumulative_volume = volume.cumsum().replace(0, pd.NA)
    return (typical * volume).cumsum() / cumulative_volume


@dataclass(frozen=True)
class StrategyParams:
    values: dict[str, Any] = field(default_factory=dict)

    def get_float(self, key: str, default: float) -> float:
        return f(self.values.get(key, default), default)

    def get_int(self, key: str, default: int) -> int:
        try:
            return int(self.values.get(key, default))
        except Exception:
            return default


class BaseStrategy(ABC):
    strategy_id: str
    display_name: str

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = StrategyParams(params or {})

    @abstractmethod
    def evaluate(self, df: pd.DataFrame, *, asset: str = "", timeframe: str = "") -> dict[str, Any]:
        raise NotImplementedError

    def _wait(self, reason: str):
        return wait_signal(self.strategy_id, reason)


def risk_levels(entry: float, atr_value: float, side: str, sl_mult: float = 1.2, tp_mult: float = 1.8) -> tuple[float, float]:
    risk = max(abs(atr_value) * sl_mult, abs(entry) * 0.002)
    if side == "BUY":
        return entry - risk, entry + risk * tp_mult
    return entry + risk, entry - risk * tp_mult
