"""Prompt 29.4.4k manual paper-only switch dry-run / fail-closed preflight.

This module validates the manual switch contract from Prompt 29.4.4j without
activating paper orders.  It is intentionally a dry-run preflight: even when the
manual enable/confirm controls are correct, this patch must keep execution
disabled and require a later explicit activation patch.
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

REPORT_NAME = "paper_unlock_manual_switch_preflight_report.json"
PROMPT_ID = "29.4.4k"
SWITCH_REPORT_NAME = "paper_unlock_experiment_switch_draft_report.json"
SWITCH_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_GUARDED_PAPER_SWITCH_DRAFT"
PROFILE_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1"
EXPERIMENT_NAME = "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_EXPERIMENT_DESIGN"
REQUIRED_SWITCH_DECISION = "GUARDED_PAPER_SWITCH_IMPLEMENTATION_DRAFT_READY_DIAGNOSTIC"
READY_DECISION = "MANUAL_PAPER_SWITCH_PREFLIGHT_READY_DIAGNOSTIC"
KEEP_DECISION = "KEEP_DIAGNOSTIC"
DEFAULT_CONFIRM_VALUE = "CONFIRM_MAP_SCORE_65_79_REPAIRED_STABILITY_V1_PAPER_ONLY"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaperUnlockManualSwitchPreflightSettings:
    enabled: bool = True
    switch_name: str = SWITCH_NAME
    profile_name: str = PROFILE_NAME
    experiment_name: str = EXPERIMENT_NAME
    required_switch_decision: str = REQUIRED_SWITCH_DECISION
    required_selected_entries: int = 20
    required_cadence_variant: str = "bounded_6_daily_30_weekly_0h"
    manual_enable_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE"
    manual_confirm_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM"
    expected_manual_confirm_value: str = DEFAULT_CONFIRM_VALUE
    requested_mode_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE"
    testnet_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET"
    live_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE"
    exchange_broker_env: str = "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER"
    require_paper_mode: bool = True
    require_exchange_broker_blocked: bool = True
    require_two_step_manual_activation: bool = True
    require_separate_activation_patch: bool = True
    max_positions: int = 1
    risk_per_trade_pct: float = 0.0025
    max_daily_entries: int = 6
    max_weekly_entries: int = 30
    abort_max_consecutive_losses: int = 3
    abort_max_drawdown_pct: float = 1.0

    @classmethod
    def from_config(cls, cfg: Any = Config) -> "PaperUnlockManualSwitchPreflightSettings":
        return cls(
            enabled=bool(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ENABLED", True)),
            switch_name=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_SWITCH_NAME", SWITCH_NAME) or SWITCH_NAME),
            profile_name=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_PROFILE_NAME", PROFILE_NAME) or PROFILE_NAME),
            experiment_name=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXPERIMENT_NAME", EXPERIMENT_NAME) or EXPERIMENT_NAME),
            required_switch_decision=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_SWITCH_DECISION", REQUIRED_SWITCH_DECISION) or REQUIRED_SWITCH_DECISION),
            required_selected_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_SELECTED_ENTRIES", 20), 20)),
            required_cadence_variant=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRED_CADENCE_VARIANT", "bounded_6_daily_30_weekly_0h") or "bounded_6_daily_30_weekly_0h"),
            manual_enable_env=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MANUAL_ENABLE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_ENABLE"),
            manual_confirm_env=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MANUAL_CONFIRM_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_MANUAL_CONFIRM"),
            expected_manual_confirm_value=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXPECTED_CONFIRM_VALUE", DEFAULT_CONFIRM_VALUE) or DEFAULT_CONFIRM_VALUE),
            requested_mode_env=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUESTED_MODE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_REQUESTED_MODE"),
            testnet_env=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_TESTNET_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_TESTNET"),
            live_env=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_LIVE_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_LIVE"),
            exchange_broker_env=str(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_EXCHANGE_BROKER_ENV", "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER") or "PAPER_UNLOCK_EXPERIMENT_SWITCH_EXCHANGE_BROKER"),
            require_paper_mode=bool(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_PAPER_MODE", True)),
            require_exchange_broker_blocked=bool(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_EXCHANGE_BROKER_BLOCKED", True)),
            require_two_step_manual_activation=bool(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_TWO_STEP", True)),
            require_separate_activation_patch=bool(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_REQUIRE_SEPARATE_PATCH", True)),
            max_positions=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_POSITIONS", 1), 1)),
            risk_per_trade_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_RISK_PER_TRADE_PCT", 0.0025), 0.0025)),
            max_daily_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_DAILY_ENTRIES", 6), 6)),
            max_weekly_entries=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_MAX_WEEKLY_ENTRIES", 30), 30)),
            abort_max_consecutive_losses=max(1, _safe_int(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ABORT_MAX_CONSECUTIVE_LOSSES", 3), 3)),
            abort_max_drawdown_pct=max(0.0, _safe_float(getattr(cfg, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ABORT_MAX_DRAWDOWN_PCT", 1.0), 1.0)),
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


def _switch_contract(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("switch_contract")
    return value if isinstance(value, dict) else {}


def _runtime_profile(contract: dict[str, Any]) -> dict[str, Any]:
    value = contract.get("runtime_profile")
    return value if isinstance(value, dict) else {}


def _manual_controls(contract: dict[str, Any]) -> dict[str, Any]:
    value = contract.get("manual_switch_controls")
    return value if isinstance(value, dict) else {}


def _abort_interlocks(contract: dict[str, Any]) -> dict[str, Any]:
    value = contract.get("abort_interlocks")
    return value if isinstance(value, dict) else {}


def _str_env(env: Mapping[str, str], key: str, default: str = "") -> str:
    value = env.get(key, default)
    if value is None:
        return default
    return str(value)


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _switch_draft_guard(switch_report: dict[str, Any], settings: PaperUnlockManualSwitchPreflightSettings) -> dict[str, Any]:
    decision = _decision(switch_report)
    contract = _switch_contract(switch_report)
    runtime_profile = _runtime_profile(contract)
    controls = _manual_controls(contract)
    aborts = _abort_interlocks(contract)
    counts = switch_report.get("counts", {}) if isinstance(switch_report.get("counts"), dict) else {}
    activation_guard = switch_report.get("activation_draft_guard", {}) if isinstance(switch_report.get("activation_draft_guard"), dict) else {}

    report_status_ok = str(switch_report.get("status") or "").upper() == "PASS"
    decision_ok = str(decision.get("status") or "") == settings.required_switch_decision
    switch_name_ok = str(decision.get("switch_name") or switch_report.get("switch_name") or "") == settings.switch_name
    profile_name_ok = str(decision.get("profile_name") or switch_report.get("profile_name") or "") == settings.profile_name
    experiment_name_ok = str(decision.get("experiment_name") or switch_report.get("experiment_name") or "") == settings.experiment_name
    activation_guard_ok = bool(activation_guard.get("passes_activation_draft_guard", False)) or bool(decision.get("activation_guard_ok", False))
    selected_entries = _safe_int(decision.get("selected_entries", counts.get("selected_entries", 0)), 0)
    selected_entries_ok = selected_entries >= settings.required_selected_entries
    cadence_ok = str(decision.get("best_stability_review_variant") or activation_guard.get("best_stability_review_variant") or "") == settings.required_cadence_variant
    implementation_ready = bool(decision.get("switch_implementation_ready", False))
    execution_disabled_ok = (
        not bool(switch_report.get("operational_unlock_allowed", False))
        and not bool(switch_report.get("paper_unlock_experiment_allowed", False))
        and not bool(switch_report.get("paper_orders_enabled", False))
        and not bool(switch_report.get("profile_activation_allowed", False))
        and not bool(switch_report.get("automatic_activation_allowed", False))
        and not bool(switch_report.get("manual_activation_allowed", False))
        and not bool(decision.get("operational_unlock_allowed", False))
        and not bool(decision.get("paper_unlock_experiment_allowed", False))
        and not bool(decision.get("paper_orders_enabled", False))
        and not bool(decision.get("profile_activation_allowed", False))
        and not bool(decision.get("automatic_activation_allowed", False))
        and not bool(decision.get("manual_activation_allowed", False))
        and _safe_int(counts.get("orders_submitted", 0), 0) == 0
        and _safe_int(counts.get("positions_opened", 0), 0) == 0
    )
    contract_draft_only_ok = bool(contract.get("draft_only", False)) and not bool(contract.get("activation_in_this_patch_allowed", True))
    contract_blocks_execution_ok = (
        not bool(contract.get("automatic_activation_allowed", True))
        and not bool(contract.get("paper_orders_enabled_in_this_patch", True))
        and not bool(contract.get("operational_unlock_allowed_in_this_patch", True))
        and not bool(contract.get("testnet_allowed", True))
        and not bool(contract.get("live_allowed", True))
        and not bool(contract.get("exchange_broker_allowed", True))
    )
    controls_ok = (
        bool(controls.get("separate_activation_patch_required", False))
        and bool(controls.get("two_step_confirmation_required", False))
        and bool(controls.get("must_fail_closed_if_missing", False))
        and bool(controls.get("must_fail_closed_if_live_or_testnet", False))
        and bool(controls.get("must_fail_closed_if_exchange_broker_enabled", False))
    )
    runtime_profile_ok = (
        str(runtime_profile.get("entry_state_policy") or "") == "CONFIRMATION_ONLY"
        and runtime_profile.get("allowed_structure_states") == ["CONFIRMATION"]
        and set(runtime_profile.get("blocked_structure_states") or []) >= {"WAIT", "NO_STRUCTURE", "CONFLICT"}
        and _safe_int(runtime_profile.get("max_positions", 0), 0) <= settings.max_positions
        and _safe_float(runtime_profile.get("risk_per_trade_pct", 999.0), 999.0) <= settings.risk_per_trade_pct
        and _safe_int(runtime_profile.get("max_daily_entries", 999999), 999999) <= settings.max_daily_entries
        and _safe_int(runtime_profile.get("max_weekly_entries", 999999), 999999) <= settings.max_weekly_entries
    )
    aborts_ok = (
        bool(aborts.get("pause_on_manual_confirmation_missing", False))
        and bool(aborts.get("pause_on_any_live_or_testnet_mode", False))
        and bool(aborts.get("pause_on_exchange_broker_available", False))
        and _safe_int(aborts.get("max_consecutive_losses", settings.abort_max_consecutive_losses), settings.abort_max_consecutive_losses) <= settings.abort_max_consecutive_losses
        and _safe_float(aborts.get("max_drawdown_pct", settings.abort_max_drawdown_pct), settings.abort_max_drawdown_pct) <= settings.abort_max_drawdown_pct
    )

    guard = {
        "report_status_ok": report_status_ok,
        "decision_ok": decision_ok,
        "switch_name_ok": switch_name_ok,
        "profile_name_ok": profile_name_ok,
        "experiment_name_ok": experiment_name_ok,
        "activation_guard_ok": activation_guard_ok,
        "selected_entries": selected_entries,
        "selected_entries_ok": selected_entries_ok,
        "required_selected_entries": settings.required_selected_entries,
        "cadence_ok": cadence_ok,
        "required_cadence_variant": settings.required_cadence_variant,
        "implementation_ready": implementation_ready,
        "execution_disabled_ok": execution_disabled_ok,
        "contract_draft_only_ok": contract_draft_only_ok,
        "contract_blocks_execution_ok": contract_blocks_execution_ok,
        "manual_controls_contract_ok": controls_ok,
        "runtime_profile_ok": runtime_profile_ok,
        "abort_interlocks_ok": aborts_ok,
        "counts": counts,
        "decision_status": decision.get("status", ""),
    }
    guard["passes_switch_draft_guard"] = all([
        report_status_ok,
        decision_ok,
        switch_name_ok,
        profile_name_ok,
        experiment_name_ok,
        activation_guard_ok,
        selected_entries_ok,
        cadence_ok,
        implementation_ready,
        execution_disabled_ok,
        contract_draft_only_ok,
        contract_blocks_execution_ok,
        controls_ok,
        runtime_profile_ok,
        aborts_ok,
    ])
    return guard


def _evaluate_operator_controls(
    name: str,
    settings: PaperUnlockManualSwitchPreflightSettings,
    env: Mapping[str, str],
    *,
    switch_guard_ok: bool,
    activation_patch_present: bool = False,
    forced_mode: str | None = None,
    forced_live: bool | None = None,
    forced_testnet: bool | None = None,
    forced_exchange_broker: str | None = None,
) -> dict[str, Any]:
    enable_value = _str_env(env, settings.manual_enable_env, "")
    confirm_value = _str_env(env, settings.manual_confirm_env, "")
    requested_mode = str(forced_mode if forced_mode is not None else _str_env(env, settings.requested_mode_env, "paper") or "paper").lower()
    live_requested = bool(forced_live) if forced_live is not None else _truthy(_str_env(env, settings.live_env, "0"))
    testnet_requested = bool(forced_testnet) if forced_testnet is not None else _truthy(_str_env(env, settings.testnet_env, "0"))
    exchange_broker_mode = str(forced_exchange_broker if forced_exchange_broker is not None else _str_env(env, settings.exchange_broker_env, "blocked") or "blocked").lower()

    manual_enable_ok = enable_value == "1"
    manual_confirm_ok = confirm_value == settings.expected_manual_confirm_value
    two_step_ok = manual_enable_ok and manual_confirm_ok if settings.require_two_step_manual_activation else manual_enable_ok
    paper_mode_ok = (requested_mode == "paper") if settings.require_paper_mode else requested_mode in {"paper", "diagnostic"}
    live_testnet_block_ok = not live_requested and not testnet_requested and requested_mode not in {"live", "testnet"}
    exchange_broker_block_ok = exchange_broker_mode in {"", "blocked", "paper", "paper_only"} if settings.require_exchange_broker_blocked else True
    separate_patch_ok = bool(activation_patch_present) if settings.require_separate_activation_patch else True
    future_manual_preflight_ok = all([
        switch_guard_ok,
        two_step_ok,
        paper_mode_ok,
        live_testnet_block_ok,
        exchange_broker_block_ok,
        separate_patch_ok,
    ])
    activation_allowed_in_this_patch = False
    paper_orders_enabled_in_this_patch = False
    fail_closed = not activation_allowed_in_this_patch and not paper_orders_enabled_in_this_patch
    return {
        "scenario": name,
        "manual_enable_ok": manual_enable_ok,
        "manual_confirm_ok": manual_confirm_ok,
        "two_step_ok": two_step_ok,
        "requested_mode": requested_mode,
        "paper_mode_ok": paper_mode_ok,
        "live_requested": live_requested,
        "testnet_requested": testnet_requested,
        "live_testnet_block_ok": live_testnet_block_ok,
        "exchange_broker_mode": exchange_broker_mode,
        "exchange_broker_block_ok": exchange_broker_block_ok,
        "switch_guard_ok": bool(switch_guard_ok),
        "separate_activation_patch_present": bool(activation_patch_present),
        "separate_patch_ok": separate_patch_ok,
        "future_manual_preflight_ok": future_manual_preflight_ok,
        "activation_allowed_in_this_patch": activation_allowed_in_this_patch,
        "paper_orders_enabled_in_this_patch": paper_orders_enabled_in_this_patch,
        "orders_would_be_submitted": False,
        "positions_would_be_opened": False,
        "fail_closed": fail_closed,
        "block_reasons": [
            reason for reason, failed in [
                ("SWITCH_DRAFT_GUARD_NOT_PASS", not switch_guard_ok),
                ("MANUAL_ENABLE_MISSING_OR_FALSE", not manual_enable_ok),
                ("MANUAL_CONFIRM_MISSING_OR_MISMATCH", not manual_confirm_ok),
                ("MODE_NOT_PAPER", not paper_mode_ok),
                ("LIVE_OR_TESTNET_REQUESTED", not live_testnet_block_ok),
                ("EXCHANGE_BROKER_NOT_BLOCKED", not exchange_broker_block_ok),
                ("SEPARATE_ACTIVATION_PATCH_REQUIRED", not separate_patch_ok),
                ("ACTIVATION_DISABLED_IN_THIS_PATCH", not activation_allowed_in_this_patch),
            ] if failed
        ],
    }


def _preflight_suite(settings: PaperUnlockManualSwitchPreflightSettings, env: Mapping[str, str], switch_guard_ok: bool) -> dict[str, Any]:
    valid_env = {
        settings.manual_enable_env: "1",
        settings.manual_confirm_env: settings.expected_manual_confirm_value,
        settings.requested_mode_env: "paper",
        settings.live_env: "0",
        settings.testnet_env: "0",
        settings.exchange_broker_env: "blocked",
    }
    scenarios = [
        _evaluate_operator_controls("actual_environment", settings, env, switch_guard_ok=switch_guard_ok, activation_patch_present=False),
        _evaluate_operator_controls("missing_manual_env", settings, {}, switch_guard_ok=switch_guard_ok, activation_patch_present=False),
        _evaluate_operator_controls("manual_enable_only", settings, {settings.manual_enable_env: "1"}, switch_guard_ok=switch_guard_ok, activation_patch_present=False),
        _evaluate_operator_controls("manual_confirm_only", settings, {settings.manual_confirm_env: settings.expected_manual_confirm_value}, switch_guard_ok=switch_guard_ok, activation_patch_present=False),
        _evaluate_operator_controls("manual_confirm_mismatch", settings, {settings.manual_enable_env: "1", settings.manual_confirm_env: "WRONG"}, switch_guard_ok=switch_guard_ok, activation_patch_present=False),
        _evaluate_operator_controls("live_mode_requested", settings, valid_env, switch_guard_ok=switch_guard_ok, activation_patch_present=True, forced_mode="live", forced_live=True),
        _evaluate_operator_controls("testnet_mode_requested", settings, valid_env, switch_guard_ok=switch_guard_ok, activation_patch_present=True, forced_mode="testnet", forced_testnet=True),
        _evaluate_operator_controls("exchange_broker_available", settings, valid_env, switch_guard_ok=switch_guard_ok, activation_patch_present=True, forced_exchange_broker="exchange"),
        _evaluate_operator_controls("valid_manual_controls_without_activation_patch", settings, valid_env, switch_guard_ok=switch_guard_ok, activation_patch_present=False),
        _evaluate_operator_controls("valid_manual_controls_future_patch_simulation", settings, valid_env, switch_guard_ok=switch_guard_ok, activation_patch_present=True),
    ]
    by_name = {str(s.get("scenario")): s for s in scenarios}
    negative_names = [
        "missing_manual_env",
        "manual_enable_only",
        "manual_confirm_only",
        "manual_confirm_mismatch",
        "live_mode_requested",
        "testnet_mode_requested",
        "exchange_broker_available",
        "valid_manual_controls_without_activation_patch",
    ]
    negative_fail_closed_ok = all(
        bool(by_name[name].get("fail_closed", False))
        and not bool(by_name[name].get("future_manual_preflight_ok", False))
        and not bool(by_name[name].get("activation_allowed_in_this_patch", False))
        and not bool(by_name[name].get("paper_orders_enabled_in_this_patch", False))
        for name in negative_names
    )
    future_patch_simulation_ok = (
        bool(by_name["valid_manual_controls_future_patch_simulation"].get("future_manual_preflight_ok", False))
        and not bool(by_name["valid_manual_controls_future_patch_simulation"].get("activation_allowed_in_this_patch", False))
        and not bool(by_name["valid_manual_controls_future_patch_simulation"].get("paper_orders_enabled_in_this_patch", False))
        and bool(by_name["valid_manual_controls_future_patch_simulation"].get("fail_closed", False))
    )
    all_no_orders = all(
        not bool(s.get("orders_would_be_submitted", False))
        and not bool(s.get("positions_would_be_opened", False))
        and not bool(s.get("paper_orders_enabled_in_this_patch", False))
        and not bool(s.get("activation_allowed_in_this_patch", False))
        for s in scenarios
    )
    return {
        "scenarios": scenarios,
        "negative_fail_closed_ok": negative_fail_closed_ok,
        "future_patch_simulation_ok": future_patch_simulation_ok,
        "all_scenarios_no_orders_ok": all_no_orders,
        "actual_environment": by_name["actual_environment"],
        "passes_preflight_suite": bool(switch_guard_ok and negative_fail_closed_ok and future_patch_simulation_ok and all_no_orders),
    }


def build_paper_unlock_manual_switch_preflight_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockManualSwitchPreflightSettings | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    settings = settings or PaperUnlockManualSwitchPreflightSettings.from_config()
    env = dict(os.environ if env is None else env)
    base = Path(base_dir)
    switch_path = base / SWITCH_REPORT_NAME
    switch_report = _read_json(switch_path)
    switch_guard = _switch_draft_guard(switch_report, settings)
    suite = _preflight_suite(settings, env, bool(switch_guard.get("passes_switch_draft_guard", False)))
    ready = bool(settings.enabled and switch_guard.get("passes_switch_draft_guard", False) and suite.get("passes_preflight_suite", False))
    decision_status = READY_DECISION if ready else KEEP_DECISION
    reason = (
        "Manual paper-only switch dry-run preflight passed fail-closed controls. Execution remains disabled; a separate explicit manual activation patch is still required."
        if ready else
        "Manual paper-only switch preflight failed or switch prerequisites are incomplete; execution remains disabled."
    )
    next_patch = (
        "29.4.4l explicit manual paper-only activation patch draft, paper-only/fail-closed and still no live/testnet."
        if ready else
        "Repair manual switch preflight failures before any activation patch."
    )
    counts = switch_guard.get("counts", {}) if isinstance(switch_guard.get("counts"), dict) else {}
    report = {
        "prompt": PROMPT_ID,
        "report_type": "paper_unlock_manual_switch_preflight",
        "generated_at": utc_now_iso(),
        "status": "PASS" if ready else "WARN",
        "preflight_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT",
        "switch_name": settings.switch_name,
        "profile_name": settings.profile_name,
        "experiment_name": settings.experiment_name,
        "diagnostic_only": True,
        "dry_run_only": True,
        "fail_closed_preflight": True,
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
        "switch_draft_guard": switch_guard,
        "preflight_suite": suite,
        "manual_control_contract": {
            "manual_enable_env": settings.manual_enable_env,
            "manual_enable_required_value": "1",
            "manual_confirm_env": settings.manual_confirm_env,
            "manual_confirm_required_value": settings.expected_manual_confirm_value,
            "requested_mode_env": settings.requested_mode_env,
            "required_mode": "paper" if settings.require_paper_mode else "paper_or_diagnostic",
            "testnet_env": settings.testnet_env,
            "live_env": settings.live_env,
            "exchange_broker_env": settings.exchange_broker_env,
            "exchange_broker_required_state": "blocked",
            "separate_activation_patch_required": settings.require_separate_activation_patch,
            "two_step_confirmation_required": settings.require_two_step_manual_activation,
            "activation_allowed_in_this_patch": False,
        },
        "runtime_profile_preflight": {
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "entry_state_policy": "CONFIRMATION_ONLY",
            "allowed_structure_states": ["CONFIRMATION"],
            "blocked_structure_states": ["WAIT", "NO_STRUCTURE", "CONFLICT"],
            "max_positions": settings.max_positions,
            "risk_per_trade_pct": settings.risk_per_trade_pct,
            "max_daily_entries": settings.max_daily_entries,
            "max_weekly_entries": settings.max_weekly_entries,
            "abort_max_consecutive_losses": settings.abort_max_consecutive_losses,
            "abort_max_drawdown_pct": settings.abort_max_drawdown_pct,
        },
        "safety_matrix": {
            "paper_only": True,
            "live_block": True,
            "testnet_block": True,
            "exchange_broker_blocked": True,
            "paper_orders_blocked_this_patch": True,
            "automatic_activation_blocked": True,
            "manual_activation_blocked_this_patch": True,
            "fail_closed_when_env_missing": bool(suite.get("negative_fail_closed_ok", False)),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "counts": {
            "source_target_rows": counts.get("source_target_rows", 0),
            "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
            "selected_entries": switch_guard.get("selected_entries", counts.get("selected_entries", 0)),
            "preflight_scenarios": len(suite.get("scenarios", [])),
            "orders_submitted": 0,
            "positions_opened": 0,
        },
        "decision": {
            "status": decision_status,
            "reason": reason,
            "next_patch": next_patch,
            "preflight_name": "MAP_SCORE_65_79_REPAIRED_STABILITY_V1_MANUAL_SWITCH_PREFLIGHT",
            "switch_name": settings.switch_name,
            "profile_name": settings.profile_name,
            "experiment_name": settings.experiment_name,
            "selected_entries": switch_guard.get("selected_entries", 0),
            "switch_draft_ready": bool(switch_guard.get("passes_switch_draft_guard", False)),
            "fail_closed_preflight_ok": bool(suite.get("passes_preflight_suite", False)),
            "future_patch_simulation_ok": bool(suite.get("future_patch_simulation_ok", False)),
            "operational_unlock_allowed": False,
            "paper_unlock_experiment_allowed": False,
            "paper_orders_enabled": False,
            "profile_activation_allowed": False,
            "automatic_activation_allowed": False,
            "manual_activation_allowed": False,
        },
        "files": {
            "report": str(base / REPORT_NAME),
            "switch_draft": str(switch_path),
            "activation_draft": str(base / "paper_unlock_activation_draft_report.json"),
            "shadow_stability_review": str(base / "paper_unlock_shadow_stability_review_report.json"),
            "events": str(base / "paper_events.jsonl"),
        },
    }
    return report


def write_paper_unlock_manual_switch_preflight_report(
    base_dir: str | Path = "data",
    settings: PaperUnlockManualSwitchPreflightSettings | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    report = build_paper_unlock_manual_switch_preflight_report(base, settings, env=env)
    (base / REPORT_NAME).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report
