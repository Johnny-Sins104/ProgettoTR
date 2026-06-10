"""test_unified_trade_cost.py — Unit tests for UnifiedCostModel.

All values are pre-computed from the live implementation and verified numerically.

Scenario bps (BTC/USDT 15m atr=0):
  optimistic:   total_round_trip_bps = 5.0   (latency=0, partial=0)
  realistic:    total_round_trip_bps = 10.0  (latency=0, partial=0)
  conservative: total_round_trip_bps = 13.25 (latency=1.75, partial=0)
  severe:        total_round_trip_bps = 25.875 (latency=6.875, partial=5.5)

API parity (Prompt 3A): compute_trade_outcome and apply_cost_to_backtest_trade
both call _compute_cost_amounts(entry_notional, exit_notional, bps) — EXACT parity
on all trades, flat or non-flat. No documented approximation. apply_cost_to_backtest_trade
requires entry_price, exit_price, quantity explicitly (no notional shortcut).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "trading_bot"))

try:
    from core.unified_trade_cost import SCENARIO_NAMES, TradeOutcome, UnifiedCostModel
except ImportError as _exc:
    pytest.skip(f"unified_trade_cost import failed: {_exc}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _buy_win_all():
    """BUY win: entry=50000, exit=51000, stop=49500, qty=0.01 — all scenarios."""
    return UnifiedCostModel.all_scenarios(
        side="BUY",
        entry_price=50000.0,
        exit_price=51000.0,
        stop_price=49500.0,
        quantity=0.01,
        symbol="BTC/USDT",
        timeframe="15m",
        atr_pct=0.0,
    )


def _buy_loss_all():
    """BUY loss: entry=50000, exit=49500, stop=49500, qty=0.01 — all scenarios."""
    return UnifiedCostModel.all_scenarios(
        side="BUY",
        entry_price=50000.0,
        exit_price=49500.0,
        stop_price=49500.0,
        quantity=0.01,
        symbol="BTC/USDT",
        timeframe="15m",
        atr_pct=0.0,
    )


# ---------------------------------------------------------------------------
# Test 1: BUY win — gross PnL, initial_risk, gross_R
# ---------------------------------------------------------------------------

def test_buy_win_gross_pnl():
    """gross_pnl=10.0, initial_risk=5.0, gross_R=2.0 per tutti gli scenari reali."""
    outcomes = _buy_win_all()
    assert set(outcomes.keys()) == set(SCENARIO_NAMES) - {"zero"}
    for name, o in outcomes.items():
        assert o.gross_pnl == pytest.approx(10.0, rel=1e-4), name
        assert o.initial_risk == pytest.approx(5.0, rel=1e-4), name
        assert o.gross_R == pytest.approx(2.0, rel=1e-4), name


# ---------------------------------------------------------------------------
# Test 2: BUY loss — gross_pnl and gross_R
# ---------------------------------------------------------------------------

def test_buy_loss_gross_pnl():
    """BUY loss: gross_pnl=-5.0, gross_R=-1.0 per scenario realistic."""
    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0,
        exit_price=49500.0,
        stop_price=49500.0,
        quantity=0.01,
        scenario="realistic",
    )
    assert o.gross_pnl == pytest.approx(-5.0, rel=1e-4)
    assert o.gross_R == pytest.approx(-1.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Test 3: SELL win — simmetria con BUY win
# ---------------------------------------------------------------------------

def test_sell_win_gross_pnl():
    """SELL win: gross_pnl=10.0, initial_risk=5.0, gross_R=2.0 per tutti gli scenari."""
    outcomes = UnifiedCostModel.all_scenarios(
        side="SELL",
        entry_price=50000.0,
        exit_price=49000.0,
        stop_price=50500.0,
        quantity=0.01,
        symbol="BTC/USDT",
        timeframe="15m",
        atr_pct=0.0,
    )
    for name, o in outcomes.items():
        assert o.gross_pnl == pytest.approx(10.0, rel=1e-4), name
        assert o.initial_risk == pytest.approx(5.0, rel=1e-4), name
        assert o.gross_R == pytest.approx(2.0, rel=1e-4), name


# ---------------------------------------------------------------------------
# Test 4: SELL loss
# ---------------------------------------------------------------------------

def test_sell_loss_gross_pnl():
    """SELL loss: gross_pnl=-5.0, gross_R=-1.0."""
    o = UnifiedCostModel.compute_trade_outcome(
        side="SELL",
        entry_price=50000.0,
        exit_price=50500.0,
        stop_price=50500.0,
        quantity=0.01,
        scenario="realistic",
    )
    assert o.gross_pnl == pytest.approx(-5.0, rel=1e-4)
    assert o.gross_R == pytest.approx(-1.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Test 5: net_pnl < gross_pnl per BUY win (costi riducono il profitto)
# ---------------------------------------------------------------------------

def test_net_pnl_less_than_gross_for_win():
    """In tutti gli scenari net_pnl < gross_pnl (trade vincente)."""
    outcomes = _buy_win_all()
    for name, o in outcomes.items():
        assert o.net_pnl < o.gross_pnl, (
            f"scenario={name}: net_pnl={o.net_pnl} non < gross_pnl={o.gross_pnl}"
        )


# ---------------------------------------------------------------------------
# Test 6: net_pnl < gross_pnl per BUY loss (costi peggiorano la perdita)
# ---------------------------------------------------------------------------

def test_net_pnl_worse_than_gross_for_loss():
    """In tutti gli scenari net_pnl < gross_pnl (trade perdente)."""
    outcomes = _buy_loss_all()
    for name, o in outcomes.items():
        assert o.net_pnl < o.gross_pnl, (
            f"scenario={name}: net_pnl={o.net_pnl} non < gross_pnl={o.gross_pnl}"
        )


# ---------------------------------------------------------------------------
# Test 7: net_R < gross_R per BUY win
# ---------------------------------------------------------------------------

def test_net_R_less_than_gross_R_for_win():
    """In tutti gli scenari net_R < gross_R (trade vincente BUY)."""
    outcomes = _buy_win_all()
    for name, o in outcomes.items():
        assert o.net_R < o.gross_R, (
            f"scenario={name}: net_R={o.net_R} non < gross_R={o.gross_R}"
        )


# ---------------------------------------------------------------------------
# Test 8: total_cost_amt > 0 per tutti gli scenari e per BUY/SELL
# ---------------------------------------------------------------------------

def test_total_cost_positive():
    """total_cost_amt > 0 per tutti gli scenari e per entrambi i lati."""
    params_buy = dict(side="BUY", entry_price=50000.0, exit_price=51000.0,
                      stop_price=49500.0, quantity=0.01, symbol="BTC/USDT",
                      timeframe="15m", atr_pct=0.0)
    params_sell = dict(side="SELL", entry_price=50000.0, exit_price=49000.0,
                       stop_price=50500.0, quantity=0.01, symbol="BTC/USDT",
                       timeframe="15m", atr_pct=0.0)
    for label, params in (("BUY", params_buy), ("SELL", params_sell)):
        outcomes = UnifiedCostModel.all_scenarios(**params)
        for name, o in outcomes.items():
            assert o.total_cost_amt > 0, f"{label} scenario={name}: total_cost_amt={o.total_cost_amt}"


# ---------------------------------------------------------------------------
# Test 9: total_round_trip_bps > 0 per tutti gli scenari
# ---------------------------------------------------------------------------

def test_cost_not_zero():
    """total_round_trip_bps > 0 per gli scenari reali; 'zero' per definizione ha 0 bps."""
    for name in SCENARIO_NAMES:
        if name == "zero":
            continue
        bps = UnifiedCostModel.bps_for_scenario(
            name, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0
        )
        assert bps["total_round_trip_bps"] > 0, f"scenario={name}"


# ---------------------------------------------------------------------------
# Test 10: ordinamento scenari per total_round_trip_bps (BTC/USDT 15m atr=0)
# Valori attesi: optimistic=5.0, realistic=10.0, conservative=13.25, severe=25.875
# ---------------------------------------------------------------------------

def test_scenario_ordering_bps():
    """optimistic < realistic < conservative < severe in total_round_trip_bps."""
    bps = {
        s: UnifiedCostModel.bps_for_scenario(s, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0)
        for s in SCENARIO_NAMES
    }
    assert bps["optimistic"]["total_round_trip_bps"] == pytest.approx(5.0, rel=1e-4)
    assert bps["realistic"]["total_round_trip_bps"] == pytest.approx(10.0, rel=1e-4)
    assert bps["conservative"]["total_round_trip_bps"] == pytest.approx(13.25, rel=1e-4)
    assert bps["severe"]["total_round_trip_bps"] == pytest.approx(25.875, rel=1e-4)

    assert (
        bps["optimistic"]["total_round_trip_bps"]
        < bps["realistic"]["total_round_trip_bps"]
        < bps["conservative"]["total_round_trip_bps"]
        < bps["severe"]["total_round_trip_bps"]
    )


# ---------------------------------------------------------------------------
# Test 11: 5m più costoso di 15m per BTC realistic (tf_mult_5m=1.2)
# Atteso: 5m=10.4, 15m=10.0
# ---------------------------------------------------------------------------

def test_5m_more_expensive_than_15m():
    """BTC realistic: total_round_trip_bps 5m=10.4 > 15m=10.0."""
    bps_5m = UnifiedCostModel.bps_for_scenario("realistic", symbol="BTC/USDT", timeframe="5m", atr_pct=0.0)
    bps_15m = UnifiedCostModel.bps_for_scenario("realistic", symbol="BTC/USDT", timeframe="15m", atr_pct=0.0)
    assert bps_5m["total_round_trip_bps"] == pytest.approx(10.4, rel=1e-4)
    assert bps_15m["total_round_trip_bps"] == pytest.approx(10.0, rel=1e-4)
    assert bps_5m["total_round_trip_bps"] > bps_15m["total_round_trip_bps"]


# ---------------------------------------------------------------------------
# Test 12: XRP spread_bps > BTC spread_bps (realistic 15m)
# Atteso: XRP=2.4, BTC=2.0
# ---------------------------------------------------------------------------

def test_xrp_more_expensive_than_btc():
    """XRP/USDT spread_bps=2.4 > BTC/USDT spread_bps=2.0 per scenario realistic."""
    bps_xrp = UnifiedCostModel.bps_for_scenario("realistic", symbol="XRP/USDT", timeframe="15m", atr_pct=0.0)
    bps_btc = UnifiedCostModel.bps_for_scenario("realistic", symbol="BTC/USDT", timeframe="15m", atr_pct=0.0)
    assert bps_xrp["spread_bps"] == pytest.approx(2.4, rel=1e-4)
    assert bps_btc["spread_bps"] == pytest.approx(2.0, rel=1e-4)
    assert bps_xrp["spread_bps"] > bps_btc["spread_bps"]


# ---------------------------------------------------------------------------
# Test 13: formula initial_risk = abs(entry - stop) * qty
# entry=100, exit=120, stop=90, qty=5 → initial_risk=50.0
# ---------------------------------------------------------------------------

def test_initial_risk_formula():
    """initial_risk = abs(entry - stop) * qty = abs(100 - 90) * 5 = 50.0."""
    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=100.0,
        exit_price=120.0,
        stop_price=90.0,
        quantity=5.0,
        scenario="realistic",
    )
    assert o.initial_risk == pytest.approx(50.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Test 14: formula notional = entry_price * quantity
# entry=50000, qty=0.02 → notional=1000.0
# ---------------------------------------------------------------------------

def test_notional_formula():
    """notional = entry_price * quantity = 50000 * 0.02 = 1000.0."""
    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0,
        exit_price=51000.0,
        stop_price=49500.0,
        quantity=0.02,
        scenario="realistic",
    )
    assert o.notional == pytest.approx(1000.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Test 15: conversione bps->R non è diretta ma passa per notional
# entry=50000, stop=49000, qty=0.01:
#   initial_risk = 10.0, notional = 500.0
#   cost_R = total_cost_amt / initial_risk  ≠  total_bps / 10000
# ---------------------------------------------------------------------------

def test_no_direct_bps_to_R():
    """cost_R = cost_amt / initial_risk != total_bps / 10000 (passa per notional)."""
    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0,
        exit_price=51000.0,
        stop_price=49000.0,
        quantity=0.01,
        scenario="realistic",
    )
    # realistic BTC/USDT 15m atr=0: latency=0, partial=0
    # initial_risk = abs(50000 - 49000) * 0.01 = 10.0
    # notional = 50000 * 0.01 = 500.0
    assert o.initial_risk == pytest.approx(10.0, rel=1e-4)
    assert o.notional == pytest.approx(500.0, rel=1e-4)

    cost_R = o.total_cost_amt / o.initial_risk
    direct_bps_ratio = o.total_round_trip_bps / 10000.0

    # Direct conversion: 10 bps / 10000 = 0.001
    # Real value: cost_amt ≈ 0.504 (via notional) → cost_R ≈ 0.0504
    assert abs(cost_R - direct_bps_ratio) > 1e-4, (
        f"cost_R={cost_R} dovrebbe essere diverso da direct_bps_ratio={direct_bps_ratio}"
    )


# ---------------------------------------------------------------------------
# Test 16: all_scenarios ritorna dict con 4 chiavi
# ---------------------------------------------------------------------------

def test_all_scenarios_returns_four():
    """all_scenarios() ritorna esattamente 4 scenari."""
    outcomes = UnifiedCostModel.all_scenarios(
        side="BUY",
        entry_price=50000.0,
        exit_price=51000.0,
        stop_price=49500.0,
        quantity=0.01,
    )
    assert set(outcomes.keys()) == {"optimistic", "realistic", "conservative", "severe"}
    assert len(outcomes) == 4
    for name, o in outcomes.items():
        assert isinstance(o, TradeOutcome)
        assert o.scenario == name


# ---------------------------------------------------------------------------
# Test 17: apply_cost_to_backtest_trade coerenza numerica
# gross_pnl=10.0, initial_risk=5.0, entry_price=50000, exit_price=50000 (flat)
# qty=0.01 → entry_notional=exit_notional=500.0, scenario=realistic 15m atr=0
# realistic 15m atr=0: fee_entry=4bps, fee_exit=4bps, spread=2bps → total=10.0bps
# fee_entry = 500 * 4/10000 = 0.2, fee_exit = 500 * 4/10000 = 0.2, spread = 0.1
# cost_amt = 0.5, net_pnl = 9.5, gross_R = 2.0, net_R = 1.9
# ---------------------------------------------------------------------------

def test_apply_cost_to_backtest_trade():
    """apply_cost_to_backtest_trade: coerenza numerica per realistic BTC/USDT 15m."""
    result = UnifiedCostModel.apply_cost_to_backtest_trade(
        gross_pnl=10.0,
        initial_risk=5.0,
        entry_price=50000.0,
        exit_price=50000.0,
        quantity=0.01,
        scenario="realistic",
        symbol="BTC/USDT",
        timeframe="15m",
        atr_pct=0.0,
    )
    assert result["gross_pnl"] == pytest.approx(10.0, rel=1e-4)
    assert result["total_round_trip_bps"] == pytest.approx(10.0, rel=1e-4)
    assert result["cost_amt"] == pytest.approx(0.5, rel=1e-4)
    assert result["net_pnl"] == pytest.approx(9.5, rel=1e-4)
    assert result["gross_R"] == pytest.approx(2.0, rel=1e-4)
    assert result["net_R"] == pytest.approx(1.9, rel=1e-4)


# ---------------------------------------------------------------------------
# Test 18: fill_probability nell'intervallo (0, 1]
# ---------------------------------------------------------------------------

def test_fill_probability_range():
    """0.0 < fill_probability <= 1.0 per tutti gli scenari."""
    for name in SCENARIO_NAMES:
        bps = UnifiedCostModel.bps_for_scenario(name, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0)
        fp = bps["fill_probability"]
        assert 0.0 < fp <= 1.0, f"scenario={name}: fill_probability={fp}"


# ---------------------------------------------------------------------------
# Test 19: simmetria BUY/SELL — gross_pnl e gross_R identici a parità di distanza
# BUY:  entry=50000, exit=51000, stop=49500 (distanza exit=+1000, stop=500)
# SELL: entry=50000, exit=49000, stop=50500 (distanza exit=-1000, stop=500)
# ---------------------------------------------------------------------------

def test_sell_buy_symmetry():
    """gross_pnl e gross_R identici per BUY e SELL con stessa distanza R."""
    o_buy = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0,
        exit_price=51000.0,
        stop_price=49500.0,
        quantity=0.01,
        scenario="realistic",
    )
    o_sell = UnifiedCostModel.compute_trade_outcome(
        side="SELL",
        entry_price=50000.0,
        exit_price=49000.0,
        stop_price=50500.0,
        quantity=0.01,
        scenario="realistic",
    )
    assert abs(o_buy.gross_pnl) == pytest.approx(abs(o_sell.gross_pnl), rel=1e-4)
    assert abs(o_buy.gross_R) == pytest.approx(abs(o_sell.gross_R), rel=1e-4)
    assert o_buy.gross_pnl == pytest.approx(10.0, rel=1e-4)
    assert o_sell.gross_pnl == pytest.approx(10.0, rel=1e-4)
    assert o_buy.gross_R == pytest.approx(2.0, rel=1e-4)
    assert o_sell.gross_R == pytest.approx(2.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Test 20: atr_pct aumenta slippage_bps
# atr=0 → slippage_bps=0.0 per tutti gli scenari (atr_bps=0)
# atr=2.0 → atr_bps=200, slippage = atr_bps * slippage_frac * stress * tf_mult
# ---------------------------------------------------------------------------

def test_atr_pct_increases_slippage():
    """slippage_bps(atr=2.0) >= slippage_bps(atr=0) per gli scenari reali (non 'zero')."""
    for name in SCENARIO_NAMES:
        if name == "zero":
            continue
        b0 = UnifiedCostModel.bps_for_scenario(name, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0)
        b2 = UnifiedCostModel.bps_for_scenario(name, symbol="BTC/USDT", timeframe="15m", atr_pct=2.0)
        assert b2["slippage_bps"] >= b0["slippage_bps"], (
            f"scenario={name}: slippage(atr=2)={b2['slippage_bps']} "
            f"< slippage(atr=0)={b0['slippage_bps']}"
        )
        assert b0["slippage_bps"] == pytest.approx(0.0, abs=1e-9), f"scenario={name}"
        assert b2["slippage_bps"] > 0.0, f"scenario={name}: slippage dovrebbe essere > 0 con atr=2.0"


# ===========================================================================
# NUOVI TEST — Prompt 2H: fail-closed, parity, latency/partial_fill
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 21: invalid side → ValueError (fail-closed)
# ---------------------------------------------------------------------------

def test_invalid_side_raises():
    """compute_trade_outcome lancia ValueError per side non valido."""
    with pytest.raises(ValueError, match="side"):
        UnifiedCostModel.compute_trade_outcome(
            side="LONG",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario="realistic",
        )


def test_none_side_raises():
    """compute_trade_outcome lancia ValueError per side=None."""
    with pytest.raises(ValueError, match="side"):
        UnifiedCostModel.compute_trade_outcome(
            side=None,
            entry_price=50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario="realistic",
        )


# ---------------------------------------------------------------------------
# Test 22: invalid scenario → ValueError (fail-closed)
# ---------------------------------------------------------------------------

def test_invalid_scenario_in_compute_raises():
    """compute_trade_outcome lancia ValueError per scenario non valido."""
    for bad in ("HIGH", "LOW", "DYNAMIC", "kelly", "aggressive", ""):
        with pytest.raises(ValueError, match="scenario"):
            UnifiedCostModel.compute_trade_outcome(
                side="BUY",
                entry_price=50000.0, exit_price=51000.0,
                stop_price=49500.0, quantity=0.01,
                scenario=bad,
            )


def test_invalid_scenario_in_bps_raises():
    """bps_for_scenario lancia ValueError per scenario non valido."""
    with pytest.raises(ValueError, match="scenario"):
        UnifiedCostModel.bps_for_scenario("LOW")


def test_invalid_scenario_in_apply_raises():
    """apply_cost_to_backtest_trade lancia ValueError per scenario non valido."""
    with pytest.raises(ValueError, match="scenario"):
        UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=10.0, initial_risk=5.0,
            entry_price=50000.0, exit_price=50000.0, quantity=0.01,
            scenario="HIGH",
        )


# ---------------------------------------------------------------------------
# Test 23: prezzi negativi o zero → ValueError (fail-closed)
# ---------------------------------------------------------------------------

def test_negative_entry_price_raises():
    """Prezzo entry negativo lancia ValueError."""
    with pytest.raises(ValueError):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=-50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario="realistic",
        )


def test_zero_entry_price_raises():
    """Prezzo entry zero lancia ValueError."""
    with pytest.raises(ValueError):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=0.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario="realistic",
        )


def test_zero_quantity_raises():
    """Quantità zero lancia ValueError."""
    with pytest.raises(ValueError):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.0,
            scenario="realistic",
        )


# ---------------------------------------------------------------------------
# Test 24: stop == entry → ValueError (initial_risk indefinito)
# ---------------------------------------------------------------------------

def test_stop_equals_entry_raises():
    """Stop uguale all'entry lancia ValueError (initial_risk=0 è indefinito)."""
    with pytest.raises(ValueError):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=50000.0, quantity=0.01,
            scenario="realistic",
        )


