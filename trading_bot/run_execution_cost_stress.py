"""Prompt 28.10 — execution realism / slippage stress runner.

Runs or aggregates multi-asset backtests under base/conservative/severe
execution-cost models and exports a cost-stress matrix.
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


def _summarize_asset_cost(symbol: str, timeframe: str, cost_model: str, runs_dir: Path) -> dict[str, Any]:
    run_dir = runs_dir / _asset_slug(symbol) / timeframe / cost_model
    if not run_dir.exists():
        return {
            "symbol": symbol,
            "asset_slug": _asset_slug(symbol),
            "timeframe": timeframe,
            "cost_model": cost_model,
            "status": "MISSING_REPORTS",
            "run_dir": str(run_dir),
        }
    readiness = _load_json(run_dir / "paper_readiness_report.json")
    lifecycle = _load_json(run_dir / "lifecycle_consistency_report.json")
    archetype = _load_json(run_dir / "archetype_performance_report.json")
    runtime = _load_json(run_dir / "runtime_profile_report.json")
    profile = readiness.get("timeframe_profile") or {"timeframe": timeframe}
    approx_days = float(profile.get("approx_days", 0.0) or 0.0)
    trades = int(readiness.get("closed_trades", 0) or 0)
    net_pct = float(readiness.get("net_pnl_pct", 0.0) or 0.0)
    annualized_simple = net_pct / approx_days * 365.0 if approx_days > 0 else 0.0
    by_arch = archetype.get("by_archetype", {}) if isinstance(archetype, dict) else {}
    positive_arches = {
        arch: row for arch, row in by_arch.items()
        if int(row.get("trades", 0) or 0) > 0 and float(row.get("avg_r", 0.0) or 0.0) > 0.0
    }
    return {
        "symbol": symbol,
        "asset_slug": _asset_slug(symbol),
        "timeframe": timeframe,
        "cost_model": cost_model,
        "status": readiness.get("status", "UNKNOWN" if readiness else "MISSING_REPORTS"),
        "net_pnl_pct": round(net_pct, 4),
        "annualized_simple_pct": round(annualized_simple, 4),
        "max_drawdown_pct": readiness.get("max_drawdown_pct"),
        "closed_trades": trades,
        "lifecycle_status": lifecycle.get("status"),
        "positive_archetypes": positive_arches,
        "runtime_total_seconds": runtime.get("total_runtime_seconds"),
        "warnings": readiness.get("warnings", []),
        "blockers": readiness.get("blockers", []),
        "run_dir": str(run_dir),
    }


def _aggregate(rows: list[dict[str, Any]], cost_models: list[str]) -> dict[str, Any]:
    by_model: dict[str, Any] = {}
    for model in cost_models:
        model_rows = [r for r in rows if r.get("cost_model") == model and r.get("status") != "MISSING_REPORTS"]
        positive = [r for r in model_rows if float(r.get("net_pnl_pct") or 0.0) > 0 and r.get("lifecycle_status") == "PASS"]
        total_trades = sum(int(r.get("closed_trades", 0) or 0) for r in model_rows)
        avg_net = sum(float(r.get("net_pnl_pct") or 0.0) for r in model_rows) / len(model_rows) if model_rows else 0.0
        max_dd = max([float(r.get("max_drawdown_pct") or 0.0) for r in model_rows] or [0.0])
        arch_counts: dict[str, int] = {}
        for r in positive:
            for arch in (r.get("positive_archetypes") or {}).keys():
                arch_counts[arch] = arch_counts.get(arch, 0) + 1
        by_model[model] = {
            "tested_assets": [r.get("symbol") for r in model_rows],
            "positive_assets": [r.get("symbol") for r in positive],
            "positive_asset_count": len(positive),
            "total_closed_trades": total_trades,
            "average_net_pnl_pct": round(avg_net, 4),
            "worst_max_drawdown_pct": round(max_dd, 4),
            "positive_archetype_asset_counts": arch_counts,
            "robust_positive_archetypes": [a for a, c in arch_counts.items() if c >= 2],
            "passes_minimum": bool(len(positive) >= (3 if model == "conservative" else 2) and total_trades >= 100),
        }

    blockers = []
    warnings = []
    failed_models = sorted({str(r.get("cost_model")) for r in rows if r.get("status") == "FAILED"})
    missing_by_model = {
        model: [r.get("symbol") for r in rows if r.get("cost_model") == model and r.get("status") in {"FAILED", "MISSING_REPORTS"}]
        for model in cost_models
    }
    for model, missing_assets in missing_by_model.items():
        if missing_assets:
            blockers.append(f"Cost model {model} did not produce valid reports for: {missing_assets}.")
    if failed_models:
        blockers.append(f"Execution stress subprocess failed for cost models: {failed_models}.")
    if by_model.get("base", {}).get("positive_asset_count", 0) < 3:
        blockers.append("Base cost model has fewer than 3 positive assets.")
    if by_model.get("conservative", {}).get("positive_asset_count", 0) < 3:
        blockers.append("Conservative cost model has fewer than 3 positive assets.")
    if by_model.get("severe", {}).get("positive_asset_count", 0) < 2:
        warnings.append("Severe cost model has fewer than 2 positive assets; treat edge as cost-sensitive.")

    status = "EXECUTION_STRESS_READY"
    if blockers:
        status = "NOT_READY"
    elif warnings:
        status = "EXECUTION_STRESS_RESEARCH_READY"

    return {"status": status, "by_cost_model": by_model, "blockers": blockers, "warnings": warnings}


def run_model(args: argparse.Namespace, model: str, symbols: list[str]) -> bool:
    cmd = [
        sys.executable,
        str(TRADING_BOT_DIR / "run_multi_asset_robustness.py"),
        "--symbols", ",".join(symbols),
        "--timeframe", args.timeframe,
        "--candles", str(args.candles),
        "--balance", str(args.balance),
        "--cost-model", model,
    ]
    if args.equivalent_15m_candles:
        cmd.append("--equivalent-15m-candles")
    if args.fast:
        cmd.append("--fast")
    if args.no_download_cache:
        cmd.append("--no-download-cache")
    if args.force_download_cache:
        cmd.append("--force-download-cache")
    if args.days is not None:
        cmd.extend(["--days", str(args.days)])
    print("\n" + "=" * 100)
    print(f"[ExecutionCostStress] Running cost_model={model}")
    print(" ".join(cmd))
    print("=" * 100)
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if completed.returncode != 0:
        print(f"[ExecutionCostStress] ERROR: model {model} failed with exit code {completed.returncode}")
        if args.stop_on_error:
            raise SystemExit(completed.returncode)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run/aggregate execution cost stress tests.")
    parser.add_argument("--symbols", default="BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT", help="Comma-separated asset list. Default is the 28.11 paper universe; add XRP/USDT explicitly for research-only stress.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--candles", type=int, default=50000)
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--cost-models", default="base,conservative,severe")
    parser.add_argument("--equivalent-15m-candles", action="store_true")
    parser.add_argument("--fast", action="store_true")
    parser.add_argument("--aggregate-only", action="store_true")
    parser.add_argument("--no-download-cache", action="store_true")
    parser.add_argument("--force-download-cache", action="store_true")
    parser.add_argument("--days", type=float, default=None)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--runs-dir", default="data/multi_asset_runs")
    parser.add_argument("--output", default="data/execution_cost_stress_report.json")
    args = parser.parse_args()

    symbols = [_display_symbol(s) for s in args.symbols.split(",") if s.strip()]
    models = [m.strip().lower() for m in args.cost_models.split(",") if m.strip()]
    models = [m for m in models if m in {"base", "conservative", "severe"}]
    if not models:
        models = ["base", "conservative", "severe"]

    failed_models: set[str] = set()
    if not args.aggregate_only:
        for model in models:
            if not run_model(args, model, symbols):
                failed_models.add(model)

    runs_dir = Path(args.runs_dir)
    rows: list[dict[str, Any]] = []
    for model in models:
        for symbol in symbols:
            if model in failed_models:
                rows.append({
                    "symbol": symbol,
                    "asset_slug": _asset_slug(symbol),
                    "timeframe": args.timeframe,
                    "cost_model": model,
                    "status": "FAILED",
                    "run_dir": str(runs_dir / _asset_slug(symbol) / args.timeframe / model),
                })
            else:
                rows.append(_summarize_asset_cost(symbol, args.timeframe, model, runs_dir))

    report = {
        "summary": _aggregate(rows, models),
        "failed_cost_models": sorted(failed_models),
        "asset_cost_rows": rows,
        "guardrails": {
            "base_min_positive_assets": 3,
            "conservative_min_positive_assets": 3,
            "severe_min_positive_assets": 2,
            "minimum_aggregated_trades": 100,
            "note": "If conservative passes, move to threshold-freeze/OOS and paper-engine design. If severe fails, use it as risk sizing stress rather than a hard blocker.",
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[ExecutionCostStress] Report exported -> {out}")
    print(f"Status: {report['summary']['status']}")
    for model, row in report["summary"]["by_cost_model"].items():
        print(
            f"- {model}: positives={row['positive_assets']} | avg_net={row['average_net_pnl_pct']}% | "
            f"worst_DD={row['worst_max_drawdown_pct']}% | trades={row['total_closed_trades']} | arches={row['robust_positive_archetypes']}"
        )


if __name__ == "__main__":
    main()
