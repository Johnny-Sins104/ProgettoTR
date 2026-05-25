"""Prompt 29.4.4j guarded paper-only experiment switch implementation draft.

This module turns the Prompt 29.4.4i activation draft into a concrete manual
switch *implementation draft*.  It deliberately does not enable paper orders,
testnet, live trading, profile activation, or any automatic switch in this
patch.

A PASS/READY decision means the switch contract and safety interlocks are
internally consistent.  Activation still requires a separate explicit patch and
a two-step manual confirmation path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from config import Config
from core.calibrated_structure_shadow import _safe_float, _safe_int

REPORT_NAME = "paper_unlock_experiment_switch_draft_report.json"
PROMPT_ID = "29.4.4j"
SWITCH_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT"
DRAFT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ACTIVATION_DRAFT"
PROFILE_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"
EXPERIMENT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN"
REQUIRED_ACTIVATION_DECISION = "GUARDED_PAPER_ACTIVATION_DRAFT_READY_DIAGNOSTIC"
READY_DECISION = "GUARDED_PAPER_SWITCH_IMPLEMENTATION_DRAFT_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaperUnlockExperimentSwitchDraftSettings:
    enabled: bool = True
    switch_name: str = SWITCH_NAME
    activation_draft_name: str = DRAFT_NAME
    profile_name: str = PROFILE_NAME
    experiment_name: str = EXPERIMENT_NAME
    required_activation_decision: str = REQUIRED_ACTIVATION_DECISION
    required_selected_entries: int = 20
    required_cadence_variant: str = "bounded_6_daily_30_weekly_0h"
    require_two_step_manual_activation: bool = True
    require_separate_activation_patch: bool = True
    require_confirmation_only: bool = True
    require_paper_mode: bool = True
    max_positions: int = 1
    risk_per_trade_pct: float = 0.0025
    max_daily_entries: int = 6
    max_weekly_entries: int = 30
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0
    manual_enable_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE"
    manual_confirm_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM"
    expected_manual_confirm_value: str = "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY"
    max_report_age_hours: float = 0.0  # 0 = age not enforced for offline diagnostic reports

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockExperimentSwitchDraftSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ENABLED", True)),
            switch_name=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_NAME", SWITCH_NAME) or SWITCH_NAME),
            activation_draft_name=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ACTIVATION_DRAFT_NAME", DRAFT_NAME) or DRAFT_NAME),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            experiment_name=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_EXPERIMENT_NAME", EXPERIMENT_NAME) or EXPERIMENT_NAME),
            required_activation_decision=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_ACTIVATION_DECISION", REQUIRED_ACTIVATION_DECISION) or REQUIRED_ACTIVATION_DECISION),
            required_selected_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_SELECTED_ENTRIES", 20), 20)),
            required_cadence_variant=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h") or "bounded_6_daily_30_weekly_0h"),
            require_two_step_manual_activation=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_TWO_STEP", True)),
            require_separate_activation_patch=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_SEPARATE_PATCH", True)),
            require_confirmation_only=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_CONFIRMATION_ONLY", True)),
            require_paper_mode=bool(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_REQUIRE_PAPER_MODE", True)),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_POSITIONS", 1), 1)),
            risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_RISK_PER_TRADE_PCT", 0.0025), 0.0025)),
            max_daily_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_DAILY_ENTRIES", 6), 6)),
            max_weekly_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_WEEKLY_ENTRIES", 30), 30)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ABORT_MAX_CONSECUTIVE_LOSSES", 3), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ABORT_MAX_DRAWDOWN_PCT", 1.0), 1.0)),
            manual_enable_env=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE"),
            manual_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM"),
            expected_manual_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_EXPECTED_CONFIRM_VALUE", "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY") or "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY"),
            max_report_age_hours=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_MAX_REPORT_AGE_HOURS", 0.0), 0.0)),
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


def _activation_interlocks(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("activation_interlocks")
    return value if isinstance(value, dict) else {}


def _activation_draft(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("activation_draft")
    return value if isinstance(value, dict) else {}


def _runtime_limits(interlocks: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    value = interlocks.get("proposed_runtime_limits")
    if isinstance(value, dict):
        return value
    value = draft.get("runtime_limits")
    return value if isinstance(value, dict) else {}


def _future_switch_requirements(interlocks: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    value = interlocks.get("future_manual_switch_requirements")
    if isinstance(value, dict):
        return value
    value = draft.get("manual_switch_requirements")
    return value if isinstance(value, dict) else {}


def _activation_draft_guard(activation_report: dict[str, Any], settings: PaperUnlockExperimentSwitchDraftSettings) -> dict[str, Any]:
    decision = _decision(activation_report)
    interlocks = _activation_interlocks(activation_report)
    draft = _activation_draft(activation_report)
    runtime_limits = _runtime_limits(interlocks, draft)
    manual_requirements = _future_switch_requirements(interlocks, draft)
    stability = activation_report.get("stability_prerequisite", {}) if isinstance(activation_report.get("stability_prerequisite"), dict) else {}
    counts = activation_report.get("counts", {}) if isinstance(activation_report.get("counts"), dict) else {}

    report_status_ok = str(activation_report.get("status") or "").upper() == "PASS"
    decision_ok = str(decision.get("status") or "") == settings.required_activation_decision
    draft_name_ok = str(decision.get("draft_name") or activation_report.get("draft_name") or "") == settings.activation_draft_name
    profile_name_ok = str(decision.get("profile_name") or activation_report.get("profile_name") or "") == settings.profile_name
    experiment_name_ok = str(decision.get("experiment_name") or activation_report.get("experiment_name") or "") == settings.experiment_name
    interlocks_ready = bool(decision.get("interlocks_ready", False))
    stability_ok = bool(stability.get("passes_stability_prerequisite", False))
    selected_entries = _safe_int(decision.get("selected_entries", counts.get("selected_entries", 0)), 0)
    selected_entries_ok = selected_entries >= settings.required_selected_entries
    cadence_ok = str(decision.get("best_stability_review_variant") or stability.get("best_stability_review_variant") or "") == settings.required_cadence_variant
    execution_disabled_ok = (
        not bool(activation_report.get("operational_unlock_allowed", False))
        and not bool(activation_report.get("paper_unlock_experiment_allowed", False))
        and not bool(activation_report.get("paper_orders_enabled", False))
        and not bool(activation_report.get("profile_activation_allowed", False))
        and not bool(decision.get("operational_unlock_allowed", False))
        and not bool(decision.get("paper_unlock_experiment_allowed", False))
        and not bool(decision.get("paper_orders_enabled", False))
        and not bool(decision.get("profile_activation_allowed", False))
        and _safe_int(counts.get("orders_submitted", 0), 0) == 0
        and _safe_int(counts.get("positions_opened", 0), 0) == 0
    )
    no_auto_activation_ok = (
        not bool(activation_report.get("automatic_activation_allowed", False))
        and not bool(decision.get("automatic_activation_allowed", False))
        and not bool(interlocks.get("automatic_activation_allowed", False))
    )
    manual_required_ok = bool(interlocks.get("manual_activation_required", activation_report.get("manual_activation_required", False)))
    separate_patch_ok = bool(manual_requirements.get("separate_patch_required", settings.require_separate_activation_patch)) if settings.require_separate_activation_patch else True
    two_step_ok = bool(manual_requirements.get("two_step_confirmation_required", settings.require_two_step_manual_activation)) if settings.require_two_step_manual_activation else True
    live_block_ok = bool(interlocks.get("live_allowed", False)) is False and bool(interlocks.get("testnet_allowed", False)) is False
    exchange_block_ok = bool(manual_requirements.get("must_keep_exchange_broker_blocked", True))
    entry_state_policy = str(runtime_limits.get("entry_state_policy") or draft.get("entry_state_policy") or "")
    allowed_states = runtime_limits.get("allowed_structure_states", [])
    if not isinstance(allowed_states, list):
        allowed_states = []
    blocked_states = runtime_limits.get("blocked_structure_states", [])
    if not isinstance(blocked_states, list):
        blocked_states = []
    confirmation_only_ok = True
    if settings.require_confirmation_only:
        confirmation_only_ok = entry_state_policy == "CONFIRMATION_ONLY" and allowed_states == ["CONFIRMATION"]
    blocked_states_ok = all(state in blocked_states for state in ["WAIT", "NO_STRUCTURE", "CONFLICT"])
    limits_ok = (
        _safe_int(runtime_limits.get("max_positions", 0), 0) == settings.max_positions
        and _safe_float(runtime_limits.get("risk_per_trade_pct", 0), 0.0) <= settings.risk_per_trade_pct + 1e-12
        and _safe_int(runtime_limits.get("max_daily_entries", 0), 0) <= settings.max_daily_entries
        and _safe_int(runtime_limits.get("max_weekly_entries", 0), 0) <= settings.max_weekly_entries
    )
    guard = {
        "activation_report_status_ok": report_status_ok,
        "activation_decision_ok": decision_ok,
        "draft_name_ok": draft_name_ok,
        "profile_name_ok": profile_name_ok,
        "experiment_name_ok": experiment_name_ok,
        "interlocks_ready": interlocks_ready,
        "stability_prerequisite_ok": stability_ok,
        "selected_entries_ok": selected_entries_ok,
        "cadence_variant_ok": cadence_ok,
        "execution_disabled_ok": execution_disabled_ok,
        "no_auto_activation_ok": no_auto_activation_ok,
        "manual_activation_required_ok": manual_required_ok,
        "separate_patch_required_ok": separate_patch_ok,
        "two_step_confirmation_required_ok": two_step_ok,
        "live_testnet_block_ok": live_block_ok,
        "exchange_broker_block_ok": exchange_block_ok,
        "confirmation_only_ok": confirmation_only_ok,
        "blocked_states_ok": blocked_states_ok,
        "limits_ok": limits_ok,
        "selected_entries": selected_entries,
        "required_selected_entries": settings.required_selected_entries,
        "best_stability_review_variant": decision.get("best_stability_review_variant", ""),
        "runtime_limits": runtime_limits,
        "manual_switch_requirements": manual_requirements,
        "decision_status": decision.get("status", ""),
        "counts": counts,
    }
    guard["passes_activation_draft_guard"] = all([
        report_status_ok,
        decision_ok,
        draft_name_ok,
        profile_name_ok,
        experiment_name_ok,
        interlocks_ready,
        stability_ok,
        selected_entries_ok,
        cadence_ok,
        execution_disabled_ok,
        no_auto_activation_ok,
        manual_required_ok,
        separate_patch_ok,
        two_step_ok,
        live_block_ok,
        exchange_block_ok,
        confirmation_only_ok,
        blocked_states_ok,
        limits_ok,
    ])
    return guard


def _switch_contract(settings: PaperUnlockExperimentSwitchDraftSettings, activation_guard: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_type": "paper_only_manual_switch_draft",
        "draft_only": True,
        "implementation_ready_for_future_patch": bool(activation_guard.get("passes_activation_draft_guard", False)),
        "activation_in_this_patch_allowed": False,
        "automatic_activation_allowed": False,
        "paper_orders_enabled_in_this_patch": False,
        "operational_unlock_allowed_in_this_patch": False,
        "testnet_allowed": False,
        "live_allowed": False,
        "exchange_broker_allowed": False,
        "manual_switch_controls": {
            "separate_activation_patch_required": settings.require_separate_activation_patch,
            "two_step_confirmation_required": settings.require_two_step_manual_activation,
            "manual_enable_env": settings.manual_enable_env,
            "manual_enable_required_value": "1",
            "manual_confirm_env": settings.manual_confirm_env,
            "manual_confirm_required_value": settings.expected_manual_confirm_value,
            "required_mode": "paper" if settings.require_paper_mode else "paper_or_diagnostic",
            "must_fail_closed_if_missing": True,
            "must_fail_closed_if_live_or_testnet": True,
            "must_fail_closed_if_exchange_broker_enabled": True,
            "must_recheck_activation_draft_report": True,
            "must_recheck_shadow_stability_report": True,
        },
        "runtime_profile": {
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "entry_state_policy": "CONFIRMATION_ONLY" if settings.require_confirmation_only else "CONTEXT_OR_CONFIRMATION",
            "allowed_structure_states": ["CONFIRMATION"] if settings.require_confirmation_only else ["CONTEXT", "CONFIRMATION"],
            "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
            "map_score_min": 65.0,
            "map_score_max": 79.999,
            "max_positions": settings.max_positions,
            "risk_per_trade_pct": settings.risk_per_trade_pct,
            "max_daily_entries": settings.max_daily_entries,
            "max_weekly_entries": settings.max_weekly_entries,
        },
        "abort_interlocks": {
            "max_consecutive_losses": settings.abort_max_consecutive_losses,
            "max_drawdown_pct": settings.abort_max_drawdown_pct,
            "pause_on_missing_activation_draft": True,
            "pause_on_activation_draft_not_pass": True,
            "pause_on_stability_prerequisite_failure": True,
            "pause_on_cadence_mismatch": True,
            "pause_on_selected_entries_below_min": True,
            "pause_on_manual_confirmation_missing": True,
            "pause_on_any_live_or_testnet_mode": True,
            "pause_on_exchange_broker_available": True,
        },
        "prerequisite_snapshot": {
            "passes_activation_draft_guard": bool(activation_guard.get("passes_activation_draft_guard", False)),
            "selected_entries": activation_guard.get("selected_entries", 0),
            "best_stability_review_variant": activation_guard.get("best_stability_review_variant", ""),
        },
    }


def build_paper_unlock_experiment_switch_draft_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockExperimentSwitchDraftSettings | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockExperimentSwitchDraftSettings.from_config()
    base = Path(base_dir)
    activation_path = base / "paper_unlock_activation_draft_report.json"
    activation_report = _read_json(activation_path)
    activation_guard = _activation_draft_guard(activation_report, settings)
    switch_contract = _switch_contract(settings, activation_guard)

    ready = bool(settings.enabled and activation_guard.get("passes_activation_draft_guard", False))
    decision_status = READY_DECISION if ready else KEEP_DECISION
    reason = (
        "Guarded paper-only switch implementation draft is ready, but all execution remains disabled; "
        "a separate explicit manual activation patch is still required."
        if ready else
        "Guarded paper-only switch implementation draft prerequisites are incomplete; execution remains disabled."
    )
    next_patch = (
        "29.4.4k manual paper-only switch dry-run / fail-closed preflight, still no live/testnet."
        if ready else
        "Repair switch-draft prerequisites before any manual paper-only switch work."
    )
    counts = activation_guard.get("counts", {}) if isinstance(activation_guard.get("counts"), dict) else {}
    report = {
        "prompt": PROMPT_ID,
        "report_type": "paper_unlock_experiment_switch_draft",
        "generated_at": utc_now_iso(),
        "status": "PASS" if ready else "WARN",
        "switch_name": settings.switch_name,
        "activation_draft_name": settings.activation_draft_name,
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "diagnostic_only": True,
        "draft_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
        "automatic_activation_allowed": False,
        "manual_activation_allowed": False,
        "activation_in_this_patch_allowed": False,
        "activation_draft_guard": activation_guard,
        "switch_contract": switch_contract,
        "implementation_draft": {
            "switch_name": settings.switch_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "activation_draft_name": settings.activation_draft_name,
            "implementation_ready_for_future_patch": ready,
            "manual_switch_controls": switch_contract["manual_switch_controls"],
            "runtime_profile": switch_contract["runtime_profile"],
            "abort_interlocks": switch_contract["abort_interlocks"],
        },
        "safety_matrix": {
            "paper_only": True,
            "live_block": True,
            "testnet_block": True,
            "exchange_broker_blocked": True,
            "paper_orders_blocked_this_patch": True,
            "automatic_activation_blocked": True,
            "manual_activation_blocked_this_patch": True,
            "requires_separate_activation_patch": True,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "counts": {
            "source_target_rows": counts.get("source_target_rows", 0),
            "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
            "selected_entries": activation_guard.get("selected_entries", counts.get("selected_entries", 0)),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "decision": {
            "status": decision_status,
            "reason": reason,
            "next_patch": next_patch,
            "switch_name": settings.switch_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "activation_draft_name": settings.activation_draft_name,
            "best_stability_review_variant": activation_guard.get("best_stability_review_variant", ""),
            "selected_entries": activation_guard.get("selected_entries", 0),
            "activation_draft_ready": bool(activation_guard.get("passes_activation_draft_guard", False)),
            "switch_implementation_ready": ready,
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": False,
            "manual_activation_allowed": False,
        },
        "files": {
            "report": str(base / REPORT_NAME),
            "activation_draft": str(activation_path),
            "shadow_stability_review": str(base / "paper_unlock_shadow_stability_review_report.json"),
            "bounded_cadence": str(base / "paper_unlock_bounded_cadence_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_experiment_switch_draft_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockExperimentSwitchDraftSettings | None = None,
) -> dict[str, Any]:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_experiment_switch_draft_report(base, settings)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
