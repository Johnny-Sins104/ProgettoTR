import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from core.multi_asset_dataset import MultiAssetDatasetBuilder, DatasetBuildConfig
from core.training_dataset_loader import MultiAssetTrainingDatasetLoader
from core.regime_model_manager import FEATURE_NAMES


def _synthetic_asset(asset: str, rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dt = pd.date_range("2024-01-01", periods=rows, freq="15min", tz="UTC")
    returns = rng.normal(0, 0.0015, rows)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + rng.uniform(0.0002, 0.0020, rows))
    low = close * (1 - rng.uniform(0.0002, 0.0020, rows))
    open_ = close * (1 + rng.normal(0, 0.0004, rows))
    vol = rng.uniform(1000, 5000, rows)
    return pd.DataFrame({"datetime": dt, "Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol})


def main():
    with tempfile.TemporaryDirectory() as td:
        dataset_dir = Path(td) / "datasets"
        builder = MultiAssetDatasetBuilder(DatasetBuildConfig(output_dir=str(dataset_dir), min_total_ml_samples=50, min_regime_samples=5))
        builder.build_from_frames({
            "BTCUSDT": _synthetic_asset("BTCUSDT", 900, 1),
            "ETHUSDT": _synthetic_asset("ETHUSDT", 900, 2),
        })
        source = dataset_dir / "meta_label_dataset.parquet"
        output = Path(td) / "market_features.parquet"
        report_path = Path(td) / "training_dataset_report.json"
        df, report = MultiAssetTrainingDatasetLoader.load_expanded_training_dataset(
            source_path=str(source),
            output_path=str(output),
            report_path=str(report_path),
            min_samples=50,
        )
        assert output.exists(), "compatible parquet was not written"
        assert report_path.exists(), "training report was not written"
        assert len(df) == report.rows_after_cleaning
        assert len(df) >= 50
        assert set(FEATURE_NAMES + ["outcome"]).issubset(df.columns)
        assert set(df["outcome"].unique()).issubset({0, 1})
        assert report.per_asset_counts.get("BTCUSDT", 0) > 0
        assert report.per_asset_counts.get("ETHUSDT", 0) > 0
    print("Multi-asset training loader tests passed.")


if __name__ == "__main__":
    main()
