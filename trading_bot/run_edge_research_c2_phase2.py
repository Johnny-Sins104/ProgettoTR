"""Cycle-2 STRAT-02 runner — four declared families on the 2019+ panel.

Usage:
    python trading_bot/run_edge_research_c2_phase2.py

Contract:
- final-OOS region physically removed before any computation (guard);
- 48 configurations declared and frozen BEFORE any validation metric,
  including the causal regime filter definition (counted as parameters);
- every evaluation appended to the CUMULATIVE trial log
  (data/edge_research/trial_log.jsonl) with cycle=2 — cycle-1 trials
  keep counting for DSR;
- scenario 'realistic', fixed 0.005 risk, costs at the 5m execution TF.

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
from trading_bot.research.hypotheses_c2 import (  # noqa: E402
    all_c2_configs,
    c2_specs_for,
    is_panel_family,
    xs_events_panel,
)
from trading_bot.research.regime import daily_regime_labels, regime_for_times  # noqa: E402

DIAGNOSTIC_ONLY = True
OPENS_ORDERS = False

PHASE = "C2-STRAT-02"
SCENARIO = "realistic"
CYCLE = 2

C2_CACHE = ROOT / "data" / "strat02_cache"
C2_LOCK = "strat02_temporal_splits.json"
C2_RESEARCH = ROOT / "data" / "edge_research2"
TRIAL_LOG_DIR = ROOT / "data" / "edge_research"   # cumulative, shared with cycle 1


def _split_view(events: List, boundary: pd.Timestamp, which: str) -> List:
    b = str(boundary)
    if which == "train":
        return [e for e in events if e.signal_time < b]
    return [e for e in events if e.signal_time >= b]


def main() -> int:
    t0 = time.time()
    contract = SplitContract.load(C2_CACHE, lock_name=C2_LOCK)
    panel_manifest = json.loads(
        (C2_CACHE / "strat02_panel_manifest.json").read_text(encoding="utf-8")
    )
    panel: List[str] = panel_manifest["panel_with_data"]

    print("=" * 70)
    print("C2 STRAT-02 — four families on the 2019+ broad panel")
    print(f"  panel ({len(panel)}): {', '.join(panel)}")
    print(f"  split lock hash : {contract.lock_sha256[:16]}")
    print(f"  train      : {contract.train_start} -> {contract.train_end}")
    print(f"  validation : {contract.val_start} -> {contract.val_end}")
    print(f"  final-OOS  : SEALED")
    print("=" * 70)

    configs = all_c2_configs()
    decl_path = C2_RESEARCH / "hypotheses_declaration_c2.json"
    if decl_path.exists():
        existing = json.loads(decl_path.read_text(encoding="utf-8"))
        if {c["config_id"] for c in existing["configs"]} != {c.config_id for c in configs}:
            raise RuntimeError(
                "cycle-2 declaration exists but does not match code grids — "
                "changing configs after declaration is forbidden"
            )
        print(f"[decl] declaration already frozen ({len(configs)} configs)")
    else:
        write_json_atomic(
            decl_path,
            {
                "declared_at_utc": pd.Timestamp.utcnow().isoformat(),
                "cycle": CYCLE,
                "split_lock_sha256": contract.lock_sha256,
                "risk_per_trade": 0.005,
                "cost_scenario_default": SCENARIO,
                "regime_filter_definition": (
                    "BTC daily SMA200 trend, causal at D-1 close: bull if "
                    "close>sma200 and sma200 rising over 20d; bear if "
                    "close<sma200 and sma200 falling; chop otherwise; "
                    "unknown if <221 daily closes. See research/regime.py."
                ),
                "cycle1_knowledge_statement": (
                    "Cycle-1 NO_CANDIDATE (regime dependence) motivated the new "
                    "XSR family and the regime-stratified gate, declared here a "
                    "priori. No cycle-2 configuration was selected or tuned from "
                    "cycle-1 validation/OOS metrics. Cycle-1 trials remain in "
                    "the cumulative trial log."
                ),
                "n_configs": len(configs),
                "configs": [c.to_dict() for c in configs],
            },
        )
        print(f"[decl] froze {len(configs)} configurations -> {decl_path}")

    # ------------------------------------------------------------------
    # Load frames, seal OOS
    # ------------------------------------------------------------------
    frames15: Dict[str, pd.DataFrame] = {}
    executors: Dict[str, CausalExecutor] = {}
    for asset in panel:
        df15, df5 = load_asset_frames(asset, C2_CACHE)
        df15 = guard_no_oos(df15, contract, PHASE)
        df5 = guard_no_oos(df5, contract, PHASE)
        frames15[asset] = df15
        executors[asset] = CausalExecutor(df15, df5)
        print(f"[data] {asset}: 15m rows={len(df15)} "
              f"(oos dropped={df15.attrs.get('oos_rows_dropped')})")

    daily_labels = daily_regime_labels(frames15["BTCUSDT"])

    bars_by_split: Dict[str, int] = {}
    for split, (a, b) in (
        ("train", (contract.train_start, contract.val_start)),
        ("validation", (contract.val_start, contract.oos_start)),
    ):
        bars_by_split[split] = sum(
            int(((df["datetime"] >= a) & (df["datetime"] < b)).sum())
            for df in frames15.values()
        )

    events_dir = C2_RESEARCH / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------
    results: List[Dict[str, Any]] = []
    for cfg in configs:
        tc = time.time()
        if is_panel_family(cfg):
            events = xs_events_panel(
                frames15, executors, cfg,
                contract.train_start, contract.oos_start,
                daily_labels=daily_labels,
            )
            n_signals = len(events)
        else:
            events = []
            n_signals = 0
            for asset in panel:
                specs = c2_specs_for(cfg, frames15[asset])
                t15 = frames15[asset]["datetime"]
                n_signals += sum(
                    1 for s in specs
                    if contract.train_start <= t15.iloc[s.idx15] < contract.oos_start
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

        write_json_atomic(
            events_dir / f"{cfg.config_id}_train_val.json",
            {
                "config_id": cfg.config_id,
                "family": cfg.family,
                "cycle": CYCLE,
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
            m = compute_metrics(
                trades, bars_in_window_15m=bars_by_split[split], n_signals=len(view)
            )
            # regime-stratified net R (by signal time, causal labels)
            if trades:
                regs = regime_for_times(
                    daily_labels,
                    pd.Series([t.event.signal_time for t in trades]),
                )
                by_regime: Dict[str, Dict[str, float]] = {}
                for r in ("bull", "bear", "chop", "unknown"):
                    sel = [t for t, g in zip(trades, regs) if g == r]
                    if sel:
                        by_regime[r] = {
                            "trades": len(sel),
                            "sum_net_R": float(sum(t.net_R for t in sel)),
                            "net_pnl": float(sum(t.net_pnl for t in sel)),
                        }
                m["by_regime"] = by_regime
            row[split] = m

            append_trial(
                TRIAL_LOG_DIR,
                {
                    "phase": PHASE,
                    "cycle": CYCLE,
                    "config_id": cfg.config_id,
                    "family": cfg.family,
                    "config_hash": config_hash({"family": cfg.family, **cfg.params}),
                    "params": cfg.params,
                    "split": split,
                    "scenario": SCENARIO,
                    "split_lock_sha256": contract.lock_sha256,
                    "metrics": {k: v for k, v in m.items() if k != "by_regime"},
                    "by_regime": m.get("by_regime"),
                },
            )

        v = row["validation"]
        pf = v["profit_factor"]
        print(
            f"[eval] {cfg.config_id} ({cfg.family[:22]:<22}) "
            f"train_R={row['train']['sum_net_R']:+9.1f} "
            f"val_R={v['sum_net_R']:+8.1f} "
            f"val_PF={pf if pf is None else round(pf, 3)} "
            f"val_n={v['trades']} [{time.time() - tc:.0f}s]"
        )
        results.append(row)

    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for row in results:
        by_family.setdefault(row["family"], []).append(row)

    report = {
        "report_type": "c2_strat02_family_report",
        "diagnostic_only": True,
        "opens_orders": False,
        "cycle": CYCLE,
        "generated_at_utc": pd.Timestamp.utcnow().isoformat(),
        "scenario": SCENARIO,
        "risk_per_trade": 0.005,
        "panel": panel,
        "split_lock_sha256": contract.lock_sha256,
        "final_oos_accessed": False,
        "n_configs_evaluated": len(results),
        "families": {
            fam: {"n_configs": len(rows), "configs": rows}
            for fam, rows in by_family.items()
        },
    }
    out_path = C2_RESEARCH / "phase2_report.json"
    write_json_atomic(out_path, report)
    print(f"\n[done] {len(results)} configs in {time.time() - t0:.1f}s -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
