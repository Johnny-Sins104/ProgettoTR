"""Prompt 29.5.0c pattern-conditioned shadow/backtest review.

Diagnostic-only module that evaluates whether Prompt 29.5.0a scenario context
and Prompt 29.5.0b candlestick-pattern context would have improved trade
selection.  It never changes thresholds, strategy decisions, paper orders,
testnet or live execution.

Two evidence sources are supported:

1. Runtime evidence from ``data/paper_events.jsonl`` by joining
   CRYPTO_SCENARIO_DIAGNOSTIC and CANDLESTICK_PATTERN_DIAGNOSTIC events.
2. Optional historical shadow evidence from cached OHLCV parquet files, where
   scenario + pattern candidates are replayed causally and evaluated over
   forward horizons without submitting orders.
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
import os

import pandas as pd

from config import Config
from core.crypto_intraday_scenario import evaluate_crypto_intraday_scenario
from core.candlestick_patterns import detect_candlestick_patterns

REPORT_NAME = "pattern_conditioned_shadow_report.json"
RUNTIME_SCENARIO_EVENT = "CRYPTO_SCENARIO_DIAGNOSTIC"
RUNTIME_PATTERN_EVENT = "CANDLESTICK_PATTERN_DIAGNOSTIC"


@dataclass(frozen=True)
class PatternConditionedShadowSettings:
    enabled: bool = True
    historical_enabled: bool = True
    max_rows_per_asset: int = 5000
    min_warmup_rows: int = 450
    eval_stride: int = 1
    horizons: tuple[int, ...] = (3, 6, 12)
    stop_loss_pct: float = 0.0035
    tp1_pct: float = 0.0035
    tp2_pct: float = 0.0070
    symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT")
    timeframe: str = "5m"
    min_operational_candidates: int = 20
    min_expectancy_r: float = 0.05

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PatternConditionedShadowSettings":
        return cls(
            enabled=bool(getattr(cfg, "PATTERN_CONDITIONED_SHADOW_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "PATTERN_CONDITIONED_HISTORICAL_ENABLED", True)),
            max_rows_per_asset=_safe_int(getattr(cfg, "PATTERN_CONDITIONED_MAX_ROWS_PER_ASSET", 5000), 5000),
            min_warmup_rows=_safe_int(getattr(cfg, "PATTERN_CONDITIONED_MIN_WARMUP_ROWS", 450), 450),
            eval_stride=max(1, _safe_int(getattr(cfg, "PATTERN_CONDITIONED_EVAL_STRIDE", 1), 1)),
            horizons=_parse_int_tuple(getattr(cfg, "PATTERN_CONDITIONED_HORIZONS", "3,6,12"), (3, 6, 12)),
            stop_loss_pct=_safe_float(getattr(cfg, "PATTERN_CONDITIONED_STOP_LOSS_PCT", getattr(cfg, "PAPER_SHADOW_STOP_LOSS_PCT", 0.0035)), 0.0035),
            tp1_pct=_safe_float(getattr(cfg, "PATTERN_CONDITIONED_TP1_PCT", getattr(cfg, "PAPER_SHADOW_TP1_PCT", 0.0035)), 0.0035),
            tp2_pct=_safe_float(getattr(cfg, "PATTERN_CONDITIONED_TP2_PCT", getattr(cfg, "PAPER_SHADOW_TP2_PCT", 0.0070)), 0.0070),
            symbols=tuple(_parse_symbols(getattr(cfg, "PATTERN_CONDITIONED_SYMBOLS", getattr(cfg, "PAPER_ASSET_UNIVERSE", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT")))),
            timeframe=str(getattr(cfg, "PAPER_DEFAULT_TIMEFRAME", "5m") or "5m"),
            min_operational_candidates=_safe_int(getattr(cfg, "PATTERN_CONDITIONED_MIN_OPERATIONAL_CANDIDATES", 20), 20),
            min_expectancy_r=_safe_float(getattr(cfg, "PATTERN_CONDITIONED_MIN_EXPECTANCY_R", 0.05), 0.05),
        )


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
    return 0.0 if d <= 0 else n / d * 100.0


def _parse_int_tuple(value: Any, default: tuple[int, ...]) -> tuple[int, ...]:
    try:
        items = [int(str(x).strip()) for x in str(value).replace(";", ",").split(",") if str(x).strip()]
        return tuple(x for x in items if x > 0) or default
    except Exception:
        return default


def _parse_symbols(value: Any) -> list[str]:
    return [x.strip().upper() for x in str(value or "").replace(";", ",").split(",") if x.strip()]


def _event_type(event: dict[str, Any]) -> str:
    return str(event.get("event_type") or "").upper()


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                obj["__line_no__"] = i
                rows.append(obj)
        except Exception:
            continue
    return rows


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


def _close_col(df: pd.DataFrame) -> str:
    if "Close" in df.columns:
        return "Close"
    return "close"


def _high_col(df: pd.DataFrame) -> str:
    if "High" in df.columns:
        return "High"
    return "high"


def _low_col(df: pd.DataFrame) -> str:
    if "Low" in df.columns:
        return "Low"
    return "low"


def _open_col(df: pd.DataFrame) -> str:
    if "Open" in df.columns:
        return "Open"
    return "open"


def _volume_col(df: pd.DataFrame) -> str:
    if "Volume" in df.columns:
        return "Volume"
    return "volume"


def _normalize_ohlcv(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    out = df.copy()
    rename = {}
    for src, dst in (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"), ("volume", "Volume")):
        if src in out.columns and dst not in out.columns:
            rename[src] = dst
    if rename:
        out = out.rename(columns=rename)
    if "datetime" not in out.columns:
        for cand in ("timestamp", "date", "time", "Date", "Datetime"):
            if cand in out.columns:
                out["datetime"] = pd.to_datetime(out[cand], utc=True, errors="coerce")
                break
    if "datetime" not in out.columns:
        out["datetime"] = pd.RangeIndex(len(out)).astype(str)
    out["asset"] = symbol.replace("/", "").upper()
    return out


def _add_minimal_structure_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    c, h, l, v = _close_col(out), _high_col(out), _low_col(out), _volume_col(out)
    close = pd.to_numeric(out[c], errors="coerce")
    high = pd.to_numeric(out[h], errors="coerce")
    low = pd.to_numeric(out[l], errors="coerce")
    volume = pd.to_numeric(out[v], errors="coerce")

    if "range_pos_400" not in out.columns:
        roll_high = high.rolling(400, min_periods=50).max()
        roll_low = low.rolling(400, min_periods=50).min()
        denom = (roll_high - roll_low).replace(0, pd.NA)
        out["range_pos_400"] = ((close - roll_low) / denom).clip(0, 1).fillna(0.5)
    if "local_support" not in out.columns:
        out["local_support"] = low.rolling(20, min_periods=5).min().shift(1).fillna(low)
    if "local_resistance" not in out.columns:
        out["local_resistance"] = high.rolling(20, min_periods=5).max().shift(1).fillna(high)
    if "macro_support" not in out.columns:
        out["macro_support"] = low.rolling(200, min_periods=30).min().shift(1).fillna(out["local_support"])
    if "macro_resistance" not in out.columns:
        out["macro_resistance"] = high.rolling(200, min_periods=30).max().shift(1).fillna(out["local_resistance"])
    prox = _safe_float(getattr(Config, "CRYPTO_SCENARIO_SR_PROXIMITY_PCT", 0.0035), 0.0035)
    if "near_support" not in out.columns:
        out["near_support"] = ((close - pd.to_numeric(out["local_support"], errors="coerce")).abs() / close.replace(0, pd.NA) <= prox).fillna(False)
    if "near_resistance" not in out.columns:
        out["near_resistance"] = ((close - pd.to_numeric(out["local_resistance"], errors="coerce")).abs() / close.replace(0, pd.NA) <= prox).fillna(False)
    if "market_regime" not in out.columns:
        ret = close.pct_change().abs().rolling(96, min_periods=20).mean()
        med = ret.rolling(400, min_periods=50).median()
        out["market_regime"] = ["TRENDING" if (math.isfinite(_safe_float(a, float("nan"))) and math.isfinite(_safe_float(b, float("nan"))) and a > b * 1.3) else "RANGING" for a, b in zip(ret, med)]
    if "volume_bias" not in out.columns:
        vol_ma = volume.rolling(20, min_periods=5).mean()
        out["volume_bias"] = ["HIGH" if _safe_float(x, 0.0) > _safe_float(y, 1.0) * 1.1 else "NEUTRAL" for x, y in zip(volume, vol_ma)]
    if "atr" not in out.columns:
        prev_close = close.shift(1)
        tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        out["atr"] = tr.rolling(14, min_periods=3).mean().fillna(tr).fillna(close * 0.002)
    return out


def _runtime_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenario_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    pattern_rows: list[dict[str, Any]] = []
    for event in events:
        et = _event_type(event)
        key = (str(event.get("cycle_id") or ""), str(event.get("symbol") or ""))
        if et == RUNTIME_SCENARIO_EVENT:
            scenario_by_key[key] = event
        elif et == RUNTIME_PATTERN_EVENT:
            pattern_rows.append(event)

    rows: list[dict[str, Any]] = []
    for pattern in pattern_rows:
        key = (str(pattern.get("cycle_id") or ""), str(pattern.get("symbol") or ""))
        scenario = scenario_by_key.get(key, {})
        p_bias = str(pattern.get("pattern_bias") or "HOLD").upper()
        s_bias = str(scenario.get("directional_bias") or pattern.get("scenario_directional_bias") or "HOLD").upper()
        aligned = _is_aligned_candidate(pattern_bias=p_bias, scenario_bias=s_bias, scenario_integration=str(pattern.get("scenario_integration") or ""), pattern_alignment=str(pattern.get("pattern_alignment") or ""))
        rows.append({
            "source": "runtime_events",
            "cycle_id": pattern.get("cycle_id"),
            "symbol": pattern.get("symbol"),
            "ts": pattern.get("ts"),
            "scenario": pattern.get("scenario") or scenario.get("scenario"),
            "scenario_bias": s_bias,
            "pattern_bias": p_bias,
            "candidate_side": p_bias if p_bias in {"BUY", "SELL"} else s_bias if s_bias in {"BUY", "SELL"} else "HOLD",
            "patterns": pattern.get("patterns") or [],
            "pattern_score": _safe_float(pattern.get("pattern_score"), 0.0),
            "scenario_integration": pattern.get("scenario_integration"),
            "pattern_alignment": pattern.get("pattern_alignment"),
            "dominant_filter": pattern.get("dominant_filter") or scenario.get("dominant_filter"),
            "aligned_candidate": bool(aligned),
        })
    return rows


def _is_aligned_candidate(*, pattern_bias: str, scenario_bias: str, scenario_integration: str, pattern_alignment: str) -> bool:
    p = str(pattern_bias or "HOLD").upper()
    s = str(scenario_bias or "HOLD").upper()
    integ = str(scenario_integration or "").upper()
    align = str(pattern_alignment or "").upper()
    if p not in {"BUY", "SELL"}:
        return False
    if s in {"BUY", "SELL"} and s != p:
        return False
    if "CONFIRMED_BY_CANDLE" in integ:
        return True
    if align in {"PATTERN_ENGINE_ALIGNED", "PATTERN_SCENARIO_ALIGNED"}:
        return True
    return False


def _candidate_bucket(row: dict[str, Any]) -> str:
    if not row.get("aligned_candidate"):
        return "NON_ALIGNED_OR_WAIT"
    scenario = str(row.get("scenario") or "UNKNOWN")
    side = str(row.get("candidate_side") or "HOLD")
    return f"{side}_{scenario}"


def _summarize_runtime(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_asset: dict[str, Any] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("symbol") or "UNKNOWN")].append(row)
    for symbol, asset_rows in sorted(grouped.items()):
        aligned = [r for r in asset_rows if r.get("aligned_candidate")]
        by_asset[symbol] = {
            "rows": len(asset_rows),
            "aligned_candidates": len(aligned),
            "aligned_rate_pct": round(_pct(len(aligned), len(asset_rows)), 4),
            "candidate_sides": dict(Counter(str(r.get("candidate_side") or "HOLD") for r in asset_rows)),
            "scenarios": dict(Counter(str(r.get("scenario") or "UNKNOWN") for r in asset_rows)),
            "scenario_integrations": dict(Counter(str(r.get("scenario_integration") or "") for r in asset_rows)),
            "pattern_alignment": dict(Counter(str(r.get("pattern_alignment") or "") for r in asset_rows)),
            "patterns": dict(_pattern_counter(asset_rows)),
            "buckets": dict(Counter(_candidate_bucket(r) for r in asset_rows)),
            "pattern_score": _metrics([_safe_float(r.get("pattern_score"), 0.0) for r in asset_rows]),
            "recent": asset_rows[-5:],
        }
    return {
        "rows": len(rows),
        "aligned_candidates": sum(1 for r in rows if r.get("aligned_candidate")),
        "candidate_sides": dict(Counter(str(r.get("candidate_side") or "HOLD") for r in rows)),
        "buckets": dict(Counter(_candidate_bucket(r) for r in rows)),
        "by_asset": by_asset,
        "btc_focus": by_asset.get("BTC/USDT", {"rows": 0, "aligned_candidates": 0}),
    }


def _pattern_counter(rows: list[dict[str, Any]]) -> Counter[str]:
    c: Counter[str] = Counter()
    for row in rows:
        for p in row.get("patterns") or []:
            c[str(p)] += 1
    return c


def _cache_path_for_symbol(data_dir: Path, symbol: str, timeframe: str) -> Path | None:
    slug = symbol.replace("/", "").lower()
    candidates = [
        data_dir / f"{slug}_{timeframe}_150k_cache.parquet",
        data_dir / f"{slug}_{timeframe}_cache.parquet",
        data_dir / f"{slug}_cache.parquet",
    ]
    # Legacy BTC names seen in the project.
    if symbol.upper() == "BTC/USDT":
        candidates.extend([
            data_dir / f"btc_{timeframe}_150k_cache.parquet",
            data_dir / f"btc_{timeframe}_cache.parquet",
        ])
    for p in candidates:
        if p.exists():
            return p
    return None


def _read_cache(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _side_from_pattern_result(pattern: Any, scenario: Any) -> str:
    p = str(getattr(pattern, "pattern_bias", "HOLD") or "HOLD").upper()
    s = str(getattr(scenario, "directional_bias", "HOLD") or "HOLD").upper()
    integ = str(getattr(pattern, "scenario_integration", "") or "")
    align = "PATTERN_SCENARIO_ALIGNED" if p in {"BUY", "SELL"} and s == p else ""
    if _is_aligned_candidate(pattern_bias=p, scenario_bias=s, scenario_integration=integ, pattern_alignment=align):
        return p
    return "HOLD"


def _evaluate_forward(df: pd.DataFrame, idx: int, side: str, settings: PatternConditionedShadowSettings) -> dict[str, Any]:
    c, h, l = _close_col(df), _high_col(df), _low_col(df)
    entry = _safe_float(df.iloc[idx][c], 0.0)
    if entry <= 0 or side not in {"BUY", "SELL"}:
        return {"status": "INVALID", "r": 0.0, "outcome": "INVALID"}
    max_horizon = max(settings.horizons)
    stop_pct = max(settings.stop_loss_pct, 1e-8)
    tp1_pct = max(settings.tp1_pct, stop_pct)
    tp2_pct = max(settings.tp2_pct, tp1_pct)

    if side == "BUY":
        sl = entry * (1.0 - stop_pct)
        tp1 = entry * (1.0 + tp1_pct)
        tp2 = entry * (1.0 + tp2_pct)
    else:
        sl = entry * (1.0 + stop_pct)
        tp1 = entry * (1.0 - tp1_pct)
        tp2 = entry * (1.0 - tp2_pct)

    touched_tp1 = False
    result = {"status": "OPEN", "r": 0.0, "outcome": "NO_TOUCH", "bars_to_event": max_horizon, "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2}
    for step in range(1, max_horizon + 1):
        if idx + step >= len(df):
            break
        row = df.iloc[idx + step]
        hi = _safe_float(row[h], entry)
        lo = _safe_float(row[l], entry)
        if side == "BUY":
            sl_hit = lo <= sl
            tp1_hit = hi >= tp1
            tp2_hit = hi >= tp2
        else:
            sl_hit = hi >= sl
            tp1_hit = lo <= tp1
            tp2_hit = lo <= tp2
        # Conservative same-candle ordering: stop before target.
        if sl_hit:
            result.update({"status": "CLOSED", "r": -1.0, "outcome": "SL", "bars_to_event": step})
            return result
        if tp2_hit:
            result.update({"status": "CLOSED", "r": round(tp2_pct / stop_pct, 6), "outcome": "TP2", "bars_to_event": step})
            return result
        if tp1_hit:
            touched_tp1 = True
            result.update({"status": "OPEN", "r": round(tp1_pct / stop_pct, 6), "outcome": "TP1_ONLY", "bars_to_event": step})

    if touched_tp1:
        return result
    exit_idx = min(idx + max_horizon, len(df) - 1)
    exit_close = _safe_float(df.iloc[exit_idx][c], entry)
    raw_ret = (exit_close - entry) / entry if side == "BUY" else (entry - exit_close) / entry
    result.update({"status": "TIME_EXIT", "r": round(raw_ret / stop_pct, 6), "outcome": "TIME_EXIT", "bars_to_event": exit_idx - idx})
    return result


def _historical_shadow(data_dir: Path, settings: PatternConditionedShadowSettings) -> dict[str, Any]:
    if not settings.historical_enabled:
        return {"enabled": False, "status": "DISABLED", "rows": 0, "candidates": 0, "warnings": ["historical shadow disabled"]}

    warnings: list[str] = []
    all_candidates: list[dict[str, Any]] = []
    by_asset: dict[str, Any] = {}
    for symbol in settings.symbols:
        cache_path = _cache_path_for_symbol(data_dir, symbol, settings.timeframe)
        if cache_path is None:
            warnings.append(f"missing_cache:{symbol}")
            by_asset[symbol] = {"status": "MISSING_CACHE", "candidates": 0}
            continue
        try:
            raw = _read_cache(cache_path)
            df = _normalize_ohlcv(raw, symbol)
            if len(df) > settings.max_rows_per_asset:
                df = df.tail(settings.max_rows_per_asset).reset_index(drop=True)
            df = _add_minimal_structure_features(df)
        except Exception as exc:
            warnings.append(f"cache_read_or_prepare_failed:{symbol}:{exc.__class__.__name__}:{exc}")
            by_asset[symbol] = {"status": "READ_ERROR", "error": str(exc), "candidates": 0, "path": str(cache_path)}
            continue
        asset_candidates: list[dict[str, Any]] = []
        start = max(3, min(settings.min_warmup_rows, max(3, len(df) - max(settings.horizons) - 1)))
        end = max(start, len(df) - max(settings.horizons))
        for idx in range(start, end, settings.eval_stride):
            window = df.iloc[: idx + 1]
            try:
                scenario = evaluate_crypto_intraday_scenario(window, symbol=symbol)
                pattern = detect_candlestick_patterns(window, symbol=symbol, scenario=scenario.to_dict())
            except Exception as exc:
                if len(warnings) < 20:
                    warnings.append(f"eval_failed:{symbol}:{idx}:{exc.__class__.__name__}:{exc}")
                continue
            side = _side_from_pattern_result(pattern, scenario)
            if side not in {"BUY", "SELL"}:
                continue
            forward = _evaluate_forward(df, idx, side, settings)
            row = df.iloc[idx]
            candidate = {
                "symbol": symbol,
                "idx": int(idx),
                "datetime": str(row.get("datetime", idx)),
                "side": side,
                "scenario": scenario.scenario,
                "scenario_bias": scenario.directional_bias,
                "pattern_bias": pattern.pattern_bias,
                "patterns": list(pattern.patterns),
                "pattern_score": float(pattern.pattern_score),
                "scenario_integration": pattern.scenario_integration,
                "range_pos_400": _safe_float(row.get("range_pos_400"), 0.5),
                "dominant_bucket": f"{side}_{scenario.scenario}",
                "forward": forward,
                "r": _safe_float(forward.get("r"), 0.0),
                "outcome": forward.get("outcome"),
            }
            asset_candidates.append(candidate)
            all_candidates.append(candidate)
        by_asset[symbol] = _summarize_candidate_list(asset_candidates)
        by_asset[symbol]["status"] = "PASS"
        by_asset[symbol]["cache_path"] = str(cache_path)
        by_asset[symbol]["rows_evaluated"] = max(0, end - start)
    return {
        "enabled": True,
        "status": "PASS" if all_candidates else "WARN",
        "settings": {
            "max_rows_per_asset": settings.max_rows_per_asset,
            "min_warmup_rows": settings.min_warmup_rows,
            "eval_stride": settings.eval_stride,
            "horizons": list(settings.horizons),
            "stop_loss_pct": settings.stop_loss_pct,
            "tp1_pct": settings.tp1_pct,
            "tp2_pct": settings.tp2_pct,
            "symbols": list(settings.symbols),
        },
        "candidates": len(all_candidates),
        "summary": _summarize_candidate_list(all_candidates),
        "by_asset": by_asset,
        "recent_candidates": _recent_candidates(all_candidates, 15),
        "warnings": warnings[:50],
    }


def _summarize_candidate_list(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "candidates": 0,
            "expectancy_r": 0.0,
            "win_rate_pct": 0.0,
            "loss_rate_pct": 0.0,
            "outcomes": {},
            "buckets": {},
            "sides": {},
            "patterns": {},
            "r_distribution": _metrics([]),
        }
    rs = [_safe_float(r.get("r"), 0.0) for r in rows]
    wins = sum(1 for r in rs if r > 0)
    losses = sum(1 for r in rs if r < 0)
    outcomes = Counter(str(r.get("outcome") or "UNKNOWN") for r in rows)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get("dominant_bucket") or "UNKNOWN")].append(row)
    bucket_summary = {}
    for bucket, bucket_rows in sorted(buckets.items()):
        br = [_safe_float(r.get("r"), 0.0) for r in bucket_rows]
        bucket_summary[bucket] = {
            "candidates": len(bucket_rows),
            "expectancy_r": round(float(mean(br)), 6) if br else 0.0,
            "win_rate_pct": round(_pct(sum(1 for x in br if x > 0), len(br)), 4),
            "outcomes": dict(Counter(str(r.get("outcome") or "UNKNOWN") for r in bucket_rows)),
        }
    return {
        "candidates": len(rows),
        "expectancy_r": round(float(mean(rs)), 6) if rs else 0.0,
        "win_rate_pct": round(_pct(wins, len(rows)), 4),
        "loss_rate_pct": round(_pct(losses, len(rows)), 4),
        "outcomes": dict(outcomes),
        "buckets": bucket_summary,
        "sides": dict(Counter(str(r.get("side") or "UNKNOWN") for r in rows)),
        "patterns": dict(_pattern_counter(rows)),
        "r_distribution": _metrics(rs),
    }


def _recent_candidates(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows[-limit:]:
        out.append({
            "symbol": row.get("symbol"),
            "datetime": row.get("datetime"),
            "side": row.get("side"),
            "scenario": row.get("scenario"),
            "patterns": row.get("patterns"),
            "pattern_score": row.get("pattern_score"),
            "range_pos_400": row.get("range_pos_400"),
            "outcome": row.get("outcome"),
            "r": row.get("r"),
        })
    return out


def _runtime_decision(runtime_summary: dict[str, Any], historical: dict[str, Any], settings: PatternConditionedShadowSettings) -> dict[str, Any]:
    hist_summary = historical.get("summary", {}) if isinstance(historical, dict) else {}
    candidates = _safe_int(hist_summary.get("candidates"), 0)
    expectancy = _safe_float(hist_summary.get("expectancy_r"), 0.0)
    runtime_aligned = _safe_int(runtime_summary.get("aligned_candidates"), 0)
    if candidates >= settings.min_operational_candidates and expectancy >= settings.min_expectancy_r:
        return {
            "status": "SHADOW_EDGE_CANDIDATE",
            "action": "keep diagnostic-only; prepare controlled profile refinement, not direct live/testnet",
            "next_patch": "29.4.4c Paper unlock profile refinement with pattern-conditioned filters",
            "historical_candidates": candidates,
            "historical_expectancy_r": expectancy,
            "runtime_aligned_candidates": runtime_aligned,
        }
    if candidates > 0:
        return {
            "status": "SHADOW_INCONCLUSIVE_OR_WEAK",
            "action": "collect more rows or refine scenario/pattern definitions; do not unlock operationally",
            "next_patch": "29.5.0d Scenario-pattern calibration or 29.4.4c only if manual review approves",
            "historical_candidates": candidates,
            "historical_expectancy_r": expectancy,
            "runtime_aligned_candidates": runtime_aligned,
        }
    if runtime_aligned > 0:
        return {
            "status": "RUNTIME_PATTERN_AVAILABLE_NEEDS_HISTORICAL_CONFIRMATION",
            "action": "fix/enable historical parquet shadow if needed; do not unlock operationally",
            "next_patch": "29.5.0c rerun with historical parquet support",
            "historical_candidates": 0,
            "runtime_aligned_candidates": runtime_aligned,
        }
    return {
        "status": "NO_PATTERN_EDGE_EVIDENCE_YET",
        "action": "do not relax thresholds; keep collecting diagnostics or refine pattern definitions",
        "next_patch": "29.5.0d Scenario-pattern calibration after more rows",
        "historical_candidates": 0,
        "runtime_aligned_candidates": 0,
    }


def build_pattern_conditioned_shadow_report(data_dir: str | Path, settings: PatternConditionedShadowSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or PatternConditionedShadowSettings.from_config()
    events = _read_events(base / "paper_events.jsonl")
    runtime = _summarize_runtime(_runtime_rows(events))
    historical = _historical_shadow(base, settings)
    decision = _runtime_decision(runtime, historical, settings)
    status = "PASS" if decision.get("status") == "SHADOW_EDGE_CANDIDATE" else "WARN"
    if not settings.enabled:
        status = "DISABLED"
    payload = {
        "report_type": "pattern_conditioned_shadow_review",
        "prompt": "29.5.0c",
        "generated_at": utc_now_iso(),
        "status": status,
        "safety": {
            "diagnostic_only": True,
            "opens_orders": False,
            "changes_thresholds": False,
            "enables_live_or_testnet": False,
            "pattern_conditioned_operational_unlock": False,
        },
        "counts": {
            "events_total": len(events),
            "runtime_pattern_rows": runtime.get("rows", 0),
            "runtime_aligned_candidates": runtime.get("aligned_candidates", 0),
            "historical_candidates": (historical.get("summary") or {}).get("candidates", 0) if isinstance(historical, dict) else 0,
            "signals_detected": sum(1 for e in events if _event_type(e) == "SIGNAL_DETECTED"),
            "orders_submitted": sum(1 for e in events if _event_type(e) in {"PAPER_ORDER_SUBMITTED", "PAPER_ORDER_CONFIRMED"}),
            "positions_opened": sum(1 for e in events if _event_type(e) == "POSITION_OPENED"),
        },
        "decision": decision,
        "runtime_review": runtime,
        "historical_shadow": historical,
        "files": {"events": str(base / "paper_events.jsonl"), "report": str(base / REPORT_NAME)},
        "diagnostic_only": True,
        "opens_orders": False,
        "changes_thresholds": False,
        "enables_live_or_testnet": False,
    }
    return payload


def write_pattern_conditioned_shadow_report(data_dir: str | Path, settings: PatternConditionedShadowSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_pattern_conditioned_shadow_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "PatternConditionedShadowSettings",
    "build_pattern_conditioned_shadow_report",
    "write_pattern_conditioned_shadow_report",
]
