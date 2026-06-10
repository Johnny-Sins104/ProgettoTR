"""Cycle-2 STRAT-02 hypothesis families — declared BEFORE any evaluation.

Four families, max 12 configurations each (48 total). None of these
grids was chosen from cycle-1 rankings: VB and TP are re-declared from
their economic premises for the multi-regime train; XS moves to the
broad point-in-time panel; XSR is the NEW regime-conditioned family
whose filter (trading_bot/research/regime.py) is causal at the signal
bar and is counted as parameters.

Cycle-1 knowledge statement (honesty): the researcher knows cycle 1
ended NO_CANDIDATE for regime dependence. That knowledge motivated the
NEW family (XSR) and the regime-stratified validation gate — both
declared here a priori — but no cycle-2 configuration was selected,
ranked or tuned using cycle-1 validation/OOS metrics. All 36 cycle-1
trials remain counted in the cumulative trial log for DSR.

VB2  Volatility breakout (re-declared)
     Premise unchanged: closing breaks of multi-day extremes with volume
     confirmation mark impulse starts. New axis (declared, economic):
     higher-timeframe EMA alignment — in a multi-regime train, breakouts
     against the EMA50/EMA200 stack are disproportionately fakeouts.

TP2  Trend pullback (re-declared)
     Canonical structure on the new train: EMA-stack trend, pullback to
     a dynamic mean, reclaim entry, fixed-R target.

XS2  Cross-sectional momentum, broad panel
     Same relative-strength premise, now ranked across every panel
     symbol tradable at the rebalance (point-in-time set, min 8) —
     wider breadth is the main statistical fix from cycle 1.

XSR  Regime-conditioned cross-sectional momentum (NEW)
     Premise: long-only relative-strength harvesting is profitable only
     when the market regime supports directional longs; the causal BTC
     SMA200 regime filter gates NEW entries at each rebalance. Long-only
     by construction (a regime gate on a hedged long/short book would
     unbalance it; the directional long leg is what the filter protects).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .edge_lab import (
    BARS_5M_PER_DAY,
    CausalExecutor,
    DirectionalSignalSpec,
    TradeEvent,
)
from .hypotheses import HypothesisConfig, _col
from .regime import regime_at

MIN_PANEL_AVAILABLE = 8


# ---------------------------------------------------------------------------
# VB2 — volatility breakout, re-declared (12)
# ---------------------------------------------------------------------------

def vb2_configs() -> List[HypothesisConfig]:
    out: List[HypothesisConfig] = []
    i = 0
    for days, lookback in ((1, 96), (2, 192), (3, 288)):
        for align in (True, False):
            for stop_mult, trail_mult in ((2.0, 4.0), (3.0, 6.0)):
                i += 1
                out.append(
                    HypothesisConfig(
                        config_id=f"VB2{i:02d}",
                        family="volatility_breakout_c2",
                        params={
                            "lookback_bars_15m": lookback,
                            "ema_alignment": align,
                            "volume_min": 1.2,
                            "stop_atr_mult": stop_mult,
                            "trail_atr_mult": trail_mult,
                            "max_hold_days": 6,
                        },
                        rationale=(
                            f"Break of the prior {days}-day extreme on a closed 15m "
                            f"candle, volume_ratio_20>=1.2"
                            + (
                                ", EMA50/EMA200 stack aligned with the break "
                                "(fakeout filter in mixed regimes)"
                                if align
                                else ", no trend alignment (pure expansion bet)"
                            )
                            + f". Stop {stop_mult}xATR15, trail {trail_mult}xATR15, "
                            "max hold 6d."
                        ),
                    )
                )
    assert len(out) == 12
    return out


def vb2_specs(df15: pd.DataFrame, cfg: HypothesisConfig) -> List[DirectionalSignalSpec]:
    p = cfg.params
    n = p["lookback_bars_15m"]
    close = df15["Close"].to_numpy(float)
    ph = _col(df15, f"prior_high_{n}")
    pl = _col(df15, f"prior_low_{n}")
    vol = _col(df15, "volume_ratio_20")
    atr = _col(df15, "atr14")
    ema50 = _col(df15, "ema50")
    ema200 = _col(df15, "ema200")

    base = (vol >= p["volume_min"]) & (atr > 0)
    long_m = base & ~np.isnan(ph) & (close > ph)
    short_m = base & ~np.isnan(pl) & (close < pl)
    if p["ema_alignment"]:
        long_m &= (ema50 > ema200) & (close > ema200)
        short_m &= (ema50 < ema200) & (close < ema200)

    hold = p["max_hold_days"] * BARS_5M_PER_DAY
    specs: List[DirectionalSignalSpec] = []
    for idx in np.flatnonzero(long_m):
        specs.append(
            DirectionalSignalSpec(
                idx15=int(idx), side="BUY",
                stop_atr_mult=p["stop_atr_mult"], exit_style="atr_trailing",
                trail_atr_mult=p["trail_atr_mult"], max_hold_bars_5m=hold,
            )
        )
    for idx in np.flatnonzero(short_m):
        specs.append(
            DirectionalSignalSpec(
                idx15=int(idx), side="SELL",
                stop_atr_mult=p["stop_atr_mult"], exit_style="atr_trailing",
                trail_atr_mult=p["trail_atr_mult"], max_hold_bars_5m=hold,
            )
        )
    return specs


# ---------------------------------------------------------------------------
# TP2 — trend pullback, re-declared (12)
# ---------------------------------------------------------------------------

def tp2_configs() -> List[HypothesisConfig]:
    out: List[HypothesisConfig] = []
    i = 0
    for ref in ("ema20", "ema50"):
        for stop_mult in (1.5, 2.5):
            for rr in (1.5, 2.0, 3.0):
                i += 1
                out.append(
                    HypothesisConfig(
                        config_id=f"TP2{i:02d}",
                        family="trend_pullback_c2",
                        params={
                            "ref_ema": ref,
                            "stop_atr_mult": stop_mult,
                            "target_rr": rr,
                            "rsi_long": (40.0, 65.0),
                            "rsi_short": (35.0, 60.0),
                            "band_pct": 0.002,
                            "max_hold_days": 2,
                        },
                        rationale=(
                            f"EMA-stack trend, pullback to {ref} (0.2% band), reclaim "
                            f"entry, stop {stop_mult}xATR15, target {rr}R, hold<=2d. "
                            "Re-test of the canonical pullback premise on the "
                            "multi-regime 2019+ train."
                        ),
                    )
                )
    assert len(out) == 12
    return out


# tp2 signal logic identical in structure to cycle 1 (premise unchanged)
from .hypotheses import tp_specs as _tp_specs_impl  # noqa: E402


def tp2_specs(df15: pd.DataFrame, cfg: HypothesisConfig) -> List[DirectionalSignalSpec]:
    return _tp_specs_impl(df15, cfg)


# ---------------------------------------------------------------------------
# XS2 — broad-panel cross-sectional momentum (12)
# ---------------------------------------------------------------------------

def xs2_configs() -> List[HypothesisConfig]:
    out: List[HypothesisConfig] = []
    i = 0
    for form_days in (3, 7, 14):
        for hold_days in (1, 3):
            for mode in ("long_short", "long_only"):
                i += 1
                out.append(
                    HypothesisConfig(
                        config_id=f"XS2{i:02d}",
                        family="xs_momentum_c2",
                        params={
                            "formation_days": form_days,
                            "hold_days": hold_days,
                            "mode": mode,
                            "stop_atr_mult": 2.5,
                            "min_panel": MIN_PANEL_AVAILABLE,
                        },
                        rationale=(
                            f"Every {hold_days}d rank ALL panel symbols tradable at the "
                            f"rebalance (point-in-time set, >= {MIN_PANEL_AVAILABLE}) by "
                            f"{form_days}d return; hold top long"
                            + (" / bottom short" if mode == "long_short" else "")
                            + f" {hold_days}d, 2.5xATR15 disaster stop. Wider breadth "
                            "is the statistical fix over the 5-asset cycle-1 panel."
                        ),
                    )
                )
    assert len(out) == 12
    return out


# ---------------------------------------------------------------------------
# XSR — regime-conditioned XS momentum (NEW, 12)
# ---------------------------------------------------------------------------

def xsr_configs() -> List[HypothesisConfig]:
    out: List[HypothesisConfig] = []
    i = 0
    for form_days in (3, 7, 14):
        for hold_days in (1, 3):
            for regime_rule in ("bull_only", "not_bear"):
                i += 1
                out.append(
                    HypothesisConfig(
                        config_id=f"XSR{i:02d}",
                        family="xs_momentum_regime_c2",
                        params={
                            "formation_days": form_days,
                            "hold_days": hold_days,
                            "mode": "long_only",
                            "regime_rule": regime_rule,
                            "regime_filter": "BTC daily SMA200 trend, causal D-1 (research/regime.py)",
                            "stop_atr_mult": 2.5,
                            "min_panel": MIN_PANEL_AVAILABLE,
                        },
                        rationale=(
                            f"As XS2 long-only ({form_days}d formation, {hold_days}d hold) "
                            f"but NEW entries gated by the causal BTC regime filter "
                            f"({regime_rule}): long relative-strength harvesting only "
                            "works when the market supports directional longs. The "
                            "filter is declared a priori and counted as parameters."
                        ),
                    )
                )
    assert len(out) == 12
    return out


# ---------------------------------------------------------------------------
# Broad-panel XS event generation (used by XS2 and XSR)
# ---------------------------------------------------------------------------

def xs_events_panel(
    frames15: Dict[str, pd.DataFrame],
    executors: Dict[str, CausalExecutor],
    cfg: HypothesisConfig,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
    daily_labels: Optional[pd.Series] = None,
) -> List[TradeEvent]:
    """XS momentum across the point-in-time tradable panel.

    A symbol participates in a rebalance iff it has a closed 15m candle
    and a valid formation return at that time (i.e. it was listed, not
    yet delisted, with enough history). Requires >= min_panel symbols.
    For XSR configs, NEW entries are gated by the causal regime filter.
    """
    p = cfg.params
    form_col = f"ret_{p['formation_days']}d"
    hold_bars = p["hold_days"] * BARS_5M_PER_DAY
    regime_rule = p.get("regime_rule")

    panel: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for asset, df in frames15.items():
        panel[asset] = (
            df["datetime"].to_numpy(dtype="datetime64[ns]"),
            _col(df, form_col),
        )

    start = window_start.ceil("D")
    rebalances = pd.date_range(start, window_end, freq=f"{p['hold_days']}D", tz="UTC")

    events: List[TradeEvent] = []
    for rb in rebalances:
        if regime_rule is not None:
            if daily_labels is None:
                raise ValueError("XSR config requires daily regime labels")
            reg = regime_at(daily_labels, rb)
            if regime_rule == "bull_only" and reg != "bull":
                continue
            if regime_rule == "not_bear" and reg in ("bear", "unknown"):
                continue

        rb64 = np.datetime64(rb.tz_convert("UTC").tz_localize(None))
        scores: Dict[str, Tuple[int, float]] = {}
        for asset, (times, rets) in panel.items():
            j = int(np.searchsorted(times, rb64 - np.timedelta64(15, "m"), side="right")) - 1
            if j < 0:
                continue
            # symbol must be alive: its latest candle no older than 1 hour
            if rb64 - times[j] > np.timedelta64(60, "m"):
                continue
            r = rets[j]
            if np.isnan(r):
                continue
            scores[asset] = (j, float(r))
        if len(scores) < p["min_panel"]:
            continue

        ranked = sorted(scores.items(), key=lambda kv: kv[1][1], reverse=True)
        legs: List[Tuple[str, int, str]] = [(ranked[0][0], ranked[0][1][0], "BUY")]
        if p["mode"] == "long_short":
            legs.append((ranked[-1][0], ranked[-1][1][0], "SELL"))

        for asset, idx15, side in legs:
            spec = DirectionalSignalSpec(
                idx15=idx15, side=side,
                stop_atr_mult=p["stop_atr_mult"], exit_style="time_stop",
                max_hold_bars_5m=hold_bars,
            )
            events.extend(
                executors[asset].run(
                    [spec],
                    family=cfg.family,
                    config_id=cfg.config_id,
                    asset=asset,
                    window_start=window_start,
                    window_end=window_end,
                )
            )
    return sorted(events, key=lambda e: e.entry_time)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def all_c2_configs() -> List[HypothesisConfig]:
    return vb2_configs() + tp2_configs() + xs2_configs() + xsr_configs()


def c2_specs_for(cfg: HypothesisConfig, df15: pd.DataFrame) -> List[DirectionalSignalSpec]:
    if cfg.family == "volatility_breakout_c2":
        return vb2_specs(df15, cfg)
    if cfg.family == "trend_pullback_c2":
        return tp2_specs(df15, cfg)
    raise ValueError(f"{cfg.family} is not a per-asset directional family")


def is_panel_family(cfg: HypothesisConfig) -> bool:
    return cfg.family in ("xs_momentum_c2", "xs_momentum_regime_c2")
