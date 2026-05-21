"""
core/execution_analytics.py — Institutional Execution Quality Analytics Engine
===============================================================================
Tracks, computes, and reports execution quality metrics for a crypto futures
trading system. Identifies systematic live-vs-backtest deviations.

  1. FILL EFFICIENCY         — actual fill price vs theoretical signal price
  2. IMPLEMENTATION SHORTFALL— total cost of execution (IS framework)
  3. SLIPPAGE ATTRIBUTION    — breakdown by source (spread, impact, delay, urgency)
  4. LIVE vs BACKTEST DEVIATION — detects systematic execution degradation
  5. ROLLING QUALITY SCORES  — trends in execution efficiency over time

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  THE IMPLEMENTATION SHORTFALL FRAMEWORK (Perold 1988)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Implementation Shortfall (IS) is the total cost of executing a trade,
measured as the difference between:
  - The "paper" portfolio return (at ideal signal prices)
  - The actual portfolio return (at real execution prices)

IS Components:
  (A) Explicit costs: Commission + fees (known and modelled)
  (B) Spread cost: Paying the bid-ask spread at entry and exit
  (C) Market impact: Adverse price movement caused by our own order
  (D) Delay cost: Price movement during the delay between decision and fill
  (E) Opportunity cost: Cost of not filling (missed trades that would've won)

Total IS = explicit + spread + impact + delay + opportunity cost

A robust execution model must track all five components to accurately
predict live performance from backtest results.
"""

from __future__ import annotations

import json
import math
import os
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

from core.slippage_model import SlippageEstimate
from core.liquidity_model import FillResult


# ════════════════════════════════════════════════════════════════════════════
# §1 — DATA STRUCTURES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ExecutionRecord:
    """
    Complete record of a single trade's execution versus its theoretical ideal.
    Captures all five components of Implementation Shortfall.
    """
    # Identity
    trade_id:               int   = 0
    timestamp:              str   = ""
    side:                   str   = "BUY"
    regime:                 str   = "RANGING"
    vol_regime:             str   = "NORMAL"

    # Prices
    theoretical_entry:      float = 0.0   # ideal signal price (naive backtest)
    actual_entry:           float = 0.0   # actual simulated fill price
    theoretical_exit:       float = 0.0   # ideal SL/TP price
    actual_exit:            float = 0.0   # actual simulated exit price

    # Trade parameters
    size:                   float = 0.0   # filled size (may be < requested)
    requested_size:         float = 0.0   # requested position size
    atr_val:                float = 0.0

    # Slippage components at entry (in bps)
    entry_spread_bps:       float = 0.0
    entry_impact_bps:       float = 0.0
    entry_slippage_bps:     float = 0.0   # total at entry
    entry_urgency_bps:      float = 0.0

    # Slippage components at exit (in bps)
    exit_spread_bps:        float = 0.0
    exit_impact_bps:        float = 0.0
    exit_slippage_bps:      float = 0.0   # total at exit
    exit_urgency_bps:       float = 0.0

    # Fill quality
    fill_pct:               float = 1.0   # fraction of order filled [0, 1]
    fill_delay_candles:     int   = 0     # candles waited before fill
    was_partial_fill:       bool  = False
    was_no_fill:            bool  = False

    # Commission
    commission_paid:        float = 0.0   # in base currency units

    # PnL comparison
    theoretical_pnl:        float = 0.0   # PnL at ideal prices
    actual_pnl:             float = 0.0   # PnL at friction-adjusted prices
    pnl_degradation:        float = 0.0   # actual - theoretical (negative = worse)
    pnl_degradation_bps:    float = 0.0   # degradation as % of notional in bps

    # Total IS
    total_is_bps:           float = 0.0   # Implementation Shortfall in bps
    round_trip_cost_bps:    float = 0.0   # entry + exit friction in bps


