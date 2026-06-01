"""Prompt 29.4.4s-7 — LSR-v2 backtest matrix / cost stress grid.

Diagnostic-only simulator for Liquidity Sweep Reversal v2 candidates.  It turns
LSR-v2 candidate_ready events into simulated trades across multiple history
windows and cost scenarios.  It never routes signals, calls brokers, submits
orders, opens positions, mutates paper state, or enables live/testnet/exchange
broker paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import json
import math
import statistics

from core.liquidity_sweep_reversal_v2 import (
    LSRV2Settings,
    detect_lsr_v2_candidates,
    load_market_rows,
    normalize_timeframe_label,
)

PROMPT_ID = "29.4.4s-7"
TRADE_EVENT_TYPE = "LSR_V2_BACKTEST_TRADE"
MATRIX_REPORT_NAME = "lsr_v2_backtest_matrix_report.json"
COST_STRESS_REPORT_NAME = "lsr_v2_cost_stress_report.json"
TRADE_FILE_PREFIX = "lsr_v2_trades"
READY_DECISION = "LSR_V2_BACKTEST_MATRIX_READY_DIAGNOSTIC"
NOT_READY_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_NOT_READY"
RESEARCH_READY_DECISION = "LSR_V2_RESEARCH_READY_REQUIRES_WF_OOS"
NO_MARKET_DATA_DECISION = "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
NO_MATCHING_TIMEFRAME_DECISION = "KEEP_DIAGNOSTIC_NO_MATCHING_TIMEFRAME_DATA"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_NO_BACKTEST_TRADES"
LOAD_ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_BACKTEST_ERROR"

PRIMARY_COST_MODEL = "conservative"
DEFAULT_WINDOWS = (10_000, 12_000, 15_000, 18_000, 20_000, 30_000, 50_000)
PRIMARY_VALIDATION_WINDOWS = (10_000, 12_000, 15_000, 18_000, 20_000)


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
        den = float(den)
        if abs(den) <= 1e-12:
            return default
        out = float(num) / den
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _round(value: Any, digits: int = 6) -> float | None:
    try:
        out = float(value)
        if math.isfinite(out):
            return round(out, digits)
    except Exception:
        pass
    return None


def _median(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    if not vals:
        return None
    return float(statistics.median(vals))


def _avg(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


@dataclass(frozen=True)
class CostScenario:
    name: str
    fee_rate: float
    spread_bps: float
    slippage_bps: float

    @property
    def round_trip_cost_bps(self) -> float:
        return self.fee_rate * 2.0 * 10_000.0 + self.spread_bps + self.slippage_bps


DEFAULT_COST_SCENARIOS: tuple[CostScenario, ...] = (
    CostScenario("base", fee_rate=0.0004, spread_bps=0.5, slippage_bps=0.5),
    CostScenario("conservative", fee_rate=0.0004, spread_bps=2.0, slippage_bps=3.0),
    CostScenario("severe", fee_rate=0.0008, spread_bps=5.0, slippage_bps=8.0),
)


@dataclass(frozen=True)
class LSRV2BacktestSettings:
    data_dir: str = "data"
    input_path: str | None = None
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    max_rows: int = 250_000
    windows: tuple[int, ...] = DEFAULT_WINDOWS
    primary_windows: tuple[int, ...] = PRIMARY_VALIDATION_WINDOWS
    cost_models: tuple[str, ...] = ("base", "conservative", "severe")
    max_holding_bars: int = 48
    starting_equity: float = 1000.0
    risk_per_trade_pct: float = 0.0025
    one_position_at_time: bool = True
    min_closed_trades: int = 30
    preferred_closed_trades: int = 50
    min_positive_windows: int = 3
    min_avg_r_post_cost: float = 0.0
    max_breakeven_ratio: float = 0.30
    breakeven_r_abs: float = 0.10
    max_top_trade_concentration: float = 0.45
    max_drawdown_r: float = 10.0
    strong_negative_window_r: float = -3.0
    require_severe_cost_survival: bool = True
    strict_timeframe: bool = True
    allow_timeframe_fallback: bool = False
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

    @classmethod
    def default(cls) -> "LSRV2BacktestSettings":
        return cls()


def parse_windows(raw: str | Sequence[int] | None) -> tuple[int, ...]:
    if raw is None:
        return DEFAULT_WINDOWS
    if isinstance(raw, str):
        vals: list[int] = []
        for token in raw.split(","):
            token = token.strip().lower().replace("_", "")
            if not token:
                continue
            mult = 1000 if token.endswith("k") else 1
            if token.endswith("k"):
                token = token[:-1]
            try:
                vals.append(int(float(token) * mult))
            except Exception:
                continue
        return tuple(dict.fromkeys(v for v in vals if v > 0)) or DEFAULT_WINDOWS
    return tuple(dict.fromkeys(int(v) for v in raw if int(v) > 0)) or DEFAULT_WINDOWS


def _window_label(size: int) -> str:
    if size % 1000 == 0:
        return f"{size // 1000}k"
    return str(size)


def _cost_scenarios_by_name() -> dict[str, CostScenario]:
    return {c.name: c for c in DEFAULT_COST_SCENARIOS}


def selected_cost_scenarios(names: Sequence[str] | None = None) -> tuple[CostScenario, ...]:
    by_name = _cost_scenarios_by_name()
    if not names:
        return DEFAULT_COST_SCENARIOS
    out: list[CostScenario] = []
    for name in names:
        key = str(name).strip().lower()
        if key in by_name and key not in {c.name for c in out}:
            out.append(by_name[key])
    return tuple(out) or DEFAULT_COST_SCENARIOS


def _candidate_selection_settings(settings: LSRV2BacktestSettings) -> LSRV2Settings:
    # Candidate selection uses the s-6b detector with neutral spread/slippage so
    # the cost grid stresses the same candidate set across scenarios.
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


def _simulate_candidate(
    *,
    rows: list[dict[str, Any]],
    candidate: dict[str, Any],
    window_size: int,
    window_label: str,
    cost: CostScenario,
    settings: LSRV2BacktestSettings,
) -> dict[str, Any] | None:
    if not candidate.get("candidate_ready"):
        return None
    levels = candidate.get("levels") if isinstance(candidate.get("levels"), dict) else {}
    entry = _safe_float(levels.get("entry_price"), 0.0)
    stop = _safe_float(levels.get("stop_loss"), 0.0)
    target = _safe_float(levels.get("take_profit"), 0.0)
    side = str(candidate.get("side", "")).upper()
    retest_index = candidate.get("retest_index")
    entry_index = _safe_int(retest_index, -1)
    if side not in {"BUY", "SELL"} or entry <= 0 or stop <= 0 or target <= 0 or entry_index < 0:
        return None
    if entry_index >= len(rows) - 1:
        return None
    risk_abs = abs(entry - stop)
    if risk_abs <= 0:
        return None

    exit_index: int | None = None
    exit_price: float | None = None
    exit_reason = "TIME_EXIT"
    ambiguous_hit = False
    max_i = min(len(rows) - 1, entry_index + max(1, int(settings.max_holding_bars)))
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
        "symbol": candidate.get("symbol", settings.symbol),
        "timeframe": settings.timeframe,
        "window_size": int(window_size),
        "window_label": window_label,
        "cost_model": cost.name,
        "side": side,
        "archetype": "LIQUIDITY_SWEEP_REVERSAL_V2",
        "entry_index": entry_index,
        "exit_index": exit_index,
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
        "orders_submitted_by_lsr_v2_backtest": 0,
        "positions_opened_by_lsr_v2_backtest": 0,
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


def _summarize_trades(trades: Sequence[dict[str, Any]], settings: LSRV2BacktestSettings) -> dict[str, Any]:
    closed = list(trades)
    r_values = [_safe_float(t.get("net_r"), 0.0) for t in closed]
    gross_values = [_safe_float(t.get("gross_r"), 0.0) for t in closed]
    wins = [r for r in r_values if r > settings.breakeven_r_abs]
    losses = [r for r in r_values if r < -settings.breakeven_r_abs]
    breakevens = [r for r in r_values if -settings.breakeven_r_abs <= r <= settings.breakeven_r_abs]
    positive_sum = sum(r for r in r_values if r > 0)
    negative_sum = abs(sum(r for r in r_values if r < 0))
    top_positive = max([r for r in r_values if r > 0], default=0.0)
    top_trade_concentration = _safe_div(top_positive, positive_sum, 0.0) or 0.0
    by_side: dict[str, dict[str, Any]] = {}
    for side in ("BUY", "SELL"):
        side_trades = [t for t in closed if str(t.get("side")) == side]
        side_r = [_safe_float(t.get("net_r"), 0.0) for t in side_trades]
        by_side[side] = {
            "closed_trades": len(side_trades),
            "sum_r_post_cost": _round(sum(side_r), 8),
            "avg_r_post_cost": _round(_avg(side_r) or 0.0, 8),
            "win_rate": _round(_safe_div(len([r for r in side_r if r > settings.breakeven_r_abs]), len(side_r), 0.0) or 0.0, 6),
        }
    by_exit_reason: dict[str, int] = {}
    by_regime: dict[str, int] = {}
    for t in closed:
        reason = str(t.get("exit_reason", "UNKNOWN"))
        by_exit_reason[reason] = by_exit_reason.get(reason, 0) + 1
        regime = str(t.get("regime", "UNKNOWN"))
        by_regime[regime] = by_regime.get(regime, 0) + 1
    count = len(closed)
    return {
        "closed_trades": count,
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), count, 0.0) or 0.0, 6),
        "loss_rate": _round(_safe_div(len(losses), count, 0.0) or 0.0, 6),
        "breakeven_ratio": _round(_safe_div(len(breakevens), count, 0.0) or 0.0, 6),
        "gross_avg_r": _round(_avg(gross_values) or 0.0, 8),
        "avg_r_post_cost": _round(_avg(r_values) or 0.0, 8),
        "median_r_post_cost": _round(_median(r_values) or 0.0, 8),
        "sum_r_post_cost": _round(sum(r_values), 8),
        "profit_factor_r": _round(_safe_div(positive_sum, negative_sum, None), 8),
        "max_drawdown_r": _round(_max_drawdown(r_values), 8),
        "top_trade_concentration": _round(top_trade_concentration, 8),
        "top_trade_concentration_ok": bool(top_trade_concentration <= settings.max_top_trade_concentration or positive_sum <= 0),
        "breakeven_drag_ok": bool((_safe_div(len(breakevens), count, 0.0) or 0.0) <= settings.max_breakeven_ratio),
        "by_side": by_side,
        "by_exit_reason": by_exit_reason,
        "by_regime": by_regime,
        "ambiguous_same_bar_hits": len([t for t in closed if t.get("ambiguous_same_bar_hit")]),
    }


def _simulate_window(
    *,
    rows: list[dict[str, Any]],
    window_size: int,
    cost: CostScenario,
    settings: LSRV2BacktestSettings,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    window_rows = rows[-window_size:] if len(rows) > window_size else list(rows)
    window_label = _window_label(min(window_size, len(window_rows))) if len(window_rows) < window_size else _window_label(window_size)
    detector_settings = _candidate_selection_settings(settings)
    candidates = detect_lsr_v2_candidates(window_rows, detector_settings)
    ready_candidates = [c for c in candidates if c.get("candidate_ready")]
    trades: list[dict[str, Any]] = []
    last_exit_index = -1
    skipped_overlap = 0
    for cand in ready_candidates:
        retest_i = _safe_int(cand.get("retest_index"), -1)
        if settings.one_position_at_time and retest_i <= last_exit_index:
            skipped_overlap += 1
            continue
        trade = _simulate_candidate(
            rows=window_rows,
            candidate=cand,
            window_size=window_size,
            window_label=window_label,
            cost=cost,
            settings=settings,
        )
        if trade is None:
            continue
        trades.append(trade)
        last_exit_index = max(last_exit_index, _safe_int(trade.get("exit_index"), last_exit_index))
    summary = _summarize_trades(trades, settings)
    summary.update({
        "window_size": int(window_size),
        "window_label": window_label,
        "actual_input_rows": len(window_rows),
        "cost_model": cost.name,
        "round_trip_cost_bps": _round(cost.round_trip_cost_bps, 6),
        "candidates_count": len(candidates),
        "candidate_ready_count": len(ready_candidates),
        "simulated_trades": len(trades),
        "skipped_overlap_candidates": skipped_overlap,
        "one_position_at_time": bool(settings.one_position_at_time),
    })
    return summary, trades


def _evaluate_primary_criteria(window_summaries: Sequence[dict[str, Any]], settings: LSRV2BacktestSettings) -> dict[str, Any]:
    primary = [s for s in window_summaries if s.get("cost_model") == PRIMARY_COST_MODEL and int(s.get("window_size", 0)) in set(settings.primary_windows)]
    positive = [s for s in primary if _safe_float(s.get("sum_r_post_cost"), 0.0) > 0]
    long_windows = [s for s in window_summaries if s.get("cost_model") == PRIMARY_COST_MODEL and int(s.get("window_size", 0)) >= 18_000]
    total_trades = sum(_safe_int(s.get("closed_trades"), 0) for s in primary)
    all_r_weighted_sum = sum(_safe_float(s.get("sum_r_post_cost"), 0.0) for s in primary)
    all_trade_count = sum(_safe_int(s.get("closed_trades"), 0) for s in primary)
    weighted_avg_r = _safe_div(all_r_weighted_sum, all_trade_count, 0.0) or 0.0
    long_strong_negative = [s for s in long_windows if _safe_float(s.get("sum_r_post_cost"), 0.0) <= settings.strong_negative_window_r]
    breakeven_ok = all(bool(s.get("breakeven_drag_ok", False)) for s in primary if _safe_int(s.get("closed_trades"), 0) > 0)
    concentration_ok = all(bool(s.get("top_trade_concentration_ok", False)) for s in primary if _safe_int(s.get("closed_trades"), 0) > 0)
    drawdown_ok = all(_safe_float(s.get("max_drawdown_r"), 999.0) <= settings.max_drawdown_r for s in primary if _safe_int(s.get("closed_trades"), 0) > 0)
    severe = [s for s in window_summaries if s.get("cost_model") == "severe" and int(s.get("window_size", 0)) in set(settings.primary_windows)]
    severe_positive = sum(1 for s in severe if _safe_float(s.get("sum_r_post_cost"), 0.0) > 0)
    severe_cost_survival = bool(severe and severe_positive >= settings.min_positive_windows)
    criteria = {
        "primary_cost_model": PRIMARY_COST_MODEL,
        "primary_windows": list(settings.primary_windows),
        "positive_windows": len(positive),
        "required_positive_windows": settings.min_positive_windows,
        "closed_trades": total_trades,
        "min_closed_trades": settings.min_closed_trades,
        "preferred_closed_trades": settings.preferred_closed_trades,
        "weighted_avg_r_post_cost": _round(weighted_avg_r, 8),
        "net_sum_r_post_cost": _round(all_r_weighted_sum, 8),
        "long_windows_strong_negative_count": len(long_strong_negative),
        "long_windows_strong_negative": [s.get("window_label") for s in long_strong_negative],
        "breakeven_drag_ok": bool(breakeven_ok),
        "top_trade_concentration_ok": bool(concentration_ok),
        "max_drawdown_ok": bool(drawdown_ok),
        "severe_cost_survival": bool(severe_cost_survival),
        "requires_severe_cost_survival": bool(settings.require_severe_cost_survival),
    }
    blockers: list[str] = []
    if len(positive) < settings.min_positive_windows:
        blockers.append("positive_windows_below_threshold")
    if total_trades < settings.min_closed_trades:
        blockers.append("closed_trades_below_minimum")
    if weighted_avg_r <= settings.min_avg_r_post_cost:
        blockers.append("weighted_avg_r_post_cost_not_positive")
    if all_r_weighted_sum <= 0:
        blockers.append("net_sum_r_post_cost_not_positive")
    if long_strong_negative:
        blockers.append("long_window_strong_negative")
    if not breakeven_ok:
        blockers.append("breakeven_drag_not_ok")
    if not concentration_ok:
        blockers.append("top_trade_concentration_not_ok")
    if not drawdown_ok:
        blockers.append("max_drawdown_not_ok")
    if settings.require_severe_cost_survival and not severe_cost_survival:
        blockers.append("severe_cost_survival_not_ok")
    criteria["research_ready"] = not blockers
    criteria["blockers"] = blockers
    return criteria


def _build_cost_stress_report(window_summaries: Sequence[dict[str, Any]], settings: LSRV2BacktestSettings, *, report_path: Path) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for s in window_summaries:
        by_model.setdefault(str(s.get("cost_model", "UNKNOWN")), []).append(s)
    model_summary: dict[str, dict[str, Any]] = {}
    for model, rows in by_model.items():
        closed = sum(_safe_int(r.get("closed_trades"), 0) for r in rows)
        net_r = sum(_safe_float(r.get("sum_r_post_cost"), 0.0) for r in rows)
        positive_windows = sum(1 for r in rows if _safe_float(r.get("sum_r_post_cost"), 0.0) > 0)
        model_summary[model] = {
            "windows": len(rows),
            "closed_trades": closed,
            "sum_r_post_cost": _round(net_r, 8),
            "weighted_avg_r_post_cost": _round(_safe_div(net_r, closed, 0.0) or 0.0, 8),
            "positive_windows": positive_windows,
            "negative_windows": len(rows) - positive_windows,
        }
    base = model_summary.get("base", {})
    conservative = model_summary.get("conservative", {})
    severe = model_summary.get("severe", {})
    base_net = _safe_float(base.get("sum_r_post_cost"), 0.0)
    cons_net = _safe_float(conservative.get("sum_r_post_cost"), 0.0)
    severe_net = _safe_float(severe.get("sum_r_post_cost"), 0.0)
    report = {
        "prompt_id": PROMPT_ID,
        "status": "PASS",
        "decision": "LSR_V2_COST_STRESS_READY_DIAGNOSTIC",
        "created_at": utc_now_iso(),
        "model_summary": model_summary,
        "base_to_conservative_delta_r": _round(cons_net - base_net, 8),
        "conservative_to_severe_delta_r": _round(severe_net - cons_net, 8),
        "severe_cost_survival": bool(severe and _safe_int(severe.get("positive_windows"), 0) >= settings.min_positive_windows),
        "orders_submitted_by_cost_stress": 0,
        "positions_opened_by_cost_stress": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(report_path),
    }
    _write_json(report_path, report)
    return report


def run_lsr_v2_backtest_matrix(settings: LSRV2BacktestSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2BacktestSettings.default()
    data_dir = Path(settings.data_dir)
    matrix_path = data_dir / MATRIX_REPORT_NAME
    cost_path = data_dir / COST_STRESS_REPORT_NAME
    data_dir.mkdir(parents=True, exist_ok=True)

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
            "load_errors": load_info.get("load_errors", []),
            "timeframe_mismatch_paths": load_info.get("timeframe_mismatch_paths", []),
            "windows": list(settings.windows),
            "cost_models": list(settings.cost_models),
            "window_summaries": [],
            "criteria": {"research_ready": False, "blockers": ["no_market_data_or_no_matching_timeframe"]},
            "orders_submitted_by_lsr_v2_backtest": 0,
            "positions_opened_by_lsr_v2_backtest": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(matrix_path),
            "cost_stress_report": str(cost_path),
        }
        _write_json(matrix_path, report)
        _write_json(cost_path, {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": decision,
            "created_at": utc_now_iso(),
            "model_summary": {},
            "orders_submitted_by_cost_stress": 0,
            "positions_opened_by_cost_stress": 0,
            "promotion_ready": False,
            "report": str(cost_path),
        })
        return report

    try:
        cost_scenarios = selected_cost_scenarios(settings.cost_models)
        window_summaries: list[dict[str, Any]] = []
        all_trade_files: dict[str, str] = {}
        total_trades = 0
        for window_size in settings.windows:
            window_trades_all_costs: list[dict[str, Any]] = []
            for cost in cost_scenarios:
                summary, trades = _simulate_window(rows=rows, window_size=int(window_size), cost=cost, settings=settings)
                window_summaries.append(summary)
                window_trades_all_costs.extend(trades)
                total_trades += len(trades)
            label = _window_label(int(window_size))
            trade_path = data_dir / f"{TRADE_FILE_PREFIX}_{label}.jsonl"
            _write_jsonl(trade_path, window_trades_all_costs)
            all_trade_files[label] = str(trade_path)
        criteria = _evaluate_primary_criteria(window_summaries, settings)
        cost_report = _build_cost_stress_report(window_summaries, settings, report_path=cost_path)
        if total_trades <= 0:
            decision = NO_TRADES_DECISION
            status = "WARN"
        elif criteria.get("research_ready"):
            decision = RESEARCH_READY_DECISION
            status = "PASS"
        else:
            decision = NOT_READY_DECISION
            status = "PASS"
        report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": decision,
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
            "tried_paths": load_info.get("tried_paths", []),
            "load_errors": load_info.get("load_errors", []),
            "settings": asdict(settings),
            "candidate_selection_note": "same neutral-spread LSR-v2 candidate set is stressed across cost models; costs are applied in simulated trade PnL",
            "windows": list(settings.windows),
            "primary_windows": list(settings.primary_windows),
            "cost_models": [asdict(c) | {"round_trip_cost_bps": c.round_trip_cost_bps} for c in cost_scenarios],
            "total_simulated_trade_rows": total_trades,
            "window_summaries": window_summaries,
            "criteria": criteria,
            "cost_stress_summary": cost_report.get("model_summary", {}),
            "trade_files": all_trade_files,
            "orders_submitted_by_lsr_v2_backtest": 0,
            "positions_opened_by_lsr_v2_backtest": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "promotion_blocked_reason": "requires walk-forward, embargoed OOS, bootstrap and strategy promotion gate even if research_ready=true",
            "report": str(matrix_path),
            "cost_stress_report": str(cost_path),
        }
        _write_json(matrix_path, report)
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
            "orders_submitted_by_lsr_v2_backtest": 0,
            "positions_opened_by_lsr_v2_backtest": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(matrix_path),
            "cost_stress_report": str(cost_path),
        }
        _write_json(matrix_path, report)
        return report
