"""STRAT-02 runner — evaluate the three declared hypothesis families.

Usage:
    python trading_bot/run_edge_research_phase2.py

Contract enforced here:
- The final-OOS region is removed from every frame before any computation
  (fail-closed guard; contaminated rows raise OOSContaminationError).
- All 36 configurations are declared (with rationale) and written to
  data/edge_research/hypotheses_declaration.json BEFORE any validation
  metric is computed. The declaration file is immutable once written.
- Every configuration evaluation is appended to the persistent trial log,
  regardless of outcome.
- Costs: UnifiedCostModel scenario 'realistic'; risk fixed at 0.005.

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
    guard_no_oos,
    load_asset_frames,
    portfolio_replay,
    write_json_atomic,
)
from trading_bot.research.hypotheses import (  # noqa: E402
    all_configs,
    specs_for,
    xs_events,
)

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False

PHASE = "STRAT-02"
SCENARIO = "realistic"


def _split_view(events: List, boundary: pd.Timestamp, which: str) -> List:
    """A trade belongs to the split in which its SIGNAL fired."""
    b = str(boundary)
    if which == "train":
        return [e for e in events if e.signal_time < b]
    return [e for e in events if e.signal_time >= b]


def main() -> int:
    t0 = time.time()
    research_dir = ROOT / DEFAULT_RESEARCH_DIR
    cache_dir = ROOT / DEFAULT_CACHE_DIR
    contract = SplitContract.load(cache_dir)

    print("=" * 70)
    print("STRAT-02 — hypothesis family evaluation (train / validation only)")
    print(f"  split lock hash : {contract.lock_sha256[:16]}")
    print(f"  train      : {contract.train_start} -> {contract.train_end}")
    print(f"  validation : {contract.val_start} -> {contract.val_end}")
    print(f"  final-OOS  : SEALED (guard active, never loaded here)")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Declaration BEFORE evaluation (immutable once written)
    # ------------------------------------------------------------------
    configs = all_configs()
    decl_path = research_dir / "hypotheses_declaration.json"
    if decl_path.exists():
        existing = json.loads(decl_path.read_text(encoding="utf-8"))
        declared_ids = {c["config_id"] for c in existing["configs"]}
        current_ids = {c.config_id for c in configs}
        if declared_ids != current_ids:
            raise RuntimeError(
                "hypotheses_declaration.json exists but does not match the "
                "code-declared grids. Adding/changing configs after "
                "declaration is forbidden."
            )
        print(f"[decl] declaration already frozen ({len(declared_ids)} configs)")
    else:
        write_json_atomic(
            decl_path,
            {
                "declared_at_utc": pd.Timestamp.utcnow().isoformat(),
                "split_lock_sha256": contract.lock_sha256,
                "risk_per_trade": 0.005,
                "cost_scenario_default": SCENARIO,
                "n_configs": len(configs),
                "configs": [c.to_dict() for c in configs],
            },
        )
        print(f"[decl] froze {len(configs)} configurations -> {decl_path}")

    # ------------------------------------------------------------------
    # 2. Load frames, seal OOS
    # ------------------------------------------------------------------
    frames15: Dict[str, pd.DataFrame] = {}
    executors: Dict[str, CausalExecutor] = {}
    bars_by_split: Dict[str, Dict[str, int]] = {"train": {}, "validation": {}}
    for asset in ASSETS:
        df15, df5 = load_asset_frames(asset, cache_dir)
        df15 = guard_no_oos(df15, contract, PHASE)
        df5 = guard_no_oos(df5, contract, PHASE)
        frames15[asset] = df15
        executors[asset] = CausalExecutor(df15, df5)
        dt = df15["datetime"]
        bars_by_split["train"][asset] = int(
            ((dt >= contract.train_start) & (dt < contract.val_start)).sum()
        )
        bars_by_split["validation"][asset] = int(
            ((dt >= contract.val_start) & (dt < contract.oos_start)).sum()
        )
        print(
            f"[data] {asset}: 15m rows={len(df15)} 5m rows guarded, "
            f"oos rows dropped={df15.attrs.get('oos_rows_dropped')}"
        )

    events_dir = research_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 3. Evaluate every config on train+val window; split views by signal
    # ------------------------------------------------------------------
    results: List[Dict[str, Any]] = []
    for cfg in configs:
        events = []
        n_signals = 0
        if cfg.family == "xs_momentum":
            events = xs_events(
                frames15, executors, cfg, contract.train_start, contract.oos_start
            )
            n_signals = len(events)
        else:
            for asset in ASSETS:
                specs = specs_for(cfg, frames15[asset])
                n_signals += len(
                    [
                        s
                        for s in specs
                        if contract.train_start
                        <= frames15[asset]["datetime"].iloc[s.idx15]
                        < contract.oos_start
                    ]
                )
                events.extend(
                    executors[asset].run(
                        specs,
                        family=cfg.family,
                        config_id=cfg.config_id,
                        asset=asset,
                        window_start=contract.train_start,
                        window_end=contract.oos_start,
                    )
                )
        events.sort(key=lambda e: e.entry_time)

        # persist raw events for phase-3 reuse (scenario re-replays, folds)
        write_json_atomic(
            events_dir / f"{cfg.config_id}_train_val.json",
            {
                "config_id": cfg.config_id,
                "family": cfg.family,
                "config_hash": config_hash({"family": cfg.family, **cfg.params}),
                "window": [str(contract.train_start), str(contract.oos_start)],
                "n_signals_window": n_signals,
                "events": [e.to_dict() for e in events],
            },
        )

        row: Dict[str, Any] = {
            "config_id": cfg.config_id,
            "family": cfg.family,
            "params": cfg.params,
            "n_signals_train_val": n_signals,
        }
        for split in ("train", "validation"):
            view = _split_view(events, contract.val_start, split)
            trades = portfolio_replay(view, scenario=SCENARIO)
            bars = sum(bars_by_split[split].values())
            m = compute_metrics(
                trades, bars_in_window_15m=bars, n_signals=len(view)
            )
            per_asset = {}
            for asset in ASSETS:
                a_trades = [t for t in trades if t.event.asset == asset]
                per_asset[asset] = compute_metrics(
                    a_trades,
                    bars_in_window_15m=bars_by_split[split][asset],
                    n_signals=len([e for e in view if e.asset == asset]),
                )
            row[split] = m
            row[f"{split}_per_asset"] = per_asset

            append_trial(
                research_dir,
                {
                    "phase": PHASE,
                    "config_id": cfg.config_id,
                    "family": cfg.family,
                    "config_hash": config_hash({"family": cfg.family, **cfg.params}),
                    "params": cfg.params,
                    "split": split,
                    "scenario": SCENARIO,
                    "split_lock_sha256": contract.lock_sha256,
                    "metrics": m,
                },
            )

        v = row["validation"]
        pf = v["profit_factor"]
        print(
            f"[eval] {cfg.config_id} ({cfg.family[:18]:<18}) "
            f"train_R={row['train']['sum_net_R']:+8.1f} "
            f"val_R={v['sum_net_R']:+8.1f} val_PF={pf if pf is None else round(pf, 3)} "
            f"val_trades={v['trades']}"
        )
        results.append(row)

    # ------------------------------------------------------------------
    # 4. Family reports
    # ------------------------------------------------------------------
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for row in results:
        by_family.setdefault(row["family"], []).append(row)

    report = {
        "report_type": "strat02_family_report",
        "diagnostic_only": True,
        "opens_orders": False,
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "scenario": SCENARIO,
        "risk_per_trade": 0.005,
        "split_lock_sha256": contract.lock_sha256,
        "final_oos_accessed": False,
        "n_configs_evaluated": len(results),
        "families": {
            fam: {
                "n_configs": len(rows),
                "configs": rows,
            }
            for fam, rows in by_family.items()
        },
    }
    out_path = research_dir / "phase2_report.json"
    write_json_atomic(out_path, report)
    print(f"\n[done] {len(results)} configs evaluated in {time.time() - t0:.1f}s")
    print(f"[done] report -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
