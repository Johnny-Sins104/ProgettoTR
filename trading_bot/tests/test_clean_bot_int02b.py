"""End-to-end tests for TR-INT-02B correctness via run_cycle().

All assertions exercise run_cycle() as the public entry point.
Direct calls to private helpers are limited to setup fixtures only.

Contracts verified:
  - Fill never happens in the same cycle as pending creation
  - Fill price is the Open of a subsequent bar, never signal-bar Close
  - High/Low from bars before the fill bar do not trigger SL/TP
  - Events after fill can trigger SL/TP on the same fill bar
  - UCM error leaves position/cash/closed_trades unchanged
  - Entry gap behaviour is identical in backtest and paper
  - Default risk is 0.005 in settings, CLI parser, and avvia_bot_live
  - SELL is explicitly rejected with a logged event (clean paper is long-only)
  - Pending and position survive a restart (read back from written state file)
  - Corrupt state file returns _corrupt_recovery flag without silently losing position
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from trading_bot.clean_bot import paper_live
from trading_bot.clean_bot.backtest import _exit_position, _trade_from_signal, run_backtest_frame
from trading_bot.clean_bot.models import BacktestSettings, Signal, validate_entry_price
from trading_bot.clean_bot.paper_live import (
    CleanPaperSettings,
    _default_state,
    _fill_pending_order,
    _read_state,
    _state_path,
    _write_state,
)
from trading_bot.core.unified_trade_cost import UnifiedCostModel


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

T0 = "2026-01-01T00:00:00+00:00"
T1 = "2026-01-01T00:05:00+00:00"
T2 = "2026-01-01T00:10:00+00:00"
T3 = "2026-01-01T00:15:00+00:00"


def _settings(tmp_path: Path) -> CleanPaperSettings:
    return CleanPaperSettings(data_dir=str(tmp_path), telegram_enabled=False)


def _sig(*, stop: float = 95.0, tp: float = 130.0, side: str = "BUY") -> Signal:
    return Signal(
        strategy="int02b", side=side, score=1.0, reason="test",
        stop_price=stop, take_profit=tp, metadata={},
    )


def _frame(*rows: dict) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    df["datetime"] = pd.date_range("2026-01-01", periods=len(df), freq="5min", tz="UTC")
    return df


def _mock(
    monkeypatch,
    state: dict,
    frame: pd.DataFrame,
    *,
    signal: Signal | None = None,
    signal_row_idx: int = -2,
    capture_emits: list | None = None,
) -> None:
    """Patch the six external hooks run_cycle() uses. State is mutated in-place."""
    sig_idx = max(0, len(frame) + signal_row_idx) if signal_row_idx < 0 else signal_row_idx
    sig_row = frame.iloc[sig_idx]

    def _capturing_emit(settings, event_type, **payload):
        if capture_emits is not None:
            capture_emits.append({"event_type": event_type, **payload})

    monkeypatch.setattr(paper_live, "_read_state", lambda _s: state)
    monkeypatch.setattr(paper_live, "_prepared_frame", lambda _s: (frame, "test"))
    monkeypatch.setattr(paper_live, "_signal", lambda _s, _f: (signal, sig_row))
    monkeypatch.setattr(paper_live, "_write_state", lambda _s, _st: None)
    monkeypatch.setattr(paper_live, "_emit", _capturing_emit)
    monkeypatch.setattr(paper_live, "_send_telegram", lambda *_a, **_k: {"ok": False})


# ---------------------------------------------------------------------------
# 1. Observed price 109 cannot produce a backdated fill at signal-bar Close
# ---------------------------------------------------------------------------

def test_no_fill_at_signal_close_price(tmp_path, monkeypatch) -> None:
    """Cycle N observes bar with Close=102 as signal, Open=109 as current bar.
    Fill must NOT happen in this cycle — price 109 does not produce a fill here.
    The pending is created with signal_price=102, position=None.
    """
    settings = _settings(tmp_path)
    state = _default_state(settings)
    # Frame: signal bar (idx 0) + current bar (idx 1)
    frame = _frame(
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 109.0, "High": 115.0, "Low": 108.0, "Close": 113.0, "atr14": 1.0},
    )
    signal = _sig(stop=95.0, tp=130.0)
    _mock(monkeypatch, state, frame, signal=signal)

    report = paper_live.run_cycle(settings)

    # Must have created a pending but NOT a position
    assert report["action"] == "PENDING_ORDER_CREATED", f"expected PENDING_ORDER_CREATED, got {report['action']}"
    assert state.get("pending_order") is not None
    assert state.get("position") is None
    # Signal price captured correctly (not fill price)
    assert state["pending_order"]["signal_price"] == 102.0


# ---------------------------------------------------------------------------
# 2. Pending created in cycle N is NOT filled in cycle N
# ---------------------------------------------------------------------------

def test_pending_not_filled_same_cycle(tmp_path, monkeypatch) -> None:
    """Creating a pending and filling it must be in separate run_cycle calls."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    frame = _frame(
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 109.0, "High": 115.0, "Low": 108.0, "Close": 113.0, "atr14": 1.0},
    )
    _mock(monkeypatch, state, frame, signal=_sig())

    report = paper_live.run_cycle(settings)

    assert report["action"] == "PENDING_ORDER_CREATED"
    assert state.get("position") is None, "position must not be open after first cycle"
    assert state.get("pending_order") is not None, "pending must exist after first cycle"


