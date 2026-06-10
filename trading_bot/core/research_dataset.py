"""
STRAT-01: Deterministic public historical-data expansion pipeline.

Implements the dataset expansion and research contract defined in
docs/STRATEGY_RESEARCH_ROADMAP.md § STRAT-01.

Assets    : BTCUSDT, ETHUSDT, XRPUSDT, SOLUSDT, BNBUSDT
Signal TF : 15m closed candles
Exec TF   : 5m closed candles
Source    : Binance Futures public klines API (no credentials required)
Cache     : atomic parquet writes + SHA-256 manifest JSON per file
Splits    : immutable train / validation / final-OOS (OOS >= 20%)
Audit     : gap count, range, honest sufficiency — no synthetic substitution

Design constraints
------------------
- No private API keys, no private endpoints, no bot startup, no orders.
- Missing history is reported honestly; synthetic candles are never written.
- All candles persisted are closed (close_time_ms <= now_utc_ms).
- Temporal split boundaries are written to a lock file once and never changed.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

STRAT01_ASSETS: Tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT")
STRAT01_SIGNAL_TF = "15m"
STRAT01_EXEC_TF = "5m"
STRAT01_SIGNAL_TF_MINUTES = 15
STRAT01_EXEC_TF_MINUTES = 5
STRAT01_TARGET_YEARS = 4.0
STRAT01_OOS_FRACTION = 0.20
STRAT01_VAL_FRACTION = 0.20

BINANCE_FUTURES_PUBLIC_KLINES = "https://fapi.binance.com/fapi/v1/klines"
STRAT01_PROVENANCE = "binance_futures_public_api"
STRAT01_SPLIT_LOCK_FILE = "strat01_temporal_splits.json"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CacheManifest:
    asset: str
    timeframe: str
    source_url: str
    provenance: str
    download_utc: str
    row_count: int
    first_ts: str
    last_ts: str
    coverage_days: float
    coverage_years: float
    gap_count: int
    gap_bars_total: int
    sha256: str
    path: str
    timeframe_minutes: int


@dataclass
class TemporalSplitBoundaries:
    frozen_at: str
    input_hash: str
    train_start: str
    train_end: str
    val_start: str
    val_end: str
    oos_start: str
    oos_end: str
    oos_fraction_actual: float
    oos_fraction_min: float
    val_fraction_actual: float


@dataclass
class AssetSufficiency:
    asset: str
    timeframe: str
    coverage_years: float
    target_years: float
    sufficient: bool
    gap_count: int
    gap_bars_total: int
    synthetic_substitution: bool
    note: str


@dataclass
class Strat01AuditReport:
    generated_at: str
    assets_audited: List[str]
    timeframes_audited: List[str]
    sufficiency: List[Dict]
    splits: Optional[Dict]
    global_sufficient: bool
    warnings: List[str]
    synthetic_substitution_used: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ts_iso(ts: "pd.Timestamp") -> str:
    return ts.isoformat()


def _interval_to_minutes(interval: str) -> int:
    mapping = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "2h": 120, "4h": 240, "1d": 1440,
    }
    if interval not in mapping:
        raise ValueError(f"Unknown interval '{interval}'. Supported: {list(mapping)}")
    return mapping[interval]


def _detect_time_col(df: pd.DataFrame) -> str:
    for candidate in ("open_time_utc", "datetime", "timestamp", "time", "date"):
        if candidate in df.columns:
            return candidate
    raise KeyError(f"Cannot find a datetime column in DataFrame columns: {list(df.columns)}")


# ---------------------------------------------------------------------------
# ClosedCandleGuard
# ---------------------------------------------------------------------------

class ClosedCandleGuard:
    """
    Filters out candles whose close_time_ms is in the future.

    A candle is *closed* when its close_time_ms <= now_utc_ms.
    If the DataFrame has no close_time_ms column the candles are treated as
    already closed (consistent with bulk historical downloads).
    """

    @staticmethod
    def filter(df: pd.DataFrame, now_utc_ms: Optional[int] = None) -> pd.DataFrame:
        if now_utc_ms is None:
            now_utc_ms = int(time.time() * 1000)
        if "close_time_ms" not in df.columns:
            return df.copy()
        return df[df["close_time_ms"] <= now_utc_ms].reset_index(drop=True)


# ---------------------------------------------------------------------------
# AtomicParquetWriter
# ---------------------------------------------------------------------------

class AtomicParquetWriter:
    """
    Writes a DataFrame to parquet atomically (tmp → os.replace) and produces
    a CacheManifest containing a SHA-256 hash, provenance, date range,
    row count, gap count and gap bar total.
    """

    @staticmethod
    def write(
        df: pd.DataFrame,
        path: Path,
        asset: str,
        timeframe: str,
        timeframe_minutes: int,
    ) -> CacheManifest:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to tmp then rename so the target is never partial.
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp.parquet"
        )
        tmp_path = Path(tmp_path_str)
        try:
            os.close(tmp_fd)
            df.to_parquet(str(tmp_path), index=False, compression="snappy")
            sha256 = AtomicParquetWriter._sha256_file(tmp_path)
            os.replace(str(tmp_path), str(path))
        except Exception:
            try:
                os.unlink(str(tmp_path))
            except OSError:
                pass
            raise

        first_ts, last_ts, coverage_days, gap_count, gap_bars = (
            AtomicParquetWriter._analyse(df, timeframe_minutes)
        )

        manifest = CacheManifest(
            asset=asset,
            timeframe=timeframe,
            source_url=BINANCE_FUTURES_PUBLIC_KLINES,
            provenance=STRAT01_PROVENANCE,
            download_utc=_utc_now_iso(),
            row_count=len(df),
            first_ts=first_ts,
            last_ts=last_ts,
            coverage_days=coverage_days,
            coverage_years=round(coverage_days / 365.25, 4),
            gap_count=gap_count,
            gap_bars_total=gap_bars,
            sha256=sha256,
            path=str(path),
            timeframe_minutes=timeframe_minutes,
        )

        manifest_path = path.with_suffix(".manifest.json")
        with manifest_path.open("w", encoding="utf-8") as fh:
            json.dump(asdict(manifest), fh, indent=2)

        return manifest

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(str(path), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _analyse(
        df: pd.DataFrame, tf_minutes: int
    ) -> Tuple[str, str, float, int, int]:
        """Return (first_ts, last_ts, coverage_days, gap_count, gap_bars_total)."""
        if df.empty:
            return ("", "", 0.0, 0, 0)

        col = _detect_time_col(df)
        times = pd.to_datetime(df[col], utc=True).sort_values().reset_index(drop=True)

        first_ts = _ts_iso(times.iloc[0])
        last_ts = _ts_iso(times.iloc[-1])
        coverage_days = (
            (times.iloc[-1] - times.iloc[0]).total_seconds() / 86400.0
        )

        expected_ms = tf_minutes * 60 * 1000
        diffs_ms = (
            times.diff()
            .dt.total_seconds()
            .dropna()
            * 1000.0
        )
        gap_mask = diffs_ms > expected_ms * 1.5
        gap_count = int(gap_mask.sum())
        gap_bars = int(
            ((diffs_ms[gap_mask] / expected_ms).astype(int) - 1).sum()
        )

        return first_ts, last_ts, round(coverage_days, 2), gap_count, max(gap_bars, 0)


# ---------------------------------------------------------------------------
# PublicBinanceKlineDownloader
# ---------------------------------------------------------------------------

class PublicBinanceKlineDownloader:
    """
    Downloads OHLCV klines from the Binance Futures public API.

    No authentication is required and no credentials are accepted.
    The returned DataFrame contains only *closed* candles
    (close_time_ms <= until_utc_ms).
    """

    MAX_LIMIT = 1500

    def __init__(
        self,
        base_url: str = BINANCE_FUTURES_PUBLIC_KLINES,
        rate_limit_seconds: float = 0.25,
    ) -> None:
        self._base_url = base_url
        self._rate_limit_seconds = rate_limit_seconds

    def fetch_closed_candles(
        self,
        symbol: str,
        interval: str,
        target_years: float = STRAT01_TARGET_YEARS,
        until_utc_ms: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Fetch historical closed candles for *symbol* from the public Binance
        Futures klines endpoint.

        Columns returned:
            open_time_utc  (datetime64[ns, UTC])
            open, high, low, close, volume  (float64)
            close_time_ms  (int64)
        """
        try:
            import requests  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "requests is required for downloading: pip install requests"
            ) from exc

        now_ms = until_utc_ms if until_utc_ms is not None else int(time.time() * 1000)
        tf_minutes = _interval_to_minutes(interval)
        candle_ms = tf_minutes * 60 * 1000
        target_bars = int(target_years * 365.25 * 24 * 60 / tf_minutes)
        since_ms = now_ms - target_bars * candle_ms

        rows: List = []
        while since_ms < now_ms:
            resp = requests.get(
                self._base_url,
                params={
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "startTime": since_ms,
                    "limit": self.MAX_LIMIT,
                },
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            rows.extend(batch)
            last_open_ms = int(batch[-1][0])
            since_ms = last_open_ms + candle_ms
            if len(batch) < self.MAX_LIMIT:
                break
            time.sleep(self._rate_limit_seconds)

        if not rows:
            return pd.DataFrame(
                columns=["open_time_utc", "open", "high", "low", "close", "volume", "close_time_ms"]
            )

        df = pd.DataFrame(
            [
                (
                    int(r[0]),
                    float(r[1]),
                    float(r[2]),
                    float(r[3]),
                    float(r[4]),
                    float(r[5]),
                    int(r[6]),
                )
                for r in rows
            ],
            columns=["open_time_ms", "open", "high", "low", "close", "volume", "close_time_ms"],
        )
        df["open_time_utc"] = pd.to_datetime(df["open_time_ms"], unit="ms", utc=True)
        df = df.drop(columns=["open_time_ms"])
        df = df[["open_time_utc", "open", "high", "low", "close", "volume", "close_time_ms"]]

        df = ClosedCandleGuard.filter(df, now_utc_ms=now_ms)
        df = df.sort_values("open_time_utc").reset_index(drop=True)
        return df


# ---------------------------------------------------------------------------
# TemporalSplitter
# ---------------------------------------------------------------------------

class TemporalSplitter:
    """
    Defines immutable train / validation / final-OOS temporal boundaries.

    Boundaries are written to a lock file on the first call.  Subsequent
    calls with the same input data hash return the locked boundaries unchanged,
    ensuring the OOS set is never contaminated by strategy selection.
    """

    def __init__(
        self,
        oos_fraction: float = STRAT01_OOS_FRACTION,
        val_fraction: float = STRAT01_VAL_FRACTION,
    ) -> None:
        if oos_fraction < 0.20:
            raise ValueError(f"oos_fraction must be >= 0.20; got {oos_fraction}")
        self._oos_fraction = oos_fraction
        self._val_fraction = val_fraction
        self._train_fraction = 1.0 - oos_fraction - val_fraction

    def compute_splits(
        self,
        manifests: List[CacheManifest],
        lock_path: Optional[Path] = None,
    ) -> TemporalSplitBoundaries:
        """
        Compute temporal splits from manifest date ranges.

        If *lock_path* exists and was produced from the same input data hash,
        the stored boundaries are returned unchanged (immutability guarantee).
        """
        input_hash = self._input_hash(manifests)

        if lock_path is not None:
            lp = Path(lock_path)
            if lp.exists():
                locked = json.loads(lp.read_text(encoding="utf-8"))
                if locked.get("input_hash") == input_hash:
                    return TemporalSplitBoundaries(
                        frozen_at=locked["frozen_at"],
                        input_hash=locked["input_hash"],
                        train_start=locked["train_start"],
                        train_end=locked["train_end"],
                        val_start=locked["val_start"],
                        val_end=locked["val_end"],
                        oos_start=locked["oos_start"],
                        oos_end=locked["oos_end"],
                        oos_fraction_actual=locked["oos_fraction_actual"],
                        oos_fraction_min=locked["oos_fraction_min"],
                        val_fraction_actual=locked["val_fraction_actual"],
                    )

        # Use signal-timeframe manifests to anchor boundaries; fall back to all.
        signal_ms = [m for m in manifests if m.timeframe == STRAT01_SIGNAL_TF] or list(manifests)

        global_first = min(pd.Timestamp(m.first_ts) for m in signal_ms)
        global_last = max(pd.Timestamp(m.last_ts) for m in signal_ms)
        total_sec = (global_last - global_first).total_seconds()

        train_end = global_first + pd.Timedelta(seconds=total_sec * self._train_fraction)
        val_end = train_end + pd.Timedelta(seconds=total_sec * self._val_fraction)
        oos_actual = (global_last - val_end).total_seconds() / total_sec

        splits = TemporalSplitBoundaries(
            frozen_at=_utc_now_iso(),
            input_hash=input_hash,
            train_start=_ts_iso(global_first),
            train_end=_ts_iso(train_end),
            val_start=_ts_iso(train_end),
            val_end=_ts_iso(val_end),
            oos_start=_ts_iso(val_end),
            oos_end=_ts_iso(global_last),
            oos_fraction_actual=round(oos_actual, 4),
            oos_fraction_min=self._oos_fraction,
            val_fraction_actual=round(self._val_fraction, 4),
        )

        if lock_path is not None:
            lp = Path(lock_path)
            lp.parent.mkdir(parents=True, exist_ok=True)
            with lp.open("w", encoding="utf-8") as fh:
                json.dump(asdict(splits), fh, indent=2)

        return splits

    @staticmethod
    def _input_hash(manifests: List[CacheManifest]) -> str:
        entries = sorted(
            (m.asset, m.timeframe, m.first_ts, m.last_ts) for m in manifests
        )
        payload = json.dumps(entries, sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


# ---------------------------------------------------------------------------
# DataSufficiencyAuditor
# ---------------------------------------------------------------------------

class DataSufficiencyAuditor:
    """
    Audits gap counts, date range and target-year sufficiency.

    Never synthesizes missing data.  Insufficient history is reported
    honestly in the audit report.
    """

    def __init__(self, target_years: float = STRAT01_TARGET_YEARS) -> None:
        self._target_years = target_years

    def audit(
        self,
        manifests: List[CacheManifest],
        splits: Optional[TemporalSplitBoundaries] = None,
    ) -> Strat01AuditReport:
        sufficiency: List[Dict] = []
        warnings: List[str] = []
        global_sufficient = True

        for m in manifests:
            sufficient = m.coverage_years >= self._target_years
            if not sufficient:
                global_sufficient = False
                warnings.append(
                    f"{m.asset}/{m.timeframe}: only {m.coverage_years:.3f}y available "
                    f"(target {self._target_years}y); history NOT synthesized"
                )
            if m.gap_count > 0:
                warnings.append(
                    f"{m.asset}/{m.timeframe}: {m.gap_count} gap(s), "
                    f"{m.gap_bars_total} bar(s) missing"
                )

            note = ""
            if not sufficient:
                note = (
                    f"insufficient_history: {m.coverage_years:.3f}y < "
                    f"{self._target_years}y target"
                )

            sufficiency.append(
                asdict(
                    AssetSufficiency(
                        asset=m.asset,
                        timeframe=m.timeframe,
                        coverage_years=m.coverage_years,
                        target_years=self._target_years,
                        sufficient=sufficient,
                        gap_count=m.gap_count,
                        gap_bars_total=m.gap_bars_total,
                        synthetic_substitution=False,
                        note=note,
                    )
                )
            )

        return Strat01AuditReport(
            generated_at=_utc_now_iso(),
            assets_audited=sorted({m.asset for m in manifests}),
            timeframes_audited=sorted({m.timeframe for m in manifests}),
            sufficiency=sufficiency,
            splits=asdict(splits) if splits is not None else None,
            global_sufficient=global_sufficient,
            warnings=warnings,
            synthetic_substitution_used=False,
        )


# ---------------------------------------------------------------------------
# Strat01Pipeline
# ---------------------------------------------------------------------------

class Strat01Pipeline:
    """
    Orchestrates STRAT-01 dataset expansion end-to-end.

    build_from_offline_frames : used offline / in tests (no network calls).
    download_and_build        : downloads from Binance public API.
    """

    def __init__(
        self,
        cache_dir: str = "data/strat01_cache",
        assets: Tuple[str, ...] = STRAT01_ASSETS,
        target_years: float = STRAT01_TARGET_YEARS,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._assets = assets
        self._target_years = target_years
        self._downloader = PublicBinanceKlineDownloader()
        self._splitter = TemporalSplitter()
        self._auditor = DataSufficiencyAuditor(target_years)

    def build_from_offline_frames(
        self,
        signal_frames: Dict[str, pd.DataFrame],
        exec_frames: Dict[str, pd.DataFrame],
    ) -> Strat01AuditReport:
        """Build from pre-loaded frames; no network access required."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        manifests: List[CacheManifest] = []

        for asset, df in signal_frames.items():
            df = ClosedCandleGuard.filter(df)
            path = self._cache_dir / f"{asset}_{STRAT01_SIGNAL_TF}.parquet"
            m = AtomicParquetWriter.write(
                df, path, asset, STRAT01_SIGNAL_TF, STRAT01_SIGNAL_TF_MINUTES
            )
            manifests.append(m)

        for asset, df in exec_frames.items():
            df = ClosedCandleGuard.filter(df)
            path = self._cache_dir / f"{asset}_{STRAT01_EXEC_TF}.parquet"
            m = AtomicParquetWriter.write(
                df, path, asset, STRAT01_EXEC_TF, STRAT01_EXEC_TF_MINUTES
            )
            manifests.append(m)

        lock_path = self._cache_dir / STRAT01_SPLIT_LOCK_FILE
        splits = self._splitter.compute_splits(manifests, lock_path=lock_path)
        report = self._auditor.audit(manifests, splits)

        report_path = self._cache_dir / "strat01_audit_report.json"
        with report_path.open("w", encoding="utf-8") as fh:
            json.dump(asdict(report), fh, indent=2)

        return report

    def download_and_build(self) -> Strat01AuditReport:
        """Download from Binance public API then build cache and audit."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        signal_frames: Dict[str, pd.DataFrame] = {}
        exec_frames: Dict[str, pd.DataFrame] = {}

        for asset in self._assets:
            print(f"[STRAT-01] Downloading {asset} {STRAT01_SIGNAL_TF} ({self._target_years:.0f}y)...")
            signal_frames[asset] = self._downloader.fetch_closed_candles(
                asset, STRAT01_SIGNAL_TF, self._target_years
            )
            print(f"[STRAT-01] Downloading {asset} {STRAT01_EXEC_TF} ({self._target_years:.0f}y)...")
            exec_frames[asset] = self._downloader.fetch_closed_candles(
                asset, STRAT01_EXEC_TF, self._target_years
            )

        return self.build_from_offline_frames(signal_frames, exec_frames)
