"""Prompt 29.5.0b candlestick pattern feature engine.

Diagnostic-only layer that detects explicit candle patterns and combines them
with the Prompt 29.5.0a crypto intraday scenario context.  The module is built
for paper/live-like analysis only: it does not change thresholds, verdicts,
order flow, testnet or live execution.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
import json
import math

import pandas as pd

from config import Config


PATTERN_EVENT_TYPE = "CANDLESTICK_PATTERN_DIAGNOSTIC"
REPORT_NAME = "candlestick_pattern_report.json"
DIRECTIONAL_CONFLICT_SCORE_CAP = 15.0


@dataclass(frozen=True)
class CandlestickPatternSettings:
    enabled: bool = True
    min_body_ratio: float = 0.25
    strong_body_ratio: float = 0.55
    doji_body_ratio: float = 0.12
    wick_ratio: float = 0.45
    pin_wick_to_body: float = 2.0
    inside_bar_tolerance_pct: float = 0.0
    outside_bar_tolerance_pct: float = 0.0
    opposite_wick_max_ratio: float = 0.10
    engulfing_body_multiplier: float = 1.05
    reclaim_buffer_pct: float = 0.0003
    retest_tolerance_pct: float = 0.0015
    volume_ratio_threshold: float = 1.10

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "CandlestickPatternSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_CANDLESTICK_PATTERNS_ENABLED", True)),
            min_body_ratio=_safe_float(getattr(cfg, "CANDLE_PATTERN_MIN_BODY_RATIO", 0.25), 0.25),
            strong_body_ratio=_safe_float(getattr(cfg, "CANDLE_PATTERN_STRONG_BODY_RATIO", 0.55), 0.55),
            doji_body_ratio=_safe_float(getattr(cfg, "CANDLE_PATTERN_DOJI_BODY_RATIO", 0.12), 0.12),
            wick_ratio=_safe_float(getattr(cfg, "CANDLE_PATTERN_WICK_RATIO", 0.45), 0.45),
            pin_wick_to_body=_safe_float(getattr(cfg, "CANDLE_PATTERN_PIN_WICK_TO_BODY", 2.0), 2.0),
            inside_bar_tolerance_pct=_safe_float(getattr(cfg, "CANDLE_PATTERN_INSIDE_TOLERANCE_PCT", 0.0), 0.0),
            outside_bar_tolerance_pct=_safe_float(getattr(cfg, "CANDLE_PATTERN_OUTSIDE_TOLERANCE_PCT", 0.0), 0.0),
            opposite_wick_max_ratio=_safe_float(getattr(cfg, "CANDLE_PATTERN_OPPOSITE_WICK_MAX_RATIO", 0.10), 0.10),
            engulfing_body_multiplier=_safe_float(getattr(cfg, "CANDLE_PATTERN_ENGULFING_BODY_MULTIPLIER", 1.05), 1.05),
            reclaim_buffer_pct=_safe_float(getattr(cfg, "CANDLE_PATTERN_RECLAIM_BUFFER_PCT", 0.0003), 0.0003),
            retest_tolerance_pct=_safe_float(getattr(cfg, "CANDLE_PATTERN_RETEST_TOLERANCE_PCT", 0.0015), 0.0015),
            volume_ratio_threshold=_safe_float(getattr(cfg, "CANDLE_PATTERN_VOLUME_RATIO_THRESHOLD", 1.10), 1.10),
        )


@dataclass(frozen=True)
class PatternResult:
    patterns: tuple[str, ...]
    bullish_patterns: tuple[str, ...]
    bearish_patterns: tuple[str, ...]
    neutral_patterns: tuple[str, ...]
    pattern_bias: str
    pattern_score: float
    scenario_integration: str
    recommendation: str
    confirmations: tuple[str, ...]
    missing_confirmations: tuple[str, ...]
    candle_metrics: dict[str, float]
    context: dict[str, Any]
    diagnostic_only: bool = True
    strategy_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["patterns"] = list(self.patterns)
        out["bullish_patterns"] = list(self.bullish_patterns)
        out["bearish_patterns"] = list(self.bearish_patterns)
        out["neutral_patterns"] = list(self.neutral_patterns)
        out["confirmations"] = list(self.confirmations)
        out["missing_confirmations"] = list(self.missing_confirmations)
        return out


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        if math.isfinite(f):
            return f
    except Exception:
        pass
    return default


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _row_get(row: Any, key: str, default: Any = 0.0) -> Any:
    try:
        return row.get(key, default)
    except Exception:
        return default


def _col(df: pd.DataFrame, a: str, b: str | None = None) -> str:
    if a in df.columns:
        return a
    if b and b in df.columns:
        return b
    return a


def _last_mean(df: pd.DataFrame, col: str, window: int, default: float, *, exclude_current: bool = True) -> float:
    """Return a historical rolling mean without peeking at the candle being scored.

    For pattern diagnostics, the last row is the candle under analysis. Including
    it in the reference volume mean creates an autoreferential look-ahead effect:
    an exceptional current volume inflates its own baseline and suppresses the
    volume-ratio signal.
    """
    try:
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            if exclude_current and len(series) > 1:
                series = series.iloc[:-1]
            vals = series.tail(window).dropna()
            if len(vals):
                return _safe_float(vals.mean(), default)
    except Exception:
        pass
    return default


def _distance_pct(price: float, level: float) -> float:
    if price <= 0 or level <= 0:
        return 999.0
    return abs(price - level) / price


def _candle_stats(row: Any, df: pd.DataFrame, settings: CandlestickPatternSettings) -> dict[str, float]:
    open_ = _safe_float(_row_get(row, "Open", _row_get(row, "open", 0.0)))
    high = _safe_float(_row_get(row, "High", _row_get(row, "high", 0.0)))
    low = _safe_float(_row_get(row, "Low", _row_get(row, "low", 0.0)))
    close = _safe_float(_row_get(row, "Close", _row_get(row, "close", 0.0)))
    volume = _safe_float(_row_get(row, "Volume", _row_get(row, "volume", 0.0)))
    rng = max(high - low, 1e-12)
    body = abs(close - open_)
    upper_wick = max(0.0, high - max(open_, close))
    lower_wick = max(0.0, min(open_, close) - low)
    vol_col = _col(df, "Volume", "volume")
    avg_vol = _last_mean(df, vol_col, 20, volume)
    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "range": rng,
        "body": body,
        "body_ratio": _clip(body / rng, 0.0, 1.0),
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "upper_wick_ratio": _clip(upper_wick / rng, 0.0, 1.0),
        "lower_wick_ratio": _clip(lower_wick / rng, 0.0, 1.0),
        "bullish_body": 1.0 if close > open_ else 0.0,
        "bearish_body": 1.0 if close < open_ else 0.0,
        "volume_ratio_20": volume / avg_vol if avg_vol > 0 else 1.0,
    }


def detect_candlestick_patterns(
    df: pd.DataFrame,
    *,
    symbol: str = "",
    scenario: dict[str, Any] | None = None,
    settings: CandlestickPatternSettings | None = None,
) -> PatternResult:
    settings = settings or CandlestickPatternSettings.from_config()
    if df is None or df.empty:
        return PatternResult((), (), (), (), "HOLD", 0.0, "NO_DATA", "NO_DATA", (), ("empty_dataframe",), {}, {"symbol": symbol})

    scenario = scenario if isinstance(scenario, dict) else {}
    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else row
    prev2 = df.iloc[-3] if len(df) >= 3 else prev
    stats = _candle_stats(row, df, settings)
    prev_stats = _candle_stats(prev, df, settings)
    prev2_stats = _candle_stats(prev2, df, settings)

    o, h, l, c = stats["open"], stats["high"], stats["low"], stats["close"]
    po, ph, pl, pc = prev_stats["open"], prev_stats["high"], prev_stats["low"], prev_stats["close"]
    p2o, p2c = prev2_stats["open"], prev2_stats["close"]
    range_pos = _safe_float(_row_get(row, "range_pos_400", 0.5), 0.5)
    local_support = _safe_float(_row_get(row, "local_support", 0.0))
    local_resistance = _safe_float(_row_get(row, "local_resistance", 0.0))
    near_support = bool(_row_get(row, "near_support", False)) or _distance_pct(c, local_support) <= _safe_float(getattr(Config, "CRYPTO_SCENARIO_SR_PROXIMITY_PCT", 0.0035), 0.0035)
    near_resistance = bool(_row_get(row, "near_resistance", False)) or _distance_pct(c, local_resistance) <= _safe_float(getattr(Config, "CRYPTO_SCENARIO_SR_PROXIMITY_PCT", 0.0035), 0.0035)
    volume_confirmed = stats["volume_ratio_20"] >= settings.volume_ratio_threshold
    strong_body = stats["body_ratio"] >= settings.strong_body_ratio
    small_body = stats["body_ratio"] <= settings.doji_body_ratio
    bullish_body = c > o
    bearish_body = c < o
    prev_bullish = pc > po
    prev_bearish = pc < po

    bullish: list[str] = []
    bearish: list[str] = []
    neutral: list[str] = []
    confirmations: list[str] = []
    missing: list[str] = []

    # Single-candle patterns. Directional pin bars must be asymmetric.
    lower_long = stats["lower_wick_ratio"] >= settings.wick_ratio and stats["lower_wick"] >= max(stats["body"], 1e-12) * settings.pin_wick_to_body
    upper_long = stats["upper_wick_ratio"] >= settings.wick_ratio and stats["upper_wick"] >= max(stats["body"], 1e-12) * settings.pin_wick_to_body
    upper_small = stats["upper_wick_ratio"] <= settings.opposite_wick_max_ratio
    lower_small = stats["lower_wick_ratio"] <= settings.opposite_wick_max_ratio
    bilateral_indecision = lower_long and upper_long and stats["body_ratio"] <= max(0.30, settings.doji_body_ratio)

    if small_body:
        if stats["lower_wick_ratio"] >= 0.70 and upper_small:
            bullish.append("dragonfly_doji")
        elif stats["upper_wick_ratio"] >= 0.70 and lower_small:
            bearish.append("gravestone_doji")
        else:
            neutral.append("doji")
    if bilateral_indecision:
        neutral.append("high_wave_doji")
        missing.append("directional_wick_exclusivity")
    else:
        if lower_long and upper_small and (bullish_body or stats["body_ratio"] <= 0.30):
            if range_pos <= 0.55:
                bullish.append("hammer")
                bullish.append("bullish_pin_bar")
            else:
                bearish.append("hanging_man")
        if upper_long and lower_small and (bearish_body or stats["body_ratio"] <= 0.30):
            if range_pos >= 0.45:
                bearish.append("shooting_star")
                bearish.append("bearish_pin_bar")
            else:
                bullish.append("inverted_hammer")

    # Two-candle patterns. Engulfing must fully engulf the prior body and expand it.
    engulfing_body_ok = stats["body"] >= prev_stats["body"] * settings.engulfing_body_multiplier
    if bullish_body and prev_bearish and o <= pc and c >= po and engulfing_body_ok:
        bullish.append("bullish_engulfing")
    if bearish_body and prev_bullish and o >= pc and c <= po and engulfing_body_ok:
        bearish.append("bearish_engulfing")
    tol_inside = c * settings.inside_bar_tolerance_pct
    if h <= ph + tol_inside and l >= pl - tol_inside:
        neutral.append("inside_bar")
        if bullish_body:
            bullish.append("bullish_inside_bar")
        elif bearish_body:
            bearish.append("bearish_inside_bar")
    tol_outside = c * settings.outside_bar_tolerance_pct
    close_pos = _clip((c - l) / max(h - l, 1e-12), 0.0, 1.0)
    if h >= ph - tol_outside and l <= pl + tol_outside:
        neutral.append("outside_bar")
        if bullish_body and close_pos >= 0.67:
            bullish.append("bullish_outside_bar")
        elif bearish_body and close_pos <= 0.33:
            bearish.append("bearish_outside_bar")

    # Three-candle reversal patterns.
    if len(df) >= 3:
        p2_trend_bear = p2c < p2o and prev2_stats["body_ratio"] >= settings.strong_body_ratio
        p2_trend_bull = p2c > p2o and prev2_stats["body_ratio"] >= settings.strong_body_ratio
        star_body = prev_stats["body_ratio"] <= 0.35
        star_gap_down = max(po, pc) < min(p2o, p2c) and max(po, pc) < min(o, c)
        star_gap_up = min(po, pc) > max(p2o, p2c) and min(po, pc) > max(o, c)
        if p2_trend_bear and star_body and star_gap_down and bullish_body and c > (p2o + p2c) / 2.0:
            bullish.append("morning_star")
        if p2_trend_bull and star_body and star_gap_up and bearish_body and c < (p2o + p2c) / 2.0:
            bearish.append("evening_star")
        if p2c < p2o and prev_bearish and bullish_body and c > po and stats["body_ratio"] >= settings.min_body_ratio:
            bullish.append("bullish_three_bar_reversal")
        if p2c > p2o and prev_bullish and bearish_body and c < po and stats["body_ratio"] >= settings.min_body_ratio:
            bearish.append("bearish_three_bar_reversal")

    # Level-based structural candle patterns.
    buffer = c * settings.reclaim_buffer_pct
    if local_support > 0 and o > local_support and l < local_support - buffer and c > local_support + buffer:
        bullish.append("fake_breakdown_reclaim")
        confirmations.append("support_reclaim")
    if local_resistance > 0 and o < local_resistance and h > local_resistance + buffer and c < local_resistance - buffer:
        bearish.append("fake_breakout_reclaim")
        confirmations.append("resistance_reclaim")
    retest_bull_reaction = bullish_body or stats["lower_wick_ratio"] >= 0.50
    retest_bear_reaction = bearish_body or stats["upper_wick_ratio"] >= 0.50
    if local_resistance > 0 and po <= local_resistance and pc > local_resistance and l <= local_resistance * (1.0 + settings.retest_tolerance_pct) and c > local_resistance and retest_bull_reaction:
        bullish.append("breakout_retest_hold")
        confirmations.append("breakout_retest_hold")
    if local_support > 0 and po >= local_support and pc < local_support and h >= local_support * (1.0 - settings.retest_tolerance_pct) and c < local_support and retest_bear_reaction:
        bearish.append("breakdown_retest_reject")
        confirmations.append("breakdown_retest_reject")

    if near_support:
        confirmations.append("near_support")
    if near_resistance:
        confirmations.append("near_resistance")
    if volume_confirmed:
        confirmations.append("volume_confirmed")
    else:
        missing.append("volume_confirmation")
    if not (bullish or bearish or neutral):
        neutral.append("no_explicit_pattern")
        missing.append("explicit_candlestick_pattern")

    # Scenario integration.
    scenario_name = str(scenario.get("scenario") or "").upper()
    current_zone = str(scenario.get("current_zone") or "").upper()
    scenario_bias = str(scenario.get("directional_bias") or "HOLD").upper()
    score = 0.0
    bull_set = set(bullish)
    bear_set = set(bearish)
    directional_conflict = bool(bull_set and bear_set)
    if directional_conflict:
        neutral.append("conflicting_directional_patterns")
        missing.append("clear_directional_candle")
        score = DIRECTIONAL_CONFLICT_SCORE_CAP
    else:
        if bullish:
            score += 35.0 + min(20.0, 5.0 * len(bull_set))
        if bearish:
            score += 35.0 + min(20.0, 5.0 * len(bear_set))
        if neutral and not (bullish or bearish):
            score += 15.0
        if volume_confirmed:
            score += 10.0
        if near_support and bullish:
            score += 15.0
        if near_resistance and bearish:
            score += 15.0
        if strong_body:
            score += 5.0

    bull_count = len(bull_set)
    bear_count = len(bear_set)
    if directional_conflict:
        bias = "HOLD"
    elif bull_count > bear_count:
        bias = "BUY"
    elif bear_count > bull_count:
        bias = "SELL"
    else:
        bias = "HOLD"

    integration = "PATTERN_WAIT"
    recommendation = "WAIT_FOR_CLEAR_CANDLE_CONFIRMATION"
    if scenario_name in {"NEAR_SUPPORT", "BUY_REJECTION_CANDIDATE"}:
        if bias == "BUY":
            integration = "BUY_REJECTION_CONFIRMED_BY_CANDLE"
            recommendation = "BUY_REJECTION_CANDIDATE_FOR_SHADOW_REVIEW"
        elif bias == "SELL":
            integration = "SUPPORT_BREAKDOWN_CANDLE_PRESSURE"
            recommendation = "SELL_ONLY_AFTER_BREAKDOWN_RETEST_CONFIRMATION"
        else:
            integration = "SUPPORT_CONTEXT_NO_CANDLE_CONFIRMATION"
            recommendation = "WAIT_FOR_BUY_REJECTION_OR_SELL_BREAKDOWN_CONFIRMATION"
    elif scenario_name in {"NEAR_RESISTANCE", "SELL_REJECTION_CANDIDATE"}:
        if bias == "SELL":
            integration = "SELL_REJECTION_CONFIRMED_BY_CANDLE"
            recommendation = "SELL_REJECTION_CANDIDATE_FOR_SHADOW_REVIEW"
        elif bias == "BUY":
            integration = "RESISTANCE_BREAKOUT_CANDLE_PRESSURE"
            recommendation = "BUY_ONLY_AFTER_BREAKOUT_RETEST_CONFIRMATION"
        else:
            integration = "RESISTANCE_CONTEXT_NO_CANDLE_CONFIRMATION"
            recommendation = "WAIT_FOR_SELL_REJECTION_OR_BUY_BREAKOUT_CONFIRMATION"
    elif scenario_name in {"BUY_BREAKOUT_CANDIDATE", "SELL_BREAKDOWN_CANDIDATE"}:
        integration = "BREAKOUT_SCENARIO_PATTERN_REVIEW"
        recommendation = "REQUIRE_RETEST_OR_CONTINUATION_CONFIRMATION"
    elif "MID_RANGE" in scenario_name or "MID_RANGE" in current_zone:
        integration = "MID_RANGE_PATTERN_DEGRADED"
        recommendation = "KEEP_BLOCKED_MID_RANGE_PATTERN_NOT_ACTIONABLE"
        score = min(score, 35.0)
    elif scenario_bias in {"BUY", "SELL"} and bias == scenario_bias:
        integration = "SCENARIO_AND_PATTERN_ALIGNED"
        recommendation = "ALIGNED_PATTERN_FOR_SHADOW_REVIEW"
    elif scenario_bias in {"BUY", "SELL"} and bias in {"BUY", "SELL"} and bias != scenario_bias:
        integration = "SCENARIO_PATTERN_CONFLICT"
        recommendation = "KEEP_BLOCKED_CONFLICTING_PATTERN"
        score = min(score, 45.0)
    if directional_conflict:
        integration = "CONFLICTING_CANDLE_PATTERNS_NEUTRALIZED"
        recommendation = "KEEP_BLOCKED_CANDLE_INDECISION"
        score = min(score, DIRECTIONAL_CONFLICT_SCORE_CAP)

    all_patterns = tuple(dict.fromkeys([*bullish, *bearish, *neutral]))
    context = {
        "symbol": symbol,
        "scenario": scenario_name or None,
        "current_zone": current_zone or None,
        "scenario_directional_bias": scenario_bias,
        "range_pos_400": round(_clip(range_pos, 0.0, 1.0), 8),
        "near_support": bool(near_support),
        "near_resistance": bool(near_resistance),
        "local_support": round(local_support, 8),
        "local_resistance": round(local_resistance, 8),
        "directional_conflict": bool(directional_conflict),
        "conflict_reason": "bullish_and_bearish_patterns_coexist" if directional_conflict else "",
        "conflict_score_cap": DIRECTIONAL_CONFLICT_SCORE_CAP if directional_conflict else None,
    }
    metrics = {
        "body_ratio": round(stats["body_ratio"], 6),
        "upper_wick_ratio": round(stats["upper_wick_ratio"], 6),
        "lower_wick_ratio": round(stats["lower_wick_ratio"], 6),
        "volume_ratio_20": round(stats["volume_ratio_20"], 6),
        "range": round(stats["range"], 8),
    }
    return PatternResult(
        patterns=all_patterns,
        bullish_patterns=tuple(dict.fromkeys(bullish)),
        bearish_patterns=tuple(dict.fromkeys(bearish)),
        neutral_patterns=tuple(dict.fromkeys(neutral)),
        pattern_bias=bias,
        pattern_score=round(_clip(score, 0.0, 100.0), 6),
        scenario_integration=integration,
        recommendation=recommendation,
        confirmations=tuple(dict.fromkeys(confirmations)),
        missing_confirmations=tuple(dict.fromkeys(missing)),
        candle_metrics=metrics,
        context=context,
    )


def build_candlestick_pattern_diagnostic(
    *,
    symbol: str,
    df: pd.DataFrame,
    cycle_id: str,
    candle_ts: str,
    scenario_diagnostic: dict[str, Any] | None = None,
    signal_diagnostic: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = detect_candlestick_patterns(df, symbol=symbol, scenario=scenario_diagnostic)
    sig = signal_diagnostic if isinstance(signal_diagnostic, dict) else {}
    conf = confidence if isinstance(confidence, dict) else {}
    payload = result.to_dict()
    payload.update({
        "event_type": PATTERN_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "candle_ts": candle_ts,
        "scenario": (scenario_diagnostic or {}).get("scenario") if isinstance(scenario_diagnostic, dict) else None,
        "scenario_directional_bias": (scenario_diagnostic or {}).get("directional_bias") if isinstance(scenario_diagnostic, dict) else None,
        "scenario_alignment": (scenario_diagnostic or {}).get("scenario_alignment") if isinstance(scenario_diagnostic, dict) else None,
        "dominant_filter": str(sig.get("dominant_filter") or ""),
        "diagnostic_reason": str(sig.get("diagnostic_reason") or ""),
        "intended_side": str(sig.get("intended_side") or ""),
        "technical_score": _safe_float(sig.get("technical_score"), _safe_float(conf.get("tech_score"), 0.0)),
        "ai_prob": _safe_float(sig.get("ai_prob"), _safe_float(conf.get("ai_prob"), 0.0)),
        "setup_quality": _safe_float(sig.get("setup_quality"), _safe_float(conf.get("setup_quality"), 0.0)),
        "pattern_alignment": _pattern_alignment(result.pattern_bias, str(sig.get("intended_side") or ""), str((scenario_diagnostic or {}).get("directional_bias") if isinstance(scenario_diagnostic, dict) else "")),
        "ts": utc_now_iso(),
    })
    return payload


def _pattern_alignment(pattern_bias: str, intended_side: str, scenario_bias: str) -> str:
    p = str(pattern_bias or "HOLD").upper()
    s = str(intended_side or "").upper()
    sc = str(scenario_bias or "HOLD").upper()
    if p in {"BUY", "SELL"} and s == p:
        return "PATTERN_ENGINE_ALIGNED"
    if p in {"BUY", "SELL"} and s in {"BUY", "SELL"} and s != p:
        return "PATTERN_ENGINE_CONFLICT"
    if p in {"BUY", "SELL"} and sc == p:
        return "PATTERN_SCENARIO_ALIGNED"
    if p in {"BUY", "SELL"} and sc in {"BUY", "SELL"} and sc != p:
        return "PATTERN_SCENARIO_CONFLICT"
    if p in {"BUY", "SELL"}:
        return "PATTERN_HAS_SIDE_ENGINE_WAIT"
    return "BOTH_WAIT"


def read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                obj["__line_no__"] = idx
                rows.append(obj)
        except Exception:
            continue
    return rows


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "").upper()


def _metrics(values: list[float]) -> dict[str, float]:
    vals = sorted([_safe_float(v, 0.0) for v in values if math.isfinite(_safe_float(v, float("nan")))])
    if not vals:
        return {"min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0, "avg": 0.0}

    def pick(q: float) -> float:
        if len(vals) == 1:
            return vals[0]
        idx = int(round((len(vals) - 1) * q))
        return vals[max(0, min(len(vals) - 1, idx))]

    return {
        "min": round(vals[0], 8),
        "p25": round(pick(0.25), 8),
        "median": round(pick(0.50), 8),
        "p75": round(pick(0.75), 8),
        "max": round(vals[-1], 8),
        "avg": round(float(mean(vals)), 8),
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_asset: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row.get("symbol") or "UNKNOWN")].append(row)
    for symbol, asset_rows in sorted(groups.items()):
        pattern_counts: Counter[str] = Counter()
        for row in asset_rows:
            for p in row.get("patterns") or []:
                pattern_counts[str(p)] += 1
        by_asset[symbol] = {
            "scans": len(asset_rows),
            "directional_patterns": sum(1 for r in asset_rows if str(r.get("pattern_bias") or "HOLD").upper() in {"BUY", "SELL"}),
            "pattern_bias": dict(Counter(str(r.get("pattern_bias") or "HOLD").upper() for r in asset_rows)),
            "pattern_alignment": dict(Counter(str(r.get("pattern_alignment") or "").upper() for r in asset_rows)),
            "scenario_integration": dict(Counter(str(r.get("scenario_integration") or "").upper() for r in asset_rows)),
            "patterns": dict(pattern_counts),
            "dominant_filters": dict(Counter(str(r.get("dominant_filter") or "NONE") for r in asset_rows)),
            "pattern_score": _metrics([_safe_float(r.get("pattern_score"), 0.0) for r in asset_rows]),
            "recent": _recent(asset_rows, 5),
        }
    return by_asset


def _recent(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[-limit:]:
        out.append({
            "ts": row.get("ts"),
            "cycle_id": row.get("cycle_id"),
            "symbol": row.get("symbol"),
            "patterns": row.get("patterns", []),
            "pattern_bias": row.get("pattern_bias"),
            "pattern_score": row.get("pattern_score"),
            "scenario": row.get("scenario"),
            "scenario_integration": row.get("scenario_integration"),
            "pattern_alignment": row.get("pattern_alignment"),
            "recommendation": row.get("recommendation"),
            "dominant_filter": row.get("dominant_filter"),
        })
    return out


def _decision(rows: list[dict[str, Any]], btc_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NO_PATTERN_ROWS",
            "action": "run paper once with candlestick pattern diagnostics enabled",
            "next_patch": "29.5.0b validation rerun",
        }
    btc_directional = [r for r in btc_rows if str(r.get("pattern_bias") or "HOLD").upper() in {"BUY", "SELL"}]
    btc_aligned = [r for r in btc_rows if str(r.get("pattern_alignment") or "").upper() in {"PATTERN_ENGINE_ALIGNED", "PATTERN_SCENARIO_ALIGNED"}]
    if btc_aligned:
        return {
            "status": "PATTERN_SIDE_ATTRIBUTION_AVAILABLE",
            "action": "keep diagnostic-only; run shadow review before using pattern bias in unlock",
            "next_patch": "29.5.0c Pattern-conditioned shadow review",
            "btc_directional_rows": len(btc_directional),
            "btc_aligned_rows": len(btc_aligned),
        }
    if btc_directional:
        return {
            "status": "PATTERN_SIDE_PRESENT_BUT_NOT_ALIGNED",
            "action": "keep blocked; integrate with scenario/AI only after shadow validation",
            "next_patch": "29.5.0c Pattern-conditioned shadow review",
            "btc_directional_rows": len(btc_directional),
            "btc_aligned_rows": 0,
        }
    return {
        "status": "PATTERN_CONFIRMATION_WEAK",
        "action": "collect more runtime rows; do not relax thresholds; no operational unlock from patterns yet",
        "next_patch": "29.5.0c Pattern-conditioned shadow review after sufficient rows",
        "btc_directional_rows": 0,
        "btc_aligned_rows": 0,
    }


def write_candlestick_pattern_report(data_dir: str | Path) -> dict[str, Any]:
    base = Path(data_dir)
    events_path = base / "paper_events.jsonl"
    report_path = base / REPORT_NAME
    events = read_events(events_path)
    rows = [e for e in events if _event_type(e) == PATTERN_EVENT_TYPE]
    btc_rows = [r for r in rows if str(r.get("symbol") or "").upper() == "BTC/USDT"]
    by_asset = _summarize(rows)
    pattern_counts: Counter[str] = Counter()
    for row in rows:
        for p in row.get("patterns") or []:
            pattern_counts[str(p)] += 1
    decision = _decision(rows, btc_rows)
    payload = {
        "report_type": "candlestick_pattern_feature_engine",
        "prompt": "29.5.0b",
        "generated_at": utc_now_iso(),
        "status": "WARN" if decision.get("status") in {"PATTERN_CONFIRMATION_WEAK", "PATTERN_SIDE_PRESENT_BUT_NOT_ALIGNED", "NO_PATTERN_ROWS"} else "PASS",
        "safety": {
            "diagnostic_only": True,
            "opens_orders": False,
            "changes_thresholds": False,
            "enables_live_or_testnet": False,
            "pattern_bias_operational_unlock": False,
        },
        "counts": {
            "events_total": len(events),
            "pattern_events": len(rows),
            "btc_pattern_events": len(btc_rows),
            "signals_detected": sum(1 for e in events if _event_type(e) == "SIGNAL_DETECTED"),
            "orders_submitted": sum(1 for e in events if _event_type(e) in {"PAPER_ORDER_SUBMITTED", "PAPER_ORDER_CONFIRMED"}),
            "positions_opened": sum(1 for e in events if _event_type(e) == "POSITION_OPENED"),
        },
        "decision": decision,
        "patterns": dict(pattern_counts),
        "directional_bias": dict(Counter(str(r.get("pattern_bias") or "HOLD").upper() for r in rows)),
        "scenario_integration": dict(Counter(str(r.get("scenario_integration") or "").upper() for r in rows)),
        "pattern_alignment": dict(Counter(str(r.get("pattern_alignment") or "").upper() for r in rows)),
        "btc_focus": by_asset.get("BTC/USDT", {"scans": 0, "patterns": {}, "pattern_bias": {}, "recent": []}),
        "by_asset": by_asset,
        "recent_patterns": _recent(rows, 12),
        "files": {"events": str(events_path), "report": str(report_path)},
        "diagnostic_only": True,
        "opens_orders": False,
        "changes_thresholds": False,
        "enables_live_or_testnet": False,
    }
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


__all__ = [
    "CandlestickPatternSettings",
    "PatternResult",
    "detect_candlestick_patterns",
    "build_candlestick_pattern_diagnostic",
    "write_candlestick_pattern_report",
]
