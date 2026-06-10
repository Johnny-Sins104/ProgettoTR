"""funding.py — Perpetual funding accrual for the clean_bot backtester.

Funding is a PnL accrual on the holding period, NOT a transaction cost.
It must never be added to UnifiedCostModel._SCENARIO_PARAMS; it flows into
Trade.funding_pnl / Trade.net_pnl_with_funding only when
BacktestSettings.funding_enabled is True (opt-in, default off).

Data contract (parquet)
-----------------------
Columns:
  datetime      tz-aware UTC timestamps on the funding grid. Binance USDT-M
                is nominally every 8h (00:00/08:00/16:00 UTC) but some symbols
                settle every 4h or 1h, so the grid interval is detected per
                file from the modal timestamp diff and validated against the
                allowlist {1h, 4h, 8h}. All timestamps must be exact whole
                hours.
  symbol        str, must match the requested symbol on every row.
  funding_rate  float, decimal units (0.0001 = 1 bp). Hard cap |rate| < 0.0075.

Rows sorted ascending, no duplicates, no nulls. Any violation raises
ValueError (fail-closed, no silent coercion).

Sign convention
---------------
payment = -direction * funding_rate * mark_price * qty   (direction: +1 BUY, -1 SELL)
Long pays positive funding (negative pnl); short receives it (positive pnl).

Accrual convention
------------------
A funding event at timestamp t is charged iff entry_time < t <= exit_time:
the position must already be open at the funding instant, so an entry exactly
at a funding timestamp is NOT charged while an exit exactly at one IS.

Mark-price approximation: each funding timestamp is as-of joined (backward)
to the latest bar Close <= t. Bar Close ~= mark price is a stated
approximation of this research backtester.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

FUNDING_COLUMNS = ("datetime", "symbol", "funding_rate")
MAX_ABS_FUNDING_RATE = 0.0075
# Funding settlement intervals seen on Binance USDT-M perpetuals.
ALLOWED_GRID_HOURS = (1, 4, 8)


def _symbol_slug(symbol: str) -> str:
    return str(symbol or "").replace("/", "").replace(":", "").lower()


def funding_cache_path(data_dir: Path, symbol: str) -> Path:
    """Deterministic funding cache name: {slug}_funding.parquet."""
    slug = _symbol_slug(symbol)
    if not slug:
        raise ValueError(f"invalid symbol for funding cache: {symbol!r}")
    return Path(data_dir) / f"{slug}_funding.parquet"


def validate_funding_frame(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Validate a funding DataFrame against the data contract. Fail-closed.

    Returns the validated frame (datetime coerced to tz-aware UTC, sorted).
    Raises ValueError on any contract violation.
    """
    missing = sorted(set(FUNDING_COLUMNS).difference(df.columns))
    if missing:
        raise ValueError(f"funding frame missing columns: {missing}")
    if len(df) == 0:
        raise ValueError(f"funding frame for {symbol} is empty")

    out = df.loc[:, list(FUNDING_COLUMNS)].copy()

    if out["symbol"].isna().any():
        raise ValueError(f"funding frame for {symbol} has null symbol values")
    bad_symbols = sorted(set(out["symbol"].astype(str)) - {str(symbol)})
    if bad_symbols:
        raise ValueError(
            f"funding frame symbol mismatch: expected {symbol!r}, found {bad_symbols}"
        )

    dt = pd.to_datetime(out["datetime"], utc=True, errors="coerce")
    if dt.isna().any():
        raise ValueError(f"funding frame for {symbol} has unparseable datetime values")
    out["datetime"] = dt

    rates = pd.to_numeric(out["funding_rate"], errors="coerce")
    if rates.isna().any():
        raise ValueError(f"funding frame for {symbol} has null/non-numeric funding_rate values")
    if not rates.map(math.isfinite).all():
        raise ValueError(f"funding frame for {symbol} has non-finite funding_rate values")
    if (rates.abs() >= MAX_ABS_FUNDING_RATE).any():
        worst = float(rates.abs().max())
        raise ValueError(
            f"funding frame for {symbol} breaches |funding_rate| < {MAX_ABS_FUNDING_RATE}: "
            f"max abs rate {worst}"
        )
    out["funding_rate"] = rates.astype(float)

    if out["datetime"].duplicated().any():
        raise ValueError(f"funding frame for {symbol} has duplicate timestamps")
    if not out["datetime"].is_monotonic_increasing:
        raise ValueError(f"funding frame for {symbol} is not sorted ascending")

    off_grid = out["datetime"][
        (out["datetime"].dt.minute != 0)
        | (out["datetime"].dt.second != 0)
        | (out["datetime"].dt.microsecond != 0)
        | (out["datetime"].dt.nanosecond != 0)
    ]
    if len(off_grid):
        raise ValueError(
            f"funding frame for {symbol} has off-grid timestamps (not whole hours), "
            f"first: {off_grid.iloc[0]}"
        )

    if len(out) >= 2:
        diffs = out["datetime"].diff().dropna()
        modal = diffs.mode().iloc[0]
        modal_hours = modal.total_seconds() / 3600.0
        if modal_hours not in [float(h) for h in ALLOWED_GRID_HOURS]:
            raise ValueError(
                f"funding frame for {symbol} has modal interval {modal_hours}h, "
                f"expected one of {list(ALLOWED_GRID_HOURS)}h"
            )

    return out.reset_index(drop=True)


