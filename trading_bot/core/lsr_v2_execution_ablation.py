"""Prompt 29.4.4s-7c — LSR-v2 execution/cost ablation audit.

Diagnostic-only research layer for Liquidity Sweep Reversal v2.  It evaluates
execution variants on the same LSR-v2 candidate detector used by s-6b/s-7 and
attributes whether the currently fragile edge is mainly a function of entry,
stop, target, max-holding, or transaction-cost assumptions.

This module must never submit orders, open positions, mutate paper state, route
signals, call a broker, lower runtime thresholds, or enable live/testnet paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import json
import math

from core.liquidity_sweep_reversal_v2 import (
    LSRV2Settings,
    detect_lsr_v2_candidates,
    load_market_rows,
    normalize_timeframe_label,
)
from core.lsr_v2_backtest_matrix import (
    CostScenario,
    DEFAULT_COST_SCENARIOS,
    DEFAULT_WINDOWS,
    PRIMARY_VALIDATION_WINDOWS,
    parse_windows,
    selected_cost_scenarios,
)

PROMPT_ID = "29.4.4s-7c"
TRADE_EVENT_TYPE = "LSR_V2_EXECUTION_ABLATION_TRADE"
REPORT_NAME = "lsr_v2_execution_ablation_report.json"
VARIANTS_REPORT_NAME = "lsr_v2_execution_ablation_variants.json"
TRADES_JSONL_NAME = "lsr_v2_execution_ablation_trades.jsonl"
COST_BREAK_EVEN_REPORT_NAME = "lsr_v2_cost_break_even_report.json"
READY_DECISION = "LSR_V2_EXECUTION_VARIANT_RESEARCH_READY"
FRAGILE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_FRAGILE_EDGE"
COST_SENSITIVE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COST_SENSITIVE"
REJECT_EXECUTION_DECISION = "REJECT_LSR_V2_CURRENT_EXECUTION"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ABLATION_NO_TRADES"
NO_MARKET_DATA_DECISION = "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
NO_MATCHING_TIMEFRAME_DECISION = "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
LOAD_ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ABLATION_ERROR"

ENTRY_POLICIES = (
    "retest_entry_limit_like",
    "retest_entry_mid",
    "retest_entry_close",
    "confirmation_close_entry",
)
STOP_POLICIES = (
    "stop_at_sweep_extreme",
    "stop_at_sweep_extreme_plus_atr_buffer",
)
TARGET_POLICIES = (
    "tp_fixed_1_5R",
    "tp_fixed_2R",
    "tp_structure_liquidity_target",
)
MAX_HOLDING_SET = (12, 24, 36)


@dataclass(frozen=True)
class ExecutionVariant:
    variant_id: str
    entry_policy: str
    stop_policy: str
    target_policy: str
    max_holding_bars: int


@dataclass(frozen=True)
class LSRV2ExecutionAblationSettings:
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
    max_breakeven_ratio: float = 0.30
    breakeven_r_abs: float = 0.10
    max_top_trade_concentration: float = 0.45
    max_drawdown_r: float = 10.0
    strong_negative_window_r: float = -3.0
    require_severe_cost_survival: bool = True
    min_severe_positive_windows: int = 3
    max_cost_to_edge_ratio: float = 0.75
    strict_timeframe: bool = True
    allow_timeframe_fallback: bool = False
    max_trade_rows_to_write: int = 250_000
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
    def default(cls) -> "LSRV2ExecutionAblationSettings":
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


def _window_label(size: int) -> str:
    if int(size) % 1000 == 0:
        return f"{int(size) // 1000}k"
    return str(int(size))


def build_default_variants() -> tuple[ExecutionVariant, ...]:
    variants: list[ExecutionVariant] = []
    for entry in ENTRY_POLICIES:
        for stop in STOP_POLICIES:
            for target in TARGET_POLICIES:
                for hold in MAX_HOLDING_SET:
                    variant_id = f"{entry}__{stop}__{target}__hold_{hold}"
                    variants.append(ExecutionVariant(variant_id, entry, stop, target, int(hold)))
    return tuple(variants)


def _candidate_selection_settings(settings: LSRV2ExecutionAblationSettings) -> LSRV2Settings:
    return LSRV2Settings(
        data_dir=settings.data_dir,
        input_path=settings.input_path,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        strict_timeframe=settings.strict_timeframe,
        allow_timeframe_fallback=settings.allow_timeframe_fallback,
        max_rows=settings.max_rows,
        pool_lookback=settings.pool_lookback,
        confirmation_window=settings.confirmation_window,
        retest_window=settings.retest_window,
        min_sweep_bps=settings.min_sweep_bps,
        retest_tolerance_bps=settings.retest_tolerance_bps,
        stop_buffer_bps=settings.stop_buffer_bps,
        target_rr=settings.target_rr,
        min_rr=settings.min_rr,
        fee_rate=0.0004,
        spread_bps=0.0,
        slippage_bps=0.0,
        max_cost_to_r=settings.max_cost_to_r,
        require_volume_confirmation=settings.require_volume_confirmation,
        require_retest_for_candidate_ready=settings.require_retest_for_candidate_ready,
    )


def _cost_to_r(entry: float, stop: float, scenario: CostScenario) -> float:
    risk_abs = abs(float(entry) - float(stop))
    if risk_abs <= 0 or entry <= 0:
        return 999.0
    return (float(entry) * scenario.round_trip_cost_bps / 10_000.0) / risk_abs


def _row_close(row: dict[str, Any]) -> float:
    return _safe_float(row.get("close"), 0.0)


def _candidate_levels(candidate: dict[str, Any]) -> dict[str, float]:
    levels = candidate.get("levels") if isinstance(candidate.get("levels"), dict) else {}
    return {
        "pool": _safe_float(levels.get("liquidity_pool_level"), 0.0),
        "sweep_extreme": _safe_float(levels.get("sweep_extreme"), 0.0),
        "micro_structure_level": _safe_float(levels.get("micro_structure_level"), 0.0),
        "entry": _safe_float(levels.get("entry_price"), 0.0),
        "stop": _safe_float(levels.get("stop_loss"), 0.0),
        "target": _safe_float(levels.get("take_profit"), 0.0),
    }


def _atr_proxy(candidate: dict[str, Any]) -> float:
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    return max(_safe_float(quality.get("atr_proxy"), 0.0), 0.0)


def _resolve_entry(rows: list[dict[str, Any]], candidate: dict[str, Any], variant: ExecutionVariant) -> tuple[int, float] | None:
    levels = _candidate_levels(candidate)
    side = str(candidate.get("side", "")).upper()
    retest_index = _safe_int(candidate.get("retest_index"), -1)
    reclaim_index = _safe_int(candidate.get("reclaim_index"), -1)
    if side not in {"BUY", "SELL"}:
        return None
    if variant.entry_policy == "confirmation_close_entry":
        entry_index = reclaim_index
        if entry_index < 0 or entry_index >= len(rows) - 1:
            return None
        return entry_index, _row_close(rows[entry_index])
    entry_index = retest_index
    if entry_index < 0 or entry_index >= len(rows) - 1:
        return None
    retest_close = _row_close(rows[entry_index])
    base_entry = levels["entry"]
    if base_entry <= 0 or retest_close <= 0:
        return None
    if variant.entry_policy == "retest_entry_limit_like":
        return entry_index, base_entry
    if variant.entry_policy == "retest_entry_close":
        return entry_index, retest_close
    if variant.entry_policy == "retest_entry_mid":
        return entry_index, (base_entry + retest_close) / 2.0
    return None


def _resolve_stop(candidate: dict[str, Any], variant: ExecutionVariant, side: str, settings: LSRV2ExecutionAblationSettings) -> float:
    levels = _candidate_levels(candidate)
    sweep = levels["sweep_extreme"]
    if sweep <= 0:
        return 0.0
    if variant.stop_policy == "stop_at_sweep_extreme":
        return sweep
    atr = _atr_proxy(candidate)
    atr_buffer = atr * max(float(settings.atr_stop_buffer_multiple), 0.0)
    bps_buffer = sweep * max(float(settings.stop_buffer_bps), 0.0) / 10_000.0
    buffer_abs = max(atr_buffer, bps_buffer)
    if side == "BUY":
        return sweep - buffer_abs
    return sweep + buffer_abs


def _resolve_target(candidate: dict[str, Any], variant: ExecutionVariant, side: str, entry: float, stop: float, settings: LSRV2ExecutionAblationSettings) -> float:
    risk_abs = abs(float(entry) - float(stop))
    if risk_abs <= 0 or entry <= 0 or stop <= 0:
        return 0.0
    direction = 1.0 if side == "BUY" else -1.0
    if variant.target_policy == "tp_fixed_1_5R":
        return entry + direction * risk_abs * 1.5
    if variant.target_policy == "tp_fixed_2R":
        return entry + direction * risk_abs * 2.0
    levels = _candidate_levels(candidate)
    micro = levels["micro_structure_level"]
    fallback_rr = max(float(settings.structure_target_min_rr), 1.0)
    fallback_target = entry + direction * risk_abs * fallback_rr
    if micro <= 0:
        return fallback_target
    raw_rr = ((micro - entry) * direction) / risk_abs
    if not math.isfinite(raw_rr):
        raw_rr = 0.0
    if raw_rr < settings.structure_target_min_rr:
        rr = settings.structure_target_min_rr
    elif raw_rr > settings.structure_target_max_rr:
        rr = settings.structure_target_max_rr
    else:
        rr = raw_rr
    return entry + direction * risk_abs * rr


def _simulate_variant_candidate(
    *,
    rows: list[dict[str, Any]],
    candidate: dict[str, Any],
    window_size: int,
    window_label: str,
    cost: CostScenario,
    variant: ExecutionVariant,
    settings: LSRV2ExecutionAblationSettings,
) -> dict[str, Any] | None:
    if not candidate.get("candidate_ready"):
        return None
    side = str(candidate.get("side", "")).upper()
    if side not in {"BUY", "SELL"}:
        return None
    entry_resolved = _resolve_entry(rows, candidate, variant)
    if entry_resolved is None:
        return None
    entry_index, entry = entry_resolved
    stop = _resolve_stop(candidate, variant, side, settings)
    target = _resolve_target(candidate, variant, side, entry, stop, settings)
    if entry <= 0 or stop <= 0 or target <= 0 or entry_index < 0 or entry_index >= len(rows) - 1:
        return None
    risk_abs = abs(entry - stop)
    if risk_abs <= 0:
        return None

    exit_index: int | None = None
    exit_price: float | None = None
    exit_reason = "TIME_EXIT"
    ambiguous_hit = False
    max_i = min(len(rows) - 1, entry_index + max(1, int(variant.max_holding_bars)))
    for i in range(entry_index + 1, max_i + 1):
        high = _safe_float(rows[i].get("high"), 0.0)
        low = _safe_float(rows[i].get("low"), 0.0)
        if side == "BUY":
            stop_hit = low <= stop
            target_hit = high >= target
            if stop_hit and target_hit:
                ambiguous_hit = True
                exit_index = i
                exit_price = stop
                exit_reason = "STOP_LOSS_AMBIGUOUS_SAME_BAR"
                break
            if stop_hit:
                exit_index = i
                exit_price = stop
                exit_reason = "STOP_LOSS"
                break
            if target_hit:
                exit_index = i
                exit_price = target
                exit_reason = "TAKE_PROFIT"
                break
        else:
            stop_hit = high >= stop
            target_hit = low <= target
            if stop_hit and target_hit:
                ambiguous_hit = True
                exit_index = i
                exit_price = stop
                exit_reason = "STOP_LOSS_AMBIGUOUS_SAME_BAR"
                break
            if stop_hit:
                exit_index = i
                exit_price = stop
                exit_reason = "STOP_LOSS"
                break
            if target_hit:
                exit_index = i
                exit_price = target
                exit_reason = "TAKE_PROFIT"
                break
    if exit_index is None:
        exit_index = max_i
        exit_price = _row_close(rows[exit_index])
        exit_reason = "TIME_EXIT"
    if exit_price is None or exit_price <= 0:
        return None

    direction = 1.0 if side == "BUY" else -1.0
    gross_r = ((exit_price - entry) * direction) / risk_abs
    cost_r = _cost_to_r(entry, stop, cost)
    net_r = gross_r - cost_r
    risk_amount = float(settings.starting_equity) * float(settings.risk_per_trade_pct)
    gross_pnl = gross_r * risk_amount
    cost_pnl = cost_r * risk_amount
    net_pnl = net_r * risk_amount
    return {
        "event_type": TRADE_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "created_at": utc_now_iso(),
        "candidate_id": candidate.get("candidate_id"),
        "variant_id": variant.variant_id,
        "entry_policy": variant.entry_policy,
        "stop_policy": variant.stop_policy,
        "target_policy": variant.target_policy,
        "variant_max_holding_bars": int(variant.max_holding_bars),
        "symbol": candidate.get("symbol", settings.symbol),
        "timeframe": settings.timeframe,
        "window_size": int(window_size),
        "window_label": window_label,
        "cost_model": cost.name,
        "side": side,
        "archetype": "LIQUIDITY_SWEEP_REVERSAL_V2",
        "entry_index": int(entry_index),
        "exit_index": int(exit_index),
        "holding_bars": int(exit_index - entry_index),
        "entry_timestamp": rows[entry_index].get("timestamp"),
        "exit_timestamp": rows[exit_index].get("timestamp"),
        "sweep_timestamp": candidate.get("sweep_timestamp"),
        "reclaim_timestamp": candidate.get("reclaim_timestamp"),
        "retest_timestamp": candidate.get("retest_timestamp"),
        "entry_price": _round(entry, 10),
        "stop_loss": _round(stop, 10),
        "take_profit": _round(target, 10),
        "exit_price": _round(exit_price, 10),
        "exit_reason": exit_reason,
        "ambiguous_same_bar_hit": bool(ambiguous_hit),
        "gross_r": _round(gross_r, 8),
        "cost_r": _round(cost_r, 8),
        "net_r": _round(net_r, 8),
        "gross_pnl": _round(gross_pnl, 8),
        "cost_pnl": _round(cost_pnl, 8),
        "net_pnl": _round(net_pnl, 8),
        "risk_amount": _round(risk_amount, 8),
        "risk_per_trade_pct": settings.risk_per_trade_pct,
        "round_trip_cost_bps": _round(cost.round_trip_cost_bps, 6),
        "fee_rate": cost.fee_rate,
        "spread_bps": cost.spread_bps,
        "slippage_bps": cost.slippage_bps,
        "quality_grade": ((candidate.get("quality") or {}).get("grade") if isinstance(candidate.get("quality"), dict) else None),
        "quality_score": ((candidate.get("quality") or {}).get("score") if isinstance(candidate.get("quality"), dict) else None),
        "regime": ((candidate.get("filters") or {}).get("regime") if isinstance(candidate.get("filters"), dict) else "UNKNOWN"),
        "audit_only": True,
        "submit_order": False,
        "route_order": False,
        "broker_submit_called": False,
        "orders_submitted_by_lsr_v2_ablation": 0,
        "positions_opened_by_lsr_v2_ablation": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
    }


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _summarize_trades(trades: Sequence[dict[str, Any]], settings: LSRV2ExecutionAblationSettings) -> dict[str, Any]:
    closed = list(trades)
    net = [_safe_float(t.get("net_r"), 0.0) for t in closed]
    gross = [_safe_float(t.get("gross_r"), 0.0) for t in closed]
    costs = [_safe_float(t.get("cost_r"), 0.0) for t in closed]
    wins = [x for x in net if x > settings.breakeven_r_abs]
    losses = [x for x in net if x < -settings.breakeven_r_abs]
    breakevens = [x for x in net if abs(x) <= settings.breakeven_r_abs]
    positive = sorted((x for x in net if x > 0), reverse=True)
    positive_sum = sum(positive)
    top_1 = positive[0] / positive_sum if positive_sum > 0 and positive else 0.0
    top_3 = sum(positive[:3]) / positive_sum if positive_sum > 0 and positive else 0.0
    by_exit: dict[str, int] = {}
    by_side: dict[str, int] = {}
    for trade in closed:
        by_exit[str(trade.get("exit_reason", "UNKNOWN"))] = by_exit.get(str(trade.get("exit_reason", "UNKNOWN")), 0) + 1
        by_side[str(trade.get("side", "UNKNOWN"))] = by_side.get(str(trade.get("side", "UNKNOWN")), 0) + 1
    return {
        "closed_trades": len(closed),
        "sum_r_post_cost": _round(sum(net), 8),
        "avg_r_post_cost": _round(_avg(net) or 0.0, 8),
        "median_r_post_cost": _round(sorted(net)[len(net)//2] if net else 0.0, 8),
        "sum_gross_r": _round(sum(gross), 8),
        "sum_cost_r": _round(sum(costs), 8),
        "avg_cost_r": _round(_avg(costs) or 0.0, 8),
        "cost_to_edge_ratio": _round(_safe_div(sum(costs), sum(gross), 999.0) if sum(gross) > 0 else 999.0, 8),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), len(closed), 0.0) or 0.0, 8),
        "loss_rate": _round(_safe_div(len(losses), len(closed), 0.0) or 0.0, 8),
        "breakeven_rate": _round(_safe_div(len(breakevens), len(closed), 0.0) or 0.0, 8),
        "timeout_rate": _round(_safe_div(by_exit.get("TIME_EXIT", 0), len(closed), 0.0) or 0.0, 8),
        "take_profit_rate": _round(_safe_div(by_exit.get("TAKE_PROFIT", 0), len(closed), 0.0) or 0.0, 8),
        "stop_loss_rate": _round(_safe_div(by_exit.get("STOP_LOSS", 0) + by_exit.get("STOP_LOSS_AMBIGUOUS_SAME_BAR", 0), len(closed), 0.0) or 0.0, 8),
        "max_drawdown_r": _round(_max_drawdown(net), 8),
        "top_1_positive_concentration": _round(top_1, 8),
        "top_3_positive_concentration": _round(top_3, 8),
        "exit_reason_counts": dict(sorted(by_exit.items())),
        "side_counts": dict(sorted(by_side.items())),
    }


def _simulate_window(
    *,
    rows: list[dict[str, Any]],
    window_size: int,
    cost_scenarios: tuple[CostScenario, ...],
    variants: tuple[ExecutionVariant, ...],
    settings: LSRV2ExecutionAblationSettings,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    window_rows = rows[-int(window_size):] if int(window_size) < len(rows) else rows[:]
    label = _window_label(int(window_size))
    candidate_settings = _candidate_selection_settings(settings)
    candidates = [c for c in detect_lsr_v2_candidates(window_rows, candidate_settings) if c.get("candidate_ready")]
    trades: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for variant in variants:
        for cost in cost_scenarios:
            variant_trades: list[dict[str, Any]] = []
            for candidate in candidates:
                trade = _simulate_variant_candidate(
                    rows=window_rows,
                    candidate=candidate,
                    window_size=int(window_size),
                    window_label=label,
                    cost=cost,
                    variant=variant,
                    settings=settings,
                )
                if trade is not None:
                    variant_trades.append(trade)
            trades.extend(variant_trades)
            summary = _summarize_trades(variant_trades, settings)
            summary.update({
                "window_size": int(window_size),
                "window_label": label,
                "candidate_ready_count": len(candidates),
                "variant_id": variant.variant_id,
                "entry_policy": variant.entry_policy,
                "stop_policy": variant.stop_policy,
                "target_policy": variant.target_policy,
                "max_holding_bars": int(variant.max_holding_bars),
                "cost_model": cost.name,
                "round_trip_cost_bps": _round(cost.round_trip_cost_bps, 6),
            })
            summaries.append(summary)
    return summaries, trades


def _group_summaries(summaries: Sequence[dict[str, Any]], *, primary_cost_model: str, primary_windows: set[int]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in summaries:
        if str(row.get("cost_model")) != primary_cost_model:
            continue
        if _safe_int(row.get("window_size"), 0) not in primary_windows:
            continue
        grouped.setdefault(str(row.get("variant_id")), []).append(row)
    return grouped


def _variant_rollup(rows: Sequence[dict[str, Any]], settings: LSRV2ExecutionAblationSettings) -> dict[str, Any]:
    closed = sum(_safe_int(r.get("closed_trades"), 0) for r in rows)
    sum_r = sum(_safe_float(r.get("sum_r_post_cost"), 0.0) for r in rows)
    sum_gross = sum(_safe_float(r.get("sum_gross_r"), 0.0) for r in rows)
    sum_cost = sum(_safe_float(r.get("sum_cost_r"), 0.0) for r in rows)
    positive_windows = sum(1 for r in rows if _safe_float(r.get("sum_r_post_cost"), 0.0) > 0)
    strong_negative = sum(1 for r in rows if _safe_float(r.get("sum_r_post_cost"), 0.0) <= settings.strong_negative_window_r)
    breakeven_trades = sum(_safe_int(r.get("breakeven_count"), 0) for r in rows)
    top1 = max((_safe_float(r.get("top_1_positive_concentration"), 0.0) for r in rows), default=0.0)
    max_dd = max((_safe_float(r.get("max_drawdown_r"), 0.0) for r in rows), default=0.0)
    return {
        "windows": len(rows),
        "closed_trades": closed,
        "positive_windows": positive_windows,
        "strong_negative_windows": strong_negative,
        "sum_r_post_cost": _round(sum_r, 8),
        "weighted_avg_r_post_cost": _round(_safe_div(sum_r, closed, 0.0) or 0.0, 8),
        "sum_gross_r": _round(sum_gross, 8),
        "sum_cost_r": _round(sum_cost, 8),
        "cost_to_edge_ratio": _round(_safe_div(sum_cost, sum_gross, 999.0) if sum_gross > 0 else 999.0, 8),
        "breakeven_ratio": _round(_safe_div(breakeven_trades, closed, 0.0) or 0.0, 8),
        "top_trade_concentration": _round(top1, 8),
        "max_drawdown_r": _round(max_dd, 8),
    }


def _build_variant_report(summaries: Sequence[dict[str, Any]], settings: LSRV2ExecutionAblationSettings) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    primary_windows = {int(w) for w in settings.primary_windows}
    primary_grouped = _group_summaries(summaries, primary_cost_model=settings.primary_cost_model, primary_windows=primary_windows)
    severe_grouped = _group_summaries(summaries, primary_cost_model=settings.severe_cost_model, primary_windows=primary_windows)
    rollups: list[dict[str, Any]] = []
    for variant_id, rows in primary_grouped.items():
        base = _variant_rollup(rows, settings)
        severe = _variant_rollup(severe_grouped.get(variant_id, []), settings)
        first = rows[0] if rows else {}
        blockers: list[str] = []
        if base["closed_trades"] < settings.min_closed_trades:
            blockers.append("closed_trades_below_minimum")
        if base["positive_windows"] < settings.min_positive_windows:
            blockers.append("positive_windows_below_threshold")
        if _safe_float(base.get("weighted_avg_r_post_cost"), 0.0) <= settings.min_avg_r_post_cost:
            blockers.append("weighted_avg_r_post_cost_not_positive")
        if _safe_float(base.get("sum_r_post_cost"), 0.0) <= settings.min_sum_r_post_cost:
            blockers.append("net_sum_r_post_cost_not_positive")
        if _safe_float(base.get("breakeven_ratio"), 0.0) > settings.max_breakeven_ratio:
            blockers.append("breakeven_drag_not_ok")
        if _safe_float(base.get("top_trade_concentration"), 0.0) > settings.max_top_trade_concentration:
            blockers.append("top_trade_concentration_not_ok")
        if _safe_float(base.get("max_drawdown_r"), 0.0) > settings.max_drawdown_r:
            blockers.append("max_drawdown_not_ok")
        severe_survival = bool(severe and _safe_int(severe.get("positive_windows"), 0) >= settings.min_severe_positive_windows and _safe_float(severe.get("sum_r_post_cost"), 0.0) > 0)
        if settings.require_severe_cost_survival and not severe_survival:
            blockers.append("severe_cost_survival_not_ok")
        if _safe_float(base.get("cost_to_edge_ratio"), 999.0) > settings.max_cost_to_edge_ratio:
            blockers.append("cost_to_edge_ratio_not_ok")
        rollup = {
            "variant_id": variant_id,
            "entry_policy": first.get("entry_policy"),
            "stop_policy": first.get("stop_policy"),
            "target_policy": first.get("target_policy"),
            "max_holding_bars": first.get("max_holding_bars"),
            "primary_cost_model": settings.primary_cost_model,
            "primary": base,
            "severe": severe,
            "severe_cost_survival": severe_survival,
            "research_ready": not blockers,
            "blockers": blockers,
        }
        rollups.append(rollup)
    rollups.sort(key=lambda r: (
        bool(r.get("research_ready")),
        _safe_int((r.get("primary") or {}).get("positive_windows"), 0),
        _safe_float((r.get("primary") or {}).get("sum_r_post_cost"), 0.0),
        _safe_float((r.get("primary") or {}).get("weighted_avg_r_post_cost"), 0.0),
    ), reverse=True)
    best = rollups[0] if rollups else {}
    return rollups, best


def _pair_key(row: dict[str, Any]) -> str:
    return "|".join([
        str(row.get("candidate_id", "")),
        str(row.get("window_label", "")),
        str(row.get("variant_id", "")),
    ])


def _build_cost_break_even_report(trades: Sequence[dict[str, Any]], settings: LSRV2ExecutionAblationSettings, *, report_path: Path) -> dict[str, Any]:
    by_model: dict[str, dict[str, dict[str, Any]]] = {}
    for row in trades:
        by_model.setdefault(str(row.get("cost_model")), {})[_pair_key(row)] = row
    primary = by_model.get(settings.primary_cost_model, {})
    severe = by_model.get(settings.severe_cost_model, {})
    paired = 0
    win_to_nonwin = 0
    total_degradation_r = 0.0
    degradation_values: list[float] = []
    break_even_bps_values: list[float] = []
    fee_break_even_bps_values: list[float] = []
    maker_vs_taker_values: list[float] = []
    for key, p in primary.items():
        s = severe.get(key)
        if not s:
            continue
        paired += 1
        p_net = _safe_float(p.get("net_r"), 0.0)
        s_net = _safe_float(s.get("net_r"), 0.0)
        if p_net > settings.breakeven_r_abs and s_net <= settings.breakeven_r_abs:
            win_to_nonwin += 1
        degradation = p_net - s_net
        total_degradation_r += degradation
        degradation_values.append(degradation)
        cost_r_per_bps = _safe_div(_safe_float(p.get("cost_r"), 0.0), _safe_float(p.get("round_trip_cost_bps"), 0.0), None)
        if cost_r_per_bps and cost_r_per_bps > 0:
            gross_r = _safe_float(p.get("gross_r"), 0.0)
            break_even_bps_values.append(max(0.0, gross_r / cost_r_per_bps))
            fee_break_even_bps_values.append(max(0.0, gross_r / cost_r_per_bps / 2.0))
        # Approximate maker-vs-taker benefit: remove slippage from primary cost model.
        slippage_bps = _safe_float(p.get("slippage_bps"), 0.0)
        if cost_r_per_bps and cost_r_per_bps > 0:
            maker_vs_taker_values.append(slippage_bps * cost_r_per_bps)
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if paired else "WARN",
        "decision": "LSR_V2_COST_BREAK_EVEN_READY_DIAGNOSTIC" if paired else "KEEP_DIAGNOSTIC_LSR_V2_COST_BREAK_EVEN_NO_PAIRED_TRADES",
        "created_at": utc_now_iso(),
        "primary_cost_model": settings.primary_cost_model,
        "severe_cost_model": settings.severe_cost_model,
        "paired_trade_count": paired,
        "primary_win_to_severe_nonwin_count": win_to_nonwin,
        "primary_win_to_severe_nonwin_ratio": _round(_safe_div(win_to_nonwin, paired, 0.0) or 0.0, 8),
        "avg_primary_to_severe_degradation_r": _round(_avg(degradation_values) or 0.0, 8),
        "sum_primary_to_severe_degradation_r": _round(total_degradation_r, 8),
        "avg_slippage_break_even_bps": _round(_avg(break_even_bps_values) or 0.0, 8),
        "avg_fee_break_even_bps": _round(_avg(fee_break_even_bps_values) or 0.0, 8),
        "avg_maker_vs_taker_difference_r": _round(_avg(maker_vs_taker_values) or 0.0, 8),
        "orders_submitted_by_cost_break_even": 0,
        "positions_opened_by_cost_break_even": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(report_path),
    }
    _write_json(report_path, report)
    return report


def _classify(best: dict[str, Any], all_rollups: Sequence[dict[str, Any]], settings: LSRV2ExecutionAblationSettings) -> tuple[str, list[str], list[str]]:
    if not best:
        return NO_TRADES_DECISION, ["NO_ABLATION_TRADES"], ["no_variant_trades"]
    blockers = list(best.get("blockers") or [])
    labels: list[str] = []
    if best.get("research_ready"):
        return READY_DECISION, ["LSR_V2_EXECUTION_VARIANT_RESEARCH_READY"], []
    primary = best.get("primary") if isinstance(best.get("primary"), dict) else {}
    if _safe_int(primary.get("closed_trades"), 0) < settings.min_closed_trades:
        labels.append("LOW_SAMPLE_EDGE")
    if "severe_cost_survival_not_ok" in blockers or "cost_to_edge_ratio_not_ok" in blockers:
        labels.append("COST_SENSITIVE_EDGE")
    if "top_trade_concentration_not_ok" in blockers:
        labels.append("OUTLIER_DOMINATED_EDGE")
    if _safe_float(primary.get("sum_r_post_cost"), 0.0) > 0 or _safe_float(primary.get("weighted_avg_r_post_cost"), 0.0) > 0:
        labels.append("FRAGILE_POSITIVE_EDGE")
    if not labels:
        labels.append("REJECT_LSR_V2_CURRENT_EXECUTION")
    if "COST_SENSITIVE_EDGE" in labels:
        decision = COST_SENSITIVE_DECISION
    elif "FRAGILE_POSITIVE_EDGE" in labels:
        decision = FRAGILE_DECISION
    else:
        decision = REJECT_EXECUTION_DECISION
    return decision, list(dict.fromkeys(labels)), blockers


def run_lsr_v2_execution_ablation(settings: LSRV2ExecutionAblationSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2ExecutionAblationSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    report_path = data_dir / REPORT_NAME
    variants_path = data_dir / VARIANTS_REPORT_NAME
    trades_path = data_dir / TRADES_JSONL_NAME
    break_even_path = data_dir / COST_BREAK_EVEN_REPORT_NAME

    load_settings = _candidate_selection_settings(settings)
    rows, load_info = load_market_rows(load_settings)
    if not rows:
        no_matching = bool(load_info.get("no_matching_timeframe_data"))
        decision = NO_MATCHING_TIMEFRAME_DECISION if no_matching else NO_MARKET_DATA_DECISION
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": decision,
            "created_at": utc_now_iso(),
            "symbol": settings.symbol,
            "requested_timeframe": load_info.get("requested_timeframe", normalize_timeframe_label(settings.timeframe)),
            "detected_timeframe": load_info.get("detected_timeframe", ""),
            "timeframe_match": bool(load_info.get("timeframe_match", False)),
            "input_rows": 0,
            "input_path": load_info.get("input_path", ""),
            "tried_paths": load_info.get("tried_paths", []),
            "timeframe_mismatch_paths": load_info.get("timeframe_mismatch_paths", []),
            "load_errors": load_info.get("load_errors", []),
            "variant_count": len(build_default_variants()),
            "total_trade_rows": 0,
            "orders_submitted_by_lsr_v2_ablation": 0,
            "positions_opened_by_lsr_v2_ablation": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(report_path),
            "variants_report": str(variants_path),
            "trades_jsonl": str(trades_path),
            "cost_break_even_report": str(break_even_path),
        }
        _write_json(report_path, report)
        _write_json(variants_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": decision, "variants": []})
        _write_json(break_even_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": decision, "paired_trade_count": 0})
        _write_jsonl(trades_path, [])
        return report

    try:
        variants = build_default_variants()
        cost_scenarios = selected_cost_scenarios(settings.cost_models)
        all_summaries: list[dict[str, Any]] = []
        all_trades: list[dict[str, Any]] = []
        for window_size in settings.windows:
            summaries, trades = _simulate_window(
                rows=rows,
                window_size=int(window_size),
                cost_scenarios=cost_scenarios,
                variants=variants,
                settings=settings,
            )
            all_summaries.extend(summaries)
            all_trades.extend(trades)
        written_trades = _write_jsonl(trades_path, all_trades, max_rows=settings.max_trade_rows_to_write)
        variant_rollups, best = _build_variant_report(all_summaries, settings)
        _write_json(variants_path, {
            "prompt_id": PROMPT_ID,
            "status": "PASS" if variant_rollups else "WARN",
            "decision": "LSR_V2_EXECUTION_ABLATION_VARIANTS_READY_DIAGNOSTIC" if variant_rollups else NO_TRADES_DECISION,
            "created_at": utc_now_iso(),
            "settings": asdict(settings),
            "variant_count": len(variant_rollups),
            "best_variant_id": best.get("variant_id"),
            "variants": variant_rollups,
            "promotion_ready": False,
            "orders_submitted_by_lsr_v2_ablation_variants": 0,
            "positions_opened_by_lsr_v2_ablation_variants": 0,
        })
        break_even = _build_cost_break_even_report(all_trades, settings, report_path=break_even_path)
        decision, labels, blockers = _classify(best, variant_rollups, settings)
        status = "PASS" if all_trades else "WARN"
        report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": decision,
            "classification_labels": labels,
            "blockers": blockers,
            "created_at": utc_now_iso(),
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
            "cost_models": [asdict(c) | {"round_trip_cost_bps": c.round_trip_cost_bps} for c in cost_scenarios],
            "variant_count": len(variant_rollups),
            "total_trade_rows": len(all_trades),
            "written_trade_rows": written_trades,
            "best_variant": best,
            "best_variant_id": best.get("variant_id"),
            "best_primary_closed_trades": (best.get("primary") or {}).get("closed_trades") if isinstance(best.get("primary"), dict) else 0,
            "best_primary_positive_windows": (best.get("primary") or {}).get("positive_windows") if isinstance(best.get("primary"), dict) else 0,
            "best_primary_sum_r_post_cost": (best.get("primary") or {}).get("sum_r_post_cost") if isinstance(best.get("primary"), dict) else 0,
            "best_primary_weighted_avg_r_post_cost": (best.get("primary") or {}).get("weighted_avg_r_post_cost") if isinstance(best.get("primary"), dict) else 0,
            "best_severe_cost_survival": bool(best.get("severe_cost_survival")) if best else False,
            "cost_break_even_summary": {
                "paired_trade_count": break_even.get("paired_trade_count", 0),
                "primary_win_to_severe_nonwin_ratio": break_even.get("primary_win_to_severe_nonwin_ratio", 0.0),
                "avg_slippage_break_even_bps": break_even.get("avg_slippage_break_even_bps", 0.0),
                "avg_fee_break_even_bps": break_even.get("avg_fee_break_even_bps", 0.0),
                "avg_maker_vs_taker_difference_r": break_even.get("avg_maker_vs_taker_difference_r", 0.0),
            },
            "orders_submitted_by_lsr_v2_ablation": 0,
            "positions_opened_by_lsr_v2_ablation": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "promotion_blocked_reason": "execution ablation is diagnostic; requires walk-forward, embargoed OOS, bootstrap and promotion gate before paper supervised",
            "report": str(report_path),
            "variants_report": str(variants_path),
            "trades_jsonl": str(trades_path),
            "cost_break_even_report": str(break_even_path),
        }
        _write_json(report_path, report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": LOAD_ERROR_DECISION,
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "input_rows": len(rows),
            "input_path": load_info.get("input_path", ""),
            "orders_submitted_by_lsr_v2_ablation": 0,
            "positions_opened_by_lsr_v2_ablation": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(report_path),
            "variants_report": str(variants_path),
            "trades_jsonl": str(trades_path),
            "cost_break_even_report": str(break_even_path),
        }
        _write_json(report_path, report)
        return report