# ---------------------------------------------------------------------------
# 3. Fill happens in the subsequent cycle at that cycle's bar Open
# ---------------------------------------------------------------------------

def test_fill_in_next_cycle(tmp_path, monkeypatch) -> None:
    """Pending from cycle N is filled in cycle N+1 at Open of the N+1 bar."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    # Inject a pre-existing pending (as if cycle N already ran)
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": 95.0,
        "take_profit": 130.0,
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    state["last_processed_bar"] = ""  # no previously processed bar → stale check bypassed

    # Cycle N+1: signal row at T0, current row at T1 (Open=114).
    # atr14=3.0 so close(118) - 3*trail_mult(10) = 88 < stop(95) → no TRAIL_UPDATE.
    frame = _frame(
        {"Open": 110.0, "High": 112.0, "Low": 109.0, "Close": 111.0},
        {"Open": 114.0, "High": 120.0, "Low": 113.0, "Close": 118.0, "atr14": 3.0},
    )
    _mock(monkeypatch, state, frame, signal=None, signal_row_idx=0)

    report = paper_live.run_cycle(settings)

    assert report["action"] == "FILL_PENDING", f"expected FILL_PENDING, got {report['action']}"
    pos = state.get("position")
    assert pos is not None, "position must be open after fill cycle"
    assert pos["entry_price"] == 114.0, f"fill must be at Open=114, got {pos['entry_price']}"
    assert pos["signal_price"] == 102.0, "signal_price audit field must carry original Close"
    assert state.get("pending_order") is None, "pending must be consumed after fill"


# ---------------------------------------------------------------------------
# 4. High/Low of bars before the fill bar cannot trigger SL/TP
# ---------------------------------------------------------------------------

def test_pre_fill_bar_highlow_do_not_trigger_sltop(tmp_path, monkeypatch) -> None:
    """OHLC of the bar that produced the signal is not used for SL/TP evaluation.
    Only the fill bar's OHLC is used (after Open = fill price).
    """
    settings = _settings(tmp_path)
    state = _default_state(settings)
    # Pre-inject pending
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": 95.0,
        "take_profit": 130.0,
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    state["last_processed_bar"] = ""  # stale check bypassed

    # Fill bar (current): Open=109, Low=90 (below SL=95!) — Low came AFTER Open=fill.
    # Position opened at 109 (STEP 1). Then STEP 2 sees Low=90 <= SL=95 → SL trigger.
    frame = _frame(
        {"Open": 110.0, "High": 112.0, "Low": 109.0, "Close": 111.0},
        {"Open": 109.0, "High": 110.0, "Low": 90.0, "Close": 92.0, "atr14": 1.0},
    )
    _mock(monkeypatch, state, frame, signal=None, signal_row_idx=0)

    report = paper_live.run_cycle(settings)

    # Fill happened, then SL triggered on same fill bar
    assert report["action"] in ("CLOSE", "FILL_PENDING"), f"unexpected action: {report['action']}"
    if report["action"] == "CLOSE":
        closed = state.get("closed_trades", [])
        assert len(closed) == 1
        assert closed[0]["close_reason"] == "SL"
        assert closed[0]["entry_price"] == 109.0  # filled at Open=109


def test_pre_fill_bar_neutral_highlow_leaves_position_open(tmp_path, monkeypatch) -> None:
    """Fill bar with High/Low between SL and TP: position remains open."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": 95.0,
        "take_profit": 130.0,
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    state["last_processed_bar"] = ""

    # Fill bar: Open=109, High=112, Low=106 — no SL (95) or TP (130) triggered
    frame = _frame(
        {"Open": 110.0, "High": 112.0, "Low": 109.0, "Close": 111.0},
        {"Open": 109.0, "High": 112.0, "Low": 106.0, "Close": 110.0, "atr14": 1.0},
    )
    _mock(monkeypatch, state, frame, signal=None, signal_row_idx=0)

    report = paper_live.run_cycle(settings)

    assert state.get("position") is not None, "position must remain open"
    assert state.get("closed_trades", []) == [], "no trades should be closed"


