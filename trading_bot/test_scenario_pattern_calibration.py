from pathlib import Path
import json
import tempfile

import pandas as pd

import core.scenario_pattern_calibration as spc
from core.scenario_pattern_calibration import (
    ScenarioPatternCalibrationSettings,
    build_scenario_pattern_calibration_report,
    write_scenario_pattern_calibration_report,
)


def _sample_ohlcv(rows: int = 520) -> pd.DataFrame:
    data = []
    price = 100.0
    for i in range(rows):
        drift = ((i % 40) - 20) * 0.001
        open_ = price
        close = max(1.0, price * (1.0 + drift / 100.0))
        high = max(open_, close) * 1.002
        low = min(open_, close) * (0.995 if i % 13 == 0 else 0.998)
        volume = 1000 + (i % 17) * 15
        data.append({"datetime": f"2026-01-01T00:{i % 60:02d}:00Z", "Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume})
        price = close
    return pd.DataFrame(data)


def main():
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        fake_cache = data_dir / "btcusdt_5m_150k_cache.parquet"
        fake_cache.write_text("synthetic", encoding="utf-8")
        original_cache_path = spc._cache_path_for_symbol
        original_read_cache = spc._read_cache
        try:
            spc._cache_path_for_symbol = lambda data_dir_arg, symbol, timeframe: fake_cache if symbol == "BTC/USDT" else None
            spc._read_cache = lambda path: _sample_ohlcv()
            settings = ScenarioPatternCalibrationSettings(
                symbols=("BTC/USDT",),
                max_rows_per_asset=520,
                min_warmup_rows=80,
                eval_stride=5,
                min_bucket_candidates=1,
                min_profile_candidates=1,
                score_thresholds=(40.0, 50.0, 60.0),
            )
            report = build_scenario_pattern_calibration_report(data_dir, settings)
            assert report["prompt"] == "29.5.0d"
            assert report["safety"]["diagnostic_only"] is True
            assert report["safety"]["opens_orders"] is False
            assert "bucket_ranking" in report
            assert "focus_profile_threshold_grid" in report
            written = write_scenario_pattern_calibration_report(data_dir, settings)
        finally:
            spc._cache_path_for_symbol = original_cache_path
            spc._read_cache = original_read_cache
        path = data_dir / "scenario_pattern_calibration_report.json"
        assert path.exists()
        payload = json.loads(path.read_text())
        assert payload["counts"]["orders_submitted"] == 0
        assert written["files"]["report"].endswith("scenario_pattern_calibration_report.json")
    print("Scenario-pattern calibration tests passed.")


if __name__ == "__main__":
    main()
