"""STRAT-03 (part 1) runner — robust selection WITHOUT touching final-OOS.

Usage:
    python trading_bot/run_edge_research_phase3.py

Selection rule (objective, declared here before execution):
  1. Eligibility on validation (realistic scenario, pooled 5 assets):
       trades >= 40, profit_factor > 1.0, max_drawdown_pct <= 20,
       sum_net_R > 0, and train sum_net_R > 0 (cross-split consistency).
  2. Rank eligible configs by validation sum_net_R, descending.
  3. Walk down the ranking; a config enters the shortlist only if it also
     passes the parameter-plateau check (every declared grid neighbour has
     validation sum_net_R > 0) and the walk-forward stability check
     (>= 50% of the 4 contiguous folds positive).
  4. Stop at 3 configs or when the ranking is exhausted.

Additional diagnostics for every shortlisted config:
  - Deflated Sharpe Ratio counting ALL distinct configurations in the
    persistent trial log as trials.
  - Probability of Backtest Overfitting via CSCV (S=16 blocks) over the
    full 36-config panel.
  - Conservative and severe cost scenario re-runs on validation.
  - Temporal concentration (per-quarter contribution, best-month-removed).

Diagnostic-only: no orders, no exchange access, no final-OOS access.
"""
from __future__ import annotations

import itertools
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from trading_bot.research.edge_lab import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEFAULT_RESEARCH_DIR,
    SplitContract,
    TradeEvent,
    append_trial,
    compute_metrics,
    portfolio_replay,
    read_trial_log,
    write_json_atomic,
)
from trading_bot.research.hypotheses import all_configs  # noqa: E402

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False

PHASE = "STRAT-03"
N_FOLDS = 4
CSCV_BLOCKS = 16
MAX_SHORTLIST = 3

