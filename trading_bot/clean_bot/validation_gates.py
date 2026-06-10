"""validation_gates.py — Deterministic validation gates for clean_bot backtests.

TR-INT-05 implements M9-M15 from integration_phase1_report.md §7B.

VALIDATION_CONFIG is an immutable MappingProxyType with no os.environ reads.
All gate functions are pure; no global mutable state is written.
"""
from __future__ import annotations

import math
import types
from collections import defaultdict
from dataclasses import asdict, replace as _dc_replace
from datetime import datetime
from typing import Any

import pandas as pd

from .backtest import run_backtest_frame
from .models import BacktestSettings
from .strategies import Strategy, default_strategies


# ---------------------------------------------------------------------------
# M9: Immutable validation configuration — independent of .env
# ---------------------------------------------------------------------------

VALIDATION_CONFIG: types.MappingProxyType = types.MappingProxyType({
    "warmup_bars": 401,               # matches run_backtest_frame start index
    "oos_split_ratio": 0.3,           # last 30% of dataset is OOS
    "min_oos_trades": 50,             # economic gate: minimum trades required
    "min_pf": 1.0,                    # profit factor must be strictly > this
    "min_net_pnl": 0.0,              # net P&L must be strictly > this
    "temporal_conc_max_pct": 50.0,    # worst week ≤ 50% of abs(total P&L)
    "temporal_min_weeks": 3,          # gate requires ≥ 3 distinct ISO weeks
    "cost_scenario": "conservative",  # UCM scenario used in cost runs
    "risk_per_trade_pct": 0.005,      # fixed risk (§0 baseline)
})


# ---------------------------------------------------------------------------
# Panel validation configuration (Edge Research 03 — 4h/1d multi-symbol panel)
#
# Low-frequency strategies cannot reach 50 OOS trades per symbol: the trade
# count is pooled across ALL panel symbols. Temporal concentration uses
# monthly buckets (ISO weeks are too granular for 1d holding periods).
# VALIDATION_CONFIG above is intentionally untouched.
# ---------------------------------------------------------------------------

PANEL_VALIDATION_CONFIG: types.MappingProxyType = types.MappingProxyType({
    "min_oos_trades_panel": 50,       # pooled across all panel symbols
    "min_pf": 1.0,                    # pooled profit factor strictly > this
    "min_net_pnl": 0.0,               # pooled net P&L strictly > this
    "temporal_conc_max_pct": 50.0,    # worst month ≤ 50% of abs(total P&L)
    "temporal_bucket": "month",
    "temporal_min_buckets": 3,        # gate requires ≥ 3 distinct months
    "warmup_bars_by_timeframe": types.MappingProxyType({"4h": 401, "1d": 260}),
    "cost_scenario": "conservative",  # unchanged policy
    "risk_per_trade_pct": 0.005,      # unchanged policy
    "min_positive_regimes": 2,        # net pnl > 0 in ≥ 2 of bull/bear/sideways
})


# ---------------------------------------------------------------------------
# M10: OOS warmup with explicit no-lookahead guarantee
# ---------------------------------------------------------------------------

def oos_with_warmup(
    df: pd.DataFrame,
    *,
    warmup_bars: int | None = None,
    oos_split_ratio: float | None = None,
) -> tuple[pd.DataFrame, int]:
    """Create an OOS slice with a no-lookahead warmup prefix.

    Split logic
    -----------
    split = int(n * (1 - oos_split_ratio))
    warmup rows  = df[max(0, split - warmup_bars) : split]  (from train)
    true OOS     = df[split:]
    returned df  = concat(warmup_rows, true_OOS), index reset to 0

    No-lookahead guarantee: warmup rows come exclusively from the train portion;
    no OOS row is ever seen during the train/selection phase.  The backtest
    starts firing signals at idx=warmup_bars which equals the train/OOS boundary
    (when warmup_bars == VALIDATION_CONFIG['warmup_bars'] == 401).

    Returns
    -------
    (oos_df, warmup_count)
        oos_df       : DataFrame starting with warmup rows then true OOS.
        warmup_count : number of leading warmup rows; oos_df[warmup_count:] is
                       the true untouched OOS.
    """
    if warmup_bars is None:
        warmup_bars = int(VALIDATION_CONFIG["warmup_bars"])
    if oos_split_ratio is None:
        oos_split_ratio = float(VALIDATION_CONFIG["oos_split_ratio"])

    n = len(df)
    split = int(n * (1.0 - oos_split_ratio))
    warmup_start = max(0, split - warmup_bars)
    actual_warmup = split - warmup_start

    oos_df = df.iloc[warmup_start:].reset_index(drop=True)
    return oos_df, actual_warmup


