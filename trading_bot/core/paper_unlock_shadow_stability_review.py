"""Prompt 29.4.4h shadow sample stability review.

Diagnostic-only follow-up to Prompt 29.4.4g.  The bounded cadence patch found a
candidate rolling shadow collection profile.  This module reviews whether that
sample is stable enough to justify a *future* paper-only activation draft.

Safety invariant: no orders, no paper order enablement, no live/testnet, no risk
or threshold changes.  A positive decision is only a diagnostic stability
candidate for another guarded-design patch.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from config import Config
from core.calibrated_structure_shadow import _safe_float, _safe_int, _summarize_rows
from core.independent_repaired_validation import _parse_dt, _sort_rows
from core.paper_unlock_bounded_cadence import (
    COLLECTION_NAME as BOUNDED_COLLECTION_NAME,
    REPORT_NAME as BOUNDED_CADENCE_REPORT_NAME,
    PaperUnlockBoundedCadenceSettings,
    _bounded_select,
    _cadence_profiles,
    _concentration,
    _holdout,
    _read_json,
    _split_windows,
    _window_stability,
)
from core.paper_unlock_shadow_dry_run import (
    _dry_run_gate,
    _entry_candidate_rows,
    _equity_curve,
    _experiment_design_guard,
    _target_rows,
)
from core.paper_unlock_shadow_rate_calibration import REPORT_NAME as RATE_CALIBRATION_REPORT_NAME
from core.calibrated_structure_shadow import _collect_historical_rows
from core.structure_context_repair import repair_structure_rows

REPORT_NAME = "paper_unlock_shadow_stability_review_report.json"
PROMPT_ID = "29.4.4h"
REVIEW_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_SAMPLE_STABILITY_REVIEW"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaperUnlockShadowStabilityReviewSettings:
    enabled: bool = True
    historical_enabled: bool = True
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    max_rows_per_asset: int = 5000
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    min_shadow_entries: int = 20
    min_shadow_expectancy_r: float = 0.05
    max_shadow_loss_rate_pct: float = 50.0
    max_shadow_time_exit_rate_pct: float = 60.0
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999
    dry_run_risk_per_trade_pct: float = 0.0025
    require_bounded_cadence_candidate: bool = True
    min_positive_window_rate_pct: float = 66.67
    min_holdout_entries: int = 5
    max_asset_concentration_pct: float = 75.0
    max_side_concentration_pct: float = 85.0
    min_distinct_assets: int = 2
    min_distinct_sides: int = 2
    min_distinct_days: int = 3
    max_single_day_concentration_pct: float = 45.0
    review_name: str = REVIEW_NAME

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockShadowStabilityReviewSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_HISTORICAL_ENABLED", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_HISTORICAL_ENABLED", True))),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_ROWS_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_EVAL_STRIDE", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_STRUCTURE_WINDOW_ROWS", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_shadow_entries=max(5, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_ENTRIES", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_ENTRIES", 20)), 20)),
            min_shadow_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_EXPECTANCY_R", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_EXPECTANCY_R", 0.05)), 0.05),
            max_shadow_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_LOSS_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_LOSS_RATE_PCT", 50.0)), 50.0),
            max_shadow_time_exit_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ABORT_MAX_CONSECUTIVE_LOSSES", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_CONSECUTIVE_LOSSES", 3)), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ABORT_MAX_DRAWDOWN_PCT", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_DRAWDOWN_PCT", 1.0)), 1.0)),
            map_score_candidate_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
            dry_run_risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_RISK_PER_TRADE_PCT", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_RISK_PER_TRADE_PCT", 0.0025)), 0.0025)),
            require_bounded_cadence_candidate=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_REQUIRE_BOUNDED_CADENCE", True)),
            min_positive_window_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_POSITIVE_WINDOW_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_POSITIVE_WINDOW_RATE_PCT", 66.67)), 66.67),
            min_holdout_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_HOLDOUT_ENTRIES", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_HOLDOUT_ENTRIES", 5)), 5)),
            max_asset_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_ASSET_CONCENTRATION_PCT", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ASSET_CONCENTRATION_PCT", 75.0)), 75.0),
            max_side_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_SIDE_CONCENTRATION_PCT", getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_SIDE_CONCENTRATION_PCT", 85.0)), 85.0),
            min_distinct_assets=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_ASSETS", 2), 2)),
            min_distinct_sides=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_SIDES", 2), 2)),
            min_distinct_days=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MIN_DISTINCT_DAYS", 3), 3)),
            max_single_day_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_MAX_SINGLE_DAY_CONCENTRATION_PCT", 45.0), 45.0),
            review_name=str(getattr(cfg, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_NAME", REVIEW_NAME) or REVIEW_NAME),
        )

    def bounded_settings(self) -> PaperUnlockBoundedCadenceSettings:
        return PaperUnlockBoundedCadenceSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            max_rows_per_asset=self.max_rows_per_asset,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            min_shadow_entries=self.min_shadow_entries,
            min_shadow_expectancy_r=self.min_shadow_expectancy_r,
            max_shadow_loss_rate_pct=self.max_shadow_loss_rate_pct,
            max_shadow_time_exit_rate_pct=self.max_shadow_time_exit_rate_pct,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
            dry_run_risk_per_trade_pct=self.dry_run_risk_per_trade_pct,
            abort_max_consecutive_losses=self.abort_max_consecutive_losses,
            abort_max_drawdown_pct=self.abort_max_drawdown_pct,
            require_experiment_design_ready=True,
            require_rate_calibration_ready=True,
            min_positive_window_rate_pct=self.min_positive_window_rate_pct,
            min_holdout_entries=self.min_holdout_entries,
            max_asset_concentration_pct=self.max_asset_concentration_pct,
            max_side_concentration_pct=self.max_side_concentration_pct,
        )

    def dry_run_settings(self, daily_entries: int, weekly_entries: int):
        return self.bounded_settings().dry_run_settings(daily_entries, weekly_entries)


def _safe_pct(count: int, total: int) -> float:
    return round((count / total) * 100.0, 4) if total else 0.0


def _date_key(row: dict[str, Any]) -> str:
    dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
    return dt.date().isoformat() if dt else "UNKNOWN_DATE"


def _week_key(row: dict[str, Any]) -> str:
    dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
    if not dt:
        return "UNKNOWN_WEEK"
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _bounded_cadence_guard(bounded_report: dict[str, Any], settings: PaperUnlockShadowStabilityReviewSettings) -> dict[str, Any]:
    if not bounded_report:
        return {"bounded_cadence_available": False, "bounded_cadence_candidate_ready": False, "reason": "missing 29.4.4g report"}
    decision = bounded_report.get("decision", {}) if isinstance(bounded_report.get("decision"), dict) else {}
    best = decision.get("best_bounded_cadence_variant", {}) if isinstance(decision.get("best_bounded_cadence_variant"), dict) else {}
    status = str(bounded_report.get("status") or "")
    decision_status = str(decision.get("status") or "")
    ready = bool(
        status == "PASS"
        and decision_status == "ROLLING_SHADOW_COLLECTION_CANDIDATE_DIAGNOSTIC"
        and best.get("rolling_collection_candidate", False)
        and not bool(bounded_report.get("paper_orders_enabled", False) or decision.get("paper_orders_enabled", False))
        and not bool(bounded_report.get("operational_unlock_allowed", False) or decision.get("operational_unlock_allowed", False))
        and not bool(bounded_report.get("paper_unlock_experiment_allowed", False) or decision.get("paper_unlock_experiment_allowed", False))
    )
    if not settings.require_bounded_cadence_candidate:
        ready = bool(bounded_report) and not bool(bounded_report.get("paper_orders_enabled", False))
    return {
        "bounded_cadence_available": bool(bounded_report),
        "bounded_cadence_candidate_ready": ready,
        "bounded_cadence_status": status,
        "bounded_cadence_decision": decision_status,
        "best_bounded_cadence_variant": best.get("name", ""),
        "best_selected_entries": _safe_int(best.get("selected_entries"), 0),
        "paper_orders_enabled": bool(bounded_report.get("paper_orders_enabled", False) or decision.get("paper_orders_enabled", False)),
        "paper_unlock_experiment_allowed": bool(bounded_report.get("paper_unlock_experiment_allowed", False) or decision.get("paper_unlock_experiment_allowed", False)),
        "operational_unlock_allowed": bool(bounded_report.get("operational_unlock_allowed", False) or decision.get("operational_unlock_allowed", False)),
        "reason": "bounded cadence diagnostic candidate ready" if ready else "bounded cadence prerequisite missing or unsafe",
    }


def _fallback_rows_from_bounded_report(bounded_report: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    decision = bounded_report.get("decision", {}) if isinstance(bounded_report.get("decision"), dict) else {}
    best_name = ""
    best = decision.get("best_bounded_cadence_variant", {}) if isinstance(decision.get("best_bounded_cadence_variant"), dict) else {}
    best_name = str(best.get("name") or "")
    variants = bounded_report.get("bounded_cadence_variants", []) if isinstance(bounded_report.get("bounded_cadence_variants"), list) else []
    selected_tail: list[dict[str, Any]] = []
    selected_variant: dict[str, Any] = {}
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        if str(variant.get("name") or "") == best_name:
            selected_variant = variant
            selected_tail = [r for r in variant.get("selected_tail", []) if isinstance(r, dict)]
            break
    if not selected_tail and isinstance(best.get("selected_tail"), list):
        selected_tail = [r for r in best.get("selected_tail", []) if isinstance(r, dict)]
        selected_variant = best
    rows = []
    for row in selected_tail:
        rows.append({
            **row,
            "repaired_structure_context_ok": str(row.get("structure_state") or "").upper() in {"CONTEXT", "CONFIRMATION"},
            "repaired_structure_confirmed": str(row.get("structure_state") or "").upper() == "CONFIRMATION",
        })
    return rows, {
        "available": bool(rows),
        "source": BOUNDED_CADENCE_REPORT_NAME,
        "rows": len(rows),
        "variant": best_name,
        "reason": "Used 29.4.4g selected_tail fallback because historical parquet rows were unavailable.",
        "variant_summary": selected_variant.get("summary", {}) if isinstance(selected_variant, dict) else {},
    }


def _find_profile(settings: PaperUnlockShadowStabilityReviewSettings, name: str | None) -> Any:
    profiles = _cadence_profiles(settings.bounded_settings())
    for p in profiles:
        if str(p.name) == str(name):
            return p
    # Default to the cadence that passed locally in 29.4.4g if absent.
    for p in profiles:
        if p.name == "bounded_6_daily_30_weekly_0h":
            return p
    return profiles[-1]


def _collect_selected_rows(base: Path, settings: PaperUnlockShadowStabilityReviewSettings, bounded_report: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    bounded_settings = settings.bounded_settings()
    dry_settings = bounded_settings.dry_run_settings()
    if settings.enabled and settings.historical_enabled:
        historical = _collect_historical_rows(base, dry_settings.calibrated_settings())
        repaired = repair_structure_rows(list(historical.get("candidate_rows") or []))
    else:
        historical = {"status": "DISABLED", "candidate_rows": [], "by_asset": {}}
        repaired = []
    if repaired:
        target_all = _target_rows(repaired, dry_settings)
        target_entry = _entry_candidate_rows(target_all)
        decision = bounded_report.get("decision", {}) if isinstance(bounded_report.get("decision"), dict) else {}
        best = decision.get("best_bounded_cadence_variant", {}) if isinstance(decision.get("best_bounded_cadence_variant"), dict) else {}
        profile = _find_profile(settings, best.get("name"))
        selected, rejected, cadence_summary = _bounded_select(target_entry, profile)
        return selected, rejected, cadence_summary, {
            "available": False,
            "historical_status": historical.get("status", "UNKNOWN"),
            "source_target_rows": len(target_all),
            "entry_candidate_rows": len(target_entry),
            "scenario_pattern_evaluation_rows": _safe_int(historical.get("scenario_pattern_evaluation_rows"), 0),
            "candidate_rows_pre_structure": _safe_int(historical.get("candidate_rows_pre_structure"), 0),
            "structured_candidate_rows": len(repaired),
            "by_asset": historical.get("by_asset", {}) if isinstance(historical.get("by_asset"), dict) else {},
        }
    fallback_rows, fallback_info = _fallback_rows_from_bounded_report(bounded_report)
    return fallback_rows, [], {}, {
        **fallback_info,
        "historical_status": historical.get("status", "UNKNOWN") if isinstance(historical, dict) else "UNKNOWN",
        "source_target_rows": _safe_int((bounded_report.get("counts") or {}).get("source_target_rows") if isinstance(bounded_report.get("counts"), dict) else 0, len(fallback_rows)),
        "entry_candidate_rows": _safe_int((bounded_report.get("counts") or {}).get("entry_candidate_rows") if isinstance(bounded_report.get("counts"), dict) else 0, len(fallback_rows)),
        "scenario_pattern_evaluation_rows": _safe_int((bounded_report.get("counts") or {}).get("scenario_pattern_evaluation_rows") if isinstance(bounded_report.get("counts"), dict) else 0, 0),
        "candidate_rows_pre_structure": _safe_int((bounded_report.get("counts") or {}).get("candidate_rows_pre_structure") if isinstance(bounded_report.get("counts"), dict) else 0, 0),
        "structured_candidate_rows": _safe_int((bounded_report.get("counts") or {}).get("structured_candidate_rows") if isinstance(bounded_report.get("counts"), dict) else 0, len(fallback_rows)),
        "by_asset": {},
    }


def _temporal_dispersion(rows: list[dict[str, Any]], settings: PaperUnlockShadowStabilityReviewSettings) -> dict[str, Any]:
    n = len(rows)
    days = Counter(_date_key(r) for r in rows)
    weeks = Counter(_week_key(r) for r in rows)
    day_conc = _safe_pct(max(days.values()) if days else 0, n)
    ok = bool(n > 0 and len(days) >= settings.min_distinct_days and day_conc <= settings.max_single_day_concentration_pct)
    return {
        "entries": n,
        "distinct_days": len(days),
        "distinct_weeks": len(weeks),
        "day_counts": dict(days),
        "week_counts": dict(weeks),
        "max_single_day_concentration_pct": day_conc,
        "max_allowed_single_day_concentration_pct": settings.max_single_day_concentration_pct,
        "min_distinct_days": settings.min_distinct_days,
        "temporal_dispersion_ok": ok,
        "start": _sort_rows(rows)[0].get("datetime") if rows else None,
        "end": _sort_rows(rows)[-1].get("datetime") if rows else None,
    }


def _outcome_quality(rows: list[dict[str, Any]], settings: PaperUnlockShadowStabilityReviewSettings) -> dict[str, Any]:
    summary = _summarize_rows(rows) if rows else {}
    outcomes = summary.get("outcomes", {}) if isinstance(summary.get("outcomes"), dict) else {}
    tp_total = _safe_int(outcomes.get("TP1_ONLY"), 0) + _safe_int(outcomes.get("TP2"), 0)
    sl = _safe_int(outcomes.get("SL"), 0)
    time_exit = _safe_int(outcomes.get("TIME_EXIT"), 0)
    n = len(rows)
    return {
        "summary": summary,
        "tp_total": tp_total,
        "sl": sl,
        "time_exit": time_exit,
        "tp_total_rate_pct": _safe_pct(tp_total, n),
        "sl_rate_pct": _safe_pct(sl, n),
        "time_exit_rate_pct": _safe_pct(time_exit, n),
        "expectancy_ok": _safe_float(summary.get("expectancy_r"), 0.0) >= settings.min_shadow_expectancy_r,
        "loss_rate_ok": _safe_float(summary.get("loss_rate_pct"), 100.0) <= settings.max_shadow_loss_rate_pct,
        "time_exit_ok": _safe_float(summary.get("time_exit_rate_pct"), 100.0) <= settings.max_shadow_time_exit_rate_pct,
        "sample_ok": n >= settings.min_shadow_entries,
    }


def _state_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    state_counts = Counter(str(r.get("structure_state") or "UNKNOWN").upper() for r in rows)
    confirmation_counts = Counter(str(r.get("confirmation_summary") or "UNKNOWN") for r in rows)
    location_counts = Counter(str(r.get("price_location") or "UNKNOWN") for r in rows)
    by_state: dict[str, Any] = {}
    for state in sorted(state_counts):
        subset = [r for r in rows if str(r.get("structure_state") or "UNKNOWN").upper() == state]
        by_state[state] = _summarize_rows(subset)
    return {
        "state_counts": dict(state_counts),
        "confirmation_summary_counts": dict(confirmation_counts),
        "price_location_counts": dict(location_counts),
        "by_state": by_state,
    }


def _review_checks(rows: list[dict[str, Any]], bounded_guard: dict[str, Any], experiment_guard: dict[str, Any], settings: PaperUnlockShadowStabilityReviewSettings, cadence_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    bounded_settings = settings.bounded_settings()
    dry_settings = bounded_settings.dry_run_settings()
    summary = _summarize_rows(rows) if rows else {}
    equity = _equity_curve(rows, dry_settings)
    dry_gate = _dry_run_gate(summary, equity, experiment_guard, dry_settings)
    windows = _window_stability(rows, bounded_settings)
    holdout = _holdout(rows, bounded_settings)
    concentration = _concentration(rows, bounded_settings)
    temporal = _temporal_dispersion(rows, settings)
    outcome = _outcome_quality(rows, settings)
    distinct_assets_ok = _safe_int(concentration.get("distinct_assets"), 0) >= settings.min_distinct_assets
    distinct_sides_ok = _safe_int(concentration.get("distinct_sides"), 0) >= settings.min_distinct_sides
    execution_disabled_ok = bool(
        not bounded_guard.get("paper_orders_enabled")
        and not bounded_guard.get("paper_unlock_experiment_allowed")
        and not bounded_guard.get("operational_unlock_allowed")
    )
    stability_candidate = bool(
        (not settings.require_bounded_cadence_candidate or bounded_guard.get("bounded_cadence_candidate_ready"))
        and experiment_guard.get("experiment_design_ready")
        and execution_disabled_ok
        and outcome.get("sample_ok")
        and outcome.get("expectancy_ok")
        and outcome.get("loss_rate_ok")
        and outcome.get("time_exit_ok")
        and dry_gate.get("consecutive_loss_guard_ok")
        and dry_gate.get("drawdown_guard_ok")
        and windows.get("positive_window_rate_ok")
        and holdout.get("holdout_ok")
        and concentration.get("passes_concentration_guard")
        and distinct_assets_ok
        and distinct_sides_ok
        and temporal.get("temporal_dispersion_ok")
    )
    return {
        "stability_candidate": stability_candidate,
        "sample_ok": outcome.get("sample_ok"),
        "aggregate_expectancy_ok": outcome.get("expectancy_ok"),
        "aggregate_loss_rate_ok": outcome.get("loss_rate_ok"),
        "aggregate_time_exit_ok": outcome.get("time_exit_ok"),
        "equity_guard_ok": bool(dry_gate.get("consecutive_loss_guard_ok") and dry_gate.get("drawdown_guard_ok")),
        "rolling_window_ok": bool(windows.get("positive_window_rate_ok")),
        "holdout_ok": bool(holdout.get("holdout_ok")),
        "concentration_ok": bool(concentration.get("passes_concentration_guard") and distinct_assets_ok and distinct_sides_ok),
        "temporal_dispersion_ok": bool(temporal.get("temporal_dispersion_ok")),
        "execution_disabled_ok": execution_disabled_ok,
        "dry_run_gate": dry_gate,
        "equity_dry_run": equity,
        "window_stability": windows,
        "holdout": holdout,
        "concentration": {**concentration, "distinct_assets_ok": distinct_assets_ok, "distinct_sides_ok": distinct_sides_ok},
        "temporal_dispersion": temporal,
        "outcome_quality": outcome,
        "cadence_summary": cadence_summary or {},
        "state_breakdown": _state_breakdown(rows),
    }


def _decision(checks: dict[str, Any], bounded_guard: dict[str, Any], selected_rows: list[dict[str, Any]], settings: PaperUnlockShadowStabilityReviewSettings) -> dict[str, Any]:
    if settings.require_bounded_cadence_candidate and not bool(bounded_guard.get("bounded_cadence_candidate_ready")):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "29.4.4g bounded cadence prerequisite is not ready; shadow stability review cannot advance.",
            "best_stability_review_variant": "",
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "Repair bounded cadence prerequisites before any paper-only activation draft.",
        }
    if checks.get("stability_candidate"):
        return {
            "status": "SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC",
            "reason": "Bounded cadence shadow sample passed aggregate, equity, rolling-window, holdout, concentration and temporal dispersion guards. Execution remains disabled pending a separate guarded paper-only activation draft.",
            "best_stability_review_variant": bounded_guard.get("best_bounded_cadence_variant", ""),
            "selected_entries": len(selected_rows),
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "29.4.4i guarded paper-only activation draft / safety interlock design, still no live/testnet and no automatic activation.",
        }
    failed = [k for k, v in checks.items() if k.endswith("_ok") and v is False]
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "Shadow sample stability review did not pass all guards; keep collecting/reviewing shadow rows before any activation draft.",
        "failed_checks": failed,
        "best_stability_review_variant": bounded_guard.get("best_bounded_cadence_variant", ""),
        "selected_entries": len(selected_rows),
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
        "orders_submitted": 0,
        "positions_opened": 0,
        "next_patch": "Repair failed stability guards or keep rolling shadow collection diagnostic-only.",
    }


def _settings_payload(settings: PaperUnlockShadowStabilityReviewSettings) -> dict[str, Any]:
    return {
        "review_name": settings.review_name,
        "min_shadow_entries": settings.min_shadow_entries,
        "min_shadow_expectancy_r": settings.min_shadow_expectancy_r,
        "max_shadow_loss_rate_pct": settings.max_shadow_loss_rate_pct,
        "max_shadow_time_exit_rate_pct": settings.max_shadow_time_exit_rate_pct,
        "abort_max_consecutive_losses": settings.abort_max_consecutive_losses,
        "abort_max_drawdown_pct": settings.abort_max_drawdown_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
        "require_bounded_cadence_candidate": settings.require_bounded_cadence_candidate,
        "min_positive_window_rate_pct": settings.min_positive_window_rate_pct,
        "min_holdout_entries": settings.min_holdout_entries,
        "max_asset_concentration_pct": settings.max_asset_concentration_pct,
        "max_side_concentration_pct": settings.max_side_concentration_pct,
        "min_distinct_assets": settings.min_distinct_assets,
        "min_distinct_sides": settings.min_distinct_sides,
        "min_distinct_days": settings.min_distinct_days,
        "max_single_day_concentration_pct": settings.max_single_day_concentration_pct,
    }


def build_paper_unlock_shadow_stability_review_report(data_dir: str | Path = "data", settings: PaperUnlockShadowStabilityReviewSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or PaperUnlockShadowStabilityReviewSettings.from_config()
    bounded_report = _read_json(base / BOUNDED_CADENCE_REPORT_NAME)
    bounded_guard = _bounded_cadence_guard(bounded_report, settings)
    experiment_report = _read_json(base / "paper_unlock_experiment_design_report.json")
    experiment_guard = _experiment_design_guard(experiment_report, settings.bounded_settings().dry_run_settings())
    selected_rows, rejected_rows, cadence_summary, source_info = _collect_selected_rows(base, settings, bounded_report)
    checks = _review_checks(selected_rows, bounded_guard, experiment_guard, settings, cadence_summary)
    decision = _decision(checks, bounded_guard, selected_rows, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC" else "WARN")
    report = {
        "report_type": "paper_only_shadow_sample_stability_review",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "review_name": settings.review_name,
        "collection_name": BOUNDED_COLLECTION_NAME,
        "bounded_cadence_guard": bounded_guard,
        "experiment_design_guard": experiment_guard,
        "stability_checks": checks,
        "selected_summary": _summarize_rows(selected_rows) if selected_rows else {},
        "selected_tail": [
            {
                "datetime": r.get("datetime"),
                "symbol": r.get("symbol"),
                "side": r.get("side"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
                "map_score": r.get("map_score"),
                "structure_state": r.get("structure_state"),
                "confirmation_summary": r.get("confirmation_summary"),
            }
            for r in selected_rows[-25:]
        ],
        "rejected_entries": len(rejected_rows),
        "source_info": source_info,
        "fallback": {"available": bool(source_info.get("available")), "source": source_info.get("source", ""), "rows": source_info.get("rows", 0), "reason": source_info.get("reason", "")},
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "profile_activation_allowed": False,
        "paper_orders_enabled": False,
        "settings": _settings_payload(settings),
        "counts": {
            "scenario_pattern_evaluation_rows": _safe_int(source_info.get("scenario_pattern_evaluation_rows"), 0),
            "candidate_rows_pre_structure": _safe_int(source_info.get("candidate_rows_pre_structure"), 0),
            "structured_candidate_rows": _safe_int(source_info.get("structured_candidate_rows"), 0),
            "source_target_rows": _safe_int(source_info.get("source_target_rows"), 0),
            "entry_candidate_rows": _safe_int(source_info.get("entry_candidate_rows"), 0),
            "selected_entries": len(selected_rows),
            "rejected_entries": len(rejected_rows),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "by_asset": source_info.get("by_asset", {}) if isinstance(source_info.get("by_asset"), dict) else {},
        "files": {
            "report": str(base / REPORT_NAME),
            "paper_unlock_bounded_cadence": str(base / BOUNDED_CADENCE_REPORT_NAME),
            "paper_unlock_shadow_rate_calibration": str(base / RATE_CALIBRATION_REPORT_NAME),
            "paper_unlock_experiment_design": str(base / "paper_unlock_experiment_design_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_shadow_stability_review_report(data_dir: str | Path = "data", settings: PaperUnlockShadowStabilityReviewSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_shadow_stability_review_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "REVIEW_NAME",
    "PaperUnlockShadowStabilityReviewSettings",
    "build_paper_unlock_shadow_stability_review_report",
    "write_paper_unlock_shadow_stability_review_report",
]