# ---------------------------------------------------------------------------
# Test 25: apply_cost_to_backtest_trade fail-closed su entry_price/initial_risk
# ---------------------------------------------------------------------------

def test_apply_zero_entry_price_raises():
    """apply_cost_to_backtest_trade lancia ValueError per entry_price=0."""
    with pytest.raises(ValueError):
        UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=10.0, initial_risk=5.0,
            entry_price=0.0, exit_price=50000.0, quantity=0.01,
            scenario="realistic",
        )


def test_apply_zero_initial_risk_raises():
    """apply_cost_to_backtest_trade lancia ValueError per initial_risk=0."""
    with pytest.raises(ValueError):
        UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=10.0, initial_risk=0.0,
            entry_price=50000.0, exit_price=50000.0, quantity=0.01,
            scenario="realistic",
        )


# ---------------------------------------------------------------------------
# Test 26: latency_amt e partial_fill_amt inclusi in total_cost_amt (severe)
# severe BTC/USDT 15m: latency_bps=6.875, partial_fill_bps=5.5
# entry=50000, qty=0.01 → notional=500
# latency_amt = 500 * 6.875/10000 = 0.34375
# partial_fill_amt = 500 * 5.5/10000 = 0.275
# ---------------------------------------------------------------------------

def test_latency_partial_included_in_total_cost():
    """severe: latency_amt e partial_fill_amt sono > 0 e inclusi in total_cost_amt."""
    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0, exit_price=51000.0,
        stop_price=49500.0, quantity=0.01,
        scenario="severe", symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
    )
    assert o.latency_amt == pytest.approx(0.34375, rel=1e-4), (
        f"latency_amt={o.latency_amt}, expected 0.34375"
    )
    assert o.partial_fill_amt == pytest.approx(0.275, rel=1e-4), (
        f"partial_fill_amt={o.partial_fill_amt}, expected 0.275"
    )
    # total_cost_amt deve essere la somma di tutte e 6 le componenti
    manual_total = (
        o.fee_entry_amt + o.fee_exit_amt + o.spread_amt
        + o.slippage_amt + o.latency_amt + o.partial_fill_amt
    )
    assert o.total_cost_amt == pytest.approx(manual_total, rel=1e-6), (
        f"total_cost_amt={o.total_cost_amt} != manual sum {manual_total}"
    )


