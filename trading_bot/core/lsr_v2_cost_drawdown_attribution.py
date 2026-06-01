"""Prompt 29.4.4s-8b — LSR-v2 cost degradation and drawdown attribution audit.

Diagnostic-only attribution layer for the locked LSR-v2 research profile:
LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24.

The audit consumes trade rows produced by the sample-expansion/robustness
pipeline and explains two remaining blockers from Prompt 29.4.4s-8:

* cost degradation under the severe cost model;
* excessive drawdown under the primary/conservative cost model.

The module is deliberately forensic. It must never submit orders, open
positions, mutate paper state, route signals, call a broker, lower runtime
thresholds, enable live/testnet paths, or promote a strategy by itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import hashlib
import json
import math

PROMPT_ID = "29.4.4s-8b"
LOCKED_PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
LOCKED_VARIANT_ID = "retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24"

INPUT_TRADES_NAME = "lsr_v2_sample_expansion_trades.jsonl"
ROBUSTNESS_REPORT_NAME = "lsr_v2_robustness_validation_report.json"

REPORT_NAME = "lsr_v2_cost_drawdown_attribution_report.json"
COST_DEGRADATION_REPORT_NAME = "lsr_v2_cost_degradation_attribution_report.json"
DRAWDOWN_ATTRIBUTION_REPORT_NAME = "lsr_v2_drawdown_attribution_report.json"
DRAWDOWN_SEGMENTS_NAME = "lsr_v2_drawdown_segments.jsonl"
RISK_OVERLAY_PREFLIGHT_REPORT_NAME = "lsr_v2_risk_overlay_preflight_report.json"

READY_DECISION = "LSR_V2_COST_DRAWDOWN_ATTRIBUTION_READY"
COST_CONFIRMED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COST_DEGRADATION_CONFIRMED"
DRAWDOWN_CLUSTERED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_CLUSTERED"
RISK_OVERLAY_REQUIRED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_RISK_OVERLAY_REQUIRED"
REJECT_DECISION = "REJECT_LSR_V2_OPERATIONALLY_UNSTABLE"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COST_DRAWDOWN_NO_TRADES"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COST_DRAWDOWN_ERROR"


@dataclass(frozen=True)
class LSRV2CostDrawdownAttributionSettings:
    data_dir: str = "data"
    trades_path: str | None = None
    robustness_report_path: str | None = None
    primary_cost_model: str = "conservative"
    severe_cost_model: str = "severe"
    max_drawdown_r: float = 25.0
    min_severe_positive_ratio: float = 0.45
    max_cost_degradation_ratio: float = 0.85
    breakeven_r_abs: float = 0.10
    min_segment_depth_r: float = 2.0
    max_drawdown_segment_share: float = 0.65
    max_group_loss_share: float = 0.60
    max_consecutive_losses_limit: int = 8
    min_primary_trades: int = 50
    max_segments_to_write: int = 10_000

    @classmethod
    def default(cls) -> "LSRV2CostDrawdownAttributionSettings":
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


def _group_value(row: dict[str, Any], key: str) -> str:
    if key == "asset":
        return _dataset(row)[0]
    if key == "timeframe":
        return _dataset(row)[1]
    if key == "side":
        return str(row.get("side") or "UNKNOWN")
    if key == "window":
        return str(row.get("window_label") or row.get("window_size") or "UNKNOWN")
    if key == "exit_reason":
        return str(row.get("exit_reason") or "UNKNOWN")
    if key == "asset_timeframe":
        s, tf = _dataset(row)
        return f"{s}|{tf}"
    return str(row.get(key) or "UNKNOWN")


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _basic_summary(rows: Sequence[dict[str, Any]], settings: LSRV2CostDrawdownAttributionSettings) -> dict[str, Any]:
    net = [_safe_float(r.get("net_r"), 0.0) for r in rows]
    wins = [x for x in net if x > settings.breakeven_r_abs]
    losses = [x for x in net if x < -settings.breakeven_r_abs]
    breakevens = [x for x in net if abs(x) <= settings.breakeven_r_abs]
    return {
        "closed_trades": len(rows),
        "sum_r_post_cost": _round(sum(net), 8),
        "avg_r_post_cost": _round(_avg(net) or 0.0, 8),
        "median_r_post_cost": _round(_median(net) or 0.0, 8),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), len(rows), 0.0) or 0.0, 8),
        "loss_rate": _round(_safe_div(len(losses), len(rows), 0.0) or 0.0, 8),
        "breakeven_rate": _round(_safe_div(len(breakevens), len(rows), 0.0) or 0.0, 8),
        "max_drawdown_r": _round(_max_drawdown(net), 8),
    }


def _group_summary(rows: Sequence[dict[str, Any]], key: str, settings: LSRV2CostDrawdownAttributionSettings) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_group_value(row, key), []).append(row)
    out: list[dict[str, Any]] = []
    for value, group_rows in groups.items():
        summary = _basic_summary(group_rows, settings)
        summary.update({
            "group_key": key,
            "group_value": value,
            "negative_sum_r": _round(sum(min(0.0, _safe_float(r.get("net_r"), 0.0)) for r in group_rows), 8),
            "positive_sum_r": _round(sum(max(0.0, _safe_float(r.get("net_r"), 0.0)) for r in group_rows), 8),
            "first_entry_timestamp": str(_trade_sort_key(group_rows[0])[0]) if group_rows else None,
            "last_entry_timestamp": str(_trade_sort_key(group_rows[-1])[0]) if group_rows else None,
        })
        out.append(summary)
    return sorted(out, key=lambda x: (_safe_float(x.get("sum_r_post_cost"), 0.0), -_safe_int(x.get("closed_trades"), 0)))


def _group_loss_share(groups: Sequence[dict[str, Any]]) -> float:
    losses = [abs(_safe_float(g.get("negative_sum_r"), 0.0)) for g in groups]
    total_loss = sum(losses)
    if total_loss <= 1e-12:
        return 0.0
    return max(losses) / total_loss


def _cost_degradation_attribution(primary_rows: Sequence[dict[str, Any]], severe_rows: Sequence[dict[str, Any]], settings: LSRV2CostDrawdownAttributionSettings) -> dict[str, Any]:
    primary_by = {_pair_key(r): r for r in primary_rows}
    severe_by = {_pair_key(r): r for r in severe_rows}
    paired_keys = sorted(set(primary_by) & set(severe_by))
    paired: list[dict[str, Any]] = []
    for key in paired_keys:
        p = primary_by[key]
        s = severe_by[key]
        p_net = _safe_float(p.get("net_r"), 0.0)
        s_net = _safe_float(s.get("net_r"), 0.0)
        row = dict(p)
        row.update({
            "pair_key": key,
            "primary_net_r": p_net,
            "severe_net_r": s_net,
            "delta_r_primary_minus_severe": p_net - s_net,
            "primary_win_to_severe_loss": bool(p_net > settings.breakeven_r_abs and s_net < -settings.breakeven_r_abs),
            "primary_win_to_severe_nonwin": bool(p_net > settings.breakeven_r_abs and s_net <= settings.breakeven_r_abs),
            "severe_negative": bool(s_net < -settings.breakeven_r_abs),
        })
        paired.append(row)

    primary_net = [r["primary_net_r"] for r in paired]
    severe_net = [r["severe_net_r"] for r in paired]
    deltas = [r["delta_r_primary_minus_severe"] for r in paired]
    p_sum = sum(primary_net)
    s_sum = sum(severe_net)
    severe_positive_ratio = _safe_div(sum(1 for x in severe_net if x > settings.breakeven_r_abs), len(severe_net), 0.0) or 0.0
    degradation_ratio = _safe_div(p_sum - s_sum, abs(p_sum), 999.0) if abs(p_sum) > 1e-12 else 999.0

    by: dict[str, list[dict[str, Any]]] = {}
    group_reports: dict[str, list[dict[str, Any]]] = {}
    for key in ("asset", "timeframe", "side", "window", "exit_reason", "asset_timeframe"):
        by.clear()
        for row in paired:
            by.setdefault(_group_value(row, key), []).append(row)
        rows: list[dict[str, Any]] = []
        for value, group_rows in by.items():
            gp = [r["primary_net_r"] for r in group_rows]
            gs = [r["severe_net_r"] for r in group_rows]
            gd = [r["delta_r_primary_minus_severe"] for r in group_rows]
            rows.append({
                "group_key": key,
                "group_value": value,
                "paired_trade_count": len(group_rows),
                "primary_sum_r_post_cost": _round(sum(gp), 8),
                "severe_sum_r_post_cost": _round(sum(gs), 8),
                "delta_sum_r": _round(sum(gd), 8),
                "avg_delta_r": _round(_avg(gd) or 0.0, 8),
                "severe_negative_ratio": _round(_safe_div(sum(1 for x in gs if x < -settings.breakeven_r_abs), len(gs), 0.0) or 0.0, 8),
                "primary_win_to_severe_loss_count": sum(1 for r in group_rows if r["primary_win_to_severe_loss"]),
                "primary_win_to_severe_nonwin_count": sum(1 for r in group_rows if r["primary_win_to_severe_nonwin"]),
                "cost_degradation_ratio": _round((_safe_div(sum(gp) - sum(gs), abs(sum(gp)), 999.0) if abs(sum(gp)) > 1e-12 else 999.0), 8),
            })
        group_reports[key] = sorted(rows, key=lambda x: _safe_float(x.get("delta_sum_r"), 0.0), reverse=True)

    non_destructive = bool(s_sum > 0 and severe_positive_ratio >= settings.min_severe_positive_ratio and (degradation_ratio or 999.0) <= settings.max_cost_degradation_ratio)
    worst_cost_groups = {
        key: values[:5]
        for key, values in group_reports.items()
    }
    return {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if paired else "WARN",
        "decision": "LSR_V2_COST_DEGRADATION_ATTRIBUTION_READY" if paired else NO_TRADES_DECISION,
        "created_at": utc_now_iso(),
        "paired_trade_count": len(paired),
        "primary_sum_r_post_cost": _round(p_sum, 8),
        "severe_sum_r_post_cost": _round(s_sum, 8),
        "primary_avg_r_post_cost": _round(_avg(primary_net) or 0.0, 8),
        "severe_avg_r_post_cost": _round(_avg(severe_net) or 0.0, 8),
        "sum_delta_r_primary_minus_severe": _round(sum(deltas), 8),
        "avg_delta_r_primary_minus_severe": _round(_avg(deltas) or 0.0, 8),
        "median_delta_r_primary_minus_severe": _round(_median(deltas) or 0.0, 8),
        "severe_positive_ratio": _round(severe_positive_ratio, 8),
        "severe_negative_ratio": _round(_safe_div(sum(1 for x in severe_net if x < -settings.breakeven_r_abs), len(severe_net), 0.0) or 0.0, 8),
        "cost_degradation_ratio": _round(degradation_ratio or 999.0, 8),
        "cost_degradation_non_destructive": non_destructive,
        "primary_win_to_severe_loss_count": sum(1 for r in paired if r["primary_win_to_severe_loss"]),
        "primary_win_to_severe_nonwin_count": sum(1 for r in paired if r["primary_win_to_severe_nonwin"]),
        "group_reports": group_reports,
        "worst_cost_groups": worst_cost_groups,
        "orders_submitted_by_lsr_v2_cost_degradation_attribution": 0,
        "positions_opened_by_lsr_v2_cost_degradation_attribution": 0,
        "audit_only": True,
        "promotion_ready": False,
    }


def _drawdown_segments(rows: Sequence[dict[str, Any]], settings: LSRV2CostDrawdownAttributionSettings) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    equity = 0.0
    peak = 0.0
    peak_idx = -1
    current: dict[str, Any] | None = None
    segments: list[dict[str, Any]] = []
    max_consecutive_losses = 0
    current_loss_streak = 0

    for i, row in enumerate(rows):
        net = _safe_float(row.get("net_r"), 0.0)
        prev_equity = equity
        equity += net
        if net < -settings.breakeven_r_abs:
            current_loss_streak += 1
            max_consecutive_losses = max(max_consecutive_losses, current_loss_streak)
        elif net > settings.breakeven_r_abs:
            current_loss_streak = 0

        if equity >= peak:
            if current and _safe_float(current.get("depth_r"), 0.0) >= settings.min_segment_depth_r:
                current["recovery_trade_index"] = i
                current["recovery_entry_timestamp"] = str(row.get("entry_timestamp") or "")
                segments.append(current)
            peak = equity
            peak_idx = i
            current = None
            continue

        dd = peak - equity
        if current is None:
            start = rows[peak_idx] if 0 <= peak_idx < len(rows) else row
            current = {
                "event_type": "LSR_V2_DRAWDOWN_SEGMENT",
                "prompt_id": PROMPT_ID,
                "segment_index": len(segments) + 1,
                "start_peak_trade_index": peak_idx,
                "start_peak_entry_timestamp": str(start.get("entry_timestamp") or ""),
                "trough_trade_index": i,
                "trough_entry_timestamp": str(row.get("entry_timestamp") or ""),
                "peak_equity_r": _round(peak, 8),
                "trough_equity_r": _round(equity, 8),
                "depth_r": _round(dd, 8),
                "duration_trades_to_trough": max(0, i - peak_idx),
                "recovery_trade_index": None,
                "recovery_entry_timestamp": None,
                "recovered": False,
                "orders_submitted_by_lsr_v2_drawdown_attribution": 0,
                "positions_opened_by_lsr_v2_drawdown_attribution": 0,
                "audit_only": True,
            }
        elif dd > _safe_float(current.get("depth_r"), 0.0):
            current.update({
                "trough_trade_index": i,
                "trough_entry_timestamp": str(row.get("entry_timestamp") or ""),
                "trough_equity_r": _round(equity, 8),
                "depth_r": _round(dd, 8),
                "duration_trades_to_trough": max(0, i - _safe_int(current.get("start_peak_trade_index"), i)),
            })

    if current and _safe_float(current.get("depth_r"), 0.0) >= settings.min_segment_depth_r:
        current["recovered"] = False
        segments.append(current)
    for idx, seg in enumerate(segments, start=1):
        seg["segment_index"] = idx
        seg["recovered"] = seg.get("recovery_trade_index") is not None
        start = max(0, _safe_int(seg.get("start_peak_trade_index"), 0))
        trough = min(len(rows) - 1, max(start, _safe_int(seg.get("trough_trade_index"), start)))
        subset = rows[start : trough + 1]
        seg["asset_loss_contribution"] = _loss_contribution(subset, "asset")
        seg["timeframe_loss_contribution"] = _loss_contribution(subset, "timeframe")
        seg["side_loss_contribution"] = _loss_contribution(subset, "side")
        seg["exit_reason_loss_contribution"] = _loss_contribution(subset, "exit_reason")
    net = [_safe_float(r.get("net_r"), 0.0) for r in rows]
    worst = max((_safe_float(s.get("depth_r"), 0.0) for s in segments), default=_max_drawdown(net))
    total_segment_depth = sum(_safe_float(s.get("depth_r"), 0.0) for s in segments)
    worst_share = _safe_div(worst, total_segment_depth, 0.0) if total_segment_depth > 1e-12 else 0.0
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if rows else "WARN",
        "decision": "LSR_V2_DRAWDOWN_ATTRIBUTION_READY" if rows else NO_TRADES_DECISION,
        "created_at": utc_now_iso(),
        "closed_trades": len(rows),
        "sum_r_post_cost": _round(sum(net), 8),
        "max_drawdown_r": _round(_max_drawdown(net), 8),
        "max_drawdown_limit_r": _round(settings.max_drawdown_r, 8),
        "max_drawdown_above_limit": bool(_max_drawdown(net) > settings.max_drawdown_r),
        "drawdown_segment_count": len(segments),
        "worst_segment_depth_r": _round(worst, 8),
        "worst_segment_depth_share": _round(worst_share or 0.0, 8),
        "drawdown_clustered": bool((worst_share or 0.0) >= settings.max_drawdown_segment_share and len(segments) > 0),
        "max_consecutive_losses": max_consecutive_losses,
        "max_consecutive_losses_above_limit": bool(max_consecutive_losses > settings.max_consecutive_losses_limit),
        "loss_groups": {
            "asset": _group_summary(rows, "asset", settings),
            "timeframe": _group_summary(rows, "timeframe", settings),
            "side": _group_summary(rows, "side", settings),
            "asset_timeframe": _group_summary(rows, "asset_timeframe", settings),
            "exit_reason": _group_summary(rows, "exit_reason", settings),
        },
        "group_loss_share": {},
        "orders_submitted_by_lsr_v2_drawdown_attribution": 0,
        "positions_opened_by_lsr_v2_drawdown_attribution": 0,
        "audit_only": True,
        "promotion_ready": False,
    }
    report["group_loss_share"] = {
        key: _round(_group_loss_share(value), 8)
        for key, value in report["loss_groups"].items()
    }
    return report, segments


def _loss_contribution(rows: Sequence[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, float] = {}
    for row in rows:
        loss = min(0.0, _safe_float(row.get("net_r"), 0.0))
        if loss < 0:
            groups[_group_value(row, key)] = groups.get(_group_value(row, key), 0.0) + abs(loss)
    total = sum(groups.values())
    if total <= 1e-12:
        return []
    return [
        {"group_value": value, "loss_r": _round(loss, 8), "loss_share": _round(loss / total, 8)}
        for value, loss in sorted(groups.items(), key=lambda x: x[1], reverse=True)
    ]


def _simulate_pause_after_loss_streak(rows: Sequence[dict[str, Any]], *, streak_limit: int, pause_trades: int, settings: LSRV2CostDrawdownAttributionSettings) -> dict[str, Any]:
    executed: list[dict[str, Any]] = []
    skipped = 0
    streak = 0
    pause_left = 0
    for row in rows:
        if pause_left > 0:
            skipped += 1
            pause_left -= 1
            continue
        executed.append(row)
        net = _safe_float(row.get("net_r"), 0.0)
        if net < -settings.breakeven_r_abs:
            streak += 1
        elif net > settings.breakeven_r_abs:
            streak = 0
        if streak >= streak_limit:
            pause_left = pause_trades
            streak = 0
    return _overlay_summary(f"pause_after_{streak_limit}_losses_skip_{pause_trades}", executed, skipped, rows, settings)


def _simulate_pause_after_drawdown(rows: Sequence[dict[str, Any]], *, dd_limit: float, pause_trades: int, settings: LSRV2CostDrawdownAttributionSettings) -> dict[str, Any]:
    executed: list[dict[str, Any]] = []
    skipped = 0
    pause_left = 0
    equity = 0.0
    peak = 0.0
    for row in rows:
        if pause_left > 0:
            skipped += 1
            pause_left -= 1
            continue
        executed.append(row)
        equity += _safe_float(row.get("net_r"), 0.0)
        peak = max(peak, equity)
        if peak - equity >= dd_limit:
            pause_left = pause_trades
            peak = equity
    return _overlay_summary(f"pause_after_{dd_limit:g}r_drawdown_skip_{pause_trades}", executed, skipped, rows, settings)


def _simulate_exclude_worst_group(rows: Sequence[dict[str, Any]], *, group_key: str, settings: LSRV2CostDrawdownAttributionSettings) -> dict[str, Any]:
    groups = _group_summary(rows, group_key, settings)
    if not groups:
        return _overlay_summary(f"exclude_worst_{group_key}", rows, 0, rows, settings)
    worst = groups[0]["group_value"]
    executed = [r for r in rows if _group_value(r, group_key) != worst]
    skipped = len(rows) - len(executed)
    summary = _overlay_summary(f"exclude_worst_{group_key}", executed, skipped, rows, settings)
    summary["excluded_group_value"] = worst
    summary["diagnostic_only_oracle_overlay"] = True
    return summary


def _overlay_summary(name: str, executed: Sequence[dict[str, Any]], skipped: int, baseline: Sequence[dict[str, Any]], settings: LSRV2CostDrawdownAttributionSettings) -> dict[str, Any]:
    base_sum = sum(_safe_float(r.get("net_r"), 0.0) for r in baseline)
    base_dd = _max_drawdown([_safe_float(r.get("net_r"), 0.0) for r in baseline])
    summary = _basic_summary(executed, settings)
    new_sum = _safe_float(summary.get("sum_r_post_cost"), 0.0)
    new_dd = _safe_float(summary.get("max_drawdown_r"), 0.0)
    return {
        "overlay_name": name,
        "executed_trades": len(executed),
        "skipped_trades": skipped,
        "skipped_ratio": _round(_safe_div(skipped, len(baseline), 0.0) or 0.0, 8),
        "sum_r_post_cost": _round(new_sum, 8),
        "avg_r_post_cost": summary.get("avg_r_post_cost"),
        "max_drawdown_r": _round(new_dd, 8),
        "delta_sum_r_vs_baseline": _round(new_sum - base_sum, 8),
        "delta_drawdown_r_vs_baseline": _round(new_dd - base_dd, 8),
        "drawdown_reduced": bool(new_dd < base_dd),
        "pnl_preserved": bool(new_sum > 0 and new_sum >= base_sum * 0.75),
        "risk_overlay_candidate": bool(new_dd < base_dd and new_sum > 0),
        "audit_only": True,
        "submit_order": False,
        "broker_submit_called": False,
    }


def _risk_overlay_preflight(rows: Sequence[dict[str, Any]], settings: LSRV2CostDrawdownAttributionSettings) -> dict[str, Any]:
    overlays = [
        _overlay_summary("baseline_no_overlay", rows, 0, rows, settings),
        _simulate_pause_after_loss_streak(rows, streak_limit=3, pause_trades=3, settings=settings),
        _simulate_pause_after_loss_streak(rows, streak_limit=4, pause_trades=5, settings=settings),
        _simulate_pause_after_drawdown(rows, dd_limit=max(5.0, settings.max_drawdown_r * 0.40), pause_trades=5, settings=settings),
        _simulate_pause_after_drawdown(rows, dd_limit=max(8.0, settings.max_drawdown_r * 0.60), pause_trades=8, settings=settings),
        _simulate_exclude_worst_group(rows, group_key="asset_timeframe", settings=settings),
        _simulate_exclude_worst_group(rows, group_key="side", settings=settings),
    ]
    candidates = [o for o in overlays[1:] if o.get("risk_overlay_candidate")]
    candidates_sorted = sorted(candidates, key=lambda x: (_safe_float(x.get("max_drawdown_r"), 999.0), -_safe_float(x.get("sum_r_post_cost"), 0.0)))
    return {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if rows else "WARN",
        "decision": "LSR_V2_RISK_OVERLAY_PREFLIGHT_READY" if rows else NO_TRADES_DECISION,
        "created_at": utc_now_iso(),
        "overlay_count": len(overlays),
        "candidate_overlay_count": len(candidates),
        "best_overlay": candidates_sorted[0] if candidates_sorted else None,
        "overlays": overlays,
        "orders_submitted_by_lsr_v2_risk_overlay_preflight": 0,
        "positions_opened_by_lsr_v2_risk_overlay_preflight": 0,
        "audit_only": True,
        "promotion_ready": False,
    }


def _classify(
    *,
    primary_rows: Sequence[dict[str, Any]],
    robustness_report: dict[str, Any],
    cost_report: dict[str, Any],
    drawdown_report: dict[str, Any],
    risk_report: dict[str, Any],
    settings: LSRV2CostDrawdownAttributionSettings,
) -> tuple[str, list[str], list[str]]:
    labels: list[str] = []
    blockers: list[str] = []
    inherited = list(robustness_report.get("blockers") or []) if isinstance(robustness_report, dict) else []
    for blocker in inherited:
        if isinstance(blocker, str) and blocker not in blockers:
            blockers.append(f"inherited_{blocker}")
    if len(primary_rows) < settings.min_primary_trades:
        blockers.append("primary_trades_below_minimum")
        labels.append("LOW_SAMPLE")
    if not cost_report.get("cost_degradation_non_destructive", False):
        blockers.append("cost_degradation_confirmed")
        labels.append("COST_DEGRADATION_CONFIRMED")
    if drawdown_report.get("max_drawdown_above_limit", False):
        blockers.append("max_drawdown_above_limit_confirmed")
        labels.append("DRAWDOWN_ABOVE_LIMIT")
    if drawdown_report.get("drawdown_clustered", False):
        blockers.append("drawdown_clustered")
        labels.append("DRAWDOWN_CLUSTERED")
    if drawdown_report.get("max_consecutive_losses_above_limit", False):
        blockers.append("max_consecutive_losses_above_limit")
        labels.append("LOSS_STREAK_RISK")
    if (risk_report.get("candidate_overlay_count") or 0) > 0 and ("max_drawdown_above_limit_confirmed" in blockers or "drawdown_clustered" in blockers):
        labels.append("RISK_OVERLAY_REQUIRED")

    # Hard reject only when the primary profile is net-negative or the drawdown is
    # larger than total positive edge, indicating an operationally unusable shape.
    primary_sum = sum(_safe_float(r.get("net_r"), 0.0) for r in primary_rows)
    positive_sum = sum(max(0.0, _safe_float(r.get("net_r"), 0.0)) for r in primary_rows)
    max_dd = _safe_float(drawdown_report.get("max_drawdown_r"), 0.0)
    if primary_sum <= 0 or (positive_sum > 0 and max_dd > positive_sum):
        labels.append("OPERATIONALLY_UNSTABLE")
        return REJECT_DECISION, list(dict.fromkeys(labels)), blockers or ["operational_instability"]

    if not blockers:
        return READY_DECISION, ["ATTRIBUTION_READY"], []
    if "RISK_OVERLAY_REQUIRED" in labels:
        return RISK_OVERLAY_REQUIRED_DECISION, list(dict.fromkeys(labels)), blockers
    if "drawdown_clustered" in blockers:
        return DRAWDOWN_CLUSTERED_DECISION, list(dict.fromkeys(labels)), blockers
    if "cost_degradation_confirmed" in blockers:
        return COST_CONFIRMED_DECISION, list(dict.fromkeys(labels)), blockers
    return RISK_OVERLAY_REQUIRED_DECISION, list(dict.fromkeys(labels)), blockers


def _safe_empty_report(settings: LSRV2CostDrawdownAttributionSettings, paths: dict[str, Path], reason: str) -> dict[str, Any]:
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
        "orders_submitted_by_lsr_v2_cost_drawdown_attribution": 0,
        "positions_opened_by_lsr_v2_cost_drawdown_attribution": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(paths["report"]),
        "cost_degradation_report": str(paths["cost"]),
        "drawdown_attribution_report": str(paths["drawdown"]),
        "drawdown_segments_jsonl": str(paths["segments"]),
        "risk_overlay_preflight_report": str(paths["risk"]),
    }
    empty = {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_TRADES_DECISION, "created_at": created, "promotion_ready": False}
    _write_json(paths["report"], report)
    _write_json(paths["cost"], empty)
    _write_json(paths["drawdown"], empty)
    _write_json(paths["risk"], empty)
    _write_jsonl(paths["segments"], [])
    return report


def run_lsr_v2_cost_drawdown_attribution(settings: LSRV2CostDrawdownAttributionSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2CostDrawdownAttributionSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "report": data_dir / REPORT_NAME,
        "cost": data_dir / COST_DEGRADATION_REPORT_NAME,
        "drawdown": data_dir / DRAWDOWN_ATTRIBUTION_REPORT_NAME,
        "segments": data_dir / DRAWDOWN_SEGMENTS_NAME,
        "risk": data_dir / RISK_OVERLAY_PREFLIGHT_REPORT_NAME,
    }
    trades_path = Path(settings.trades_path) if settings.trades_path else data_dir / INPUT_TRADES_NAME
    robustness_path = Path(settings.robustness_report_path) if settings.robustness_report_path else data_dir / ROBUSTNESS_REPORT_NAME

    try:
        raw_rows = _read_jsonl(trades_path)
        if not raw_rows:
            return _safe_empty_report(settings, paths, "no_sample_expansion_trade_rows")
        locked_rows = _filter_locked(raw_rows)
        primary = _dedupe([r for r in locked_rows if str(r.get("cost_model")) == settings.primary_cost_model])
        severe = _dedupe([r for r in locked_rows if str(r.get("cost_model")) == settings.severe_cost_model])
        if not primary:
            return _safe_empty_report(settings, paths, "no_primary_cost_model_trades")

        robustness_report = _read_json(robustness_path)
        cost_report = _cost_degradation_attribution(primary, severe, settings)
        drawdown_report, segments = _drawdown_segments(primary, settings)
        risk_report = _risk_overlay_preflight(primary, settings)
        decision, labels, blockers = _classify(
            primary_rows=primary,
            robustness_report=robustness_report,
            cost_report=cost_report,
            drawdown_report=drawdown_report,
            risk_report=risk_report,
            settings=settings,
        )
        _write_json(paths["cost"], {**cost_report, "report": str(paths["cost"])})
        _write_json(paths["drawdown"], {**drawdown_report, "report": str(paths["drawdown"]), "drawdown_segments_jsonl": str(paths["segments"])})
        written_segments = _write_jsonl(paths["segments"], segments, max_rows=settings.max_segments_to_write)
        _write_json(paths["risk"], {**risk_report, "report": str(paths["risk"])})

        primary_summary = _basic_summary(primary, settings)
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
            "robustness_report_path": str(robustness_path),
            "robustness_decision": robustness_report.get("decision"),
            "robustness_blockers": robustness_report.get("blockers", []),
            "raw_trade_rows": len(raw_rows),
            "locked_trade_rows": len(locked_rows),
            "primary_trade_count": len(primary),
            "severe_trade_count": len(severe),
            "primary_summary": primary_summary,
            "primary_sum_r_post_cost": primary_summary.get("sum_r_post_cost"),
            "primary_avg_r_post_cost": primary_summary.get("avg_r_post_cost"),
            "primary_max_drawdown_r": primary_summary.get("max_drawdown_r"),
            "cost_degradation_non_destructive": cost_report.get("cost_degradation_non_destructive", False),
            "cost_degradation_ratio": cost_report.get("cost_degradation_ratio"),
            "severe_positive_ratio": cost_report.get("severe_positive_ratio"),
            "max_drawdown_above_limit": drawdown_report.get("max_drawdown_above_limit", False),
            "drawdown_clustered": drawdown_report.get("drawdown_clustered", False),
            "max_consecutive_losses": drawdown_report.get("max_consecutive_losses"),
            "risk_overlay_candidate_count": risk_report.get("candidate_overlay_count", 0),
            "best_risk_overlay": risk_report.get("best_overlay"),
            "written_drawdown_segments": written_segments,
            "orders_submitted_by_lsr_v2_cost_drawdown_attribution": 0,
            "positions_opened_by_lsr_v2_cost_drawdown_attribution": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "submit_order": False,
            "broker_submit_called": False,
            "promotion_ready": False,
            "promotion_blocked_reason": "cost/drawdown attribution is diagnostic; no runtime or paper execution promotion is allowed here",
            "report": str(paths["report"]),
            "cost_degradation_report": str(paths["cost"]),
            "drawdown_attribution_report": str(paths["drawdown"]),
            "drawdown_segments_jsonl": str(paths["segments"]),
            "risk_overlay_preflight_report": str(paths["risk"]),
        }
        _write_json(paths["report"], report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": [],
            "blockers": ["cost_drawdown_attribution_error"],
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "orders_submitted_by_lsr_v2_cost_drawdown_attribution": 0,
            "positions_opened_by_lsr_v2_cost_drawdown_attribution": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(paths["report"]),
            "cost_degradation_report": str(paths["cost"]),
            "drawdown_attribution_report": str(paths["drawdown"]),
            "drawdown_segments_jsonl": str(paths["segments"]),
            "risk_overlay_preflight_report": str(paths["risk"]),
        }
        _write_json(paths["report"], report)
        _write_json(paths["cost"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_json(paths["drawdown"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_json(paths["risk"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_jsonl(paths["segments"], [])
        return report
