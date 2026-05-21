from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl

from core.market_structure_features import MarketStructureFeatureBuilder, MarketStructureConfig
from core.multi_asset_dataset import DatasetBuildConfig, MultiAssetDatasetBuilder
from core.training_dataset_loader import MultiAssetTrainingDatasetLoader


def _candles(asset: str, rows: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(abs(hash(asset)) % 10_000)
    dt = pd.date_range("2024-01-01", periods=rows, freq="15min", tz="UTC")
    base = 65000 if asset == "BTCUSDT" else 2500
    close = base * np.exp(np.cumsum(rng.normal(0.0, 0.002, rows)))
    spread = close * 0.001
    return pd.DataFrame({
        "datetime": dt,
        "Open": close * (1 + rng.normal(0, 0.0004, rows)),
        "High": close + spread,
        "Low": close - spread,
        "Close": close,
        "Volume": rng.lognormal(9, 0.4, rows),
    })


def test_market_structure_builder_basic() -> None:
    builder = MultiAssetDatasetBuilder(DatasetBuildConfig(output_dir=tempfile.mkdtemp(), min_total_ml_samples=10, min_regime_samples=1))
    candles, _ = builder.normalize_ohlcv(_candles("BTCUSDT"), "BTCUSDT")
    base_features = builder.build_features(candles)
    required = {
        "realized_vol_1d_ms",
        "volatility_compression",
        "htf_4h_return",
        "session_london",
        "liquidity_sweep_score",
        "btc_return_1",
        "funding_available",
        "open_interest_available",
        "btc_dominance_available",
    }
    missing = required.difference(base_features.columns)
    assert not missing, f"missing market structure features: {missing}"
    assert base_features["datetime"].is_sorted()


def test_external_macro_asof_merge() -> None:
    candles = pl.from_pandas(_candles("BTCUSDT", 100).assign(asset="BTCUSDT"))
    funding = pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=10, freq="8h", tz="UTC"),
        "asset": "BTCUSDT",
        "funding_rate": np.linspace(-0.0001, 0.0002, 10),
        "funding_available": 1.0,
    })
    enriched, report = MarketStructureFeatureBuilder().enrich(candles, {"funding": funding})
    assert report.external_sources["funding"] is True
    assert "funding_rate" in enriched.columns
    assert float(enriched["funding_available"].max()) == 1.0


def test_training_loader_preserves_macro_features() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = DatasetBuildConfig(output_dir=str(Path(td) / "datasets"), min_total_ml_samples=10, min_regime_samples=1, label_horizon=20)
        report = MultiAssetDatasetBuilder(cfg).build_from_frames({"BTCUSDT": _candles("BTCUSDT", 700), "ETHUSDT": _candles("ETHUSDT", 700)})
        source = Path(report.output_files["meta_label_dataset"])
        df, train_report = MultiAssetTrainingDatasetLoader.load_expanded_training_dataset(
            source_path=str(source),
            output_path=str(Path(td) / "market_features.parquet"),
            report_path=str(Path(td) / "training_dataset_report.json"),
            min_samples=10,
        )
        assert len(df) > 10
        macro_report = Path("data/macro_feature_training_report.json")
        assert train_report.rows_after_cleaning == len(df)


def main() -> None:
    test_market_structure_builder_basic()
    test_external_macro_asof_merge()
    test_training_loader_preserves_macro_features()
    print("Market structure feature tests passed.")


if __name__ == "__main__":
    main()