@dataclass
class ExecutionSummary:
    """Aggregated execution quality metrics across all recorded trades."""
    n_trades:               int   = 0
    n_complete_fills:       int   = 0
    n_partial_fills:        int   = 0
    n_no_fills:             int   = 0

    # Average friction metrics (in basis points)
    avg_entry_slippage_bps: float = 0.0
    avg_exit_slippage_bps:  float = 0.0
    avg_round_trip_bps:     float = 0.0
    avg_is_bps:             float = 0.0

    # Worst case
    max_slippage_bps:       float = 0.0
    p95_slippage_bps:       float = 0.0   # 95th percentile slippage

    # Fill efficiency
    avg_fill_pct:           float = 1.0
    avg_fill_delay_candles: float = 0.0

    # Attribution (% of total IS by source)
    spread_pct_of_is:       float = 0.0
    impact_pct_of_is:       float = 0.0
    delay_pct_of_is:        float = 0.0
    commission_pct_of_is:   float = 0.0

    # PnL impact
    total_theoretical_pnl:  float = 0.0
    total_actual_pnl:       float = 0.0
    total_pnl_degradation:  float = 0.0
    degradation_pct:        float = 0.0   # % of theoretical PnL lost to friction

    # Regime breakdown
    by_vol_regime:          Dict[str, float] = field(default_factory=dict)
    by_market_regime:       Dict[str, float] = field(default_factory=dict)

    # Diagnostics metadata
    timestamp:              str   = ""
    window_size:            int   = 0     # rolling window size used


@dataclass
class LiveVsBacktestDeviation:
    """
    Tracks systematic deviation between backtest assumptions and live execution.
    Used to calibrate the simulation model to match observed live performance.
    """
    # Observed live metrics
    live_avg_slippage_bps:  float = 0.0
    live_fill_rate:         float = 0.0
    live_partial_fill_rate: float = 0.0

    # Backtest assumptions
    bt_avg_slippage_bps:    float = 0.0
    bt_fill_rate:           float = 1.0
    bt_partial_fill_rate:   float = 0.0

    # Deviation measures
    slippage_deviation_bps: float = 0.0   # live - backtest slippage
    fill_rate_deviation:    float = 0.0   # live - backtest fill rate
    net_alpha_decay:        float = 0.0   # PnL lost due to execution gap

    # Calibration recommendations
    recommended_slippage_factor: float = 1.0
    recommended_fill_factor:     float = 1.0


# ════════════════════════════════════════════════════════════════════════════
# §2 — EXECUTION ANALYTICS ENGINE
# ════════════════════════════════════════════════════════════════════════════