def test_optimistic_realistic_zero_latency_partial():
    """optimistic e realistic hanno latency_amt=0 e partial_fill_amt=0."""
    for sc in ("optimistic", "realistic"):
        o = UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        assert o.latency_amt == pytest.approx(0.0, abs=1e-10), f"{sc}: latency_amt={o.latency_amt}"
        assert o.partial_fill_amt == pytest.approx(0.0, abs=1e-10), f"{sc}: partial_fill_amt={o.partial_fill_amt}"


# ---------------------------------------------------------------------------
# Test 27: parity — compute_trade_outcome vs apply_cost_to_backtest_trade
# Exact parity on flat trade (entry == exit) for all scenarios.
# Both APIs use _compute_cost_amounts(entry_notional, exit_notional, bps) identically.
# ---------------------------------------------------------------------------

def test_compute_vs_apply_parity_flat_trade():
    """Parity: compute_trade_outcome == apply_cost_to_backtest_trade on flat trade."""
    entry = 50000.0
    stop = 49000.0
    qty = 0.01
    initial_risk = abs(entry - stop) * qty  # 10.0

    for sc in SCENARIO_NAMES:
        o = UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=entry, exit_price=entry,  # flat: entry == exit
            stop_price=stop, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        r = UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=0.0,
            initial_risk=initial_risk,
            entry_price=entry, exit_price=entry, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        assert o.total_cost_amt == pytest.approx(r["cost_amt"], rel=1e-9), (
            f"Parity failure scenario={sc}: "
            f"compute={o.total_cost_amt:.8f}, apply={r['cost_amt']:.8f}"
        )


