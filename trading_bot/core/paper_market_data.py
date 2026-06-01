"""Local market-data fallback for paper-mode operation.

This module is intentionally read-only: it loads cached OHLCV candles for the
paper engine when live exchange endpoints are unavailable. It never routes
orders, changes gates, or mutates broker state.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import MutableMapping

import pandas as pd


class CachedMarketDataNotFound(FileNotFoundError):
    """Raised when no suitable local OHLCV cache exists for a paper symbol."""


@dataclass(frozen=True)
class MarketDataFrame:
    df: pd.DataFrame
    source: str
    path: Path
    rows_available: int
    rows_returned: int
    replay_end_offset: int | None = None


def _asset_slug(symbol: str) -> str:
    return str(symbol).replace("/", "").replace(":", "").lower()


def _legacy_base(symbol: str) -> str:
    return "btc" if str(symbol).upper().startswith("BTC/") else _asset_slug(symbol)


def discover_cached_ohlcv_path(data_dir: str | Path, symbol: str, timeframe: str) -> Path | None:
    data_path = Path(data_dir)
    base = _legacy_base(symbol)
    slug = _asset_slug(symbol)
    candidates = [
        data_path / f"{base}_{timeframe}_150k_cache.parquet",
        data_path / f"{slug}_{timeframe}_150k_cache.parquet",
        data_path / f"{base}_{timeframe}_100k_cache.parquet",
        data_path / f"{base}_{timeframe}_50k_cache.parquet",
        data_path / f"{base}_{timeframe}_25k_cache.parquet",
        data_path / f"{base}_{timeframe}_10k_cache.parquet",
        data_path / f"{base}_{timeframe}_cache.parquet",
        data_path / f"{slug}_{timeframe}_cache.parquet",
        data_path / f"{slug}_cache.parquet",
    ]
    if str(symbol).upper() == "BTC/USDT":
        candidates.append(data_path / "btc_15m_cache.parquet")
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            return path
    for path in sorted(data_path.glob(f"{base}_{timeframe}_*_cache.parquet"), reverse=True):
        if path.exists():
            return path
    return None


def _normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename: dict[str, str] = {}
    for col in list(out.columns):
        low = str(col).lower()
        if low == "open":
            rename[col] = "Open"
        elif low == "high":
            rename[col] = "High"
        elif low == "low":
            rename[col] = "Low"
        elif low == "close":
            rename[col] = "Close"
        elif low in {"volume", "vol"}:
            rename[col] = "Volume"
        elif low in {"timestamp", "date"}:
            rename[col] = "datetime"
    if rename:
        out = out.rename(columns=rename)
    if "datetime" not in out.columns:
        if out.index.name == "datetime":
            out = out.reset_index()
        elif isinstance(out.index, pd.DatetimeIndex):
            out = out.reset_index().rename(columns={out.index.name or "index": "datetime"})
    needed = ["datetime", "Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in needed if col not in out.columns]
    if missing:
        raise ValueError(f"cached OHLCV is missing required columns: {missing}")
    out = out[needed].copy()
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=needed).drop_duplicates(subset=["datetime"]).sort_values("datetime")
    out = out.set_index("datetime")
    out.index.name = "datetime"
    return out.astype(float)


def load_cached_ohlcv(
    *,
    data_dir: str | Path,
    symbol: str,
    timeframe: str,
    limit: int,
    end_offset: int | None = None,
) -> MarketDataFrame:
    path = discover_cached_ohlcv_path(data_dir, symbol, timeframe)
    if path is None:
        raise CachedMarketDataNotFound(f"no cached OHLCV found for {symbol} {timeframe} in {Path(data_dir)}")
    df = _normalize_ohlcv_frame(pd.read_parquet(path))
    rows_available = int(len(df))
    if rows_available <= 0:
        raise CachedMarketDataNotFound(f"cached OHLCV is empty: {path}")
    limit = max(1, int(limit))
    if end_offset is None:
        window = df.tail(limit)
        replay_end_offset = None
    else:
        replay_end_offset = min(max(limit, int(end_offset)), rows_available)
        window = df.iloc[max(0, replay_end_offset - limit):replay_end_offset]
    return MarketDataFrame(
        df=window.copy(),
        source="local_cache",
        path=path,
        rows_available=rows_available,
        rows_returned=int(len(window)),
        replay_end_offset=replay_end_offset,
    )


def load_replay_ohlcv(
    *,
    data_dir: str | Path,
    symbol: str,
    timeframe: str,
    limit: int,
    replay_offsets: MutableMapping[str, int],
    step: int = 1,
    start_offset: int | None = None,
) -> MarketDataFrame:
    key = f"{symbol}|{timeframe}"
    first = load_cached_ohlcv(data_dir=data_dir, symbol=symbol, timeframe=timeframe, limit=limit, end_offset=limit)
    rows_available = first.rows_available
    initial_offset = int(start_offset) if start_offset is not None else int(limit)
    current = int(replay_offsets.get(key, max(1, initial_offset)))
    if current < int(limit):
        current = int(limit)
    if current > rows_available:
        current = int(limit)
    replay_offsets[key] = current + max(1, int(step))
    return load_cached_ohlcv(
        data_dir=data_dir,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        end_offset=current,
    )
