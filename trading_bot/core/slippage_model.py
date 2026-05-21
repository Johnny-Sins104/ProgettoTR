"""
core/slippage_model.py — Institutional-Grade Execution Slippage Model
======================================================================
Models realistic execution price adjustments for crypto futures trading,
accounting for:

  1. BASE SLIPPAGE        — proportional to ATR (market noise floor)
  2. BID-ASK SPREAD       — half-spread applied on entry and exit
  3. SPREAD WIDENING      — non-linear expansion during HIGH_VOL/EXTREME regimes
  4. VOLUME MARKET IMPACT — large orders push price adversely
  5. URGENCY PREMIUM      — market orders vs limit orders cost differential
  6. BREAKOUT PREMIUM     — breakout entries suffer extra adverse price moves

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHY NAIVE BACKTESTS FAIL LIVE: SLIPPAGE EDITION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A naive backtest assumes fills at the exact candle close price. This is
wrong for three structural reasons:

  (A) BID-ASK SPREAD: The "close" is the last traded price. Buying at
      close means paying the ask (close + half_spread). Selling means
      hitting the bid (close − half_spread). For BTC on Binance, the
      typical spread is 0.5–1 bps in normal conditions, expanding to
      5–15 bps during flash crashes or announcement events.

  (B) STOP-LOSS SLIPPAGE: SL orders on exchanges are market orders
      that execute at the best available bid/ask at the moment of
      trigger. In fast-moving markets, the trigger price and fill
      price can differ by 0.2–0.5%, doubling the effective loss.

  (C) ATR-PROPORTIONAL NOISE: In high-volatility environments, the
      bid-ask spread alone understates friction. The "noise floor" of
      the market (measured by ATR) means that any order will experience
      adverse selection proportional to the volatility regime.

  Consequence: A system with 5 bps/trade expectancy can be completely
  wiped out by 3–7 bps/trade execution friction, turning a profitable
  strategy into a capital-destroying machine.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from config import Config


# ════════════════════════════════════════════════════════════════════════════
# §1 — DATA STRUCTURES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class SlippageEstimate:
    """
    Complete breakdown of execution cost for a single order.
    All values are expressed as price-level adjustments (not percentages).
    """
    # Input context
    theoretical_price:    float = 0.0   # ideal fill price (signal price)
    side:                 str   = "BUY"
    order_type:           str   = "LIMIT"  # "LIMIT" | "MARKET" | "STOP"

    # Cost components (in price units)
    half_spread:          float = 0.0   # half bid-ask spread
    base_slippage:        float = 0.0   # ATR-proportional baseline noise
    spread_widening:      float = 0.0   # extra spread during high-vol
    volume_impact:        float = 0.0   # adverse selection from order size
    urgency_premium:      float = 0.0   # market order vs limit premium

    # Aggregate results
    total_slippage_price: float = 0.0   # total price adjustment (always adverse)
    adjusted_price:       float = 0.0   # actual simulated fill price
    total_slippage_bps:   float = 0.0   # total friction in basis points
    total_cost_pct:       float = 0.0   # total friction as % of price

    # Regime context
    vol_regime:           str   = "NORMAL"
    atr_ratio:            float = 1.0   # current ATR / rolling median ATR


@dataclass
class SpreadEstimate:
    """Bid-ask spread metrics for a given market state."""
    price:              float = 0.0
    raw_spread_bps:     float = 0.0   # typical spread in basis points
    widening_factor:    float = 1.0   # multiplier applied during high-vol
    effective_spread_bps: float = 0.0 # spread × widening_factor
    half_spread:        float = 0.0   # actual price adjustment (half the full spread)


# ════════════════════════════════════════════════════════════════════════════
# §2 — VOLATILITY REGIME PARAMETERS
# ════════════════════════════════════════════════════════════════════════════

# Base spread in basis points for BTC futures under normal market conditions
# Source: Binance USDT-M empirical data (2022–2024 average)
_BASE_SPREAD_BPS: Dict[str, float] = {
    "LOW_VOL":  0.40,   # Very quiet markets — tight spreads
    "NORMAL":   0.80,   # Baseline conditions
    "HIGH_VOL": 2.50,   # Elevated volatility — wider books
    "EXTREME":  8.00,   # Flash crashes / macro events — very thin books
}

# Spread widening multipliers applied on top of base spread
_SPREAD_WIDENING: Dict[str, float] = {
    "LOW_VOL":  1.0,
    "NORMAL":   1.0,
    "HIGH_VOL": 2.2,   # Spread expands ~2.2× its base during high-vol
    "EXTREME":  5.0,   # Extreme events can push spread 5× normal
}

# ATR fraction used as base slippage (fraction of 1 ATR unit)
# Represents execution noise within the volatility envelope
_ATR_SLIPPAGE_FRACTION: Dict[str, float] = {
    "LOW_VOL":  0.005,  # 0.5% of 1 ATR
    "NORMAL":   0.010,  # 1.0% of 1 ATR
    "HIGH_VOL": 0.025,  # 2.5% of 1 ATR — wider noise floor
    "EXTREME":  0.060,  # 6.0% of 1 ATR — chaotic execution
}

# Market impact coefficient (bps per million notional in base currency)
# Models permanent adverse price impact from order size
_MARKET_IMPACT_BPS_PER_M: float = 1.2   # 1.2 bps per $1M notional

# Urgency premium for market orders vs limit orders (in bps)
# Market orders cross the spread plus pay a time-priority premium
_URGENCY_PREMIUM_BPS: Dict[str, float] = {
    "LIMIT":  0.0,
    "MARKET": 1.5,   # 1.5 bps extra for aggressive market orders
    "STOP":   2.5,   # STOP orders become market orders at trigger — worst case
}


# ════════════════════════════════════════════════════════════════════════════
# §3 — SLIPPAGE MODEL
# ════════════════════════════════════════════════════════════════════════════

class SlippageModel:
    """
    Computes realistic execution price adjustments for crypto futures orders.

    Usage
    -----
    model = SlippageModel(atr_slippage_factor=1.0, randomize=True)
    estimate = model.estimate_slippage(
        side="BUY", entry_price=65000.0, atr_val=650.0,
        order_size_notional=5000.0, vol_regime="NORMAL",
        order_type="LIMIT", entry_type="BREAKOUT"
    )
    fill_price = estimate.adjusted_price
    """

    def __init__(
        self,
        atr_slippage_factor:  float = 1.0,    # Scales ATR-proportional base slippage
        spread_factor:        float = 1.0,    # Scales bid-ask spread estimates
        impact_factor:        float = 1.0,    # Scales market impact
        randomize:            bool  = True,   # Add stochastic noise (realistic)
        random_seed:          Optional[int] = None,
    ):
        self.atr_slippage_factor = atr_slippage_factor
        self.spread_factor       = spread_factor
        self.impact_factor       = impact_factor
        self.randomize           = randomize

        if random_seed is not None:
            random.seed(random_seed)

    # ── Public API ────────────────────────────────────────────────────────────

    def estimate_slippage(
        self,
        side:                  str,
        entry_price:           float,
        atr_val:               float,
        order_size_notional:   float = 0.0,
        vol_regime:            str   = "NORMAL",
        order_type:            str   = "LIMIT",
        entry_type:            str   = "BREAKOUT",
        atr_ratio:             float = 1.0,
    ) -> SlippageEstimate:
        """
        Compute a full slippage estimate for an entry order.

        Parameters
        ----------
        side                 : "BUY" or "SELL"
        entry_price          : theoretical signal price (candle close / breakout level)
        atr_val              : current ATR value in price units
        order_size_notional  : order value in base currency (e.g. €5,000)
        vol_regime           : "LOW_VOL" | "NORMAL" | "HIGH_VOL" | "EXTREME"
        order_type           : "LIMIT" | "MARKET" | "STOP"
        entry_type           : "BREAKOUT" | "LIMIT" | "MARKET"
        atr_ratio            : current ATR / rolling_median_ATR (for scaling)

        Returns
        -------
        SlippageEstimate with all cost components broken out.
        """
        est = SlippageEstimate(
            theoretical_price=entry_price,
            side=side,
            order_type=order_type,
            vol_regime=vol_regime,
            atr_ratio=atr_ratio,
        )

        # ── 1. Bid-Ask Spread ─────────────────────────────────────────────
        spread_est = self.estimate_spread(entry_price, vol_regime)
        est.half_spread = spread_est.half_spread

        # ── 2. ATR-Proportional Base Slippage ────────────────────────────
        atr_frac = _ATR_SLIPPAGE_FRACTION.get(vol_regime, 0.010) * self.atr_slippage_factor
        base_slip = atr_val * atr_frac

        # Add stochastic noise: slippage varies trade-to-trade
        if self.randomize:
            # Log-normal noise: most slippage near median, occasional spikes
            noise_factor = max(0.2, random.lognormvariate(mu=0.0, sigma=0.4))
            base_slip *= noise_factor

        est.base_slippage = base_slip

        # ── 3. Spread Widening (regime-specific additional spread) ────────
        # Already included in half_spread from estimate_spread above.
        # Separately track the widening component for diagnostics.
        base_spread_bps = _BASE_SPREAD_BPS.get("NORMAL", 0.80)
        widened_spread_bps = _BASE_SPREAD_BPS.get(vol_regime, 0.80)
        spread_diff_bps = max(0.0, widened_spread_bps - base_spread_bps)
        est.spread_widening = (spread_diff_bps / 10_000.0) * entry_price * 0.5

        # ── 4. Volume / Market Impact ─────────────────────────────────────
        # Impact scales with order size (larger orders move the market more)
        # Model: impact = alpha × sqrt(order_notional / 1_000_000) × atr_ratio
        # The sqrt function reflects the square-root market impact law (Almgren 2001)
        if order_size_notional > 0:
            notional_m = order_size_notional / 1_000_000.0
            impact_bps = (_MARKET_IMPACT_BPS_PER_M * math.sqrt(notional_m)
                          * self.impact_factor * max(1.0, atr_ratio))
            est.volume_impact = (impact_bps / 10_000.0) * entry_price
        else:
            est.volume_impact = 0.0

        # ── 5. Urgency Premium (order type) ──────────────────────────────
        urgency_bps = _URGENCY_PREMIUM_BPS.get(order_type, 0.0)
        # BREAKOUT entries typically use market orders — add urgency premium
        if entry_type == "BREAKOUT" and order_type == "LIMIT":
            urgency_bps += 0.8   # Breakout limits risk partial fill + delay
        est.urgency_premium = (urgency_bps / 10_000.0) * entry_price

        # ── 6. Aggregate: Total Slippage ──────────────────────────────────
        total_slip = (
            est.half_spread
            + est.base_slippage
            + est.spread_widening   # incremental beyond normal spread
            + est.volume_impact
            + est.urgency_premium
        )
        est.total_slippage_price = total_slip

        # ── 7. Direction: Slippage always goes against the trade ─────────
        if side == "BUY":
            est.adjusted_price = entry_price + total_slip
        else:  # SELL
            est.adjusted_price = entry_price - total_slip

        # ── 8. Summary metrics in bps ─────────────────────────────────────
        est.total_slippage_bps = (total_slip / entry_price) * 10_000.0
        est.total_cost_pct     = (total_slip / entry_price) * 100.0

        return est

    def estimate_exit_slippage(
        self,
        side:            str,
        exit_price:      float,
        atr_val:         float,
        order_size_notional: float = 0.0,
        vol_regime:      str   = "NORMAL",
        exit_type:       str   = "TP",   # "TP" | "SL" | "TIME"
        atr_ratio:       float = 1.0,
    ) -> SlippageEstimate:
        """
        Compute slippage for an exit order (TP or SL).

        SL exits are particularly costly because they are triggered as market
        orders in fast-moving markets, often executing at significantly worse
        prices than the stop trigger level.
        """
        # SL exits use market order semantics — worst case execution
        if exit_type == "SL":
            order_type = "STOP"
            # In fast markets, SL slippage can be much larger
            # We apply an extra multiplier to the ATR fraction
            sl_atr_boost = 1.8 if vol_regime in ("HIGH_VOL", "EXTREME") else 1.2
            atr_val = atr_val * sl_atr_boost
        elif exit_type == "TP":
            order_type = "LIMIT"
        else:
            order_type = "MARKET"

        # For exits, the direction of adverse slippage reverses:
        # If original trade was BUY, exit is SELL → slippage reduces sell price
        exit_side = "SELL" if side == "BUY" else "BUY"

        est = self.estimate_slippage(
            side=exit_side,
            entry_price=exit_price,
            atr_val=atr_val,
            order_size_notional=order_size_notional,
            vol_regime=vol_regime,
            order_type=order_type,
            entry_type="STOP" if exit_type == "SL" else "LIMIT",
            atr_ratio=atr_ratio,
        )

        # Override theoretical price back to original exit price for clarity
        est.theoretical_price = exit_price
        return est

    def estimate_spread(
        self,
        price:      float,
        vol_regime: str = "NORMAL",
    ) -> SpreadEstimate:
        """
        Estimate the current bid-ask spread for an asset.

        Returns a SpreadEstimate with the half-spread price adjustment.
        """
        base_bps  = _BASE_SPREAD_BPS.get(vol_regime, 0.80) * self.spread_factor
        widening  = _SPREAD_WIDENING.get(vol_regime, 1.0)
        eff_bps   = base_bps * widening

        half_spread = (eff_bps / 10_000.0) * price * 0.5

        return SpreadEstimate(
            price=price,
            raw_spread_bps=base_bps,
            widening_factor=widening,
            effective_spread_bps=eff_bps,
            half_spread=half_spread,
        )

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def vol_regime_from_atr_ratio(atr_ratio: float) -> str:
        """Classify volatility regime from ATR/median ratio (same tiers as DynamicRiskEngine)."""
        if atr_ratio < 0.75:
            return "LOW_VOL"
        elif atr_ratio <= 1.40:
            return "NORMAL"
        elif atr_ratio <= 2.00:
            return "HIGH_VOL"
        else:
            return "EXTREME"

    @staticmethod
    def bps_to_price(bps: float, price: float) -> float:
        """Convert basis points to absolute price adjustment."""
        return (bps / 10_000.0) * price

    @staticmethod
    def price_to_bps(price_adj: float, price: float) -> float:
        """Convert absolute price adjustment to basis points."""
        return (price_adj / price) * 10_000.0 if price > 0 else 0.0

    def describe_estimate(self, est: SlippageEstimate) -> str:
        """Return a human-readable breakdown of a slippage estimate."""
        lines = [
            f"  Slippage Estimate [{est.side} @ {est.theoretical_price:,.2f} | {est.vol_regime}]",
            f"    Half-Spread        : {est.half_spread:+.4f}  ({self.price_to_bps(est.half_spread, est.theoretical_price):.2f} bps)",
            f"    Base Slippage(ATR) : {est.base_slippage:+.4f}",
            f"    Spread Widening    : {est.spread_widening:+.4f}",
            f"    Volume Impact      : {est.volume_impact:+.4f}",
            f"    Urgency Premium    : {est.urgency_premium:+.4f}",
            f"    ─────────────────────────────────────────",
            f"    Total Slippage     : {est.total_slippage_price:+.4f}  ({est.total_slippage_bps:.2f} bps = {est.total_cost_pct:.4f}%)",
            f"    Fill Price         : {est.adjusted_price:,.4f}  (vs. theoretical {est.theoretical_price:,.4f})",
        ]
        return "\n".join(lines)
