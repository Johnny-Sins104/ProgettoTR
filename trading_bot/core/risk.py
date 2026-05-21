"""
core/risk.py — Institutional-Grade Dynamic Risk Management Engine
==================================================================
Replaces the static RiskManager with a stateful, adaptive DynamicRiskEngine
that continuously adjusts position sizing based on:

  1. Calibrated Kelly Criterion     (uses ProbabilityCalibrator output)
  2. Volatility Regime Scaling      (ATR-based, 4 regime tiers)
  3. Drawdown Circuit-Breaker       (3 protection tiers, auto-recovery)
  4. Dynamic Leverage Control       (inversely proportional to vol regime)
  5. Equity Curve Protection        (profit-lock + daily-loss-limit)
  6. Risk Diagnostics & Analytics   (RiskSnapshot log, dashboard, export)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHY KELLY IS DANGEROUS IN NON-STATIONARY MARKETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kelly's Criterion maximises the *long-run* geometric growth rate under three
assumptions that crypto futures systematically violate:

  (A) STATIONARITY — p and b are constant over time.
      Reality: TRENDING regime win rate ~60%, RANGING ~45%. Regime changes
      can flip p by 15 percentage points in a single session.

  (B) IID OUTCOMES — each trade is independent.
      Reality: loss clusters dominate bear markets and volatility spikes.
      Serial correlation of losses means consecutive losses are more likely
      than Kelly assumes, driving a geometric sequence of destruction.

  (C) EXACT PROBABILITY — p is known precisely.
      Reality: even a calibrated model carries epistemic uncertainty.
      A +5pp error in p at 2:1 R:R moves Kelly from 37% to 62% of capital.

  Consequence: Full Kelly produces ruin probability 3-5× higher than
  Half-Kelly in non-stationary regimes (Tharp 2013, Vince 1992).
  The correct approach is FRACTIONAL KELLY + VOLATILITY SCALING.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHY VOLATILITY ADAPTATION MATTERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ATR measures the market's "noise floor". When ATR expands 2x beyond its
median (e.g. BTC flash crashes, macro announcements), stop-loss distances
widen automatically — but the FRACTION of capital risked remains unchanged
in a naive system, implicitly doubling real leverage.

Volatility targeting (Hurst et al. 2012) keeps portfolio volatility constant
by scaling exposure inversely with realised ATR:

    position_size ∝ 1 / ATR_ratio

This produces smaller positions exactly when uncertainty is highest —
the opposite of "averaging into a falling market", which is ruin-inducing.

In practice, a 4-tier ATR regime (LOW / NORMAL / HIGH / EXTREME) provides
a robust, interpretable framework without continuous recalibration noise.
"""

from __future__ import annotations

import csv
import json
import os
import math
import warnings
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Deque, List, Optional, Tuple, Dict, Any

from config import Config


# ════════════════════════════════════════════════════════════════════════════
# §1 — ENUMERATIONS & DATA STRUCTURES
# ════════════════════════════════════════════════════════════════════════════

class VolatilityRegime:
    """
    Four-tier ATR-based volatility classification.

    Thresholds are expressed as multiples of the rolling ATR median.
    Each tier maps to a risk multiplier and a maximum leverage cap.
    """
    LOW_VOL  = "LOW_VOL"    # ATR < 0.75x median  — unusually quiet
    NORMAL   = "NORMAL"     # 0.75x <= ATR <= 1.4x median — baseline
    HIGH_VOL = "HIGH_VOL"   # 1.4x < ATR <= 2.0x median  — elevated
    EXTREME  = "EXTREME"    # ATR > 2.0x median            — crisis / spike

    # Risk fraction multipliers per regime
    RISK_MULTIPLIERS = {
        LOW_VOL:  1.10,   # Slight upsize in quiet markets (more edge clarity)
        NORMAL:   1.00,   # Baseline
        HIGH_VOL: 0.60,   # 40% reduction — stop distances wider, edge less reliable
        EXTREME:  0.30,   # 70% reduction — near-minimal sizing during crises
    }

    # Maximum leverage caps per regime
    MAX_LEVERAGE_CAPS = {
        LOW_VOL:  10.0,
        NORMAL:    8.0,
        HIGH_VOL:  5.0,
        EXTREME:   3.0,
    }


class DrawdownTier:
    """
    Three-tier drawdown protection circuit-breaker.

    Tiers are based on drawdown from the rolling PEAK equity.
    The multiplier scales the final risk_pct output before Kelly.
    Recovery: tier relaxes ONLY when equity recovers above the
    tier's lower threshold (hysteresis prevents oscillation).
    """
    NORMAL    = "NORMAL"    # DD < 8%
    CAUTION   = "CAUTION"   # 8% <= DD < 15%  — reduce exposure
    REDUCED   = "REDUCED"   # 15% <= DD < 22% — significant reduction
    PROTECTED = "PROTECTED" # DD >= 22%        — near-capital preservation

    # Risk multipliers per drawdown tier
    RISK_MULTIPLIERS = {
        NORMAL:    1.00,
        CAUTION:   0.60,   # -40%
        REDUCED:   0.35,   # -65%
        PROTECTED: 0.15,   # -85% — minimal participation only
    }

    # Drawdown thresholds (from Config, overrideable at construction)
    THRESHOLDS = {
        CAUTION:   8.0,
        REDUCED:   15.0,
        PROTECTED: 22.0,
    }