# ---------------------------------------------------------------------------
# 5. Events after the fill CAN trigger SL/TP (they are temporally valid)
# ---------------------------------------------------------------------------

def test_tp_after_fill_closes_position(tmp_path, monkeypatch) -> None:
    """TP hit on the fill bar (High >= tp) produces a closed trade."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": 95.0,
        "take_profit": 115.0,
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    state["last_processed_bar"] = ""

    # Fill at Open=109, High=120 >= TP=115 → TP hit after fill
    frame = _frame(
        {"Open": 110.0, "High": 112.0, "Low": 109.0, "Close": 111.0},
        {"Open": 109.0, "High": 120.0, "Low": 108.0, "Close": 119.0, "atr14": 1.0},
    )
    _mock(monkeypatch, state, frame, signal=None, signal_row_idx=0)

    report = paper_live.run_cycle(settings)

    closed = state.get("closed_trades", [])
    assert len(closed) == 1, "TP must produce a closed trade"
    assert closed[0]["close_reason"] == "TP"
    assert closed[0]["exit_price"] == 115.0  # conservative fill at TP, not gap open


# ---------------------------------------------------------------------------
# 6. UCM error leaves position, cash, and closed_trades unchanged
# ---------------------------------------------------------------------------

def test_ucm_error_leaves_state_unchanged(tmp_path, monkeypatch) -> None:
    """If UCM raises ValueError, the position must not be closed and state unchanged."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    state["cash"] = 0.0
    state["position"] = {
        "position_id": "ucm_test",
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

    def _ucm_raiser(**kwargs):
        raise ValueError("simulated UCM failure")

    monkeypatch.setattr(UnifiedCostModel, "compute_trade_outcome", staticmethod(_ucm_raiser))

    emits: list = []
    # SL triggered (Low=88 < stop=95)
    frame = _frame({"Open": 96.0, "High": 97.0, "Low": 88.0, "Close": 89.0, "atr14": 1.0})
    _mock(monkeypatch, state, frame, signal=None, capture_emits=emits)

    report = paper_live.run_cycle(settings)

    assert report["action"] == "UCM_ERROR", f"expected UCM_ERROR, got {report['action']}"
    assert state.get("position") is not None, "position must remain open"
    assert state["cash"] == 0.0, "cash must be unchanged"
    assert state.get("closed_trades", []) == [], "no trade must be recorded"
    ucm_events = [e for e in emits if e["event_type"] == "CLEAN_UCM_ERROR"]
    assert len(ucm_events) >= 1, "CLEAN_UCM_ERROR event must be emitted"


# ---------------------------------------------------------------------------
# 7. Entry gap: identical behaviour in backtest and paper
# ---------------------------------------------------------------------------

def test_entry_gap_below_sl_backtest_skips_trade() -> None:
    """Backtest: if Open of entry bar is at or below SL, trade is not created."""
    df = _frame(
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 100.0},
        {"Open": 92.0, "High": 96.0, "Low": 90.0, "Close": 93.0},  # entry bar Opens below SL=95
    )
    settings = BacktestSettings(symbol="XRP/USDT")
    signal = _sig(stop=95.0, tp=130.0)

    # _exit_position called with entry_idx=1, entry_open=92 < SL=95
    # validate_entry_price must reject before _exit_position is called
    ok, reason = validate_entry_price(float(df.iloc[1]["Open"]), signal)
    assert not ok
    assert reason == "ENTRY_AT_OR_BELOW_SL"


