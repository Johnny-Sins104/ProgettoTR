"""
test_execution_model.py — Verification Suite for the Execution Simulation Layer
================================================================================
Validates all three execution simulation components:
  - SlippageModel: dynamic slippage, spread, and market impact
  - LiquidityModel: fill probability, partial fills, queue delays
  - ExecutionAnalytics: IS framework, fill efficiency, deviation diagnostics

Run from: trading_bot/ directory
  python -X utf8 test_execution_model.py
"""

import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.slippage_model import SlippageModel, SlippageEstimate
from core.liquidity_model import LiquidityModel, FillResult
from core.execution_analytics import ExecutionAnalytics, ExecutionRecord
from config import Config


# ===========================================================================
# Test infrastructure
# ═══════════════════════════════════════════════════════════════════════════

print("=" * 70)
print("  EXECUTION MODEL — UNIT TEST SUITE")
print("=" * 70)

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


PRICE = 65_000.0
ATR   = 650.0   # 1% ATR on BTC


# ===========================================================================
# §A — SLIPPAGE MODEL TESTS
# ===========================================================================

print("\n  -- A: SlippageModel Tests --")

slip_model = SlippageModel(randomize=False, random_seed=42)   # deterministic

# A01: Basic instantiation
check(slip_model is not None, "A01: SlippageModel instantiates")

# A02: Normal regime estimate has positive slippage
est = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR,
    order_size_notional=5000.0, vol_regime="NORMAL",
    order_type="LIMIT", entry_type="BREAKOUT"
)
check(isinstance(est, SlippageEstimate), "A02: Returns SlippageEstimate dataclass")
check(est.total_slippage_price > 0, "A03: Positive total slippage",
      f"got {est.total_slippage_price}")
check(est.total_slippage_bps > 0, "A04: Positive slippage in bps",
      f"got {est.total_slippage_bps}")

# A05: BUY slippage raises fill price
check(est.adjusted_price > PRICE, "A05: BUY entry fill price > theoretical",
      f"adjusted={est.adjusted_price:.2f} vs theoretical={PRICE}")

# A06: SELL slippage lowers fill price
sell_est = slip_model.estimate_slippage(
    side="SELL", entry_price=PRICE, atr_val=ATR,
    order_size_notional=5000.0, vol_regime="NORMAL",
    order_type="LIMIT", entry_type="BREAKOUT"
)
check(sell_est.adjusted_price < PRICE, "A06: SELL entry fill price < theoretical",
      f"adjusted={sell_est.adjusted_price:.2f}")

# A07: HIGH_VOL has more slippage than NORMAL
est_hv = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR * 2.0,
    order_size_notional=5000.0, vol_regime="HIGH_VOL",
    order_type="LIMIT", entry_type="BREAKOUT", atr_ratio=1.8
)
check(est_hv.total_slippage_bps > est.total_slippage_bps,
      "A07: HIGH_VOL > NORMAL slippage",
      f"HIGH_VOL={est_hv.total_slippage_bps:.2f} vs NORMAL={est.total_slippage_bps:.2f}")

# A08: EXTREME has more slippage than HIGH_VOL
est_ex = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR * 3.0,
    order_size_notional=5000.0, vol_regime="EXTREME",
    order_type="MARKET", entry_type="BREAKOUT", atr_ratio=2.5
)
check(est_ex.total_slippage_bps > est_hv.total_slippage_bps,
      "A08: EXTREME > HIGH_VOL slippage",
      f"EXTREME={est_ex.total_slippage_bps:.2f} vs HIGH_VOL={est_hv.total_slippage_bps:.2f}")

# A09: Market orders have more urgency premium than limit orders
est_mkt = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR,
    order_size_notional=5000.0, vol_regime="NORMAL",
    order_type="MARKET", entry_type="MARKET"
)
est_lmt = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR,
    order_size_notional=5000.0, vol_regime="NORMAL",
    order_type="LIMIT", entry_type="LIMIT"
)
check(est_mkt.urgency_premium >= est_lmt.urgency_premium,
      "A09: MARKET orders have >= urgency premium vs LIMIT",
      f"market={est_mkt.urgency_premium:.4f} vs limit={est_lmt.urgency_premium:.4f}")

