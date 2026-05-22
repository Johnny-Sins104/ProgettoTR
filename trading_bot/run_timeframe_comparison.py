"""Aggregate Prompt 28.8 multi-timeframe backtest reports.

Usage workflow:
  1) Run each timeframe in a separate process, copying the generated reports to
     data/timeframe_runs/<timeframe>/ after each run, or pass explicit folders.
  2) Run this script to create data/timeframe_comparison_report.json.

This script intentionally does not launch full backtests itself; keeping each
run in a fresh process avoids global model/risk state contamination.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _summarize_run(run_dir: Path, fallback_timeframe: str) -> dict[str, Any]:
    readiness = _load_json(run_dir / "paper_readiness_report.json")
    signal = _load_json(run_dir / "signal_density_report.json")
    archetype = _load_json(run_dir / "archetype_performance_report.json")
    lifecycle = _load_json(run_dir / "lifecycle_consistency_report.json")

    profile = readiness.get("timeframe_profile") or {"timeframe": fallback_timeframe}
    funnel = signal.get("funnel", {}) if isinstance(signal, dict) else {}
    by_arch = archetype.get("by_archetype", {}) if isinstance(archetype, dict) else {}

    positive = {
        name: row for name, row in by_arch.items()
        if int(row.get("trades", 0) or 0) > 0 and float(row.get("avg_r", 0.0) or 0.0) > 0
    }
    approx_days = float(profile.get("approx_days", 0.0) or 0.0)
    trades = int(readiness.get("closed_trades", 0) or 0)
    trades_per_year = trades / approx_days * 365.0 if approx_days > 0 else 0.0
    net_pct = float(readiness.get("net_pnl_pct", 0.0) or 0.0)
    annualized_simple = net_pct / approx_days * 365.0 if approx_days > 0 else 0.0

    return {
        "timeframe": profile.get("timeframe", fallback_timeframe),
        "minutes": profile.get("minutes"),
        "approx_days": round(approx_days, 2),
        "status": readiness.get("status", "UNKNOWN"),
        "net_pnl_pct": round(net_pct, 4),
        "annualized_simple_pct": round(annualized_simple, 4),
        "max_drawdown_pct": readiness.get("max_drawdown_pct"),
        "closed_trades": trades,
        "trades_per_year": round(trades_per_year, 2),
        "meta_acceptance_rate_pct": funnel.get("meta_acceptance_rate_pct"),
        "technical_candidates": funnel.get("technical_candidates"),
        "meta_accepted": funnel.get("meta_accepted"),
        "lifecycle_status": lifecycle.get("status"),
        "positive_archetypes": positive,
        "warnings": readiness.get("warnings", []),
        "blockers": readiness.get("blockers", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate multi-timeframe reports into a robustness matrix.")
    parser.add_argument("--runs-dir", default="data/timeframe_runs", help="Folder containing subfolders named 15m, 5m, 3m.")
    parser.add_argument("--output", default="data/timeframe_comparison_report.json")
    parser.add_argument("--timeframes", default="15m,5m,3m")
    args = parser.parse_args()

    base = Path(args.runs_dir)
    rows = []
    for tf in [x.strip() for x in args.timeframes.split(",") if x.strip()]:
        run_dir = base / tf
        if not run_dir.exists():
            rows.append({"timeframe": tf, "status": "MISSING_REPORTS", "run_dir": str(run_dir)})
            continue
        rows.append(_summarize_run(run_dir, tf))

    # Conservative ranking: paper-ready first, then annualized return, then lower DD.
    def score(row: dict[str, Any]) -> tuple:
        status_rank = {"PAPER_READY": 3, "RESEARCH_READY": 2, "NOT_READY": 1}.get(row.get("status"), 0)
        return (status_rank, float(row.get("annualized_simple_pct") or 0.0), -float(row.get("max_drawdown_pct") or 999.0))

    ranked = sorted(rows, key=score, reverse=True)
    report = {
        "summary": ranked,
        "best_candidate": ranked[0] if ranked else None,
        "guardrails": {
            "minimum_preferred_trades": 30,
            "minimum_positive_archetypes": 2,
            "max_preferred_drawdown_pct": 12.0,
            "note": "Treat 5m/3m as execution-sensitive until slippage/fill realism is upgraded.",
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[TimeframeComparison] Report exported -> {out}")
    for row in ranked:
        print(
            f"- {row.get('timeframe')}: {row.get('status')} | "
            f"net={row.get('net_pnl_pct')}% | annualized={row.get('annualized_simple_pct')}% | "
            f"DD={row.get('max_drawdown_pct')}% | trades/year={row.get('trades_per_year')}"
        )


if __name__ == "__main__":
    main()
