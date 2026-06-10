"""
STRAT-01 mandatory tests.

Covers the six required test IDs from the STRATEGY_RESEARCH_ROADMAP § STRAT-01:
    test_public_data_only_no_credentials
    test_closed_candles_only
    test_atomic_cache_and_manifest_hashes
    test_temporal_split_final_oos_untouched
    test_gap_and_range_audit
    test_insufficient_history_reported_honestly

All tests are fully offline: no network access, no credentials, no bot startup.
Synthetic frames are used solely to exercise the infrastructure contracts.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "trading_bot")):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.research_dataset import (
    BINANCE_FUTURES_PUBLIC_KLINES,
    STRAT01_EXEC_TF,
    STRAT01_EXEC_TF_MINUTES,
    STRAT01_OOS_FRACTION,
    STRAT01_PROVENANCE,
    STRAT01_SIGNAL_TF,
    STRAT01_SIGNAL_TF_MINUTES,
    STRAT01_TARGET_YEARS,
    AtomicParquetWriter,
    CacheManifest,
    ClosedCandleGuard,
    DataSufficiencyAuditor,
    PublicBinanceKlineDownloader,
    TemporalSplitter,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_ohlcv_frame(
    rows: int = 1000,
    tf_minutes: int = 15,
    start: str = "2021-01-01",
    include_close_time: bool = False,
    add_future_candle: bool = False,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a minimal OHLCV frame for tests (no strategy logic, no real data)."""
    rng = np.random.default_rng(seed)
    start_ms = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    candle_ms = tf_minutes * 60 * 1000

    open_times_ms = [start_ms + i * candle_ms for i in range(rows)]
    close_times_ms = [t + candle_ms - 1 for t in open_times_ms]

    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.002, rows)))
    df = pd.DataFrame(
        {
            "open_time_utc": pd.to_datetime(open_times_ms, unit="ms", utc=True),
            "open": closes * (1.0 + rng.normal(0, 0.001, rows)),
            "high": closes * (1.0 + np.abs(rng.normal(0, 0.003, rows))),
            "low": closes * (1.0 - np.abs(rng.normal(0, 0.003, rows))),
            "close": closes,
            "volume": rng.lognormal(8.0, 0.5, rows),
        }
    )

    if include_close_time or add_future_candle:
        df["close_time_ms"] = close_times_ms
        if add_future_candle:
            future_open_ms = open_times_ms[-1] + candle_ms
            future_close_ms = future_open_ms + candle_ms - 1
            future_row = pd.DataFrame(
                {
                    "open_time_utc": [
                        pd.Timestamp(future_open_ms, unit="ms", tz="UTC")
                    ],
                    "open": [closes[-1]],
                    "high": [closes[-1] * 1.002],
                    "low": [closes[-1] * 0.998],
                    "close": [closes[-1] * 1.001],
                    "volume": [1000.0],
                    "close_time_ms": [future_close_ms],
                }
            )
            df = pd.concat([df, future_row], ignore_index=True)

    return df


def _make_manifest(
    asset: str = "BTCUSDT",
    timeframe: str = "15m",
    first_ts: str = "2020-01-01T00:00:00+00:00",
    last_ts: str = "2025-01-01T00:00:00+00:00",
    coverage_years: float = 5.0,
    gap_count: int = 0,
    gap_bars_total: int = 0,
) -> CacheManifest:
    return CacheManifest(
        asset=asset,
        timeframe=timeframe,
        source_url=BINANCE_FUTURES_PUBLIC_KLINES,
        provenance=STRAT01_PROVENANCE,
        download_utc="2026-06-09T00:00:00+00:00",
        row_count=175200,
        first_ts=first_ts,
        last_ts=last_ts,
        coverage_days=round(coverage_years * 365.25, 2),
        coverage_years=coverage_years,
        gap_count=gap_count,
        gap_bars_total=gap_bars_total,
        sha256="placeholder",
        path="/placeholder",
        timeframe_minutes=15 if timeframe == "15m" else 5,
    )


# ---------------------------------------------------------------------------
# test_public_data_only_no_credentials
# ---------------------------------------------------------------------------

def test_public_data_only_no_credentials() -> None:
    """PublicBinanceKlineDownloader must not accept or store any credentials."""
    downloader = PublicBinanceKlineDownloader()

    # No credential attributes on the instance
    for attr in ("api_key", "api_secret", "secret", "key", "credentials", "auth"):
        assert not hasattr(downloader, attr), (
            f"Unexpected credential attribute on downloader: '{attr}'"
        )

    # Constructor signature must not accept credential parameters
    sig = inspect.signature(PublicBinanceKlineDownloader.__init__)
    param_names = set(sig.parameters.keys()) - {"self"}
    for cred_param in ("api_key", "api_secret", "secret", "credentials", "token"):
        assert cred_param not in param_names, (
            f"Constructor accepts credential parameter: '{cred_param}'"
        )

    # The base URL is public Binance (no embedded auth or API key)
    assert "fapi.binance.com" in downloader._base_url
    assert "apiKey" not in downloader._base_url
    assert "secret" not in downloader._base_url.lower()
    assert downloader._base_url.startswith("https://")


