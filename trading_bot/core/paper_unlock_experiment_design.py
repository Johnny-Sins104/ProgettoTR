
"""Prompt 29.4.4d calibrated paper-only unlock experiment design.

This module converts the non-operational profile design from Prompt 29.4.4c
(``MAP_SCORE_65_79_REPAIRED_STABILITY_V1``) into a calibrated *paper-only
experiment design*.  It intentionally does not enable paper orders, open
positions, testnet, live trading, risk changes, or threshold changes.

The output is ``paper_unlock_experiment_design_report.json``.  Its role is to
make the next experiment auditable before any execution path is wired.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json

from config import Config
from core.calibrated_structure_shadow import _collect_historical_rows, _safe_float, _safe_int, _summarize_rows
from core.independent_repaired_validation import IndependentRepairedValidationSettings, _component_quality, _sort_rows, _target_map_score_65_79
from core.paper_unlock_profile_refinement import PROFILE_NAME, PaperUnlockProfileRefinementSettings
from core.repaired_structure_shadow_validation import _is_clean, _is_confirmation, _is_conflict, _is_entry_state, _is_no_structure, _is_wait
from core.structure_context_repair import repair_structure_rows

REPORT_NAME = "paper_unlock_experiment_design_report.json"
PROMPT_ID = "29.4.4d"
EXPERIMENT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN"
PROFILE_REPORT_NAME = "paper_unlock_profile_refinement_report.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaperUnlockExperimentDesignSettings:
    enabled: bool = True
    historical_enabled: bool = True
    focus_symbol: str = "BTC/USDT"
    focus_bucket: str = "BUY_BUY_REJECTION_CANDIDATE"
    max_rows_per_asset: int = 5000
    eval_stride: int = 3
    max_structure_candidates_per_asset: int = 220
    structure_window_rows: int = 900
    min_variant_candidates: int = 50
    min_component_candidates: int = 10
    min_fold_candidates: int = 10
    min_holdout_candidates: int = 15
    fold_count: int = 3
    holdout_fraction: float = 0.35
    min_expectancy_r: float = 0.10
    min_win_rate_pct: float = 52.0
    max_loss_rate_pct: float = 45.0
    max_time_exit_rate_pct: float = 60.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999
    profile_name: str = PROFILE_NAME
    experiment_name: str = EXPERIMENT_NAME
    proposed_max_positions: int = 1
    proposed_risk_per_trade_pct: float = 0.0025
    proposed_max_daily_entries: int = 1
    proposed_max_weekly_entries: int = 5
    proposed_runtime_shadow_min_candidates: int = 20
    proposed_min_runtime_expectancy_r: float = 0.05
    proposed_max_runtime_loss_rate_pct: float = 50.0
    proposed_abort_max_consecutive_losses: int = 3
    proposed_abort_max_drawdown_pct: float = 1.0
    require_profile_design_ready: bool = True

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockExperimentDesignSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_HISTORICAL_ENABLED", True)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_ROWS_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_EVAL_STRIDE", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_STRUCTURE_WINDOW_ROWS", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_VARIANT_CANDIDATES", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_component_candidates=max(3, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_COMPONENT_CANDIDATES", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_COMPONENT_CANDIDATES", 10)), 10)),
            min_fold_candidates=max(3, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_FOLD_CANDIDATES", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_FOLD_CANDIDATES", 10)), 10)),
            min_holdout_candidates=max(3, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_HOLDOUT_CANDIDATES", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_CANDIDATES", 15)), 15)),
            fold_count=max(2, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_FOLD_COUNT", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_FOLD_COUNT", 3)), 3)),
            holdout_fraction=min(0.80, max(0.10, _safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_HOLDOUT_FRACTION", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_HOLDOUT_FRACTION", 0.35)), 0.35))),
            min_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_EXPECTANCY_R", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_EXPECTANCY_R", 0.10)), 0.10),
            min_win_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_WIN_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_WIN_RATE_PCT", 52.0)), 52.0),
            max_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_LOSS_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_LOSS_RATE_PCT", 45.0)), 45.0),
            max_time_exit_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROFILE_NAME", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_PROFILE_NAME", PROFILE_NAME)) or PROFILE_NAME),
            experiment_name=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_EXPERIMENT_NAME", EXPERIMENT_NAME) or EXPERIMENT_NAME),
            proposed_max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_POSITIONS", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_MAX_POSITIONS", 1)), 1)),
            proposed_risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_RISK_PER_TRADE_PCT", getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_RISK_PER_TRADE_PCT", 0.0025)), 0.0025)),
            proposed_max_daily_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_DAILY_ENTRIES", 1), 1)),
            proposed_max_weekly_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_PROPOSED_MAX_WEEKLY_ENTRIES", 5), 5)),
            proposed_runtime_shadow_min_candidates=max(5, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_RUNTIME_SHADOW_MIN_CANDIDATES", 20), 20)),
            proposed_min_runtime_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MIN_RUNTIME_EXPECTANCY_R", 0.05), 0.05),
            proposed_max_runtime_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_MAX_RUNTIME_LOSS_RATE_PCT", 50.0), 50.0),
            proposed_abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_CONSECUTIVE_LOSSES", 3), 3)),
            proposed_abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_ABORT_MAX_DRAWDOWN_PCT", 1.0), 1.0)),
            require_profile_design_ready=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_DESIGN_REQUIRE_PROFILE_READY", True)),
        )

    def independent_settings(self) -> IndependentRepairedValidationSettings:
        return IndependentRepairedValidationSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            max_rows_per_asset=self.max_rows_per_asset,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            min_variant_candidates=self.min_variant_candidates,
            min_component_candidates=self.min_component_candidates,
            min_fold_candidates=self.min_fold_candidates,
            min_holdout_candidates=self.min_holdout_candidates,
            fold_count=self.fold_count,
            holdout_fraction=self.holdout_fraction,
            min_expectancy_r=self.min_expectancy_r,
            min_win_rate_pct=self.min_win_rate_pct,
            max_loss_rate_pct=self.max_loss_rate_pct,
            max_time_exit_rate_pct=self.max_time_exit_rate_pct,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
        )

    def calibrated_settings(self):
        # Reuse the 29.4.4c settings object because collection uses its
        # calibrated_structure_shadow settings adapter.
        return PaperUnlockProfileRefinementSettings(
            enabled=self.enabled,
            historical_enabled=self.historical_enabled,
            focus_symbol=self.focus_symbol,
            focus_bucket=self.focus_bucket,
            max_rows_per_asset=self.max_rows_per_asset,
            eval_stride=self.eval_stride,
            max_structure_candidates_per_asset=self.max_structure_candidates_per_asset,
            structure_window_rows=self.structure_window_rows,
            min_variant_candidates=self.min_variant_candidates,
            min_component_candidates=self.min_component_candidates,
            min_fold_candidates=self.min_fold_candidates,
            min_holdout_candidates=self.min_holdout_candidates,
            fold_count=self.fold_count,
            holdout_fraction=self.holdout_fraction,
            min_expectancy_r=self.min_expectancy_r,
            min_win_rate_pct=self.min_win_rate_pct,
            max_loss_rate_pct=self.max_loss_rate_pct,
            max_time_exit_rate_pct=self.max_time_exit_rate_pct,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
            proposed_profile_name=self.profile_name,
            proposed_max_positions=self.proposed_max_positions,
            proposed_risk_per_trade_pct=self.proposed_risk_per_trade_pct,
        ).independent_settings().calibrated_settings()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {"status": "READ_ERROR", "error": str(exc)}


def _profile_design_guard(profile_report: dict[str, Any]) -> dict[str, Any]:
    if not profile_report:
        return {
            "profile_design_ready": False,
            "profile_report_status": "MISSING",
            "profile_decision_status": "MISSING",
            "reason": "paper_unlock_profile_refinement_report.json is missing",
        }
    decision = profile_report.get("decision", {}) if isinstance(profile_report.get("decision"), dict) else {}
    source = profile_report.get("source_validation", {}) if isinstance(profile_report.get("source_validation"), dict) else {}
    status = str(profile_report.get("status") or "NA")
    decision_status = str(decision.get("status") or "NA")
    ready = bool(
        status == "PASS"
        and decision_status == "PROFILE_REFINEMENT_DESIGN_READY_DIAGNOSTIC"
        and bool(source.get("independent_guard_ok", False))
        and not bool(decision.get("operational_unlock_allowed", False))
        and not bool(decision.get("paper_unlock_experiment_allowed", False))
    )
    return {
        "profile_design_ready": ready,
        "profile_report_status": status,
        "profile_decision_status": decision_status,
        "profile_name": decision.get("profile_name", ""),
        "independent_guard_ok": bool(source.get("independent_guard_ok", False)),
        "source_validation": source,
        "reason": "profile design guard passed" if ready else "profile design guard did not pass or profile attempted to enable execution",
    }


def _experiment_gate(summary: dict[str, Any], settings: PaperUnlockExperimentDesignSettings, *, allowed_state: bool) -> dict[str, Any]:
    candidates = _safe_int(summary.get("candidates"), 0)
    expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
    win = _safe_float(summary.get("win_rate_pct"), 0.0)
    loss = _safe_float(summary.get("loss_rate_pct"), 100.0)
    time_exit = _safe_float(summary.get("time_exit_rate_pct"), 100.0)
    checks = {
        "allowed_state": bool(allowed_state),
        "sample_ok": candidates >= settings.min_variant_candidates,
        "expectancy_ok": expectancy >= settings.min_expectancy_r,
        "win_rate_ok": win >= settings.min_win_rate_pct,
        "loss_rate_ok": loss <= settings.max_loss_rate_pct,
        "time_exit_ok": time_exit <= settings.max_time_exit_rate_pct,
        "min_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
    }
    checks["passes_experiment_design_gate"] = bool(
        checks["allowed_state"]
        and checks["sample_ok"]
        and checks["expectancy_ok"]
        and checks["win_rate_ok"]
        and checks["loss_rate_ok"]
        and checks["time_exit_ok"]
    )
    return checks


def _summary_with_gate(rows: list[dict[str, Any]], settings: PaperUnlockExperimentDesignSettings, *, allowed_state: bool) -> dict[str, Any]:
    summary = _summarize_rows(rows)
    summary["gate_checks"] = _experiment_gate(summary, settings, allowed_state=allowed_state)
    summary["passes_experiment_design_gate"] = bool(summary["gate_checks"].get("passes_experiment_design_gate"))
    return summary


def _variant(name: str, rows: list[dict[str, Any]], fn: Callable[[dict[str, Any]], bool], settings: PaperUnlockExperimentDesignSettings, description: str, *, allowed_state: bool) -> dict[str, Any]:
    selected = [r for r in rows if fn(r)]
    return {
        "name": name,
        "description": description,
        "allowed_for_future_paper_experiment": bool(allowed_state),
        **_summary_with_gate(selected, settings, allowed_state=allowed_state),
    }


def _target_rows(rows: list[dict[str, Any]], settings: PaperUnlockExperimentDesignSettings) -> list[dict[str, Any]]:
    ist = settings.independent_settings()
    return [r for r in rows if _target_map_score_65_79(r, ist)]


def _experiment_variants(rows: list[dict[str, Any]], target: list[dict[str, Any]], settings: PaperUnlockExperimentDesignSettings) -> list[dict[str, Any]]:
    return sorted([
        _variant("experiment_source_map_score_65_79", rows, lambda r: r in target, settings, "Source profile rows from 29.4.4c/29.5.0j. Used only to design the experiment.", allowed_state=True),
        _variant("experiment_entry_state_only", target, _is_entry_state, settings, "Future paper-only experiment selector: repaired CONTEXT or CONFIRMATION only.", allowed_state=True),
        _variant("experiment_clean_entry_state", target, lambda r: _is_entry_state(r) and _is_clean(r), settings, "Entry-state selector plus clean pattern/range diagnostics.", allowed_state=True),
        _variant("experiment_confirmation_only", target, _is_confirmation, settings, "Hard repaired confirmation only; audited but not required by source candidate.", allowed_state=True),
        _variant("experiment_bos_only", target, lambda r: "BOS" in str(r.get("confirmation_summary") or "").upper(), settings, "BOS-only subset of the source candidate.", allowed_state=True),
        _variant("blocked_wait_watchlist", target, _is_wait, settings, "WAIT rows remain watchlist-only and cannot enter the paper experiment.", allowed_state=False),
        _variant("blocked_no_structure", target, _is_no_structure, settings, "NO_STRUCTURE rows remain blocked.", allowed_state=False),
        _variant("blocked_conflict", target, _is_conflict, settings, "CONFLICT rows remain blocked.", allowed_state=False),
    ], key=lambda v: (bool(v.get("passes_experiment_design_gate")), _safe_float(v.get("expectancy_r"), 0.0), _safe_float(v.get("win_rate_pct"), 0.0), _safe_int(v.get("candidates"), 0)), reverse=True)


def _allowed_symbols(target: list[dict[str, Any]]) -> list[str]:
    return sorted({str(r.get("symbol") or "").upper() for r in target if str(r.get("symbol") or "").strip()})


def _allowed_sides(target: list[dict[str, Any]]) -> list[str]:
    return sorted({str(r.get("side") or "").upper() for r in target if str(r.get("side") or "").strip()})


def _experiment_plan(target: list[dict[str, Any]], settings: PaperUnlockExperimentDesignSettings, profile_guard: dict[str, Any]) -> dict[str, Any]:
    return {
        "experiment_name": settings.experiment_name,
        "experiment_status": "DESIGN_ONLY_NOT_ENABLED",
        "profile_name": settings.profile_name,
        "source_patch": "29.4.4c",
        "source_profile_ready": bool(profile_guard.get("profile_design_ready", False)),
        "scope": {
            "mode": "paper_only_future_patch",
            "allowed_symbols_from_validation": _allowed_symbols(target),
            "allowed_sides_from_validation": _allowed_sides(target),
            "timeframe": "5m",
            "requires_existing_strategy_signal": True,
            "requires_repaired_structure_layer": True,
            "map_score_min_inclusive": settings.map_score_candidate_min,
            "map_score_max_inclusive": settings.map_score_candidate_max,
            "allowed_structure_states": ["CONTEXT", "CONFIRMATION"],
            "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
        },
        "risk_design": {
            "max_positions": settings.proposed_max_positions,
            "risk_per_trade_pct": settings.proposed_risk_per_trade_pct,
            "max_daily_entries": settings.proposed_max_daily_entries,
            "max_weekly_entries": settings.proposed_max_weekly_entries,
            "live_block": True,
            "testnet_block": True,
            "orders_enabled_in_this_patch": False,
            "position_opening_enabled_in_this_patch": False,
        },
        "runtime_shadow_prerequisites_for_future_activation": {
            "min_runtime_shadow_candidates": settings.proposed_runtime_shadow_min_candidates,
            "min_runtime_expectancy_r": settings.proposed_min_runtime_expectancy_r,
            "max_runtime_loss_rate_pct": settings.proposed_max_runtime_loss_rate_pct,
            "requires_manual_user_approval": True,
            "requires_separate_patch": True,
        },
        "abort_criteria_for_future_experiment": {
            "max_consecutive_losses": settings.proposed_abort_max_consecutive_losses,
            "max_drawdown_pct": settings.proposed_abort_max_drawdown_pct,
            "abort_on_any_live_or_testnet_mode": True,
            "abort_on_missing_repaired_structure": True,
            "abort_on_wait_no_structure_or_conflict_entry": True,
        },
    }


def _component_audit(target: list[dict[str, Any]], settings: PaperUnlockExperimentDesignSettings) -> dict[str, Any]:
    ist = settings.independent_settings()
    return {
        "target_by_asset": _component_quality(target, lambda r: str(r.get("symbol") or "NA"), ist, min_candidates=3),
        "target_by_side": _component_quality(target, lambda r: str(r.get("side") or "NA"), ist, min_candidates=3),
        "target_by_asset_side": _component_quality(target, lambda r: f"{r.get('symbol') or 'NA'}:{r.get('side') or 'NA'}", ist, min_candidates=3),
        "target_by_state": _component_quality(target, lambda r: str(r.get("structure_state") or "NA"), ist, min_candidates=3),
        "target_by_confirmation_summary": _component_quality(target, lambda r: str(r.get("confirmation_summary") or "NA"), ist, min_candidates=3),
        "target_by_price_location": _component_quality(target, lambda r: str(r.get("price_location") or "NA"), ist, min_candidates=3),
    }


def _fallback_from_profile(profile_report: dict[str, Any]) -> dict[str, Any]:
    if not profile_report:
        return {"available": False}
    decision = profile_report.get("decision", {}) if isinstance(profile_report.get("decision"), dict) else {}
    best = decision.get("best_profile_design_variant", {}) if isinstance(decision.get("best_profile_design_variant"), dict) else {}
    return {
        "available": True,
        "source": PROFILE_REPORT_NAME,
        "profile_report_status": profile_report.get("status"),
        "profile_decision_status": decision.get("status"),
        "profile_name": decision.get("profile_name"),
        "best_profile_design_variant": best,
        "counts": profile_report.get("counts", {}) if isinstance(profile_report.get("counts"), dict) else {},
    }


def _decision(profile_guard: dict[str, Any], source_summary: dict[str, Any], variants: list[dict[str, Any]], fallback: dict[str, Any], settings: PaperUnlockExperimentDesignSettings) -> dict[str, Any]:
    source_gate = bool((source_summary.get("gate_checks") or {}).get("passes_experiment_design_gate"))
    best_allowed = next((v for v in variants if v.get("allowed_for_future_paper_experiment") and v.get("passes_experiment_design_gate")), {})
    fallback_best = fallback.get("best_profile_design_variant", {}) if isinstance(fallback.get("best_profile_design_variant"), dict) else {}
    fallback_gate = bool(fallback_best.get("passes_profile_design_gate") or (fallback_best.get("gate_checks") or {}).get("passes_profile_design_gate")) if isinstance(fallback_best, dict) else False
    ready = bool(profile_guard.get("profile_design_ready") and (source_gate or fallback_gate))
    if settings.require_profile_design_ready and not profile_guard.get("profile_design_ready"):
        ready = False
    if ready:
        return {
            "status": "PAPER_EXPERIMENT_DESIGN_READY_DIAGNOSTIC",
            "reason": "29.4.4c profile design is ready; a calibrated paper-only experiment plan can be drafted, but this patch keeps all execution disabled.",
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "best_experiment_design_variant": best_allowed or source_summary or fallback_best,
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "profile_activation_allowed": False,
            "paper_orders_enabled": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "29.4.4e paper-only shadow experiment dry-run harness, still no live/testnet and only if user explicitly proceeds.",
        }
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "Paper experiment design is blocked because profile readiness or source candidate gates are not satisfied.",
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "best_experiment_design_variant": best_allowed or source_summary or fallback_best,
        "profile_guard": profile_guard,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "profile_activation_allowed": False,
        "paper_orders_enabled": False,
        "orders_submitted": 0,
        "positions_opened": 0,
        "next_patch": "Re-run 29.4.4c/29.5.0j until profile design is ready; do not start paper experiment.",
    }


def _settings_payload(settings: PaperUnlockExperimentDesignSettings) -> dict[str, Any]:
    return {
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
        "proposed_max_positions": settings.proposed_max_positions,
        "proposed_risk_per_trade_pct": settings.proposed_risk_per_trade_pct,
        "proposed_max_daily_entries": settings.proposed_max_daily_entries,
        "proposed_max_weekly_entries": settings.proposed_max_weekly_entries,
        "proposed_runtime_shadow_min_candidates": settings.proposed_runtime_shadow_min_candidates,
        "require_profile_design_ready": settings.require_profile_design_ready,
    }


def build_paper_unlock_experiment_design_report(data_dir: str | Path = "data", settings: PaperUnlockExperimentDesignSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or PaperUnlockExperimentDesignSettings.from_config()
    profile_report = _read_json(base / PROFILE_REPORT_NAME)
    profile_guard = _profile_design_guard(profile_report)
    if not settings.enabled:
        historical = {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
        rows: list[dict[str, Any]] = []
    else:
        historical = _collect_historical_rows(base, settings.calibrated_settings())
        rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
    target = _target_rows(rows, settings) if rows else []
    fallback = _fallback_from_profile(profile_report) if not target else {"available": False}
    source_summary = _summary_with_gate(target, settings, allowed_state=True)
    source_summary["name"] = "experiment_source_map_score_65_79"
    source_summary["description"] = "29.4.4d source paper-experiment profile selector; design-only, not active."
    variants = _experiment_variants(rows, target, settings) if rows else []
    component_audit = _component_audit(target, settings) if target else {}
    plan = _experiment_plan(target, settings, profile_guard)
    decision = _decision(profile_guard, source_summary, variants, fallback, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "PAPER_EXPERIMENT_DESIGN_READY_DIAGNOSTIC" else "WARN")
    report = {
        "report_type": "calibrated_paper_only_unlock_experiment_design",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "profile_guard": profile_guard,
        "experiment_plan": plan,
        "source_summary": source_summary,
        "experiment_variants": variants,
        "experiment_variants_top": variants[:8],
        "component_audit": component_audit,
        "fallback": fallback,
        "historical_summary": _summarize_rows(rows) if rows else {},
        "settings": _settings_payload(settings),
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "profile_activation_allowed": False,
        "paper_orders_enabled": False,
        "counts": {
            "scenario_pattern_evaluation_rows": _safe_int(historical.get("scenario_pattern_evaluation_rows"), 0),
            "candidate_rows_pre_structure": _safe_int(historical.get("candidate_rows_pre_structure"), 0),
            "structured_candidate_rows": len(rows),
            "target_candidate_rows": len(target) if target else _safe_int((fallback.get("counts") or {}).get("target_candidate_rows"), 0) if isinstance(fallback.get("counts"), dict) else 0,
            "experiment_variants": len(variants),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "by_asset": historical.get("by_asset", {}) if isinstance(historical.get("by_asset"), dict) else {},
        "recent_target_rows": [
            {
                "datetime": r.get("datetime"),
                "symbol": r.get("symbol"),
                "side": r.get("side"),
                "bucket": r.get("bucket"),
                "map_score": r.get("map_score"),
                "structure_state": r.get("structure_state"),
                "confirmation_summary": r.get("confirmation_summary"),
                "price_location": r.get("price_location"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
            }
            for r in _sort_rows(target)[-20:]
        ] if target else [],
        "files": {
            "report": str(base / REPORT_NAME),
            "paper_unlock_profile_refinement": str(base / PROFILE_REPORT_NAME),
            "independent_repaired_validation": str(base / "independent_repaired_validation_report.json"),
            "repaired_structure_shadow_validation": str(base / "repaired_structure_shadow_validation_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_experiment_design_report(data_dir: str | Path = "data", settings: PaperUnlockExperimentDesignSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_experiment_design_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "EXPERIMENT_NAME",
    "PaperUnlockExperimentDesignSettings",
    "build_paper_unlock_experiment_design_report",
    "write_paper_unlock_experiment_design_report",
]
