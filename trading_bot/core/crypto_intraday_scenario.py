"""Prompt 29.5.0a crypto intraday scenario engine.

Diagnostic-only layer that converts existing OHLCV/market-structure features into
an explicit operational scenario map.  It does not change strategy decisions,
thresholds, risk, broker state, paper orders, testnet, or live execution.

The module answers the question exposed by Prompt 29.4.4a: when unlock is
rejected for ``no_intended_side`` or ``TECH_SCORE_LOW``, what market scenario was
actually present (near support, near resistance, mid-range, breakout candidate,
rejection candidate, etc.)?
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
import re

import pandas as pd

from config import Config


SCENARIO_EVENT_TYPE = "CRYPTO_SCENARIO_DIAGNOSTIC"
REPORT_NAME = "crypto_intraday_scenario_report.json"


@dataclass(frozen=True)
class ScenarioSettings:
    enabled: bool = True
    support_resistance_proximity_pct: float = 0.0035
    breakout_buffer_pct: float = 0.0005
    min_body_ratio: float = 0.35
    rejection_wick_ratio: float = 0.45
    volume_ratio_threshold: float = 1.10
    no_trade_low: float = 0.40
    no_trade_high: float = 0.60
    range_extreme_low: float = 0.25
    range_extreme_high: float = 0.75

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "ScenarioSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_CRYPTO_SCENARIO_ENABLED", True)),
            support_resistance_proximity_pct=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_SR_PROXIMITY_PCT", 0.0035), 0.0035),
            breakout_buffer_pct=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_BREAKOUT_BUFFER_PCT", 0.0005), 0.0005),
            min_body_ratio=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_MIN_BODY_RATIO", 0.35), 0.35),
            rejection_wick_ratio=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_REJECTION_WICK_RATIO", 0.45), 0.45),
            volume_ratio_threshold=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_VOLUME_RATIO_THRESHOLD", 1.10), 1.10),
            no_trade_low=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_NO_TRADE_LOW", 0.40), 0.40),
            no_trade_high=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_NO_TRADE_HIGH", 0.60), 0.60),
            range_extreme_low=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_RANGE_EXTREME_LOW", 0.25), 0.25),
            range_extreme_high=_safe_float(getattr(cfg, "CRYPTO_SCENARIO_RANGE_EXTREME_HIGH", 0.75), 0.75),
        )


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    directional_bias: str
    confidence_score: float
    current_zone: str
    recommendation: str
    allowed_setups: tuple[str, ...]
    blocked_setups: tuple[str, ...]
    reasons: tuple[str, ...]
    levels: dict[str, float]
    candle: dict[str, float]
    context: dict[str, Any]
    diagnostic_only: bool = True
    strategy_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["allowed_setups"] = list(self.allowed_setups)
        out["blocked_setups"] = list(self.blocked_setups)
        out["reasons"] = list(self.reasons)
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


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _pct(n: float, d: float) -> float:
    if d <= 0:
        return 0.0
    return n / d * 100.0


def _row_get(row: Any, key: str, default: Any = 0.0) -> Any:
    try:
        return row.get(key, default)
    except Exception:
        return default


def _last_series_mean(df: pd.DataFrame, col: str, window: int, default: float = 0.0) -> float:
    try:
        if col in df.columns and len(df[col]) > 0:
            vals = pd.to_numeric(df[col], errors="coerce").tail(window).dropna()
            if len(vals):
                return _safe_float(vals.mean(), default)
    except Exception:
        pass
    return default


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _distance_pct(price: float, level: float) -> float:
    if price <= 0 or level <= 0:
        return 999.0
    return abs(price - level) / price


def _zone_from_range_pos(range_pos: float, settings: ScenarioSettings) -> str:
    if range_pos <= settings.range_extreme_low:
        return "RANGE_EXTREME_LOW"
    if range_pos >= settings.range_extreme_high:
        return "RANGE_EXTREME_HIGH"
    if settings.no_trade_low <= range_pos <= settings.no_trade_high:
        return "MID_RANGE_NO_TRADE"
    if range_pos < settings.no_trade_low:
        return "LOWER_RANGE"
    if range_pos > settings.no_trade_high:
        return "UPPER_RANGE"
    return "UNKNOWN_RANGE_ZONE"


def evaluate_crypto_intraday_scenario(
    df: pd.DataFrame,
    *,
    symbol: str = "",
    settings: ScenarioSettings | None = None,
) -> ScenarioResult:
    """Evaluate a diagnostic crypto intraday scenario from the last candle.

    The function reads only current/past OHLCV and existing indicator columns.
    It returns explicit scenario context; it never changes any trading verdict.
    """
    settings = settings or ScenarioSettings.from_config()
    if df is None or df.empty:
        return ScenarioResult(
            scenario="NO_DATA",
            directional_bias="HOLD",
            confidence_score=0.0,
            current_zone="UNKNOWN",
            recommendation="NO_DATA",
            allowed_setups=(),
            blocked_setups=("ALL",),
            reasons=("empty_dataframe",),
            levels={},
            candle={},
            context={"symbol": symbol},
        )

    row = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else row
    open_ = _safe_float(_row_get(row, "Open", _row_get(row, "open", 0.0)))
    high = _safe_float(_row_get(row, "High", _row_get(row, "high", 0.0)))
    low = _safe_float(_row_get(row, "Low", _row_get(row, "low", 0.0)))
    close = _safe_float(_row_get(row, "Close", _row_get(row, "close", 0.0)))
    volume = _safe_float(_row_get(row, "Volume", _row_get(row, "volume", 0.0)))
    atr = _safe_float(_row_get(row, "atr", 0.0), max(close * 0.002, 1e-8) if close else 1e-8)
    candle_range = max(1e-8, high - low)
    body = abs(close - open_)
    body_ratio = _clip(body / candle_range, 0.0, 1.0)
    upper_wick = max(0.0, high - max(open_, close))
    lower_wick = max(0.0, min(open_, close) - low)
    upper_wick_ratio = _clip(upper_wick / candle_range, 0.0, 1.0)
    lower_wick_ratio = _clip(lower_wick / candle_range, 0.0, 1.0)

    local_support = _safe_float(_row_get(row, "local_support", 0.0))
    local_resistance = _safe_float(_row_get(row, "local_resistance", 0.0))
    macro_support = _safe_float(_row_get(row, "macro_support", 0.0))
    macro_resistance = _safe_float(_row_get(row, "macro_resistance", 0.0))
    range_pos = _safe_float(_row_get(row, "range_pos_400", 0.5), 0.5)
    if not 0.0 <= range_pos <= 1.0:
        range_pos = _clip(range_pos, 0.0, 1.0)
    regime = str(_row_get(row, "market_regime", _row_get(row, "regime", "UNKNOWN"))).upper()
    volume_bias = str(_row_get(row, "volume_bias", "NEUTRAL")).upper()
    avg_volume_20 = _last_series_mean(df, "Volume" if "Volume" in df.columns else "volume", 20, volume)
    volume_ratio = volume / avg_volume_20 if avg_volume_20 > 0 else 1.0

    near_support = bool(_row_get(row, "near_support", False)) or _distance_pct(close, local_support) <= settings.support_resistance_proximity_pct
    near_resistance = bool(_row_get(row, "near_resistance", False)) or _distance_pct(close, local_resistance) <= settings.support_resistance_proximity_pct
    buffer = settings.breakout_buffer_pct
    bullish_body = close > open_
    bearish_body = close < open_
    close_above_resistance = bool(local_resistance > 0 and close > local_resistance * (1.0 + buffer))
    close_below_support = bool(local_support > 0 and close < local_support * (1.0 - buffer))
    high_swept_resistance = bool(local_resistance > 0 and high > local_resistance * (1.0 + buffer) and close < local_resistance)
    low_swept_support = bool(local_support > 0 and low < local_support * (1.0 - buffer) and close > local_support)
    volume_confirmed = bool(volume_ratio >= settings.volume_ratio_threshold)
    strong_body = bool(body_ratio >= settings.min_body_ratio)
    upper_rejection = bool(upper_wick_ratio >= settings.rejection_wick_ratio)
    lower_rejection = bool(lower_wick_ratio >= settings.rejection_wick_ratio)

    engulfing = _safe_float(_row_get(row, "cdl_engulfing", 0.0))
    doji = _safe_float(_row_get(row, "cdl_doji", 0.0))
    bullish_pattern = bool(engulfing > 0 or (lower_rejection and bullish_body))
    bearish_pattern = bool(engulfing < 0 or (upper_rejection and bearish_body))

    current_zone = _zone_from_range_pos(range_pos, settings)
    reasons: list[str] = [f"zone:{current_zone}", f"regime:{regime}"]
    allowed: list[str] = []
    blocked: list[str] = []
    scenario = current_zone
    bias = "HOLD"
    recommendation = "WAIT_FOR_CONFIRMATION"
    score = 0.0

    # Highest priority: confirmed breakout/breakdown candidates.
    if close_above_resistance and strong_body and volume_confirmed:
        scenario = "BUY_BREAKOUT_CANDIDATE"
        bias = "BUY"
        allowed = ["BUY_BREAKOUT", "BUY_BREAKOUT_RETEST"]
        blocked = ["SELL_INTO_BREAKOUT"]
        score = 70.0 + min(20.0, (volume_ratio - 1.0) * 20.0) + min(10.0, body_ratio * 10.0)
        recommendation = "WAIT_FOR_BREAKOUT_RETEST_OR_CONTINUATION_CONFIRMATION"
        reasons += ["close_above_local_resistance", "strong_body", "volume_confirmed"]
    elif close_below_support and strong_body and volume_confirmed:
        scenario = "SELL_BREAKDOWN_CANDIDATE"
        bias = "SELL"
        allowed = ["SELL_BREAKDOWN", "SELL_BREAKDOWN_RETEST"]
        blocked = ["BUY_INTO_BREAKDOWN"]
        score = 70.0 + min(20.0, (volume_ratio - 1.0) * 20.0) + min(10.0, body_ratio * 10.0)
        recommendation = "WAIT_FOR_BREAKDOWN_RETEST_OR_CONTINUATION_CONFIRMATION"
        reasons += ["close_below_local_support", "strong_body", "volume_confirmed"]
    # Rejection candidates at structural levels.
    elif (high_swept_resistance or near_resistance) and (upper_rejection or bearish_pattern):
        scenario = "SELL_REJECTION_CANDIDATE"
        bias = "SELL"
        allowed = ["SELL_REJECTION", "SELL_LIQUIDITY_SWEEP_REVERSAL"]
        blocked = ["BUY_INTO_RESISTANCE"]
        score = 55.0 + upper_wick_ratio * 25.0 + (10.0 if high_swept_resistance else 0.0) + (8.0 if volume_confirmed else 0.0)
        recommendation = "SELL_ONLY_AFTER_CLOSE_BACK_BELOW_RESISTANCE_AND_RISK_REWARD_CHECK"
        reasons += ["near_or_swept_resistance", "upper_wick_rejection"]
    elif (low_swept_support or near_support) and (lower_rejection or bullish_pattern):
        scenario = "BUY_REJECTION_CANDIDATE"
        bias = "BUY"
        allowed = ["BUY_REJECTION", "BUY_LIQUIDITY_SWEEP_REVERSAL"]
        blocked = ["SELL_INTO_SUPPORT"]
        score = 55.0 + lower_wick_ratio * 25.0 + (10.0 if low_swept_support else 0.0) + (8.0 if volume_confirmed else 0.0)
        recommendation = "BUY_ONLY_AFTER_CLOSE_BACK_ABOVE_SUPPORT_AND_RISK_REWARD_CHECK"
        reasons += ["near_or_swept_support", "lower_wick_rejection"]
    elif current_zone == "MID_RANGE_NO_TRADE":
        scenario = "MID_RANGE_NO_TRADE"
        bias = "HOLD"
        allowed = []
        blocked = ["BUY_MID_RANGE", "SELL_MID_RANGE"]
        score = 20.0
        recommendation = "NO_TRADE_WAIT_FOR_EDGE_OF_RANGE_OR_BREAKOUT"
        reasons += ["price_inside_mid_range"]
    elif near_support or current_zone == "RANGE_EXTREME_LOW":
        scenario = "NEAR_SUPPORT"
        bias = "HOLD"
        allowed = ["BUY_REJECTION", "SELL_BREAKDOWN"]
        blocked = ["SELL_INTO_SUPPORT_WITHOUT_BREAKDOWN"]
        score = 40.0 + (10.0 if volume_confirmed else 0.0) + (8.0 if lower_rejection else 0.0)
        recommendation = "WAIT_FOR_BUY_REJECTION_OR_SELL_BREAKDOWN_CONFIRMATION"
        reasons += ["support_context"]
    elif near_resistance or current_zone == "RANGE_EXTREME_HIGH":
        scenario = "NEAR_RESISTANCE"
        bias = "HOLD"
        allowed = ["SELL_REJECTION", "BUY_BREAKOUT"]
        blocked = ["BUY_INTO_RESISTANCE_WITHOUT_BREAKOUT"]
        score = 40.0 + (10.0 if volume_confirmed else 0.0) + (8.0 if upper_rejection else 0.0)
        recommendation = "WAIT_FOR_SELL_REJECTION_OR_BUY_BREAKOUT_CONFIRMATION"
        reasons += ["resistance_context"]
    elif regime == "TRENDING":
        ema_200 = _safe_float(_row_get(row, "ema_200", 0.0))
        ema_400 = _safe_float(_row_get(row, "ema_400", 0.0))
        trend_bias = "BUY" if ema_200 > ema_400 and close > ema_200 else "SELL" if ema_200 < ema_400 and close < ema_200 else "HOLD"
        scenario = "TREND_CONTEXT_WAIT_PULLBACK"
        bias = trend_bias
        allowed = ["HTF_ALIGNED_PULLBACK", "BREAKOUT_RETEST"] if trend_bias in {"BUY", "SELL"} else []
        blocked = ["COUNTER_TREND_ENTRY"] if trend_bias in {"BUY", "SELL"} else []
        score = 38.0 + (10.0 if volume_confirmed else 0.0)
        recommendation = "WAIT_FOR_PULLBACK_OR_BREAKOUT_RETEST"
        reasons += ["trend_context"]
    else:
        scenario = "WAIT_FOR_CONFIRMATION"
        bias = "HOLD"
        allowed = ["BREAKOUT", "REJECTION"]
        blocked = ["LOW_CONVICTION_ENTRY"]
        score = 30.0 + (5.0 if volume_confirmed else 0.0)
        recommendation = "WAIT_FOR_CLEAR_SUPPORT_RESISTANCE_OR_BREAKOUT_CONTEXT"
        reasons += ["no_clear_operational_scenario"]

    # Safety overlay: avoid suggesting shorts near lower range and longs near upper range without confirmed break.
    if bias == "SELL" and range_pos < settings.no_trade_low and not close_below_support:
        blocked.append("SELL_LOW_IN_RANGE_WITHOUT_BREAKDOWN")
        recommendation = "KEEP_SELL_BLOCKED_UNLESS_BREAKDOWN_CONFIRMS"
        score = min(score, 45.0)
        reasons.append("sell_low_in_range_safety_overlay")
    if bias == "BUY" and range_pos > settings.no_trade_high and not close_above_resistance:
        blocked.append("BUY_HIGH_IN_RANGE_WITHOUT_BREAKOUT")
        recommendation = "KEEP_BUY_BLOCKED_UNLESS_BREAKOUT_CONFIRMS"
        score = min(score, 45.0)
        reasons.append("buy_high_in_range_safety_overlay")

    levels = {
        "last_price": round(close, 8),
        "local_support": round(local_support, 8),
        "local_resistance": round(local_resistance, 8),
        "macro_support": round(macro_support, 8),
        "macro_resistance": round(macro_resistance, 8),
        "range_pos_400": round(range_pos, 8),
        "dist_to_support_pct": round(_distance_pct(close, local_support) * 100.0, 6),
        "dist_to_resistance_pct": round(_distance_pct(close, local_resistance) * 100.0, 6),
        "atr": round(atr, 8),
    }
    candle = {
        "open": round(open_, 8),
        "high": round(high, 8),
        "low": round(low, 8),
        "close": round(close, 8),
        "volume": round(volume, 8),
        "body_ratio": round(body_ratio, 6),
        "upper_wick_ratio": round(upper_wick_ratio, 6),
        "lower_wick_ratio": round(lower_wick_ratio, 6),
        "volume_ratio_20": round(volume_ratio, 6),
    }
    context = {
        "symbol": symbol,
        "regime": regime,
        "volume_bias": volume_bias,
        "near_support": bool(near_support),
        "near_resistance": bool(near_resistance),
        "close_above_resistance": bool(close_above_resistance),
        "close_below_support": bool(close_below_support),
        "high_swept_resistance": bool(high_swept_resistance),
        "low_swept_support": bool(low_swept_support),
        "volume_confirmed": bool(volume_confirmed),
        "strong_body": bool(strong_body),
        "engulfing": round(engulfing, 4),
        "doji": round(doji, 4),
    }

    return ScenarioResult(
        scenario=scenario,
        directional_bias=bias,
        confidence_score=round(_clip(score, 0.0, 100.0), 6),
        current_zone=current_zone,
        recommendation=recommendation,
        allowed_setups=tuple(dict.fromkeys(allowed)),
        blocked_setups=tuple(dict.fromkeys(blocked)),
        reasons=tuple(dict.fromkeys(reasons)),
        levels=levels,
        candle=candle,
        context=context,
    )


def build_crypto_scenario_diagnostic(
    *,
    symbol: str,
    df: pd.DataFrame,
    cycle_id: str,
    candle_ts: str,
    final_verdict: Any = None,
    final_score: Any = None,
    signal_diagnostic: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = evaluate_crypto_intraday_scenario(df, symbol=symbol)
    sig = signal_diagnostic if isinstance(signal_diagnostic, dict) else {}
    conf = confidence if isinstance(confidence, dict) else {}
    payload = result.to_dict()
    payload.update({
        "event_type": SCENARIO_EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "candle_ts": candle_ts,
        "final_verdict": str(final_verdict or "HOLD").upper(),
        "final_score": _safe_int(final_score, 0),
        "technical_score": _safe_float(sig.get("technical_score"), _safe_float(conf.get("tech_score"), 0.0)),
        "intended_side": str(sig.get("intended_side") or ""),
        "dominant_filter": str(sig.get("dominant_filter") or ""),
        "diagnostic_reason": str(sig.get("diagnostic_reason") or ""),
        "ai_prob": _safe_float(sig.get("ai_prob"), _safe_float(conf.get("ai_prob"), 0.0)),
        "setup_quality": _safe_float(sig.get("setup_quality"), _safe_float(conf.get("setup_quality"), 0.0)),
        "scenario_alignment": _scenario_alignment(result.directional_bias, str(sig.get("intended_side") or "")),
        "ts": utc_now_iso(),
    })
    return payload


def _scenario_alignment(scenario_bias: str, intended_side: str) -> str:
    b = str(scenario_bias or "HOLD").upper()
    s = str(intended_side or "").upper()
    if b in {"BUY", "SELL"} and s == b:
        return "ALIGNED"
    if b in {"BUY", "SELL"} and s in {"BUY", "SELL"} and s != b:
        return "CONFLICT"
    if b in {"BUY", "SELL"} and s in {"", "HOLD"}:
        return "SCENARIO_HAS_DIRECTION_BUT_ENGINE_HOLD"
    if b == "HOLD" and s in {"BUY", "SELL"}:
        return "ENGINE_HAS_SIDE_BUT_SCENARIO_WAIT"
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


def _latest(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[-limit:]:
        out.append({
            "ts": row.get("ts"),
            "cycle_id": row.get("cycle_id"),
            "symbol": row.get("symbol"),
            "scenario": row.get("scenario"),
            "directional_bias": row.get("directional_bias"),
            "current_zone": row.get("current_zone"),
            "confidence_score": row.get("confidence_score"),
            "dominant_filter": row.get("dominant_filter"),
            "scenario_alignment": row.get("scenario_alignment"),
            "recommendation": row.get("recommendation"),
        })
    return out


def _recommendation(rows: list[dict[str, Any]], btc_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "status": "NO_SCENARIO_EVENTS",
            "action": "verify PAPER_CRYPTO_SCENARIO_ENABLED and run a paper cycle",
            "next_patch": "29.5.0a rerun after CRYPTO_SCENARIO_DIAGNOSTIC events exist",
        }
    btc_counter = Counter(str(r.get("scenario") or "UNKNOWN") for r in btc_rows)
    align_counter = Counter(str(r.get("scenario_alignment") or "UNKNOWN") for r in btc_rows)
    filter_counter = Counter(str(r.get("dominant_filter") or "UNKNOWN") for r in btc_rows)
    directional = [r for r in btc_rows if str(r.get("directional_bias") or "HOLD") in {"BUY", "SELL"}]
    engine_hold_with_scenario = [r for r in btc_rows if str(r.get("scenario_alignment")) == "SCENARIO_HAS_DIRECTION_BUT_ENGINE_HOLD"]
    mid_range = btc_counter.get("MID_RANGE_NO_TRADE", 0)
    no_direction = filter_counter.get("TECH_SCORE_LOW", 0) + filter_counter.get("NO_TECHNICAL_CANDIDATE", 0)

    if engine_hold_with_scenario:
        return {
            "status": "SCENARIO_SIDE_ATTRIBUTION_AVAILABLE",
            "action": "keep gates unchanged; use scenario side as diagnostic input for profile refinement, not direct trading",
            "next_patch": "29.5.0b Candlestick pattern feature engine + scenario integration",
            "btc_directional_scenarios": len(directional),
            "btc_engine_hold_with_scenario_direction": len(engine_hold_with_scenario),
            "dominant_btc_scenario": btc_counter.most_common(1)[0][0] if btc_counter else "UNKNOWN",
        }
    if mid_range >= max(1, len(btc_rows) // 2):
        return {
            "status": "MID_RANGE_DOMINANT",
            "action": "do not force trades; no-trade zone is dominant and should remain protective",
            "next_patch": "29.4.4c Paper unlock profile refinement only after more edge-of-range samples",
            "dominant_btc_scenario": "MID_RANGE_NO_TRADE",
        }
    if no_direction >= max(1, len(btc_rows) // 2):
        return {
            "status": "TECH_SIDE_ATTRIBUTION_WEAK",
            "action": "add richer candlestick/retest/reclaim features before relaxing thresholds",
            "next_patch": "29.5.0b Candlestick pattern feature engine + scenario integration",
            "dominant_btc_filter": filter_counter.most_common(1)[0][0] if filter_counter else "UNKNOWN",
        }
    return {
        "status": "SCENARIO_BASELINE_READY",
        "action": "use this report to guide profile refinement; do not change paper/live decisions automatically",
        "next_patch": "29.5.0b Candlestick pattern feature engine + scenario integration",
        "dominant_btc_scenario": btc_counter.most_common(1)[0][0] if btc_counter else "UNKNOWN",
        "dominant_alignment": align_counter.most_common(1)[0][0] if align_counter else "UNKNOWN",
    }


def build_crypto_scenario_report(data_dir: str | Path) -> dict[str, Any]:
    data_path = Path(data_dir)
    events_path = data_path / "paper_events.jsonl"
    events = read_events(events_path)
    scenario_events = [e for e in events if _event_type(e) == SCENARIO_EVENT_TYPE]
    event_counts = Counter(_event_type(e) for e in events)
    by_asset_raw: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in scenario_events:
        by_asset_raw[str(row.get("symbol") or "UNKNOWN")].append(row)

    by_asset: dict[str, Any] = {}
    for symbol, rows in sorted(by_asset_raw.items()):
        scenarios = Counter(str(r.get("scenario") or "UNKNOWN") for r in rows)
        zones = Counter(str(r.get("current_zone") or "UNKNOWN") for r in rows)
        directions = Counter(str(r.get("directional_bias") or "HOLD") for r in rows)
        alignment = Counter(str(r.get("scenario_alignment") or "UNKNOWN") for r in rows)
        filters = Counter(str(r.get("dominant_filter") or "UNKNOWN") for r in rows)
        by_asset[symbol] = {
            "scans": len(rows),
            "scenarios": dict(scenarios.most_common()),
            "zones": dict(zones.most_common()),
            "directional_bias": dict(directions.most_common()),
            "scenario_alignment": dict(alignment.most_common()),
            "dominant_filters": dict(filters.most_common()),
            "directional_scenarios": int(sum(v for k, v in directions.items() if k in {"BUY", "SELL"})),
            "mid_range_no_trade": int(scenarios.get("MID_RANGE_NO_TRADE", 0)),
            "confidence_score": _metrics([_safe_float(r.get("confidence_score"), 0.0) for r in rows]),
            "range_pos_400": _metrics([_safe_float(((r.get("levels") or {}).get("range_pos_400") if isinstance(r.get("levels"), dict) else 0.0), 0.0) for r in rows]),
            "recent": _latest(rows, limit=6),
        }

    btc_rows = by_asset_raw.get("BTC/USDT", [])
    scenario_counter = Counter(str(r.get("scenario") or "UNKNOWN") for r in scenario_events)
    alignment_counter = Counter(str(r.get("scenario_alignment") or "UNKNOWN") for r in scenario_events)
    direction_counter = Counter(str(r.get("directional_bias") or "HOLD") for r in scenario_events)
    decision = _recommendation(scenario_events, btc_rows)
    status = "PASS" if scenario_events else "WARN"
    if decision.get("status") in {"TECH_SIDE_ATTRIBUTION_WEAK", "MID_RANGE_DOMINANT"}:
        status = "WARN"

    return {
        "report_type": "crypto_intraday_scenario_engine",
        "prompt": "29.5.0a",
        "generated_at": utc_now_iso(),
        "status": status,
        "diagnostic_only": True,
        "strategy_changed": False,
        "opens_orders": False,
        "changes_thresholds": False,
        "enables_live_or_testnet": False,
        "files": {"events": str(events_path), "report": str(data_path / REPORT_NAME)},
        "counts": {
            "events_total": len(events),
            "scenario_events": len(scenario_events),
            "asset_scanned": event_counts.get("ASSET_SCANNED", 0),
            "signals_detected": event_counts.get("SIGNAL_DETECTED", 0),
            "orders_submitted": event_counts.get("PAPER_ORDER_SUBMITTED", 0),
            "positions_opened": event_counts.get("POSITION_OPENED", 0),
            "btc_scenario_events": len(btc_rows),
        },
        "scenarios": dict(scenario_counter.most_common()),
        "directional_bias": dict(direction_counter.most_common()),
        "scenario_alignment": dict(alignment_counter.most_common()),
        "by_asset": by_asset,
        "btc_focus": by_asset.get("BTC/USDT", {}),
        "recent_scenarios": _latest(scenario_events, limit=12),
        "decision": decision,
        "safety": {
            "diagnostic_only": True,
            "changes_thresholds": False,
            "opens_orders": False,
            "enables_live_or_testnet": False,
            "scenario_bias_operational_unlock": False,
        },
    }


def write_crypto_scenario_report(data_dir: str | Path) -> dict[str, Any]:
    path = Path(data_dir) / REPORT_NAME
    report = build_crypto_scenario_report(data_dir)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Build Prompt 29.5.0a crypto intraday scenario report")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    payload = write_crypto_scenario_report(args.data_dir)
    print(json.dumps({"status": payload.get("status"), "counts": payload.get("counts"), "decision": payload.get("decision")}, indent=2))
