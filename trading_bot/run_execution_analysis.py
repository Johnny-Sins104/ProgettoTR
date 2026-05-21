"""
run_execution_analysis.py — Institutional Execution Friction Simulation & Diagnostics
======================================================================================
Runs a full execution quality audit on the trading strategy by comparing:

  (A) NAIVE BACKTEST     — ideal fills at signal prices, no slippage
  (B) FRICTION-ADJUSTED  — realistic slippage, spread, partial fills, queue delays

Produces:
  - Terminal console dashboard with color-coded execution quality grades
  - data/execution_diagnostics_report.json (full IS attribution breakdown)
  - Rolling fill efficiency series
  - Live-vs-backtest deviation calibration report

Usage:
  python -X utf8 run_execution_analysis.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHY NAIVE BACKTESTS FAIL LIVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. SLIPPAGE ON ENTRY: A limit order placed at the signal candle's close
   faces the bid-ask spread on entry. At 1 bps spread, over 200 trades/yr,
   that's 200 bps = 2% annual drag. In HIGH_VOL regimes, this expands to
   15+ bps per entry, turning marginal setups into guaranteed losers.

2. STOP-LOSS EXECUTION SLIPPAGE: SL orders trigger as market orders.
   In fast BTC markets, a SL set at $60,000 may execute at $59,600 (−0.67%),
   increasing the effective loss on a 1% SL trade by 67%.

3. FILL RATE DEGRADATION: Limit orders that look profitable in hindsight
   (because price moved far beyond the entry) are precisely the orders
   most likely NOT to fill — the market moved away before the limit was hit.
   This "selection bias" makes naive backtests systematically optimistic.

4. PARTIAL FILLS: Large positions in thin markets may only partially fill,
   reducing the winning position size while keeping the risk of a full SL.

5. QUEUE DELAY COST: A 2-candle delay at entry means the fill price has
   moved against the entry signal. For a breakout strategy, this is
   especially damaging — the ideal entry was at the breakout, not 30m later.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HOW EXECUTION FRICTION DESTROYS EDGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Edge is the per-trade expected profit margin above a random strategy.
Friction is the per-trade expected cost from market microstructure.

If Edge < Friction, the strategy is unprofitable regardless of its
naive backtest results.

Mathematical formulation:
  Net Expected Value = (Win Rate × Avg Win × Fill Rate)
                     - (Loss Rate × Avg Loss)
                     - Round-Trip Friction Bps
                     - Commission

A strategy with:
  - 55% win rate, 2:1 R:R → gross expectancy = +5.0 bps/trade
  - Round-trip friction = 6.0 bps/trade
  - Net EV = −1.0 bps/trade → LOSS-MAKING despite positive naive backtest
"""

import os
import sys
import json
import random
import warnings
import numpy as np
import pandas as pd

# Fix Windows UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

warnings.filterwarnings("ignore")

# ── Add project root to path ──────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.slippage_model import SlippageModel, SlippageEstimate
from core.liquidity_model import LiquidityModel, FillResult
from core.execution_analytics import ExecutionAnalytics, ExecutionRecord


# ════════════════════════════════════════════════════════════════════════════
# §1 — SYNTHETIC TRADE GENERATOR (for self-contained analysis)
# ════════════════════════════════════════════════════════════════════════════

