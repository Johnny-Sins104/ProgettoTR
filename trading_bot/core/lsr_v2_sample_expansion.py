"""Prompt 29.4.4s-7e — LSR-v2 sample expansion / data horizon robustness audit.

Diagnostic-only expansion layer for the locked LSR-v2 research profile:
LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24.

The audit scans available market-data cache files for requested assets and
requested timeframes, reruns the locked profile across an expanded window set,
and summarizes whether the low-sample blocker is likely a data-horizon problem,
an asset/timeframe specificity problem, or a structural insufficiency of the
profile.

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
import re

from core.liquidity_sweep_reversal_v2 import (
    LSRV2Settings,
    infer_timeframe_from_path,
    load_market_rows,
    normalize_timeframe_label,
)
from core.lsr_v2_backtest_matrix import parse_windows, selected_cost_scenarios
from core.lsr_v2_execution_ablation import LSRV2ExecutionAblationSettings, _simulate_window
from core.lsr_v2_locked_profile import LOCKED_PROFILE_NAME, LOCKED_VARIANT_ID, locked_variant

PROMPT_ID = "29.4.4s-7e"
TRADE_EVENT_TYPE = "LSR_V2_SAMPLE_EXPANSION_TRADE"
REPORT_NAME = "lsr_v2_sample_expansion_report.json"
BY_ASSET_NAME = "lsr_v2_sample_expansion_by_asset.json"
BY_TIMEFRAME_NAME = "lsr_v2_sample_expansion_by_timeframe.json"
TRADES_JSONL_NAME = "lsr_v2_sample_expansion_trades.jsonl"

READY_DECISION = "LSR_V2_SAMPLE_EXPANSION_READY_FOR_WALK_FORWARD"
LOW_SAMPLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LOW_SAMPLE"
ASSET_SPECIFIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_ASSET_SPECIFIC"
TIMEFRAME_SPECIFIC_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_TIMEFRAME_SPECIFIC"
REJECT_DECISION = "REJECT_LSR_V2_INSUFFICIENT_SAMPLE"
NO_MARKET_DATA_DECISION = "KEEP_DIAGNOSTIC_NO_MARKET_DATA"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SAMPLE_EXPANSION_ERROR"

DEFAULT_SAMPLE_WINDOWS = (10_000, 12_000, 15_000, 18_000, 20_000, 30_000, 50_000, 100_000, 150_000)
DEFAULT_SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT")
DEFAULT_TIMEFRAMES = ("5m", "15m")
MARKET_EXTENSIONS = {".parquet", ".csv", ".jsonl", ".json"}
EXCLUDED_FILE_NAMES = {
    REPORT_NAME,
    BY_ASSET_NAME,
    BY_TIMEFRAME_NAME,
    TRADES_JSONL_NAME,
    "lsr_v2_candidate_audit.jsonl",
    "lsr_v2_candidate_audit_report.json",
    "lsr_v2_backtest_matrix_report.json",
    "lsr_v2_cost_stress_report.json",
    "lsr_v2_trade_forensics_report.json",
    "lsr_v2_trade_forensics_by_window.json",
    "lsr_v2_cost_failure_attribution_report.json",
    "lsr_v2_execution_ablation_report.json",
    "lsr_v2_execution_ablation_variants.json",
    "lsr_v2_execution_ablation_trades.jsonl",
    "lsr_v2_cost_break_even_report.json",
    "lsr_v2_locked_profile_report.json",
    "lsr_v2_locked_profile_trades.jsonl",
    "lsr_v2_locked_profile_cost_drilldown.json",
    "lsr_v2_locked_profile_window_stability.json",
    "trade_level_telemetry.jsonl",
}


@dataclass(frozen=True)
class LSRV2SampleExpansionSettings:
    data_dir: str = "data"
    input_path: str | None = None
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES
    windows: tuple[int, ...] = DEFAULT_SAMPLE_WINDOWS
    cost_models: tuple[str, ...] = ("base", "conservative", "severe")
    primary_cost_model: str = "conservative"
    severe_cost_model: str = "severe"
    max_rows: int = 250_000
    starting_equity: float = 1000.0
    risk_per_trade_pct: float = 0.0025
    min_closed_trades: int = 30
    preferred_closed_trades: int = 50
    min_positive_windows: int = 3
    min_severe_positive_windows: int = 3
    min_avg_r_post_cost: float = 0.0
    min_sum_r_post_cost: float = 0.0
    max_top_trade_concentration: float = 0.45
    strong_negative_window_r: float = -3.0
    max_drawdown_r: float = 10.0
    breakeven_r_abs: float = 0.10
    max_breakeven_ratio: float = 0.30
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
    def default(cls) -> "LSRV2SampleExpansionSettings":
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
    size = int(size)
    if size % 1000 == 0:
        return f"{size // 1000}k"
    return str(size)


def _parse_csv_tuple(raw: str | Sequence[str] | None, default: Sequence[str]) -> tuple[str, ...]:
    if raw is None:
        return tuple(default)
    if isinstance(raw, str):
        values = [x.strip() for x in raw.split(",") if x.strip()]
    else:
        values = [str(x).strip() for x in raw if str(x).strip()]
    return tuple(dict.fromkeys(values)) or tuple(default)


def parse_symbols(raw: str | Sequence[str] | None) -> tuple[str, ...]:
    return _parse_csv_tuple(raw, DEFAULT_SYMBOLS)


def parse_timeframes(raw: str | Sequence[str] | None) -> tuple[str, ...]:
    vals = tuple(normalize_timeframe_label(x) for x in _parse_csv_tuple(raw, DEFAULT_TIMEFRAMES))
    return tuple(dict.fromkeys(v for v in vals if v)) or DEFAULT_TIMEFRAMES


def _symbol_key(symbol: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(symbol or "").lower())


def _infer_symbol_from_path(path: Path, requested_symbols: Sequence[str]) -> str:
    name = path.name.lower()
    for symbol in requested_symbols:
        base = _symbol_key(symbol)
        asset = base.replace("usdt", "")
        if base and base in re.sub(r"[^a-z0-9]", "", name):
            return symbol
        if asset and re.search(rf"(^|[^a-z0-9]){re.escape(asset)}([^a-z0-9]|$)", name):
            return symbol
    # Known fallback aliases.  These are only used for report labeling.
    aliases = {"btc": "BTC/USDT", "eth": "ETH/USDT", "sol": "SOL/USDT", "bnb": "BNB/USDT"}
    for token, symbol in aliases.items():
        if re.search(rf"(^|[^a-z0-9]){token}([^a-z0-9]|$)", name):
            return symbol
    return requested_symbols[0] if requested_symbols else "UNKNOWN"


def _market_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in MARKET_EXTENSIONS:
        return False
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    if path.name.startswith("lsr_v2_") or path.name.startswith("paper_"):
        return False
    return True


def discover_market_inputs(settings: LSRV2SampleExpansionSettings) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data_dir = Path(settings.data_dir)
    requested_timeframes = set(parse_timeframes(settings.timeframes))
    requested_symbols = parse_symbols(settings.symbols)
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    if settings.input_path:
        path = Path(settings.input_path)
        detected_tf = infer_timeframe_from_path(path)
        symbol = _infer_symbol_from_path(path, requested_symbols)
        included.append({
            "path": str(path),
            "symbol": symbol,
            "timeframe": normalize_timeframe_label(detected_tf if detected_tf != "UNKNOWN" else next(iter(requested_timeframes), "")),
            "detected_timeframe": detected_tf,
            "explicit_input": True,
        })
        return included, {"included_count": 1, "excluded": excluded, "explicit_input": True}

    if not data_dir.exists():
        return [], {"included_count": 0, "excluded": [], "explicit_input": False, "missing_data_dir": str(data_dir)}

    seen: set[str] = set()
    for path in sorted(data_dir.glob("*")):
        if not _market_file(path):
            continue
        detected_tf = normalize_timeframe_label(infer_timeframe_from_path(path))
        symbol = _infer_symbol_from_path(path, requested_symbols)
        symbol_allowed = symbol in requested_symbols
        timeframe_allowed = detected_tf in requested_timeframes
        item = {"path": str(path), "symbol": symbol, "detected_timeframe": detected_tf, "timeframe": detected_tf}
        if not timeframe_allowed:
            item["excluded_reason"] = "timeframe_not_requested"
            excluded.append(item)
            continue
        if not symbol_allowed:
            item["excluded_reason"] = "symbol_not_requested"
            excluded.append(item)
            continue
        key = f"{symbol}|{detected_tf}|{path.resolve()}"
        if key in seen:
            continue
        seen.add(key)
        item["explicit_input"] = False
        included.append(item)
    return included, {"included_count": len(included), "excluded": excluded, "explicit_input": False}


def _ablation_settings_for_target(settings: LSRV2SampleExpansionSettings, target: dict[str, Any], rows_count: int | None = None) -> LSRV2ExecutionAblationSettings:
    return LSRV2ExecutionAblationSettings(
        data_dir=settings.data_dir,
        input_path=target.get("path"),
        symbol=str(target.get("symbol", "BTC/USDT")),
        timeframe=str(target.get("timeframe", "5m")),
        max_rows=settings.max_rows,
        windows=settings.windows,
        primary_windows=settings.windows,
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
        breakeven_r_abs=settings.breakeven_r_abs,
        max_breakeven_ratio=settings.max_breakeven_ratio,
        max_top_trade_concentration=settings.max_top_trade_concentration,
        max_drawdown_r=settings.max_drawdown_r,
        strong_negative_window_r=settings.strong_negative_window_r,
        min_severe_positive_windows=settings.min_severe_positive_windows,
        require_severe_cost_survival=True,
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


def _load_settings_for_target(settings: LSRV2SampleExpansionSettings, target: dict[str, Any]) -> LSRV2Settings:
    return LSRV2Settings(
        data_dir=settings.data_dir,
        input_path=str(target.get("path")),
        symbol=str(target.get("symbol", "BTC/USDT")),
        timeframe=str(target.get("timeframe", "5m")),
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


def _positive_concentration(net_values: Sequence[float]) -> tuple[float, float, float]:
    positives = sorted((float(v) for v in net_values if float(v) > 0), reverse=True)
    total = sum(positives)
    if total <= 0 or not positives:
        return 0.0, 0.0, 0.0
    return positives[0] / total, sum(positives[:3]) / total, sum(positives[:5]) / total


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += float(value)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def _summarize_trade_rows(trades: Sequence[dict[str, Any]], settings: LSRV2SampleExpansionSettings) -> dict[str, Any]:
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
        "sum_gross_r": _round(gross_sum, 8),
        "sum_cost_r": _round(cost_sum, 8),
        "cost_to_edge_ratio": _round(_safe_div(cost_sum, gross_sum, 999.0) if gross_sum > 0 else 999.0, 8),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakevens),
        "win_rate": _round(_safe_div(len(wins), len(trades), 0.0) or 0.0, 8),
        "loss_rate": _round(_safe_div(len(losses), len(trades), 0.0) or 0.0, 8),
        "breakeven_rate": _round(_safe_div(len(breakevens), len(trades), 0.0) or 0.0, 8),
        "max_drawdown_r": _round(_max_drawdown(net), 8),
        "top_1_positive_concentration": _round(top1, 8),
        "top_3_positive_concentration": _round(top3, 8),
        "top_5_positive_concentration": _round(top5, 8),
        "exit_reason_counts": dict(sorted(by_exit.items())),
        "side_counts": dict(sorted(by_side.items())),
        "window_trade_counts": dict(sorted(by_window.items())),
    }


def _target_key(symbol: str, timeframe: str) -> str:
    return f"{symbol}|{timeframe}"


def _simulate_target(settings: LSRV2SampleExpansionSettings, target: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    load_settings = _load_settings_for_target(settings, target)
    rows, load_info = load_market_rows(load_settings)
    symbol = str(target.get("symbol", load_settings.symbol))
    timeframe = str(load_info.get("detected_timeframe") or target.get("timeframe") or load_settings.timeframe)
    if not rows:
        summary = {
            "status": "WARN",
            "decision": NO_MARKET_DATA_DECISION,
            "symbol": symbol,
            "timeframe": timeframe,
            "input_path": str(target.get("path", "")),
            "input_rows": 0,
            "load_info": load_info,
            "closed_trades": 0,
            "positive_primary_windows": 0,
            "positive_severe_windows": 0,
            "blockers": ["no_market_data"],
        }
        return summary, []

    cost_scenarios = selected_cost_scenarios(settings.cost_models)
    variant = locked_variant()
    ablation_settings = _ablation_settings_for_target(settings, {**target, "timeframe": timeframe}, len(rows))
    target_windows = tuple(int(w) for w in settings.windows if int(w) <= len(rows)) or (len(rows),)
    all_summaries: list[dict[str, Any]] = []
    all_trades: list[dict[str, Any]] = []
    for window_size in target_windows:
        summaries, trades = _simulate_window(
            rows=rows,
            window_size=int(window_size),
            cost_scenarios=cost_scenarios,
            variants=(variant,),
            settings=ablation_settings,
        )
        all_summaries.extend(summaries)
        all_trades.extend(trades)

    for trade in all_trades:
        trade["prompt_id"] = PROMPT_ID
        trade["event_type"] = TRADE_EVENT_TYPE
        trade["locked_profile_name"] = LOCKED_PROFILE_NAME
        trade["locked_variant_id"] = LOCKED_VARIANT_ID
        trade["sample_expansion_symbol"] = symbol
        trade["sample_expansion_timeframe"] = timeframe
        trade["input_path"] = str(target.get("path", ""))
        trade["orders_submitted_by_lsr_v2_sample_expansion"] = 0
        trade["positions_opened_by_lsr_v2_sample_expansion"] = 0
        trade["submit_order"] = False
        trade["broker_submit_called"] = False
        trade["audit_only"] = True
        trade["live_allowed"] = False
        trade["testnet_allowed"] = False
        trade["exchange_broker_allowed"] = False

    primary = [t for t in all_trades if str(t.get("cost_model")) == settings.primary_cost_model]
    severe = [t for t in all_trades if str(t.get("cost_model")) == settings.severe_cost_model]
    primary_summary = _summarize_trade_rows(primary, settings)
    severe_summary = _summarize_trade_rows(severe, settings)
    primary_windows = [s for s in all_summaries if str(s.get("cost_model")) == settings.primary_cost_model]
    severe_windows = [s for s in all_summaries if str(s.get("cost_model")) == settings.severe_cost_model]
    positive_primary_windows = sum(1 for s in primary_windows if _safe_float(s.get("sum_r_post_cost"), 0.0) > 0)
    positive_severe_windows = sum(1 for s in severe_windows if _safe_float(s.get("sum_r_post_cost"), 0.0) > 0)
    strong_negative_primary = sum(1 for s in primary_windows if _safe_float(s.get("sum_r_post_cost"), 0.0) <= settings.strong_negative_window_r)
    summary = {
        "status": "PASS" if all_trades else "WARN",
        "decision": "LSR_V2_SAMPLE_EXPANSION_TARGET_READY_DIAGNOSTIC" if all_trades else LOW_SAMPLE_DECISION,
        "symbol": symbol,
        "timeframe": timeframe,
        "input_path": str(target.get("path", "")),
        "input_rows": len(rows),
        "windows_requested": list(settings.windows),
        "windows_evaluated": list(target_windows),
        "cost_models": list(settings.cost_models),
        "primary_cost_model": settings.primary_cost_model,
        "severe_cost_model": settings.severe_cost_model,
        "positive_primary_windows": positive_primary_windows,
        "positive_severe_windows": positive_severe_windows,
        "strong_negative_primary_windows": strong_negative_primary,
        "primary": primary_summary,
        "severe": severe_summary,
        "window_summaries": all_summaries,
        "load_info": load_info,
        "orders_submitted_by_lsr_v2_sample_expansion_target": 0,
        "positions_opened_by_lsr_v2_sample_expansion_target": 0,
        "promotion_ready": False,
    }
    return summary, all_trades


def _group_report(trades: Sequence[dict[str, Any]], group_key: str, settings: LSRV2SampleExpansionSettings) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        if str(trade.get("cost_model")) != settings.primary_cost_model:
            continue
        key = str(trade.get(group_key, "UNKNOWN"))
        grouped.setdefault(key, []).append(trade)
    rows: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        summary = _summarize_trade_rows(items, settings)
        summary[group_key] = key
        rows.append(summary)
    return rows


def _classify(global_summary: dict[str, Any], targets: Sequence[dict[str, Any]], settings: LSRV2SampleExpansionSettings) -> tuple[str, list[str], list[str]]:
    labels: list[str] = []
    blockers: list[str] = []
    closed = _safe_int(global_summary.get("closed_trades"), 0)
    positive = _safe_int(global_summary.get("positive_primary_windows"), 0)
    severe_positive = _safe_int(global_summary.get("positive_severe_windows"), 0)
    avg_r = _safe_float(global_summary.get("avg_r_post_cost"), 0.0)
    sum_r = _safe_float(global_summary.get("sum_r_post_cost"), 0.0)
    top3 = _safe_float(global_summary.get("top_3_positive_concentration"), 0.0)

    if closed < settings.min_closed_trades:
        labels.append("LOW_SAMPLE_EDGE")
        blockers.append("closed_trades_below_minimum")
    if closed >= settings.min_closed_trades and closed < settings.preferred_closed_trades:
        labels.append("LOW_SAMPLE_EDGE")
    if positive < settings.min_positive_windows:
        labels.append("WINDOW_INSTABILITY_EDGE")
        blockers.append("positive_windows_below_threshold")
    if severe_positive < settings.min_severe_positive_windows:
        labels.append("COST_SENSITIVE_EDGE")
        blockers.append("severe_cost_survival_not_ok")
    if avg_r <= settings.min_avg_r_post_cost or sum_r <= settings.min_sum_r_post_cost:
        labels.append("NEGATIVE_OR_FLAT_EDGE")
        blockers.append("primary_edge_not_positive")
    if top3 > settings.max_top_trade_concentration:
        labels.append("OUTLIER_DOMINATED_EDGE")
        blockers.append("top_trade_concentration_not_ok")

    analyzed_assets = {str(t.get("symbol")) for t in targets if _safe_int((t.get("primary") or {}).get("closed_trades"), 0) > 0}
    analyzed_timeframes = {str(t.get("timeframe")) for t in targets if _safe_int((t.get("primary") or {}).get("closed_trades"), 0) > 0}
    requested_assets = set(parse_symbols(settings.symbols))
    requested_timeframes = set(parse_timeframes(settings.timeframes))
    if len(requested_assets) > 1 and len(analyzed_assets) <= 1:
        labels.append("ASSET_SPECIFIC_OR_UNTESTED")
    if len(requested_timeframes) > 1 and len(analyzed_timeframes) <= 1:
        labels.append("TIMEFRAME_SPECIFIC_OR_UNTESTED")

    labels = list(dict.fromkeys(labels)) or ["FRAGILE_POSITIVE_EDGE"]
    blockers = list(dict.fromkeys(blockers))
    if not blockers:
        return READY_DECISION, ["RESEARCH_READY_FOR_WALK_FORWARD"], []
    if "closed_trades_below_minimum" in blockers and closed == 0:
        return REJECT_DECISION, labels, blockers
    if "closed_trades_below_minimum" in blockers:
        return LOW_SAMPLE_DECISION, labels, blockers
    if "severe_cost_survival_not_ok" in blockers:
        return TIMEFRAME_SPECIFIC_DECISION if "TIMEFRAME_SPECIFIC_OR_UNTESTED" in labels else LOW_SAMPLE_DECISION, labels, blockers
    if "positive_windows_below_threshold" in blockers:
        return TIMEFRAME_SPECIFIC_DECISION if "TIMEFRAME_SPECIFIC_OR_UNTESTED" in labels else ASSET_SPECIFIC_DECISION, labels, blockers
    return LOW_SAMPLE_DECISION, labels, blockers


def _safe_no_data_report(settings: LSRV2SampleExpansionSettings, discovery: dict[str, Any], *, report_path: Path, by_asset_path: Path, by_tf_path: Path, trades_path: Path) -> dict[str, Any]:
    report = {
        "prompt_id": PROMPT_ID,
        "status": "WARN",
        "decision": NO_MARKET_DATA_DECISION,
        "classification_labels": [],
        "blockers": ["no_market_data"],
        "created_at": utc_now_iso(),
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "requested_symbols": list(parse_symbols(settings.symbols)),
        "requested_timeframes": list(parse_timeframes(settings.timeframes)),
        "windows": list(settings.windows),
        "market_discovery": discovery,
        "datasets_analyzed": 0,
        "closed_trades": 0,
        "orders_submitted_by_lsr_v2_sample_expansion": 0,
        "positions_opened_by_lsr_v2_sample_expansion": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(report_path),
        "by_asset_report": str(by_asset_path),
        "by_timeframe_report": str(by_tf_path),
        "trades_jsonl": str(trades_path),
    }
    _write_json(report_path, report)
    _write_json(by_asset_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_MARKET_DATA_DECISION, "assets": []})
    _write_json(by_tf_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_MARKET_DATA_DECISION, "timeframes": []})
    _write_jsonl(trades_path, [])
    return report


def run_lsr_v2_sample_expansion(settings: LSRV2SampleExpansionSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2SampleExpansionSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    report_path = data_dir / REPORT_NAME
    by_asset_path = data_dir / BY_ASSET_NAME
    by_tf_path = data_dir / BY_TIMEFRAME_NAME
    trades_path = data_dir / TRADES_JSONL_NAME

    targets, discovery = discover_market_inputs(settings)
    if not targets:
        return _safe_no_data_report(settings, discovery, report_path=report_path, by_asset_path=by_asset_path, by_tf_path=by_tf_path, trades_path=trades_path)

    try:
        target_reports: list[dict[str, Any]] = []
        all_trades: list[dict[str, Any]] = []
        for target in targets:
            target_report, trades = _simulate_target(settings, target)
            target_reports.append(target_report)
            all_trades.extend(trades)

        written = _write_jsonl(trades_path, all_trades, max_rows=settings.max_trade_rows_to_write)
        primary_trades = [t for t in all_trades if str(t.get("cost_model")) == settings.primary_cost_model]
        severe_trades = [t for t in all_trades if str(t.get("cost_model")) == settings.severe_cost_model]
        global_primary = _summarize_trade_rows(primary_trades, settings)
        global_severe = _summarize_trade_rows(severe_trades, settings)
        positive_primary_windows = 0
        positive_severe_windows = 0
        for target in target_reports:
            positive_primary_windows += _safe_int(target.get("positive_primary_windows"), 0)
            positive_severe_windows += _safe_int(target.get("positive_severe_windows"), 0)
        global_primary["positive_primary_windows"] = positive_primary_windows
        global_primary["positive_severe_windows"] = positive_severe_windows
        decision, labels, blockers = _classify(global_primary, target_reports, settings)
        status = "PASS" if target_reports else "WARN"

        by_asset_rows = _group_report(all_trades, "sample_expansion_symbol", settings)
        by_timeframe_rows = _group_report(all_trades, "sample_expansion_timeframe", settings)
        by_asset_report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": "LSR_V2_SAMPLE_EXPANSION_BY_ASSET_READY_DIAGNOSTIC" if by_asset_rows else LOW_SAMPLE_DECISION,
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "primary_cost_model": settings.primary_cost_model,
            "assets": by_asset_rows,
            "orders_submitted_by_lsr_v2_sample_expansion_by_asset": 0,
            "positions_opened_by_lsr_v2_sample_expansion_by_asset": 0,
            "promotion_ready": False,
            "report": str(by_asset_path),
        }
        by_tf_report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": "LSR_V2_SAMPLE_EXPANSION_BY_TIMEFRAME_READY_DIAGNOSTIC" if by_timeframe_rows else LOW_SAMPLE_DECISION,
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "primary_cost_model": settings.primary_cost_model,
            "timeframes": by_timeframe_rows,
            "orders_submitted_by_lsr_v2_sample_expansion_by_timeframe": 0,
            "positions_opened_by_lsr_v2_sample_expansion_by_timeframe": 0,
            "promotion_ready": False,
            "report": str(by_tf_path),
        }
        _write_json(by_asset_path, by_asset_report)
        _write_json(by_tf_path, by_tf_report)

        report = {
            "prompt_id": PROMPT_ID,
            "status": status,
            "decision": decision,
            "classification_labels": labels,
            "blockers": blockers,
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "requested_symbols": list(parse_symbols(settings.symbols)),
            "requested_timeframes": list(parse_timeframes(settings.timeframes)),
            "windows": list(settings.windows),
            "cost_models": list(settings.cost_models),
            "primary_cost_model": settings.primary_cost_model,
            "severe_cost_model": settings.severe_cost_model,
            "settings": asdict(settings),
            "market_discovery": discovery,
            "datasets_analyzed": len(target_reports),
            "datasets_with_trades": sum(1 for r in target_reports if _safe_int((r.get("primary") or {}).get("closed_trades"), 0) > 0),
            "input_rows_total": sum(_safe_int(r.get("input_rows"), 0) for r in target_reports),
            "total_trade_rows": len(all_trades),
            "written_trade_rows": written,
            "closed_trades": global_primary.get("closed_trades", 0),
            "preferred_closed_trades": settings.preferred_closed_trades,
            "min_closed_trades": settings.min_closed_trades,
            "positive_primary_windows": positive_primary_windows,
            "positive_severe_windows": positive_severe_windows,
            "avg_r_post_cost": global_primary.get("avg_r_post_cost", 0.0),
            "sum_r_post_cost": global_primary.get("sum_r_post_cost", 0.0),
            "severe_avg_r_post_cost": global_severe.get("avg_r_post_cost", 0.0),
            "severe_sum_r_post_cost": global_severe.get("sum_r_post_cost", 0.0),
            "top_1_positive_concentration": global_primary.get("top_1_positive_concentration", 0.0),
            "top_3_positive_concentration": global_primary.get("top_3_positive_concentration", 0.0),
            "top_5_positive_concentration": global_primary.get("top_5_positive_concentration", 0.0),
            "win_rate": global_primary.get("win_rate", 0.0),
            "loss_rate": global_primary.get("loss_rate", 0.0),
            "breakeven_rate": global_primary.get("breakeven_rate", 0.0),
            "max_drawdown_r": global_primary.get("max_drawdown_r", 0.0),
            "asset_count_with_trades": len({str(t.get("sample_expansion_symbol")) for t in primary_trades}),
            "timeframe_count_with_trades": len({str(t.get("sample_expansion_timeframe")) for t in primary_trades}),
            "target_reports": target_reports,
            "orders_submitted_by_lsr_v2_sample_expansion": 0,
            "positions_opened_by_lsr_v2_sample_expansion": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "promotion_blocked_reason": "sample expansion is diagnostic; requires walk-forward, embargoed OOS, bootstrap and promotion gate before paper supervised",
            "report": str(report_path),
            "by_asset_report": str(by_asset_path),
            "by_timeframe_report": str(by_tf_path),
            "trades_jsonl": str(trades_path),
        }
        _write_json(report_path, report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": [],
            "blockers": ["sample_expansion_error"],
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "orders_submitted_by_lsr_v2_sample_expansion": 0,
            "positions_opened_by_lsr_v2_sample_expansion": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(report_path),
            "by_asset_report": str(by_asset_path),
            "by_timeframe_report": str(by_tf_path),
            "trades_jsonl": str(trades_path),
        }
        _write_json(report_path, report)
        _write_json(by_asset_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION, "assets": []})
        _write_json(by_tf_path, {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION, "timeframes": []})
        _write_jsonl(trades_path, [])
        return report
