"""Tests for the STRAT-02 edge research lab engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_bot.research.edge_lab import (
    RISK_PER_TRADE,
    CausalExecutor,
    DirectionalSignalSpec,
    OOSContaminationError,
    SplitContract,
    TradeEvent,
    compute_metrics,
    guard_no_oos,
    portfolio_replay,
)


def _mk_15m(n: int = 50, start: str = "2024-01-01", price: float = 100.0) -> pd.DataFrame:
    dt = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    df = pd.DataFrame(
        {
            "datetime": dt,
            "Open": price,
            "High": price + 1.0,
            "Low": price - 1.0,
            "Close": price,
            "Volume": 10.0,
        }
    )
    df["atr14"] = 2.0
    return df


def _mk_5m(n: int = 150, start: str = "2024-01-01", price: float = 100.0) -> pd.DataFrame:
    dt = pd.date_range(start, periods=n, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "datetime": dt,
            "Open": price,
            "High": price + 0.5,
            "Low": price - 0.5,
            "Close": price,
            "Volume": 3.0,
            "atr14": 0.5,
        }
    )
    df["atr_pct"] = df["atr14"] / df["Close"] * 100.0
    return df


def _window(df15):
    return df15["datetime"].iloc[0], df15["datetime"].iloc[-1] + pd.Timedelta(minutes=15)


def test_entry_is_first_5m_open_after_15m_close():
    df15, df5 = _mk_15m(), _mk_5m()
    ex = CausalExecutor(df15, df5)
    j = ex.entry_bar_for_signal(4)  # bar 4 opens at +60min, closes at +75min
    assert df5["datetime"].iloc[j] == df15["datetime"].iloc[4] + pd.Timedelta(minutes=15)


def test_fixed_rr_stop_loss_hit():
    df15, df5 = _mk_15m(), _mk_5m()
    # force a stop hit: a 5m bar 10 bars after entry dives below the stop
    df5.loc[25, "Low"] = 90.0
    ex = CausalExecutor(df15, df5)
    spec = DirectionalSignalSpec(
        idx15=4, side="BUY", stop_atr_mult=2.0, exit_style="fixed_rr",
        rr=2.0, max_hold_bars_5m=100,
    )
    ws, we = _window(df15)
    events = ex.run([spec], family="f", config_id="c", asset="BTCUSDT",
                    window_start=ws, window_end=we)
    assert len(events) == 1
    ev = events[0]
    assert ev.exit_reason in ("SL", "SL_SAME_BAR")
    assert ev.exit_price == pytest.approx(ev.entry_price - 2.0 * 2.0)


def test_gap_through_stop_fills_at_open():
    df15, df5 = _mk_15m(), _mk_5m()
    df5.loc[20, "Open"] = 90.0
    df5.loc[20, "Low"] = 89.0
    ex = CausalExecutor(df15, df5)
    spec = DirectionalSignalSpec(
        idx15=4, side="BUY", stop_atr_mult=2.0, exit_style="fixed_rr",
        rr=2.0, max_hold_bars_5m=100,
    )
    ws, we = _window(df15)
    events = ex.run([spec], family="f", config_id="c", asset="BTCUSDT",
                    window_start=ws, window_end=we)
    assert events[0].exit_reason == "SL_GAP"
    assert events[0].exit_price == 90.0  # worst-case: open below stop


def test_one_position_per_asset():
    df15, df5 = _mk_15m(), _mk_5m()
    ex = CausalExecutor(df15, df5)
    specs = [
        DirectionalSignalSpec(idx15=i, side="BUY", stop_atr_mult=2.0,
                              exit_style="time_stop", max_hold_bars_5m=30)
        for i in (4, 5, 6)
    ]
    ws, we = _window(df15)
    events = ex.run(specs, family="f", config_id="c", asset="BTCUSDT",
                    window_start=ws, window_end=we)
    assert len(events) == 1  # the next two signals fall inside the busy window


def test_replay_risk_budget_is_half_percent():
    ev = TradeEvent(
        family="f", config_id="c", asset="BTCUSDT", side="BUY",
        signal_time="2024-01-01 00:00:00+00:00",
        entry_time="2024-01-01 01:00:00+00:00",
        exit_time="2024-01-01 02:00:00+00:00",
        entry_price=100.0, exit_price=104.0, stop_price=96.0,
        exit_reason="TP", bars_held_5m=12, atr_pct_entry=0.5,
    )
    trades = portfolio_replay([ev], scenario="realistic", starting_equity=1000.0)
    assert len(trades) == 1
    tr = trades[0]
    # risk budget must be exactly 0.5% of equity: 1000 * 0.005 = 5
    assert tr.qty * abs(ev.entry_price - ev.stop_price) == pytest.approx(5.0)
    assert tr.net_pnl < tr.gross_pnl  # costs always reduce pnl
    assert tr.cost > 0


def test_replay_rejects_other_risk_values():
    with pytest.raises(ValueError):
        portfolio_replay([], scenario="realistic", risk_per_trade=0.01)


def test_scenario_ordering_on_costs():
    ev = TradeEvent(
        family="f", config_id="c", asset="BTCUSDT", side="BUY",
        signal_time="2024-01-01 00:00:00+00:00",
        entry_time="2024-01-01 01:00:00+00:00",
        exit_time="2024-01-01 02:00:00+00:00",
        entry_price=100.0, exit_price=104.0, stop_price=96.0,
        exit_reason="TP", bars_held_5m=12, atr_pct_entry=0.5,
    )
    nets = {}
    for sc in ("optimistic", "realistic", "conservative", "severe"):
        nets[sc] = portfolio_replay([ev], scenario=sc)[0].net_pnl
    assert nets["optimistic"] > nets["realistic"] > nets["conservative"] > nets["severe"]


def test_guard_no_oos_drops_oos_rows():
    df15 = _mk_15m(n=100)
    cut = df15["datetime"].iloc[60]
    contract = SplitContract(
        input_hash="x",
        train_start=df15["datetime"].iloc[0],
        train_end=df15["datetime"].iloc[40],
        val_start=df15["datetime"].iloc[40],
        val_end=cut,
        oos_start=cut,
        oos_end=df15["datetime"].iloc[-1],
        lock_sha256="y",
    )
    out = guard_no_oos(df15, contract, "TEST")
    assert len(out) == 60
    assert (out["datetime"] < cut).all()
    assert out.attrs["oos_rows_dropped"] == 40


def test_compute_metrics_basics():
    evs = []
    for i, (exit_p, reason) in enumerate([(104.0, "TP"), (96.0, "SL"), (104.0, "TP")]):
        evs.append(
            TradeEvent(
                family="f", config_id="c", asset="BTCUSDT", side="BUY",
                signal_time=f"2024-01-0{i+1} 00:00:00+00:00",
                entry_time=f"2024-01-0{i+1} 01:00:00+00:00",
                exit_time=f"2024-01-0{i+1} 02:00:00+00:00",
                entry_price=100.0, exit_price=exit_p, stop_price=96.0,
                exit_reason=reason, bars_held_5m=12, atr_pct_entry=0.5,
            )
        )
    trades = portfolio_replay(evs, scenario="realistic")
    m = compute_metrics(trades, bars_in_window_15m=1000, n_signals=3)
    assert m["trades"] == 3
    assert m["wins"] == 2 and m["losses"] == 1
    assert m["profit_factor"] is not None and m["profit_factor"] > 1.0
    assert m["signal_density_per_1k_bars"] == pytest.approx(3.0)
    assert m["total_costs"] > 0
