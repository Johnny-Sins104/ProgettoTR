"""Prompt 29.4.4s-6b — LSR-v2 timeframe strictness + candidate quality report.

This module is deliberately diagnostic-only.  It scans historical OHLCV rows for
Liquidity Sweep Reversal v2 candidates and writes audit artifacts.  It must not
submit orders, open positions, route to a broker, alter risk limits, or lower
runtime thresholds.

Candidate definition, simplified for deterministic backtests:
    liquidity pool -> sweep -> failed continuation -> reclaim -> CHoCH/BOS
    approximation -> optional retest entry candidate.

The detector is intentionally conservative in side effects and explicit about
missing data.  It can consume lists of dictionaries, JSON/JSONL/CSV/Parquet files
or a pandas DataFrame through the runner.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import csv
import json
import math
import os
import re
import statistics

PROMPT_ID = "29.4.4s-6b"
EVENT_TYPE = "LSR_V2_CANDIDATE_AUDIT"
REPORT_NAME = "lsr_v2_candidate_audit_report.json"
JSONL_NAME = "lsr_v2_candidate_audit.jsonl"
READY_DECISION = "LSR_V2_CANDIDATE_AUDIT_READY_DIAGNOSTIC"
NO_MARKET_DATA_DECISION = "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
NO_MATCHING_TIMEFRAME_DECISION = "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
LOAD_ERROR_DECISION = "KEEP_DIAGNOSTIC_MARKET_DATA_LOAD_ERROR"


@dataclass(frozen=True)
class LSRV2Settings:
    data_dir: str = "data"
    input_path: str | None = None
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    strict_timeframe: bool = True
    allow_timeframe_fallback: bool = False
    report_name: str = REPORT_NAME
    jsonl_name: str = JSONL_NAME
    max_rows: int = 250000
    pool_lookback: int = 20
    confirmation_window: int = 4
    retest_window: int = 6
    micro_structure_lookback: int = 5
    min_sweep_bps: float = 2.0
    reclaim_buffer_bps: float = 0.0
    retest_tolerance_bps: float = 8.0
    stop_buffer_bps: float = 2.0
    target_rr: float = 2.0
    min_rr: float = 1.5
    fee_rate: float = 0.0004
    spread_bps: float = 0.0
    slippage_bps: float = 0.0
    max_cost_to_r: float = 0.35
    require_retest_for_candidate_ready: bool = True
    require_volume_confirmation: bool = False
    min_volume_ratio: float = 1.05

    @classmethod
    def from_env(cls) -> "LSRV2Settings":
        def _get(name: str, default: str) -> str:
            return os.environ.get(name, default)

        def _f(name: str, default: float) -> float:
            try:
                return float(_get(name, str(default)))
            except Exception:
                return default

        def _i(name: str, default: int) -> int:
            try:
                return int(float(_get(name, str(default))))
            except Exception:
                return default

        def _b(name: str, default: bool) -> bool:
            raw = _get(name, "1" if default else "0").strip().lower()
            return raw in {"1", "true", "yes", "y", "on"}

        return cls(
            data_dir=_get("LSR_V2_DATA_DIR", "data"),
            input_path=os.environ.get("LSR_V2_INPUT_PATH"),
            symbol=_get("LSR_V2_SYMBOL", "BTC/USDT"),
            timeframe=_get("LSR_V2_TIMEFRAME", "5m"),
            strict_timeframe=_b("LSR_V2_STRICT_TIMEFRAME", True),
            allow_timeframe_fallback=_b("LSR_V2_ALLOW_TIMEFRAME_FALLBACK", False),
            max_rows=_i("LSR_V2_MAX_ROWS", 250000),
            pool_lookback=_i("LSR_V2_POOL_LOOKBACK", 20),
            confirmation_window=_i("LSR_V2_CONFIRMATION_WINDOW", 4),
            retest_window=_i("LSR_V2_RETEST_WINDOW", 6),
            micro_structure_lookback=_i("LSR_V2_MICRO_STRUCTURE_LOOKBACK", 5),
            min_sweep_bps=_f("LSR_V2_MIN_SWEEP_BPS", 2.0),
            reclaim_buffer_bps=_f("LSR_V2_RECLAIM_BUFFER_BPS", 0.0),
            retest_tolerance_bps=_f("LSR_V2_RETEST_TOLERANCE_BPS", 8.0),
            stop_buffer_bps=_f("LSR_V2_STOP_BUFFER_BPS", 2.0),
            target_rr=_f("LSR_V2_TARGET_RR", 2.0),
            min_rr=_f("LSR_V2_MIN_RR", 1.5),
            fee_rate=_f("LSR_V2_FEE_RATE", 0.0004),
            spread_bps=_f("LSR_V2_SPREAD_BPS", 0.0),
            slippage_bps=_f("LSR_V2_SLIPPAGE_BPS", 0.0),
            max_cost_to_r=_f("LSR_V2_MAX_COST_TO_R", 0.35),
            require_retest_for_candidate_ready=_b("LSR_V2_REQUIRE_RETEST_READY", True),
            require_volume_confirmation=_b("LSR_V2_REQUIRE_VOLUME_CONFIRMATION", False),
            min_volume_ratio=_f("LSR_V2_MIN_VOLUME_RATIO", 1.05),
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        if value is None:
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _get(row: dict[str, Any], aliases: Sequence[str], default: Any = None) -> Any:
    if not isinstance(row, dict):
        return default
    for key in aliases:
        if key in row and row.get(key) is not None:
            return row.get(key)
    lower = {str(k).lower(): v for k, v in row.items()}
    for key in aliases:
        val = lower.get(str(key).lower())
        if val is not None:
            return val
    return default


def _timestamp(row: dict[str, Any], index: int) -> str:
    raw = _get(row, ("timestamp", "datetime", "date", "time", "open_time", "ts"), None)
    if raw is None:
        return str(index)
    try:
        # pandas timestamps and datetime objects stringify cleanly; numeric millisecond
        # epochs are made readable when possible.
        if isinstance(raw, (int, float)) and raw > 10_000_000_000:
            return datetime.fromtimestamp(raw / 1000.0, tz=timezone.utc).isoformat()
        if isinstance(raw, (int, float)) and raw > 1_000_000_000:
            return datetime.fromtimestamp(raw, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return str(raw)


def _normalize_row(row: dict[str, Any], index: int, default_symbol: str) -> dict[str, Any]:
    out = dict(row)
    out["_index"] = index
    out["timestamp"] = _timestamp(row, index)
    out["symbol"] = str(_get(row, ("symbol", "asset", "pair"), default_symbol) or default_symbol)
    out["open"] = _safe_float(_get(row, ("open", "o"), None), None)
    out["high"] = _safe_float(_get(row, ("high", "h"), None), None)
    out["low"] = _safe_float(_get(row, ("low", "l"), None), None)
    out["close"] = _safe_float(_get(row, ("close", "c"), None), None)
    out["volume"] = _safe_float(_get(row, ("volume", "vol", "base_volume"), 0.0), 0.0)
    out["regime"] = str(_get(row, ("market_regime", "regime"), "UNKNOWN") or "UNKNOWN")
    return out


def normalize_ohlcv_rows(rows: Iterable[dict[str, Any]], settings: LSRV2Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or LSRV2Settings()
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        row = _normalize_row(raw, idx, settings.symbol)
        if all(row.get(k) is not None for k in ("open", "high", "low", "close")):
            normalized.append(row)
        if len(normalized) >= max(0, int(settings.max_rows)):
            break
    return normalized


def _load_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("candles", "data", "rows", "ohlcv"):
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]
    return []


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        return list(csv.DictReader(fh))


def _load_parquet(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on local env
        raise RuntimeError(f"pandas is required to read parquet input: {exc}") from exc
    df = pd.read_parquet(path)
    if getattr(df, "index", None) is not None and df.index.name and df.index.name not in df.columns:
        df = df.reset_index()
    elif getattr(df, "index", None) is not None and "timestamp" not in df.columns:
        try:
            # Preserve useful DateTimeIndex values without forcing it on RangeIndex.
            if str(type(df.index)).lower().find("datetime") >= 0:
                df = df.reset_index().rename(columns={df.index.name or "index": "timestamp"})
        except Exception:
            pass
    return df.to_dict("records")


_TIMEFRAME_TOKEN_RE = re.compile(r"(?<![a-zA-Z0-9])(\d{1,3}[mhdw]|\d{1,3}min|\d{1,3}minute|\d{1,3}minutes|\d{1,2}hour|\d{1,2}hours|\d{1,2}day|\d{1,2}days)(?=($|[^a-zA-Z0-9]))", re.IGNORECASE)
_TIMEFRAME_NORMALIZATION = {
    "1min": "1m",
    "1minute": "1m",
    "1minutes": "1m",
    "3min": "3m",
    "3minute": "3m",
    "3minutes": "3m",
    "5min": "5m",
    "5minute": "5m",
    "5minutes": "5m",
    "15min": "15m",
    "15minute": "15m",
    "15minutes": "15m",
    "30min": "30m",
    "30minute": "30m",
    "30minutes": "30m",
    "1hour": "1h",
    "1hours": "1h",
    "4hour": "4h",
    "4hours": "4h",
    "1day": "1d",
    "1days": "1d",
}


def normalize_timeframe_label(value: Any) -> str:
    raw = str(value or "").strip().lower().replace(" ", "")
    if not raw:
        return ""
    return _TIMEFRAME_NORMALIZATION.get(raw, raw)


def infer_timeframe_from_path(path: Path | str) -> str:
    """Infer a timeframe label from a file name without confusing 50k/20k windows."""
    name = Path(path).name.lower()
    normalized = re.sub(r"[._\-]+", "_", name)
    # Prefer explicit token matching, e.g. btc_15m_50k_cache.parquet -> 15m.
    for token in normalized.split("_"):
        token = token.split(".")[0]
        label = normalize_timeframe_label(token)
        if re.fullmatch(r"\d{1,3}[mhdw]", label):
            return label
    # Fallback for names such as btc5m_cache.csv while still requiring m/h/d/w.
    match = _TIMEFRAME_TOKEN_RE.search(name.replace(".", "_"))
    if match:
        return normalize_timeframe_label(match.group(1))
    return "UNKNOWN"


def timeframe_matches_path(path: Path | str, requested_timeframe: str) -> tuple[bool, str]:
    requested = normalize_timeframe_label(requested_timeframe)
    detected = infer_timeframe_from_path(path)
    return bool(requested and detected == requested), detected


def _market_data_extension(path: Path) -> bool:
    return path.suffix.lower() in {".parquet", ".csv", ".jsonl", ".json"}


def _candidate_input_paths(
    data_dir: Path,
    symbol: str,
    timeframe: str,
    *,
    allow_timeframe_fallback: bool = False,
) -> list[Path]:
    compact = symbol.replace("/", "").replace(":", "").lower()
    underscored = symbol.replace("/", "_").replace(":", "_").lower()
    requested = normalize_timeframe_label(timeframe)
    strict_patterns = [
        f"*{compact}*{requested}*.parquet",
        f"*{underscored}*{requested}*.parquet",
        f"*btc*{requested}*.parquet",
        f"*{requested}*.parquet",
        f"*{compact}*{requested}*.csv",
        f"*{underscored}*{requested}*.csv",
        f"*btc*{requested}*.csv",
        f"*{requested}*.csv",
        f"*{compact}*{requested}*.jsonl",
        f"*{underscored}*{requested}*.jsonl",
        f"*btc*{requested}*.jsonl",
        f"*{requested}*.jsonl",
        f"*{compact}*{requested}*.json",
        f"*{underscored}*{requested}*.json",
        f"*btc*{requested}*.json",
        f"*{requested}*.json",
    ]
    fallback_patterns = ["*btc*.parquet", "*.parquet", "*btc*.csv", "*.csv", "*btc*.jsonl", "*.jsonl", "*btc*.json", "*.json"]
    patterns = strict_patterns + (fallback_patterns if allow_timeframe_fallback else [])
    out: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(data_dir.glob(pattern)):
            if path.name in {JSONL_NAME, REPORT_NAME, "trade_level_telemetry.jsonl"}:
                continue
            if path in seen or not path.is_file() or not _market_data_extension(path):
                continue
            matched, detected = timeframe_matches_path(path, requested)
            if matched or allow_timeframe_fallback:
                seen.add(path)
                out.append(path)
    return out


def load_market_rows(settings: LSRV2Settings) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data_dir = Path(settings.data_dir)
    requested = normalize_timeframe_label(settings.timeframe)
    explicit_path = Path(settings.input_path) if settings.input_path else None
    candidates = [explicit_path] if explicit_path else _candidate_input_paths(
        data_dir,
        settings.symbol,
        requested,
        allow_timeframe_fallback=bool(settings.allow_timeframe_fallback),
    )
    errors: list[str] = []
    tried: list[str] = []
    mismatch_paths: list[dict[str, str]] = []
    for path in candidates:
        if path is None:
            continue
        tried.append(str(path))
        detected_timeframe = infer_timeframe_from_path(path)
        timeframe_match = detected_timeframe == requested
        if settings.strict_timeframe and not settings.allow_timeframe_fallback and not timeframe_match:
            mismatch_paths.append({
                "path": str(path),
                "requested_timeframe": requested,
                "detected_timeframe": detected_timeframe,
            })
            errors.append(f"timeframe_mismatch:{path}:requested={requested}:detected={detected_timeframe}")
            continue
        try:
            if not path.exists() or not path.is_file():
                errors.append(f"missing:{path}")
                continue
            suffix = path.suffix.lower()
            if suffix == ".parquet":
                raw = _load_parquet(path)
            elif suffix == ".csv":
                raw = _load_csv(path)
            elif suffix == ".jsonl":
                raw = _load_jsonl(path)
            elif suffix == ".json":
                raw = _load_json(path)
            else:
                errors.append(f"unsupported_suffix:{path}")
                continue
            rows = normalize_ohlcv_rows(raw, settings)
            if rows:
                return rows, {
                    "input_path": str(path),
                    "tried_paths": tried,
                    "load_errors": errors,
                    "input_rows": len(rows),
                    "requested_timeframe": requested,
                    "detected_timeframe": detected_timeframe,
                    "timeframe_match": timeframe_match,
                    "strict_timeframe": bool(settings.strict_timeframe),
                    "allow_timeframe_fallback": bool(settings.allow_timeframe_fallback),
                    "timeframe_mismatch_paths": mismatch_paths,
                    "no_matching_timeframe_data": False,
                }
            errors.append(f"no_ohlcv_rows:{path}")
        except Exception as exc:
            errors.append(f"{path}:{type(exc).__name__}:{exc}")

    # When no path was tried under strict discovery, enumerate nearby market-data files
    # only for diagnostics.  Do not load them unless fallback is explicitly enabled.
    if not explicit_path and settings.strict_timeframe and not settings.allow_timeframe_fallback:
        for path in sorted(data_dir.glob("*")):
            if not path.is_file() or not _market_data_extension(path):
                continue
            if path.name in {JSONL_NAME, REPORT_NAME, "trade_level_telemetry.jsonl"}:
                continue
            detected = infer_timeframe_from_path(path)
            if detected != requested:
                mismatch_paths.append({
                    "path": str(path),
                    "requested_timeframe": requested,
                    "detected_timeframe": detected,
                })

    no_matching = bool(mismatch_paths) and not candidates
    if explicit_path and mismatch_paths:
        no_matching = True
    elif mismatch_paths and not tried:
        no_matching = True
    elif mismatch_paths and not any("no_ohlcv_rows" in e or "missing" in e or "unsupported_suffix" in e for e in errors):
        no_matching = True
    return [], {
        "input_path": "",
        "tried_paths": tried,
        "load_errors": errors,
        "input_rows": 0,
        "requested_timeframe": requested,
        "detected_timeframe": "",
        "timeframe_match": False,
        "strict_timeframe": bool(settings.strict_timeframe),
        "allow_timeframe_fallback": bool(settings.allow_timeframe_fallback),
        "timeframe_mismatch_paths": mismatch_paths,
        "no_matching_timeframe_data": bool(no_matching or mismatch_paths),
    }


def _bps(level: float, bps: float) -> float:
    return float(level) * float(bps) / 10000.0


def _avg_volume(rows: list[dict[str, Any]], start: int, end: int) -> float:
    vals = [_safe_float(r.get("volume"), 0.0) or 0.0 for r in rows[max(0, start):max(0, end)]]
    vals = [v for v in vals if v > 0]
    return sum(vals) / len(vals) if vals else 0.0


def _volume_ok(rows: list[dict[str, Any]], idx: int, settings: LSRV2Settings) -> tuple[bool, float]:
    volume = _safe_float(rows[idx].get("volume"), 0.0) or 0.0
    avg = _avg_volume(rows, idx - settings.pool_lookback, idx)
    if avg <= 0:
        return (not settings.require_volume_confirmation), 0.0
    ratio = volume / avg
    return ratio >= settings.min_volume_ratio, round(ratio, 6)


def _cost_to_r(entry: float, stop: float, settings: LSRV2Settings) -> float:
    risk = abs(entry - stop)
    if risk <= 0 or entry <= 0:
        return 999.0
    round_trip_cost_bps = settings.fee_rate * 2.0 * 10000.0 + settings.spread_bps + settings.slippage_bps
    cost_abs = entry * round_trip_cost_bps / 10000.0
    return cost_abs / risk



def _avg_true_range_proxy(rows: list[dict[str, Any]], start: int, end: int) -> float:
    vals: list[float] = []
    for r in rows[max(0, start):max(0, end)]:
        high = _safe_float(r.get("high"), None)
        low = _safe_float(r.get("low"), None)
        if high is None or low is None:
            continue
        rng = float(high) - float(low)
        if rng > 0:
            vals.append(rng)
    return sum(vals) / len(vals) if vals else 0.0


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return float(numerator) / float(denominator)


def _quality_grade(*, candidate_ready: bool, retest_ready: bool, gross_rr: float, cost_to_r: float, volume_ratio: float, settings: LSRV2Settings) -> tuple[str, int, list[str]]:
    score = 0
    reasons: list[str] = []
    if candidate_ready:
        score += 30
        reasons.append("candidate_ready")
    if retest_ready:
        score += 20
        reasons.append("retest_ready")
    if gross_rr >= max(settings.target_rr, settings.min_rr):
        score += 20
        reasons.append("rr_target_met")
    elif gross_rr >= settings.min_rr:
        score += 10
        reasons.append("rr_min_met")
    if cost_to_r <= settings.max_cost_to_r * 0.50:
        score += 20
        reasons.append("low_cost_to_r")
    elif cost_to_r <= settings.max_cost_to_r:
        score += 10
        reasons.append("cost_to_r_ok")
    if volume_ratio >= max(settings.min_volume_ratio, 1.20):
        score += 10
        reasons.append("volume_expansion")
    elif volume_ratio >= 1.0:
        score += 5
        reasons.append("volume_neutral_or_better")
    if score >= 80:
        return "A", score, reasons
    if score >= 55:
        return "B", score, reasons
    return "C", score, reasons

def _candidate_payload(
    *,
    settings: LSRV2Settings,
    rows: list[dict[str, Any]],
    side: str,
    sweep_i: int,
    reclaim_i: int,
    retest_i: int | None,
    pool_level: float,
    sweep_extreme: float,
    micro_structure_level: float,
    volume_ratio: float,
) -> dict[str, Any]:
    retest_ready = retest_i is not None
    entry_price = pool_level
    if side == "BUY":
        stop_loss = sweep_extreme - _bps(sweep_extreme, settings.stop_buffer_bps)
        risk_abs = max(entry_price - stop_loss, 0.0)
        take_profit = entry_price + risk_abs * settings.target_rr
    else:
        stop_loss = sweep_extreme + _bps(sweep_extreme, settings.stop_buffer_bps)
        risk_abs = max(stop_loss - entry_price, 0.0)
        take_profit = entry_price - risk_abs * settings.target_rr
    gross_rr = abs(take_profit - entry_price) / risk_abs if risk_abs > 0 else 0.0
    cost_to_r = _cost_to_r(entry_price, stop_loss, settings)
    cost_to_r_ok = cost_to_r <= settings.max_cost_to_r
    rr_ok = gross_rr >= settings.min_rr
    _, vol_ratio_now = _volume_ok(rows, sweep_i, settings)
    volume_ok = (not settings.require_volume_confirmation) or (vol_ratio_now >= settings.min_volume_ratio)
    candidate_ready = bool(rr_ok and cost_to_r_ok and volume_ok and (retest_ready or not settings.require_retest_for_candidate_ready))
    atr_proxy = _avg_true_range_proxy(rows, sweep_i - settings.pool_lookback, sweep_i)
    if side == "BUY":
        sweep_depth_abs = max(pool_level - sweep_extreme, 0.0)
        reclaim_strength_abs = max(float(rows[reclaim_i]["close"]) - pool_level, 0.0)
        retest_distance_abs = abs(float(rows[retest_i]["low"]) - pool_level) if retest_i is not None else None
    else:
        sweep_depth_abs = max(sweep_extreme - pool_level, 0.0)
        reclaim_strength_abs = max(pool_level - float(rows[reclaim_i]["close"]), 0.0)
        retest_distance_abs = abs(float(rows[retest_i]["high"]) - pool_level) if retest_i is not None else None
    sweep_depth_atr = _safe_ratio(sweep_depth_abs, atr_proxy)
    reclaim_strength_atr = _safe_ratio(reclaim_strength_abs, atr_proxy)
    retest_distance_atr = _safe_ratio(retest_distance_abs or 0.0, atr_proxy) if retest_distance_abs is not None else None
    quality_grade, quality_score, quality_reasons = _quality_grade(
        candidate_ready=candidate_ready,
        retest_ready=retest_ready,
        gross_rr=gross_rr,
        cost_to_r=cost_to_r,
        volume_ratio=vol_ratio_now,
        settings=settings,
    )
    cand_id = f"lsrv2_{side.lower()}_{rows[sweep_i].get('timestamp')}_{sweep_i}".replace(" ", "_").replace(":", "-").replace("/", "")
    return {
        "event_type": EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "candidate_id": cand_id,
        "symbol": rows[sweep_i].get("symbol", settings.symbol),
        "timeframe": settings.timeframe,
        "side": side,
        "archetype": "LIQUIDITY_SWEEP_REVERSAL_V2",
        "sweep_timestamp": rows[sweep_i].get("timestamp"),
        "reclaim_timestamp": rows[reclaim_i].get("timestamp"),
        "retest_timestamp": rows[retest_i].get("timestamp") if retest_i is not None else None,
        "sweep_index": sweep_i,
        "reclaim_index": reclaim_i,
        "retest_index": retest_i,
        "lifecycle": {
            "liquidity_pool_detected": True,
            "sweep_detected": True,
            "failed_continuation": True,
            "structure_reclaim": True,
            "choch_bos_approx": True,
            "retest_ready": retest_ready,
        },
        "levels": {
            "liquidity_pool_level": round(pool_level, 10),
            "sweep_extreme": round(sweep_extreme, 10),
            "micro_structure_level": round(micro_structure_level, 10),
            "entry_price": round(entry_price, 10),
            "stop_loss": round(stop_loss, 10),
            "take_profit": round(take_profit, 10),
        },
        "entry_plan": {
            "entry_type": "LIMIT_RETEST" if retest_ready else "WAIT_FOR_RETEST",
            "entry_price": round(entry_price, 10),
            "submit_order": False,
            "route_order": False,
            "broker_submit_called": False,
        },
        "risk": {
            "risk_abs": round(risk_abs, 10),
            "target_rr": settings.target_rr,
            "gross_rr": round(gross_rr, 6),
            "round_trip_fee_bps": round(settings.fee_rate * 2.0 * 10000.0, 6),
            "spread_bps": settings.spread_bps,
            "slippage_bps": settings.slippage_bps,
            "cost_to_r": round(cost_to_r, 6),
        },
        "quality": {
            "grade": quality_grade,
            "score": quality_score,
            "reasons": quality_reasons,
            "atr_proxy": round(atr_proxy, 10),
            "sweep_depth_abs": round(sweep_depth_abs, 10),
            "sweep_depth_atr": round(sweep_depth_atr, 6) if sweep_depth_atr is not None else None,
            "reclaim_strength_abs": round(reclaim_strength_abs, 10),
            "reclaim_strength_atr": round(reclaim_strength_atr, 6) if reclaim_strength_atr is not None else None,
            "retest_distance_abs": round(retest_distance_abs, 10) if retest_distance_abs is not None else None,
            "retest_distance_atr": round(retest_distance_atr, 6) if retest_distance_atr is not None else None,
        },
        "filters": {
            "rr_ok": bool(rr_ok),
            "cost_to_r_ok": bool(cost_to_r_ok),
            "volume_ok": bool(volume_ok),
            "volume_ratio": round(volume_ratio, 6),
            "regime": rows[sweep_i].get("regime", "UNKNOWN"),
        },
        "candidate_ready": candidate_ready,
        "orders_submitted_by_lsr_v2": 0,
        "positions_opened_by_lsr_v2": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
    }


def _find_buy_candidate(rows: list[dict[str, Any]], i: int, settings: LSRV2Settings) -> dict[str, Any] | None:
    prior = rows[i - settings.pool_lookback:i]
    pool_low = min(float(r["low"]) for r in prior)
    sweep_low = float(rows[i]["low"])
    if not (sweep_low < pool_low - _bps(pool_low, settings.min_sweep_bps)):
        return None

    volume_ok, volume_ratio = _volume_ok(rows, i, settings)
    if settings.require_volume_confirmation and not volume_ok:
        return None

    reclaim_level = pool_low + _bps(pool_low, settings.reclaim_buffer_bps)
    micro_start = max(0, i - settings.micro_structure_lookback)
    micro_high = max(float(r["high"]) for r in rows[micro_start:i])
    max_j = min(len(rows) - 1, i + settings.confirmation_window)
    for j in range(i, max_j + 1):
        close_j = float(rows[j]["close"])
        if close_j <= reclaim_level:
            continue
        # Failed continuation: no close below the sweep extreme before reclaim.
        if any(float(rows[k]["close"]) < sweep_low for k in range(i, j + 1)):
            continue
        choch = close_j > micro_high or float(rows[j]["high"]) > micro_high
        if not choch:
            continue
        retest_i: int | None = None
        max_k = min(len(rows) - 1, j + settings.retest_window)
        for k in range(j + 1, max_k + 1):
            low_k = float(rows[k]["low"])
            close_k = float(rows[k]["close"])
            if low_k <= pool_low + _bps(pool_low, settings.retest_tolerance_bps) and close_k >= reclaim_level:
                retest_i = k
                break
        return _candidate_payload(
            settings=settings,
            rows=rows,
            side="BUY",
            sweep_i=i,
            reclaim_i=j,
            retest_i=retest_i,
            pool_level=pool_low,
            sweep_extreme=sweep_low,
            micro_structure_level=micro_high,
            volume_ratio=volume_ratio,
        )
    return None


def _find_sell_candidate(rows: list[dict[str, Any]], i: int, settings: LSRV2Settings) -> dict[str, Any] | None:
    prior = rows[i - settings.pool_lookback:i]
    pool_high = max(float(r["high"]) for r in prior)
    sweep_high = float(rows[i]["high"])
    if not (sweep_high > pool_high + _bps(pool_high, settings.min_sweep_bps)):
        return None

    volume_ok, volume_ratio = _volume_ok(rows, i, settings)
    if settings.require_volume_confirmation and not volume_ok:
        return None

    reclaim_level = pool_high - _bps(pool_high, settings.reclaim_buffer_bps)
    micro_start = max(0, i - settings.micro_structure_lookback)
    micro_low = min(float(r["low"]) for r in rows[micro_start:i])
    max_j = min(len(rows) - 1, i + settings.confirmation_window)
    for j in range(i, max_j + 1):
        close_j = float(rows[j]["close"])
        if close_j >= reclaim_level:
            continue
        if any(float(rows[k]["close"]) > sweep_high for k in range(i, j + 1)):
            continue
        choch = close_j < micro_low or float(rows[j]["low"]) < micro_low
        if not choch:
            continue
        retest_i: int | None = None
        max_k = min(len(rows) - 1, j + settings.retest_window)
        for k in range(j + 1, max_k + 1):
            high_k = float(rows[k]["high"])
            close_k = float(rows[k]["close"])
            if high_k >= pool_high - _bps(pool_high, settings.retest_tolerance_bps) and close_k <= reclaim_level:
                retest_i = k
                break
        return _candidate_payload(
            settings=settings,
            rows=rows,
            side="SELL",
            sweep_i=i,
            reclaim_i=j,
            retest_i=retest_i,
            pool_level=pool_high,
            sweep_extreme=sweep_high,
            micro_structure_level=micro_low,
            volume_ratio=volume_ratio,
        )
    return None


def detect_lsr_v2_candidates(rows: Iterable[dict[str, Any]], settings: LSRV2Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or LSRV2Settings()
    normalized = normalize_ohlcv_rows(rows, settings)
    min_needed = settings.pool_lookback + settings.confirmation_window + 2
    if len(normalized) < min_needed:
        return []
    out: list[dict[str, Any]] = []
    last_sweep_i_by_side: dict[str, int] = {"BUY": -999999, "SELL": -999999}
    # Leave room for confirmation/retest windows.
    scan_end = len(normalized) - 1
    for i in range(settings.pool_lookback, scan_end):
        buy = _find_buy_candidate(normalized, i, settings)
        if buy is not None and i - last_sweep_i_by_side["BUY"] > settings.confirmation_window:
            out.append(buy)
            last_sweep_i_by_side["BUY"] = i
        sell = _find_sell_candidate(normalized, i, settings)
        if sell is not None and i - last_sweep_i_by_side["SELL"] > settings.confirmation_window:
            out.append(sell)
            last_sweep_i_by_side["SELL"] = i
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def _median(values: list[float]) -> float | None:
    vals = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not vals:
        return None
    return float(statistics.median(vals))


def _avg(values: list[float]) -> float | None:
    vals = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _round_optional(value: float | None, digits: int = 6) -> float | None:
    return round(float(value), digits) if value is not None and math.isfinite(float(value)) else None


def _summarize_candidates(candidates: list[dict[str, Any]], input_rows: int = 0) -> dict[str, Any]:
    by_side: dict[str, int] = {}
    by_regime: dict[str, int] = {}
    quality_buckets: dict[str, int] = {"A": 0, "B": 0, "C": 0}
    ready_quality_buckets: dict[str, int] = {"A": 0, "B": 0, "C": 0}
    ready = 0
    retest_ready = 0
    cost_ok = 0
    rr_values: list[float] = []
    ready_rr_values: list[float] = []
    sweep_depth_atr_values: list[float] = []
    reclaim_strength_values: list[float] = []
    retest_distance_values: list[float] = []
    for c in candidates:
        side = str(c.get("side", "UNKNOWN"))
        by_side[side] = by_side.get(side, 0) + 1
        filters = c.get("filters") if isinstance(c.get("filters"), dict) else {}
        regime = str(filters.get("regime", "UNKNOWN"))
        by_regime[regime] = by_regime.get(regime, 0) + 1
        lifecycle = c.get("lifecycle") if isinstance(c.get("lifecycle"), dict) else {}
        risk = c.get("risk") if isinstance(c.get("risk"), dict) else {}
        quality = c.get("quality") if isinstance(c.get("quality"), dict) else {}
        grade = str(quality.get("grade", "C")) if quality else "C"
        if grade not in quality_buckets:
            quality_buckets[grade] = 0
            ready_quality_buckets[grade] = 0
        quality_buckets[grade] += 1
        rr = _safe_float(risk.get("gross_rr"), None)
        if rr is not None:
            rr_values.append(rr)
        sweep_depth_atr = _safe_float(quality.get("sweep_depth_atr"), None)
        reclaim_strength_atr = _safe_float(quality.get("reclaim_strength_atr"), None)
        retest_distance_atr = _safe_float(quality.get("retest_distance_atr"), None)
        if sweep_depth_atr is not None:
            sweep_depth_atr_values.append(sweep_depth_atr)
        if reclaim_strength_atr is not None:
            reclaim_strength_values.append(reclaim_strength_atr)
        if retest_distance_atr is not None:
            retest_distance_values.append(retest_distance_atr)
        if lifecycle.get("retest_ready"):
            retest_ready += 1
        if filters.get("cost_to_r_ok"):
            cost_ok += 1
        if c.get("candidate_ready"):
            ready += 1
            ready_quality_buckets[grade] += 1
            if rr is not None:
                ready_rr_values.append(rr)
    count = len(candidates)
    input_rows = max(0, int(input_rows or 0))
    candidate_density_pct = (count / input_rows * 100.0) if input_rows else 0.0
    ready_density_pct = (ready / input_rows * 100.0) if input_rows else 0.0
    retest_to_ready_ratio = (ready / retest_ready) if retest_ready else 0.0
    candidate_to_ready_ratio = (ready / count) if count else 0.0
    return {
        "candidates_count": count,
        "candidate_ready_count": ready,
        "retest_ready_count": retest_ready,
        "cost_to_r_ok_count": cost_ok,
        "by_side": by_side,
        "by_regime": by_regime,
        "long_count": by_side.get("BUY", 0),
        "short_count": by_side.get("SELL", 0),
        "candidate_density_pct": round(candidate_density_pct, 6),
        "ready_density_pct": round(ready_density_pct, 6),
        "retest_to_ready_ratio": round(retest_to_ready_ratio, 6),
        "candidate_to_ready_ratio": round(candidate_to_ready_ratio, 6),
        "quality_buckets": quality_buckets,
        "ready_quality_buckets": ready_quality_buckets,
        "quality_A": quality_buckets.get("A", 0),
        "quality_B": quality_buckets.get("B", 0),
        "quality_C": quality_buckets.get("C", 0),
        "ready_quality_A": ready_quality_buckets.get("A", 0),
        "ready_quality_B": ready_quality_buckets.get("B", 0),
        "ready_quality_C": ready_quality_buckets.get("C", 0),
        "median_rr": _round_optional(_median(rr_values)),
        "min_rr": _round_optional(min(rr_values) if rr_values else None),
        "max_rr": _round_optional(max(rr_values) if rr_values else None),
        "ready_median_rr": _round_optional(_median(ready_rr_values)),
        "avg_sweep_depth_atr": _round_optional(_avg(sweep_depth_atr_values)),
        "avg_reclaim_strength": _round_optional(_avg(reclaim_strength_values)),
        "avg_retest_distance_atr": _round_optional(_avg(retest_distance_values)),
    }


def run_lsr_v2_candidate_audit(settings: LSRV2Settings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2Settings()
    data_dir = Path(settings.data_dir)
    jsonl_path = data_dir / settings.jsonl_name
    report_path = data_dir / settings.report_name

    rows, load_info = load_market_rows(settings)
    if not rows:
        _write_jsonl(jsonl_path, [])
        no_matching_timeframe = bool(load_info.get("no_matching_timeframe_data"))
        report = {
            "status": "WARN",
            "decision": NO_MATCHING_TIMEFRAME_DECISION if no_matching_timeframe else NO_MARKET_DATA_DECISION,
            "prompt_id": PROMPT_ID,
            "created_at": utc_now_iso(),
            "symbol": settings.symbol,
            "requested_timeframe": load_info.get("requested_timeframe", normalize_timeframe_label(settings.timeframe)),
            "detected_timeframe": load_info.get("detected_timeframe", ""),
            "timeframe": settings.timeframe,
            "timeframe_match": bool(load_info.get("timeframe_match", False)),
            "strict_timeframe": bool(load_info.get("strict_timeframe", settings.strict_timeframe)),
            "allow_timeframe_fallback": bool(load_info.get("allow_timeframe_fallback", settings.allow_timeframe_fallback)),
            "timeframe_mismatch_paths": load_info.get("timeframe_mismatch_paths", []),
            "input_rows": 0,
            "input_path": load_info.get("input_path", ""),
            "tried_paths": load_info.get("tried_paths", []),
            "load_errors": load_info.get("load_errors", []),
            "summary": _summarize_candidates([], 0),
            "candidates_count": 0,
            "candidate_ready_count": 0,
            "retest_ready_count": 0,
            "orders_submitted_by_lsr_v2": 0,
            "positions_opened_by_lsr_v2": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "jsonl": str(jsonl_path),
            "report": str(report_path),
        }
        _write_json(report_path, report)
        return report

    try:
        candidates = detect_lsr_v2_candidates(rows, settings)
    except Exception as exc:
        _write_jsonl(jsonl_path, [])
        report = {
            "status": "WARN",
            "decision": LOAD_ERROR_DECISION,
            "prompt_id": PROMPT_ID,
            "created_at": utc_now_iso(),
            "symbol": settings.symbol,
            "requested_timeframe": load_info.get("requested_timeframe", normalize_timeframe_label(settings.timeframe)),
            "detected_timeframe": load_info.get("detected_timeframe", ""),
            "timeframe": settings.timeframe,
            "timeframe_match": bool(load_info.get("timeframe_match", False)),
            "strict_timeframe": bool(load_info.get("strict_timeframe", settings.strict_timeframe)),
            "allow_timeframe_fallback": bool(load_info.get("allow_timeframe_fallback", settings.allow_timeframe_fallback)),
            "input_rows": len(rows),
            "input_path": load_info.get("input_path", ""),
            "error": f"{type(exc).__name__}: {exc}",
            "candidates_count": 0,
            "candidate_ready_count": 0,
            "orders_submitted_by_lsr_v2": 0,
            "positions_opened_by_lsr_v2": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "jsonl": str(jsonl_path),
            "report": str(report_path),
        }
        _write_json(report_path, report)
        return report

    written = _write_jsonl(jsonl_path, candidates)
    summary = _summarize_candidates(candidates, len(rows))
    report = {
        "status": "PASS",
        "decision": READY_DECISION,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "symbol": settings.symbol,
        "requested_timeframe": load_info.get("requested_timeframe", normalize_timeframe_label(settings.timeframe)),
        "detected_timeframe": load_info.get("detected_timeframe", ""),
        "timeframe": settings.timeframe,
        "timeframe_match": bool(load_info.get("timeframe_match", False)),
        "strict_timeframe": bool(load_info.get("strict_timeframe", settings.strict_timeframe)),
        "allow_timeframe_fallback": bool(load_info.get("allow_timeframe_fallback", settings.allow_timeframe_fallback)),
        "timeframe_mismatch_paths": load_info.get("timeframe_mismatch_paths", []),
        "input_rows": len(rows),
        "input_path": load_info.get("input_path", ""),
        "tried_paths": load_info.get("tried_paths", []),
        "load_errors": load_info.get("load_errors", []),
        "settings": asdict(settings),
        "summary": summary,
        "candidates_count": summary["candidates_count"],
        "candidate_ready_count": summary["candidate_ready_count"],
        "retest_ready_count": summary["retest_ready_count"],
        "jsonl_rows": written,
        "orders_submitted_by_lsr_v2": 0,
        "positions_opened_by_lsr_v2": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "promotion_blocked_reason": "candidate audit only; requires backtest matrix, cost stress, walk-forward/OOS and promotion gate",
        "jsonl": str(jsonl_path),
        "report": str(report_path),
    }
    _write_json(report_path, report)
    return report
