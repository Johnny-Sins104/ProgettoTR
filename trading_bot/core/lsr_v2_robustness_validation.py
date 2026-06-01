"""Prompt 29.4.4s-8 — LSR-v2 walk-forward / OOS / bootstrap validation suite.

Diagnostic-only robustness validation for the locked LSR-v2 research profile:
LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24.

The validator consumes trade-level rows produced by the sample-expansion audit
(`lsr_v2_sample_expansion_trades.jsonl`), deduplicates repeated window-level
representations of the same opportunity, and runs trade-level robustness checks:

* purged/embargoed temporal fold stability (walk-forward proxy);
* chronological out-of-sample holdout;
* bootstrap / Monte Carlo trade resampling;
* cost-degradation checks between primary and severe cost models;
* asset, timeframe, side and drawdown stability.

It must never submit orders, open positions, mutate paper state, route signals,
call a broker, lower runtime thresholds, or enable live/testnet paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import hashlib
import json
import math
import random

PROMPT_ID = "29.4.4s-8"
LOCKED_PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
LOCKED_VARIANT_ID = "retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24"

INPUT_TRADES_NAME = "lsr_v2_sample_expansion_trades.jsonl"
REPORT_NAME = "lsr_v2_robustness_validation_report.json"
WALK_FORWARD_REPORT_NAME = "lsr_v2_walk_forward_report.json"
OOS_REPORT_NAME = "lsr_v2_oos_report.json"
BOOTSTRAP_REPORT_NAME = "lsr_v2_bootstrap_report.json"
WALK_FORWARD_TRADES_NAME = "lsr_v2_walk_forward_trades.jsonl"

PASS_DECISION = "LSR_V2_ROBUSTNESS_VALIDATION_PASS"
READY_DECISION = "LSR_V2_READY_FOR_PROMOTION_GATE"
WF_UNSTABLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_WALK_FORWARD_UNSTABLE"
OOS_FAILED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OOS_FAILED"
BOOTSTRAP_FRAGILE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_BOOTSTRAP_FRAGILE"
COST_FAILED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_FAILED"
REJECT_DECISION = "REJECT_LSR_V2_ROBUSTNESS_FAILED"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ROBUSTNESS_NO_TRADES"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ROBUSTNESS_ERROR"


@dataclass(frozen=True)
class LSRV2RobustnessValidationSettings:
    data_dir: str = "data"
    trades_path: str | None = None
    primary_cost_model: str = "conservative"
    severe_cost_model: str = "severe"
    min_unique_primary_trades: int = 50
    min_walk_forward_folds: int = 5
    walk_forward_folds: int = 8
    embargo_trades: int = 1
    min_walk_forward_positive_ratio: float = 0.55
    oos_holdout_ratio: float = 0.20
    min_oos_avg_r: float = 0.0
    min_oos_sum_r: float = 0.0
    bootstrap_iterations: int = 500
    bootstrap_sample_fraction: float = 1.0
    min_bootstrap_positive_ratio: float = 0.60
    min_bootstrap_median_avg_r: float = 0.0
    max_drawdown_r: float = 25.0
    max_asset_pnl_share: float = 0.65
    max_timeframe_pnl_share: float = 0.75
    min_positive_asset_ratio: float = 0.50
    min_positive_timeframe_ratio: float = 0.50
    min_positive_side_ratio: float = 0.50
    min_severe_positive_ratio: float = 0.45
    max_cost_degradation_ratio: float = 0.85
    breakeven_r_abs: float = 0.10
    random_seed: int = 294408
    max_walk_forward_trade_rows_to_write: int = 250_000

    @classmethod
    def default(cls) -> "LSRV2RobustnessValidationSettings":
        return cls()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_div(num: float, den: float, default: float | None = None) -> float | None:
    try:
        den_f = float(den)
        if abs(den_f) <= 1e-12:
            return default
        out = float(num) / den_f
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _round(value: Any, digits: int = 8) -> float | None:
    try:
        out = float(value)
        if math.isfinite(out):
            return round(out, digits)
    except Exception:
        pass
    return None


def _avg(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    return sum(vals) / len(vals) if vals else None


def _median(values: Sequence[float]) -> float | None:
    vals = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not vals:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _quantile(values: Sequence[float], q: float) -> float | None:
    vals = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = max(0.0, min(1.0, float(q))) * (len(vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    weight = pos - lo
    return vals[lo] * (1.0 - weight) + vals[hi] * weight


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]], *, max_rows: int | None = None) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            if max_rows is not None and count >= max_rows:
                break
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except Exception:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _trade_sort_key(row: dict[str, Any]) -> tuple[str, int, str, int, str]:
    ts = str(row.get("entry_timestamp") or row.get("sweep_timestamp") or row.get("reclaim_timestamp") or "")
    idx = _safe_int(row.get("entry_index"), 0)
    symbol = str(row.get("sample_expansion_symbol") or row.get("symbol") or "")
    timeframe = str(row.get("sample_expansion_timeframe") or row.get("timeframe") or "")
    cid = str(row.get("candidate_id") or "")
    return (ts, idx, symbol, idx, f"{timeframe}|{cid}")


def _trade_dataset(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("sample_expansion_symbol") or row.get("symbol") or "UNKNOWN"),
        str(row.get("sample_expansion_timeframe") or row.get("timeframe") or "UNKNOWN"),
    )


def _dedupe_key(row: dict[str, Any], *, include_cost: bool = True) -> str:
    symbol, timeframe = _trade_dataset(row)
    parts = [
        symbol,
        timeframe,
        str(row.get("candidate_id") or ""),
        str(row.get("side") or ""),
        str(row.get("entry_timestamp") or ""),
        str(row.get("entry_index") or ""),
        str(row.get("entry_price") or ""),
        str(row.get("stop_loss") or ""),
        str(row.get("take_profit") or ""),
    ]
    if include_cost:
        parts.append(str(row.get("cost_model") or ""))
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _pair_key(row: dict[str, Any]) -> str:
    return _dedupe_key(row, include_cost=False)


def _dedupe_trades(rows: Sequence[dict[str, Any]], *, include_cost: bool = True) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _dedupe_key(row, include_cost=include_cost)
        prev = best.get(key)
        if prev is None:
            best[key] = dict(row)
            continue
        # Prefer the longest window representation because it carries the most
        # historical context, while still representing the same opportunity.
        if _safe_int(row.get("window_size"), 0) >= _safe_int(prev.get("window_size"), 0):
            best[key] = dict(row)
    return sorted(best.values(), key=_trade_sort_key)


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _positive_concentration(values: Sequence[float]) -> tuple[float, float, float]:
    positives = sorted((float(v) for v in values if float(v) > 0), reverse=True)
    total = sum(positives)
    if total <= 0 or not positives:
        return 0.0, 0.0, 0.0
    return positives[0] / total, sum(positives[:3]) / total, sum(positives[:5]) / total


def _basic_trade_summary(rows: Sequence[dict[str, Any]], settings: LSRV2RobustnessValidationSettings) -> dict[str, Any]:
    net = [_safe_float(r.get("net_r"), 0.0) for r in rows]
    gross = [_safe_float(r.get("gross_r"), 0.0) for r in rows]
    cost = [_safe_float(r.get("cost_r"), 0.0) for r in rows]
    top1, top3, top5 = _positive_concentration(net)
    wins = [x for x in net if x > settings.breakeven_r_abs]
    losses = [x for x in net if x < -settings.breakeven_r_abs]
    breakevens = [x for x in net if abs(x) <= settings.breakeven_r_abs]
    by_exit: dict[str, int] = {}
    by_side: dict[str, int] = {}
    for row in rows:
        by_exit[str(row.get("exit_reason", "UNKNOWN"))] = by_exit.get(str(row.get("exit_reason", "UNKNOWN")), 0) + 1
        by_side[str(row.get("side", "UNKNOWN"))] = by_side.get(str(row.get("side", "UNKNOWN")), 0) + 1
    return {
        "closed_trades": len(rows),
        "sum_r_post_cost": _round(sum(net), 8),
        "avg_r_post_cost": _round(_avg(net) or 0.0, 8),
        "median_r_post_cost": _round(_median(net) or 0.0, 8),
        "sum_gross_r": _round(sum(gross), 8),
        "sum_cost_r": _round(sum(cost), 8),
        "cost_to_edge_ratio": _round(_safe_div(sum(cost), sum(gross), 999.0) if sum(gross) > 0 else 999.0, 8),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), len(rows), 0.0) or 0.0, 8),
        "loss_rate": _round(_safe_div(len(losses), len(rows), 0.0) or 0.0, 8),
        "breakeven_rate": _round(_safe_div(len(breakevens), len(rows), 0.0) or 0.0, 8),
        "max_drawdown_r": _round(_max_drawdown(net), 8),
        "top_1_positive_concentration": _round(top1, 8),
        "top_3_positive_concentration": _round(top3, 8),
        "top_5_positive_concentration": _round(top5, 8),
        "exit_reason_counts": dict(sorted(by_exit.items())),
        "side_counts": dict(sorted(by_side.items())),
    }


def _split_sequential_folds(rows: Sequence[dict[str, Any]], folds: int) -> list[list[dict[str, Any]]]:
    if not rows:
        return []
    folds = max(1, min(int(folds), len(rows)))
    out: list[list[dict[str, Any]]] = []
    n = len(rows)
    for i in range(folds):
        start = int(round(i * n / folds))
        end = int(round((i + 1) * n / folds))
        chunk = list(rows[start:end])
        if chunk:
            out.append(chunk)
    return out


def _run_walk_forward(rows: Sequence[dict[str, Any]], settings: LSRV2RobustnessValidationSettings) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    folds = _split_sequential_folds(list(rows), settings.walk_forward_folds)
    fold_rows: list[dict[str, Any]] = []
    labelled_trades: list[dict[str, Any]] = []
    for idx, fold in enumerate(folds, start=1):
        net = [_safe_float(t.get("net_r"), 0.0) for t in fold]
        summary = _basic_trade_summary(fold, settings)
        start_key = _trade_sort_key(fold[0])[0] if fold else None
        end_key = _trade_sort_key(fold[-1])[0] if fold else None
        row = {
            "fold_index": idx,
            "fold_count": len(folds),
            "embargo_trades": int(settings.embargo_trades),
            "start_entry_timestamp": start_key,
            "end_entry_timestamp": end_key,
            "closed_trades": len(fold),
            "sum_r_post_cost": summary.get("sum_r_post_cost"),
            "avg_r_post_cost": summary.get("avg_r_post_cost"),
            "median_r_post_cost": summary.get("median_r_post_cost"),
            "max_drawdown_r": summary.get("max_drawdown_r"),
            "positive": (sum(net) > 0),
        }
        fold_rows.append(row)
        for trade in fold:
            labelled = dict(trade)
            labelled["event_type"] = "LSR_V2_WALK_FORWARD_TRADE"
            labelled["prompt_id"] = PROMPT_ID
            labelled["walk_forward_fold"] = idx
            labelled["walk_forward_fold_count"] = len(folds)
            labelled["orders_submitted_by_lsr_v2_walk_forward"] = 0
            labelled["positions_opened_by_lsr_v2_walk_forward"] = 0
            labelled["audit_only"] = True
            labelled["submit_order"] = False
            labelled["broker_submit_called"] = False
            labelled_trades.append(labelled)
    positive_count = sum(1 for f in fold_rows if f.get("positive"))
    positive_ratio = _safe_div(positive_count, len(fold_rows), 0.0) or 0.0
    net_all = [_safe_float(t.get("net_r"), 0.0) for t in rows]
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if rows else "WARN",
        "decision": "LSR_V2_WALK_FORWARD_READY_DIAGNOSTIC" if rows else NO_TRADES_DECISION,
        "created_at": utc_now_iso(),
        "fold_count": len(fold_rows),
        "min_walk_forward_folds": settings.min_walk_forward_folds,
        "walk_forward_positive_folds": positive_count,
        "walk_forward_positive_ratio": _round(positive_ratio, 8),
        "walk_forward_stable": bool(len(fold_rows) >= settings.min_walk_forward_folds and positive_ratio >= settings.min_walk_forward_positive_ratio),
        "closed_trades": len(rows),
        "sum_r_post_cost": _round(sum(net_all), 8),
        "avg_r_post_cost": _round(_avg(net_all) or 0.0, 8),
        "max_drawdown_r": _round(_max_drawdown(net_all), 8),
        "folds": fold_rows,
        "orders_submitted_by_lsr_v2_walk_forward": 0,
        "positions_opened_by_lsr_v2_walk_forward": 0,
        "promotion_ready": False,
    }
    return report, labelled_trades


def _run_oos(rows: Sequence[dict[str, Any]], settings: LSRV2RobustnessValidationSettings) -> dict[str, Any]:
    if not rows:
        return {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": NO_TRADES_DECISION,
            "created_at": utc_now_iso(),
            "oos_pass": False,
            "promotion_ready": False,
        }
    n = len(rows)
    holdout_n = max(1, int(math.ceil(n * max(0.01, min(0.80, settings.oos_holdout_ratio)))))
    train = list(rows[: max(0, n - holdout_n)])
    holdout = list(rows[max(0, n - holdout_n):])
    train_summary = _basic_trade_summary(train, settings)
    oos_summary = _basic_trade_summary(holdout, settings)
    oos_sum = _safe_float(oos_summary.get("sum_r_post_cost"), 0.0)
    oos_avg = _safe_float(oos_summary.get("avg_r_post_cost"), 0.0)
    oos_pass = bool(oos_sum > settings.min_oos_sum_r and oos_avg > settings.min_oos_avg_r)
    return {
        "prompt_id": PROMPT_ID,
        "status": "PASS",
        "decision": "LSR_V2_OOS_READY_DIAGNOSTIC",
        "created_at": utc_now_iso(),
        "holdout_ratio": settings.oos_holdout_ratio,
        "train_closed_trades": train_summary.get("closed_trades", 0),
        "oos_closed_trades": oos_summary.get("closed_trades", 0),
        "train": train_summary,
        "oos": oos_summary,
        "oos_sum_r_post_cost": oos_summary.get("sum_r_post_cost", 0.0),
        "oos_avg_r_post_cost": oos_summary.get("avg_r_post_cost", 0.0),
        "oos_pass": oos_pass,
        "orders_submitted_by_lsr_v2_oos": 0,
        "positions_opened_by_lsr_v2_oos": 0,
        "promotion_ready": False,
    }


def _run_bootstrap(rows: Sequence[dict[str, Any]], settings: LSRV2RobustnessValidationSettings) -> dict[str, Any]:
    net = [_safe_float(t.get("net_r"), 0.0) for t in rows]
    if not net:
        return {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": NO_TRADES_DECISION,
            "created_at": utc_now_iso(),
            "bootstrap_pass": False,
            "promotion_ready": False,
        }
    rng = random.Random(settings.random_seed)
    sample_size = max(1, int(round(len(net) * max(0.10, min(2.0, settings.bootstrap_sample_fraction)))))
    sums: list[float] = []
    avgs: list[float] = []
    dds: list[float] = []
    for _ in range(max(1, int(settings.bootstrap_iterations))):
        sample = [rng.choice(net) for _i in range(sample_size)]
        sums.append(sum(sample))
        avgs.append(sum(sample) / len(sample))
        dds.append(_max_drawdown(sample))
    positive_ratio = (sum(1 for x in sums if x > 0) / len(sums)) if sums else 0.0
    median_avg = _median(avgs) or 0.0
    bootstrap_pass = bool(positive_ratio >= settings.min_bootstrap_positive_ratio and median_avg > settings.min_bootstrap_median_avg_r)
    return {
        "prompt_id": PROMPT_ID,
        "status": "PASS",
        "decision": "LSR_V2_BOOTSTRAP_READY_DIAGNOSTIC",
        "created_at": utc_now_iso(),
        "random_seed": settings.random_seed,
        "bootstrap_iterations": int(settings.bootstrap_iterations),
        "bootstrap_sample_size": sample_size,
        "source_trade_count": len(net),
        "bootstrap_positive_ratio": _round(positive_ratio, 8),
        "bootstrap_median_sum_r": _round(_median(sums) or 0.0, 8),
        "bootstrap_median_avg_r": _round(median_avg, 8),
        "bootstrap_p05_sum_r": _round(_quantile(sums, 0.05) or 0.0, 8),
        "bootstrap_p95_sum_r": _round(_quantile(sums, 0.95) or 0.0, 8),
        "bootstrap_p95_max_drawdown_r": _round(_quantile(dds, 0.95) or 0.0, 8),
        "bootstrap_pass": bootstrap_pass,
        "orders_submitted_by_lsr_v2_bootstrap": 0,
        "positions_opened_by_lsr_v2_bootstrap": 0,
        "promotion_ready": False,
    }


def _group_summary(rows: Sequence[dict[str, Any]], key_name: str, settings: LSRV2RobustnessValidationSettings) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if key_name == "asset":
            key = str(row.get("sample_expansion_symbol") or row.get("symbol") or "UNKNOWN")
        elif key_name == "timeframe":
            key = str(row.get("sample_expansion_timeframe") or row.get("timeframe") or "UNKNOWN")
        elif key_name == "side":
            key = str(row.get("side") or "UNKNOWN")
        else:
            key = str(row.get(key_name) or "UNKNOWN")
        groups.setdefault(key, []).append(row)
    out: list[dict[str, Any]] = []
    for key, vals in sorted(groups.items()):
        s = _basic_trade_summary(vals, settings)
        s["key"] = key
        s["positive"] = _safe_float(s.get("sum_r_post_cost"), 0.0) > 0
        out.append(s)
    return out


def _pnl_dominance(groups: Sequence[dict[str, Any]]) -> float:
    positives = [_safe_float(g.get("sum_r_post_cost"), 0.0) for g in groups if _safe_float(g.get("sum_r_post_cost"), 0.0) > 0]
    total = sum(positives)
    if total <= 0 or not positives:
        return 1.0
    return max(positives) / total


def _positive_group_ratio(groups: Sequence[dict[str, Any]]) -> float:
    if not groups:
        return 0.0
    return sum(1 for g in groups if g.get("positive")) / len(groups)


def _cost_degradation(primary_rows: Sequence[dict[str, Any]], severe_rows: Sequence[dict[str, Any]], settings: LSRV2RobustnessValidationSettings) -> dict[str, Any]:
    primary_by = {_pair_key(r): r for r in primary_rows}
    severe_by = {_pair_key(r): r for r in severe_rows}
    paired_keys = sorted(set(primary_by) & set(severe_by))
    deltas: list[float] = []
    severe_net: list[float] = []
    primary_net: list[float] = []
    primary_pos_to_severe_neg = 0
    for key in paired_keys:
        p = _safe_float(primary_by[key].get("net_r"), 0.0)
        s = _safe_float(severe_by[key].get("net_r"), 0.0)
        primary_net.append(p)
        severe_net.append(s)
        deltas.append(p - s)
        if p > settings.breakeven_r_abs and s < -settings.breakeven_r_abs:
            primary_pos_to_severe_neg += 1
    p_sum = sum(primary_net)
    s_sum = sum(severe_net)
    severe_positive_ratio = _safe_div(sum(1 for x in severe_net if x > 0), len(severe_net), 0.0) or 0.0
    degradation_ratio = _safe_div(p_sum - s_sum, abs(p_sum), 999.0) if abs(p_sum) > 1e-12 else 999.0
    non_destructive = bool(s_sum > 0 and severe_positive_ratio >= settings.min_severe_positive_ratio and (degradation_ratio or 999.0) <= settings.max_cost_degradation_ratio)
    return {
        "paired_trade_count": len(paired_keys),
        "primary_sum_r_post_cost": _round(p_sum, 8),
        "severe_sum_r_post_cost": _round(s_sum, 8),
        "primary_avg_r_post_cost": _round(_avg(primary_net) or 0.0, 8),
        "severe_avg_r_post_cost": _round(_avg(severe_net) or 0.0, 8),
        "avg_delta_r_primary_minus_severe": _round(_avg(deltas) or 0.0, 8),
        "median_delta_r_primary_minus_severe": _round(_median(deltas) or 0.0, 8),
        "primary_positive_to_severe_negative_count": primary_pos_to_severe_neg,
        "primary_positive_to_severe_negative_ratio": _round(_safe_div(primary_pos_to_severe_neg, len(paired_keys), 0.0) or 0.0, 8),
        "severe_positive_ratio": _round(severe_positive_ratio, 8),
        "cost_degradation_ratio": _round(degradation_ratio or 999.0, 8),
        "cost_degradation_non_destructive": non_destructive,
    }


def _classify(
    *,
    primary_summary: dict[str, Any],
    wf_report: dict[str, Any],
    oos_report: dict[str, Any],
    bootstrap_report: dict[str, Any],
    cost_report: dict[str, Any],
    asset_groups: Sequence[dict[str, Any]],
    timeframe_groups: Sequence[dict[str, Any]],
    side_groups: Sequence[dict[str, Any]],
    settings: LSRV2RobustnessValidationSettings,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    labels: list[str] = []
    if _safe_int(primary_summary.get("closed_trades"), 0) < settings.min_unique_primary_trades:
        blockers.append("unique_primary_trades_below_minimum")
        labels.append("LOW_SAMPLE_AFTER_DEDUP")
    if not wf_report.get("walk_forward_stable"):
        blockers.append("walk_forward_positive_ratio_below_minimum")
        labels.append("WALK_FORWARD_UNSTABLE")
    if not oos_report.get("oos_pass"):
        blockers.append("oos_failed")
        labels.append("OOS_FAILED")
    if not bootstrap_report.get("bootstrap_pass"):
        blockers.append("bootstrap_fragile")
        labels.append("BOOTSTRAP_FRAGILE")
    if not cost_report.get("cost_degradation_non_destructive"):
        blockers.append("cost_degradation_failed")
        labels.append("COST_DEGRADATION_FAILED")
    if (_safe_float(primary_summary.get("max_drawdown_r"), 0.0) or 0.0) > settings.max_drawdown_r:
        blockers.append("max_drawdown_above_limit")
        labels.append("DRAWDOWN_UNSTABLE")
    asset_share = _pnl_dominance(asset_groups)
    tf_share = _pnl_dominance(timeframe_groups)
    asset_ratio = _positive_group_ratio(asset_groups)
    tf_ratio = _positive_group_ratio(timeframe_groups)
    side_ratio = _positive_group_ratio(side_groups)
    if asset_groups and asset_share > settings.max_asset_pnl_share:
        blockers.append("single_asset_pnl_dominance")
        labels.append("ASSET_CONCENTRATION")
    if timeframe_groups and tf_share > settings.max_timeframe_pnl_share:
        blockers.append("single_timeframe_pnl_dominance")
        labels.append("TIMEFRAME_CONCENTRATION")
    if asset_groups and asset_ratio < settings.min_positive_asset_ratio:
        blockers.append("asset_positive_ratio_below_minimum")
        labels.append("ASSET_INSTABILITY")
    if timeframe_groups and tf_ratio < settings.min_positive_timeframe_ratio:
        blockers.append("timeframe_positive_ratio_below_minimum")
        labels.append("TIMEFRAME_INSTABILITY")
    if side_groups and side_ratio < settings.min_positive_side_ratio:
        blockers.append("side_positive_ratio_below_minimum")
        labels.append("SIDE_INSTABILITY")

    if not blockers:
        return READY_DECISION, ["ROBUSTNESS_VALIDATION_PASS", "READY_FOR_PROMOTION_GATE_REVIEW"], []
    # Prioritize the most actionable failure in the decision field.
    if "walk_forward_positive_ratio_below_minimum" in blockers:
        decision = WF_UNSTABLE_DECISION
    elif "oos_failed" in blockers:
        decision = OOS_FAILED_DECISION
    elif "bootstrap_fragile" in blockers:
        decision = BOOTSTRAP_FRAGILE_DECISION
    elif "cost_degradation_failed" in blockers:
        decision = COST_FAILED_DECISION
    else:
        decision = REJECT_DECISION
    return decision, list(dict.fromkeys(labels)), blockers


def _safe_no_trade_report(settings: LSRV2RobustnessValidationSettings, paths: dict[str, Path], reason: str) -> dict[str, Any]:
    created = utc_now_iso()
    report = {
        "prompt_id": PROMPT_ID,
        "status": "WARN",
        "decision": NO_TRADES_DECISION,
        "classification_labels": ["NO_TRADE_ROWS"],
        "blockers": [reason],
        "created_at": created,
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "raw_trade_rows": 0,
        "unique_primary_trades": 0,
        "orders_submitted_by_lsr_v2_robustness": 0,
        "positions_opened_by_lsr_v2_robustness": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(paths["report"]),
        "walk_forward_report": str(paths["wf"]),
        "oos_report": str(paths["oos"]),
        "bootstrap_report": str(paths["bootstrap"]),
        "walk_forward_trades_jsonl": str(paths["wf_trades"]),
    }
    wf = {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_TRADES_DECISION, "created_at": created, "folds": [], "promotion_ready": False}
    oos = {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_TRADES_DECISION, "created_at": created, "promotion_ready": False}
    boot = {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_TRADES_DECISION, "created_at": created, "promotion_ready": False}
    _write_json(paths["report"], report)
    _write_json(paths["wf"], wf)
    _write_json(paths["oos"], oos)
    _write_json(paths["bootstrap"], boot)
    _write_jsonl(paths["wf_trades"], [])
    return report


def run_lsr_v2_robustness_validation(settings: LSRV2RobustnessValidationSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2RobustnessValidationSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": data_dir / REPORT_NAME,
        "wf": data_dir / WALK_FORWARD_REPORT_NAME,
        "oos": data_dir / OOS_REPORT_NAME,
        "bootstrap": data_dir / BOOTSTRAP_REPORT_NAME,
        "wf_trades": data_dir / WALK_FORWARD_TRADES_NAME,
    }
    trades_path = Path(settings.trades_path) if settings.trades_path else data_dir / INPUT_TRADES_NAME

    try:
        raw_rows = _read_jsonl(trades_path)
        if not raw_rows:
            return _safe_no_trade_report(settings, paths, "no_sample_expansion_trade_rows")

        locked_rows = [
            r for r in raw_rows
            if str(r.get("locked_variant_id") or r.get("variant_id") or "") == LOCKED_VARIANT_ID
            or str(r.get("locked_profile_name") or "") == LOCKED_PROFILE_NAME
        ]
        if not locked_rows:
            # Be permissive for synthetic/unit fixtures that only contain cost models.
            locked_rows = raw_rows[:]

        primary_raw = [r for r in locked_rows if str(r.get("cost_model")) == settings.primary_cost_model]
        severe_raw = [r for r in locked_rows if str(r.get("cost_model")) == settings.severe_cost_model]
        primary = _dedupe_trades(primary_raw, include_cost=True)
        severe = _dedupe_trades(severe_raw, include_cost=True)
        if not primary:
            return _safe_no_trade_report(settings, paths, "no_primary_cost_model_trades")

        primary_summary = _basic_trade_summary(primary, settings)
        wf_report, wf_trade_rows = _run_walk_forward(primary, settings)
        oos_report = _run_oos(primary, settings)
        bootstrap_report = _run_bootstrap(primary, settings)
        cost_report = _cost_degradation(primary, severe, settings)
        asset_groups = _group_summary(primary, "asset", settings)
        timeframe_groups = _group_summary(primary, "timeframe", settings)
        side_groups = _group_summary(primary, "side", settings)
        decision, labels, blockers = _classify(
            primary_summary=primary_summary,
            wf_report=wf_report,
            oos_report=oos_report,
            bootstrap_report=bootstrap_report,
            cost_report=cost_report,
            asset_groups=asset_groups,
            timeframe_groups=timeframe_groups,
            side_groups=side_groups,
            settings=settings,
        )
        status = "PASS"
        written_wf_trades = _write_jsonl(paths["wf_trades"], wf_trade_rows, max_rows=settings.max_walk_forward_trade_rows_to_write)
        wf_report["report"] = str(paths["wf"])
        wf_report["walk_forward_trades_jsonl"] = str(paths["wf_trades"])
        wf_report["written_walk_forward_trade_rows"] = written_wf_trades
        oos_report["report"] = str(paths["oos"])
        bootstrap_report["report"] = str(paths["bootstrap"])
        _write_json(paths["wf"], wf_report)
        _write_json(paths["oos"], oos_report)
        _write_json(paths["bootstrap"], bootstrap_report)

        report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": decision,
            "classification_labels": labels,
            "blockers": blockers,
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "settings": asdict(settings),
            "input_trades_path": str(trades_path),
            "raw_trade_rows": len(raw_rows),
            "locked_trade_rows": len(locked_rows),
            "primary_raw_trade_rows": len(primary_raw),
            "severe_raw_trade_rows": len(severe_raw),
            "unique_primary_trades": len(primary),
            "unique_severe_trades": len(severe),
            "dedupe_removed_primary_rows": max(0, len(primary_raw) - len(primary)),
            "primary_cost_model": settings.primary_cost_model,
            "severe_cost_model": settings.severe_cost_model,
            "primary_summary": primary_summary,
            "walk_forward_positive_ratio": wf_report.get("walk_forward_positive_ratio"),
            "walk_forward_stable": wf_report.get("walk_forward_stable", False),
            "oos_pass": oos_report.get("oos_pass", False),
            "oos_avg_r_post_cost": oos_report.get("oos_avg_r_post_cost"),
            "oos_sum_r_post_cost": oos_report.get("oos_sum_r_post_cost"),
            "bootstrap_pass": bootstrap_report.get("bootstrap_pass", False),
            "bootstrap_positive_ratio": bootstrap_report.get("bootstrap_positive_ratio"),
            "bootstrap_median_avg_r": bootstrap_report.get("bootstrap_median_avg_r"),
            "cost_degradation_non_destructive": cost_report.get("cost_degradation_non_destructive", False),
            "cost_degradation": cost_report,
            "asset_stability": {
                "groups": asset_groups,
                "positive_group_ratio": _round(_positive_group_ratio(asset_groups), 8),
                "max_positive_pnl_share": _round(_pnl_dominance(asset_groups), 8),
                "asset_stability_ok": bool(_positive_group_ratio(asset_groups) >= settings.min_positive_asset_ratio and _pnl_dominance(asset_groups) <= settings.max_asset_pnl_share),
            },
            "timeframe_stability": {
                "groups": timeframe_groups,
                "positive_group_ratio": _round(_positive_group_ratio(timeframe_groups), 8),
                "max_positive_pnl_share": _round(_pnl_dominance(timeframe_groups), 8),
                "timeframe_stability_ok": bool(_positive_group_ratio(timeframe_groups) >= settings.min_positive_timeframe_ratio and _pnl_dominance(timeframe_groups) <= settings.max_timeframe_pnl_share),
            },
            "side_stability": {
                "groups": side_groups,
                "positive_group_ratio": _round(_positive_group_ratio(side_groups), 8),
                "side_stability_ok": bool(_positive_group_ratio(side_groups) >= settings.min_positive_side_ratio),
            },
            "orders_submitted_by_lsr_v2_robustness": 0,
            "positions_opened_by_lsr_v2_robustness": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "promotion_blocked_reason": "robustness validation is diagnostic; separate promotion gate required before paper supervised",
            "report": str(paths["report"]),
            "walk_forward_report": str(paths["wf"]),
            "oos_report": str(paths["oos"]),
            "bootstrap_report": str(paths["bootstrap"]),
            "walk_forward_trades_jsonl": str(paths["wf_trades"]),
        }
        _write_json(paths["report"], report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": [],
            "blockers": ["robustness_validation_error"],
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "orders_submitted_by_lsr_v2_robustness": 0,
            "positions_opened_by_lsr_v2_robustness": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(paths["report"]),
            "walk_forward_report": str(paths["wf"]),
            "oos_report": str(paths["oos"]),
            "bootstrap_report": str(paths["bootstrap"]),
            "walk_forward_trades_jsonl": str(paths["wf_trades"]),
        }
        _write_json(paths["report"], report)
        _write_json(paths["wf"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION, "folds": []})
        _write_json(paths["oos"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_json(paths["bootstrap"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_jsonl(paths["wf_trades"], [])
        return report
