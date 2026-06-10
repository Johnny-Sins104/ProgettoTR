"""Cycle-2 STRAT-03 (part 1) — robust selection with regime stratification.

Usage:
    python trading_bot/run_edge_research_c2_phase3.py

Selection rule (objective, declared here before execution):
  1. Eligibility on validation (realistic, pooled panel):
       trades >= 40, PF > 1.0, max DD <= 20%, sum_net_R > 0,
       train sum_net_R > 0, AND the NEW regime gate: net-positive
       (sum_net_R > 0) in at least 2 distinct regimes among
       bull/bear/chop, counting only regimes with >= 10 validation
       trades for this config.
  2. Rank eligible configs by validation sum_net_R, descending.
  3. Shortlist entry additionally requires the parameter-plateau check
     and the 4-fold walk-forward stability check (>= 2 folds positive).
  4. Stop at 3 configs.

DSR counts the CUMULATIVE trial log (cycle 1 + cycle 2 distinct
configurations). PBO via CSCV over the 48-config cycle-2 panel.
Diagnostic-only. No final-OOS access.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from trading_bot.research.edge_lab import (  # noqa: E402
    SplitContract,
    TradeEvent,
    append_trial,
    compute_metrics,
    portfolio_replay,
    read_trial_log,
    write_json_atomic,
)
from trading_bot.run_edge_research_phase3 import (  # noqa: E402
    cscv_pbo,
    deflated_sharpe,
)

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False

PHASE = "C2-STRAT-03"
CYCLE = 2
N_FOLDS = 4
MAX_SHORTLIST = 3
ELIG_MIN_TRADES = 40
ELIG_MAX_DD = 20.0
REGIME_MIN_TRADES = 10
REGIME_MIN_POSITIVE = 2

C2_CACHE = ROOT / "data" / "strat02_cache"
C2_LOCK = "strat02_temporal_splits.json"
C2_RESEARCH = ROOT / "data" / "edge_research2"
TRIAL_LOG_DIR = ROOT / "data" / "edge_research"

_GRID_AXES_C2 = {
    "volatility_breakout_c2": {
        "lookback_bars_15m": [96, 192, 288],
        "ema_alignment": [True, False],
        "stop_atr_mult": [2.0, 3.0],
    },
    "trend_pullback_c2": {
        "ref_ema": ["ema20", "ema50"],
        "stop_atr_mult": [1.5, 2.5],
        "target_rr": [1.5, 2.0, 3.0],
    },
    "xs_momentum_c2": {
        "formation_days": [3, 7, 14],
        "hold_days": [1, 3],
        "mode": ["long_short", "long_only"],
    },
    "xs_momentum_regime_c2": {
        "formation_days": [3, 7, 14],
        "hold_days": [1, 3],
        "regime_rule": ["bull_only", "not_bear"],
    },
}


def grid_neighbours_c2(cfg_row: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[str]:
    fam = cfg_row["family"]
    axes = _GRID_AXES_C2[fam]
    me = cfg_row["params"]
    out = []
    for other in rows:
        if other["family"] != fam or other["config_id"] == cfg_row["config_id"]:
            continue
        diffs = 0
        step_ok = True
        for ax, values in axes.items():
            if me.get(ax) != other["params"].get(ax):
                diffs += 1
                try:
                    if abs(values.index(me.get(ax)) - values.index(other["params"].get(ax))) != 1:
                        step_ok = False
                except ValueError:
                    step_ok = False
        ignored_equal = all(
            me.get(k) == other["params"].get(k)
            for k in me
            if k not in axes and k != "trail_atr_mult"
        )
        if diffs == 1 and step_ok and ignored_equal:
            out.append(other["config_id"])
    return out


def load_events_c2(config_id: str) -> List[TradeEvent]:
    p = C2_RESEARCH / "events" / f"{config_id}_train_val.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    return [TradeEvent(**e) for e in payload["events"]]


def view_by_signal(events: List[TradeEvent], start: str, end: str) -> List[TradeEvent]:
    return [e for e in events if start <= e.signal_time < end]


def regime_positive_count(metrics: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    by_regime = metrics.get("by_regime") or {}
    detail = {}
    positives = 0
    for reg in ("bull", "bear", "chop"):
        d = by_regime.get(reg)
        if not d or d["trades"] < REGIME_MIN_TRADES:
            detail[reg] = {"counted": False, **(d or {})}
            continue
        ok = d["sum_net_R"] > 0
        positives += int(ok)
        detail[reg] = {"counted": True, "positive": ok, **d}
    return positives, detail


def main() -> int:
    t0 = time.time()
    contract = SplitContract.load(C2_CACHE, lock_name=C2_LOCK)
    phase2 = json.loads((C2_RESEARCH / "phase2_report.json").read_text(encoding="utf-8"))
    rows: List[Dict[str, Any]] = []
    for fam in phase2["families"].values():
        rows.extend(fam["configs"])
    print(f"[load] {len(rows)} cycle-2 config results")

    trial_log = read_trial_log(TRIAL_LOG_DIR)
    n_trials = len({t["config_id"] for t in trial_log})
    print(f"[trials] CUMULATIVE distinct configurations (cycle1+cycle2): {n_trials}")

    # CSCV/PBO over the cycle-2 panel
    tv_start, tv_end = str(contract.train_start), str(contract.oos_start)
    weeks = pd.date_range(contract.train_start, contract.oos_start, freq="7D", tz="UTC")
    cfg_ids = [r["config_id"] for r in rows]
    matrix = np.zeros((len(weeks) - 1, len(cfg_ids)))
    for ci, cid in enumerate(cfg_ids):
        events = load_events_c2(cid)
        trades = portfolio_replay(
            view_by_signal(events, tv_start, tv_end), scenario="realistic"
        )
        if not trades:
            continue
        times = pd.to_datetime([t.event.exit_time for t in trades], utc=True)
        idx = np.searchsorted(weeks, times, side="right") - 1
        for k, r in zip(idx, [t.net_R for t in trades]):
            if 0 <= k < matrix.shape[0]:
                matrix[k, ci] += r
    pbo_res = cscv_pbo(matrix)
    print(f"[cscv] PBO={pbo_res['pbo']} over {pbo_res['n_combinations']} combinations")

    # Eligibility incl. the NEW regime gate
    eligibility = {}
    ranked = []
    for r in rows:
        v, tr = r["validation"], r["train"]
        reasons = []
        if v["trades"] < ELIG_MIN_TRADES:
            reasons.append(f"val trades {v['trades']} < {ELIG_MIN_TRADES}")
        if v["profit_factor"] is None or v["profit_factor"] <= 1.0:
            reasons.append(f"val PF {v['profit_factor']} <= 1.0")
        if v["max_drawdown_pct"] > ELIG_MAX_DD:
            reasons.append(f"val DD {v['max_drawdown_pct']:.1f}% > {ELIG_MAX_DD}%")
        if v["sum_net_R"] <= 0:
            reasons.append("val sum_net_R <= 0")
        if tr["sum_net_R"] <= 0:
            reasons.append("train sum_net_R <= 0")
        pos, regime_detail = regime_positive_count(v)
        if pos < REGIME_MIN_POSITIVE:
            reasons.append(
                f"regime gate: positive in {pos} regime(s) "
                f"(need >= {REGIME_MIN_POSITIVE} with >= {REGIME_MIN_TRADES} trades)"
            )
        eligibility[r["config_id"]] = {
            "eligible": not reasons,
            "reasons": reasons or ["OK"],
            "regimes_positive": pos,
            "regime_detail": regime_detail,
        }
        if not reasons:
            ranked.append(r)
    ranked.sort(key=lambda r: r["validation"]["sum_net_R"], reverse=True)
    print(f"[rank] eligible configs after regime gate: {len(ranked)}")

    fold_edges = pd.date_range(
        contract.train_start, contract.oos_start, periods=N_FOLDS + 1, tz="UTC"
    )

    def walk_forward(cid: str) -> Dict[str, Any]:
        events = load_events_c2(cid)
        folds = []
        for i in range(N_FOLDS):
            view = view_by_signal(events, str(fold_edges[i]), str(fold_edges[i + 1]))
            m = compute_metrics(portfolio_replay(view, scenario="realistic"))
            folds.append(
                {"fold": i + 1, "window": [str(fold_edges[i]), str(fold_edges[i + 1])],
                 "trades": m["trades"], "sum_net_R": m["sum_net_R"],
                 "profit_factor": m["profit_factor"]}
            )
        positives = sum(1 for f in folds if f["sum_net_R"] > 0)
        return {"folds": folds, "positive_folds": positives,
                "pass": positives >= math.ceil(N_FOLDS / 2)}

    shortlist: List[Dict[str, Any]] = []
    audit_trail: List[Dict[str, Any]] = []
    for r in ranked:
        if len(shortlist) >= MAX_SHORTLIST:
            break
        cid = r["config_id"]
        wf = walk_forward(cid)
        neigh_ids = grid_neighbours_c2(r, rows)
        neigh_detail = []
        plateau_ok = len(neigh_ids) > 0
        for nid in neigh_ids:
            nrow = next(x for x in rows if x["config_id"] == nid)
            nv = nrow["validation"]["sum_net_R"]
            neigh_detail.append({"config_id": nid, "val_sum_net_R": nv})
            if nv <= 0:
                plateau_ok = False
        audit = {
            "config_id": cid,
            "val_sum_net_R": r["validation"]["sum_net_R"],
            "walk_forward_pass": wf["pass"],
            "plateau_pass": plateau_ok,
        }
        if not wf["pass"]:
            audit["excluded"] = "walk-forward instability"
            audit_trail.append(audit)
            continue
        if not plateau_ok:
            audit["excluded"] = "isolated optimum (plateau check failed)"
            audit_trail.append(audit)
            continue

        events = load_events_c2(cid)
        val_view = view_by_signal(events, str(contract.val_start), str(contract.oos_start))
        scen_metrics = {}
        for sc in ("conservative", "severe"):
            m = compute_metrics(portfolio_replay(val_view, scenario=sc))
            scen_metrics[sc] = m
            append_trial(
                TRIAL_LOG_DIR,
                {"phase": PHASE, "cycle": CYCLE, "config_id": cid,
                 "family": r["family"], "params": r["params"],
                 "split": "validation", "scenario": sc,
                 "split_lock_sha256": contract.lock_sha256, "metrics": m},
            )
        dsr = deflated_sharpe(
            [t.net_R for t in portfolio_replay(val_view, scenario="realistic")],
            n_trials=n_trials,
        )
        audit["selected"] = True
        audit_trail.append(audit)
        shortlist.append(
            {
                "config_id": cid,
                "family": r["family"],
                "params": r["params"],
                "validation_realistic": r["validation"],
                "validation_scenarios": scen_metrics,
                "walk_forward": wf,
                "plateau": {"neighbours": neigh_detail, "pass": plateau_ok},
                "dsr_validation": dsr,
                "regime_detail_validation": eligibility[cid]["regime_detail"],
            }
        )
        print(
            f"[shortlist] {cid} selected "
            f"(val_R={r['validation']['sum_net_R']:+.1f}, "
            f"severe_R={scen_metrics['severe']['sum_net_R']:+.1f}, "
            f"DSR={dsr.get('dsr_probability')}, "
            f"regimes+={eligibility[cid]['regimes_positive']})"
        )

    report = {
        "report_type": "c2_strat03_selection_report",
        "diagnostic_only": True,
        "opens_orders": False,
        "cycle": CYCLE,
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "split_lock_sha256": contract.lock_sha256,
        "final_oos_accessed": False,
        "n_trials_counted_cumulative": n_trials,
        "selection_rule": (
            f"validation-only ranking with eligibility (trades>={ELIG_MIN_TRADES}, "
            f"PF>1.0, DD<={ELIG_MAX_DD}%, train consistency) PLUS regime gate "
            f"(net-positive in >= {REGIME_MIN_POSITIVE} regimes with >= "
            f"{REGIME_MIN_TRADES} trades), then plateau and walk-forward"
        ),
        "cscv_pbo_c2_panel": pbo_res,
        "eligibility": eligibility,
        "ranking_audit": audit_trail,
        "shortlist": shortlist,
    }
    out = C2_RESEARCH / "phase3_report.json"
    write_json_atomic(out, report)
    print(f"\n[done] shortlist size: {len(shortlist)} in {time.time() - t0:.1f}s -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
