"""Prompt 29.4.4g bounded cadence expansion / rolling shadow collection.

Diagnostic-only follow-up to Prompt 29.4.4f.  The previous rate calibration
showed that only the all-shadow ceiling could reach the minimum sample.  This
module tests additional *bounded* cadence profiles and rolling stability guards
without enabling paper orders or changing risk/thresholds.

Safety invariant: no orders, no live, no testnet, no paper experiment
activation.  A positive result is only a rolling shadow collection candidate for
another diagnostic review patch.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from config import Config
from core.calibrated_structure_shadow import _collect_historical_rows, _safe_float, _safe_int, _summarize_rows
from core.independent_repaired_validation import _parse_dt, _sort_rows
from core.paper_unlock_shadow_dry_run import (
    PaperUnlockShadowDryRunSettings,
    _dry_run_gate,
    _entry_candidate_rows,
    _equity_curve,
    _experiment_design_guard,
    _read_json,
    _target_rows,
)
from core.paper_unlock_shadow_rate_calibration import (
    CALIBRATION_NAME as RATE_CALIBRATION_NAME,
    REPORT_NAME as RATE_CALIBRATION_REPORT_NAME,
    PaperUnlockShadowRateCalibrationSettings,
)
from core.structure_context_repair import repair_structure_rows

REPORT_NAME = "paper_unlock_bounded_cadence_report.json"
PROMPT_ID = "29.4.4g"
COLLECTION_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_BOUNDED_CADENCE_COLLECTION"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BoundedCadenceProfile:
    name: str
    max_daily_entries: int
    max_weekly_entries: int
    min_hours_between_entries: float
    description: str
    bounded_collection_profile: bool = True


@dataclass(frozen=True)
class PaperUnlockBoundedCadenceSettings:
    enabled: bool = True
    historical_enabled: bool = True
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    max_rows_per_asset: int = 5000
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    min_variant_candidates: int = 50
    min_shadow_entries: int = 20
    min_shadow_expectancy_r: float = 0.05
    max_shadow_loss_rate_pct: float = 50.0
    max_shadow_time_exit_rate_pct: float = 60.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999
    dry_run_risk_per_trade_pct: float = 0.0025
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0
    require_experiment_design_ready: bool = True
    require_rate_calibration_ready: bool = True
    collection_name: str = COLLECTION_NAME
    min_positive_window_rate_pct: float = 66.67
    min_holdout_entries: int = 5
    max_asset_concentration_pct: float = 75.0
    max_side_concentration_pct: float = 85.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockBoundedCadenceSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_HISTORICAL_ENABLED", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_HISTORICAL_ENABLED", True))),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ROWS_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_EVAL_STRIDE", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_STRUCTURE_WINDOW_ROWS", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_VARIANT_CANDIDATES", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_shadow_entries=max(5, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_ENTRIES", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_ENTRIES", 20)), 20)),
            min_shadow_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_EXPECTANCY_R", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_EXPECTANCY_R", 0.05)), 0.05),
            max_shadow_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_LOSS_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_LOSS_RATE_PCT", 50.0)), 50.0),
            max_shadow_time_exit_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
            dry_run_risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_RISK_PER_TRADE_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_RISK_PER_TRADE_PCT", 0.0025)), 0.0025)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_CONSECUTIVE_LOSSES", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_CONSECUTIVE_LOSSES", 3)), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_ABORT_MAX_DRAWDOWN_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_DRAWDOWN_PCT", 1.0)), 1.0)),
            require_experiment_design_ready=bool(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_REQUIRE_EXPERIMENT_READY", getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_EXPERIMENT_READY", True))),
            require_rate_calibration_ready=bool(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_REQUIRE_RATE_CALIBRATION", True)),
            collection_name=str(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_NAME", COLLECTION_NAME) or COLLECTION_NAME),
            min_positive_window_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_POSITIVE_WINDOW_RATE_PCT", 66.67), 66.67),
            min_holdout_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MIN_HOLDOUT_ENTRIES", 5), 5)),
            max_asset_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_ASSET_CONCENTRATION_PCT", 75.0), 75.0),
            max_side_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_BOUNDED_CADENCE_MAX_SIDE_CONCENTRATION_PCT", 85.0), 85.0),
        )

    def dry_run_settings(self, daily_entries: int = 1, weekly_entries: int = 5) -> PaperUnlockShadowDryRunSettings:
        return PaperUnlockShadowDryRunSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            max_rows_per_asset=self.max_rows_per_asset,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            min_variant_candidates=self.min_variant_candidates,
            min_shadow_entries=self.min_shadow_entries,
            min_shadow_expectancy_r=self.min_shadow_expectancy_r,
            max_shadow_loss_rate_pct=self.max_shadow_loss_rate_pct,
            max_shadow_time_exit_rate_pct=self.max_shadow_time_exit_rate_pct,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
            dry_run_risk_per_trade_pct=self.dry_run_risk_per_trade_pct,
            dry_run_max_daily_entries=max(1, int(daily_entries)),
            dry_run_max_weekly_entries=max(1, int(weekly_entries)),
            abort_max_consecutive_losses=self.abort_max_consecutive_losses,
            abort_max_drawdown_pct=self.abort_max_drawdown_pct,
            require_experiment_design_ready=self.require_experiment_design_ready,
        )

    def calibrated_settings(self):
        return self.dry_run_settings().calibrated_settings()


def _cadence_profiles(settings: PaperUnlockBoundedCadenceSettings) -> list[BoundedCadenceProfile]:
    return [
        BoundedCadenceProfile("bounded_2_daily_14_weekly_0h", 2, 14, 0.0, "Controlled weekly cadence; expected to remain sample-constrained."),
        BoundedCadenceProfile("bounded_3_daily_18_weekly_0h", 3, 18, 0.0, "Moderate bounded cadence between 29.4.4f balanced and expanded profiles."),
        BoundedCadenceProfile("bounded_4_daily_24_weekly_0h", 4, 24, 0.0, "Higher bounded sample cadence; still has explicit daily/weekly caps."),
        BoundedCadenceProfile("bounded_5_daily_25_weekly_0h", 5, 25, 0.0, "Rolling collection cadence designed to recover more shadow rows without ceiling behavior."),
        BoundedCadenceProfile("bounded_6_daily_30_weekly_0h", 6, 30, 0.0, "Upper bounded collection cadence for diagnostics only; not an activation profile."),
        BoundedCadenceProfile("bounded_4_daily_24_weekly_4h", 4, 24, 4.0, "Same as 4/24 but requires a four-hour spacing between selected entries."),
        BoundedCadenceProfile("bounded_5_daily_25_weekly_4h", 5, 25, 4.0, "Same as 5/25 with a four-hour spacing guard."),
        BoundedCadenceProfile("bounded_6_daily_30_weekly_4h", 6, 30, 4.0, "Upper bounded cadence with spacing guard, diagnostics only."),
    ]


def _day_key(row: dict[str, Any]) -> str:
    dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
    return dt.date().isoformat() if dt else "UNKNOWN_DATE"


def _week_key(row: dict[str, Any]) -> str:
    dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
    if not dt:
        return "UNKNOWN_WEEK"
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _hours_between(prev: datetime | None, current: datetime | None) -> float | None:
    if not prev or not current:
        return None
    return abs((current - prev).total_seconds()) / 3600.0


def _bounded_select(rows: list[dict[str, Any]], profile: BoundedCadenceProfile) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    daily_counts: Counter[str] = Counter()
    weekly_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    last_selected_dt: datetime | None = None
    for row in _sort_rows(rows):
        day = _day_key(row)
        week = _week_key(row)
        current_dt = _parse_dt(row.get("datetime") or row.get("timestamp") or row.get("time"))
        reason = ""
        if daily_counts[day] >= profile.max_daily_entries:
            reason = "DAILY_LIMIT"
        elif weekly_counts[week] >= profile.max_weekly_entries:
            reason = "WEEKLY_LIMIT"
        elif profile.min_hours_between_entries > 0:
            delta_h = _hours_between(last_selected_dt, current_dt)
            if delta_h is not None and delta_h < profile.min_hours_between_entries:
                reason = "COOLDOWN_LIMIT"
        if reason:
            rejection_counts[reason] += 1
            rejected.append({**row, "bounded_cadence_reject_reason": reason})
            continue
        daily_counts[day] += 1
        weekly_counts[week] += 1
        last_selected_dt = current_dt or last_selected_dt
        selected.append({
            **row,
            "bounded_cadence_event": "ROLLING_SHADOW_ENTRY_ACCEPTED",
            "bounded_cadence_day": day,
            "bounded_cadence_week": week,
            "bounded_cadence_profile": profile.name,
        })
    return selected, rejected, {
        "max_daily_entries": profile.max_daily_entries,
        "max_weekly_entries": profile.max_weekly_entries,
        "min_hours_between_entries": profile.min_hours_between_entries,
        "days_used": len(daily_counts),
        "weeks_used": len(weekly_counts),
        "max_observed_daily_entries": max(daily_counts.values()) if daily_counts else 0,
        "max_observed_weekly_entries": max(weekly_counts.values()) if weekly_counts else 0,
        "rejection_counts": dict(rejection_counts),
    }


def _split_windows(rows: list[dict[str, Any]], folds: int = 3) -> list[list[dict[str, Any]]]:
    ordered = _sort_rows(rows)
    if not ordered:
        return []
    folds = max(1, min(folds, len(ordered)))
    windows: list[list[dict[str, Any]]] = []
    base, remainder = divmod(len(ordered), folds)
    start = 0
    for i in range(folds):
        size = base + (1 if i < remainder else 0)
        end = start + size
        chunk = ordered[start:end]
        if chunk:
            windows.append(chunk)
        start = end
    return windows


def _window_stability(rows: list[dict[str, Any]], settings: PaperUnlockBoundedCadenceSettings) -> dict[str, Any]:
    windows = _split_windows(rows, 3)
    records = []
    positive = 0
    passing = 0
    for idx, win in enumerate(windows, start=1):
        summary = _summarize_rows(win) if win else {}
        expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
        loss = _safe_float(summary.get("loss_rate_pct"), 100.0)
        ok = bool(expectancy >= 0.0 and loss <= settings.max_shadow_loss_rate_pct)
        if expectancy > 0.0:
            positive += 1
        if ok:
            passing += 1
        records.append({
            "window": idx,
            "entries": len(win),
            "expectancy_r": summary.get("expectancy_r", 0.0),
            "win_rate_pct": summary.get("win_rate_pct", 0.0),
            "loss_rate_pct": summary.get("loss_rate_pct", 0.0),
            "time_exit_rate_pct": summary.get("time_exit_rate_pct", 0.0),
            "passes_window_guard": ok,
            "start": win[0].get("datetime") if win else None,
            "end": win[-1].get("datetime") if win else None,
        })
    count = len(windows)
    positive_rate = round((positive / count) * 100.0, 4) if count else 0.0
    passing_rate = round((passing / count) * 100.0, 4) if count else 0.0
    return {
        "window_count": count,
        "positive_windows": positive,
        "passing_windows": passing,
        "positive_window_rate_pct": positive_rate,
        "passing_window_rate_pct": passing_rate,
        "min_positive_window_rate_pct": settings.min_positive_window_rate_pct,
        "positive_window_rate_ok": bool(positive_rate >= settings.min_positive_window_rate_pct),
        "windows": records,
    }


def _holdout(rows: list[dict[str, Any]], settings: PaperUnlockBoundedCadenceSettings) -> dict[str, Any]:
    ordered = _sort_rows(rows)
    if not ordered:
        return {"entries": 0, "holdout_ok": False, "reason": "no rows"}
    size = max(settings.min_holdout_entries, int(round(len(ordered) * 0.25)))
    size = min(size, len(ordered))
    hold = ordered[-size:]
    summary = _summarize_rows(hold)
    ok = bool(len(hold) >= settings.min_holdout_entries and _safe_float(summary.get("expectancy_r"), 0.0) >= 0.0 and _safe_float(summary.get("loss_rate_pct"), 100.0) <= settings.max_shadow_loss_rate_pct)
    return {
        "entries": len(hold),
        "min_holdout_entries": settings.min_holdout_entries,
        "holdout_ok": ok,
        "summary": summary,
        "start": hold[0].get("datetime"),
        "end": hold[-1].get("datetime"),
    }


def _concentration(rows: list[dict[str, Any]], settings: PaperUnlockBoundedCadenceSettings) -> dict[str, Any]:
    n = len(rows)
    assets = Counter(str(r.get("symbol") or "NA") for r in rows)
    sides = Counter(str(r.get("side") or "NA") for r in rows)
    asset_conc = round((max(assets.values()) / n) * 100.0, 4) if n and assets else 0.0
    side_conc = round((max(sides.values()) / n) * 100.0, 4) if n and sides else 0.0
    asset_ok = bool(n > 0 and asset_conc <= settings.max_asset_concentration_pct and len(assets) >= 2)
    side_ok = bool(n > 0 and side_conc <= settings.max_side_concentration_pct and len(sides) >= 2)
    return {
        "entries": n,
        "asset_counts": dict(assets),
        "side_counts": dict(sides),
        "distinct_assets": len(assets),
        "distinct_sides": len(sides),
        "asset_concentration_pct": asset_conc,
        "side_concentration_pct": side_conc,
        "max_asset_concentration_pct": settings.max_asset_concentration_pct,
        "max_side_concentration_pct": settings.max_side_concentration_pct,
        "asset_concentration_ok": asset_ok,
        "side_concentration_ok": side_ok,
        "passes_concentration_guard": bool(asset_ok and side_ok),
    }


def _rate_calibration_guard(rate_report: dict[str, Any], settings: PaperUnlockBoundedCadenceSettings) -> dict[str, Any]:
    if not rate_report:
        return {
            "rate_calibration_available": False,
            "rate_calibration_status": "MISSING",
            "rate_calibration_decision": "MISSING",
            "reason": f"{RATE_CALIBRATION_REPORT_NAME} is missing",
        }
    decision = rate_report.get("decision", {}) if isinstance(rate_report.get("decision"), dict) else {}
    status = str(rate_report.get("status") or "NA")
    decision_status = str(decision.get("status") or "NA")
    counts = rate_report.get("counts", {}) if isinstance(rate_report.get("counts"), dict) else {}
    # 29.4.4f normally stays WARN/KEEP_DIAGNOSTIC because only the ceiling passed.
    # That is an acceptable prerequisite here: this patch exists precisely to test
    # additional bounded cadence profiles after that block.
    ready = bool(
        status in {"PASS", "WARN"}
        and decision_status in {"KEEP_DIAGNOSTIC", "SHADOW_RATE_CALIBRATION_READY_DIAGNOSTIC"}
        and _safe_int(counts.get("entry_candidate_rows"), 0) > 0
        and not bool(rate_report.get("paper_orders_enabled", False) or decision.get("paper_orders_enabled", False))
        and not bool(rate_report.get("operational_unlock_allowed", False) or decision.get("operational_unlock_allowed", False))
    )
    return {
        "rate_calibration_available": bool(rate_report),
        "rate_calibration_ready": ready,
        "rate_calibration_status": status,
        "rate_calibration_decision": decision_status,
        "best_rate_variant": (decision.get("best_rate_variant") or {}).get("name") if isinstance(decision.get("best_rate_variant"), dict) else "",
        "entry_candidate_rows": _safe_int(counts.get("entry_candidate_rows"), 0),
        "best_selected_entries": _safe_int(counts.get("best_selected_entries"), 0),
        "paper_orders_enabled": bool(rate_report.get("paper_orders_enabled", False) or decision.get("paper_orders_enabled", False)),
        "operational_unlock_allowed": bool(rate_report.get("operational_unlock_allowed", False) or decision.get("operational_unlock_allowed", False)),
        "reason": "rate calibration guard passed for bounded cadence diagnostics" if ready else "rate calibration prerequisite did not pass or execution flags were attempted",
    }


def _fallback_rows_from_rate_report(rate_report: dict[str, Any]) -> list[dict[str, Any]]:
    decision = rate_report.get("decision", {}) if isinstance(rate_report.get("decision"), dict) else {}
    best = decision.get("best_rate_variant", {}) if isinstance(decision.get("best_rate_variant"), dict) else {}
    variants = rate_report.get("rate_limit_variants", []) if isinstance(rate_report.get("rate_limit_variants"), list) else []
    candidates: list[dict[str, Any]] = []
    if isinstance(best.get("selected_tail"), list):
        candidates.extend([x for x in best.get("selected_tail", []) if isinstance(x, dict)])
    for v in variants:
        if not isinstance(v, dict):
            continue
        if str(v.get("name") or "") == "all_shadow_ceiling_99_daily_99_weekly" and isinstance(v.get("selected_tail"), list):
            candidates = [x for x in v.get("selected_tail", []) if isinstance(x, dict)]
            break
    enriched: list[dict[str, Any]] = []
    for row in candidates:
        state = str(row.get("structure_state") or "").upper()
        enriched.append({
            **row,
            "repaired_structure_context_ok": state in {"CONTEXT", "CONFIRMATION"},
            "repaired_structure_confirmed": state == "CONFIRMATION",
            "repaired_wait_state": state == "WAIT",
            "repaired_no_structure": state == "NO_STRUCTURE",
            "repaired_conflict": state == "CONFLICT",
        })
    return enriched


def _variant_record(profile: BoundedCadenceProfile, rows: list[dict[str, Any]], experiment_guard: dict[str, Any], rate_guard: dict[str, Any], settings: PaperUnlockBoundedCadenceSettings) -> dict[str, Any]:
    dry_settings = settings.dry_run_settings(profile.max_daily_entries, profile.max_weekly_entries)
    selected, rejected, cadence_summary = _bounded_select(rows, profile)
    summary = _summarize_rows(selected) if selected else {}
    equity = _equity_curve(selected, dry_settings)
    dry_gate = _dry_run_gate(summary, equity, experiment_guard, dry_settings)
    windows = _window_stability(selected, settings)
    holdout = _holdout(selected, settings)
    concentration = _concentration(selected, settings)
    prerequisite_ok = bool((not settings.require_rate_calibration_ready or rate_guard.get("rate_calibration_ready")) and experiment_guard.get("experiment_design_ready"))
    rolling_collection_candidate = bool(
        profile.bounded_collection_profile
        and prerequisite_ok
        and dry_gate.get("passes_shadow_dry_run_gate")
        and windows.get("positive_window_rate_ok")
        and holdout.get("holdout_ok")
        and concentration.get("passes_concentration_guard")
    )
    return {
        "name": profile.name,
        "description": profile.description,
        "max_daily_entries": profile.max_daily_entries,
        "max_weekly_entries": profile.max_weekly_entries,
        "min_hours_between_entries": profile.min_hours_between_entries,
        "bounded_collection_profile": profile.bounded_collection_profile,
        "rolling_collection_candidate": rolling_collection_candidate,
        "selected_entries": len(selected),
        "rejected_entries": len(rejected),
        "summary": summary,
        "equity_dry_run": equity,
        "dry_run_gate": dry_gate,
        "window_stability": windows,
        "holdout": holdout,
        "concentration": concentration,
        "cadence_summary": cadence_summary,
        "selected_by_symbol": dict(Counter(str(r.get("symbol") or "NA") for r in selected)),
        "selected_by_side": dict(Counter(str(r.get("side") or "NA") for r in selected)),
        "selected_by_outcome": dict(Counter(str(r.get("outcome") or "NA") for r in selected)),
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
            for r in selected[-25:]
        ],
    }


def _score_variant(v: dict[str, Any]) -> tuple[int, int, int, int, float, int, float]:
    summary = v.get("summary", {}) if isinstance(v.get("summary"), dict) else {}
    dry_gate = v.get("dry_run_gate", {}) if isinstance(v.get("dry_run_gate"), dict) else {}
    windows = v.get("window_stability", {}) if isinstance(v.get("window_stability"), dict) else {}
    return (
        1 if bool(v.get("rolling_collection_candidate")) else 0,
        1 if bool(dry_gate.get("passes_shadow_dry_run_gate")) else 0,
        1 if bool(windows.get("positive_window_rate_ok")) else 0,
        _safe_int(v.get("selected_entries"), 0),
        _safe_float(summary.get("expectancy_r"), 0.0),
        -_safe_int(v.get("rejected_entries"), 999),
        -_safe_float(summary.get("loss_rate_pct"), 100.0),
    )


def _settings_payload(settings: PaperUnlockBoundedCadenceSettings) -> dict[str, Any]:
    return {
        "collection_name": settings.collection_name,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_shadow_entries": settings.min_shadow_entries,
        "min_shadow_expectancy_r": settings.min_shadow_expectancy_r,
        "max_shadow_loss_rate_pct": settings.max_shadow_loss_rate_pct,
        "max_shadow_time_exit_rate_pct": settings.max_shadow_time_exit_rate_pct,
        "abort_max_consecutive_losses": settings.abort_max_consecutive_losses,
        "abort_max_drawdown_pct": settings.abort_max_drawdown_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
        "require_experiment_design_ready": settings.require_experiment_design_ready,
        "require_rate_calibration_ready": settings.require_rate_calibration_ready,
        "min_positive_window_rate_pct": settings.min_positive_window_rate_pct,
        "min_holdout_entries": settings.min_holdout_entries,
        "max_asset_concentration_pct": settings.max_asset_concentration_pct,
        "max_side_concentration_pct": settings.max_side_concentration_pct,
    }


def _decision(experiment_guard: dict[str, Any], rate_guard: dict[str, Any], best: dict[str, Any], variants: list[dict[str, Any]], settings: PaperUnlockBoundedCadenceSettings) -> dict[str, Any]:
    if settings.require_experiment_design_ready and not bool(experiment_guard.get("experiment_design_ready")):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "29.4.4d experiment design guard is not ready; bounded cadence collection cannot advance.",
            "best_bounded_cadence_variant": best,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "Repair experiment design prerequisites before any cadence collection review.",
        }
    if settings.require_rate_calibration_ready and not bool(rate_guard.get("rate_calibration_ready")):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "29.4.4f rate calibration guard is not ready; bounded cadence collection cannot advance.",
            "best_bounded_cadence_variant": best,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "Repair rate calibration prerequisites before testing bounded cadence collection.",
        }
    candidates = [v for v in variants if bool(v.get("rolling_collection_candidate"))]
    if candidates:
        return {
            "status": "ROLLING_SHADOW_COLLECTION_CANDIDATE_DIAGNOSTIC",
            "reason": "At least one bounded cadence profile reached sample, dry-run, rolling-window, holdout and concentration guards. Execution remains disabled pending shadow sample stability review.",
            "best_bounded_cadence_variant": best,
            "candidate_bounded_cadence_variants": [v.get("name") for v in candidates],
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "29.4.4h shadow sample stability review, still diagnostic-only and no live/testnet.",
        }
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "No bounded cadence profile passed sample, dry-run, rolling-window, holdout and concentration guards.",
        "best_bounded_cadence_variant": best,
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
        "orders_submitted": 0,
        "positions_opened": 0,
        "next_patch": "Collect more rolling shadow observations or adjust bounded cadence diagnostics before any paper experiment activation.",
    }


def build_paper_unlock_bounded_cadence_report(data_dir: str | Path = "data", settings: PaperUnlockBoundedCadenceSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or PaperUnlockBoundedCadenceSettings.from_config()
    dry_settings = settings.dry_run_settings()
    experiment_report = _read_json(base / "paper_unlock_experiment_design_report.json")
    experiment_guard = _experiment_design_guard(experiment_report, dry_settings)
    rate_report = _read_json(base / RATE_CALIBRATION_REPORT_NAME)
    rate_guard = _rate_calibration_guard(rate_report, settings)

    fallback: dict[str, Any] = {"available": False}
    if not settings.enabled:
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
        repaired_rows: list[dict[str, Any]] = []
    else:
        historical = _collect_historical_rows(base, dry_settings.calibrated_settings())
        repaired_rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
        if not repaired_rows:
            repaired_rows = _fallback_rows_from_rate_report(rate_report)
            fallback = {
                "available": bool(repaired_rows),
                "source": RATE_CALIBRATION_REPORT_NAME,
                "rows": len(repaired_rows),
                "reason": "Used rate-calibration selected_tail fallback because historical parquet rows were unavailable.",
            }

    target_all = _target_rows(repaired_rows, dry_settings) if repaired_rows else []
    target_entry = _entry_candidate_rows(target_all)
    variants = [_variant_record(profile, target_entry, experiment_guard, rate_guard, settings) for profile in _cadence_profiles(settings)]
    variants = sorted(variants, key=_score_variant, reverse=True)
    best = variants[0] if variants else {}
    decision = _decision(experiment_guard, rate_guard, best, variants, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "ROLLING_SHADOW_COLLECTION_CANDIDATE_DIAGNOSTIC" else "WARN")
    report = {
        "report_type": "paper_only_bounded_cadence_rolling_shadow_collection",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "collection_name": settings.collection_name,
        "experiment_design_guard": experiment_guard,
        "rate_calibration_guard": rate_guard,
        "source_target_summary": _summarize_rows(target_all) if target_all else {},
        "entry_candidate_summary": _summarize_rows(target_entry) if target_entry else {},
        "bounded_cadence_variants": variants,
        "fallback": fallback,
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
            "scenario_pattern_evaluation_rows": _safe_int(historical.get("scenario_pattern_evaluation_rows"), 0),
            "candidate_rows_pre_structure": _safe_int(historical.get("candidate_rows_pre_structure"), 0),
            "structured_candidate_rows": len(repaired_rows),
            "source_target_rows": len(target_all),
            "entry_candidate_rows": len(target_entry),
            "bounded_cadence_variants": len(variants),
            "best_selected_entries": _safe_int(best.get("selected_entries"), 0) if best else 0,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "by_asset": historical.get("by_asset", {}) if isinstance(historical.get("by_asset"), dict) else {},
        "files": {
            "report": str(base / REPORT_NAME),
            "paper_unlock_shadow_rate_calibration": str(base / RATE_CALIBRATION_REPORT_NAME),
            "paper_unlock_shadow_dry_run": str(base / "paper_unlock_shadow_dry_run_report.json"),
            "paper_unlock_experiment_design": str(base / "paper_unlock_experiment_design_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_bounded_cadence_report(data_dir: str | Path = "data", settings: PaperUnlockBoundedCadenceSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_bounded_cadence_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "COLLECTION_NAME",
    "BoundedCadenceProfile",
    "PaperUnlockBoundedCadenceSettings",
    "build_paper_unlock_bounded_cadence_report",
    "write_paper_unlock_bounded_cadence_report",
]
