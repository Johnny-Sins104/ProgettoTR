"""Prompt 29.4.4s-8d — LSR-v2 combined risk overlay / operational viability preflight.

Diagnostic-only combined risk-overlay layer for the locked LSR-v2 research
profile: LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24.

This module consumes LSR-v2 sample-expansion trade rows and evaluates
non-oracle combinations of risk overlays. It is a preflight for research
validation only: it must never submit orders, open positions, mutate paper
state, route signals, call a broker, lower strategy thresholds, enable
live/testnet paths, or promote the strategy by itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
import json
import math

from .lsr_v2_risk_overlay_ablation import (  # internal research helpers from s-8c
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
    INPUT_TRADES_NAME,
    _basic_stats,
    _cost_metrics,
    _dataset,
    _dedupe,
    _filter_locked,
    _group_value,
    _pair_key,
    _pair_rows,
    _read_json,
    _read_jsonl,
    _round,
    _safe_div,
    _safe_float,
    _safe_int,
    _trade_sort_key,
    _write_json,
    _write_jsonl,
)

PROMPT_ID = "29.4.4s-8d"
RISK_OVERLAY_REPORT_NAME = "lsr_v2_risk_overlay_ablation_report.json"
REPORT_NAME = "lsr_v2_combined_risk_overlay_report.json"
VARIANTS_REPORT_NAME = "lsr_v2_combined_risk_overlay_variants.json"
TRADES_JSONL_NAME = "lsr_v2_combined_risk_overlay_trades.jsonl"
PREFLIGHT_REPORT_NAME = "lsr_v2_operational_viability_preflight_report.json"

READY_DECISION = "LSR_V2_COMBINED_OVERLAY_RESEARCH_READY"
PREFLIGHT_PASS_DECISION = "LSR_V2_OPERATIONAL_VIABILITY_PREFLIGHT_PASS"
INSUFFICIENT_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_INSUFFICIENT"
DRAWDOWN_REMAINS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_DRAWDOWN_REMAINS_HIGH"
LOSS_STREAK_REMAINS_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_LOSS_STREAK_REMAINS_HIGH"
EDGE_DESTROYED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_EDGE_DESTROYED_BY_OVERLAY"
REJECT_DECISION = "REJECT_LSR_V2_OPERATIONALLY_UNSTABLE"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_NO_TRADES"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_COMBINED_OVERLAY_ERROR"

TRADE_EVENT_TYPE = "LSR_V2_COMBINED_RISK_OVERLAY_TRADE"


@dataclass(frozen=True)
class LSRV2CombinedRiskOverlaySettings:
    data_dir: str = "data"
    trades_path: str | None = None
    risk_overlay_report_path: str | None = None
    primary_cost_model: str = "conservative"
    severe_cost_model: str = "severe"
    breakeven_r_abs: float = 0.10
    max_drawdown_r: float = 15.0
    max_consecutive_losses_limit: int = 10
    min_profit_retention_ratio: float = 0.50
    min_sum_r_post_cost: float = 0.0
    min_avg_r_post_cost: float = 0.0
    min_trades_kept: int = 300
    max_cost_degradation_ratio: float = 1.25
    min_severe_positive_ratio: float = 0.60
    max_trade_rows_to_write: int = 300_000

    # Deterministic, non-oracle simulation parameters.
    loss_streak_limit: int = 3
    loss_streak_pause_short: int = 12
    loss_streak_pause_long: int = 24
    drawdown_pause_short: int = 12
    drawdown_pause_long: int = 24
    group_risk_pause_trades: int = 15
    session_pause_trades: int = 12
    cooldown_after_loss_pause_12: int = 12
    cooldown_after_loss_pause_24: int = 24

    @classmethod
    def default(cls) -> "LSRV2CombinedRiskOverlaySettings":
        return cls()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_paths(data_dir: Path) -> dict[str, Path]:
    return {
        "report": data_dir / REPORT_NAME,
        "variants": data_dir / VARIANTS_REPORT_NAME,
        "trades": data_dir / TRADES_JSONL_NAME,
        "preflight": data_dir / PREFLIGHT_REPORT_NAME,
    }


def _copy_row(row: dict[str, Any], *, step_id: str | None = None, skip_reason: str | None = None) -> dict[str, Any]:
    out = dict(row)
    if step_id:
        out["overlay_step_id"] = step_id
    if skip_reason:
        out["skip_reason"] = skip_reason
    return out


def _apply_loss_streak_pause(
    rows: Sequence[dict[str, Any]],
    *,
    limit: int,
    pause_trades: int,
    settings: LSRV2CombinedRiskOverlaySettings,
    step_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pause_left = 0
    streak = 0
    for row in rows:
        if pause_left > 0:
            skipped.append(_copy_row(row, step_id=step_id, skip_reason=f"{step_id}_pause"))
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
    return kept, skipped


def _apply_rolling_drawdown_pause(
    rows: Sequence[dict[str, Any]],
    *,
    dd_limit_r: float,
    pause_trades: int,
    settings: LSRV2CombinedRiskOverlaySettings,
    step_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pause_left = 0
    equity = 0.0
    peak = 0.0
    for row in rows:
        if pause_left > 0:
            skipped.append(_copy_row(row, step_id=step_id, skip_reason=f"{step_id}_pause"))
            pause_left -= 1
            continue
        kept.append(row)
        equity += _safe_float(row.get("net_r"), 0.0)
        peak = max(peak, equity)
        if peak - equity >= dd_limit_r:
            pause_left = pause_trades
            peak = equity
    return kept, skipped


def _apply_session_loss_cap(
    rows: Sequence[dict[str, Any]],
    *,
    loss_cap_r: float,
    pause_trades: int,
    settings: LSRV2CombinedRiskOverlaySettings,
    step_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    session_net: dict[str, float] = {}
    session_pause: dict[str, int] = {}
    for row in rows:
        session = _group_value(row, "session")
        if session_pause.get(session, 0) > 0:
            skipped.append(_copy_row(row, step_id=step_id, skip_reason=f"{step_id}_pause"))
            session_pause[session] = session_pause.get(session, 0) - 1
            continue
        if session_net.get(session, 0.0) <= -abs(loss_cap_r):
            skipped.append(_copy_row(row, step_id=step_id, skip_reason=f"{step_id}_cap"))
            session_pause[session] = max(0, pause_trades - 1)
            continue
        kept.append(row)
        session_net[session] = session_net.get(session, 0.0) + _safe_float(row.get("net_r"), 0.0)
    return kept, skipped


def _apply_group_risk_cap(
    rows: Sequence[dict[str, Any]],
    *,
    group_key: str,
    dd_limit_r: float,
    pause_trades: int,
    settings: LSRV2CombinedRiskOverlaySettings,
    step_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    equity: dict[str, float] = {}
    peak: dict[str, float] = {}
    pause: dict[str, int] = {}
    for row in rows:
        group = _group_value(row, group_key)
        if pause.get(group, 0) > 0:
            skipped.append(_copy_row(row, step_id=step_id, skip_reason=f"{step_id}_pause"))
            pause[group] = pause.get(group, 0) - 1
            continue
        kept.append(row)
        equity[group] = equity.get(group, 0.0) + _safe_float(row.get("net_r"), 0.0)
        peak[group] = max(peak.get(group, 0.0), equity[group])
        if peak[group] - equity[group] >= dd_limit_r:
            pause[group] = pause_trades
            peak[group] = equity[group]
    return kept, skipped


def _apply_cooldown_after_loss(
    rows: Sequence[dict[str, Any]],
    *,
    pause_trades: int,
    settings: LSRV2CombinedRiskOverlaySettings,
    step_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pause_left = 0
    for row in rows:
        if pause_left > 0:
            skipped.append(_copy_row(row, step_id=step_id, skip_reason=f"{step_id}_pause"))
            pause_left -= 1
            continue
        kept.append(row)
        if _safe_float(row.get("net_r"), 0.0) < -settings.breakeven_r_abs:
            pause_left = pause_trades
    return kept, skipped


def _step_loss3(pause: int) -> tuple[str, Callable[[Sequence[dict[str, Any]], LSRV2CombinedRiskOverlaySettings], tuple[list[dict[str, Any]], list[dict[str, Any]]]]]:
    step_id = f"loss3_pause_{pause}"
    return step_id, lambda rows, settings: _apply_loss_streak_pause(rows, limit=3, pause_trades=pause, settings=settings, step_id=step_id)


def _step_dd(limit: float, pause: int) -> tuple[str, Callable[[Sequence[dict[str, Any]], LSRV2CombinedRiskOverlaySettings], tuple[list[dict[str, Any]], list[dict[str, Any]]]]]:
    step_id = f"dd{limit:g}_pause_{pause}"
    return step_id, lambda rows, settings: _apply_rolling_drawdown_pause(rows, dd_limit_r=limit, pause_trades=pause, settings=settings, step_id=step_id)


def _step_session(cap: float, pause: int) -> tuple[str, Callable[[Sequence[dict[str, Any]], LSRV2CombinedRiskOverlaySettings], tuple[list[dict[str, Any]], list[dict[str, Any]]]]]:
    step_id = f"session_loss_{cap:g}R_pause_{pause}"
    return step_id, lambda rows, settings: _apply_session_loss_cap(rows, loss_cap_r=cap, pause_trades=pause, settings=settings, step_id=step_id)


def _step_group(key: str, dd: float, pause: int) -> tuple[str, Callable[[Sequence[dict[str, Any]], LSRV2CombinedRiskOverlaySettings], tuple[list[dict[str, Any]], list[dict[str, Any]]]]]:
    step_id = f"{key}_cap_{dd:g}R_pause_{pause}"
    return step_id, lambda rows, settings: _apply_group_risk_cap(rows, group_key=key, dd_limit_r=dd, pause_trades=pause, settings=settings, step_id=step_id)


def _step_cooldown(pause: int) -> tuple[str, Callable[[Sequence[dict[str, Any]], LSRV2CombinedRiskOverlaySettings], tuple[list[dict[str, Any]], list[dict[str, Any]]]]]:
    step_id = f"cooldown_after_loss_{pause}"
    return step_id, lambda rows, settings: _apply_cooldown_after_loss(rows, pause_trades=pause, settings=settings, step_id=step_id)


def _variant_defs(settings: LSRV2CombinedRiskOverlaySettings) -> list[tuple[str, list[tuple[str, Callable]]]]:
    loss_short = _step_loss3(settings.loss_streak_pause_short)
    loss_long = _step_loss3(settings.loss_streak_pause_long)
    dd10_short = _step_dd(10.0, settings.drawdown_pause_short)
    dd10_long = _step_dd(10.0, settings.drawdown_pause_long)
    dd15_short = _step_dd(15.0, settings.drawdown_pause_short)
    session2 = _step_session(2.0, settings.session_pause_trades)
    session3 = _step_session(3.0, settings.session_pause_trades)
    asset_cap = _step_group("asset_timeframe", 5.0, settings.group_risk_pause_trades)
    side_cap = _step_group("side", 5.0, settings.group_risk_pause_trades)
    cooldown12 = _step_cooldown(settings.cooldown_after_loss_pause_12)
    cooldown24 = _step_cooldown(settings.cooldown_after_loss_pause_24)
    return [
        ("combo_loss3_dd10", [loss_short, dd10_short]),
        ("combo_loss3_dd15", [loss_short, dd15_short]),
        ("combo_loss3_dd10_asset_cap", [loss_short, dd10_short, asset_cap]),
        ("combo_loss3_dd10_side_cap", [loss_short, dd10_short, side_cap]),
        ("combo_loss3_session_loss_2R", [loss_short, session2]),
        ("combo_loss3_session_loss_3R", [loss_short, session3]),
        ("combo_loss3_dd10_cooldown_12", [loss_short, dd10_short, cooldown12]),
        ("combo_loss3_dd10_cooldown_24", [loss_short, dd10_short, cooldown24]),
        ("combo_loss3_dd10_asset_side_cap", [loss_short, dd10_short, asset_cap, side_cap]),
        ("combo_loss3_dd10_session_cap_cooldown", [loss_short, dd10_short, session2, cooldown12]),
        # A few nearby non-oracle controls to prevent a single too-narrow experiment.
        ("combo_loss3_long_dd10", [loss_long, dd10_short]),
        ("combo_loss3_dd10_long", [loss_short, dd10_long]),
        ("combo_loss3_dd15_asset_side_cap", [loss_short, dd15_short, asset_cap, side_cap]),
        ("combo_loss3_session3_dd10", [loss_short, session3, dd10_short]),
    ]


def _baseline_summary(rows: Sequence[dict[str, Any]], paired: dict[str, dict[str, Any]], settings: LSRV2CombinedRiskOverlaySettings) -> dict[str, Any]:
    stats = _basic_stats(rows, settings)  # type: ignore[arg-type]
    cost = _cost_metrics(rows, paired, settings)  # type: ignore[arg-type]
    return {
        "overlay_id": "baseline_no_combined_overlay",
        "overlay_family": "baseline",
        "description": "No combined overlay; reference profile only.",
        "steps": [],
        "oracle_overlay": False,
        "diagnostic_only": True,
        "trades_kept": len(rows),
        "trades_filtered": 0,
        "trades_kept_ratio": 1.0,
        "sum_r_post_cost": stats.get("sum_r_post_cost"),
        "avg_r_post_cost": stats.get("avg_r_post_cost"),
        "max_drawdown_r": stats.get("max_drawdown_r"),
        "max_consecutive_losses": stats.get("max_consecutive_losses"),
        "win_rate": stats.get("win_rate"),
        "loss_rate": stats.get("loss_rate"),
        "breakeven_rate": stats.get("breakeven_rate"),
        "profit_retention_ratio": 1.0,
        "drawdown_reduction_ratio": 0.0,
        "cost_degradation_ratio": cost.get("cost_degradation_ratio"),
        "severe_positive_ratio": cost.get("severe_positive_ratio"),
        "cost_degradation_non_destructive": cost.get("cost_degradation_non_destructive", False),
        "combined_overlay_valid": False,
        "orders_submitted_by_lsr_v2_combined_overlay": 0,
        "positions_opened_by_lsr_v2_combined_overlay": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "promotion_ready": False,
    }


def _summarize_variant(
    overlay_id: str,
    steps: list[str],
    kept: Sequence[dict[str, Any]],
    skipped: Sequence[dict[str, Any]],
    baseline: Sequence[dict[str, Any]],
    paired: dict[str, dict[str, Any]],
    settings: LSRV2CombinedRiskOverlaySettings,
) -> dict[str, Any]:
    base_stats = _basic_stats(baseline, settings)  # type: ignore[arg-type]
    stats = _basic_stats(kept, settings)  # type: ignore[arg-type]
    cost = _cost_metrics(kept, paired, settings)  # type: ignore[arg-type]
    base_sum = _safe_float(base_stats.get("sum_r_post_cost"), 0.0)
    base_dd = _safe_float(base_stats.get("max_drawdown_r"), 0.0)
    kept_sum = _safe_float(stats.get("sum_r_post_cost"), 0.0)
    kept_dd = _safe_float(stats.get("max_drawdown_r"), 0.0)
    profit_retention = _safe_div(kept_sum, base_sum, 0.0) if abs(base_sum) > 1e-12 else 0.0
    dd_reduction = _safe_div(base_dd - kept_dd, base_dd, 0.0) if base_dd > 1e-12 else 0.0
    trades_kept = len(kept)
    trades_filtered = len(skipped)
    cost_degradation = _safe_float(cost.get("cost_degradation_ratio"), 999.0)
    severe_positive = _safe_float(cost.get("severe_positive_ratio"), 0.0)
    max_streak = _safe_int(stats.get("max_consecutive_losses"), 999)
    valid = bool(
        trades_kept >= settings.min_trades_kept
        and kept_sum > settings.min_sum_r_post_cost
        and _safe_float(stats.get("avg_r_post_cost"), 0.0) > settings.min_avg_r_post_cost
        and kept_dd <= settings.max_drawdown_r
        and max_streak <= settings.max_consecutive_losses_limit
        and (profit_retention or 0.0) >= settings.min_profit_retention_ratio
        and cost_degradation <= settings.max_cost_degradation_ratio
        and severe_positive >= settings.min_severe_positive_ratio
    )
    return {
        "overlay_id": overlay_id,
        "overlay_family": "combined_non_oracle",
        "description": "Non-oracle sequential combination of LSR-v2 risk pauses/caps.",
        "steps": steps,
        "oracle_overlay": False,
        "diagnostic_only": True,
        "trades_kept": trades_kept,
        "trades_filtered": trades_filtered,
        "trades_kept_ratio": _round(_safe_div(trades_kept, len(baseline), 0.0) or 0.0, 8),
        "sum_r_post_cost": stats.get("sum_r_post_cost"),
        "avg_r_post_cost": stats.get("avg_r_post_cost"),
        "max_drawdown_r": stats.get("max_drawdown_r"),
        "max_consecutive_losses": stats.get("max_consecutive_losses"),
        "win_rate": stats.get("win_rate"),
        "loss_rate": stats.get("loss_rate"),
        "breakeven_rate": stats.get("breakeven_rate"),
        "profit_retention_ratio": _round(profit_retention or 0.0, 8),
        "drawdown_reduction_ratio": _round(dd_reduction or 0.0, 8),
        "cost_degradation_ratio": _round(cost_degradation, 8),
        "severe_positive_ratio": _round(severe_positive, 8),
        "cost_degradation_non_destructive": bool(cost.get("cost_degradation_non_destructive", False)),
        "combined_overlay_valid": valid,
        "validation_criteria": {
            "max_drawdown_r": settings.max_drawdown_r,
            "max_consecutive_losses_limit": settings.max_consecutive_losses_limit,
            "min_profit_retention_ratio": settings.min_profit_retention_ratio,
            "min_trades_kept": settings.min_trades_kept,
            "max_cost_degradation_ratio": settings.max_cost_degradation_ratio,
            "min_severe_positive_ratio": settings.min_severe_positive_ratio,
        },
        "orders_submitted_by_lsr_v2_combined_overlay": 0,
        "positions_opened_by_lsr_v2_combined_overlay": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "promotion_ready": False,
    }


def _overlay_trade_row(row: dict[str, Any], overlay_id: str, *, kept: bool, skip_reason: str | None) -> dict[str, Any]:
    out = dict(row)
    out.update({
        "event_type": TRADE_EVENT_TYPE,
        "prompt_id": PROMPT_ID,
        "overlay_id": overlay_id,
        "trade_kept_by_combined_overlay": kept,
        "skip_reason": skip_reason,
        "orders_submitted_by_lsr_v2_combined_overlay": 0,
        "positions_opened_by_lsr_v2_combined_overlay": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "audit_only": True,
        "promotion_ready": False,
    })
    return out


def _run_variant(
    overlay_id: str,
    step_defs: list[tuple[str, Callable]],
    primary_rows: Sequence[dict[str, Any]],
    paired: dict[str, dict[str, Any]],
    settings: LSRV2CombinedRiskOverlaySettings,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    kept = list(primary_rows)
    all_skipped: list[dict[str, Any]] = []
    steps: list[str] = []
    for step_id, fn in step_defs:
        steps.append(step_id)
        kept, skipped = fn(kept, settings)
        all_skipped.extend(skipped)
    summary = _summarize_variant(overlay_id, steps, kept, all_skipped, primary_rows, paired, settings)
    rows: list[dict[str, Any]] = []
    for row in kept:
        rows.append(_overlay_trade_row(row, overlay_id, kept=True, skip_reason=None))
    for row in all_skipped:
        rows.append(_overlay_trade_row(row, overlay_id, kept=False, skip_reason=str(row.get("skip_reason") or "filtered")))
    return summary, rows


def _select_best_variant(variants: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    pool = [v for v in variants if v.get("overlay_id") != "baseline_no_combined_overlay"]
    if not pool:
        return None
    return sorted(
        pool,
        key=lambda v: (
            not bool(v.get("combined_overlay_valid")),
            _safe_float(v.get("max_drawdown_r"), 999.0),
            _safe_int(v.get("max_consecutive_losses"), 999),
            -_safe_float(v.get("sum_r_post_cost"), 0.0),
            -_safe_float(v.get("profit_retention_ratio"), 0.0),
            _safe_float(v.get("cost_degradation_ratio"), 999.0),
        ),
    )[0]


def _build_variants(primary: Sequence[dict[str, Any]], severe: Sequence[dict[str, Any]], settings: LSRV2CombinedRiskOverlaySettings) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    paired = _pair_rows(primary, severe)
    variants: list[dict[str, Any]] = [_baseline_summary(primary, paired, settings)]
    selected_rows: list[dict[str, Any]] = []
    for overlay_id, steps in _variant_defs(settings):
        summary, rows = _run_variant(overlay_id, steps, primary, paired, settings)
        variants.append(summary)
        if summary.get("combined_overlay_valid") or overlay_id in {
            "combo_loss3_dd10",
            "combo_loss3_dd10_asset_side_cap",
            "combo_loss3_dd10_session_cap_cooldown",
        }:
            selected_rows.extend(rows)
    return variants, selected_rows


def _classify(variants: Sequence[dict[str, Any]], inherited_report: dict[str, Any], settings: LSRV2CombinedRiskOverlaySettings) -> tuple[str, list[str], list[str]]:
    baseline = next((v for v in variants if v.get("overlay_id") == "baseline_no_combined_overlay"), {})
    valid = [v for v in variants if v.get("combined_overlay_valid")]
    best = _select_best_variant(variants) or {}
    labels: list[str] = []
    blockers: list[str] = []
    for blocker in list(inherited_report.get("blockers") or []):
        if isinstance(blocker, str):
            inherited = f"inherited_{blocker}"
            if inherited not in blockers:
                blockers.append(inherited)
    baseline_sum = _safe_float(baseline.get("sum_r_post_cost"), 0.0)
    if baseline_sum <= 0:
        labels.append("BASELINE_NET_NEGATIVE")
        return REJECT_DECISION, labels, blockers or ["baseline_net_negative"]
    if valid:
        labels.append("COMBINED_OVERLAY_RESEARCH_READY")
        labels.append("OPERATIONAL_VIABILITY_PREFLIGHT_PASS")
        # Keep inherited blockers visible but do not block the preflight result; the overlay addressed them diagnostically.
        return PREFLIGHT_PASS_DECISION, list(dict.fromkeys(labels)), blockers
    best_sum = _safe_float(best.get("sum_r_post_cost"), 0.0)
    best_retention = _safe_float(best.get("profit_retention_ratio"), 0.0)
    best_dd = _safe_float(best.get("max_drawdown_r"), 999.0)
    best_streak = _safe_int(best.get("max_consecutive_losses"), 999)
    if best_sum <= settings.min_sum_r_post_cost or best_retention < settings.min_profit_retention_ratio:
        labels.append("EDGE_DESTROYED_BY_COMBINED_OVERLAY")
        return EDGE_DESTROYED_DECISION, list(dict.fromkeys(labels)), blockers or ["overlay_edge_destroyed"]
    if best_dd > settings.max_drawdown_r:
        labels.append("DRAWDOWN_REMAINS_HIGH")
        blockers.append("best_overlay_drawdown_above_limit")
        return DRAWDOWN_REMAINS_DECISION, list(dict.fromkeys(labels)), blockers
    if best_streak > settings.max_consecutive_losses_limit:
        labels.append("LOSS_STREAK_REMAINS_HIGH")
        blockers.append("best_overlay_loss_streak_above_limit")
        return LOSS_STREAK_REMAINS_DECISION, list(dict.fromkeys(labels)), blockers
    labels.append("COMBINED_OVERLAY_INSUFFICIENT")
    blockers.append("no_valid_combined_overlay")
    return INSUFFICIENT_DECISION, list(dict.fromkeys(labels)), blockers


def _preflight_report(variants: Sequence[dict[str, Any]], decision: str, labels: list[str], blockers: list[str], settings: LSRV2CombinedRiskOverlaySettings, paths: dict[str, Path]) -> dict[str, Any]:
    baseline = next((v for v in variants if v.get("overlay_id") == "baseline_no_combined_overlay"), {})
    non_baseline = [v for v in variants if v.get("overlay_id") != "baseline_no_combined_overlay"]
    valid = [v for v in non_baseline if v.get("combined_overlay_valid")]
    best = _select_best_variant(variants) or {}
    return {
        "prompt_id": PROMPT_ID,
        "status": "PASS" if variants else "WARN",
        "decision": decision,
        "classification_labels": labels,
        "blockers": blockers,
        "created_at": utc_now_iso(),
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "baseline": baseline,
        "best_combined_overlay": best,
        "variant_count": len(variants),
        "valid_combined_overlay_count": len(valid),
        "minimum_criteria": {
            "max_drawdown_r": settings.max_drawdown_r,
            "max_consecutive_losses_limit": settings.max_consecutive_losses_limit,
            "min_profit_retention_ratio": settings.min_profit_retention_ratio,
            "min_trades_kept": settings.min_trades_kept,
            "max_cost_degradation_ratio": settings.max_cost_degradation_ratio,
            "min_severe_positive_ratio": settings.min_severe_positive_ratio,
        },
        "audit_only": True,
        "promotion_ready": False,
        "orders_submitted_by_lsr_v2_operational_viability_preflight": 0,
        "positions_opened_by_lsr_v2_operational_viability_preflight": 0,
        "report": str(paths["preflight"]),
    }


def _safe_empty_report(settings: LSRV2CombinedRiskOverlaySettings, paths: dict[str, Path], reason: str) -> dict[str, Any]:
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
        "valid_combined_overlay_count": 0,
        "orders_submitted_by_lsr_v2_combined_overlay": 0,
        "positions_opened_by_lsr_v2_combined_overlay": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(paths["report"]),
        "variants_report": str(paths["variants"]),
        "trades_jsonl": str(paths["trades"]),
        "operational_viability_preflight_report": str(paths["preflight"]),
    }
    empty = {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_TRADES_DECISION, "created_at": created, "promotion_ready": False}
    _write_json(paths["report"], report)
    _write_json(paths["variants"], empty)
    _write_json(paths["preflight"], empty)
    _write_jsonl(paths["trades"], [])
    return report


def run_lsr_v2_combined_risk_overlay(settings: LSRV2CombinedRiskOverlaySettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2CombinedRiskOverlaySettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = _write_paths(data_dir)
    trades_path = Path(settings.trades_path) if settings.trades_path else data_dir / INPUT_TRADES_NAME
    inherited_path = Path(settings.risk_overlay_report_path) if settings.risk_overlay_report_path else data_dir / RISK_OVERLAY_REPORT_NAME
    try:
        raw_rows = _read_jsonl(trades_path)
        if not raw_rows:
            return _safe_empty_report(settings, paths, "no_sample_expansion_trade_rows")
        locked_rows = _filter_locked(raw_rows)
        primary = _dedupe([r for r in locked_rows if str(r.get("cost_model")) == settings.primary_cost_model])
        severe = _dedupe([r for r in locked_rows if str(r.get("cost_model")) == settings.severe_cost_model])
        primary = sorted(primary, key=_trade_sort_key)
        severe = sorted(severe, key=_trade_sort_key)
        if not primary:
            return _safe_empty_report(settings, paths, "no_primary_cost_model_trades")
        inherited_report = _read_json(inherited_path)
        variants, selected_trade_rows = _build_variants(primary, severe, settings)
        decision, labels, blockers = _classify(variants, inherited_report, settings)
        best = _select_best_variant(variants) or {}
        baseline = next((v for v in variants if v.get("overlay_id") == "baseline_no_combined_overlay"), {})
        valid = [v for v in variants if v.get("combined_overlay_valid")]
        written_rows = _write_jsonl(paths["trades"], selected_trade_rows, max_rows=settings.max_trade_rows_to_write)
        variants_payload = {
            "prompt_id": PROMPT_ID,
            "status": "PASS",
            "decision": "LSR_V2_COMBINED_RISK_OVERLAY_VARIANTS_READY",
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "variant_count": len(variants),
            "valid_combined_overlay_count": len(valid),
            "variants": variants,
            "audit_only": True,
            "promotion_ready": False,
            "orders_submitted_by_lsr_v2_combined_overlay_variants": 0,
            "positions_opened_by_lsr_v2_combined_overlay_variants": 0,
            "report": str(paths["variants"]),
        }
        _write_json(paths["variants"], variants_payload)
        preflight = _preflight_report(variants, decision, labels, blockers, settings, paths)
        _write_json(paths["preflight"], preflight)
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
            "risk_overlay_report_path": str(inherited_path),
            "inherited_risk_overlay_decision": inherited_report.get("decision"),
            "inherited_risk_overlay_blockers": inherited_report.get("blockers", []),
            "raw_trade_rows": len(raw_rows),
            "locked_trade_rows": len(locked_rows),
            "primary_trade_count": len(primary),
            "severe_trade_count": len(severe),
            "variant_count": len(variants),
            "valid_combined_overlay_count": len(valid),
            "baseline_sum_r_post_cost": baseline.get("sum_r_post_cost"),
            "baseline_avg_r_post_cost": baseline.get("avg_r_post_cost"),
            "baseline_max_drawdown_r": baseline.get("max_drawdown_r"),
            "baseline_max_consecutive_losses": baseline.get("max_consecutive_losses"),
            "best_combined_overlay_id": best.get("overlay_id"),
            "best_combined_overlay_valid": best.get("combined_overlay_valid", False),
            "best_combined_overlay_trades_kept": best.get("trades_kept"),
            "best_combined_overlay_trades_filtered": best.get("trades_filtered"),
            "best_combined_overlay_sum_r_post_cost": best.get("sum_r_post_cost"),
            "best_combined_overlay_avg_r_post_cost": best.get("avg_r_post_cost"),
            "best_combined_overlay_max_drawdown_r": best.get("max_drawdown_r"),
            "best_combined_overlay_max_consecutive_losses": best.get("max_consecutive_losses"),
            "best_combined_overlay_profit_retention_ratio": best.get("profit_retention_ratio"),
            "best_combined_overlay_drawdown_reduction_ratio": best.get("drawdown_reduction_ratio"),
            "best_combined_overlay_cost_degradation_ratio": best.get("cost_degradation_ratio"),
            "best_combined_overlay_severe_positive_ratio": best.get("severe_positive_ratio"),
            "written_combined_overlay_trade_rows": written_rows,
            "orders_submitted_by_lsr_v2_combined_overlay": 0,
            "positions_opened_by_lsr_v2_combined_overlay": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "submit_order": False,
            "broker_submit_called": False,
            "promotion_ready": False,
            "promotion_blocked_reason": "combined risk overlay preflight is diagnostic; promotion gate and runtime execution remain disabled",
            "report": str(paths["report"]),
            "variants_report": str(paths["variants"]),
            "trades_jsonl": str(paths["trades"]),
            "operational_viability_preflight_report": str(paths["preflight"]),
        }
        _write_json(paths["report"], report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": [],
            "blockers": ["combined_risk_overlay_error"],
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "orders_submitted_by_lsr_v2_combined_overlay": 0,
            "positions_opened_by_lsr_v2_combined_overlay": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(paths["report"]),
            "variants_report": str(paths["variants"]),
            "trades_jsonl": str(paths["trades"]),
            "operational_viability_preflight_report": str(paths["preflight"]),
        }
        _write_json(paths["report"], report)
        _write_json(paths["variants"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_json(paths["preflight"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_jsonl(paths["trades"], [])
        return report


__all__ = [
    "LOCKED_PROFILE_NAME",
    "LOCKED_VARIANT_ID",
    "LSRV2CombinedRiskOverlaySettings",
    "run_lsr_v2_combined_risk_overlay",
]
