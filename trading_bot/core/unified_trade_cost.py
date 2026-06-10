"""unified_trade_cost.py — Unified cost model for diagnostics, backtest and benchmark.

Calculates per-trade gross PnL, cost breakdown, net PnL, gross R, net R.
All 6 cost components are charged: fee_entry, fee_exit, spread, slippage, latency, partial_fill.

Scenarios
---------
optimistic   : maker entry + maker exit, low spread, no latency  (~3-5 bps RT)
realistic    : taker entry (breakout/stop) + taker exit          (~8-12 bps RT)
conservative : taker + taker + stress x1.75 multiplier           (~15-20 bps RT)
severe       : taker + taker + stress x2.75 + partial fill pen   (~30-45 bps RT)

Formula
-------
gross_pnl       = (exit - entry) * qty * direction   (direction = +1 BUY, -1 SELL)
notional        = entry * qty                        (entry notional)
exit_notional   = exit * qty
fee_entry_amt   = notional * fee_entry_bps / 10000
fee_exit_amt    = exit_notional * fee_exit_bps / 10000
spread_amt      = notional * spread_bps / 10000
slippage_amt    = notional * slippage_bps / 10000
latency_amt     = notional * latency_bps / 10000
partial_fill_amt = notional * partial_fill_bps / 10000
total_cost      = sum of all six components above
net_pnl         = gross_pnl - total_cost
initial_risk    = abs(entry - stop) * qty            (always > 0)
gross_R         = gross_pnl / initial_risk
net_R           = net_pnl / initial_risk

API parity
----------
compute_trade_outcome() and apply_cost_to_backtest_trade() produce IDENTICAL costs
for the same entry_price, exit_price, quantity and scenario. Both use the same
_compute_cost_amounts() inner function. Parity is exact (not approximate).

apply_cost_to_backtest_trade() requires entry_price, exit_price, quantity explicitly.
If the exit price is not available in the caller's context, the caller must raise an
error rather than silently estimating.

Fail-closed
-----------
All public methods validate inputs strictly using math.isfinite for every float.
Unknown side, unknown scenario, non-positive prices/quantity, stop==entry,
NaN/Inf in any numeric input, unsupported timeframe, stop on wrong side of entry
all raise ValueError immediately. No silent defaults.

Supported timeframes: 1m, 5m, 15m, 1h, 4h
(any other value raises ValueError — no silent fallback to 15m)

Risk policy for Phases 3-5
---------------------------
Fixed risk_pct = 0.005 (= 0.5% per trade).  Value 0.005, label "0.5%".
Scenarios banned from benchmark: LOW, MEDIUM, HIGH, DYNAMIC, Kelly.
Dynamic Risk: excluded. May be evaluated post-OOS as reduce-only ablation only.
"""
from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

# Allow import both inside trading_bot/ and from project root.
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

SCENARIO_NAMES = ("optimistic", "realistic", "conservative", "severe", "zero")

# Only 5m and 15m have validated cost parameters for the benchmark.
# 1m, 1h, 4h are rejected with ValueError until explicit calibrated params exist.
SUPPORTED_TIMEFRAMES = frozenset({"5m", "15m"})

# Fixed bps parameters per scenario (Binance USDT-M Futures baseline).
# maker_fee and taker_fee are per-side (one-way). RT = entry + exit.
_SCENARIO_PARAMS: Dict[str, Dict[str, Any]] = {
    "optimistic": {
        "maker_fee_bps_side": 2.0,   # 0.02%
        "taker_fee_bps_side": 4.0,   # 0.04%
        "entry_order": "LIMIT",      # maker entry
        "exit_order": "LIMIT",       # maker exit (limit TP)
        "spread_base_bps": 1.0,      # BTC-like tight spread
        "slippage_frac": 0.002,      # 0.2% of ATR in bps (very small)
        "latency_bps": 0.0,
        "partial_fill_bps": 0.0,
        "stress_mult": 1.0,
        "tf_mult_5m": 1.0,           # no uplift in optimistic
        "tf_mult_15m": 1.0,
        "fill_probability": 0.98,
    },
    "realistic": {
        "maker_fee_bps_side": 2.0,
        "taker_fee_bps_side": 4.0,
        "entry_order": "MARKET",     # taker entry (breakout/stop)
        "exit_order": "MARKET",      # taker exit (stop hit)
        "spread_base_bps": 2.0,
        "slippage_frac": 0.004,
        "latency_bps": 0.0,
        "partial_fill_bps": 0.0,
        "stress_mult": 1.0,
        "tf_mult_5m": 1.20,
        "tf_mult_15m": 1.0,
        "fill_probability": 0.96,
    },
    "conservative": {
        "maker_fee_bps_side": 2.0,
        "taker_fee_bps_side": 4.0,
        "entry_order": "MARKET",
        "exit_order": "MARKET",
        "spread_base_bps": 2.0,
        "slippage_frac": 0.008,
        "latency_bps": 1.0,
        "partial_fill_bps": 0.0,
        "stress_mult": 1.75,
        "tf_mult_5m": 1.20,
        "tf_mult_15m": 1.0,
        "fill_probability": 0.93,
    },
    "severe": {
        "maker_fee_bps_side": 2.0,
        "taker_fee_bps_side": 4.0,
        "entry_order": "MARKET",
        "exit_order": "MARKET",
        "spread_base_bps": 2.0,
        "slippage_frac": 0.014,
        "latency_bps": 2.5,
        "partial_fill_bps": 2.0,
        "stress_mult": 2.75,
        "tf_mult_5m": 1.20,
        "tf_mult_15m": 1.0,
        "fill_probability": 0.85,
    },
}