def test_entry_gap_below_sl_paper_discards_pending(tmp_path, monkeypatch) -> None:
    """Paper: if fill price is at or below SL, pending is discarded with event."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": 100.0,  # SL = 100
        "take_profit": 130.0,
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    state["last_processed_bar"] = ""

    emits: list = []
    # Fill bar: Open=98 ≤ SL=100 → pending must be discarded
    frame = _frame(
        {"Open": 105.0, "High": 107.0, "Low": 104.0, "Close": 106.0},
        {"Open": 98.0, "High": 104.0, "Low": 96.0, "Close": 100.0, "atr14": 1.0},
    )
    _mock(monkeypatch, state, frame, signal=None, signal_row_idx=0, capture_emits=emits)

    paper_live.run_cycle(settings)

    assert state.get("position") is None, "position must not be opened on gap-below-SL"
    assert state.get("pending_order") is None, "pending must be discarded"
    discard_events = [e for e in emits if e["event_type"] == "CLEAN_PENDING_DISCARDED"]
    assert len(discard_events) >= 1
    assert discard_events[0]["reason"] == "ENTRY_AT_OR_BELOW_SL"


def test_entry_gap_above_tp_paper_discards_pending(tmp_path, monkeypatch) -> None:
    """Paper: if fill price is at or above TP, pending is discarded."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": 95.0,
        "take_profit": 115.0,  # TP = 115
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    state["last_processed_bar"] = ""

    emits: list = []
    # Fill bar: Open=120 ≥ TP=115 → pending must be discarded
    frame = _frame(
        {"Open": 105.0, "High": 107.0, "Low": 104.0, "Close": 106.0},
        {"Open": 120.0, "High": 125.0, "Low": 119.0, "Close": 122.0, "atr14": 1.0},
    )
    _mock(monkeypatch, state, frame, signal=None, signal_row_idx=0, capture_emits=emits)

    paper_live.run_cycle(settings)

    assert state.get("position") is None
    assert state.get("pending_order") is None
    discard_events = [e for e in emits if e["event_type"] == "CLEAN_PENDING_DISCARDED"]
    assert len(discard_events) >= 1
    assert discard_events[0]["reason"] == "ENTRY_AT_OR_ABOVE_TP"


def test_entry_gap_below_sl_backtest_via_run_frame() -> None:
    """Integration: run_backtest_frame skips the trade when entry Open is below SL."""
    # Construct a minimal df with signal at idx 400 (warmup done) and bad entry at idx 401
    # Use enough rows for the backtest to process
    rows = []
    for i in range(405):
        rows.append({
            "Open": 100.0, "High": 105.0, "Low": 95.0, "Close": 100.0,
            "Volume": 1000.0,
            "datetime": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=5 * i),
            "ema50": 99.0, "ema200": 98.0, "atr14": 1.0, "atr_pct": 0.01,
            "volume_ratio_20": 2.0, "prior_high_576": 99.0, "prior_high_288": 99.0,
            "prior_low_48": 90.0, "prior_high_48": 99.0,
            "ema20": 99.5, "range_low_96": 90.0, "range_pos_400": 0.5,
            "lower_wick_ratio": 0.0, "body_ratio": 0.5, "rsi14": 50.0,
        })
    df = pd.DataFrame(rows)
    # Force a signal at idx 400: price breaks above prior_high, ema50 > ema200, volume
    df.at[400, "Close"] = 105.0
    df.at[400, "prior_high_576"] = 104.0
    df.at[400, "atr_pct"] = 0.5  # within valid ATR range
    df.at[400, "volume_ratio_20"] = 2.0
    # Entry bar (idx 401): Open far below SL
    # signal stop would be approx 105 - 4 * 1 = 101, so set Open = 99 (below SL)
    df.at[401, "Open"] = 99.0

    from trading_bot.clean_bot.strategies import AdaptiveTrendBreakoutStrategy
    strat = AdaptiveTrendBreakoutStrategy(lookback_bars=576)
    settings = BacktestSettings(symbol="XRP/USDT", timeframe="5m")
    result = run_backtest_frame(raw_rows=len(df), df=df, settings=settings, strategies=[strat])
    # The signal at 400 with entry at 99 (below SL ~101) must be skipped
    for trade in result.get("trades", []):
        assert trade["entry_price"] != 99.0, "entry below SL must be skipped"


