"""test_clean_bot_funding.py — Funding accrual in the clean_bot backtester.

Pure in-memory tests (no parquet, no network) following the fixture patterns
of test_validation_gates.py. Verify:
- sign convention: long pays positive funding, short receives it
- accrual convention: entry < t <= exit (entry exactly at a funding instant
  is not charged; exit exactly at one is)
- funding never touches cost / net_pnl; net_pnl_with_funding == net_pnl + funding_pnl
- default off: behavior identical to pre-funding backtester, new fields None
- fail-closed pairing and data-contract violations raise ValueError
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "trading_bot"))

from trading_bot.clean_bot.backtest import run_backtest_frame
from trading_bot.clean_bot.funding import (
    MAX_ABS_FUNDING_RATE,
    accrue_funding_for_trade,
    funding_cache_path,
    validate_funding_frame,
)
from trading_bot.clean_bot.models import BacktestSettings, Signal
from trading_bot.clean_bot.strategies import Strategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bars(n: int = 600, start: str = "2024-01-01", freq: str = "4h") -> pd.DataFrame:
    """Minimal OHLCV frame with the columns required by backtest machinery."""
    prices = [100.0 + i * 0.01 for i in range(n)]
    return pd.DataFrame({
        "Open":            prices,
        "High":            [p + 0.5 for p in prices],
        "Low":             [p - 0.5 for p in prices],
        "Close":           prices,
        "Volume":          [1000.0] * n,
        "ema50":           [p + 0.1 for p in prices],
        "ema200":          prices,
        "atr14":           [1.0] * n,
        "atr_pct":         [0.5] * n,
        "volume_ratio_20": [1.5] * n,
        "datetime": pd.date_range(start, periods=n, freq=freq, tz="UTC"),
    })


def _make_funding(
    n: int = 400,
    rate: float = 0.0001,
    start: str = "2024-01-01",
    freq: str = "8h",
    symbol: str = "BTC/USDT",
) -> pd.DataFrame:
    """Synthetic funding series on a controlled grid with a constant rate."""
    return pd.DataFrame({
        "datetime": pd.date_range(start, periods=n, freq=freq, tz="UTC"),
        "symbol": [symbol] * n,
        "funding_rate": [rate] * n,
    })


class _MockSignalAt(Strategy):
    """Fires a single BUY signal at exactly fire_idx; silent everywhere else."""
    name = "mock_signal"

    def __init__(self, fire_idx: int) -> None:
        self._fire = fire_idx

    def signal(self, df: pd.DataFrame, idx: int) -> Signal | None:
        if idx != self._fire:
            return None
        close = float(df.iloc[idx]["Close"])
        return Signal(
            strategy="mock_signal",
            side="BUY",
            score=1.0,
            reason="mock",
            stop_price=close * 0.90,
            take_profit=close * 1.50,
            metadata={"max_hold_bars": 36},
        )


# ---------------------------------------------------------------------------
# accrue_funding_for_trade — sign convention and event selection
# ---------------------------------------------------------------------------

def test_long_pays_positive_funding() -> None:
    """Long over 3 funding events with positive rate: funding_pnl < 0, 3 events."""
    bars = _make_bars()
    funding = _make_funding(rate=0.0001)
    # entry 01:00, exit next day 01:00 → events at 08:00, 16:00, 00:00 = 3
    pnl, events = accrue_funding_for_trade(
        funding_df=funding,
        bars_df=bars,
        side="BUY",
        entry_time="2024-01-01 01:00:00+00:00",
        exit_time="2024-01-02 01:00:00+00:00",
        qty=1.0,
    )
    assert events == 3
    assert pnl < 0.0


def test_short_receives_positive_funding_symmetric() -> None:
    """Short over the same window: funding_pnl positive and exactly opposite."""
    bars = _make_bars()
    funding = _make_funding(rate=0.0001)
    pnl_long, ev_long = accrue_funding_for_trade(
        funding_df=funding, bars_df=bars, side="BUY",
        entry_time="2024-01-01 01:00:00+00:00",
        exit_time="2024-01-02 01:00:00+00:00", qty=1.0,
    )
    pnl_short, ev_short = accrue_funding_for_trade(
        funding_df=funding, bars_df=bars, side="SELL",
        entry_time="2024-01-01 01:00:00+00:00",
        exit_time="2024-01-02 01:00:00+00:00", qty=1.0,
    )
    assert ev_long == ev_short == 3
    assert pnl_short > 0.0
    assert pnl_short == pytest.approx(-pnl_long, rel=1e-12)


def test_negative_rate_long_receives() -> None:
    """Negative funding rate: long receives (positive pnl)."""
    bars = _make_bars()
    funding = _make_funding(rate=-0.0002)
    pnl, events = accrue_funding_for_trade(
        funding_df=funding, bars_df=bars, side="BUY",
        entry_time="2024-01-01 01:00:00+00:00",
        exit_time="2024-01-01 23:00:00+00:00", qty=2.0,
    )
    assert events == 2  # 08:00 and 16:00
    assert pnl > 0.0


def test_entry_exactly_at_funding_event_not_charged() -> None:
    """Entry exactly at a funding timestamp: that event is NOT charged."""
    bars = _make_bars()
    funding = _make_funding(rate=0.0001)
    pnl, events = accrue_funding_for_trade(
        funding_df=funding, bars_df=bars, side="BUY",
        entry_time="2024-01-01 08:00:00+00:00",  # exact funding instant
        exit_time="2024-01-01 15:00:00+00:00",   # before the next one
        qty=1.0,
    )
    assert events == 0
    assert pnl == 0.0


def test_exit_exactly_at_funding_event_charged() -> None:
    """Exit exactly at a funding timestamp: that event IS charged."""
    bars = _make_bars()
    funding = _make_funding(rate=0.0001)
    pnl, events = accrue_funding_for_trade(
        funding_df=funding, bars_df=bars, side="BUY",
        entry_time="2024-01-01 09:00:00+00:00",
        exit_time="2024-01-01 16:00:00+00:00",  # exact funding instant
        qty=1.0,
    )
    assert events == 1
    assert pnl < 0.0


def test_trade_shorter_than_funding_interval() -> None:
    """Trade fully inside one funding interval: zero events, zero pnl."""
    bars = _make_bars()
    funding = _make_funding(rate=0.0005)
    pnl, events = accrue_funding_for_trade(
        funding_df=funding, bars_df=bars, side="BUY",
        entry_time="2024-01-01 08:30:00+00:00",
        exit_time="2024-01-01 12:00:00+00:00",
        qty=1.0,
    )
    assert events == 0
    assert pnl == 0.0


def test_payment_uses_asof_mark_price() -> None:
    """Per-event payment = -direction * rate * mark * qty with mark = last Close <= t."""
    bars = _make_bars(freq="4h")  # bars at 00:00, 04:00, 08:00, ...
    funding = _make_funding(rate=0.0001)
    pnl, events = accrue_funding_for_trade(
        funding_df=funding, bars_df=bars, side="BUY",
        entry_time="2024-01-01 01:00:00+00:00",
        exit_time="2024-01-01 09:00:00+00:00",
        qty=3.0,
    )
    assert events == 1  # only 08:00
    # mark at 08:00 = Close of the 08:00 bar = 100.0 + 2*0.01 = 100.02
    expected = -1.0 * 0.0001 * 100.02 * 3.0
    assert pnl == pytest.approx(expected, rel=1e-12)


def test_invalid_side_raises() -> None:
    with pytest.raises(ValueError, match="side"):
        accrue_funding_for_trade(
            funding_df=_make_funding(), bars_df=_make_bars(), side="LONG",
            entry_time="2024-01-01 01:00:00+00:00",
            exit_time="2024-01-02 01:00:00+00:00", qty=1.0,
        )


def test_invalid_qty_raises() -> None:
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="qty"):
            accrue_funding_for_trade(
                funding_df=_make_funding(), bars_df=_make_bars(), side="BUY",
                entry_time="2024-01-01 01:00:00+00:00",
                exit_time="2024-01-02 01:00:00+00:00", qty=bad,
            )


def test_exit_before_entry_raises() -> None:
    with pytest.raises(ValueError, match="before"):
        accrue_funding_for_trade(
            funding_df=_make_funding(), bars_df=_make_bars(), side="BUY",
            entry_time="2024-01-02 01:00:00+00:00",
            exit_time="2024-01-01 01:00:00+00:00", qty=1.0,
        )


def test_funding_event_before_first_bar_raises() -> None:
    """A funding event that cannot be priced (no bar <= t) fails closed."""
    bars = _make_bars(start="2024-01-05")  # bars start after the funding events
    funding = _make_funding(start="2024-01-01", rate=0.0001)
    with pytest.raises(ValueError, match="no bar"):
        accrue_funding_for_trade(
            funding_df=funding, bars_df=bars, side="BUY",
            entry_time="2024-01-01 01:00:00+00:00",
            exit_time="2024-01-02 01:00:00+00:00", qty=1.0,
        )


# ---------------------------------------------------------------------------
# validate_funding_frame / data contract
# ---------------------------------------------------------------------------

def test_valid_frame_accepted() -> None:
    out = validate_funding_frame(_make_funding(), "BTC/USDT")
    assert list(out.columns) == ["datetime", "symbol", "funding_rate"]
    assert len(out) == 400


def test_missing_columns_rejected() -> None:
    df = _make_funding().drop(columns=["funding_rate"])
    with pytest.raises(ValueError, match="missing columns"):
        validate_funding_frame(df, "BTC/USDT")


def test_empty_frame_rejected() -> None:
    df = _make_funding().iloc[0:0]
    with pytest.raises(ValueError, match="empty"):
        validate_funding_frame(df, "BTC/USDT")


def test_symbol_mismatch_rejected() -> None:
    df = _make_funding(symbol="ETH/USDT")
    with pytest.raises(ValueError, match="symbol mismatch"):
        validate_funding_frame(df, "BTC/USDT")


def test_null_rate_rejected() -> None:
    df = _make_funding()
    df.loc[5, "funding_rate"] = None
    with pytest.raises(ValueError, match="null"):
        validate_funding_frame(df, "BTC/USDT")


def test_rate_cap_breach_rejected() -> None:
    df = _make_funding()
    df.loc[5, "funding_rate"] = MAX_ABS_FUNDING_RATE  # >= cap fails
    with pytest.raises(ValueError, match="breaches"):
        validate_funding_frame(df, "BTC/USDT")
    df2 = _make_funding()
    df2.loc[5, "funding_rate"] = -0.01
    with pytest.raises(ValueError, match="breaches"):
        validate_funding_frame(df2, "BTC/USDT")


def test_duplicate_timestamps_rejected() -> None:
    df = _make_funding()
    df.loc[5, "datetime"] = df.loc[4, "datetime"]
    df = df.sort_values("datetime").reset_index(drop=True)
    with pytest.raises(ValueError, match="duplicate"):
        validate_funding_frame(df, "BTC/USDT")


def test_out_of_order_rejected() -> None:
    df = _make_funding()
    df.loc[5, "datetime"] = pd.Timestamp("2023-01-01", tz="UTC")
    with pytest.raises(ValueError, match="sorted"):
        validate_funding_frame(df, "BTC/USDT")


def test_off_grid_timestamp_rejected() -> None:
    df = _make_funding()
    df.loc[5, "datetime"] = df.loc[5, "datetime"] + pd.Timedelta(minutes=7)
    with pytest.raises(ValueError, match="off-grid"):
        validate_funding_frame(df, "BTC/USDT")


def test_unsupported_modal_interval_rejected() -> None:
    """A 3h grid is not a known Binance funding interval → rejected."""
    df = _make_funding(freq="3h")
    with pytest.raises(ValueError, match="modal interval"):
        validate_funding_frame(df, "BTC/USDT")


def test_4h_grid_accepted() -> None:
    """Some USDT-M symbols settle every 4h: allowlisted, not rejected."""
    out = validate_funding_frame(_make_funding(freq="4h"), "BTC/USDT")
    assert len(out) == 400


def test_funding_cache_path_naming() -> None:
    p = funding_cache_path(Path("/tmp/data"), "BTC/USDT")
    assert p.name == "btcusdt_funding.parquet"
    with pytest.raises(ValueError):
        funding_cache_path(Path("/tmp/data"), "")


def test_panel_cache_path_naming() -> None:
    """4h/1d kline caches use the deterministic {slug}_{tf}_cache convention."""
    from trading_bot.clean_bot.data import cache_path

    assert cache_path(Path("/tmp/data"), "BTC/USDT", "4h").name == "btcusdt_4h_cache.parquet"
    assert cache_path(Path("/tmp/data"), "DOGE/USDT", "1d").name == "dogeusdt_1d_cache.parquet"
    # 5m/1m explicit dicts unchanged
    assert cache_path(Path("/tmp/data"), "BTC/USDT", "5m").name == "btc_5m_150k_cache.parquet"
    # fail-closed on unknown timeframe and invalid symbol
    with pytest.raises(ValueError, match="timeframe"):
        cache_path(Path("/tmp/data"), "BTC/USDT", "2h")
    with pytest.raises(ValueError, match="symbol"):
        cache_path(Path("/tmp/data"), "", "4h")


# ---------------------------------------------------------------------------
# Backtester integration — opt-in, fail-closed pairing, default unchanged
# ---------------------------------------------------------------------------

def _bt_settings(**overrides):
    base = dict(
        symbol="BTC/USDT",
        timeframe="4h",
        starting_balance=1000.0,
        risk_per_trade_pct=0.005,
        cost_model="conservative",
    )
    base.update(overrides)
    return BacktestSettings(**base)


def test_funding_enabled_without_df_raises() -> None:
    with pytest.raises(ValueError, match="funding_df"):
        run_backtest_frame(
            raw_rows=600, df=_make_bars(),
            settings=_bt_settings(funding_enabled=True),
            strategies=[_MockSignalAt(410)],
        )


def test_funding_df_without_enabled_raises() -> None:
    with pytest.raises(ValueError, match="funding_enabled"):
        run_backtest_frame(
            raw_rows=600, df=_make_bars(),
            settings=_bt_settings(),
            strategies=[_MockSignalAt(410)],
            funding_df=_make_funding(),
        )


def test_default_off_fields_none_and_metrics_unchanged() -> None:
    """funding_enabled=False (default): no funding keys, trade fields None."""
    result = run_backtest_frame(
        raw_rows=600, df=_make_bars(),
        settings=_bt_settings(),
        strategies=[_MockSignalAt(410)],
    )
    assert result["metrics"]["closed_trades"] >= 1
    assert "funding_pnl_total" not in result["metrics"]
    assert "net_pnl_with_funding" not in result["metrics"]
    for t in result["trades"]:
        assert t["funding_pnl"] is None
        assert t["funding_events"] is None
        assert t["net_pnl_with_funding"] is None


def test_funding_enabled_populates_fields_and_identity() -> None:
    """With funding on: fields populated, identity net_pnl_with_funding ==
    net_pnl + funding_pnl exact, cost untouched by funding."""
    bars = _make_bars()
    funding = _make_funding(
        n=2000, rate=0.0005,
        start="2024-01-01", freq="8h",
    )
    settings_off = _bt_settings()
    settings_on = _bt_settings(funding_enabled=True)
    strategies = [_MockSignalAt(410)]

    res_off = run_backtest_frame(
        raw_rows=600, df=bars, settings=settings_off, strategies=strategies,
    )
    res_on = run_backtest_frame(
        raw_rows=600, df=bars, settings=settings_on, strategies=strategies,
        funding_df=funding,
    )
    assert res_on["metrics"]["closed_trades"] == res_off["metrics"]["closed_trades"] >= 1

    for t_on, t_off in zip(res_on["trades"], res_off["trades"]):
        assert t_on["funding_pnl"] is not None
        assert t_on["funding_events"] is not None
        assert t_on["net_pnl_with_funding"] == pytest.approx(
            t_on["net_pnl"] + t_on["funding_pnl"], rel=1e-12
        )
        # funding never leaks into cost or net_pnl of the same trade
        assert t_on["cost"] == pytest.approx(t_off["cost"], rel=1e-9)
        assert t_on["net_pnl"] == pytest.approx(t_off["net_pnl"], rel=1e-9)
        # long trade held across 8h events with positive rate pays funding
        if t_on["side"] == "BUY" and t_on["funding_events"] > 0:
            assert t_on["funding_pnl"] < 0.0

    m = res_on["metrics"]
    assert m["funding_pnl_total"] == pytest.approx(
        sum(t["funding_pnl"] for t in res_on["trades"]), rel=1e-9
    )
    assert m["funding_events_total"] == sum(t["funding_events"] for t in res_on["trades"])
    assert m["net_pnl_with_funding"] == pytest.approx(
        m["net_pnl"] + m["funding_pnl_total"], rel=1e-9
    )
    # cost-only keys keep their cost-only semantics even with funding on
    assert m["net_pnl"] == pytest.approx(res_off["metrics"]["net_pnl"], rel=1e-9)


def test_settings_asdict_gains_only_funding_enabled() -> None:
    """asdict(settings) output is stable except the one new key."""
    from dataclasses import asdict
    d = asdict(_bt_settings())
    assert d["funding_enabled"] is False
    expected_keys = {
        "symbol", "timeframe", "starting_balance", "risk_per_trade_pct",
        "max_daily_loss_pct", "max_positions", "max_hold_bars",
        "cost_model", "max_rows", "funding_enabled",
    }
    assert set(d.keys()) == expected_keys
