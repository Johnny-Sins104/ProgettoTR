"""Prompt 29.4.4n guarded paper-only experiment enable implementation.

This module is the first operator-controlled paper-only enable implementation for
MAP_SCORE_65_79_REPAIRED_STABILITY_V1.  It remains fail-closed by default and
requires the full manual control stack plus a dedicated operator enable/confirm
pair before reporting paper orders as enabled.

Safety boundaries:
- paper-only mode is required;
- live/testnet/exchange broker are blocked;
- automatic activation is never allowed;
- no real exchange orders are submitted by this module;
- the report only authorizes paper-order handling when every interlock passes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os

from config import Config
from core.calibrated_structure_shadow import _safe_float, _safe_int

REPORT_NAME = "paper_unlock_guarded_enable_report.json"
PROMPT_ID = "29.4.4n"
FINAL_PREFLIGHT_REPORT_NAME = "paper_unlock_final_enable_preflight_report.json"
FINAL_PREFLIGHT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT"
ACTIVATION_PATCH_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT"
SWITCH_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT"
PROFILE_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"
EXPERIMENT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN"
ENABLE_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_ENABLE"
REQUIRED_FINAL_PREFLIGHT_DECISION = "FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT_READY_DIAGNOSTIC"
READY_DECISION = "GUARDED_PAPER_ENABLE_IMPLEMENTATION_READY_OPERATOR_CONTROLLED"
ACTIVE_DECISION = "GUARDED_PAPER_ENABLE_ACTIVE_OPERATOR_CONTROLLED"
KEEP_DECISION = "KEEP_DIAGNOSTIC"
DEFAULT_SWITCH_CONFIRM_VALUE = "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY"
DEFAULT_ACTIVATION_CONFIRM_VALUE = "ACTIVATE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_DRAFT"
DEFAULT_FINAL_CONFIRM_VALUE = "ENABLE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_CANDIDATE"
DEFAULT_OPERATOR_CONFIRM_VALUE = "OPERATOR_CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ORDERS"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        p = Path(path)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "enable", "enabled"}


def _str_env(env: Mapping[str, str], key: str, default: str = "") -> str:
    try:
        return str(env.get(key, default) if env.get(key, default) is not None else default).strip()
    except Exception:
        return default


@dataclass(frozen=True)
class PaperUnlockGuardedEnableSettings:
    enabled: bool = True
    enable_name: str = ENABLE_NAME
    final_preflight_name: str = FINAL_PREFLIGHT_NAME
    activation_patch_name: str = ACTIVATION_PATCH_NAME
    switch_name: str = SWITCH_NAME
    profile_name: str = PROFILE_NAME
    experiment_name: str = EXPERIMENT_NAME
    required_final_preflight_decision: str = REQUIRED_FINAL_PREFLIGHT_DECISION
    required_selected_entries: int = 20
    required_cadence_variant: str = "bounded_6_daily_30_weekly_0h"
    manual_enable_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE"
    manual_confirm_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM"
    expected_manual_confirm_value: str = DEFAULT_SWITCH_CONFIRM_VALUE
    manual_activation_patch_env: str = "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH"
    manual_activation_confirm_env: str = "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM"
    expected_activation_confirm_value: str = DEFAULT_ACTIVATION_CONFIRM_VALUE
    final_enable_patch_env: str = "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH"
    final_enable_confirm_env: str = "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM"
    expected_final_confirm_value: str = DEFAULT_FINAL_CONFIRM_VALUE
    operator_enable_env: str = "PAPER_UNLOCK_OPERATOR_ENABLE_PAPER_ORDERS"
    operator_confirm_env: str = "PAPER_UNLOCK_OPERATOR_CONFIRM_PAPER_ORDERS"
    expected_operator_confirm_value: str = DEFAULT_OPERATOR_CONFIRM_VALUE
    requested_mode_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE"
    testnet_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET"
    live_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE"
    exchange_broker_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER"
    require_paper_mode: bool = True
    require_exchange_broker_blocked: bool = True
    require_two_step_manual_activation: bool = True
    require_activation_patch: bool = True
    require_activation_confirm: bool = True
    require_final_enable_patch: bool = True
    require_final_enable_confirm: bool = True
    require_operator_enable: bool = True
    require_operator_confirm: bool = True
    allow_operator_controlled_paper_orders: bool = True
    max_positions: int = 1
    risk_per_trade_pct: float = 0.0025
    max_daily_entries: int = 6
    max_weekly_entries: int = 30
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockGuardedEnableSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_ENABLED", True)),
            enable_name=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_NAME", ENABLE_NAME) or ENABLE_NAME),
            final_preflight_name=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_FINAL_PREFLIGHT_NAME", FINAL_PREFLIGHT_NAME) or FINAL_PREFLIGHT_NAME),
            activation_patch_name=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_PATCH_NAME", ACTIVATION_PATCH_NAME) or ACTIVATION_PATCH_NAME),
            switch_name=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_SWITCH_NAME", SWITCH_NAME) or SWITCH_NAME),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            experiment_name=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_EXPERIMENT_NAME", EXPERIMENT_NAME) or EXPERIMENT_NAME),
            required_final_preflight_decision=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_FINAL_PREFLIGHT_DECISION", REQUIRED_FINAL_PREFLIGHT_DECISION) or REQUIRED_FINAL_PREFLIGHT_DECISION),
            required_selected_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_SELECTED_ENTRIES", 20), 20)),
            required_cadence_variant=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h") or "bounded_6_daily_30_weekly_0h"),
            manual_enable_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE"),
            manual_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM"),
            expected_manual_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_MANUAL_CONFIRM_VALUE", DEFAULT_SWITCH_CONFIRM_VALUE) or DEFAULT_SWITCH_CONFIRM_VALUE),
            manual_activation_patch_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_PATCH_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH") or "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH"),
            manual_activation_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_ACTIVATION_CONFIRM_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM") or "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM"),
            expected_activation_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_ACTIVATION_CONFIRM_VALUE", DEFAULT_ACTIVATION_CONFIRM_VALUE) or DEFAULT_ACTIVATION_CONFIRM_VALUE),
            final_enable_patch_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_FINAL_ENABLE_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH") or "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH"),
            final_enable_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_FINAL_CONFIRM_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM") or "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM"),
            expected_final_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_FINAL_CONFIRM_VALUE", DEFAULT_FINAL_CONFIRM_VALUE) or DEFAULT_FINAL_CONFIRM_VALUE),
            operator_enable_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_OPERATOR_ENABLE_ENV", "PAPER_UNLOCK_OPERATOR_ENABLE_PAPER_ORDERS") or "PAPER_UNLOCK_OPERATOR_ENABLE_PAPER_ORDERS"),
            operator_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_OPERATOR_CONFIRM_ENV", "PAPER_UNLOCK_OPERATOR_CONFIRM_PAPER_ORDERS") or "PAPER_UNLOCK_OPERATOR_CONFIRM_PAPER_ORDERS"),
            expected_operator_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_EXPECTED_OPERATOR_CONFIRM_VALUE", DEFAULT_OPERATOR_CONFIRM_VALUE) or DEFAULT_OPERATOR_CONFIRM_VALUE),
            requested_mode_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUESTED_MODE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE"),
            testnet_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_TESTNET_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET"),
            live_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_LIVE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE"),
            exchange_broker_env=str(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_EXCHANGE_BROKER_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER"),
            require_paper_mode=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_PAPER_MODE", True)),
            require_exchange_broker_blocked=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_EXCHANGE_BROKER_BLOCKED", True)),
            require_two_step_manual_activation=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_TWO_STEP", True)),
            require_activation_patch=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_ACTIVATION_PATCH", True)),
            require_activation_confirm=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_ACTIVATION_CONFIRM", True)),
            require_final_enable_patch=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_FINAL_ENABLE_PATCH", True)),
            require_final_enable_confirm=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_FINAL_CONFIRM", True)),
            require_operator_enable=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_OPERATOR_ENABLE", True)),
            require_operator_confirm=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_REQUIRE_OPERATOR_CONFIRM", True)),
            allow_operator_controlled_paper_orders=bool(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_ALLOW_PAPER_ORDERS", True)),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_MAX_POSITIONS", 1), 1)),
            risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_RISK_PER_TRADE_PCT", 0.0025), 0.0025)),
            max_daily_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_MAX_DAILY_ENTRIES", 6), 6)),
            max_weekly_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_MAX_WEEKLY_ENTRIES", 30), 30)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_ABORT_MAX_CONSECUTIVE_LOSSES", 3), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_GUARDED_ENABLE_ABORT_MAX_DRAWDOWN_PCT", 1.0), 1.0)),
        )


def _final_preflight_guard(report: Mapping[str, Any], settings: PaperUnlockGuardedEnableSettings) -> dict[str, Any]:
    decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
    counts = report.get("counts", {}) if isinstance(report.get("counts"), dict) else {}
    final_contract = report.get("final_enable_contract", {}) if isinstance(report.get("final_enable_contract"), dict) else {}
    runtime_profile = report.get("runtime_profile_candidate", {}) if isinstance(report.get("runtime_profile_candidate"), dict) else {}

    report_status_ok = report.get("status") == "PASS"
    decision_ok = decision.get("status") == settings.required_final_preflight_decision
    final_preflight_name_ok = decision.get("final_preflight_name") == settings.final_preflight_name
    profile_name_ok = decision.get("profile_name") == settings.profile_name
    selected_entries = _safe_int(decision.get("selected_entries", counts.get("selected_entries", 0)), 0)
    selected_entries_ok = selected_entries >= settings.required_selected_entries
    candidate_allowed_ok = bool(decision.get("paper_order_activation_candidate_allowed", report.get("paper_order_activation_candidate_allowed", False)))
    negative_fail_closed_ok = bool(decision.get("negative_fail_closed_ok", False))
    final_enable_preflight_ok = bool(decision.get("final_enable_preflight_ok", False))
    activation_guard_ok = bool(decision.get("activation_patch_guard_ok", False))
    no_orders_ok = not bool(report.get("paper_orders_enabled", False)) and _safe_int(counts.get("orders_submitted", 0), 0) == 0 and _safe_int(counts.get("positions_opened", 0), 0) == 0
    live_testnet_block_ok = not bool(report.get("enables_live_or_testnet", False)) and not bool(report.get("operational_unlock_allowed", False))
    cadence_ok = final_contract.get("required_cadence_variant", settings.required_cadence_variant) == settings.required_cadence_variant
    runtime_policy_ok = (
        runtime_profile.get("entry_state_policy") == "CONFIRMATION_ONLY"
        and "CONFIRMATION" in list(runtime_profile.get("allowed_structure_states", []))
        and all(x in list(runtime_profile.get("blocked_structure_states", [])) for x in ["WAIT", "NO_STRUCTURE", "CONFLICT"])
    )
    guard = {
        "report_status_ok": report_status_ok,
        "decision_ok": decision_ok,
        "final_preflight_name_ok": final_preflight_name_ok,
        "profile_name_ok": profile_name_ok,
        "selected_entries": selected_entries,
        "required_selected_entries": settings.required_selected_entries,
        "selected_entries_ok": selected_entries_ok,
        "candidate_allowed_ok": candidate_allowed_ok,
        "negative_fail_closed_ok": negative_fail_closed_ok,
        "final_enable_preflight_ok": final_enable_preflight_ok,
        "activation_patch_guard_ok": activation_guard_ok,
        "no_orders_ok": no_orders_ok,
        "live_testnet_block_ok": live_testnet_block_ok,
        "cadence_ok": cadence_ok,
        "runtime_policy_ok": runtime_policy_ok,
        "counts": counts,
        "final_preflight_decision_status": decision.get("status", ""),
    }
    guard["passes_final_preflight_guard"] = all([
        report_status_ok,
        decision_ok,
        final_preflight_name_ok,
        profile_name_ok,
        selected_entries_ok,
        candidate_allowed_ok,
        negative_fail_closed_ok,
        final_enable_preflight_ok,
        activation_guard_ok,
        no_orders_ok,
        live_testnet_block_ok,
        cadence_ok,
        runtime_policy_ok,
    ])
    guard["failed_checks"] = [k for k, v in guard.items() if k.endswith("_ok") and v is False]
    return guard


def _evaluate_operator_controls(
    name: str,
    settings: PaperUnlockGuardedEnableSettings,
    env: Mapping[str, str],
    *,
    final_preflight_guard_ok: bool,
    enable_patch_context_present: bool,
    forced_mode: str | None = None,
    forced_live: bool | None = None,
    forced_testnet: bool | None = None,
    forced_exchange_broker: str | None = None,
) -> dict[str, Any]:
    manual_enable_ok = _str_env(env, settings.manual_enable_env, "") == "1"
    manual_confirm_ok = _str_env(env, settings.manual_confirm_env, "") == settings.expected_manual_confirm_value
    activation_patch_ok = _truthy(_str_env(env, settings.manual_activation_patch_env, "0")) if settings.require_activation_patch else True
    activation_confirm_ok = _str_env(env, settings.manual_activation_confirm_env, "") == settings.expected_activation_confirm_value if settings.require_activation_confirm else True
    final_enable_ok = _truthy(_str_env(env, settings.final_enable_patch_env, "0")) if settings.require_final_enable_patch else True
    final_confirm_ok = _str_env(env, settings.final_enable_confirm_env, "") == settings.expected_final_confirm_value if settings.require_final_enable_confirm else True
    operator_enable_ok = _truthy(_str_env(env, settings.operator_enable_env, "0")) if settings.require_operator_enable else True
    operator_confirm_ok = _str_env(env, settings.operator_confirm_env, "") == settings.expected_operator_confirm_value if settings.require_operator_confirm else True
    requested_mode = str(forced_mode if forced_mode is not None else (_str_env(env, settings.requested_mode_env, "paper") or "paper")).lower()
    live_requested = bool(forced_live) if forced_live is not None else _truthy(_str_env(env, settings.live_env, "0"))
    testnet_requested = bool(forced_testnet) if forced_testnet is not None else _truthy(_str_env(env, settings.testnet_env, "0"))
    exchange_broker_mode = str(forced_exchange_broker if forced_exchange_broker is not None else (_str_env(env, settings.exchange_broker_env, "blocked") or "blocked")).lower()

    two_step_ok = manual_enable_ok and manual_confirm_ok if settings.require_two_step_manual_activation else manual_enable_ok
    activation_stack_ok = activation_patch_ok and activation_confirm_ok
    final_step_ok = final_enable_ok and final_confirm_ok
    operator_step_ok = operator_enable_ok and operator_confirm_ok
    paper_mode_ok = (requested_mode == "paper") if settings.require_paper_mode else requested_mode in {"paper", "diagnostic"}
    live_testnet_block_ok = not live_requested and not testnet_requested and requested_mode not in {"live", "testnet"}
    exchange_broker_block_ok = exchange_broker_mode in {"", "blocked", "paper", "paper_only"} if settings.require_exchange_broker_blocked else True
    operator_enable_contract_ok = all([
        final_preflight_guard_ok,
        two_step_ok,
        activation_stack_ok,
        final_step_ok,
        operator_step_ok,
        paper_mode_ok,
        live_testnet_block_ok,
        exchange_broker_block_ok,
        enable_patch_context_present,
    ])
    paper_orders_enabled_in_this_patch = bool(settings.allow_operator_controlled_paper_orders and operator_enable_contract_ok)
    paper_unlock_experiment_allowed_in_this_patch = bool(paper_orders_enabled_in_this_patch)
    manual_activation_allowed_in_this_patch = bool(paper_orders_enabled_in_this_patch)
    # Operational unlock means live/testnet/exchange execution in this project. It remains blocked.
    operational_unlock_allowed_in_this_patch = False
    automatic_activation_allowed_in_this_patch = False
    live_or_testnet_allowed_in_this_patch = False
    exchange_broker_allowed_in_this_patch = False
    orders_submitted_in_this_patch = 0
    positions_opened_in_this_patch = 0
    fail_closed_when_not_authorized = (
        paper_orders_enabled_in_this_patch is False
        and paper_unlock_experiment_allowed_in_this_patch is False
        and manual_activation_allowed_in_this_patch is False
        and orders_submitted_in_this_patch == 0
        and positions_opened_in_this_patch == 0
        and operational_unlock_allowed_in_this_patch is False
    ) if not operator_enable_contract_ok else True
    return {
        "scenario": name,
        "final_preflight_guard_ok": bool(final_preflight_guard_ok),
        "manual_enable_ok": manual_enable_ok,
        "manual_confirm_ok": manual_confirm_ok,
        "two_step_ok": two_step_ok,
        "activation_patch_ok": activation_patch_ok,
        "activation_confirm_ok": activation_confirm_ok,
        "activation_stack_ok": activation_stack_ok,
        "final_enable_ok": final_enable_ok,
        "final_confirm_ok": final_confirm_ok,
        "final_step_ok": final_step_ok,
        "operator_enable_ok": operator_enable_ok,
        "operator_confirm_ok": operator_confirm_ok,
        "operator_step_ok": operator_step_ok,
        "enable_patch_context_present": bool(enable_patch_context_present),
        "requested_mode": requested_mode,
        "paper_mode_ok": paper_mode_ok,
        "live_requested": live_requested,
        "testnet_requested": testnet_requested,
        "live_testnet_block_ok": live_testnet_block_ok,
        "exchange_broker_mode": exchange_broker_mode,
        "exchange_broker_block_ok": exchange_broker_block_ok,
        "operator_enable_contract_ok": operator_enable_contract_ok,
        "paper_orders_enabled_in_this_patch": paper_orders_enabled_in_this_patch,
        "paper_unlock_experiment_allowed_in_this_patch": paper_unlock_experiment_allowed_in_this_patch,
        "manual_activation_allowed_in_this_patch": manual_activation_allowed_in_this_patch,
        "automatic_activation_allowed_in_this_patch": automatic_activation_allowed_in_this_patch,
        "operational_unlock_allowed_in_this_patch": operational_unlock_allowed_in_this_patch,
        "live_or_testnet_allowed_in_this_patch": live_or_testnet_allowed_in_this_patch,
        "exchange_broker_allowed_in_this_patch": exchange_broker_allowed_in_this_patch,
        "orders_submitted_in_this_patch": orders_submitted_in_this_patch,
        "positions_opened_in_this_patch": positions_opened_in_this_patch,
        "fail_closed_when_not_authorized": fail_closed_when_not_authorized,
        "block_reasons": [
            reason for reason, failed in [
                ("FINAL_PREFLIGHT_GUARD_NOT_PASS", not final_preflight_guard_ok),
                ("MANUAL_ENABLE_MISSING_OR_FALSE", not manual_enable_ok),
                ("MANUAL_CONFIRM_MISSING_OR_MISMATCH", not manual_confirm_ok),
                ("ACTIVATION_PATCH_FLAG_MISSING", not activation_patch_ok),
                ("ACTIVATION_CONFIRM_MISSING_OR_MISMATCH", not activation_confirm_ok),
                ("FINAL_ENABLE_FLAG_MISSING", not final_enable_ok),
                ("FINAL_ENABLE_CONFIRM_MISMATCH", not final_confirm_ok),
                ("OPERATOR_ENABLE_MISSING", not operator_enable_ok),
                ("OPERATOR_CONFIRM_MISMATCH", not operator_confirm_ok),
                ("ENABLE_PATCH_CONTEXT_REQUIRED", not enable_patch_context_present),
                ("MODE_NOT_PAPER", not paper_mode_ok),
                ("LIVE_OR_TESTNET_REQUESTED", not live_testnet_block_ok),
                ("EXCHANGE_BROKER_NOT_BLOCKED", not exchange_broker_block_ok),
            ] if failed
        ],
    }


def _valid_env(settings: PaperUnlockGuardedEnableSettings) -> dict[str, str]:
    return {
        settings.manual_enable_env: "1",
        settings.manual_confirm_env: settings.expected_manual_confirm_value,
        settings.manual_activation_patch_env: "1",
        settings.manual_activation_confirm_env: settings.expected_activation_confirm_value,
        settings.final_enable_patch_env: "1",
        settings.final_enable_confirm_env: settings.expected_final_confirm_value,
        settings.operator_enable_env: "1",
        settings.operator_confirm_env: settings.expected_operator_confirm_value,
        settings.requested_mode_env: "paper",
        settings.live_env: "0",
        settings.testnet_env: "0",
        settings.exchange_broker_env: "blocked",
    }


def _operator_enable_suite(settings: PaperUnlockGuardedEnableSettings, env: Mapping[str, str], final_preflight_guard_ok: bool) -> dict[str, Any]:
    valid_env = _valid_env(settings)
    scenarios = [
        _evaluate_operator_controls("actual_environment", settings, env, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True),
        _evaluate_operator_controls("missing_all_manual_env", settings, {}, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True),
        _evaluate_operator_controls("final_stack_without_operator_enable", settings, {k: v for k, v in valid_env.items() if k not in {settings.operator_enable_env, settings.operator_confirm_env}}, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True),
        _evaluate_operator_controls("operator_enable_without_final_stack", settings, {settings.operator_enable_env: "1", settings.operator_confirm_env: settings.expected_operator_confirm_value}, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True),
        _evaluate_operator_controls("operator_confirm_mismatch", settings, {**valid_env, settings.operator_confirm_env: "WRONG"}, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True),
        _evaluate_operator_controls("valid_controls_without_enable_patch_context", settings, valid_env, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=False),
        _evaluate_operator_controls("live_mode_requested", settings, valid_env, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True, forced_mode="live", forced_live=True),
        _evaluate_operator_controls("testnet_mode_requested", settings, valid_env, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True, forced_mode="testnet", forced_testnet=True),
        _evaluate_operator_controls("exchange_broker_available", settings, valid_env, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True, forced_exchange_broker="exchange"),
        _evaluate_operator_controls("valid_operator_controlled_paper_enable_simulation", settings, valid_env, final_preflight_guard_ok=final_preflight_guard_ok, enable_patch_context_present=True),
    ]
    by_name = {str(s.get("scenario")): s for s in scenarios}
    negative_names = [
        "missing_all_manual_env",
        "final_stack_without_operator_enable",
        "operator_enable_without_final_stack",
        "operator_confirm_mismatch",
        "valid_controls_without_enable_patch_context",
        "live_mode_requested",
        "testnet_mode_requested",
        "exchange_broker_available",
    ]
    negative_fail_closed_ok = all(
        bool(by_name[name].get("fail_closed_when_not_authorized", False))
        and not bool(by_name[name].get("operator_enable_contract_ok", False))
        and not bool(by_name[name].get("paper_orders_enabled_in_this_patch", False))
        and not bool(by_name[name].get("paper_unlock_experiment_allowed_in_this_patch", False))
        and not bool(by_name[name].get("manual_activation_allowed_in_this_patch", False))
        for name in negative_names
    )
    simulated_active = by_name["valid_operator_controlled_paper_enable_simulation"]
    operator_controlled_enable_ok = (
        bool(simulated_active.get("operator_enable_contract_ok", False))
        and bool(simulated_active.get("paper_orders_enabled_in_this_patch", False))
        and bool(simulated_active.get("paper_unlock_experiment_allowed_in_this_patch", False))
        and bool(simulated_active.get("manual_activation_allowed_in_this_patch", False))
        and not bool(simulated_active.get("automatic_activation_allowed_in_this_patch", False))
        and not bool(simulated_active.get("operational_unlock_allowed_in_this_patch", False))
        and not bool(simulated_active.get("live_or_testnet_allowed_in_this_patch", False))
        and not bool(simulated_active.get("exchange_broker_allowed_in_this_patch", False))
        and _safe_int(simulated_active.get("orders_submitted_in_this_patch", 0), 0) == 0
        and _safe_int(simulated_active.get("positions_opened_in_this_patch", 0), 0) == 0
    )
    actual = by_name["actual_environment"]
    actual_paper_orders_enabled = bool(actual.get("paper_orders_enabled_in_this_patch", False))
    all_no_real_orders = all(
        _safe_int(s.get("orders_submitted_in_this_patch", 0), 0) == 0
        and _safe_int(s.get("positions_opened_in_this_patch", 0), 0) == 0
        and not bool(s.get("operational_unlock_allowed_in_this_patch", False))
        and not bool(s.get("live_or_testnet_allowed_in_this_patch", False))
        for s in scenarios
    )
    return {
        "scenarios": scenarios,
        "negative_fail_closed_ok": negative_fail_closed_ok,
        "operator_controlled_enable_ok": operator_controlled_enable_ok,
        "operator_controlled_paper_enable_simulation": simulated_active,
        "actual_environment": actual,
        "actual_paper_orders_enabled": actual_paper_orders_enabled,
        "all_scenarios_no_real_orders_ok": all_no_real_orders,
        "passes_operator_enable_suite": bool(final_preflight_guard_ok and negative_fail_closed_ok and operator_controlled_enable_ok and all_no_real_orders),
    }


def build_paper_unlock_guarded_enable_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockGuardedEnableSettings | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockGuardedEnableSettings.from_config()
    env = dict(os.environ if env is None else env)
    base = Path(base_dir)
    final_preflight_path = base / FINAL_PREFLIGHT_REPORT_NAME
    final_preflight_report = _read_json(final_preflight_path)
    final_guard = _final_preflight_guard(final_preflight_report, settings)
    suite = _operator_enable_suite(settings, env, bool(final_guard.get("passes_final_preflight_guard", False)))
    implementation_ready = bool(settings.enabled and final_guard.get("passes_final_preflight_guard", False) and suite.get("passes_operator_enable_suite", False))
    actual = suite.get("actual_environment", {}) if isinstance(suite.get("actual_environment"), dict) else {}
    actual_paper_orders_enabled = bool(implementation_ready and actual.get("paper_orders_enabled_in_this_patch", False))
    actual_paper_unlock_experiment_allowed = bool(implementation_ready and actual.get("paper_unlock_experiment_allowed_in_this_patch", False))
    actual_manual_activation_allowed = bool(implementation_ready and actual.get("manual_activation_allowed_in_this_patch", False))
    if actual_paper_orders_enabled:
        decision_status = ACTIVE_DECISION
        reason = "Operator-controlled paper-only enable is active for paper orders; live/testnet/exchange broker remain blocked and no orders are submitted by this report."
        next_patch = "29.4.4o paper-only runtime order audit / first controlled paper-cycle monitoring, still no live/testnet."
    elif implementation_ready:
        decision_status = READY_DECISION
        reason = "Guarded paper-only enable implementation is ready and fail-closed; set explicit operator controls to enable paper orders in a paper-only runtime."
        next_patch = "Set operator controls only for a supervised paper-only run, or proceed to 29.4.4o runtime paper-order audit after activation."
    else:
        decision_status = KEEP_DECISION
        reason = "Guarded paper-only enable implementation did not pass final preflight or operator-control suite; paper orders remain disabled."
        next_patch = "Repair guarded paper-only enable failures before operator-controlled paper orders."
    counts = final_guard.get("counts", {}) if isinstance(final_guard.get("counts"), dict) else {}
    selected_entries = final_guard.get("selected_entries", counts.get("selected_entries", 0))
    report = {
        "prompt": PROMPT_ID,
        "report_type": "paper_unlock_guarded_enable",
        "generated_at": utc_now_iso(),
        "status": "PASS" if implementation_ready else "WARN",
        "enable_name": settings.enable_name,
        "final_preflight_name": settings.final_preflight_name,
        "activation_patch_name": settings.activation_patch_name,
        "switch_name": settings.switch_name,
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "paper_only": True,
        "operator_controlled": True,
        "diagnostic_only": not actual_paper_orders_enabled,
        "opens_orders": False,
        "orders_submitted": 0,
        "positions_opened": 0,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "changes_risk": False,
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": actual_paper_unlock_experiment_allowed,
        "paper_orders_enabled": actual_paper_orders_enabled,
        "profile_activation_allowed": actual_manual_activation_allowed,
        "automatic_activation_allowed": False,
        "manual_activation_allowed": actual_manual_activation_allowed,
        "exchange_broker_allowed": False,
        "live_allowed": False,
        "testnet_allowed": False,
        "paper_order_activation_candidate_allowed": bool(final_guard.get("candidate_allowed_ok", False)),
        "runtime_enable_contract": {
            "enable_name": settings.enable_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "entry_state_policy": "CONFIRMATION_ONLY",
            "allowed_structure_states": ["CONFIRMATION"],
            "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
            "map_score_min": 65.0,
            "map_score_max": 79.999,
            "max_positions": settings.max_positions,
            "risk_per_trade_pct": settings.risk_per_trade_pct,
            "max_daily_entries": settings.max_daily_entries,
            "max_weekly_entries": settings.max_weekly_entries,
            "abort_max_consecutive_losses": settings.abort_max_consecutive_losses,
            "abort_max_drawdown_pct": settings.abort_max_drawdown_pct,
            "paper_orders_enabled": actual_paper_orders_enabled,
            "manual_activation_allowed": actual_manual_activation_allowed,
            "automatic_activation_allowed": False,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
        },
        "manual_operator_controls": {
            "manual_enable_env": settings.manual_enable_env,
            "manual_enable_required_value": "1",
            "manual_confirm_env": settings.manual_confirm_env,
            "manual_confirm_required_value": settings.expected_manual_confirm_value,
            "activation_patch_env": settings.manual_activation_patch_env,
            "activation_patch_required_value": "1",
            "activation_confirm_env": settings.manual_activation_confirm_env,
            "activation_confirm_required_value": settings.expected_activation_confirm_value,
            "final_enable_env": settings.final_enable_patch_env,
            "final_enable_required_value": "1",
            "final_confirm_env": settings.final_enable_confirm_env,
            "final_confirm_required_value": settings.expected_final_confirm_value,
            "operator_enable_env": settings.operator_enable_env,
            "operator_enable_required_value": "1",
            "operator_confirm_env": settings.operator_confirm_env,
            "operator_confirm_required_value": settings.expected_operator_confirm_value,
            "requested_mode_env": settings.requested_mode_env,
            "required_mode": "paper" if settings.require_paper_mode else "paper_or_diagnostic",
            "testnet_env": settings.testnet_env,
            "testnet_required_value": "0",
            "live_env": settings.live_env,
            "live_required_value": "0",
            "exchange_broker_env": settings.exchange_broker_env,
            "exchange_broker_required_state": "blocked",
        },
        "final_preflight_guard": final_guard,
        "operator_enable_suite": suite,
        "safety_matrix": {
            "paper_only": True,
            "operator_controlled": True,
            "live_block": True,
            "testnet_block": True,
            "exchange_broker_blocked": True,
            "automatic_activation_blocked": True,
            "negative_fail_closed_ok": bool(suite.get("negative_fail_closed_ok", False)),
            "operator_controlled_enable_ok": bool(suite.get("operator_controlled_enable_ok", False)),
            "actual_paper_orders_enabled": actual_paper_orders_enabled,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "counts": {
            "source_target_rows": counts.get("source_target_rows", 0),
            "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
            "selected_entries": selected_entries,
            "operator_enable_scenarios": len(suite.get("scenarios", [])),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "decision": {
            "status": decision_status,
            "reason": reason,
            "next_patch": next_patch,
            "enable_name": settings.enable_name,
            "final_preflight_name": settings.final_preflight_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "selected_entries": selected_entries,
            "final_preflight_guard_ok": bool(final_guard.get("passes_final_preflight_guard", False)),
            "operator_enable_suite_ok": bool(suite.get("passes_operator_enable_suite", False)),
            "negative_fail_closed_ok": bool(suite.get("negative_fail_closed_ok", False)),
            "operator_controlled_enable_ok": bool(suite.get("operator_controlled_enable_ok", False)),
            "actual_operator_enable_contract_ok": bool(actual.get("operator_enable_contract_ok", False)),
            "paper_orders_enabled": actual_paper_orders_enabled,
            "paper_unlock_experiment_allowed": actual_paper_unlock_experiment_allowed,
            "manual_activation_allowed": actual_manual_activation_allowed,
            "automatic_activation_allowed": False,
            "operational_unlock_allowed": False,
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "files": {
            "report": str(base / REPORT_NAME),
            "final_enable_preflight": str(final_preflight_path),
            "manual_activation_patch": str(base / "paper_unlock_manual_activation_patch_report.json"),
            "manual_switch_preflight": str(base / "paper_unlock_manual_switch_preflight_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_guarded_enable_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockGuardedEnableSettings | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_guarded_enable_report(base, settings, env=env)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