# ---------------------------------------------------------------------------
# M11: Full no-cost re-run via UnifiedCostModel scenario="zero"
# ---------------------------------------------------------------------------

def run_without_costs(
    *,
    df: pd.DataFrame,
    settings: BacktestSettings,
    strategies: list[Strategy] | None = None,
    raw_rows: int | None = None,
) -> dict[str, Any]:
    """M11: Full backtest re-run with zero costs via UnifiedCostModel scenario="zero".

    Runs the identical code path as run_backtest_frame() with cost_model="zero"
    so every UCM call returns zero cost. This is a full re-run from scratch —
    NOT post-hoc cost removal. The delta between a cost run and this result is
    the exact cost drag.
    """
    zero_settings = _dc_replace(settings, cost_model="zero")
    result = run_backtest_frame(
        raw_rows=raw_rows or len(df),
        df=df,
        settings=zero_settings,
        strategies=strategies or default_strategies(),
    )
    result["_zero_cost"] = True
    result["report_type"] = "clean_bot_backtest_no_cost"
    result["metrics"]["total_cost"] = 0.0
    for trade in result.get("trades", []):
        trade["_zero_cost"] = True
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(ts: Any) -> datetime | None:
    try:
        result = pd.to_datetime(str(ts), utc=True)
        return result.to_pydatetime()
    except Exception:
        return None