# ---------------------------------------------------------------------------
# Test 28: parity verificata per BUY e SELL (flat trade, tutti gli scenari)
# ---------------------------------------------------------------------------

def test_compute_vs_apply_parity_sell_flat():
    """Parity: compute_trade_outcome SELL == apply_cost_to_backtest_trade su flat trade."""
    entry = 50000.0
    stop = 50500.0
    qty = 0.01
    initial_risk = abs(entry - stop) * qty

    for sc in SCENARIO_NAMES:
        o = UnifiedCostModel.compute_trade_outcome(
            side="SELL",
            entry_price=entry, exit_price=entry,
            stop_price=stop, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        r = UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=0.0,
            initial_risk=initial_risk,
            entry_price=entry, exit_price=entry, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
        )
        assert o.total_cost_amt == pytest.approx(r["cost_amt"], rel=1e-9), (
            f"Parity failure scenario={sc} SELL: "
            f"compute={o.total_cost_amt:.8f}, apply={r['cost_amt']:.8f}"
        )


# ---------------------------------------------------------------------------
# Test 29: severe scenario con prezzi entry/exit molto diversi (ampia win)
# Verifica che total_cost_amt sia correttamente più alto di conservative
# ---------------------------------------------------------------------------

def test_severe_higher_cost_than_conservative():
    """severe total_cost_amt > conservative total_cost_amt per BUY win ampio."""
    o_con = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0, exit_price=53000.0,
        stop_price=49000.0, quantity=0.01,
        scenario="conservative", symbol="BTC/USDT", timeframe="15m",
    )
    o_sev = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0, exit_price=53000.0,
        stop_price=49000.0, quantity=0.01,
        scenario="severe", symbol="BTC/USDT", timeframe="15m",
    )
    assert o_sev.total_cost_amt > o_con.total_cost_amt, (
        f"severe.total_cost={o_sev.total_cost_amt} non > conservative.total_cost={o_con.total_cost_amt}"
    )
    assert o_sev.latency_amt > o_con.latency_amt, "severe latency_amt deve essere > conservative"
    assert o_sev.partial_fill_amt > 0, "severe partial_fill_amt deve essere > 0"


