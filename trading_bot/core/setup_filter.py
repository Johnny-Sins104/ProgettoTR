"""
core/setup_filter.py — Technical + market-structure setup filtering engine
==========================================================================
Calculates a multi-dimensional Technical Quality Score (0-100) for setup
candidates and optionally enhances it with causal market-structure context.

Prompt 27 refactor
------------------
The legacy score was mostly indicator/local-pattern driven.  The refactored
version keeps backward compatibility but adds a market-structure overlay:
liquidity sweeps, volatility compression/expansion, HTF alignment, session
context and BTC beta.  The overlay is conservative and diagnostic-first.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple
import pandas as pd
from config import Config


class SetupFilter:
    """
    Evaluates rule-based technical setups to score baseline quality and decide
    whether they warrant evaluation by the secondary ML meta-model.
    """

    @classmethod
    def _get_val(cls, row: pd.Series | dict, key: str, default: Any) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        if isinstance(row, pd.Series):
            return row.get(key, default)
        return default

    @classmethod
    def calculate_legacy_quality_score(cls, row: pd.Series | dict, volume_ratio: float, side: str) -> float:
        """Legacy indicator-driven score preserved for comparability."""
        def get_val(key, default):
            return cls._get_val(row, key, default)

        conf_score = 0.0
        close = float(get_val("Close", get_val("close", 0.0)) or 0.0)
        ema_200 = float(get_val("ema_200", 0.0) or 0.0)
        if ema_200 > 0:
            if side == "BUY" and close > ema_200:
                conf_score += 15.0
            elif side == "SELL" and close < ema_200:
                conf_score += 15.0

        rsi = float(get_val("rsi_14", get_val("rsi", 50.0)) or 50.0)
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

        eng = float(get_val("cdl_engulfing", 0.0) or 0.0)
        doji = float(get_val("cdl_doji", 0.0) or 0.0)
        if side == "BUY" and eng == 100.0:
            conf_score += 10.0
        elif side == "SELL" and eng == -100.0:
            conf_score += 10.0
        elif doji == 100.0:
            conf_score += 5.0

        vol_score = 0.0
        if volume_ratio >= 1.2:
            vol_score += 15.0
        elif volume_ratio >= 0.8:
            vol_score += 10.0
        else:
            vol_score += 5.0

        v_bias = get_val("volume_bias", "NEUTRAL")
        if side == "BUY" and v_bias == "BULLISH":
            vol_score += 15.0
        elif side == "SELL" and v_bias == "BEARISH":
            vol_score += 15.0
        elif v_bias == "NEUTRAL":
            vol_score += 7.5

        macro_score = 0.0
        near_sup = bool(get_val("near_support", False))
        near_res = bool(get_val("near_resistance", False))
        if side == "BUY" and near_sup:
            macro_score += 20.0
        elif side == "SELL" and near_res:
            macro_score += 20.0
        else:
            macro_score += 5.0

        dist_psy = float(get_val("dist_to_psy_level", get_val("dist_to_psy", 999.0)) or 999.0)
        if dist_psy < 0.2:
            macro_score += 10.0
        elif dist_psy < 0.5:
            macro_score += 5.0
        else:
            macro_score += 2.0

        return float(conf_score + vol_score + macro_score)

    @classmethod
    def calculate_quality_details(cls, row: pd.Series | dict, volume_ratio: float, side: str) -> Dict[str, Any]:
        legacy_score = cls.calculate_legacy_quality_score(row, volume_ratio, side)
        details: Dict[str, Any] = {
            "legacy_quality": float(legacy_score),
            "setup_quality": float(legacy_score),
            "structure_score": 0.0,
            "setup_archetype": "LEGACY",
            "structure_reasons": [],
            "edge_adjustment_r": 0.0,
        }
        if not getattr(Config, "SETUP_STRUCTURE_FEATURES_ENABLED", True):
            return details
        try:
            from core.setup_engine import MarketStructureSetupEngine
            structure = MarketStructureSetupEngine.evaluate(row, side, legacy_score)
            details.update({
                "setup_quality": float(structure.enhanced_quality),
                "structure_score": float(structure.structure_score),
                "setup_archetype": structure.archetype,
                "structure_reasons": list(structure.reasons),
                "edge_adjustment_r": float(structure.edge_adjustment_r),
                "structure_components": dict(structure.components),
            })
        except Exception as exc:
            details["structure_error"] = str(exc)
        return details

    @classmethod
    def calculate_quality_score(cls, row: pd.Series | dict, volume_ratio: float, side: str) -> float:
        """Backward-compatible API returning the enhanced quality score."""
        return float(cls.calculate_quality_details(row, volume_ratio, side).get("setup_quality", 0.0))

    @classmethod
    def evaluate_setup(cls, side: str, row: pd.Series | dict, volume_ratio: float) -> Tuple[bool, float]:
        if side not in ("BUY", "SELL"):
            return False, 0.0
        details = cls.calculate_quality_details(row, volume_ratio, side)
        quality_score = float(details.get("setup_quality", 0.0))
        structure_score = float(details.get("structure_score", 0.0))
        is_accepted = quality_score >= Config.META_QUALITY_THRESHOLD
        if getattr(Config, "SETUP_STRUCTURE_GATING", False):
            is_accepted = is_accepted and structure_score >= float(getattr(Config, "SETUP_STRUCTURE_MIN_SCORE", 20.0))
        return bool(is_accepted), quality_score

    @classmethod
    def evaluate_setup_details(cls, side: str, row: pd.Series | dict, volume_ratio: float) -> Tuple[bool, Dict[str, Any]]:
        if side not in ("BUY", "SELL"):
            return False, {"setup_quality": 0.0, "setup_archetype": "INVALID", "structure_score": 0.0}
        details = cls.calculate_quality_details(row, volume_ratio, side)
        quality_score = float(details.get("setup_quality", 0.0))
        structure_score = float(details.get("structure_score", 0.0))
        is_accepted = quality_score >= Config.META_QUALITY_THRESHOLD
        if getattr(Config, "SETUP_STRUCTURE_GATING", False):
            is_accepted = is_accepted and structure_score >= float(getattr(Config, "SETUP_STRUCTURE_MIN_SCORE", 20.0))
        details["accepted"] = bool(is_accepted)
        return bool(is_accepted), details
