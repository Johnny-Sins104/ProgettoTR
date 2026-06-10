"""test_panel_validation_gates.py — Panel-level gates for 4h/1d research.

Synthetic per-symbol trade dicts only (no parquet, no network). Also includes
a regression test asserting that the per-symbol VALIDATION_CONFIG is unchanged
by the panel additions.
"""
from __future__ import annotations

import sys
import types as types_mod
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "trading_bot"))

from trading_bot.clean_bot.validation_gates import (
    PANEL_VALIDATION_CONFIG,
    VALIDATION_CONFIG,
    is_promising_panel,
    panel_oos_with_warmup,
    regime_stratified_check,
    temporal_concentration_check,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _trade(entry_time: str, net_pnl: float) -> dict:
    return {"entry_time": entry_time, "exit_time": entry_time, "net_pnl": net_pnl}


def _panel_results(n_symbols: int = 16, trades_per_symbol: int = 4) -> dict:
    """16 symbols x 4 trades: every symbol fails a per-symbol 50-trade gate,
    the pooled panel passes it. Trades spread over 4 months, mostly winners."""
    results: dict[str, dict] = {}
    months = ["2025-01", "2025-02", "2025-03", "2025-04"]
    for s in range(n_symbols):
        trades = []
        for k in range(trades_per_symbol):
            month = months[k % len(months)]
            day = 1 + (s % 27)
            pnl = 10.0 if (s + k) % 4 != 0 else -5.0  # 3 winners : 1 loser
            trades.append(_trade(f"{month}-{day:02d} 00:00:00+00:00", pnl))
        results[f"SYM{s}/USDT"] = {"trades": trades}
    return results


# ---------------------------------------------------------------------------
# Config immutability and regression
# ---------------------------------------------------------------------------

def test_validation_config_unchanged() -> None:
    """Regression: the per-symbol config is byte-identical to its M9 spec."""
    assert dict(VALIDATION_CONFIG) == {
        "warmup_bars": 401,
        "oos_split_ratio": 0.3,
        "min_oos_trades": 50,
        "min_pf": 1.0,
        "min_net_pnl": 0.0,
        "temporal_conc_max_pct": 50.0,
        "temporal_min_weeks": 3,
        "cost_scenario": "conservative",
        "risk_per_trade_pct": 0.005,
    }


def test_panel_config_immutable_and_spec() -> None:
    assert isinstance(PANEL_VALIDATION_CONFIG, types_mod.MappingProxyType)
    with pytest.raises(TypeError):
        PANEL_VALIDATION_CONFIG["min_pf"] = 0.0  # type: ignore[index]
    assert PANEL_VALIDATION_CONFIG["min_oos_trades_panel"] == 50
    assert PANEL_VALIDATION_CONFIG["temporal_bucket"] == "month"
    assert PANEL_VALIDATION_CONFIG["temporal_min_buckets"] == 3
    assert PANEL_VALIDATION_CONFIG["cost_scenario"] == "conservative"
    assert PANEL_VALIDATION_CONFIG["risk_per_trade_pct"] == 0.005
    assert PANEL_VALIDATION_CONFIG["min_positive_regimes"] == 2
    wb = PANEL_VALIDATION_CONFIG["warmup_bars_by_timeframe"]
    assert isinstance(wb, types_mod.MappingProxyType)
    assert wb["4h"] == 401 and wb["1d"] == 260


# ---------------------------------------------------------------------------
# is_promising_panel — pooled counting
# ---------------------------------------------------------------------------

def test_panel_pools_trades_across_symbols() -> None:
    """16 symbols x 4 trades = 64 pooled: passes while each symbol alone would fail."""
    results = _panel_results()
    passes, checks = is_promising_panel(results)
    assert checks["n_trades"] == 64
    assert all(v == 4 for v in checks["per_symbol_trades"].values())
    assert checks["trades_ok"] is True
    assert checks["pf_ok"] is True
    assert checks["pnl_ok"] is True
    assert checks["temporal_ok"] is True, checks["temporal_detail"]
    assert passes is True


def test_panel_fails_below_pooled_minimum() -> None:
    """8 symbols x 4 trades = 32 pooled < 50: trade gate fails."""
    passes, checks = is_promising_panel(_panel_results(n_symbols=8))
    assert checks["n_trades"] == 32
    assert checks["trades_ok"] is False
    assert passes is False


def test_panel_fails_on_negative_pooled_pnl() -> None:
    results = _panel_results()
    for r in results.values():
        for t in r["trades"]:
            t["net_pnl"] = -abs(t["net_pnl"])
    passes, checks = is_promising_panel(results)
    assert checks["pnl_ok"] is False
    assert checks["pf_ok"] is False
    assert passes is False


def test_panel_monthly_concentration_gate() -> None:
    """All pnl concentrated in one month: monthly bucket gate fails."""
    results = {
        f"SYM{s}/USDT": {
            "trades": [_trade(f"2025-03-{(k % 27) + 1:02d} 00:00:00+00:00", 10.0)
                       for k in range(4)]
        }
        for s in range(16)
    }
    passes, checks = is_promising_panel(results)
    assert checks["temporal_ok"] is False
    detail = checks["temporal_detail"]
    assert detail["bucket"] == "month"
    assert "insufficient_weeks" in detail["reason"] or "worst_week_pct" in detail["reason"]
    assert passes is False


def test_panel_missing_trades_key_raises() -> None:
    with pytest.raises(ValueError, match="trades"):
        is_promising_panel({"BTC/USDT": {}})


def test_panel_empty_input_fails_closed() -> None:
    passes, checks = is_promising_panel({})
    assert passes is False
    assert checks["reason"] == "no_per_symbol_results"


# ---------------------------------------------------------------------------
# temporal_concentration_check — bucket parameter
# ---------------------------------------------------------------------------

def test_week_bucket_default_unchanged() -> None:
    """Default call keeps original ISO-week behavior (legacy keys intact)."""
    trades = [_trade(f"2025-01-{d:02d} 00:00:00+00:00", 5.0) for d in (1, 8, 15, 22)]
    out = temporal_concentration_check(trades)
    assert out["bucket"] == "week"
    assert out["n_weeks"] == 4
    assert out["passes"] is True


def test_month_bucket_groups_by_month() -> None:
    trades = [
        _trade("2025-01-02 00:00:00+00:00", 5.0),
        _trade("2025-01-28 00:00:00+00:00", 5.0),
        _trade("2025-02-10 00:00:00+00:00", 5.0),
        _trade("2025-03-05 00:00:00+00:00", 5.0),
    ]
    out = temporal_concentration_check(trades, bucket="month")
    assert out["bucket"] == "month"
    assert out["n_weeks"] == 3  # 3 distinct months (legacy key name)
    assert out["passes"] is True


def test_unknown_bucket_raises() -> None:
    with pytest.raises(ValueError, match="bucket"):
        temporal_concentration_check([_trade("2025-01-01", 1.0)], bucket="day")


# ---------------------------------------------------------------------------
# regime_stratified_check
# ---------------------------------------------------------------------------

def _regime_series() -> pd.Series:
    idx = pd.to_datetime(
        ["2025-01-01", "2025-02-01", "2025-03-01"], utc=True
    )
    return pd.Series(["bull", "bear", "sideways"], index=idx)


def test_regime_two_of_three_positive_passes() -> None:
    trades = [
        _trade("2025-01-10 00:00:00+00:00", 10.0),   # bull +
        _trade("2025-02-10 00:00:00+00:00", 5.0),    # bear +
        _trade("2025-03-10 00:00:00+00:00", -3.0),   # sideways -
    ]
    out = regime_stratified_check(trades, _regime_series())
    assert out["n_positive_regimes"] == 2
    assert out["passes"] is True
    assert out["regime_pnl"] == {"bull": 10.0, "bear": 5.0, "sideways": -3.0}


def test_regime_one_of_three_positive_fails() -> None:
    trades = [
        _trade("2025-01-10 00:00:00+00:00", 10.0),   # bull +
        _trade("2025-02-10 00:00:00+00:00", -5.0),   # bear -
        _trade("2025-03-10 00:00:00+00:00", -3.0),   # sideways -
    ]
    out = regime_stratified_check(trades, _regime_series())
    assert out["n_positive_regimes"] == 1
    assert out["passes"] is False
    assert "positive_regimes=1" in out["reason"]


def test_regime_missing_labels_fails_closed() -> None:
    trades = [_trade("2025-01-10 00:00:00+00:00", 10.0)]
    out = regime_stratified_check(trades, None)
    assert out["passes"] is False
    assert out["reason"] == "no_regime_labels"
    out2 = regime_stratified_check(trades, pd.Series(dtype=object))
    assert out2["passes"] is False


def test_regime_trade_before_first_label_fails_closed() -> None:
    trades = [_trade("2024-12-01 00:00:00+00:00", 10.0)]
    out = regime_stratified_check(trades, _regime_series())
    assert out["passes"] is False
    assert "unlabeled_trades" in out["reason"]


def test_regime_unsorted_labels_raise() -> None:
    idx = pd.to_datetime(["2025-02-01", "2025-01-01"], utc=True)
    labels = pd.Series(["bull", "bear"], index=idx)
    with pytest.raises(ValueError, match="sorted"):
        regime_stratified_check([_trade("2025-02-10 00:00:00+00:00", 1.0)], labels)


# ---------------------------------------------------------------------------
# panel_oos_with_warmup
# ---------------------------------------------------------------------------

def _df(n: int) -> pd.DataFrame:
    return pd.DataFrame({
        "Close": range(n),
        "datetime": pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC"),
    })


def test_panel_warmup_uses_declared_lookback_when_larger() -> None:
    df = _df(2000)
    # declared 300 + buffer 20 = 320 > 260 (1d config) → warmup 320
    oos_df, warmup = panel_oos_with_warmup(
        df, timeframe="1d", declared_max_lookback_bars=300,
    )
    assert warmup == 320
    split = int(2000 * 0.7)
    assert len(oos_df) == (2000 - split) + 320


def test_panel_warmup_floor_from_config() -> None:
    # declared 100 + 20 = 120 < 260 → config floor wins on 1d; 401 on 4h
    _, warmup_1d = panel_oos_with_warmup(_df(2000), timeframe="1d", declared_max_lookback_bars=100)
    assert warmup_1d == 260
    _, warmup_4h = panel_oos_with_warmup(_df(2000), timeframe="4h", declared_max_lookback_bars=100)
    assert warmup_4h == 401


def test_panel_warmup_requires_declared_lookback() -> None:
    with pytest.raises(ValueError, match="declared_max_lookback_bars"):
        panel_oos_with_warmup(_df(2000), timeframe="1d", declared_max_lookback_bars=None)
    with pytest.raises(ValueError, match="declared_max_lookback_bars"):
        panel_oos_with_warmup(_df(2000), timeframe="1d", declared_max_lookback_bars=0)


def test_panel_warmup_rejects_unknown_timeframe() -> None:
    for bad in ("15m", "1h", "", None):
        with pytest.raises(ValueError, match="timeframe"):
            panel_oos_with_warmup(_df(2000), timeframe=bad, declared_max_lookback_bars=100)
