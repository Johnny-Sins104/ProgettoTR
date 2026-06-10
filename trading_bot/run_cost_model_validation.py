"""
run_cost_model_validation.py — Phase 2: Unified Cost Model Validation
=======================================================================
Diagnostic-only script. Validates UnifiedCostModel numerics across
all scenarios and test cases. Does NOT open orders, connect to any
exchange, or modify existing files.

Usage (from project root):
    python trading_bot/run_cost_model_validation.py

Exit code: 0 if gate_result == PASS, 1 if gate_result == BLOCKED.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Path setup — allow import from both project root and trading_bot/
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parent.parent          # trading_bot/ -> project root
_TRADING_BOT = _THIS_FILE.parent                 # trading_bot/
for _p in (str(PROJECT_ROOT), str(_TRADING_BOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_PATH = DATA_DIR / "cost_model_validation.json"
PHASE1_STATUS_PATH = DATA_DIR / "market_data_integrity_status.json"

# Safety guards — immutable constants
DIAGNOSTIC_ONLY: bool = True
OPENS_ORDERS: bool = False
LIVE_TRADING_ALLOWED: bool = False
PAPER_TRADING_ACTIVATION_ALLOWED: bool = False

# ---------------------------------------------------------------------------
# Import cost model
# ---------------------------------------------------------------------------
from core.unified_trade_cost import (  # noqa: E402  (after sys.path insert)
    SCENARIO_NAMES as _ALL_SCENARIO_NAMES,
    UnifiedCostModel,
)

# This gate validates only real-cost scenarios: "zero" is a diagnostic-only
# scenario excluded by UnifiedCostModel.all_scenarios() and would violate the
# total_cost > 0 assertions by construction.
SCENARIO_NAMES = tuple(s for s in _ALL_SCENARIO_NAMES if s != "zero")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round6(v: float) -> float:
    return round(v, 6)


def _fmt(label: str, value: Any) -> str:
    return f"  {label:<45} {value}"


def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


# ---------------------------------------------------------------------------
# Step 1 — Read Phase 1 gate
# ---------------------------------------------------------------------------

def read_phase1_gate() -> tuple[str, str]:
    """Return (gate_result, note) from market_data_integrity_status.json."""
    try:
        raw = json.loads(PHASE1_STATUS_PATH.read_text(encoding="utf-8"))
        result = str(raw.get("gate_result", "UNKNOWN")).upper()
        note = (
            "Phase 2 proceeds per user instruction: "
            "raw OHLCV approved, contamination in derived reports only"
        )
        return result, note
    except Exception as exc:
        return "UNKNOWN", f"Could not read phase1 status: {exc}"


# ---------------------------------------------------------------------------
# Step 2 — Numerical test cases
# ---------------------------------------------------------------------------

def _run_case(
    label: str,
    side: str,
    entry: float,
    exit_: float,
    stop: float,
    qty: float,
    symbol: str,
    timeframe: str,
    atr_pct: float = 0.0,
) -> tuple[Dict[str, Any], List[str]]:
    """
    Run all_scenarios for a test case and collect results + assertion failures.
    Returns (case_dict, failures).
    """
    outcomes = UnifiedCostModel.all_scenarios(
        side=side,
        entry_price=entry,
        exit_price=exit_,
        stop_price=stop,
        quantity=qty,
        symbol=symbol,
        timeframe=timeframe,
        atr_pct=atr_pct,
    )

    failures: List[str] = []
    by_scenario: Dict[str, Any] = {}
    costs_ordered: List[float] = []

    for sc in SCENARIO_NAMES:
        o = outcomes[sc]
        by_scenario[sc] = o.to_dict()
        costs_ordered.append(o.total_cost_amt)

        # total_cost > 0 always
        if o.total_cost_amt <= 0:
            failures.append(
                f"[{label}][{sc}] total_cost_amt={o.total_cost_amt} not > 0"
            )

        # net_pnl < gross_pnl always (costs always reduce net)
        if not (o.net_pnl < o.gross_pnl):
            failures.append(
                f"[{label}][{sc}] net_pnl={o.net_pnl} not < gross_pnl={o.gross_pnl}"
            )

        # net_R < gross_R always
        if not (o.net_R < o.gross_R):
            failures.append(
                f"[{label}][{sc}] net_R={o.net_R} not < gross_R={o.gross_R}"
            )

        # cost_R > 0
        ir = o.initial_risk
        if ir > 1e-12:
            cost_R = o.total_cost_amt / ir
            if cost_R <= 0:
                failures.append(
                    f"[{label}][{sc}] cost_R={cost_R} not > 0"
                )

    # Scenario ordering: optimistic < realistic < conservative < severe
    for i in range(len(SCENARIO_NAMES) - 1):
        sc_a = SCENARIO_NAMES[i]
        sc_b = SCENARIO_NAMES[i + 1]
        if not (costs_ordered[i] < costs_ordered[i + 1]):
            failures.append(
                f"[{label}] total_cost ordering violated: "
                f"{sc_a}={costs_ordered[i]} not < {sc_b}={costs_ordered[i + 1]}"
            )

    case_dict: Dict[str, Any] = {
        "inputs": {
            "side": side,
            "entry_price": entry,
            "exit_price": exit_,
            "stop_price": stop,
            "quantity": qty,
            "symbol": symbol,
            "timeframe": timeframe,
            "atr_pct": atr_pct,
        },
        "expected": {
            "initial_risk": round(abs(entry - stop) * qty, 8),
            "gross_pnl": round(
                (exit_ - entry) * qty * (1.0 if side == "BUY" else -1.0), 8
            ),
            "gross_R": round(
                (exit_ - entry) * qty * (1.0 if side == "BUY" else -1.0)
                / (abs(entry - stop) * qty),
                8,
            ),
        },
        "by_scenario": by_scenario,
        "assertions_passed": len(failures) == 0,
    }
    return case_dict, failures


def run_numerical_cases() -> tuple[Dict[str, Any], List[str]]:
    all_failures: List[str] = []
    cases: Dict[str, Any] = {}

    print("\n" + "=" * 70)
    print("NUMERICAL TEST CASES")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Case A — BUY win, 1:2 RR, BTC 15m
    # ------------------------------------------------------------------
    print("\n[CASE A] BUY win — BTC/USDT 15m — entry=50000 exit=51000 stop=49500 qty=0.01")
    cA, fA = _run_case(
        label="A_buy_win",
        side="BUY",
        entry=50000.0, exit_=51000.0, stop=49500.0,
        qty=0.01, symbol="BTC/USDT", timeframe="15m",
    )
    cases["case_A_buy_win"] = cA
    all_failures.extend(fA)

    # Print table for Case A
    print(_fmt("scenario", "total_cost_amt  net_pnl  gross_R  net_R  total_bps"))
    for sc in SCENARIO_NAMES:
        o_dict = cA["by_scenario"][sc]
        print(_fmt(
            sc,
            f"{o_dict['total_cost_amt']:.6f}  "
            f"{o_dict['net_pnl']:.6f}  "
            f"{o_dict['gross_R']:.4f}  "
            f"{o_dict['net_R']:.4f}  "
            f"{o_dict['total_round_trip_bps']:.4f}",
        ))
    print(_fmt("ordering check", _pass_fail(len(fA) == 0)))

    # ------------------------------------------------------------------
    # Case B — BUY loss, stop hit, BTC 15m
    # ------------------------------------------------------------------
    print("\n[CASE B] BUY loss — BTC/USDT 15m — entry=50000 exit=49500 stop=49500 qty=0.01")
    cB, fB = _run_case(
        label="B_buy_loss",
        side="BUY",
        entry=50000.0, exit_=49500.0, stop=49500.0,
        qty=0.01, symbol="BTC/USDT", timeframe="15m",
    )
    cases["case_B_buy_loss"] = cB
    all_failures.extend(fB)

    # Extra check: net_R < -1.0 in all scenarios
    print(_fmt("scenario", "gross_R   net_R"))
    for sc in SCENARIO_NAMES:
        o_dict = cB["by_scenario"][sc]
        net_R_ok = o_dict["net_R"] < -1.0
        if not net_R_ok:
            fB.append(
                f"[B_buy_loss][{sc}] net_R={o_dict['net_R']} not < -1.0 (stop loss not worsened by costs)"
            )
        print(_fmt(sc, f"{o_dict['gross_R']:.4f}   {o_dict['net_R']:.4f}  net_R<-1: {_pass_fail(net_R_ok)}"))
    all_failures.extend(fB[len(fB) - len([f for f in fB if "not < -1.0" in f]):])

    # ------------------------------------------------------------------
    # Case C — SELL win (short), BTC 15m
    # ------------------------------------------------------------------
    print("\n[CASE C] SELL win — BTC/USDT 15m — entry=50000 exit=49000 stop=50500 qty=0.01")
    cC, fC = _run_case(
        label="C_sell_win",
        side="SELL",
        entry=50000.0, exit_=49000.0, stop=50500.0,
        qty=0.01, symbol="BTC/USDT", timeframe="15m",
    )
    cases["case_C_sell_win"] = cC
    all_failures.extend(fC)

    # Check symmetry: SELL gross_R == BUY gross_R (same risk/reward distances)
    sell_gross_R = cC["by_scenario"]["realistic"]["gross_R"]
    buy_gross_R = cA["by_scenario"]["realistic"]["gross_R"]
    symmetry_ok = abs(sell_gross_R - buy_gross_R) < 1e-6
    if not symmetry_ok:
        all_failures.append(
            f"[C_sell_win] BUY/SELL gross_R symmetry failed: "
            f"BUY={buy_gross_R} SELL={sell_gross_R}"
        )
    print(_fmt("SELL gross_R", f"{sell_gross_R:.6f}  (BUY gross_R={buy_gross_R:.6f})  symmetry={_pass_fail(symmetry_ok)}"))
    print(_fmt("scenario", "gross_R   net_R"))
    for sc in SCENARIO_NAMES:
        o_dict = cC["by_scenario"][sc]
        print(_fmt(sc, f"{o_dict['gross_R']:.4f}   {o_dict['net_R']:.4f}"))

    # ------------------------------------------------------------------
    # Case D — SELL loss (stop hit)
    # ------------------------------------------------------------------
    print("\n[CASE D] SELL loss — BTC/USDT 15m — entry=50000 exit=50500 stop=50500 qty=0.01")
    cD, fD = _run_case(
        label="D_sell_loss",
        side="SELL",
        entry=50000.0, exit_=50500.0, stop=50500.0,
        qty=0.01, symbol="BTC/USDT", timeframe="15m",
    )
    cases["case_D_sell_loss"] = cD
    all_failures.extend(fD)

    # Extra check: net_R < -1.0 in all scenarios
    print(_fmt("scenario", "gross_R   net_R"))
    for sc in SCENARIO_NAMES:
        o_dict = cD["by_scenario"][sc]
        net_R_ok = o_dict["net_R"] < -1.0
        if not net_R_ok:
            fD.append(
                f"[D_sell_loss][{sc}] net_R={o_dict['net_R']} not < -1.0"
            )
        print(_fmt(sc, f"{o_dict['gross_R']:.4f}   {o_dict['net_R']:.4f}  net_R<-1: {_pass_fail(net_R_ok)}"))
    # Avoid double-counting; fD already extended above
    all_failures.extend([f for f in fD if "not < -1.0" in f])

    # ------------------------------------------------------------------
    # Case E — XRP/USDT 5m (smaller asset, higher tf_mult)
    # ------------------------------------------------------------------
    print("\n[CASE E] BUY win — XRP/USDT 5m — entry=1.40 exit=1.47 stop=1.35 qty=1000")
    cE, fE = _run_case(
        label="E_xrp_5m",
        side="BUY",
        entry=1.40, exit_=1.47, stop=1.35,
        qty=1000.0, symbol="XRP/USDT", timeframe="5m",
    )
    cases["case_E_xrp_5m"] = cE
    all_failures.extend(fE)

    print(_fmt("scenario", "total_cost_amt  total_bps"))
    for sc in SCENARIO_NAMES:
        o_dict = cE["by_scenario"][sc]
        print(_fmt(sc, f"{o_dict['total_cost_amt']:.6f}  {o_dict['total_round_trip_bps']:.4f}"))

    # XRP 5m total bps should be > XRP 15m (due to tf_mult_5m=1.2 in realistic+)
    print("\n  [5m vs 15m cost comparison for XRP]")
    xrp_5m_costs: Dict[str, float] = {}
    xrp_15m_costs: Dict[str, float] = {}
    tf_ok_all = True
    for sc in SCENARIO_NAMES:
        bps_5m = UnifiedCostModel.bps_for_scenario(sc, "XRP/USDT", "5m")["total_round_trip_bps"]
        bps_15m = UnifiedCostModel.bps_for_scenario(sc, "XRP/USDT", "15m")["total_round_trip_bps"]
        xrp_5m_costs[sc] = bps_5m
        xrp_15m_costs[sc] = bps_15m
        # optimistic has tf_mult_5m=1.0 so they may be equal; realistic+ should be higher
        if sc != "optimistic":
            tf_ok = bps_5m > bps_15m
            if not tf_ok:
                all_failures.append(
                    f"[E_xrp_5m][{sc}] 5m bps={bps_5m} not > 15m bps={bps_15m}"
                )
                tf_ok_all = False
            print(_fmt(f"  {sc}: 5m={bps_5m:.4f} vs 15m={bps_15m:.4f}", _pass_fail(tf_ok)))
        else:
            print(_fmt(f"  {sc}: 5m={bps_5m:.4f} vs 15m={bps_15m:.4f}", "N/A (tf_mult=1.0 in optimistic)"))

    cE["xrp_5m_vs_15m_bps"] = {
        "5m": xrp_5m_costs,
        "15m": xrp_15m_costs,
        "5m_higher_than_15m_for_realistic_and_above": tf_ok_all,
    }

    return cases, all_failures


# ---------------------------------------------------------------------------
# Step 3 — Summary table
# ---------------------------------------------------------------------------

def print_summary_table(cases: Dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print("SUMMARY TABLE — gross_R / net_R by case and scenario")
    print("=" * 70)
    header = f"{'case':<20} {'scenario':<14} {'gross_pnl':>10} {'net_pnl':>10} {'gross_R':>8} {'net_R':>8} {'total_cost':>12}"
    print(header)
    print("-" * 84)
    for case_key, case_data in cases.items():
        for sc in SCENARIO_NAMES:
            o = case_data["by_scenario"][sc]
            print(
                f"{case_key:<20} {sc:<14} "
                f"{o['gross_pnl']:>10.4f} "
                f"{o['net_pnl']:>10.4f} "
                f"{o['gross_R']:>8.4f} "
                f"{o['net_R']:>8.4f} "
                f"{o['total_cost_amt']:>12.6f}"
            )
        print("-" * 84)


# ---------------------------------------------------------------------------
# Step 4 — BPS breakeven check across symbols and timeframes
# ---------------------------------------------------------------------------

def run_bps_breakeven_check() -> tuple[Dict[str, Any], List[str], bool]:
    print("\n" + "=" * 70)
    print("BPS BREAKEVEN CHECK — scenario ordering by symbol and timeframe")
    print("=" * 70)

    combos = [
        ("BTC/USDT", "5m"),
        ("BTC/USDT", "15m"),
        ("XRP/USDT", "5m"),
        ("XRP/USDT", "15m"),
    ]

    failures: List[str] = []
    bps_table: Dict[str, Any] = {}
    ordering_ok_overall = True

    print(f"{'symbol+tf':<18} {'optimistic':>12} {'realistic':>12} {'conservative':>12} {'severe':>12} {'ordered?':>10}")
    print("-" * 80)

    for symbol, tf in combos:
        row: Dict[str, float] = {}
        costs_seq: List[float] = []
        for sc in SCENARIO_NAMES:
            bps = UnifiedCostModel.bps_for_scenario(sc, symbol, tf)
            total_bps = bps["total_round_trip_bps"]
            row[sc] = total_bps
            costs_seq.append(total_bps)

        # Verify strict ordering
        ordering_ok = all(
            costs_seq[i] < costs_seq[i + 1] for i in range(len(SCENARIO_NAMES) - 1)
        )
        if not ordering_ok:
            ordering_ok_overall = False
            failures.append(
                f"[bps_check][{symbol} {tf}] scenario bps ordering violated: {dict(zip(SCENARIO_NAMES, costs_seq))}"
            )

        key = f"{symbol.replace('/', '')}_{tf}"
        bps_table[key] = row
        print(
            f"{symbol} {tf:<6}      "
            f"{row['optimistic']:>12.4f} "
            f"{row['realistic']:>12.4f} "
            f"{row['conservative']:>12.4f} "
            f"{row['severe']:>12.4f} "
            f"{'YES' if ordering_ok else 'NO':>10}"
        )

    print(f"\n  Overall ordering verified: {_pass_fail(ordering_ok_overall)}")
    return bps_table, failures, ordering_ok_overall


# ---------------------------------------------------------------------------
# Step 5 — Build JSON report and write
# ---------------------------------------------------------------------------

def build_report(
    phase1_gate: str,
    phase1_note: str,
    cases: Dict[str, Any],
    bps_table: Dict[str, Any],
    ordering_verified: bool,
    all_failures: List[str],
) -> Dict[str, Any]:
    gate_result = "PASS" if len(all_failures) == 0 else "BLOCKED"

    report: Dict[str, Any] = {
        "report_type": "cost_model_validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": DIAGNOSTIC_ONLY,
        "opens_orders": OPENS_ORDERS,
        "live_trading_allowed": LIVE_TRADING_ALLOWED,
        "paper_trading_activation_allowed": PAPER_TRADING_ACTIVATION_ALLOWED,
        "phase1_gate_inherited": phase1_gate,
        "phase1_gate_note": phase1_note,
        "gate_result": gate_result,
        "gate_reasons": all_failures if all_failures else ["All numerical assertions passed"],
        "numerical_cases": cases,
        "bps_by_scenario_and_symbol": bps_table,
        "scenario_ordering_verified": ordering_verified,
        "cost_formulas": {
            "gross_pnl": "(exit - entry) * qty * direction",
            "notional": "entry * qty",
            "cost_amt": "notional * total_bps / 10000",
            "net_pnl": "gross_pnl - total_cost_amt",
            "initial_risk": "abs(entry - stop) * qty",
            "gross_R": "gross_pnl / initial_risk",
            "net_R": "net_pnl / initial_risk",
            "cost_R": "cost_amt / initial_risk",
            "no_direct_bps_to_R": True,
        },
    }
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 70)
    print("PHASE 2 — Unified Cost Model Validation")
    print("Diagnostic only. No orders. No live trading. No paper activation.")
    print("=" * 70)

    # Step 1 — Phase 1 gate
    phase1_gate, phase1_note = read_phase1_gate()
    print(f"\n[Phase 1 gate] {phase1_gate}")
    print(f"  Note: {phase1_note}")
    print("  (Phase 2 does not block on Phase 1 BLOCKED per user instruction.)")

    # Step 2 — Numerical test cases
    cases, case_failures = run_numerical_cases()

    # Step 3 — Summary table
    print_summary_table(cases)

    # Step 4 — BPS breakeven check
    bps_table, bps_failures, ordering_verified = run_bps_breakeven_check()

    # Aggregate all failures
    all_failures = case_failures + bps_failures

    # Step 5 — Build and write JSON
    report = build_report(
        phase1_gate=phase1_gate,
        phase1_note=phase1_note,
        cases=cases,
        bps_table=bps_table,
        ordering_verified=ordering_verified,
        all_failures=all_failures,
    )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "=" * 70)
    print(f"GATE RESULT: {report['gate_result']}")
    if all_failures:
        print(f"  {len(all_failures)} assertion(s) failed:")
        for f in all_failures:
            print(f"    - {f}")
    else:
        print("  All assertions passed.")
    print(f"\nReport written to: {OUTPUT_PATH}")
    print("=" * 70)

    return 0 if report["gate_result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
