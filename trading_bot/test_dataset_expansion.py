from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from core.multi_asset_dataset import DatasetBuildConfig, MultiAssetDatasetBuilder


def make_frame(rows: int = 1200, start: str = "2023-01-01", seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dt = pd.date_range(pd.Timestamp(start, tz="UTC"), periods=rows, freq="15min")
    close = 100 * np.exp(np.cumsum(rng.normal(0.0, 0.003, rows)))
    high = close * (1 + rng.uniform(0.0005, 0.002, rows))
    low = close * (1 - rng.uniform(0.0005, 0.002, rows))
    open_ = close * (1 + rng.normal(0.0, 0.0005, rows))
    vol = rng.lognormal(8, 0.5, rows)
    return pd.DataFrame({"datetime": dt, "Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol})


def test_builder_outputs_reports_and_parquet() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = DatasetBuildConfig(
            assets=("BTCUSDT", "ETHUSDT"),
            output_dir=td,
            min_total_ml_samples=10,
            min_regime_samples=1,
            min_asset_years=0.01,
            label_horizon=24,
        )
        builder = MultiAssetDatasetBuilder(cfg)
        report = builder.build_from_frames({"BTCUSDT": make_frame(seed=1), "ETHUSDT": make_frame(seed=2)})
        assert report.total_candles == 2400
        assert report.total_features == 2400
        assert report.total_candidates > 0
        assert report.total_meta_labels > 0
        for rel in [
            "dataset_summary.json",
            "regime_balance_report.json",
            "asset_coverage_report.json",
            "feature_integrity_report.json",
            "feature_distribution_reports/feature_distribution_summary.json",
        ]:
            assert (Path(td) / rel).exists(), rel
        for key in ["candles", "market_features", "candidate_trades", "meta_label_dataset", "regime_tagged_dataset"]:
            assert Path(report.output_files[key]).exists(), key
        meta = pl.read_parquet(report.output_files["meta_label_dataset"])
        assert "label_end_time" in meta.columns
        assert "outcome" in meta.columns


def test_duplicate_and_missing_timestamp_detection() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = DatasetBuildConfig(output_dir=td, min_asset_years=0.0)
        builder = MultiAssetDatasetBuilder(cfg)
        df = make_frame(rows=200)
        df = pd.concat([df.iloc[:50], df.iloc[[49]], df.iloc[52:]], ignore_index=True)  # duplicate + gap
        normalized, quality = builder.normalize_ohlcv(df, "BTCUSDT")
        assert normalized.height == 198
        assert quality.duplicate_timestamps_removed == 1
        assert quality.missing_timestamp_count >= 2


def test_reports_warn_on_small_dataset() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = DatasetBuildConfig(output_dir=td, min_total_ml_samples=999999, min_regime_samples=999999, min_asset_years=99)
        builder = MultiAssetDatasetBuilder(cfg)
        report = builder.build_from_frames({"BTCUSDT": make_frame(rows=500)})
        joined = "\n".join(report.warnings)
        assert "total_ml_samples_below_minimum" in joined
        assert "coverage_below_min_years" in joined
        summary = json.loads((Path(td) / "dataset_summary.json").read_text())
        assert summary["total_candles"] == 500


if __name__ == "__main__":
    test_builder_outputs_reports_and_parquet()
    test_duplicate_and_missing_timestamp_detection()
    test_reports_warn_on_small_dataset()
    print("Dataset expansion tests passed.")