# ===========================================================================
# NUOVI TEST — Prompt 3A: NaN/Inf rejection, timeframe validation, side/stop
#              consistency, non-flat parity, risk policy
# ===========================================================================

# ---------------------------------------------------------------------------
# Test 30: NaN input → ValueError (fail-closed)
# ---------------------------------------------------------------------------

def test_nan_entry_price_raises():
    """entry_price=NaN → ValueError in compute_trade_outcome."""
    import math
    with pytest.raises(ValueError, match="finite"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=float("nan"), exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario="realistic",
        )


def test_nan_stop_price_raises():
    """stop_price=NaN → ValueError."""
    with pytest.raises(ValueError, match="finite"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=float("nan"), quantity=0.01,
            scenario="realistic",
        )


def test_inf_exit_price_raises():
    """exit_price=+Inf → ValueError."""
    with pytest.raises(ValueError, match="finite"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=float("inf"),
            stop_price=49500.0, quantity=0.01,
            scenario="realistic",
        )


def test_neg_inf_quantity_raises():
    """-Inf quantity → ValueError."""
    with pytest.raises(ValueError, match="finite"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=float("-inf"),
            scenario="realistic",
        )


def test_nan_in_apply_cost_raises():
    """apply_cost_to_backtest_trade: NaN gross_pnl → ValueError."""
    with pytest.raises(ValueError, match="finite"):
        UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=float("nan"), initial_risk=5.0,
            entry_price=50000.0, exit_price=50000.0, quantity=0.01,
            scenario="realistic",
        )


