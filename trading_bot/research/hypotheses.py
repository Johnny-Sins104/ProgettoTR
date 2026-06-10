"""STRAT-02 hypothesis families and the full declared configuration grids.

Exactly three families, max 12 configurations each. Every configuration is
declared here — with its economic rationale — BEFORE any validation run.
Adding a configuration after looking at validation results is forbidden;
every configuration in these grids is logged as a trial whether or not it
looks promising.

Families
--------
VB  Volatility breakout (15m signal, causal 5m execution)
    Premise: after volatility compression, stop-driven order flow produces
    range expansion; closing breaks of multi-day extremes with above-average
    volume mark the start of impulse moves that an ATR trailing stop can
    ride. Symmetric long/short.

TP  Trend pullback (15m)
    Premise: in an established trend (EMA stack), pullbacks to a dynamic
    mean get absorbed by trend participants; entering on the reclaim buys
    the trend at a discount with a tight invalidation, so the payoff is
    asymmetric. Symmetric long/short.

XS  Cross-sectional momentum (relative selection across the 5 assets)
    Premise: relative-strength persistence among correlated crypto majors
    (Moskowitz-Ooi-Pedersen momentum literature): recent relative winners
    keep outperforming relative losers over horizons of days. Implemented
    as periodic rebalances holding the top-ranked asset (optionally short
    the bottom-ranked), with a disaster stop.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .edge_lab import (
    BARS_5M_PER_DAY,
    BARS_15M_PER_DAY,
    CausalExecutor,
    DirectionalSignalSpec,
    TradeEvent,
    config_hash,
)


# ---------------------------------------------------------------------------
# Config containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HypothesisConfig:
    config_id: str
    family: str
    params: Dict[str, Any]
    rationale: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["config_hash"] = config_hash({"family": self.family, **self.params})
        return d


# ---------------------------------------------------------------------------
# Family VB — volatility breakout (12 configs)
# ---------------------------------------------------------------------------

_VB_RATIONALE = (
    "Breakout of the prior {days}-day extreme on a closed 15m candle with "
    "volume confirmation (volume_ratio_20 >= 1.2){squeeze}. Stop "
    "{stop}xATR15, ATR trailing {trail}xATR15 to ride expansion; max hold "
    "6 days. Economic basis: stop-run/expansion after {regime}."
)


def vb_configs() -> List[HypothesisConfig]:
    out: List[HypothesisConfig] = []
    i = 0
    for days, lookback in ((1, 96), (2, 192), (3, 288)):
        for squeeze_pmax in (0.5, 1.0):
            for stop_mult, trail_mult in ((2.0, 4.0), (3.0, 6.0)):
                i += 1
                squeeze_txt = (
                    " and 1-day ATR%-rank <= 0.5 (volatility compression)"
                    if squeeze_pmax < 1.0
                    else ""
                )
                out.append(
                    HypothesisConfig(
                        config_id=f"VB{i:02d}",
                        family="volatility_breakout",
                        params={
                            "lookback_bars_15m": lookback,
                            "squeeze_pmax": squeeze_pmax,
                            "volume_min": 1.2,
                            "stop_atr_mult": stop_mult,
                            "trail_atr_mult": trail_mult,
                            "max_hold_days": 6,
                        },
                        rationale=_VB_RATIONALE.format(
                            days=days,
                            squeeze=squeeze_txt,
                            stop=stop_mult,
                            trail=trail_mult,
                            regime=(
                                "compression" if squeeze_pmax < 1.0 else "any regime"
                            ),
                        ),
                    )
                )
    assert len(out) == 12
    return out


def vb_specs(df15: pd.DataFrame, cfg: HypothesisConfig) -> List[DirectionalSignalSpec]:
    p = cfg.params
    n = p["lookback_bars_15m"]
    close = df15["Close"].to_numpy(float)
    ph = df15[f"prior_high_{n}"].to_numpy(float)
    pl = df15[f"prior_low_{n}"].to_numpy(float)
    vol = df15["volume_ratio_20"].to_numpy(float)
    rank = df15["atr_pct_rank_96"].to_numpy(float)
    atr = df15["atr14"].to_numpy(float)

    base = (vol >= p["volume_min"]) & (atr > 0) & ~np.isnan(rank)
    if p["squeeze_pmax"] < 1.0:
        base = base & (rank <= p["squeeze_pmax"])
    long_m = base & ~np.isnan(ph) & (close > ph)
    short_m = base & ~np.isnan(pl) & (close < pl)

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
# Family TP — trend pullback (12 configs)
# ---------------------------------------------------------------------------

_TP_RATIONALE = (
    "15m trend defined by EMA stack (close vs ema200 and ema50 vs ema200); "
    "entry when price pulls back to {ref} (band 0.2%) and closes back on the "
    "trend side with RSI in the neutral band. Stop {stop}xATR15, fixed "
    "target {rr}R, max hold 2 days. Economic basis: trend participants "
    "absorb pullbacks at the dynamic mean, giving tight-invalidation "
    "asymmetric entries."
)


def tp_configs() -> List[HypothesisConfig]:
    out: List[HypothesisConfig] = []
    i = 0
    for ref in ("ema20", "ema50"):
        for stop_mult in (1.5, 2.5):
            for rr in (1.5, 2.0, 3.0):
                i += 1
                out.append(
                    HypothesisConfig(
                        config_id=f"TP{i:02d}",
                        family="trend_pullback",
                        params={
                            "ref_ema": ref,
                            "stop_atr_mult": stop_mult,
                            "target_rr": rr,
                            "rsi_long": (40.0, 65.0),
                            "rsi_short": (35.0, 60.0),
                            "band_pct": 0.002,
                            "max_hold_days": 2,
                        },
                        rationale=_TP_RATIONALE.format(ref=ref, stop=stop_mult, rr=rr),
                    )
                )
    assert len(out) == 12
    return out


def tp_specs(df15: pd.DataFrame, cfg: HypothesisConfig) -> List[DirectionalSignalSpec]:
    p = cfg.params
    close = df15["Close"].to_numpy(float)
    low = df15["Low"].to_numpy(float)
    high = df15["High"].to_numpy(float)
    ema50 = df15["ema50"].to_numpy(float)
    ema200 = df15["ema200"].to_numpy(float)
    ref = df15[p["ref_ema"]].to_numpy(float)
    rsi = df15["rsi14"].to_numpy(float)
    atr = df15["atr14"].to_numpy(float)
    band = p["band_pct"]

    valid = (atr > 0) & (ema200 > 0) & ~np.isnan(rsi)
    lo_rsi_l, hi_rsi_l = p["rsi_long"]
    lo_rsi_s, hi_rsi_s = p["rsi_short"]
    long_m = (
        valid
        & (close > ema200) & (ema50 > ema200)
        & (low <= ref * (1 + band)) & (close > ref)
        & (rsi >= lo_rsi_l) & (rsi <= hi_rsi_l)
    )
    short_m = (
        valid
        & (close < ema200) & (ema50 < ema200)
        & (high >= ref * (1 - band)) & (close < ref)
        & (rsi >= lo_rsi_s) & (rsi <= hi_rsi_s)
    )

    hold = p["max_hold_days"] * BARS_5M_PER_DAY
    specs: List[DirectionalSignalSpec] = []
    for idx in np.flatnonzero(long_m):
        specs.append(
            DirectionalSignalSpec(
                idx15=int(idx), side="BUY",
                stop_atr_mult=p["stop_atr_mult"], exit_style="fixed_rr",
                rr=p["target_rr"], max_hold_bars_5m=hold,
            )
        )
    for idx in np.flatnonzero(short_m):
        specs.append(
            DirectionalSignalSpec(
                idx15=int(idx), side="SELL",
                stop_atr_mult=p["stop_atr_mult"], exit_style="fixed_rr",
                rr=p["target_rr"], max_hold_bars_5m=hold,
            )
        )
    return specs


# ---------------------------------------------------------------------------
# Family XS — cross-sectional momentum (12 configs)
# ---------------------------------------------------------------------------

_XS_RATIONALE = (
    "Every {hold} day(s) rank the 5 assets by their past {form}-day return "
    "on closed 15m candles; hold the top-ranked asset long{short_leg} for "
    "{hold} day(s) with a 2.5xATR15 disaster stop. Economic basis: "
    "cross-sectional momentum persistence among correlated crypto majors "
    "(relative flows chase recent winners)."
)


def xs_configs() -> List[HypothesisConfig]:
    out: List[HypothesisConfig] = []
    i = 0
    for form_days in (3, 7, 14):
        for hold_days in (1, 3):
            for mode in ("long_short", "long_only"):
                i += 1
                out.append(
                    HypothesisConfig(
                        config_id=f"XS{i:02d}",
                        family="xs_momentum",
                        params={
                            "formation_days": form_days,
                            "hold_days": hold_days,
                            "mode": mode,
                            "stop_atr_mult": 2.5,
                        },
                        rationale=_XS_RATIONALE.format(
                            form=form_days,
                            hold=hold_days,
                            short_leg=(
                                " and the bottom-ranked short"
                                if mode == "long_short"
                                else ""
                            ),
                        ),
                    )
                )
    assert len(out) == 12
    return out


def xs_events(
    frames15: Dict[str, pd.DataFrame],
    executors: Dict[str, CausalExecutor],
    cfg: HypothesisConfig,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> List[TradeEvent]:
    """Generate XS momentum trades across the 5-asset panel.

    Rebalance times are 00:00 UTC every hold_days; ranking uses the last
    CLOSED 15m candle before/at the rebalance time (causal).
    """
    p = cfg.params
    form_col = f"ret_{p['formation_days']}d"
    hold_bars = p["hold_days"] * BARS_5M_PER_DAY

    # asset -> (datetimes ns array, formation return array)
    panel: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for asset, df in frames15.items():
        panel[asset] = (
            df["datetime"].to_numpy(dtype="datetime64[ns]"),
            df[form_col].to_numpy(float),
        )

    start = window_start.ceil("D")
    rebalances = pd.date_range(start, window_end, freq=f"{p['hold_days']}D", tz="UTC")

    events: List[TradeEvent] = []
    for rb in rebalances:
        rb64 = np.datetime64(rb.tz_convert("UTC").tz_localize(None))
        scores: Dict[str, Tuple[int, float]] = {}
        for asset, (times, rets) in panel.items():
            # last 15m bar whose CLOSE (open + 15min) is <= rebalance time
            j = int(np.searchsorted(times, rb64 - np.timedelta64(15, "m"), side="right")) - 1
            if j < 0:
                continue
            r = rets[j]
            if np.isnan(r):
                continue
            scores[asset] = (j, float(r))
        if len(scores) < len(panel):
            continue  # require the full panel for a fair ranking

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
            evs = executors[asset].run(
                [spec],
                family=cfg.family,
                config_id=cfg.config_id,
                asset=asset,
                window_start=window_start,
                window_end=window_end,
            )
            events.extend(evs)
    return sorted(events, key=lambda e: e.entry_time)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def all_configs() -> List[HypothesisConfig]:
    return vb_configs() + tp_configs() + xs_configs()


def specs_for(
    cfg: HypothesisConfig, df15: pd.DataFrame
) -> List[DirectionalSignalSpec]:
    if cfg.family == "volatility_breakout":
        return vb_specs(df15, cfg)
    if cfg.family == "trend_pullback":
        return tp_specs(df15, cfg)
    raise ValueError(f"{cfg.family} is not a per-asset directional family")
