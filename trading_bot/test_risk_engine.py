"""
test_risk_engine.py — Standalone verification suite for DynamicRiskEngine.
Run from: trading_bot/ directory
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.risk import (
    DynamicRiskEngine,
    RiskManager,
    VolatilityRegime,
    DrawdownTier,
    RiskSnapshot,
)
from config import Config

ENTRY = 60_000.0   # BTC entry price
ATR   = 600.0      # typical 1% ATR on 15m BTC

def make_engine(balance=1000.0, **kwargs) -> DynamicRiskEngine:
    return DynamicRiskEngine(
        initial_balance=balance,
        vol_lookback=20,
        dd_caution_pct=8.0,
        dd_reduced_pct=15.0,
        dd_protected_pct=22.0,
        daily_loss_limit_pct=5.0,
        profit_lock_pct=30.0,
        max_leverage=10.0,
        **kwargs,
    )

print("=" * 65)
print("  DYNAMIC RISK ENGINE — UNIT TEST SUITE")
print("=" * 65)
passes = 0
failures = 0

def check(condition: bool, label: str, detail: str = "") -> None:
    global passes, failures
    if condition:
        passes += 1
        print(f"  [PASS] {label}")
    else:
        failures += 1
        print(f"  [FAIL] {label}  |  {detail}")

# ── T01: Basic import and instantiation ──────────────────────────────────────
engine = make_engine()
check(engine is not None, "T01: DynamicRiskEngine instantiates")
check(isinstance(RiskManager(), DynamicRiskEngine), "T02: RiskManager is DynamicRiskEngine alias")

# ── T03: Volatility regime classification ─────────────────────────────────────
atrs_normal = [600.0] * 20
for a in atrs_normal:
    engine._push_atr(a)
regime_n, ratio_n = engine._classify_vol_regime(600.0)
check(regime_n == VolatilityRegime.NORMAL, "T03: Normal ATR -> NORMAL regime",
      f"got {regime_n}")

regime_h, ratio_h = engine._classify_vol_regime(900.0)   # 1.5x median
check(regime_h == VolatilityRegime.HIGH_VOL, "T04: 1.5x ATR -> HIGH_VOL regime",
      f"got {regime_h}, ratio={ratio_h}")

regime_e, ratio_e = engine._classify_vol_regime(1300.0)  # 2.17x median
check(regime_e == VolatilityRegime.EXTREME, "T05: 2.17x ATR -> EXTREME regime",
      f"got {regime_e}, ratio={ratio_e}")

regime_l, ratio_l = engine._classify_vol_regime(400.0)   # 0.67x median
check(regime_l == VolatilityRegime.LOW_VOL, "T06: 0.67x ATR -> LOW_VOL regime",
      f"got {regime_l}, ratio={ratio_l}")

# ── T07: Drawdown tier classification ────────────────────────────────────────
eng2 = make_engine(balance=1000.0)
eng2._peak_balance = 1000.0

# Simulate 8.5% drawdown
eng2._current_balance = 915.0
dd = eng2._compute_drawdown_pct()
tier = eng2._classify_dd_tier(dd)
check(tier == DrawdownTier.CAUTION, "T07: 8.5% DD -> CAUTION tier",
      f"dd={dd:.1f}%, tier={tier}")

# Simulate 16% drawdown
eng2._current_balance = 840.0
dd = eng2._compute_drawdown_pct()
tier = eng2._classify_dd_tier(dd)
check(tier == DrawdownTier.REDUCED, "T08: 16% DD -> REDUCED tier",
      f"dd={dd:.1f}%, tier={tier}")

# Simulate 25% drawdown
eng2._current_balance = 750.0
dd = eng2._compute_drawdown_pct()
tier = eng2._classify_dd_tier(dd)
check(tier == DrawdownTier.PROTECTED, "T09: 25% DD -> PROTECTED tier",
      f"dd={dd:.1f}%, tier={tier}")

# ── T10: Hysteresis — tier should not relax immediately ───────────────────────
# Still 22.5% DD: should stay PROTECTED
eng2._current_balance = 775.0
dd = eng2._compute_drawdown_pct()
tier = eng2._classify_dd_tier(dd)
check(tier == DrawdownTier.PROTECTED, "T10: Hysteresis — 22.5% DD stays PROTECTED",
      f"dd={dd:.1f}%, tier={tier}")

# ── T11: Kelly calculation ────────────────────────────────────────────────────
eng3 = make_engine()
raw_k, capped_k, kf = eng3._compute_kelly(75.0, 2.0, "TRENDING", DrawdownTier.NORMAL)
# Kelly formula: f* = (0.75*2 - 0.25)/2 = (1.5-0.25)/2 = 0.625
check(abs(raw_k - 0.625) < 0.001, "T11: Kelly f* = 0.625 for p=0.75, RR=2.0",
      f"got raw_k={raw_k:.4f}")
check(capped_k <= 0.20, "T12: Capped Kelly <= hard max 20%",
      f"got capped_k={capped_k:.4f}")
check(capped_k <= raw_k * kf + 1e-9, "T13: Capped Kelly <= raw * fraction (hard cap may apply)",
      f"capped={capped_k:.4f}, raw*kf={raw_k*kf:.4f}")

# ── T14: Vol multiplier reduces risk in HIGH_VOL ─────────────────────────────
eng4 = make_engine(balance=1000.0)
for a in [600.0] * 20:
    eng4._push_atr(a)

sl_price = ENTRY - ATR * Config.ATR_MULT  # 60_000 - 1200 = 58_800

# NORMAL vol run
size_n, snap_n = eng4.size_position(
    balance=1000.0, entry_price=ENTRY, sl_price=sl_price,
    side="BUY", regime="TRENDING", ai_prob=75.0, rr_ratio=2.0,
    atr_val=600.0,
)
# HIGH_VOL run (spike ATR to 900)
size_h, snap_h = eng4.size_position(
    balance=1000.0, entry_price=ENTRY, sl_price=sl_price,
    side="BUY", regime="TRENDING", ai_prob=75.0, rr_ratio=2.0,
    atr_val=900.0,
)
check(size_h < size_n, "T14: HIGH_VOL reduces position size vs NORMAL",
      f"size_normal={size_n:.6f}, size_high_vol={size_h:.6f}")
check(snap_h.vol_multiplier < snap_n.vol_multiplier, "T15: HIGH_VOL multiplier < NORMAL multiplier",
      f"vol_mult_norm={snap_n.vol_multiplier}, vol_mult_high={snap_h.vol_multiplier}")

# ── T16: Drawdown circuit-breaker reduces size ────────────────────────────────
eng5 = make_engine(balance=1000.0)
for a in [600.0] * 20:
    eng5._push_atr(a)

eng5._peak_balance = 1000.0

# Baseline (no DD)
size_base, snap_base = eng5.size_position(
    balance=1000.0, entry_price=ENTRY, sl_price=sl_price,
    side="BUY", regime="TRENDING", ai_prob=75.0, rr_ratio=2.0, atr_val=600.0,
)
# Simulate 16% drawdown
eng5.update_equity(840.0)
size_dd, snap_dd = eng5.size_position(
    balance=840.0, entry_price=ENTRY, sl_price=sl_price,
    side="BUY", regime="TRENDING", ai_prob=75.0, rr_ratio=2.0, atr_val=600.0,
)
check(size_dd < size_base, "T16: DD=16% (REDUCED) cuts position size",
      f"base={size_base:.6f}, dd_reduced={size_dd:.6f}")
check(snap_dd.dd_tier == DrawdownTier.REDUCED, "T17: Snapshot records REDUCED tier",
      f"got {snap_dd.dd_tier}")
pct_reduction = (size_base - size_dd) / size_base * 100
check(pct_reduction > 50, "T18: Size reduction > 50% at REDUCED tier",
      f"actual reduction = {pct_reduction:.1f}%")

# ── T19: calculate_targets backward compatibility ─────────────────────────────
eng6 = make_engine()
targets = eng6.calculate_targets("BUY", 60000.0, 600.0, rr_ratio=2.0)
check("sl" in targets and "tp" in targets, "T19: calculate_targets returns sl+tp")
check(targets["sl"] < 60000.0, "T20: BUY sl < entry",
      f"sl={targets['sl']:.2f}")
check(targets["tp"] > 60000.0, "T21: BUY tp > entry",
      f"tp={targets['tp']:.2f}")
check("tp1" in targets and "tp2" in targets, "T22: calculate_targets returns tp1+tp2 (scale-out)")

# ── T23: calculate_kelly_risk_pct shim ───────────────────────────────────────
eng7 = make_engine(balance=1000.0)
for a in [600.0] * 20:
    eng7._push_atr(a)
kelly_risk = eng7.calculate_kelly_risk_pct(75.0, 2.0, 0.07)
check(0.005 <= kelly_risk <= 0.20, "T23: Kelly shim returns valid range",
      f"got {kelly_risk:.4f}")

# ── T24: Daily loss limit blocks sizing ───────────────────────────────────────
eng8 = make_engine(balance=1000.0)
eng8._daily_start_balance = 1000.0
eng8._current_balance = 940.0  # -6% daily PnL (below -5% limit)
for a in [600.0] * 20:
    eng8._push_atr(a)
size_blocked, snap_blocked = eng8.size_position(
    balance=940.0, entry_price=ENTRY, sl_price=sl_price,
    side="BUY", regime="TRENDING", ai_prob=75.0, rr_ratio=2.0, atr_val=600.0,
)
check(size_blocked == 0.0, "T24: Daily loss limit blocks new position (size=0)",
      f"got size={size_blocked}")
check(snap_blocked.daily_loss_blocked, "T25: Snapshot records daily_loss_blocked=True",
      f"got {snap_blocked.daily_loss_blocked}")

# ── T26: Profit lock activates at +30% ────────────────────────────────────────
eng9 = make_engine(balance=1000.0)  # profit_lock_pct=30.0 set by make_engine default
eng9._current_balance = 1350.0   # +35% above initial
check(eng9._check_profit_lock(), "T26: Profit lock fires at +35% gain")
eng9._current_balance = 1290.0   # +29% — below threshold
check(not eng9._check_profit_lock(), "T27: Profit lock OFF at +29% gain")

# ── T28: RiskSnapshot fields are populated ────────────────────────────────────
eng10 = make_engine(balance=1000.0)
for a in [600.0] * 20:
    eng10._push_atr(a)
_, snap = eng10.size_position(
    balance=1000.0, entry_price=ENTRY, sl_price=sl_price,
    side="BUY", regime="TRENDING", ai_prob=72.0, rr_ratio=2.0, atr_val=600.0,
)
check(snap.timestamp != "", "T28: Snapshot timestamp is set")
check(snap.trade_num == 1, "T29: First trade is trade_num=1")
check(snap.vol_regime in (VolatilityRegime.NORMAL, VolatilityRegime.LOW_VOL,
                          VolatilityRegime.HIGH_VOL, VolatilityRegime.EXTREME),
      "T30: Snapshot vol_regime is valid enum value", f"got {snap.vol_regime}")
check(snap.dd_tier in (DrawdownTier.NORMAL, DrawdownTier.CAUTION,
                       DrawdownTier.REDUCED, DrawdownTier.PROTECTED),
      "T31: Snapshot dd_tier is valid enum value", f"got {snap.dd_tier}")
check(snap.notional_value > 0, "T32: Snapshot notional_value > 0",
      f"got {snap.notional_value}")
check(0 < snap.effective_leverage <= 10.0, "T33: Effective leverage within bounds",
      f"got {snap.effective_leverage:.3f}x")

# ── T34: Diagnostics aggregation ─────────────────────────────────────────────
diag = eng10.compute_diagnostics()
check(diag.n_snapshots == 1, "T34: Diagnostics counts 1 snapshot", f"got {diag.n_snapshots}")
check(diag.avg_risk_pct > 0, "T35: Diagnostics avg_risk_pct > 0", f"got {diag.avg_risk_pct}")

# ── T36: Export to CSV ────────────────────────────────────────────────────────
import tempfile
with tempfile.TemporaryDirectory() as tmpdir:
    csv_path = os.path.join(tmpdir, "test_risk_log.csv")
    eng10.export_risk_log(csv_path, fmt="csv")
    check(os.path.exists(csv_path), "T36: CSV export creates file")
    with open(csv_path) as fh:
        content = fh.read()
    check("trade_num" in content, "T37: CSV export contains trade_num column")

# ── T38: Hard limits respected ────────────────────────────────────────────────
eng11 = make_engine(balance=1000.0)
for a in [600.0] * 20:
    eng11._push_atr(a)
# p=0.99, RR=5 => full Kelly = (0.99*5 - 0.01)/5 = 0.988
# Should be hard-capped at 20%
size_max, snap_max = eng11.size_position(
    balance=1000.0, entry_price=ENTRY, sl_price=sl_price,
    side="BUY", regime="TRENDING", ai_prob=99.0, rr_ratio=5.0, atr_val=600.0,
)
check(snap_max.final_risk_pct <= 0.20, "T38: Hard cap at 20% — extreme Kelly capped",
      f"got final_risk_pct={snap_max.final_risk_pct:.4f}")

# ── T39: SELL side targets ────────────────────────────────────────────────────
eng12 = make_engine()
targets_sell = eng12.calculate_targets("SELL", 60000.0, 600.0, rr_ratio=2.0)
check(targets_sell["sl"] > 60000.0, "T39: SELL sl > entry", f"sl={targets_sell['sl']:.2f}")
check(targets_sell["tp"] < 60000.0, "T40: SELL tp < entry", f"tp={targets_sell['tp']:.2f}")

# ── Final summary ─────────────────────────────────────────────────────────────
print()
print("=" * 65)
print(f"  RESULTS: {passes} passed  |  {failures} failed  |  {passes+failures} total")
print("=" * 65)

if failures > 0:
    sys.exit(1)
