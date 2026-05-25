"""Prompt 29.4.4f shadow dry-run sample expansion / rate-limit calibration.

This module is a diagnostic-only follow-up to Prompt 29.4.4e.  The 29.4.4e
shadow harness validated the mechanics, but the conservative daily/weekly rate
limits selected too few entries for readiness.  This module compares multiple
shadow-only rate-limit profiles against the same MAP_SCORE_65_79 repaired
candidate set.

Safety invariant: no orders, no live, no testnet, no paper experiment
activation, and no threshold/risk mutation.  Even a passing calibration only
means that a future patch may draft a guarded paper-only activation; execution
remains disabled here.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from config import Config
from core.calibrated_structure_shadow import _collect_historical_rows, _safe_float, _safe_int, _summarize_rows
from core.paper_unlock_shadow_dry_run import (
    HARNESS_NAME as DRY_RUN_HARNESS_NAME,
    REPORT_NAME as SHADOW_DRY_RUN_REPORT_NAME,
    PaperUnlockShadowDryRunSettings,
    _dry_run_gate,
    _dry_run_select,
    _equity_curve,
    _entry_candidate_rows,
    _experiment_design_guard,
    _read_json,
    _target_rows,
)
from core.structure_context_repair import repair_structure_rows

REPORT_NAME = "paper_unlock_shadow_rate_calibration_report.json"
PROMPT_ID = "29.4.4f"
CALIBRATION_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_RATE_CALIBRATION"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RateLimitProfile:
    name: str
    max_daily_entries: int
    max_weekly_entries: int
    description: str


@dataclass(frozen=True)
class PaperUnlockShadowRateCalibrationSettings:
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
    calibration_name: str = CALIBRATION_NAME
    require_rate_limited_profile: bool = True

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockShadowRateCalibrationSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_HISTORICAL_ENABLED", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_HISTORICAL_ENABLED", True))),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_ROWS_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_EVAL_STRIDE", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_STRUCTURE_WINDOW_ROWS", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_VARIANT_CANDIDATES", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_shadow_entries=max(5, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_ENTRIES", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_ENTRIES", 20)), 20)),
            min_shadow_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MIN_EXPECTANCY_R", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MIN_EXPECTANCY_R", 0.05)), 0.05),
            max_shadow_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_LOSS_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_LOSS_RATE_PCT", 50.0)), 50.0),
            max_shadow_time_exit_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
            dry_run_risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_RISK_PER_TRADE_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_RISK_PER_TRADE_PCT", 0.0025)), 0.0025)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_CONSECUTIVE_LOSSES", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_CONSECUTIVE_LOSSES", 3)), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ABORT_MAX_DRAWDOWN_PCT", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_ABORT_MAX_DRAWDOWN_PCT", 1.0)), 1.0)),
            require_experiment_design_ready=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_EXPERIMENT_READY", getattr(cfg, "PAPER_UNLOCK_SHADOW_DRY_RUN_REQUIRE_EXPERIMENT_READY", True))),
            calibration_name=str(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_NAME", CALIBRATION_NAME) or CALIBRATION_NAME),
            require_rate_limited_profile=bool(getattr(cfg, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_REQUIRE_RATE_LIMITED_PROFILE", True)),
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


def _rate_profiles(settings: PaperUnlockShadowRateCalibrationSettings) -> list[RateLimitProfile]:
    # The first profile mirrors 29.4.4e. Later profiles expand sampling while
    # still retaining explicit daily/weekly caps. The final all-shadow profile is
    # a diagnostic ceiling, never a recommended activation profile by itself.
    return [
        RateLimitProfile("current_1_daily_5_weekly", 1, 5, "Original 29.4.4e conservative shadow cadence."),
        RateLimitProfile("weekly_relaxed_1_daily_10_weekly", 1, 10, "Keep one entry per day but reduce weekly under-sampling."),
        RateLimitProfile("balanced_2_daily_10_weekly", 2, 10, "Moderate expansion for runtime paper shadow sampling."),
        RateLimitProfile("expanded_3_daily_15_weekly", 3, 15, "Expanded diagnostic cadence with still bounded weekly exposure."),
        RateLimitProfile("sample_expanded_4_daily_20_weekly", 4, 20, "Sample-expansion cadence intended to reach the minimum shadow sample."),
        RateLimitProfile("all_shadow_ceiling_99_daily_99_weekly", 99, 99, "Diagnostic ceiling; measures all eligible shadow entries, not an activation cadence."),
    ]


def _variant_record(profile: RateLimitProfile, rows: list[dict[str, Any]], guard: dict[str, Any], settings: PaperUnlockShadowRateCalibrationSettings) -> dict[str, Any]:
    dry_settings = settings.dry_run_settings(profile.max_daily_entries, profile.max_weekly_entries)
    selected, rejected, limit_summary = _dry_run_select(rows, dry_settings)
    summary = _summarize_rows(selected) if selected else {}
    equity = _equity_curve(selected, dry_settings)
    gate = _dry_run_gate(summary, equity, guard, dry_settings)
    # The all-shadow ceiling is intentionally not a directly deployable rate-limit profile.
    rate_limited_profile = profile.max_daily_entries < 99 and profile.max_weekly_entries < 99
    deployable_candidate = bool(gate.get("passes_shadow_dry_run_gate") and rate_limited_profile)
    return {
        "name": profile.name,
        "description": profile.description,
        "max_daily_entries": profile.max_daily_entries,
        "max_weekly_entries": profile.max_weekly_entries,
        "rate_limited_profile": rate_limited_profile,
        "deployable_rate_candidate": deployable_candidate,
        "selected_entries": len(selected),
        "rate_limited_rejections": len(rejected),
        "summary": summary,
        "equity_dry_run": equity,
        "gate": gate,
        "rate_limit_summary": limit_summary,
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
            for r in selected[-20:]
        ],
    }


def _score_variant(v: dict[str, Any]) -> tuple[int, int, float, int, float, int]:
    gate = v.get("gate", {}) if isinstance(v.get("gate"), dict) else {}
    summary = v.get("summary", {}) if isinstance(v.get("summary"), dict) else {}
    equity = v.get("equity_dry_run", {}) if isinstance(v.get("equity_dry_run"), dict) else {}
    return (
        1 if bool(v.get("deployable_rate_candidate")) else 0,
        1 if bool(gate.get("passes_shadow_dry_run_gate")) else 0,
        _safe_float(summary.get("expectancy_r"), 0.0),
        _safe_int(v.get("selected_entries"), 0),
        -_safe_float(summary.get("loss_rate_pct"), 100.0),
        -_safe_int(equity.get("max_consecutive_losses"), 999),
    )


def _decision(guard: dict[str, Any], best: dict[str, Any], variants: list[dict[str, Any]], settings: PaperUnlockShadowRateCalibrationSettings) -> dict[str, Any]:
    if settings.require_experiment_design_ready and not bool(guard.get("experiment_design_ready")):
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "29.4.4d experiment design guard is not ready; rate-limit calibration cannot advance.",
            "best_rate_variant": best,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "Repair 29.4.4d/29.4.4e prerequisites before any paper experiment activation.",
        }
    deployable = [v for v in variants if bool(v.get("deployable_rate_candidate"))]
    ceiling_only = bool(best.get("gate", {}).get("passes_shadow_dry_run_gate")) and not bool(best.get("rate_limited_profile"))
    if deployable:
        return {
            "status": "SHADOW_RATE_CALIBRATION_READY_DIAGNOSTIC",
            "reason": "At least one bounded rate-limit profile reached the minimum shadow sample and passed expectancy/loss/time-exit/abort guards. Execution remains disabled pending a separate guarded paper-only activation draft.",
            "best_rate_variant": best,
            "deployable_rate_variants": [v.get("name") for v in deployable],
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "29.4.4g guarded paper-only experiment activation draft, still no live/testnet and only after explicit user approval.",
        }
    if ceiling_only:
        return {
            "status": "KEEP_DIAGNOSTIC",
            "reason": "Only the unbounded all-shadow ceiling passed; no bounded rate-limit profile is ready for a paper experiment draft.",
            "best_rate_variant": best,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "Collect more shadow observations or test additional bounded cadence profiles before activation.",
        }
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "No expanded shadow rate-limit profile passed sample/expectancy/loss/time-exit/abort guards.",
        "best_rate_variant": best,
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
        "orders_submitted": 0,
        "positions_opened": 0,
        "next_patch": "Repair dry-run guard failures or keep collecting diagnostic shadow rows before any activation.",
    }


def _settings_payload(settings: PaperUnlockShadowRateCalibrationSettings) -> dict[str, Any]:
    return {
        "calibration_name": settings.calibration_name,
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
        "require_rate_limited_profile": settings.require_rate_limited_profile,
    }


def build_paper_unlock_shadow_rate_calibration_report(data_dir: str | Path = "data", settings: PaperUnlockShadowRateCalibrationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or PaperUnlockShadowRateCalibrationSettings.from_config()
    baseline_settings = settings.dry_run_settings()
    experiment_report = _read_json(base / "paper_unlock_experiment_design_report.json")
    guard = _experiment_design_guard(experiment_report, baseline_settings)
    if not settings.enabled:
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
        repaired_rows: list[dict[str, Any]] = []
    else:
        historical = _collect_historical_rows(base, baseline_settings.calibrated_settings())
        repaired_rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
    target_all = _target_rows(repaired_rows, baseline_settings) if repaired_rows else []
    target_entry = _entry_candidate_rows(target_all)
    variants = [_variant_record(profile, target_entry, guard, settings) for profile in _rate_profiles(settings)]
    variants = sorted(variants, key=_score_variant, reverse=True)
    best = variants[0] if variants else {}
    decision = _decision(guard, best, variants, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "SHADOW_RATE_CALIBRATION_READY_DIAGNOSTIC" else "WARN")
    report = {
        "report_type": "paper_only_shadow_rate_limit_calibration",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "calibration_name": settings.calibration_name,
        "experiment_design_guard": guard,
        "source_target_summary": _summarize_rows(target_all) if target_all else {},
        "entry_candidate_summary": _summarize_rows(target_entry) if target_entry else {},
        "rate_limit_variants": variants,
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
            "rate_limit_variants": len(variants),
            "best_selected_entries": _safe_int(best.get("selected_entries"), 0) if best else 0,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "by_asset": historical.get("by_asset", {}) if isinstance(historical.get("by_asset"), dict) else {},
        "files": {
            "report": str(base / REPORT_NAME),
            "paper_unlock_shadow_dry_run": str(base / SHADOW_DRY_RUN_REPORT_NAME),
            "paper_unlock_experiment_design": str(base / "paper_unlock_experiment_design_report.json"),
            "paper_unlock_profile_refinement": str(base / "paper_unlock_profile_refinement_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_shadow_rate_calibration_report(data_dir: str | Path = "data", settings: PaperUnlockShadowRateCalibrationSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_shadow_rate_calibration_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "CALIBRATION_NAME",
    "PaperUnlockShadowRateCalibrationSettings",
    "build_paper_unlock_shadow_rate_calibration_report",
    "write_paper_unlock_shadow_rate_calibration_report",
]