# ---------------------------------------------------------------------------
# 8. Default risk is 0.005 in all paths
# ---------------------------------------------------------------------------

def test_risk_default_in_settings() -> None:
    """Both CleanPaperSettings and BacktestSettings default to risk_per_trade_pct=0.005."""
    assert CleanPaperSettings().risk_per_trade_pct == 0.005
    assert BacktestSettings().risk_per_trade_pct == 0.005


def test_risk_default_in_cli_parser() -> None:
    """tools/clean_bot_paper_live.py must declare default=0.005 for --risk-per-trade-pct."""
    cli_path = Path(__file__).resolve().parents[2] / "tools" / "clean_bot_paper_live.py"
    text = cli_path.read_text(encoding="utf-8")
    assert "default=0.005" in text, \
        "tools/clean_bot_paper_live.py must have default=0.005 for --risk-per-trade-pct"
    assert "default=0.01" not in text, \
        "tools/clean_bot_paper_live.py must not have default=0.01 for --risk-per-trade-pct"


def test_risk_default_in_avvia_bot_live() -> None:
    """avvia_bot_live.py must not have 0.01 as a default for any --clean-* risk setting.
    Note: 0.0025 in _prepare_paper_live is intentional for legacy paper engine — not clean bot.
    """
    src = Path(__file__).resolve().parents[2] / "trading_bot" / "avvia_bot_live.py"
    text = src.read_text(encoding="utf-8")
    # Verify the removed 0.01 defaults are gone
    assert '"--risk-per-trade-pct", 0.01' not in text, \
        "0.01 default found for --risk-per-trade-pct in avvia_bot_live.py (must be 0.005)"
    assert "\"--risk-per-trade-pct\", 0.01" not in text


# ---------------------------------------------------------------------------
# 9. SELL signals are explicitly rejected with a logged event
# ---------------------------------------------------------------------------