ELIG_MIN_TRADES = 40
ELIG_MAX_DD = 20.0


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Acklam's inverse normal CDF approximation (sufficient accuracy)."""
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def deflated_sharpe(
    net_r: Sequence[float], n_trials: int
) -> Dict[str, Optional[float]]:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    Uses the per-trade net-R series; the benchmark SR0 is the expected
    maximum Sharpe under the null across *n_trials* independent trials.
    """
    x = np.asarray(list(net_r), dtype=float)
    t = x.size
    if t < 10:
        return {"sharpe": None, "sr0": None, "dsr_probability": None, "n_obs": t,
                "n_trials": n_trials}
    mu, sd = float(x.mean()), float(x.std(ddof=1))
    if sd <= 0:
        return {"sharpe": None, "sr0": None, "dsr_probability": None, "n_obs": t,
                "n_trials": n_trials}
    sr = mu / sd
    z = (x - x.mean()) / x.std(ddof=0)
    skew = float((z ** 3).mean())
    kurt = float((z ** 4).mean())

    gamma = 0.5772156649015329
    n = max(2, int(n_trials))
    e = math.e
    sr_var = 1.0  # variance proxy of SR estimates across trials (null, unit)
    sr0 = math.sqrt(sr_var / (t - 1)) * (
        (1 - gamma) * _norm_ppf(1 - 1.0 / n) + gamma * _norm_ppf(1 - 1.0 / (n * e))
    )
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        return {"sharpe": sr, "sr0": sr0, "dsr_probability": None, "n_obs": t,
                "n_trials": n, "note": "non-normal correction denominator <= 0"}
    dsr = _norm_cdf((sr - sr0) * math.sqrt(t - 1) / math.sqrt(denom))
    return {"sharpe": sr, "sr0": sr0, "dsr_probability": dsr, "n_obs": t,
            "n_trials": n, "skew": skew, "kurtosis": kurt}


def cscv_pbo(returns_matrix: np.ndarray, n_blocks: int = CSCV_BLOCKS) -> Dict[str, Any]:
    """Probability of Backtest Overfitting via CSCV (Bailey et al.).

    returns_matrix: (n_periods, n_configs) per-period returns (net R sums).
    Splits periods into n_blocks contiguous blocks; for every C(S, S/2)
    in-sample block combination, picks the IS-best config and records its
    out-of-sample relative rank. PBO = share of combinations where the
    IS-best config is below the OOS median (logit < 0).
    """
    n_periods, n_cfg = returns_matrix.shape
    if n_periods < n_blocks or n_cfg < 2:
        return {"pbo": None, "n_combinations": 0,
                "note": "insufficient periods/configs for CSCV"}
    blocks = np.array_split(np.arange(n_periods), n_blocks)
    half = n_blocks // 2
    logits: List[float] = []
    below = 0
    combos = list(itertools.combinations(range(n_blocks), half))
    for combo in combos:
        is_idx = np.concatenate([blocks[i] for i in combo])
        oos_idx = np.concatenate([blocks[i] for i in range(n_blocks) if i not in combo])
        is_perf = returns_matrix[is_idx].sum(axis=0)
        oos_perf = returns_matrix[oos_idx].sum(axis=0)
        best = int(np.argmax(is_perf))
        # relative OOS rank of the IS-best config (0..1, higher = better)
        rank = (oos_perf < oos_perf[best]).sum() + 0.5 * (
            (oos_perf == oos_perf[best]).sum() - 1
        )
        omega = (rank + 0.5) / n_cfg
        omega = min(max(omega, 1e-9), 1 - 1e-9)
        lam = math.log(omega / (1 - omega))
        logits.append(lam)
        if lam < 0:
            below += 1
    return {
        "pbo": below / len(combos),
        "n_combinations": len(combos),
        "n_blocks": n_blocks,
        "mean_logit": float(np.mean(logits)),
    }


# ---------------------------------------------------------------------------
# Event store access
# ---------------------------------------------------------------------------

def load_events(research_dir: Path, config_id: str) -> Tuple[Dict[str, Any], List[TradeEvent]]:
    p = research_dir / "events" / f"{config_id}_train_val.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    events = [TradeEvent(**e) for e in payload["events"]]
    return payload, events


def view_by_signal(events: List[TradeEvent], start: str, end: str) -> List[TradeEvent]:
    return [e for e in events if start <= e.signal_time < end]


# ---------------------------------------------------------------------------
# Neighbour map for plateau checks
# ---------------------------------------------------------------------------

_GRID_AXES = {
    "volatility_breakout": {
        "lookback_bars_15m": [96, 192, 288],
        "squeeze_pmax": [0.5, 1.0],
        "stop_atr_mult": [2.0, 3.0],   # paired with trail in the grid
    },
    "trend_pullback": {
        "ref_ema": ["ema20", "ema50"],
        "stop_atr_mult": [1.5, 2.5],
        "target_rr": [1.5, 2.0, 3.0],
    },
    "xs_momentum": {
        "formation_days": [3, 7, 14],
        "hold_days": [1, 3],
        "mode": ["long_short", "long_only"],
    },
}


def grid_neighbours(cfg_row: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[str]:
    """Configs of the same family differing by exactly one axis step."""
    fam = cfg_row["family"]
    axes = _GRID_AXES[fam]
    me = cfg_row["params"]
    out = []
    for other in rows:
        if other["family"] != fam or other["config_id"] == cfg_row["config_id"]:
            continue
        diffs = []
        for ax, values in axes.items():
            if me.get(ax) != other["params"].get(ax):
                try:
                    da = abs(values.index(me.get(ax)) - values.index(other["params"].get(ax)))
                except ValueError:
                    da = 99
                diffs.append((ax, da))
        ignored_equal = all(
            me.get(k) == other["params"].get(k)
            for k in me
            if k not in axes and k != "trail_atr_mult"
        )
        if len(diffs) == 1 and diffs[0][1] == 1 and ignored_equal:
            out.append(other["config_id"])
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    t0 = time.time()
    research_dir = ROOT / DEFAULT_RESEARCH_DIR
    cache_dir = ROOT / DEFAULT_CACHE_DIR
    contract = SplitContract.load(cache_dir)

    phase2 = json.loads(
        (research_dir / "phase2_report.json").read_text(encoding="utf-8")
    )
    rows: List[Dict[str, Any]] = []
    for fam in phase2["families"].values():
        rows.extend(fam["configs"])
    print(f"[load] {len(rows)} phase-2 config results")

    trial_log = read_trial_log(research_dir)
    n_trials = len({t["config_id"] for t in trial_log})
    print(f"[trials] distinct configurations counted for DSR: {n_trials}")

    # ------------------------------------------------------------------
    # CSCV / PBO over the FULL config panel (train+val, weekly blocks)
    # ------------------------------------------------------------------
    tv_start, tv_end = str(contract.train_start), str(contract.oos_start)
    weeks = pd.date_range(contract.train_start, contract.oos_start, freq="7D", tz="UTC")
    cfg_ids = [r["config_id"] for r in rows]
    matrix = np.zeros((len(weeks) - 1, len(cfg_ids)))
    replayed_cache: Dict[str, List] = {}
    for ci, cid in enumerate(cfg_ids):
        _, events = load_events(research_dir, cid)
        trades = portfolio_replay(
            view_by_signal(events, tv_start, tv_end), scenario="realistic"
        )
        replayed_cache[cid] = trades
        if not trades:
            continue
        times = pd.to_datetime([t.event.exit_time for t in trades], utc=True)
        rsum = np.array([t.net_R for t in trades])
        idx = np.searchsorted(weeks, times, side="right") - 1
        for k, r in zip(idx, rsum):
            if 0 <= k < matrix.shape[0]:
                matrix[k, ci] += r
    pbo_res = cscv_pbo(matrix)
    print(f"[cscv] PBO={pbo_res['pbo']} over {pbo_res['n_combinations']} combinations")

    # ------------------------------------------------------------------
    # Eligibility + ranking on validation only
    # ------------------------------------------------------------------
    def eligible(r: Dict[str, Any]) -> Tuple[bool, str]:
        v, tr = r["validation"], r["train"]
        if v["trades"] < ELIG_MIN_TRADES:
            return False, f"val trades {v['trades']} < {ELIG_MIN_TRADES}"
        if v["profit_factor"] is None or v["profit_factor"] <= 1.0:
            return False, f"val PF {v['profit_factor']} <= 1.0"
        if v["max_drawdown_pct"] > ELIG_MAX_DD:
            return False, f"val DD {v['max_drawdown_pct']:.1f}% > {ELIG_MAX_DD}%"
        if v["sum_net_R"] <= 0:
            return False, f"val sum_net_R {v['sum_net_R']:.1f} <= 0"
        if tr["sum_net_R"] <= 0:
            return False, f"train sum_net_R {tr['sum_net_R']:.1f} <= 0 (inconsistent)"
        return True, "OK"

    eligibility = {}
    ranked = []
    for r in rows:
        ok, reason = eligible(r)
        eligibility[r["config_id"]] = {"eligible": ok, "reason": reason}
        if ok:
            ranked.append(r)
    ranked.sort(key=lambda r: r["validation"]["sum_net_R"], reverse=True)
    print(f"[rank] eligible configs: {len(ranked)}")

    # ------------------------------------------------------------------
    # Fold boundaries for walk-forward stability
    # ------------------------------------------------------------------
    fold_edges = pd.date_range(
        contract.train_start, contract.oos_start, periods=N_FOLDS + 1, tz="UTC"
    )

    def walk_forward(cid: str) -> Dict[str, Any]:
        _, events = load_events(research_dir, cid)
        folds = []
        for i in range(N_FOLDS):
            view = view_by_signal(events, str(fold_edges[i]), str(fold_edges[i + 1]))
            trades = portfolio_replay(view, scenario="realistic")
            m = compute_metrics(trades)
            folds.append(
                {
                    "fold": i + 1,
                    "window": [str(fold_edges[i]), str(fold_edges[i + 1])],
                    "trades": m["trades"],
                    "sum_net_R": m["sum_net_R"],
                    "profit_factor": m["profit_factor"],
                }
            )
        positives = sum(1 for f in folds if f["sum_net_R"] > 0)
        return {
            "folds": folds,
            "positive_folds": positives,
            "pass": positives >= math.ceil(N_FOLDS / 2),
        }

    def plateau(r: Dict[str, Any]) -> Dict[str, Any]:
        neigh = grid_neighbours(r, rows)
        detail = []
        ok = True
        for nid in neigh:
            nrow = next(x for x in rows if x["config_id"] == nid)
            nv = nrow["validation"]["sum_net_R"]
            detail.append({"config_id": nid, "val_sum_net_R": nv})
            if nv <= 0:
                ok = False
        return {"neighbours": detail, "pass": ok and len(neigh) > 0}

    def concentration(cid: str) -> Dict[str, Any]:
        trades = replayed_cache[cid]
        view = [t for t in trades if t.event.signal_time >= str(contract.val_start)]
        if not view:
            return {"note": "no validation trades"}
        df = pd.DataFrame(
            {
                "month": [str(t.event.exit_time)[:7] for t in view],
                "quarter": [
                    f"{pd.Timestamp(t.event.exit_time).year}Q{pd.Timestamp(t.event.exit_time).quarter}"
                    for t in view
                ],
                "net_R": [t.net_R for t in view],
            }
        )
        by_month = df.groupby("month")["net_R"].sum().sort_values(ascending=False)
        total = df["net_R"].sum()
        without_best_month = total - by_month.iloc[0]
        return {
            "total_net_R": float(total),
            "best_month": by_month.index[0],
            "best_month_net_R": float(by_month.iloc[0]),
            "net_R_without_best_month": float(without_best_month),
            "by_quarter": df.groupby("quarter")["net_R"].sum().round(2).to_dict(),
            "pass_best_month_removed_positive": bool(without_best_month > 0),
        }

    # ------------------------------------------------------------------
    # Build the shortlist
    # ------------------------------------------------------------------
    shortlist: List[Dict[str, Any]] = []
    audit_trail: List[Dict[str, Any]] = []
    for r in ranked:
        if len(shortlist) >= MAX_SHORTLIST:
            break
        cid = r["config_id"]
        wf = walk_forward(cid)
        pl = plateau(r)
        entry_audit = {
            "config_id": cid,
            "val_sum_net_R": r["validation"]["sum_net_R"],
            "walk_forward_pass": wf["pass"],
            "plateau_pass": pl["pass"],
        }
        if not wf["pass"]:
            entry_audit["excluded"] = "walk-forward instability"
            audit_trail.append(entry_audit)
            continue
        if not pl["pass"]:
            entry_audit["excluded"] = "isolated optimum (plateau check failed)"
            audit_trail.append(entry_audit)
            continue

        # scenario stress on validation
        _, events = load_events(research_dir, cid)
        val_view = view_by_signal(events, str(contract.val_start), str(contract.oos_start))
        scen_metrics = {}
        for sc in ("conservative", "severe"):
            trades = portfolio_replay(val_view, scenario=sc)
            m = compute_metrics(trades)
            scen_metrics[sc] = m
            append_trial(
                research_dir,
                {
                    "phase": PHASE,
                    "config_id": cid,
                    "family": r["family"],
                    "params": r["params"],
                    "split": "validation",
                    "scenario": sc,
                    "split_lock_sha256": contract.lock_sha256,
                    "metrics": m,
                },
            )

        dsr = deflated_sharpe(
            [t.net_R for t in portfolio_replay(val_view, scenario="realistic")],
            n_trials=n_trials,
        )
        conc = concentration(cid)
        entry_audit["selected"] = True
        audit_trail.append(entry_audit)
        shortlist.append(
            {
                "config_id": cid,
                "family": r["family"],
                "params": r["params"],
                "validation_realistic": r["validation"],
                "validation_scenarios": scen_metrics,
                "walk_forward": wf,
                "plateau": pl,
                "dsr_validation": dsr,
                "temporal_concentration_validation": conc,
            }
        )
        print(
            f"[shortlist] {cid} selected "
            f"(val_R={r['validation']['sum_net_R']:+.1f}, "
            f"severe_R={scen_metrics['severe']['sum_net_R']:+.1f}, "
            f"DSR={dsr.get('dsr_probability')})"
        )

    report = {
        "report_type": "strat03_selection_report",
        "diagnostic_only": True,
        "opens_orders": False,
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "split_lock_sha256": contract.lock_sha256,
        "final_oos_accessed": False,
        "n_trials_counted": n_trials,
        "selection_rule": (
            "validation-only ranking by sum_net_R with eligibility "
            f"(trades>={ELIG_MIN_TRADES}, PF>1.0, DD<={ELIG_MAX_DD}%, "
            "train consistency), plateau and walk-forward required"
        ),
        "cscv_pbo_full_panel": pbo_res,
        "eligibility": eligibility,
        "ranking_audit": audit_trail,
        "shortlist": shortlist,
    }
    out = research_dir / "phase3_report.json"
    write_json_atomic(out, report)
    print(f"\n[done] shortlist size: {len(shortlist)} in {time.time() - t0:.1f}s")
    print(f"[done] report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