@dataclass
class RiskSnapshot:
    """
    Immutable record of risk state at one decision point.
    Appended to RiskLog after every position-sizing call.
    """
    timestamp:          str   = ""
    trade_num:          int   = 0

    # Inputs
    balance:            float = 0.0
    peak_balance:       float = 0.0
    drawdown_pct:       float = 0.0
    atr_val:            float = 0.0
    atr_ratio:          float = 1.0    # atr / rolling_median
    ai_prob:            float = 50.0
    rr_ratio:           float = 2.0
    regime:             str   = "RANGING"

    # Classification
    vol_regime:         str   = VolatilityRegime.NORMAL
    dd_tier:            str   = DrawdownTier.NORMAL

    # Multipliers applied
    vol_multiplier:     float = 1.0
    dd_multiplier:      float = 1.0
    kelly_fraction:     float = 0.5

    # Computed outputs
    raw_kelly:          float = 0.0    # unconstrained Kelly f*
    capped_kelly:       float = 0.0    # after fraction and hard cap
    base_risk_pct:      float = 0.0    # after vol + dd scaling
    final_risk_pct:     float = 0.0    # final value used for sizing
    max_leverage:       float = 8.0

    # Capital exposure
    risk_capital:       float = 0.0    # balance × final_risk_pct
    position_size:      float = 0.0    # in base asset units
    notional_value:     float = 0.0    # position_size × entry_price
    effective_leverage: float = 0.0    # notional / balance

    # Protection flags
    daily_loss_blocked: bool  = False
    profit_lock_active: bool  = False


@dataclass
class RiskDiagnostics:
    """Aggregated statistics computed from the risk log."""
    n_snapshots:         int   = 0
    avg_risk_pct:        float = 0.0
    max_risk_pct:        float = 0.0
    min_risk_pct:        float = 0.0
    avg_leverage:        float = 0.0
    max_leverage_used:   float = 0.0
    pct_in_high_vol:     float = 0.0   # % of trades during HIGH_VOL or EXTREME
    pct_in_caution_dd:   float = 0.0   # % of trades in CAUTION+ drawdown tier
    avg_dd_multiplier:   float = 0.0
    avg_vol_multiplier:  float = 0.0
    circuit_breaker_hits: int  = 0     # times DD >= REDUCED tier
    total_risk_capital:  float = 0.0


# ════════════════════════════════════════════════════════════════════════════
# §2 — CORE ENGINE
# ════════════════════════════════════════════════════════════════════════════