# Per-symbol spread override (round-trip bps, base)
_SYMBOL_SPREAD_BPS: Dict[str, float] = {
    "btcusdt": 1.0,
    "ethusdt": 1.2,
    "solusdt": 2.0,
    "bnbusdt": 1.8,
    "xrpusdt": 2.4,
}


def _symbol_slug(symbol: str) -> str:
    return str(symbol or "BTC/USDT").replace("/", "").replace(":", "").lower()


def _scenario_spread_bps(scenario: str, symbol: str) -> float:
    p = _SCENARIO_PARAMS[scenario]
    base_from_symbol = _SYMBOL_SPREAD_BPS.get(_symbol_slug(symbol), 2.0)
    base_from_scenario = float(p["spread_base_bps"])
    return max(base_from_symbol, base_from_scenario)


def _bps_components(
    scenario: str,
    symbol: str,
    timeframe: str,
    atr_pct: float = 0.0,
) -> Dict[str, float]:
    """Return individual cost components in bps (round-trip). All 6 components included."""
    if scenario == "zero":
        return {
            "fee_entry_bps": 0.0,
            "fee_exit_bps": 0.0,
            "spread_bps": 0.0,
            "slippage_bps": 0.0,
            "latency_bps": 0.0,
            "partial_fill_bps": 0.0,
            "total_round_trip_bps": 0.0,
            "fill_probability": 1.0,
        }
    p = _SCENARIO_PARAMS[scenario]
    tf = str(timeframe).lower()

    entry_fee = float(p["taker_fee_bps_side"]) if p["entry_order"] == "MARKET" else float(p["maker_fee_bps_side"])
    exit_fee = float(p["taker_fee_bps_side"]) if p["exit_order"] == "MARKET" else float(p["maker_fee_bps_side"])

    spread = _scenario_spread_bps(scenario, symbol)

    atr_bps = max(0.0, float(atr_pct) * 100.0)
    slippage = min(35.0, atr_bps * float(p["slippage_frac"]))

    latency = float(p["latency_bps"])
    partial = float(p["partial_fill_bps"])
    stress = float(p["stress_mult"])

    # Timeframe multiplier: only 5m and 15m have validated parameters
    if tf == "5m":
        tf_mult = float(p["tf_mult_5m"])
    else:  # tf == "15m"
        tf_mult = float(p["tf_mult_15m"])

    variable = (spread + slippage + latency + partial) * stress * tf_mult
    total = entry_fee + exit_fee + variable

    return {
        "fee_entry_bps": round(entry_fee, 6),
        "fee_exit_bps": round(exit_fee, 6),
        "spread_bps": round(spread * stress * tf_mult, 6),
        "slippage_bps": round(slippage * stress * tf_mult, 6),
        "latency_bps": round(latency * stress * tf_mult, 6),
        "partial_fill_bps": round(partial * stress * tf_mult, 6),
        "total_round_trip_bps": round(max(0.0, total), 6),
        "fill_probability": float(p["fill_probability"]),
    }