def _week_key(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _month_key(dt: datetime) -> str:
    return f"{dt.year}-{dt.month:02d}"


# ---------------------------------------------------------------------------
# M12: Temporal concentration gate
# ---------------------------------------------------------------------------

def temporal_concentration_check(
    trades: list[dict[str, Any]],
    *,
    max_worst_week_pct: float | None = None,
    min_weeks: int | None = None,
    bucket: str = "week",
) -> dict[str, Any]:
    """M12: Flag anomalous P&L concentration in a single time bucket.

    bucket="week" (default, ISO weeks) preserves the original M12 behavior.
    bucket="month" is used by the panel gates (4h/1d trades make ISO weeks
    too granular). With bucket="month" the legacy *_week* output keys carry
    the monthly values; the "bucket" key states the granularity.

    A bucket accounting for > max_worst_week_pct% of abs(total P&L) is an
    anomaly. The gate requires >= min_weeks distinct buckets to run.

    Uses entry_time from trade dicts (falls back to exit_time).

    Returns
    -------
    dict with: passes, reason, bucket, n_weeks, worst_week_pct,
    max_worst_week_pct, min_weeks, weekly (sorted list of bucket summaries).
    """
    if bucket not in ("week", "month"):
        raise ValueError(f"Unknown temporal bucket {bucket!r}: must be 'week' or 'month'.")
    key_fn = _week_key if bucket == "week" else _month_key

    if max_worst_week_pct is None:
        max_worst_week_pct = float(VALIDATION_CONFIG["temporal_conc_max_pct"])
    if min_weeks is None:
        min_weeks = int(VALIDATION_CONFIG["temporal_min_weeks"])

    base: dict[str, Any] = {
        "max_worst_week_pct": max_worst_week_pct,
        "min_weeks": min_weeks,
        "bucket": bucket,
    }

    if not trades:
        return {**base, "passes": False, "reason": "no_trades", "n_weeks": 0,
                "worst_week_pct": 0.0, "weekly": []}

    week_pnl: dict[str, float] = defaultdict(float)
    for t in trades:
        pnl = float(t.get("net_pnl", 0.0))
        dt = _parse_dt(t.get("entry_time") or t.get("exit_time"))
        if dt is None:
            continue
        week_pnl[key_fn(dt)] += pnl

    if not week_pnl:
        return {**base, "passes": False, "reason": "no_parseable_timestamps",
                "n_weeks": 0, "worst_week_pct": 0.0, "weekly": []}

    n_weeks = len(week_pnl)
    abs_total = sum(abs(v) for v in week_pnl.values())

    if abs_total <= 0.0:
        return {**base, "passes": False, "reason": "zero_abs_total_pnl",
                "n_weeks": n_weeks, "worst_week_pct": 0.0, "weekly": []}

    weekly = sorted(
        [
            {
                "week": w,
                "pnl": round(v, 8),
                "abs_pct": round(abs(v) / abs_total * 100.0, 4),
            }
            for w, v in week_pnl.items()
        ],
        key=lambda x: x["week"],
    )

    worst_week_pct = max(x["abs_pct"] for x in weekly)

    if n_weeks < min_weeks:
        passes = False
        reason = f"insufficient_weeks: {n_weeks} < {min_weeks}"
    elif worst_week_pct > max_worst_week_pct:
        passes = False
        reason = f"worst_week_pct={worst_week_pct:.2f} > threshold={max_worst_week_pct:.1f}"
    else:
        passes = True
        reason = "ok"

    return {
        **base,
        "passes": passes,
        "reason": reason,
        "n_weeks": n_weeks,
        "worst_week_pct": round(worst_week_pct, 4),
        "weekly": weekly,
    }


# ---------------------------------------------------------------------------
# M13: Economic gate (adapted for clean_bot, not copied from botClaude)
# ---------------------------------------------------------------------------

def is_promising(
    metrics: dict[str, Any],
    trades: list[dict[str, Any]] | None = None,
    *,
    temporal_check: bool = True,
) -> tuple[bool, dict[str, Any]]:
    """M13: Post-cost economic acceptance gate for clean_bot OOS results.

    Criteria (adapted — not a direct copy of botClaude is_promising):
    - profit_factor  strictly > min_pf  (1.0)
    - net_pnl        strictly > min_net_pnl  (0.0)
    - closed_trades  >= min_oos_trades  (50)
    - temporal concentration passes  (when trades provided and temporal_check=True)

    Returns (passes: bool, checks: dict)
    """
    pf_raw = metrics.get("profit_factor")
    try:
        pf_val = float(pf_raw) if pf_raw is not None else 0.0
        if not math.isfinite(pf_val):
            pf_val = 0.0
    except (TypeError, ValueError):
        pf_val = 0.0

    net_pnl = float(metrics.get("net_pnl") or 0.0)
    n_trades = int(metrics.get("closed_trades") or 0)

    min_pf = float(VALIDATION_CONFIG["min_pf"])
    min_trades = int(VALIDATION_CONFIG["min_oos_trades"])
    min_net_pnl = float(VALIDATION_CONFIG["min_net_pnl"])

    checks: dict[str, Any] = {
        "pf_ok": pf_val > min_pf,
        "pf_val": round(pf_val, 6),
        "min_pf": min_pf,
        "pnl_ok": net_pnl > min_net_pnl,
        "net_pnl": round(net_pnl, 8),
        "min_net_pnl": min_net_pnl,
        "trades_ok": n_trades >= min_trades,
        "n_trades": n_trades,
        "min_trades": min_trades,
    }

    if temporal_check and trades:
        tc = temporal_concentration_check(trades)
        checks["temporal_ok"] = tc["passes"]
        checks["temporal_detail"] = tc
    else:
        checks["temporal_ok"] = True

    passes = bool(
        checks["pf_ok"] and checks["pnl_ok"] and checks["trades_ok"] and checks["temporal_ok"]
    )
    checks["passes"] = passes
    return passes, checks


# ---------------------------------------------------------------------------
# Dataset date range — correct report timestamps from actual data (M15 support)
# ---------------------------------------------------------------------------

def dataset_date_range(df: pd.DataFrame) -> dict[str, str]:
    """Extract actual start and end timestamps from the dataset's datetime column.

    Returns {"start": str, "end": str}; both empty if column absent or empty.
    Dates come from the data, never from hardcoded defaults.
    """
    if "datetime" not in df.columns or len(df) == 0:
        return {"start": "", "end": ""}
    dts = pd.to_datetime(df["datetime"], utc=True, errors="coerce").dropna()
    if dts.empty:
        return {"start": "", "end": ""}
    return {
        "start": str(dts.min()),
        "end": str(dts.max()),
    }


# ---------------------------------------------------------------------------
# M15: Main deterministic validation entry point
# ---------------------------------------------------------------------------

def run_validation(
    *,
    df: pd.DataFrame,
    settings: BacktestSettings | None = None,
    strategies: list[Strategy] | None = None,
) -> dict[str, Any]:
    """Run deterministic validation on a prepared OHLCV DataFrame.

    Determinism guarantee: same df + same settings → identical output.
    No random state, no time-based seeds, no .env reads.

    Steps
    -----
    1. Split into OOS with warmup (no-lookahead).
    2. Run cost backtest on OOS (UCM).
    3. Run no-cost backtest on same OOS (full re-run, not post-hoc).
    4. Temporal concentration gate on cost run trades.
    5. Economic gate on cost run metrics.
    6. Record dataset and OOS date ranges from actual timestamps.
    7. Emit edge_demonstrated decision.

    Returns
    -------
    dict with keys: report_type, config, dataset_date_range, oos_date_range,
    warmup_bars, oos_rows, cost_run, nocost_run, temporal_concentration,
    economic_gate, edge_demonstrated.
    """
    if settings is None:
        settings = BacktestSettings(
            risk_per_trade_pct=float(VALIDATION_CONFIG["risk_per_trade_pct"]),
            cost_model=str(VALIDATION_CONFIG["cost_scenario"]),
        )
    strategies = strategies or default_strategies()

    oos_df, warmup_count = oos_with_warmup(df)
    true_oos_df = oos_df.iloc[warmup_count:] if warmup_count < len(oos_df) else oos_df

    date_range = dataset_date_range(df)
    oos_date_range = dataset_date_range(true_oos_df)

    cost_result = run_backtest_frame(
        raw_rows=len(df),
        df=oos_df,
        settings=settings,
        strategies=strategies,
    )
    nocost_result = run_without_costs(
        df=oos_df,
        settings=settings,
        strategies=strategies,
        raw_rows=len(df),
    )

    cost_trades = cost_result.get("trades", [])
    cost_metrics = cost_result.get("metrics", {})
    promising, gate_checks = is_promising(cost_metrics, cost_trades)
    tc = temporal_concentration_check(cost_trades)

    return {
        "report_type": "clean_bot_validation_gates",
        "diagnostic_only": True,
        "opens_orders": False,
        "config": dict(VALIDATION_CONFIG),
        "dataset_date_range": date_range,
        "oos_date_range": oos_date_range,
        "warmup_bars": warmup_count,
        "oos_rows": len(oos_df) - warmup_count,
        "cost_run": {
            "metrics": cost_metrics,
            "n_trades": len(cost_trades),
        },
        "nocost_run": {
            "metrics": nocost_result["metrics"],
            "n_trades": len(nocost_result["trades"]),
        },
        "temporal_concentration": tc,
        "economic_gate": {
            "promising": promising,
            "checks": gate_checks,
        },
        "edge_demonstrated": bool(promising and tc["passes"]),
    }


# ---------------------------------------------------------------------------
# Panel gates (Edge Research 03) — additive; per-symbol gates above untouched
# ---------------------------------------------------------------------------

def is_promising_panel(
    per_symbol_results: dict[str, dict[str, Any]],
    *,
    config: types.MappingProxyType = PANEL_VALIDATION_CONFIG,
) -> tuple[bool, dict[str, Any]]:
    """Economic acceptance gate for a multi-symbol panel run (4h/1d research).

    per_symbol_results maps symbol -> {"trades": [trade dicts...]}. Trades are
    POOLED across all symbols before evaluation: low-frequency strategies
    cannot reach the trade-count gate per symbol, but the panel as a whole must.

    Criteria (pooled):
    - closed trades >= min_oos_trades_panel (50)
    - profit factor strictly > min_pf (1.0)
    - net pnl strictly > min_net_pnl (0.0)
    - temporal concentration with monthly buckets passes

    Returns (passes: bool, checks: dict) in the same style as is_promising().
    """
    if not isinstance(per_symbol_results, dict) or not per_symbol_results:
        return False, {"passes": False, "reason": "no_per_symbol_results"}

    pooled: list[dict[str, Any]] = []
    per_symbol_counts: dict[str, int] = {}
    for symbol, result in per_symbol_results.items():
        trades = (result or {}).get("trades")
        if trades is None:
            raise ValueError(
                f"per_symbol_results[{symbol!r}] has no 'trades' key; "
                f"pass an explicit (possibly empty) trade list."
            )
        per_symbol_counts[str(symbol)] = len(trades)
        pooled.extend(trades)

    net_pnl = sum(float(t.get("net_pnl", 0.0)) for t in pooled)
    gross_profit = sum(max(0.0, float(t.get("net_pnl", 0.0))) for t in pooled)
    gross_loss = sum(abs(min(0.0, float(t.get("net_pnl", 0.0)))) for t in pooled)
    pf_val = (gross_profit / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    min_pf = float(config["min_pf"])
    min_trades = int(config["min_oos_trades_panel"])
    min_net_pnl = float(config["min_net_pnl"])

    tc = temporal_concentration_check(
        pooled,
        max_worst_week_pct=float(config["temporal_conc_max_pct"]),
        min_weeks=int(config["temporal_min_buckets"]),
        bucket=str(config["temporal_bucket"]),
    )

    checks: dict[str, Any] = {
        "pf_ok": pf_val > min_pf,
        "pf_val": round(pf_val, 6) if math.isfinite(pf_val) else pf_val,
        "min_pf": min_pf,
        "pnl_ok": net_pnl > min_net_pnl,
        "net_pnl": round(net_pnl, 8),
        "min_net_pnl": min_net_pnl,
        "trades_ok": len(pooled) >= min_trades,
        "n_trades": len(pooled),
        "min_trades": min_trades,
        "per_symbol_trades": per_symbol_counts,
        "temporal_ok": tc["passes"],
        "temporal_detail": tc,
    }
    passes = bool(
        checks["pf_ok"] and checks["pnl_ok"] and checks["trades_ok"] and checks["temporal_ok"]
    )
    checks["passes"] = passes
    return passes, checks


def regime_stratified_check(
    trades: list[dict[str, Any]],
    regime_by_time: "pd.Series | None",
    *,
    min_positive_regimes: int | None = None,
) -> dict[str, Any]:
    """Require pooled net pnl > 0 in >= min_positive_regimes distinct regimes.

    regime_by_time: pd.Series with a sorted tz-aware DatetimeIndex and regime
    labels as values (e.g. "bull"/"bear"/"sideways" — the labeling series comes
    from the cycle-2 regime logic). Each trade's entry_time is mapped to the
    latest label at or before it (backward as-of).

    Fail-closed: missing labels, no trades, or any unlabelable trade fails the
    check with an explicit reason — never a silent pass.
    """
    if min_positive_regimes is None:
        min_positive_regimes = int(PANEL_VALIDATION_CONFIG["min_positive_regimes"])

    base: dict[str, Any] = {"min_positive_regimes": min_positive_regimes}

    if regime_by_time is None or len(regime_by_time) == 0:
        return {**base, "passes": False, "reason": "no_regime_labels",
                "regime_pnl": {}, "n_positive_regimes": 0}
    if not trades:
        return {**base, "passes": False, "reason": "no_trades",
                "regime_pnl": {}, "n_positive_regimes": 0}

    labels = regime_by_time.copy()
    idx = pd.to_datetime(labels.index, utc=True)
    if not idx.is_monotonic_increasing:
        raise ValueError("regime_by_time index must be sorted ascending")
    labels.index = idx

    regime_pnl: dict[str, float] = defaultdict(float)
    unlabeled = 0
    for t in trades:
        dt = _parse_dt(t.get("entry_time") or t.get("exit_time"))
        if dt is None:
            unlabeled += 1
            continue
        pos = labels.index.searchsorted(pd.Timestamp(dt), side="right") - 1
        if pos < 0:
            unlabeled += 1
            continue
        regime_pnl[str(labels.iloc[pos])] += float(t.get("net_pnl", 0.0))

    result_pnl = {k: round(v, 8) for k, v in sorted(regime_pnl.items())}
    n_positive = sum(1 for v in regime_pnl.values() if v > 0.0)

    if unlabeled > 0:
        return {**base, "passes": False, "reason": f"unlabeled_trades: {unlabeled}",
                "regime_pnl": result_pnl, "n_positive_regimes": n_positive}

    passes = n_positive >= min_positive_regimes
    reason = "ok" if passes else (
        f"positive_regimes={n_positive} < required={min_positive_regimes}"
    )
    return {**base, "passes": passes, "reason": reason,
            "regime_pnl": result_pnl, "n_positive_regimes": n_positive}


def panel_oos_with_warmup(
    df: pd.DataFrame,
    *,
    timeframe: str,
    declared_max_lookback_bars: int,
    oos_split_ratio: float | None = None,
    warmup_buffer_bars: int = 20,
) -> tuple[pd.DataFrame, int]:
    """OOS split for panel research with a strategy-aware warmup. Fail-closed.

    warmup = max(warmup_bars_by_timeframe[timeframe],
                 declared_max_lookback_bars + warmup_buffer_bars)

    declared_max_lookback_bars is MANDATORY and must be positive: on 1d the
    silent 401-bar default of oos_with_warmup() (~1.3 years) could undersize
    or oversize the warmup relative to the declared strategy lookback. The
    caller must align the backtest start index with the returned warmup_count.
    """
    tf = str(timeframe or "").lower().strip()
    warmup_by_tf = PANEL_VALIDATION_CONFIG["warmup_bars_by_timeframe"]
    if tf not in warmup_by_tf:
        raise ValueError(
            f"Unsupported panel timeframe {timeframe!r}: must be one of "
            f"{sorted(warmup_by_tf)}."
        )
    if declared_max_lookback_bars is None or int(declared_max_lookback_bars) <= 0:
        raise ValueError(
            "declared_max_lookback_bars is required and must be > 0 "
            "(no silent warmup default for panel research)."
        )

    warmup = max(
        int(warmup_by_tf[tf]),
        int(declared_max_lookback_bars) + int(warmup_buffer_bars),
    )
    return oos_with_warmup(df, warmup_bars=warmup, oos_split_ratio=oos_split_ratio)