class DynamicRiskEngine:
    """
    Stateful, adaptive position-sizing engine.

    Public API (drop-in compatible with the old RiskManager):
    ----------------------------------------------------------
    engine = DynamicRiskEngine(initial_balance=1000.0)

    # Called once per trade signal:
    size, snapshot = engine.size_position(
        balance, entry_price, sl_price,
        side, regime, ai_prob, rr_ratio, atr_val
    )

    # Called after each trade closes:
    engine.update_equity(new_balance)

    # Legacy shim (backward-compatible with backtest_lab.py):
    targets = engine.calculate_targets(side, entry_price, atr)
    risk_pct = engine.calculate_kelly_risk_pct(ai_prob, rr, default_risk)
    """

    # Hard limits — never exceeded regardless of model output
    _HARD_MAX_RISK_PCT  = 0.20    # 20% of balance max per trade
    _HARD_MIN_RISK_PCT  = 0.005   # 0.5% of balance floor
    _HARD_MAX_LEVERAGE  = 15.0    # absolute leverage ceiling
    _HARD_MIN_LEVERAGE  = 1.0

    def __init__(
        self,
        initial_balance:      float = 1000.0,
        atr_mult:             float = None,
        vol_lookback:         int   = 50,     # ATR samples for median calculation
        dd_caution_pct:       float = 8.0,
        dd_reduced_pct:       float = 15.0,
        dd_protected_pct:     float = 22.0,
        daily_loss_limit_pct: float = 5.0,   # block trades if day PnL < -5%
        profit_lock_pct:      float = 30.0,  # lock floor risk once +30% above start
        max_leverage:         float = None,
    ):
        """
        Parameters
        ----------
        initial_balance      : starting equity (used for profit-lock reference)
        atr_mult             : stop-loss ATR multiplier (falls back to Config)
        vol_lookback         : number of ATR observations for rolling median
        dd_caution_pct       : drawdown % that triggers CAUTION tier
        dd_reduced_pct       : drawdown % that triggers REDUCED tier
        dd_protected_pct     : drawdown % that triggers PROTECTED tier
        daily_loss_limit_pct : daily PnL loss % that blocks new entries
        profit_lock_pct      : % above initial that activates profit floor
        max_leverage         : hard leverage cap (overrides Config if supplied)
        """
        self.atr_mult            = atr_mult if atr_mult is not None else Config.ATR_MULT
        self.vol_lookback        = vol_lookback
        self.initial_balance     = initial_balance
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.profit_lock_pct     = profit_lock_pct
        # A zero/negative max_leverage can arrive from legacy DYNAMIC profile callers.
        # Treat it as "use the configured default" rather than silently forcing zero-size trades.
        if max_leverage is None or float(max_leverage) <= 0:
            self._max_leverage_cfg = getattr(Config, "MAX_LEVERAGE", 10.0)
        else:
            self._max_leverage_cfg = float(max_leverage)

        # Drawdown tier thresholds
        DrawdownTier.THRESHOLDS[DrawdownTier.CAUTION]   = dd_caution_pct
        DrawdownTier.THRESHOLDS[DrawdownTier.REDUCED]   = dd_reduced_pct
        DrawdownTier.THRESHOLDS[DrawdownTier.PROTECTED] = dd_protected_pct

        # ── Live state ────────────────────────────────────────────────────
        self._peak_balance       = initial_balance
        self._current_balance    = initial_balance
        self._daily_start_balance = initial_balance   # reset each trading day
        self._current_dd_tier    = DrawdownTier.NORMAL
        self._trade_num          = 0

        # Rolling ATR history for volatility regime classification
        self._atr_history: Deque[float] = deque(maxlen=vol_lookback)

        # Append-only risk log for diagnostics
        self._risk_log: List[RiskSnapshot] = []

    # ── Equity tracking ───────────────────────────────────────────────────────

    def update_equity(self, new_balance: float) -> None:
        """
        Must be called after every trade close.
        Updates peak equity, drawdown tier, and daily PnL tracking.
        """
        self._current_balance = max(0.0, new_balance)
        if self._current_balance > self._peak_balance:
            self._peak_balance = self._current_balance
        # Drawdown tier is lazily recomputed at next size_position() call

    def reset_daily_balance(self, balance: float = None) -> None:
        """
        Call at the start of each trading day to reset the daily loss limit.
        """
        self._daily_start_balance = balance if balance is not None else self._current_balance

    # ── Volatility regime ─────────────────────────────────────────────────────

    def _push_atr(self, atr_val: float) -> None:
        """Record an ATR observation into the rolling window."""
        if atr_val > 0:
            self._atr_history.append(atr_val)

    def _classify_vol_regime(self, atr_val: float) -> Tuple[str, float]:
        """
        Classify current volatility regime by comparing atr_val to
        the rolling median of the ATR history.

        Returns (regime_label, atr_ratio)
        where atr_ratio = atr_val / rolling_median.
        """
        if len(self._atr_history) < 5:
            # Not enough history — assume NORMAL
            return VolatilityRegime.NORMAL, 1.0

        # Rolling median (robust to outliers vs mean)
        sorted_atrs = sorted(self._atr_history)
        n = len(sorted_atrs)
        median = sorted_atrs[n // 2] if n % 2 else (sorted_atrs[n//2-1] + sorted_atrs[n//2]) / 2
        if median <= 0:
            return VolatilityRegime.NORMAL, 1.0

        ratio = atr_val / median

        if ratio < 0.75:
            regime = VolatilityRegime.LOW_VOL
        elif ratio <= 1.40:
            regime = VolatilityRegime.NORMAL
        elif ratio <= 2.00:
            regime = VolatilityRegime.HIGH_VOL
        else:
            regime = VolatilityRegime.EXTREME

        return regime, round(ratio, 4)

    # ── Drawdown tier ─────────────────────────────────────────────────────────

    def _compute_drawdown_pct(self) -> float:
        """Current drawdown from peak as a percentage."""
        if self._peak_balance <= 0:
            return 0.0
        return (self._peak_balance - self._current_balance) / self._peak_balance * 100

    def _classify_dd_tier(self, dd_pct: float) -> str:
        """
        Classify drawdown tier with HYSTERESIS:
        Tier upgrades (lower protection) require 2pp recovery margin above
        the entry threshold to prevent oscillation at tier boundaries.
        """
        thresholds = DrawdownTier.THRESHOLDS
        # Determine raw tier
        if dd_pct >= thresholds[DrawdownTier.PROTECTED]:
            raw = DrawdownTier.PROTECTED
        elif dd_pct >= thresholds[DrawdownTier.REDUCED]:
            raw = DrawdownTier.REDUCED
        elif dd_pct >= thresholds[DrawdownTier.CAUTION]:
            raw = DrawdownTier.CAUTION
        else:
            raw = DrawdownTier.NORMAL

        # Hysteresis: only relax tier if recovering clearly past threshold
        tier_order = [DrawdownTier.NORMAL, DrawdownTier.CAUTION,
                      DrawdownTier.REDUCED, DrawdownTier.PROTECTED]
        current_idx = tier_order.index(self._current_dd_tier)
        new_idx     = tier_order.index(raw)

        if new_idx < current_idx:
            # Recovery path — apply 2pp hysteresis buffer
            entry_threshold = {
                DrawdownTier.CAUTION:   thresholds[DrawdownTier.CAUTION],
                DrawdownTier.REDUCED:   thresholds[DrawdownTier.REDUCED],
                DrawdownTier.PROTECTED: thresholds[DrawdownTier.PROTECTED],
            }.get(self._current_dd_tier, 0.0)
            if dd_pct > entry_threshold - 2.0:
                raw = self._current_dd_tier   # Stay in current tier — not recovered enough

        self._current_dd_tier = raw
        return raw

    # ── Kelly calculation ─────────────────────────────────────────────────────

    @staticmethod
    def _kelly_f(p: float, b: float) -> float:
        """
        Full Kelly fraction: f* = (p·b − q) / b
        Clipped to [0, 1] — never borrow beyond 100%.
        """
        q = 1.0 - p
        f = (p * b - q) / b
        return max(0.0, min(f, 1.0))

    def _compute_kelly(
        self,
        ai_prob:    float,   # calibrated probability in % [0, 100]
        rr_ratio:   float,
        regime:     str,
        dd_tier:    str,
    ) -> Tuple[float, float, float]:
        """
        Compute the final risk fraction using calibrated fractional Kelly.

        Steps:
          1. p_cal = ai_prob / 100
          2. f* = Kelly(p_cal, rr_ratio)           raw unconstrained Kelly
          3. fraction = regime-specific Kelly fraction (TRENDING vs RANGING)
          4. capped = min(f* × fraction, hard_max)  hard safety cap
          5. Return (raw_kelly, capped_kelly, kelly_fraction_used)
        """
        if ai_prob == 50.0 or not Config.USE_KELLY_SIZING:
            return 0.0, 0.0, Config.KELLY_FRACTION

        p = max(0.01, min(0.99, ai_prob / 100.0))
        b = max(0.01, rr_ratio)

        raw_f = self._kelly_f(p, b)

        # Regime-specific Kelly fraction
        if regime == "TRENDING":
            kf = getattr(Config, "KELLY_FRACTION_TRENDING", Config.KELLY_FRACTION)
        else:
            kf = getattr(Config, "KELLY_FRACTION_RANGING",
                         Config.KELLY_FRACTION * 0.7)  # More conservative in ranging

        # Drawdown-aware Kelly fraction reduction
        dd_kf_scale = {
            DrawdownTier.NORMAL:    1.0,
            DrawdownTier.CAUTION:   0.8,
            DrawdownTier.REDUCED:   0.5,
            DrawdownTier.PROTECTED: 0.2,
        }.get(dd_tier, 1.0)

        effective_kf = kf * dd_kf_scale
        capped = min(raw_f * effective_kf, self._HARD_MAX_RISK_PCT)

        return raw_f, capped, effective_kf

    # ── Daily loss limit & profit lock ────────────────────────────────────────

    def _check_daily_loss_limit(self) -> bool:
        """
        Returns True if the daily loss limit has been breached.
        When True, new position entries should be blocked.
        """
        if self._daily_start_balance <= 0:
            return False
        daily_pnl_pct = (
            (self._current_balance - self._daily_start_balance)
            / self._daily_start_balance * 100
        )
        return daily_pnl_pct < -self.daily_loss_limit_pct

    def _check_profit_lock(self) -> bool:
        """
        Returns True if the profit-lock condition is active.
        Profit-lock floors the minimum risk at 50% of the current risk,
        protecting accrued gains from a single catastrophic sequence.
        """
        if self.initial_balance <= 0:
            return False
        gain_pct = (self._current_balance - self.initial_balance) / self.initial_balance * 100
        return gain_pct >= self.profit_lock_pct

    # ── MAIN PUBLIC METHOD ────────────────────────────────────────────────────

    def size_position(
        self,
        balance:       float,
        entry_price:   float,
        sl_price:      float,
        side:          str,
        regime:        str   = "RANGING",
        ai_prob:       float = 50.0,
        rr_ratio:      float = 2.0,
        atr_val:       float = 0.0,
        base_risk_pct: float = None,   # override; None = use Kelly
        commission:    float = None,
    ) -> Tuple[float, RiskSnapshot]:
        """
        Compute the optimal position size for a new trade.

        Pipeline
        --------
          atr_val
            → vol_regime (LOW_VOL / NORMAL / HIGH_VOL / EXTREME)
            → vol_multiplier

          (peak_balance - balance) / peak_balance
            → dd_tier (NORMAL / CAUTION / REDUCED / PROTECTED)
            → dd_multiplier

          ai_prob, rr_ratio
            → raw_kelly, capped_kelly       [calibrated fractional Kelly]

          base = capped_kelly if ai_prob!=50 else default_risk_pct
          adjusted = base × vol_multiplier × dd_multiplier
          final = clip(adjusted, min_risk, max_risk)

          size = (balance × final) / (risk_per_unit + 2×entry×commission)
          size = min(size, (balance × max_leverage) / entry_price)

        Parameters
        ----------
        balance       : current account equity
        entry_price   : trade entry price
        sl_price      : stop-loss price
        side          : "BUY" or "SELL"
        regime        : "TRENDING" or "RANGING"
        ai_prob       : calibrated AI win probability [0, 100]
        rr_ratio      : reward-to-risk ratio
        atr_val       : current ATR (bar range)
        base_risk_pct : explicit override (skips Kelly if set)
        commission    : commission rate per side (defaults to Config)

        Returns
        -------
        (position_size, RiskSnapshot)
        """
        self._trade_num += 1
        self._current_balance = balance
        commission = commission if commission is not None else Config.COMMISSION_RATE

        # ── 0. Update equity state ────────────────────────────────────────────
        if balance > self._peak_balance:
            self._peak_balance = balance
        self._push_atr(atr_val)

        dd_pct        = self._compute_drawdown_pct()
        dd_tier       = self._classify_dd_tier(dd_pct)
        vol_regime, atr_ratio = self._classify_vol_regime(atr_val)

        vol_mult      = VolatilityRegime.RISK_MULTIPLIERS[vol_regime]
        dd_mult       = DrawdownTier.RISK_MULTIPLIERS[dd_tier]
        max_lev_vol   = VolatilityRegime.MAX_LEVERAGE_CAPS[vol_regime]
        max_lev       = min(max_lev_vol, self._max_leverage_cfg, self._HARD_MAX_LEVERAGE)

        # ── 1. Protection checks ──────────────────────────────────────────────
        daily_blocked   = self._check_daily_loss_limit()
        profit_lock_on  = self._check_profit_lock()

        if daily_blocked:
            # Soft block: return zero size but still record snapshot
            snap = RiskSnapshot(
                timestamp=datetime.now().isoformat(timespec="seconds"),
                trade_num=self._trade_num, balance=balance,
                peak_balance=self._peak_balance, drawdown_pct=dd_pct,
                atr_val=atr_val, atr_ratio=atr_ratio, ai_prob=ai_prob,
                rr_ratio=rr_ratio, regime=regime,
                vol_regime=vol_regime, dd_tier=dd_tier,
                vol_multiplier=vol_mult, dd_multiplier=dd_mult,
                final_risk_pct=0.0, max_leverage=max_lev,
                daily_loss_blocked=True, profit_lock_active=profit_lock_on,
            )
            self._risk_log.append(snap)
            return 0.0, snap

        # ── 2. Risk fraction calculation ──────────────────────────────────────
        # Use explicit base_risk_pct if provided (e.g. backtest fixed profiles)
        if base_risk_pct is not None:
            raw_kelly  = 0.0
            capped_kelly = 0.0
            kf_used    = 0.0
            final_base = float(base_risk_pct)
        else:
            raw_kelly, capped_kelly, kf_used = self._compute_kelly(
                ai_prob, rr_ratio, regime, dd_tier
            )
            if capped_kelly > 0:
                final_base = capped_kelly
            else:
                # Kelly returned 0 (no edge or disabled) — use default profile risk
                profile_defaults = {"LOW": 0.03, "MEDIUM": 0.07, "HIGH": 0.15, "DYNAMIC": 0.05}
                final_base = profile_defaults.get(
                    getattr(Config, "RISK_CLASS", "MEDIUM"), 0.05
                )

        # ── 3. Apply regime multipliers ───────────────────────────────────────
        adjusted = final_base * vol_mult * dd_mult

        # Profit-lock: floor risk at 50% of current adjusted (protect gains)
        if profit_lock_on:
            adjusted = max(adjusted, final_base * 0.5)

        # Hard clip
        final_risk = max(
            self._HARD_MIN_RISK_PCT,
            min(adjusted, self._HARD_MAX_RISK_PCT)
        )

        # ── 4. Position sizing ────────────────────────────────────────────────
        risk_capital = balance * final_risk
        risk_per_unit = abs(entry_price - sl_price)

        if risk_per_unit <= 0:
            # Degenerate case: no SL distance — return minimum size
            size = 0.0
        else:
            if Config.USE_COMMISSION_AWARE_SIZING:
                denom = risk_per_unit + 2.0 * entry_price * commission
            else:
                denom = risk_per_unit
            size = risk_capital / denom

        # Leverage cap
        max_size = (balance * max_lev) / entry_price if entry_price > 0 else 0.0
        size = min(size, max_size)
        size = max(0.0, size)

        notional  = size * entry_price
        eff_lev   = notional / balance if balance > 0 else 0.0

        # ── 5. Build snapshot ─────────────────────────────────────────────────
        snap = RiskSnapshot(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            trade_num=self._trade_num,
            balance=round(balance, 4),
            peak_balance=round(self._peak_balance, 4),
            drawdown_pct=round(dd_pct, 3),
            atr_val=round(atr_val, 6),
            atr_ratio=round(atr_ratio, 4),
            ai_prob=round(ai_prob, 2),
            rr_ratio=round(rr_ratio, 2),
            regime=regime,
            vol_regime=vol_regime,
            dd_tier=dd_tier,
            vol_multiplier=round(vol_mult, 3),
            dd_multiplier=round(dd_mult, 3),
            kelly_fraction=round(kf_used, 4),
            raw_kelly=round(raw_kelly, 4),
            capped_kelly=round(capped_kelly, 4),
            base_risk_pct=round(final_base, 4),
            final_risk_pct=round(final_risk, 4),
            max_leverage=round(max_lev, 2),
            risk_capital=round(risk_capital, 4),
            position_size=round(size, 8),
            notional_value=round(notional, 4),
            effective_leverage=round(eff_lev, 3),
            daily_loss_blocked=daily_blocked,
            profit_lock_active=profit_lock_on,
        )
        self._risk_log.append(snap)
        return size, snap

    # ── Legacy shim — backward-compatible with backtest_lab.py ───────────────

    def calculate_targets(
        self,
        side:        str,
        entry_price: float,
        atr:         float,
        rr_ratio:    float = 2.0,
    ) -> dict:
        """
        Compute SL / TP price levels from entry + ATR.
        Preserved for backward compatibility with existing call sites.
        """
        if side == "BUY":
            sl  = entry_price - atr * self.atr_mult
            tp1 = entry_price + (entry_price - sl) * Config.TP1_RR
            tp2 = entry_price + (entry_price - sl) * rr_ratio
        elif side == "SELL":
            sl  = entry_price + atr * self.atr_mult
            tp1 = entry_price - (sl - entry_price) * Config.TP1_RR
            tp2 = entry_price - (sl - entry_price) * rr_ratio
        else:
            raise ValueError(f"side must be 'BUY' or 'SELL', got: {side!r}")

        return {"entry": entry_price, "sl": sl, "tp1": tp1, "tp2": tp2, "tp": tp2}

    def calculate_kelly_risk_pct(
        self,
        ai_probability: float,
        rr_ratio:       float,
        default_risk:   float,
    ) -> float:
        """
        Legacy shim used by backtest_lab.py and engine.py.

        Returns a risk fraction [0.005, 0.20] using the full
        DynamicRiskEngine pipeline (vol + DD scaling applied against
        the current engine state).

        NOTE: For full position sizing, prefer size_position() which
        also computes the actual contract size and builds a RiskSnapshot.
        """
        dd_pct   = self._compute_drawdown_pct()
        dd_tier  = self._current_dd_tier
        regime   = "RANGING"   # Conservative default for the shim path

        raw_k, capped_k, kf = self._compute_kelly(ai_probability, rr_ratio, regime, dd_tier)

        if not Config.USE_KELLY_SIZING or ai_probability == 50.0:
            base = default_risk
        elif ai_probability < 55.0:
            base = 0.005   # Below uncertainty threshold — minimum symbolic size
        elif capped_k > 0:
            base = capped_k
        else:
            base = default_risk

        # Volatility and drawdown adjustment
        # Use the last recorded ATR ratio for vol regime if history exists
        if self._atr_history:
            sorted_atrs = sorted(self._atr_history)
            n = len(sorted_atrs)
            median = sorted_atrs[n//2] if n % 2 else (sorted_atrs[n//2-1]+sorted_atrs[n//2])/2
            last_atr = self._atr_history[-1]
            ratio = last_atr / max(median, 1e-9)
            if ratio < 0.75:
                vol_regime = VolatilityRegime.LOW_VOL
            elif ratio <= 1.40:
                vol_regime = VolatilityRegime.NORMAL
            elif ratio <= 2.00:
                vol_regime = VolatilityRegime.HIGH_VOL
            else:
                vol_regime = VolatilityRegime.EXTREME
        else:
            vol_regime = VolatilityRegime.NORMAL

        vol_mult = VolatilityRegime.RISK_MULTIPLIERS[vol_regime]
        dd_mult  = DrawdownTier.RISK_MULTIPLIERS[dd_tier]

        adjusted = base * vol_mult * dd_mult
        return float(max(self._HARD_MIN_RISK_PCT, min(adjusted, self._HARD_MAX_RISK_PCT)))


    def record_trade_event(
        self,
        trade: Dict[str, Any],
        balance_before: float,
        balance_after: float,
    ) -> None:
        """
        Record a closed-trade event against the latest sizing snapshot.

        The risk engine's primary quantitative diagnostics are generated at
        position-sizing time, because that is where risk_pct, leverage, notional,
        volatility multiplier and drawdown multiplier are known.  This method
        closes the lifecycle by updating equity and attaching realized PnL metadata
        to the latest snapshot when available.  It prevents the common failure mode
        where the backtest changes balance but the risk layer remains unaware.
        """
        self.update_equity(balance_after)
        if not self._risk_log:
            warnings.warn(
                "RiskTradeEvent received but no sizing snapshot exists. "
                "The backtest may be mutating balance without risk sizing.",
                RuntimeWarning,
            )
            return

        # Store realized trade lifecycle data in a side-channel attribute so we do
        # not break CSV/JSON schema compatibility of RiskSnapshot.
        if not hasattr(self, "_trade_events"):
            self._trade_events = []
        pnl = trade.get("realized_pnl", trade.get("pnl", None))
        if pnl is None:
            pnl = float(balance_after) - float(balance_before)
        pnl = float(pnl or 0.0)

        # If the trade object carries a zero PnL but the balance actually moved,
        # trust the balance delta.  This prevents report/display divergence when
        # legacy code mutates equity through a different PnL field name.
        balance_delta = float(balance_after) - float(balance_before)
        if abs(pnl) < 1e-12 and abs(balance_delta) > 1e-12:
            pnl = balance_delta

        snapshot = self._risk_log[-1]
        event = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "side": trade.get("side"),
            "result": trade.get("result"),
            "entry": trade.get("entry"),
            "exit": trade.get("exit", trade.get("tp" if trade.get("result") == "WIN" else "sl")),
            "pnl": pnl,
            "realized_pnl": pnl,
            "balance_before": float(balance_before),
            "balance_after": float(balance_after),
            "regime": trade.get("regime"),
            "ai_prob": trade.get("ai_prob"),
            "risk_trade_num": getattr(snapshot, "trade_num", None),
            "risk_pct": getattr(snapshot, "final_risk_pct", 0.0),
            "risk_capital": getattr(snapshot, "risk_capital", 0.0),
            "position_size": getattr(snapshot, "position_size", 0.0),
            "notional_value": getattr(snapshot, "notional_value", 0.0),
            "effective_leverage": getattr(snapshot, "effective_leverage", 0.0),
            "vol_regime": getattr(snapshot, "vol_regime", None),
            "dd_tier": getattr(snapshot, "dd_tier", None),
        }
        self._trade_events.append(event)

    @property
    def trade_events(self) -> List[Dict[str, Any]]:
        """Closed-trade lifecycle events recorded by the backtest."""
        return list(getattr(self, "_trade_events", []))

    def export_trade_events(self, path: str = "data/risk_event_log.json") -> str:
        """Export closed-trade lifecycle events for auditability."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.trade_events, fh, indent=2)
        print(f"  [RiskEngine] Trade events exported -> {path}  ({len(self.trade_events)} records)")
        return path

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def compute_diagnostics(self) -> RiskDiagnostics:
        """Aggregate the risk log into summary statistics."""
        d = RiskDiagnostics()
        log = [
            s for s in self._risk_log
            if not s.daily_loss_blocked
            and float(getattr(s, "position_size", 0.0) or 0.0) > 0.0
            and float(getattr(s, "risk_capital", 0.0) or 0.0) > 0.0
        ]
        d.n_snapshots = len(log)
        if not log:
            return d

        risks     = [s.final_risk_pct for s in log]
        leverages = [s.effective_leverage for s in log]
        vol_mults = [s.vol_multiplier for s in log]
        dd_mults  = [s.dd_multiplier  for s in log]

        d.avg_risk_pct      = sum(risks) / len(risks)
        d.max_risk_pct      = max(risks)
        d.min_risk_pct      = min(risks)
        d.avg_leverage      = sum(leverages) / len(leverages)
        d.max_leverage_used = max(leverages)
        d.avg_vol_multiplier = sum(vol_mults) / len(vol_mults)
        d.avg_dd_multiplier  = sum(dd_mults)  / len(dd_mults)
        d.total_risk_capital = sum(s.risk_capital for s in log)

        high_vol_count = sum(
            1 for s in log
            if s.vol_regime in (VolatilityRegime.HIGH_VOL, VolatilityRegime.EXTREME)
        )
        d.pct_in_high_vol = high_vol_count / d.n_snapshots * 100

        caution_count = sum(
            1 for s in log
            if s.dd_tier in (DrawdownTier.CAUTION, DrawdownTier.REDUCED, DrawdownTier.PROTECTED)
        )
        d.pct_in_caution_dd = caution_count / d.n_snapshots * 100

        d.circuit_breaker_hits = sum(
            1 for s in log
            if s.dd_tier in (DrawdownTier.REDUCED, DrawdownTier.PROTECTED)
        )

        return d

    def print_risk_dashboard(self, width: int = 88) -> None:
        """Print a formatted risk analytics dashboard to stdout."""
        d = self.compute_diagnostics()
        sep = "=" * width

        print(f"\n{sep}")
        print(f"  DYNAMIC RISK ENGINE DASHBOARD")
        print(sep)
        closed_events = len(self.trade_events)
        sizing_events = len(self._risk_log)
        blocked_sizing = sum(1 for s in self._risk_log if s.daily_loss_blocked or s.position_size <= 0)
        print(f"  Trades analysed     : {d.n_snapshots}")
        print(f"  Closed trade events : {closed_events}")
        print(f"  Sizing snapshots    : {sizing_events}  ({blocked_sizing} blocked/no-size)")
        if closed_events != d.n_snapshots:
            print(f"  [AUDIT WARNING] Closed events ({closed_events}) != risk-bearing sizing events ({d.n_snapshots}).")
        print(f"  Avg Risk / Trade    : {d.avg_risk_pct*100:.3f}%")
        print(f"  Max Risk / Trade    : {d.max_risk_pct*100:.3f}%")
        print(f"  Min Risk / Trade    : {d.min_risk_pct*100:.3f}%")
        print(f"  Avg Effective Lev.  : {d.avg_leverage:.2f}x")
        print(f"  Max Effective Lev.  : {d.max_leverage_used:.2f}x")
        print(f"  Total Risk Capital  : {d.total_risk_capital:.2f}")
        print()
        print(f"  Vol Regime Scaling  : avg multiplier = {d.avg_vol_multiplier:.3f}")
        print(f"  Trades in HIGH_VOL+ : {d.pct_in_high_vol:.1f}%")
        print(f"  DD Tier Scaling     : avg multiplier = {d.avg_dd_multiplier:.3f}")
        print(f"  Trades in CAUTION+  : {d.pct_in_caution_dd:.1f}%")
        print(f"  Circuit-breaker hits: {d.circuit_breaker_hits}")

        # Current state
        print()
        print(f"  Current State:")
        print(f"    Balance           : {self._current_balance:.4f}")
        print(f"    Peak Balance      : {self._peak_balance:.4f}")
        dd_now = self._compute_drawdown_pct()
        print(f"    Current Drawdown  : {dd_now:.2f}%")
        print(f"    DD Tier           : {self._current_dd_tier}")
        if self._atr_history:
            vol_r, ratio = self._classify_vol_regime(list(self._atr_history)[-1])
            print(f"    Vol Regime        : {vol_r}  (ATR ratio {ratio:.2f}x)")
        print(f"    Profit Lock       : {'ACTIVE' if self._check_profit_lock() else 'OFF'}")
        print(f"    Daily Loss Block  : {'ACTIVE' if self._check_daily_loss_limit() else 'OFF'}")
        print(sep + "\n")

    def export_risk_log(
        self,
        path:   str,
        fmt:    str = "csv",   # "csv" | "json"
    ) -> str:
        """
        Export the full risk log to disk.

        Parameters
        ----------
        path : output file path
        fmt  : "csv" or "json"

        Returns the written path.
        """
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        if fmt == "json":
            data = [asdict(s) for s in self._risk_log]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        else:
            if not self._risk_log:
                return path
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=asdict(self._risk_log[0]).keys())
                writer.writeheader()
                for s in self._risk_log:
                    writer.writerow(asdict(s))

        print(f"  [RiskEngine] Log exported -> {path}  ({len(self._risk_log)} records)")
        return path

    @property
    def risk_log(self) -> List[RiskSnapshot]:
        """Read-only access to the risk log."""
        return list(self._risk_log)

    @property
    def last_snapshot(self) -> Optional[RiskSnapshot]:
        """Most recent risk snapshot."""
        return self._risk_log[-1] if self._risk_log else None


# ════════════════════════════════════════════════════════════════════════════
# §3 — BACKWARD-COMPATIBLE ALIAS
# ════════════════════════════════════════════════════════════════════════════

class RiskManager(DynamicRiskEngine):
    """
    Drop-in alias for backward compatibility.

    All existing code importing `from core.risk import RiskManager` continues
    to work without modification.  The alias inherits the full DynamicRiskEngine
    and exposes the same public interface as the old class:

        calculate_targets(side, entry_price, atr, rr_ratio)   [unchanged]
        calculate_kelly_risk_pct(ai_prob, rr_ratio, default)  [enhanced]

    The only behavioural difference: calculate_kelly_risk_pct() now applies
    volatility regime scaling and drawdown circuit-breaker on top of Kelly.
    """
    pass