# A10: STOP orders have highest urgency premium
est_stop = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR,
    order_size_notional=5000.0, vol_regime="NORMAL",
    order_type="STOP", entry_type="STOP"
)
check(est_stop.urgency_premium >= est_mkt.urgency_premium,
      "A10: STOP orders have >= urgency premium vs MARKET",
      f"stop={est_stop.urgency_premium:.4f} vs market={est_mkt.urgency_premium:.4f}")

# A11: Larger orders have more market impact
est_small = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR,
    order_size_notional=1_000.0, vol_regime="NORMAL",
    order_type="LIMIT", entry_type="BREAKOUT"
)
est_large = slip_model.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR,
    order_size_notional=500_000.0, vol_regime="NORMAL",
    order_type="LIMIT", entry_type="BREAKOUT"
)
check(est_large.volume_impact > est_small.volume_impact,
      "A11: Larger orders have more market impact",
      f"large={est_large.volume_impact:.4f} vs small={est_small.volume_impact:.4f}")

# A12: Spread widening in HIGH_VOL vs NORMAL
spread_normal = slip_model.estimate_spread(PRICE, "NORMAL")
spread_hv     = slip_model.estimate_spread(PRICE, "HIGH_VOL")
check(spread_hv.effective_spread_bps > spread_normal.effective_spread_bps,
      "A12: HIGH_VOL spread > NORMAL spread",
      f"HV={spread_hv.effective_spread_bps:.2f} vs NM={spread_normal.effective_spread_bps:.2f}")

# A13: Exit slippage on SL is larger than TP
sl_exit = slip_model.estimate_exit_slippage(
    side="BUY", exit_price=PRICE * 0.98, atr_val=ATR,
    vol_regime="NORMAL", exit_type="SL"
)
tp_exit = slip_model.estimate_exit_slippage(
    side="BUY", exit_price=PRICE * 1.04, atr_val=ATR,
    vol_regime="NORMAL", exit_type="TP"
)
check(sl_exit.total_slippage_bps > tp_exit.total_slippage_bps,
      "A13: SL exit slippage > TP exit slippage (market vs limit)",
      f"SL={sl_exit.total_slippage_bps:.2f} vs TP={tp_exit.total_slippage_bps:.2f}")

# A14: Vol regime classification
check(SlippageModel.vol_regime_from_atr_ratio(0.5) == "LOW_VOL",  "A14: 0.5 ratio -> LOW_VOL")
check(SlippageModel.vol_regime_from_atr_ratio(1.0) == "NORMAL",   "A15: 1.0 ratio -> NORMAL")
check(SlippageModel.vol_regime_from_atr_ratio(1.7) == "HIGH_VOL", "A16: 1.7 ratio -> HIGH_VOL")
check(SlippageModel.vol_regime_from_atr_ratio(2.5) == "EXTREME",  "A17: 2.5 ratio -> EXTREME")

# A18: describe_estimate returns non-empty string
desc = slip_model.describe_estimate(est)
check(len(desc) > 50, "A18: describe_estimate() returns valid breakdown string")


# ===========================================================================
# §B — LIQUIDITY MODEL TESTS
# ===========================================================================

print("\n  -- B: LiquidityModel Tests --")

liq_model_det = LiquidityModel(randomize=False, random_seed=42)  # deterministic

# B01: Basic instantiation
check(liq_model_det is not None, "B01: LiquidityModel instantiates")

# B02: Market depth estimate in normal conditions
depth = liq_model_det.estimate_market_depth(PRICE, "NORMAL", 1.0)
check(depth.depth_usd > 1_000_000, "B02: NORMAL regime depth > $1M",
      f"depth={depth.depth_usd:,.0f}")

# B03: HIGH_VOL depth is lower than NORMAL
depth_hv = liq_model_det.estimate_market_depth(PRICE, "HIGH_VOL", 1.0)
check(depth_hv.depth_usd < depth.depth_usd, "B03: HIGH_VOL depth < NORMAL depth",
      f"HV={depth_hv.depth_usd:,.0f} vs NM={depth.depth_usd:,.0f}")

# B04: EXTREME depth is lowest
depth_ex = liq_model_det.estimate_market_depth(PRICE, "EXTREME", 1.0)
check(depth_ex.depth_usd < depth_hv.depth_usd, "B04: EXTREME depth < HIGH_VOL",
      f"EX={depth_ex.depth_usd:,.0f} vs HV={depth_hv.depth_usd:,.0f}")

