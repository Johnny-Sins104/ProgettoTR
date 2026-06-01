"""Prompt 29.4.4s-3 archetype pruning + breakeven drag hardening.

This module is diagnostic-only.  It mines archived backtest reports across
multiple candle windows and promotes only strategies/archetypes that show
positive realized edge across enough independent windows.  It must not lower
runtime thresholds, force trades, enable paper/live execution, or modify broker
state.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json
import os
import shutil
import subprocess
import sys
import time

REPORT_NAME = "edge_strategy_discovery_report.json"
PROMPT_ID = "29.4.4s-3"
READY_DECISION = "EDGE_STRATEGY_DISCOVERY_READY_DIAGNOSTIC"
NO_VALID_DECISION = "KEEP_DIAGNOSTIC_NO_VALID_EDGE_STRATEGY"
PRUNING_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_ARCHETYPE_PRUNING_REQUIRED"
RUN_FAILED_DECISION = "KEEP_DIAGNOSTIC_BACKTEST_MATRIX_FAILED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if out == out and out not in {float("inf"), float("-inf")}:
            return out
    except Exception:
        pass
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@dataclass(frozen=True)
class EdgeDiscoverySettings:
    data_dir: str = "data"
    report_name: str = REPORT_NAME
    labels: tuple[str, ...] = ("10k", "12k", "15k", "18k", "20k")
    candle_windows: tuple[int, ...] = (10000, 12000, 15000, 18000, 20000)
    min_windows: int = 3
    min_positive_windows: int = 3
    min_total_trades: int = 20
    min_window_trades: int = 3
    min_weighted_avg_r: float = 0.05
    min_total_pnl: float = 0.0
    max_negative_window_avg_r: float = -0.10
    max_allowed_negative_windows: int = 0
    # Breakeven drag: a high BE ratio is only acceptable if the archetype still
    # shows positive net R.  BE trades are not neutral after fees/slippage.
    max_breakeven_drag_ratio: float = 0.45
    max_breakeven_drag_avg_r: float = 0.0
    min_prune_trades: int = 20
    min_readiness_positive_windows: int = 2
    balance: float = 100.0
    timeout_seconds: int = 1800

    @classmethod
    def default(cls) -> "EdgeDiscoverySettings":
        return cls()


def _label_for_window(candles: int) -> str:
    if candles % 1000 == 0:
        return f"{candles // 1000}k"
    return str(candles)


def _archived_path(data_dir: Path, label: str, filename: str) -> Path:
    return data_dir / "edge_strategy_runs" / label / filename


def _candidate_paths(data_dir: Path, label: str, filename: str) -> Iterable[Path]:
    stem = filename.replace("_report.json", "")
    yield data_dir / f"{stem}_{label}.json"
    yield _archived_path(data_dir, label, filename)
    # Historical fallback for signal-density reports already archived by hand.
    if filename == "signal_density_report.json":
        yield data_dir / f"signal_density_{label}.json"
    if filename == "archetype_performance_report.json":
        yield data_dir / f"archetype_performance_{label}.json"
    if filename == "paper_readiness_report.json":
        yield data_dir / f"paper_readiness_{label}.json"


def _first_existing_report(data_dir: Path, label: str, filename: str) -> tuple[dict[str, Any], str]:
    seen: set[Path] = set()
    for path in _candidate_paths(data_dir, label, filename):
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            report = _read_json(path)
            if report:
                return report, str(path)
    return {}, ""


def _extract_window(label: str, data_dir: Path) -> dict[str, Any]:
    signal, signal_path = _first_existing_report(data_dir, label, "signal_density_report.json")
    archetype, archetype_path = _first_existing_report(data_dir, label, "archetype_performance_report.json")
    readiness, readiness_path = _first_existing_report(data_dir, label, "paper_readiness_report.json")

    funnel = signal.get("funnel") if isinstance(signal.get("funnel"), dict) else {}
    prob_dist = signal.get("probability_distribution") if isinstance(signal.get("probability_distribution"), dict) else {}
    by_arch = archetype.get("by_archetype") if isinstance(archetype.get("by_archetype"), dict) else {}

    return {
        "label": label,
        "missing": not bool(signal or archetype or readiness),
        "paths": {
            "signal_density": signal_path,
            "archetype_performance": archetype_path,
            "paper_readiness": readiness_path,
        },
        "funnel": {
            "bars_evaluated": _safe_int(funnel.get("bars_evaluated"), 0),
            "technical_candidates": _safe_int(funnel.get("technical_candidates"), 0),
            "meta_accepted": _safe_int(funnel.get("meta_accepted"), 0),
            "pending_triggers_created": _safe_int(funnel.get("pending_triggers_created"), 0),
            "opened_trades": _safe_int(funnel.get("opened_trades"), 0),
            "closed_trades": _safe_int(funnel.get("closed_trades"), 0),
            "cost_aware_pass": _safe_int(funnel.get("cost_aware_pass"), 0),
            "cost_aware_fail": _safe_int(funnel.get("cost_aware_fail"), 0),
        },
        "probability": {
            "max": _safe_float(prob_dist.get("max"), 0.0),
            "median": _safe_float(prob_dist.get("median"), 0.0),
            "p90": _safe_float(prob_dist.get("p90"), 0.0),
        },
        "readiness": {
            "status": str(readiness.get("status", "UNKNOWN")),
            "net_pnl_pct": _safe_float(readiness.get("net_pnl_pct"), 0.0),
            "max_drawdown_pct": _safe_float(readiness.get("max_drawdown_pct"), 0.0),
            "closed_trades": _safe_int(readiness.get("closed_trades"), 0),
            "blockers": readiness.get("blockers", []) if isinstance(readiness.get("blockers"), list) else [],
            "warnings": readiness.get("warnings", []) if isinstance(readiness.get("warnings"), list) else [],
        },
        "by_archetype": by_arch if isinstance(by_arch, dict) else {},
    }


def _archetype_row(label: str, name: str, raw: dict[str, Any]) -> dict[str, Any]:
    trades = _safe_int(raw.get("trades"), 0)
    avg_r = _safe_float(raw.get("avg_r"), 0.0)
    total_pnl = _safe_float(raw.get("total_pnl"), 0.0)
    wins = _safe_int(raw.get("wins"), 0)
    losses = _safe_int(raw.get("losses"), 0)
    breakevens = _safe_int(raw.get("breakevens"), 0)
    denom = max(trades, 1)
    breakeven_ratio = breakevens / denom if trades > 0 else 0.0
    loss_ratio = losses / denom if trades > 0 else 0.0
    win_ratio = wins / denom if trades > 0 else 0.0
    return {
        "label": label,
        "archetype": name,
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate_pct": _safe_float(raw.get("win_rate_pct"), 0.0),
        "total_pnl": total_pnl,
        "avg_pnl": _safe_float(raw.get("avg_pnl"), 0.0),
        "avg_r": avg_r,
        "median_r": _safe_float(raw.get("median_r"), 0.0),
        "min_r": _safe_float(raw.get("min_r"), 0.0),
        "max_r": _safe_float(raw.get("max_r"), 0.0),
        "win_ratio": round(win_ratio, 6),
        "loss_ratio": round(loss_ratio, 6),
        "breakeven_ratio": round(breakeven_ratio, 6),
        "completed_non_win_ratio": round((losses + breakevens) / denom if trades > 0 else 0.0, 6),
        "positive_edge": trades > 0 and avg_r > 0.0 and total_pnl > 0.0,
    }


def _aggregate_archetypes(windows: list[dict[str, Any]], settings: EdgeDiscoverySettings) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for window in windows:
        label = str(window.get("label", ""))
        for name, raw in (window.get("by_archetype") or {}).items():
            if isinstance(raw, dict):
                grouped.setdefault(str(name), []).append(_archetype_row(label, str(name), raw))

    out: list[dict[str, Any]] = []
    for name, rows in sorted(grouped.items()):
        eligible = [r for r in rows if r["trades"] >= settings.min_window_trades]
        total_trades = sum(r["trades"] for r in rows)
        weighted_avg_r = (
            sum(r["avg_r"] * r["trades"] for r in rows) / total_trades if total_trades > 0 else 0.0
        )
        total_pnl = sum(r["total_pnl"] for r in rows)
        positive_windows = sum(1 for r in eligible if r["avg_r"] >= settings.min_weighted_avg_r and r["total_pnl"] > 0)
        negative_windows = sum(1 for r in eligible if r["avg_r"] < settings.max_negative_window_avg_r or r["total_pnl"] < 0)
        min_avg_r = min((r["avg_r"] for r in eligible), default=0.0)
        max_avg_r = max((r["avg_r"] for r in eligible), default=0.0)
        windows_seen = len(rows)
        eligible_windows = len(eligible)
        low_sample_windows = [r["label"] for r in rows if r["trades"] < settings.min_window_trades]
        negative_labels = [r["label"] for r in eligible if r["avg_r"] < settings.max_negative_window_avg_r or r["total_pnl"] < 0]
        positive_labels = [r["label"] for r in eligible if r["avg_r"] >= settings.min_weighted_avg_r and r["total_pnl"] > 0]
        total_breakevens = sum(r["breakevens"] for r in rows)
        total_wins = sum(r["wins"] for r in rows)
        total_losses = sum(r["losses"] for r in rows)
        breakeven_ratio = total_breakevens / total_trades if total_trades > 0 else 0.0
        win_ratio = total_wins / total_trades if total_trades > 0 else 0.0
        loss_ratio = total_losses / total_trades if total_trades > 0 else 0.0
        breakeven_drag_rows = [
            r
            for r in eligible
            if r["breakeven_ratio"] >= settings.max_breakeven_drag_ratio
            and (r["avg_r"] <= settings.max_breakeven_drag_avg_r or r["total_pnl"] <= 0)
        ]
        breakeven_drag_labels = [r["label"] for r in breakeven_drag_rows]
        breakeven_drag_windows = len(breakeven_drag_rows)
        breakeven_drag_detected = breakeven_drag_windows > 0
        prune_recommended = (
            total_trades >= settings.min_prune_trades
            and (
                weighted_avg_r < settings.min_weighted_avg_r
                or total_pnl <= settings.min_total_pnl
                or negative_windows > settings.max_allowed_negative_windows
                or min_avg_r < settings.max_negative_window_avg_r
                or breakeven_drag_detected
            )
        )

        valid = (
            eligible_windows >= settings.min_windows
            and positive_windows >= settings.min_positive_windows
            and total_trades >= settings.min_total_trades
            and weighted_avg_r >= settings.min_weighted_avg_r
            and total_pnl > settings.min_total_pnl
            and negative_windows <= settings.max_allowed_negative_windows
            and min_avg_r >= settings.max_negative_window_avg_r
            and not breakeven_drag_detected
        )
        if valid:
            status = "VALID_EDGE_CANDIDATE"
        elif weighted_avg_r > 0 and total_pnl > 0:
            status = "WATCHLIST_LOW_SAMPLE_OR_UNSTABLE"
        else:
            status = "BLOCKED_NEGATIVE_OR_UNSTABLE_EDGE"

        blockers: list[str] = []
        if eligible_windows < settings.min_windows:
            blockers.append(f"eligible_windows<{settings.min_windows}")
        if positive_windows < settings.min_positive_windows:
            blockers.append(f"positive_windows<{settings.min_positive_windows}")
        if total_trades < settings.min_total_trades:
            blockers.append(f"total_trades<{settings.min_total_trades}")
        if weighted_avg_r < settings.min_weighted_avg_r:
            blockers.append(f"weighted_avg_r<{settings.min_weighted_avg_r}")
        if total_pnl <= settings.min_total_pnl:
            blockers.append("total_pnl_not_positive")
        if negative_windows > settings.max_allowed_negative_windows:
            blockers.append("negative_windows_present")
        if min_avg_r < settings.max_negative_window_avg_r:
            blockers.append("min_window_avg_r_too_negative")
        if breakeven_drag_detected:
            blockers.append("breakeven_drag_detected")
        if prune_recommended:
            blockers.append("prune_recommended")

        edge_score = round((weighted_avg_r * 100.0) + positive_windows * 10.0 - negative_windows * 15.0 - breakeven_drag_windows * 10.0, 4)
        out.append(
            {
                "archetype": name,
                "status": status,
                "valid_edge": valid,
                "edge_score": edge_score,
                "windows_seen": windows_seen,
                "eligible_windows": eligible_windows,
                "positive_windows": positive_windows,
                "negative_windows": negative_windows,
                "positive_labels": positive_labels,
                "negative_labels": negative_labels,
                "low_sample_labels": low_sample_windows,
                "total_trades": total_trades,
                "total_pnl": round(total_pnl, 6),
                "weighted_avg_r": round(weighted_avg_r, 6),
                "min_eligible_avg_r": round(min_avg_r, 6),
                "max_eligible_avg_r": round(max_avg_r, 6),
                "total_wins": total_wins,
                "total_losses": total_losses,
                "total_breakevens": total_breakevens,
                "win_ratio": round(win_ratio, 6),
                "loss_ratio": round(loss_ratio, 6),
                "breakeven_ratio": round(breakeven_ratio, 6),
                "breakeven_drag_detected": breakeven_drag_detected,
                "breakeven_drag_windows": breakeven_drag_windows,
                "breakeven_drag_labels": breakeven_drag_labels,
                "prune_recommended": prune_recommended,
                "blockers": blockers,
                "window_rows": rows,
            }
        )
    return sorted(out, key=lambda x: (not x["valid_edge"], -x["edge_score"], str(x["archetype"])))


def _build_pruning_recommendations(archetypes: list[dict[str, Any]], settings: EdgeDiscoverySettings) -> dict[str, Any]:
    hard_block: list[str] = []
    diagnostic_only: list[str] = []
    watchlist_expand: list[str] = []
    breakeven_drag: list[str] = []

    for row in archetypes:
        name = str(row.get("archetype", "UNKNOWN"))
        if bool(row.get("breakeven_drag_detected")):
            breakeven_drag.append(name)
        if bool(row.get("prune_recommended")):
            hard_block.append(name)
        elif row.get("status") == "WATCHLIST_LOW_SAMPLE_OR_UNSTABLE":
            watchlist_expand.append(name)
        elif row.get("status") == "BLOCKED_NEGATIVE_OR_UNSTABLE_EDGE":
            diagnostic_only.append(name)

    hard_block = sorted(set(hard_block))
    diagnostic_only = sorted(set(x for x in diagnostic_only if x not in hard_block))
    watchlist_expand = sorted(set(x for x in watchlist_expand if x not in hard_block))
    breakeven_drag = sorted(set(breakeven_drag))

    return {
        "hard_block_archetypes": hard_block,
        "diagnostic_only_archetypes": diagnostic_only,
        "watchlist_expand_archetypes": watchlist_expand,
        "breakeven_drag_archetypes": breakeven_drag,
        "recommended_env": {
            "EDGE_STRATEGY_PRUNING_ENABLED": "0",
            "EDGE_STRATEGY_BLOCKED_ARCHETYPES": ",".join(hard_block),
            "EDGE_STRATEGY_WATCHLIST_ARCHETYPES": ",".join(watchlist_expand),
        },
        "policy": (
            "Diagnostic-only recommendation. Hard-block candidates should not be enabled automatically; "
            "operator must review and explicitly wire them into runtime gates in a later patch."
        ),
        "criteria": {
            "min_prune_trades": settings.min_prune_trades,
            "max_breakeven_drag_ratio": settings.max_breakeven_drag_ratio,
            "max_breakeven_drag_avg_r": settings.max_breakeven_drag_avg_r,
            "min_weighted_avg_r": settings.min_weighted_avg_r,
            "max_negative_window_avg_r": settings.max_negative_window_avg_r,
        },
    }


def _build_breakeven_drag_summary(archetypes: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for row in archetypes:
        rows.append({
            "archetype": row.get("archetype"),
            "total_trades": row.get("total_trades", 0),
            "total_breakevens": row.get("total_breakevens", 0),
            "breakeven_ratio": row.get("breakeven_ratio", 0.0),
            "weighted_avg_r": row.get("weighted_avg_r", 0.0),
            "total_pnl": row.get("total_pnl", 0.0),
            "breakeven_drag_detected": row.get("breakeven_drag_detected", False),
            "breakeven_drag_labels": row.get("breakeven_drag_labels", []),
            "prune_recommended": row.get("prune_recommended", False),
        })
    return {
        "rows": sorted(rows, key=lambda x: (-float(x.get("breakeven_ratio") or 0.0), str(x.get("archetype")))),
        "blocked_by_breakeven_drag": sorted(str(r.get("archetype")) for r in archetypes if r.get("breakeven_drag_detected")),
    }


def build_edge_strategy_discovery_report(
    settings: EdgeDiscoverySettings | None = None,
    *,
    write: bool = True,
) -> dict[str, Any]:
    settings = settings or EdgeDiscoverySettings.default()
    data_dir = Path(settings.data_dir)
    windows = [_extract_window(label, data_dir) for label in settings.labels]
    missing_labels = [w["label"] for w in windows if w.get("missing")]
    missing_archetype_labels = [
        w["label"]
        for w in windows
        if not w.get("missing") and not (w.get("by_archetype") or {})
    ]
    missing_readiness_labels = [
        w["label"]
        for w in windows
        if not w.get("missing") and not w.get("paths", {}).get("paper_readiness")
    ]
    analyzed_windows = [w for w in windows if not w.get("missing")]
    archetypes = _aggregate_archetypes(analyzed_windows, settings)
    valid = [a for a in archetypes if a.get("valid_edge")]
    watchlist = [a for a in archetypes if a.get("status") == "WATCHLIST_LOW_SAMPLE_OR_UNSTABLE"]

    readiness_positive = [
        w["label"]
        for w in analyzed_windows
        if w.get("readiness", {}).get("net_pnl_pct", 0.0) > 0.0
        and str(w.get("readiness", {}).get("status", "")).upper() in {"RESEARCH_READY", "READY", "PASS"}
    ]
    long_window_not_ready = [
        w["label"]
        for w in analyzed_windows
        if w.get("label") in {"15k", "18k", "20k", "50k", "100k"}
        and str(w.get("readiness", {}).get("status", "")).upper() not in {"RESEARCH_READY", "READY", "PASS"}
    ]

    pruning_recommendations = _build_pruning_recommendations(archetypes, settings)
    breakeven_drag_summary = _build_breakeven_drag_summary(archetypes)

    status = "PASS" if valid else "WARN"
    if valid:
        decision = READY_DECISION
    elif pruning_recommendations.get("hard_block_archetypes") or breakeven_drag_summary.get("blocked_by_breakeven_drag"):
        decision = PRUNING_REQUIRED_DECISION
    else:
        decision = NO_VALID_DECISION
    report = {
        "prompt": PROMPT_ID,
        "status": status,
        "decision": decision,
        "ts": utc_now_iso(),
        "data_dir": str(data_dir),
        "report": str(data_dir / settings.report_name),
        "settings": asdict(settings),
        "labels_checked": list(settings.labels),
        "missing_labels": missing_labels,
        "missing_archetype_labels": missing_archetype_labels,
        "missing_readiness_labels": missing_readiness_labels,
        "analyzed_window_count": len(analyzed_windows),
        "valid_strategy_count": len(valid),
        "watchlist_strategy_count": len(watchlist),
        "valid_strategies": valid,
        "watchlist_strategies": watchlist,
        "pruning_recommendations": pruning_recommendations,
        "breakeven_drag_summary": breakeven_drag_summary,
        "all_archetype_scores": archetypes,
        "readiness_positive_labels": readiness_positive,
        "long_window_not_ready_labels": long_window_not_ready,
        "window_summary": [
            {
                "label": w["label"],
                "funnel": w.get("funnel", {}),
                "probability": w.get("probability", {}),
                "readiness": w.get("readiness", {}),
                "paths": w.get("paths", {}),
            }
            for w in analyzed_windows
        ],
        "safety_note": (
            "Diagnostic only: this report discovers and scores strategy archetypes, breakeven drag, "
            "and pruning candidates. It does not lower thresholds, force trades, enable live/testnet/"
            "exchange broker, submit paper orders, or apply pruning automatically."
        ),
    }
    if write:
        _write_json(data_dir / settings.report_name, report)
    return report


def _copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def archive_current_reports(data_dir: str | Path, label: str) -> dict[str, str]:
    data_dir = Path(data_dir)
    archive_dir = data_dir / "edge_strategy_runs" / label
    mapping = {
        "signal_density_report.json": data_dir / f"signal_density_{label}.json",
        "archetype_performance_report.json": data_dir / f"archetype_performance_{label}.json",
        "paper_readiness_report.json": data_dir / f"paper_readiness_{label}.json",
        "adaptive_regime_threshold_report.json": data_dir / f"adaptive_regime_threshold_{label}.json",
        "risk_event_log.json": data_dir / f"risk_event_log_{label}.json",
        "risk_log.json": data_dir / f"risk_log_{label}.json",
    }
    copied: dict[str, str] = {}
    for filename, flat_dst in mapping.items():
        src = data_dir / filename
        if _copy_if_exists(src, archive_dir / filename):
            copied[filename] = str(archive_dir / filename)
            # Flat copies make manual inspection with existing commands easier.
            _copy_if_exists(src, flat_dst)
    return copied


def _stream_backtest_subprocess(
    command: list[str],
    *,
    root: Path,
    log_path: Path,
    timeout_seconds: int,
) -> tuple[int, bool]:
    """Run a backtest subprocess with live UTF-8-safe console streaming.

    The first 29.4.4s-2 runner used subprocess.run(stdout=PIPE), so Windows
    users saw a blank console for many minutes while every backtest was running.
    This helper keeps a per-window log but also streams output line-by-line to
    stdout.  It forces UTF-8/unbuffered child output to avoid cp1252 decode
    failures and silent buffering.
    """

    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    proc = subprocess.Popen(
        command,
        cwd=str(root),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        env=env,
    )
    started = time.monotonic()
    timed_out = False

    with log_path.open("w", encoding="utf-8", errors="replace") as fh:
        if proc.stdout is not None:
            for line in proc.stdout:
                fh.write(line)
                fh.flush()
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except UnicodeEncodeError:
                    safe = line.encode("ascii", "replace").decode("ascii", "replace")
                    sys.stdout.write(safe)
                    sys.stdout.flush()
                if timeout_seconds > 0 and time.monotonic() - started > timeout_seconds:
                    timed_out = True
                    proc.kill()
                    break
        try:
            returncode = proc.wait(timeout=10 if timed_out else timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            returncode = proc.wait(timeout=10)

    return int(returncode), timed_out


def run_backtest_matrix(
    settings: EdgeDiscoverySettings | None = None,
    *,
    python_executable: str | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    settings = settings or EdgeDiscoverySettings.default()
    root = Path(project_root or Path.cwd())
    py = python_executable or sys.executable
    data_dir = root / settings.data_dir
    results: list[dict[str, Any]] = []
    failed = False

    for idx, candles in enumerate(settings.candle_windows, start=1):
        label = _label_for_window(candles)
        log_dir = data_dir / "edge_strategy_runs" / label
        log_path = log_dir / "backtest_stdout.txt"
        command = [
            py,
            "-u",
            "trading_bot/run_custom_backtest.py",
            "--balance",
            str(settings.balance),
            "--candles",
            str(candles),
        ]
        started = utc_now_iso()
        print(
            f"[EDGE DISCOVERY START] window={idx}/{len(settings.candle_windows)} "
            f"label={label} candles={candles} log={log_path}",
            flush=True,
        )
        returncode, timed_out = _stream_backtest_subprocess(
            command,
            root=root,
            log_path=log_path,
            timeout_seconds=settings.timeout_seconds,
        )
        archived = archive_current_reports(data_dir, label) if returncode == 0 and not timed_out else {}
        if returncode != 0 or timed_out:
            failed = True
        print(
            f"[EDGE DISCOVERY DONE] label={label} returncode={returncode} "
            f"timed_out={timed_out} archived={len(archived)}",
            flush=True,
        )
        results.append(
            {
                "label": label,
                "candles": candles,
                "command": " ".join(command),
                "returncode": returncode,
                "timed_out": timed_out,
                "started": started,
                "finished": utc_now_iso(),
                "log": str(log_path),
                "archived": archived,
            }
        )
    report = build_edge_strategy_discovery_report(settings, write=True)
    report["backtest_matrix"] = results
    if failed:
        report["status"] = "WARN"
        report["decision"] = RUN_FAILED_DECISION
    _write_json(Path(settings.data_dir) / settings.report_name, report)
    return report
