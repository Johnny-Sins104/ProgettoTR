"""Characterization and regression tests for clean_bot — updated for TR-INT-02.

Tests that documented pre-TR-INT-02 defects now assert the CORRECTED behaviour.
The original defect descriptions are preserved in docstrings for traceability.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.clean_bot.backtest import _exit_position, _trade_from_signal
from trading_bot.clean_bot.models import BacktestSettings, Signal
from trading_bot.clean_bot import paper_live
from pathlib import Path

from trading_bot.clean_bot.paper_live import (
    CleanPaperSettings,
    _close_position,
    _create_pending_order,
    _default_state,
    _fill_pending_order,
    _read_state,
    _state_path,
)
from trading_bot.core.unified_trade_cost import UnifiedCostModel


def _signal(*, stop: float = 95.0, take_profit: float = 120.0) -> Signal:
    return Signal(
        strategy="characterization",
        side="BUY",
        score=1.0,
        reason="fixture",
        stop_price=stop,
        take_profit=take_profit,
        metadata={},
    )


def _frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["datetime"] = pd.date_range("2026-01-01", periods=len(frame), freq="5min", tz="UTC")
    return frame


def _paper_fill_via_pending(tmp_path, signal_row: pd.Series, fill_row: pd.Series, signal: Signal):
    """Create pending order at signal_row, fill at fill_row's Open."""
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state = _default_state(settings)
    pending = _create_pending_order(settings, state, signal, signal_row, str(signal_row["datetime"]))
    assert pending is not None, "expected pending_order to be created"
    fill_price = float(fill_row["Open"])
    position = _fill_pending_order(settings, state, fill_price, str(fill_row["datetime"]), 0.0)
    return position, state


def _backtest_trade(frame: pd.DataFrame, signal: Signal):
    return _trade_from_signal(
        df=frame,
        signal_idx=0,
        entry_idx=1,
        exit_idx=1,
        exit_price=110.0,
        exit_reason="FIXTURE",
        signal=signal,
        symbol="BTC/USDT",
        balance=100.0,
        settings=BacktestSettings(),
    )


# ---------------------------------------------------------------------------
# Backtest entry timing — was already correct, still correct
# ---------------------------------------------------------------------------

def test_characterize_backtest_entry_timing_already_uses_open_n1() -> None:
    """Backtest uses Open of bar N+1 — was correct pre-TR-INT-02, still correct."""
    frame = _frame([
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 105.0, "High": 111.0, "Low": 104.0, "Close": 109.0},
    ])
    trade = _backtest_trade(frame, _signal())
    assert trade.entry_price == 105.0
    assert trade.entry_time == str(frame.iloc[1]["datetime"])


# ---------------------------------------------------------------------------
# Paper entry timing — DEFECT CORRECTED in TR-INT-02
# ---------------------------------------------------------------------------

def test_paper_entry_uses_open_next_bar(tmp_path) -> None:
    """
    Defect (pre-TR-INT-02): paper used Close of signal bar N as entry.
    Fix: paper creates pending order; fill at Open of bar N+1.
    """
    frame = _frame([
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 105.0, "High": 111.0, "Low": 104.0, "Close": 109.0},
    ])
    position, _ = _paper_fill_via_pending(tmp_path, frame.iloc[0], frame.iloc[1], _signal())
    assert position is not None
    assert position["entry_price"] == 105.0       # Open of bar N+1
    assert position["signal_price"] == 102.0      # Close of bar N — stored for audit
    assert position["entry_price"] != position["signal_price"]


def test_paper_backtest_entry_now_parity(tmp_path) -> None:
    """
    Defect (pre-TR-INT-02): paper at Close N, backtest at Open N+1 → divergence.
    Fix: both fill at Open N+1 → parity.
    """
    frame = _frame([
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 105.0, "High": 111.0, "Low": 104.0, "Close": 109.0},
    ])
    signal = _signal()
    position, _ = _paper_fill_via_pending(tmp_path, frame.iloc[0], frame.iloc[1], signal)
    trade = _backtest_trade(frame, signal)
    assert position is not None
    assert position["entry_price"] == 105.0
    assert trade.entry_price == 105.0
    assert position["entry_price"] == trade.entry_price


# ---------------------------------------------------------------------------
# Gap handling — DEFECT CORRECTED in TR-INT-02
# ---------------------------------------------------------------------------

