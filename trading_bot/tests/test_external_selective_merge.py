from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

if "config" not in sys.modules:
    config_mod = types.ModuleType("config")

    class Config:  # minimal stub for candlestick diagnostics
        PAPER_CANDLESTICK_PATTERNS_ENABLED = True
        CANDLE_PATTERN_MIN_BODY_RATIO = 0.25
        CANDLE_PATTERN_STRONG_BODY_RATIO = 0.55
        CANDLE_PATTERN_DOJI_BODY_RATIO = 0.12
        CANDLE_PATTERN_WICK_RATIO = 0.45
        CANDLE_PATTERN_PIN_WICK_TO_BODY = 2.0
        CANDLE_PATTERN_INSIDE_TOLERANCE_PCT = 0.0
        CANDLE_PATTERN_OUTSIDE_TOLERANCE_PCT = 0.0
        CANDLE_PATTERN_OPPOSITE_WICK_MAX_RATIO = 0.10
        CANDLE_PATTERN_ENGULFING_BODY_MULTIPLIER = 1.05
        CANDLE_PATTERN_RECLAIM_BUFFER_PCT = 0.0003
        CANDLE_PATTERN_RETEST_TOLERANCE_PCT = 0.0015
        CANDLE_PATTERN_VOLUME_RATIO_THRESHOLD = 1.10
        CRYPTO_SCENARIO_SR_PROXIMITY_PCT = 0.0035

    config_mod.Config = Config
    sys.modules["config"] = config_mod


def test_candlestick_conflicting_fake_breakout_breakdown_reclaims_are_neutralized() -> None:
    from candlestick_patterns import detect_candlestick_patterns

    df = pd.DataFrame(
        [
            {"Open": 104.0, "High": 106.0, "Low": 102.0, "Close": 103.0, "Volume": 100.0},
            {"Open": 103.0, "High": 107.0, "Low": 101.0, "Close": 104.0, "Volume": 100.0},
            {
                "Open": 105.0,
                "High": 115.0,
                "Low": 95.0,
                "Close": 105.0,
                "Volume": 120.0,
                "local_support": 100.0,
                "local_resistance": 110.0,
                "near_support": True,
                "near_resistance": True,
                "range_pos_400": 0.50,
            },
        ]
    )
    result = detect_candlestick_patterns(df, symbol="BTC/USDT")

    assert "fake_breakdown_reclaim" in result.bullish_patterns
    assert "fake_breakout_reclaim" in result.bearish_patterns
    assert result.pattern_bias == "HOLD"
    assert result.pattern_score <= 15.0
    assert result.scenario_integration == "CONFLICTING_CANDLE_PATTERNS_NEUTRALIZED"
    assert result.context["directional_conflict"] is True
    assert result.context["conflict_reason"] == "bullish_and_bearish_patterns_coexist"


def test_correlation_engine_uses_modern_fill_and_safe_diagonal_assignment() -> None:
    from correlation_engine import CorrelationEngine

    engine = CorrelationEngine(assets=["BTC", "ETH"])
    idx = pd.date_range("2026-01-01", periods=6, freq="min")
    engine.update_prices("BTC", idx, pd.Series([100, 101, 102, 103, 104, 105]))
    engine.update_prices("ETH", idx, pd.Series([200, 201, 201, 202, 203, 204]))

    returns = engine.calculate_returns()
    corr = engine.get_correlation_matrix(returns, window=5)

    assert list(corr.index) == ["BTC", "ETH"]
    assert corr.iloc[0, 0] == 1.0
    assert corr.iloc[1, 1] == 1.0


def test_notifier_close_cancels_polling_task_without_leaking_session() -> None:
    from notifier import Notifier

    async def scenario() -> None:
        notifier = Notifier()
        task = asyncio.create_task(asyncio.sleep(60))
        notifier._polling_task = task
        await notifier.close()
        assert notifier._polling_task is None
        assert task.cancelled()

    asyncio.run(scenario())


def test_main_keeps_live_indicator_windowing_and_log_rotation() -> None:
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "def append_to_log_with_rotation" in source
    assert "append_to_log_with_rotation(log_file, log_line)" in source
    assert 'with open(log_file, "a", encoding="utf-8") as lf' not in source.replace(
        '        with open(log_file, "a", encoding="utf-8") as lf:\n            lf.write(line)',
        "",
    )
    assert "TechnicalAnalyzer().add_indicators(df, is_live=True)" in source