def generate_synthetic_trades(
    n_trades:     int   = 150,
    base_price:   float = 65_000.0,
    win_rate:     float = 0.52,
    avg_rr:       float = 2.0,
    regime_mix:   float = 0.55,   # fraction TRENDING
    vol_mix:      float = 0.25,   # fraction HIGH_VOL
    random_seed:  int   = 42,
) -> list:
    """
    Generate synthetic trade scenarios with realistic parameter distributions.
    Returns a list of trade dicts compatible with the execution analysis pipeline.
    """
    random.seed(random_seed)
    np.random.seed(random_seed)

    trades = []
    balance = 10_000.0
    atr_base = base_price * 0.010   # 1% ATR baseline

    for i in range(n_trades):
        # Market regime
        regime    = "TRENDING" if random.random() < regime_mix else "RANGING"
        vol_ratio = random.uniform(0.6, 3.2)
        vol_regime = SlippageModel.vol_regime_from_atr_ratio(vol_ratio)

        # Price variation
        price = base_price * (1 + random.uniform(-0.05, 0.05))
        atr   = atr_base * vol_ratio * random.uniform(0.8, 1.3)

        # Side and entry type
        side       = random.choice(["BUY", "SELL"])
        entry_type = "BREAKOUT" if regime == "TRENDING" else "LIMIT"

        # Determine trade outcome
        rr_ratio  = avg_rr * random.uniform(0.8, 1.3)
        is_winner = random.random() < (win_rate * (1.2 if regime == "TRENDING" else 0.9))

        sl_mult = Config.ATR_MULT
        if side == "BUY":
            sl_price = price - atr * sl_mult
            tp_price = price + atr * sl_mult * rr_ratio
            exit_price_theoretical = tp_price if is_winner else sl_price
        else:
            sl_price = price + atr * sl_mult
            tp_price = price - atr * sl_mult * rr_ratio
            exit_price_theoretical = tp_price if is_winner else sl_price

        # Risk-based position sizing
        risk_pct = 0.07
        risk_capital = balance * risk_pct
        risk_per_unit = abs(price - sl_price)
        if risk_per_unit > 0:
            size = risk_capital / risk_per_unit
            max_size = (balance * 8.0) / price
            size = min(size, max_size)
        else:
            size = 0.001

        notional = size * price
        volume_ratio = random.uniform(0.5, 3.0)

        trades.append({
            "id":         i + 1,
            "side":       side,
            "regime":     regime,
            "vol_regime": vol_regime,
            "vol_ratio":  vol_ratio,
            "price":      price,
            "atr":        atr,
            "sl_price":   sl_price,
            "tp_price":   tp_price,
            "exit_price_theoretical": exit_price_theoretical,
            "exit_type":  "TP" if is_winner else "SL",
            "size":       size,
            "notional":   notional,
            "entry_type": entry_type,
            "volume_ratio": volume_ratio,
            "is_winner":  is_winner,
            "balance":    balance,
        })

        # Update balance for naive scenario
        if is_winner:
            pnl = size * abs(tp_price - price) - notional * Config.COMMISSION_RATE * 2
        else:
            pnl = -size * abs(price - sl_price) - notional * Config.COMMISSION_RATE * 2
        balance = max(100.0, balance + pnl)

    return trades


# ════════════════════════════════════════════════════════════════════════════
# §2 — NAIVE BACKTEST (baseline, no friction)
# ════════════════════════════════════════════════════════════════════════════

def run_naive_backtest(trades: list) -> dict:
    """Simulate the naive backtest: ideal fills, flat commission, no slippage."""
    balance = 10_000.0
    equity_curve = [balance]
    trade_results = []
    commission_rate = Config.COMMISSION_RATE

    for t in trades:
        size      = t["size"]
        price     = t["price"]
        exit_p    = t["exit_price_theoretical"]
        side      = t["side"]
        notional  = size * price

        commission = notional * commission_rate * 2

        if side == "BUY":
            pnl = size * (exit_p - price) - commission
        else:
            pnl = size * (price - exit_p) - commission

        balance += pnl
        balance = max(0.01, balance)
        equity_curve.append(balance)
        trade_results.append({"pnl": pnl, "balance": balance})

    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd_series = (peak - eq) / peak * 100
    max_dd = float(dd_series.max())

    returns = np.diff(eq) / eq[:-1]
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0.0

    total_commission = sum(t["size"] * t["price"] * commission_rate * 2 for t in trades)
    wins  = sum(1 for t in trades if t["is_winner"])
    total = len(trades)

    return {
        "label":           "Naive Backtest (No Friction)",
        "final_balance":   balance,
        "net_pnl":         balance - 10_000.0,
        "net_pnl_pct":     (balance / 10_000.0 - 1) * 100,
        "max_drawdown":    max_dd,
        "sharpe":          sharpe,
        "win_rate":        wins / total * 100,
        "total_trades":    total,
        "total_commission":total_commission,
        "equity_curve":    equity_curve,
        "trade_results":   trade_results,
    }


# ════════════════════════════════════════════════════════════════════════════
# §3 — FRICTION-ADJUSTED BACKTEST
# ════════════════════════════════════════════════════════════════════════════

