"""STRAT-03 (part 2) runner — THE single final-OOS access and gate decision.

Usage:
    python trading_bot/run_edge_research_phase4.py

Hard rules enforced here:
- This script refuses to run if the OOS access log already exists: the
  final-OOS may be opened exactly once. There is no override flag.
- Only the configurations frozen in phase3_report.json are executed,
  byte-identical parameters, no re-tuning.
- Gates (all required, realistic scenario unless stated):
    1. trades >= 50
    2. profit factor > 1.20
    3. net PnL > 0
    4. max drawdown <= 15%
    5. Deflated Sharpe probability >= 0.95 (counting ALL logged trials)
    6. PBO < 0.50 (CSCV over the full 36-config panel, from phase 3)
    7. severe cost scenario still positive (net PnL > 0)
    8. top 3 trades <= 35% of positive gross profit
    9. temporal concentration: net PnL with the single best calendar
       month removed must remain > 0 (conservative interpretation,
       documented in the report)
   10. no prior final-OOS contamination (verified and declared)

Writes data/edge_research_report.json with edge_demonstrated true/false.
Diagnostic-only: no orders, no exchange access, no credentials.
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
    ASSETS,
    DEFAULT_CACHE_DIR,
    DEFAULT_RESEARCH_DIR,
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
from trading_bot.research.hypotheses import (  # noqa: E402
    HypothesisConfig,
    all_configs,
    specs_for,
    xs_events,
)
from trading_bot.run_edge_research_phase3 import deflated_sharpe  # noqa: E402

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False

PHASE = "STRAT-03-FINAL-OOS"
OOS_ACCESS_LOG = "oos_access_log.json"

GATES_SPEC = {
    "min_trades": 50,
    "min_profit_factor": 1.20,
    "min_net_pnl": 0.0,
    "max_drawdown_pct": 15.0,
    "min_dsr_probability": 0.95,
    "max_pbo": 0.50,
    "severe_min_net_pnl": 0.0,
    "max_top3_profit_share": 0.35,
}


def main() -> int:
    t0 = time.time()
    research_dir = ROOT / DEFAULT_RESEARCH_DIR
    cache_dir = ROOT / DEFAULT_CACHE_DIR
    contract = SplitContract.load(cache_dir)

    access_log_path = research_dir / OOS_ACCESS_LOG
    if access_log_path.exists():
        print("FATAL: final-OOS was already accessed once. Re-running phase 4")
        print("would contaminate the out-of-sample set. Refusing.")
        print(f"  access log: {access_log_path}")
        return 2

    phase3 = json.loads(
        (research_dir / "phase3_report.json").read_text(encoding="utf-8")
    )
    if phase3.get("final_oos_accessed") is not False:
        print("FATAL: phase 3 report does not certify final_oos_accessed=false")
        return 2
    shortlist = phase3["shortlist"]
    pbo_full = phase3["cscv_pbo_full_panel"]
    trial_log = read_trial_log(research_dir)
    n_trials = len({t["config_id"] for t in trial_log})

    print("=" * 70)
    print("STRAT-03 FINAL GATE — single final-OOS access")
    print(f"  shortlist size : {len(shortlist)}")
    print(f"  trials counted : {n_trials}")
    print(f"  OOS window     : {contract.oos_start} -> {contract.oos_end}")
    print("=" * 70)

    candidates: List[Dict[str, Any]] = []
    edge_demonstrated = False
    oos_opened = False

    if shortlist:
        # ---- the single OOS access starts here --------------------------
        oos_opened = True
        write_json_atomic(
            access_log_path,
            {
                "accessed_at_utc": pd.Timestamp.utcnow().isoformat(),
                "phase": PHASE,
                "purpose": "single final-OOS gate evaluation of frozen shortlist",
                "shortlist_config_ids": [s["config_id"] for s in shortlist],
                "split_lock_sha256": contract.lock_sha256,
            },
        )

        frames15: Dict[str, pd.DataFrame] = {}
        executors: Dict[str, CausalExecutor] = {}
        bars_oos: Dict[str, int] = {}
        for asset in ASSETS:
            df15, df5 = load_asset_frames(asset, cache_dir)  # full history
            frames15[asset] = df15
            executors[asset] = CausalExecutor(df15, df5)
            dt = df15["datetime"]
            bars_oos[asset] = int(
                ((dt >= contract.oos_start) & (dt < contract.oos_end)).sum()
            )

        cfg_by_id = {c.config_id: c for c in all_configs()}

        for entry in shortlist:
            cid = entry["config_id"]
            cfg = cfg_by_id[cid]
            frozen_hash = config_hash({"family": cfg.family, **cfg.params})
            declared = entry["params"]
            if declared != cfg.params:
                raise RuntimeError(
                    f"{cid}: frozen params differ from code grids — aborting"
                )

            if cfg.family == "xs_momentum":
                events = xs_events(
                    frames15, executors, cfg, contract.oos_start, contract.oos_end
                )
            else:
                events = []
                for asset in ASSETS:
                    specs = specs_for(cfg, frames15[asset])
                    events.extend(
                        executors[asset].run(
                            specs,
                            family=cfg.family,
                            config_id=cid,
                            asset=asset,
                            window_start=contract.oos_start,
                            window_end=contract.oos_end,
                        )
                    )
            events.sort(key=lambda e: e.entry_time)

            scen: Dict[str, Any] = {}
            for sc in ("realistic", "conservative", "severe"):
                trades = portfolio_replay(events, scenario=sc)
                m = compute_metrics(
                    trades,
                    bars_in_window_15m=sum(bars_oos.values()),
                    n_signals=len(events),
                )
                scen[sc] = m
                append_trial(
                    research_dir,
                    {
                        "phase": PHASE,
                        "config_id": cid,
                        "family": cfg.family,
                        "params": cfg.params,
                        "split": "final_oos",
                        "scenario": sc,
                        "split_lock_sha256": contract.lock_sha256,
                        "metrics": m,
                    },
                )

            real_trades = portfolio_replay(events, scenario="realistic")
            dsr = deflated_sharpe([t.net_R for t in real_trades], n_trials=n_trials)

            # temporal concentration on the OOS, realistic scenario
            conc: Dict[str, Any] = {"note": "no trades"}
            best_month_removed_positive = False
            if real_trades:
                dfc = pd.DataFrame(
                    {
                        "month": [str(t.event.exit_time)[:7] for t in real_trades],
                        "pnl": [t.net_pnl for t in real_trades],
                    }
                )
                by_m = dfc.groupby("month")["pnl"].sum().sort_values(ascending=False)
                total = float(dfc["pnl"].sum())
                rem = total - float(by_m.iloc[0])
                best_month_removed_positive = rem > 0
                conc = {
                    "total_net_pnl": total,
                    "best_month": by_m.index[0],
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
                    pbo_full["pbo"] is not None and pbo_full["pbo"] < GATES_SPEC["max_pbo"]
                ),
                "severe_still_positive": scen["severe"]["net_pnl"] > GATES_SPEC["severe_min_net_pnl"],
                "top3_le_35pct_gross_profit": (
                    m["top3_profit_share"] is not None
                    and m["top3_profit_share"] <= GATES_SPEC["max_top3_profit_share"]
                ),
                "temporal_concentration": best_month_removed_positive,
                "no_oos_contamination": True,  # certified below in the report
            }
            passed = all(gates.values())
            margin = {
                "trades": m["trades"] - GATES_SPEC["min_trades"],
                "profit_factor": (
                    None
                    if m["profit_factor"] is None
                    else round(m["profit_factor"] - GATES_SPEC["min_profit_factor"], 4)
                ),
                "net_pnl": round(m["net_pnl"], 4),
                "drawdown_headroom_pct": round(
                    GATES_SPEC["max_drawdown_pct"] - m["max_drawdown_pct"], 2
                ),
                "dsr": (
                    None
                    if dsr["dsr_probability"] is None
                    else round(dsr["dsr_probability"] - GATES_SPEC["min_dsr_probability"], 4)
                ),
                "pbo": (
                    None
                    if pbo_full["pbo"] is None
                    else round(GATES_SPEC["max_pbo"] - pbo_full["pbo"], 4)
                ),
                "severe_net_pnl": round(scen["severe"]["net_pnl"], 4),
                "top3_share_headroom": (
                    None
                    if m["top3_profit_share"] is None
                    else round(GATES_SPEC["max_top3_profit_share"] - m["top3_profit_share"], 4)
                ),
            }
            if passed:
                edge_demonstrated = True
            candidates.append(
                {
                    "config_id": cid,
                    "family": cfg.family,
                    "params": cfg.params,
                    "config_hash": frozen_hash,
                    "final_oos": scen,
                    "dsr_final_oos": dsr,
                    "temporal_concentration": conc,
                    "gates": gates,
                    "gates_passed": passed,
                    "gate_margins": margin,
                    "validation_reference": entry["validation_realistic"],
                }
            )
            print(
                f"[gate] {cid}: passed={passed} "
                f"trades={m['trades']} PF={m['profit_factor']} "
                f"netPnL={m['net_pnl']:.2f} DD={m['max_drawdown_pct']:.1f}% "
                f"DSR={dsr.get('dsr_probability')} severe={scen['severe']['net_pnl']:.2f}"
            )
            for g, ok in gates.items():
                if not ok:
                    print(f"        FAILED gate: {g}")

    contamination_statement = (
        "Final-OOS protection: phases 2/3 loaded data through guard_no_oos(), "
        "which physically drops every candle with datetime >= oos_start before "
        "any signal computation (see trading_bot/research/edge_lab.py). The "
        "phase-2 and phase-3 reports certify final_oos_accessed=false. This "
        "phase-4 run is the first and only read of the OOS region; the access "
        "is recorded in oos_access_log.json and re-running phase 4 is refused."
    )

    report = {
        "report_type": "edge_research_report",
        "diagnostic_only": True,
        "opens_orders": False,
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "methodology": "docs/STRATEGY_RESEARCH_ROADMAP.md STRAT-01..STRAT-04",
        "split_lock_sha256": contract.lock_sha256,
        "splits": {
            "train": [str(contract.train_start), str(contract.train_end)],
            "validation": [str(contract.val_start), str(contract.val_end)],
            "final_oos": [str(contract.oos_start), str(contract.oos_end)],
        },
        "risk_per_trade": 0.005,
        "total_trials_counted": n_trials,
        "trial_log_entries": len(trial_log),
        "gates_spec": GATES_SPEC,
        "cscv_pbo_full_panel": pbo_full,
        "final_oos_opened": oos_opened,
        "oos_contamination_statement": contamination_statement,
        "shortlist_size": len(shortlist),
        "candidates": candidates,
        "edge_demonstrated": edge_demonstrated,
    }
    out = ROOT / "data" / "edge_research_report.json"
    write_json_atomic(out, report)
    print("\n" + "=" * 70)
    print(f"edge_demonstrated = {edge_demonstrated}")
    print(f"report -> {out} ({time.time() - t0:.1f}s)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