class ExecutionAnalytics:
    """
    Tracks and computes execution quality metrics across the backtest lifecycle.

    Usage
    -----
    analytics = ExecutionAnalytics()

    # After each trade:
    analytics.record_execution(record)

    # After backtest completes:
    summary = analytics.compute_summary()
    analytics.print_dashboard(summary)
    analytics.export_report("data/execution_diagnostics_report.json")
    """

    def __init__(
        self,
        rolling_window:       int   = 50,
        commission_rate:      float = 0.0002,
        live_slippage_bps:    Optional[float] = None,   # calibrated from live data
        live_fill_rate:       Optional[float] = None,   # calibrated from live data
    ):
        self.rolling_window    = rolling_window
        self.commission_rate   = commission_rate
        self.live_slippage_bps = live_slippage_bps
        self.live_fill_rate    = live_fill_rate

        # Storage
        self._records: List[ExecutionRecord] = []
        self._rolling: Deque[ExecutionRecord] = deque(maxlen=rolling_window)
        self._trade_counter = 0

    # ── Record a single execution event ──────────────────────────────────────

    def record_from_slippage(
        self,
        side:               str,
        regime:             str,
        vol_regime:         str,
        theoretical_entry:  float,
        theoretical_exit:   float,
        entry_slip:         SlippageEstimate,
        exit_slip:          SlippageEstimate,
        fill_result:        FillResult,
        size:               float,
        atr_val:            float,
        timestamp:          str = "",
    ) -> ExecutionRecord:
        """
        Create an ExecutionRecord from SlippageEstimate + FillResult data.
        Computes PnL comparison and implementation shortfall automatically.
        """
        self._trade_counter += 1

        actual_entry = entry_slip.adjusted_price
        actual_exit  = exit_slip.adjusted_price
        filled_size  = fill_result.filled_size

        # Commission: paid on actual fill
        notional_entry = filled_size * actual_entry
        notional_exit  = filled_size * actual_exit
        commission = (notional_entry + notional_exit) * self.commission_rate

        # Theoretical PnL (naive backtest)
        if side == "BUY":
            theoretical_pnl = size * (theoretical_exit - theoretical_entry)
            actual_pnl      = filled_size * (actual_exit - actual_entry) - commission
        else:
            theoretical_pnl = size * (theoretical_entry - theoretical_exit)
            actual_pnl      = filled_size * (actual_entry - actual_exit) - commission

        # If no fill — opportunity cost
        if fill_result.is_no_fill:
            actual_pnl = 0.0

        pnl_degradation = actual_pnl - theoretical_pnl

        # IS in bps (relative to notional)
        notional_ref = size * theoretical_entry if theoretical_entry > 0 else 1.0
        pnl_deg_bps = (-pnl_degradation / notional_ref) * 10_000 if notional_ref > 0 else 0.0

        # Round-trip cost in bps
        round_trip_bps = entry_slip.total_slippage_bps + exit_slip.total_slippage_bps

        # Total IS = round-trip slippage + commission + fill-rate shortfall
        commission_bps = (commission / notional_ref) * 10_000 if notional_ref > 0 else 0.0
        # Opportunity cost bps if partial/no fill
        opp_cost_bps = 0.0
        if fill_result.is_partial_fill:
            # Estimate cost of not filling the remaining fraction
            unfilled_fraction = 1.0 - fill_result.fill_pct
            opp_cost_bps = unfilled_fraction * 20.0  # Proxy: 20 bps per unfilled unit
        elif fill_result.is_no_fill:
            opp_cost_bps = 50.0  # Full miss: assume missed positive expectancy

        total_is_bps = round_trip_bps + commission_bps + opp_cost_bps

        record = ExecutionRecord(
            trade_id=self._trade_counter,
            timestamp=timestamp or datetime.now().isoformat(),
            side=side,
            regime=regime,
            vol_regime=vol_regime,
            theoretical_entry=theoretical_entry,
            actual_entry=actual_entry,
            theoretical_exit=theoretical_exit,
            actual_exit=actual_exit,
            size=filled_size,
            requested_size=size,
            atr_val=atr_val,
            # Entry slippage breakdown
            entry_spread_bps=SlippageEstimate.total_slippage_bps if False else (
                entry_slip.half_spread / theoretical_entry * 10_000 if theoretical_entry > 0 else 0.0
            ),
            entry_impact_bps=(entry_slip.volume_impact / theoretical_entry * 10_000
                              if theoretical_entry > 0 else 0.0),
            entry_slippage_bps=entry_slip.total_slippage_bps,
            entry_urgency_bps=(entry_slip.urgency_premium / theoretical_entry * 10_000
                               if theoretical_entry > 0 else 0.0),
            # Exit slippage breakdown
            exit_spread_bps=(exit_slip.half_spread / theoretical_exit * 10_000
                             if theoretical_exit > 0 else 0.0),
            exit_impact_bps=(exit_slip.volume_impact / theoretical_exit * 10_000
                             if theoretical_exit > 0 else 0.0),
            exit_slippage_bps=exit_slip.total_slippage_bps,
            exit_urgency_bps=(exit_slip.urgency_premium / theoretical_exit * 10_000
                              if theoretical_exit > 0 else 0.0),
            # Fill quality
            fill_pct=fill_result.fill_pct,
            fill_delay_candles=fill_result.fill_delay_candles,
            was_partial_fill=fill_result.is_partial_fill,
            was_no_fill=fill_result.is_no_fill,
            commission_paid=commission,
            # PnL comparison
            theoretical_pnl=theoretical_pnl,
            actual_pnl=actual_pnl,
            pnl_degradation=pnl_degradation,
            pnl_degradation_bps=pnl_deg_bps,
            total_is_bps=total_is_bps,
            round_trip_cost_bps=round_trip_bps,
        )

        self._records.append(record)
        self._rolling.append(record)
        return record

    def record_execution(self, record: ExecutionRecord) -> None:
        """Record a pre-built ExecutionRecord directly."""
        self._records.append(record)
        self._rolling.append(record)

    # ── Analytics computation ─────────────────────────────────────────────────

    def compute_summary(
        self,
        use_rolling: bool = False,
    ) -> ExecutionSummary:
        """
        Compute aggregated execution quality metrics.

        Parameters
        ----------
        use_rolling : if True, compute only over the last `rolling_window` trades
        """
        records = list(self._rolling) if use_rolling else self._records
        n = len(records)

        if n == 0:
            return ExecutionSummary(timestamp=datetime.now().isoformat())

        summary = ExecutionSummary(
            n_trades=n,
            n_complete_fills=sum(1 for r in records if not r.was_partial_fill and not r.was_no_fill),
            n_partial_fills=sum(1 for r in records if r.was_partial_fill),
            n_no_fills=sum(1 for r in records if r.was_no_fill),
            timestamp=datetime.now().isoformat(),
            window_size=self.rolling_window if use_rolling else n,
        )

        # ── Slippage metrics ──────────────────────────────────────────────
        entry_bps = np.array([r.entry_slippage_bps for r in records])
        exit_bps  = np.array([r.exit_slippage_bps  for r in records])
        rt_bps    = np.array([r.round_trip_cost_bps for r in records])
        is_bps    = np.array([r.total_is_bps        for r in records])

        summary.avg_entry_slippage_bps = float(entry_bps.mean()) if len(entry_bps) else 0.0
        summary.avg_exit_slippage_bps  = float(exit_bps.mean())  if len(exit_bps)  else 0.0
        summary.avg_round_trip_bps     = float(rt_bps.mean())    if len(rt_bps)    else 0.0
        summary.avg_is_bps             = float(is_bps.mean())    if len(is_bps)    else 0.0
        summary.max_slippage_bps       = float(rt_bps.max())     if len(rt_bps)    else 0.0
        summary.p95_slippage_bps       = float(np.percentile(rt_bps, 95)) if len(rt_bps) > 1 else 0.0

        # ── Fill quality ──────────────────────────────────────────────────
        fill_pcts = np.array([r.fill_pct for r in records])
        delays    = np.array([r.fill_delay_candles for r in records])
        summary.avg_fill_pct           = float(fill_pcts.mean()) if len(fill_pcts) else 1.0
        summary.avg_fill_delay_candles = float(delays.mean())    if len(delays)    else 0.0

        # ── PnL impact ────────────────────────────────────────────────────
        theo_pnls   = [r.theoretical_pnl for r in records]
        actual_pnls = [r.actual_pnl      for r in records]
        summary.total_theoretical_pnl = sum(theo_pnls)
        summary.total_actual_pnl      = sum(actual_pnls)
        summary.total_pnl_degradation = summary.total_actual_pnl - summary.total_theoretical_pnl

        if abs(summary.total_theoretical_pnl) > 0:
            summary.degradation_pct = abs(
                summary.total_pnl_degradation / summary.total_theoretical_pnl * 100
            )

        # ── IS Attribution ────────────────────────────────────────────────
        total_is = float(is_bps.sum())
        if total_is > 0:
            spread_total = sum(r.entry_spread_bps + r.exit_spread_bps for r in records)
            impact_total = sum(r.entry_impact_bps + r.exit_impact_bps for r in records)
            comm_total   = sum(r.commission_paid / max(r.requested_size * r.theoretical_entry, 1)
                               * 10_000 for r in records)
            delay_total  = sum(r.fill_delay_candles * 2.0 for r in records)  # 2 bps proxy per candle

            summary.spread_pct_of_is     = spread_total / total_is * 100
            summary.impact_pct_of_is     = impact_total / total_is * 100
            summary.commission_pct_of_is = comm_total   / total_is * 100
            summary.delay_pct_of_is      = delay_total  / total_is * 100

        # ── Regime breakdown ──────────────────────────────────────────────
        for regime in ("LOW_VOL", "NORMAL", "HIGH_VOL", "EXTREME"):
            sub = [r for r in records if r.vol_regime == regime]
            if sub:
                avg_slip = float(np.mean([r.round_trip_cost_bps for r in sub]))
                summary.by_vol_regime[regime] = avg_slip

        for regime in ("TRENDING", "RANGING"):
            sub = [r for r in records if r.regime == regime]
            if sub:
                avg_slip = float(np.mean([r.round_trip_cost_bps for r in sub]))
                summary.by_market_regime[regime] = avg_slip

        return summary

    def compute_live_vs_backtest_deviation(
        self,
        backtest_slippage_bps: float,
        backtest_fill_rate:    float = 1.0,
    ) -> LiveVsBacktestDeviation:
        """
        Compare live execution metrics against backtest assumptions.
        Returns deviation analysis and calibration recommendations.
        """
        summary = self.compute_summary()

        live_slip = summary.avg_round_trip_bps
        live_fill = summary.avg_fill_pct

        deviation = LiveVsBacktestDeviation(
            live_avg_slippage_bps  = live_slip,
            live_fill_rate         = live_fill,
            live_partial_fill_rate = summary.n_partial_fills / max(summary.n_trades, 1),
            bt_avg_slippage_bps    = backtest_slippage_bps,
            bt_fill_rate           = backtest_fill_rate,
            bt_partial_fill_rate   = 0.0,
            slippage_deviation_bps = live_slip - backtest_slippage_bps,
            fill_rate_deviation    = live_fill - backtest_fill_rate,
        )

        # Net alpha decay from execution gap
        # Approx: each bps of extra slippage costs ~(n_trades × notional × bps/10000)
        deviation.net_alpha_decay = deviation.slippage_deviation_bps * summary.n_trades / 10_000

        # Calibration recommendations
        if backtest_slippage_bps > 0:
            deviation.recommended_slippage_factor = live_slip / backtest_slippage_bps
        else:
            deviation.recommended_slippage_factor = 1.0

        if backtest_fill_rate > 0:
            deviation.recommended_fill_factor = live_fill / backtest_fill_rate
        else:
            deviation.recommended_fill_factor = 1.0

        return deviation

    def compute_rolling_fill_efficiency(self) -> List[float]:
        """
        Returns a list of rolling fill efficiency scores (one per trade).
        Fill efficiency = actual_pnl / theoretical_pnl for each trade.
        Values < 1.0 indicate execution degraded performance.
        """
        efficiencies = []
        for r in self._records:
            if abs(r.theoretical_pnl) > 0.001:
                eff = r.actual_pnl / r.theoretical_pnl
            elif r.was_no_fill:
                eff = 0.0
            else:
                eff = 1.0
            efficiencies.append(eff)
        return efficiencies

    # ── Console dashboard ─────────────────────────────────────────────────────

    def print_dashboard(
        self,
        summary: Optional[ExecutionSummary] = None,
        width: int = 80,
    ) -> None:
        """Print a rich execution quality dashboard to stdout."""
        if summary is None:
            summary = self.compute_summary()

        sep  = "=" * width
        hsep = "-" * width

        def row(label: str, value: str, indent: int = 2) -> str:
            pad  = " " * indent
            dots = "." * max(1, width - indent - len(label) - len(value) - 2)
            return f"{pad}{label} {dots} {value}"

        def grade(val: float, bad: float, warn: float, good: float) -> str:
            if val <= good:  return "EXCELLENT"
            if val <= warn:  return "GOOD"
            if val <= bad:   return "WARNING"
            return "CRITICAL"

        print(f"\n{sep}")
        print(f"  EXECUTION QUALITY ANALYTICS DASHBOARD")
        print(f"  Trades Analysed: {summary.n_trades}  |  Window: {summary.window_size}")
        print(sep)

        # Fill quality
        print(f"\n  A — ORDER FILL QUALITY")
        print(hsep)
        print(row("Complete Fills",       f"{summary.n_complete_fills} ({summary.n_complete_fills/max(summary.n_trades,1)*100:.1f}%)"))
        print(row("Partial Fills",        f"{summary.n_partial_fills} ({summary.n_partial_fills/max(summary.n_trades,1)*100:.1f}%)"))
        print(row("No-Fill (Missed)",     f"{summary.n_no_fills} ({summary.n_no_fills/max(summary.n_trades,1)*100:.1f}%)"))
        print(row("Avg Fill Fraction",    f"{summary.avg_fill_pct*100:.1f}%"))
        print(row("Avg Fill Delay",       f"{summary.avg_fill_delay_candles:.2f} candles"))

        # Slippage metrics
        print(f"\n  B — EXECUTION FRICTION (BASIS POINTS)")
        print(hsep)
        entry_g = grade(summary.avg_entry_slippage_bps, 10, 5, 2)
        exit_g  = grade(summary.avg_exit_slippage_bps,  15, 8, 3)
        rt_g    = grade(summary.avg_round_trip_bps,     25, 12, 5)
        print(row("Avg Entry Slippage",   f"{summary.avg_entry_slippage_bps:.2f} bps  [{entry_g}]"))
        print(row("Avg Exit Slippage",    f"{summary.avg_exit_slippage_bps:.2f} bps  [{exit_g}]"))
        print(row("Avg Round-Trip Cost",  f"{summary.avg_round_trip_bps:.2f} bps  [{rt_g}]"))
        print(row("Avg Total IS",         f"{summary.avg_is_bps:.2f} bps"))
        print(row("P95 Slippage",         f"{summary.p95_slippage_bps:.2f} bps  (worst 5% of trades)"))
        print(row("Max Observed Slip",    f"{summary.max_slippage_bps:.2f} bps"))

        # IS Attribution
        if summary.avg_is_bps > 0:
            print(f"\n  C — IS ATTRIBUTION (% of Total Friction)")
            print(hsep)
            print(row("  Spread Cost",        f"{summary.spread_pct_of_is:.1f}%"))
            print(row("  Market Impact",      f"{summary.impact_pct_of_is:.1f}%"))
            print(row("  Commission",         f"{summary.commission_pct_of_is:.1f}%"))
            print(row("  Queue Delay",        f"{summary.delay_pct_of_is:.1f}%"))

        # PnL impact
        print(f"\n  D — PNL IMPACT OF EXECUTION FRICTION")
        print(hsep)
        sign = "+" if summary.total_theoretical_pnl >= 0 else ""
        sign2 = "+" if summary.total_actual_pnl >= 0 else ""
        sign3 = "+" if summary.total_pnl_degradation >= 0 else ""
        print(row("Theoretical PnL (naive)", f"{sign}{summary.total_theoretical_pnl:,.4f}"))
        print(row("Actual PnL (friction-adj)", f"{sign2}{summary.total_actual_pnl:,.4f}"))
        print(row("PnL Degradation",         f"{sign3}{summary.total_pnl_degradation:,.4f}  ({summary.degradation_pct:.2f}% of theoretical)"))

        # Regime breakdown
        if summary.by_vol_regime:
            print(f"\n  E — FRICTION BY VOLATILITY REGIME (Round-Trip bps)")
            print(hsep)
            for regime, avg_bps in sorted(summary.by_vol_regime.items()):
                g = grade(avg_bps, 25, 12, 5)
                print(row(f"  {regime}", f"{avg_bps:.2f} bps  [{g}]"))

        if summary.by_market_regime:
            print(f"\n  F — FRICTION BY MARKET REGIME")
            print(hsep)
            for regime, avg_bps in sorted(summary.by_market_regime.items()):
                print(row(f"  {regime}", f"{avg_bps:.2f} bps"))

        print(f"\n{sep}\n")

    # ── Export ────────────────────────────────────────────────────────────────

    def export_report(
        self,
        path:               str,
        include_records:    bool = True,
        backtest_naive_pnl: Optional[float] = None,
    ) -> str:
        """
        Export a full execution diagnostics report to JSON.

        Parameters
        ----------
        path               : output file path
        include_records    : whether to include individual trade records
        backtest_naive_pnl : naive backtest PnL for deviation comparison

        Returns the path written.
        """
        summary = self.compute_summary()

        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "n_trades": summary.n_trades,
                "rolling_window": self.rolling_window,
                "commission_rate": self.commission_rate,
            },
            "fill_quality": {
                "complete_fills":       summary.n_complete_fills,
                "partial_fills":        summary.n_partial_fills,
                "no_fills":             summary.n_no_fills,
                "avg_fill_fraction_pct": summary.avg_fill_pct * 100,
                "avg_fill_delay_candles": summary.avg_fill_delay_candles,
            },
            "friction_metrics_bps": {
                "avg_entry_slippage":   summary.avg_entry_slippage_bps,
                "avg_exit_slippage":    summary.avg_exit_slippage_bps,
                "avg_round_trip":       summary.avg_round_trip_bps,
                "avg_total_is":         summary.avg_is_bps,
                "p95_slippage":         summary.p95_slippage_bps,
                "max_slippage":         summary.max_slippage_bps,
            },
            "is_attribution_pct": {
                "spread":               summary.spread_pct_of_is,
                "market_impact":        summary.impact_pct_of_is,
                "commission":           summary.commission_pct_of_is,
                "queue_delay":          summary.delay_pct_of_is,
            },
            "pnl_impact": {
                "theoretical_pnl":      summary.total_theoretical_pnl,
                "actual_pnl":           summary.total_actual_pnl,
                "pnl_degradation":      summary.total_pnl_degradation,
                "degradation_pct":      summary.degradation_pct,
            },
            "regime_breakdown": {
                "by_vol_regime":        summary.by_vol_regime,
                "by_market_regime":     summary.by_market_regime,
            },
            "fill_efficiency_series": self.compute_rolling_fill_efficiency()[-100:],
        }

        # Live vs backtest deviation if naive PnL provided
        if backtest_naive_pnl is not None and summary.n_trades > 0:
            naive_slip = 0.0  # Naive backtest has zero slippage
            deviation = self.compute_live_vs_backtest_deviation(
                backtest_slippage_bps=naive_slip,
                backtest_fill_rate=1.0,
            )
            report["live_vs_backtest_deviation"] = {
                "slippage_deviation_bps":     deviation.slippage_deviation_bps,
                "fill_rate_deviation":         deviation.fill_rate_deviation,
                "net_alpha_decay":             deviation.net_alpha_decay,
                "recommended_slippage_factor": deviation.recommended_slippage_factor,
                "recommended_fill_factor":     deviation.recommended_fill_factor,
            }

        # Optionally include raw trade records (capped at 500 for file size)
        if include_records and self._records:
            report["execution_records"] = [
                {k: v for k, v in asdict(r).items()}
                for r in self._records[-500:]
            ]

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, default=lambda x: float(x) if isinstance(x, (int, float)) else str(x))

        print(f"  [ExecutionAnalytics] Report exported -> {path}")
        return path