def run_friction_backtest(
    trades:         list,
    slippage_model: SlippageModel,
    liquidity_model:LiquidityModel,
    analytics:      ExecutionAnalytics,
) -> dict:
    """
    Simulate the friction-adjusted backtest with full execution modeling.
    Applies dynamic slippage, spread, partial fills, and queue delays.
    """
    balance = 10_000.0
    equity_curve = [balance]
    trade_results = []
    commission_rate = Config.COMMISSION_RATE
    missed_trades = 0
    partial_trades = 0
    total_friction_pnl_lost = 0.0

    for t in trades:
        side       = t["side"]
        price      = t["price"]
        atr        = t["atr"]
        vol_regime = t["vol_regime"]
        vol_ratio  = t["vol_ratio"]
        regime     = t["regime"]
        entry_type = t["entry_type"]
        size       = t["size"]
        notional   = t["notional"]
        exit_price_theoretical = t["exit_price_theoretical"]
        exit_type  = t["exit_type"]
        volume_ratio = t["volume_ratio"]

        # ── 1. Check fill probability ─────────────────────────────────────
        fill_result = liquidity_model.simulate_fill(
            order_size_notional=notional,
            price=price,
            volume_ratio=volume_ratio,
            vol_regime=vol_regime,
            order_type="LIMIT" if entry_type == "LIMIT" else "MARKET",
            side=side,
            entry_type=entry_type,
        )

        if fill_result.is_no_fill:
            missed_trades += 1
            continue

        if fill_result.is_partial_fill:
            partial_trades += 1

        # Use actual fill size (may be partial)
        filled_size    = fill_result.filled_size
        filled_notional = filled_size * price

        # ── 2. Entry slippage ─────────────────────────────────────────────
        entry_slip = slippage_model.estimate_slippage(
            side=side,
            entry_price=price,
            atr_val=atr,
            order_size_notional=filled_notional,
            vol_regime=vol_regime,
            order_type="LIMIT" if entry_type == "LIMIT" else "MARKET",
            entry_type=entry_type,
            atr_ratio=vol_ratio,
        )

        # ── 3. Exit slippage ──────────────────────────────────────────────
        exit_slip = slippage_model.estimate_exit_slippage(
            side=side,
            exit_price=exit_price_theoretical,
            atr_val=atr,
            order_size_notional=filled_notional,
            vol_regime=vol_regime,
            exit_type=exit_type,
            atr_ratio=vol_ratio,
        )

        actual_entry = entry_slip.adjusted_price
        actual_exit  = exit_slip.adjusted_price

        # ── 4. Commission on actual fill ───────────────────────────────────
        commission = (filled_size * actual_entry + filled_size * actual_exit) * commission_rate

        # ── 5. Compute friction-adjusted PnL ─────────────────────────────
        if side == "BUY":
            pnl = filled_size * (actual_exit - actual_entry) - commission
        else:
            pnl = filled_size * (actual_entry - actual_exit) - commission

        # Compute naive PnL for comparison
        naive_notional = size * price
        naive_commission = naive_notional * commission_rate * 2
        if side == "BUY":
            naive_pnl = size * (exit_price_theoretical - price) - naive_commission
        else:
            naive_pnl = size * (price - exit_price_theoretical) - naive_commission

        friction_cost = pnl - naive_pnl
        total_friction_pnl_lost += friction_cost

        balance += pnl
        balance = max(0.01, balance)
        equity_curve.append(balance)
        trade_results.append({"pnl": pnl, "balance": balance})

        # ── 6. Record for ExecutionAnalytics ─────────────────────────────
        analytics.record_from_slippage(
            side=side,
            regime=regime,
            vol_regime=vol_regime,
            theoretical_entry=price,
            theoretical_exit=exit_price_theoretical,
            entry_slip=entry_slip,
            exit_slip=exit_slip,
            fill_result=fill_result,
            size=size,
            atr_val=atr,
            timestamp="",
        )

    eq = np.array(equity_curve)
    peak = np.maximum.accumulate(eq)
    dd_series = (peak - eq) / peak * 100
    max_dd = float(dd_series.max())

    returns = np.diff(eq) / eq[:-1]
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 0 else 0.0

    executed_trades = len([t for t in trade_results])
    wins  = sum(1 for r in trade_results if r["pnl"] > 0)

    return {
        "label":            "Friction-Adjusted (Realistic Execution)",
        "final_balance":    balance,
        "net_pnl":          balance - 10_000.0,
        "net_pnl_pct":      (balance / 10_000.0 - 1) * 100,
        "max_drawdown":     max_dd,
        "sharpe":           sharpe,
        "win_rate":         wins / max(executed_trades, 1) * 100,
        "total_trades":     executed_trades,
        "missed_trades":    missed_trades,
        "partial_trades":   partial_trades,
        "total_friction_pnl_lost": total_friction_pnl_lost,
        "equity_curve":     equity_curve,
        "trade_results":    trade_results,
    }


