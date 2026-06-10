"""test_validation_gates.py — TR-INT-05 mandatory tests.

Covers M9-M15 from integration_phase1_report.md §7B.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import os
import re
import types as types_mod
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from trading_bot.clean_bot.backtest import run_backtest_frame
from trading_bot.clean_bot.models import BacktestSettings, Signal
from trading_bot.clean_bot.strategies import Strategy
from trading_bot.clean_bot.validation_gates import (
    VALIDATION_CONFIG,
    dataset_date_range,
    is_promising,
    oos_with_warmup,
    run_validation,
    run_without_costs,
    temporal_concentration_check,
)
from trading_bot.core.unified_trade_cost import UnifiedCostModel

_OPTIMIZER_PATH = Path(__file__).resolve().parents[2] / "tools" / "clean_bot_optimizer.py"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_test_df(n: int = 500) -> pd.DataFrame:
    """Minimal OHLCV DataFrame with all columns required by backtest machinery."""
    prices = [100.0 + i * 0.01 for i in range(n)]
    return pd.DataFrame({
        "Open":           prices,
        "High":           [p + 0.5 for p in prices],
        "Low":            [p - 0.5 for p in prices],
        "Close":          prices,
        "Volume":         [1000.0] * n,
        "ema50":          [p + 0.1 for p in prices],
        "ema200":         prices,
        "atr14":          [1.0] * n,
        "atr_pct":        [0.5] * n,
        "volume_ratio_20":[1.5] * n,
        "datetime": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
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
# M9 — Immutable validation configuration
# ---------------------------------------------------------------------------

def test_immutable_config_env_independent() -> None:
    """VALIDATION_CONFIG is a MappingProxyType: immutable and independent of os.environ."""
    # Type guarantee
    assert isinstance(VALIDATION_CONFIG, types_mod.MappingProxyType)

    # Write attempt must raise
    with pytest.raises(TypeError):
        VALIDATION_CONFIG["new_key"] = 99  # type: ignore[index]

    # Key values match specification
    assert VALIDATION_CONFIG["warmup_bars"] == 401
    assert VALIDATION_CONFIG["oos_split_ratio"] == pytest.approx(0.3)
    assert VALIDATION_CONFIG["min_oos_trades"] == 50
    assert VALIDATION_CONFIG["cost_scenario"] == "conservative"
    assert VALIDATION_CONFIG["risk_per_trade_pct"] == pytest.approx(0.005)

    # Setting an env var must not affect the config (no os.environ reads)
    os.environ["VALIDATION_CONFIG_WARMUP_BARS"] = "9999"
    os.environ["VALIDATION_MIN_OOS_TRADES"] = "9999"
    try:
        assert VALIDATION_CONFIG["warmup_bars"] == 401
        assert VALIDATION_CONFIG["min_oos_trades"] == 50
    finally:
        os.environ.pop("VALIDATION_CONFIG_WARMUP_BARS", None)
        os.environ.pop("VALIDATION_MIN_OOS_TRADES", None)


# ---------------------------------------------------------------------------
# M12 — Temporal concentration gate
# ---------------------------------------------------------------------------

def test_temporal_concentration_gate() -> None:
    """M12: concentrated week > 50% → fails; balanced → passes; < 3 weeks → fails."""
    # One week dominates (> 50% of abs total) → gate fails
    concentrated = [
        {"net_pnl": 100.0, "entry_time": "2024-01-01T00:00:00+00:00"},  # week 1
        {"net_pnl":  10.0, "entry_time": "2024-01-08T00:00:00+00:00"},  # week 2
        {"net_pnl":   5.0, "entry_time": "2024-01-15T00:00:00+00:00"},  # week 3
    ]
    # abs_total = 115, week1_pct = 100/115 ≈ 86.9% > 50%
    r = temporal_concentration_check(concentrated)
    assert r["passes"] is False
    assert r["worst_week_pct"] > 50.0
    assert r["n_weeks"] >= 3

    # Balanced weeks → gate passes
    balanced = [
        {"net_pnl": 10.0, "entry_time": "2024-01-01T00:00:00+00:00"},
        {"net_pnl":  8.0, "entry_time": "2024-01-08T00:00:00+00:00"},
        {"net_pnl":  9.0, "entry_time": "2024-01-15T00:00:00+00:00"},
    ]
    r2 = temporal_concentration_check(balanced)
    assert r2["passes"] is True
    assert r2["worst_week_pct"] <= 50.0

    # Only 2 weeks → insufficient_weeks regardless of balance
    two_weeks = [
        {"net_pnl": 10.0, "entry_time": "2024-01-01T00:00:00+00:00"},
        {"net_pnl": 10.0, "entry_time": "2024-01-08T00:00:00+00:00"},
    ]
    r3 = temporal_concentration_check(two_weeks)
    assert r3["passes"] is False
    assert "insufficient_weeks" in r3["reason"]

    # Empty trades → no_trades
    r4 = temporal_concentration_check([])
    assert r4["passes"] is False
    assert r4["reason"] == "no_trades"


# ---------------------------------------------------------------------------
# M11 — Full no-cost re-run (not post-hoc)
# ---------------------------------------------------------------------------

def test_cost_vs_nocost_full_rerun() -> None:
    """M11: no-cost run is a full re-run; cost=0.0, _zero_cost=True, net==gross per trade."""
    df = _make_test_df(500)
    settings = BacktestSettings(
        starting_balance=1000.0,
        risk_per_trade_pct=0.005,
        cost_model="conservative",
    )
    strategies = [_MockSignalAt(410)]

    cost_result = run_backtest_frame(raw_rows=500, df=df, settings=settings, strategies=strategies)
    nocost_result = run_without_costs(df=df, settings=settings, strategies=strategies)

    # Both runs must produce at least one trade
    assert cost_result["metrics"]["closed_trades"] >= 1
    assert nocost_result["metrics"]["closed_trades"] >= 1

    # Structural guarantees on no-cost result
    assert nocost_result["_zero_cost"] is True
    assert nocost_result["metrics"]["total_cost"] == pytest.approx(0.0)

    # Per-trade guarantees: cost=0, _zero_cost flag, net_pnl == gross_pnl
    for t in nocost_result["trades"]:
        assert t["cost"] == pytest.approx(0.0), f"no-cost trade must have cost=0, got {t['cost']}"
        assert t["_zero_cost"] is True
        assert t["net_pnl"] == pytest.approx(t["gross_pnl"]), (
            f"no-cost trade: net_pnl={t['net_pnl']!r} must equal gross_pnl={t['gross_pnl']!r}"
        )

    # Same number of trades (same signal, same entry/exit logic)
    assert cost_result["metrics"]["closed_trades"] == nocost_result["metrics"]["closed_trades"]

    # Cost run trade has non-zero cost (UCM applied)
    cost_trades = cost_result["trades"]
    assert any(t["cost"] != pytest.approx(0.0) for t in cost_trades), (
        "cost run must apply non-zero cost via UCM"
    )


# ---------------------------------------------------------------------------
# M10 + M15 — OOS warmup no-lookahead guarantee
# ---------------------------------------------------------------------------

def test_oos_warmup_no_lookahead() -> None:
    """M10/M15: signals at idx < 401 (warmup) never fire; idx == 401 fires (OOS boundary)."""
    n = 1000
    df = _make_test_df(n)
    oos_df, warmup_count = oos_with_warmup(df)

    # Math checks: split=700, warmup_start=299, actual_warmup=401
    expected_split = int(n * (1.0 - float(VALIDATION_CONFIG["oos_split_ratio"])))  # 700
    expected_warmup_start = max(0, expected_split - int(VALIDATION_CONFIG["warmup_bars"]))  # 299
    expected_warmup_count = expected_split - expected_warmup_start  # 401
    expected_oos_len = n - expected_warmup_start  # 701
    expected_true_oos = n - expected_split  # 300

    assert warmup_count == expected_warmup_count == 401
    assert len(oos_df) == expected_oos_len
    assert len(oos_df) - warmup_count == expected_true_oos

    settings = BacktestSettings(starting_balance=1000.0)

    # Signal in warmup zone (idx=400 < 401) must NEVER fire
    r_warmup = run_backtest_frame(
        raw_rows=n, df=oos_df, settings=settings, strategies=[_MockSignalAt(400)]
    )
    assert r_warmup["metrics"]["closed_trades"] == 0, (
        "signal at idx=400 (warmup) must not fire — backtest starts at idx=401"
    )

    # Signal at OOS boundary (idx=401 == warmup_count) MUST fire
    r_oos = run_backtest_frame(
        raw_rows=n, df=oos_df, settings=settings, strategies=[_MockSignalAt(401)]
    )
    assert r_oos["metrics"]["closed_trades"] >= 1, (
        "signal at idx=401 (OOS boundary) must fire"
    )


# ---------------------------------------------------------------------------
# M9 (optimizer) — UCM replaces local flat-cost authority
# ---------------------------------------------------------------------------

def test_optimizer_uses_unified_cost_model() -> None:
    """Optimizer routes costs through UCM; _cost_bps and local flat bps are removed."""
    text = _OPTIMIZER_PATH.read_text(encoding="utf-8")

    # Local flat-cost authority removed
    assert "_cost_bps" not in text, "_cost_bps must be removed from optimizer"
    # "CostModel" substring is fine as part of "UnifiedCostModel"; the local class must be gone
    assert "class CostModel" not in text, "local CostModel dataclass must be removed from optimizer"
    assert "cost_models()" not in text, "local cost_models() factory must be removed from optimizer"

    # UCM import and scenario mapping present
    assert "UnifiedCostModel" in text, "optimizer must import UnifiedCostModel"
    assert "_ucm_scenario" in text, "optimizer must define _ucm_scenario"

    # Scenario mapping: "base" → "realistic"
    assert '"base": "realistic"' in text or "'base': 'realistic'" in text, (
        "optimizer must map base → realistic"
    )

    # UCM call in _run_candidate
    assert "apply_cost_to_backtest_trade" in text, (
        "optimizer must call UnifiedCostModel.apply_cost_to_backtest_trade"
    )

    # symbol and timeframe passed to UCM
    assert "symbol=symbol" in text, "optimizer must pass symbol to UCM"
    assert "timeframe=timeframe" in text, "optimizer must pass timeframe to UCM"


# ---------------------------------------------------------------------------
# M10 (optimizer) — OOS gate replaces second-half split
# ---------------------------------------------------------------------------

def test_optimizer_selection_does_not_use_final_oos() -> None:
    """Optimizer uses oos_with_warmup for candidate selection; no second-half contamination."""
    text = _OPTIMIZER_PATH.read_text(encoding="utf-8")

    # Old contaminated second-half split removed
    assert "second_half" not in text, "second_half contamination must be removed from optimizer"
    assert "len(df) // 2" not in text, "second-half split (len(df) // 2) must be removed"
    assert "split = len" not in text, "hardcoded midpoint split must be removed"

    # True OOS gate in place
    assert "oos_with_warmup" in text, "optimizer must use oos_with_warmup"
    assert "oos_gate" in text, "optimizer report settings must declare oos_gate"

    # _paper_eligible now checks OOS metrics (not second-half)
    import re
    paper_eligible_src = re.search(
        r"def _paper_eligible\(.*?\).*?(?=\ndef |\Z)", text, re.DOTALL
    )
    assert paper_eligible_src is not None, "_paper_eligible not found in optimizer"
    pe_body = paper_eligible_src.group(0)
    assert "second_half" not in pe_body, "_paper_eligible must not reference second_half"
    assert "oos" in pe_body.lower(), "_paper_eligible must evaluate oos metrics"


# ---------------------------------------------------------------------------
# M15 — Report dates from actual dataset timestamps
# ---------------------------------------------------------------------------

def test_report_dates_match_dataset() -> None:
    """dataset_date_range returns actual timestamps from the df, not hardcoded values."""
    n = 50
    start_ts = pd.Timestamp("2024-03-01 00:00:00+00:00")
    end_ts   = pd.Timestamp("2024-03-15 23:55:00+00:00")
    df = pd.DataFrame({
        "Close": [100.0] * n,
        "datetime": pd.date_range(start=start_ts, end=end_ts, periods=n, tz="UTC"),
    })

    dr = dataset_date_range(df)
    assert dr["start"] != "", "start must not be empty"
    assert dr["end"]   != "", "end must not be empty"
    assert "2024-03-01" in dr["start"], f"start should contain 2024-03-01, got {dr['start']!r}"
    assert "2024-03-15" in dr["end"],   f"end should contain 2024-03-15, got {dr['end']!r}"

    # start < end
    assert dr["start"] < dr["end"]

    # Missing datetime column → empty strings (no KeyError, no hardcoded fallback)
    df_no_dt = pd.DataFrame({"Close": [100.0, 200.0]})
    dr2 = dataset_date_range(df_no_dt)
    assert dr2["start"] == "", "missing datetime column must yield empty start"
    assert dr2["end"]   == "", "missing datetime column must yield empty end"

    # Empty df → empty strings
    df_empty = pd.DataFrame({"Close": [], "datetime": pd.Series([], dtype="datetime64[ns]")})
    dr3 = dataset_date_range(df_empty)
    assert dr3["start"] == ""
    assert dr3["end"]   == ""


# ---------------------------------------------------------------------------
# M13 — Economic gate: profit factor
# ---------------------------------------------------------------------------

def test_economic_gate_pf() -> None:
    """M13: PF must be strictly > 1.0; equality at 1.0 is rejected."""
    # PF exactly at boundary → fails (strictly > 1.0 required)
    passes, checks = is_promising(
        {"profit_factor": 1.0, "net_pnl": 50.0, "closed_trades": 60},
        temporal_check=False,
    )
    assert passes is False
    assert checks["pf_ok"] is False

    # PF > 1.0 with sufficient trades and positive pnl → passes
    passes2, checks2 = is_promising(
        {"profit_factor": 1.5, "net_pnl": 50.0, "closed_trades": 60},
        temporal_check=False,
    )
    assert passes2 is True
    assert checks2["pf_ok"] is True

    # PF below 1.0 → fails
    passes3, checks3 = is_promising(
        {"profit_factor": 0.8, "net_pnl": -10.0, "closed_trades": 60},
        temporal_check=False,
    )
    assert passes3 is False
    assert checks3["pf_ok"] is False

    # PF = None (no losses) → treated as 0.0 → fails
    passes4, checks4 = is_promising(
        {"profit_factor": None, "net_pnl": 50.0, "closed_trades": 60},
        temporal_check=False,
    )
    assert passes4 is False, "PF=None (no trades closed at a loss) must fail the gate"

    # Net PnL = 0.0 → pnl_ok fails even with good PF
    passes5, checks5 = is_promising(
        {"profit_factor": 1.5, "net_pnl": 0.0, "closed_trades": 60},
        temporal_check=False,
    )
    assert passes5 is False
    assert checks5["pnl_ok"] is False


# ---------------------------------------------------------------------------
# M13 — Economic gate: minimum trades
# ---------------------------------------------------------------------------

def test_economic_gate_min_trades() -> None:
    """M13: minimum 50 closed trades required; 49 is rejected."""
    # 49 trades → fails (strictly < 50)
    passes, checks = is_promising(
        {"profit_factor": 1.5, "net_pnl": 50.0, "closed_trades": 49},
        temporal_check=False,
    )
    assert passes is False
    assert checks["trades_ok"] is False
    assert checks["n_trades"] == 49
    assert checks["min_trades"] == 50

    # Exactly 50 trades → passes (at the boundary)
    passes2, checks2 = is_promising(
        {"profit_factor": 1.5, "net_pnl": 50.0, "closed_trades": 50},
        temporal_check=False,
    )
    assert passes2 is True
    assert checks2["trades_ok"] is True

    # 0 trades → fails
    passes3, checks3 = is_promising(
        {"profit_factor": None, "net_pnl": 0.0, "closed_trades": 0},
        temporal_check=False,
    )
    assert passes3 is False
    assert checks3["trades_ok"] is False

    # 200 trades (well above threshold) → trades_ok passes
    _, checks4 = is_promising(
        {"profit_factor": 1.5, "net_pnl": 50.0, "closed_trades": 200},
        temporal_check=False,
    )
    assert checks4["trades_ok"] is True


# ---------------------------------------------------------------------------
# M15 — Deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_output() -> None:
    """Same df + same settings → byte-identical output on two successive calls."""
    df = _make_test_df(600)
    settings = BacktestSettings(
        starting_balance=1000.0,
        risk_per_trade_pct=0.005,
        cost_model="conservative",
    )
    strategies = [_MockSignalAt(410)]

    result1 = run_validation(df=df, settings=settings, strategies=strategies)
    result2 = run_validation(df=df, settings=settings, strategies=strategies)

    # Canonical JSON comparison (covers all nested floats, strings, bools, None)
    j1 = json.dumps(result1, sort_keys=True, default=str)
    j2 = json.dumps(result2, sort_keys=True, default=str)
    assert j1 == j2, "run_validation must produce identical output on identical inputs"

    # Spot-check structural fields
    assert result1["report_type"] == "clean_bot_validation_gates"
    assert result1["diagnostic_only"] is True
    assert result1["opens_orders"] is False
    assert result1["warmup_bars"] == result2["warmup_bars"]
    assert result1["oos_rows"]    == result2["oos_rows"]
    assert result1["dataset_date_range"] == result2["dataset_date_range"]
    assert result1["edge_demonstrated"] == result2["edge_demonstrated"]
    assert result1["cost_run"]["n_trades"] == result2["cost_run"]["n_trades"]
    assert result1["nocost_run"]["n_trades"] == result2["nocost_run"]["n_trades"]


# ---------------------------------------------------------------------------
# Helpers for optimizer tests
# ---------------------------------------------------------------------------

def _make_optimizer_df(n: int = 620) -> pd.DataFrame:
    """DataFrame with all optimizer columns; signal fires at idx=577 (lookback_bars=576).

    Signal condition: close > prior_high AND close > ema50 > ema200 AND volume_ratio>=1.5
    close=p, ema50=p-1, ema200=p-2 satisfies close>ema50>ema200 at every bar.
    """
    prices = [1000.0 + i * 0.1 for i in range(n)]
    return pd.DataFrame({
        "Open":  prices,
        "High":  [p + 0.5 for p in prices],
        "Low":   [p - 0.5 for p in prices],
        "Close": prices,
        "Volume": [1000.0] * n,
        "ema50":  [p - 1.0 for p in prices],
        "ema200": [p - 2.0 for p in prices],
        "atr14":  [4.0] * n,
        "atr_pct": [0.5] * n,
        "volume_ratio_20": [2.0] * n,
        "prior_high_576":  [p - 50.0 for p in prices],
        "prior_high_1152": [p - 50.0 for p in prices],
        "datetime": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
    })


def _load_optimizer():
    spec = importlib.util.spec_from_file_location("clean_bot_optimizer", _OPTIMIZER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# M11 (Issue 1) — Spy test: run_without_costs routes through UCM
# ---------------------------------------------------------------------------

def test_run_without_costs_calls_ucm() -> None:
    """M11: run_without_costs() must call UCM.apply_cost_to_backtest_trade with scenario='zero'."""
    df = _make_test_df(500)
    settings = BacktestSettings(
        starting_balance=1000.0,
        risk_per_trade_pct=0.005,
        cost_model="conservative",
    )
    strategies = [_MockSignalAt(410)]

    with patch(
        "trading_bot.clean_bot.backtest.UnifiedCostModel.apply_cost_to_backtest_trade",
        wraps=UnifiedCostModel.apply_cost_to_backtest_trade,
    ) as spy:
        result = run_without_costs(df=df, settings=settings, strategies=strategies)

    assert spy.call_count >= 1, "run_without_costs must call UCM.apply_cost_to_backtest_trade"
    for c in spy.call_args_list:
        assert c.kwargs.get("scenario") == "zero", (
            f"every UCM call from run_without_costs must use scenario='zero', "
            f"got {c.kwargs.get('scenario')!r}"
        )
    assert result["_zero_cost"] is True
    assert result["metrics"]["total_cost"] == pytest.approx(0.0)
    for t in result.get("trades", []):
        assert t["cost"] == pytest.approx(0.0), f"zero-cost trade must have cost=0, got {t['cost']}"
        assert t["_zero_cost"] is True
        assert t["net_pnl"] == pytest.approx(t["gross_pnl"])


# ---------------------------------------------------------------------------
# Issue 2 — Behavioral: UCM errors propagate (fail-closed)
# ---------------------------------------------------------------------------

def test_optimizer_ucm_error_fails_closed() -> None:
    """_run_candidate must propagate UCM ValueError; no silent gross_pnl fallback."""
    optimizer = _load_optimizer()
    df = _make_optimizer_df()
    params = {
        "lookback_bars": 576,
        "volume_min": 1.5,
        "stop_atr_mult": 4.0,
        "trail_atr_mult": 10.0,
        "max_hold_bars": 1728,
    }

    with patch(
        "trading_bot.core.unified_trade_cost.UnifiedCostModel.apply_cost_to_backtest_trade",
        side_effect=ValueError("injected UCM failure"),
    ):
        with pytest.raises(ValueError, match="injected UCM failure"):
            optimizer._run_candidate(
                df,
                params=params,
                balance=100.0,
                risk_per_trade_pct=0.005,
                cost_model="conservative",
            )


# ---------------------------------------------------------------------------
# Issue 3 — OOS must not influence ranking; 20 OOS trades rejected
# ---------------------------------------------------------------------------

def test_oos_does_not_influence_ranking_behavioral() -> None:
    """Behavioral: changing OOS alone cannot change score or rank; only the gate status can flip.

    Proves three invariants via build_report with mocked _run_candidate:
    1. score == train["return_pct"] — not contaminated by full-run OOS data
    2. Rank order is identical across scenarios that differ only in OOS
    3. Gate status (PAPER_CANDIDATE / RESEARCH_ONLY) CAN change when OOS changes
    """
    optimizer = _load_optimizer()

    # Controlled metrics — full and train are the same in both scenarios
    full_m   = {"closed_trades": 50, "return_pct": 9.0,  "profit_factor": 1.3,
                "win_rate_pct": 55.0, "max_drawdown_pct": 5.0, "average_r": 0.4, "trades": []}
    train_hi = {"closed_trades": 40, "return_pct": 12.0, "profit_factor": 1.4,
                "win_rate_pct": 60.0, "max_drawdown_pct": 4.0, "average_r": 0.5, "trades": []}
    train_lo = {"closed_trades": 35, "return_pct": 5.0,  "profit_factor": 1.15,
                "win_rate_pct": 52.0, "max_drawdown_pct": 8.0, "average_r": 0.2, "trades": []}
    # OOS that passes the gate (≥50 trades, PF>1, return>0, temporal gate OK)
    _base_dt = _dt.datetime(2024, 1, 1, tzinfo=_dt.timezone.utc)
    _oos_pass_trades = [
        {"net_pnl": 1.0, "entry_time": (_base_dt + _dt.timedelta(weeks=i % 4, hours=i)).isoformat()}
        for i in range(60)
    ]
    oos_pass = {"closed_trades": 60, "return_pct": 4.0,  "profit_factor": 1.2,
                "win_rate_pct": 55.0, "max_drawdown_pct": 3.0, "average_r": 0.3, "trades": _oos_pass_trades}
    # OOS that fails the economic gate (too few trades)
    oos_fail = {"closed_trades": 5,  "return_pct": 2.0,  "profit_factor": 1.1,
                "win_rate_pct": 55.0, "max_drawdown_pct": 5.0, "average_r": 0.3, "trades": []}

    n = 3000
    prices = [1000.0 + i * 0.1 for i in range(n)]
    fake_df = pd.DataFrame({
        "Open":  prices,
        "High":  [p + 0.5 for p in prices],
        "Low":   [p - 0.5 for p in prices],
        "Close": prices,
        "Volume": [1000.0] * n,
        "ema50":  [p - 1.0 for p in prices],
        "ema200": [p - 2.0 for p in prices],
        "atr14":  [4.0] * n,
        "atr_pct": [0.5] * n,
        "volume_ratio_20": [2.0] * n,
        "prior_high_576":  [p - 50.0 for p in prices],
        "prior_high_1152": [p - 50.0 for p in prices],
        "datetime": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
    })

    # Two symbols; one params each → 3 _run_candidate calls per symbol (full, train, oos)
    # Seq for symbol BTC: full_val, train_hi, oos_X
    # Seq for symbol ETH: full_val, train_lo, oos_Y
    def _make_mock(oos_btc, oos_eth, full_val=None):
        fval = full_val if full_val is not None else full_m
        seq = [fval, train_hi, oos_btc, fval, train_lo, oos_eth]
        state = {"i": 0}
        def _side(*a, **kw):
            r = seq[state["i"] % len(seq)]
            state["i"] += 1
            return r
        return _side

    single_param = [optimizer._candidate_grid()[0]]

    with patch.object(optimizer, "load_ohlcv", return_value=fake_df), \
         patch.object(optimizer, "add_indicators", side_effect=lambda df: df), \
         patch.object(optimizer, "_candidate_grid", return_value=single_param), \
         patch.object(optimizer, "_run_candidate", side_effect=_make_mock(oos_pass, oos_fail)):
        report_1 = optimizer.build_report(
            data_dir=Path("/fake"), symbols=["BTC/USDT", "ETH/USDT"], timeframe="5m",
            balance=100.0, risk_per_trade_pct=0.005, cost_model="conservative", max_rows=n,
        )

    with patch.object(optimizer, "load_ohlcv", return_value=fake_df), \
         patch.object(optimizer, "add_indicators", side_effect=lambda df: df), \
         patch.object(optimizer, "_candidate_grid", return_value=single_param), \
         patch.object(optimizer, "_run_candidate", side_effect=_make_mock(oos_fail, oos_pass)):
        report_2 = optimizer.build_report(
            data_dir=Path("/fake"), symbols=["BTC/USDT", "ETH/USDT"], timeframe="5m",
            balance=100.0, risk_per_trade_pct=0.005, cost_model="conservative", max_rows=n,
        )

    rows_1 = sorted(report_1["top_by_symbol"], key=lambda r: r["score"], reverse=True)
    rows_2 = sorted(report_2["top_by_symbol"], key=lambda r: r["score"], reverse=True)

    # Invariant 1: score is train-only — identical across OOS scenarios
    assert rows_1[0]["score"] == rows_2[0]["score"], "score must not change when OOS changes"
    assert rows_1[1]["score"] == rows_2[1]["score"], "score must not change when OOS changes"

    # Invariant 2: score equals train["return_pct"], not full+train (which would be 9+12=21)
    assert rows_1[0]["score"] == pytest.approx(train_hi["return_pct"]), (
        f"score={rows_1[0]['score']} must equal train-only {train_hi['return_pct']}, "
        f"not full+train={full_m['return_pct'] + train_hi['return_pct']}"
    )
    assert rows_1[0]["score"] != pytest.approx(full_m["return_pct"] + train_hi["return_pct"]), (
        "score must not include the full-run return (that would contaminate with OOS data)"
    )

    # Invariant 3: ranking order is preserved — BTC (train=12) always before ETH (train=5)
    assert rows_1[0]["symbol"] == rows_2[0]["symbol"] == "BTC/USDT"
    assert rows_1[1]["symbol"] == rows_2[1]["symbol"] == "ETH/USDT"

    # Invariant 4: the gate CAN change — BTC flips between the two scenarios
    btc_1 = next(r for r in report_1["top_by_symbol"] if r["symbol"] == "BTC/USDT")
    btc_2 = next(r for r in report_2["top_by_symbol"] if r["symbol"] == "BTC/USDT")
    assert btc_1["status"] == "PAPER_CANDIDATE", "BTC must be PAPER_CANDIDATE with passing OOS"
    assert btc_2["status"] == "RESEARCH_ONLY",   "BTC must be RESEARCH_ONLY with failing OOS"

    # Scenario 3: full changed to worst possible values; train/OOS identical to scenario 1
    # Score and ranking must be byte-identical; gate must still pass (full is irrelevant).
    full_bad = {"closed_trades": 0, "return_pct": -50.0, "profit_factor": 0.1,
                "win_rate_pct": 0.0, "max_drawdown_pct": 99.0, "average_r": -5.0, "trades": []}

    with patch.object(optimizer, "load_ohlcv", return_value=fake_df), \
         patch.object(optimizer, "add_indicators", side_effect=lambda df: df), \
         patch.object(optimizer, "_candidate_grid", return_value=single_param), \
         patch.object(optimizer, "_run_candidate", side_effect=_make_mock(oos_pass, oos_fail, full_bad)):
        report_3 = optimizer.build_report(
            data_dir=Path("/fake"), symbols=["BTC/USDT", "ETH/USDT"], timeframe="5m",
            balance=100.0, risk_per_trade_pct=0.005, cost_model="conservative", max_rows=n,
        )

    rows_3 = sorted(report_3["top_by_symbol"], key=lambda r: r["score"], reverse=True)

    # Invariant 5: changing full while train/OOS are constant must not change score or ranking
    assert rows_1[0]["score"] == rows_3[0]["score"], "score must not change when only full changes"
    assert rows_1[1]["score"] == rows_3[1]["score"], "score must not change when only full changes"
    assert rows_3[0]["symbol"] == "BTC/USDT", "ranking must not change when only full changes"
    assert rows_3[1]["symbol"] == "ETH/USDT", "ranking must not change when only full changes"

    # Invariant 6: even terrible full metrics must not block PAPER_CANDIDATE when OOS passes
    btc_3 = next(r for r in report_3["top_by_symbol"] if r["symbol"] == "BTC/USDT")
    assert btc_3["status"] == "PAPER_CANDIDATE", (
        "full with 0 closed_trades must not block PAPER_CANDIDATE — gate is OOS-only"
    )


def test_oos_20_trades_rejected() -> None:
    """_paper_eligible must reject when OOS has 20 trades (minimum is 50); 50 with valid temporal passes."""
    optimizer = _load_optimizer()
    good_full = {"closed_trades": 40, "return_pct": 5.0, "profit_factor": 1.2}

    oos_20 = {"closed_trades": 20, "return_pct": 3.0, "profit_factor": 1.5}
    assert optimizer._paper_eligible(good_full, oos_20) is False, (
        "20 OOS trades must be rejected (minimum is 50)"
    )

    oos_49 = {"closed_trades": 49, "return_pct": 3.0, "profit_factor": 1.5}
    assert optimizer._paper_eligible(good_full, oos_49) is False, (
        "49 OOS trades must be rejected (minimum is 50)"
    )

    _base = _dt.datetime(2024, 1, 1, tzinfo=_dt.timezone.utc)
    _trades_50 = [
        {"net_pnl": 1.0, "entry_time": (_base + _dt.timedelta(weeks=i % 4, hours=i)).isoformat()}
        for i in range(50)
    ]
    oos_50 = {"closed_trades": 50, "return_pct": 3.0, "profit_factor": 1.5, "trades": _trades_50}
    assert optimizer._paper_eligible(good_full, oos_50) is True, (
        "50 OOS trades with valid temporal distribution must pass"
    )


def test_temporal_gate_enforced_when_oos_trades_present() -> None:
    """Temporal gate is active when OOS trades carry timestamps; skipped when trades absent."""
    optimizer = _load_optimizer()

    full_ok = {"closed_trades": 50, "return_pct": 9.0, "profit_factor": 1.3}
    oos_ok  = {"closed_trades": 60, "return_pct": 4.0, "profit_factor": 1.2}

    base = _dt.datetime(2024, 1, 1, tzinfo=_dt.timezone.utc)

    # 60 trades spread evenly across 4 ISO weeks → temporal gate passes
    good_trades = [
        {"net_pnl": 1.0,
         "entry_time": (base + _dt.timedelta(weeks=i % 4, hours=i)).isoformat()}
        for i in range(60)
    ]
    # 60 trades all within one ISO week → insufficient_weeks (1 < 3) → temporal gate fails
    bad_trades = [
        {"net_pnl": 1.0,
         "entry_time": (base + _dt.timedelta(hours=i)).isoformat()}
        for i in range(60)
    ]

    # Well-spread trades: all four conditions met → eligible
    assert optimizer._paper_eligible(full_ok, {**oos_ok, "trades": good_trades}) is True, (
        "50+ trades, PF>1, P&L>0, temporal OK → must be eligible"
    )

    # Temporally concentrated trades: temporal gate fails → not eligible
    assert optimizer._paper_eligible(full_ok, {**oos_ok, "trades": bad_trades}) is False, (
        "temporal gate must reject when all trades are in one week"
    )

    # No trades supplied: temporal gate is mandatory → not eligible
    assert optimizer._paper_eligible(full_ok, {**oos_ok, "trades": []}) is False, (
        "empty trades list must fail the mandatory temporal gate"
    )
    assert optimizer._paper_eligible(full_ok, oos_ok) is False, (
        "absent 'trades' key must fail the mandatory temporal gate"
    )
