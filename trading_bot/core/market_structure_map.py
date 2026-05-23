"""Prompt 29.5.0e liquidity + supply/demand + structure break engine.

Diagnostic-only market-structure layer for ProgettoTR.

The module builds an explicit map of:

- equal highs / equal lows and nearby liquidity pools;
- supply and demand zones from confirmed swing pivots;
- HH / HL / LH / LL swing sequence;
- BOS, CHOCH and MSS candidates;
- retest / failed retest / confirmation-close diagnostics.

It is intentionally non-operational.  It does not change thresholds, paper
unlock settings, risk, order flow, testnet or live execution.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
import json
import math

import numpy as np
import pandas as pd

from config import Config


REPORT_NAME = "market_structure_map_report.json"
PROMPT_ID = "29.5.0e"
EVENT_TYPE = "MARKET_STRUCTURE_MAP_DIAGNOSTIC"


@dataclass(frozen=True)
class MarketStructureMapSettings:
    enabled: bool = True
    historical_enabled: bool = True
    symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT")
    timeframe: str = "5m"
    max_rows_per_asset: int = 5000
    min_warmup_rows: int = 450
    eval_stride: int = 25
    max_snapshots_per_asset: int = 160
    evaluation_window_rows: int = 900
    swing_left: int = 3
    swing_right: int = 2
    recent_swing_lookback: int = 12
    equal_level_tolerance_pct: float = 0.0015
    liquidity_near_pct: float = 0.0040
    zone_atr_mult: float = 0.45
    retest_tolerance_pct: float = 0.0020
    confirmation_body_ratio: float = 0.35
    confirmation_close_buffer_pct: float = 0.0005
    focus_symbol: str = "BTC/USDT"

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "MarketStructureMapSettings":
        return cls(
            enabled=bool(getattr(cfg, "MARKET_STRUCTURE_MAP_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "MARKET_STRUCTURE_MAP_HISTORICAL_ENABLED", True)),
            symbols=tuple(_parse_symbols(getattr(cfg, "MARKET_STRUCTURE_MAP_SYMBOLS", getattr(cfg, "PAPER_ASSET_UNIVERSE", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT"))) or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]),
            timeframe=str(getattr(cfg, "PAPER_DEFAULT_TIMEFRAME", "5m") or "5m"),
            max_rows_per_asset=max(200, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_MAX_ROWS_PER_ASSET", 5000), 5000)),
            min_warmup_rows=max(50, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_MIN_WARMUP_ROWS", 450), 450)),
            eval_stride=max(1, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_EVAL_STRIDE", 25), 25)),
            max_snapshots_per_asset=max(10, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_MAX_SNAPSHOTS_PER_ASSET", 160), 160)),
            evaluation_window_rows=max(120, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_EVALUATION_WINDOW_ROWS", 900), 900)),
            swing_left=max(1, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_SWING_LEFT", 3), 3)),
            swing_right=max(1, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_SWING_RIGHT", 2), 2)),
            recent_swing_lookback=max(4, _safe_int(getattr(cfg, "MARKET_STRUCTURE_MAP_RECENT_SWING_LOOKBACK", 12), 12)),
            equal_level_tolerance_pct=max(0.0, _safe_float(getattr(cfg, "MARKET_STRUCTURE_MAP_EQUAL_LEVEL_TOLERANCE_PCT", 0.0015), 0.0015)),
            liquidity_near_pct=max(0.0, _safe_float(getattr(cfg, "MARKET_STRUCTURE_MAP_LIQUIDITY_NEAR_PCT", 0.0040), 0.0040)),
            zone_atr_mult=max(0.0, _safe_float(getattr(cfg, "MARKET_STRUCTURE_MAP_ZONE_ATR_MULT", 0.45), 0.45)),
            retest_tolerance_pct=max(0.0, _safe_float(getattr(cfg, "MARKET_STRUCTURE_MAP_RETEST_TOLERANCE_PCT", 0.0020), 0.0020)),
            confirmation_body_ratio=max(0.0, _safe_float(getattr(cfg, "MARKET_STRUCTURE_MAP_CONFIRMATION_BODY_RATIO", 0.35), 0.35)),
            confirmation_close_buffer_pct=max(0.0, _safe_float(getattr(cfg, "MARKET_STRUCTURE_MAP_CONFIRMATION_CLOSE_BUFFER_PCT", 0.0005), 0.0005)),
            focus_symbol=str(getattr(cfg, "MARKET_STRUCTURE_MAP_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
        )


@dataclass(frozen=True)
class MarketStructureMapResult:
    symbol: str
    price: float
    price_location: str
    structure_bias: str
    trend_state: str
    swing_sequence: tuple[str, ...]
    last_HH: float
    last_HL: float
    last_LH: float
    last_LL: float
    equal_highs: bool
    equal_lows: bool
    liquidity_above_highs: bool
    liquidity_below_lows: bool
    nearest_liquidity: dict[str, Any]
    demand_zone_low: float
    demand_zone_high: float
    supply_zone_low: float
    supply_zone_high: float
    in_demand_zone: bool
    in_supply_zone: bool
    bos_bullish: bool
    bos_bearish: bool
    choch_bullish: bool
    choch_bearish: bool
    mss_bullish: bool
    mss_bearish: bool
    breakout_retest_confirmed: bool
    breakdown_retest_confirmed: bool
    failed_retest: bool
    confirmation_close: bool
    missing_confirmation: tuple[str, ...]
    confirmation_summary: str
    map_score: float
    levels: dict[str, float]
    context: dict[str, Any]
    diagnostic_only: bool = True
    strategy_changed: bool = False
    operational_unlock_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["swing_sequence"] = list(self.swing_sequence)
        out["missing_confirmation"] = list(self.missing_confirmation)
        return out


@dataclass(frozen=True)
class _Swing:
    idx: int
    kind: str  # H or L
    price: float
    label: str


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


def _parse_symbols(value: Any) -> list[str]:
    return [x.strip().upper() for x in str(value or "").replace(";", ",").split(",") if x.strip()]


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


def _col(df: pd.DataFrame, preferred: str, fallback: str) -> str:
    if preferred in df.columns:
        return preferred
    if fallback in df.columns:
        return fallback
    return preferred


def _open_col(df: pd.DataFrame) -> str:
    return _col(df, "Open", "open")


def _high_col(df: pd.DataFrame) -> str:
    return _col(df, "High", "high")


def _low_col(df: pd.DataFrame) -> str:
    return _col(df, "Low", "low")


def _close_col(df: pd.DataFrame) -> str:
    return _col(df, "Close", "close")


def _volume_col(df: pd.DataFrame) -> str:
    return _col(df, "Volume", "volume")


def _normalize_ohlcv(df: pd.DataFrame, symbol: str = "") -> pd.DataFrame:
    out = df.copy()
    rename: dict[str, str] = {}
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
        if getattr(out.index, "name", None) or not isinstance(out.index, pd.RangeIndex):
            out["datetime"] = pd.to_datetime(out.index, utc=True, errors="coerce")
        else:
            out["datetime"] = list(range(len(out)))
    if symbol:
        out["asset"] = symbol.replace("/", "").upper()
    return out.reset_index(drop=True)


def _add_minimal_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    o, h, l, c, v = _open_col(out), _high_col(out), _low_col(out), _close_col(out), _volume_col(out)
    for required in (o, h, l, c):
        if required not in out.columns:
            raise ValueError(f"OHLCV dataframe missing required column: {required}")
    open_ = pd.to_numeric(out[o], errors="coerce")
    high = pd.to_numeric(out[h], errors="coerce")
    low = pd.to_numeric(out[l], errors="coerce")
    close = pd.to_numeric(out[c], errors="coerce")
    volume = pd.to_numeric(out[v], errors="coerce") if v in out.columns else pd.Series([0.0] * len(out))

    if "atr" not in out.columns:
        prev_close = close.shift(1)
        tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        out["atr"] = tr.rolling(14, min_periods=3).mean().fillna(tr).fillna(close.abs() * 0.002)
    if "range_pos_400" not in out.columns:
        roll_high = high.rolling(400, min_periods=50).max()
        roll_low = low.rolling(400, min_periods=50).min()
        denom = (roll_high - roll_low).replace(0, pd.NA)
        out["range_pos_400"] = ((close - roll_low) / denom).clip(0, 1).fillna(0.5)
    if "volume_z_1d" not in out.columns and len(out) > 5:
        vm = volume.rolling(96, min_periods=20).mean()
        vs = volume.rolling(96, min_periods=20).std().replace(0, pd.NA)
        out["volume_z_1d"] = ((volume - vm) / vs).replace([math.inf, -math.inf], pd.NA).fillna(0.0)
    return out


def _cache_path_for_symbol(data_dir: Path, symbol: str, timeframe: str) -> Path | None:
    slug = symbol.replace("/", "").lower()
    candidates = [
        data_dir / f"{slug}_{timeframe}_150k_cache.parquet",
        data_dir / f"{slug}_{timeframe}_cache.parquet",
        data_dir / f"{slug}_cache.parquet",
    ]
    if symbol.upper() == "BTC/USDT":
        candidates.extend([
            data_dir / f"btc_{timeframe}_150k_cache.parquet",
            data_dir / f"btc_{timeframe}_cache.parquet",
            data_dir / "btc_15m_cache.parquet",
        ])
    for path in candidates:
        if path.exists():
            return path
    return None


def _read_cache(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _confirmed_swings(df: pd.DataFrame, settings: MarketStructureMapSettings) -> list[_Swing]:
    h, l = _high_col(df), _low_col(df)
    # Hotfix 29.5.0e-1: use numpy windows instead of pandas Series slicing.
    # The first 29.5.0e runner was correct but too slow on 5k-row historical
    # replays because each snapshot rebuilt swings with thousands of pandas
    # iloc slices.  Small numpy slices keep the calculation deterministic and
    # make the report suitable for local CLI use.
    high = pd.to_numeric(df[h], errors="coerce").to_numpy(dtype="float64", copy=False)
    low = pd.to_numeric(df[l], errors="coerce").to_numpy(dtype="float64", copy=False)
    left = settings.swing_left
    right = settings.swing_right
    n = len(df)
    raw: list[tuple[int, str, float]] = []
    # Only swings with right-side confirmation inside the already-known window.
    if n < left + right + 1:
        return []
    for i in range(left, n - right):
        hi = float(high[i])
        lo = float(low[i])
        if not math.isfinite(hi) or not math.isfinite(lo):
            continue
        high_window = high[i - left : i + right + 1]
        low_window = low[i - left : i + right + 1]
        if high_window.size == left + right + 1 and hi >= float(np.nanmax(high_window)):
            raw.append((i, "H", hi))
        if low_window.size == left + right + 1 and lo <= float(np.nanmin(low_window)):
            raw.append((i, "L", lo))

    # De-duplicate consecutive same-kind pivots by keeping the more extreme one.
    compact: list[tuple[int, str, float]] = []
    for idx, kind, price in sorted(raw, key=lambda x: (x[0], x[1])):
        if compact and compact[-1][1] == kind:
            pidx, pkind, pprice = compact[-1]
            if (kind == "H" and price >= pprice) or (kind == "L" and price <= pprice):
                compact[-1] = (idx, kind, price)
            continue
        compact.append((idx, kind, price))

    highs: list[tuple[int, float, str]] = []
    lows: list[tuple[int, float, str]] = []
    out: list[_Swing] = []
    for idx, kind, price in compact:
        if kind == "H":
            prev = highs[-1][1] if highs else None
            label = "H" if prev is None else ("HH" if price > prev else "LH")
            highs.append((idx, price, label))
        else:
            prev = lows[-1][1] if lows else None
            label = "L" if prev is None else ("HL" if price > prev else "LL")
            lows.append((idx, price, label))
        out.append(_Swing(idx=idx, kind=kind, price=float(price), label=label))
    return out


def _last_by_label(swings: list[_Swing], label: str) -> float:
    for s in reversed(swings):
        if s.label == label:
            return round(s.price, 8)
    return 0.0


def _last_swing(swings: list[_Swing], kind: str) -> _Swing | None:
    for s in reversed(swings):
        if s.kind == kind:
            return s
    return None


def _previous_swing(swings: list[_Swing], kind: str, before_idx: int) -> _Swing | None:
    prev = [s for s in swings if s.kind == kind and s.idx < before_idx]
    return prev[-1] if prev else None


def _near(a: float, b: float, tol_pct: float) -> bool:
    ref = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / ref <= tol_pct


def _recent_equal_level(swings: list[_Swing], kind: str, settings: MarketStructureMapSettings) -> tuple[bool, float, int]:
    items = [s for s in swings if s.kind == kind][-settings.recent_swing_lookback :]
    if len(items) < 2:
        return False, 0.0, 0
    best_level = 0.0
    best_count = 0
    for s in items:
        cluster = [x for x in items if _near(x.price, s.price, settings.equal_level_tolerance_pct)]
        if len(cluster) > best_count:
            best_count = len(cluster)
            best_level = float(mean([x.price for x in cluster]))
    return best_count >= 2, round(best_level, 8), int(best_count)


def _structure_bias(swings: list[_Swing]) -> tuple[str, str]:
    recent = [s.label for s in swings if s.label in {"HH", "HL", "LH", "LL"}][-6:]
    hh_hl = sum(1 for x in recent if x in {"HH", "HL"})
    lh_ll = sum(1 for x in recent if x in {"LH", "LL"})
    if hh_hl >= 4 and hh_hl > lh_ll:
        return "BULLISH", "UPTREND"
    if lh_ll >= 4 and lh_ll > hh_hl:
        return "BEARISH", "DOWNTREND"
    if recent and recent[-1] in {"HH", "HL"} and hh_hl > lh_ll:
        return "BULLISH_WEAK", "UPTREND_WEAK"
    if recent and recent[-1] in {"LH", "LL"} and lh_ll > hh_hl:
        return "BEARISH_WEAK", "DOWNTREND_WEAK"
    return "RANGING", "RANGE"


def _price_location(close: float, demand_low: float, demand_high: float, supply_low: float, supply_high: float, range_pos: float) -> str:
    if demand_low > 0 and demand_low <= close <= demand_high:
        return "IN_DEMAND_ZONE"
    if supply_low > 0 and supply_low <= close <= supply_high:
        return "IN_SUPPLY_ZONE"
    if range_pos <= 0.25:
        return "LOW_RANGE_NEAR_DEMAND"
    if range_pos >= 0.75:
        return "HIGH_RANGE_NEAR_SUPPLY"
    if 0.40 <= range_pos <= 0.60:
        return "MID_RANGE"
    if range_pos < 0.40:
        return "LOWER_RANGE"
    return "UPPER_RANGE"


def _body_ratio(row: pd.Series, df: pd.DataFrame) -> float:
    o, h, l, c = _open_col(df), _high_col(df), _low_col(df), _close_col(df)
    open_ = _safe_float(row.get(o), 0.0)
    high = _safe_float(row.get(h), 0.0)
    low = _safe_float(row.get(l), 0.0)
    close = _safe_float(row.get(c), 0.0)
    rng = max(1e-12, high - low)
    return max(0.0, min(1.0, abs(close - open_) / rng))


def evaluate_market_structure_map(
    df: pd.DataFrame,
    *,
    symbol: str = "",
    settings: MarketStructureMapSettings | None = None,
) -> MarketStructureMapResult:
    """Evaluate the current causal market-structure map from a dataframe."""
    settings = settings or MarketStructureMapSettings.from_config()
    if df is None or df.empty:
        return MarketStructureMapResult(
            symbol=symbol,
            price=0.0,
            price_location="NO_DATA",
            structure_bias="UNKNOWN",
            trend_state="UNKNOWN",
            swing_sequence=(),
            last_HH=0.0,
            last_HL=0.0,
            last_LH=0.0,
            last_LL=0.0,
            equal_highs=False,
            equal_lows=False,
            liquidity_above_highs=False,
            liquidity_below_lows=False,
            nearest_liquidity={},
            demand_zone_low=0.0,
            demand_zone_high=0.0,
            supply_zone_low=0.0,
            supply_zone_high=0.0,
            in_demand_zone=False,
            in_supply_zone=False,
            bos_bullish=False,
            bos_bearish=False,
            choch_bullish=False,
            choch_bearish=False,
            mss_bullish=False,
            mss_bearish=False,
            breakout_retest_confirmed=False,
            breakdown_retest_confirmed=False,
            failed_retest=False,
            confirmation_close=False,
            missing_confirmation=("no_data",),
            confirmation_summary="NO_DATA",
            map_score=0.0,
            levels={},
            context={"symbol": symbol},
        )

    work = _add_minimal_features(_normalize_ohlcv(df, symbol))
    o, h, l, c = _open_col(work), _high_col(work), _low_col(work), _close_col(work)
    row = work.iloc[-1]
    prev = work.iloc[-2] if len(work) >= 2 else row
    close = _safe_float(row.get(c), 0.0)
    high = _safe_float(row.get(h), close)
    low = _safe_float(row.get(l), close)
    prev_close = _safe_float(prev.get(c), close)
    atr = max(_safe_float(row.get("atr"), close * 0.002 if close else 0.0), close * 0.0005 if close else 1e-8, 1e-8)
    range_pos = max(0.0, min(1.0, _safe_float(row.get("range_pos_400"), 0.5)))

    swings = _confirmed_swings(work, settings)
    sequence = tuple(s.label for s in swings[-10:])
    bias, trend_state = _structure_bias(swings)
    last_high = _last_swing(swings, "H")
    last_low = _last_swing(swings, "L")
    previous_high = _previous_swing(swings, "H", last_high.idx if last_high else len(work))
    previous_low = _previous_swing(swings, "L", last_low.idx if last_low else len(work))

    equal_highs, eq_high_level, eq_high_count = _recent_equal_level(swings, "H", settings)
    equal_lows, eq_low_level, eq_low_count = _recent_equal_level(swings, "L", settings)

    last_high_price = last_high.price if last_high else 0.0
    last_low_price = last_low.price if last_low else 0.0
    prev_high_price = previous_high.price if previous_high else 0.0
    prev_low_price = previous_low.price if previous_low else 0.0

    demand_low = demand_high = supply_low = supply_high = 0.0
    if last_low:
        pivot = work.iloc[last_low.idx]
        po = _safe_float(pivot.get(o), last_low.price)
        pc = _safe_float(pivot.get(c), last_low.price)
        demand_low = round(min(last_low.price, po, pc), 8)
        demand_high = round(max(po, pc, last_low.price + settings.zone_atr_mult * atr), 8)
    if last_high:
        pivot = work.iloc[last_high.idx]
        po = _safe_float(pivot.get(o), last_high.price)
        pc = _safe_float(pivot.get(c), last_high.price)
        supply_high = round(max(last_high.price, po, pc), 8)
        supply_low = round(min(po, pc, last_high.price - settings.zone_atr_mult * atr), 8)

    in_demand = bool(demand_low > 0 and demand_low <= close <= demand_high)
    in_supply = bool(supply_low > 0 and supply_low <= close <= supply_high)
    location = _price_location(close, demand_low, demand_high, supply_low, supply_high, range_pos)

    # Liquidity pools: equal-level pools have priority, otherwise recent swing levels.
    high_pool = eq_high_level if equal_highs else last_high_price
    low_pool = eq_low_level if equal_lows else last_low_price
    liquidity_above = bool(high_pool > close and (high_pool - close) / max(close, 1e-12) <= settings.liquidity_near_pct)
    liquidity_below = bool(low_pool > 0 and low_pool < close and (close - low_pool) / max(close, 1e-12) <= settings.liquidity_near_pct)
    dist_above = (high_pool - close) / max(close, 1e-12) if high_pool > close else 999.0
    dist_below = (close - low_pool) / max(close, 1e-12) if low_pool > 0 and low_pool < close else 999.0
    if dist_above <= dist_below:
        nearest_liq = {"side": "ABOVE", "level": round(high_pool, 8), "distance_pct": round(dist_above * 100.0, 5), "equal_pool": bool(equal_highs)}
    else:
        nearest_liq = {"side": "BELOW", "level": round(low_pool, 8), "distance_pct": round(dist_below * 100.0, 5), "equal_pool": bool(equal_lows)}

    buffer = settings.confirmation_close_buffer_pct
    bos_bullish = bool(last_high_price > 0 and prev_close <= last_high_price and close > last_high_price * (1.0 + buffer))
    bos_bearish = bool(last_low_price > 0 and prev_close >= last_low_price and close < last_low_price * (1.0 - buffer))
    choch_bullish = bool(bos_bullish and bias.startswith("BEARISH"))
    choch_bearish = bool(bos_bearish and bias.startswith("BULLISH"))

    swept_low_reclaim = bool(low_pool > 0 and low < low_pool * (1.0 - buffer) and close > low_pool)
    swept_high_reject = bool(high_pool > 0 and high > high_pool * (1.0 + buffer) and close < high_pool)
    mss_bullish = bool(swept_low_reclaim and (choch_bullish or close > prev_close))
    mss_bearish = bool(swept_high_reject and (choch_bearish or close < prev_close))

    retest_tol = settings.retest_tolerance_pct
    breakout_retest = bool(last_high_price > 0 and low <= last_high_price * (1.0 + retest_tol) and close > last_high_price * (1.0 + buffer))
    breakdown_retest = bool(last_low_price > 0 and high >= last_low_price * (1.0 - retest_tol) and close < last_low_price * (1.0 - buffer))
    failed_retest = bool(
        (last_high_price > 0 and high >= last_high_price * (1.0 - retest_tol) and close < last_high_price and not bos_bullish)
        or (last_low_price > 0 and low <= last_low_price * (1.0 + retest_tol) and close > last_low_price and not bos_bearish)
    )
    strong_body = _body_ratio(row, work) >= settings.confirmation_body_ratio
    confirmation_close = bool(strong_body and (bos_bullish or bos_bearish or mss_bullish or mss_bearish or breakout_retest or breakdown_retest))

    missing: list[str] = []
    if not swings:
        missing.append("confirmed_swings")
    if not confirmation_close:
        missing.append("confirmation_close")
    if not (bos_bullish or bos_bearish or choch_bullish or choch_bearish or mss_bullish or mss_bearish):
        missing.append("structure_break_or_shift")
    if not (liquidity_above or liquidity_below or swept_low_reclaim or swept_high_reject):
        missing.append("nearby_liquidity_or_sweep")

    score = 0.0
    if swings:
        score += 20.0
    if equal_highs or equal_lows:
        score += 10.0
    if liquidity_above or liquidity_below:
        score += 15.0
    if in_demand or in_supply:
        score += 15.0
    if bos_bullish or bos_bearish:
        score += 15.0
    if choch_bullish or choch_bearish:
        score += 10.0
    if mss_bullish or mss_bearish:
        score += 15.0
    if confirmation_close:
        score += 20.0
    score = round(min(100.0, score), 4)

    if mss_bullish:
        summary = "BULLISH_MSS_AFTER_LIQUIDITY_RECLAIM"
    elif mss_bearish:
        summary = "BEARISH_MSS_AFTER_LIQUIDITY_REJECTION"
    elif choch_bullish:
        summary = "BULLISH_CHOCH"
    elif choch_bearish:
        summary = "BEARISH_CHOCH"
    elif bos_bullish:
        summary = "BULLISH_BOS"
    elif bos_bearish:
        summary = "BEARISH_BOS"
    elif in_demand:
        summary = "PRICE_IN_DEMAND_WAIT_CONFIRMATION"
    elif in_supply:
        summary = "PRICE_IN_SUPPLY_WAIT_CONFIRMATION"
    elif liquidity_above or liquidity_below:
        summary = "NEAR_LIQUIDITY_WAIT_REACTION"
    else:
        summary = "NO_STRUCTURAL_CONFIRMATION"

    return MarketStructureMapResult(
        symbol=symbol,
        price=round(close, 8),
        price_location=location,
        structure_bias=bias,
        trend_state=trend_state,
        swing_sequence=sequence,
        last_HH=_last_by_label(swings, "HH"),
        last_HL=_last_by_label(swings, "HL"),
        last_LH=_last_by_label(swings, "LH"),
        last_LL=_last_by_label(swings, "LL"),
        equal_highs=bool(equal_highs),
        equal_lows=bool(equal_lows),
        liquidity_above_highs=liquidity_above,
        liquidity_below_lows=liquidity_below,
        nearest_liquidity=nearest_liq,
        demand_zone_low=demand_low,
        demand_zone_high=demand_high,
        supply_zone_low=supply_low,
        supply_zone_high=supply_high,
        in_demand_zone=in_demand,
        in_supply_zone=in_supply,
        bos_bullish=bos_bullish,
        bos_bearish=bos_bearish,
        choch_bullish=choch_bullish,
        choch_bearish=choch_bearish,
        mss_bullish=mss_bullish,
        mss_bearish=mss_bearish,
        breakout_retest_confirmed=breakout_retest,
        breakdown_retest_confirmed=breakdown_retest,
        failed_retest=failed_retest,
        confirmation_close=confirmation_close,
        missing_confirmation=tuple(missing),
        confirmation_summary=summary,
        map_score=score,
        levels={
            "last_swing_high": round(last_high_price, 8),
            "previous_swing_high": round(prev_high_price, 8),
            "last_swing_low": round(last_low_price, 8),
            "previous_swing_low": round(prev_low_price, 8),
            "equal_high_level": round(eq_high_level, 8),
            "equal_low_level": round(eq_low_level, 8),
            "liquidity_above_level": round(high_pool, 8),
            "liquidity_below_level": round(low_pool, 8),
        },
        context={
            "swing_count": len(swings),
            "equal_high_count": eq_high_count,
            "equal_low_count": eq_low_count,
            "range_pos_400": round(range_pos, 8),
            "atr": round(atr, 8),
            "body_ratio": round(_body_ratio(row, work), 8),
            "swept_low_reclaim": swept_low_reclaim,
            "swept_high_reject": swept_high_reject,
            "settings": {
                "swing_left": settings.swing_left,
                "swing_right": settings.swing_right,
                "equal_level_tolerance_pct": settings.equal_level_tolerance_pct,
                "liquidity_near_pct": settings.liquidity_near_pct,
                "retest_tolerance_pct": settings.retest_tolerance_pct,
            },
        },
    )


def build_market_structure_map_diagnostic(
    *,
    symbol: str,
    df: pd.DataFrame,
    cycle_id: str = "",
    candle_ts: str = "",
    scenario_diagnostic: dict[str, Any] | None = None,
    pattern_diagnostic: dict[str, Any] | None = None,
    signal_diagnostic: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = evaluate_market_structure_map(df, symbol=symbol)
    payload = result.to_dict()
    return {
        "event_type": EVENT_TYPE,
        "cycle_id": cycle_id,
        "symbol": symbol,
        "ts": utc_now_iso(),
        "candle_ts": candle_ts,
        "price": payload.get("price"),
        "price_location": payload.get("price_location"),
        "structure_bias": payload.get("structure_bias"),
        "trend_state": payload.get("trend_state"),
        "swing_sequence": payload.get("swing_sequence"),
        "equal_highs": payload.get("equal_highs"),
        "equal_lows": payload.get("equal_lows"),
        "liquidity_above_highs": payload.get("liquidity_above_highs"),
        "liquidity_below_lows": payload.get("liquidity_below_lows"),
        "nearest_liquidity": payload.get("nearest_liquidity"),
        "demand_zone_low": payload.get("demand_zone_low"),
        "demand_zone_high": payload.get("demand_zone_high"),
        "supply_zone_low": payload.get("supply_zone_low"),
        "supply_zone_high": payload.get("supply_zone_high"),
        "in_demand_zone": payload.get("in_demand_zone"),
        "in_supply_zone": payload.get("in_supply_zone"),
        "bos_bullish": payload.get("bos_bullish"),
        "bos_bearish": payload.get("bos_bearish"),
        "choch_bullish": payload.get("choch_bullish"),
        "choch_bearish": payload.get("choch_bearish"),
        "mss_bullish": payload.get("mss_bullish"),
        "mss_bearish": payload.get("mss_bearish"),
        "breakout_retest_confirmed": payload.get("breakout_retest_confirmed"),
        "breakdown_retest_confirmed": payload.get("breakdown_retest_confirmed"),
        "failed_retest": payload.get("failed_retest"),
        "confirmation_close": payload.get("confirmation_close"),
        "missing_confirmation": payload.get("missing_confirmation"),
        "confirmation_summary": payload.get("confirmation_summary"),
        "map_score": payload.get("map_score"),
        "levels": payload.get("levels"),
        "context": payload.get("context"),
        "scenario": (scenario_diagnostic or {}).get("scenario"),
        "scenario_directional_bias": (scenario_diagnostic or {}).get("directional_bias"),
        "candlestick_patterns": (pattern_diagnostic or {}).get("patterns"),
        "candlestick_bias": (pattern_diagnostic or {}).get("pattern_bias"),
        "diagnostic_filter": (signal_diagnostic or {}).get("dominant_filter"),
        "confidence_snapshot": confidence or {},
        "diagnostic_only": True,
        "strategy_changed": False,
        "operational_unlock_allowed": False,
    }


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


def _runtime_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [e for e in events if _event_type(e) == EVENT_TYPE]
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_symbol[str(row.get("symbol") or "UNKNOWN")].append(row)
    asset_summary = {}
    for symbol, asset_rows in sorted(by_symbol.items()):
        asset_summary[symbol] = _summarize_result_rows(asset_rows, latest=asset_rows[-1] if asset_rows else {})
    return {
        "rows": len(rows),
        "symbols": len(by_symbol),
        "by_symbol": asset_summary,
        "recent": rows[-10:],
    }


def _bool_count(rows: list[dict[str, Any]], key: str) -> int:
    return sum(1 for r in rows if bool(r.get(key)))


def _summarize_result_rows(rows: list[dict[str, Any]], *, latest: dict[str, Any] | None = None) -> dict[str, Any]:
    latest = latest or (rows[-1] if rows else {})
    return {
        "rows": len(rows),
        "structure_bias": dict(Counter(str(r.get("structure_bias") or "UNKNOWN") for r in rows)),
        "price_location": dict(Counter(str(r.get("price_location") or "UNKNOWN") for r in rows)),
        "confirmation_summary": dict(Counter(str(r.get("confirmation_summary") or "UNKNOWN") for r in rows)),
        "bos_bullish": _bool_count(rows, "bos_bullish"),
        "bos_bearish": _bool_count(rows, "bos_bearish"),
        "choch_bullish": _bool_count(rows, "choch_bullish"),
        "choch_bearish": _bool_count(rows, "choch_bearish"),
        "mss_bullish": _bool_count(rows, "mss_bullish"),
        "mss_bearish": _bool_count(rows, "mss_bearish"),
        "equal_highs": _bool_count(rows, "equal_highs"),
        "equal_lows": _bool_count(rows, "equal_lows"),
        "liquidity_above_highs": _bool_count(rows, "liquidity_above_highs"),
        "liquidity_below_lows": _bool_count(rows, "liquidity_below_lows"),
        "in_demand_zone": _bool_count(rows, "in_demand_zone"),
        "in_supply_zone": _bool_count(rows, "in_supply_zone"),
        "confirmation_close": _bool_count(rows, "confirmation_close"),
        "failed_retest": _bool_count(rows, "failed_retest"),
        "map_score_distribution": _metrics([_safe_float(r.get("map_score"), 0.0) for r in rows]),
        "latest": latest,
    }


def _historical_map(data_dir: Path, settings: MarketStructureMapSettings) -> dict[str, Any]:
    if not settings.historical_enabled:
        return {"enabled": False, "status": "DISABLED", "warnings": ["historical map disabled"]}

    warnings: list[str] = []
    by_asset: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    total_rows_loaded = 0
    for symbol in settings.symbols:
        cache_path = _cache_path_for_symbol(data_dir, symbol, settings.timeframe)
        if cache_path is None:
            warnings.append(f"missing_cache:{symbol}")
            by_asset[symbol] = {"status": "MISSING_CACHE", "rows_loaded": 0, "snapshots_evaluated": 0}
            continue
        try:
            raw = _read_cache(cache_path)
            df = _normalize_ohlcv(raw, symbol)
            if len(df) > settings.max_rows_per_asset:
                df = df.tail(settings.max_rows_per_asset).reset_index(drop=True)
            df = _add_minimal_features(df)
        except Exception as exc:
            warnings.append(f"cache_read_or_prepare_failed:{symbol}:{exc.__class__.__name__}:{exc}")
            by_asset[symbol] = {"status": "READ_ERROR", "error": str(exc), "cache_path": str(cache_path), "rows_loaded": 0, "snapshots_evaluated": 0}
            continue

        total_rows_loaded += len(df)
        start = max(settings.min_warmup_rows, settings.swing_left + settings.swing_right + 5)
        end = len(df)
        asset_rows: list[dict[str, Any]] = []
        if end > start:
            idxs = list(range(start, end, settings.eval_stride))
            # Keep the historical map representative but bounded.  This is a
            # diagnostics report, not an exhaustive backtest; 29.5.0f will do
            # the calibrated candidate-level review.
            if len(idxs) > settings.max_snapshots_per_asset:
                step = max(1, math.ceil(len(idxs) / settings.max_snapshots_per_asset))
                idxs = idxs[::step][-settings.max_snapshots_per_asset:]
            for idx in idxs:
                try:
                    window_start = max(0, idx + 1 - settings.evaluation_window_rows)
                    window = df.iloc[window_start : idx + 1].reset_index(drop=True)
                    result = evaluate_market_structure_map(window, symbol=symbol, settings=settings)
                    d = result.to_dict()
                    d["idx"] = int(idx)
                    d["window_start_idx"] = int(window_start)
                    d["evaluation_window_rows"] = int(len(window))
                    d["datetime"] = str(df.iloc[idx].get("datetime", idx))
                    asset_rows.append(d)
                    all_rows.append(d)
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    if len(warnings) < 50:
                        warnings.append(f"eval_failed:{symbol}:{idx}:{exc.__class__.__name__}:{exc}")
                    continue
        latest_window = df.tail(settings.evaluation_window_rows).reset_index(drop=True) if len(df) else df
        latest = evaluate_market_structure_map(latest_window, symbol=symbol, settings=settings).to_dict() if len(df) else {}
        by_asset[symbol] = {
            "status": "PASS" if asset_rows else "WARN",
            "cache_path": str(cache_path),
            "rows_loaded": len(df),
            "snapshots_evaluated": len(asset_rows),
            **_summarize_result_rows(asset_rows, latest=latest),
        }

    status = "PASS" if any((v.get("status") == "PASS") for v in by_asset.values() if isinstance(v, dict)) else "WARN"
    return {
        "enabled": True,
        "status": status,
        "settings": {
            "symbols": list(settings.symbols),
            "timeframe": settings.timeframe,
            "max_rows_per_asset": settings.max_rows_per_asset,
            "min_warmup_rows": settings.min_warmup_rows,
            "eval_stride": settings.eval_stride,
            "max_snapshots_per_asset": settings.max_snapshots_per_asset,
            "evaluation_window_rows": settings.evaluation_window_rows,
            "swing_left": settings.swing_left,
            "swing_right": settings.swing_right,
            "equal_level_tolerance_pct": settings.equal_level_tolerance_pct,
            "liquidity_near_pct": settings.liquidity_near_pct,
            "zone_atr_mult": settings.zone_atr_mult,
            "retest_tolerance_pct": settings.retest_tolerance_pct,
        },
        "rows_loaded": total_rows_loaded,
        "snapshots_evaluated": len(all_rows),
        "summary": _summarize_result_rows(all_rows, latest={}),
        "by_asset": by_asset,
        "warnings": warnings[:50],
    }


def _decision(runtime: dict[str, Any], historical: dict[str, Any], settings: MarketStructureMapSettings) -> dict[str, Any]:
    focus = settings.focus_symbol
    focus_latest = {}
    if isinstance(historical.get("by_asset"), dict):
        focus_latest = (((historical.get("by_asset") or {}).get(focus) or {}).get("latest") or {})
    if not focus_latest and isinstance(runtime.get("by_symbol"), dict):
        focus_latest = (((runtime.get("by_symbol") or {}).get(focus) or {}).get("latest") or {})

    status = "STRUCTURE_MAP_READY_DIAGNOSTIC" if historical.get("status") == "PASS" or runtime.get("rows", 0) else "NO_STRUCTURE_DATA"
    if historical.get("status") == "WARN" and not runtime.get("rows", 0):
        status = "STRUCTURE_MAP_PARTIAL_WARN"
    return {
        "status": status,
        "operational_unlock_allowed": False,
        "candidate_use": "DIAGNOSTIC_ONLY_FOR_29_5_0F_SHADOW_REVIEW",
        "focus_symbol": focus,
        "focus_latest": {
            "price_location": focus_latest.get("price_location", "NA"),
            "structure_bias": focus_latest.get("structure_bias", "NA"),
            "confirmation_summary": focus_latest.get("confirmation_summary", "NA"),
            "nearest_liquidity": focus_latest.get("nearest_liquidity", {}),
            "demand_zone": [focus_latest.get("demand_zone_low", 0.0), focus_latest.get("demand_zone_high", 0.0)],
            "supply_zone": [focus_latest.get("supply_zone_low", 0.0), focus_latest.get("supply_zone_high", 0.0)],
            "missing_confirmation": focus_latest.get("missing_confirmation", []),
            "map_score": focus_latest.get("map_score", 0.0),
        },
        "next_patch": "29.5.0f calibrated scenario-pattern-structure shadow review",
        "reason": "structure map is diagnostic-only; it must be validated against scenario/pattern candidates before any paper unlock refinement",
    }


def build_market_structure_map_report(data_dir: str | Path = "data", settings: MarketStructureMapSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or MarketStructureMapSettings.from_config()
    events = _read_events(base / "paper_events.jsonl")
    runtime = _runtime_summary(events)
    historical = _historical_map(base, settings)
    orders_submitted = sum(1 for e in events if _event_type(e) in {"PAPER_ORDER_SUBMITTED", "PAPER_ORDER_CONFIRMED", "ORDER_FILLED", "PAPER_ORDER_FILLED"})
    positions_opened = sum(1 for e in events if _event_type(e) in {"POSITION_OPENED", "PAPER_POSITION_OPENED"})
    decision = _decision(runtime, historical, settings)
    status = "PASS" if decision.get("status") == "STRUCTURE_MAP_READY_DIAGNOSTIC" else "WARN"
    report = {
        "prompt": PROMPT_ID,
        "hotfix": "29.5.0e-1",
        "generated_at": utc_now_iso(),
        "status": status,
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "files": {"events": str(base / "paper_events.jsonl"), "report": str(base / REPORT_NAME)},
        "counts": {
            "runtime_structure_rows": runtime.get("rows", 0),
            "historical_snapshots_evaluated": historical.get("snapshots_evaluated", 0) if isinstance(historical, dict) else 0,
            "historical_rows_loaded": historical.get("rows_loaded", 0) if isinstance(historical, dict) else 0,
            "orders_submitted": orders_submitted,
            "positions_opened": positions_opened,
        },
        "decision": decision,
        "runtime": runtime,
        "historical_map": historical,
        "feature_contract": {
            "equal_highs": "recent confirmed swing-high cluster within tolerance",
            "equal_lows": "recent confirmed swing-low cluster within tolerance",
            "liquidity_above_highs": "nearby high/equal-high pool above current price",
            "liquidity_below_lows": "nearby low/equal-low pool below current price",
            "supply_demand_zones": "zones projected from latest confirmed swing pivot and ATR/body area",
            "bos": "close beyond latest confirmed swing high/low with buffer",
            "choch": "BOS against prior dominant structure bias",
            "mss": "liquidity sweep/reclaim or rejection plus directional shift",
            "confirmation_close": "strong body close confirming BOS/CHOCH/MSS/retest condition",
        },
        "safety": {
            "no_live": True,
            "no_testnet": True,
            "no_orders": True,
            "no_threshold_changes": True,
            "paper_unlock_unchanged": True,
        },
    }
    return report


def write_market_structure_map_report(data_dir: str | Path = "data") -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_market_structure_map_report(base)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "EVENT_TYPE",
    "REPORT_NAME",
    "MarketStructureMapResult",
    "MarketStructureMapSettings",
    "evaluate_market_structure_map",
    "build_market_structure_map_diagnostic",
    "build_market_structure_map_report",
    "write_market_structure_map_report",
]