# ════════════════════════════════════════════════════════════════════════════
# §4 — MAIN RUNNER
# ════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("   INSTITUTIONAL EXECUTION SIMULATION & ANALYSIS ENGINE")
    print("=" * 80)
    print()

    # ── Initialize models ─────────────────────────────────────────────────
    slippage_model = SlippageModel(
        atr_slippage_factor = Config.SLIPPAGE_ATR_FACTOR,
        spread_factor       = Config.SLIPPAGE_SPREAD_FACTOR,
        impact_factor       = Config.SLIPPAGE_IMPACT_FACTOR,
        randomize           = Config.EXECUTION_RANDOMIZE,
        random_seed         = 42,
    )

    liquidity_model = LiquidityModel(
        fill_prob_factor    = Config.FILL_PROB_FACTOR,
        partial_prob_factor = Config.PARTIAL_FILL_FACTOR,
        depth_factor        = Config.DEPTH_FACTOR,
        randomize           = Config.EXECUTION_RANDOMIZE,
        random_seed         = 42,
    )

    analytics = ExecutionAnalytics(
        rolling_window  = 50,
        commission_rate = Config.COMMISSION_RATE,
    )

    # ── Load historical BTC data if available ─────────────────────────────
    btc_price_anchor = 65_000.0
    parquet_path = os.path.join("data", "btc_15m_cache.parquet")
    if os.path.exists(parquet_path):
        try:
            import polars as pl
            df = pl.read_parquet(parquet_path).to_pandas()
            btc_price_anchor = float(df["Close"].tail(100).mean())
            print(f"  Data anchor loaded: {len(df)} BTC candles. Avg price: ${btc_price_anchor:,.0f}")
        except Exception as e:
            print(f"  Warning: Could not load parquet data ({e}). Using synthetic anchor.")
    else:
        print(f"  No parquet cache found. Using synthetic BTC anchor @ ${btc_price_anchor:,}")

    print()

    # ── Generate synthetic trades ─────────────────────────────────────────
    print("  Generating synthetic trade portfolio (150 trades)...")
    trades = generate_synthetic_trades(
        n_trades    = 150,
        base_price  = btc_price_anchor,
        win_rate    = 0.52,
        avg_rr      = 2.0,
        regime_mix  = 0.55,
        vol_mix     = 0.25,
        random_seed = 42,
    )

    regime_counts = {r: sum(1 for t in trades if t["regime"] == r) for r in ["TRENDING", "RANGING"]}
    vol_counts    = {r: sum(1 for t in trades if t["vol_regime"] == r)
                     for r in ["LOW_VOL", "NORMAL", "HIGH_VOL", "EXTREME"]}

    print(f"  Trade portfolio: {len(trades)} trades")
    print(f"  Regime mix:  TRENDING={regime_counts['TRENDING']} | RANGING={regime_counts['RANGING']}")
    for r, n in vol_counts.items():
        if n > 0:
            print(f"  {r}: {n} trades")
    print()

    # ── Run naive backtest ────────────────────────────────────────────────
    print("  Running Naive Backtest (no execution friction)...")
    naive_results = run_naive_backtest(trades)

    # ── Run friction-adjusted backtest ────────────────────────────────────
    print("  Running Friction-Adjusted Backtest (full execution model)...")
    friction_results = run_friction_backtest(
        trades, slippage_model, liquidity_model, analytics
    )

    # ── Print comparison table ─────────────────────────────────────────────
    sep = "=" * 80
    print(f"\n{sep}")
    print(f"  EXECUTION FRICTION ANALYSIS — BACKTEST COMPARISON REPORT")
    print(sep)
    print(f"  {'Metric':<35} {'Naive BT':>15}  {'Friction-Adj':>15}  {'Delta':>12}")
    print(f"  {'-'*77}")

    def comparison_row(label, naive_val, friction_val, fmt="{:.2f}", suffix=""):
        naive_str   = fmt.format(naive_val) + suffix
        friction_str = fmt.format(friction_val) + suffix
        delta = friction_val - naive_val
        sign = "+" if delta >= 0 else ""
        delta_str = f"{sign}{fmt.format(delta)}{suffix}"
        print(f"  {label:<35} {naive_str:>15}  {friction_str:>15}  {delta_str:>12}")

    comparison_row("Final Balance (€)",           naive_results["final_balance"],    friction_results["final_balance"],    fmt="{:,.2f}")
    comparison_row("Net PnL (%)",                  naive_results["net_pnl_pct"],      friction_results["net_pnl_pct"],      fmt="{:+.2f}", suffix="%")
    comparison_row("Max Drawdown (%)",             naive_results["max_drawdown"],     friction_results["max_drawdown"],     fmt="{:.2f}", suffix="%")
    comparison_row("Sharpe Ratio",                 naive_results["sharpe"],           friction_results["sharpe"],           fmt="{:.3f}")
    comparison_row("Win Rate (%)",                 naive_results["win_rate"],         friction_results["win_rate"],         fmt="{:.1f}", suffix="%")
    comparison_row("Executed Trades",              naive_results["total_trades"],     friction_results["total_trades"],     fmt="{:.0f}")
    print(f"  {'Missed Trades (no fill)':<35} {'—':>15}  {friction_results['missed_trades']:>15}  {'—':>12}")
    print(f"  {'Partial Fills':<35} {'—':>15}  {friction_results['partial_trades']:>15}  {'—':>12}")
    friction_pnl_lost = friction_results['total_friction_pnl_lost']
    sign = "+" if friction_pnl_lost >= 0 else ""
    print(f"  {'Total PnL Lost to Friction':<35} {'—':>15}  {sign}{friction_pnl_lost:>14,.2f}  {'—':>12}")
    print(sep)

    # ── Print slippage model example ──────────────────────────────────────
    print(f"\n  SLIPPAGE MODEL — EXAMPLE BREAKDOWN")
    print("-" * 80)
    example_slip = slippage_model.estimate_slippage(
        side="BUY",
        entry_price=btc_price_anchor,
        atr_val=btc_price_anchor * 0.010,
        order_size_notional=5_000.0,
        vol_regime="NORMAL",
        order_type="LIMIT",
        entry_type="BREAKOUT",
        atr_ratio=1.0,
    )
    print(slippage_model.describe_estimate(example_slip))

    print(f"\n  HIGH_VOL REGIME (stress scenario):")
    hv_slip = slippage_model.estimate_slippage(
        side="BUY",
        entry_price=btc_price_anchor,
        atr_val=btc_price_anchor * 0.025,
        order_size_notional=5_000.0,
        vol_regime="HIGH_VOL",
        order_type="STOP",
        entry_type="BREAKOUT",
        atr_ratio=1.8,
    )
    print(slippage_model.describe_estimate(hv_slip))

    # ── Print execution analytics dashboard ───────────────────────────────
    summary = analytics.compute_summary()
    analytics.print_dashboard(summary)

    # ── Print liquidity fill statistics ──────────────────────────────────
    print(f"  LIQUIDITY MODEL — FILL STATISTICS")
    print("-" * 80)
    print(f"  Complete Fill Rate : {summary.n_complete_fills / max(summary.n_trades, 1) * 100:.1f}%")
    print(f"  Partial Fill Rate  : {summary.n_partial_fills  / max(summary.n_trades, 1) * 100:.1f}%")
    print(f"  Avg Fill Fraction  : {summary.avg_fill_pct * 100:.1f}%")
    print(f"  Avg Queue Delay    : {summary.avg_fill_delay_candles:.2f} candles")

    # ── Live vs backtest deviation analysis ───────────────────────────────
    print(f"\n  LIVE vs BACKTEST DEVIATION DIAGNOSTICS")
    print("-" * 80)
    deviation = analytics.compute_live_vs_backtest_deviation(
        backtest_slippage_bps=0.0,   # Naive backtest has zero slippage
        backtest_fill_rate=1.0,
    )
    print(f"  Naive BT Slippage    : 0.00 bps (ideal fills)")
    print(f"  Friction Model Slip  : {summary.avg_round_trip_bps:.2f} bps (realistic execution)")
    print(f"  Slippage Gap         : +{summary.avg_round_trip_bps:.2f} bps per trade")
    print(f"  Fill Rate Gap        : {deviation.fill_rate_deviation:+.2f} ({deviation.fill_rate_deviation*100:+.1f}%)")
    annual_drag = summary.avg_round_trip_bps * naive_results["total_trades"] / 10_000 * 100
    print(f"  Estimated Annual Drag: {annual_drag:.2f}% ({naive_results['total_trades']} trades × {summary.avg_round_trip_bps:.1f} bps)")
    print(f"  Calibration Factor   : {deviation.recommended_slippage_factor:.2f}x slippage | {deviation.recommended_fill_factor:.2f}x fill rate")
    print()

    # ── Quant Corner ──────────────────────────────────────────────────────
    print("=" * 80)
    print("  QUANT CORNER — EXECUTION FRICTION THEORY")
    print("=" * 80)
    print("""
  1. WHY NAIVE BACKTESTS FAIL LIVE:
     Naive backtests assume fills at signal prices with flat commissions.
     Three structural failures make them systematically optimistic:

     (A) BID-ASK SPREAD: Every entry costs half the spread on entry and exit.
         At 1 bps spread on BTC, 200 annual trades = 200 bps = 2% annual drag.

     (B) STOP-LOSS SLIPPAGE: SL orders execute as market orders in fast markets.
         A 0.5% SL set at $60,000 may fill at $59,700 = 0.8% actual loss.

     (C) BREAKOUT FILL BIAS: The best breakout entries (that go far) are the
         ones limit orders never fill. Backtests overstate win rates because
         they assume filling at the ideal entry on all setups.

  2. HOW EXECUTION FRICTION DESTROYS EDGE:
     Edge = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
     For a 55% WR / 2:1 R:R system: Edge = 0.55×2 - 0.45×1 = 0.65 R/trade

     Round-trip friction of 5 bps on $5,000 notional = $2.50/trade
     If edge = $3.00/trade and friction = $2.50/trade, 83% of edge is destroyed.

     This is why institutional desks spend more engineering effort on execution
     optimization than on signal generation — the "last mile" of execution
     determines whether a strategy is profitable or ruin-inducing.
    """)
    print("=" * 80)

    # ── Export JSON report ────────────────────────────────────────────────
    os.makedirs("data", exist_ok=True)
    report_path = os.path.join("data", "execution_diagnostics_report.json")
    analytics.export_report(
        path=report_path,
        include_records=True,
        backtest_naive_pnl=naive_results["net_pnl"],
    )

    # Also write a simple comparison summary
    comparison_data = {
        "metadata": {
            "generated_at": pd.Timestamp.now().isoformat(),
            "n_synthetic_trades": len(trades),
            "btc_price_anchor": btc_price_anchor,
        },
        "naive_backtest": {
            "label":          naive_results["label"],
            "final_balance":  naive_results["final_balance"],
            "net_pnl_pct":    naive_results["net_pnl_pct"],
            "max_drawdown":   naive_results["max_drawdown"],
            "sharpe":         naive_results["sharpe"],
            "win_rate":       naive_results["win_rate"],
            "total_trades":   naive_results["total_trades"],
        },
        "friction_backtest": {
            "label":          friction_results["label"],
            "final_balance":  friction_results["final_balance"],
            "net_pnl_pct":    friction_results["net_pnl_pct"],
            "max_drawdown":   friction_results["max_drawdown"],
            "sharpe":         friction_results["sharpe"],
            "win_rate":       friction_results["win_rate"],
            "total_trades":   friction_results["total_trades"],
            "missed_trades":  friction_results["missed_trades"],
            "partial_trades": friction_results["partial_trades"],
        },
        "friction_metrics": {
            "avg_entry_slippage_bps": summary.avg_entry_slippage_bps,
            "avg_exit_slippage_bps":  summary.avg_exit_slippage_bps,
            "avg_round_trip_bps":     summary.avg_round_trip_bps,
            "avg_is_bps":             summary.avg_is_bps,
            "p95_slippage_bps":       summary.p95_slippage_bps,
            "total_pnl_degradation":  summary.total_pnl_degradation,
            "degradation_pct":        summary.degradation_pct,
        },
    }

    comparison_path = os.path.join("data", "execution_comparison_report.json")
    with open(comparison_path, "w", encoding="utf-8") as fh:
        json.dump(comparison_data, fh, indent=2)
    print(f"  Comparison summary exported -> {comparison_path}")
    print()


if __name__ == "__main__":
    main()