def load_funding(data_dir: Path, symbol: str) -> pd.DataFrame:
    """Load and validate the funding series for a symbol. Fail-closed."""
    path = funding_cache_path(data_dir, symbol)
    if not path.exists():
        raise FileNotFoundError(str(path))
    return validate_funding_frame(pd.read_parquet(path), symbol)


def accrue_funding_for_trade(
    *,
    funding_df: pd.DataFrame,
    bars_df: pd.DataFrame,
    side: str,
    entry_time,
    exit_time,
    qty: float,
) -> tuple[float, int]:
    """Accrue funding payments over a trade's holding period.

    Returns (funding_pnl, funding_events). funding_pnl follows the module
    sign convention: long pays positive funding, short receives it.
    Raises ValueError on invalid inputs or unpriceable funding events.
    """
    _side = str(side or "").upper().strip()
    if _side not in ("BUY", "SELL"):
        raise ValueError(f"Invalid side {side!r}: must be 'BUY' or 'SELL'.")
    q = float(qty)
    if not math.isfinite(q) or q <= 0:
        raise ValueError(f"qty must be a finite positive number, got {qty!r}")

    entry_ts = pd.Timestamp(entry_time)
    exit_ts = pd.Timestamp(exit_time)
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.tz_localize("UTC")
    if exit_ts.tzinfo is None:
        exit_ts = exit_ts.tz_localize("UTC")
    if pd.isna(entry_ts) or pd.isna(exit_ts):
        raise ValueError(f"unparseable entry/exit time: {entry_time!r} / {exit_time!r}")
    if exit_ts < entry_ts:
        raise ValueError(f"exit_time {exit_ts} before entry_time {entry_ts}")

    for col in ("datetime", "funding_rate"):
        if col not in funding_df.columns:
            raise ValueError(f"funding_df missing column {col!r}")
    if "datetime" not in bars_df.columns or "Close" not in bars_df.columns:
        raise ValueError("bars_df must have 'datetime' and 'Close' columns")

    # Position must already be open at the funding instant: entry < t <= exit.
    mask = (funding_df["datetime"] > entry_ts) & (funding_df["datetime"] <= exit_ts)
    events = funding_df.loc[mask, ["datetime", "funding_rate"]]
    if events.empty:
        return 0.0, 0

    bar_times = pd.to_datetime(bars_df["datetime"], utc=True)
    if not bar_times.is_monotonic_increasing:
        raise ValueError("bars_df datetime must be sorted ascending")
    closes = pd.to_numeric(bars_df["Close"], errors="coerce")

    direction = 1.0 if _side == "BUY" else -1.0
    funding_pnl = 0.0
    for t, rate in zip(events["datetime"], events["funding_rate"]):
        rate = float(rate)
        if not math.isfinite(rate):
            raise ValueError(f"non-finite funding_rate at {t}")
        # Backward as-of: latest bar Close <= t approximates the mark price.
        pos = bar_times.searchsorted(t, side="right") - 1
        if pos < 0:
            raise ValueError(f"no bar at or before funding event {t}: cannot price it")
        mark = float(closes.iloc[pos])
        if not math.isfinite(mark) or mark <= 0:
            raise ValueError(f"invalid mark price {mark!r} for funding event {t}")
        funding_pnl += -direction * rate * mark * q

    if not math.isfinite(funding_pnl):
        raise ValueError(f"funding_pnl is not finite: {funding_pnl!r}")
    return funding_pnl, int(len(events))