def test_backtest_gap_stop_fills_at_min_open_sl() -> None:
    """
    Defect (pre-TR-INT-02): gap-down stop filled at SL price (optimistic).
    Fix: fill at min(open, SL) → adversely correct.
    """
    frame = _frame([
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        {"Open": 90.0,  "High": 96.0,  "Low": 85.0, "Close": 91.0},
    ])
    exit_idx, exit_price, reason = _exit_position(
        frame,
        entry_idx=1,
        signal=_signal(stop=95.0, take_profit=120.0),
        settings=BacktestSettings(),
    )
    assert exit_idx == 1
    assert reason == "SL_GAP"
    assert exit_price == pytest.approx(min(float(frame.iloc[1]["Open"]), 95.0))  # min(90,95)=90
    assert exit_price < 95.0   # worse than declared SL
    assert exit_price == pytest.approx(90.0)


def test_paper_gap_stop_fills_at_min_open_sl(tmp_path, monkeypatch) -> None:
    """
    Defect (pre-TR-INT-02): paper gap-down stop filled at SL price (optimistic).
    Fix: fill at min(open, SL) = min(90, 95) = 90.
    """
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state = _default_state(settings)
    state["cash"] = 0.0
    state["position"] = {
        "position_id": "fixture",
        "symbol": settings.symbol,
        "side": "BUY",
        "qty": 1.0,
        "entry_price": 100.0,
        "entry_fee": 0.0,
        "cost_basis": 100.0,
        "stop_loss": 95.0,
        "stop_price_at_entry": 95.0,
        "take_profit": 120.0,
        "trail_atr_mult": 10.0,
        "atr_pct_at_entry": 0.0,
    }
    frame = _frame([{"Open": 90.0, "High": 96.0, "Low": 85.0, "Close": 91.0, "atr14": 1.0}])

    monkeypatch.setattr(paper_live, "_read_state", lambda _s: state)
    monkeypatch.setattr(paper_live, "_prepared_frame", lambda _s: (frame, "fixture"))
    monkeypatch.setattr(paper_live, "_signal", lambda _s, _f: (None, frame.iloc[0]))
    monkeypatch.setattr(paper_live, "_write_state", lambda _s, _st: None)
    monkeypatch.setattr(paper_live, "_emit", lambda *_a, **_k: None)
    monkeypatch.setattr(paper_live, "_send_telegram", lambda *_a, **_k: {"ok": False})

    report = paper_live.run_cycle(settings)
    closed = state["closed_trades"][-1]

    assert report["action"] == "CLOSE"
    assert closed["exit_price"] == pytest.approx(90.0)           # min(open=90, SL=95)
    assert closed["exit_price"] == pytest.approx(float(frame.iloc[0]["Open"]))
    assert closed["close_reason"] == "SL_GAP"


# ---------------------------------------------------------------------------
# Cost model — DEFECT CORRECTED in TR-INT-02
# ---------------------------------------------------------------------------

def test_clean_bot_backtest_cost_uses_unified_cost_model() -> None:
    """
    Defect (pre-TR-INT-02): cost was local flat-bps (13 bps, no UCM).
    Fix: cost comes from UnifiedCostModel; audit field cost_bps_applied is set.
    """
    frame = _frame([
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 105.0, "High": 111.0, "Low": 104.0, "Close": 109.0},
    ])
    trade = _backtest_trade(frame, _signal())

    # UCM populates audit fields; flat bps does not
    assert trade.cost_bps_applied is not None
    assert trade.entry_timing == "open_n1"

    # Cost must differ from old local flat-bps formula (13 bps conservative)
    old_flat_cost = abs(trade.qty * trade.entry_price) * 13.0 / 10000.0
    assert trade.cost != pytest.approx(old_flat_cost), (
        f"Expected UCM cost (not flat 13 bps). got={trade.cost:.8f} flat={old_flat_cost:.8f}"
    )


# ---------------------------------------------------------------------------
# Risk defaults — DEFECT CORRECTED in TR-INT-02
# ---------------------------------------------------------------------------

def test_clean_bot_risk_defaults_are_half_percent() -> None:
    """
    Defect (pre-TR-INT-02): both settings defaulted to risk_per_trade_pct = 0.01.
    Fix: both settings default to 0.005 (constraint in §0 baseline).
    """
    assert BacktestSettings().risk_per_trade_pct == 0.005
    assert CleanPaperSettings().risk_per_trade_pct == 0.005