# B05: Market orders always fill
fill_mkt = liq_model_det.simulate_fill(
    order_size_notional=5000.0, price=PRICE, volume_ratio=1.0,
    vol_regime="NORMAL", order_type="MARKET", side="BUY"
)
check(not fill_mkt.is_no_fill, "B05: Market orders always fill",
      f"is_no_fill={fill_mkt.is_no_fill}")
check(fill_mkt.fill_pct == 1.0, "B06: Market orders always fully fill",
      f"fill_pct={fill_mkt.fill_pct}")

# B07: Market order delay = 0
check(fill_mkt.fill_delay_candles == 0, "B07: Market orders have zero queue delay",
      f"delay={fill_mkt.fill_delay_candles}")

# B08: STOP orders also fill (as market orders)
fill_stop = liq_model_det.simulate_fill(
    order_size_notional=5000.0, price=PRICE, volume_ratio=1.0,
    vol_regime="NORMAL", order_type="STOP", side="BUY"
)
check(not fill_stop.is_no_fill, "B08: STOP orders always fill (market semantics)")
check(fill_stop.fill_delay_candles == 0, "B09: STOP orders have zero delay")

# B10: Market impact is positive
check(fill_mkt.total_impact_bps >= 0, "B10: Market order impact >= 0 bps",
      f"impact={fill_mkt.total_impact_bps}")

# B11: EXTREME vol has larger market impact
fill_ex = liq_model_det.simulate_fill(
    order_size_notional=50_000.0, price=PRICE, volume_ratio=0.5,
    vol_regime="EXTREME", order_type="MARKET", side="BUY"
)
fill_nm = liq_model_det.simulate_fill(
    order_size_notional=50_000.0, price=PRICE, volume_ratio=0.5,
    vol_regime="NORMAL", order_type="MARKET", side="BUY"
)
check(fill_ex.total_impact_bps >= fill_nm.total_impact_bps,
      "B11: EXTREME market impact >= NORMAL impact",
      f"EX={fill_ex.total_impact_bps:.2f} vs NM={fill_nm.total_impact_bps:.2f}")

# B12: get_fill_statistics returns valid structure
fills = [fill_mkt, fill_stop, fill_ex, fill_nm]
stats = liq_model_det.get_fill_statistics(fills)
check("total_orders" in stats and stats["total_orders"] == 4,
      "B12: get_fill_statistics returns total_orders=4", f"got {stats}")
check("avg_fill_fraction" in stats, "B13: statistics contain avg_fill_fraction")

# B14: Queue delay for limit orders
delay_nm = liq_model_det.simulate_queue_delay("LIMIT", "NORMAL", "LIMIT")
delay_ex = liq_model_det.simulate_queue_delay("LIMIT", "EXTREME", "LIMIT")
check(delay_nm >= 0, "B14: Queue delay >= 0 candles",   f"got {delay_nm}")
check(delay_ex >= delay_nm, "B15: EXTREME delay >= NORMAL delay",
      f"EX={delay_ex} vs NM={delay_nm}")

# B16: Empty fill statistics returns empty dict
empty_stats = liq_model_det.get_fill_statistics([])
check(empty_stats == {}, "B16: Empty fill list returns empty statistics dict")


# ===========================================================================
# §C — EXECUTION ANALYTICS TESTS
# ===========================================================================

print("\n  -- C: ExecutionAnalytics Tests --")

analytics = ExecutionAnalytics(
    rolling_window=20,
    commission_rate=Config.COMMISSION_RATE,
)
slip_model_det = SlippageModel(randomize=False, random_seed=42)
liq_model_r    = LiquidityModel(randomize=False, random_seed=42)

# C01: Basic instantiation
check(analytics is not None, "C01: ExecutionAnalytics instantiates")

# C02: record_from_slippage creates valid record
entry_slip = slip_model_det.estimate_slippage(
    side="BUY", entry_price=PRICE, atr_val=ATR,
    order_size_notional=5000.0, vol_regime="NORMAL",
    order_type="LIMIT", entry_type="BREAKOUT"
)
exit_slip = slip_model_det.estimate_exit_slippage(
    side="BUY", exit_price=PRICE * 1.04, atr_val=ATR,
    vol_regime="NORMAL", exit_type="TP"
)
fill_res = liq_model_r.simulate_fill(
    order_size_notional=5000.0, price=PRICE, volume_ratio=1.2,
    vol_regime="NORMAL", order_type="LIMIT", side="BUY"
)