# ---------------------------------------------------------------------------
# test_closed_candles_only
# ---------------------------------------------------------------------------

def test_closed_candles_only() -> None:
    """ClosedCandleGuard must drop the current (future close_time_ms) candle."""
    now_ms = int(time.time() * 1000)
    candle_ms = 15 * 60 * 1000
    start = pd.Timestamp(now_ms - 100 * candle_ms, unit="ms", tz="UTC").isoformat()

    df = _make_ohlcv_frame(
        rows=100,
        tf_minutes=15,
        start=start,
        include_close_time=True,
        add_future_candle=True,
    )

    # 100 historical + 1 future = 101 rows
    assert len(df) == 101

    # Last row's close_time_ms is in the future
    assert df["close_time_ms"].iloc[-1] > now_ms

    # Guard drops the open candle
    filtered = ClosedCandleGuard.filter(df, now_utc_ms=now_ms)
    assert len(filtered) == 100, (
        f"Expected 100 closed candles; got {len(filtered)}"
    )
    assert (filtered["close_time_ms"] <= now_ms).all()

    # All kept candles have close_time_ms strictly in the past
    assert filtered["close_time_ms"].max() <= now_ms

    # Without close_time_ms column: all rows pass through unmodified
    df_no_ct = df.drop(columns=["close_time_ms"])
    filtered_no_ct = ClosedCandleGuard.filter(df_no_ct, now_utc_ms=now_ms)
    assert len(filtered_no_ct) == 101


# ---------------------------------------------------------------------------
# test_atomic_cache_and_manifest_hashes
# ---------------------------------------------------------------------------

def test_atomic_cache_and_manifest_hashes() -> None:
    """AtomicParquetWriter produces a file with matching SHA-256 and manifest."""
    df = _make_ohlcv_frame(rows=500, tf_minutes=15)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "BTCUSDT_15m.parquet"
        manifest = AtomicParquetWriter.write(
            df, path, "BTCUSDT", "15m", STRAT01_SIGNAL_TF_MINUTES
        )

        # Target file exists at declared path
        assert path.exists(), "Parquet file not found at declared path"

        # No temp file left behind
        orphans = list(Path(tmpdir).glob("*.tmp.parquet"))
        assert len(orphans) == 0, f"Temp file(s) not cleaned up: {orphans}"

        # Manifest JSON exists alongside the parquet
        manifest_json_path = path.with_suffix(".manifest.json")
        assert manifest_json_path.exists(), "Manifest JSON not found"

        # SHA-256 in manifest matches the actual file content
        h = hashlib.sha256()
        with open(str(path), "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        assert h.hexdigest() == manifest.sha256, (
            "SHA-256 in manifest does not match actual file content"
        )

        # Row count is accurate
        assert manifest.row_count == len(df)

        # Provenance and source URL are set to public API constants
        assert manifest.provenance == STRAT01_PROVENANCE
        assert "fapi.binance.com" in manifest.source_url

        # Manifest JSON is self-consistent
        manifest_data = json.loads(manifest_json_path.read_text(encoding="utf-8"))
        assert manifest_data["sha256"] == manifest.sha256
        assert manifest_data["row_count"] == manifest.row_count
        assert manifest_data["provenance"] == STRAT01_PROVENANCE

        # Coverage is positive and plausible
        assert manifest.coverage_days > 0
        assert manifest.coverage_years > 0


# ---------------------------------------------------------------------------
# test_temporal_split_final_oos_untouched
# ---------------------------------------------------------------------------

def test_temporal_split_final_oos_untouched() -> None:
    """OOS fraction >= 20%, temporal order is correct, splits are immutable."""
    manifests = [
        _make_manifest("BTCUSDT", "15m", "2020-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00", 5.0),
        _make_manifest("ETHUSDT", "15m", "2020-01-01T00:00:00+00:00", "2025-01-01T00:00:00+00:00", 5.0),
    ]

    splitter = TemporalSplitter(oos_fraction=0.20, val_fraction=0.20)

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "splits.json"

        splits = splitter.compute_splits(manifests, lock_path=lock_path)

        # OOS fraction meets minimum requirement
        assert splits.oos_fraction_actual >= STRAT01_OOS_FRACTION, (
            f"OOS fraction {splits.oos_fraction_actual:.4f} < minimum {STRAT01_OOS_FRACTION}"
        )

        # Temporal order: train < val < oos
        t_train_end = pd.Timestamp(splits.train_end)
        t_val_start = pd.Timestamp(splits.val_start)
        t_val_end = pd.Timestamp(splits.val_end)
        t_oos_start = pd.Timestamp(splits.oos_start)
        t_oos_end = pd.Timestamp(splits.oos_end)

        assert t_val_start <= t_train_end, "Val must start at or after train end"
        assert t_oos_start <= t_val_end, "OOS must start at or after val end"
        assert t_oos_end > t_oos_start, "OOS range must be non-empty"

        # OOS is after both train and val
        assert t_oos_start > pd.Timestamp(splits.train_start)

        # Lock file written
        assert lock_path.exists(), "Split lock file was not created"

        # Second call with same data returns identical splits (immutability)
        splits2 = splitter.compute_splits(manifests, lock_path=lock_path)
        assert splits2.train_start == splits.train_start
        assert splits2.train_end == splits.train_end
        assert splits2.val_start == splits.val_start
        assert splits2.val_end == splits.val_end
        assert splits2.oos_start == splits.oos_start
        assert splits2.oos_end == splits.oos_end
        assert splits2.oos_fraction_actual == splits.oos_fraction_actual
        assert splits2.input_hash == splits.input_hash


