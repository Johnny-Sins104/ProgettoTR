"""Prompt 28.9 — multi-asset robustness runner/aggregator.

This script can either launch separate backtest processes for a list of assets
or aggregate already archived reports under data/multi_asset_runs/<asset>/<timeframe>.
Running each asset in a fresh Python process avoids global model/risk state leakage.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

TRADING_BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TRADING_BOT_DIR.parent
os.chdir(PROJECT_ROOT)


def _asset_slug(symbol: str) -> str:
    return str(symbol).replace("/", "").replace(":", "").lower()


def _display_symbol(symbol: str) -> str:
    symbol = str(symbol).strip().upper().replace(":USDT", "")
    if "/" not in symbol and symbol.endswith("USDT"):
        symbol = symbol[:-4] + "/USDT"
    return symbol


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _summarize_run(run_dir: Path, symbol: str, timeframe: str) -> dict[str, Any]:
    readiness = _load_json(run_dir / "paper_readiness_report.json")
    signal = _load_json(run_dir / "signal_density_report.json")
    archetype = _load_json(run_dir / "archetype_performance_report.json")
    lifecycle = _load_json(run_dir / "lifecycle_consistency_report.json")
    runtime = _load_json(run_dir / "runtime_profile_report.json")

    profile = readiness.get("timeframe_profile") or {"timeframe": timeframe}
    approx_days = float(profile.get("approx_days", 0.0) or 0.0)
    net_pct = float(readiness.get("net_pnl_pct", 0.0) or 0.0)
    trades = int(readiness.get("closed_trades", 0) or 0)
    max_dd = readiness.get("max_drawdown_pct")
    trades_per_year = trades / approx_days * 365.0 if approx_days > 0 else 0.0
    annualized_simple = net_pct / approx_days * 365.0 if approx_days > 0 else 0.0

    funnel = signal.get("funnel", {}) if isinstance(signal, dict) else {}
    by_arch = archetype.get("by_archetype", {}) if isinstance(archetype, dict) else {}
    positive_arches = {
        name: row for name, row in by_arch.items()
        if int(row.get("trades", 0) or 0) > 0 and float(row.get("avg_r", 0.0) or 0.0) > 0.0
    }
    negative_arches = {
        name: row for name, row in by_arch.items()
        if int(row.get("trades", 0) or 0) > 0 and float(row.get("avg_r", 0.0) or 0.0) <= 0.0
    }

    return {
        "symbol": symbol,
        "asset_slug": _asset_slug(symbol),
        "timeframe": profile.get("timeframe", timeframe),
        "minutes": profile.get("minutes"),
        "approx_days": round(approx_days, 2),
        "status": readiness.get("status", "MISSING_REPORTS" if not readiness else "UNKNOWN"),
        "net_pnl_pct": round(net_pct, 4),
        "annualized_simple_pct": round(annualized_simple, 4),
        "max_drawdown_pct": max_dd,
        "closed_trades": trades,
        "trades_per_year": round(trades_per_year, 2),
        "lifecycle_status": lifecycle.get("status"),
        "meta_acceptance_rate_pct": funnel.get("meta_acceptance_rate_pct"),
        "technical_candidates": funnel.get("technical_candidates"),
        "meta_accepted": funnel.get("meta_accepted"),
        "positive_archetypes": positive_arches,
        "negative_archetypes": negative_arches,
        "warnings": readiness.get("warnings", []),
        "blockers": readiness.get("blockers", []),
        "runtime_total_seconds": runtime.get("total_runtime_seconds"),
        "runtime_largest_phases": runtime.get("largest_phases", [])[:5],
        "run_dir": str(run_dir),
    }


def _build_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matrix: dict[str, Any] = {}
    for row in rows:
        symbol = row["symbol"]
        for arch, perf in (row.get("positive_archetypes") or {}).items():
            matrix.setdefault(arch, {})[symbol] = {
                "trades": perf.get("trades"),
                "avg_r": perf.get("avg_r"),
                "win_rate_pct": perf.get("win_rate_pct"),
                "avg_pnl": perf.get("avg_pnl"),
                "status": "positive",
            }
        for arch, perf in (row.get("negative_archetypes") or {}).items():
            matrix.setdefault(arch, {})[symbol] = {
                "trades": perf.get("trades"),
                "avg_r": perf.get("avg_r"),
                "win_rate_pct": perf.get("win_rate_pct"),
                "avg_pnl": perf.get("avg_pnl"),
                "status": "non_positive",
            }
    return matrix


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in rows if r.get("status") not in ("MISSING_REPORTS", "FAILED")]
    positive_assets = [r for r in valid if float(r.get("net_pnl_pct") or 0.0) > 0 and str(r.get("lifecycle_status")) == "PASS"]
    total_trades = sum(int(r.get("closed_trades", 0) or 0) for r in valid)
    symbols_positive = [r.get("symbol") for r in positive_assets]

    all_positive_arches: dict[str, int] = {}
    for r in valid:
        for arch in (r.get("positive_archetypes") or {}).keys():
            all_positive_arches[arch] = all_positive_arches.get(arch, 0) + 1

    blockers = []
    warnings = []
    if len(positive_assets) < 2:
        blockers.append(f"Only {len(positive_assets)} assets are net-positive with lifecycle PASS; need at least 2.")
    if total_trades < 100:
        warnings.append(f"Aggregated closed trades {total_trades} < preferred 100.")
    robust_arches = [arch for arch, count in all_positive_arches.items() if count >= 2]
    if len(robust_arches) < 1:
        warnings.append("No archetype is positive on at least 2 assets yet.")

    status = "MULTI_ASSET_RESEARCH_READY"
    if blockers:
        status = "NOT_READY"
    elif len(positive_assets) >= 2 and total_trades >= 100 and robust_arches:
        status = "MULTI_ASSET_PAPER_CANDIDATE"

    return {
        "status": status,
        "tested_assets": [r.get("symbol") for r in rows],
        "valid_assets": [r.get("symbol") for r in valid],
        "positive_assets": symbols_positive,
        "positive_asset_count": len(positive_assets),
        "total_closed_trades": total_trades,
        "robust_positive_archetypes": robust_arches,
        "positive_archetype_asset_counts": all_positive_arches,
        "blockers": blockers,
        "warnings": warnings,
    }


def run_asset_backtests(args: argparse.Namespace, symbols: list[str]) -> None:
    for symbol in symbols:
        cmd = [
            sys.executable,
            str(TRADING_BOT_DIR / "run_custom_backtest.py"),
            "--balance", str(args.balance),
            "--symbol", symbol,
            "--timeframe", args.timeframe,
            "--candles", str(args.candles),
        ]
        if args.equivalent_15m_candles:
            cmd.append("--equivalent-15m-candles")
        if args.fast:
            cmd.append("--fast")
        if getattr(args, "cost_model", None):
            cmd.extend(["--cost-model", str(args.cost_model)])
        if args.no_download_cache:
            cmd.append("--no-download-cache")
        if args.force_download_cache:
            cmd.append("--force-download-cache")
        if args.no_charts:
            cmd.append("--no-charts")
        if args.quiet_wf:
            cmd.append("--quiet-wf")
        if args.days is not None:
            cmd.extend(["--days", str(args.days)])

        print("\n" + "=" * 100)
        print(f"[MultiAsset] Running {symbol} {args.timeframe}")
        print(" ".join(cmd))
        print("=" * 100)
        completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        if completed.returncode != 0:
            print(f"[MultiAsset] WARNING: {symbol} failed with exit code {completed.returncode}")
            if args.stop_on_error:
                raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run/aggregate multi-asset robustness tests.")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT", help="Comma-separated asset list. Default is the 28.11 paper universe; add XRP/USDT explicitly for research-only stress.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--candles", type=int, default=50000)
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--equivalent-15m-candles", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--no-download-cache", action="store_true")
    parser.add_argument("--force-download-cache", action="store_true")
    parser.add_argument("--no-charts", action="store_true")
    parser.add_argument("--quiet-wf", action="store_true")
    parser.add_argument("--days", type=float, default=None)
    parser.add_argument(
        "--cost-model",
        default="base",
        choices=("base", "conservative", "severe"),
        help="Execution-cost model propagated to run_custom_backtest and used for cost-specific report aggregation.",
    )
    parser.add_argument("--aggregate-only", action="store_true", help="Do not run backtests; aggregate existing data/multi_asset_runs reports.")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--runs-dir", default="data/multi_asset_runs")
    parser.add_argument("--output", default="data/multi_asset_robustness_report.json")
    args = parser.parse_args()

    symbols = [_display_symbol(s) for s in args.symbols.split(",") if s.strip()]
    if not args.aggregate_only:
        run_asset_backtests(args, symbols)

    rows: list[dict[str, Any]] = []
    base = Path(args.runs_dir)
    for symbol in symbols:
        run_dir = base / _asset_slug(symbol) / args.timeframe
        cost_specific_dir = run_dir / str(getattr(args, "cost_model", "base") or "base").lower()
        if cost_specific_dir.exists():
            run_dir = cost_specific_dir
        if not run_dir.exists():
            rows.append({"symbol": symbol, "asset_slug": _asset_slug(symbol), "timeframe": args.timeframe, "status": "MISSING_REPORTS", "run_dir": str(run_dir)})
            continue
        rows.append(_summarize_run(run_dir, symbol, args.timeframe))

    report = {
        "summary": _aggregate(rows),
        "asset_rows": rows,
        "archetype_asset_matrix": _build_matrix(rows),
        "cost_model": str(args.cost_model),
        "guardrails": {
            "minimum_positive_assets": 2,
            "minimum_aggregated_trades": 100,
            "minimum_archetype_positive_assets": 2,
            "note": "Prompt 28.9 validates robustness only; execution realism/slippage stress remains Prompt 28.10.",
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[MultiAsset] Report exported -> {out}")
    print(f"Status: {report['summary']['status']}")
    print(f"Positive assets: {report['summary']['positive_assets']}")
    print(f"Total closed trades: {report['summary']['total_closed_trades']}")
    print(f"Robust archetypes: {report['summary']['robust_positive_archetypes']}")
    for row in rows:
        print(
            f"- {row.get('symbol')}: {row.get('status')} | net={row.get('net_pnl_pct')}% | "
            f"DD={row.get('max_drawdown_pct')}% | trades={row.get('closed_trades')} | lifecycle={row.get('lifecycle_status')}"
        )


if __name__ == "__main__":
    main()
