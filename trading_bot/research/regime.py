"""Causal market-regime labelling for cycle-2 research (declared a priori).

Rule (frozen BEFORE any cycle-2 test, counted as parameters of the
regime-conditioned family):

  Daily BTC closes are derived from closed 15m candles (UTC days; a day
  is used only once fully closed). For calendar day D the label uses
  ONLY data through day D-1's close:

    sma200 = 200-day simple moving average of daily closes
    bull : close[D-1] > sma200[D-1] and sma200[D-1] > sma200[D-21]
    bear : close[D-1] < sma200[D-1] and sma200[D-1] < sma200[D-21]
    chop : anything else
    unknown : fewer than 221 daily closes available

  Every 15m bar inherits the label of its calendar day. The label for
  day D is fully known at 00:00 UTC of day D — strictly causal at every
  15m signal bar inside D.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

REGIMES = ("bull", "bear", "chop")
SMA_DAYS = 200
SLOPE_DAYS = 20
MIN_DAYS = SMA_DAYS + SLOPE_DAYS + 1


def daily_regime_labels(df15_btc: pd.DataFrame) -> pd.Series:
    """Label per calendar day (index = day, value in REGIMES/'unknown')."""
    dt = pd.to_datetime(df15_btc["datetime"], utc=True)
    closes = pd.Series(df15_btc["Close"].to_numpy(float), index=dt)
    daily_close = closes.resample("1D").last().dropna()

    sma = daily_close.rolling(SMA_DAYS).mean()
    sma_prev = sma.shift(SLOPE_DAYS)

    lab = pd.Series("unknown", index=daily_close.index, dtype=object)
    valid = sma.notna() & sma_prev.notna()
    bull = valid & (daily_close > sma) & (sma > sma_prev)
    bear = valid & (daily_close < sma) & (sma < sma_prev)
    chop = valid & ~bull & ~bear
    lab[bull] = "bull"
    lab[bear] = "bear"
    lab[chop] = "chop"

    # label known the NEXT day (use day D-1 data for day D) — causal shift
    return lab.shift(1).fillna("unknown")


def regime_for_times(daily_labels: pd.Series, times: pd.Series) -> np.ndarray:
    """Regime label for arbitrary (tz-aware) timestamps."""
    days = pd.to_datetime(times, utc=True).dt.floor("D")
    mapping: Dict[pd.Timestamp, str] = daily_labels.to_dict()
    return np.array([mapping.get(d, "unknown") for d in days], dtype=object)


def regime_at(daily_labels: pd.Series, ts: pd.Timestamp) -> str:
    day = pd.Timestamp(ts).tz_convert("UTC").floor("D")
    return str(daily_labels.get(day, "unknown"))
