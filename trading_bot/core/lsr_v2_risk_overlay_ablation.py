"""Prompt 29.4.4s-8c — LSR-v2 risk overlay ablation / drawdown control preflight.

Diagnostic-only risk-overlay ablation layer for the locked LSR-v2 research
profile: LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24.

The module consumes trade rows produced by the sample-expansion pipeline and
compares offline risk overlays intended to reduce drawdown, loss streaks and
cost-degradation exposure. It is deliberately a research preflight: it must
never submit orders, open positions, mutate paper state, route signals, call a
broker, lower strategy thresholds, enable live/testnet paths, or promote the
strategy by itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import hashlib
import json
import math

PROMPT_ID = "29.4.4s-8c"
LOCKED_PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
LOCKED_VARIANT_ID = "retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24"

INPUT_TRADES_NAME = "lsr_v2_sample_expansion_trades.jsonl"
ATTRIBUTION_REPORT_NAME = "lsr_v2_cost_drawdown_attribution_report.json"
REPORT_NAME = "lsr_v2_risk_overlay_ablation_report.json"
VARIANTS_REPORT_NAME = "lsr_v2_risk_overlay_variants.json"
TRADES_JSONL_NAME = "lsr_v2_risk_overlay_trades.jsonl"
SELECTION_REPORT_NAME = "lsr_v2_risk_overlay_selection_report.json"

READY_DECISION = "LSR_V2_RISK_OVERLAY_RESEARCH_READY"
INSUFFICIENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_OVERLAY_INSUFFICIENT"
DRAWDOWN_REMAINS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_REMAINS_HIGH"
EDGE_DESTROYED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_EDGE_DESTROYED_BY_OVERLAY"
REJECT_DECISION = "REJECT_LSR_V2_OPERATIONALLY_UNSTABLE"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_NO_TRADES"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_ERROR"

TRADE_EVENT_TYPE = "LSR_V2_RISK_OVERLAY_TRADE"


@dataclass(frozen=True)
class LSRV2RiskOverlayAblationSettings:
    data_dir: str = "data"
    trades_path: str | None = None
    attribution_report_path: str | None = None
    primary_cost_model: str = "conservative"
    severe_cost_model: str = "severe"
    breakeven_r_abs: float = 0.10
    max_drawdown_r: float = 25.0
    max_consecutive_losses_limit: int = 10
    min_profit_retention_ratio: float = 0.50
    min_drawdown_reduction_ratio: float = 0.40
    min_sum_r_post_cost: float = 0.0
    min_avg_r_post_cost: float = 0.0
    min_trades_kept_ratio: float = 0.20
    max_cost_degradation_ratio: float = 0.85
    min_severe_positive_ratio: float = 0.45
    max_trade_rows_to_write: int = 250_000
    loss_streak_pause_trades: int = 12
    drawdown_pause_trades: int = 18
    session_pause_trades: int = 12
    risk_cap_pause_trades: int = 15
    expected_r_min_group_trades: int = 20
    expected_r_min_avg_r: float = 0.0

    @classmethod
    def default(cls) -> "LSRV2RiskOverlayAblationSettings":
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


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        value = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


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


def _dataset(row: dict[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("sample_expansion_symbol") or row.get("symbol") or "UNKNOWN"),
        str(row.get("sample_expansion_timeframe") or row.get("timeframe") or "UNKNOWN"),
    )


def _group_value(row: dict[str, Any], key: str) -> str:
    if key == "asset":
        return _dataset(row)[0]
    if key == "timeframe":
        return _dataset(row)[1]
    if key == "asset_timeframe":
        s, tf = _dataset(row)
        return f"{s}|{tf}"
    if key == "side":
        return str(row.get("side") or "UNKNOWN")
    if key == "window":
        return str(row.get("window_label") or row.get("window_size") or "UNKNOWN")
    if key == "exit_reason":
        return str(row.get("exit_reason") or "UNKNOWN")
    if key == "session":
        return _session_key(row)
    return str(row.get(key) or "UNKNOWN")


def _session_key(row: dict[str, Any]) -> str:
    ts = str(row.get("entry_timestamp") or row.get("sweep_timestamp") or "")
    if len(ts) >= 10:
        return ts[:10]
    return str(row.get("window_label") or row.get("window_size") or "UNKNOWN_SESSION")


def _trade_sort_key(row: dict[str, Any]) -> tuple[str, int, str, str, str]:
    ts = str(row.get("entry_timestamp") or row.get("sweep_timestamp") or row.get("reclaim_timestamp") or "")
    idx = _safe_int(row.get("entry_index"), 0)
    symbol, timeframe = _dataset(row)
    cid = str(row.get("candidate_id") or "")
    return (ts, idx, symbol, timeframe, cid)


def _pair_key(row: dict[str, Any]) -> str:
    symbol, timeframe = _dataset(row)
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
    return hashlib.sha1("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()


def _dedupe(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _pair_key(row)
        prev = best.get(key)
        if prev is None or _safe_int(row.get("window_size"), 0) >= _safe_int(prev.get("window_size"), 0):
            best[key] = dict(row)
    return sorted(best.values(), key=_trade_sort_key)


def _filter_locked(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    locked = [
        r for r in rows
        if str(r.get("locked_variant_id") or r.get("variant_id") or "") == LOCKED_VARIANT_ID
        or str(r.get("locked_profile_name") or "") == LOCKED_PROFILE_NAME
    ]
    return locked if locked else list(rows)


def _max_drawdown_from_values(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _max_consecutive_losses(values: Sequence[float], breakeven: float) -> int:
    max_streak = 0
    streak = 0
    for value in values:
        if value < -breakeven:
            streak += 1
            max_streak = max(max_streak, streak)
        elif value > breakeven:
            streak = 0
    return max_streak


def _basic_stats(rows: Sequence[dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> dict[str, Any]:
    values = [_safe_float(r.get("net_r"), 0.0) for r in rows]
    wins = [x for x in values if x > settings.breakeven_r_abs]
    losses = [x for x in values if x < -settings.breakeven_r_abs]
    breakevens = [x for x in values if abs(x) <= settings.breakeven_r_abs]
    return {
        "closed_trades": len(rows),
        "sum_r_post_cost": _round(sum(values), 8),
        "avg_r_post_cost": _round(_avg(values) or 0.0, 8),
        "median_r_post_cost": _round(_median(values) or 0.0, 8),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), len(rows), 0.0) or 0.0, 8),
        "loss_rate": _round(_safe_div(len(losses), len(rows), 0.0) or 0.0, 8),
        "breakeven_rate": _round(_safe_div(len(breakevens), len(rows), 0.0) or 0.0, 8),
        "max_drawdown_r": _round(_max_drawdown_from_values(values), 8),
        "max_consecutive_losses": _max_consecutive_losses(values, settings.breakeven_r_abs),
    }


def _pair_rows(primary_rows: Sequence[dict[str, Any]], severe_rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    severe_by_key = {_pair_key(row): row for row in severe_rows}
    paired: dict[str, dict[str, Any]] = {}
    for primary in primary_rows:
        key = _pair_key(primary)
        severe = severe_by_key.get(key)
        paired[key] = {
            "primary": primary,
            "severe": severe,
            "primary_net_r": _safe_float(primary.get("net_r"), 0.0),
            "severe_net_r": _safe_float(severe.get("net_r"), 0.0) if severe else None,
        }
    return paired


def _kept_keys(rows: Sequence[dict[str, Any]]) -> set[str]:
    return {_pair_key(r) for r in rows}


def _cost_metrics(kept_rows: Sequence[dict[str, Any]], paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> dict[str, Any]:
    keys = _kept_keys(kept_rows)
    primary_values: list[float] = []
    severe_values: list[float] = []
    for key in keys:
        pair = paired.get(key)
        if not pair:
            continue
        primary_values.append(_safe_float(pair.get("primary_net_r"), 0.0))
        severe_net = pair.get("severe_net_r")
        if severe_net is not None:
            severe_values.append(float(severe_net))
    primary_sum = sum(primary_values)
    severe_sum = sum(severe_values)
    degradation = _safe_div(primary_sum - severe_sum, abs(primary_sum), 999.0) if abs(primary_sum) > 1e-12 else 999.0
    severe_positive_ratio = _safe_div(sum(1 for x in severe_values if x > settings.breakeven_r_abs), len(severe_values), 0.0) or 0.0
    return {
        "paired_trade_count": len(severe_values),
        "primary_sum_r_post_cost_for_pairs": _round(primary_sum, 8),
        "severe_sum_r_post_cost": _round(severe_sum, 8),
        "cost_degradation_ratio": _round(degradation, 8),
        "severe_positive_ratio": _round(severe_positive_ratio, 8),
        "cost_degradation_non_destructive": bool(
            severe_sum > 0
            and severe_positive_ratio >= settings.min_severe_positive_ratio
            and (degradation or 999.0) <= settings.max_cost_degradation_ratio
        ),
    }


def _overlay_summary(
    overlay_id: str,
    overlay_family: str,
    kept_rows: Sequence[dict[str, Any]],
    skipped_rows: Sequence[dict[str, Any]],
    baseline_rows: Sequence[dict[str, Any]],
    paired: dict[str, dict[str, Any]],
    settings: LSRV2RiskOverlayAblationSettings,
    *,
    description: str,
    oracle_overlay: bool = False,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_stats = _basic_stats(baseline_rows, settings)
    kept_stats = _basic_stats(kept_rows, settings)
    base_sum = _safe_float(base_stats.get("sum_r_post_cost"), 0.0)
    base_dd = _safe_float(base_stats.get("max_drawdown_r"), 0.0)
    kept_sum = _safe_float(kept_stats.get("sum_r_post_cost"), 0.0)
    kept_dd = _safe_float(kept_stats.get("max_drawdown_r"), 0.0)
    drawdown_reduction = _safe_div(base_dd - kept_dd, base_dd, 0.0) if base_dd > 1e-12 else 0.0
    profit_retention = _safe_div(kept_sum, base_sum, 0.0) if abs(base_sum) > 1e-12 else 0.0
    trades_kept = len(kept_rows)
    trades_filtered = len(skipped_rows)
    kept_ratio = _safe_div(trades_kept, len(baseline_rows), 0.0) or 0.0
    cost = _cost_metrics(kept_rows, paired, settings)
    severe_positive = _safe_float(cost.get("severe_positive_ratio"), 0.0)
    cost_degradation = _safe_float(cost.get("cost_degradation_ratio"), 999.0)
    overlay_valid = bool(
        trades_kept > 0
        and kept_ratio >= settings.min_trades_kept_ratio
        and kept_sum > settings.min_sum_r_post_cost
        and (_safe_float(kept_stats.get("avg_r_post_cost"), 0.0) > settings.min_avg_r_post_cost)
        and (drawdown_reduction or 0.0) >= settings.min_drawdown_reduction_ratio
        and _safe_int(kept_stats.get("max_consecutive_losses"), 999) <= settings.max_consecutive_losses_limit
        and (profit_retention or 0.0) >= settings.min_profit_retention_ratio
        and (cost_degradation <= _safe_float(_cost_metrics(baseline_rows, paired, settings).get("cost_degradation_ratio"), 999.0) or severe_positive >= settings.min_severe_positive_ratio)
    )
    overlay_cost = {
        "filtered_trade_count": trades_filtered,
        "filtered_trade_ratio": _round(_safe_div(trades_filtered, len(baseline_rows), 0.0) or 0.0, 8),
        "delta_sum_r_vs_baseline": _round(kept_sum - base_sum, 8),
        "profit_retention_ratio": _round(profit_retention or 0.0, 8),
    }
    overlay_benefit = {
        "drawdown_reduction_r": _round(base_dd - kept_dd, 8),
        "drawdown_reduction_ratio": _round(drawdown_reduction or 0.0, 8),
        "max_consecutive_losses_reduction": _safe_int(base_stats.get("max_consecutive_losses"), 0) - _safe_int(kept_stats.get("max_consecutive_losses"), 0),
        "cost_degradation_ratio": _round(cost_degradation, 8),
        "severe_positive_ratio": _round(severe_positive, 8),
    }
    summary = {
        "overlay_id": overlay_id,
        "overlay_family": overlay_family,
        "description": description,
        "params": params or {},
        "oracle_overlay": oracle_overlay,
        "diagnostic_only": True,
        "trades_kept": trades_kept,
        "trades_filtered": trades_filtered,
        "trades_kept_ratio": _round(kept_ratio, 8),
        "sum_r_post_cost": kept_stats.get("sum_r_post_cost"),
        "avg_r_post_cost": kept_stats.get("avg_r_post_cost"),
        "max_drawdown_r": kept_stats.get("max_drawdown_r"),
        "max_consecutive_losses": kept_stats.get("max_consecutive_losses"),
        "win_rate": kept_stats.get("win_rate"),
        "loss_rate": kept_stats.get("loss_rate"),
        "breakeven_rate": kept_stats.get("breakeven_rate"),
        "profit_retention_ratio": overlay_cost["profit_retention_ratio"],
        "drawdown_reduction_ratio": overlay_benefit["drawdown_reduction_ratio"],
        "cost_degradation_ratio": overlay_benefit["cost_degradation_ratio"],
        "severe_positive_ratio": overlay_benefit["severe_positive_ratio"],
        "cost_degradation_non_destructive": cost.get("cost_degradation_non_destructive", False),
        "overlay_valid": overlay_valid,
        "overlay_cost": overlay_cost,
        "overlay_benefit": overlay_benefit,
        "baseline_sum_r_post_cost": base_stats.get("sum_r_post_cost"),
        "baseline_max_drawdown_r": base_stats.get("max_drawdown_r"),
        "baseline_max_consecutive_losses": base_stats.get("max_consecutive_losses"),
        "orders_submitted_by_lsr_v2_risk_overlay": 0,
        "positions_opened_by_lsr_v2_risk_overlay": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "promotion_ready": False,
    }
    return summary


def _baseline_overlay(rows: Sequence[dict[str, Any]], paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> dict[str, Any]:
    return _overlay_summary(
        "baseline_no_overlay",
        "baseline",
        rows,
        [],
        rows,
        paired,
        settings,
        description="No risk overlay; reference profile only.",
    )


def _pause_after_loss_streak(rows: Sequence[dict[str, Any]], limit: int, pause_trades: int, paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pause_left = 0
    streak = 0
    for row in rows:
        if pause_left > 0:
            skipped.append({**row, "skip_reason": f"pause_after_{limit}_losses"})
            pause_left -= 1
            continue
        kept.append(row)
        net = _safe_float(row.get("net_r"), 0.0)
        if net < -settings.breakeven_r_abs:
            streak += 1
        elif net > settings.breakeven_r_abs:
            streak = 0
        if streak >= limit:
            pause_left = pause_trades
            streak = 0
    summary = _overlay_summary(
        f"max_consecutive_loss_pause_{limit}",
        "loss_streak_pause",
        kept,
        skipped,
        rows,
        paired,
        settings,
        description=f"Skip the next {pause_trades} candidate trades after {limit} consecutive losses.",
        params={"loss_streak_limit": limit, "pause_trades": pause_trades},
    )
    return summary, kept, skipped


def _rolling_drawdown_pause(rows: Sequence[dict[str, Any]], dd_limit: float, pause_trades: int, paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pause_left = 0
    equity = 0.0
    peak = 0.0
    for row in rows:
        if pause_left > 0:
            skipped.append({**row, "skip_reason": f"pause_after_{dd_limit:g}r_drawdown"})
            pause_left -= 1
            continue
        kept.append(row)
        equity += _safe_float(row.get("net_r"), 0.0)
        peak = max(peak, equity)
        if peak - equity >= dd_limit:
            pause_left = pause_trades
            peak = equity
    summary = _overlay_summary(
        f"rolling_drawdown_pause_{dd_limit:g}R",
        "rolling_drawdown_pause",
        kept,
        skipped,
        rows,
        paired,
        settings,
        description=f"Skip the next {pause_trades} candidate trades after a rolling drawdown of {dd_limit:g}R.",
        params={"drawdown_limit_r": dd_limit, "pause_trades": pause_trades},
    )
    return summary, kept, skipped


def _session_loss_cap(rows: Sequence[dict[str, Any]], loss_cap_r: float, pause_trades: int, paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    session_net: dict[str, float] = {}
    session_pause: dict[str, int] = {}
    for row in rows:
        session = _session_key(row)
        if session_pause.get(session, 0) > 0:
            skipped.append({**row, "skip_reason": f"session_loss_cap_{loss_cap_r:g}R"})
            session_pause[session] = session_pause.get(session, 0) - 1
            continue
        if session_net.get(session, 0.0) <= -abs(loss_cap_r):
            skipped.append({**row, "skip_reason": f"session_loss_cap_{loss_cap_r:g}R"})
            session_pause[session] = max(0, pause_trades - 1)
            continue
        kept.append(row)
        session_net[session] = session_net.get(session, 0.0) + _safe_float(row.get("net_r"), 0.0)
    summary = _overlay_summary(
        f"daily_or_session_loss_cap_{loss_cap_r:g}R",
        "session_loss_cap",
        kept,
        skipped,
        rows,
        paired,
        settings,
        description=f"Stop taking candidates within the same detected session after cumulative session loss reaches {loss_cap_r:g}R.",
        params={"loss_cap_r": loss_cap_r, "pause_trades": pause_trades},
    )
    return summary, kept, skipped


def _severe_cost_filter(rows: Sequence[dict[str, Any]], paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings, threshold: float) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        severe = paired.get(_pair_key(row), {}).get("severe_net_r")
        if severe is None or float(severe) >= threshold:
            kept.append(row)
        else:
            skipped.append({**row, "skip_reason": f"severe_cost_filter_lt_{threshold:g}R"})
    label = "severe_cost_filter" if threshold <= -settings.breakeven_r_abs else "cost_break_even_filter"
    summary = _overlay_summary(
        f"{label}_{threshold:g}R",
        "oracle_cost_filter",
        kept,
        skipped,
        rows,
        paired,
        settings,
        description="Oracle diagnostic: keep only trades whose paired severe-cost result is above threshold. Not directly deployable without an ex-ante cost proxy.",
        oracle_overlay=True,
        params={"severe_net_r_threshold": threshold},
    )
    return summary, kept, skipped


def _group_expected_r_filter(rows: Sequence[dict[str, Any]], paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings, group_key: str, min_avg_r: float, use_severe: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[float]] = {}
    for row in rows:
        group = _group_value(row, group_key)
        if use_severe:
            severe = paired.get(_pair_key(row), {}).get("severe_net_r")
            value = float(severe) if severe is not None else _safe_float(row.get("net_r"), 0.0)
        else:
            value = _safe_float(row.get("net_r"), 0.0)
        groups.setdefault(group, []).append(value)
    allowed = {
        group for group, values in groups.items()
        if len(values) >= settings.expected_r_min_group_trades and (_avg(values) or 0.0) > min_avg_r
    }
    kept = [row for row in rows if _group_value(row, group_key) in allowed]
    skipped = [{**row, "skip_reason": f"low_expected_r_{group_key}"} for row in rows if _group_value(row, group_key) not in allowed]
    summary = _overlay_summary(
        f"low_expected_r_filter_{group_key}_{'severe' if use_severe else 'primary'}",
        "oracle_group_expected_r_filter",
        kept,
        skipped,
        rows,
        paired,
        settings,
        description="Oracle diagnostic: filter groups with weak realized expected R. Requires future ex-ante proxy before runtime use.",
        oracle_overlay=True,
        params={"group_key": group_key, "min_avg_r": min_avg_r, "use_severe": use_severe},
    )
    summary["allowed_groups"] = sorted(allowed)
    return summary, kept, skipped


def _group_risk_cap(rows: Sequence[dict[str, Any]], group_key: str, dd_limit: float, pause_trades: int, paired: dict[str, dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    equity: dict[str, float] = {}
    peak: dict[str, float] = {}
    pause: dict[str, int] = {}
    for row in rows:
        group = _group_value(row, group_key)
        if pause.get(group, 0) > 0:
            skipped.append({**row, "skip_reason": f"{group_key}_risk_cap_{dd_limit:g}R"})
            pause[group] = pause.get(group, 0) - 1
            continue
        kept.append(row)
        equity[group] = equity.get(group, 0.0) + _safe_float(row.get("net_r"), 0.0)
        peak[group] = max(peak.get(group, 0.0), equity[group])
        if peak[group] - equity[group] >= dd_limit:
            pause[group] = pause_trades
            peak[group] = equity[group]
    summary = _overlay_summary(
        f"{group_key}_risk_cap_{dd_limit:g}R",
        f"{group_key}_risk_cap",
        kept,
        skipped,
        rows,
        paired,
        settings,
        description=f"Pause a {group_key} bucket after its local drawdown reaches {dd_limit:g}R.",
        params={"group_key": group_key, "drawdown_limit_r": dd_limit, "pause_trades": pause_trades},
    )
    return summary, kept, skipped


def _build_overlay_variants(primary_rows: Sequence[dict[str, Any]], severe_rows: Sequence[dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    paired = _pair_rows(primary_rows, severe_rows)
    variants: list[dict[str, Any]] = [_baseline_overlay(primary_rows, paired, settings)]
    selected_trade_rows: list[dict[str, Any]] = []

    produced: list[tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = []
    for limit in (3, 5, 7):
        produced.append(_pause_after_loss_streak(primary_rows, limit, settings.loss_streak_pause_trades, paired, settings))
    for dd_limit in (5.0, 10.0, 15.0):
        produced.append(_rolling_drawdown_pause(primary_rows, dd_limit, settings.drawdown_pause_trades, paired, settings))
    for loss_cap in (2.0, 3.0):
        produced.append(_session_loss_cap(primary_rows, loss_cap, settings.session_pause_trades, paired, settings))
    for threshold in (-settings.breakeven_r_abs, 0.0, settings.breakeven_r_abs):
        produced.append(_severe_cost_filter(primary_rows, paired, settings, threshold))
    for group_key in ("asset_timeframe", "side", "timeframe", "asset"):
        produced.append(_group_expected_r_filter(primary_rows, paired, settings, group_key, settings.expected_r_min_avg_r, use_severe=False))
        produced.append(_group_expected_r_filter(primary_rows, paired, settings, group_key, settings.expected_r_min_avg_r, use_severe=True))
    produced.append(_group_risk_cap(primary_rows, "asset_timeframe", 5.0, settings.risk_cap_pause_trades, paired, settings))
    produced.append(_group_risk_cap(primary_rows, "side", 5.0, settings.risk_cap_pause_trades, paired, settings))
    produced.append(_group_risk_cap(primary_rows, "asset_timeframe", 10.0, settings.risk_cap_pause_trades, paired, settings))
    produced.append(_group_risk_cap(primary_rows, "side", 10.0, settings.risk_cap_pause_trades, paired, settings))

    for summary, kept, skipped in produced:
        variants.append(summary)
        if summary.get("overlay_valid") or summary.get("overlay_id") in {
            "max_consecutive_loss_pause_3",
            "rolling_drawdown_pause_5R",
            "daily_or_session_loss_cap_2R",
        }:
            overlay_id = str(summary.get("overlay_id"))
            for row in kept:
                selected_trade_rows.append(_overlay_trade_row(row, overlay_id, kept=True, skip_reason=None))
            for row in skipped:
                selected_trade_rows.append(_overlay_trade_row(row, overlay_id, kept=False, skip_reason=str(row.get("skip_reason") or "filtered")))

    # Ensure deterministic unique overlay IDs; later duplicates are suffixed.
    seen: dict[str, int] = {}
    unique: list[dict[str, Any]] = []
    for v in variants:
        oid = str(v.get("overlay_id") or "overlay")
        count = seen.get(oid, 0)
        seen[oid] = count + 1
        if count:
            v = {**v, "overlay_id": f"{oid}_{count + 1}"}
        unique.append(v)
    return unique, selected_trade_rows


def _overlay_trade_row(row: dict[str, Any], overlay_id: str, *, kept: bool, skip_reason: str | None) -> dict[str, Any]:
    out = dict(row)
    out.update({
        "event_type": TRADE_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "overlay_id": overlay_id,
        "trade_kept_by_overlay": kept,
        "skip_reason": skip_reason,
        "orders_submitted_by_lsr_v2_risk_overlay": 0,
        "positions_opened_by_lsr_v2_risk_overlay": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "audit_only": True,
        "promotion_ready": False,
    })
    return out


def _select_best_variant(variants: Sequence[dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> dict[str, Any] | None:
    candidates = [v for v in variants if v.get("overlay_id") != "baseline_no_overlay" and not v.get("oracle_overlay")]
    valid = [v for v in candidates if v.get("overlay_valid")]
    pool = valid if valid else candidates
    if not pool:
        return None
    return sorted(
        pool,
        key=lambda v: (
            not bool(v.get("overlay_valid")),
            -_safe_float(v.get("drawdown_reduction_ratio"), 0.0),
            -_safe_float(v.get("profit_retention_ratio"), 0.0),
            _safe_float(v.get("max_drawdown_r"), 999.0),
            -_safe_float(v.get("sum_r_post_cost"), 0.0),
        ),
    )[0]


def _selection_report(variants: Sequence[dict[str, Any]], settings: LSRV2RiskOverlayAblationSettings) -> dict[str, Any]:
    baseline = next((v for v in variants if v.get("overlay_id") == "baseline_no_overlay"), {})
    non_oracle = [v for v in variants if v.get("overlay_id") != "baseline_no_overlay" and not v.get("oracle_overlay")]
    oracle = [v for v in variants if v.get("oracle_overlay")]
    valid = [v for v in non_oracle if v.get("overlay_valid")]
    best = _select_best_variant(variants, settings)
    best_oracle = sorted(
        oracle,
        key=lambda v: (-_safe_float(v.get("drawdown_reduction_ratio"), 0.0), -_safe_float(v.get("sum_r_post_cost"), 0.0)),
    )[0] if oracle else None
    return {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if variants else "WARN",
        "decision": "LSR_V2_RISK_OVERLAY_SELECTION_READY" if variants else NO_TRADES_DECISION,
        "created_at": utc_now_iso(),
        "baseline": baseline,
        "variant_count": len(variants),
        "non_oracle_variant_count": len(non_oracle),
        "oracle_variant_count": len(oracle),
        "valid_non_oracle_overlay_count": len(valid),
        "best_overlay": best,
        "best_oracle_overlay": best_oracle,
        "minimum_criteria": {
            "min_drawdown_reduction_ratio": settings.min_drawdown_reduction_ratio,
            "max_consecutive_losses_limit": settings.max_consecutive_losses_limit,
            "min_profit_retention_ratio": settings.min_profit_retention_ratio,
            "min_trades_kept_ratio": settings.min_trades_kept_ratio,
        },
        "audit_only": True,
        "promotion_ready": False,
        "orders_submitted_by_lsr_v2_risk_overlay_selection": 0,
        "positions_opened_by_lsr_v2_risk_overlay_selection": 0,
    }


def _classify(variants: Sequence[dict[str, Any]], attribution_report: dict[str, Any], settings: LSRV2RiskOverlayAblationSettings) -> tuple[str, list[str], list[str]]:
    baseline = next((v for v in variants if v.get("overlay_id") == "baseline_no_overlay"), {})
    non_oracle = [v for v in variants if v.get("overlay_id") != "baseline_no_overlay" and not v.get("oracle_overlay")]
    valid = [v for v in non_oracle if v.get("overlay_valid")]
    blockers: list[str] = []
    labels: list[str] = []
    inherited = list(attribution_report.get("blockers") or []) if isinstance(attribution_report, dict) else []
    for blocker in inherited:
        if isinstance(blocker, str) and blocker not in blockers:
            blockers.append(f"inherited_{blocker}")
    baseline_sum = _safe_float(baseline.get("sum_r_post_cost"), 0.0)
    baseline_dd = _safe_float(baseline.get("max_drawdown_r"), 0.0)
    baseline_streak = _safe_int(baseline.get("max_consecutive_losses"), 0)
    if baseline_sum <= 0:
        labels.append("BASELINE_NET_NEGATIVE")
        return REJECT_DECISION, labels, blockers or ["baseline_net_negative"]
    if baseline_dd > settings.max_drawdown_r:
        blockers.append("baseline_drawdown_above_limit")
        labels.append("BASELINE_DRAWDOWN_ABOVE_LIMIT")
    if baseline_streak > settings.max_consecutive_losses_limit:
        blockers.append("baseline_loss_streak_above_limit")
        labels.append("BASELINE_LOSS_STREAK_ABOVE_LIMIT")
    if not valid:
        if non_oracle and all(_safe_float(v.get("sum_r_post_cost"), 0.0) <= 0 or _safe_float(v.get("profit_retention_ratio"), 0.0) < settings.min_profit_retention_ratio for v in non_oracle):
            labels.append("EDGE_DESTROYED_BY_OVERLAY")
            return EDGE_DESTROYED_DECISION, list(dict.fromkeys(labels)), blockers or ["overlay_edge_destroyed"]
        if non_oracle and max((_safe_float(v.get("drawdown_reduction_ratio"), 0.0) for v in non_oracle), default=0.0) < settings.min_drawdown_reduction_ratio:
            labels.append("DRAWDOWN_REMAINS_HIGH")
            return DRAWDOWN_REMAINS_DECISION, list(dict.fromkeys(labels)), blockers or ["drawdown_reduction_below_minimum"]
        labels.append("OVERLAY_INSUFFICIENT")
        return INSUFFICIENT_DECISION, list(dict.fromkeys(labels)), blockers or ["no_valid_overlay"]
    labels.append("RISK_OVERLAY_RESEARCH_READY")
    if blockers:
        labels.append("BASELINE_RISK_BLOCKED_BUT_OVERLAY_CANDIDATE_FOUND")
    return READY_DECISION, list(dict.fromkeys(labels)), blockers


def _safe_empty_report(settings: LSRV2RiskOverlayAblationSettings, paths: dict[str, Path], reason: str) -> dict[str, Any]:
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
        "primary_trade_count": 0,
        "severe_trade_count": 0,
        "variant_count": 0,
        "orders_submitted_by_lsr_v2_risk_overlay_ablation": 0,
        "positions_opened_by_lsr_v2_risk_overlay_ablation": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(paths["report"]),
        "variants_report": str(paths["variants"]),
        "trades_jsonl": str(paths["trades"]),
        "selection_report": str(paths["selection"]),
    }
    empty = {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_TRADES_DECISION, "created_at": created, "promotion_ready": False}
    _write_json(paths["report"], report)
    _write_json(paths["variants"], empty)
    _write_json(paths["selection"], empty)
    _write_jsonl(paths["trades"], [])
    return report


def run_lsr_v2_risk_overlay_ablation(settings: LSRV2RiskOverlayAblationSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2RiskOverlayAblationSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": data_dir / REPORT_NAME,
        "variants": data_dir / VARIANTS_REPORT_NAME,
        "trades": data_dir / TRADES_JSONL_NAME,
        "selection": data_dir / SELECTION_REPORT_NAME,
    }
    trades_path = Path(settings.trades_path) if settings.trades_path else data_dir / INPUT_TRADES_NAME
    attribution_path = Path(settings.attribution_report_path) if settings.attribution_report_path else data_dir / ATTRIBUTION_REPORT_NAME

    try:
        raw_rows = _read_jsonl(trades_path)
        if not raw_rows:
            return _safe_empty_report(settings, paths, "no_sample_expansion_trade_rows")
        locked_rows = _filter_locked(raw_rows)
        primary = _dedupe([r for r in locked_rows if str(r.get("cost_model")) == settings.primary_cost_model])
        severe = _dedupe([r for r in locked_rows if str(r.get("cost_model")) == settings.severe_cost_model])
        if not primary:
            return _safe_empty_report(settings, paths, "no_primary_cost_model_trades")
        attribution_report = _read_json(attribution_path)
        variants, selected_trade_rows = _build_overlay_variants(primary, severe, settings)
        selection = _selection_report(variants, settings)
        decision, labels, blockers = _classify(variants, attribution_report, settings)
        best = selection.get("best_overlay") or {}
        baseline = selection.get("baseline") or {}
        written_trade_rows = _write_jsonl(paths["trades"], selected_trade_rows, max_rows=settings.max_trade_rows_to_write)
        variants_payload = {
            "prompt_id": PROMPT_ID,
            "status": "PASS",
            "decision": "LSR_V2_RISK_OVERLAY_VARIANTS_READY",
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "variant_count": len(variants),
            "variants": variants,
            "audit_only": True,
            "promotion_ready": False,
            "orders_submitted_by_lsr_v2_risk_overlay_variants": 0,
            "positions_opened_by_lsr_v2_risk_overlay_variants": 0,
            "report": str(paths["variants"]),
        }
        _write_json(paths["variants"], variants_payload)
        _write_json(paths["selection"], {**selection, "report": str(paths["selection"])})
        report = {
            "prompt_id": PROMPT_ID,
            "status": "PASS",
            "decision": decision,
            "classification_labels": labels,
            "blockers": blockers,
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "settings": asdict(settings),
            "input_trades_path": str(trades_path),
            "attribution_report_path": str(attribution_path),
            "attribution_decision": attribution_report.get("decision"),
            "attribution_blockers": attribution_report.get("blockers", []),
            "raw_trade_rows": len(raw_rows),
            "locked_trade_rows": len(locked_rows),
            "primary_trade_count": len(primary),
            "severe_trade_count": len(severe),
            "variant_count": len(variants),
            "valid_overlay_count": selection.get("valid_non_oracle_overlay_count", 0),
            "oracle_variant_count": selection.get("oracle_variant_count", 0),
            "baseline_sum_r_post_cost": baseline.get("sum_r_post_cost"),
            "baseline_avg_r_post_cost": baseline.get("avg_r_post_cost"),
            "baseline_max_drawdown_r": baseline.get("max_drawdown_r"),
            "baseline_max_consecutive_losses": baseline.get("max_consecutive_losses"),
            "best_overlay_id": best.get("overlay_id"),
            "best_overlay_family": best.get("overlay_family"),
            "best_overlay_valid": best.get("overlay_valid", False),
            "best_overlay_oracle": best.get("oracle_overlay", False),
            "best_overlay_trades_kept": best.get("trades_kept"),
            "best_overlay_trades_filtered": best.get("trades_filtered"),
            "best_overlay_sum_r_post_cost": best.get("sum_r_post_cost"),
            "best_overlay_avg_r_post_cost": best.get("avg_r_post_cost"),
            "best_overlay_max_drawdown_r": best.get("max_drawdown_r"),
            "best_overlay_max_consecutive_losses": best.get("max_consecutive_losses"),
            "best_overlay_profit_retention_ratio": best.get("profit_retention_ratio"),
            "best_overlay_drawdown_reduction_ratio": best.get("drawdown_reduction_ratio"),
            "best_overlay_cost_degradation_ratio": best.get("cost_degradation_ratio"),
            "best_overlay_severe_positive_ratio": best.get("severe_positive_ratio"),
            "written_overlay_trade_rows": written_trade_rows,
            "orders_submitted_by_lsr_v2_risk_overlay_ablation": 0,
            "positions_opened_by_lsr_v2_risk_overlay_ablation": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "submit_order": False,
            "broker_submit_called": False,
            "promotion_ready": False,
            "promotion_blocked_reason": "risk overlay ablation is diagnostic; no runtime or paper execution promotion is allowed here",
            "report": str(paths["report"]),
            "variants_report": str(paths["variants"]),
            "trades_jsonl": str(paths["trades"]),
            "selection_report": str(paths["selection"]),
        }
        _write_json(paths["report"], report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": [],
            "blockers": ["risk_overlay_ablation_error"],
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "orders_submitted_by_lsr_v2_risk_overlay_ablation": 0,
            "positions_opened_by_lsr_v2_risk_overlay_ablation": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(paths["report"]),
            "variants_report": str(paths["variants"]),
            "trades_jsonl": str(paths["trades"]),
            "selection_report": str(paths["selection"]),
        }
        _write_json(paths["report"], report)
        _write_json(paths["variants"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_json(paths["selection"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_jsonl(paths["trades"], [])
        return report


__all__ = [
    "LOCKED_PROFILE_NAME",
    "LOCKED_VARIANT_ID",
    "LSRV2RiskOverlayAblationSettings",
    "run_lsr_v2_risk_overlay_ablation",
]
