"""families.py — Strategy-family scaffolds for Edge Research 03.

Two families, both emitting clean_bot Signals so every trade flows through
run_backtest_frame and the UnifiedCostModel unchanged:

TSMOMFamily   Time-series momentum on 4h/1d bars. Signal at idx uses ONLY
              rows <= idx (causal by construction; covered by a
              shift-the-future test).
CarryFamily   Funding carry on perpetuals: enter short when funding is
              persistently positive above an entry threshold (the short
              RECEIVES positive funding). Requires funding_enabled=True
              backtests (clean_bot/funding.py). The funding series is
              injected at construction and consumed causally (only events
              with timestamp <= the current bar's datetime).

Exit style: both families hold to trailing-stop/time exit via the existing
atr_trailing metadata channel of _exit_position. Threshold-decay exits for
the carry family are a panel-runner concern (documented in panel_runner.py);
if they prove necessary, an additive metadata-gated "time_exit_only" path is
the planned fallback — the default backtest path stays untouched.

Configs are frozen dataclasses with fail-closed validation; the grid for each
family is capped at 12 declared configs (declared_trials.py enforces it).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from trading_bot.clean_bot.models import Signal
from trading_bot.clean_bot.strategies import Strategy

_BARS_PER_YEAR = {"4h": 6 * 365, "1d": 365}
_STOP_ATR_MULT = 3.0
_TRAIL_ATR_MULT = 3.0


def _validate_timeframe(timeframe: str) -> None:
    if timeframe not in ("4h", "1d"):
        raise ValueError(
            f"Unsupported family timeframe {timeframe!r}: must be '4h' or '1d'."
        )


@dataclass(frozen=True)
class TSMOMConfig:
    """Grid axes: lookback x vol-target x timeframe (x direction)."""
    lookback_bars: int
    vol_target_ann: float
    timeframe: Literal["4h", "1d"]
    long_short: Literal["long_only", "long_short"] = "long_only"

    def __post_init__(self) -> None:
        _validate_timeframe(self.timeframe)
        if not (10 <= int(self.lookback_bars) <= 1000):
            raise ValueError(
                f"lookback_bars must be in [10, 1000], got {self.lookback_bars!r}."
            )
        if not (0.0 < float(self.vol_target_ann) <= 5.0) or not math.isfinite(
            float(self.vol_target_ann)
        ):
            raise ValueError(
                f"vol_target_ann must be a finite value in (0, 5], got {self.vol_target_ann!r}."
            )
        if self.long_short not in ("long_only", "long_short"):
            raise ValueError(
                f"long_short must be 'long_only' or 'long_short', got {self.long_short!r}."
            )


@dataclass(frozen=True)
class TSMOMFamily(Strategy):
    """Time-series momentum: sign of the lookback return, ATR risk, trailing exit.

    vol_target_ann acts as a volatility filter at the scaffold level (no entry
    when realized annualized vol exceeds 2x the target) and is recorded in the
    signal metadata as target_leverage for the panel runner's vol-targeted
    sizing (post cycle-2 merge).
    """
    config: TSMOMConfig
    name: str = "tsmom"

    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        cfg = self.config
        lb = int(cfg.lookback_bars)
        if idx < lb:
            return None

        row = df.iloc[idx]
        close = float(row["Close"])
        close_then = float(df.iloc[idx - lb]["Close"])
        atr = float(row.get("atr14", 0.0))
        if close <= 0 or close_then <= 0 or atr <= 0:
            return None

        momentum = close / close_then - 1.0

        # Realized vol over the lookback window, annualized by timeframe.
        window = df["Close"].iloc[idx - lb: idx + 1]
        rets = window.pct_change().dropna()
        if len(rets) < 2:
            return None
        vol_bar = float(rets.std())
        if not math.isfinite(vol_bar) or vol_bar <= 0:
            return None
        vol_ann = vol_bar * math.sqrt(_BARS_PER_YEAR[cfg.timeframe])
        if vol_ann > 2.0 * float(cfg.vol_target_ann):
            return None

        if momentum > 0:
            side = "BUY"
        elif momentum < 0 and cfg.long_short == "long_short":
            side = "SELL"
        else:
            return None

        if side == "BUY":
            stop = close - _STOP_ATR_MULT * atr
            if stop <= 0:
                return None
        else:
            stop = close + _STOP_ATR_MULT * atr

        return Signal(
            strategy=self.name,
            side=side,
            score=abs(momentum),
            reason=f"tsmom lb={lb} mom={momentum:.4f} vol_ann={vol_ann:.3f}",
            stop_price=stop,
            take_profit=0.0,  # trailing exit; TP unused in atr_trailing path
            metadata={
                "exit_style": "atr_trailing",
                "trail_atr_mult": _TRAIL_ATR_MULT,
                "max_hold_bars": lb,
                "target_leverage": float(cfg.vol_target_ann) / vol_ann,
                "family": "tsmom",
                "timeframe": cfg.timeframe,
            },
        )


@dataclass(frozen=True)
class CarryConfig:
    """Grid axes: metric x window x thresholds x max_hold x timeframe."""
    metric: Literal["zscore", "percentile"]
    window_events: int
    entry_threshold: float
    exit_threshold: float
    max_hold_bars: int
    timeframe: Literal["4h", "1d"]

    def __post_init__(self) -> None:
        _validate_timeframe(self.timeframe)
        if self.metric not in ("zscore", "percentile"):
            raise ValueError(f"metric must be 'zscore' or 'percentile', got {self.metric!r}.")
        if not (10 <= int(self.window_events) <= 2000):
            raise ValueError(
                f"window_events must be in [10, 2000], got {self.window_events!r}."
            )
        if not math.isfinite(float(self.entry_threshold)) or not math.isfinite(
            float(self.exit_threshold)
        ):
            raise ValueError("entry_threshold and exit_threshold must be finite.")
        if float(self.entry_threshold) <= float(self.exit_threshold):
            raise ValueError(
                f"entry_threshold ({self.entry_threshold!r}) must be strictly greater "
                f"than exit_threshold ({self.exit_threshold!r})."
            )
        if self.metric == "percentile" and not (
            0.0 < float(self.exit_threshold) < float(self.entry_threshold) <= 1.0
        ):
            raise ValueError(
                "percentile thresholds must satisfy 0 < exit < entry <= 1."
            )
        if not (1 <= int(self.max_hold_bars) <= 5000):
            raise ValueError(
                f"max_hold_bars must be in [1, 5000], got {self.max_hold_bars!r}."
            )


@dataclass(frozen=True)
class CarryFamily(Strategy):
    """Funding carry: short the perp when funding is persistently positive.

    The funding series (validated per clean_bot/funding.py) is injected at
    construction. The metric at bar idx is computed CAUSALLY from the last
    window_events funding events with timestamp <= the bar's datetime.
    Entry: metric >= entry_threshold -> SELL (the short receives positive
    funding). Exit: trailing stop / max_hold_bars; exit_threshold is recorded
    in metadata for the panel runner's threshold-decay exit ablation.

    Backtests for this family MUST run with funding_enabled=True, otherwise
    the carry pnl (the point of the trade) is not accounted.
    """
    config: CarryConfig
    funding_df: pd.DataFrame = None  # validated frame: datetime, funding_rate
    name: str = "funding_carry"

    def __post_init__(self) -> None:
        if self.funding_df is None or "datetime" not in self.funding_df.columns \
                or "funding_rate" not in self.funding_df.columns:
            raise ValueError(
                "CarryFamily requires a validated funding_df with "
                "'datetime' and 'funding_rate' columns (see clean_bot/funding.py)."
            )

    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        cfg = self.config
        row = df.iloc[idx]
        bar_time = pd.Timestamp(row["datetime"])
        if bar_time.tzinfo is None:
            bar_time = bar_time.tz_localize("UTC")

        close = float(row["Close"])
        atr = float(row.get("atr14", 0.0))
        if close <= 0 or atr <= 0:
            return None

        # Causal window: only funding events already settled at this bar.
        pos = self.funding_df["datetime"].searchsorted(bar_time, side="right")
        window = self.funding_df["funding_rate"].iloc[max(0, pos - cfg.window_events): pos]
        if len(window) < cfg.window_events:
            return None

        last = float(window.iloc[-1])
        if cfg.metric == "zscore":
            std = float(window.std())
            if not math.isfinite(std) or std <= 0:
                return None
            metric = (last - float(window.mean())) / std
        else:
            metric = float((window <= last).mean())

        if not math.isfinite(metric) or metric < float(cfg.entry_threshold):
            return None

        return Signal(
            strategy=self.name,
            side="SELL",
            score=metric,
            reason=(
                f"carry {cfg.metric}={metric:.3f} >= {cfg.entry_threshold} "
                f"(last_rate={last:.6f})"
            ),
            stop_price=close + _STOP_ATR_MULT * atr,
            take_profit=0.0,  # trailing exit; TP unused in atr_trailing path
            metadata={
                "exit_style": "atr_trailing",
                "trail_atr_mult": _TRAIL_ATR_MULT,
                "max_hold_bars": int(cfg.max_hold_bars),
                "exit_threshold": float(cfg.exit_threshold),
                "family": "funding_carry",
                "timeframe": cfg.timeframe,
                "requires_funding_enabled": True,
            },
        )