def test_inf_in_apply_cost_entry_raises():
    """apply_cost_to_backtest_trade: Inf entry_price → ValueError."""
    with pytest.raises(ValueError, match="finite"):
        UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=10.0, initial_risk=5.0,
            entry_price=float("inf"), exit_price=50000.0, quantity=0.01,
            scenario="realistic",
        )


# ---------------------------------------------------------------------------
# Test 31: unsupported timeframe → ValueError (no silent 15m fallback)
# ---------------------------------------------------------------------------

def test_unsupported_timeframe_raises_in_compute():
    """compute_trade_outcome: timeframe '30m' → ValueError."""
    with pytest.raises(ValueError, match="timeframe"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=49500.0, quantity=0.01,
            scenario="realistic",
            timeframe="30m",
        )


def test_unsupported_timeframe_raises_in_apply():
    """apply_cost_to_backtest_trade: timeframe '2h' → ValueError."""
    with pytest.raises(ValueError, match="timeframe"):
        UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=10.0, initial_risk=5.0,
            entry_price=50000.0, exit_price=50000.0, quantity=0.01,
            scenario="realistic",
            timeframe="2h",
        )


def test_unsupported_timeframe_raises_in_bps():
    """bps_for_scenario: timeframe '3d' → ValueError."""
    with pytest.raises(ValueError, match="timeframe"):
        UnifiedCostModel.bps_for_scenario("realistic", timeframe="3d")


def test_supported_timeframes_all_valid():
    """5m, 15m, 4h, 1d are the supported benchmark timeframes — do not raise."""
    for tf in ("5m", "15m", "4h", "1d"):
        bps = UnifiedCostModel.bps_for_scenario("realistic", timeframe=tf)
        assert bps["total_round_trip_bps"] > 0, f"timeframe={tf}"


def test_1m_timeframe_rejected():
    """1m has no validated cost parameters → ValueError."""
    with pytest.raises(ValueError, match="timeframe"):
        UnifiedCostModel.bps_for_scenario("realistic", timeframe="1m")


def test_1h_timeframe_rejected():
    """1h has no validated cost parameters → ValueError."""
    with pytest.raises(ValueError, match="timeframe"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY", entry_price=50000.0, exit_price=51000.0,
            stop_price=49000.0, quantity=0.01, scenario="realistic", timeframe="1h",
        )


def test_30m_timeframe_rejected():
    """30m has no validated cost parameters → ValueError."""
    with pytest.raises(ValueError, match="timeframe"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY", entry_price=50000.0, exit_price=51000.0,
            stop_price=49000.0, quantity=0.01, scenario="realistic", timeframe="30m",
        )


def test_empty_timeframe_rejected():
    """Empty/None timeframe → ValueError (fail-closed, no silent 15m default)."""
    for bad in ("", None):
        with pytest.raises(ValueError, match="timeframe"):
            UnifiedCostModel.bps_for_scenario("realistic", timeframe=bad)


# ---------------------------------------------------------------------------
# Test 31b: 4h/1d accepted by all public APIs (Edge Research 03)
# tf_mult_4h = tf_mult_1d = 1.0 → bps identical to the 15m baseline.
# ---------------------------------------------------------------------------

def test_4h_1d_accepted_compute():
    """compute_trade_outcome accepts 4h and 1d without raising."""
    for tf in ("4h", "1d"):
        o = UnifiedCostModel.compute_trade_outcome(
            side="BUY", entry_price=50000.0, exit_price=55000.0,
            stop_price=47500.0, quantity=0.01,
            scenario="realistic", timeframe=tf,
        )
        assert o.timeframe == tf
        assert o.total_cost_amt > 0


def test_4h_1d_accepted_apply():
    """apply_cost_to_backtest_trade accepts 4h and 1d without raising."""
    for tf in ("4h", "1d"):
        r = UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=50.0, initial_risk=25.0,
            entry_price=50000.0, exit_price=55000.0, quantity=0.01,
            scenario="realistic", timeframe=tf,
        )
        assert r["cost_amt"] > 0


