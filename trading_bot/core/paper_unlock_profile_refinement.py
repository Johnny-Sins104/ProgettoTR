"""Prompt 29.4.4c paper unlock profile refinement design.

Diagnostic-only design layer after Prompt 29.5.0j.

29.5.0j promoted ``map_score_65_79_all`` to a non-operational stability
candidate.  This module turns that result into a *paper-only profile design*
that a later patch can test.  It does not enable the profile, submit paper
orders, open positions, lower thresholds, enable testnet, or change live risk.

The output is ``paper_unlock_profile_refinement_report.json``.  Its purpose is
to define the candidate profile, profile constraints, blocked states and next
patch criteria before any paper-only unlock experiment is attempted.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import math

from config import Config
from core.calibrated_structure_shadow import _collect_historical_rows, _safe_float, _safe_int, _summarize_rows
from core.independent_repaired_validation import (
    IndependentRepairedValidationSettings,
    _component_quality,
    _concentration,
    _sort_rows,
    _target_map_score_65_79,
    _walk_forward,
)
from core.repaired_structure_shadow_validation import (
    _is_clean,
    _is_confirmation,
    _is_conflict,
    _is_entry_state,
    _is_no_structure,
    _is_wait,
)
from core.structure_context_repair import repair_structure_rows

REPORT_NAME = "paper_unlock_profile_refinement_report.json"
PROMPT_ID = "29.4.4c"
PROFILE_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"
SOURCE_STABILITY_VARIANT = "map_score_65_79_all"


@dataclass(frozen=True)
class PaperUnlockProfileRefinementSettings:
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
    min_holdout_expectancy_r: float = 0.05
    min_holdout_win_rate_pct: float = 52.0
    max_holdout_loss_rate_pct: float = 45.0
    min_positive_fold_rate_pct: float = 66.67
    max_asset_concentration_pct: float = 70.0
    max_side_concentration_pct: float = 80.0
    map_score_candidate_min: float = 65.0
    map_score_candidate_max: float = 79.999
    proposed_profile_name: str = PROFILE_NAME
    proposed_max_positions: int = 1
    proposed_risk_per_trade_pct: float = 0.0025
    require_independent_stability_candidate: bool = True

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockProfileRefinementSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_ENABLED", True)),
            historical_enabled=bool(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_HISTORICAL_ENABLED", True)),
            focus_symbol=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_SYMBOL", "BTC/USDT") or "BTC/USDT").upper(),
            focus_bucket=str(getattr(cfg, "SCENARIO_PATTERN_FOCUS_BUCKET", "BUY_BUY_REJECTION_CANDIDATE") or "BUY_BUY_REJECTION_CANDIDATE").upper(),
            max_rows_per_asset=max(500, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ROWS_PER_ASSET", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_ROWS_PER_ASSET", 5000)), 5000)),
            eval_stride=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_EVAL_STRIDE", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_EVAL_STRIDE", 3)), 3)),
            max_structure_candidates_per_asset=max(20, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_STRUCTURE_CANDIDATES_PER_ASSET", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_STRUCTURE_CANDIDATES_PER_ASSET", 220)), 220)),
            structure_window_rows=max(120, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_STRUCTURE_WINDOW_ROWS", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_STRUCTURE_WINDOW_ROWS", 900)), 900)),
            min_variant_candidates=max(10, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_VARIANT_CANDIDATES", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_VARIANT_CANDIDATES", 50)), 50)),
            min_component_candidates=max(3, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_COMPONENT_CANDIDATES", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_COMPONENT_CANDIDATES", 10)), 10)),
            min_fold_candidates=max(3, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_FOLD_CANDIDATES", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_FOLD_CANDIDATES", 10)), 10)),
            min_holdout_candidates=max(3, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_CANDIDATES", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_CANDIDATES", 15)), 15)),
            fold_count=max(2, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_FOLD_COUNT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_FOLD_COUNT", 3)), 3)),
            holdout_fraction=min(0.80, max(0.10, _safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_HOLDOUT_FRACTION", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_HOLDOUT_FRACTION", 0.35)), 0.35))),
            min_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_EXPECTANCY_R", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_EXPECTANCY_R", 0.10)), 0.10),
            min_win_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_WIN_RATE_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_WIN_RATE_PCT", 52.0)), 52.0),
            max_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_LOSS_RATE_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_LOSS_RATE_PCT", 45.0)), 45.0),
            max_time_exit_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_TIME_EXIT_RATE_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_TIME_EXIT_RATE_PCT", 60.0)), 60.0),
            min_holdout_expectancy_r=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_EXPECTANCY_R", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_EXPECTANCY_R", 0.05)), 0.05),
            min_holdout_win_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_HOLDOUT_WIN_RATE_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_HOLDOUT_WIN_RATE_PCT", 52.0)), 52.0),
            max_holdout_loss_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_HOLDOUT_LOSS_RATE_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_HOLDOUT_LOSS_RATE_PCT", 45.0)), 45.0),
            min_positive_fold_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MIN_POSITIVE_FOLD_RATE_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MIN_POSITIVE_FOLD_RATE_PCT", 66.67)), 66.67),
            max_asset_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_ASSET_CONCENTRATION_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_ASSET_CONCENTRATION_PCT", 70.0)), 70.0),
            max_side_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAX_SIDE_CONCENTRATION_PCT", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAX_SIDE_CONCENTRATION_PCT", 80.0)), 80.0),
            map_score_candidate_min=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MIN", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MIN", 65.0)), 65.0),
            map_score_candidate_max=_safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_MAP_SCORE_CANDIDATE_MAX", getattr(cfg, "INDEPENDENT_REPAIRED_VALIDATION_MAP_SCORE_CANDIDATE_MAX", 79.999)), 79.999),
            proposed_profile_name=str(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            proposed_max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_MAX_POSITIONS", 1), 1)),
            proposed_risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_PROPOSED_RISK_PER_TRADE_PCT", 0.0025), 0.0025)),
            require_independent_stability_candidate=bool(getattr(cfg, "PAPER_UNLOCK_PROFILE_REFINEMENT_REQUIRE_STABILITY_CANDIDATE", True)),
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
            min_holdout_expectancy_r=self.min_holdout_expectancy_r,
            min_holdout_win_rate_pct=self.min_holdout_win_rate_pct,
            max_holdout_loss_rate_pct=self.max_holdout_loss_rate_pct,
            min_positive_fold_rate_pct=self.min_positive_fold_rate_pct,
            max_asset_concentration_pct=self.max_asset_concentration_pct,
            max_side_concentration_pct=self.max_side_concentration_pct,
            map_score_candidate_min=self.map_score_candidate_min,
            map_score_candidate_max=self.map_score_candidate_max,
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_upper(value: Any) -> str:
    return str(value or "").upper()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _load_independent_report(base: Path) -> dict[str, Any]:
    return _load_json(base / "independent_repaired_validation_report.json")


def _independent_guard_ok(payload: dict[str, Any]) -> bool:
    decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
    return bool(
        payload.get("status") == "PASS"
        and decision.get("status") == "STABILITY_CANDIDATE_DIAGNOSTIC"
        and decision.get("paper_unlock_refinement_candidate", True) is not False
        and decision.get("operational_unlock_allowed") is False
    )


def _collect_repaired_rows(base: Path, settings: PaperUnlockProfileRefinementSettings) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    independent_settings = settings.independent_settings()
    if not settings.enabled:
        return [], {"status": "DISABLED", "candidate_rows": [], "warnings": [], "by_asset": {}}
    historical = _collect_historical_rows(base, independent_settings.calibrated_settings())
    rows = repair_structure_rows(list(historical.get("candidate_rows") or []))
    return rows, historical


def _target_rows(rows: list[dict[str, Any]], settings: PaperUnlockProfileRefinementSettings) -> list[dict[str, Any]]:
    independent_settings = settings.independent_settings()
    return [r for r in rows if _target_map_score_65_79(r, independent_settings)]


def _profile_gate(summary: dict[str, Any], settings: PaperUnlockProfileRefinementSettings, *, entry_candidate_allowed: bool) -> dict[str, Any]:
    candidates = _safe_int(summary.get("candidates"), 0)
    expectancy = _safe_float(summary.get("expectancy_r"), 0.0)
    win = _safe_float(summary.get("win_rate_pct"), 0.0)
    loss = _safe_float(summary.get("loss_rate_pct"), 0.0)
    time_exit = _safe_float(summary.get("time_exit_rate_pct"), 0.0)
    checks = {
        "sample_ok": candidates >= settings.min_variant_candidates,
        "expectancy_ok": expectancy >= settings.min_expectancy_r,
        "win_rate_ok": win >= settings.min_win_rate_pct,
        "loss_rate_ok": loss <= settings.max_loss_rate_pct,
        "time_exit_ok": time_exit <= settings.max_time_exit_rate_pct,
        "entry_candidate_allowed": bool(entry_candidate_allowed),
        "min_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
    }
    checks["passes_profile_design_gate"] = bool(
        checks["entry_candidate_allowed"]
        and checks["sample_ok"]
        and checks["expectancy_ok"]
        and checks["win_rate_ok"]
        and checks["loss_rate_ok"]
        and checks["time_exit_ok"]
    )
    return checks


def _summary_with_gate(rows: list[dict[str, Any]], settings: PaperUnlockProfileRefinementSettings, *, entry_candidate_allowed: bool) -> dict[str, Any]:
    summary = _summarize_rows(rows)
    summary["gate_checks"] = _profile_gate(summary, settings, entry_candidate_allowed=entry_candidate_allowed)
    summary["passes_profile_design_gate"] = bool(summary["gate_checks"].get("passes_profile_design_gate"))
    return summary


def _variant(name: str, rows: list[dict[str, Any]], fn: Callable[[dict[str, Any]], bool], settings: PaperUnlockProfileRefinementSettings, description: str, *, entry_candidate_allowed: bool) -> dict[str, Any]:
    selected = [r for r in rows if fn(r)]
    return {
        "name": name,
        "description": description,
        "entry_candidate_allowed": bool(entry_candidate_allowed),
        **_summary_with_gate(selected, settings, entry_candidate_allowed=entry_candidate_allowed),
    }


def _profile_variants(rows: list[dict[str, Any]], target: list[dict[str, Any]], settings: PaperUnlockProfileRefinementSettings) -> list[dict[str, Any]]:
    return sorted([
        _variant("source_map_score_65_79_all", rows, lambda r: r in target, settings, "Source 29.5.0j stability candidate. Used as design source, not an auto-entry trigger.", entry_candidate_allowed=True),
        _variant("paper_profile_entry_state_only", target, _is_entry_state, settings, "MAP_SCORE_65_79 restricted to repaired CONTEXT/CONFIRMATION entry states.", entry_candidate_allowed=True),
        _variant("paper_profile_no_wait_no_conflict", target, lambda r: not _is_wait(r) and not _is_conflict(r) and not _is_no_structure(r), settings, "MAP_SCORE_65_79 excluding WAIT, CONFLICT and NO_STRUCTURE rows.", entry_candidate_allowed=True),
        _variant("paper_profile_confirmation_only", target, _is_confirmation, settings, "MAP_SCORE_65_79 with true repaired confirmation only.", entry_candidate_allowed=True),
        _variant("paper_profile_clean_source", target, _is_clean, settings, "MAP_SCORE_65_79 with clean pattern/range rows.", entry_candidate_allowed=True),
        _variant("watchlist_wait_only_blocked", target, _is_wait, settings, "WAIT rows are watchlist-only and must not become entries.", entry_candidate_allowed=False),
        _variant("no_structure_blocked", target, _is_no_structure, settings, "NO_STRUCTURE rows are blocked from entry.", entry_candidate_allowed=False),
        _variant("conflict_blocked", target, _is_conflict, settings, "CONFLICT rows are blocked from entry.", entry_candidate_allowed=False),
    ], key=lambda v: (bool(v.get("passes_profile_design_gate")), _safe_float(v.get("expectancy_r"), 0.0), _safe_float(v.get("win_rate_pct"), 0.0), _safe_int(v.get("candidates"), 0)), reverse=True)


def _state_matrix(target_rows: list[dict[str, Any]]) -> dict[str, Any]:
    states = Counter(str(r.get("structure_state") or "NA") for r in target_rows)
    summaries: dict[str, dict[str, Any]] = {}
    for state in states:
        vals = [r for r in target_rows if str(r.get("structure_state") or "NA") == state]
        summaries[state] = _summarize_rows(vals)
    return {
        "state_counts": dict(states),
        "entry_state_rows": sum(1 for r in target_rows if _is_entry_state(r)),
        "confirmation_rows": sum(1 for r in target_rows if _is_confirmation(r)),
        "wait_rows": sum(1 for r in target_rows if _is_wait(r)),
        "no_structure_rows": sum(1 for r in target_rows if _is_no_structure(r)),
        "conflict_rows": sum(1 for r in target_rows if _is_conflict(r)),
        "state_summaries": summaries,
    }


def _allowed_symbols_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(r.get("symbol") or "").upper() for r in rows if str(r.get("symbol") or "").strip()})


def _allowed_sides_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(r.get("side") or "").upper() for r in rows if str(r.get("side") or "").strip()})


def _profile_spec(target_rows: list[dict[str, Any]], settings: PaperUnlockProfileRefinementSettings, independent_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_name": settings.proposed_profile_name,
        "profile_status": "DESIGN_ONLY_NOT_ENABLED",
        "source_patch": "29.5.0j",
        "source_variant": SOURCE_STABILITY_VARIANT,
        "allowed_symbols_from_validation": _allowed_symbols_from_rows(target_rows),
        "allowed_sides_from_validation": _allowed_sides_from_rows(target_rows),
        "selector": {
            "map_score_min_inclusive": settings.map_score_candidate_min,
            "map_score_max_inclusive": settings.map_score_candidate_max,
            "requires_independent_stability_candidate": settings.require_independent_stability_candidate,
            "requires_repaired_structure_layer": True,
            "requires_no_live_or_testnet": True,
            "requires_existing_strategy_signal": True,
        },
        "entry_state_policy": {
            "allowed_for_future_experiment": ["CONTEXT", "CONFIRMATION"],
            "blocked": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
            "wait_policy": "watchlist_only_not_entry",
            "conflict_policy": "hard_block",
            "no_structure_policy": "hard_block",
        },
        "paper_risk_design": {
            "max_positions": settings.proposed_max_positions,
            "risk_per_trade_pct": settings.proposed_risk_per_trade_pct,
            "live_block": True,
            "testnet_block": True,
            "orders_enabled_in_this_patch": False,
            "position_opening_enabled_in_this_patch": False,
        },
        "required_prior_guard": {
            "independent_report_status": independent_report.get("status", "MISSING") if independent_report else "MISSING",
            "independent_decision_status": ((independent_report.get("decision") or {}).get("status") if isinstance(independent_report.get("decision"), dict) else "MISSING") if independent_report else "MISSING",
        },
    }


def _component_audit(target_rows: list[dict[str, Any]], rows: list[dict[str, Any]], settings: PaperUnlockProfileRefinementSettings) -> dict[str, Any]:
    independent_settings = settings.independent_settings()
    return {
        "target_by_asset": _component_quality(target_rows, lambda r: str(r.get("symbol") or "NA"), independent_settings, min_candidates=3),
        "target_by_side": _component_quality(target_rows, lambda r: str(r.get("side") or "NA"), independent_settings, min_candidates=3),
        "target_by_asset_side": _component_quality(target_rows, lambda r: f"{r.get('symbol') or 'NA'}:{r.get('side') or 'NA'}", independent_settings, min_candidates=3),
        "target_by_structure_state": _component_quality(target_rows, lambda r: str(r.get("structure_state") or "NA"), independent_settings, min_candidates=3),
        "target_by_confirmation_summary": _component_quality(target_rows, lambda r: str(r.get("confirmation_summary") or "NA"), independent_settings, min_candidates=3),
        "target_by_price_location": _component_quality(target_rows, lambda r: str(r.get("price_location") or "NA"), independent_settings, min_candidates=3),
        "all_rows_by_profile_bucket": _component_quality(rows, lambda r: "MAP_SCORE_65_79" if _target_map_score_65_79(r, independent_settings) else "OUTSIDE_PROFILE", independent_settings, min_candidates=10),
    }


def _fallback_summary(base: Path, independent_report: dict[str, Any]) -> dict[str, Any]:
    if not independent_report:
        return {"available": False}
    decision = independent_report.get("decision", {}) if isinstance(independent_report.get("decision"), dict) else {}
    best = decision.get("best_stability_variant", {}) if isinstance(decision.get("best_stability_variant"), dict) else {}
    return {
        "available": True,
        "source": str(base / "independent_repaired_validation_report.json"),
        "status": independent_report.get("status"),
        "decision_status": decision.get("status"),
        "best_stability_variant": best,
        "counts": independent_report.get("counts", {}) if isinstance(independent_report.get("counts"), dict) else {},
        "walk_forward": (independent_report.get("walk_forward") or {}).get("stability_checks", {}) if isinstance(independent_report.get("walk_forward"), dict) else {},
        "concentration": (independent_report.get("concentration") or {}).get("checks", {}) if isinstance(independent_report.get("concentration"), dict) else {},
    }


def _decision(target_summary: dict[str, Any], independent_report: dict[str, Any], variants: list[dict[str, Any]], target_rows: list[dict[str, Any]], fallback: dict[str, Any], settings: PaperUnlockProfileRefinementSettings) -> dict[str, Any]:
    independent_ok = _independent_guard_ok(independent_report)
    source_gate = bool((target_summary.get("gate_checks") or {}).get("passes_profile_design_gate"))
    best_entry_variant = next((v for v in variants if v.get("entry_candidate_allowed") and v.get("passes_profile_design_gate")), {})
    design_ready = bool(independent_ok and (source_gate or fallback.get("available")))
    if settings.require_independent_stability_candidate and not independent_ok:
        design_ready = False
    if design_ready:
        return {
            "status": "PROFILE_REFINEMENT_DESIGN_READY_DIAGNOSTIC",
            "reason": "29.5.0j stability candidate is present; a paper-only profile design can be drafted, but this patch keeps all execution disabled.",
            "profile_name": settings.proposed_profile_name,
            "source_variant": SOURCE_STABILITY_VARIANT,
            "best_profile_design_variant": best_entry_variant or target_summary,
            "source_profile_summary": target_summary,
            "operational_unlock_allowed": False,
            "paper_unlock_refinement_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "profile_activation_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
            "next_patch": "29.4.4d calibrated paper-only unlock experiment design, still no live/testnet and only if user explicitly proceeds.",
            "required_next_step": "Implement a separate paper-only experiment gate that reuses this profile spec and keeps live/testnet blocked.",
        }
    reasons: list[str] = []
    if not independent_ok:
        reasons.append("independent 29.5.0j stability candidate missing or not passing")
    if not source_gate and not fallback.get("available"):
        reasons.append("source MAP_SCORE_65_79 profile did not pass profile design gate")
    if not target_rows and not fallback.get("available"):
        reasons.append("no target rows available")
    return {
        "status": "KEEP_DIAGNOSTIC",
        "reason": "; ".join(reasons or ["profile refinement design not ready"]),
        "profile_name": settings.proposed_profile_name,
        "source_variant": SOURCE_STABILITY_VARIANT,
        "best_profile_design_variant": best_entry_variant or (variants[0] if variants else target_summary),
        "source_profile_summary": target_summary,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "profile_activation_allowed": False,
        "orders_submitted": 0,
        "positions_opened": 0,
        "recommended_actions": [
            "Keep the profile diagnostic-only until independent stability is present.",
            "Do not enable paper unlock from this design report alone.",
            "Keep WAIT, NO_STRUCTURE and CONFLICT blocked from entry in any future experiment.",
        ],
        "next_patch": "29.5.0j-1 or sample expansion before paper unlock profile work",
    }


def _settings_payload(settings: PaperUnlockProfileRefinementSettings) -> dict[str, Any]:
    return {
        "focus_symbol": settings.focus_symbol,
        "focus_bucket": settings.focus_bucket,
        "max_rows_per_asset": settings.max_rows_per_asset,
        "eval_stride": settings.eval_stride,
        "max_structure_candidates_per_asset": settings.max_structure_candidates_per_asset,
        "structure_window_rows": settings.structure_window_rows,
        "min_variant_candidates": settings.min_variant_candidates,
        "min_expectancy_r": settings.min_expectancy_r,
        "min_win_rate_pct": settings.min_win_rate_pct,
        "max_loss_rate_pct": settings.max_loss_rate_pct,
        "max_time_exit_rate_pct": settings.max_time_exit_rate_pct,
        "fold_count": settings.fold_count,
        "holdout_fraction": settings.holdout_fraction,
        "max_asset_concentration_pct": settings.max_asset_concentration_pct,
        "max_side_concentration_pct": settings.max_side_concentration_pct,
        "map_score_candidate_min": settings.map_score_candidate_min,
        "map_score_candidate_max": settings.map_score_candidate_max,
        "proposed_profile_name": settings.proposed_profile_name,
        "proposed_max_positions": settings.proposed_max_positions,
        "proposed_risk_per_trade_pct": settings.proposed_risk_per_trade_pct,
        "require_independent_stability_candidate": settings.require_independent_stability_candidate,
    }


def build_paper_unlock_profile_refinement_report(data_dir: str | Path = "data", settings: PaperUnlockProfileRefinementSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    settings = settings or PaperUnlockProfileRefinementSettings.from_config()
    independent_report = _load_independent_report(base)
    if not settings.enabled:
        rows: list[dict[str, Any]] = []
        historical = {"status": "DISABLED", "warnings": [], "by_asset": {}}
    else:
        rows, historical = _collect_repaired_rows(base, settings)
    target = _target_rows(rows, settings) if rows else []
    target_summary = _summary_with_gate(target, settings, entry_candidate_allowed=True) if target else {}
    target_summary.update({
        "name": SOURCE_STABILITY_VARIANT,
        "description": "Source stability candidate from 29.5.0j used to design a future paper-only profile.",
    })
    fallback = _fallback_summary(base, independent_report) if not target else {"available": False}
    if not target and fallback.get("available"):
        best = fallback.get("best_stability_variant", {}) if isinstance(fallback.get("best_stability_variant"), dict) else {}
        target_summary = dict(best)
        target_summary.setdefault("name", SOURCE_STABILITY_VARIANT)
        target_summary.setdefault("description", "Source stability candidate loaded from independent validation fallback report.")
        if "gate_checks" not in target_summary:
            target_summary["gate_checks"] = _profile_gate(target_summary, settings, entry_candidate_allowed=True)
        target_summary["passes_profile_design_gate"] = bool((target_summary.get("gate_checks") or {}).get("passes_profile_design_gate"))
    variants = _profile_variants(rows, target, settings) if target else []
    independent_settings = settings.independent_settings()
    walk_forward = _walk_forward(target, independent_settings) if target else (independent_report.get("walk_forward", {}) if isinstance(independent_report.get("walk_forward"), dict) else {})
    concentration = _concentration(target, independent_settings) if target else (independent_report.get("concentration", {}) if isinstance(independent_report.get("concentration"), dict) else {})
    profile_spec = _profile_spec(target, settings, independent_report)
    component_audit = _component_audit(target, rows, settings) if target else {}
    decision = _decision(target_summary, independent_report, variants, target, fallback, settings)
    status = "DISABLED" if not settings.enabled else ("PASS" if decision.get("status") == "PROFILE_REFINEMENT_DESIGN_READY_DIAGNOSTIC" else "WARN")
    report = {
        "report_type": "paper_unlock_profile_refinement_design",
        "prompt": PROMPT_ID,
        "generated_at": utc_now_iso(),
        "status": status,
        "decision": decision,
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "paper_unlock_refinement_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "profile_activation_allowed": False,
        "safety": {
            "no_orders": True,
            "no_live": True,
            "no_testnet": True,
            "paper_unlock_unchanged": True,
            "risk_unchanged": True,
            "diagnostic_only": True,
            "profile_design_only": True,
        },
        "counts": {
            "scenario_pattern_evaluation_rows": historical.get("scenario_pattern_evaluation_rows", 0),
            "candidate_rows_pre_structure": historical.get("candidate_rows_pre_structure", 0),
            "structured_candidate_rows": len(rows),
            "target_candidate_rows": len(target) or _safe_int((fallback.get("counts") or {}).get("target_candidate_rows") if isinstance(fallback.get("counts"), dict) else 0, 0),
            "profile_variants": len(variants),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "settings": _settings_payload(settings),
        "source_validation": {
            "independent_report_status": independent_report.get("status", "MISSING") if independent_report else "MISSING",
            "independent_decision_status": ((independent_report.get("decision") or {}).get("status") if isinstance(independent_report.get("decision"), dict) else "MISSING") if independent_report else "MISSING",
            "independent_guard_ok": _independent_guard_ok(independent_report),
        },
        "profile_spec": profile_spec,
        "source_profile_summary": target_summary,
        "profile_variants": variants,
        "profile_variants_top": variants[:12],
        "state_matrix": _state_matrix(target) if target else {},
        "walk_forward": walk_forward,
        "concentration": concentration,
        "component_audit": component_audit,
        "historical_summary": _summarize_rows(rows) if rows else {},
        "by_asset": historical.get("by_asset", {}),
        "fallback": fallback,
        "warnings": historical.get("warnings", []),
        "recent_target_rows": [
            {
                "symbol": r.get("symbol"),
                "datetime": r.get("datetime"),
                "side": r.get("side"),
                "bucket": r.get("bucket"),
                "pattern_score": r.get("pattern_score"),
                "range_pos_400": r.get("range_pos_400"),
                "map_score": r.get("map_score"),
                "structure_bias": r.get("structure_bias"),
                "price_location": r.get("price_location"),
                "confirmation_summary": r.get("confirmation_summary"),
                "structure_state": r.get("structure_state"),
                "structure_relabel": r.get("structure_relabel"),
                "outcome": r.get("outcome"),
                "r": r.get("r"),
            }
            for r in _sort_rows(target)[-20:]
        ],
        "files": {
            "report": str(base / REPORT_NAME),
            "independent_repaired_validation": str(base / "independent_repaired_validation_report.json"),
            "repaired_structure_shadow_validation": str(base / "repaired_structure_shadow_validation_report.json"),
            "structure_context_repair": str(base / "structure_context_repair_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_profile_refinement_report(data_dir: str | Path = "data", settings: PaperUnlockProfileRefinementSettings | None = None) -> dict[str, Any]:
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_profile_refinement_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


__all__ = [
    "REPORT_NAME",
    "PROFILE_NAME",
    "PaperUnlockProfileRefinementSettings",
    "build_paper_unlock_profile_refinement_report",
    "write_paper_unlock_profile_refinement_report",
]