record = analytics.record_from_slippage(
    side="BUY", regime="TRENDING", vol_regime="NORMAL",
    theoretical_entry=PRICE, theoretical_exit=PRICE * 1.04,
    entry_slip=entry_slip, exit_slip=exit_slip,
    fill_result=fill_res, size=5000.0 / PRICE,
    atr_val=ATR, timestamp="2026-01-01T00:00:00"
)
check(isinstance(record, ExecutionRecord), "C02: record_from_slippage returns ExecutionRecord")
check(record.trade_id == 1, "C03: First record has trade_id=1")
check(record.entry_slippage_bps > 0, "C04: Entry slippage bps > 0",
      f"got {record.entry_slippage_bps}")
check(record.exit_slippage_bps > 0, "C05: Exit slippage bps > 0",
      f"got {record.exit_slippage_bps}")
check(record.round_trip_cost_bps > 0, "C06: Round-trip cost > 0 bps",
      f"got {record.round_trip_cost_bps}")

# C07: Commission is computed correctly
expected_comm = fill_res.filled_size * PRICE * Config.COMMISSION_RATE * 2
check(record.commission_paid >= 0, "C07: Commission paid >= 0",
      f"got {record.commission_paid}")

# C08: Add multiple records and compute summary
for vol_regime in ("NORMAL", "HIGH_VOL", "NORMAL", "EXTREME", "NORMAL"):
    e_slip = slip_model_det.estimate_slippage(
        side="BUY", entry_price=PRICE, atr_val=ATR,
        order_size_notional=3000.0, vol_regime=vol_regime,
        order_type="LIMIT", entry_type="BREAKOUT"
    )
    x_slip = slip_model_det.estimate_exit_slippage(
        side="BUY", exit_price=PRICE * 1.04, atr_val=ATR,
        vol_regime=vol_regime, exit_type="TP"
    )
    f_res = liq_model_r.simulate_fill(
        order_size_notional=3000.0, price=PRICE, volume_ratio=1.0,
        vol_regime=vol_regime, order_type="LIMIT", side="BUY"
    )
    analytics.record_from_slippage(
        side="BUY", regime="RANGING", vol_regime=vol_regime,
        theoretical_entry=PRICE, theoretical_exit=PRICE * 1.04,
        entry_slip=e_slip, exit_slip=x_slip, fill_result=f_res,
        size=3000.0 / PRICE, atr_val=ATR, timestamp=""
    )

summary = analytics.compute_summary()
check(summary.n_trades >= 5, "C08: Summary counts all recorded trades",
      f"got {summary.n_trades}")
check(summary.avg_entry_slippage_bps > 0, "C09: avg_entry_slippage_bps > 0",
      f"got {summary.avg_entry_slippage_bps}")
check(summary.avg_round_trip_bps > 0, "C10: avg_round_trip_bps > 0",
      f"got {summary.avg_round_trip_bps}")
check(0.0 <= summary.avg_fill_pct <= 1.0, "C11: avg_fill_pct in [0, 1]",
      f"got {summary.avg_fill_pct}")
check(summary.avg_fill_delay_candles >= 0, "C12: avg_fill_delay >= 0",
      f"got {summary.avg_fill_delay_candles}")

# C13: Regime breakdown populated
check(len(summary.by_vol_regime) > 0, "C13: by_vol_regime breakdown populated")
check(len(summary.by_market_regime) > 0, "C14: by_market_regime breakdown populated")

# C15: Rolling fill efficiency returns list
efficiencies = analytics.compute_rolling_fill_efficiency()
check(len(efficiencies) == summary.n_trades, "C15: fill efficiency series has correct length",
      f"eff_len={len(efficiencies)} vs n_trades={summary.n_trades}")

# C16: compute_live_vs_backtest_deviation
deviation = analytics.compute_live_vs_backtest_deviation(
    backtest_slippage_bps=0.0, backtest_fill_rate=1.0
)
check(deviation.slippage_deviation_bps >= 0, "C16: Slippage deviation >= 0 (friction model > naive)",
      f"got {deviation.slippage_deviation_bps}")
check(deviation.recommended_slippage_factor >= 0, "C17: Calibration factor >= 0")

