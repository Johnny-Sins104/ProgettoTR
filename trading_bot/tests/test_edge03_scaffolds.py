"""test_edge03_scaffolds.py — Edge Research 03 lab scaffolds.

Covers: declaration registry rules (cap, one-shot, undeclared-run guard,
cumulative numbering from 84), causality of both family signals
(shift-the-future), config fail-closed validation, and runtime isolation
(no runtime module imports research.edge03).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "trading_bot"))

from trading_bot.research.edge03 import declared_trials as dt
from trading_bot.research.edge03.families import (
    CarryConfig,
    CarryFamily,
    TSMOMConfig,
    TSMOMFamily,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    dt._reset_registry_for_tests()
    yield
    dt._reset_registry_for_tests()


def _tsmom_cfg(lookback: int = 50, **kw) -> TSMOMConfig:
    base = dict(lookback_bars=lookback, vol_target_ann=0.5, timeframe="1d")
    base.update(kw)
    return TSMOMConfig(**base)


def _carry_cfg(**kw) -> CarryConfig:
    base = dict(metric="zscore", window_events=30, entry_threshold=1.0,
                exit_threshold=0.0, max_hold_bars=42, timeframe="4h")
    base.update(kw)
    return CarryConfig(**base)


def _bars(n: int = 200, freq: str = "D", trend: float = 0.5) -> pd.DataFrame:
    prices = [100.0 + i * trend for i in range(n)]
    return pd.DataFrame({
        "Open": prices,
        "High": [p + 1.0 for p in prices],
        "Low": [p - 1.0 for p in prices],
        "Close": prices,
        "Volume": [1000.0] * n,
        "atr14": [2.0] * n,
        "atr_pct": [0.5] * n,
        "datetime": pd.date_range("2024-01-01", periods=n, freq=freq, tz="UTC"),
    })


def _funding(n: int = 200, rates=None) -> pd.DataFrame:
    if rates is None:
        rates = [0.0001] * n
    return pd.DataFrame({
        "datetime": pd.date_range("2023-06-01", periods=n, freq="8h", tz="UTC"),
        "symbol": ["BTC/USDT"] * n,
        "funding_rate": rates,
    })


# ---------------------------------------------------------------------------
# Declaration registry
# ---------------------------------------------------------------------------

def test_numbering_starts_at_85(tmp_path: Path) -> None:
    cfgs = tuple(_tsmom_cfg(lookback=20 + i * 10) for i in range(3))
    numbers = dt.declare_trials("tsmom", cfgs, log_path=tmp_path / "log.json")
    assert numbers == [85, 86, 87]
    assert dt.declared_trial_count() == 87


def test_cumulative_numbering_across_families(tmp_path: Path) -> None:
    log = tmp_path / "log.json"
    dt.declare_trials("tsmom", tuple(_tsmom_cfg(lookback=20 + i * 10) for i in range(12)), log_path=log)
    numbers = dt.declare_trials("funding_carry", (_carry_cfg(),), log_path=log)
    assert numbers == [97]
    payload = json.loads(log.read_text())
    assert payload["starting_count"] == 84
    assert payload["cumulative_count"] == 97
    assert [t["trial_number"] for t in payload["trials"]] == list(range(85, 98))


def test_thirteenth_config_raises(tmp_path: Path) -> None:
    cfgs = tuple(_tsmom_cfg(lookback=20 + i * 10) for i in range(13))
    with pytest.raises(ValueError, match="max 12"):
        dt.declare_trials("tsmom", cfgs, log_path=tmp_path / "log.json")


def test_double_declaration_raises(tmp_path: Path) -> None:
    dt.declare_trials("tsmom", (_tsmom_cfg(),), log_path=tmp_path / "log.json")
    with pytest.raises(ValueError, match="already declared"):
        dt.declare_trials("tsmom", (_tsmom_cfg(lookback=99),), log_path=tmp_path / "log.json")


def test_duplicate_configs_raise(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        dt.declare_trials("tsmom", (_tsmom_cfg(), _tsmom_cfg()), log_path=tmp_path / "log.json")


def test_unknown_family_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="family"):
        dt.declare_trials("scalping", (_tsmom_cfg(),), log_path=tmp_path / "log.json")


def test_mutable_config_rejected(tmp_path: Path) -> None:
    @dataclass
    class MutableCfg:
        x: int = 1

    with pytest.raises(ValueError, match="FROZEN"):
        dt.declare_trials("tsmom", (MutableCfg(),), log_path=tmp_path / "log.json")


def test_undeclared_run_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="declare_trials"):
        dt.assert_declared("tsmom", _tsmom_cfg())
    dt.declare_trials("tsmom", (_tsmom_cfg(lookback=20),), log_path=tmp_path / "log.json")
    with pytest.raises(ValueError, match="NOT declared"):
        dt.assert_declared("tsmom", _tsmom_cfg(lookback=999))
    assert dt.assert_declared("tsmom", _tsmom_cfg(lookback=20)) == 85


# ---------------------------------------------------------------------------
# Config fail-closed validation
# ---------------------------------------------------------------------------

def test_tsmom_config_validation() -> None:
    with pytest.raises(ValueError, match="timeframe"):
        _tsmom_cfg(timeframe="15m")
    with pytest.raises(ValueError, match="lookback"):
        _tsmom_cfg(lookback=5)
    with pytest.raises(ValueError, match="vol_target_ann"):
        _tsmom_cfg(vol_target_ann=0.0)
    with pytest.raises(ValueError, match="long_short"):
        _tsmom_cfg(long_short="short_only")


def test_carry_config_validation() -> None:
    with pytest.raises(ValueError, match="metric"):
        _carry_cfg(metric="mean")
    with pytest.raises(ValueError, match="window_events"):
        _carry_cfg(window_events=5)
    with pytest.raises(ValueError, match="strictly greater"):
        _carry_cfg(entry_threshold=0.5, exit_threshold=0.5)
    with pytest.raises(ValueError, match="percentile"):
        _carry_cfg(metric="percentile", entry_threshold=1.5, exit_threshold=0.5)
    with pytest.raises(ValueError, match="max_hold_bars"):
        _carry_cfg(max_hold_bars=0)


def test_carry_family_requires_funding_df() -> None:
    with pytest.raises(ValueError, match="funding_df"):
        CarryFamily(config=_carry_cfg(), funding_df=None)


# ---------------------------------------------------------------------------
# Causality (shift-the-future)
# ---------------------------------------------------------------------------

def test_tsmom_signal_is_causal() -> None:
    """Signal at idx is identical when every row AFTER idx is perturbed."""
    fam = TSMOMFamily(config=_tsmom_cfg(lookback=50))
    df1 = _bars(200)
    df2 = df1.copy()
    df2.loc[df2.index > 120, ["Open", "High", "Low", "Close"]] *= 5.0

    s1 = fam.signal(df1, 120)
    s2 = fam.signal(df2, 120)
    assert s1 is not None, "uptrend at idx=120 must produce a BUY signal"
    assert s1 == s2, "future rows changed the signal: lookahead detected"
    assert s1.side == "BUY"


def test_tsmom_no_signal_before_lookback() -> None:
    fam = TSMOMFamily(config=_tsmom_cfg(lookback=50))
    assert fam.signal(_bars(200), 30) is None


def test_carry_signal_is_causal() -> None:
    """Signal at idx ignores funding events with timestamp > bar datetime."""
    cfg = _carry_cfg(window_events=30, entry_threshold=1.0)
    bars = _bars(200, freq="4h")
    idx = 150
    bar_time = bars.iloc[idx]["datetime"]

    # Base series: low rates, last pre-bar event spikes -> zscore >= 1
    base = _funding(400)
    pos = base["datetime"].searchsorted(bar_time, side="right")
    base.loc[pos - 1, "funding_rate"] = 0.005

    fam1 = CarryFamily(config=cfg, funding_df=base)
    s1 = fam1.signal(bars, idx)
    assert s1 is not None and s1.side == "SELL"

    # Perturb ONLY future funding events: signal must be identical.
    future = base.copy()
    future.loc[future.index >= pos, "funding_rate"] = -0.006
    fam2 = CarryFamily(config=cfg, funding_df=future)
    s2 = fam2.signal(bars, idx)
    assert s1 == s2, "future funding events changed the signal: lookahead detected"


def test_carry_no_signal_below_threshold() -> None:
    """Flat funding series: zscore undefined/zero -> no signal."""
    fam = CarryFamily(config=_carry_cfg(), funding_df=_funding(400))
    assert fam.signal(_bars(200, freq="4h"), 150) is None


def test_carry_no_signal_with_insufficient_history() -> None:
    fam = CarryFamily(
        config=_carry_cfg(window_events=300), funding_df=_funding(50)
    )
    assert fam.signal(_bars(200, freq="4h"), 150) is None


# ---------------------------------------------------------------------------
# Runtime isolation
# ---------------------------------------------------------------------------

def test_research_edge03_not_imported_by_runtime() -> None:
    """No module outside research/ and tests/ may reference research.edge03."""
    offenders: list[str] = []
    for py in (PROJECT_ROOT / "trading_bot").rglob("*.py"):
        rel = py.relative_to(PROJECT_ROOT)
        parts = rel.parts
        if "research" in parts or "tests" in parts or "__pycache__" in parts:
            continue
        text = py.read_text(encoding="utf-8", errors="replace")
        if "edge03" in text:
            offenders.append(str(rel))
    assert offenders == [], f"runtime modules reference research.edge03: {offenders}"


def test_lab_banner_constants() -> None:
    from trading_bot.research import edge03

    assert edge03.DIAGNOSTIC_ONLY is True
    assert edge03.OPENS_ORDERS is False
    assert edge03.LIVE_TRADING_ALLOWED is False
    assert edge03.PAPER_TRADING_ACTIVATION_ALLOWED is False


# ---------------------------------------------------------------------------
# Panel runner (injected loader; full path through run_backtest_frame)
# ---------------------------------------------------------------------------

def test_panel_runner_rejects_undeclared_config(tmp_path: Path) -> None:
    from trading_bot.research.edge03.panel_runner import run_trial_on_panel

    with pytest.raises(ValueError, match="declare_trials"):
        run_trial_on_panel(
            family="tsmom",
            config=_tsmom_cfg(),
            strategy_factory=lambda cfg, sym: TSMOMFamily(config=cfg),
            symbols=["BTC/USDT"],
            timeframe="1d",
            panel_loader=lambda sym, tf: _bars(600),
        )


def test_panel_runner_runs_declared_trial(tmp_path: Path) -> None:
    from trading_bot.research.edge03.panel_runner import run_trial_on_panel

    cfg = _tsmom_cfg(lookback=50)
    dt.declare_trials("tsmom", (cfg,), log_path=tmp_path / "log.json")
    report = run_trial_on_panel(
        family="tsmom",
        config=cfg,
        strategy_factory=lambda c, sym: TSMOMFamily(config=c),
        symbols=["AAA/USDT", "BBB/USDT"],
        timeframe="1d",
        panel_loader=lambda sym, tf: _bars(600),
    )
    assert report["trial_number"] == 85
    assert report["diagnostic_only"] is True
    assert report["opens_orders"] is False
    assert set(report["per_symbol"].keys()) == {"AAA/USDT", "BBB/USDT"}
    assert "passes" in report["panel_gate"]
