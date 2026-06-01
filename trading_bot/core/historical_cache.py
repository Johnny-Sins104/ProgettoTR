"""Historical OHLCV cache management for backtests.

Prompt 28.5: make the --candles request honest.  The backtest runner should not
silently run on 1k bars when the user requested 50k.  This module selects the
largest local cache, can extract BTC candles from the expanded multi-asset
research dataset, and can optionally download a larger OHLCV cache via CCXT.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


@dataclass(frozen=True)
class CacheCandidate:
    path: Path
    rows: int
    source: str


@dataclass(frozen=True)
class CacheResolution:
    path: Path
    rows: int
    requested_rows: int
    exact_or_sufficient: bool
    source: str
    warnings: tuple[str, ...] = ()


def timeframe_to_minutes(timeframe: str) -> int:
    tf = str(timeframe).strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("d"):
        return int(tf[:-1]) * 24 * 60
    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def _asset_slug(symbol: str) -> str:
    return str(symbol).replace("/", "").replace(":", "").lower()


def _display_asset(symbol: str) -> str:
    return str(symbol).replace("/", "").replace(":USDT", "").upper()


def cache_filename(symbol: str, timeframe: str, rows: int) -> str:
    # Preserve legacy BTC-style filenames for compatibility with existing scripts.
    base = "btc" if str(symbol).upper().startswith("BTC/") else _asset_slug(symbol)
    return f"{base}_{timeframe}_{int(rows)//1000}k_cache.parquet" if rows >= 1000 else f"{base}_{timeframe}_{rows}_cache.parquet"


def legacy_cache_filenames(symbol: str, timeframe: str) -> list[str]:
    base = "btc" if str(symbol).upper().startswith("BTC/") else _asset_slug(symbol)
    return [
        f"{base}_{timeframe}_100k_cache.parquet",
        f"{base}_{timeframe}_50k_cache.parquet",
        f"{base}_{timeframe}_25k_cache.parquet",
        f"{base}_{timeframe}_10k_cache.parquet",
        f"{base}_{timeframe}_cache.parquet",
    ]


def count_parquet_rows(path: os.PathLike[str] | str) -> int:
    try:
        import polars as pl  # type: ignore

        try:
            return int(pl.scan_parquet(str(path)).select(pl.len()).collect().item())
        except Exception:
            return int(pl.read_parquet(str(path)).height)
    except Exception:
        try:
            return int(len(pd.read_parquet(str(path))))
        except Exception:
            return 0


def discover_local_caches(data_dir: str | os.PathLike[str], symbol: str, timeframe: str) -> list[CacheCandidate]:
    data_path = Path(data_dir)
    candidates: list[CacheCandidate] = []
    seen: set[Path] = set()

    for name in legacy_cache_filenames(symbol, timeframe):
        path = data_path / name
        if path.exists() and path not in seen:
            rows = count_parquet_rows(path)
            if rows > 0:
                candidates.append(CacheCandidate(path=path, rows=rows, source="local_cache"))
            seen.add(path)

    base = "btc" if str(symbol).upper().startswith("BTC/") else _asset_slug(symbol)
    for path in sorted(data_path.glob(f"{base}_{timeframe}_*_cache.parquet")):
        if path not in seen:
            rows = count_parquet_rows(path)
            if rows > 0:
                candidates.append(CacheCandidate(path=path, rows=rows, source="local_cache"))
            seen.add(path)

    return sorted(candidates, key=lambda c: c.rows, reverse=True)


def _normalize_candle_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rename = {}
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
        elif low in ("volume", "vol"):
            rename[col] = "Volume"
    if rename:
        out = out.rename(columns=rename)
    if "datetime" not in out.columns:
        if out.index.name == "datetime":
            out = out.reset_index()
        elif "timestamp" in out.columns:
            out = out.rename(columns={"timestamp": "datetime"})
    needed = ["datetime", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in out.columns]
    if missing:
        raise ValueError(f"Cannot normalize candle dataframe; missing columns: {missing}")
    out = out[needed].copy()
    out["datetime"] = pd.to_datetime(out["datetime"], utc=True)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=needed).drop_duplicates(subset=["datetime"]).sort_values("datetime")
    return out


def try_extract_from_multi_asset_dataset(
    *,
    requested_rows: int,
    symbol: str,
    timeframe: str,
    data_dir: str | os.PathLike[str] = "data",
) -> Optional[CacheCandidate]:
    """Create a single-asset cache from data/datasets/candles_multi_asset.parquet if available."""
    import polars as pl

    data_path = Path(data_dir)
    source_path = data_path / "datasets" / "candles_multi_asset.parquet"
    if not source_path.exists():
        return None

    asset = _display_asset(symbol)
    # Existing datasets typically use BTCUSDT style symbols.
    accepted_assets = {asset, asset.replace("USDT", "/USDT"), str(symbol).upper(), str(symbol).replace("/", "").upper()}
    try:
        df = pl.read_parquet(source_path)
        if "timeframe" in df.columns:
            df = df.filter(pl.col("timeframe").cast(pl.Utf8).str.to_lowercase() == str(timeframe).lower())
        elif str(timeframe).lower() != "15m":
            # The legacy expanded candle dataset has historically been 15m.
            # Do not create a fake 5m/3m cache from 15m rows.
            return None
        if "asset" in df.columns:
            df = df.filter(pl.col("asset").cast(pl.Utf8).str.to_uppercase().is_in(list(accepted_assets)))
        if df.height <= 0:
            return None
        pdf = df.to_pandas()
        pdf = _normalize_candle_columns(pdf)
        pdf = pdf.tail(int(requested_rows)) if requested_rows > 0 else pdf
        if len(pdf) <= 0:
            return None
        target = data_path / cache_filename(symbol, timeframe, max(int(requested_rows), len(pdf)))
        target.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame(pdf).write_parquet(str(target), compression="snappy")
        return CacheCandidate(path=target, rows=len(pdf), source="multi_asset_dataset_extract")
    except Exception as exc:
        print(f"⚠️ [HistoricalCache] Impossibile estrarre cache da {source_path}: {exc}")
        return None


async def download_ohlcv_cache(
    *,
    requested_rows: int,
    exchange_id: str,
    symbol: str,
    timeframe: str,
    data_dir: str | os.PathLike[str] = "data",
    limit: int = 1000,
    rate_limit_seconds: float = 0.25,
) -> CacheCandidate:
    """Download paginated OHLCV history and write a parquet cache."""
    try:
        from .aiohttp_compat import install_aiohttp_windows_ssl_context_compat

        install_aiohttp_windows_ssl_context_compat()
        import ccxt.async_support as ccxt_async  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("ccxt is required to download a larger historical cache.") from exc

    exchange_cls = getattr(ccxt_async, exchange_id)
    exchange = exchange_cls({"enableRateLimit": True})
    candle_ms = timeframe_to_minutes(timeframe) * 60 * 1000
    now_ms = int(time.time() * 1000)
    since = now_ms - int(requested_rows * candle_ms * 1.05)
    rows: list[list[float]] = []
    try:
        while len(rows) < requested_rows:
            batch = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
            if not batch:
                break
            if rows and batch[0][0] <= rows[-1][0]:
                since = rows[-1][0] + candle_ms
                continue
            rows.extend(batch)
            since = batch[-1][0] + candle_ms
            print(f"  [HistoricalCache] Downloaded {min(len(rows), requested_rows)}/{requested_rows} candles...")
            await asyncio.sleep(rate_limit_seconds)
    finally:
        await exchange.close()

    if not rows:
        raise RuntimeError("No OHLCV rows returned by exchange.")
    rows = rows[-requested_rows:]
    df = pd.DataFrame(rows, columns=["datetime", "Open", "High", "Low", "Close", "Volume"])
    df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
    df = _normalize_candle_columns(df)

    import polars as pl

    target = Path(data_dir) / cache_filename(symbol, timeframe, requested_rows)
    target.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(df).write_parquet(str(target), compression="snappy")
    return CacheCandidate(path=target, rows=len(df), source="exchange_download")


def resolve_backtest_cache(
    *,
    requested_rows: int,
    config,
    data_dir: str | os.PathLike[str] = "data",
    allow_download: bool = True,
    force_download: bool = False,
    rate_limit_seconds: Optional[float] = None,
) -> CacheResolution:
    """Resolve a cache path that honestly satisfies, or reports failure to satisfy, requested rows."""
    warnings: list[str] = []
    symbol = getattr(config, "SYMBOL", "BTC/USDT")
    timeframe = getattr(config, "TIMEFRAME", "15m")
    exchange_id = getattr(config, "EXCHANGE_ID", "binanceusdm")
    if rate_limit_seconds is None:
        rate_limit_seconds = float(getattr(config, "BACKTEST_HISTORY_RATE_LIMIT_SECONDS", 0.25))
    requested_rows = int(max(1, requested_rows))

    local = discover_local_caches(data_dir, symbol, timeframe)
    sufficient = [c for c in local if c.rows >= requested_rows]
    if sufficient and not force_download:
        best = sufficient[0]
        return CacheResolution(best.path, best.rows, requested_rows, True, best.source, tuple(warnings))

    best_local = local[0] if local else None
    if best_local is not None:
        warnings.append(
            f"Requested {requested_rows} candles but largest local cache {best_local.path} contains only {best_local.rows}."
        )

    extracted = try_extract_from_multi_asset_dataset(
        requested_rows=requested_rows,
        symbol=symbol,
        timeframe=timeframe,
        data_dir=data_dir,
    )
    if extracted is not None and extracted.rows >= requested_rows and not force_download:
        warnings.append(f"Built requested cache from expanded multi-asset dataset: {extracted.path} ({extracted.rows} rows).")
        return CacheResolution(extracted.path, extracted.rows, requested_rows, True, extracted.source, tuple(warnings))
    if extracted is not None:
        warnings.append(f"Multi-asset extract available but short: {extracted.path} has {extracted.rows} rows.")
        local = discover_local_caches(data_dir, symbol, timeframe)
        best_local = local[0] if local else extracted

    if allow_download:
        try:
            print(f"📡 [HistoricalCache] Download richiesto: {requested_rows} candele {symbol} {timeframe} da {exchange_id}...")
            downloaded = asyncio.run(
                download_ohlcv_cache(
                    requested_rows=requested_rows,
                    exchange_id=exchange_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    data_dir=data_dir,
                    rate_limit_seconds=float(rate_limit_seconds),
                )
            )
            if downloaded.rows >= requested_rows:
                warnings.append(f"Downloaded larger historical cache: {downloaded.path} ({downloaded.rows} rows).")
                return CacheResolution(downloaded.path, downloaded.rows, requested_rows, True, downloaded.source, tuple(warnings))
            warnings.append(f"Downloaded cache is still short: {downloaded.path} has {downloaded.rows} rows.")
            best_local = downloaded if best_local is None or downloaded.rows > best_local.rows else best_local
        except Exception as exc:
            warnings.append(f"Historical download failed; using best available cache. Reason: {exc}")

    if best_local is None:
        raise RuntimeError(
            f"No OHLCV cache available for {symbol} {timeframe}, and historical download did not produce data."
        )

    return CacheResolution(best_local.path, best_local.rows, requested_rows, False, best_local.source, tuple(warnings))