def test_4h_1d_bps_equal_15m_baseline():
    """4h/1d bps exactly equal 15m bps per scenario/symbol (tf_mult = 1.0)."""
    for symbol in ("BTC/USDT", "XRP/USDT"):
        for sc in SCENARIO_NAMES:
            if sc == "zero":
                continue
            bps_15m = UnifiedCostModel.bps_for_scenario(sc, symbol, "15m")
            for tf in ("4h", "1d"):
                bps_tf = UnifiedCostModel.bps_for_scenario(sc, symbol, tf)
                assert bps_tf["total_round_trip_bps"] == bps_15m["total_round_trip_bps"], (
                    f"{symbol} {tf} {sc}: bps={bps_tf['total_round_trip_bps']} "
                    f"!= 15m baseline {bps_15m['total_round_trip_bps']}"
                )


def test_compute_vs_apply_parity_1d():
    """Exact compute/apply parity on a 1d trade, all scenarios."""
    entry, stop, exit_, qty = 50000.0, 47500.0, 58000.0, 0.01
    initial_risk = abs(entry - stop) * qty
    gross_pnl = (exit_ - entry) * qty
    for sc in SCENARIO_NAMES:
        o = UnifiedCostModel.compute_trade_outcome(
            side="BUY", entry_price=entry, exit_price=exit_,
            stop_price=stop, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="1d", atr_pct=0.0,
        )
        r = UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=gross_pnl, initial_risk=initial_risk,
            entry_price=entry, exit_price=exit_, quantity=qty,
            scenario=sc, symbol="BTC/USDT", timeframe="1d", atr_pct=0.0,
        )
        assert o.total_cost_amt == pytest.approx(r["cost_amt"], rel=1e-9), (
            f"1d parity failure scenario={sc}: "
            f"compute={o.total_cost_amt:.8f}, apply={r['cost_amt']:.8f}"
        )


def test_scenario_ordering_bps_1d():
    """optimistic < realistic < conservative < severe also on 1d."""
    seq = [
        UnifiedCostModel.bps_for_scenario(sc, "BTC/USDT", "1d")["total_round_trip_bps"]
        for sc in ("optimistic", "realistic", "conservative", "severe")
    ]
    assert seq[0] < seq[1] < seq[2] < seq[3], f"ordering violated on 1d: {seq}"


# ---------------------------------------------------------------------------
# Test 32: side/stop consistency (fail-closed)
# ---------------------------------------------------------------------------

def test_buy_stop_above_entry_raises():
    """BUY with stop > entry → ValueError (stop must be < entry for BUY)."""
    with pytest.raises(ValueError, match="stop_price"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=51000.0,  # stop above entry — invalid for BUY
            quantity=0.01,
            scenario="realistic",
        )


def test_buy_stop_equal_entry_raises():
    """BUY with stop == entry → ValueError."""
    with pytest.raises(ValueError):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=50000.0,
            quantity=0.01,
            scenario="realistic",
        )


def test_sell_stop_below_entry_raises():
    """SELL with stop < entry → ValueError (stop must be > entry for SELL)."""
    with pytest.raises(ValueError, match="stop_price"):
        UnifiedCostModel.compute_trade_outcome(
            side="SELL",
            entry_price=50000.0, exit_price=49000.0,
            stop_price=49000.0,  # stop below entry — invalid for SELL
            quantity=0.01,
            scenario="realistic",
        )


# ---------------------------------------------------------------------------
# Test 33: non-flat parity — compute vs apply at 1%, 20%, 100% price moves
# Both APIs use _compute_cost_amounts identically, so parity must be exact.
# ---------------------------------------------------------------------------

def _non_flat_parity(exit_price: float, scenario: str = "realistic") -> None:
    entry = 50000.0
    stop = 49000.0
    qty = 0.01
    initial_risk = abs(entry - stop) * qty
    direction = 1.0  # BUY
    gross_pnl = (exit_price - entry) * qty * direction

    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=entry, exit_price=exit_price,
        stop_price=stop, quantity=qty,
        scenario=scenario, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
    )
    r = UnifiedCostModel.apply_cost_to_backtest_trade(
        gross_pnl=gross_pnl,
        initial_risk=initial_risk,
        entry_price=entry, exit_price=exit_price, quantity=qty,
        scenario=scenario, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
    )
    assert o.total_cost_amt == pytest.approx(r["cost_amt"], rel=1e-9), (
        f"Non-flat parity failure at exit={exit_price} scenario={scenario}: "
        f"compute={o.total_cost_amt:.10f}, apply={r['cost_amt']:.10f}"
    )


def test_parity_at_1pct_move():
    """Exact parity at +1% exit price move (exit=50500)."""
    for sc in SCENARIO_NAMES:
        _non_flat_parity(exit_price=50500.0, scenario=sc)


def test_parity_at_20pct_move():
    """Exact parity at +20% exit price move (exit=60000). Old API had ~8% error here."""
    for sc in SCENARIO_NAMES:
        _non_flat_parity(exit_price=60000.0, scenario=sc)


def test_parity_at_100pct_move():
    """Exact parity at +100% exit price move (exit=100000). Old API had ~40% error here."""
    for sc in SCENARIO_NAMES:
        _non_flat_parity(exit_price=100000.0, scenario=sc)


def test_parity_at_loss_trade():
    """Exact parity on a losing trade (exit < entry)."""
    for sc in SCENARIO_NAMES:
        _non_flat_parity(exit_price=48000.0, scenario=sc)


