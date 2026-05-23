from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.market_structure_map import (
    EVENT_TYPE,
    MarketStructureMapSettings,
    build_market_structure_map_diagnostic,
    build_market_structure_map_report,
    evaluate_market_structure_map,
)


def _sample_df() -> pd.DataFrame:
    rows = []
    close = 100.0
    for i in range(80):
        # Causal zig-zag with repeated highs/lows and a final break/retest area.
        phase = i % 12
        if phase < 6:
            close += 1.3
        else:
            close -= 1.1
        open_ = close - (0.4 if phase < 6 else -0.3)
        high = max(open_, close) + (1.0 if phase in {5, 6} else 0.45)
        low = min(open_, close) - (1.0 if phase in {0, 11} else 0.45)
        rows.append({"datetime": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=5 * i), "Open": open_, "High": high, "Low": low, "Close": close, "Volume": 1000 + i})
    # Force a recent bullish close through prior swing-high region.
    rows[-1]["Close"] = rows[-2]["High"] + 2.0
    rows[-1]["High"] = rows[-1]["Close"] + 0.8
    rows[-1]["Low"] = rows[-2]["High"] - 0.2
    return pd.DataFrame(rows)


def test_market_structure_map_evaluates_core_contract() -> None:
    settings = MarketStructureMapSettings(swing_left=2, swing_right=1, min_warmup_rows=20, eval_stride=10)
    result = evaluate_market_structure_map(_sample_df(), symbol="BTC/USDT", settings=settings)
    payload = result.to_dict()
    assert payload["diagnostic_only"] is True
    assert payload["strategy_changed"] is False
    assert payload["operational_unlock_allowed"] is False
    assert "structure_bias" in payload
    assert "nearest_liquidity" in payload
    assert "demand_zone_low" in payload
    assert "supply_zone_high" in payload
    assert "confirmation_summary" in payload
    assert isinstance(payload["swing_sequence"], list)


def test_market_structure_map_diagnostic_event_shape() -> None:
    diag = build_market_structure_map_diagnostic(symbol="BTC/USDT", df=_sample_df(), cycle_id="c1", candle_ts="t1")
    assert diag["event_type"] == EVENT_TYPE
    assert diag["diagnostic_only"] is True
    assert diag["operational_unlock_allowed"] is False
    assert "bos_bullish" in diag
    assert "missing_confirmation" in diag


def test_market_structure_map_report_empty_dir_is_safe(tmp_path: Path) -> None:
    report = build_market_structure_map_report(tmp_path, settings=MarketStructureMapSettings(symbols=("BTC/USDT",), historical_enabled=True, max_rows_per_asset=200))
    assert report["diagnostic_only"] is True
    assert report["opens_orders"] is False
    assert report["enables_live_or_testnet"] is False
    assert report["decision"]["operational_unlock_allowed"] is False


if __name__ == "__main__":
    test_market_structure_map_evaluates_core_contract()
    test_market_structure_map_diagnostic_event_shape()
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        test_market_structure_map_report_empty_dir_is_safe(Path(d))
    print("Market structure map tests passed.")
