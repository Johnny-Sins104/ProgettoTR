"""
core/setup_filter.py — Institutional-Grade Technical Setup Filtering Engine
========================================================================
Calculates a multi-dimensional Technical Quality Score (0-100) for setup candidates,
and filters out lower-probability setups prior to ML meta-labeling.

Scoring Pillars:
  1. Technical Confluence (Max 40)  — EMA alignment, RSI positioning, engulfing patterns
  2. Volume Strength (Max 30)      — volume ratios, buying/selling volume bias
  3. Macro Proximity (Max 30)      — Support/Resistance zones, psychological price barriers
"""

import pandas as pd
from config import Config


class SetupFilter:
    """
    Evaluates rule-based technical setups to score their baseline quality
    and decide if they warrant evaluation by the secondary ML meta-model.
    """

    @classmethod
    def calculate_quality_score(cls, row: pd.Series | dict, volume_ratio: float, side: str) -> float:
        """
        Calculates a quantitative technical quality score (0-100) based on three pillars.
        Supports both pandas Series and dictionaries for live/backtest compatibility.
        """
        # Get helper function to fetch dictionary or series values safely
        def get_val(key, default):
            if isinstance(row, dict):
                return row.get(key, default)
            elif isinstance(row, pd.Series):
                return row.get(key, default)
            return default

        # --- 1. TECHNICAL CONFLUENCE (Max 40) ---
        conf_score = 0.0
        
        # EMA 200 alignment (15 points)
        close = float(get_val("Close", get_val("close", 0.0)))
        ema_200 = float(get_val("ema_200", 0.0))
        if ema_200 > 0:
            if side == "BUY" and close > ema_200:
                conf_score += 15.0
            elif side == "SELL" and close < ema_200:
                conf_score += 15.0
                
        # RSI alignment (15 points)
        rsi = float(get_val("rsi_14", 50.0))
        if side == "BUY":
            if rsi < 45.0:
                conf_score += 15.0
            elif rsi < 65.0:
                conf_score += 10.0
        else:
            if rsi > 55.0:
                conf_score += 15.0
            elif rsi > 35.0:
                conf_score += 10.0
                
        # Pattern confirmation (10 points)
        eng = float(get_val("cdl_engulfing", 0.0))
        doji = float(get_val("cdl_doji", 0.0))
        if side == "BUY" and eng == 100.0:
            conf_score += 10.0
        elif side == "SELL" and eng == -100.0:
            conf_score += 10.0
        elif doji == 100.0:
            conf_score += 5.0

        # --- 2. VOLUME STRENGTH (Max 30) ---
        vol_score = 0.0
        
        # Volume ratio (15 points)
        if volume_ratio >= 1.2:
            vol_score += 15.0
        elif volume_ratio >= 0.8:
            vol_score += 10.0
        else:
            vol_score += 5.0
            
        # Volume bias (15 points)
        v_bias = get_val("volume_bias", "NEUTRAL")
        if side == "BUY" and v_bias == "BULLISH":
            vol_score += 15.0
        elif side == "SELL" and v_bias == "BEARISH":
            vol_score += 15.0
        elif v_bias == "NEUTRAL":
            vol_score += 7.5

        # --- 3. MACRO PROXIMITY (Max 30) ---
        macro_score = 0.0
        
        # Support / Resistance proximity (20 points)
        near_sup = bool(get_val("near_support", False))
        near_res = bool(get_val("near_resistance", False))
        if side == "BUY" and near_sup:
            macro_score += 20.0
        elif side == "SELL" and near_res:
            macro_score += 20.0
        else:
            macro_score += 5.0
            
        # Distance to psychological level (10 points)
        dist_psy = float(get_val("dist_to_psy_level", 999.0))
        if dist_psy < 0.2:
            macro_score += 10.0
        elif dist_psy < 0.5:
            macro_score += 5.0
        else:
            macro_score += 2.0
            
        return float(conf_score + vol_score + macro_score)

    @classmethod
    def evaluate_setup(cls, side: str, row: pd.Series | dict, volume_ratio: float) -> tuple[bool, float]:
        """
        Evaluates a candidate setup based on the quality threshold.
        Returns a tuple of (is_accepted, quality_score).
        """
        if side not in ("BUY", "SELL"):
            return False, 0.0

        quality_score = cls.calculate_quality_score(row, volume_ratio, side)
        is_accepted = quality_score >= Config.META_QUALITY_THRESHOLD
        
        return is_accepted, quality_score