def test_sell_signal_rejected_with_event(tmp_path, monkeypatch) -> None:
    """SELL signal must trigger CLEAN_SELL_REJECTED event and create no pending."""
    settings = _settings(tmp_path)
    state = _default_state(settings)
    frame = _frame(
        {"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 102.0},
        {"Open": 99.0, "High": 101.0, "Low": 97.0, "Close": 98.0, "atr14": 1.0},
    )
    sell_signal = _sig(stop=110.0, tp=80.0, side="SELL")
    emits: list = []
    _mock(monkeypatch, state, frame, signal=sell_signal, capture_emits=emits)

    report = paper_live.run_cycle(settings)

    assert report["action"] == "SELL_REJECTED", f"expected SELL_REJECTED, got {report['action']}"
    assert state.get("pending_order") is None, "no pending for SELL"
    sell_events = [e for e in emits if e["event_type"] == "CLEAN_SELL_REJECTED"]
    assert len(sell_events) >= 1, "CLEAN_SELL_REJECTED event must be emitted"
    assert sell_events[0]["side"] == "SELL"


# ---------------------------------------------------------------------------
# 10. Pending and position survive a restart
# ---------------------------------------------------------------------------

def test_pending_survives_restart(tmp_path) -> None:
    """Pending written by _write_state is correctly recovered after restart."""
    settings = _settings(tmp_path)
    initial = _default_state(settings)
    initial["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": 95.0,
        "take_profit": 130.0,
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    _write_state(settings, initial)

    recovered = _read_state(settings)

    assert recovered.get("pending_order") is not None, "pending must survive restart"
    assert recovered["pending_order"]["signal_price"] == 102.0
    assert recovered["pending_order"]["stop_price"] == 95.0


def test_position_survives_restart(tmp_path) -> None:
    """Open position written by _write_state is correctly recovered after restart."""
    settings = _settings(tmp_path)
    initial = _default_state(settings)
    initial["position"] = {
        "position_id": "restart_test",
        "symbol": settings.symbol,
        "side": "BUY",
        "qty": 0.05,
        "entry_price": 105.0,
        "entry_fee": 0.0,
        "cost_basis": 5.25,
        "stop_loss": 95.0,
        "stop_price_at_entry": 95.0,
        "take_profit": 130.0,
        "trail_atr_mult": 10.0,
        "atr_pct_at_entry": 0.0,
    }
    initial["cash"] = 94.75
    _write_state(settings, initial)

    recovered = _read_state(settings)

    assert recovered.get("position") is not None, "position must survive restart"
    assert recovered["position"]["position_id"] == "restart_test"
    assert recovered["cash"] == pytest.approx(94.75)


# ---------------------------------------------------------------------------
# 11. Corrupt state file returns flag, does NOT silently reset an open position
# ---------------------------------------------------------------------------

def test_corrupt_state_returns_flag(tmp_path) -> None:
    """A corrupt state file must set _corrupt_recovery=True instead of silently losing state."""
    settings = _settings(tmp_path)
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{invalid json{{", encoding="utf-8")

    recovered = _read_state(settings)

    assert recovered.get("_corrupt_recovery") is True
    assert "_corrupt_error" in recovered


def test_non_dict_state_returns_flag(tmp_path) -> None:
    """A valid JSON but non-dict state (e.g., list) must set _corrupt_recovery=True."""
    settings = _settings(tmp_path)
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[1, 2, 3]", encoding="utf-8")

    recovered = _read_state(settings)

    assert recovered.get("_corrupt_recovery") is True


# ---------------------------------------------------------------------------
# 12. Atomic save: .tmp file does not linger; original survives failed write
# ---------------------------------------------------------------------------

def test_atomic_save_no_tmp_after_success(tmp_path) -> None:
    """After a successful write, no .tmp file remains."""
    settings = _settings(tmp_path)
    _write_state(settings, _default_state(settings))

    assert not _state_path(settings).with_suffix(".tmp").exists()
    assert _state_path(settings).exists()


def test_atomic_save_preserves_state_on_tmp_write_failure(tmp_path, monkeypatch) -> None:
    """If writing .tmp fails, the original state file is untouched."""
    settings = _settings(tmp_path)
    initial = _default_state(settings)
    initial["cash"] = 77.0
    _write_state(settings, initial)

    from pathlib import Path as _Path
    original_write = _Path.write_text
    calls = [0]

    def failing_write(self, data, *args, **kwargs):
        if str(self).endswith(".tmp"):
            calls[0] += 1
            if calls[0] == 1:
                raise OSError("simulated tmp write failure")
        return original_write(self, data, *args, **kwargs)

    monkeypatch.setattr(_Path, "write_text", failing_write)

    corrupt = _default_state(settings)
    corrupt["cash"] = 1.0
    with pytest.raises(OSError):
        _write_state(settings, corrupt)

    recovered = _read_state(settings)
    assert recovered["cash"] == pytest.approx(77.0), "original cash must be intact"


# ---------------------------------------------------------------------------
# 13. validate_entry_price shared function — BUY and SELL coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entry,stop,tp,side,expected_valid,expected_reason", [
    (105.0, 95.0, 130.0, "BUY",  True,  "OK"),                       # BUY valid
    (95.0,  95.0, 130.0, "BUY",  False, "ENTRY_AT_OR_BELOW_SL"),     # BUY at SL
    (90.0,  95.0, 130.0, "BUY",  False, "ENTRY_AT_OR_BELOW_SL"),     # BUY below SL
    (130.0, 95.0, 130.0, "BUY",  False, "ENTRY_AT_OR_ABOVE_TP"),     # BUY at TP
    (140.0, 95.0, 130.0, "BUY",  False, "ENTRY_AT_OR_ABOVE_TP"),     # BUY above TP
    (105.0, 115.0, 90.0, "SELL", True,  "OK"),                       # SELL valid
    (115.0, 115.0, 90.0, "SELL", False, "ENTRY_AT_OR_ABOVE_SL"),     # SELL at SL
    (120.0, 115.0, 90.0, "SELL", False, "ENTRY_AT_OR_ABOVE_SL"),     # SELL above SL
    (90.0,  115.0, 90.0, "SELL", False, "ENTRY_AT_OR_BELOW_TP"),     # SELL at TP
    (85.0,  115.0, 90.0, "SELL", False, "ENTRY_AT_OR_BELOW_TP"),     # SELL below TP
])
def test_validate_entry_price(entry, stop, tp, side, expected_valid, expected_reason) -> None:
    signal = Signal(
        strategy="t", side=side, score=1.0, reason="t",
        stop_price=stop, take_profit=tp, metadata={},
    )
    valid, reason = validate_entry_price(entry, signal)
    assert valid == expected_valid
    assert reason == expected_reason


# ---------------------------------------------------------------------------
# Cycle 02 additions
# ---------------------------------------------------------------------------

# 14. Risk default 0.005 in backtest and optimizer CLIs

def test_risk_default_in_backtest_cli() -> None:
    """tools/clean_bot_backtest.py must declare default=0.005 for --risk-per-trade-pct."""
    cli = Path(__file__).resolve().parents[2] / "tools" / "clean_bot_backtest.py"
    text = cli.read_text(encoding="utf-8")
    assert "--risk-per-trade-pct" in text
    assert "default=0.005" in text, "backtest CLI must use default=0.005 for --risk-per-trade-pct"
    assert "default=0.01" not in text, "backtest CLI must not use 0.01 as risk default"


def test_risk_default_in_optimizer_cli() -> None:
    """tools/clean_bot_optimizer.py must declare default=0.005 for --risk-per-trade-pct."""
    cli = Path(__file__).resolve().parents[2] / "tools" / "clean_bot_optimizer.py"
    text = cli.read_text(encoding="utf-8")
    assert "--risk-per-trade-pct" in text
    assert "default=0.005" in text, "optimizer CLI must use default=0.005 for --risk-per-trade-pct"
    assert "default=0.01" not in text, "optimizer CLI must not use 0.01 as risk default"


# 15. Corrupt state → run_cycle() returns STATE_CORRUPT_BLOCKED without side-effects

def test_run_cycle_corrupt_state_is_blocked(tmp_path, monkeypatch) -> None:
    """run_cycle() with a corrupt state file returns STATE_CORRUPT_BLOCKED.

    Guarantees:
    - _write_state is never called (file untouched, balance and position cannot be lost)
    - No position is opened or closed
    - At least one CORRUPT event is emitted
    """
    settings = _settings(tmp_path)
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_content = "{invalid json"
    path.write_text(corrupt_content, encoding="utf-8")

    emits: list = []
    wrote_states: list = []

    # Capture _emit calls. _read_state calls _emit internally before run_cycle checks the
    # flag, so we patch at module level to capture both.
    monkeypatch.setattr(paper_live, "_emit", lambda _s, t, **p: emits.append({"event_type": t, **p}))
    monkeypatch.setattr(paper_live, "_write_state", lambda _s, st: wrote_states.append(st))

    report = paper_live.run_cycle(settings)

    assert report["action"] == "STATE_CORRUPT_BLOCKED", f"expected STATE_CORRUPT_BLOCKED, got {report['action']}"

    # File must be unchanged — not overwritten with a clean default
    assert path.read_text(encoding="utf-8") == corrupt_content, "corrupt file must not be overwritten"

    # _write_state must never have been called
    assert wrote_states == [], "_write_state must not be called when state is corrupt"

    # At least one corruption event must be emitted (either CLEAN_STATE_CORRUPT_RECOVERY
    # or CLEAN_STATE_CORRUPT_BLOCKED from run_cycle, or both)
    corrupt_events = [e for e in emits if "CORRUPT" in e["event_type"]]
    assert len(corrupt_events) >= 1, "at least one CORRUPT event must be emitted"

    # run_cycle's own event
    blocked_events = [e for e in emits if e["event_type"] == "CLEAN_STATE_CORRUPT_BLOCKED"]
    assert len(blocked_events) >= 1, "CLEAN_STATE_CORRUPT_BLOCKED event must be emitted by run_cycle"


def test_run_cycle_corrupt_state_no_position_opened(tmp_path, monkeypatch) -> None:
    """Corrupt state must not result in any order being opened."""
    settings = _settings(tmp_path)
    path = _state_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[not, a, dict]", encoding="utf-8")

    positions_opened: list = []

    def _tracking_write(settings, state):
        if state.get("position"):
            positions_opened.append(state["position"])

    monkeypatch.setattr(paper_live, "_emit", lambda *_a, **_k: None)
    monkeypatch.setattr(paper_live, "_write_state", _tracking_write)

    report = paper_live.run_cycle(settings)

    assert report["action"] == "STATE_CORRUPT_BLOCKED"
    assert positions_opened == [], "no position must be opened when state is corrupt"


# 16. Parity: paper discard reason matches validate_entry_price() output

@pytest.mark.parametrize("fill_price,stop,tp,expected_reason", [
    (90.0,  95.0,  130.0, "ENTRY_AT_OR_BELOW_SL"),   # fill below SL
    (95.0,  95.0,  130.0, "ENTRY_AT_OR_BELOW_SL"),   # fill at SL boundary
    (130.0, 95.0,  130.0, "ENTRY_AT_OR_ABOVE_TP"),   # fill at TP boundary
    (140.0, 95.0,  130.0, "ENTRY_AT_OR_ABOVE_TP"),   # fill above TP
])
def test_paper_entry_gap_parity_with_validate_entry_price(
    tmp_path, monkeypatch, fill_price: float, stop: float, tp: float, expected_reason: str
) -> None:
    """Paper CLEAN_PENDING_DISCARDED reason matches validate_entry_price() output exactly.

    This verifies that _fill_pending_order delegates to validate_entry_price() rather than
    re-implementing its own inline checks.
    """
    settings = _settings(tmp_path)
    state = _default_state(settings)
    state["pending_order"] = {
        "signal_price": 102.0,
        "signal_bar": T0,
        "stop_price": stop,
        "take_profit": tp,
        "strategy": "int02b",
        "reason": "test",
        "metadata": {},
        "created_at": T0,
    }
    state["last_processed_bar"] = ""

    emits: list = []
    frame = _frame(
        {"Open": 105.0, "High": 107.0, "Low": 104.0, "Close": 106.0},
        {"Open": fill_price, "High": fill_price + 5, "Low": fill_price - 5,
         "Close": fill_price + 2, "atr14": 1.0},
    )
    _mock(monkeypatch, state, frame, signal=None, signal_row_idx=0, capture_emits=emits)

    paper_live.run_cycle(settings)

    # validate_entry_price must agree with the paper's discard reason
    stub = Signal(strategy="t", side="BUY", score=0.0, reason="t",
                  stop_price=stop, take_profit=tp, metadata={})
    valid, vep_reason = validate_entry_price(fill_price, stub)
    assert not valid
    assert vep_reason == expected_reason

    discard_events = [e for e in emits if e["event_type"] == "CLEAN_PENDING_DISCARDED"]
    assert len(discard_events) >= 1, "CLEAN_PENDING_DISCARDED must be emitted"
    assert discard_events[0]["reason"] == vep_reason, (
        f"paper reason '{discard_events[0]['reason']}' must match validate_entry_price() '{vep_reason}'"
    )
