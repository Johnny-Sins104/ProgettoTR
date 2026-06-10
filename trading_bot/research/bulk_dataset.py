"""Cycle-2 STRAT-01: bulk historical dataset from data.binance.vision.

Downloads monthly (and current-month daily) USDT-M futures kline archives
with SHA-256 checksum verification, builds atomic parquet caches with
manifests, freezes the immutable cycle-2 temporal split and writes the
panel manifest documenting the point-in-time selection rule.

Panel selection rule (declared, point-in-time, survivorship-free)
-----------------------------------------------------------------
The 16 earliest USDT perpetual contracts listed on Binance UM futures
(all listed between 2019-09 and 2020-02). Listing order is a
point-in-time liquidity proxy: Binance launched contracts in order of
market demand. The set includes contracts that were later delisted
(e.g. XMR/DASH/ZEC in 2024) — their history ends at delisting and they
participate in the cross-sectional panel only while tradable, which is
exactly the information available at the time.

Diagnostic-only. Public data, no credentials, no orders.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "trading_bot"))

import pandas as pd  # noqa: E402

from core.research_dataset import (  # noqa: E402
    CacheManifest,
    DataSufficiencyAuditor,
    TemporalSplitter,
)

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False

BASE_URL = "https://data.binance.vision/data/futures/um"
API_KLINES = "https://fapi.binance.com/fapi/v1/klines"

C2_PANEL: Tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "BCHUSDT", "XRPUSDT", "EOSUSDT", "LTCUSDT",
    "TRXUSDT", "ETCUSDT", "LINKUSDT", "XLMUSDT", "ADAUSDT", "XMRUSDT",
    "DASHUSDT", "ZECUSDT", "XTZUSDT", "BNBUSDT",
)
C2_SELECTION_RULE = (
    "The 16 earliest USDT perpetuals listed on Binance UM futures "
    "(2019-09..2020-02), in listing order — a point-in-time liquidity "
    "proxy free of survivorship bias; later-delisted contracts included "
    "until their delisting date."
)
TIMEFRAMES = ("15m", "5m")
FIRST_MONTH = (2019, 9)          # UM futures archives begin 2019-12/2020-01
C2_CACHE_DIR = Path("data/strat02_cache")
C2_SPLIT_LOCK = "strat02_temporal_splits.json"
C2_PROVENANCE = "binance_vision_um_futures_bulk"
MIN_PANEL_SYMBOLS = 12


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _months(first: Tuple[int, int], last: Tuple[int, int]):
    y, m = first
    while (y, m) <= last:
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


# ---------------------------------------------------------------------------
# HTTP with checksum verification
# ---------------------------------------------------------------------------

class BulkFetcher:
    def __init__(self) -> None:
        import requests

        self._s = requests.Session()
        self._requests = requests

    def get(self, url: str) -> Optional[bytes]:
        """GET a URL; None on 404 (absent archive), raise on other errors."""
        for attempt in range(4):
            try:
                r = self._s.get(url, timeout=60)
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                return r.content
            if attempt == 3:
                r.raise_for_status()
            time.sleep(2.0 * (attempt + 1))
        return None

    def fetch_zip_verified(self, zip_url: str) -> Optional[bytes]:
        """Download archive + .CHECKSUM; fail-closed on SHA-256 mismatch."""
        blob = self.get(zip_url)
        if blob is None:
            return None
        chk = self.get(zip_url + ".CHECKSUM")
        if chk is None:
            raise RuntimeError(f"Archive exists but checksum file missing: {zip_url}")
        expected = chk.decode("utf-8").strip().split()[0].lower()
        actual = hashlib.sha256(blob).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"CHECKSUM MISMATCH for {zip_url}: expected {expected}, got {actual}"
            )
        return blob


def _parse_kline_zip(blob: bytes) -> List[Tuple[int, float, float, float, float, float, int]]:
    """Extract (open_ms, o, h, l, c, vol, close_ms) rows from an archive."""
    rows: List[Tuple[int, float, float, float, float, float, int]] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        for name in zf.namelist():
            with zf.open(name) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8")
                reader = csv.reader(text)
                for rec in reader:
                    if not rec or not rec[0].strip().isdigit():
                        continue  # header line or junk
                    ot = int(rec[0])
                    ct = int(rec[6])
                    # 2025+ archives use microseconds; older use milliseconds
                    if ot > 10**14:
                        ot //= 1000
                        ct //= 1000
                    rows.append(
                        (ot, float(rec[1]), float(rec[2]), float(rec[3]),
                         float(rec[4]), float(rec[5]), ct)
                    )
    return rows


# ---------------------------------------------------------------------------
# Symbol download
# ---------------------------------------------------------------------------

def download_symbol(
    fetcher: BulkFetcher,
    symbol: str,
    interval: str,
    now_utc: datetime,
) -> pd.DataFrame:
    last_full_month = (now_utc.year, now_utc.month - 1) if now_utc.month > 1 else (
        now_utc.year - 1, 12
    )
    rows: List[Tuple[int, float, float, float, float, float, int]] = []
    months_found = 0
    for y, m in _months(FIRST_MONTH, last_full_month):
        url = f"{BASE_URL}/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{y:04d}-{m:02d}.zip"
        blob = fetcher.fetch_zip_verified(url)
        if blob is None:
            continue
        months_found += 1
        rows.extend(_parse_kline_zip(blob))

    # Current month: daily archives (published with ~1 day lag)
    day = datetime(now_utc.year, now_utc.month, 1, tzinfo=timezone.utc)
    while day.date() <= now_utc.date():
        url = (
            f"{BASE_URL}/daily/klines/{symbol}/{interval}/"
            f"{symbol}-{interval}-{day:%Y-%m-%d}.zip"
        )
        blob = fetcher.fetch_zip_verified(url)
        if blob is not None:
            rows.extend(_parse_kline_zip(blob))
        day += pd.Timedelta(days=1)

    if not rows:
        return pd.DataFrame(
            columns=["open_time_utc", "open", "high", "low", "close", "volume", "close_time_ms"]
        )

    # Tail fill from the public API (closed candles only) so coverage
    # reaches the latest closed candle even before today's daily archive.
    rows.sort(key=lambda r: r[0])
    last_open = rows[-1][0]
    tf_ms = {"5m": 300_000, "15m": 900_000}[interval]
    now_ms = int(now_utc.timestamp() * 1000)
    since = last_open + tf_ms
    while since < now_ms:
        blob = fetcher.get(
            f"{API_KLINES}?symbol={symbol}&interval={interval}"
            f"&startTime={since}&limit=1500"
        )
        if blob is None:
            break
        batch = json.loads(blob)
        if not batch:
            break
        for r in batch:
            rows.append(
                (int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                 float(r[4]), float(r[5]), int(r[6]))
            )
        since = int(batch[-1][0]) + tf_ms
        if len(batch) < 1500:
            break
        time.sleep(0.25)

    df = pd.DataFrame(
        rows,
        columns=["open_time_ms", "open", "high", "low", "close", "volume", "close_time_ms"],
    )
    df = df.drop_duplicates(subset="open_time_ms").sort_values("open_time_ms")
    # closed candles only
    df = df[df["close_time_ms"] <= int(now_utc.timestamp() * 1000)]
    df["open_time_utc"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True)
    df = df[
        ["open_time_utc", "open", "high", "low", "close", "volume", "close_time_ms"]
    ].reset_index(drop=True)
    df.attrs["months_found"] = months_found
    return df


# ---------------------------------------------------------------------------
# Atomic write + manifest (bulk provenance)
# ---------------------------------------------------------------------------

def write_cache(
    df: pd.DataFrame, path: Path, asset: str, timeframe: str, tf_minutes: int
) -> CacheManifest:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp.parquet")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False, compression="snappy")
        h = hashlib.sha256()
        with open(tmp, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    times = pd.to_datetime(df["open_time_utc"], utc=True)
    diffs = times.diff().dt.total_seconds().dropna() * 1000.0
    expected_ms = tf_minutes * 60 * 1000
    gap_mask = diffs > expected_ms * 1.5
    gap_bars = int(((diffs[gap_mask] / expected_ms).astype(int) - 1).sum()) if gap_mask.any() else 0
    coverage_days = (times.iloc[-1] - times.iloc[0]).total_seconds() / 86400.0 if len(df) else 0.0

    manifest = CacheManifest(
        asset=asset,
        timeframe=timeframe,
        source_url=f"{BASE_URL}/monthly/klines/{asset}/{timeframe}/",
        provenance=C2_PROVENANCE,
        download_utc=_utc_now_iso(),
        row_count=len(df),
        first_ts=times.iloc[0].isoformat() if len(df) else "",
        last_ts=times.iloc[-1].isoformat() if len(df) else "",
        coverage_days=round(coverage_days, 2),
        coverage_years=round(coverage_days / 365.25, 4),
        gap_count=int(gap_mask.sum()),
        gap_bars_total=max(gap_bars, 0),
        sha256=h.hexdigest(),
        path=str(path),
        timeframe_minutes=tf_minutes,
    )
    with path.with_suffix(".manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(
            {**asdict(manifest), "checksum_verified": True,
             "selection_rule": C2_SELECTION_RULE},
            fh, indent=2,
        )
    return manifest


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

    cache_dir = ROOT / C2_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetcher = BulkFetcher()
    now_utc = datetime.now(timezone.utc)

    manifests: List[CacheManifest] = []
    skipped: List[str] = []
    for symbol in C2_PANEL:
        for interval in TIMEFRAMES:
            t0 = time.time()
            df = download_symbol(fetcher, symbol, interval, now_utc)
            if df.empty:
                print(f"[bulk] {symbol} {interval}: NO ARCHIVES (skipped)")
                skipped.append(f"{symbol}:{interval}")
                continue
            m = write_cache(
                df,
                cache_dir / f"{symbol}_{interval}.parquet",
                symbol,
                interval,
                15 if interval == "15m" else 5,
            )
            print(
                f"[bulk] {symbol} {interval}: rows={m.row_count} "
                f"{m.first_ts[:10]} -> {m.last_ts[:10]} "
                f"({m.coverage_years:.2f}y, gaps={m.gap_count}) "
                f"[{time.time() - t0:.0f}s]"
            )
            manifests.append(m)

    symbols_ok = sorted({m.asset for m in manifests})
    if len(symbols_ok) < MIN_PANEL_SYMBOLS:
        print(
            f"FATAL: only {len(symbols_ok)} symbols with data "
            f"(< {MIN_PANEL_SYMBOLS} required). Honest failure, no synthesis."
        )
        return 2

    splitter = TemporalSplitter(oos_fraction=0.20, val_fraction=0.20)
    splits = splitter.compute_splits(
        manifests, lock_path=cache_dir / C2_SPLIT_LOCK
    )
    auditor = DataSufficiencyAuditor(target_years=4.0)
    report = auditor.audit(manifests, splits)

    panel_manifest = {
        "generated_at_utc": _utc_now_iso(),
        "cycle": 2,
        "selection_rule": C2_SELECTION_RULE,
        "panel_declared": list(C2_PANEL),
        "panel_with_data": symbols_ok,
        "skipped": skipped,
        "min_panel_symbols": MIN_PANEL_SYMBOLS,
        "checksum_policy": "every archive verified against its .CHECKSUM (sha256); mismatch aborts",
        "splits": asdict(splits),
        "sufficiency": report.sufficiency,
        "warnings": report.warnings,
        "synthetic_substitution_used": False,
    }
    out = cache_dir / "strat02_panel_manifest.json"
    with out.open("w", encoding="utf-8") as fh:
        json.dump(panel_manifest, fh, indent=2)

    print(f"\n[done] panel symbols with data: {len(symbols_ok)}: {symbols_ok}")
    print(f"[done] split: train {splits.train_start} -> {splits.train_end}")
    print(f"[done]        val   {splits.val_start} -> {splits.val_end}")
    print(f"[done]        OOS   {splits.oos_start} -> {splits.oos_end}")
    print(f"[done] panel manifest -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
