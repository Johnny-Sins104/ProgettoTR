from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .models import Signal


def _f(row: pd.Series, key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
        if value == value:
            return value
    except Exception:
        pass
    return default


def _rr_levels(entry: float, stop: float, side: str, rr: float = 2.0) -> tuple[float, float]:
    risk = abs(entry - stop)
    if risk <= 0:
        return stop, entry
    if side == "BUY":
        return stop, entry + risk * rr
    return stop, entry - risk * rr


class Strategy(ABC):
    name: str

    @abstractmethod
    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        raise NotImplementedError


@dataclass(frozen=True)
class AdaptiveTrendBreakoutStrategy(Strategy):
    """Spot-first trend breakout with wide ATR risk and trailing exit."""

    lookback_bars: int = 576
    volume_min: float = 1.5
    stop_atr_mult: float = 4.0
    trail_atr_mult: float = 10.0
    max_hold_bars: int = 1728
    min_atr_pct: float = 0.03
    max_atr_pct: float = 1.50
    name: str = "adaptive_trend_breakout"

    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        row = df.iloc[idx]
        close = _f(row, "Close")
        ema50 = _f(row, "ema50")
        ema200 = _f(row, "ema200")
        atr = _f(row, "atr14")
        atr_pct = _f(row, "atr_pct")
        vol_ratio = _f(row, "volume_ratio_20")
        prior_high = _f(row, f"prior_high_{self.lookback_bars}")
        if min(close, ema50, ema200, atr, prior_high) <= 0:
            return None
        if not (self.min_atr_pct <= atr_pct <= self.max_atr_pct):
            return None
        if not (close > prior_high and close > ema50 > ema200 and vol_ratio >= self.volume_min):
            return None
        stop = close - atr * self.stop_atr_mult
        stop, tp = _rr_levels(close, stop, "BUY", 99.0)
        return Signal(
            self.name,
            "BUY",
            82.0,
            "long-only trend breakout with ATR trailing exit",
            stop,
            tp,
            {
                "exit_style": "atr_trailing",
                "lookback_bars": self.lookback_bars,
                "volume_min": self.volume_min,
                "stop_atr_mult": self.stop_atr_mult,
                "trail_atr_mult": self.trail_atr_mult,
                "max_hold_bars": self.max_hold_bars,
                "atr_pct": atr_pct,
                "volume_ratio_20": vol_ratio,
            },
        )


class TrendPullbackStrategy(Strategy):
    name = "trend_pullback"

    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        row = df.iloc[idx]
        close = _f(row, "Close")
        low = _f(row, "Low")
        high = _f(row, "High")
        ema50 = _f(row, "ema50")
        ema200 = _f(row, "ema200")
        atr = _f(row, "atr14")
        rsi = _f(row, "rsi14", 50.0)
        if min(close, ema50, ema200, atr) <= 0:
            return None
        if close > ema200 and ema50 > ema200 and low <= ema50 * 1.002 and close > ema50 and 42 <= rsi <= 62:
            stop = close - atr * 1.35
            stop, tp = _rr_levels(close, stop, "BUY", 2.0)
            return Signal(self.name, "BUY", 70.0, "uptrend pullback reclaimed ema50", stop, tp, {"rsi14": rsi})
        if close < ema200 and ema50 < ema200 and high >= ema50 * 0.998 and close < ema50 and 38 <= rsi <= 58:
            stop = close + atr * 1.35
            stop, tp = _rr_levels(close, stop, "SELL", 2.0)
            return Signal(self.name, "SELL", 70.0, "downtrend pullback rejected ema50", stop, tp, {"rsi14": rsi})
        return None


class SupportRejectionStrategy(Strategy):
    name = "support_rejection"

    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        row = df.iloc[idx]
        close = _f(row, "Close")
        open_ = _f(row, "Open")
        low = _f(row, "Low")
        atr = _f(row, "atr14")
        range_pos = _f(row, "range_pos_400", 0.5)
        lower_wick = _f(row, "lower_wick_ratio")
        body_ratio = _f(row, "body_ratio")
        vol_ratio = _f(row, "volume_ratio_20")
        support = _f(row, "range_low_96")
        if min(close, low, atr, support) <= 0:
            return None
        near_support_pct = abs(close - support) / close * 100.0
        bullish_reclaim = close > open_ and lower_wick >= 0.35 and body_ratio >= 0.20
        if range_pos <= 0.16 and near_support_pct <= 0.45 and bullish_reclaim and vol_ratio >= 0.65:
            stop = min(low, support) - atr * 0.25
            stop, tp = _rr_levels(close, stop, "BUY", 1.8)
            return Signal(
                self.name,
                "BUY",
                75.0,
                "support rejection with lower wick and volume",
                stop,
                tp,
                {"range_pos_400": range_pos, "near_support_pct": near_support_pct, "volume_ratio_20": vol_ratio},
            )
        return None


class BreakoutMomentumStrategy(Strategy):
    name = "breakout_momentum"

    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        row = df.iloc[idx]
        close = _f(row, "Close")
        high = _f(row, "High")
        low = _f(row, "Low")
        atr = _f(row, "atr14")
        ema20 = _f(row, "ema20")
        ema50 = _f(row, "ema50")
        prior_high = _f(row, "prior_high_48")
        prior_low = _f(row, "prior_low_48")
        vol_ratio = _f(row, "volume_ratio_20")
        if min(close, atr, ema20, ema50, prior_high, prior_low) <= 0:
            return None
        closes_near_high = (high - close) <= atr * 0.20
        closes_near_low = (close - low) <= atr * 0.20
        if close > prior_high and close > ema20 > ema50 and vol_ratio >= 1.35 and closes_near_high:
            stop = close - atr * 1.15
            stop, tp = _rr_levels(close, stop, "BUY", 1.7)
            return Signal(self.name, "BUY", 72.0, "volume breakout above 48-bar high", stop, tp, {"volume_ratio_20": vol_ratio})
        if close < prior_low and close < ema20 < ema50 and vol_ratio >= 1.35 and closes_near_low:
            stop = close + atr * 1.15
            stop, tp = _rr_levels(close, stop, "SELL", 1.7)
            return Signal(self.name, "SELL", 72.0, "volume breakdown below 48-bar low", stop, tp, {"volume_ratio_20": vol_ratio})
        return None


def strategy_profile(name: str = "conservative") -> list[Strategy]:
    profile = str(name or "conservative").strip().lower()
    if profile == "conservative":
        return [AdaptiveTrendBreakoutStrategy()]
    if profile == "active":
        return [
            AdaptiveTrendBreakoutStrategy(
                lookback_bars=288,
                volume_min=1.2,
                stop_atr_mult=4.0,
                trail_atr_mult=10.0,
                max_hold_bars=576,
            )
        ]
    if profile == "aggressive":
        return [
            AdaptiveTrendBreakoutStrategy(
                lookback_bars=288,
                volume_min=1.2,
                stop_atr_mult=3.0,
                trail_atr_mult=10.0,
                max_hold_bars=576,
            )
        ]
    raise ValueError(f"unknown clean strategy profile: {name}")


def default_strategies() -> list[Strategy]:
    return strategy_profile("conservative")


def research_strategies() -> list[Strategy]:
    return [AdaptiveTrendBreakoutStrategy(), SupportRejectionStrategy(), TrendPullbackStrategy(), BreakoutMomentumStrategy()]

def strategy_by_name(name: str) -> Strategy:
    for strategy in research_strategies():
        if strategy.name == name:
            return strategy
    raise ValueError(f"unknown clean strategy: {name}")
