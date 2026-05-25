"""Prompt 29.5.0f calibrated scenario-pattern-structure shadow review.

Diagnostic-only review layer that combines the 29.5.0d scenario/pattern
calibration candidate with the 29.5.0e market-structure map.  It compares:

- baseline scenario + pattern aligned candidates;
- calibrated BTC BUY_REJECTION pattern profile variants;
- the same variants after liquidity / supply-demand / structure filters.

Safety invariant: this module never opens orders, never changes paper unlock
settings, never changes thresholds, and never enables testnet or live routing.
It only writes ``calibrated_structure_shadow_report.json``.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable
import json
import math

import pandas as pd

from config import Config
from core.crypto_intraday_scenario import evaluate_crypto_intraday_scenario
from core.candlestick_patterns import detect_candlestick_patterns
from core.market_structure_map import (
    MarketStructureMapSettings,
    evaluate_market_structure_map,
)
from core.pattern_conditioned_shadow import (
    PatternConditionedShadowSettings,
    _add_minimal_structure_features,
    _cache_path_for_symbol,
    _evaluate_forward,
    _normalize_ohlcv,
    _read_cache,
    _safe_float,
    _safe_int,
)
from core.scenario_pattern_calibration import (
    BEARISH_CONFLICT_PATTERNS,
    BULLISH_CONFLICT_PATTERNS,
    ScenarioPatternCalibrationSettings,
    _bucket_key,
    _candidate_side,
    _conflicting_pattern_names,
    _pattern_conflict,
    _range_filter_ok,
)

REPORT_NAME = "calibrated_structure_shadow_report.json"
PROMPT_ID = "29.5.0f"
POSITIVE_OUTCOMES = {"TP1_ONLY", "TP2"}
NEGATIVE_OUTCOMES = {"SL"}


@dataclass(frozen=True)
class CalibratedStructureShadowSettings:
    enabled: bool = True
    historical_enabled: bool = True
    symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT")
    timeframe: str = "5m"
    max_rows_per_asset: int = 5000
    min_warmup_rows: int = 450
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    score_thresholds: tuple[float, ...] = (60.0, 65.0, 70.0)
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    candidate_profile_name: str = "BTC_BUY_REJECTION_PATTERN_CONFIRMED"
    support_range_pos_max: float = 0.40
    resistance_range_pos_min: float = 0.60
    min_variant_candidates: int = 50
    min_structure_expectancy_r: float = 0.10
    min_structure_win_rate_pct: float = 52.0
    max_structure_loss_rate_pct: float = 45.0
    max_confirmed_time_exit_rate_pct: float = 60.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "CalibratedStructureShadowSettings":
        spc = ScenarioPatternCalibrationSettings.from_config(cfg)
        return cls(
            enabled=bool(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_HISTORICAL_ENABLED", True)),
            symbols=tuple(_parse_symbols(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_SYMBOLS", ",".join(spc.symbols))) or list(spc.symbols)),
            timeframe=str(getattr(cfg, "PAPER_DEFAULT_TIMEFRAME", spc.timeframe) or spc.timeframe),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_ROWS_PER_ASSET", spc.max_rows_per_asset), spc.max_rows_per_asset)),
            min_warmup_rows=max(50, _safe_int(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_WARMUP_ROWS", spc.min_warmup_rows), spc.min_warmup_rows)),
            eval_stride=max(1, _safe_int(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_EVAL_STRIDE", 3), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_STRUCTURE_WINDOW_ROWS", getattr(cfg, "MARKET_STRUCTURE_MAP_EVALUATION_WINDOW_ROWS", 900)), 900)),
            score_thresholds=_parse_float_tuple(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_SCORE_THRESHOLDS", "60,65,70"), (60.0, 65.0, 70.0)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", spc.focus_symbol) or spc.focus_symbol).upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", spc.focus_bucket) or spc.focus_bucket).upper(),
            candidate_profile_name=str(getattr(cfg, "SCENARIO_PATTERN_CANDIDATE_PROFILE", spc.candidate_profile_name) or spc.candidate_profile_name),
            support_range_pos_max=_safe_float(getattr(cfg, "SCENARIO_PATTERN_SUPPORT_RANGE_POS_MAX", spc.support_range_pos_max), spc.support_range_pos_max),
            resistance_range_pos_min=_safe_float(getattr(cfg, "SCENARIO_PATTERN_RESISTANCE_RANGE_POS_MIN", spc.resistance_range_pos_min), spc.resistance_range_pos_min),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_VARIANT_CANDIDATES", 50), 50)),
            min_structure_expectancy_r=_safe_float(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_EXPECTANCY_R", 0.10), 0.10),
            min_structure_win_rate_pct=_safe_float(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MIN_WIN_RATE_PCT", 52.0), 52.0),
            max_structure_loss_rate_pct=_safe_float(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_LOSS_RATE_PCT", 45.0), 45.0),
            max_confirmed_time_exit_rate_pct=_safe_float(getattr(cfg, "CALIBRATED_STRUCTURE_SHADOW_MAX_TIME_EXIT_RATE_PCT", 60.0), 60.0),
        )

    def scenario_settings(self) -> ScenarioPatternCalibrationSettings:
        base = ScenarioPatternCalibrationSettings.from_config()
        return ScenarioPatternCalibrationSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            symbols=self.symbols,
            timeframe=self.timeframe,
            max_rows_per_asset=self.max_rows_per_asset,
            min_warmup_rows=self.min_warmup_rows,
            eval_stride=self.eval_stride,
            horizons=base.horizons,
            stop_loss_pct=base.stop_loss_pct,
            tp1_pct=base.tp1_pct,
            tp2_pct=base.tp2_pct,
            score_thresholds=tuple(sorted(set(self.score_thresholds + base.score_thresholds))),
            min_bucket_candidates=base.min_bucket_candidates,
            min_profile_candidates=base.min_profile_candidates,
            min_bucket_expectancy_r=base.min_bucket_expectancy_r,
            min_profile_expectancy_r=base.min_profile_expectancy_r,
            min_profile_win_rate_pct=base.min_profile_win_rate_pct,
            max_profile_loss_rate_pct=base.max_profile_loss_rate_pct,
            support_range_pos_max=self.support_range_pos_max,
            resistance_range_pos_min=self.resistance_range_pos_min,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            candidate_profile_name=self.candidate_profile_name,
        )

    def market_structure_settings(self) -> MarketStructureMapSettings:
        base = MarketStructureMapSettings.from_config()
        return MarketStructureMapSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            symbols=self.symbols,
            timeframe=self.timeframe,
            max_rows_per_asset=self.max_rows_per_asset,
            min_warmup_rows=self.min_warmup_rows,
            eval_stride=base.eval_stride,
            max_snapshots_per_asset=base.max_snapshots_per_asset,
            evaluation_window_rows=self.structure_window_rows,
            swing_left=base.swing_left,
            swing_right=base.swing_right,
            recent_swing_lookback=base.recent_swing_lookback,
            equal_level_tolerance_pct=base.equal_level_tolerance_pct,
            liquidity_near_pct=base.liquidity_near_pct,
            zone_atr_mult=base.zone_atr_mult,
            retest_tolerance_pct=base.retest_tolerance_pct,
            confirmation_body_ratio=base.confirmation_body_ratio,
            confirmation_close_buffer_pct=base.confirmation_close_buffer_pct,
            focus_symbol=self.focus_symbol,
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_symbols(value: Any) -> list[str]:
    return [x.strip().upper() for x in str(value or "").replace(";", ",").split(",") if x.strip()]


def _parse_float_tuple(value: Any, default: tuple[float, ...]) -> tuple[float, ...]:
    try:
        vals = [_safe_float(str(x).strip(), float("nan")) for x in str(value).replace(";", ",").split(",") if str(x).strip()]
        out = tuple(sorted({float(x) for x in vals if math.isfinite(float(x))}))
        return out or default
    except Exception:
        return default


def _pct(n: float, d: float) -> float:
    return 0.0 if d <= 0 else n / d * 100.0


def _metrics(values: Iterable[float]) -> dict[str, float]:
    vals = sorted([_safe_float(v, float("nan")) for v in values])
    vals = [v for v in vals if math.isfinite(v)]
    if not vals:
        return {"count": 0, "min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0, "avg": 0.0}

    def pick(q: float) -> float:
        if len(vals) == 1:
            return vals[0]
        idx = int(round((len(vals) - 1) * q))
        return vals[max(0, min(len(vals) - 1, idx))]

    return {
        "count": len(vals),
        "min": round(vals[0], 8),
        "p25": round(pick(0.25), 8),
        "median": round(pick(0.50), 8),
        "p75": round(pick(0.75), 8),
        "max": round(vals[-1], 8),
        "avg": round(float(mean(vals)), 8),
    }


def _outcome_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(str(r.get("outcome") or "UNKNOWN") for r in rows)
    return {
        "TP1_ONLY": int(c.get("TP1_ONLY", 0)),
        "TP2": int(c.get("TP2", 0)),
        "SL": int(c.get("SL", 0)),
        "TIME_EXIT": int(c.get("TIME_EXIT", 0)),
        "NO_TOUCH": int(c.get("NO_TOUCH", 0)),
        "INVALID": int(c.get("INVALID", 0)),
        "OTHER": int(sum(v for k, v in c.items() if k not in {"TP1_ONLY", "TP2", "SL", "TIME_EXIT", "NO_TOUCH", "INVALID"})),
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "candidates": 0,
            "expectancy_r": 0.0,
            "win_rate_pct": 0.0,
            "loss_rate_pct": 0.0,
            "tp1_rate_pct": 0.0,
            "tp2_rate_pct": 0.0,
            "sl_rate_pct": 0.0,
            "time_exit_rate_pct": 0.0,
            "outcomes": _outcome_counts([]),
            "r_distribution": _metrics([]),
            "pattern_score_distribution": _metrics([]),
            "map_score_distribution": _metrics([]),
            "range_pos_400_distribution": _metrics([]),
        }
    rs = [_safe_float(r.get("r"), 0.0) for r in rows]
    outcomes = _outcome_counts(rows)
    wins = sum(1 for r in rows if str(r.get("outcome")) in POSITIVE_OUTCOMES or _safe_float(r.get("r"), 0.0) > 0)
    losses = sum(1 for r in rows if str(r.get("outcome")) in NEGATIVE_OUTCOMES or _safe_float(r.get("r"), 0.0) < 0)
    summaries = Counter(str(r.get("confirmation_summary") or "NA") for r in rows)
    locations = Counter(str(r.get("price_location") or "NA") for r in rows)
    biases = Counter(str(r.get("structure_bias") or "NA") for r in rows)
    return {
        "candidates": len(rows),
        "expectancy_r": round(float(mean(rs)), 6) if rs else 0.0,
        "win_rate_pct": round(_pct(wins, len(rows)), 4),
        "loss_rate_pct": round(_pct(losses, len(rows)), 4),
        "tp1_rate_pct": round(_pct(outcomes.get("TP1_ONLY", 0), len(rows)), 4),
        "tp2_rate_pct": round(_pct(outcomes.get("TP2", 0), len(rows)), 4),
        "sl_rate_pct": round(_pct(outcomes.get("SL", 0), len(rows)), 4),
        "time_exit_rate_pct": round(_pct(outcomes.get("TIME_EXIT", 0), len(rows)), 4),
        "outcomes": outcomes,
        "r_distribution": _metrics(rs),
        "pattern_score_distribution": _metrics([_safe_float(r.get("pattern_score"), 0.0) for r in rows]),
        "map_score_distribution": _metrics([_safe_float(r.get("map_score"), 0.0) for r in rows]),
        "range_pos_400_distribution": _metrics([_safe_float(r.get("range_pos_400"), 0.5) for r in rows]),
        "structure_bias_counts": dict(biases.most_common(10)),
        "price_location_counts": dict(locations.most_common(10)),
        "confirmation_summary_counts": dict(summaries.most_common(10)),
        "structure_context_rate_pct": round(_pct(sum(1 for r in rows if r.get("structure_context_ok")), len(rows)), 4),
        "structure_confirmed_rate_pct": round(_pct(sum(1 for r in rows if r.get("structure_confirmed")), len(rows)), 4),
    }


def _structure_context_ok(side: str, structure: dict[str, Any]) -> bool:
    side = str(side or "").upper()
    bias = str(structure.get("structure_bias") or "").upper()
    loc = str(structure.get("price_location") or "").upper()
    summary = str(structure.get("confirmation_summary") or "").upper()
    nearest = structure.get("nearest_liquidity") if isinstance(structure.get("nearest_liquidity"), dict) else {}
    nearest_side = str(nearest.get("side") or "").upper()
    nearest_dist = _safe_float(nearest.get("distance_pct"), 999.0)

    in_demand = bool(structure.get("in_demand_zone")) or "DEMAND" in loc
    in_supply = bool(structure.get("in_supply_zone")) or "SUPPLY" in loc
    lower = "LOW" in loc or "DEMAND" in loc
    upper = "HIGH" in loc or "SUPPLY" in loc
    near_below = bool(structure.get("liquidity_below_lows")) or (nearest_side == "BELOW" and nearest_dist <= 0.50)
    near_above = bool(structure.get("liquidity_above_highs")) or (nearest_side == "ABOVE" and nearest_dist <= 0.50)

    if side == "BUY":
        constructive = (
            bias.startswith("BULLISH")
            or in_demand
            or lower
            or near_below
            or bool(structure.get("mss_bullish"))
            or bool(structure.get("choch_bullish"))
            or bool(structure.get("bos_bullish"))
            or "BULLISH" in summary
            or "DEMAND" in summary
            or "LIQUIDITY" in summary
        )
        hard_contra = in_supply and bias.startswith("BEARISH") and not (structure.get("mss_bullish") or structure.get("choch_bullish"))
        return bool(constructive and not hard_contra)
    if side == "SELL":
        constructive = (
            bias.startswith("BEARISH")
            or in_supply
            or upper
            or near_above
            or bool(structure.get("mss_bearish"))
            or bool(structure.get("choch_bearish"))
            or bool(structure.get("bos_bearish"))
            or "BEARISH" in summary
            or "SUPPLY" in summary
            or "LIQUIDITY" in summary
        )
        hard_contra = in_demand and bias.startswith("BULLISH") and not (structure.get("mss_bearish") or structure.get("choch_bearish"))
        return bool(constructive and not hard_contra)
    return False


def _structure_confirmed(side: str, structure: dict[str, Any]) -> bool:
    side = str(side or "").upper()
    if side == "BUY":
        return bool(
            structure.get("confirmation_close")
            and (
                structure.get("bos_bullish")
                or structure.get("choch_bullish")
                or structure.get("mss_bullish")
                or structure.get("breakout_retest_confirmed")
            )
        )
    if side == "SELL":
        return bool(
            structure.get("confirmation_close")
            and (
                structure.get("bos_bearish")
                or structure.get("choch_bearish")
                or structure.get("mss_bearish")
                or structure.get("breakdown_retest_confirmed")
            )
        )
    return False


def _sample_tail(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    return rows[-limit:]


def _collect_historical_rows(data_dir: Path, settings: CalibratedStructureShadowSettings) -> dict[str, Any]:
    if not settings.historical_enabled:
        return {"status": "DISABLED", "candidate_rows": [], "warnings": ["historical disabled"], "by_asset": {}}

    scenario_settings = settings.scenario_settings()
    structure_settings = settings.market_structure_settings()
    shadow_settings = scenario_settings.shadow_settings()
    warnings: list[str] = []
    candidate_rows: list[dict[str, Any]] = []
    by_asset: dict[str, Any] = {}
    eval_counts: Counter[str] = Counter()
    candidate_counts_pre_structure: Counter[str] = Counter()

    for symbol in settings.symbols:
        cache_path = _cache_path_for_symbol(data_dir, symbol, settings.timeframe)
        if cache_path is None:
            warnings.append(f"missing_cache:{symbol}")
            by_asset[symbol] = {"status": "MISSING_CACHE", "candidate_rows": 0, "structured_rows": 0}
            continue
        try:
            raw = _read_cache(cache_path)
            df = _normalize_ohlcv(raw, symbol)
            if len(df) > settings.max_rows_per_asset:
                df = df.tail(settings.max_rows_per_asset).reset_index(drop=True)
            df = _add_minimal_structure_features(df)
        except Exception as exc:
            msg = f"cache_prepare_failed:{symbol}:{exc.__class__.__name__}:{str(exc).splitlines()[0][:220]}"
            warnings.append(msg)
            by_asset[symbol] = {"status": "READ_ERROR", "error": str(exc), "cache_path": str(cache_path), "candidate_rows": 0, "structured_rows": 0}
            continue

        start = max(3, min(settings.min_warmup_rows, max(3, len(df) - max(shadow_settings.horizons) - 1)))
        end = max(start, len(df) - max(shadow_settings.horizons))
        raw_candidates: list[dict[str, Any]] = []
        for idx in range(start, end, settings.eval_stride):
            eval_counts[symbol] += 1
            window = df.iloc[: idx + 1]
            try:
                scenario = evaluate_crypto_intraday_scenario(window, symbol=symbol)
                pattern = detect_candlestick_patterns(window, symbol=symbol, scenario=scenario.to_dict())
            except Exception as exc:
                if len(warnings) < 40:
                    warnings.append(f"scenario_pattern_eval_failed:{symbol}:{idx}:{exc.__class__.__name__}:{str(exc).splitlines()[0][:220]}")
                continue
            side = _candidate_side(pattern.pattern_bias, scenario.directional_bias, pattern.scenario_integration)
            if side not in {"BUY", "SELL"}:
                continue
            row = df.iloc[idx]
            forward = _evaluate_forward(df, idx, side, shadow_settings)
            patterns = list(pattern.patterns)
            conflicting_names = _conflicting_pattern_names(side, patterns)
            has_conflict = bool(conflicting_names) or _pattern_conflict(side, pattern.bullish_patterns, pattern.bearish_patterns)
            base_row = {
                "symbol": symbol,
                "idx": int(idx),
                "datetime": str(row.get("datetime", idx)),
                "side": side,
                "scenario": scenario.scenario,
                "scenario_bias": scenario.directional_bias,
                "scenario_score": float(scenario.confidence_score),
                "pattern_bias": pattern.pattern_bias,
                "pattern_score": float(pattern.pattern_score),
                "patterns": patterns,
                "bullish_patterns": list(pattern.bullish_patterns),
                "bearish_patterns": list(pattern.bearish_patterns),
                "scenario_integration": pattern.scenario_integration,
                "alignment": "PATTERN_SCENARIO_ALIGNED",
                "has_conflicting_patterns": bool(has_conflict),
                "conflicting_patterns": conflicting_names,
                "range_pos_400": _safe_float(row.get("range_pos_400"), 0.5),
                "near_support": bool(row.get("near_support", False)),
                "near_resistance": bool(row.get("near_resistance", False)),
                "bucket": _bucket_key(side, scenario.scenario),
                "asset_bucket": f"{symbol}:{_bucket_key(side, scenario.scenario)}",
                "r": _safe_float(forward.get("r"), 0.0),
                "outcome": forward.get("outcome"),
                "forward": forward,
            }
            base_row["range_filter_ok"] = _range_filter_ok(base_row, scenario_settings)
            raw_candidates.append(base_row)

        candidate_counts_pre_structure[symbol] = len(raw_candidates)
        structured_candidates: list[dict[str, Any]] = []
        for base_row in _sample_tail(raw_candidates, settings.max_structure_candidates_per_asset):
            idx = _safe_int(base_row.get("idx"), 0)
            left = max(0, idx + 1 - settings.structure_window_rows)
            structure_window = df.iloc[left : idx + 1]
            try:
                structure = evaluate_market_structure_map(structure_window, symbol=symbol, settings=structure_settings).to_dict()
            except Exception as exc:
                if len(warnings) < 40:
                    warnings.append(f"structure_eval_failed:{symbol}:{idx}:{exc.__class__.__name__}:{str(exc).splitlines()[0][:220]}")
                continue
            enriched = dict(base_row)
            enriched.update({
                "structure_bias": structure.get("structure_bias", "UNKNOWN"),
                "trend_state": structure.get("trend_state", "UNKNOWN"),
                "price_location": structure.get("price_location", "UNKNOWN"),
                "map_score": _safe_float(structure.get("map_score"), 0.0),
                "nearest_liquidity": structure.get("nearest_liquidity", {}),
                "liquidity_above_highs": bool(structure.get("liquidity_above_highs")),
                "liquidity_below_lows": bool(structure.get("liquidity_below_lows")),
                "in_demand_zone": bool(structure.get("in_demand_zone")),
                "in_supply_zone": bool(structure.get("in_supply_zone")),
                "bos_bullish": bool(structure.get("bos_bullish")),
                "bos_bearish": bool(structure.get("bos_bearish")),
                "choch_bullish": bool(structure.get("choch_bullish")),
                "choch_bearish": bool(structure.get("choch_bearish")),
                "mss_bullish": bool(structure.get("mss_bullish")),
                "mss_bearish": bool(structure.get("mss_bearish")),
                "breakout_retest_confirmed": bool(structure.get("breakout_retest_confirmed")),
                "breakdown_retest_confirmed": bool(structure.get("breakdown_retest_confirmed")),
                "failed_retest": bool(structure.get("failed_retest")),
                "confirmation_close": bool(structure.get("confirmation_close")),
                "missing_confirmation": list(structure.get("missing_confirmation") or []),
                "confirmation_summary": structure.get("confirmation_summary", "NA"),
                "demand_zone_low": _safe_float(structure.get("demand_zone_low"), 0.0),
                "demand_zone_high": _safe_float(structure.get("demand_zone_high"), 0.0),
                "supply_zone_low": _safe_float(structure.get("supply_zone_low"), 0.0),
                "supply_zone_high": _safe_float(structure.get("supply_zone_high"), 0.0),
            })
            enriched["structure_context_ok"] = _structure_context_ok(enriched["side"], enriched)
            enriched["structure_confirmed"] = _structure_confirmed(enriched["side"], enriched)
            structured_candidates.append(enriched)
            candidate_rows.append(enriched)

        by_asset[symbol] = {
            "status": "PASS",
            "cache_path": str(cache_path),
            "rows_loaded": int(len(df)),
            "scenario_pattern_evaluation_rows": int(eval_counts[symbol]),
            "candidate_rows_pre_structure": int(candidate_counts_pre_structure[symbol]),
            "structured_rows": int(len(structured_candidates)),
            "sampling": {
                "mode": "tail_recent_candidates",
                "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
                "structure_window_rows": settings.structure_window_rows,
                "eval_stride": settings.eval_stride,
            },
            "summary": _summarize_rows(structured_candidates),
        }

    return {
        "status": "PASS" if candidate_rows else "WARN",
        "candidate_rows": candidate_rows,
        "warnings": warnings,
        "by_asset": by_asset,
        "scenario_pattern_evaluation_rows": int(sum(eval_counts.values())),
        "candidate_rows_pre_structure": int(sum(candidate_counts_pre_structure.values())),
        "structured_rows": int(len(candidate_rows)),
    }


def _variant(name: str, rows: list[dict[str, Any]], fn: Callable[[dict[str, Any]], bool], settings: CalibratedStructureShadowSettings, description: str) -> dict[str, Any]:
    selected = [r for r in rows if fn(r)]
    summary = _summarize_rows(selected)
    sample_ok = summary["candidates"] >= settings.min_variant_candidates
    expectancy_ok = summary["expectancy_r"] >= settings.min_structure_expectancy_r
    win_ok = summary["win_rate_pct"] >= settings.min_structure_win_rate_pct
    loss_ok = summary["loss_rate_pct"] <= settings.max_structure_loss_rate_pct
    time_exit_ok = summary["time_exit_rate_pct"] <= settings.max_confirmed_time_exit_rate_pct
    passes = bool(sample_ok and expectancy_ok and win_ok and loss_ok and time_exit_ok)
    return {
        "name": name,
        "description": description,
        "passes_candidate_gate": passes,
        "gate_checks": {
            "sample_ok": sample_ok,
            "expectancy_ok": expectancy_ok,
            "win_rate_ok": win_ok,
            "loss_rate_ok": loss_ok,
            "time_exit_ok": time_exit_ok,
            "min_candidates": settings.min_variant_candidates,
            "min_expectancy_r": settings.min_structure_expectancy_r,
            "min_win_rate_pct": settings.min_structure_win_rate_pct,
            "max_loss_rate_pct": settings.max_structure_loss_rate_pct,
            "max_time_exit_rate_pct": settings.max_confirmed_time_exit_rate_pct,
        },
        **summary,
    }


def _build_variants(rows: list[dict[str, Any]], settings: CalibratedStructureShadowSettings) -> list[dict[str, Any]]:
    focus = lambda r: str(r.get("symbol") or "").upper() == settings.focus_symbol and str(r.get("bucket") or "").upper() == settings.focus_bucket
    clean = lambda r: (not r.get("has_conflicting_patterns")) and bool(r.get("range_filter_ok"))
    variants: list[dict[str, Any]] = [
        _variant("baseline_scenario_pattern_structured_sample", rows, lambda r: True, settings, "All aligned scenario+pattern candidates for which structure was evaluated."),
        _variant("clean_pattern_range_filter", rows, lambda r: clean(r), settings, "No conflicting pattern and support/resistance range filter passed."),
        _variant("structure_context_all_assets", rows, lambda r: bool(r.get("structure_context_ok")), settings, "Any asset with constructive structure context."),
        _variant("structure_confirmed_all_assets", rows, lambda r: bool(r.get("structure_confirmed")), settings, "Any asset with confirmation_close plus BOS/CHOCH/MSS/retest."),
        _variant("btc_focus_clean", rows, lambda r: focus(r) and clean(r), settings, "BTC BUY_REJECTION focus bucket after clean pattern/range filter."),
    ]
    for threshold in settings.score_thresholds:
        t = float(threshold)
        variants.append(_variant(
            f"btc_focus_score_{int(t)}_clean",
            rows,
            lambda r, t=t: focus(r) and clean(r) and _safe_float(r.get("pattern_score"), 0.0) >= t,
            settings,
            f"BTC focus clean profile with pattern_score >= {t:g}.",
        ))
        variants.append(_variant(
            f"btc_focus_score_{int(t)}_structure_context",
            rows,
            lambda r, t=t: focus(r) and clean(r) and _safe_float(r.get("pattern_score"), 0.0) >= t and bool(r.get("structure_context_ok")),
            settings,
            f"BTC focus clean profile with pattern_score >= {t:g} and constructive structure context.",
        ))
        variants.append(_variant(
            f"btc_focus_score_{int(t)}_structure_confirmed",
            rows,
            lambda r, t=t: focus(r) and clean(r) and _safe_float(r.get("pattern_score"), 0.0) >= t and bool(r.get("structure_confirmed")),
            settings,
            f"BTC focus clean profile with pattern_score >= {t:g} and hard structural confirmation.",
        ))
    return variants


def _rank_variants(variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = list(variants)
    ranked.sort(
        key=lambda v: (
            bool(v.get("passes_candidate_gate")),
            _safe_float(v.get("expectancy_r"), 0.0),
            _safe_float(v.get("win_rate_pct"), 0.0),
            _safe_int(v.get("candidates"), 0),
        ),
        reverse=True,
    )
    for idx, item in enumerate(ranked, start=1):
        item["rank"] = idx
    return ranked


def _fallback_from_reports(data_dir: Path, settings: CalibratedStructureShadowSettings) -> dict[str, Any]:
    spc_path = data_dir / "scenario_pattern_calibration_report.json"
    msm_path = data_dir / "market_structure_map_report.json"
    spc: dict[str, Any] = {}
    msm: dict[str, Any] = {}
    for path, target in ((spc_path, "spc"), (msm_path, "msm")):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                if target == "spc":
                    spc = payload
                else:
                    msm = payload
        except Exception:
            continue
    decision = spc.get("decision", {}) if isinstance(spc.get("decision"), dict) else {}
    focus = decision.get("focus_bucket_baseline", {}) if isinstance(decision.get("focus_bucket_baseline"), dict) else {}
    focus_grid = spc.get("focus_profile_threshold_grid", []) if isinstance(spc.get("focus_profile_threshold_grid"), list) else []
    msm_dec = msm.get("decision", {}) if isinstance(msm.get("decision"), dict) else {}
    return {
        "available": bool(spc or msm),
        "reason": "detailed parquet replay unavailable; using 29.5.0d and 29.5.0e report summaries only",
        "scenario_pattern_report": str(spc_path),
        "market_structure_map_report": str(msm_path),
        "scenario_pattern_status": spc.get("status", "MISSING") if spc else "MISSING",
        "market_structure_status": msm.get("status", "MISSING") if msm else "MISSING",
        "scenario_pattern_decision": decision.get("status", "NA"),
        "focus_bucket_baseline": focus,
        "focus_profile_threshold_grid": focus_grid,
        "market_structure_focus_latest": msm_dec.get("focus_latest", {}) if isinstance(msm_dec.get("focus_latest"), dict) else {},
        "counts": {
            "scenario_pattern_historical_candidates": ((spc.get("counts") or {}).get("historical_candidates", 0) if isinstance(spc.get("counts"), dict) else 0),
            "market_structure_snapshots": ((msm.get("counts") or {}).get("historical_snapshots_evaluated", 0) if isinstance(msm.get("counts"), dict) else 0),
        },
        "candidate_profile": {
            "name": settings.candidate_profile_name,
            "asset": settings.focus_symbol,
            "bucket": settings.focus_bucket,
            "status": "NOT_APPROVED_FALLBACK_ONLY",
        },
    }


def _decision(variants: list[dict[str, Any]], fallback: dict[str, Any], settings: CalibratedStructureShadowSettings) -> dict[str, Any]:
    passing = [v for v in variants if v.get("passes_candidate_gate")]
    focus_structure = [
        v for v in variants
        if str(v.get("name") or "").startswith("btc_focus_") and "structure" in str(v.get("name") or "")
    ]
    passing_focus = [v for v in focus_structure if v.get("passes_candidate_gate")]
    best = passing_focus[0] if passing_focus else (passing[0] if passing else None)
    if best:
        return {
            "status": "STRUCTURE_FILTER_CANDIDATE",
            "reason": "at least one scenario-pattern-structure variant passed shadow gates, but it remains non-operational until paper unlock refinement",
            "candidate_profile": {
                "name": settings.candidate_profile_name,
                "asset": settings.focus_symbol,
                "bucket": settings.focus_bucket,
                "recommended_variant": best.get("name"),
                "status": "NON_OPERATIONAL_STRUCTURE_FILTER_CANDIDATE",
                "no_orders": True,
                "no_live": True,
                "no_testnet": True,
            },
            "best_variant": best,
            "operational_unlock_allowed": False,
            "next_patch": "29.4.4c paper unlock profile refinement only after manual review; otherwise collect more shadow evidence",
        }
    if fallback.get("available") and not variants:
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": fallback.get("reason", "fallback summary only"),
            "candidate_profile": fallback.get("candidate_profile", {}),
            "operational_unlock_allowed": False,
            "next_patch": "rerun 29.5.0f locally with parquet support or collect more structure-aligned shadow rows",
            "fallback_summary_only": True,
        }
    best_watch = variants[0] if variants else {}
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "structure filters did not pass calibrated shadow gates with enough sample/expectancy/win-rate/loss-rate evidence",
        "candidate_profile": {
            "name": settings.candidate_profile_name,
            "asset": settings.focus_symbol,
            "bucket": settings.focus_bucket,
            "status": "NOT_APPROVED_KEEP_DIAGNOSTIC",
            "no_orders": True,
            "no_live": True,
            "no_testnet": True,
        },
        "best_watchlist_variant": best_watch,
        "operational_unlock_allowed": False,
        "next_patch": "collect more structure-confirmed shadow rows or refine structure filters before paper unlock refinement",
    }


def _settings_payload(settings: CalibratedStructureShadowSettings) -> dict[str, Any]:
    return {
        "symbols": list(settings.symbols),
        "timeframe": settings.timeframe,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "min_warmup_rows": settings.min_warmup_rows,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "score_thresholds": list(settings.score_thresholds),
        "focus_symbol": settings.focus_symbol,
        "focus_bucket": settings.focus_bucket,
        "candidate_profile_name": settings.candidate_profile_name,
        "support_range_pos_max": settings.support_range_pos_max,
        "resistance_range_pos_min": settings.resistance_range_pos_min,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_structure_expectancy_r": settings.min_structure_expectancy_r,
        "min_structure_win_rate_pct": settings.min_structure_win_rate_pct,
        "max_structure_loss_rate_pct": settings.max_structure_loss_rate_pct,
        "max_confirmed_time_exit_rate_pct": settings.max_confirmed_time_exit_rate_pct,
    }


def build_calibrated_structure_shadow_report(data_dir: str | Path = "data", settings: CalibratedStructureShadowSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or CalibratedStructureShadowSettings.from_config()
    historical = _collect_historical_rows(base, settings)
    rows = list(historical.get("candidate_rows") or [])
    variants = _rank_variants(_build_variants(rows, settings)) if rows else []
    fallback = _fallback_from_reports(base, settings) if not rows else {"available": False}
    decision = _decision(variants, fallback, settings)
    if not settings.enabled:
        status = "DISABLED"
    elif decision.get("status") == "STRUCTURE_FILTER_CANDIDATE":
        status = "PASS"
    else:
        status = "WARN"

    report = {
        "report_type": "calibrated_structure_shadow_review",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "safety": {
            "no_orders": True,
            "no_live": True,
            "no_testnet": True,
            "paper_unlock_unchanged": True,
            "risk_unchanged": True,
            "diagnostic_only": True,
        },
        "counts": {
            "scenario_pattern_evaluation_rows": historical.get("scenario_pattern_evaluation_rows", 0),
            "candidate_rows_pre_structure": historical.get("candidate_rows_pre_structure", 0),
            "structured_candidate_rows": len(rows),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "settings": _settings_payload(settings),
        "historical_summary": _summarize_rows(rows),
        "variant_ranking": variants,
        "variant_ranking_top": variants[:12],
        "by_asset": historical.get("by_asset", {}),
        "fallback": fallback,
        "filters": {
            "clean_pattern_filter": {
                "exclude_conflicting_patterns": True,
                "buy_conflicting_bearish_patterns": list(BEARISH_CONFLICT_PATTERNS),
                "sell_conflicting_bullish_patterns": list(BULLISH_CONFLICT_PATTERNS),
                "support_range_pos_400_max": settings.support_range_pos_max,
                "resistance_range_pos_400_min": settings.resistance_range_pos_min,
            },
            "structure_context_filter": {
                "buy": "bullish bias, demand/lower range, nearby liquidity below, or bullish BOS/CHOCH/MSS context",
                "sell": "bearish bias, supply/upper range, nearby liquidity above, or bearish BOS/CHOCH/MSS context",
            },
            "structure_confirmation_filter": {
                "buy": "confirmation_close plus bullish BOS/CHOCH/MSS or breakout retest",
                "sell": "confirmation_close plus bearish BOS/CHOCH/MSS or breakdown retest",
            },
        },
        "recent_rows": [
            {
                "symbol": r.get("symbol"),
                "datetime": r.get("datetime"),
                "side": r.get("side"),
                "bucket": r.get("bucket"),
                "pattern_score": r.get("pattern_score"),
                "range_pos_400": r.get("range_pos_400"),
                "structure_bias": r.get("structure_bias"),
                "price_location": r.get("price_location"),
                "confirmation_summary": r.get("confirmation_summary"),
                "structure_context_ok": r.get("structure_context_ok"),
                "structure_confirmed": r.get("structure_confirmed"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
            }
            for r in rows[-20:]
        ],
        "warnings": historical.get("warnings", []),
        "files": {
            "report": str(base / REPORT_NAME),
            "scenario_pattern_calibration": str(base / "scenario_pattern_calibration_report.json"),
            "market_structure_map": str(base / "market_structure_map_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_calibrated_structure_shadow_report(data_dir: str | Path = "data", settings: CalibratedStructureShadowSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_calibrated_structure_shadow_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "CalibratedStructureShadowSettings",
    "build_calibrated_structure_shadow_report",
    "write_calibrated_structure_shadow_report",
]