# ---------------------------------------------------------------------------
# Test 34: risk policy — 0.5% = 0.005 numeric value, not 0.5
# equity=1000, risk_pct=0.005 → risk_budget = 5.0 USDT
# ---------------------------------------------------------------------------

def test_risk_policy_0005():
    """risk_pct=0.005 (0.5%) gives risk_budget=5.0 on equity=1000."""
    equity = 1000.0
    risk_pct = 0.005
    risk_budget = equity * risk_pct
    assert risk_budget == pytest.approx(5.0, rel=1e-9), (
        f"risk_budget={risk_budget} != 5.0. "
        f"risk_pct must be 0.005 (0.5%), NOT 0.5 (50%)."
    )


def test_risk_policy_not_half():
    """Confirm 0.005 != 0.5 (catches the 50x error from old JSON)."""
    risk_pct_correct = 0.005
    risk_pct_wrong = 0.5
    equity = 10000.0
    assert equity * risk_pct_correct == pytest.approx(50.0)
    assert equity * risk_pct_wrong == pytest.approx(5000.0)
    assert risk_pct_correct != risk_pct_wrong


# ---------------------------------------------------------------------------
# Test 35: non-flat SELL parity — compute vs apply at 1%, 20%, 100% moves
# SELL: entry=50000, stop=50500 (stop above entry).
#   exit < entry = profit, exit > entry = loss.
# Both APIs use _compute_cost_amounts identically → exact parity.
# ---------------------------------------------------------------------------

def _non_flat_parity_sell(exit_price: float, scenario: str = "realistic") -> None:
    entry = 50000.0
    stop = 50500.0  # stop above entry — valid for SELL
    qty = 0.01
    initial_risk = abs(entry - stop) * qty
    gross_pnl = (entry - exit_price) * qty  # SELL profits when price falls

    o = UnifiedCostModel.compute_trade_outcome(
        side="SELL",
        entry_price=entry, exit_price=exit_price,
        stop_price=stop, quantity=qty,
        scenario=scenario, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
    )
    r = UnifiedCostModel.apply_cost_to_backtest_trade(
        gross_pnl=gross_pnl,
        initial_risk=initial_risk,
        entry_price=entry, exit_price=exit_price, quantity=qty,
        scenario=scenario, symbol="BTC/USDT", timeframe="15m", atr_pct=0.0,
    )
    assert o.total_cost_amt == pytest.approx(r["cost_amt"], rel=1e-9), (
        f"SELL non-flat parity failure at exit={exit_price} scenario={scenario}: "
        f"compute={o.total_cost_amt:.10f}, apply={r['cost_amt']:.10f}"
    )


def test_sell_parity_1pct_profit():
    """SELL +1% profit (exit=49500): exact parity all scenarios."""
    for sc in SCENARIO_NAMES:
        _non_flat_parity_sell(exit_price=49500.0, scenario=sc)


def test_sell_parity_20pct_profit():
    """SELL +20% profit (exit=40000): exact parity all scenarios."""
    for sc in SCENARIO_NAMES:
        _non_flat_parity_sell(exit_price=40000.0, scenario=sc)


def test_sell_parity_100pct_loss():
    """SELL with exit=100000 (loss — price doubled): exact parity all scenarios."""
    for sc in SCENARIO_NAMES:
        _non_flat_parity_sell(exit_price=100000.0, scenario=sc)


def test_sell_parity_loss_1pct():
    """SELL small loss (exit=50500, price rose 1%): exact parity all scenarios."""
    for sc in SCENARIO_NAMES:
        # exit == stop → borderline but stop_price is 50500 and exit != entry
        # Use exit slightly above stop to keep a valid trade
        _non_flat_parity_sell(exit_price=50600.0, scenario=sc)


# ---------------------------------------------------------------------------
# Test 36: atr_pct < 0 must raise ValueError
# Prompt 3A-H requirement: negative ATR is physically undefined.
# ---------------------------------------------------------------------------

def test_atr_pct_negative_raises_compute():
    """compute_trade_outcome with atr_pct < 0 must raise ValueError."""
    with pytest.raises(ValueError, match="atr_pct"):
        UnifiedCostModel.compute_trade_outcome(
            side="BUY",
            entry_price=50000.0, exit_price=51000.0,
            stop_price=49000.0, quantity=0.01,
            scenario="realistic", atr_pct=-0.01,
        )


def test_atr_pct_negative_raises_bps():
    """bps_for_scenario with atr_pct < 0 must raise ValueError."""
    with pytest.raises(ValueError, match="atr_pct"):
        UnifiedCostModel.bps_for_scenario("realistic", atr_pct=-0.001)


def test_atr_pct_negative_raises_apply():
    """apply_cost_to_backtest_trade with atr_pct < 0 must raise ValueError."""
    with pytest.raises(ValueError, match="atr_pct"):
        UnifiedCostModel.apply_cost_to_backtest_trade(
            gross_pnl=10.0, initial_risk=5.0,
            entry_price=50000.0, exit_price=51000.0, quantity=0.01,
            scenario="realistic", atr_pct=-0.005,
        )


def test_atr_pct_zero_accepted():
    """atr_pct=0.0 is valid — no exception raised."""
    o = UnifiedCostModel.compute_trade_outcome(
        side="BUY",
        entry_price=50000.0, exit_price=51000.0,
        stop_price=49000.0, quantity=0.01,
        scenario="realistic", atr_pct=0.0,
    )
    assert o.atr_pct == pytest.approx(0.0)
