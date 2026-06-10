from __future__ import annotations

from pathlib import Path

import pandas as pd


SYMBOL_CACHE_NAMES = {
    "BTC/USDT": "btc_5m_150k_cache.parquet",
    "ETH/USDT": "ethusdt_5m_150k_cache.parquet",
    "SOL/USDT": "solusdt_5m_150k_cache.parquet",
    "BNB/USDT": "bnbusdt_5m_150k_cache.parquet",
    "XRP/USDT": "xrpusdt_5m_150k_cache.parquet",
}

SYMBOL_CACHE_NAMES_BY_TIMEFRAME = {
    "5m": SYMBOL_CACHE_NAMES,
    "1m": {
        "XRP/USDT": "xrpusdt_1m_cache.parquet",
    },
}

# Panel research timeframes (Edge Research 03) use a deterministic naming
# convention instead of the explicit per-symbol dicts above:
# {slug}_{tf}_cache.parquet, e.g. btcusdt_4h_cache.parquet.
PANEL_TIMEFRAMES = frozenset({"4h", "1d"})


def _panel_cache_name(symbol: str, timeframe: str) -> str:
    slug = str(symbol or "").replace("/", "").replace(":", "").lower()
    if not slug or not slug.isalnum():
        raise ValueError(f"unsupported clean bot symbol for panel cache: {symbol!r}")
    return f"{slug}_{timeframe}_cache.parquet"


def cache_path(data_dir: Path, symbol: str, timeframe: str) -> Path:
    normalized_timeframe = str(timeframe or "5m").strip().lower()
    if normalized_timeframe in PANEL_TIMEFRAMES:
        return data_dir / _panel_cache_name(symbol, normalized_timeframe)
    names = SYMBOL_CACHE_NAMES_BY_TIMEFRAME.get(normalized_timeframe)
    if names is None:
        supported = ", ".join(sorted(set(SYMBOL_CACHE_NAMES_BY_TIMEFRAME) | PANEL_TIMEFRAMES))
        raise ValueError(f"unsupported clean bot timeframe: {timeframe}; supported={supported}")
    name = names.get(symbol.upper())
    if not name:
        raise ValueError(f"unsupported clean bot symbol/timeframe: {symbol} {timeframe}")
    return data_dir / name


def load_ohlcv(data_dir: Path, symbol: str, timeframe: str = "5m", max_rows: int = 50000) -> pd.DataFrame:
    path = cache_path(data_dir, symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(str(path))
    df = pd.read_parquet(path)
    required = {"datetime", "Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError(f"cache missing columns: {missing}")
    df = df.sort_values("datetime").tail(max_rows).reset_index(drop=True).copy()
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
