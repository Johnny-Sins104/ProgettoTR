"""Prompt 29.4.4i guarded paper-only activation draft.

This module converts the validated shadow sample from Prompt 29.4.4h into a
paper-only activation *design draft*.  It intentionally does not enable paper
orders, testnet, live trading, profile activation, or any risk/threshold change.

A positive decision means the safety interlock design is internally consistent
and a future, separate patch may implement a guarded manual switch.  It is not an
activation and must not be interpreted as permission to submit orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from config import Config
from core.calibrated_structure_shadow import _safe_float, _safe_int

REPORT_NAME = "paper_unlock_activation_draft_report.json"
PROMPT_ID = "29.4.4i"
DRAFT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ACTIVATION_DRAFT"
PROFILE_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"
EXPERIMENT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN"
REVIEW_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_SHADOW_SAMPLE_STABILITY_REVIEW"
REQUIRED_STABILITY_DECISION = "SHADOW_SAMPLE_STABILITY_CANDIDATE_DIAGNOSTIC"
READY_DECISION = "GUARDED_PAPER_ACTIVATION_DRAFT_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaperUnlockActivationDraftSettings:
    enabled: bool = True
    draft_name: str = DRAFT_NAME
    profile_name: str = PROFILE_NAME
    experiment_name: str = EXPERIMENT_NAME
    required_stability_decision: str = REQUIRED_STABILITY_DECISION
    required_cadence_variant: str = "bounded_6_daily_30_weekly_0h"
    required_selected_entries: int = 20
    max_positions: int = 1
    risk_per_trade_pct: float = 0.0025
    max_daily_entries: int = 6
    max_weekly_entries: int = 30
    min_hours_between_entries: float = 0.0
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0
    min_positive_window_rate_pct: float = 66.67
    min_holdout_entries: int = 5
    max_asset_concentration_pct: float = 75.0
    max_side_concentration_pct: float = 85.0
    require_confirmation_only_first_activation: bool = True
    require_manual_two_step_activation: bool = True
    require_stability_review: bool = True
    require_paper_mode: bool = True
    max_report_age_hours: float = 0.0  # 0 = do not fail on age in offline diagnostic reports

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockActivationDraftSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_ENABLED", True)),
            draft_name=str(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_NAME", DRAFT_NAME) or DRAFT_NAME),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            experiment_name=str(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_EXPERIMENT_NAME", EXPERIMENT_NAME) or EXPERIMENT_NAME),
            required_stability_decision=str(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_STABILITY_DECISION", REQUIRED_STABILITY_DECISION) or REQUIRED_STABILITY_DECISION),
            required_cadence_variant=str(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h") or "bounded_6_daily_30_weekly_0h"),
            required_selected_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRED_SELECTED_ENTRIES", 20), 20)),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_POSITIONS", 1), 1)),
            risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_RISK_PER_TRADE_PCT", 0.0025), 0.0025)),
            max_daily_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_DAILY_ENTRIES", 6), 6)),
            max_weekly_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_WEEKLY_ENTRIES", 30), 30)),
            min_hours_between_entries=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_HOURS_BETWEEN_ENTRIES", 0.0), 0.0)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_ABORT_MAX_CONSECUTIVE_LOSSES", 3), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_ABORT_MAX_DRAWDOWN_PCT", 1.0), 1.0)),
            min_positive_window_rate_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_POSITIVE_WINDOW_RATE_PCT", 66.67), 66.67),
            min_holdout_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MIN_HOLDOUT_ENTRIES", 5), 5)),
            max_asset_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_ASSET_CONCENTRATION_PCT", 75.0), 75.0),
            max_side_concentration_pct=_safe_float(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_SIDE_CONCENTRATION_PCT", 85.0), 85.0),
            require_confirmation_only_first_activation=bool(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_CONFIRMATION_ONLY", True)),
            require_manual_two_step_activation=bool(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_MANUAL_TWO_STEP", True)),
            require_stability_review=bool(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_STABILITY_REVIEW", True)),
            require_paper_mode=bool(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_REQUIRE_PAPER_MODE", True)),
            max_report_age_hours=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_ACTIVATION_DRAFT_MAX_REPORT_AGE_HOURS", 0.0), 0.0)),
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {"status": "MISSING", "path": str(path)}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"status": "INVALID", "path": str(path)}
    except Exception as exc:
        return {"status": "READ_ERROR", "path": str(path), "error": str(exc)}


def _decision(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("decision")
    return value if isinstance(value, dict) else {}


def _checks(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("stability_checks")
    return value if isinstance(value, dict) else {}


def _safe_bool(value: Any) -> bool:
    return bool(value) is True


def _stability_guard(stability_report: dict[str, Any], settings: PaperUnlockActivationDraftSettings) -> dict[str, Any]:
    decision = _decision(stability_report)
    checks = _checks(stability_report)
    counts = stability_report.get("counts", {}) if isinstance(stability_report.get("counts"), dict) else {}
    selected_entries = _safe_int(decision.get("selected_entries", counts.get("selected_entries", 0)), 0)
    best_variant = str(decision.get("best_stability_review_variant") or "")
    dry_gate = checks.get("dry_run_gate", {}) if isinstance(checks.get("dry_run_gate"), dict) else {}
    concentration = checks.get("concentration", {}) if isinstance(checks.get("concentration"), dict) else {}
    holdout = checks.get("holdout", {}) if isinstance(checks.get("holdout"), dict) else {}
    temporal = checks.get("temporal_dispersion", {}) if isinstance(checks.get("temporal_dispersion"), dict) else {}
    window = checks.get("window_stability", {}) if isinstance(checks.get("window_stability"), dict) else {}
    equity = checks.get("equity_dry_run", {}) if isinstance(checks.get("equity_dry_run"), dict) else {}
    state_breakdown = checks.get("state_breakdown", {}) if isinstance(checks.get("state_breakdown"), dict) else {}
    state_counts = state_breakdown.get("state_counts", {}) if isinstance(state_breakdown.get("state_counts"), dict) else {}

    report_status_ok = str(stability_report.get("status") or "").upper() == "PASS"
    decision_ok = str(decision.get("status") or "") == settings.required_stability_decision
    cadence_ok = best_variant == settings.required_cadence_variant
    selected_entries_ok = selected_entries >= settings.required_selected_entries
    execution_disabled_ok = (
        not bool(stability_report.get("operational_unlock_allowed", False))
        and not bool(stability_report.get("paper_unlock_experiment_allowed", False))
        and not bool(stability_report.get("paper_orders_enabled", False))
        and not bool(decision.get("operational_unlock_allowed", False))
        and not bool(decision.get("paper_unlock_experiment_allowed", False))
        and not bool(decision.get("paper_orders_enabled", False))
        and _safe_int(counts.get("orders_submitted", 0), 0) == 0
        and _safe_int(counts.get("positions_opened", 0), 0) == 0
    )
    sample_ok = bool(checks.get("sample_ok", False))
    rolling_ok = bool(checks.get("rolling_window_ok", False))
    holdout_ok = bool(checks.get("holdout_ok", False))
    concentration_ok = bool(checks.get("concentration_ok", False))
    temporal_ok = bool(checks.get("temporal_dispersion_ok", False))
    dry_run_ok = bool(dry_gate.get("passes_shadow_dry_run_gate", False))
    equity_ok = bool(checks.get("equity_guard_ok", False))
    confirmation_only_ok = True
    if settings.require_confirmation_only_first_activation:
        confirmation_count = _safe_int(state_counts.get("CONFIRMATION", 0), 0)
        non_confirmation = selected_entries - confirmation_count
        confirmation_only_ok = selected_entries > 0 and non_confirmation <= 0

    guard = {
        "stability_report_status_ok": report_status_ok,
        "stability_decision_ok": decision_ok,
        "cadence_variant_ok": cadence_ok,
        "selected_entries_ok": selected_entries_ok,
        "sample_ok": sample_ok,
        "rolling_window_ok": rolling_ok,
        "holdout_ok": holdout_ok,
        "concentration_ok": concentration_ok,
        "temporal_dispersion_ok": temporal_ok,
        "dry_run_gate_ok": dry_run_ok,
        "equity_guard_ok": equity_ok,
        "execution_disabled_ok": execution_disabled_ok,
        "confirmation_only_ok": confirmation_only_ok,
        "selected_entries": selected_entries,
        "required_selected_entries": settings.required_selected_entries,
        "best_stability_review_variant": best_variant,
        "required_cadence_variant": settings.required_cadence_variant,
        "status": decision.get("status", ""),
        "review_name": stability_report.get("review_name", REVIEW_NAME),
        "counts": counts,
        "dry_run_gate": dry_gate,
        "equity": {
            "entries": equity.get("entries", selected_entries),
            "cumulative_r": equity.get("cumulative_r", 0),
            "max_consecutive_losses": equity.get("max_consecutive_losses", 0),
            "max_drawdown_pct": equity.get("max_drawdown_pct", 0),
            "would_abort_on_consecutive_losses": bool(equity.get("would_abort_on_consecutive_losses", False)),
            "would_abort_on_drawdown": bool(equity.get("would_abort_on_drawdown", False)),
        },
        "concentration": concentration,
        "holdout": holdout,
        "temporal_dispersion": temporal,
        "window_stability": window,
        "state_counts": state_counts,
    }
    guard["passes_stability_prerequisite"] = all([
        report_status_ok,
        decision_ok,
        cadence_ok,
        selected_entries_ok,
        sample_ok,
        rolling_ok,
        holdout_ok,
        concentration_ok,
        temporal_ok,
        dry_run_ok,
        equity_ok,
        execution_disabled_ok,
        confirmation_only_ok,
    ])
    return guard


def _activation_interlocks(settings: PaperUnlockActivationDraftSettings, stability_guard: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_only": True,
        "manual_activation_required": True,
        "automatic_activation_allowed": False,
        "paper_orders_enabled_in_this_patch": False,
        "operational_unlock_allowed_in_this_patch": False,
        "testnet_allowed": False,
        "live_allowed": False,
        "profile_activation_allowed": False,
        "future_manual_switch_requirements": {
            "separate_patch_required": True,
            "two_step_confirmation_required": settings.require_manual_two_step_activation,
            "required_profile_name": settings.profile_name,
            "required_experiment_name": settings.experiment_name,
            "required_stability_decision": settings.required_stability_decision,
            "required_cadence_variant": settings.required_cadence_variant,
            "required_selected_entries": settings.required_selected_entries,
            "required_mode": "paper" if settings.require_paper_mode else "paper_or_diagnostic",
            "must_keep_live_and_testnet_blocked": True,
            "must_keep_exchange_broker_blocked": True,
            "must_recheck_latest_stability_report": True,
            "must_abort_if_any_prerequisite_missing": True,
        },
        "proposed_runtime_limits": {
            "max_positions": settings.max_positions,
            "risk_per_trade_pct": settings.risk_per_trade_pct,
            "max_daily_entries": settings.max_daily_entries,
            "max_weekly_entries": settings.max_weekly_entries,
            "min_hours_between_entries": settings.min_hours_between_entries,
            "map_score_min": 65.0,
            "map_score_max": 79.999,
            "entry_state_policy": "CONFIRMATION_ONLY" if settings.require_confirmation_only_first_activation else "CONTEXT_OR_CONFIRMATION",
            "allowed_structure_states": ["CONFIRMATION"] if settings.require_confirmation_only_first_activation else ["CONTEXT", "CONFIRMATION"],
            "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
        },
        "abort_criteria": {
            "max_consecutive_losses": settings.abort_max_consecutive_losses,
            "max_drawdown_pct": settings.abort_max_drawdown_pct,
            "pause_on_stability_report_missing": True,
            "pause_on_stability_report_not_pass": True,
            "pause_on_cadence_guard_failure": True,
            "pause_on_concentration_guard_failure": True,
            "pause_on_holdout_guard_failure": True,
            "pause_on_rolling_window_guard_failure": True,
            "pause_on_temporal_dispersion_failure": True,
            "pause_on_any_live_or_testnet_mode": True,
            "pause_on_paper_orders_without_manual_switch": True,
        },
        "prerequisite_snapshot": {
            "passes_stability_prerequisite": bool(stability_guard.get("passes_stability_prerequisite", False)),
            "selected_entries": stability_guard.get("selected_entries", 0),
            "best_stability_review_variant": stability_guard.get("best_stability_review_variant", ""),
            "state_counts": stability_guard.get("state_counts", {}),
            "equity": stability_guard.get("equity", {}),
        },
    }


def build_paper_unlock_activation_draft_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockActivationDraftSettings | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockActivationDraftSettings.from_config()
    base = Path(base_dir)
    stability_path = base / "paper_unlock_shadow_stability_review_report.json"
    stability_report = _read_json(stability_path)
    stability_guard = _stability_guard(stability_report, settings)
    interlocks = _activation_interlocks(settings, stability_guard)

    prerequisite_ok = bool(stability_guard.get("passes_stability_prerequisite", False)) if settings.require_stability_review else True
    draft_ready = bool(settings.enabled and prerequisite_ok)
    decision_status = READY_DECISION if draft_ready else KEEP_DECISION
    reason = (
        "Shadow sample stability review passed and guarded paper-only activation interlock design is ready. "
        "Execution remains disabled; activation requires a separate manual patch."
        if draft_ready else
        "Guarded paper-only activation draft prerequisites are incomplete; execution remains disabled."
    )
    next_patch = (
        "29.4.4j guarded paper-only experiment switch implementation draft, paper-only/manual and still no live/testnet."
        if draft_ready else
        "Repair activation-draft prerequisites before any paper-only switch implementation."
    )
    counts = stability_guard.get("counts", {}) if isinstance(stability_guard.get("counts"), dict) else {}

    report = {
        "prompt": PROMPT_ID,
        "report_type": "paper_unlock_activation_draft",
        "generated_at": utc_now_iso(),
        "status": "PASS" if draft_ready else "WARN",
        "draft_name": settings.draft_name,
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "source_review_name": stability_report.get("review_name", REVIEW_NAME),
        "diagnostic_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
        "automatic_activation_allowed": False,
        "manual_activation_required": True,
        "stability_prerequisite": stability_guard,
        "activation_interlocks": interlocks,
        "activation_draft": {
            "draft_name": settings.draft_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "candidate_cadence": settings.required_cadence_variant,
            "selected_entries": stability_guard.get("selected_entries", 0),
            "entry_state_policy": interlocks["proposed_runtime_limits"]["entry_state_policy"],
            "runtime_limits": interlocks["proposed_runtime_limits"],
            "abort_criteria": interlocks["abort_criteria"],
            "manual_switch_requirements": interlocks["future_manual_switch_requirements"],
        },
        "safety_matrix": {
            "live_block": True,
            "testnet_block": True,
            "paper_orders_blocked_this_patch": True,
            "exchange_broker_blocked": True,
            "requires_separate_activation_patch": True,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "counts": {
            "source_target_rows": counts.get("source_target_rows", 0),
            "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
            "selected_entries": stability_guard.get("selected_entries", counts.get("selected_entries", 0)),
            "rejected_entries": counts.get("rejected_entries", 0),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "decision": {
            "status": decision_status,
            "reason": reason,
            "next_patch": next_patch,
            "draft_name": settings.draft_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "best_stability_review_variant": stability_guard.get("best_stability_review_variant", ""),
            "selected_entries": stability_guard.get("selected_entries", 0),
            "interlocks_ready": draft_ready,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": False,
        },
        "files": {
            "report": str(base / REPORT_NAME),
            "shadow_stability_review": str(stability_path),
            "bounded_cadence": str(base / "paper_unlock_bounded_cadence_report.json"),
            "experiment_design": str(base / "paper_unlock_experiment_design_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_activation_draft_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockActivationDraftSettings | None = None,
) -> dict[str, Any]:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_activation_draft_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
