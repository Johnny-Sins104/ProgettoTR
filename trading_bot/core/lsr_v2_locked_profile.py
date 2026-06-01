"""Prompt 29.4.4s-7d — LSR-v2 locked profile validation preflight.

Diagnostic-only drilldown for the best execution variant found by s-7c:
LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24.  The module reruns only this
locked profile across the selected windows and cost models, then compares the
primary/conservative trades against severe-cost twins trade-by-trade.

It must never submit orders, open positions, mutate paper state, route signals,
call a broker, lower runtime thresholds, or enable live/testnet paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import json
import math

from core.liquidity_sweep_reversal_v2 import load_market_rows, normalize_timeframe_label
from core.lsr_v2_backtest_matrix import DEFAULT_WINDOWS, PRIMARY_VALIDATION_WINDOWS, parse_windows, selected_cost_scenarios
from core.lsr_v2_execution_ablation import (
    ExecutionVariant,
    LSRV2ExecutionAblationSettings,
    _candidate_selection_settings,
    _simulate_window,
)

PROMPT_ID = "29.4.4s-7d"
LOCKED_PROFILE_NAME = "LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24"
LOCKED_VARIANT_ID = "retest_entry_limit_like__stop_at_sweep_extreme__tp_fixed_2R__hold_24"
REPORT_NAME = "lsr_v2_locked_profile_report.json"
TRADES_JSONL_NAME = "lsr_v2_locked_profile_trades.jsonl"
COST_DRILLDOWN_NAME = "lsr_v2_locked_profile_cost_drilldown.json"
WINDOW_STABILITY_NAME = "lsr_v2_locked_profile_window_stability.json"

READY_DECISION = "LSR_V2_LOCKED_PROFILE_READY_FOR_WALK_FORWARD"
LOW_SAMPLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_LOW_SAMPLE"
COST_SENSITIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_COST_SENSITIVE"
OUTLIER_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_OUTLIER_DOMINATED"
REJECT_DECISION = "REJECT_LSR_V2_LOCKED_PROFILE"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_NO_TRADES"
NO_MARKET_DATA_DECISION = "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
NO_MATCHING_TIMEFRAME_DECISION = "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LOCKED_PROFILE_ERROR"


@dataclass(frozen=True)
class LSRV2LockedProfileSettings:
    data_dir: str = "data"
    input_path: str | None = None
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    max_rows: int = 250_000
    windows: tuple[int, ...] = DEFAULT_WINDOWS
    primary_windows: tuple[int, ...] = PRIMARY_VALIDATION_WINDOWS
    cost_models: tuple[str, ...] = ("base", "conservative", "severe")
    primary_cost_model: str = "conservative"
    severe_cost_model: str = "severe"
    starting_equity: float = 1000.0
    risk_per_trade_pct: float = 0.0025
    min_closed_trades: int = 30
    preferred_closed_trades: int = 50
    min_positive_windows: int = 3
    min_avg_r_post_cost: float = 0.0
    min_sum_r_post_cost: float = 0.0
    max_top_trade_concentration: float = 0.45
    max_drawdown_r: float = 10.0
    strong_negative_window_r: float = -3.0
    min_severe_positive_windows: int = 3
    require_severe_cost_survival: bool = True
    breakeven_r_abs: float = 0.10
    max_breakeven_ratio: float = 0.30
    max_cost_to_edge_ratio: float = 0.75
    strict_timeframe: bool = True
    allow_timeframe_fallback: bool = False
    max_trade_rows_to_write: int = 100_000
    pool_lookback: int = 20
    confirmation_window: int = 4
    retest_window: int = 6
    min_sweep_bps: float = 2.0
    retest_tolerance_bps: float = 8.0
    stop_buffer_bps: float = 2.0
    target_rr: float = 2.0
    min_rr: float = 1.5
    max_cost_to_r: float = 0.35
    require_volume_confirmation: bool = False
    require_retest_for_candidate_ready: bool = True
    atr_stop_buffer_multiple: float = 0.10
    structure_target_min_rr: float = 1.5
    structure_target_max_rr: float = 3.0

    @classmethod
    def default(cls) -> "LSRV2LockedProfileSettings":
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


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def locked_variant() -> ExecutionVariant:
    return ExecutionVariant(
        variant_id=LOCKED_VARIANT_ID,
        entry_policy="retest_entry_limit_like",
        stop_policy="stop_at_sweep_extreme",
        target_policy="tp_fixed_2R",
        max_holding_bars=24,
    )


def _ablation_settings(settings: LSRV2LockedProfileSettings) -> LSRV2ExecutionAblationSettings:
    return LSRV2ExecutionAblationSettings(
        data_dir=settings.data_dir,
        input_path=settings.input_path,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        max_rows=settings.max_rows,
        windows=settings.windows,
        primary_windows=settings.primary_windows,
        cost_models=settings.cost_models,
        primary_cost_model=settings.primary_cost_model,
        severe_cost_model=settings.severe_cost_model,
        starting_equity=settings.starting_equity,
        risk_per_trade_pct=settings.risk_per_trade_pct,
        min_closed_trades=settings.min_closed_trades,
        preferred_closed_trades=settings.preferred_closed_trades,
        min_positive_windows=settings.min_positive_windows,
        min_avg_r_post_cost=settings.min_avg_r_post_cost,
        min_sum_r_post_cost=settings.min_sum_r_post_cost,
        max_breakeven_ratio=settings.max_breakeven_ratio,
        breakeven_r_abs=settings.breakeven_r_abs,
        max_top_trade_concentration=settings.max_top_trade_concentration,
        max_drawdown_r=settings.max_drawdown_r,
        strong_negative_window_r=settings.strong_negative_window_r,
        require_severe_cost_survival=settings.require_severe_cost_survival,
        min_severe_positive_windows=settings.min_severe_positive_windows,
        max_cost_to_edge_ratio=settings.max_cost_to_edge_ratio,
        strict_timeframe=settings.strict_timeframe,
        allow_timeframe_fallback=settings.allow_timeframe_fallback,
        max_trade_rows_to_write=settings.max_trade_rows_to_write,
        pool_lookback=settings.pool_lookback,
        confirmation_window=settings.confirmation_window,
        retest_window=settings.retest_window,
        min_sweep_bps=settings.min_sweep_bps,
        retest_tolerance_bps=settings.retest_tolerance_bps,
        stop_buffer_bps=settings.stop_buffer_bps,
        target_rr=settings.target_rr,
        min_rr=settings.min_rr,
        max_cost_to_r=settings.max_cost_to_r,
        require_volume_confirmation=settings.require_volume_confirmation,
        require_retest_for_candidate_ready=settings.require_retest_for_candidate_ready,
        atr_stop_buffer_multiple=settings.atr_stop_buffer_multiple,
        structure_target_min_rr=settings.structure_target_min_rr,
        structure_target_max_rr=settings.structure_target_max_rr,
    )


def _primary_trades(trades: Sequence[dict[str, Any]], settings: LSRV2LockedProfileSettings) -> list[dict[str, Any]]:
    primary_windows = {int(w) for w in settings.primary_windows}
    return [
        t for t in trades
        if str(t.get("cost_model")) == settings.primary_cost_model
        and _safe_int(t.get("window_size"), 0) in primary_windows
        and str(t.get("variant_id")) == LOCKED_VARIANT_ID
    ]


def _trades_by_cost(trades: Sequence[dict[str, Any]], cost_model: str, settings: LSRV2LockedProfileSettings) -> list[dict[str, Any]]:
    primary_windows = {int(w) for w in settings.primary_windows}
    return [
        t for t in trades
        if str(t.get("cost_model")) == cost_model
        and _safe_int(t.get("window_size"), 0) in primary_windows
        and str(t.get("variant_id")) == LOCKED_VARIANT_ID
    ]


def _trade_pair_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("candidate_id", "")),
        str(row.get("window_label", "")),
        str(row.get("variant_id", "")),
    ])


def _positive_concentration(net_values: Sequence[float]) -> tuple[float, float, float]:
    positives = sorted((float(v) for v in net_values if float(v) > 0), reverse=True)
    total = sum(positives)
    if total <= 0 or not positives:
        return 0.0, 0.0, 0.0
    return positives[0] / total, sum(positives[:3]) / total, sum(positives[:5]) / total


def _summarize_trades(trades: Sequence[dict[str, Any]], settings: LSRV2LockedProfileSettings) -> dict[str, Any]:
    net = [_safe_float(t.get("net_r"), 0.0) for t in trades]
    gross = [_safe_float(t.get("gross_r"), 0.0) for t in trades]
    costs = [_safe_float(t.get("cost_r"), 0.0) for t in trades]
    wins = [x for x in net if x > settings.breakeven_r_abs]
    losses = [x for x in net if x < -settings.breakeven_r_abs]
    breakevens = [x for x in net if abs(x) <= settings.breakeven_r_abs]
    top1, top3, top5 = _positive_concentration(net)
    by_exit: dict[str, int] = {}
    by_side: dict[str, int] = {}
    by_window: dict[str, int] = {}
    for trade in trades:
        by_exit[str(trade.get("exit_reason", "UNKNOWN"))] = by_exit.get(str(trade.get("exit_reason", "UNKNOWN")), 0) + 1
        by_side[str(trade.get("side", "UNKNOWN"))] = by_side.get(str(trade.get("side", "UNKNOWN")), 0) + 1
        by_window[str(trade.get("window_label", "UNKNOWN"))] = by_window.get(str(trade.get("window_label", "UNKNOWN")), 0) + 1
    gross_sum = sum(gross)
    cost_sum = sum(costs)
    return {
        "closed_trades": len(trades),
        "sum_r_post_cost": _round(sum(net), 8),
        "avg_r_post_cost": _round(_avg(net) or 0.0, 8),
        "median_r_post_cost": _round(_median(net) or 0.0, 8),
        "sum_gross_r": _round(gross_sum, 8),
        "sum_cost_r": _round(cost_sum, 8),
        "avg_cost_r": _round(_avg(costs) or 0.0, 8),
        "cost_to_edge_ratio": _round(_safe_div(cost_sum, gross_sum, 999.0) if gross_sum > 0 else 999.0, 8),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), len(trades), 0.0) or 0.0, 8),
        "loss_rate": _round(_safe_div(len(losses), len(trades), 0.0) or 0.0, 8),
        "breakeven_rate": _round(_safe_div(len(breakevens), len(trades), 0.0) or 0.0, 8),
        "timeout_rate": _round(_safe_div(by_exit.get("TIME_EXIT", 0), len(trades), 0.0) or 0.0, 8),
        "take_profit_rate": _round(_safe_div(by_exit.get("TAKE_PROFIT", 0), len(trades), 0.0) or 0.0, 8),
        "stop_loss_rate": _round(_safe_div(by_exit.get("STOP_LOSS", 0) + by_exit.get("STOP_LOSS_AMBIGUOUS_SAME_BAR", 0), len(trades), 0.0) or 0.0, 8),
        "max_drawdown_r": _round(_max_drawdown(net), 8),
        "top_1_positive_concentration": _round(top1, 8),
        "top_3_positive_concentration": _round(top3, 8),
        "top_5_positive_concentration": _round(top5, 8),
        "exit_reason_counts": dict(sorted(by_exit.items())),
        "side_counts": dict(sorted(by_side.items())),
        "window_trade_counts": dict(sorted(by_window.items())),
    }


def _window_stability(trades: Sequence[dict[str, Any]], settings: LSRV2LockedProfileSettings, *, report_path: Path) -> dict[str, Any]:
    primary = _primary_trades(trades, settings)
    severe = _trades_by_cost(trades, settings.severe_cost_model, settings)
    by_model_window: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in primary + severe:
        model = str(row.get("cost_model"))
        label = str(row.get("window_label", "UNKNOWN"))
        by_model_window.setdefault(model, {}).setdefault(label, []).append(row)
    window_rows: list[dict[str, Any]] = []
    for model, windows in sorted(by_model_window.items()):
        for label, rows in sorted(windows.items()):
            summary = _summarize_trades(rows, settings)
            summary.update({"cost_model": model, "window_label": label, "window_size": _safe_int(rows[0].get("window_size"), 0) if rows else 0})
            window_rows.append(summary)
    primary_windows = [r for r in window_rows if r["cost_model"] == settings.primary_cost_model]
    severe_windows = [r for r in window_rows if r["cost_model"] == settings.severe_cost_model]
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if window_rows else "WARN",
        "decision": "LSR_V2_LOCKED_PROFILE_WINDOW_STABILITY_READY_DIAGNOSTIC" if window_rows else NO_TRADES_DECISION,
        "created_at": utc_now_iso(),
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "primary_cost_model": settings.primary_cost_model,
        "severe_cost_model": settings.severe_cost_model,
        "positive_primary_windows": sum(1 for r in primary_windows if _safe_float(r.get("sum_r_post_cost"), 0.0) > 0),
        "positive_severe_windows": sum(1 for r in severe_windows if _safe_float(r.get("sum_r_post_cost"), 0.0) > 0),
        "strong_negative_primary_windows": sum(1 for r in primary_windows if _safe_float(r.get("sum_r_post_cost"), 0.0) <= settings.strong_negative_window_r),
        "strong_negative_severe_windows": sum(1 for r in severe_windows if _safe_float(r.get("sum_r_post_cost"), 0.0) <= settings.strong_negative_window_r),
        "windows": window_rows,
        "orders_submitted_by_lsr_v2_locked_profile_window_stability": 0,
        "positions_opened_by_lsr_v2_locked_profile_window_stability": 0,
        "promotion_ready": False,
        "report": str(report_path),
    }
    _write_json(report_path, report)
    return report


def _cost_drilldown(trades: Sequence[dict[str, Any]], settings: LSRV2LockedProfileSettings, *, report_path: Path) -> dict[str, Any]:
    primary = {_trade_pair_key(t): t for t in _primary_trades(trades, settings)}
    severe = {_trade_pair_key(t): t for t in _trades_by_cost(trades, settings.severe_cost_model, settings)}
    rows: list[dict[str, Any]] = []
    deltas: list[float] = []
    break_even_bps_values: list[float] = []
    fee_break_even_values: list[float] = []
    win_to_loss = 0
    win_to_nonwin = 0
    positive_to_negative = 0
    severe_negative = 0
    for key, p in primary.items():
        s = severe.get(key)
        if not s:
            continue
        p_net = _safe_float(p.get("net_r"), 0.0)
        s_net = _safe_float(s.get("net_r"), 0.0)
        gross_r = _safe_float(p.get("gross_r"), 0.0)
        p_cost_r = _safe_float(p.get("cost_r"), 0.0)
        p_cost_bps = _safe_float(p.get("round_trip_cost_bps"), 0.0)
        cost_r_per_bps = _safe_div(p_cost_r, p_cost_bps, None)
        break_even_bps = None
        fee_break_even_bps = None
        if cost_r_per_bps and cost_r_per_bps > 0:
            break_even_bps = max(0.0, gross_r / cost_r_per_bps)
            fee_break_even_bps = break_even_bps / 2.0
            break_even_bps_values.append(break_even_bps)
            fee_break_even_values.append(fee_break_even_bps)
        delta = p_net - s_net
        deltas.append(delta)
        if p_net > settings.breakeven_r_abs and s_net < -settings.breakeven_r_abs:
            win_to_loss += 1
        if p_net > settings.breakeven_r_abs and s_net <= settings.breakeven_r_abs:
            win_to_nonwin += 1
        if p_net > 0 and s_net < 0:
            positive_to_negative += 1
        if s_net < 0:
            severe_negative += 1
        rows.append({
            "pair_key": key,
            "candidate_id": p.get("candidate_id"),
            "window_label": p.get("window_label"),
            "window_size": p.get("window_size"),
            "side": p.get("side"),
            "entry_timestamp": p.get("entry_timestamp"),
            "exit_timestamp": p.get("exit_timestamp"),
            "exit_reason": p.get("exit_reason"),
            "primary_net_r": _round(p_net, 8),
            "severe_net_r": _round(s_net, 8),
            "delta_r_primary_minus_severe": _round(delta, 8),
            "gross_r": _round(gross_r, 8),
            "primary_cost_r": _round(p_cost_r, 8),
            "severe_cost_r": _round(_safe_float(s.get("cost_r"), 0.0), 8),
            "primary_round_trip_cost_bps": _round(p_cost_bps, 6),
            "severe_round_trip_cost_bps": _round(_safe_float(s.get("round_trip_cost_bps"), 0.0), 6),
            "slippage_break_even_bps": _round(break_even_bps, 8),
            "fee_break_even_bps": _round(fee_break_even_bps, 8),
            "primary_win_to_severe_loss": bool(p_net > settings.breakeven_r_abs and s_net < -settings.breakeven_r_abs),
            "primary_win_to_severe_nonwin": bool(p_net > settings.breakeven_r_abs and s_net <= settings.breakeven_r_abs),
            "primary_positive_to_severe_negative": bool(p_net > 0 and s_net < 0),
        })
    paired = len(rows)
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if rows else "WARN",
        "decision": "LSR_V2_LOCKED_PROFILE_COST_DRILLDOWN_READY_DIAGNOSTIC" if rows else NO_TRADES_DECISION,
        "created_at": utc_now_iso(),
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "primary_cost_model": settings.primary_cost_model,
        "severe_cost_model": settings.severe_cost_model,
        "paired_trade_count": paired,
        "primary_win_to_severe_loss_count": win_to_loss,
        "primary_win_to_severe_loss_ratio": _round(_safe_div(win_to_loss, paired, 0.0) or 0.0, 8),
        "primary_win_to_severe_nonwin_count": win_to_nonwin,
        "primary_win_to_severe_nonwin_ratio": _round(_safe_div(win_to_nonwin, paired, 0.0) or 0.0, 8),
        "primary_positive_to_severe_negative_count": positive_to_negative,
        "primary_positive_to_severe_negative_ratio": _round(_safe_div(positive_to_negative, paired, 0.0) or 0.0, 8),
        "severe_negative_count": severe_negative,
        "severe_negative_ratio": _round(_safe_div(severe_negative, paired, 0.0) or 0.0, 8),
        "avg_delta_r_primary_minus_severe": _round(_avg(deltas) or 0.0, 8),
        "median_delta_r_primary_minus_severe": _round(_median(deltas) or 0.0, 8),
        "avg_slippage_break_even_bps": _round(_avg(break_even_bps_values) or 0.0, 8),
        "median_slippage_break_even_bps": _round(_median(break_even_bps_values) or 0.0, 8),
        "avg_fee_break_even_bps": _round(_avg(fee_break_even_values) or 0.0, 8),
        "median_fee_break_even_bps": _round(_median(fee_break_even_values) or 0.0, 8),
        "worst_delta_trades": sorted(rows, key=lambda r: _safe_float(r.get("delta_r_primary_minus_severe"), 0.0), reverse=True)[:20],
        "cost_pair_rows": rows,
        "orders_submitted_by_lsr_v2_locked_profile_cost_drilldown": 0,
        "positions_opened_by_lsr_v2_locked_profile_cost_drilldown": 0,
        "promotion_ready": False,
        "report": str(report_path),
    }
    _write_json(report_path, report)
    return report


def _classify(primary_summary: dict[str, Any], window_report: dict[str, Any], cost_report: dict[str, Any], settings: LSRV2LockedProfileSettings) -> tuple[str, list[str], list[str]]:
    closed = _safe_int(primary_summary.get("closed_trades"), 0)
    sum_r = _safe_float(primary_summary.get("sum_r_post_cost"), 0.0)
    avg_r = _safe_float(primary_summary.get("avg_r_post_cost"), 0.0)
    top1 = _safe_float(primary_summary.get("top_1_positive_concentration"), 0.0)
    max_dd = _safe_float(primary_summary.get("max_drawdown_r"), 0.0)
    breakeven = _safe_float(primary_summary.get("breakeven_rate"), 0.0)
    cost_to_edge = _safe_float(primary_summary.get("cost_to_edge_ratio"), 999.0)
    positive_primary = _safe_int(window_report.get("positive_primary_windows"), 0)
    positive_severe = _safe_int(window_report.get("positive_severe_windows"), 0)
    strong_negative_primary = _safe_int(window_report.get("strong_negative_primary_windows"), 0)
    severe_negative_ratio = _safe_float(cost_report.get("severe_negative_ratio"), 0.0)
    win_to_nonwin_ratio = _safe_float(cost_report.get("primary_win_to_severe_nonwin_ratio"), 0.0)

    blockers: list[str] = []
    labels: list[str] = []
    if closed < settings.min_closed_trades:
        blockers.append("closed_trades_below_minimum")
        labels.append("LOW_SAMPLE_EDGE")
    if positive_primary < settings.min_positive_windows:
        blockers.append("positive_primary_windows_below_threshold")
    if avg_r <= settings.min_avg_r_post_cost:
        blockers.append("avg_r_post_cost_not_positive")
    if sum_r <= settings.min_sum_r_post_cost:
        blockers.append("sum_r_post_cost_not_positive")
    if top1 > settings.max_top_trade_concentration:
        blockers.append("top_trade_concentration_not_ok")
        labels.append("OUTLIER_DOMINATED_EDGE")
    if max_dd > settings.max_drawdown_r:
        blockers.append("max_drawdown_not_ok")
    if breakeven > settings.max_breakeven_ratio:
        blockers.append("breakeven_drag_not_ok")
    if cost_to_edge > settings.max_cost_to_edge_ratio:
        blockers.append("cost_to_edge_ratio_not_ok")
        labels.append("COST_SENSITIVE_EDGE")
    if strong_negative_primary > 0:
        blockers.append("strong_negative_primary_window_detected")
    severe_survival = positive_severe >= settings.min_severe_positive_windows and _safe_float(cost_report.get("paired_trade_count"), 0) > 0 and severe_negative_ratio < 0.75
    if settings.require_severe_cost_survival and not severe_survival:
        blockers.append("severe_cost_survival_not_ok")
        labels.append("COST_SENSITIVE_EDGE")
    if win_to_nonwin_ratio > 0.20:
        blockers.append("primary_win_to_severe_nonwin_ratio_high")
        labels.append("COST_SENSITIVE_EDGE")
    if sum_r > 0 and avg_r > 0:
        labels.append("FRAGILE_POSITIVE_EDGE" if blockers else "LOCKED_PROFILE_POSITIVE_EDGE")
    if not blockers:
        return READY_DECISION, ["LOCKED_PROFILE_READY_FOR_WALK_FORWARD"], []
    labels = list(dict.fromkeys(labels or ["REJECT_LSR_V2_LOCKED_PROFILE"]))
    if "LOW_SAMPLE_EDGE" in labels:
        decision = LOW_SAMPLE_DECISION
    elif "COST_SENSITIVE_EDGE" in labels:
        decision = COST_SENSITIVE_DECISION
    elif "OUTLIER_DOMINATED_EDGE" in labels:
        decision = OUTLIER_DECISION
    else:
        decision = REJECT_DECISION
    return decision, labels, blockers


def _safe_no_data_report(settings: LSRV2LockedProfileSettings, load_info: dict[str, Any], *, report_path: Path, trades_path: Path, cost_path: Path, window_path: Path) -> dict[str, Any]:
    no_matching = bool(load_info.get("no_matching_timeframe_data"))
    decision = NO_MATCHING_TIMEFRAME_DECISION if no_matching else NO_MARKET_DATA_DECISION
    report = {
        "prompt_id": PROMPT_ID,
        "status": "WARN",
        "decision": decision,
        "created_at": utc_now_iso(),
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "symbol": settings.symbol,
        "requested_timeframe": load_info.get("requested_timeframe", normalize_timeframe_label(settings.timeframe)),
        "detected_timeframe": load_info.get("detected_timeframe", ""),
        "timeframe_match": bool(load_info.get("timeframe_match", False)),
        "strict_timeframe": bool(load_info.get("strict_timeframe", settings.strict_timeframe)),
        "allow_timeframe_fallback": bool(load_info.get("allow_timeframe_fallback", settings.allow_timeframe_fallback)),
        "input_path": load_info.get("input_path", ""),
        "input_rows": 0,
        "tried_paths": load_info.get("tried_paths", []),
        "timeframe_mismatch_paths": load_info.get("timeframe_mismatch_paths", []),
        "classification_labels": [],
        "blockers": ["no_market_data" if not no_matching else "no_matching_timeframe_data"],
        "primary_closed_trades": 0,
        "promotion_ready": False,
        "orders_submitted_by_lsr_v2_locked_profile": 0,
        "positions_opened_by_lsr_v2_locked_profile": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "report": str(report_path),
        "trades_jsonl": str(trades_path),
        "cost_drilldown_report": str(cost_path),
        "window_stability_report": str(window_path),
    }
    _write_json(report_path, report)
    _write_jsonl(trades_path, [])
    _write_json(cost_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": decision, "paired_trade_count": 0})
    _write_json(window_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": decision, "windows": []})
    return report


def run_lsr_v2_locked_profile(settings: LSRV2LockedProfileSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2LockedProfileSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    report_path = data_dir / REPORT_NAME
    trades_path = data_dir / TRADES_JSONL_NAME
    cost_path = data_dir / COST_DRILLDOWN_NAME
    window_path = data_dir / WINDOW_STABILITY_NAME

    ablation_settings = _ablation_settings(settings)
    load_settings = _candidate_selection_settings(ablation_settings)
    rows, load_info = load_market_rows(load_settings)
    if not rows:
        return _safe_no_data_report(settings, load_info, report_path=report_path, trades_path=trades_path, cost_path=cost_path, window_path=window_path)

    try:
        cost_scenarios = selected_cost_scenarios(settings.cost_models)
        variant = locked_variant()
        all_summaries: list[dict[str, Any]] = []
        all_trades: list[dict[str, Any]] = []
        for window_size in settings.windows:
            summaries, trades = _simulate_window(
                rows=rows,
                window_size=int(window_size),
                cost_scenarios=cost_scenarios,
                variants=(variant,),
                settings=ablation_settings,
            )
            all_summaries.extend(summaries)
            all_trades.extend(trades)
        # Rewrite lineage fields so downstream readers can distinguish locked-profile outputs from broad ablation rows.
        for trade in all_trades:
            trade["prompt_id"] = PROMPT_ID
            trade["event_type"] = "LSR_V2_LOCKED_PROFILE_TRADE"
            trade["locked_profile_name"] = LOCKED_PROFILE_NAME
            trade["locked_variant_id"] = LOCKED_VARIANT_ID
            trade["orders_submitted_by_lsr_v2_locked_profile"] = 0
            trade["positions_opened_by_lsr_v2_locked_profile"] = 0
        written = _write_jsonl(trades_path, all_trades, max_rows=settings.max_trade_rows_to_write)
        primary = _primary_trades(all_trades, settings)
        primary_summary = _summarize_trades(primary, settings)
        window_report = _window_stability(all_trades, settings, report_path=window_path)
        cost_report = _cost_drilldown(all_trades, settings, report_path=cost_path)
        if not primary:
            decision, labels, blockers = NO_TRADES_DECISION, ["LOW_SAMPLE_EDGE"], ["no_primary_locked_profile_trades"]
        else:
            decision, labels, blockers = _classify(primary_summary, window_report, cost_report, settings)
        status = "PASS" if all_trades else "WARN"
        report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": decision,
            "classification_labels": labels,
            "blockers": blockers,
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "entry_policy": variant.entry_policy,
            "stop_policy": variant.stop_policy,
            "target_policy": variant.target_policy,
            "max_holding_bars": variant.max_holding_bars,
            "symbol": settings.symbol,
            "timeframe": settings.timeframe,
            "requested_timeframe": load_info.get("requested_timeframe", normalize_timeframe_label(settings.timeframe)),
            "detected_timeframe": load_info.get("detected_timeframe", ""),
            "timeframe_match": bool(load_info.get("timeframe_match", False)),
            "strict_timeframe": bool(load_info.get("strict_timeframe", settings.strict_timeframe)),
            "allow_timeframe_fallback": bool(load_info.get("allow_timeframe_fallback", settings.allow_timeframe_fallback)),
            "input_rows": len(rows),
            "input_path": load_info.get("input_path", ""),
            "settings": asdict(settings),
            "windows": list(settings.windows),
            "primary_windows": list(settings.primary_windows),
            "cost_models": settings.cost_models,
            "total_trade_rows": len(all_trades),
            "written_trade_rows": written,
            "primary_cost_model": settings.primary_cost_model,
            "severe_cost_model": settings.severe_cost_model,
            "primary_closed_trades": primary_summary.get("closed_trades", 0),
            "primary_positive_windows": window_report.get("positive_primary_windows", 0),
            "severe_positive_windows": window_report.get("positive_severe_windows", 0),
            "primary_sum_r_post_cost": primary_summary.get("sum_r_post_cost", 0.0),
            "primary_avg_r_post_cost": primary_summary.get("avg_r_post_cost", 0.0),
            "primary_median_r_post_cost": primary_summary.get("median_r_post_cost", 0.0),
            "primary_win_rate": primary_summary.get("win_rate", 0.0),
            "primary_loss_rate": primary_summary.get("loss_rate", 0.0),
            "primary_breakeven_rate": primary_summary.get("breakeven_rate", 0.0),
            "primary_timeout_rate": primary_summary.get("timeout_rate", 0.0),
            "primary_take_profit_rate": primary_summary.get("take_profit_rate", 0.0),
            "primary_stop_loss_rate": primary_summary.get("stop_loss_rate", 0.0),
            "primary_max_drawdown_r": primary_summary.get("max_drawdown_r", 0.0),
            "top_1_positive_concentration": primary_summary.get("top_1_positive_concentration", 0.0),
            "top_3_positive_concentration": primary_summary.get("top_3_positive_concentration", 0.0),
            "top_5_positive_concentration": primary_summary.get("top_5_positive_concentration", 0.0),
            "primary_exit_reason_counts": primary_summary.get("exit_reason_counts", {}),
            "primary_side_counts": primary_summary.get("side_counts", {}),
            "cost_drilldown_summary": {
                "paired_trade_count": cost_report.get("paired_trade_count", 0),
                "primary_win_to_severe_loss_ratio": cost_report.get("primary_win_to_severe_loss_ratio", 0.0),
                "primary_win_to_severe_nonwin_ratio": cost_report.get("primary_win_to_severe_nonwin_ratio", 0.0),
                "primary_positive_to_severe_negative_ratio": cost_report.get("primary_positive_to_severe_negative_ratio", 0.0),
                "severe_negative_ratio": cost_report.get("severe_negative_ratio", 0.0),
                "avg_delta_r_primary_minus_severe": cost_report.get("avg_delta_r_primary_minus_severe", 0.0),
                "avg_slippage_break_even_bps": cost_report.get("avg_slippage_break_even_bps", 0.0),
                "avg_fee_break_even_bps": cost_report.get("avg_fee_break_even_bps", 0.0),
            },
            "orders_submitted_by_lsr_v2_locked_profile": 0,
            "positions_opened_by_lsr_v2_locked_profile": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "promotion_blocked_reason": "locked-profile preflight is diagnostic; requires walk-forward, embargoed OOS, bootstrap and promotion gate before paper supervised",
            "report": str(report_path),
            "trades_jsonl": str(trades_path),
            "cost_drilldown_report": str(cost_path),
            "window_stability_report": str(window_path),
        }
        _write_json(report_path, report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": ERROR_DECISION,
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "input_rows": len(rows),
            "input_path": load_info.get("input_path", ""),
            "orders_submitted_by_lsr_v2_locked_profile": 0,
            "positions_opened_by_lsr_v2_locked_profile": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(report_path),
            "trades_jsonl": str(trades_path),
            "cost_drilldown_report": str(cost_path),
            "window_stability_report": str(window_path),
        }
        _write_json(report_path, report)
        return report
