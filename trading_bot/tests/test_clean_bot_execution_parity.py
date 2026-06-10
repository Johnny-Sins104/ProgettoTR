"""Execution parity and contract tests for TR-INT-02.

Verifies that after TR-INT-02:
  - entry is causal (pending → fill at next bar open)
  - paper and backtest fill at the same price on deterministic replay
  - gap handling policy is correctly applied in both runners
  - UnifiedCostModel is applied exactly once per trade
  - risk_per_trade_pct == 0.005 drives sizing in both runners
  - atomic save protects state from mid-write crashes
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from trading_bot.clean_bot.backtest import _exit_position, _trade_from_signal
from trading_bot.clean_bot.models import BacktestSettings, Signal
from trading_bot.clean_bot import paper_live
from trading_bot.clean_bot.paper_live import (
    CleanPaperSettings,
    _close_position,
    _create_pending_order,
    _default_state,
    _fill_pending_order,
    _read_state,
    _state_path,
    _write_state,
)
from trading_bot.core.unified_trade_cost import UnifiedCostModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sig(*, stop: float = 95.0, tp: float = 130.0, side: str = "BUY") -> Signal:
    return Signal(
        strategy="parity_test",
        side=side,
        score=1.0,
        reason="fixture",
        stop_price=stop,
        take_profit=tp,
        metadata={},
    )


def _frame(*rows: dict) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    df["datetime"] = pd.date_range("2026-01-01", periods=len(df), freq="5min", tz="UTC")
    return df


def _open_via_pending(settings, state, signal_row, fill_row, signal):
    """Create pending at signal_row, fill at fill_row Open."""
    pending = _create_pending_order(
        settings, state, signal, signal_row, str(signal_row["datetime"])
    )
    assert pending is not None
    return _fill_pending_order(
        settings, state, float(fill_row["Open"]), str(fill_row["datetime"]), 0.0
    )


# ---------------------------------------------------------------------------
# Causal entry contract
# ---------------------------------------------------------------------------

def test_entry_is_causal(tmp_path) -> None:
    """Signal produces pending_order only. Position is created at a strictly future price."""
    settings = CleanPaperSettings(data_dir=str(tmp_path))
    state = _default_state(settings)
    signal_row = _frame({"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0}).iloc[0]
    signal = _sig(stop=95.0)

    pending = _create_pending_order(settings, state, signal, signal_row, str(signal_row["datetime"]))

    assert pending is not None
    assert state["position"] is None           # no position yet
    assert state["pending_order"] is not None  # intent recorded

    fill_price = 105.0
    assert fill_price != float(signal_row["Close"])  # fill ≠ signal Close

    pos = _fill_pending_order(settings, state, fill_price, "2026-01-01T00:05:00+00:00", 0.0)

    assert pos is not None
    assert pos["entry_price"] == fill_price   # filled at next-bar open
    assert state.get("pending_order") is None  # intent consumed (key popped by _fill)
    assert state["position"] is not None


def test_rest_paper_does_not_retrofill_open_n1(tmp_path) -> None:
    """Paper fill price ≠ signal bar Close. Fill is the Open of a subsequent bar."""
    settings = CleanPaperSettings(data_dir=str(tmp_path))
    state = _default_state(settings)
    signal_close = 102.0
    next_open = 105.0

    signal = _sig(stop=95.0)
    signal_row = _frame({"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": signal_close}).iloc[0]

    _create_pending_order(settings, state, signal, signal_row, str(signal_row["datetime"]))
    pos = _fill_pending_order(settings, state, next_open, "2026-01-01T00:05:00+00:00", 0.0)

    assert pos is not None
    assert pos["entry_price"] != signal_close   # not retrodate
    assert pos["entry_price"] == next_open       # future price
    assert pos["signal_price"] == signal_close   # audit: original signal close preserved


# ---------------------------------------------------------------------------
# Replay parity: paper fill == backtest fill
# ---------------------------------------------------------------------------

def test_replay_paper_backtest_parity(tmp_path) -> None:
    """On deterministic replay, paper fill price equals backtest Open N+1."""
    df = _frame(
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 105.0, "High": 111.0, "Low": 104.0, "Close": 109.0},
    )
    signal = _sig(stop=95.0, tp=130.0)

    # Paper: pending at bar 0, fill at bar 1 Open
    settings = CleanPaperSettings(data_dir=str(tmp_path), symbol="XRP/USDT")
    state = _default_state(settings)
    paper_pos = _open_via_pending(settings, state, df.iloc[0], df.iloc[1], signal)

    # Backtest: entry_idx = signal_idx + 1 = 1
    bt_settings = BacktestSettings(symbol="XRP/USDT", timeframe="5m", cost_model="conservative")
    bt_trade = _trade_from_signal(
        df=df, signal_idx=0, entry_idx=1, exit_idx=1,
        exit_price=float(df.iloc[1]["Close"]),
        exit_reason="TP", signal=signal,
        symbol="XRP/USDT", balance=settings.balance, settings=bt_settings,
    )

    assert paper_pos is not None
    assert paper_pos["entry_price"] == bt_trade.entry_price   # both at 105.0


def test_paper_backtest_net_pnl_parity(tmp_path) -> None:
    """Paper and backtest produce identical net_pnl when closed at same exit price."""
    df = _frame(
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 105.0, "High": 111.0, "Low": 104.0, "Close": 109.0},
    )
    signal = _sig(stop=95.0, tp=130.0)
    exit_price = 109.0

    # Paper
    settings = CleanPaperSettings(data_dir=str(tmp_path), symbol="XRP/USDT")
    state = _default_state(settings)
    state["cash"] = settings.balance
    paper_pos = _open_via_pending(settings, state, df.iloc[0], df.iloc[1], signal)
    assert paper_pos is not None
    _close_position(settings, state, exit_price, "TP", "2026-01-01T00:10:00+00:00")
    paper_pnl = state["closed_trades"][-1]["realized_pnl"]

    # Backtest
    bt_settings = BacktestSettings(symbol="XRP/USDT", timeframe="5m", cost_model="conservative")
    bt_trade = _trade_from_signal(
        df=df, signal_idx=0, entry_idx=1, exit_idx=1,
        exit_price=exit_price, exit_reason="TP", signal=signal,
        symbol="XRP/USDT", balance=settings.balance, settings=bt_settings,
    )

    # Both use UCM with identical inputs → identical net_pnl
    assert paper_pnl == pytest.approx(bt_trade.net_pnl, rel=1e-5)


# ---------------------------------------------------------------------------
# Gap handling: backtest
# ---------------------------------------------------------------------------

def test_gap_long_stop_fill_backtest() -> None:
    """BUY gap-down through SL: fill at min(open, SL), reason SL_GAP."""
    df = _frame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        {"Open": 90.0,  "High": 96.0,  "Low": 85.0, "Close": 91.0},
    )
    _, exit_price, reason = _exit_position(
        df, entry_idx=1, signal=_sig(stop=95.0, tp=120.0), settings=BacktestSettings()
    )
    assert reason == "SL_GAP"
    assert exit_price == pytest.approx(min(90.0, 95.0))   # min(open, SL) = 90
    assert exit_price < 95.0   # worse than declared SL


def test_gap_short_stop_fill_backtest() -> None:
    """SELL gap-up through SL: fill at max(open, SL), reason SL_GAP."""
    df = _frame(
        {"Open": 105.0, "High": 106.0, "Low": 104.0, "Close": 105.0},
        {"Open": 115.0, "High": 116.0, "Low": 114.0, "Close": 115.0},
    )
    _, exit_price, reason = _exit_position(
        df, entry_idx=1,
        signal=_sig(stop=110.0, tp=90.0, side="SELL"),
        settings=BacktestSettings(),
    )
    assert reason == "SL_GAP"
    assert exit_price == pytest.approx(max(115.0, 110.0))  # max(open, SL) = 115
    assert exit_price > 110.0   # worse than declared SL for SELL


def test_gap_tp_conservative_backtest() -> None:
    """BUY gap-up through TP: fill at TP (not open). Conservative — no gap profit."""
    df = _frame(
        {"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0},
        {"Open": 120.0, "High": 125.0, "Low": 119.0, "Close": 121.0},
    )
    _, exit_price, reason = _exit_position(
        df, entry_idx=1, signal=_sig(stop=90.0, tp=115.0), settings=BacktestSettings()
    )
    assert reason == "TP_GAP"
    assert exit_price == pytest.approx(115.0)                    # fill at TP
    assert exit_price < float(df.iloc[1]["Open"])                # conservative: not at gap open


def test_sl_tp_same_candle_sl_wins_backtest() -> None:
    """SL and TP both hit in same candle: SL wins (worst-case, conservative)."""
    df = _frame(
        {"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0},
        {"Open": 101.0, "High": 112.0, "Low": 93.0, "Close": 100.0},
    )
    _, exit_price, reason = _exit_position(
        df, entry_idx=1, signal=_sig(stop=95.0, tp=110.0), settings=BacktestSettings()
    )
    assert reason == "SL_SAME_BAR"
    assert exit_price == pytest.approx(95.0)   # SL, not TP


# ---------------------------------------------------------------------------
# Gap handling: paper
# ---------------------------------------------------------------------------

def test_gap_long_stop_fill_paper(tmp_path, monkeypatch) -> None:
    """BUY paper gap-down: closed at min(open, SL) with reason SL_GAP."""
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state = _default_state(settings)
    state["cash"] = 0.0
    state["position"] = {
        "position_id": "fix", "symbol": settings.symbol, "side": "BUY",
        "qty": 1.0, "entry_price": 100.0, "entry_fee": 0.0, "cost_basis": 100.0,
        "stop_loss": 95.0, "stop_price_at_entry": 95.0,
        "take_profit": 120.0, "trail_atr_mult": 10.0, "atr_pct_at_entry": 0.0,
    }
    frame = _frame({"Open": 90.0, "High": 96.0, "Low": 85.0, "Close": 91.0, "atr14": 1.0})

    _mock_cycle(monkeypatch, state, frame)
    report = paper_live.run_cycle(settings)
    closed = state["closed_trades"][-1]

    assert report["action"] == "CLOSE"
    assert closed["close_reason"] == "SL_GAP"
    assert closed["exit_price"] == pytest.approx(min(90.0, 95.0))   # 90.0


def test_gap_tp_conservative_paper(tmp_path, monkeypatch) -> None:
    """BUY paper gap-up through TP: fill at TP, not at open. Reason TP_GAP."""
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state = _default_state(settings)
    state["cash"] = 0.0
    state["position"] = {
        "position_id": "fix", "symbol": settings.symbol, "side": "BUY",
        "qty": 1.0, "entry_price": 100.0, "entry_fee": 0.0, "cost_basis": 100.0,
        "stop_loss": 90.0, "stop_price_at_entry": 90.0,
        "take_profit": 115.0, "trail_atr_mult": 10.0, "atr_pct_at_entry": 0.0,
    }
    frame = _frame({"Open": 120.0, "High": 125.0, "Low": 119.0, "Close": 121.0, "atr14": 1.0})

    _mock_cycle(monkeypatch, state, frame)
    paper_live.run_cycle(settings)
    closed = state["closed_trades"][-1]

    assert closed["close_reason"] == "TP_GAP"
    assert closed["exit_price"] == pytest.approx(115.0)            # TP, not open=120


def test_sl_tp_same_candle_sl_wins_paper(tmp_path, monkeypatch) -> None:
    """Paper: SL and TP both in same candle → SL wins."""
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state = _default_state(settings)
    state["cash"] = 0.0
    state["position"] = {
        "position_id": "fix", "symbol": settings.symbol, "side": "BUY",
        "qty": 1.0, "entry_price": 100.0, "entry_fee": 0.0, "cost_basis": 100.0,
        "stop_loss": 95.0, "stop_price_at_entry": 95.0,
        "take_profit": 110.0, "trail_atr_mult": 10.0, "atr_pct_at_entry": 0.0,
    }
    frame = _frame({"Open": 101.0, "High": 112.0, "Low": 93.0, "Close": 100.0, "atr14": 1.0})

    _mock_cycle(monkeypatch, state, frame)
    paper_live.run_cycle(settings)
    closed = state["closed_trades"][-1]

    assert closed["close_reason"] == "SL_SAME_BAR"
    assert closed["exit_price"] == pytest.approx(95.0)


# ---------------------------------------------------------------------------
# Cost ownership: UCM applied exactly once
# ---------------------------------------------------------------------------

def test_cost_applied_once(tmp_path, monkeypatch) -> None:
    """UnifiedCostModel.compute_trade_outcome is called exactly once per close."""
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state = _default_state(settings)
    state["cash"] = 0.0
    state["position"] = {
        "position_id": "fix", "symbol": settings.symbol, "side": "BUY",
        "qty": 1.0, "entry_price": 100.0, "entry_fee": 0.0, "cost_basis": 100.0,
        "stop_loss": 95.0, "stop_price_at_entry": 95.0,
        "take_profit": 120.0, "trail_atr_mult": 10.0, "atr_pct_at_entry": 0.0,
    }
    frame = _frame({"Open": 90.0, "High": 96.0, "Low": 85.0, "Close": 91.0, "atr14": 1.0})

    ucm_calls = [0]
    original_ucm = UnifiedCostModel.compute_trade_outcome

    def counting_ucm(*, side, entry_price, exit_price, stop_price, quantity, **kwargs):
        ucm_calls[0] += 1
        return original_ucm(
            side=side, entry_price=entry_price, exit_price=exit_price,
            stop_price=stop_price, quantity=quantity, **kwargs,
        )

    monkeypatch.setattr(UnifiedCostModel, "compute_trade_outcome", staticmethod(counting_ucm))
    _mock_cycle(monkeypatch, state, frame)
    paper_live.run_cycle(settings)

    assert ucm_calls[0] == 1, f"Expected UCM called once, got {ucm_calls[0]}"


# ---------------------------------------------------------------------------
# Risk sizing: 0.005 × capital
# ---------------------------------------------------------------------------

def test_risk_per_trade_is_0005_backtest() -> None:
    """BacktestSettings.risk_per_trade_pct = 0.005 drives position sizing."""
    settings = BacktestSettings(symbol="XRP/USDT")
    assert settings.risk_per_trade_pct == 0.005

    df = _frame(
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 105.0, "High": 111.0, "Low": 104.0, "Close": 109.0},
    )
    trade = _trade_from_signal(
        df=df, signal_idx=0, entry_idx=1, exit_idx=1,
        exit_price=110.0, exit_reason="TP",
        signal=_sig(stop=95.0), symbol="XRP/USDT",
        balance=100.0, settings=settings,
    )
    expected_qty = (100.0 * 0.005) / abs(105.0 - 95.0)   # 0.5 / 10 = 0.05
    assert trade.qty == pytest.approx(expected_qty, rel=1e-6)


def test_risk_per_trade_is_0005_paper(tmp_path) -> None:
    """CleanPaperSettings.risk_per_trade_pct = 0.005 drives position sizing."""
    settings = CleanPaperSettings(data_dir=str(tmp_path))
    assert settings.risk_per_trade_pct == 0.005

    state = _default_state(settings)
    state["pending_order"] = {
        "signal_price": 102.0, "signal_bar": "2026-01-01T00:00:00+00:00",
        "stop_price": 95.0, "take_profit": 130.0,
        "strategy": "test", "reason": "fixture",
        "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00",
    }
    pos = _fill_pending_order(settings, state, 105.0, "2026-01-01T00:05:00+00:00", 0.0)
    assert pos is not None

    expected_qty = (100.0 * 0.005) / abs(105.0 - 95.0)
    assert pos["qty"] == pytest.approx(expected_qty, rel=1e-6)


# ---------------------------------------------------------------------------
# Atomic save
# ---------------------------------------------------------------------------

def test_atomic_save_no_tmp_remains_after_success(tmp_path) -> None:
    """After a successful write, the .tmp file does not persist."""
    settings = CleanPaperSettings(data_dir=str(tmp_path))
    _write_state(settings, _default_state(settings))

    tmp = _state_path(settings).with_suffix(".tmp")
    assert not tmp.exists(), ".tmp must not persist after a successful atomic write"
    assert _state_path(settings).exists()


def test_atomic_save_previous_state_intact_on_write_error(tmp_path, monkeypatch) -> None:
    """If write to .tmp fails mid-stream, the original state file is untouched."""
    settings = CleanPaperSettings(data_dir=str(tmp_path))

    initial = _default_state(settings)
    initial["cash"] = 99.0
    _write_state(settings, initial)

    original_write_text = Path.write_text
    tmp_write_calls = [0]

    def failing_write_text(self, data, *args, **kwargs):
        if str(self).endswith(".tmp"):
            tmp_write_calls[0] += 1
            if tmp_write_calls[0] == 1:
                raise OSError("simulated crash during .tmp write")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    corrupt = _default_state(settings)
    corrupt["cash"] = 1.0
    with pytest.raises(OSError):
        _write_state(settings, corrupt)

    recovered = _read_state(settings)
    assert recovered["cash"] == 99.0, "Original state corrupted by failed atomic write"


# ---------------------------------------------------------------------------
# Internal helper for paper cycle mocking
# ---------------------------------------------------------------------------

def _mock_cycle(monkeypatch, state: dict, frame: pd.DataFrame) -> None:
    """Patch _read_state, _prepared_frame, _signal, _write_state, _emit, _send_telegram."""
    monkeypatch.setattr(paper_live, "_read_state", lambda _s: state)
    monkeypatch.setattr(paper_live, "_prepared_frame", lambda _s: (frame, "fixture"))
    monkeypatch.setattr(paper_live, "_signal", lambda _s, _f: (None, frame.iloc[0]))
    monkeypatch.setattr(paper_live, "_write_state", lambda _s, _st: None)
    monkeypatch.setattr(paper_live, "_emit", lambda *_a, **_k: None)
    monkeypatch.setattr(paper_live, "_send_telegram", lambda *_a, **_k: {"ok": False})
