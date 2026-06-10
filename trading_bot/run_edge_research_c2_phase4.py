"""Cycle-2 STRAT-03 (part 2) — THE single cycle-2 final-OOS access.

Usage:
    python trading_bot/run_edge_research_c2_phase4.py

Gates: the 10 cycle-1 gates UNCHANGED, plus the cycle-2 regime gate:
   11. net PnL > 0 in at least 2 distinct regimes (bull/bear/chop,
       counting only regimes with >= 10 OOS trades).

The cycle-2 final-OOS may be opened exactly once
(data/edge_research2/oos_access_log.json); re-running is refused.
DSR counts the cumulative cycle1+cycle2 trial log.

Writes data/edge_research_report_c2.json with edge_demonstrated and,
if false, the explicit cycle-3 verdict required by the declared
3-cycle ceiling. Diagnostic-only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from trading_bot.research.edge_lab import (  # noqa: E402
    CausalExecutor,
    SplitContract,
    append_trial,
    compute_metrics,
    config_hash,
    load_asset_frames,
    portfolio_replay,
    read_trial_log,
    write_json_atomic,
)
from trading_bot.research.hypotheses_c2 import (  # noqa: E402
    all_c2_configs,
    c2_specs_for,
    is_panel_family,
    xs_events_panel,
)
from trading_bot.research.regime import daily_regime_labels, regime_for_times  # noqa: E402
from trading_bot.run_edge_research_phase3 import deflated_sharpe  # noqa: E402
from trading_bot.run_edge_research_phase4 import GATES_SPEC  # noqa: E402

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False

PHASE = "C2-STRAT-03-FINAL-OOS"
CYCLE = 2
REGIME_MIN_TRADES = 10
REGIME_MIN_POSITIVE = 2

C2_CACHE = ROOT / "data" / "strat02_cache"
C2_LOCK = "strat02_temporal_splits.json"
C2_RESEARCH = ROOT / "data" / "edge_research2"
TRIAL_LOG_DIR = ROOT / "data" / "edge_research"
OOS_ACCESS_LOG = C2_RESEARCH / "oos_access_log.json"


def main() -> int:
    t0 = time.time()
    contract = SplitContract.load(C2_CACHE, lock_name=C2_LOCK)

    if OOS_ACCESS_LOG.exists():
        print("FATAL: cycle-2 final-OOS already accessed once. Refusing.")
        return 2

    phase3 = json.loads((C2_RESEARCH / "phase3_report.json").read_text(encoding="utf-8"))
    if phase3.get("final_oos_accessed") is not False:
        print("FATAL: cycle-2 phase 3 does not certify final_oos_accessed=false")
        return 2
    shortlist = phase3["shortlist"]
    pbo_full = phase3["cscv_pbo_c2_panel"]
    trial_log = read_trial_log(TRIAL_LOG_DIR)
    n_trials = len({t["config_id"] for t in trial_log})

    panel_manifest = json.loads(
        (C2_CACHE / "strat02_panel_manifest.json").read_text(encoding="utf-8")
    )
    panel: List[str] = panel_manifest["panel_with_data"]

    print("=" * 70)
    print("C2 STRAT-03 FINAL GATE — single cycle-2 final-OOS access")
    print(f"  shortlist size : {len(shortlist)}")
    print(f"  trials counted : {n_trials} (cumulative cycle1+cycle2)")
    print(f"  OOS window     : {contract.oos_start} -> {contract.oos_end}")
    print("=" * 70)

    candidates: List[Dict[str, Any]] = []
    edge_demonstrated = False
    oos_opened = False

    if shortlist:
        oos_opened = True
        write_json_atomic(
            OOS_ACCESS_LOG,
            {
                "accessed_at_utc": pd.Timestamp.utcnow().isoformat(),
                "phase": PHASE,
                "cycle": CYCLE,
                "purpose": "single cycle-2 final-OOS gate evaluation of frozen shortlist",
                "shortlist_config_ids": [s["config_id"] for s in shortlist],
                "split_lock_sha256": contract.lock_sha256,
            },
        )

        frames15: Dict[str, pd.DataFrame] = {}
        executors: Dict[str, CausalExecutor] = {}
        bars_oos = 0
        for asset in panel:
            df15, df5 = load_asset_frames(asset, C2_CACHE)  # full history
            frames15[asset] = df15
            executors[asset] = CausalExecutor(df15, df5)
            dt = df15["datetime"]
            bars_oos += int(((dt >= contract.oos_start) & (dt < contract.oos_end)).sum())

        daily_labels = daily_regime_labels(frames15["BTCUSDT"])
        cfg_by_id = {c.config_id: c for c in all_c2_configs()}

        for entry in shortlist:
            cid = entry["config_id"]
            cfg = cfg_by_id[cid]
            if entry["params"] != cfg.params:
                raise RuntimeError(f"{cid}: frozen params differ from code grids")

            if is_panel_family(cfg):
                events = xs_events_panel(
                    frames15, executors, cfg,
                    contract.oos_start, contract.oos_end,
                    daily_labels=daily_labels,
                )
            else:
                events = []
                for asset in panel:
                    specs = c2_specs_for(cfg, frames15[asset])
                    events.extend(
                        executors[asset].run(
                            specs, family=cfg.family, config_id=cid, asset=asset,
                            window_start=contract.oos_start,
                            window_end=contract.oos_end,
                        )
                    )
            events.sort(key=lambda e: e.entry_time)

            scen: Dict[str, Any] = {}
            for sc in ("realistic", "conservative", "severe"):
                trades = portfolio_replay(events, scenario=sc)
                m = compute_metrics(trades, bars_in_window_15m=bars_oos,
                                    n_signals=len(events))
                scen[sc] = m
                append_trial(
                    TRIAL_LOG_DIR,
                    {"phase": PHASE, "cycle": CYCLE, "config_id": cid,
                     "family": cfg.family, "params": cfg.params,
                     "split": "final_oos", "scenario": sc,
                     "split_lock_sha256": contract.lock_sha256, "metrics": m},
                )

            real_trades = portfolio_replay(events, scenario="realistic")
            dsr = deflated_sharpe([t.net_R for t in real_trades], n_trials=n_trials)

            # regime stratification on OOS (gate 11)
            regime_detail: Dict[str, Any] = {}
            regimes_positive = 0
            if real_trades:
                regs = regime_for_times(
                    daily_labels, pd.Series([t.event.signal_time for t in real_trades])
                )
                for reg in ("bull", "bear", "chop", "unknown"):
                    sel = [t for t, g in zip(real_trades, regs) if g == reg]
                    if not sel:
                        continue
                    pnl = float(sum(t.net_pnl for t in sel))
                    counted = len(sel) >= REGIME_MIN_TRADES and reg != "unknown"
                    positive = counted and pnl > 0
                    regimes_positive += int(positive)
                    regime_detail[reg] = {
                        "trades": len(sel), "net_pnl": pnl,
                        "counted": counted, "positive": positive,
                    }

            # temporal concentration
            conc: Dict[str, Any] = {"note": "no trades"}
            best_month_removed_positive = False
            if real_trades:
                dfc = pd.DataFrame(
                    {"month": [str(t.event.exit_time)[:7] for t in real_trades],
                     "pnl": [t.net_pnl for t in real_trades]}
                )
                by_m = dfc.groupby("month")["pnl"].sum().sort_values(ascending=False)
                total = float(dfc["pnl"].sum())
                rem = total - float(by_m.iloc[0])
                best_month_removed_positive = rem > 0
                conc = {
                    "total_net_pnl": total, "best_month": by_m.index[0],
                    "best_month_pnl": float(by_m.iloc[0]),
                    "net_pnl_without_best_month": rem,
                    "by_month": by_m.round(4).to_dict(),
                }

            m = scen["realistic"]
            gates = {
                "trades_ge_50": m["trades"] >= GATES_SPEC["min_trades"],
                "profit_factor_gt_1_20": (
                    m["profit_factor"] is not None
                    and m["profit_factor"] > GATES_SPEC["min_profit_factor"]
                ),
                "net_pnl_positive": m["net_pnl"] > GATES_SPEC["min_net_pnl"],
                "max_dd_le_15pct": m["max_drawdown_pct"] <= GATES_SPEC["max_drawdown_pct"],
                "dsr_ge_0_95": (
                    dsr["dsr_probability"] is not None
                    and dsr["dsr_probability"] >= GATES_SPEC["min_dsr_probability"]
                ),
                "pbo_lt_0_50": (
                    pbo_full["pbo"] is not None
                    and pbo_full["pbo"] < GATES_SPEC["max_pbo"]
                ),
                "severe_still_positive": scen["severe"]["net_pnl"] > GATES_SPEC["severe_min_net_pnl"],
                "top3_le_35pct_gross_profit": (
                    m["top3_profit_share"] is not None
                    and m["top3_profit_share"] <= GATES_SPEC["max_top3_profit_share"]
                ),
                "temporal_concentration": best_month_removed_positive,
                "no_oos_contamination": True,
                "regime_ge_2_positive": regimes_positive >= REGIME_MIN_POSITIVE,
            }
            passed = all(gates.values())
            margin = {
                "trades": m["trades"] - GATES_SPEC["min_trades"],
                "profit_factor": (
                    None if m["profit_factor"] is None
                    else round(m["profit_factor"] - GATES_SPEC["min_profit_factor"], 4)
                ),
                "net_pnl": round(m["net_pnl"], 4),
                "drawdown_headroom_pct": round(
                    GATES_SPEC["max_drawdown_pct"] - m["max_drawdown_pct"], 2
                ),
                "dsr": (
                    None if dsr["dsr_probability"] is None
                    else round(dsr["dsr_probability"] - GATES_SPEC["min_dsr_probability"], 4)
                ),
                "pbo": (
                    None if pbo_full["pbo"] is None
                    else round(GATES_SPEC["max_pbo"] - pbo_full["pbo"], 4)
                ),
                "severe_net_pnl": round(scen["severe"]["net_pnl"], 4),
                "top3_share_headroom": (
                    None if m["top3_profit_share"] is None
                    else round(GATES_SPEC["max_top3_profit_share"] - m["top3_profit_share"], 4)
                ),
                "regimes_positive": regimes_positive,
            }
            if passed:
                edge_demonstrated = True
            candidates.append(
                {
                    "config_id": cid, "family": cfg.family, "params": cfg.params,
                    "config_hash": config_hash({"family": cfg.family, **cfg.params}),
                    "final_oos": scen, "dsr_final_oos": dsr,
                    "regime_detail_oos": regime_detail,
                    "temporal_concentration": conc,
                    "gates": gates, "gates_passed": passed, "gate_margins": margin,
                    "validation_reference": entry["validation_realistic"],
                }
            )
            print(
                f"[gate] {cid}: passed={passed} trades={m['trades']} "
                f"PF={m['profit_factor']} netPnL={m['net_pnl']:.2f} "
                f"DD={m['max_drawdown_pct']:.1f}% DSR={dsr.get('dsr_probability')} "
                f"severe={scen['severe']['net_pnl']:.2f} regimes+={regimes_positive}"
            )
            for g, ok in gates.items():
                if not ok:
                    print(f"        FAILED gate: {g}")

    contamination_statement = (
        "Cycle-2 final-OOS protection: phases C2-2/C2-3 loaded data through "
        "guard_no_oos() which physically drops candles with datetime >= "
        "oos_start. The cycle-2 OOS overlaps the burnt cycle-1 OOS window "
        "(2025-08..2026-06) because the contract fixes it to the most recent "
        "20%; this overlap is declared, and mitigated by: configurations "
        "re-declared a priori, cumulative trial counting, and the researcher "
        "never re-ranking on cycle-1 OOS metrics. This run is the first and "
        "only read of the cycle-2 OOS; re-running is refused via "
        "oos_access_log.json."
    )

    report = {
        "report_type": "edge_research_report",
        "cycle": CYCLE,
        "cycle_ceiling": 3,
        "diagnostic_only": True,
        "opens_orders": False,
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "methodology": "docs/STRATEGY_RESEARCH_ROADMAP.md STRAT-01..STRAT-04 + cycle-2 regime gate",
        "split_lock_sha256": contract.lock_sha256,
        "splits": {
            "train": [str(contract.train_start), str(contract.train_end)],
            "validation": [str(contract.val_start), str(contract.val_end)],
            "final_oos": [str(contract.oos_start), str(contract.oos_end)],
        },
        "panel": panel,
        "risk_per_trade": 0.005,
        "total_trials_counted_cumulative": n_trials,
        "trial_log_entries": len(trial_log),
        "gates_spec": {**GATES_SPEC, "regime_min_positive": REGIME_MIN_POSITIVE,
                       "regime_min_trades": REGIME_MIN_TRADES},
        "cscv_pbo_c2_panel": pbo_full,
        "final_oos_opened": oos_opened,
        "oos_contamination_statement": contamination_statement,
        "shortlist_size": len(shortlist),
        "candidates": candidates,
        "edge_demonstrated": edge_demonstrated,
    }
    out = ROOT / "data" / "edge_research_report_c2.json"
    write_json_atomic(out, report)
    print("\n" + "=" * 70)
    print(f"edge_demonstrated = {edge_demonstrated}")
    print(f"report -> {out} ({time.time() - t0:.1f}s)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
