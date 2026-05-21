"""
core/liquidity_model.py — Institutional-Grade Order Liquidity & Fill Model
===========================================================================
Models realistic order book dynamics for crypto futures execution:

  1. FILL PROBABILITY     — function of order size vs estimated market depth
  2. PARTIAL FILLS        — large orders may only partially fill in thin markets
  3. QUEUE POSITION DELAY — limit orders wait N candles for a fill
  4. PERMANENT IMPACT     — adverse selection from large orders (Kyle lambda)
  5. TEMPORARY IMPACT     — price reversion after market-moving orders

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HOW EXECUTION FRICTION DESTROYS EDGE: LIQUIDITY EDITION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A backtest assumes that any order, of any size, is instantly filled at
the precise signal price. Three mechanisms destroy this assumption:

  (A) FILL PROBABILITY: For limit orders placed at the candle close,
      the probability of filling depends on whether price returns to
      the limit level. High-volatility breakouts often never return,
      meaning limit orders are skipped (causing missed entries).

  (B) PARTIAL FILLS: In thin markets, an order for 0.1 BTC at a
      specific price may only fill 0.06 BTC — distorting the risk-to-
      reward calculation. The remaining 0.04 BTC fills later (worse
      price) or not at all.

  (C) ADVERSE SELECTION: When you submit a large limit buy order,
      market makers detect it and widen their ask. Your fill occurs at
      a slightly worse price than the stated limit — this is the
      "information content" of your order (Kyle 1985, Glosten-Milgrom).

  Consequence: Systems backtested at "100% fill rate" often achieve
  only 70-85% fill efficiency in live trading. The 15-30% of missed
  or partial fills represent the best setups (strong moves never
  return to the entry limit) — adversely biasing the live PnL.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════════════════
# §1 — DATA STRUCTURES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class FillResult:
    """
    Complete fill simulation result for a single order.
    Models partial fills, queue delays, and market impact.
    """
    # Order request parameters
    requested_size:       float = 0.0    # size in base units (e.g. BTC)
    requested_price:      float = 0.0    # limit/stop price requested
    order_type:           str   = "LIMIT"
    side:                 str   = "BUY"

    # Fill outcome
    filled_size:          float = 0.0    # actual filled quantity
    fill_price:           float = 0.0    # average weighted fill price
    fill_pct:             float = 0.0    # fraction filled [0.0, 1.0]
    is_complete_fill:     bool  = True   # True if fully filled
    is_partial_fill:      bool  = False  # True if partially filled
    is_no_fill:           bool  = False  # True if zero fill

    # Queue dynamics
    fill_delay_candles:   int   = 0      # candles waited before fill
    queue_position:       int   = 0      # estimated position in order queue

    # Market impact
    permanent_impact_bps: float = 0.0   # permanent adverse price move
    temporary_impact_bps: float = 0.0   # temporary price spike at fill
    total_impact_bps:     float = 0.0

    # Regime context
    vol_regime:           str   = "NORMAL"
    volume_ratio:         float = 1.0   # current vol / avg vol (liquidity proxy)
    estimated_depth_usd:  float = 0.0   # estimated book depth at order price


@dataclass
class MarketDepthEstimate:
    """Estimated order book depth at a given price level."""
    price:              float = 0.0
    depth_usd:          float = 0.0    # liquidity available within 0.5% of price
    bid_depth_usd:      float = 0.0
    ask_depth_usd:      float = 0.0
    depth_bps_impact:   float = 0.0   # bps move per $100k notional


# ════════════════════════════════════════════════════════════════════════════
# §2 — MARKET DEPTH PARAMETERS
# ════════════════════════════════════════════════════════════════════════════

# Estimated available depth in USD within 0.5% of mid-price for BTC futures
# Source: empirical estimates from Binance USDT-M order book analysis
_TYPICAL_DEPTH_USD: Dict[str, float] = {
    "LOW_VOL":   8_000_000.0,   # ~$8M typical depth in quiet markets
    "NORMAL":    5_000_000.0,   # ~$5M in normal conditions
    "HIGH_VOL":  1_500_000.0,   # Depth thins dramatically during volatility
    "EXTREME":     300_000.0,   # Near-zero depth during flash crashes
}

# Fraction of depth that can be filled without significant market impact
_FILL_THRESHOLD_FRACTION = 0.05   # Orders above 5% of depth start seeing impact

# Base fill probabilities for limit orders in different regimes
# (Probability that a limit order placed at signal price gets filled this candle)
_LIMIT_FILL_PROB: Dict[str, float] = {
    "LOW_VOL":  0.92,   # Very likely to fill in quiet markets
    "NORMAL":   0.85,   # Good fill probability
    "HIGH_VOL": 0.68,   # Breakouts often don't retrace to limit levels
    "EXTREME":  0.45,   # Chaotic — many orders never fill
}

# Probability of partial fill (conditional on getting any fill at all)
_PARTIAL_FILL_PROB: Dict[str, float] = {
    "LOW_VOL":  0.05,   # Rare in liquid markets
    "NORMAL":   0.12,
    "HIGH_VOL": 0.28,   # Fairly common in volatile environments
    "EXTREME":  0.50,   # Very common during crisis periods
}

# When a partial fill occurs, fill fraction is drawn from this range
_PARTIAL_FILL_RANGE: Dict[str, Tuple[float, float]] = {
    "LOW_VOL":  (0.80, 0.95),
    "NORMAL":   (0.60, 0.90),
    "HIGH_VOL": (0.40, 0.75),
    "EXTREME":  (0.25, 0.60),
}

# Queue delay distribution: candles to wait before fill (for limit orders)
_QUEUE_DELAY_CANDLES: Dict[str, Tuple[int, int]] = {
    "LOW_VOL":  (0, 1),
    "NORMAL":   (0, 2),
    "HIGH_VOL": (0, 3),
    "EXTREME":  (1, 5),
}


# ════════════════════════════════════════════════════════════════════════════
# §3 — LIQUIDITY MODEL
# ════════════════════════════════════════════════════════════════════════════

class LiquidityModel:
    """
    Simulates order fill dynamics for crypto futures orders.

    Models fill probability, partial fills, queue delays, and market impact
    to create realistic execution simulation for backtesting.

    Usage
    -----
    model = LiquidityModel(randomize=True)
    result = model.simulate_fill(
        order_size_notional=5000.0,
        price=65000.0,
        volume_ratio=1.2,
        vol_regime="NORMAL",
        order_type="LIMIT",
        side="BUY"
    )
    if result.is_no_fill:
        print("Order not filled — missed entry")
    elif result.is_partial_fill:
        print(f"Partial fill: {result.fill_pct:.1%} at {result.fill_price}")
    """

    def __init__(
        self,
        fill_prob_factor:    float = 1.0,   # Scale fill probabilities
        partial_prob_factor: float = 1.0,   # Scale partial fill probabilities
        depth_factor:        float = 1.0,   # Scale estimated market depth
        randomize:           bool  = True,
        random_seed:         Optional[int] = None,
    ):
        self.fill_prob_factor    = fill_prob_factor
        self.partial_prob_factor = partial_prob_factor
        self.depth_factor        = depth_factor
        self.randomize           = randomize

        if random_seed is not None:
            random.seed(random_seed)

    # ── Public API ────────────────────────────────────────────────────────────

    def simulate_fill(
        self,
        order_size_notional: float,
        price:               float,
        volume_ratio:        float = 1.0,
        vol_regime:          str   = "NORMAL",
        order_type:          str   = "LIMIT",
        side:                str   = "BUY",
        entry_type:          str   = "BREAKOUT",
    ) -> FillResult:
        """
        Simulate a complete fill for a proposed order.

        Parameters
        ----------
        order_size_notional  : order value in base currency (e.g. €5,000)
        price                : order price (limit or trigger price)
        volume_ratio         : current candle volume / 20-period avg volume
        vol_regime           : "LOW_VOL" | "NORMAL" | "HIGH_VOL" | "EXTREME"
        order_type           : "LIMIT" | "MARKET" | "STOP"
        side                 : "BUY" | "SELL"
        entry_type           : "BREAKOUT" | "LIMIT" | "MARKET"

        Returns
        -------
        FillResult with fill quantity, price, and delay information.
        """
        requested_size = order_size_notional / price if price > 0 else 0.0

        result = FillResult(
            requested_size=requested_size,
            requested_price=price,
            order_type=order_type,
            side=side,
            vol_regime=vol_regime,
            volume_ratio=volume_ratio,
        )

        # Estimate market depth at this price level
        depth = self.estimate_market_depth(price, vol_regime, volume_ratio)
        result.estimated_depth_usd = depth.depth_usd

        # Market orders always fill immediately (but at worst price)
        if order_type == "MARKET":
            return self._fill_market_order(result, order_size_notional, depth, vol_regime)

        # Stop orders: trigger as market orders
        if order_type == "STOP":
            result.order_type = "MARKET"  # Model as market at trigger
            return self._fill_market_order(result, order_size_notional, depth, vol_regime,
                                           is_stop=True)

        # Limit orders: check fill probability first
        return self._fill_limit_order(result, order_size_notional, depth, vol_regime,
                                      entry_type=entry_type)

    def estimate_market_depth(
        self,
        price:        float,
        vol_regime:   str   = "NORMAL",
        volume_ratio: float = 1.0,
    ) -> MarketDepthEstimate:
        """
        Estimate available order book depth at a given price.

        Depth scales inversely with volatility and proportionally with volume.
        """
        base_depth = _TYPICAL_DEPTH_USD.get(vol_regime, 5_000_000.0) * self.depth_factor

        # Volume ratio adjusts depth: high volume = deeper book
        vol_adj = max(0.3, min(2.0, math.sqrt(volume_ratio)))
        total_depth = base_depth * vol_adj

        # Add stochastic variation (±30%)
        if self.randomize:
            noise = random.uniform(0.7, 1.3)
            total_depth *= noise

        # Impact: bps move per $100k notional
        depth_bps_impact = 10_000.0 * (100_000.0 / total_depth) if total_depth > 0 else 100.0

        return MarketDepthEstimate(
            price=price,
            depth_usd=total_depth,
            bid_depth_usd=total_depth * 0.45,
            ask_depth_usd=total_depth * 0.55,
            depth_bps_impact=depth_bps_impact,
        )

    def simulate_queue_delay(
        self,
        order_type: str   = "LIMIT",
        vol_regime: str   = "NORMAL",
        entry_type: str   = "BREAKOUT",
    ) -> int:
        """
        Estimate queue delay in candles before a limit order fills.

        Returns an integer number of candles to delay the fill.
        Market orders have zero delay.
        """
        if order_type in ("MARKET", "STOP"):
            return 0

        min_delay, max_delay = _QUEUE_DELAY_CANDLES.get(vol_regime, (0, 2))

        # Breakout limit orders placed just above/below key levels
        # often have shorter queues (fewer competing limit orders)
        if entry_type == "BREAKOUT":
            max_delay = max(0, max_delay - 1)

        if not self.randomize:
            return min_delay

        return random.randint(min_delay, max_delay)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _fill_market_order(
        self,
        result:             FillResult,
        order_notional:     float,
        depth:              MarketDepthEstimate,
        vol_regime:         str,
        is_stop:            bool = False,
    ) -> FillResult:
        """Market orders always fill — model size-dependent impact."""
        result.fill_delay_candles = 0

        # Market orders always fill (no fill probability check)
        # But they may experience severe price impact in thin markets
        depth_ratio = order_notional / max(depth.depth_usd, 1.0)

        # Permanent impact: permanent adverse price shift (Kyle lambda)
        # Lambda = price impact per unit of order flow
        perm_impact = min(50.0, depth.depth_bps_impact * math.sqrt(depth_ratio) * 10)

        # Temporary impact: spike that partially reverts
        temp_impact = perm_impact * 0.6

        if is_stop:
            # Stop orders in fast markets have extra slippage
            extra_sl_slippage = 3.0 if vol_regime in ("HIGH_VOL", "EXTREME") else 1.0
            perm_impact += extra_sl_slippage

        result.permanent_impact_bps = perm_impact
        result.temporary_impact_bps = temp_impact
        result.total_impact_bps     = perm_impact + temp_impact

        # Full fill at market — size not constrained for market orders
        result.filled_size      = result.requested_size
        result.fill_price       = result.requested_price
        result.fill_pct         = 1.0
        result.is_complete_fill = True
        result.is_partial_fill  = False
        result.is_no_fill       = False

        return result

    def _fill_limit_order(
        self,
        result:             FillResult,
        order_notional:     float,
        depth:              MarketDepthEstimate,
        vol_regime:         str,
        entry_type:         str = "BREAKOUT",
    ) -> FillResult:
        """Limit orders: check fill probability → partial fill check → delay."""

        # ── Step 1: Will the order fill at all? ───────────────────────────
        base_fill_prob = _LIMIT_FILL_PROB.get(vol_regime, 0.85) * self.fill_prob_factor

        # Breakout entries: price often doesn't retrace after breakout
        if entry_type == "BREAKOUT":
            base_fill_prob *= 0.88  # 12% extra miss for breakout limits

        # Order size relative to depth: large orders less likely to fill
        depth_ratio = order_notional / max(depth.depth_usd, 1.0)
        if depth_ratio > _FILL_THRESHOLD_FRACTION:
            size_penalty = min(0.3, (depth_ratio - _FILL_THRESHOLD_FRACTION) * 2.0)
            base_fill_prob -= size_penalty

        base_fill_prob = max(0.1, min(1.0, base_fill_prob))

        if self.randomize and random.random() > base_fill_prob:
            # Order did not fill
            result.filled_size      = 0.0
            result.fill_pct         = 0.0
            result.is_complete_fill = False
            result.is_partial_fill  = False
            result.is_no_fill       = True
            result.fill_delay_candles = self.simulate_queue_delay(
                "LIMIT", vol_regime, entry_type
            )
            return result

        # ── Step 2: Full or partial fill? ────────────────────────────────
        partial_prob = _PARTIAL_FILL_PROB.get(vol_regime, 0.12) * self.partial_prob_factor

        if self.randomize and random.random() < partial_prob:
            # Partial fill
            lo, hi = _PARTIAL_FILL_RANGE.get(vol_regime, (0.60, 0.90))
            fill_fraction = random.uniform(lo, hi)

            result.filled_size      = result.requested_size * fill_fraction
            result.fill_pct         = fill_fraction
            result.is_complete_fill = False
            result.is_partial_fill  = True
            result.is_no_fill       = False
        else:
            # Complete fill
            result.filled_size      = result.requested_size
            result.fill_pct         = 1.0
            result.is_complete_fill = True
            result.is_partial_fill  = False
            result.is_no_fill       = False

        # ── Step 3: Queue delay ───────────────────────────────────────────
        result.fill_delay_candles = self.simulate_queue_delay(
            "LIMIT", vol_regime, entry_type
        )

        # ── Step 4: Market impact for limit orders ────────────────────────
        depth_ratio = (order_notional * result.fill_pct) / max(depth.depth_usd, 1.0)
        perm_impact = min(10.0, depth.depth_bps_impact * math.sqrt(depth_ratio) * 5)
        result.permanent_impact_bps = perm_impact
        result.temporary_impact_bps = 0.0   # Limits have no temporary impact
        result.total_impact_bps     = perm_impact

        result.fill_price = result.requested_price

        return result

    def get_fill_statistics(self, fill_results: List[FillResult]) -> Dict[str, float]:
        """
        Aggregate fill statistics across a list of FillResult objects.
        Useful for execution analytics and diagnostics.
        """
        if not fill_results:
            return {}

        n = len(fill_results)
        complete = sum(1 for f in fill_results if f.is_complete_fill)
        partial  = sum(1 for f in fill_results if f.is_partial_fill)
        no_fill  = sum(1 for f in fill_results if f.is_no_fill)
        avg_pct  = sum(f.fill_pct for f in fill_results) / n
        avg_delay = sum(f.fill_delay_candles for f in fill_results) / n
        avg_impact = sum(f.total_impact_bps for f in fill_results) / n

        return {
            "total_orders":     n,
            "complete_fills":   complete,
            "partial_fills":    partial,
            "no_fills":         no_fill,
            "complete_fill_pct": complete / n * 100,
            "partial_fill_pct":  partial  / n * 100,
            "no_fill_pct":       no_fill  / n * 100,
            "avg_fill_fraction": avg_pct,
            "avg_delay_candles": avg_delay,
            "avg_impact_bps":    avg_impact,
        }
