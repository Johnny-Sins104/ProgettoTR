"""Tests for the cycle-2 causal regime labelling."""
from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.research.regime import (
    MIN_DAYS,
    daily_regime_labels,
    regime_at,
    regime_for_times,
)


def _frame_from_daily(daily_closes: np.ndarray, start: str = "2020-01-01") -> pd.DataFrame:
    """Build a 15m frame whose daily closes equal the given series."""
    days = pd.date_range(start, periods=len(daily_closes), freq="1D", tz="UTC")
    rows = []
    for d, c in zip(days, daily_closes):
        # 4 bars per day is enough: resample("1D").last() takes the last
        for k in range(4):
            rows.append({"datetime": d + pd.Timedelta(hours=6 * k), "Close": float(c)})
    return pd.DataFrame(rows)


def test_uptrend_is_bull_and_label_is_shifted():
    n = MIN_DAYS + 100
    closes = np.linspace(100, 400, n)  # steady uptrend
    df = _frame_from_daily(closes)
    labels = daily_regime_labels(df)
    assert labels.iloc[-1] == "bull"
    # first MIN_DAYS-ish labels must be unknown (insufficient history)
    assert (labels.iloc[: MIN_DAYS - 1] == "unknown").all()


def test_downtrend_is_bear():
    n = MIN_DAYS + 150
    closes = np.concatenate([
        np.linspace(100, 120, MIN_DAYS),      # warmup drift
        np.linspace(120, 40, 150),            # collapse
    ])
    df = _frame_from_daily(closes)
    labels = daily_regime_labels(df)
    assert labels.iloc[-1] == "bear"


def test_causality_label_uses_previous_day_only():
    """Day D's label must not change if day D's candles change."""
    n = MIN_DAYS + 50
    closes = np.linspace(100, 300, n)
    df_a = _frame_from_daily(closes)
    closes_b = closes.copy()
    closes_b[-1] = 1.0  # crash on the LAST day only
    df_b = _frame_from_daily(closes_b)
    la = daily_regime_labels(df_a)
    lb = daily_regime_labels(df_b)
    # the label OF the last day is computed from D-1 data: identical
    assert la.iloc[-1] == lb.iloc[-1]


def test_regime_for_times_maps_intraday_bars():
    n = MIN_DAYS + 50
    closes = np.linspace(100, 300, n)
    df = _frame_from_daily(closes)
    labels = daily_regime_labels(df)
    last_day = labels.index[-1]
    ts = pd.Series([last_day + pd.Timedelta(hours=13)])
    out = regime_for_times(labels, ts)
    assert out[0] == labels.iloc[-1]
    assert regime_at(labels, last_day + pd.Timedelta(minutes=15)) == labels.iloc[-1]