# ---------------------------------------------------------------------------
# Backup fail-closed — DEFECT CORRECTED
# ---------------------------------------------------------------------------

def test_read_state_backup_write_failure_raises(tmp_path, monkeypatch) -> None:
    """_read_state must raise — not silently recover — when the .bak write fails.

    Fail-closed guarantee: no recovery proceeds without a verified backup.
    """
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state_file = _state_path(settings)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("this is not valid json {{{", encoding="utf-8")

    original_write_bytes = Path.write_bytes

    def fail_bak_write(self: Path, data: bytes) -> int:
        if self.suffix == ".bak":
            raise OSError("simulated disk-full on backup write")
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail_bak_write)

    with pytest.raises(OSError, match="simulated disk-full"):
        _read_state(settings)


def test_read_state_bak_not_created_after_silent_write_raises(tmp_path, monkeypatch) -> None:
    """_read_state must raise when write_bytes completes without error but the .bak is absent.

    Covers the fail-closed guard added after bak.write_bytes(): if the OS/filesystem
    silently swallows the write (no exception, no file), recovery must still be blocked.
    """
    settings = CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)
    state_file = _state_path(settings)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("this is not valid json {{{", encoding="utf-8")

    original_write_bytes = Path.write_bytes

    def silent_noop_for_bak(self: Path, data: bytes) -> int:
        if self.suffix == ".bak":
            return 0  # no-op: no exception, but .bak is never written to disk
        return original_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", silent_noop_for_bak)

    with pytest.raises(RuntimeError, match="backup file not created after write_bytes"):
        _read_state(settings)


# ---------------------------------------------------------------------------
# Close event cost breakdown — DEFECT CORRECTED
# ---------------------------------------------------------------------------

def test_close_event_fee_is_sum_of_entry_exit_fees_not_total_cost(tmp_path, monkeypatch) -> None:
    """CLEAN_POSITION_CLOSED: fee = fee_entry_amt + fee_exit_amt, distinct from slippage and total_cost_amt."""
    settings = CleanPaperSettings(data_dir=str(tmp_path), cost_model="conservative", telegram_enabled=False)
    state = _default_state(settings)
    state["cash"] = 100.0
    state["position"] = {
        "position_id": "fee_test",
        "symbol": settings.symbol,
        "side": "BUY",
        "qty": 1.0,
        "entry_price": 100.0,
        "entry_fee": 0.0,
        "cost_basis": 100.0,
        "stop_loss": 90.0,
        "stop_price_at_entry": 90.0,
        "take_profit": 120.0,
        "trail_atr_mult": 10.0,
        "atr_pct_at_entry": 0.02,
        "signal_reason": "",
        "metadata": {},
    }

    emitted: list[dict] = []
    monkeypatch.setattr(paper_live, "_emit", lambda _s, etype, **kw: emitted.append({"event_type": etype, **kw}))
    monkeypatch.setattr(paper_live, "_send_telegram", lambda *_a, **_k: {"ok": False})

    _close_position(settings, state, exit_price=110.0, reason="TP", bar_time="2026-01-01T00:00:00+00:00")

    close_events = [e for e in emitted if e["event_type"] == "CLEAN_POSITION_CLOSED"]
    assert len(close_events) == 1, f"expected 1 CLEAN_POSITION_CLOSED event, got {len(close_events)}"
    ev = close_events[0]

    outcome = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=100.0,
        exit_price=110.0,
        stop_price=90.0,
        quantity=1.0,
        scenario="conservative",
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        atr_pct=0.02,
    )

    expected_fee = round(outcome.fee_entry_amt + outcome.fee_exit_amt, 8)
    assert ev["fee"] == pytest.approx(expected_fee), (
        f"fee={ev['fee']!r} != fee_entry_amt+fee_exit_amt={expected_fee!r}"
    )
    # fee must be strictly less than total_cost (spread/slippage/latency/partial_fill add to total)
    assert ev["fee"] < outcome.total_cost_amt, (
        f"fee={ev['fee']} must be < total_cost_amt={outcome.total_cost_amt} "
        "(they are distinct: fee excludes spread, slippage, latency, partial_fill)"
    )
    # slippage is tracked separately in the event
    assert ev["slippage"] == pytest.approx(round(outcome.slippage_amt, 8)), (
        f"slippage={ev['slippage']!r} != outcome.slippage_amt={outcome.slippage_amt!r}"
    )
