"""Prompt 29.4.4s-8e — LSR-v2 selected overlay robustness validation / anti-overfit lock.

Diagnostic-only validation for the locked LSR-v2 research profile plus the
selected non-oracle combined risk overlay:

* strategy profile: LSR_V2_RETEST_LIMIT_STOP_SWEEP_TP2R_HOLD24
* risk overlay: combo_loss3_dd10_side_cap

This module consumes the selected-overlay trade rows produced by s-8d and the
sample-expansion trade rows produced by s-7e. It validates only the selected
profile/overlay, not the full overlay search space, to reduce selection noise
before a later, separate promotion gate.

It must never submit orders, open positions, mutate paper state, route signals,
call a broker, lower thresholds, or enable live/testnet/exchange-broker paths.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
import json
import math

from .lsr_v2_combined_risk_overlay import (
    LOCKED_PROFILE_NAME,
    LOCKED_VARIANT_ID,
)
from .lsr_v2_robustness_validation import (
    LSRV2RobustnessValidationSettings,
    _basic_trade_summary,
    _cost_degradation,
    _dedupe_trades,
    _group_summary,
    _pair_key,
    _pnl_dominance,
    _positive_group_ratio,
    _read_jsonl,
    _round,
    _run_bootstrap,
    _run_oos,
    _run_walk_forward,
    _safe_float,
    _safe_int,
    _trade_sort_key,
    _write_json,
    _write_jsonl,
)

PROMPT_ID = "29.4.4s-8e"
SELECTED_OVERLAY_ID = "combo_loss3_dd10_side_cap"
COMBINED_TRADES_NAME = "lsr_v2_combined_risk_overlay_trades.jsonl"
SAMPLE_TRADES_NAME = "lsr_v2_sample_expansion_trades.jsonl"
REPORT_NAME = "lsr_v2_selected_overlay_validation_report.json"
WALK_FORWARD_REPORT_NAME = "lsr_v2_selected_overlay_walk_forward_report.json"
OOS_REPORT_NAME = "lsr_v2_selected_overlay_oos_report.json"
BOOTSTRAP_REPORT_NAME = "lsr_v2_selected_overlay_bootstrap_report.json"
TRADES_JSONL_NAME = "lsr_v2_selected_overlay_trades.jsonl"

PASS_DECISION = "LSR_V2_SELECTED_OVERLAY_VALIDATION_PASS"
READY_DECISION = "LSR_V2_SELECTED_OVERLAY_READY_FOR_PROMOTION_GATE"
WF_UNSTABLE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_WALK_FORWARD_UNSTABLE"
OOS_FAILED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_OOS_FAILED"
BOOTSTRAP_FRAGILE_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_BOOTSTRAP_FRAGILE"
COST_FAILED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_COST_DEGRADATION_FAILED"
DRAWDOWN_FAILED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_DRAWDOWN_FAILED"
LOSS_STREAK_FAILED_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_LOSS_STREAK_FAILED"
REJECT_DECISION = "REJECT_LSR_V2_SELECTED_OVERLAY_VALIDATION_FAILED"
NO_TRADES_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_NO_TRADES"
ERROR_DECISION = "KEEP_DIAGNOSTIC_LSR_V2_SELECTED_OVERLAY_VALIDATION_ERROR"


@dataclass(frozen=True)
class LSRV2SelectedOverlayValidationSettings:
    data_dir: str = "data"
    combined_trades_path: str | None = None
    sample_trades_path: str | None = None
    selected_overlay_id: str = SELECTED_OVERLAY_ID
    primary_cost_model: str = "conservative"
    severe_cost_model: str = "severe"
    min_unique_primary_trades: int = 300
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
    max_drawdown_r: float = 15.0
    max_consecutive_losses_limit: int = 10
    max_asset_pnl_share: float = 0.65
    max_timeframe_pnl_share: float = 0.75
    min_positive_asset_ratio: float = 0.50
    min_positive_timeframe_ratio: float = 0.50
    min_positive_side_ratio: float = 0.50
    min_severe_positive_ratio: float = 0.60
    max_cost_degradation_ratio: float = 1.25
    breakeven_r_abs: float = 0.10
    random_seed: int = 294408
    max_trade_rows_to_write: int = 300_000

    @classmethod
    def default(cls) -> "LSRV2SelectedOverlayValidationSettings":
        return cls()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_paths(data_dir: Path) -> dict[str, Path]:
    return {
        "report": data_dir / REPORT_NAME,
        "wf": data_dir / WALK_FORWARD_REPORT_NAME,
        "oos": data_dir / OOS_REPORT_NAME,
        "bootstrap": data_dir / BOOTSTRAP_REPORT_NAME,
        "trades": data_dir / TRADES_JSONL_NAME,
    }


def _lock_filter(row: dict[str, Any]) -> bool:
    return (
        str(row.get("locked_variant_id") or row.get("variant_id") or "") == LOCKED_VARIANT_ID
        or str(row.get("locked_profile_name") or "") == LOCKED_PROFILE_NAME
    )


def _selected_overlay_primary_rows(rows: Sequence[dict[str, Any]], settings: LSRV2SelectedOverlayValidationSettings) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("overlay_id") or "") != settings.selected_overlay_id:
            continue
        if row.get("trade_kept_by_combined_overlay") is not True:
            continue
        if str(row.get("cost_model") or "") != settings.primary_cost_model:
            continue
        if not _lock_filter(row):
            continue
        selected.append(dict(row))
    return _dedupe_trades(selected, include_cost=True)


def _severe_pairs_for_primary(
    selected_primary: Sequence[dict[str, Any]],
    sample_rows: Sequence[dict[str, Any]],
    settings: LSRV2SelectedOverlayValidationSettings,
) -> list[dict[str, Any]]:
    keys = {_pair_key(row) for row in selected_primary}
    severe_candidates: list[dict[str, Any]] = []
    for row in sample_rows:
        if str(row.get("cost_model") or "") != settings.severe_cost_model:
            continue
        if _lock_filter(row) is False:
            # Be permissive for older synthetic rows only when no lock metadata exists.
            if row.get("locked_variant_id") or row.get("variant_id") or row.get("locked_profile_name"):
                continue
        if _pair_key(row) in keys:
            severe_candidates.append(dict(row))
    return _dedupe_trades(severe_candidates, include_cost=True)


def _max_consecutive_losses(rows: Sequence[dict[str, Any]], breakeven_r_abs: float) -> int:
    max_streak = 0
    streak = 0
    for row in rows:
        net = _safe_float(row.get("net_r"), 0.0)
        if net < -abs(float(breakeven_r_abs)):
            streak += 1
            max_streak = max(max_streak, streak)
        elif net > abs(float(breakeven_r_abs)):
            streak = 0
    return max_streak


def _settings_for_robustness(settings: LSRV2SelectedOverlayValidationSettings) -> LSRV2RobustnessValidationSettings:
    return LSRV2RobustnessValidationSettings(
        data_dir=settings.data_dir,
        trades_path=None,
        primary_cost_model=settings.primary_cost_model,
        severe_cost_model=settings.severe_cost_model,
        min_unique_primary_trades=settings.min_unique_primary_trades,
        min_walk_forward_folds=settings.min_walk_forward_folds,
        walk_forward_folds=settings.walk_forward_folds,
        embargo_trades=settings.embargo_trades,
        min_walk_forward_positive_ratio=settings.min_walk_forward_positive_ratio,
        oos_holdout_ratio=settings.oos_holdout_ratio,
        min_oos_avg_r=settings.min_oos_avg_r,
        min_oos_sum_r=settings.min_oos_sum_r,
        bootstrap_iterations=settings.bootstrap_iterations,
        bootstrap_sample_fraction=settings.bootstrap_sample_fraction,
        min_bootstrap_positive_ratio=settings.min_bootstrap_positive_ratio,
        min_bootstrap_median_avg_r=settings.min_bootstrap_median_avg_r,
        max_drawdown_r=settings.max_drawdown_r,
        max_asset_pnl_share=settings.max_asset_pnl_share,
        max_timeframe_pnl_share=settings.max_timeframe_pnl_share,
        min_positive_asset_ratio=settings.min_positive_asset_ratio,
        min_positive_timeframe_ratio=settings.min_positive_timeframe_ratio,
        min_positive_side_ratio=settings.min_positive_side_ratio,
        min_severe_positive_ratio=settings.min_severe_positive_ratio,
        max_cost_degradation_ratio=settings.max_cost_degradation_ratio,
        breakeven_r_abs=settings.breakeven_r_abs,
        random_seed=settings.random_seed,
        max_walk_forward_trade_rows_to_write=settings.max_trade_rows_to_write,
    )


def _label_trade(row: dict[str, Any], settings: LSRV2SelectedOverlayValidationSettings, *, paired_severe: bool = False) -> dict[str, Any]:
    out = dict(row)
    out.update({
        "event_type": "LSR_V2_SELECTED_OVERLAY_VALIDATION_TRADE",
        "prompt_id": PROMPT_ID,
        "selected_overlay_id": settings.selected_overlay_id,
        "selected_overlay_profile_locked": True,
        "paired_severe_trade": paired_severe,
        "orders_submitted_by_lsr_v2_selected_overlay_validation": 0,
        "positions_opened_by_lsr_v2_selected_overlay_validation": 0,
        "submit_order": False,
        "broker_submit_called": False,
        "audit_only": True,
        "promotion_ready": False,
    })
    return out


def _classify_selected(
    *,
    primary_summary: dict[str, Any],
    wf_report: dict[str, Any],
    oos_report: dict[str, Any],
    bootstrap_report: dict[str, Any],
    cost_report: dict[str, Any],
    asset_groups: Sequence[dict[str, Any]],
    timeframe_groups: Sequence[dict[str, Any]],
    side_groups: Sequence[dict[str, Any]],
    max_consecutive_losses: int,
    settings: LSRV2SelectedOverlayValidationSettings,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    labels: list[str] = []
    if _safe_int(primary_summary.get("closed_trades"), 0) < settings.min_unique_primary_trades:
        blockers.append("selected_overlay_trades_below_minimum")
        labels.append("LOW_SAMPLE_AFTER_OVERLAY")
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
    if _safe_float(primary_summary.get("max_drawdown_r"), 0.0) > settings.max_drawdown_r:
        blockers.append("max_drawdown_above_limit")
        labels.append("DRAWDOWN_ABOVE_LIMIT")
    if max_consecutive_losses > settings.max_consecutive_losses_limit:
        blockers.append("max_consecutive_losses_above_limit")
        labels.append("LOSS_STREAK_ABOVE_LIMIT")

    asset_share = _pnl_dominance(asset_groups)
    timeframe_share = _pnl_dominance(timeframe_groups)
    asset_ratio = _positive_group_ratio(asset_groups)
    timeframe_ratio = _positive_group_ratio(timeframe_groups)
    side_ratio = _positive_group_ratio(side_groups)
    if asset_groups and asset_share > settings.max_asset_pnl_share:
        blockers.append("single_asset_pnl_dominance")
        labels.append("ASSET_CONCENTRATION")
    if timeframe_groups and timeframe_share > settings.max_timeframe_pnl_share:
        blockers.append("single_timeframe_pnl_dominance")
        labels.append("TIMEFRAME_CONCENTRATION")
    if asset_groups and asset_ratio < settings.min_positive_asset_ratio:
        blockers.append("asset_positive_ratio_below_minimum")
        labels.append("ASSET_INSTABILITY")
    if timeframe_groups and timeframe_ratio < settings.min_positive_timeframe_ratio:
        blockers.append("timeframe_positive_ratio_below_minimum")
        labels.append("TIMEFRAME_INSTABILITY")
    if side_groups and side_ratio < settings.min_positive_side_ratio:
        blockers.append("side_positive_ratio_below_minimum")
        labels.append("SIDE_INSTABILITY")

    labels = list(dict.fromkeys(labels))
    blockers = list(dict.fromkeys(blockers))
    if not blockers:
        return READY_DECISION, ["SELECTED_OVERLAY_VALIDATION_PASS", "READY_FOR_PROMOTION_GATE_REVIEW"], []
    if "walk_forward_positive_ratio_below_minimum" in blockers:
        decision = WF_UNSTABLE_DECISION
    elif "oos_failed" in blockers:
        decision = OOS_FAILED_DECISION
    elif "bootstrap_fragile" in blockers:
        decision = BOOTSTRAP_FRAGILE_DECISION
    elif "cost_degradation_failed" in blockers:
        decision = COST_FAILED_DECISION
    elif "max_drawdown_above_limit" in blockers:
        decision = DRAWDOWN_FAILED_DECISION
    elif "max_consecutive_losses_above_limit" in blockers:
        decision = LOSS_STREAK_FAILED_DECISION
    else:
        decision = REJECT_DECISION
    return decision, labels, blockers


def _safe_no_trade_report(settings: LSRV2SelectedOverlayValidationSettings, paths: dict[str, Path], reason: str) -> dict[str, Any]:
    created = utc_now_iso()
    report = {
        "prompt_id": PROMPT_ID,
        "status": "WARN",
        "decision": NO_TRADES_DECISION,
        "classification_labels": ["NO_SELECTED_OVERLAY_TRADES"],
        "blockers": [reason],
        "created_at": created,
        "locked_profile_name": LOCKED_PROFILE_NAME,
        "locked_variant_id": LOCKED_VARIANT_ID,
        "selected_overlay_id": settings.selected_overlay_id,
        "raw_combined_trade_rows": 0,
        "selected_primary_trades": 0,
        "paired_severe_trades": 0,
        "orders_submitted_by_lsr_v2_selected_overlay_validation": 0,
        "positions_opened_by_lsr_v2_selected_overlay_validation": 0,
        "live_allowed": False,
        "testnet_allowed": False,
        "exchange_broker_allowed": False,
        "audit_only": True,
        "promotion_ready": False,
        "report": str(paths["report"]),
        "walk_forward_report": str(paths["wf"]),
        "oos_report": str(paths["oos"]),
        "bootstrap_report": str(paths["bootstrap"]),
        "trades_jsonl": str(paths["trades"]),
    }
    empty = {"prompt_id": PROMPT_ID, "status": "WARN", "decision": NO_TRADES_DECISION, "created_at": created, "promotion_ready": False}
    _write_json(paths["report"], report)
    _write_json(paths["wf"], dict(empty, folds=[]))
    _write_json(paths["oos"], empty)
    _write_json(paths["bootstrap"], empty)
    _write_jsonl(paths["trades"], [])
    return report


def run_lsr_v2_selected_overlay_validation(settings: LSRV2SelectedOverlayValidationSettings | None = None) -> dict[str, Any]:
    settings = settings or LSRV2SelectedOverlayValidationSettings.default()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = _write_paths(data_dir)
    combined_path = Path(settings.combined_trades_path) if settings.combined_trades_path else data_dir / COMBINED_TRADES_NAME
    sample_path = Path(settings.sample_trades_path) if settings.sample_trades_path else data_dir / SAMPLE_TRADES_NAME

    try:
        combined_rows = _read_jsonl(combined_path)
        if not combined_rows:
            return _safe_no_trade_report(settings, paths, "no_combined_overlay_trade_rows")
        selected_primary = _selected_overlay_primary_rows(combined_rows, settings)
        if not selected_primary:
            return _safe_no_trade_report(settings, paths, "no_selected_overlay_primary_trades")

        sample_rows = _read_jsonl(sample_path)
        selected_severe = _severe_pairs_for_primary(selected_primary, sample_rows, settings)
        # Make the validation deterministic and chronological.
        selected_primary = sorted(selected_primary, key=_trade_sort_key)
        selected_severe = sorted(selected_severe, key=_trade_sort_key)

        robust_settings = _settings_for_robustness(settings)
        primary_summary = _basic_trade_summary(selected_primary, robust_settings)
        max_loss_streak = _max_consecutive_losses(selected_primary, settings.breakeven_r_abs)
        wf_report, wf_trade_rows = _run_walk_forward(selected_primary, robust_settings)
        oos_report = _run_oos(selected_primary, robust_settings)
        bootstrap_report = _run_bootstrap(selected_primary, robust_settings)
        cost_report = _cost_degradation(selected_primary, selected_severe, robust_settings)
        asset_groups = _group_summary(selected_primary, "asset", robust_settings)
        timeframe_groups = _group_summary(selected_primary, "timeframe", robust_settings)
        side_groups = _group_summary(selected_primary, "side", robust_settings)

        decision, labels, blockers = _classify_selected(
            primary_summary=primary_summary,
            wf_report=wf_report,
            oos_report=oos_report,
            bootstrap_report=bootstrap_report,
            cost_report=cost_report,
            asset_groups=asset_groups,
            timeframe_groups=timeframe_groups,
            side_groups=side_groups,
            max_consecutive_losses=max_loss_streak,
            settings=settings,
        )

        wf_report.update({
            "prompt_id": PROMPT_ID,
            "selected_overlay_id": settings.selected_overlay_id,
            "report": str(paths["wf"]),
        })
        oos_report.update({
            "prompt_id": PROMPT_ID,
            "selected_overlay_id": settings.selected_overlay_id,
            "report": str(paths["oos"]),
        })
        bootstrap_report.update({
            "prompt_id": PROMPT_ID,
            "selected_overlay_id": settings.selected_overlay_id,
            "report": str(paths["bootstrap"]),
        })
        labelled_rows: list[dict[str, Any]] = []
        labelled_rows.extend(_label_trade(r, settings, paired_severe=False) for r in selected_primary)
        labelled_rows.extend(_label_trade(r, settings, paired_severe=True) for r in selected_severe)
        written_rows = _write_jsonl(paths["trades"], labelled_rows, max_rows=settings.max_trade_rows_to_write)
        _write_json(paths["wf"], wf_report)
        _write_json(paths["oos"], oos_report)
        _write_json(paths["bootstrap"], bootstrap_report)

        asset_positive_ratio = _positive_group_ratio(asset_groups)
        timeframe_positive_ratio = _positive_group_ratio(timeframe_groups)
        side_positive_ratio = _positive_group_ratio(side_groups)
        asset_pnl_share = _pnl_dominance(asset_groups)
        timeframe_pnl_share = _pnl_dominance(timeframe_groups)
        report = {
            "prompt_id": PROMPT_ID,
            "status": "PASS",
            "decision": decision,
            "classification_labels": labels,
            "blockers": blockers,
            "created_at": utc_now_iso(),
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "selected_overlay_id": settings.selected_overlay_id,
            "overlay_oracle": False,
            "settings": asdict(settings),
            "combined_trades_path": str(combined_path),
            "sample_trades_path": str(sample_path),
            "raw_combined_trade_rows": len(combined_rows),
            "raw_sample_trade_rows": len(sample_rows),
            "selected_primary_trades": len(selected_primary),
            "paired_severe_trades": len(selected_severe),
            "written_selected_overlay_trade_rows": written_rows,
            "primary_summary": primary_summary,
            "primary_sum_r_post_cost": primary_summary.get("sum_r_post_cost"),
            "primary_avg_r_post_cost": primary_summary.get("avg_r_post_cost"),
            "primary_max_drawdown_r": primary_summary.get("max_drawdown_r"),
            "max_consecutive_losses": max_loss_streak,
            "walk_forward_stable": wf_report.get("walk_forward_stable", False),
            "walk_forward_positive_ratio": wf_report.get("walk_forward_positive_ratio"),
            "oos_pass": oos_report.get("oos_pass", False),
            "oos_avg_r_post_cost": oos_report.get("oos_avg_r_post_cost"),
            "oos_sum_r_post_cost": oos_report.get("oos_sum_r_post_cost"),
            "bootstrap_pass": bootstrap_report.get("bootstrap_pass", False),
            "bootstrap_positive_ratio": bootstrap_report.get("bootstrap_positive_ratio"),
            "bootstrap_median_avg_r": bootstrap_report.get("bootstrap_median_avg_r"),
            "cost_degradation_non_destructive": cost_report.get("cost_degradation_non_destructive", False),
            "cost_degradation_ratio": cost_report.get("cost_degradation_ratio"),
            "severe_positive_ratio": cost_report.get("severe_positive_ratio"),
            "cost_degradation": cost_report,
            "asset_stability_ok": bool(asset_positive_ratio >= settings.min_positive_asset_ratio and asset_pnl_share <= settings.max_asset_pnl_share),
            "timeframe_stability_ok": bool(timeframe_positive_ratio >= settings.min_positive_timeframe_ratio and timeframe_pnl_share <= settings.max_timeframe_pnl_share),
            "side_stability_ok": bool(side_positive_ratio >= settings.min_positive_side_ratio),
            "asset_stability": {
                "groups": asset_groups,
                "positive_group_ratio": _round(asset_positive_ratio, 8),
                "max_positive_pnl_share": _round(asset_pnl_share, 8),
            },
            "timeframe_stability": {
                "groups": timeframe_groups,
                "positive_group_ratio": _round(timeframe_positive_ratio, 8),
                "max_positive_pnl_share": _round(timeframe_pnl_share, 8),
            },
            "side_stability": {
                "groups": side_groups,
                "positive_group_ratio": _round(side_positive_ratio, 8),
            },
            "orders_submitted_by_lsr_v2_selected_overlay_validation": 0,
            "positions_opened_by_lsr_v2_selected_overlay_validation": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "submit_order": False,
            "broker_submit_called": False,
            "promotion_ready": False,
            "promotion_blocked_reason": "selected overlay validation is diagnostic; separate promotion gate required before paper supervised",
            "report": str(paths["report"]),
            "walk_forward_report": str(paths["wf"]),
            "oos_report": str(paths["oos"]),
            "bootstrap_report": str(paths["bootstrap"]),
            "trades_jsonl": str(paths["trades"]),
        }
        _write_json(paths["report"], report)
        return report
    except Exception as exc:
        report = {
            "prompt_id": PROMPT_ID,
            "status": "WARN",
            "decision": ERROR_DECISION,
            "classification_labels": [],
            "blockers": ["selected_overlay_validation_error"],
            "created_at": utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "locked_profile_name": LOCKED_PROFILE_NAME,
            "locked_variant_id": LOCKED_VARIANT_ID,
            "selected_overlay_id": settings.selected_overlay_id,
            "orders_submitted_by_lsr_v2_selected_overlay_validation": 0,
            "positions_opened_by_lsr_v2_selected_overlay_validation": 0,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "audit_only": True,
            "promotion_ready": False,
            "report": str(paths["report"]),
            "walk_forward_report": str(paths["wf"]),
            "oos_report": str(paths["oos"]),
            "bootstrap_report": str(paths["bootstrap"]),
            "trades_jsonl": str(paths["trades"]),
        }
        _write_json(paths["report"], report)
        _write_json(paths["wf"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION, "folds": []})
        _write_json(paths["oos"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_json(paths["bootstrap"], {"prompt_id": PROMPT_ID, "status": "WARN", "decision": ERROR_DECISION})
        _write_jsonl(paths["trades"], [])
        return report


__all__ = [
    "SELECTED_OVERLAY_ID",
    "LSRV2SelectedOverlayValidationSettings",
    "run_lsr_v2_selected_overlay_validation",
]