# ---------------------------------------------------------------------------
# test_gap_and_range_audit
# ---------------------------------------------------------------------------

def test_gap_and_range_audit() -> None:
    """AtomicParquetWriter counts gaps accurately; auditor reports without synthesis."""
    tf_minutes = 15
    candle_ms = tf_minutes * 60 * 1000
    start_ms = int(pd.Timestamp("2022-01-01", tz="UTC").timestamp() * 1000)
    n = 200

    # Build a uniform bar sequence then remove specific bars to create known gaps:
    #   Gap 1: remove bars at indices 51 and 52  → 2 missing bars
    #   Gap 2: remove bars at indices 101, 102, 103 → 3 missing bars
    # Total: 2 gaps, 5 missing bars.
    all_open_times = [start_ms + i * candle_ms for i in range(n)]
    remove_indices = set(range(51, 53)) | set(range(101, 104))
    open_times = [t for i, t in enumerate(all_open_times) if i not in remove_indices]

    m = len(open_times)
    df = pd.DataFrame(
        {
            "open_time_utc": pd.to_datetime(open_times, unit="ms", utc=True),
            "open": np.full(m, 100.0),
            "high": np.full(m, 101.0),
            "low": np.full(m, 99.0),
            "close": np.full(m, 100.5),
            "volume": np.full(m, 1000.0),
            "close_time_ms": [t + candle_ms - 1 for t in open_times],
        }
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "BTCUSDT_15m.parquet"
        manifest = AtomicParquetWriter.write(
            df, path, "BTCUSDT", "15m", tf_minutes
        )

        assert manifest.gap_count == 2, (
            f"Expected 2 gaps, got {manifest.gap_count}"
        )
        assert manifest.gap_bars_total == 5, (
            f"Expected 5 missing bars, got {manifest.gap_bars_total}"
        )

        auditor = DataSufficiencyAuditor(target_years=4.0)
        report = auditor.audit([manifest])

        # Audit reports gaps honestly; no synthesis
        assert report.synthetic_substitution_used is False
        gap_entry = report.sufficiency[0]
        assert gap_entry["gap_count"] == 2
        assert gap_entry["gap_bars_total"] == 5
        assert gap_entry["synthetic_substitution"] is False

        # Gap warning appears in report
        assert any("gap" in w.lower() for w in report.warnings)


# ---------------------------------------------------------------------------
# test_insufficient_history_reported_honestly
# ---------------------------------------------------------------------------

def test_insufficient_history_reported_honestly() -> None:
    """Auditor reports < 4y coverage honestly; row count unmodified, no synthesis."""
    # 2 years of 15m bars (well below 4-year target)
    two_year_rows = int(2 * 365.25 * 24 * 4)
    df = _make_ohlcv_frame(rows=two_year_rows, tf_minutes=15, start="2023-01-01")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "XRPUSDT_15m.parquet"
        manifest = AtomicParquetWriter.write(
            df, path, "XRPUSDT", "15m", STRAT01_SIGNAL_TF_MINUTES
        )

        # Coverage is genuinely less than 4 years
        assert manifest.coverage_years < STRAT01_TARGET_YEARS, (
            f"Expected < {STRAT01_TARGET_YEARS}y; got {manifest.coverage_years}y"
        )

        # Row count is the real count, not padded
        assert manifest.row_count == len(df)

        auditor = DataSufficiencyAuditor(target_years=STRAT01_TARGET_YEARS)
        report = auditor.audit([manifest])

        # Global sufficiency flag is False
        assert report.global_sufficient is False

        # No synthetic substitution
        assert report.synthetic_substitution_used is False
        for entry in report.sufficiency:
            assert entry["synthetic_substitution"] is False

        # Warning mentions "NOT synthesized" or "insufficient"
        combined_warnings = " ".join(report.warnings).lower()
        assert "not synthesized" in combined_warnings or "insufficient" in combined_warnings

        # Per-asset entry has correct flags
        xrp_entry = next(
            s for s in report.sufficiency if s["asset"] == "XRPUSDT"
        )
        assert xrp_entry["sufficient"] is False
        assert xrp_entry["coverage_years"] < STRAT01_TARGET_YEARS
        assert "insufficient_history" in xrp_entry["note"]
        assert xrp_entry["synthetic_substitution"] is False
