"""
test_candlestick_patterns.py — Pytest suite to validate candlestick pattern updates and context fixes.
Run from: trading_bot/ directory using: pytest test_candlestick_patterns.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import pytest

from core.candlestick_patterns import detect_candlestick_patterns, CandlestickPatternSettings
from config import Config

def create_base_df(rows_data: list[dict]) -> pd.DataFrame:
    """Helper to build a pandas DataFrame from a list of candle data dicts."""
    df = pd.DataFrame(rows_data)
    # Ensure columns exist that stats or scenario might read
    if "Volume" not in df.columns:
        df["Volume"] = 1000.0
    if "volume" not in df.columns:
        df["volume"] = 1000.0
    if "range_pos_400" not in df.columns:
        df["range_pos_400"] = 0.5
    if "local_support" not in df.columns:
        df["local_support"] = 0.0
    if "local_resistance" not in df.columns:
        df["local_resistance"] = 0.0
    return df

# ── Test 1: Doji & Pin Bar Exclusivity ───────────────────────────────────────
def test_doji_exclusivity():
    # 1. Neutral Doji: very tiny body, even wicks
    df_doji = create_base_df([
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0}
    ])
    res = detect_candlestick_patterns(df_doji)
    assert "doji" in res.neutral_patterns
    assert not res.bullish_patterns
    assert not res.bearish_patterns

    # 2. Dragonfly Doji: tiny body, long lower wick
    df_dragonfly = create_base_df([
        {"Open": 100.0, "High": 100.0, "Low": 95.0, "Close": 100.0}
    ])
    res_df = detect_candlestick_patterns(df_dragonfly)
    assert "dragonfly_doji" in res_df.bullish_patterns
    assert "doji" not in res_df.neutral_patterns

    # 3. Gravestone Doji: tiny body, long upper wick
    df_gravestone = create_base_df([
        {"Open": 100.0, "High": 105.0, "Low": 100.0, "Close": 100.0}
    ])
    res_gs = detect_candlestick_patterns(df_gravestone)
    assert "gravestone_doji" in res_gs.bearish_patterns
    assert "doji" not in res_gs.neutral_patterns

    # 4. Hammer (Bullish Pin Bar): tiny upper wick, long lower wick, body >= doji
    df_hammer = create_base_df([
        {"Open": 99.5, "High": 100.1, "Low": 97.0, "Close": 100.0, "range_pos_400": 0.3}
    ])
    res_ham = detect_candlestick_patterns(df_hammer)
    assert "hammer" in res_ham.bullish_patterns
    assert "bullish_pin_bar" in res_ham.bullish_patterns
    assert "doji" not in res_ham.neutral_patterns
    assert "shooting_star" not in res_ham.bearish_patterns

# ── Test 2: Context-Aware Pin Bars ──────────────────────────────────────────
def test_context_aware_pin_bars():
    # Hammer at peak (range_pos_400 = 0.9) -> should be Hanging Man (bearish)
    df_peak_hammer = create_base_df([
        {"Open": 99.5, "High": 100.1, "Low": 97.0, "Close": 100.0, "range_pos_400": 0.9}
    ])
    res_peak = detect_candlestick_patterns(df_peak_hammer)
    assert "hanging_man" in res_peak.bearish_patterns
    assert "hammer" not in res_peak.bullish_patterns

    # Shooting Star at bottom (range_pos_400 = 0.1) -> should be Inverted Hammer (bullish)
    df_low_star = create_base_df([
        {"Open": 100.0, "High": 103.0, "Low": 99.9, "Close": 99.5, "range_pos_400": 0.1}
    ])
    res_low = detect_candlestick_patterns(df_low_star)
    assert "inverted_hammer" in res_low.bullish_patterns
    assert "shooting_star" not in res_low.bearish_patterns

# ── Test 3: Engulfing Strictness (>= 1.05 body expansion) ────────────────────
def test_engulfing_strictness():
    # Previous bearish: body = 10
    prev_bear = {"Open": 100.0, "High": 101.0, "Low": 89.0, "Close": 90.0}

    # 1. Current bullish body = 8 (which is 80% of prev body, was accepted by *0.75)
    df_weak = create_base_df([
        prev_bear,
        {"Open": 89.0, "High": 98.0, "Low": 88.0, "Close": 97.0}
    ])
    res_weak = detect_candlestick_patterns(df_weak)
    assert "bullish_engulfing" not in res_weak.bullish_patterns

    # 2. Current bullish body = 11 (which is 110% of prev body, >= 1.05)
    df_strong = create_base_df([
        prev_bear,
        {"Open": 89.0, "High": 103.0, "Low": 88.0, "Close": 100.0}
    ])
    res_strong = detect_candlestick_patterns(df_strong)
    assert "bullish_engulfing" in res_strong.bullish_patterns

# ── Test 4: Inside Bar Strictness (no tolerance) ───────────────────────────
def test_inside_bar_strictness():
    # Previous: High=100, Low=90
    prev = {"Open": 95.0, "High": 100.0, "Low": 90.0, "Close": 96.0}

    # 1. Current slightly exceeds high (100.1, was inside bar with 0.0002 tolerance)
    df_exceed = create_base_df([
        prev,
        {"Open": 95.0, "High": 100.1, "Low": 91.0, "Close": 96.0}
    ])
    res_ex = detect_candlestick_patterns(df_exceed)
    assert "inside_bar" not in res_ex.neutral_patterns

    # 2. Current strictly inside: High=99.9, Low=90.1
    df_inside = create_base_df([
        prev,
        {"Open": 95.0, "High": 99.9, "Low": 90.1, "Close": 96.0}
    ])
    res_in = detect_candlestick_patterns(df_inside)
    assert "inside_bar" in res_in.neutral_patterns
    assert "bullish_inside_bar" in res_in.bullish_patterns

# ── Test 5: Outside Bar Strictness and Chiusura ──────────────────────────────
def test_outside_bar_validation():
    # Previous: High=100, Low=90
    prev = {"Open": 95.0, "High": 100.0, "Low": 90.0, "Close": 96.0}

    # 1. Current expands but closes in middle (95.0) -> outside_bar but NOT bullish_outside_bar
    df_indecision = create_base_df([
        prev,
        {"Open": 94.0, "High": 102.0, "Low": 88.0, "Close": 95.0} # body is slightly green (95 > 94)
    ])
    res_ind = detect_candlestick_patterns(df_indecision)
    assert "outside_bar" in res_ind.neutral_patterns
    assert "bullish_outside_bar" not in res_ind.bullish_patterns

    # 2. Current expands and closes strong (101.5, upper 33% of range) -> bullish_outside_bar
    df_strong = create_base_df([
        prev,
        {"Open": 94.0, "High": 102.0, "Low": 88.0, "Close": 101.5}
    ])
    res_str = detect_candlestick_patterns(df_strong)
    assert "outside_bar" in res_str.neutral_patterns
    assert "bullish_outside_bar" in res_str.bullish_patterns

# ── Test 6: Morning Star Trend and Gap ───────────────────────────────────────
def test_morning_star_validation():
    # 1. Perfect Morning Star
    df_perfect = create_base_df([
        # 1st candle: Bearish strong trend (body ratio = 10/12 = 0.83)
        {"Open": 100.0, "High": 101.0, "Low": 89.0, "Close": 90.0},
        # 2nd candle: Star completely below adjacent bodies (star open=85, close=86)
        {"Open": 85.0, "High": 87.0, "Low": 84.0, "Close": 86.0},
        # 3rd candle: Bullish closing above midpoint of 1st (95.0)
        {"Open": 88.0, "High": 98.0, "Low": 87.0, "Close": 97.0}
    ])
    res_perf = detect_candlestick_patterns(df_perfect)
    assert "morning_star" in res_perf.bullish_patterns

    # 2. Invalid Morning Star: no body gap (star overlaps with 1st close)
    df_invalid_gap = create_base_df([
        {"Open": 100.0, "High": 101.0, "Low": 89.0, "Close": 90.0},
        # Star open=90.5 (overlaps with 1st close=90.0)
        {"Open": 90.5, "High": 91.0, "Low": 84.0, "Close": 90.1},
        {"Open": 91.0, "High": 98.0, "Low": 87.0, "Close": 97.0}
    ])
    res_inv = detect_candlestick_patterns(df_invalid_gap)
    assert "morning_star" not in res_inv.bullish_patterns

# ── Test 7: Three-Bar Reversal Reclaim ───────────────────────────────────────
def test_three_bar_reversal_reclaim():
    # Bullish Three-Bar Reversal: require 3rd candle to close above 2nd open (po)
    prev2 = {"Open": 100.0, "High": 101.0, "Low": 89.0, "Close": 90.0} # bearish trend
    prev = {"Open": 90.0, "High": 91.0, "Low": 80.0, "Close": 82.0} # 2nd bearish candle (po=90)

    # 1. 3rd candle closes below 2nd open (close=88, which is > 2nd close=82)
    df_weak = create_base_df([
        prev2, prev,
        {"Open": 81.0, "High": 89.0, "Low": 80.0, "Close": 88.0}
    ])
    res_weak = detect_candlestick_patterns(df_weak)
    assert "bullish_three_bar_reversal" not in res_weak.bullish_patterns

    # 2. 3rd candle closes above 2nd open (close=92, which is > 2nd open=90)
    df_strong = create_base_df([
        prev2, prev,
        {"Open": 81.0, "High": 95.0, "Low": 80.0, "Close": 92.0}
    ])
    res_strong = detect_candlestick_patterns(df_strong)
    assert "bullish_three_bar_reversal" in res_strong.bullish_patterns

# ── Test 8: Fake Breakdown support check ─────────────────────────────────────
def test_fake_breakdown_validation():
    # Support at 100
    # 1. Opens above support (102), dips below (98), closes above (103) -> Fake Breakdown Reclaim
    df_valid = create_base_df([
        {"Open": 102.0, "High": 104.0, "Low": 98.0, "Close": 103.0, "local_support": 100.0}
    ])
    res_val = detect_candlestick_patterns(df_valid)
    assert "fake_breakdown_reclaim" in res_val.bullish_patterns

    # 2. Opens already below support (99), dips (97), closes above (102) -> Should NOT be Fake Breakdown
    df_invalid = create_base_df([
        {"Open": 99.0, "High": 103.0, "Low": 97.0, "Close": 102.0, "local_support": 100.0}
    ])
    res_inv = detect_candlestick_patterns(df_invalid)
    assert "fake_breakdown_reclaim" not in res_inv.bullish_patterns

# ── Test 9: Retest Hold and Trigger Infinito Prevention ──────────────────────
def test_retest_hold_precision():
    # Resistance at 100
    # 1st candle: Below resistance (close=98)
    c1 = {"Open": 95.0, "High": 99.0, "Low": 94.0, "Close": 98.0}
    # 2nd candle: Breakout close above resistance (close=103)
    c2 = {"Open": 97.0, "High": 104.0, "Low": 96.0, "Close": 103.0}
    # 3rd candle: Retest. Low hits 100.1, closes bullish at 102. -> Retest Hold
    c3 = {"Open": 101.0, "High": 103.0, "Low": 100.1, "Close": 102.0}
    # 4th candle: Touches level again, but not the immediate candle after breakout! -> No Retest Hold
    c4 = {"Open": 102.0, "High": 103.0, "Low": 100.1, "Close": 102.5}

    df_retest = create_base_df([c1, c2, c3])
    df_retest["local_resistance"] = 100.0
    res_retest = detect_candlestick_patterns(df_retest)
    assert "breakout_retest_hold" in res_retest.bullish_patterns

    df_infinite = create_base_df([c1, c2, c3, c4])
    df_infinite["local_resistance"] = 100.0
    res_inf = detect_candlestick_patterns(df_infinite)
    # Should not trigger breakout_retest_hold on 4th candle because immediate breakout is false
    assert "breakout_retest_hold" not in res_inf.bullish_patterns

# ── Test 10: Volume Look-Ahead Prevention ────────────────────────────────────
def test_volume_look_ahead_prevention():
    # Let's create a history of 20 candles with volume = 100
    history = [{"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 100.0} for _ in range(19)]
    # 20th candle (current) has an extreme volume spike = 1000
    current = {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000.0}

    df = create_base_df(history + [current])
    
    # Under correct calculation: avg_vol is based only on the previous 19 candles (avg = 100).
    # Thus: volume_ratio_20 = 1000 / 100 = 10.0
    # Under old look-ahead: avg_vol included current (avg = (19*100 + 1000)/20 = 145).
    # Thus: volume_ratio_20 = 1000 / 145 = 6.89
    res = detect_candlestick_patterns(df)
    ratio = res.candle_metrics["volume_ratio_20"]
    
    # Assert ratio is exactly 10.0 (previous-only average) and not biased down to 6.89
    assert abs(ratio - 10.0) < 1e-5