def _assert_finite(value: Any, name: str) -> float:
    """Convert to float and raise ValueError if not finite (NaN, +Inf, -Inf rejected)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{name} must be a finite number, got {value!r} (type {type(value).__name__})."
        )
    if not math.isfinite(v):
        raise ValueError(
            f"{name} must be finite, got {value!r}. NaN and Inf are not allowed."
        )
    return v


def _validate_trade_inputs(
    side: Any,
    entry_price: Any,
    exit_price: Any,
    stop_price: Any,
    quantity: Any,
    scenario: Any,
    timeframe: Any,
    atr_pct: Any,
) -> tuple:
    """Validate all trade inputs. Raises ValueError on any invalid input.

    Checks: finite floats only, positive prices/quantity, stop != entry,
    timeframe in SUPPORTED_TIMEFRAMES, side in BUY/SELL,
    scenario in SCENARIO_NAMES, side/stop consistency.

    Returns (side_str, entry, exit_, stop, qty, scenario_str, tf_str, atr).
    """
    _side = str(side or "").upper().strip()
    if _side not in ("BUY", "SELL"):
        raise ValueError(
            f"Invalid side {side!r}: must be 'BUY' or 'SELL'. No silent default."
        )

    _scenario = str(scenario or "").lower().strip()
    if _scenario not in SCENARIO_NAMES:
        raise ValueError(
            f"Unknown scenario {scenario!r}: must be one of {SCENARIO_NAMES}. No silent default."
        )

    tf_str = str(timeframe or "").lower().strip()
    if tf_str not in SUPPORTED_TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}: must be one of {sorted(SUPPORTED_TIMEFRAMES)}. "
            f"No implicit conversion to 15m."
        )

    entry = _assert_finite(entry_price, "entry_price")
    exit_ = _assert_finite(exit_price, "exit_price")
    stop = _assert_finite(stop_price, "stop_price")
    qty = _assert_finite(quantity, "quantity")
    atr = _assert_finite(atr_pct if atr_pct is not None else 0.0, "atr_pct")
    if atr < 0:
        raise ValueError(f"atr_pct must be >= 0, got {atr_pct!r}. Negative ATR is undefined.")

    if entry <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price!r}.")
    if exit_ <= 0:
        raise ValueError(f"exit_price must be > 0, got {exit_price!r}.")
    if stop <= 0:
        raise ValueError(f"stop_price must be > 0, got {stop_price!r}.")
    if qty <= 0:
        raise ValueError(f"quantity must be > 0, got {quantity!r}.")

    if abs(entry - stop) < 1e-12:
        raise ValueError(
            f"stop_price must differ from entry_price (initial_risk=0 is undefined). "
            f"entry={entry_price!r}, stop={stop_price!r}."
        )

    # Side/stop consistency: BUY requires stop < entry, SELL requires stop > entry
    if _side == "BUY" and stop >= entry:
        raise ValueError(
            f"For BUY, stop_price must be < entry_price. "
            f"entry={entry_price!r}, stop={stop_price!r}."
        )
    if _side == "SELL" and stop <= entry:
        raise ValueError(
            f"For SELL, stop_price must be > entry_price. "
            f"entry={entry_price!r}, stop={stop_price!r}."
        )

    return _side, entry, exit_, stop, qty, _scenario, tf_str, atr


def _compute_cost_amounts(
    entry_notional: float,
    exit_notional: float,
    bps: Dict[str, float],
) -> Dict[str, float]:
    """Single source of truth for cost component computation.

    Both compute_trade_outcome() and apply_cost_to_backtest_trade() call this
    function with the same notionals, guaranteeing exact parity.

    Returns dict with all 6 component amounts and total.
    """
    fee_entry = entry_notional * bps["fee_entry_bps"] / 10000.0
    fee_exit = exit_notional * bps["fee_exit_bps"] / 10000.0
    spread = entry_notional * bps["spread_bps"] / 10000.0
    slippage = entry_notional * bps["slippage_bps"] / 10000.0
    latency = entry_notional * bps["latency_bps"] / 10000.0
    partial_fill = entry_notional * bps["partial_fill_bps"] / 10000.0
    total = fee_entry + fee_exit + spread + slippage + latency + partial_fill
    return {
        "fee_entry_amt": fee_entry,
        "fee_exit_amt": fee_exit,
        "spread_amt": spread,
        "slippage_amt": slippage,
        "latency_amt": latency,
        "partial_fill_amt": partial_fill,
        "total_cost_amt": total,
    }


def _assert_finite_outputs(d: Dict[str, Any]) -> None:
    """Raise ValueError if any float in the dict is not finite."""
    for k, v in d.items():
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError(
                f"Output {k}={v!r} is not finite. Input validation may have missed an edge case."
            )


@dataclass(frozen=True)
class TradeOutcome:
    """Outcome of a closed trade with full cost breakdown. All 6 cost components."""
    scenario: str
    symbol: str
    timeframe: str
    side: str              # BUY or SELL
    entry_price: float
    exit_price: float
    stop_price: float
    quantity: float
    notional: float        # entry_price * quantity
    gross_pnl: float
    fee_entry_amt: float
    fee_exit_amt: float    # uses exit_notional (exit_price * quantity)
    spread_amt: float
    slippage_amt: float
    latency_amt: float
    partial_fill_amt: float
    total_cost_amt: float  # sum of all 6 components
    net_pnl: float
    initial_risk: float    # abs(entry - stop) * quantity
    gross_R: float
    net_R: float
    fee_entry_bps: float
    fee_exit_bps: float
    spread_bps: float
    slippage_bps: float
    latency_bps: float
    partial_fill_bps: float
    total_round_trip_bps: float
    fill_probability: float
    atr_pct: float

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {k: round(v, 8) if isinstance(v, float) else v for k, v in d.items()}


class UnifiedCostModel:
    """Unified, diagnostic-only cost model for benchmarks and walk-forward.

    All methods fail-closed on invalid inputs. No silent defaults.
    Risk policy for Phases 3-5: risk_pct = 0.005 (0.5% per trade, fixed).
    """

    @staticmethod
    def bps_for_scenario(
        scenario: str,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        atr_pct: float = 0.0,
    ) -> Dict[str, float]:
        """Return cost breakdown in bps for a given scenario.

        Raises ValueError for unknown scenario or unsupported timeframe.
        """
        s = str(scenario or "").lower().strip()
        if s not in SCENARIO_NAMES:
            raise ValueError(
                f"Unknown scenario {scenario!r}: must be one of {SCENARIO_NAMES}."
            )
        tf = str(timeframe or "").lower().strip()
        if tf not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe {timeframe!r}: must be one of {sorted(SUPPORTED_TIMEFRAMES)}."
            )
        atr = _assert_finite(atr_pct if atr_pct is not None else 0.0, "atr_pct")
        if atr < 0:
            raise ValueError(f"atr_pct must be >= 0, got {atr_pct!r}.")
        return _bps_components(s, symbol, tf, atr)

    @staticmethod
    def compute_trade_outcome(
        *,
        side: str,
        entry_price: float,
        exit_price: float,
        stop_price: float,
        quantity: float,
        scenario: str = "realistic",
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        atr_pct: float = 0.0,
    ) -> TradeOutcome:
        """Compute gross and net PnL for a closed trade.

        All 6 cost components are charged via _compute_cost_amounts().
        Costs flow through notional, not directly from bps to R.

        Raises ValueError on any invalid input (fail-closed, no silent defaults).
        All outputs are verified finite before returning.
        """
        _side, entry, exit_, stop, qty, s, tf, atr = _validate_trade_inputs(
            side, entry_price, exit_price, stop_price, quantity, scenario, timeframe, atr_pct
        )

        direction = 1.0 if _side == "BUY" else -1.0
        notional = entry * qty
        exit_notional = exit_ * qty
        gross_pnl = (exit_ - entry) * qty * direction
        initial_risk = abs(entry - stop) * qty

        bps = _bps_components(s, symbol, tf, atr)
        costs = _compute_cost_amounts(notional, exit_notional, bps)
        total_cost = costs["total_cost_amt"]

        net_pnl = gross_pnl - total_cost
        gross_R = gross_pnl / initial_risk
        net_R = net_pnl / initial_risk

        # Verify all outputs finite
        _assert_finite_outputs({
            "gross_pnl": gross_pnl, "total_cost_amt": total_cost,
            "net_pnl": net_pnl, "gross_R": gross_R, "net_R": net_R,
        })

        return TradeOutcome(
            scenario=s,
            symbol=symbol,
            timeframe=tf,
            side=_side,
            entry_price=round(entry, 8),
            exit_price=round(exit_, 8),
            stop_price=round(stop, 8),
            quantity=round(qty, 8),
            notional=round(notional, 4),
            gross_pnl=round(gross_pnl, 8),
            fee_entry_amt=round(costs["fee_entry_amt"], 8),
            fee_exit_amt=round(costs["fee_exit_amt"], 8),
            spread_amt=round(costs["spread_amt"], 8),
            slippage_amt=round(costs["slippage_amt"], 8),
            latency_amt=round(costs["latency_amt"], 8),
            partial_fill_amt=round(costs["partial_fill_amt"], 8),
            total_cost_amt=round(total_cost, 8),
            net_pnl=round(net_pnl, 8),
            initial_risk=round(initial_risk, 8),
            gross_R=round(gross_R, 8),
            net_R=round(net_R, 8),
            fee_entry_bps=bps["fee_entry_bps"],
            fee_exit_bps=bps["fee_exit_bps"],
            spread_bps=bps["spread_bps"],
            slippage_bps=bps["slippage_bps"],
            latency_bps=bps["latency_bps"],
            partial_fill_bps=bps["partial_fill_bps"],
            total_round_trip_bps=bps["total_round_trip_bps"],
            fill_probability=bps["fill_probability"],
            atr_pct=round(atr, 6),
        )

    @staticmethod
    def all_scenarios(
        *,
        side: str,
        entry_price: float,
        exit_price: float,
        stop_price: float,
        quantity: float,
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        atr_pct: float = 0.0,
    ) -> Dict[str, TradeOutcome]:
        """Return TradeOutcome for every real cost scenario (excludes 'zero')."""
        return {
            s: UnifiedCostModel.compute_trade_outcome(
                side=side,
                entry_price=entry_price,
                exit_price=exit_price,
                stop_price=stop_price,
                quantity=quantity,
                scenario=s,
                symbol=symbol,
                timeframe=timeframe,
                atr_pct=atr_pct,
            )
            for s in SCENARIO_NAMES if s != "zero"
        }

    @staticmethod
    def apply_cost_to_backtest_trade(
        *,
        gross_pnl: float,
        initial_risk: float,
        entry_price: float,
        exit_price: float,
        quantity: float,
        scenario: str = "realistic",
        symbol: str = "BTC/USDT",
        timeframe: str = "15m",
        atr_pct: float = 0.0,
    ) -> Dict[str, float]:
        """Apply cost model to a pre-computed backtest trade (gross pnl known).

        Uses IDENTICAL _compute_cost_amounts() as compute_trade_outcome(), guaranteeing
        exact parity for the same entry_price, exit_price, quantity and scenario.

        If exit_price is not available in the caller's context, the caller must raise
        an error rather than silently estimating. Do NOT call this with a dummy exit_price.

        Raises ValueError on invalid inputs (fail-closed).
        All outputs verified finite before returning.
        Returns: gross_pnl, cost_amt, net_pnl, gross_R, net_R, cost_R, total_round_trip_bps.
        """
        # Validate scenario and timeframe
        s = str(scenario or "").lower().strip()
        if s not in SCENARIO_NAMES:
            raise ValueError(
                f"Unknown scenario {scenario!r}: must be one of {SCENARIO_NAMES}."
            )
        tf = str(timeframe or "").lower().strip()
        if tf not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe {timeframe!r}: must be one of {sorted(SUPPORTED_TIMEFRAMES)}."
            )

        # Validate all numeric inputs
        gp = _assert_finite(gross_pnl, "gross_pnl")
        ir = _assert_finite(initial_risk, "initial_risk")
        ep = _assert_finite(entry_price, "entry_price")
        xp = _assert_finite(exit_price, "exit_price")
        qty = _assert_finite(quantity, "quantity")
        atr = _assert_finite(atr_pct if atr_pct is not None else 0.0, "atr_pct")
        if atr < 0:
            raise ValueError(f"atr_pct must be >= 0, got {atr_pct!r}.")

        if ir <= 0:
            raise ValueError(f"initial_risk must be positive, got {initial_risk!r}.")
        if ep <= 0:
            raise ValueError(f"entry_price must be positive, got {entry_price!r}.")
        if xp <= 0:
            raise ValueError(f"exit_price must be positive, got {exit_price!r}.")
        if qty <= 0:
            raise ValueError(f"quantity must be positive, got {quantity!r}.")

        notional = ep * qty
        exit_notional = xp * qty

        bps = _bps_components(s, symbol, tf, atr)
        costs = _compute_cost_amounts(notional, exit_notional, bps)
        cost_amt = costs["total_cost_amt"]

        net_pnl = gp - cost_amt
        gross_R = gp / ir
        net_R = net_pnl / ir
        cost_R = cost_amt / ir

        _assert_finite_outputs({
            "cost_amt": cost_amt, "net_pnl": net_pnl,
            "gross_R": gross_R, "net_R": net_R, "cost_R": cost_R,
        })

        return {
            "gross_pnl": round(gp, 8),
            "cost_amt": round(cost_amt, 8),
            "net_pnl": round(net_pnl, 8),
            "gross_R": round(gross_R, 8),
            "net_R": round(net_R, 8),
            "cost_R": round(cost_R, 8),
            "total_round_trip_bps": bps["total_round_trip_bps"],
        }
