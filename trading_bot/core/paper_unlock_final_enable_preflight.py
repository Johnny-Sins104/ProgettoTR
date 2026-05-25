"""Prompt 29.4.4m final manual paper-only enable preflight.

This module validates the full manual paper-only activation chain after 29.4.4l.
It produces a paper-order activation *candidate* report, but it does not submit
orders and does not enable live, testnet or an exchange broker.  The goal is to
prove the final manual controls are fail-closed before any later operator-run
paper-only experiment implementation.
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

REPORT_NAME = "paper_unlock_final_enable_preflight_report.json"
PROMPT_ID = "29.4.4m"
ACTIVATION_PATCH_REPORT_NAME = "paper_unlock_manual_activation_patch_report.json"
ACTIVATION_PATCH_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT"
FINAL_ENABLE_PREFLIGHT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT"
PREFLIGHT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT"
SWITCH_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT"
PROFILE_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"
EXPERIMENT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN"
REQUIRED_ACTIVATION_PATCH_DECISION = "EXPLICIT_MANUAL_PAPER_ACTIVATION_PATCH_DRAFT_READY_DIAGNOSTIC"
READY_DECISION = "FINAL_MANUAL_PAPER_ENABLE_PREFLIGHT_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"
DEFAULT_SWITCH_CONFIRM_VALUE = "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY"
DEFAULT_ACTIVATION_CONFIRM_VALUE = "ACTIVATE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_DRAFT"
DEFAULT_FINAL_CONFIRM_VALUE = "ENABLE_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY_CANDIDATE"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaperUnlockFinalEnablePreflightSettings:
    enabled: bool = True
    final_preflight_name: str = FINAL_ENABLE_PREFLIGHT_NAME
    activation_patch_name: str = ACTIVATION_PATCH_NAME
    preflight_name: str = PREFLIGHT_NAME
    switch_name: str = SWITCH_NAME
    profile_name: str = PROFILE_NAME
    experiment_name: str = EXPERIMENT_NAME
    required_activation_patch_decision: str = REQUIRED_ACTIVATION_PATCH_DECISION
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
    allow_paper_order_activation_candidate: bool = True
    max_positions: int = 1
    risk_per_trade_pct: float = 0.0025
    max_daily_entries: int = 6
    max_weekly_entries: int = 30
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockFinalEnablePreflightSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ENABLED", True)),
            final_preflight_name=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_NAME", FINAL_ENABLE_PREFLIGHT_NAME) or FINAL_ENABLE_PREFLIGHT_NAME),
            activation_patch_name=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_PATCH_NAME", ACTIVATION_PATCH_NAME) or ACTIVATION_PATCH_NAME),
            preflight_name=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_PREFLIGHT_NAME", PREFLIGHT_NAME) or PREFLIGHT_NAME),
            switch_name=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_SWITCH_NAME", SWITCH_NAME) or SWITCH_NAME),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            experiment_name=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPERIMENT_NAME", EXPERIMENT_NAME) or EXPERIMENT_NAME),
            required_activation_patch_decision=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_ACTIVATION_DECISION", REQUIRED_ACTIVATION_PATCH_DECISION) or REQUIRED_ACTIVATION_PATCH_DECISION),
            required_selected_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_SELECTED_ENTRIES", 20), 20)),
            required_cadence_variant=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h") or "bounded_6_daily_30_weekly_0h"),
            manual_enable_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE"),
            manual_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM"),
            expected_manual_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_MANUAL_CONFIRM_VALUE", DEFAULT_SWITCH_CONFIRM_VALUE) or DEFAULT_SWITCH_CONFIRM_VALUE),
            manual_activation_patch_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_PATCH_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH") or "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_PATCH"),
            manual_activation_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ACTIVATION_CONFIRM_ENV", "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM") or "PAPER_UNLOCK_EXPLICIT_MANUAL_ACTIVATION_CONFIRM"),
            expected_activation_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_ACTIVATION_CONFIRM_VALUE", DEFAULT_ACTIVATION_CONFIRM_VALUE) or DEFAULT_ACTIVATION_CONFIRM_VALUE),
            final_enable_patch_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_FINAL_ENABLE_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH") or "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_PATCH"),
            final_enable_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_FINAL_CONFIRM_ENV", "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM") or "PAPER_UNLOCK_FINAL_MANUAL_ENABLE_CONFIRM"),
            expected_final_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXPECTED_FINAL_CONFIRM_VALUE", DEFAULT_FINAL_CONFIRM_VALUE) or DEFAULT_FINAL_CONFIRM_VALUE),
            requested_mode_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUESTED_MODE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE"),
            testnet_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_TESTNET_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET"),
            live_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_LIVE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE"),
            exchange_broker_env=str(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_EXCHANGE_BROKER_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER"),
            require_paper_mode=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_PAPER_MODE", True)),
            require_exchange_broker_blocked=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_EXCHANGE_BROKER_BLOCKED", True)),
            require_two_step_manual_activation=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_TWO_STEP", True)),
            require_activation_patch=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_ACTIVATION_PATCH", True)),
            require_activation_confirm=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_ACTIVATION_CONFIRM", True)),
            require_final_enable_patch=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_FINAL_ENABLE_PATCH", True)),
            require_final_enable_confirm=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_REQUIRE_FINAL_CONFIRM", True)),
            allow_paper_order_activation_candidate=bool(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ALLOW_CANDIDATE", True)),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_POSITIONS", 1), 1)),
            risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_RISK_PER_TRADE_PCT", 0.0025), 0.0025)),
            max_daily_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_DAILY_ENTRIES", 6), 6)),
            max_weekly_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_MAX_WEEKLY_ENTRIES", 30), 30)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ABORT_MAX_CONSECUTIVE_LOSSES", 3), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ABORT_MAX_DRAWDOWN_PCT", 1.0), 1.0)),
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


def _str_env(env: Mapping[str, str], key: str, default: str = "") -> str:
    value = env.get(key, default)
    if value is None:
        return default
    return str(value)


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _activation_patch_guard(activation_report: dict[str, Any], settings: PaperUnlockFinalEnablePreflightSettings) -> dict[str, Any]:
    decision = _decision(activation_report)
    preflight_guard = activation_report.get("preflight_guard", {}) if isinstance(activation_report.get("preflight_guard"), dict) else {}
    suite = activation_report.get("activation_preflight_suite", {}) if isinstance(activation_report.get("activation_preflight_suite"), dict) else {}
    counts = activation_report.get("counts", {}) if isinstance(activation_report.get("counts"), dict) else {}
    report_status_ok = str(activation_report.get("status") or "").upper() == "PASS"
    decision_ok = str(decision.get("status") or "") == settings.required_activation_patch_decision
    activation_patch_name_ok = str(decision.get("activation_patch_name") or activation_report.get("activation_patch_name") or "") == settings.activation_patch_name
    preflight_name_ok = str(decision.get("preflight_name") or activation_report.get("preflight_name") or "") == settings.preflight_name
    switch_name_ok = str(decision.get("switch_name") or activation_report.get("switch_name") or "") == settings.switch_name
    profile_name_ok = str(decision.get("profile_name") or activation_report.get("profile_name") or "") == settings.profile_name
    selected_entries = _safe_int(decision.get("selected_entries", counts.get("selected_entries", 0)), 0)
    selected_entries_ok = selected_entries >= settings.required_selected_entries
    preflight_guard_ok = bool(decision.get("preflight_guard_ok", False)) or bool(preflight_guard.get("passes_preflight_guard", False))
    activation_preflight_ok = bool(decision.get("activation_preflight_ok", False)) or bool(suite.get("passes_activation_preflight_suite", False))
    negative_fail_closed_ok = bool(decision.get("negative_fail_closed_ok", False)) or bool(suite.get("negative_fail_closed_ok", False))
    future_activation_simulation_ok = bool(decision.get("future_activation_simulation_ok", False)) or bool(suite.get("future_activation_simulation_ok", False))
    cadence_ok = str(preflight_guard.get("required_cadence_variant") or settings.required_cadence_variant) == settings.required_cadence_variant
    execution_disabled_ok = (
        not bool(activation_report.get("operational_unlock_allowed", False))
        and not bool(activation_report.get("paper_unlock_experiment_allowed", False))
        and not bool(activation_report.get("paper_orders_enabled", False))
        and not bool(activation_report.get("manual_activation_allowed", False))
        and not bool(activation_report.get("automatic_activation_allowed", False))
    )
    no_orders_ok = _safe_int(counts.get("orders_submitted", 0), 0) == 0 and _safe_int(counts.get("positions_opened", 0), 0) == 0
    guard = {
        "report_status_ok": report_status_ok,
        "decision_ok": decision_ok,
        "activation_patch_name_ok": activation_patch_name_ok,
        "preflight_name_ok": preflight_name_ok,
        "switch_name_ok": switch_name_ok,
        "profile_name_ok": profile_name_ok,
        "selected_entries": selected_entries,
        "required_selected_entries": settings.required_selected_entries,
        "selected_entries_ok": selected_entries_ok,
        "required_cadence_variant": settings.required_cadence_variant,
        "cadence_ok": cadence_ok,
        "preflight_guard_ok": preflight_guard_ok,
        "activation_preflight_ok": activation_preflight_ok,
        "negative_fail_closed_ok": negative_fail_closed_ok,
        "future_activation_simulation_ok": future_activation_simulation_ok,
        "execution_disabled_ok": execution_disabled_ok,
        "no_orders_ok": no_orders_ok,
        "counts": counts,
        "activation_patch_decision_status": decision.get("status", ""),
    }
    guard["passes_activation_patch_guard"] = all([
        report_status_ok,
        decision_ok,
        activation_patch_name_ok,
        preflight_name_ok,
        switch_name_ok,
        profile_name_ok,
        selected_entries_ok,
        cadence_ok,
        preflight_guard_ok,
        activation_preflight_ok,
        negative_fail_closed_ok,
        future_activation_simulation_ok,
        execution_disabled_ok,
        no_orders_ok,
    ])
    guard["failed_checks"] = [k for k, v in guard.items() if k.endswith("_ok") and v is False]
    return guard


def _evaluate_final_enable_controls(
    name: str,
    settings: PaperUnlockFinalEnablePreflightSettings,
    env: Mapping[str, str],
    *,
    activation_patch_guard_ok: bool,
    final_patch_context_present: bool,
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
    requested_mode = str(forced_mode if forced_mode is not None else (_str_env(env, settings.requested_mode_env, "paper") or "paper")).lower()
    live_requested = bool(forced_live) if forced_live is not None else _truthy(_str_env(env, settings.live_env, "0"))
    testnet_requested = bool(forced_testnet) if forced_testnet is not None else _truthy(_str_env(env, settings.testnet_env, "0"))
    exchange_broker_mode = str(forced_exchange_broker if forced_exchange_broker is not None else (_str_env(env, settings.exchange_broker_env, "blocked") or "blocked")).lower()

    two_step_ok = manual_enable_ok and manual_confirm_ok if settings.require_two_step_manual_activation else manual_enable_ok
    activation_stack_ok = activation_patch_ok and activation_confirm_ok
    final_step_ok = final_enable_ok and final_confirm_ok
    paper_mode_ok = (requested_mode == "paper") if settings.require_paper_mode else requested_mode in {"paper", "diagnostic"}
    live_testnet_block_ok = not live_requested and not testnet_requested and requested_mode not in {"live", "testnet"}
    exchange_broker_block_ok = exchange_broker_mode in {"", "blocked", "paper", "paper_only"} if settings.require_exchange_broker_blocked else True
    final_enable_contract_ok = all([
        activation_patch_guard_ok,
        two_step_ok,
        activation_stack_ok,
        final_step_ok,
        paper_mode_ok,
        live_testnet_block_ok,
        exchange_broker_block_ok,
        final_patch_context_present,
    ])
    paper_order_activation_candidate_allowed = bool(settings.allow_paper_order_activation_candidate and final_enable_contract_ok)
    # This patch is a final preflight/candidate. It never submits orders by itself.
    paper_orders_enabled_in_this_patch = False
    positions_opened_in_this_patch = False
    orders_submitted_in_this_patch = False
    operational_unlock_allowed_in_this_patch = False
    manual_activation_allowed_in_this_patch = False
    fail_closed_for_real_execution = (
        not paper_orders_enabled_in_this_patch
        and not positions_opened_in_this_patch
        and not orders_submitted_in_this_patch
        and not operational_unlock_allowed_in_this_patch
        and not manual_activation_allowed_in_this_patch
    )
    return {
        "scenario": name,
        "activation_patch_guard_ok": bool(activation_patch_guard_ok),
        "manual_enable_ok": manual_enable_ok,
        "manual_confirm_ok": manual_confirm_ok,
        "two_step_ok": two_step_ok,
        "activation_patch_ok": activation_patch_ok,
        "activation_confirm_ok": activation_confirm_ok,
        "activation_stack_ok": activation_stack_ok,
        "final_enable_ok": final_enable_ok,
        "final_confirm_ok": final_confirm_ok,
        "final_step_ok": final_step_ok,
        "final_patch_context_present": bool(final_patch_context_present),
        "requested_mode": requested_mode,
        "paper_mode_ok": paper_mode_ok,
        "live_requested": live_requested,
        "testnet_requested": testnet_requested,
        "live_testnet_block_ok": live_testnet_block_ok,
        "exchange_broker_mode": exchange_broker_mode,
        "exchange_broker_block_ok": exchange_broker_block_ok,
        "final_enable_contract_ok": final_enable_contract_ok,
        "paper_order_activation_candidate_allowed": paper_order_activation_candidate_allowed,
        "paper_orders_enabled_in_this_patch": paper_orders_enabled_in_this_patch,
        "orders_submitted_in_this_patch": orders_submitted_in_this_patch,
        "positions_opened_in_this_patch": positions_opened_in_this_patch,
        "operational_unlock_allowed_in_this_patch": operational_unlock_allowed_in_this_patch,
        "manual_activation_allowed_in_this_patch": manual_activation_allowed_in_this_patch,
        "fail_closed_for_real_execution": fail_closed_for_real_execution,
        "block_reasons": [
            reason for reason, failed in [
                ("ACTIVATION_PATCH_GUARD_NOT_PASS", not activation_patch_guard_ok),
                ("MANUAL_ENABLE_MISSING_OR_FALSE", not manual_enable_ok),
                ("MANUAL_CONFIRM_MISSING_OR_MISMATCH", not manual_confirm_ok),
                ("ACTIVATION_PATCH_FLAG_MISSING", not activation_patch_ok),
                ("ACTIVATION_CONFIRM_MISSING_OR_MISMATCH", not activation_confirm_ok),
                ("FINAL_ENABLE_FLAG_MISSING", not final_enable_ok),
                ("FINAL_ENABLE_CONFIRM_MISMATCH", not final_confirm_ok),
                ("FINAL_PATCH_CONTEXT_REQUIRED", not final_patch_context_present),
                ("MODE_NOT_PAPER", not paper_mode_ok),
                ("LIVE_OR_TESTNET_REQUESTED", not live_testnet_block_ok),
                ("EXCHANGE_BROKER_NOT_BLOCKED", not exchange_broker_block_ok),
                ("REAL_ORDER_EXECUTION_DISABLED_IN_PREFLIGHT", not paper_orders_enabled_in_this_patch),
            ] if failed
        ],
    }


def _final_enable_preflight_suite(settings: PaperUnlockFinalEnablePreflightSettings, env: Mapping[str, str], activation_patch_guard_ok: bool) -> dict[str, Any]:
    valid_env = {
        settings.manual_enable_env: "1",
        settings.manual_confirm_env: settings.expected_manual_confirm_value,
        settings.manual_activation_patch_env: "1",
        settings.manual_activation_confirm_env: settings.expected_activation_confirm_value,
        settings.final_enable_patch_env: "1",
        settings.final_enable_confirm_env: settings.expected_final_confirm_value,
        settings.requested_mode_env: "paper",
        settings.live_env: "0",
        settings.testnet_env: "0",
        settings.exchange_broker_env: "blocked",
    }
    scenarios = [
        _evaluate_final_enable_controls("actual_environment", settings, env, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=False),
        _evaluate_final_enable_controls("missing_all_manual_env", settings, {}, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=False),
        _evaluate_final_enable_controls("switch_stack_without_final_enable", settings, {
            settings.manual_enable_env: "1",
            settings.manual_confirm_env: settings.expected_manual_confirm_value,
            settings.manual_activation_patch_env: "1",
            settings.manual_activation_confirm_env: settings.expected_activation_confirm_value,
        }, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=False),
        _evaluate_final_enable_controls("final_enable_without_switch_stack", settings, {
            settings.final_enable_patch_env: "1",
            settings.final_enable_confirm_env: settings.expected_final_confirm_value,
        }, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=False),
        _evaluate_final_enable_controls("final_confirm_mismatch", settings, {**valid_env, settings.final_enable_confirm_env: "WRONG"}, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=True),
        _evaluate_final_enable_controls("live_mode_requested", settings, valid_env, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=True, forced_mode="live", forced_live=True),
        _evaluate_final_enable_controls("testnet_mode_requested", settings, valid_env, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=True, forced_mode="testnet", forced_testnet=True),
        _evaluate_final_enable_controls("exchange_broker_available", settings, valid_env, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=True, forced_exchange_broker="exchange"),
        _evaluate_final_enable_controls("valid_final_controls_without_final_patch_context", settings, valid_env, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=False),
        _evaluate_final_enable_controls("valid_final_controls_paper_order_candidate_simulation", settings, valid_env, activation_patch_guard_ok=activation_patch_guard_ok, final_patch_context_present=True),
    ]
    by_name = {str(s.get("scenario")): s for s in scenarios}
    negative_names = [
        "missing_all_manual_env",
        "switch_stack_without_final_enable",
        "final_enable_without_switch_stack",
        "final_confirm_mismatch",
        "live_mode_requested",
        "testnet_mode_requested",
        "exchange_broker_available",
        "valid_final_controls_without_final_patch_context",
    ]
    negative_fail_closed_ok = all(
        bool(by_name[name].get("fail_closed_for_real_execution", False))
        and not bool(by_name[name].get("final_enable_contract_ok", False))
        and not bool(by_name[name].get("paper_order_activation_candidate_allowed", False))
        and not bool(by_name[name].get("paper_orders_enabled_in_this_patch", False))
        for name in negative_names
    )
    candidate = by_name["valid_final_controls_paper_order_candidate_simulation"]
    paper_order_activation_candidate_ok = (
        bool(candidate.get("final_enable_contract_ok", False))
        and bool(candidate.get("paper_order_activation_candidate_allowed", False))
        and bool(candidate.get("fail_closed_for_real_execution", False))
        and not bool(candidate.get("paper_orders_enabled_in_this_patch", False))
        and not bool(candidate.get("orders_submitted_in_this_patch", False))
    )
    all_no_real_orders = all(
        not bool(s.get("paper_orders_enabled_in_this_patch", False))
        and not bool(s.get("orders_submitted_in_this_patch", False))
        and not bool(s.get("positions_opened_in_this_patch", False))
        and not bool(s.get("operational_unlock_allowed_in_this_patch", False))
        for s in scenarios
    )
    return {
        "scenarios": scenarios,
        "negative_fail_closed_ok": negative_fail_closed_ok,
        "paper_order_activation_candidate_ok": paper_order_activation_candidate_ok,
        "paper_order_activation_candidate": candidate,
        "all_scenarios_no_real_orders_ok": all_no_real_orders,
        "actual_environment": by_name["actual_environment"],
        "passes_final_enable_preflight_suite": bool(activation_patch_guard_ok and negative_fail_closed_ok and paper_order_activation_candidate_ok and all_no_real_orders),
    }


def build_paper_unlock_final_enable_preflight_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockFinalEnablePreflightSettings | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockFinalEnablePreflightSettings.from_config()
    env = dict(os.environ if env is None else env)
    base = Path(base_dir)
    activation_path = base / ACTIVATION_PATCH_REPORT_NAME
    activation_report = _read_json(activation_path)
    activation_guard = _activation_patch_guard(activation_report, settings)
    suite = _final_enable_preflight_suite(settings, env, bool(activation_guard.get("passes_activation_patch_guard", False)))
    ready = bool(settings.enabled and activation_guard.get("passes_activation_patch_guard", False) and suite.get("passes_final_enable_preflight_suite", False))
    decision_status = READY_DECISION if ready else KEEP_DECISION
    reason = (
        "Final manual paper-only enable preflight passed. A paper-order activation candidate exists, but this patch submits no orders and keeps live/testnet blocked."
        if ready else
        "Final manual paper-only enable preflight did not pass or prerequisite activation patch draft failed; execution remains disabled."
    )
    next_patch = (
        "29.4.4n guarded paper-only experiment enable implementation / operator-controlled paper orders, still no live/testnet."
        if ready else
        "Repair final manual enable preflight failures before any paper-order enable implementation."
    )
    counts = activation_guard.get("counts", {}) if isinstance(activation_guard.get("counts"), dict) else {}
    selected_entries = activation_guard.get("selected_entries", counts.get("selected_entries", 0))
    activation_candidate = suite.get("paper_order_activation_candidate", {}) if isinstance(suite.get("paper_order_activation_candidate"), dict) else {}
    report = {
        "prompt": PROMPT_ID,
        "report_type": "paper_unlock_final_enable_preflight",
        "generated_at": utc_now_iso(),
        "status": "PASS" if ready else "WARN",
        "final_preflight_name": settings.final_preflight_name,
        "activation_patch_name": settings.activation_patch_name,
        "preflight_name": settings.preflight_name,
        "switch_name": settings.switch_name,
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "diagnostic_only": True,
        "paper_only": True,
        "final_preflight_only": True,
        "opens_orders": False,
        "enables_live_or_testnet": False,
        "changes_thresholds": False,
        "changes_risk": False,
        "operational_unlock_allowed": False,
        "paper_unlock_experiment_allowed": False,
        "paper_orders_enabled": False,
        "profile_activation_allowed": False,
        "automatic_activation_allowed": False,
        "manual_activation_allowed": False,
        "paper_order_activation_candidate_allowed": bool(ready and suite.get("paper_order_activation_candidate_ok", False)),
        "exchange_broker_allowed": False,
        "final_enable_contract": {
            "final_preflight_name": settings.final_preflight_name,
            "paper_order_activation_candidate_allowed": bool(ready and suite.get("paper_order_activation_candidate_ok", False)),
            "paper_orders_enabled_in_this_patch": False,
            "orders_submitted_in_this_patch": 0,
            "positions_opened_in_this_patch": 0,
            "manual_activation_allowed_in_this_patch": False,
            "automatic_activation_allowed": False,
            "live_allowed": False,
            "testnet_allowed": False,
            "exchange_broker_allowed": False,
            "required_activation_patch_decision": settings.required_activation_patch_decision,
            "required_activation_patch_name": settings.activation_patch_name,
            "required_profile_name": settings.profile_name,
            "required_selected_entries": settings.required_selected_entries,
            "required_cadence_variant": settings.required_cadence_variant,
        },
        "manual_final_enable_controls": {
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
            "requested_mode_env": settings.requested_mode_env,
            "required_mode": "paper" if settings.require_paper_mode else "paper_or_diagnostic",
            "testnet_env": settings.testnet_env,
            "live_env": settings.live_env,
            "exchange_broker_env": settings.exchange_broker_env,
            "exchange_broker_required_state": "blocked",
        },
        "runtime_profile_candidate": {
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
            "paper_orders_enabled_in_this_patch": False,
        },
        "activation_patch_guard": activation_guard,
        "final_enable_preflight_suite": suite,
        "safety_matrix": {
            "paper_only": True,
            "live_block": True,
            "testnet_block": True,
            "exchange_broker_blocked": True,
            "paper_orders_blocked_this_patch": True,
            "automatic_activation_blocked": True,
            "manual_activation_blocked_this_patch": True,
            "paper_order_activation_candidate_ok": bool(suite.get("paper_order_activation_candidate_ok", False)),
            "negative_fail_closed_ok": bool(suite.get("negative_fail_closed_ok", False)),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "counts": {
            "source_target_rows": counts.get("source_target_rows", 0),
            "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
            "selected_entries": selected_entries,
            "final_enable_preflight_scenarios": len(suite.get("scenarios", [])),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "decision": {
            "status": decision_status,
            "reason": reason,
            "next_patch": next_patch,
            "final_preflight_name": settings.final_preflight_name,
            "activation_patch_name": settings.activation_patch_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "selected_entries": selected_entries,
            "activation_patch_guard_ok": bool(activation_guard.get("passes_activation_patch_guard", False)),
            "final_enable_preflight_ok": bool(suite.get("passes_final_enable_preflight_suite", False)),
            "negative_fail_closed_ok": bool(suite.get("negative_fail_closed_ok", False)),
            "paper_order_activation_candidate_ok": bool(suite.get("paper_order_activation_candidate_ok", False)),
            "paper_order_activation_candidate_allowed": bool(ready and suite.get("paper_order_activation_candidate_ok", False)),
            "candidate_scenario": activation_candidate.get("scenario", ""),
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": False,
            "manual_activation_allowed": False,
        },
        "files": {
            "report": str(base / REPORT_NAME),
            "manual_activation_patch": str(activation_path),
            "manual_switch_preflight": str(base / "paper_unlock_manual_switch_preflight_report.json"),
            "experiment_switch_draft": str(base / "paper_unlock_experiment_switch_draft_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_final_enable_preflight_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockFinalEnablePreflightSettings | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_final_enable_preflight_report(base, settings, env=env)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
