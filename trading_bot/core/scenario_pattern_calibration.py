"""Prompt 29.5.0d scenario-pattern calibration.

Diagnostic-only calibration layer for Prompt 29.5.0a/0b/0c outputs.
It replays scenario + candlestick candidates on historical OHLCV caches, ranks
asset/side/scenario buckets, searches conservative pattern-score filters and
proposes (but never enables) a calibrated paper profile candidate.

Safety invariant: this module never changes strategy thresholds, paper unlock
settings, testnet routing, live execution or order flow.  It only writes
``scenario_pattern_calibration_report.json``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
import json
import math

import pandas as pd

from config import Config
from core.crypto_intraday_scenario import evaluate_crypto_intraday_scenario
from core.candlestick_patterns import detect_candlestick_patterns
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

REPORT_NAME = "scenario_pattern_calibration_report.json"
PROMPT_ID = "29.5.0d"

POSITIVE_OUTCOMES = {"TP1_ONLY", "TP2"}
NEGATIVE_OUTCOMES = {"SL"}
TIME_OUTCOME = "TIME_EXIT"
DEFAULT_NEGATIVE_BUCKETS = (
    "SELL_SELL_BREAKDOWN_CANDIDATE",
    "BUY_BUY_BREAKOUT_CANDIDATE:SOL/USDT",
    "SELL_SELL_BREAKDOWN_CANDIDATE:SOL/USDT",
)
BEARISH_CONFLICT_PATTERNS = (
    "shooting_star",
    "bearish_pin_bar",
    "bearish_engulfing",
    "bearish_outside_bar",
    "evening_star",
    "bearish_three_bar_reversal",
    "fake_breakout_reclaim",
    "breakdown_retest_reject",
)
BULLISH_CONFLICT_PATTERNS = (
    "hammer",
    "bullish_pin_bar",
    "bullish_engulfing",
    "bullish_outside_bar",
    "morning_star",
    "bullish_three_bar_reversal",
    "fake_breakdown_reclaim",
    "breakout_retest_hold",
)


@dataclass(frozen=True)
class ScenarioPatternCalibrationSettings:
    enabled: bool = True
    historical_enabled: bool = True
    symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT")
    timeframe: str = "5m"
    max_rows_per_asset: int = 5000
    min_warmup_rows: int = 450
    eval_stride: int = 1
    horizons: tuple[int, ...] = (3, 6, 12)
    stop_loss_pct: float = 0.0035
    tp1_pct: float = 0.0035
    tp2_pct: float = 0.0070
    score_thresholds: tuple[float, ...] = (50.0, 55.0, 60.0, 65.0, 70.0)
    min_bucket_candidates: int = 100
    min_profile_candidates: int = 50
    min_bucket_expectancy_r: float = 0.05
    min_profile_expectancy_r: float = 0.10
    min_profile_win_rate_pct: float = 50.0
    max_profile_loss_rate_pct: float = 35.0
    support_range_pos_max: float = 0.40
    resistance_range_pos_min: float = 0.60
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    candidate_profile_name: str = "BTC_BUY_REJECTION_PATTERN_CONFIRMED"

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "ScenarioPatternCalibrationSettings":
        base = PatternConditionedShadowSettings.from_config(cfg)
        return cls(
            enabled=bool(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_HISTORICAL_ENABLED", getattr(cfg, "PATTERN_CONDITIONED_HISTORICAL_ENABLED", True))),
            symbols=tuple(_parse_symbols(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_SYMBOLS", getattr(cfg, "PATTERN_CONDITIONED_SYMBOLS", ",".join(base.symbols)))) or list(base.symbols)),
            timeframe=str(getattr(cfg, "PAPER_DEFAULT_TIMEFRAME", base.timeframe) or base.timeframe),
            max_rows_per_asset=_safe_int(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_MAX_ROWS_PER_ASSET", base.max_rows_per_asset), base.max_rows_per_asset),
            min_warmup_rows=_safe_int(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_MIN_WARMUP_ROWS", base.min_warmup_rows), base.min_warmup_rows),
            eval_stride=max(1, _safe_int(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_EVAL_STRIDE", base.eval_stride), base.eval_stride)),
            horizons=_parse_int_tuple(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_HORIZONS", ",".join(str(x) for x in base.horizons)), base.horizons),
            stop_loss_pct=_safe_float(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_STOP_LOSS_PCT", base.stop_loss_pct), base.stop_loss_pct),
            tp1_pct=_safe_float(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_TP1_PCT", base.tp1_pct), base.tp1_pct),
            tp2_pct=_safe_float(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_TP2_PCT", base.tp2_pct), base.tp2_pct),
            score_thresholds=_parse_float_tuple(getattr(cfg, "SCENARIO_PATTERN_CALIBRATION_SCORE_THRESHOLDS", "50,55,60,65,70"), (50.0, 55.0, 60.0, 65.0, 70.0)),
            min_bucket_candidates=_safe_int(getattr(cfg, "SCENARIO_PATTERN_MIN_BUCKET_CANDIDATES", 100), 100),
            min_profile_candidates=_safe_int(getattr(cfg, "SCENARIO_PATTERN_MIN_PROFILE_CANDIDATES", 50), 50),
            min_bucket_expectancy_r=_safe_float(getattr(cfg, "SCENARIO_PATTERN_MIN_BUCKET_EXPECTANCY_R", 0.05), 0.05),
            min_profile_expectancy_r=_safe_float(getattr(cfg, "SCENARIO_PATTERN_MIN_PROFILE_EXPECTANCY_R", 0.10), 0.10),
            min_profile_win_rate_pct=_safe_float(getattr(cfg, "SCENARIO_PATTERN_MIN_PROFILE_WIN_RATE_PCT", 50.0), 50.0),
            max_profile_loss_rate_pct=_safe_float(getattr(cfg, "SCENARIO_PATTERN_MAX_PROFILE_LOSS_RATE_PCT", 35.0), 35.0),
            support_range_pos_max=_safe_float(getattr(cfg, "SCENARIO_PATTERN_SUPPORT_RANGE_POS_MAX", 0.40), 0.40),
            resistance_range_pos_min=_safe_float(getattr(cfg, "SCENARIO_PATTERN_RESISTANCE_RANGE_POS_MIN", 0.60), 0.60),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            candidate_profile_name=str(getattr(cfg, "SCENARIO_PATTERN_CANDIDATE_PROFILE", "BTC_BUY_REJECTION_PATTERN_CONFIRMED") or "BTC_BUY_REJECTION_PATTERN_CONFIRMED"),
        )

    def shadow_settings(self) -> PatternConditionedShadowSettings:
        return PatternConditionedShadowSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            max_rows_per_asset=self.max_rows_per_asset,
            min_warmup_rows=self.min_warmup_rows,
            eval_stride=self.eval_stride,
            horizons=self.horizons,
            stop_loss_pct=self.stop_loss_pct,
            tp1_pct=self.tp1_pct,
            tp2_pct=self.tp2_pct,
            symbols=self.symbols,
            timeframe=self.timeframe,
            min_operational_candidates=self.min_profile_candidates,
            min_expectancy_r=self.min_profile_expectancy_r,
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_symbols(value: Any) -> list[str]:
    return [x.strip().upper() for x in str(value or "").replace(";", ",").split(",") if x.strip()]


def _parse_int_tuple(value: Any, default: tuple[int, ...]) -> tuple[int, ...]:
    try:
        items = [int(str(x).strip()) for x in str(value).replace(";", ",").split(",") if str(x).strip()]
        out = tuple(x for x in items if x > 0)
        return out or default
    except Exception:
        return default


def _parse_float_tuple(value: Any, default: tuple[float, ...]) -> tuple[float, ...]:
    try:
        items = [_safe_float(str(x).strip(), float("nan")) for x in str(value).replace(";", ",").split(",") if str(x).strip()]
        out = tuple(sorted({float(x) for x in items if math.isfinite(float(x))}))
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


def _candidate_side(pattern_bias: str, scenario_bias: str, scenario_integration: str) -> str:
    p = str(pattern_bias or "HOLD").upper()
    s = str(scenario_bias or "HOLD").upper()
    integ = str(scenario_integration or "").upper()
    if p not in {"BUY", "SELL"}:
        return "HOLD"
    if s in {"BUY", "SELL"} and s != p:
        return "HOLD"
    if "CONFIRMED_BY_CANDLE" in integ:
        return p
    if s == p:
        return p
    return "HOLD"


def _bucket_key(side: str, scenario: str) -> str:
    return f"{str(side or 'HOLD').upper()}_{str(scenario or 'UNKNOWN').upper()}"


def _pattern_conflict(side: str, bullish_patterns: Iterable[str], bearish_patterns: Iterable[str]) -> bool:
    side = str(side or "").upper()
    bull = {str(x) for x in bullish_patterns or []}
    bear = {str(x) for x in bearish_patterns or []}
    if side == "BUY" and bear:
        return True
    if side == "SELL" and bull:
        return True
    return False


def _conflicting_pattern_names(side: str, patterns: Iterable[str]) -> list[str]:
    side = str(side or "").upper()
    names = [str(x) for x in patterns or []]
    if side == "BUY":
        return [p for p in names if p in BEARISH_CONFLICT_PATTERNS]
    if side == "SELL":
        return [p for p in names if p in BULLISH_CONFLICT_PATTERNS]
    return []


def _range_filter_ok(row: dict[str, Any], settings: ScenarioPatternCalibrationSettings) -> bool:
    side = str(row.get("side") or "").upper()
    scenario = str(row.get("scenario") or "").upper()
    range_pos = _safe_float(row.get("range_pos_400"), 0.5)
    if side == "BUY" and ("SUPPORT" in scenario or "REJECTION" in scenario):
        return range_pos <= settings.support_range_pos_max
    if side == "SELL" and ("RESISTANCE" in scenario or "REJECTION" in scenario):
        return range_pos >= settings.resistance_range_pos_min
    return True


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


def _summarize_rows(rows: list[dict[str, Any]], settings: ScenarioPatternCalibrationSettings | None = None) -> dict[str, Any]:
    if not rows:
        return {
            "candidates": 0,
            "expectancy_r": 0.0,
            "win_rate_pct": 0.0,
            "loss_rate_pct": 0.0,
            "tp1_rate_pct": 0.0,
            "tp2_rate_pct": 0.0,
            "time_exit_rate_pct": 0.0,
            "outcomes": _outcome_counts([]),
            "pattern_score_distribution": _metrics([]),
            "r_distribution": _metrics([]),
            "range_pos_400_distribution": _metrics([]),
            "patterns": {},
        }
    rs = [_safe_float(r.get("r"), 0.0) for r in rows]
    outcomes = _outcome_counts(rows)
    wins = sum(1 for r in rows if str(r.get("outcome")) in POSITIVE_OUTCOMES or _safe_float(r.get("r"), 0.0) > 0)
    losses = sum(1 for r in rows if str(r.get("outcome")) in NEGATIVE_OUTCOMES or _safe_float(r.get("r"), 0.0) < 0)
    patterns: Counter[str] = Counter()
    for row in rows:
        for p in row.get("patterns") or []:
            patterns[str(p)] += 1
    payload = {
        "candidates": len(rows),
        "expectancy_r": round(float(mean(rs)), 6) if rs else 0.0,
        "win_rate_pct": round(_pct(wins, len(rows)), 4),
        "loss_rate_pct": round(_pct(losses, len(rows)), 4),
        "tp1_rate_pct": round(_pct(outcomes.get("TP1_ONLY", 0), len(rows)), 4),
        "tp2_rate_pct": round(_pct(outcomes.get("TP2", 0), len(rows)), 4),
        "sl_rate_pct": round(_pct(outcomes.get("SL", 0), len(rows)), 4),
        "time_exit_rate_pct": round(_pct(outcomes.get("TIME_EXIT", 0), len(rows)), 4),
        "outcomes": outcomes,
        "pattern_score_distribution": _metrics([_safe_float(r.get("pattern_score"), 0.0) for r in rows]),
        "r_distribution": _metrics(rs),
        "range_pos_400_distribution": _metrics([_safe_float(r.get("range_pos_400"), 0.5) for r in rows]),
        "patterns": dict(patterns.most_common(20)),
    }
    if settings is not None:
        clean = [r for r in rows if not r.get("has_conflicting_patterns") and _range_filter_ok(r, settings)]
        payload["clean_filter"] = {
            "candidates": len(clean),
            "candidate_rate_pct": round(_pct(len(clean), len(rows)), 4),
            "expectancy_r": round(float(mean([_safe_float(r.get("r"), 0.0) for r in clean])), 6) if clean else 0.0,
            "win_rate_pct": round(_pct(sum(1 for r in clean if _safe_float(r.get("r"), 0.0) > 0), len(clean)), 4) if clean else 0.0,
            "loss_rate_pct": round(_pct(sum(1 for r in clean if _safe_float(r.get("r"), 0.0) < 0), len(clean)), 4) if clean else 0.0,
            "filters": {
                "exclude_conflicting_patterns": True,
                "support_range_pos_max": settings.support_range_pos_max,
                "resistance_range_pos_min": settings.resistance_range_pos_min,
            },
        }
    return payload


def _collect_historical_rows(data_dir: Path, settings: ScenarioPatternCalibrationSettings) -> dict[str, Any]:
    if not settings.historical_enabled:
        return {"status": "DISABLED", "evaluation_rows": 0, "candidate_rows": [], "warnings": ["historical disabled"], "by_asset": {}}

    shadow_settings = settings.shadow_settings()
    warnings: list[str] = []
    candidate_rows: list[dict[str, Any]] = []
    evaluation_counts: Counter[str] = Counter()
    by_asset: dict[str, Any] = {}
    filter_counts: Counter[str] = Counter()

    for symbol in settings.symbols:
        cache_path = _cache_path_for_symbol(data_dir, symbol, settings.timeframe)
        if cache_path is None:
            warnings.append(f"missing_cache:{symbol}")
            by_asset[symbol] = {"status": "MISSING_CACHE", "candidates": 0, "evaluation_rows": 0}
            continue
        try:
            raw = _read_cache(cache_path)
            df = _normalize_ohlcv(raw, symbol)
            if len(df) > settings.max_rows_per_asset:
                df = df.tail(settings.max_rows_per_asset).reset_index(drop=True)
            df = _add_minimal_structure_features(df)
        except Exception as exc:
            warnings.append(f"cache_prepare_failed:{symbol}:{exc.__class__.__name__}:{str(exc).splitlines()[0][:220]}")
            by_asset[symbol] = {"status": "READ_ERROR", "error": str(exc), "candidates": 0, "evaluation_rows": 0, "cache_path": str(cache_path)}
            continue

        asset_rows: list[dict[str, Any]] = []
        start = max(3, min(settings.min_warmup_rows, max(3, len(df) - max(settings.horizons) - 1)))
        end = max(start, len(df) - max(settings.horizons))
        for idx in range(start, end, settings.eval_stride):
            evaluation_counts[symbol] += 1
            window = df.iloc[: idx + 1]
            try:
                scenario = evaluate_crypto_intraday_scenario(window, symbol=symbol)
                pattern = detect_candlestick_patterns(window, symbol=symbol, scenario=scenario.to_dict())
            except Exception as exc:
                filter_counts["eval_failed"] += 1
                if len(warnings) < 30:
                    warnings.append(f"eval_failed:{symbol}:{idx}:{exc.__class__.__name__}:{str(exc).splitlines()[0][:220]}")
                continue

            p_bias = str(pattern.pattern_bias or "HOLD").upper()
            s_bias = str(scenario.directional_bias or "HOLD").upper()
            side = _candidate_side(p_bias, s_bias, pattern.scenario_integration)
            if side not in {"BUY", "SELL"}:
                if p_bias in {"BUY", "SELL"} and s_bias in {"BUY", "SELL"} and p_bias != s_bias:
                    filter_counts["scenario_pattern_conflict"] += 1
                elif p_bias == "HOLD":
                    filter_counts["pattern_hold_or_neutral"] += 1
                elif s_bias == "HOLD":
                    filter_counts["scenario_wait_or_hold"] += 1
                else:
                    filter_counts["not_aligned"] += 1
                continue

            row = df.iloc[idx]
            forward = _evaluate_forward(df, idx, side, shadow_settings)
            all_patterns = list(pattern.patterns)
            conflicting_names = _conflicting_pattern_names(side, all_patterns)
            has_conflict = bool(conflicting_names) or _pattern_conflict(side, pattern.bullish_patterns, pattern.bearish_patterns)
            candidate = {
                "symbol": symbol,
                "idx": int(idx),
                "datetime": str(row.get("datetime", idx)),
                "side": side,
                "scenario": scenario.scenario,
                "scenario_bias": scenario.directional_bias,
                "scenario_score": float(scenario.confidence_score),
                "pattern_bias": pattern.pattern_bias,
                "pattern_score": float(pattern.pattern_score),
                "patterns": all_patterns,
                "bullish_patterns": list(pattern.bullish_patterns),
                "bearish_patterns": list(pattern.bearish_patterns),
                "neutral_patterns": list(pattern.neutral_patterns),
                "confirmations": list(pattern.confirmations),
                "missing_confirmations": list(pattern.missing_confirmations),
                "scenario_integration": pattern.scenario_integration,
                "alignment": "PATTERN_SCENARIO_ALIGNED",
                "has_conflicting_patterns": bool(has_conflict),
                "conflicting_patterns": conflicting_names,
                "range_pos_400": _safe_float(row.get("range_pos_400"), 0.5),
                "near_support": bool(row.get("near_support", False)),
                "near_resistance": bool(row.get("near_resistance", False)),
                "bucket": _bucket_key(side, scenario.scenario),
                "asset_bucket": f"{symbol}:{_bucket_key(side, scenario.scenario)}",
                "forward": forward,
                "r": _safe_float(forward.get("r"), 0.0),
                "outcome": forward.get("outcome"),
            }
            candidate["range_filter_ok"] = _range_filter_ok(candidate, settings)
            candidate_rows.append(candidate)
            asset_rows.append(candidate)

        by_asset[symbol] = {
            "status": "PASS",
            "cache_path": str(cache_path),
            "rows_loaded": int(len(df)),
            "evaluation_rows": int(evaluation_counts[symbol]),
            **_summarize_rows(asset_rows, settings),
        }

    return {
        "status": "PASS" if candidate_rows else "WARN",
        "evaluation_rows": int(sum(evaluation_counts.values())),
        "evaluation_rows_by_asset": dict(evaluation_counts),
        "candidate_rows": candidate_rows,
        "filter_counts": dict(filter_counts),
        "by_asset": by_asset,
        "warnings": warnings[:60],
    }


def _rank_buckets(rows: list[dict[str, Any]], settings: ScenarioPatternCalibrationSettings) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("symbol") or "UNKNOWN"), str(row.get("bucket") or "UNKNOWN"))].append(row)

    ranked: list[dict[str, Any]] = []
    for (symbol, bucket), bucket_rows in grouped.items():
        summary = _summarize_rows(bucket_rows, settings)
        candidates = int(summary.get("candidates", 0))
        expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
        sample_ok = candidates >= settings.min_bucket_candidates
        edge_ok = expectancy >= settings.min_bucket_expectancy_r
        negative = expectancy < 0 or bucket in {"SELL_SELL_BREAKDOWN_CANDIDATE"}
        score = expectancy * 100.0 + min(candidates, 500) / 50.0 + _safe_float(summary.get("win_rate_pct"), 0.0) / 20.0
        ranked.append({
            "rank_score": round(score, 6),
            "symbol": symbol,
            "bucket": bucket,
            "sample_ok": bool(sample_ok),
            "edge_ok": bool(edge_ok),
            "negative_or_excluded": bool(negative),
            "decision_hint": "KEEP_AS_CANDIDATE" if sample_ok and edge_ok and not negative else "EXCLUDE_OR_KEEP_DIAGNOSTIC" if negative else "WATCHLIST",
            **summary,
        })
    ranked.sort(key=lambda x: (_safe_float(x.get("expectancy_r"), 0.0), _safe_int(x.get("candidates"), 0)), reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked


def _threshold_grid(rows: list[dict[str, Any]], settings: ScenarioPatternCalibrationSettings) -> list[dict[str, Any]]:
    grid: list[dict[str, Any]] = []
    for threshold in settings.score_thresholds:
        threshold_rows = [r for r in rows if _safe_float(r.get("pattern_score"), 0.0) >= threshold]
        clean_rows = [r for r in threshold_rows if not r.get("has_conflicting_patterns") and bool(r.get("range_filter_ok", True))]
        by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in clean_rows:
            by_bucket[str(row.get("asset_bucket") or f"{row.get('symbol')}:{row.get('bucket')}")].append(row)
        best_bucket = None
        if by_bucket:
            bucket_summaries = []
            for asset_bucket, bucket_rows in by_bucket.items():
                s = _summarize_rows(bucket_rows, settings)
                bucket_summaries.append({"asset_bucket": asset_bucket, **s})
            bucket_summaries.sort(key=lambda x: (_safe_float(x.get("expectancy_r"), 0.0), _safe_int(x.get("candidates"), 0)), reverse=True)
            best_bucket = bucket_summaries[0]
        grid.append({
            "pattern_score_min": float(threshold),
            "pre_clean_candidates": len(threshold_rows),
            "clean_candidates": len(clean_rows),
            "summary": _summarize_rows(clean_rows, settings),
            "best_clean_bucket": best_bucket or {},
        })
    return grid


def _profile_threshold_grid(rows: list[dict[str, Any]], settings: ScenarioPatternCalibrationSettings) -> list[dict[str, Any]]:
    focus_rows = [
        r for r in rows
        if str(r.get("symbol") or "").upper() == settings.focus_symbol
        and str(r.get("bucket") or "").upper() == settings.focus_bucket
    ]
    out: list[dict[str, Any]] = []
    for threshold in settings.score_thresholds:
        filtered = [
            r for r in focus_rows
            if _safe_float(r.get("pattern_score"), 0.0) >= threshold
            and not r.get("has_conflicting_patterns")
            and bool(r.get("range_filter_ok", True))
        ]
        summary = _summarize_rows(filtered, settings)
        passed = (
            int(summary.get("candidates", 0)) >= settings.min_profile_candidates
            and _safe_float(summary.get("expectancy_r", 0.0)) >= settings.min_profile_expectancy_r
            and _safe_float(summary.get("win_rate_pct", 0.0)) >= settings.min_profile_win_rate_pct
            and _safe_float(summary.get("loss_rate_pct", 100.0)) <= settings.max_profile_loss_rate_pct
        )
        out.append({
            "profile": settings.candidate_profile_name,
            "asset": settings.focus_symbol,
            "bucket": settings.focus_bucket,
            "pattern_score_min": float(threshold),
            "passes_candidate_gate": bool(passed),
            **summary,
        })
    return out


def _runtime_calibration(data_dir: Path, settings: ScenarioPatternCalibrationSettings) -> dict[str, Any]:
    path = data_dir / "paper_events.jsonl"
    if not path.exists():
        return {"status": "NO_EVENTS", "rows": 0, "aligned_rows": 0}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if str(event.get("event_type") or "").upper() != "CANDLESTICK_PATTERN_DIAGNOSTIC":
            continue
        p_bias = str(event.get("pattern_bias") or "HOLD").upper()
        s_bias = str(event.get("scenario_directional_bias") or "HOLD").upper()
        side = _candidate_side(p_bias, s_bias, str(event.get("scenario_integration") or ""))
        scenario = str(event.get("scenario") or "UNKNOWN").upper()
        bucket = _bucket_key(side, scenario) if side in {"BUY", "SELL"} else "NON_ALIGNED_OR_WAIT"
        rows.append({
            "symbol": str(event.get("symbol") or "UNKNOWN"),
            "side": side,
            "scenario": scenario,
            "bucket": bucket,
            "pattern_score": _safe_float(event.get("pattern_score"), 0.0),
            "patterns": event.get("patterns") or [],
            "pattern_alignment": str(event.get("pattern_alignment") or ""),
            "scenario_integration": str(event.get("scenario_integration") or ""),
        })
    aligned = [r for r in rows if r.get("side") in {"BUY", "SELL"}]
    focus = [r for r in aligned if str(r.get("symbol") or "").upper() == settings.focus_symbol and str(r.get("bucket") or "").upper() == settings.focus_bucket]
    return {
        "status": "PASS" if rows else "NO_PATTERN_ROWS",
        "rows": len(rows),
        "aligned_rows": len(aligned),
        "focus_profile_runtime_rows": len(focus),
        "buckets": dict(Counter(str(r.get("bucket") or "UNKNOWN") for r in rows)),
        "by_asset": dict(Counter(str(r.get("symbol") or "UNKNOWN") for r in rows)),
        "pattern_score_distribution": _metrics([_safe_float(r.get("pattern_score"), 0.0) for r in rows]),
        "recent": rows[-10:],
    }


def _pick_recommended_threshold(profile_grid: list[dict[str, Any]], settings: ScenarioPatternCalibrationSettings) -> dict[str, Any] | None:
    passing = [row for row in profile_grid if row.get("passes_candidate_gate")]
    if not passing:
        return None
    # Prefer the strictest threshold that still has enough candidates; tie by expectancy.
    passing.sort(key=lambda x: (_safe_float(x.get("pattern_score_min"), 0.0), _safe_float(x.get("expectancy_r"), 0.0)), reverse=True)
    return passing[0]


def _decision(
    *,
    rows: list[dict[str, Any]],
    ranked_buckets: list[dict[str, Any]],
    profile_grid: list[dict[str, Any]],
    settings: ScenarioPatternCalibrationSettings,
) -> dict[str, Any]:
    if not settings.enabled:
        return {"status": "KEEP_DIAGNOSTIC", "reason": "calibration disabled", "operational_unlock_allowed": False}
    if not rows:
        return {"status": "DO_NOT_USE_PATTERNS", "reason": "no aligned historical candidates", "operational_unlock_allowed": False}

    negative_material = [
        b for b in ranked_buckets
        if _safe_int(b.get("candidates"), 0) >= max(20, settings.min_bucket_candidates // 4)
        and _safe_float(b.get("expectancy_r"), 0.0) < 0.0
    ]
    recommended = _pick_recommended_threshold(profile_grid, settings)
    focus_baseline = next((b for b in ranked_buckets if str(b.get("symbol") or "").upper() == settings.focus_symbol and str(b.get("bucket") or "").upper() == settings.focus_bucket), None)

    if recommended:
        return {
            "status": "CALIBRATED_PROFILE_CANDIDATE",
            "reason": "focus bucket passed sample/expectancy/win/loss gates after score, conflict and range filters",
            "candidate_profile": _candidate_profile_payload(recommended, settings),
            "operational_unlock_allowed": False,
            "next_patch": "29.5.0e Liquidity + supply/demand + structure break engine, then 29.5.0f shadow review before paper unlock refinement",
            "negative_buckets_to_exclude": [_bucket_exclusion_payload(b) for b in negative_material[:10]],
            "focus_bucket_baseline": focus_baseline or {},
        }

    if focus_baseline and _safe_float(focus_baseline.get("expectancy_r"), 0.0) > 0:
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "focus bucket has positive baseline edge but did not pass calibrated profile gates under stricter filters",
            "candidate_profile": _non_operational_profile(settings),
            "operational_unlock_allowed": False,
            "next_patch": "29.5.0e/29.5.0f; do not unlock until structure-confirmed review improves the filtered profile",
            "negative_buckets_to_exclude": [_bucket_exclusion_payload(b) for b in negative_material[:10]],
            "focus_bucket_baseline": focus_baseline,
        }

    best = ranked_buckets[0] if ranked_buckets else {}
    if _safe_float(best.get("expectancy_r"), 0.0) <= 0:
        return {
            "status": "DO_NOT_USE_PATTERNS",
            "reason": "no positive calibrated bucket after replay",
            "operational_unlock_allowed": False,
            "negative_buckets_to_exclude": [_bucket_exclusion_payload(b) for b in negative_material[:10]],
        }
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "positive buckets exist, but BTC focus profile is not calibrated enough for unlock refinement",
        "candidate_profile": _non_operational_profile(settings),
        "operational_unlock_allowed": False,
        "next_patch": "29.5.0e/29.5.0f; maintain diagnostic-only mode",
        "negative_buckets_to_exclude": [_bucket_exclusion_payload(b) for b in negative_material[:10]],
        "best_bucket": best,
    }


def _candidate_profile_payload(recommended: dict[str, Any], settings: ScenarioPatternCalibrationSettings) -> dict[str, Any]:
    return {
        "name": settings.candidate_profile_name,
        "status": "NON_OPERATIONAL_CANDIDATE",
        "asset": settings.focus_symbol,
        "scenario": "BUY_REJECTION_CANDIDATE",
        "side": "BUY",
        "pattern_bias": "BUY",
        "pattern_alignment": "PATTERN_SCENARIO_ALIGNED",
        "pattern_score_min": _safe_float(recommended.get("pattern_score_min"), 0.0),
        "exclude_conflicting_bearish_patterns": list(BEARISH_CONFLICT_PATTERNS),
        "range_pos_400_max": settings.support_range_pos_max,
        "requires_structure_confirmation_next": True,
        "no_orders": True,
        "no_live": True,
        "no_testnet": True,
        "evidence": {
            "candidates": _safe_int(recommended.get("candidates"), 0),
            "expectancy_r": _safe_float(recommended.get("expectancy_r"), 0.0),
            "win_rate_pct": _safe_float(recommended.get("win_rate_pct"), 0.0),
            "loss_rate_pct": _safe_float(recommended.get("loss_rate_pct"), 0.0),
            "outcomes": recommended.get("outcomes") or {},
        },
    }


def _non_operational_profile(settings: ScenarioPatternCalibrationSettings) -> dict[str, Any]:
    return {
        "name": settings.candidate_profile_name,
        "status": "NOT_APPROVED_KEEP_DIAGNOSTIC",
        "asset": settings.focus_symbol,
        "scenario": "BUY_REJECTION_CANDIDATE",
        "side": "BUY",
        "pattern_score_min_candidates_to_review": list(settings.score_thresholds),
        "no_orders": True,
        "no_live": True,
        "no_testnet": True,
    }


def _bucket_exclusion_payload(bucket: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": bucket.get("symbol"),
        "bucket": bucket.get("bucket"),
        "candidates": bucket.get("candidates"),
        "expectancy_r": bucket.get("expectancy_r"),
        "win_rate_pct": bucket.get("win_rate_pct"),
        "loss_rate_pct": bucket.get("loss_rate_pct"),
        "reason": "negative_expectancy_or_breakdown_bucket",
    }



def _fallback_from_pattern_conditioned_report(data_dir: Path, settings: ScenarioPatternCalibrationSettings) -> dict[str, Any]:
    """Build a coarse calibration view from the 29.5.0c report.

    This is used only when detailed parquet replay is unavailable.  It cannot
    evaluate pattern_score thresholds or conflict/range filters, so it never
    approves a calibrated profile candidate on its own.
    """
    path = data_dir / "pattern_conditioned_shadow_report.json"
    if not path.exists():
        return {"available": False, "reason": "missing_pattern_conditioned_shadow_report"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"available": False, "reason": f"read_error:{exc}"}
    historical = payload.get("historical_shadow", {}) if isinstance(payload.get("historical_shadow"), dict) else {}
    by_asset_raw = historical.get("by_asset", {}) if isinstance(historical.get("by_asset"), dict) else {}
    ranked: list[dict[str, Any]] = []
    by_asset: dict[str, Any] = {}
    for symbol, asset_payload in sorted(by_asset_raw.items()):
        if not isinstance(asset_payload, dict):
            continue
        asset_copy = dict(asset_payload)
        by_asset[str(symbol)] = asset_copy
        buckets = asset_payload.get("buckets", {}) if isinstance(asset_payload.get("buckets"), dict) else {}
        for bucket, summary in buckets.items():
            if not isinstance(summary, dict):
                continue
            outcomes = summary.get("outcomes", {}) if isinstance(summary.get("outcomes"), dict) else {}
            candidates = _safe_int(summary.get("candidates"), 0)
            losses = _safe_int(outcomes.get("SL"), 0)
            row = {
                "symbol": str(symbol),
                "bucket": str(bucket),
                "candidates": candidates,
                "expectancy_r": _safe_float(summary.get("expectancy_r"), 0.0),
                "win_rate_pct": _safe_float(summary.get("win_rate_pct"), 0.0),
                "loss_rate_pct": round(_pct(losses, candidates), 4),
                "outcomes": {
                    "TP1_ONLY": _safe_int(outcomes.get("TP1_ONLY"), 0),
                    "TP2": _safe_int(outcomes.get("TP2"), 0),
                    "SL": losses,
                    "TIME_EXIT": _safe_int(outcomes.get("TIME_EXIT"), 0),
                },
                "sample_ok": candidates >= settings.min_bucket_candidates,
                "edge_ok": _safe_float(summary.get("expectancy_r"), 0.0) >= settings.min_bucket_expectancy_r,
                "negative_or_excluded": _safe_float(summary.get("expectancy_r"), 0.0) < 0.0 or str(bucket) == "SELL_SELL_BREAKDOWN_CANDIDATE",
                "decision_hint": "FALLBACK_SUMMARY_ONLY",
                "fallback_summary_only": True,
            }
            ranked.append(row)
    ranked.sort(key=lambda x: (_safe_float(x.get("expectancy_r"), 0.0), _safe_int(x.get("candidates"), 0)), reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    summary = historical.get("summary", {}) if isinstance(historical.get("summary"), dict) else {}
    return {
        "available": bool(ranked),
        "source": str(path),
        "status": historical.get("status", payload.get("status", "NA")),
        "historical_candidates": (payload.get("counts") or {}).get("historical_candidates", summary.get("candidates", 0)) if isinstance(payload.get("counts"), dict) else summary.get("candidates", 0),
        "historical_expectancy_r": summary.get("expectancy_r", 0.0),
        "bucket_ranking": ranked,
        "by_asset": by_asset,
        "reason": "detailed_replay_unavailable_used_29_5_0c_summary",
    }


def _fallback_decision(fallback: dict[str, Any], settings: ScenarioPatternCalibrationSettings) -> dict[str, Any]:
    ranked = fallback.get("bucket_ranking") if isinstance(fallback.get("bucket_ranking"), list) else []
    focus = next((b for b in ranked if str(b.get("symbol") or "").upper() == settings.focus_symbol and str(b.get("bucket") or "").upper() == settings.focus_bucket), None)
    negative = [b for b in ranked if b.get("negative_or_excluded")]
    if focus and _safe_float(focus.get("expectancy_r"), 0.0) > 0:
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "fallback used 29.5.0c bucket summaries only; pattern_score/conflict/range calibration requires parquet replay",
            "candidate_profile": _non_operational_profile(settings),
            "operational_unlock_allowed": False,
            "next_patch": "rerun 29.5.0d in the project environment with parquet support; then continue to 29.5.0e/29.5.0f",
            "negative_buckets_to_exclude": [_bucket_exclusion_payload(b) for b in negative[:10]],
            "focus_bucket_baseline": focus,
            "fallback_summary_only": True,
        }
    return {
        "status": "DO_NOT_USE_PATTERNS" if not ranked else "KEEP_DIAGNOSTIC",
        "reason": "fallback summary did not provide a positive BTC focus bucket" if ranked else "no detailed replay and no fallback bucket summary available",
        "operational_unlock_allowed": False,
        "negative_buckets_to_exclude": [_bucket_exclusion_payload(b) for b in negative[:10]],
        "fallback_summary_only": True,
    }

def _settings_payload(settings: ScenarioPatternCalibrationSettings) -> dict[str, Any]:
    return {
        "symbols": list(settings.symbols),
        "timeframe": settings.timeframe,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "min_warmup_rows": settings.min_warmup_rows,
        "eval_stride": settings.eval_stride,
        "horizons": list(settings.horizons),
        "stop_loss_pct": settings.stop_loss_pct,
        "tp1_pct": settings.tp1_pct,
        "tp2_pct": settings.tp2_pct,
        "score_thresholds": list(settings.score_thresholds),
        "min_bucket_candidates": settings.min_bucket_candidates,
        "min_profile_candidates": settings.min_profile_candidates,
        "min_bucket_expectancy_r": settings.min_bucket_expectancy_r,
        "min_profile_expectancy_r": settings.min_profile_expectancy_r,
        "min_profile_win_rate_pct": settings.min_profile_win_rate_pct,
        "max_profile_loss_rate_pct": settings.max_profile_loss_rate_pct,
        "support_range_pos_max": settings.support_range_pos_max,
        "resistance_range_pos_min": settings.resistance_range_pos_min,
        "focus_symbol": settings.focus_symbol,
        "focus_bucket": settings.focus_bucket,
        "candidate_profile_name": settings.candidate_profile_name,
    }


def build_scenario_pattern_calibration_report(data_dir: str | Path, settings: ScenarioPatternCalibrationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or ScenarioPatternCalibrationSettings.from_config()
    historical = _collect_historical_rows(base, settings)
    candidate_rows = list(historical.get("candidate_rows") or [])
    fallback = _fallback_from_pattern_conditioned_report(base, settings) if not candidate_rows else {"available": False}
    ranked = _rank_buckets(candidate_rows, settings)
    threshold_grid = _threshold_grid(candidate_rows, settings)
    profile_grid = _profile_threshold_grid(candidate_rows, settings)
    if not candidate_rows and fallback.get("available"):
        ranked = list(fallback.get("bucket_ranking") or [])
    runtime = _runtime_calibration(base, settings)
    if candidate_rows:
        decision = _decision(rows=candidate_rows, ranked_buckets=ranked, profile_grid=profile_grid, settings=settings)
    elif fallback.get("available"):
        decision = _fallback_decision(fallback, settings)
    else:
        decision = _decision(rows=candidate_rows, ranked_buckets=ranked, profile_grid=profile_grid, settings=settings)

    status = "PASS" if decision.get("status") == "CALIBRATED_PROFILE_CANDIDATE" else "WARN"
    if decision.get("status") == "DO_NOT_USE_PATTERNS":
        status = "FAIL"
    if not settings.enabled:
        status = "DISABLED"

    by_asset = historical.get("by_asset") if isinstance(historical.get("by_asset"), dict) else {}
    if not by_asset and fallback.get("available"):
        by_asset = fallback.get("by_asset") if isinstance(fallback.get("by_asset"), dict) else {}
    payload = {
        "report_type": "scenario_pattern_calibration",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "safety": {
            "diagnostic_only": True,
            "opens_orders": False,
            "changes_thresholds": False,
            "changes_paper_unlock_profile": False,
            "enables_live_or_testnet": False,
            "operational_unlock_allowed": False,
        },
        "counts": {
            "historical_evaluation_rows": historical.get("evaluation_rows", 0),
            "historical_candidates": len(candidate_rows) if candidate_rows else _safe_int(fallback.get("historical_candidates"), 0),
            "runtime_pattern_rows": runtime.get("rows", 0),
            "runtime_aligned_rows": runtime.get("aligned_rows", 0),
            "focus_profile_runtime_rows": runtime.get("focus_profile_runtime_rows", 0),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "settings": _settings_payload(settings),
        "historical_summary": _summarize_rows(candidate_rows, settings) if candidate_rows else {"fallback_summary_only": bool(fallback.get("available")), "historical_candidates": fallback.get("historical_candidates", 0), "historical_expectancy_r": fallback.get("historical_expectancy_r", 0.0)},
        "bucket_ranking": ranked,
        "bucket_ranking_top": ranked[:20],
        "by_asset": by_asset,
        "pattern_score_threshold_grid": threshold_grid,
        "focus_profile_threshold_grid": profile_grid,
        "filters": {
            "alignment_required": "pattern_bias must be BUY/SELL and not contradict scenario directional bias",
            "pattern_score_min_grid": list(settings.score_thresholds),
            "exclude_conflicting_patterns": True,
            "buy_conflicting_bearish_patterns": list(BEARISH_CONFLICT_PATTERNS),
            "sell_conflicting_bullish_patterns": list(BULLISH_CONFLICT_PATTERNS),
            "support_range_pos_400_max": settings.support_range_pos_max,
            "resistance_range_pos_400_min": settings.resistance_range_pos_min,
            "hard_excluded_bucket_templates": list(DEFAULT_NEGATIVE_BUCKETS),
        },
        "runtime_review": runtime,
        "filter_counts": historical.get("filter_counts", {}),
        "fallback": fallback,
        "recent_candidates": [
            {
                "symbol": r.get("symbol"),
                "datetime": r.get("datetime"),
                "side": r.get("side"),
                "scenario": r.get("scenario"),
                "bucket": r.get("bucket"),
                "patterns": r.get("patterns"),
                "pattern_score": r.get("pattern_score"),
                "range_pos_400": r.get("range_pos_400"),
                "has_conflicting_patterns": r.get("has_conflicting_patterns"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
            }
            for r in candidate_rows[-20:]
        ],
        "warnings": historical.get("warnings", []),
        "files": {"report": str(base / REPORT_NAME), "events": str(base / "paper_events.jsonl")},
        "diagnostic_only": True,
        "opens_orders": False,
        "changes_thresholds": False,
        "enables_live_or_testnet": False,
    }
    return payload


def write_scenario_pattern_calibration_report(data_dir: str | Path, settings: ScenarioPatternCalibrationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_scenario_pattern_calibration_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "ScenarioPatternCalibrationSettings",
    "build_scenario_pattern_calibration_report",
    "write_scenario_pattern_calibration_report",
]
