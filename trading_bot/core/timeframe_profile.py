"""Timeframe-aware backtest configuration utilities.

Prompt 28.8: allow the same research pipeline to be run on 15m, 5m and 3m
without silently using 15m assumptions for embargo, validation, cache size or
cost diagnostics.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, asdict
from typing import Iterable


SUPPORTED_TIMEFRAMES = {"15m", "5m", "3m"}


@dataclass(frozen=True)
class TimeframeProfile:
    timeframe: str
    minutes: int
    requested_rows: int
    approx_days: float
    wf_train_size: int
    wf_test_size: int
    wf_label_horizon: int
    embargo_gap: int
    expected_timeframe_minutes: int
    cost_stress_multiplier: float
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


def timeframe_to_minutes(timeframe: str) -> int:
    tf = str(timeframe).strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("d"):
        return int(tf[:-1]) * 1440
    raise ValueError(f"Unsupported timeframe: {timeframe!r}")


def normalize_timeframe(timeframe: str) -> str:
    tf = str(timeframe).strip().lower()
    if tf not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported backtest timeframe {timeframe!r}. Supported: {sorted(SUPPORTED_TIMEFRAMES)}")
    return tf


def rows_for_days(days: float, timeframe: str) -> int:
    minutes = timeframe_to_minutes(timeframe)
    return int(math.ceil(float(days) * 1440.0 / float(minutes)))


def equivalent_rows_from_baseline_rows(rows: int, *, baseline_timeframe: str, target_timeframe: str) -> int:
    baseline_minutes = timeframe_to_minutes(baseline_timeframe)
    target_minutes = timeframe_to_minutes(target_timeframe)
    return int(math.ceil(int(rows) * float(baseline_minutes) / float(target_minutes)))


def _env_was_set(name: str) -> bool:
    return name in os.environ and str(os.environ[name]).strip() != ""


def build_timeframe_profile(
    *,
    config,
    timeframe: str,
    requested_rows: int,
    days: float | None = None,
    scale_from_15m: bool = True,
) -> TimeframeProfile:
    tf = normalize_timeframe(timeframe)
    minutes = timeframe_to_minutes(tf)
    warnings: list[str] = []

    if days is not None:
        requested_rows = rows_for_days(float(days), tf)
    requested_rows = int(max(1, requested_rows))
    approx_days = requested_rows * minutes / 1440.0

    # Keep the same real-time train/test/embargo span when moving from 15m to 5m/3m.
    # Environment variables remain authoritative for explicit research sweeps.
    scale = 15.0 / float(minutes) if scale_from_15m else 1.0
    wf_train = int(round(int(getattr(config, "WF_TRAIN_SIZE", 2000)) * scale))
    wf_test = int(round(int(getattr(config, "WF_TEST_SIZE", 500)) * scale))
    wf_label = int(round(int(getattr(config, "WF_LABEL_HORIZON", 100)) * scale))
    embargo = int(round(int(getattr(config, "EMBARGO_GAP", 100)) * scale))

    if _env_was_set("WF_TRAIN_SIZE"):
        wf_train = int(os.environ["WF_TRAIN_SIZE"])
    if _env_was_set("WF_TEST_SIZE"):
        wf_test = int(os.environ["WF_TEST_SIZE"])
    if _env_was_set("WF_LABEL_HORIZON"):
        wf_label = int(os.environ["WF_LABEL_HORIZON"])
    if _env_was_set("EMBARGO_GAP"):
        embargo = int(os.environ["EMBARGO_GAP"])

    # Lower timeframes are more execution-sensitive.  The multiplier is exposed
    # in the audit/report; it does not override explicit user env stress factors.
    if tf == "15m":
        cost_stress = 1.0
    elif tf == "5m":
        cost_stress = float(getattr(config, "TIMEFRAME_COST_STRESS_5M", 1.25))
    else:  # 3m
        cost_stress = float(getattr(config, "TIMEFRAME_COST_STRESS_3M", 1.60))

    if requested_rows < wf_train + embargo + wf_test:
        warnings.append(
            "requested_rows smaller than one full scaled WF window; adaptive WF may be used or validation may be weak"
        )

    return TimeframeProfile(
        timeframe=tf,
        minutes=minutes,
        requested_rows=requested_rows,
        approx_days=approx_days,
        wf_train_size=max(1, wf_train),
        wf_test_size=max(1, wf_test),
        wf_label_horizon=max(1, wf_label),
        embargo_gap=max(1, embargo),
        expected_timeframe_minutes=minutes,
        cost_stress_multiplier=cost_stress,
        warnings=tuple(warnings),
    )


def apply_timeframe_profile(config, profile: TimeframeProfile) -> None:
    """Mutate Config class attributes for a single research run."""
    config.TIMEFRAME = profile.timeframe
    config.EXPECTED_TIMEFRAME_MINUTES = profile.expected_timeframe_minutes
    config.WF_TRAIN_SIZE = profile.wf_train_size
    config.WF_TEST_SIZE = profile.wf_test_size
    config.WF_LABEL_HORIZON = profile.wf_label_horizon
    config.EMBARGO_GAP = profile.embargo_gap
    config.ACTIVE_TIMEFRAME_PROFILE = profile.to_dict()

    # Apply friction stress only when the user did not explicitly choose values.
    if getattr(config, "TIMEFRAME_COST_STRESS_ENABLED", True):
        if not _env_was_set("SLIPPAGE_SPREAD_FACTOR"):
            config.SLIPPAGE_SPREAD_FACTOR = float(getattr(config, "SLIPPAGE_SPREAD_FACTOR", 1.0)) * profile.cost_stress_multiplier
        if not _env_was_set("SLIPPAGE_ATR_FACTOR"):
            config.SLIPPAGE_ATR_FACTOR = float(getattr(config, "SLIPPAGE_ATR_FACTOR", 1.0)) * profile.cost_stress_multiplier


    # Prompt 28.8.1: 5m is the first timeframe with higher throughput.  Relax
    # only the positive RANGING_MEAN_REVERSION path slightly; keep all other
    # archetype thresholds unchanged unless the user overrides via env.
    if profile.timeframe == "5m":
        if not _env_was_set("SETUP_MR_MIN_PROB"):
            config.SETUP_MR_MIN_PROB = float(getattr(config, "SETUP_5M_MR_MIN_PROB", 52.0))
        if not _env_was_set("SETUP_MR_MIN_NET_EDGE_R"):
            config.SETUP_MR_MIN_NET_EDGE_R = float(getattr(config, "SETUP_5M_MR_MIN_NET_EDGE_R", 0.15))


def parse_timeframe_list(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        raw = [v.strip() for v in value.split(",")]
    else:
        raw = [str(v).strip() for v in value]
    out: list[str] = []
    for item in raw:
        if not item:
            continue
        out.append(normalize_timeframe(item))
    if not out:
        raise ValueError("No valid timeframe supplied")
    return out
