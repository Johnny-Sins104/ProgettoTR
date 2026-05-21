"""Prompt 19 runner: large-scale multi-asset dataset expansion.

Usage examples
--------------
Build from local parquet caches:
    python run_dataset_expansion.py --cache BTCUSDT=data/btc_15m_cache.parquet ETHUSDT=data/eth_15m_cache.parquet

Generate an offline synthetic smoke dataset:
    python run_dataset_expansion.py --synthetic

Download from Binance Futures (requires internet + ccxt):
    python run_dataset_expansion.py --download --years 2

Optional macro sources:
    python run_dataset_expansion.py --download --years 2 --funding data/funding.parquet --open-interest data/oi.parquet
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from core.multi_asset_dataset import (
    DEFAULT_ASSETS,
    BinanceFuturesHistoricalDownloader,
    DatasetBuildConfig,
    MultiAssetDatasetBuilder,
)


def _parse_cache_args(items) -> Dict[str, str]:
    paths: Dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"Invalid --cache entry '{item}'. Expected ASSET=path.parquet")
        asset, path = item.split("=", 1)
        paths[asset.upper()] = path
    return paths


def _synthetic_ohlcv(asset: str, rows: int = 3000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed + abs(hash(asset)) % 10_000)
    start = pd.Timestamp("2023-01-01", tz="UTC")
    dt = pd.date_range(start, periods=rows, freq="15min")
    base = 65000 if asset.startswith("BTC") else 3000 if asset.startswith("ETH") else 100
    returns = rng.normal(0.00002, 0.004, size=rows)
    trend = np.sin(np.linspace(0, 18, rows)) * 0.0005
    close = base * np.exp(np.cumsum(returns + trend))
    spread = close * rng.uniform(0.0005, 0.003, size=rows)
    high = close + spread
    low = close - spread
    open_ = close * (1 + rng.normal(0, 0.0008, size=rows))
    volume = rng.lognormal(mean=9, sigma=0.7, size=rows)
    return pd.DataFrame({"datetime": dt, "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})


async def _download_frames(assets, years: float):
    downloader = BinanceFuturesHistoricalDownloader(timeframe="15m")
    frames = {}
    for asset in assets:
        print(f"[DatasetExpansion] Downloading {asset} {years:.1f}y 15m futures candles...")
        frames[asset] = await downloader.fetch_asset(asset, years=years)
    return frames


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/datasets")
    parser.add_argument("--assets", nargs="*", default=list(DEFAULT_ASSETS))
    parser.add_argument("--years", type=float, default=2.0)
    parser.add_argument("--cache", nargs="*", help="Entries like BTCUSDT=data/btc_15m_cache.parquet")
    parser.add_argument("--synthetic", action="store_true", help="Build an offline smoke dataset.")
    parser.add_argument("--synthetic-rows", type=int, default=3000)
    parser.add_argument("--download", action="store_true", help="Download Binance USDT-M futures candles via ccxt.")
    parser.add_argument("--funding", default="", help="Optional funding-rate parquet/csv with datetime, asset, funding_rate.")
    parser.add_argument("--open-interest", default="", help="Optional open-interest parquet/csv with datetime, asset, open_interest.")
    parser.add_argument("--btc-dominance", default="", help="Optional BTC dominance parquet/csv with datetime, btc_dominance.")
    parser.add_argument("--disable-market-structure", action="store_true", help="Disable Prompt 26 market-structure feature enrichment.")
    args = parser.parse_args()

    cfg = DatasetBuildConfig(
        assets=tuple(a.upper() for a in args.assets),
        output_dir=args.output_dir,
        min_years=args.years,
        enable_market_structure_features=not args.disable_market_structure,
        funding_data_path=args.funding,
        open_interest_data_path=args.open_interest,
        btc_dominance_data_path=args.btc_dominance,
    )
    builder = MultiAssetDatasetBuilder(cfg)

    cache_paths = _parse_cache_args(args.cache)
    if args.synthetic:
        frames = {asset: _synthetic_ohlcv(asset, rows=args.synthetic_rows) for asset in cfg.assets}
        report = builder.build_from_frames(frames)
    elif cache_paths:
        report = builder.build_from_parquet_paths(cache_paths)
    elif args.download:
        frames = asyncio.run(_download_frames(cfg.assets, args.years))
        report = builder.build_from_frames(frames)
    else:
        raise SystemExit("Choose one: --synthetic, --cache ASSET=path, or --download")

    print("\n[DatasetExpansion] Completed")
    print(f"  Candles     : {report.total_candles}")
    print(f"  Features    : {report.total_features}")
    print(f"  Candidates  : {report.total_candidates}")
    print(f"  Meta labels : {report.total_meta_labels}")
    print(f"  Output dir  : {Path(cfg.output_dir).resolve()}")
    if report.warnings:
        print("\n[DatasetExpansion] Warnings:")
        for w in report.warnings[:20]:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
