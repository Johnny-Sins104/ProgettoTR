"""Prompt 29.4.4s-1 signal/risk correctness hardening tests.

These tests guard the bug class found during the post-29.4.4s audit:
ambiguous candles must not become high-confidence directional signals, Kelly must
not fall back to profile risk when it finds no edge, and configuration/calibration
must fail closed rather than silently using unsafe assumptions.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from config import Config
from core.calibration import ProbabilityCalibrator
from core.candlestick_patterns import detect_candlestick_patterns
from core.paper_unlock_gate import PaperUnlockGateSettings, evaluate_paper_unlock
from core.risk import DynamicRiskEngine
from core.setup_engine import MarketStructureSetupEngine


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_high_wave_doji_is_neutral_not_hammer_and_shooting_star() -> None:
    df = _df([
        {"Open": 100.0, "High": 102.0, "Low": 98.0, "Close": 101.0, "Volume": 100.0},
        {"Open": 100.0, "High": 110.0, "Low": 90.0, "Close": 100.05, "Volume": 1000.0},
    ])
    result = detect_candlestick_patterns(df)
    assert result.pattern_bias == "HOLD"
    assert result.pattern_score <= 25.0
    assert "high_wave_doji" in result.neutral_patterns
    assert "hammer" not in result.bullish_patterns
    assert "shooting_star" not in result.bearish_patterns


def test_engulfing_requires_full_body_expansion() -> None:
    df = _df([
        {"Open": 110.0, "High": 111.0, "Low": 99.0, "Close": 100.0, "Volume": 100.0},
        {"Open": 101.0, "High": 110.0, "Low": 100.0, "Close": 109.0, "Volume": 100.0},
    ])
    result = detect_candlestick_patterns(df)
    assert "bullish_engulfing" not in result.bullish_patterns


def test_volume_ratio_excludes_current_candle_from_average() -> None:
    rows = [
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 100.0}
        for _ in range(20)
    ]
    rows.append({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 10000.0})
    result = detect_candlestick_patterns(_df(rows))
    assert math.isclose(result.candle_metrics["volume_ratio_20"], 100.0, rel_tol=1e-6)


def test_calibration_min_samples_are_conservative() -> None:
    assert ProbabilityCalibrator._MIN_SAMPLES["isotonic"] >= 300
    assert ProbabilityCalibrator._MIN_SAMPLES["sigmoid"] >= 50


def test_kelly_no_edge_returns_zero_risk_not_profile_default() -> None:
    old = Config.USE_KELLY_SIZING
    Config.USE_KELLY_SIZING = True
    try:
        engine = DynamicRiskEngine()
        size, snap = engine.size_position(
            balance=1000.0,
            entry_price=100.0,
            sl_price=99.0,
            side="BUY",
            regime="RANGING",
            ai_prob=40.0,
            rr_ratio=1.0,
        )
        assert size == 0.0
        assert snap.final_risk_pct == 0.0
        assert snap.capped_kelly == 0.0
    finally:
        Config.USE_KELLY_SIZING = old


def test_paper_unlock_profile_is_not_hardcoded_to_legacy_name() -> None:
    settings = PaperUnlockGateSettings(
        enabled=True,
        profile="MAP_SCORE_65_79_REPAIRED_STABILITY_V1",
        allowed_symbols=("BTC/USDT",),
        allowed_filters=("META_PROB_LOW",),
        min_ai_prob=40.0,
        min_setup_quality=60.0,
        require_tech_gate=False,
        max_positions=1,
    )
    decision = evaluate_paper_unlock(
        settings=settings,
        signal_diagnostic={
            "intended_side": "BUY",
            "dominant_filter": "META_PROB_LOW",
            "ai_prob": 45.0,
            "setup_quality": 70.0,
            "technical_score": 10.0,
            "thresholds": {"active_score_threshold": 0.0},
        },
        symbol="BTC/USDT",
        mode="paper",
    )
    assert not decision.reason.startswith("unsupported_profile")


def test_near_sr_does_not_mark_support_and_resistance_at_same_time() -> None:
    base = {"market_regime": "RANGING", "near_sr": 1.0, "rsi_14": 50.0}
    _, buy_low_score, buy_low_reasons, _ = MarketStructureSetupEngine._ranging_mean_reversion({**base, "bb_position": 0.20}, "BUY")
    _, sell_low_score, sell_low_reasons, _ = MarketStructureSetupEngine._ranging_mean_reversion({**base, "bb_position": 0.20}, "SELL")
    _, sell_high_score, sell_high_reasons, _ = MarketStructureSetupEngine._ranging_mean_reversion({**base, "bb_position": 0.80}, "SELL")
    assert "lower_band_reversion" in buy_low_reasons
    assert "upper_band_reversion" not in sell_low_reasons
    assert "upper_band_reversion" in sell_high_reasons

if __name__ == "__main__":
    test_high_wave_doji_is_neutral_not_hammer_and_shooting_star()
    test_engulfing_requires_full_body_expansion()
    test_volume_ratio_excludes_current_candle_from_average()
    test_calibration_min_samples_are_conservative()
    test_kelly_no_edge_returns_zero_risk_not_profile_default()
    test_paper_unlock_profile_is_not_hardcoded_to_legacy_name()
    test_near_sr_does_not_mark_support_and_resistance_at_same_time()
    print("Signal/risk correctness hardening tests passed.")