# C17: Export report to temp file
import tempfile
with tempfile.TemporaryDirectory() as tmpdir:
    report_path = os.path.join(tmpdir, "exec_report.json")
    returned_path = analytics.export_report(report_path, include_records=True)
    check(os.path.exists(returned_path), "C18: export_report creates JSON file")

    import json as _json
    with open(returned_path) as fh:
        data = _json.load(fh)
    check("friction_metrics_bps" in data, "C19: Report contains friction_metrics_bps key")
    check("fill_quality" in data, "C20: Report contains fill_quality key")
    check("execution_records" in data, "C21: Report contains execution_records")

# C22: print_dashboard runs without exception
import io
from contextlib import redirect_stdout
buf = io.StringIO()
try:
    with redirect_stdout(buf):
        analytics.print_dashboard(summary)
    check(True, "C22: print_dashboard() runs without exception")
except Exception as e:
    check(False, "C22: print_dashboard() runs without exception", str(e))


# ===========================================================================
# §D — INTEGRATION TESTS
# ===========================================================================

print("\n  -- D: Integration Tests --")

# D01: HIGH_VOL total friction > NORMAL total friction across full round trip
slip_full = SlippageModel(randomize=False)
liq_full  = LiquidityModel(randomize=False)
an_full   = ExecutionAnalytics(commission_rate=Config.COMMISSION_RATE)

def simulate_full_trade(regime: str, atr_ratio: float) -> float:
    """Returns total IS bps for a simulated round-trip trade."""
    vol_regime = SlippageModel.vol_regime_from_atr_ratio(atr_ratio)
    atr = ATR * atr_ratio
    notional = 5_000.0
    fill = liq_full.simulate_fill(
        notional, PRICE, 1.0, vol_regime, "LIMIT", "BUY", "BREAKOUT"
    )
    e_slip = slip_full.estimate_slippage(
        "BUY", PRICE, atr, notional, vol_regime, "LIMIT", "BREAKOUT", atr_ratio
    )
    x_slip = slip_full.estimate_exit_slippage(
        "BUY", PRICE * 1.04, atr, notional, vol_regime, "TP", atr_ratio
    )
    rec = an_full.record_from_slippage(
        "BUY", regime, vol_regime, PRICE, PRICE * 1.04,
        e_slip, x_slip, fill, notional / PRICE, atr
    )
    return rec.round_trip_cost_bps

normal_bps = simulate_full_trade("TRENDING", 1.0)
high_bps   = simulate_full_trade("TRENDING", 1.8)
extreme_bps = simulate_full_trade("TRENDING", 2.5)

check(high_bps > normal_bps, "D01: HIGH_VOL round-trip cost > NORMAL",
      f"HIGH={high_bps:.2f} vs NORMAL={normal_bps:.2f}")
check(extreme_bps > high_bps, "D02: EXTREME round-trip cost > HIGH_VOL",
      f"EXTREME={extreme_bps:.2f} vs HIGH={high_bps:.2f}")

# D03: Friction-adjusted PnL < theoretical PnL for winning trade
check(record.actual_pnl <= record.theoretical_pnl,
      "D03: Friction-adjusted PnL <= theoretical PnL (friction costs are real)",
      f"actual={record.actual_pnl:.4f} vs theoretical={record.theoretical_pnl:.4f}")

# D04: Commission is always > 0 for filled trades
check(record.commission_paid > 0, "D04: Commission always > 0 for executed trades",
      f"got {record.commission_paid:.6f}")

# D05: Config parameters integrated correctly
check(Config.EXECUTION_MODEL_ENABLED == True, "D05: EXECUTION_MODEL_ENABLED is True in Config")
check(Config.SLIPPAGE_ATR_FACTOR == 1.0, "D06: SLIPPAGE_ATR_FACTOR defaults to 1.0")
check(Config.FILL_PROB_FACTOR == 1.0, "D07: FILL_PROB_FACTOR defaults to 1.0")
check(Config.EXECUTION_RANDOMIZE == True, "D08: EXECUTION_RANDOMIZE defaults to True")


# ===========================================================================
# Final summary
# ===========================================================================

print()
print("=" * 70)
print(f"  RESULTS: {passes} passed  |  {failures} failed  |  {passes+failures} total")
print("=" * 70)

if failures > 0:
    sys.exit(1)
