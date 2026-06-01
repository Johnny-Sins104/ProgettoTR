"""Prompt 29 paper trading engine.

This module runs the validated 5m multi-asset strategy in a local paper broker.
It fetches candles, evaluates the existing DecisionEngine, applies paper risk
limits, simulates fills, records audit events and exposes Telegram v2 commands.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Config
from core.asset_archetype_gating import parse_symbol_list
from core.client import ExchangeClient
from core.engine import DecisionEngine
from core.paper_broker import PaperBroker
from core.broker_adapter import PaperBrokerAdapter, ExchangeBrokerAdapter
from core.paper_market_data import CachedMarketDataNotFound, load_cached_ohlcv, load_replay_ohlcv
from core.paper_position_monitor import PaperPositionMonitor
from core.telegram_control import TelegramControlBot
from core.telegram_proactive import TelegramProactiveNotifier, TelegramProactiveSettings, stable_hash
from core.analyzer import TechnicalAnalyzer

# ==============================================================================
# SISTEMA DI DIAGNOSTICA, AUDIT E REPORTING (PAPER UNLOCK PIPELINE)
# ==============================================================================
# Questi moduli contengono i tool di reporting per le varie fasi del ciclo di
# vita della paper-trading pipeline, tra cui l'analisi del regime di mercato,
# i test shadow e le pre-condizioni necessarie per l'abilitazione del trading live.
# ==============================================================================

# -- Core Metrics & Performance Reports
from core.paper_lifecycle import max_cycle_sequence, write_lifecycle_report
from core.paper_performance import write_performance_artifacts
from core.paper_once_console_summary import print_paper_once_console_summary

# -- Signal Diagnostics & Shadow Simulations
from core.paper_signal_diagnostics import (
    build_signal_diagnostic,
    write_signal_diagnostics_report,
    write_signal_diagnostics_backfill_report,
)
from core.paper_shadow_simulation import write_shadow_unlock_report

# -- Market Structure & Scenario Diagnostics
from core.crypto_intraday_scenario import build_crypto_scenario_diagnostic, write_crypto_scenario_report
from core.candlestick_patterns import build_candlestick_pattern_diagnostic, write_candlestick_pattern_report
from core.pattern_conditioned_shadow import write_pattern_conditioned_shadow_report
from core.scenario_pattern_calibration import write_scenario_pattern_calibration_report
from core.market_structure_map import build_market_structure_map_diagnostic, write_market_structure_map_report
from core.calibrated_structure_shadow import write_calibrated_structure_shadow_report
from core.structure_filter_diagnostics import write_structure_filter_diagnostics_report
from core.structure_context_repair import write_structure_context_repair_report
from core.repaired_structure_shadow_validation import write_repaired_structure_shadow_validation_report
from core.independent_repaired_validation import write_independent_repaired_validation_report

# -- Paper Unlock Gate & Profile Refinements
from core.paper_unlock_gate import PaperUnlockGateSettings, evaluate_paper_unlock
from core.paper_unlock_profile_refinement import write_paper_unlock_profile_refinement_report
from core.paper_unlock_experiment_design import write_paper_unlock_experiment_design_report
from core.paper_unlock_shadow_dry_run import write_paper_unlock_shadow_dry_run_report
from core.paper_unlock_shadow_rate_calibration import write_paper_unlock_shadow_rate_calibration_report
from core.paper_unlock_bounded_cadence import write_paper_unlock_bounded_cadence_report
from core.paper_unlock_shadow_stability_review import write_paper_unlock_shadow_stability_review_report

# -- Activation Drafts & Preflights
from core.paper_unlock_activation_draft import write_paper_unlock_activation_draft_report
from core.paper_unlock_experiment_switch_draft import write_paper_unlock_experiment_switch_draft_report
from core.paper_unlock_manual_switch_preflight import write_paper_unlock_manual_switch_preflight_report
from core.paper_unlock_manual_activation_patch import write_paper_unlock_manual_activation_patch_report
from core.paper_unlock_final_enable_preflight import write_paper_unlock_final_enable_preflight_report
from core.paper_unlock_guarded_enable import write_paper_unlock_guarded_enable_report

# -- Supervised Execution, Auditing & Guardrails
from core.paper_unlock_runtime_audit import (
    RuntimePaperOrderAuditSettings,
    build_guarded_runtime_audit_event,
    guarded_enable_runtime_state,
    write_paper_unlock_runtime_audit_report,
)
from core.paper_unlock_routing_bridge import (
    GuardedPaperRoutingBridgeSettings,
    build_guarded_paper_routing_bridge_event,
    write_paper_unlock_routing_bridge_report,
)
from core.paper_unlock_candidate_audit import (
    GuardedPaperOrderCandidateAuditSettings,
    build_guarded_paper_order_candidate_audit_event,
    write_paper_unlock_candidate_audit_report,
)
from core.paper_unlock_handoff_dry_run import (
    PaperOrderHandoffDryRunSettings,
    build_paper_order_handoff_dry_run_event,
    write_paper_unlock_handoff_dry_run_report,
)
from core.paper_unlock_supervised_execution import (
    PaperUnlockSupervisedExecutionSettings,
    build_paper_supervised_execution_event,
    write_paper_unlock_supervised_execution_report,
)
from core.paper_order_leakage_guard import (
    PaperOrderLeakageGuardSettings,
    build_legacy_paper_order_blocked_event,
    should_block_paper_order_attempt,
    write_paper_order_leakage_guard_report,
)
from core.edge_strategy_runtime_pruning import (
    EdgeStrategyRuntimePruningSettings,
    build_runtime_pruning_event,
    extract_archetype,
    evaluate_runtime_archetype_pruning,
    write_edge_strategy_runtime_pruning_report,
)
from core.lsr_v2_paper_supervised_bridge import (
    LSRV2PaperSupervisedBridgeSettings,
    write_lsr_v2_paper_supervised_bridge_report,
)
from core.lsr_v2_runtime_bridge import (
    LSRV2RuntimeBridgeSettings,
    build_lsr_v2_runtime_bridge_events_for_symbol,
    write_lsr_v2_runtime_bridge_artifacts,
)
from core.lsr_v2_engine_read_only_artifact_hook import (
    EngineReadOnlyArtifactHookSettings,
    write_lsr_v2_engine_read_only_artifact_hook_report,
)


@dataclass
class PaperEngineSettings:
    symbols: list[str]
    timeframe: str = "5m"
    cost_model: str = "conservative"
    balance: float = 1000.0
    poll_seconds: float = 60.0
    dry_run_once: bool = False
    max_cycles: int = 0
    max_positions: int = 3
    risk_per_trade_pct: float = 0.005
    rr: float = 2.0
    mode: str = "paper"
    data_dir: str = "data"
    market_data_mode: str = "live"
    market_data_cache_dir: str = "data"
    market_data_replay_step: int = 1
    market_data_replay_start_offset: int = 0
    cycle_artifacts_enabled: bool = True
    console_verbose: bool = False
    ai_debug: bool = False
    console_header_every_n_cycles: int = 12
    console_show_flat_monitor: bool = False
    telegram_proactive_enabled: bool = True
    telegram_notify_on_start: bool = True
    telegram_notify_on_shutdown: bool = True
    telegram_notify_on_signal: bool = True
    telegram_notify_on_order: bool = True
    telegram_notify_on_position_open: bool = True
    telegram_notify_on_position_close: bool = True
    telegram_notify_on_tp_sl: bool = True
    telegram_notify_on_drift_warn: bool = True
    telegram_notify_every_cycle: bool = False
    telegram_notify_no_signal_every_n_cycles: int = 12
    telegram_notify_position_every_n_cycles: int = 1
    telegram_notify_position_every_seconds: float = 300.0
    telegram_notify_position_pnl_delta_pct: float = 0.25
    telegram_proactive_dedup_seconds: float = 30.0
    telegram_proactive_max_messages_per_minute: int = 10
    signal_diagnostics_enabled: bool = True
    signal_diagnostics_backfill_enabled: bool = True
    exploratory_signal_analysis: bool = True
    paper_entry_unlock_enabled: bool = False
    unlock_rejection_analysis_enabled: bool = True
    crypto_scenario_enabled: bool = True
    candlestick_patterns_enabled: bool = True
    pattern_conditioned_shadow_enabled: bool = True
    scenario_pattern_calibration_enabled: bool = True
    market_structure_map_enabled: bool = True
    calibrated_structure_shadow_enabled: bool = True
    structure_filter_diagnostics_enabled: bool = True
    structure_context_repair_enabled: bool = True
    repaired_structure_shadow_validation_enabled: bool = True
    independent_repaired_validation_enabled: bool = True
    paper_unlock_profile_refinement_enabled: bool = True
    paper_unlock_experiment_design_enabled: bool = True
    paper_unlock_shadow_dry_run_enabled: bool = True
    paper_unlock_shadow_rate_calibration_enabled: bool = True
    paper_unlock_bounded_cadence_enabled: bool = True
    paper_unlock_shadow_stability_review_enabled: bool = True
    paper_unlock_activation_draft_enabled: bool = True
    paper_unlock_experiment_switch_draft_enabled: bool = True
    paper_unlock_manual_switch_preflight_enabled: bool = True
    paper_unlock_manual_activation_patch_enabled: bool = True
    paper_unlock_final_enable_preflight_enabled: bool = True
    paper_unlock_guarded_enable_enabled: bool = True
    paper_unlock_runtime_audit_enabled: bool = True
    paper_unlock_routing_bridge_enabled: bool = True
    paper_unlock_candidate_audit_enabled: bool = True
    paper_unlock_handoff_dry_run_enabled: bool = True
    paper_unlock_supervised_execution_enabled: bool = True
    paper_unlock_supervised_execution_operator_enable: bool = False
    paper_unlock_supervised_execution_confirm: str = ""
    paper_order_leakage_guard_enabled: bool = True
    edge_strategy_pruning_enabled: bool = False
    edge_strategy_pruning_audit_enabled: bool = True
    lsr_v2_paper_supervised_bridge_enabled: bool = True
    lsr_v2_paper_supervised_bridge_operator_enable: bool = False
    lsr_v2_paper_supervised_bridge_confirm: str = ""
    lsr_v2_engine_read_only_artifact_hook_enabled: bool = True
    shadow_simulation_enabled: bool = True
    paper_unlock_profile: str = "BTC_ONLY_40_Q60"
    paper_unlock_allowed_symbols: list[str] | None = None
    paper_unlock_min_ai_prob: float = 40.0
    paper_unlock_min_setup_quality: float = 60.0
    paper_unlock_max_positions: int = 1
    paper_unlock_live_block: bool = True


class PaperTradingEngine:
    def __init__(self, settings: PaperEngineSettings) -> None:
        if settings.mode != "paper":
            raise ValueError("Prompt 29 engine is paper-only. Real live execution is intentionally disabled.")
        self.settings = settings
        Config.PAPER_AI_DEBUG = bool(settings.ai_debug)
        Config.PAPER_UNLOCK_REJECTION_ANALYSIS_ENABLED = bool(settings.unlock_rejection_analysis_enabled)
        Config.PAPER_CRYPTO_SCENARIO_ENABLED = bool(settings.crypto_scenario_enabled)
        Config.PAPER_CANDLESTICK_PATTERNS_ENABLED = bool(settings.candlestick_patterns_enabled)
        Config.PATTERN_CONDITIONED_SHADOW_ENABLED = bool(settings.pattern_conditioned_shadow_enabled)
        Config.SCENARIO_PATTERN_CALIBRATION_ENABLED = bool(settings.scenario_pattern_calibration_enabled)
        Config.MARKET_STRUCTURE_MAP_ENABLED = bool(settings.market_structure_map_enabled)
        Config.CALIBRATED_STRUCTURE_SHADOW_ENABLED = bool(settings.calibrated_structure_shadow_enabled)
        Config.STRUCTURE_FILTER_DIAGNOSTICS_ENABLED = bool(settings.structure_filter_diagnostics_enabled)
        Config.STRUCTURE_CONTEXT_REPAIR_ENABLED = bool(settings.structure_context_repair_enabled)
        Config.REPAIRED_STRUCTURE_SHADOW_VALIDATION_ENABLED = bool(settings.repaired_structure_shadow_validation_enabled)
        Config.INDEPENDENT_REPAIRED_VALIDATION_ENABLED = bool(settings.independent_repaired_validation_enabled)
        Config.PAPER_UNLOCK_PROFILE_REFINEMENT_ENABLED = bool(settings.paper_unlock_profile_refinement_enabled)
        Config.PAPER_UNLOCK_EXPERIMENT_DESIGN_ENABLED = bool(settings.paper_unlock_experiment_design_enabled)
        Config.PAPER_UNLOCK_SHADOW_DRY_RUN_ENABLED = bool(settings.paper_unlock_shadow_dry_run_enabled)
        Config.PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ENABLED = bool(settings.paper_unlock_shadow_rate_calibration_enabled)
        Config.PAPER_UNLOCK_BOUNDED_CADENCE_ENABLED = bool(settings.paper_unlock_bounded_cadence_enabled)
        Config.PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ENABLED = bool(settings.paper_unlock_shadow_stability_review_enabled)
        Config.PAPER_UNLOCK_ACTIVATION_DRAFT_ENABLED = bool(settings.paper_unlock_activation_draft_enabled)
        Config.PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ENABLED = bool(settings.paper_unlock_experiment_switch_draft_enabled)
        Config.PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ENABLED = bool(settings.paper_unlock_manual_switch_preflight_enabled)
        Config.PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ENABLED = bool(settings.paper_unlock_manual_activation_patch_enabled)
        Config.PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ENABLED = bool(settings.paper_unlock_final_enable_preflight_enabled)
        Config.PAPER_UNLOCK_GUARDED_ENABLE_ENABLED = bool(settings.paper_unlock_guarded_enable_enabled)
        Config.PAPER_UNLOCK_RUNTIME_AUDIT_ENABLED = bool(settings.paper_unlock_runtime_audit_enabled)
        Config.PAPER_UNLOCK_ROUTING_BRIDGE_ENABLED = bool(settings.paper_unlock_routing_bridge_enabled)
        Config.PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLED = bool(settings.paper_unlock_candidate_audit_enabled)
        Config.PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLED = bool(settings.paper_unlock_handoff_dry_run_enabled)
        Config.PAPER_UNLOCK_SUPERVISED_EXECUTION_ENABLED = bool(settings.paper_unlock_supervised_execution_enabled)
        Config.PAPER_UNLOCK_SUPERVISED_EXECUTION_OPERATOR_ENABLE = bool(settings.paper_unlock_supervised_execution_operator_enable)
        Config.PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM = str(settings.paper_unlock_supervised_execution_confirm or "")
        Config.PAPER_ORDER_LEAKAGE_GUARD_ENABLED = bool(settings.paper_order_leakage_guard_enabled)
        Config.EDGE_STRATEGY_PRUNING_ENABLED = bool(settings.edge_strategy_pruning_enabled)
        Config.EDGE_STRATEGY_PRUNING_AUDIT_ENABLED = bool(settings.edge_strategy_pruning_audit_enabled)
        Config.LSR_V2_PAPER_SUPERVISED_BRIDGE_ENABLED = bool(settings.lsr_v2_paper_supervised_bridge_enabled)
        Config.LSR_V2_PAPER_SUPERVISED_BRIDGE_OPERATOR_ENABLE = bool(settings.lsr_v2_paper_supervised_bridge_operator_enable)
        Config.LSR_V2_PAPER_SUPERVISED_BRIDGE_CONFIRM = str(settings.lsr_v2_paper_supervised_bridge_confirm or "")
        Config.LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_ENABLED = bool(settings.lsr_v2_engine_read_only_artifact_hook_enabled)
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.broker = PaperBroker(
            initial_balance=settings.balance,
            fee_rate=Config.COMMISSION_RATE * 2.0,
            state_path=self.data_dir / "paper_state.json",
            events_path=self.data_dir / "paper_events.jsonl",
        )
        self.last_signal_by_symbol: dict[str, str] = {}
        self.last_prices: dict[str, float] = {}
        display_leverage = float(os.getenv("PAPER_MONITOR_LEVERAGE", "1.0") or "1.0")
        self.broker_adapter = PaperBrokerAdapter(self.broker, last_prices=self.last_prices, leverage_for_display=display_leverage)
        self.exchange_adapter_stub = ExchangeBrokerAdapter(mode="blocked")
        self.unlock_settings = PaperUnlockGateSettings.from_config(
            Config,
            enabled=bool(settings.paper_entry_unlock_enabled),
            profile=str(settings.paper_unlock_profile or "BTC_ONLY_40_Q60"),
        )
        if settings.paper_unlock_allowed_symbols:
            self.unlock_settings = PaperUnlockGateSettings(
                **{
                    **self.unlock_settings.to_dict(),
                    "allowed_symbols": tuple(settings.paper_unlock_allowed_symbols),
                }
            )
        self.runtime_audit_settings = RuntimePaperOrderAuditSettings.from_config(Config)
        self.routing_bridge_settings = GuardedPaperRoutingBridgeSettings.from_config(Config)
        self.candidate_audit_settings = GuardedPaperOrderCandidateAuditSettings.from_config(Config)
        self.handoff_dry_run_settings = PaperOrderHandoffDryRunSettings.from_config(Config)
        self.supervised_execution_settings = PaperUnlockSupervisedExecutionSettings.from_config(Config)
        self.order_leakage_guard_settings = PaperOrderLeakageGuardSettings.from_config(Config)
        self.edge_strategy_pruning_settings = EdgeStrategyRuntimePruningSettings.from_config(Config)
        self.lsr_v2_bridge_settings = LSRV2PaperSupervisedBridgeSettings.from_config(Config)
        self.lsr_v2_runtime_bridge_settings = LSRV2RuntimeBridgeSettings(
            data_dir=str(self.data_dir),
            timeframe=str(settings.timeframe or "5m"),
        )
        self.lsr_v2_engine_read_only_artifact_hook_settings = EngineReadOnlyArtifactHookSettings(data_dir=str(self.data_dir))
        self._lsr_v2_runtime_cycle_events: list[dict[str, Any]] = []
        self.position_monitor = PaperPositionMonitor(output_path=self.data_dir / "paper_position_monitor.json")
        self._cycle_seq = max_cycle_sequence(self.data_dir / "paper_events.jsonl")
        self._shutdown_requested = False
        self._active_cycle_id: str | None = None
        self._cycle_started_at: datetime | None = None
        self._last_drift_status: str | None = None
        self._last_position_pnl_pct_by_id: dict[str, float] = {}
        self._last_position_notify_cycle_by_id: dict[str, int] = {}
        self._startup_banner_printed = False
        self._last_completed_cycle_summary: dict[str, Any] | None = None
        self._paper_once_console_summary_printed = False
        self._last_lsr_v2_bridge_runtime_cycle_id: str | None = None
        self._market_data_replay_offsets: dict[str, int] = {}
        allowed_users = [x for x in os.getenv("TELEGRAM_ALLOWED_USER_IDS", getattr(Config, "TELEGRAM_ALLOWED_USER_IDS", "")).replace(";", ",").split(",") if x.strip()]
        self.telegram = TelegramControlBot(
            token=Config.TELEGRAM_TOKEN,
            chat_id=Config.TELEGRAM_CHAT_ID,
            allowed_user_ids=allowed_users,
            audit_path=self.data_dir / "telegram_audit.jsonl",
        )
        self.proactive = TelegramProactiveNotifier(
            self.telegram,
            state_path=self.data_dir / "telegram_proactive_state.json",
            settings=TelegramProactiveSettings(
                enabled=bool(settings.telegram_proactive_enabled),
                notify_on_start=bool(settings.telegram_notify_on_start),
                notify_on_shutdown=bool(settings.telegram_notify_on_shutdown),
                notify_on_signal=bool(settings.telegram_notify_on_signal),
                notify_on_order=bool(settings.telegram_notify_on_order),
                notify_on_position_open=bool(settings.telegram_notify_on_position_open),
                notify_on_position_close=bool(settings.telegram_notify_on_position_close),
                notify_on_tp_sl=bool(settings.telegram_notify_on_tp_sl),
                notify_on_drift_warn=bool(settings.telegram_notify_on_drift_warn),
                notify_every_cycle=bool(settings.telegram_notify_every_cycle),
                notify_no_signal_every_n_cycles=int(settings.telegram_notify_no_signal_every_n_cycles or 0),
                notify_position_every_n_cycles=int(settings.telegram_notify_position_every_n_cycles or 0),
                notify_position_every_seconds=float(settings.telegram_notify_position_every_seconds or 0.0),
                notify_position_pnl_delta_pct=float(settings.telegram_notify_position_pnl_delta_pct or 0.0),
                dedup_seconds=float(settings.telegram_proactive_dedup_seconds or 0.0),
                max_messages_per_minute=int(settings.telegram_proactive_max_messages_per_minute or 0),
            ),
        )
        self._register_telegram_handlers()

    def _register_telegram_handlers(self) -> None:
        self.telegram.register("/status", lambda _c, _a: self.format_status())
        self.telegram.register("/pnl", lambda _c, _a: self.format_pnl())
        self.telegram.register("/positions", lambda _c, _a: self.format_positions())
        self.telegram.register("/monitor", lambda _c, _a: self.format_positions())
        self.telegram.register("/orders", lambda _c, _a: self.format_orders())
        self.telegram.register("/risk", lambda _c, _a: self.format_risk())
        self.telegram.register("/report", lambda _c, _a: self.format_report())
        self.telegram.register("/pause", self._cmd_pause)
        self.telegram.register("/resume", self._cmd_resume)
        self.telegram.register("/kill", self._cmd_kill)

    @property
    def paper_once_console_summary_printed(self) -> bool:
        return self._paper_once_console_summary_printed

    def _cmd_pause(self, _command: str, _args: list[str]) -> str:
        self.broker.is_paused = True
        self.broker.emit("TELEGRAM_PAUSE_REQUESTED", result="PAUSED")
        self.broker.save()
        self.write_status_file()
        return "Paper engine paused. New entries disabled; open positions remain managed."

    def _cmd_resume(self, _command: str, _args: list[str]) -> str:
        self.broker.is_paused = False
        self.broker.emit("TELEGRAM_RESUME_REQUESTED", result="RESUMED")
        self.broker.save()
        self.write_status_file()
        return "Paper engine resumed. New entries enabled."

    def _cmd_kill(self, _command: str, args: list[str]) -> str:
        if not args or args[0].lower() != "confirm":
            self.broker.emit("TELEGRAM_KILL_REJECTED", reason="missing_confirm")
            return "Use /kill confirm to activate the persistent kill switch."
        self.broker.kill_switch = True
        self.broker.is_paused = True
        closed = self.broker.close_all(self.last_prices, reason="TELEGRAM_KILL")
        self.broker.emit("TELEGRAM_KILL_CONFIRMED", closed=len(closed), kill_switch=True, paused=True)
        self.broker.save()
        self.write_status_file()
        return f"Kill switch active and persistent. Closed {len(closed)} paper positions. New orders blocked."

    async def run(self) -> None:
        self.broker.ensure_event_log()
        if self.broker.state_loaded:
            self.broker.emit(
                "STATE_RESTORED",
                open_positions=len(self.broker.open_positions),
                orders=len(self.broker.orders),
                balance=self.broker.balance,
                restored_cycle_seq=self._cycle_seq,
            )
            self.broker.emit("RECOVERY_COMPLETED", status="OK", next_cycle_seq=self._cycle_seq + 1)
        self.broker.emit(
            "ENGINE_STARTED",
            mode=self.settings.mode,
            symbols=self.settings.symbols,
            timeframe=self.settings.timeframe,
            cost_model=self.settings.cost_model,
            once=bool(self.settings.dry_run_once),
            max_cycles=int(self.settings.max_cycles or 0),
            market_data_mode=self.settings.market_data_mode,
            cycle_artifacts_enabled=bool(self.settings.cycle_artifacts_enabled),
        )
        self.exchange_adapter_stub.write_design_stub(self.data_dir / "exchange_broker_adapter_stub.json")
        self.write_status_file()
        self._print_startup_banner()
        await self._notify_startup()
        tg_task = asyncio.create_task(self.telegram.poll_forever(), name="telegram_poll_forever") if self.telegram.enabled else None
        completed_cycles = 0
        try:
            while True:
                await self.tick()
                completed_cycles += 1
                if self.settings.dry_run_once:
                    break
                if self.settings.max_cycles > 0 and completed_cycles >= self.settings.max_cycles:
                    self.broker.emit(
                        "MAX_CYCLES_REACHED",
                        completed_cycles=completed_cycles,
                        max_cycles=self.settings.max_cycles,
                    )
                    break
                await asyncio.sleep(self.settings.poll_seconds)
        except asyncio.CancelledError:
            self._shutdown_requested = True
            self.broker.emit("SHUTDOWN_REQUESTED", reason="asyncio_cancelled", active_cycle_id=self._active_cycle_id)
            if self._active_cycle_id:
                self.broker.emit("ASYNC_TASK_CANCELLED", cycle_id=self._active_cycle_id, component="paper_engine")
            raise
        finally:
            print("[PaperEngine] Shutdown requested. Closing exchange sessions...", flush=True) if self._shutdown_requested else None
            self.broker.save()
            self.write_status_file()
            report = self.write_lifecycle_report()
            artifacts: dict[str, Any] = {}
            if self.settings.cycle_artifacts_enabled:
                artifacts = await asyncio.to_thread(self.write_performance_artifacts)
            else:
                self.broker.emit("ENGINE_STOP_ARTIFACTS_SKIPPED", reason="cycle_artifacts_disabled")
            if self.settings.dry_run_once and self._last_completed_cycle_summary and not self._paper_once_console_summary_printed:
                print_paper_once_console_summary(
                    self._last_completed_cycle_summary,
                    runtime_audit=(artifacts.get("paper_unlock_runtime_audit") if isinstance(artifacts, dict) else None),
                    routing_bridge=(artifacts.get("paper_unlock_routing_bridge") if isinstance(artifacts, dict) else None),
                    lsr_v2_bridge=(artifacts.get("lsr_v2_paper_supervised_bridge") if isinstance(artifacts, dict) else None),
                    lsr_v2_runtime_bridge=(artifacts.get("lsr_v2_runtime_bridge") if isinstance(artifacts, dict) else None),
                    lsr_v2_engine_artifact_hook=(artifacts.get("lsr_v2_engine_read_only_artifact_hook") if isinstance(artifacts, dict) else None),
                )
                self._paper_once_console_summary_printed = True
            self.broker.emit("ENGINE_STOPPED", lifecycle_status=report.get("status"), shutdown_requested=self._shutdown_requested)
            self.broker.save()
            self.write_status_file()
            if self._shutdown_requested:
                await self._notify_shutdown(lifecycle_report=report, artifacts=artifacts, reason="CTRL+C / shutdown_requested")
            if tg_task:
                tg_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await tg_task
                self.broker.emit("ASYNC_TASK_CANCELLED", component="telegram_poll_forever")
            if hasattr(self, "telegram") and self.telegram:
                await self.telegram.close()
            await asyncio.sleep(0.250)  # Allow lingering aiohttp connections/sockets to close fully
            self.proactive.save()
            if self._shutdown_requested:
                print("[PaperEngine] Engine stopped cleanly.", flush=True)

    async def tick(self) -> dict[str, Any]:
        self._cycle_seq += 1
        cycle_id = f"pc_{self._cycle_seq:06d}_{uuid.uuid4().hex[:8]}"
        summary: dict[str, Any] = {
            "cycle_id": cycle_id,
            "scanned": 0,
            "signals": 0,
            "orders": 0,
            "errors": 0,
            "no_signal": 0,
            "skipped": 0,
        }
        self._active_cycle_id = cycle_id
        self._cycle_started_at = datetime.now(timezone.utc)
        self._lsr_v2_runtime_cycle_events = []
        self.broker.emit(
            "CYCLE_STARTED",
            cycle_id=cycle_id,
            symbols=self.settings.symbols,
            timeframe=self.settings.timeframe,
            cost_model=self.settings.cost_model,
            market_data_mode=self.settings.market_data_mode,
        )
        if self.broker.kill_switch:
            summary["skipped"] = len(self.settings.symbols)
            self.broker.emit("TICK_SKIPPED", cycle_id=cycle_id, reason="kill_switch")
            self.write_status_file()
            await self._finish_cycle(summary)
            self._active_cycle_id = None
            self._cycle_started_at = None
            return summary
        for symbol in self.settings.symbols:
            result = await self.evaluate_symbol(symbol, cycle_id=cycle_id)
            summary["scanned"] += int(result.get("scanned", 0))
            summary["signals"] += int(result.get("signal", 0))
            summary["orders"] += int(result.get("order", 0))
            summary["errors"] += int(result.get("error", 0))
            summary["no_signal"] += int(result.get("no_signal", 0))
            summary["skipped"] += int(result.get("skipped", 0))
        self.write_status_file()
        await self._finish_cycle(summary)
        self._active_cycle_id = None
        self._cycle_started_at = None
        return summary

    async def _finish_cycle(self, summary: dict[str, Any]) -> None:
        snapshot = self.broker.snapshot(self.last_prices)
        elapsed = 0.0
        if self._cycle_started_at is not None:
            elapsed = max(0.0, (datetime.now(timezone.utc) - self._cycle_started_at).total_seconds())
        summary.update({
            "open_positions": snapshot.get("open_positions", 0),
            "pending_orders": snapshot.get("pending_orders", 0),
            "equity": snapshot.get("equity", self.broker.balance),
            "balance": snapshot.get("balance", self.broker.balance),
            "realized_pnl": snapshot.get("realized_pnl", 0.0),
            "unrealized_pnl": snapshot.get("unrealized_pnl", 0.0),
            "drawdown_pct": snapshot.get("drawdown_pct", 0.0),
            "elapsed_seconds": round(elapsed, 4),
        })
        self.broker.emit("CYCLE_COMPLETED", **summary)
        self._last_completed_cycle_summary = dict(summary)
        self.write_lifecycle_report()
        artifacts: dict[str, Any] = {}
        if self.settings.cycle_artifacts_enabled:
            artifacts = await asyncio.to_thread(self.write_performance_artifacts)
        else:
            self.broker.emit("CYCLE_ARTIFACTS_SKIPPED", cycle_id=summary.get("cycle_id"), reason="cycle_artifacts_disabled")
        drift_status = artifacts.get("drift", {}).get("status") if isinstance(artifacts, dict) else "NA"
        self._print_cycle_summary(summary, drift_status=drift_status)
        if self.settings.dry_run_once:
            print_paper_once_console_summary(
                summary,
                runtime_audit=(artifacts.get("paper_unlock_runtime_audit") if isinstance(artifacts, dict) else None),
                routing_bridge=(artifacts.get("paper_unlock_routing_bridge") if isinstance(artifacts, dict) else None),
                lsr_v2_bridge=(artifacts.get("lsr_v2_paper_supervised_bridge") if isinstance(artifacts, dict) else None),
                lsr_v2_runtime_bridge=(artifacts.get("lsr_v2_runtime_bridge") if isinstance(artifacts, dict) else None),
                lsr_v2_engine_artifact_hook=(artifacts.get("lsr_v2_engine_read_only_artifact_hook") if isinstance(artifacts, dict) else None),
            )
            self._paper_once_console_summary_printed = True
        monitor_text = self.render_position_monitor()
        if monitor_text and (self.settings.console_verbose or int(summary.get("open_positions") or 0) > 0):
            print(monitor_text, flush=True)
        elif self.settings.console_show_flat_monitor and not monitor_text:
            print("PAPER POSITION MONITOR | FLAT", flush=True)
        await self._notify_after_cycle(summary, artifacts=artifacts, drift_status=str(drift_status or "NA"))

    def _console_header_line(self) -> str:
        tg_status = "ON" if self.telegram.enabled else "OFF"
        proactive = "ON" if self.settings.telegram_proactive_enabled else "OFF"
        ai_debug = "ON" if self.settings.ai_debug else "OFF"
        unlock = "ON" if self.unlock_settings.enabled else "OFF"
        return (
            f"PROGETTOTR PAPER ENGINE | PAPER | {self.settings.timeframe} | {self.settings.cost_model} | "
            f"Telegram {tg_status} | Proactive {proactive} | AI debug {ai_debug} | Unlock {unlock}"
        )

    def _print_startup_banner(self) -> None:
        if self._startup_banner_printed:
            return
        print(self._console_header_line(), flush=True)
        print(f"assets={','.join(self.settings.symbols)} poll={self.settings.poll_seconds:g}s", flush=True)
        self._startup_banner_printed = True

    def _print_cycle_summary(self, summary: dict[str, Any], *, drift_status: str) -> None:
        header_every = max(0, int(self.settings.console_header_every_n_cycles or 0))
        if header_every and self._cycle_seq > 0 and self._cycle_seq % header_every == 0:
            print(self._console_header_line(), flush=True)
        now_label = datetime.now().strftime("%H:%M:%S")
        base = (
            f"[{now_label}] cycle={self._cycle_seq} scanned={summary['scanned']} "
            f"signals={summary['signals']} orders={summary['orders']} pos={summary['open_positions']} "
            f"equity={float(summary['equity']):.2f} dd={float(summary['drawdown_pct']):.2f}% "
            f"drift={drift_status}"
        )
        if self.settings.console_verbose:
            base += (
                f" no_signal={summary['no_signal']} skipped={summary['skipped']} "
                f"errors={summary['errors']} elapsed={float(summary.get('elapsed_seconds') or 0.0):.2f}s"
            )
        else:
            base += f" errors={summary['errors']}"
        print(base, flush=True)

    async def _send_proactive(
        self,
        notification_type: str,
        text: str,
        *,
        event_type: str = "TELEGRAM_PROACTIVE_NOTIFICATION",
        dedup_key: str | None = None,
        force: bool = False,
        **payload: Any,
    ) -> bool:
        return await self.proactive.send(
            event_type=event_type,
            notification_type=notification_type,
            text=text,
            dedup_key=dedup_key,
            force=force,
            cycle_seq=self._cycle_seq,
            **payload,
        )

    async def _notify_startup(self) -> None:
        if not self.settings.telegram_notify_on_start:
            return
        text = (
            "🟢 PAPER BOT STARTED\n"
            "Mode: PAPER\n"
            f"Assets: {', '.join(self.settings.symbols)}\n"
            f"Timeframe: {self.settings.timeframe}\n"
            f"Cost model: {self.settings.cost_model}\n"
            f"Telegram: {'ON' if self.telegram.enabled else 'OFF'}\n"
            "Adapter: PaperBrokerAdapter\n"
            "Exchange: BLOCKED\n"
            "Live: DISABLED"
        )
        await self._send_proactive(
            "startup",
            text,
            event_type="TELEGRAM_STARTUP_NOTIFICATION",
            dedup_key=f"startup:{self._cycle_seq}:{self.settings.timeframe}:{self.settings.cost_model}",
            force=True,
        )

    async def _notify_shutdown(self, *, lifecycle_report: dict[str, Any] | None, artifacts: dict[str, Any] | None, reason: str) -> None:
        if not self.settings.telegram_notify_on_shutdown:
            return
        s = self.broker.snapshot(self.last_prices)
        drift_status = "NA"
        if isinstance(artifacts, dict):
            drift = artifacts.get("drift")
            if isinstance(drift, dict):
                drift_status = str(drift.get("status") or "NA")
        lifecycle_status = str((lifecycle_report or {}).get("status") or "NA")
        text = (
            "🔴 PAPER BOT STOPPED\n"
            f"Reason: {reason}\n"
            f"Cycle: {self._cycle_seq}\n"
            f"Equity: {float(s.get('equity') or 0.0):.2f}\n"
            f"Balance: {float(s.get('balance') or 0.0):.2f}\n"
            f"Open positions: {int(s.get('open_positions') or 0)}\n"
            f"Pending orders: {int(s.get('pending_orders') or 0)}\n"
            f"Realized PnL: {float(s.get('realized_pnl') or 0.0):+.2f}\n"
            f"Unrealized PnL: {float(s.get('unrealized_pnl') or 0.0):+.2f}\n"
            f"Drift: {drift_status}\n"
            f"Lifecycle: {lifecycle_status}"
        )
        sent = await self._send_proactive(
            "shutdown",
            text,
            event_type="TELEGRAM_SHUTDOWN_NOTIFICATION",
            dedup_key=f"shutdown:{self._cycle_seq}:{self._shutdown_requested}",
            force=True,
            drift_status=drift_status,
            lifecycle_status=lifecycle_status,
            open_positions=int(s.get("open_positions") or 0),
        )
        if sent:
            self.proactive.state.last_shutdown_notified = True
            self.proactive.save()
        if int(s.get("open_positions") or 0) > 0:
            await self._notify_position_monitor_if_needed(reason="shutdown", cycle_id=str(self._active_cycle_id or ""), force=True)

    def _cycle_summary_text(self, summary: dict[str, Any], *, drift_status: str) -> str:
        ratio = 0.0
        scanned = int(summary.get("scanned") or 0)
        if scanned > 0:
            ratio = float(summary.get("no_signal") or 0) / scanned * 100.0
        return (
            "PAPER SUMMARY\n"
            f"Cycle: {self._cycle_seq}\n"
            f"Scanned: {summary['scanned']}\n"
            f"Signals: {summary['signals']}\n"
            f"Orders: {summary['orders']}\n"
            f"Positions: {summary['open_positions']}\n"
            f"Equity: {float(summary['equity']):.2f}\n"
            f"No-signal ratio: {ratio:.1f}%\n"
            f"Drift: {drift_status}"
        )

    async def _notify_after_cycle(self, summary: dict[str, Any], *, artifacts: dict[str, Any], drift_status: str) -> None:
        if not self.settings.telegram_proactive_enabled:
            return
        notify_cycle = bool(self.settings.telegram_notify_every_cycle)
        no_signal_every = max(0, int(self.settings.telegram_notify_no_signal_every_n_cycles or 0))
        if (
            not notify_cycle
            and no_signal_every
            and int(summary.get("signals") or 0) == 0
            and int(summary.get("orders") or 0) == 0
            and self._cycle_seq % no_signal_every == 0
            and self.proactive.state.last_summary_cycle != self._cycle_seq
        ):
            notify_cycle = True
        if notify_cycle:
            sent = await self._send_proactive(
                "periodic_summary",
                self._cycle_summary_text(summary, drift_status=drift_status),
                event_type="TELEGRAM_PERIODIC_SUMMARY_NOTIFICATION",
                dedup_key=f"summary:{self._cycle_seq}",
                cycle_id=summary.get("cycle_id"),
            )
            if sent:
                self.proactive.state.last_summary_cycle = self._cycle_seq
                self.proactive.save()

        if self.settings.telegram_notify_on_drift_warn and drift_status in {"WARN", "FAIL"}:
            alerts = []
            drift = artifacts.get("drift") if isinstance(artifacts, dict) else {}
            if isinstance(drift, dict):
                for alert in drift.get("alerts", [])[:8]:
                    code = alert.get("code") if isinstance(alert, dict) else None
                    severity = alert.get("severity") if isinstance(alert, dict) else None
                    if code:
                        alerts.append(f"{severity or ''} {code}".strip())
            alert_hash = stable_hash({"status": drift_status, "alerts": alerts})
            if alert_hash != self.proactive.state.last_drift_alert_hash:
                detail = "\n" + "\n".join(f"- {a}" for a in alerts) if alerts else ""
                sent = await self._send_proactive(
                    "drift_warning",
                    f"⚠️ PAPER DRIFT {drift_status}\nCycle: {self._cycle_seq}\nEquity: {float(summary['equity']):.2f}\nAlerts:{detail}",
                    event_type="TELEGRAM_DRIFT_NOTIFICATION",
                    dedup_key=f"drift:{alert_hash}",
                    cycle_id=summary.get("cycle_id"),
                    drift_status=drift_status,
                )
                if sent:
                    self.proactive.state.last_drift_alert_hash = alert_hash
                    self.proactive.save()
        self._last_drift_status = drift_status

        await self._notify_position_monitor_if_needed(reason="cycle", cycle_id=str(summary.get("cycle_id") or ""))

    def _position_tp_sl_state(self, pos: Any) -> str:
        tp1_hit = False
        tp2_hit = False
        sl_hit = False
        try:
            if str(pos.side).upper() == "BUY":
                tp1_hit = pos.take_profit_1 is not None and pos.mark_price >= pos.take_profit_1
                tp2_hit = pos.take_profit_2 is not None and pos.mark_price >= pos.take_profit_2
                sl_hit = pos.stop_loss is not None and pos.mark_price <= pos.stop_loss
            else:
                tp1_hit = pos.take_profit_1 is not None and pos.mark_price <= pos.take_profit_1
                tp2_hit = pos.take_profit_2 is not None and pos.mark_price <= pos.take_profit_2
                sl_hit = pos.stop_loss is not None and pos.mark_price >= pos.stop_loss
        except Exception:
            pass
        return f"tp1={int(tp1_hit)}|tp2={int(tp2_hit)}|sl={int(sl_hit)}"

    async def _notify_position_monitor_if_needed(self, *, reason: str, cycle_id: str = "", force: bool = False) -> None:
        if not self.settings.telegram_proactive_enabled or not self.telegram.enabled:
            return
        snapshot = self.broker_adapter.reconcile()
        if not snapshot.positions:
            return
        notify_every_cycles = max(1, int(self.settings.telegram_notify_position_every_n_cycles or 1))
        notify_every_seconds = max(0.0, float(self.settings.telegram_notify_position_every_seconds or 0.0))
        pnl_delta = max(0.0, float(self.settings.telegram_notify_position_pnl_delta_pct or 0.0))
        now_ts = datetime.now(timezone.utc).timestamp()
        should_send = bool(force)
        reasons: list[str] = [reason] if reason else []
        for pos in snapshot.positions:
            pid = str(pos.position_id)
            last_cycle = int(self.proactive.state.last_position_monitor_cycle.get(pid, -10**9) or -10**9)
            last_ts = float(self.proactive.state.last_position_monitor_sent_at.get(pid, 0.0) or 0.0)
            last_pnl_pct = self.proactive.state.last_position_pnl_pct.get(pid)
            current_state = self._position_tp_sl_state(pos)
            last_state = self.proactive.state.last_position_tp_sl_state.get(pid)
            if self._cycle_seq - last_cycle >= notify_every_cycles:
                should_send = True
                reasons.append("cycle_interval")
            if notify_every_seconds and now_ts - last_ts >= notify_every_seconds:
                should_send = True
                reasons.append("time_interval")
            if last_pnl_pct is None or abs(float(pos.unrealized_pnl_pct) - float(last_pnl_pct)) >= pnl_delta:
                should_send = True
                reasons.append("pnl_delta")
            if last_state is not None and current_state != last_state:
                should_send = True
                reasons.append("tp_sl_state_change")
            self.proactive.state.last_position_pnl_pct[pid] = float(pos.unrealized_pnl_pct)
            self.proactive.state.last_position_tp_sl_state[pid] = current_state
        if not should_send:
            self.proactive.save()
            return
        for pos in snapshot.positions:
            pid = str(pos.position_id)
            self.proactive.state.last_position_monitor_cycle[pid] = self._cycle_seq
            self.proactive.state.last_position_monitor_sent_at[pid] = now_ts
        self.proactive.save()
        monitor = self.position_monitor.format_telegram(account=snapshot.account, positions=snapshot.positions)
        event_type = "TELEGRAM_POSITION_MONITOR_NOTIFICATION" if force else "TELEGRAM_POSITION_UPDATE_NOTIFICATION"
        await self._send_proactive(
            "position_monitor",
            monitor,
            event_type=event_type,
            dedup_key=f"position_monitor:{stable_hash(monitor)}",
            reason=reason,
            trigger_reasons=sorted(set(reasons)),
            cycle_id=cycle_id,
            open_positions=len(snapshot.positions),
        )

    async def _notify_unlock_signal(self, *, symbol: str, side: str, decision: Any, cycle_id: str) -> None:
        if not self.settings.telegram_notify_on_signal:
            return
        data = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision or {})
        await self._send_proactive(
            "paper_unlock_signal",
            "🟡 PAPER UNLOCK SIGNAL\n"
            f"Profile: {data.get('profile', self.unlock_settings.profile)}\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"AI probability: {float(data.get('ai_prob') or 0.0):.2f}\n"
            f"Setup quality: {float(data.get('setup_quality') or 0.0):.2f}\n"
            f"Tech score: {float(data.get('technical_score') or 0.0):.2f}\n"
            f"Filter: {data.get('dominant_filter', '-')}\n"
            "Reason: shadow-to-paper controlled test\n"
            "Live: DISABLED\n"
            f"Cycle: {cycle_id}",
            event_type="TELEGRAM_UNLOCK_SIGNAL_NOTIFICATION",
            dedup_key=f"unlock_signal:{cycle_id}:{symbol}:{side}",
            symbol=symbol,
            side=side,
            cycle_id=cycle_id,
            unlock_profile=str(data.get('profile', self.unlock_settings.profile)),
        )

    async def _notify_signal_detected(self, *, symbol: str, side: str, score: Any, conf: dict[str, Any], cycle_id: str) -> None:
        if not self.settings.telegram_notify_on_signal:
            return
        ai_prob = conf.get("ai_prob") if isinstance(conf, dict) else None
        setup_quality = conf.get("setup_quality") if isinstance(conf, dict) else None
        if isinstance(conf, dict):
            regime = conf.get("regime") or conf.get("market_regime") or "-"
            archetype = conf.get("setup_archetype") or conf.get("archetype") or conf.get("combination") or "-"
        else:
            regime = "-"
            archetype = "-"
        await self._send_proactive(
            "signal_detected",
            "🟡 PAPER SIGNAL DETECTED\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Regime: {regime}\n"
            f"Score: {score}\n"
            f"AI probability: {ai_prob}\n"
            f"Quality: {setup_quality}\n"
            f"Archetype: {archetype}\n"
            f"Reason: Score {score} | {regime} | {archetype}\n"
            f"Cycle: {cycle_id}",
            event_type="TELEGRAM_SIGNAL_NOTIFICATION",
            dedup_key=f"signal:{cycle_id}:{symbol}:{side}",
            symbol=symbol,
            side=side,
            cycle_id=cycle_id,
        )

    async def _notify_order_filled(self, *, symbol: str, side: str, order_id: str, qty: float, price: float, stop_loss: float, take_profit: float, cycle_id: str) -> None:
        if not self.settings.telegram_notify_on_order:
            return
        notional = abs(float(qty) * float(price))
        fee_estimate = notional * self.broker.fee_rate
        risk_amount = abs(float(price) - float(stop_loss)) * abs(float(qty))
        await self._send_proactive(
            "order_filled",
            "🔵 PAPER ORDER FILLED\n"
            f"Symbol: {symbol}\n"
            f"Side: {side}\n"
            f"Entry: {price:.6f}\n"
            f"Size: {qty:.6f}\n"
            f"Notional: {notional:.2f}\n"
            f"Risk: {risk_amount:.2f}\n"
            f"Fee estimate: {fee_estimate:.4f}\n"
            f"Cycle: {cycle_id}\n"
            f"Order ID: {order_id}",
            event_type="TELEGRAM_ORDER_NOTIFICATION",
            dedup_key=f"order:{order_id}",
            symbol=symbol,
            side=side,
            order_id=order_id,
            cycle_id=cycle_id,
        )

    async def _notify_position_opened(self, *, symbol: str, side: str, cycle_id: str) -> None:
        if not self.settings.telegram_notify_on_position_open:
            return
        snapshot = self.broker_adapter.reconcile()
        matching = [p for p in snapshot.positions if p.symbol == symbol and str(p.side).upper() == side]
        pos = matching[-1] if matching else (snapshot.positions[-1] if snapshot.positions else None)
        if pos is None:
            await self._send_proactive(
                "position_opened",
                f"🟢 PAPER POSITION OPENED\nSymbol: {symbol}\nDirection: {side}\nCycle: {cycle_id}",
                event_type="TELEGRAM_POSITION_OPEN_NOTIFICATION",
                dedup_key=f"position_open:{cycle_id}:{symbol}:{side}",
                symbol=symbol,
                side=side,
                cycle_id=cycle_id,
            )
        else:
            direction = "LONG" if str(pos.side).upper() == "BUY" else "SHORT"
            risk_amount = abs(float(pos.entry_price) - float(pos.stop_loss or pos.entry_price)) * abs(float(pos.qty))
            await self._send_proactive(
                "position_opened",
                "🟢 PAPER POSITION OPENED\n"
                f"Symbol: {pos.symbol}\n"
                f"Direction: {direction}\n"
                f"Entry: {pos.entry_price:.6f}\n"
                f"Current: {pos.mark_price:.6f}\n"
                f"Size: {pos.qty:.6f}\n"
                f"Notional: {pos.notional:.2f}\n"
                f"Margin used: {pos.margin_estimate:.2f}\n"
                f"Risk amount: {risk_amount:.2f}\n"
                f"SL: {pos.stop_loss}\n"
                f"TP1: {pos.take_profit_1}\n"
                f"TP2: {pos.take_profit_2}\n"
                f"Reason: {pos.reason or '-'}",
                event_type="TELEGRAM_POSITION_OPEN_NOTIFICATION",
                dedup_key=f"position_open:{pos.position_id}",
                symbol=pos.symbol,
                side=str(pos.side),
                position_id=pos.position_id,
                cycle_id=cycle_id,
            )
        await self._notify_position_monitor_if_needed(reason="position_opened", cycle_id=cycle_id, force=True)

    async def _notify_positions_closed(self, closed: list[Any], *, cycle_id: str) -> None:
        if not closed:
            return
        for p in closed[:10]:
            symbol = str(getattr(p, "symbol", "-"))
            side = str(getattr(p, "side", "-"))
            reason = str(getattr(p, "close_reason", "-") or "-").upper()
            exit_price = float(getattr(p, "exit_price", 0.0) or 0.0)
            entry_price = float(getattr(p, "entry_price", 0.0) or 0.0)
            qty = float(getattr(p, "qty", 0.0) or 0.0)
            pnl = float(getattr(p, "realized_pnl", 0.0) or 0.0)
            base = abs(qty * entry_price) or 1.0
            pnl_pct = pnl / base * 100.0
            equity = float(self.broker.snapshot(self.last_prices).get("equity") or self.broker.balance)
            direction = "LONG" if side.upper() == "BUY" else "SHORT"
            if self.settings.telegram_notify_on_tp_sl and reason in {"TP", "SL"}:
                if reason == "TP":
                    await self._send_proactive(
                        "take_profit_hit",
                        "✅ PAPER TAKE PROFIT HIT\n"
                        f"Symbol: {symbol}\n"
                        "Level: TP\n"
                        f"Price: {exit_price:.6f}\n"
                        f"PnL: {pnl:+.2f}\n"
                        f"Equity: {equity:.2f}",
                        event_type="TELEGRAM_TP_NOTIFICATION",
                        dedup_key=f"tp:{getattr(p, 'position_id', '')}:{exit_price}",
                        symbol=symbol,
                        position_id=str(getattr(p, "position_id", "")),
                        cycle_id=cycle_id,
                    )
                else:
                    await self._send_proactive(
                        "stop_loss_hit",
                        "❌ PAPER STOP LOSS HIT\n"
                        f"Symbol: {symbol}\n"
                        f"Price: {exit_price:.6f}\n"
                        f"PnL: {pnl:+.2f}\n"
                        f"Equity: {equity:.2f}",
                        event_type="TELEGRAM_SL_NOTIFICATION",
                        dedup_key=f"sl:{getattr(p, 'position_id', '')}:{exit_price}",
                        symbol=symbol,
                        position_id=str(getattr(p, "position_id", "")),
                        cycle_id=cycle_id,
                    )
            if self.settings.telegram_notify_on_position_close:
                await self._send_proactive(
                    "position_closed",
                    "⚪ PAPER POSITION CLOSED\n"
                    f"Symbol: {symbol}\n"
                    f"Direction: {direction}\n"
                    f"Entry: {entry_price:.6f}\n"
                    f"Exit: {exit_price:.6f}\n"
                    f"Size: {qty:.6f}\n"
                    f"Realized PnL: {pnl:+.2f}\n"
                    f"PnL %: {pnl_pct:+.2f}%\n"
                    f"Reason: {reason}\n"
                    f"Equity: {equity:.2f}",
                    event_type="TELEGRAM_POSITION_CLOSE_NOTIFICATION",
                    dedup_key=f"position_close:{getattr(p, 'position_id', '')}:{reason}",
                    symbol=symbol,
                    position_id=str(getattr(p, "position_id", "")),
                    cycle_id=cycle_id,
                )

    def _paper_once_progress_logs_enabled(self) -> bool:
        """Return whether Prompt 29.4.4o-3b console progress logs should print.

        This is visibility-only: it does not alter fetch, evaluation, routing,
        broker state, risk, gates, orders, or positions. By default it is active
        for --once runs, where silence after model registry loading can be
        mistaken for a frozen process.
        """
        env_value = str(os.getenv("PAPER_ONCE_PROGRESS_LOGS", "") or "").strip().lower()
        if env_value in {"0", "false", "no", "off"}:
            return False
        if env_value in {"1", "true", "yes", "on"}:
            return True
        return bool(self.settings.dry_run_once)

    def _print_once_progress(self, message: str) -> None:
        if self._paper_once_progress_logs_enabled():
            print(message, flush=True)

    def _emit_lsr_v2_runtime_bridge_for_symbol(self, *, symbol: str, df: Any, cycle_id: str) -> None:
        """Emit cycle-scoped LSR-v2 audit events for one scanned symbol.

        This is intentionally fail-closed.  It never routes, submits orders,
        opens positions, or mutates paper state; it only appends diagnostics to
        the event log and to the in-memory cycle artifact list.
        """
        if not self.settings.lsr_v2_paper_supervised_bridge_enabled:
            return
        try:
            promotion_report = {}
            promotion_path = self.data_dir / "lsr_v2_promotion_gate_report.json"
            if promotion_path.exists():
                try:
                    promotion_report = json.loads(promotion_path.read_text(encoding="utf-8"))
                    if not isinstance(promotion_report, dict):
                        promotion_report = {}
                except Exception:
                    promotion_report = {}
            candidate_event, bridge_event = build_lsr_v2_runtime_bridge_events_for_symbol(
                df=df,
                cycle_id=cycle_id,
                symbol=symbol,
                timeframe=str(self.settings.timeframe or "5m"),
                promotion_gate_report=promotion_report,
                bridge_settings=self.lsr_v2_bridge_settings,
                runtime_settings=self.lsr_v2_runtime_bridge_settings,
                open_positions_count=len(self.broker.open_positions),
            )
            # Force-pin runtime safety before the generic event writer sees it.
            for payload in (candidate_event, bridge_event):
                payload["would_submit"] = False
                payload["broker_submit_called"] = False
                payload["routing_enabled"] = False
                payload["execution_enabled"] = False
                payload["paper_order_submission_enabled"] = False
                payload["live_enabled"] = False
                payload["testnet_enabled"] = False
                payload["exchange_broker_enabled"] = False
                payload["orders_submitted_by_lsr_v2_runtime_bridge"] = 0
                payload["positions_opened_by_lsr_v2_runtime_bridge"] = 0
                self._lsr_v2_runtime_cycle_events.append(dict(payload))
                self.broker.emit(**payload)
            # s-10e: write the cycle-scoped runtime report incrementally. The
            # watchdog hard-exit path can print the footer before the normal
            # end-of-cycle artifacts are produced, so the report must exist as
            # soon as symbol-level audit events are emitted. This is diagnostic
            # only and force-pins all submission counters to zero.
            try:
                self.write_lsr_v2_runtime_bridge_report()
            except Exception as report_exc:
                self.broker.emit(
                    "LSR_V2_RUNTIME_BRIDGE_REPORT_WRITE_FAILED",
                    prompt_id="29.4.4s-10f-1",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    error=str(report_exc),
                    orders_submitted_by_lsr_v2_runtime_bridge=0,
                    positions_opened_by_lsr_v2_runtime_bridge=0,
                    broker_submit_called=False,
                    would_submit=False,
                )
        except Exception as exc:
            self.broker.emit(
                "LSR_V2_RUNTIME_BRIDGE_APPEND_FAILED",
                prompt_id="29.4.4s-10f-1",
                cycle_id=cycle_id,
                symbol=symbol,
                error=str(exc),
                orders_submitted_by_lsr_v2_runtime_bridge=0,
                positions_opened_by_lsr_v2_runtime_bridge=0,
                broker_submit_called=False,
                would_submit=False,
            )

    async def evaluate_symbol(self, symbol: str, *, cycle_id: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {"symbol": symbol, "scanned": 0, "signal": 0, "order": 0, "error": 0, "no_signal": 0, "skipped": 0}
        client: ExchangeClient | None = None
        progress_phase = "init"
        fetch_started_at = 0.0
        evaluate_started_at = 0.0
        candle_limit = int(os.getenv("PAPER_CANDLE_LIMIT", "500"))
        try:
            progress_phase = "fetch"
            fetch_started_at = time.monotonic()
            self._print_once_progress(
                f"[FETCH START] symbol={symbol} timeframe={self.settings.timeframe} limit={candle_limit}"
            )
            df = await self._fetch_market_data(symbol=symbol, limit=candle_limit, cycle_id=cycle_id)
            fetch_elapsed = max(0.0, time.monotonic() - fetch_started_at)
            candle_count = 0 if df is None else int(getattr(df, "shape", [0])[0] or 0)
            self._print_once_progress(
                f"[FETCH DONE] symbol={symbol} candles={candle_count} elapsed_seconds={fetch_elapsed:.4f}"
            )
            self.broker.emit("EXCHANGE_CLIENT_CLOSED", cycle_id=cycle_id, symbol=symbol)
            if df is None or df.empty:
                self.broker.emit("MARKET_DATA_EMPTY", cycle_id=cycle_id, symbol=symbol)
                result["error"] = 1
                return result
            df = TechnicalAnalyzer().add_indicators(df, is_live=True)
            last = df.iloc[-1]
            last_price = float(last["Close"])
            candle_ts = str(df.index[-1])
            self.last_prices[symbol] = last_price
            result["scanned"] = 1
            closed = self.broker.update_stops(symbol, high=float(last["High"]), low=float(last["Low"]), last=last_price)
            if closed:
                await self._notify_positions_closed(closed, cycle_id=cycle_id)
            self.broker.emit(
                "ASSET_SCANNED",
                cycle_id=cycle_id,
                symbol=symbol,
                candle_ts=candle_ts,
                last_price=last_price,
                closed_positions=len(closed),
            )
            self._emit_lsr_v2_runtime_bridge_for_symbol(symbol=symbol, df=df, cycle_id=cycle_id)
            if self.broker.is_paused:
                result["skipped"] = 1
                self.broker.emit("ASSET_SKIPPED", cycle_id=cycle_id, symbol=symbol, reason="paused")
                return result
            if len(self.broker.open_positions) >= self.settings.max_positions:
                result["skipped"] = 1
                self.broker.emit("ASSET_SKIPPED", cycle_id=cycle_id, symbol=symbol, reason="max_positions")
                return result
            # One open position per symbol in the initial paper engine.
            if any(p.symbol == symbol for p in self.broker.open_positions):
                result["skipped"] = 1
                self.broker.emit("ASSET_SKIPPED", cycle_id=cycle_id, symbol=symbol, reason="position_already_open")
                return result
            progress_phase = "evaluate"
            evaluate_started_at = time.monotonic()
            self._print_once_progress(f"[EVALUATE START] symbol={symbol}")
            verdict, score, conf, _entry_type, _conf_verdict, conf_comb = DecisionEngine().evaluate(df)
            candle_key = f"{symbol}:{candle_ts}"
            duplicate_candle = bool(verdict in {"BUY", "SELL"} and self.last_signal_by_symbol.get(symbol) == candle_key)
            unlock_duplicate_candle = bool(self.last_signal_by_symbol.get(symbol) == candle_key)
            signal_diag: dict[str, Any] | None = None
            if self.settings.signal_diagnostics_enabled:
                signal_diag = build_signal_diagnostic(
                    symbol=symbol,
                    df=df,
                    final_verdict=verdict,
                    final_score=score,
                    confidence=conf,
                    entry_type=_entry_type,
                    conf_verdict=_conf_verdict,
                    conf_comb=conf_comb,
                    cycle_id=cycle_id,
                    candle_ts=candle_ts,
                    last_price=last_price,
                    duplicate_candle=duplicate_candle or unlock_duplicate_candle,
                )
                self.broker.emit(**signal_diag)

            scenario_diag: dict[str, Any] | None = None
            if self.settings.crypto_scenario_enabled:
                scenario_diag = build_crypto_scenario_diagnostic(
                    symbol=symbol,
                    df=df,
                    cycle_id=cycle_id,
                    candle_ts=candle_ts,
                    final_verdict=verdict,
                    final_score=score,
                    signal_diagnostic=signal_diag,
                    confidence=conf,
                )
                self.broker.emit(**scenario_diag)

            pattern_diag: dict[str, Any] | None = None
            if self.settings.candlestick_patterns_enabled:
                pattern_diag = build_candlestick_pattern_diagnostic(
                    symbol=symbol,
                    df=df,
                    cycle_id=cycle_id,
                    candle_ts=candle_ts,
                    scenario_diagnostic=scenario_diag,
                    signal_diagnostic=signal_diag,
                    confidence=conf,
                )
                self.broker.emit(**pattern_diag)

            structure_diag: dict[str, Any] | None = None
            if self.settings.market_structure_map_enabled:
                structure_diag = build_market_structure_map_diagnostic(
                    symbol=symbol,
                    df=df,
                    cycle_id=cycle_id,
                    candle_ts=candle_ts,
                    scenario_diagnostic=scenario_diag,
                    pattern_diagnostic=pattern_diag,
                    signal_diagnostic=signal_diag,
                    confidence=conf,
                )
                self.broker.emit(**structure_diag)

            guarded_enable_state = guarded_enable_runtime_state(self.data_dir, self.runtime_audit_settings) if self.settings.paper_unlock_runtime_audit_enabled else {}
            unlock_decision = None
            if verdict not in {"BUY", "SELL"} and self.unlock_settings.enabled:
                unlock_decision = evaluate_paper_unlock(
                    settings=self.unlock_settings,
                    signal_diagnostic=signal_diag,
                    symbol=symbol,
                    mode=self.settings.mode,
                    duplicate_candle=unlock_duplicate_candle,
                    open_positions_count=len(self.broker.open_positions),
                )
                self.broker.emit(
                    "PAPER_UNLOCK_EVALUATED",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    candle_ts=candle_ts,
                    accepted=bool(unlock_decision.accepted),
                    reason=unlock_decision.reason,
                    decision=unlock_decision.to_dict(),
                )
                if unlock_decision.accepted:
                    verdict = unlock_decision.side
                    score = int(round(unlock_decision.technical_score))
                    conf = dict(conf or {})
                    conf.update({
                        "ai_prob": unlock_decision.ai_prob,
                        "setup_quality": unlock_decision.setup_quality,
                        "tech_score": unlock_decision.technical_score,
                        "paper_unlock": True,
                        "unlock_profile": unlock_decision.profile,
                        "unlock_reason": unlock_decision.reason,
                        "crypto_scenario": ((scenario_diag or {}).get("scenario") if scenario_diag else None),
                        "scenario_directional_bias": ((scenario_diag or {}).get("directional_bias") if scenario_diag else None),
                        "candlestick_patterns": ((pattern_diag or {}).get("patterns") if pattern_diag else None),
                        "candlestick_bias": ((pattern_diag or {}).get("pattern_bias") if pattern_diag else None),
                        "candlestick_integration": ((pattern_diag or {}).get("scenario_integration") if pattern_diag else None),
                        "market_structure_bias": ((structure_diag or {}).get("structure_bias") if structure_diag else None),
                        "market_structure_confirmation": ((structure_diag or {}).get("confirmation_summary") if structure_diag else None),
                    })
                    _entry_type = "PAPER_UNLOCK"
                    _conf_verdict = "PAPER_UNLOCK"
                    conf_comb = f"PaperUnlock({unlock_decision.profile})"

            if self.settings.paper_unlock_runtime_audit_enabled and self.runtime_audit_settings.emit_runtime_events:
                runtime_audit_event = build_guarded_runtime_audit_event(
                    settings=self.runtime_audit_settings,
                    guarded_enable_state=guarded_enable_state,
                    cycle_id=cycle_id,
                    symbol=symbol,
                    candle_ts=candle_ts,
                    mode=self.settings.mode,
                    signal_diagnostic=signal_diag,
                    scenario_diagnostic=scenario_diag,
                    pattern_diagnostic=pattern_diag,
                    structure_diagnostic=structure_diag,
                    legacy_unlock_decision=(unlock_decision.to_dict() if unlock_decision is not None else {}),
                    duplicate_candle=unlock_duplicate_candle,
                    open_positions_count=len(self.broker.open_positions),
                )
                self.broker.emit(**runtime_audit_event)
                if self.settings.paper_unlock_routing_bridge_enabled and self.routing_bridge_settings.emit_bridge_events:
                    routing_bridge_event = build_guarded_paper_routing_bridge_event(
                        settings=self.routing_bridge_settings,
                        runtime_audit_event=runtime_audit_event,
                        cycle_id=cycle_id,
                        symbol=symbol,
                        open_positions_count=len(self.broker.open_positions),
                    )
                    self.broker.emit(**routing_bridge_event)
                    if (
                        self.settings.paper_unlock_candidate_audit_enabled
                        and self.candidate_audit_settings.enabled
                        and self.candidate_audit_settings.emit_candidate_events
                        and bool(routing_bridge_event.get("would_submit"))
                    ):
                        candidate_atr = float(last.get("atr", 0.0) or 0.0) or last_price * 0.01
                        candidate_event = build_guarded_paper_order_candidate_audit_event(
                            settings=self.candidate_audit_settings,
                            routing_bridge_event=routing_bridge_event,
                            cycle_id=cycle_id,
                            symbol=symbol,
                            candle_ts=candle_ts,
                            entry_price=last_price,
                            atr=candidate_atr,
                            account_balance=float(self.broker.balance),
                            equity=float(self.broker.snapshot(self.last_prices).get("equity") or self.broker.balance),
                            open_positions_count=len(self.broker.open_positions),
                            duplicate_candle=unlock_duplicate_candle,
                            duplicate_order=False,
                            daily_entry_count=0,
                            weekly_entry_count=0,
                            max_daily_entries=int(getattr(Config, "PAPER_UNLOCK_GUARDED_ENABLE_MAX_DAILY_ENTRIES", 6) or 6),
                            max_weekly_entries=int(getattr(Config, "PAPER_UNLOCK_GUARDED_ENABLE_MAX_WEEKLY_ENTRIES", 30) or 30),
                        )
                        self.broker.emit(**candidate_event)
                        if (
                            self.settings.paper_unlock_handoff_dry_run_enabled
                            and self.handoff_dry_run_settings.enabled
                            and self.handoff_dry_run_settings.emit_handoff_events
                            and bool(candidate_event.get("candidate_ready"))
                        ):
                            handoff_event = build_paper_order_handoff_dry_run_event(
                                settings=self.handoff_dry_run_settings,
                                candidate_event=candidate_event,
                                open_positions_count=len(self.broker.open_positions),
                            )
                            self.broker.emit(**handoff_event)
                            if self.settings.paper_unlock_supervised_execution_enabled:
                                supervised_probe_event = build_paper_supervised_execution_event(
                                    settings=self.supervised_execution_settings,
                                    handoff_event=handoff_event,
                                    open_positions_count=len(self.broker.open_positions),
                                )
                                if bool(supervised_probe_event.get("supervised_submit_allowed")):
                                    supervised_metadata = {
                                        "score": score,
                                        "confidence": conf,
                                        "combination": "GuardedSupervisedPaperExecution",
                                        "timeframe": self.settings.timeframe,
                                        "cost_model": self.settings.cost_model,
                                        "candle_ts": str(df.index[-1]),
                                        "cycle_id": cycle_id,
                                        "paper_unlock": True,
                                        "unlock_profile": supervised_probe_event.get("profile_name"),
                                        "unlock_tag": "PAPER_SUPERVISED_EXECUTION_29_4_4S",
                                        "guarded_supervised_execution": True,
                                        "paper_order_source": "guarded_supervised_execution",
                                        "execution_source": "guarded_supervised_execution",
                                        "candidate_ready": True,
                                        "handoff_would_create_order": True,
                                        "source_handoff_event_type": handoff_event.get("event_type"),
                                        "source_candidate_event_type": candidate_event.get("event_type"),
                                        "market_structure_bias": ((structure_diag or {}).get("structure_bias") if structure_diag else None),
                                        "market_structure_location": ((structure_diag or {}).get("price_location") if structure_diag else None),
                                        "market_structure_confirmation": ((structure_diag or {}).get("confirmation_summary") if structure_diag else None),
                                    }
                                    try:
                                        supervised_order = self.broker_adapter.place_order(
                                            symbol=str(supervised_probe_event.get("symbol") or symbol),
                                            side=str(supervised_probe_event.get("side") or verdict),  # type: ignore[arg-type]
                                            qty=float(supervised_probe_event.get("position_size") or 0.0),
                                            price=float(supervised_probe_event.get("entry_price") or last_price),
                                            stop_loss=float(supervised_probe_event.get("stop_loss") or 0.0),
                                            take_profit=float(supervised_probe_event.get("take_profit") or 0.0),
                                            metadata=supervised_metadata,
                                        )
                                        supervised_event = build_paper_supervised_execution_event(
                                            settings=self.supervised_execution_settings,
                                            handoff_event=handoff_event,
                                            open_positions_count=max(0, len(self.broker.open_positions) - 1),
                                            broker_submit_called=True,
                                            order_submitted=True,
                                            position_opened=True,
                                            order_id=supervised_order.order_id,
                                        )
                                        self.broker.emit(**supervised_event)
                                        result["signal"] = 1
                                        result["order"] = 1
                                        await self._notify_order_filled(
                                            symbol=str(supervised_event.get("symbol") or symbol),
                                            side=str(supervised_event.get("side") or verdict),
                                            order_id=supervised_order.order_id,
                                            qty=float(supervised_event.get("position_size") or 0.0),
                                            price=float(supervised_event.get("entry_price") or last_price),
                                            stop_loss=float(supervised_event.get("stop_loss") or 0.0),
                                            take_profit=float(supervised_event.get("take_profit") or 0.0),
                                            cycle_id=cycle_id,
                                        )
                                        await self._notify_position_opened(symbol=str(supervised_event.get("symbol") or symbol), side=str(supervised_event.get("side") or verdict), cycle_id=cycle_id)
                                        return result
                                    except Exception as exc:
                                        supervised_event = build_paper_supervised_execution_event(
                                            settings=self.supervised_execution_settings,
                                            handoff_event=handoff_event,
                                            open_positions_count=len(self.broker.open_positions),
                                            broker_submit_called=True,
                                            order_submitted=False,
                                            position_opened=False,
                                            error=str(exc),
                                        )
                                        self.broker.emit(**supervised_event)
                                else:
                                    self.broker.emit(**supervised_probe_event)

            evaluate_elapsed = max(0.0, time.monotonic() - evaluate_started_at) if evaluate_started_at else 0.0
            structure_state = ""
            map_score = ""
            if isinstance(structure_diag, dict):
                structure_state = str(
                    structure_diag.get("runtime_structure_state")
                    or structure_diag.get("structure_state")
                    or structure_diag.get("state")
                    or structure_diag.get("confirmation_summary")
                    or ""
                )
                map_score = structure_diag.get("map_score", "")
            self._print_once_progress(
                f"[EVALUATE DONE] symbol={symbol} side={verdict} signal={1 if verdict in {'BUY', 'SELL'} else 0} "
                f"map_score={map_score} structure_state={structure_state} elapsed_seconds={evaluate_elapsed:.4f}"
            )

            if verdict not in {"BUY", "SELL"}:
                result["no_signal"] = 1
                self.broker.emit(
                    "NO_SIGNAL",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    verdict=verdict,
                    score=score,
                    confidence=conf,
                    candle_ts=candle_ts,
                    diagnostic_filter=(signal_diag or {}).get("dominant_filter"),
                    diagnostic_reason=(signal_diag or {}).get("diagnostic_reason"),
                    scenario=(scenario_diag or {}).get("scenario") if scenario_diag else None,
                    scenario_directional_bias=(scenario_diag or {}).get("directional_bias") if scenario_diag else None,
                    scenario_current_zone=(scenario_diag or {}).get("current_zone") if scenario_diag else None,
                    scenario_recommendation=(scenario_diag or {}).get("recommendation") if scenario_diag else None,
                    scenario_alignment=(scenario_diag or {}).get("scenario_alignment") if scenario_diag else None,
                    candlestick_patterns=(pattern_diag or {}).get("patterns") if pattern_diag else None,
                    candlestick_bias=(pattern_diag or {}).get("pattern_bias") if pattern_diag else None,
                    candlestick_score=(pattern_diag or {}).get("pattern_score") if pattern_diag else None,
                    candlestick_integration=(pattern_diag or {}).get("scenario_integration") if pattern_diag else None,
                    candlestick_alignment=(pattern_diag or {}).get("pattern_alignment") if pattern_diag else None,
                    market_structure_bias=(structure_diag or {}).get("structure_bias") if structure_diag else None,
                    market_structure_location=(structure_diag or {}).get("price_location") if structure_diag else None,
                    market_structure_confirmation=(structure_diag or {}).get("confirmation_summary") if structure_diag else None,
                    market_structure_missing_confirmation=(structure_diag or {}).get("missing_confirmation") if structure_diag else None,
                    exploratory_candidate=(signal_diag or {}).get("exploratory_candidate"),
                    paper_unlock_evaluated=bool(unlock_decision is not None),
                    paper_unlock_accepted=False if unlock_decision is not None else None,
                    paper_unlock_reason=(unlock_decision.reason if unlock_decision is not None else None),
                )
                return result
            if duplicate_candle:
                result["no_signal"] = 1
                self.broker.emit(
                    "NO_SIGNAL",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    verdict=verdict,
                    reason="duplicate_candle",
                    score=score,
                    confidence=conf,
                    candle_ts=candle_ts,
                    diagnostic_filter="DUPLICATE_CANDLE",
                    diagnostic_reason="accepted setup already processed for this candle",
                    scenario=(scenario_diag or {}).get("scenario") if scenario_diag else None,
                    scenario_directional_bias=(scenario_diag or {}).get("directional_bias") if scenario_diag else None,
                    scenario_current_zone=(scenario_diag or {}).get("current_zone") if scenario_diag else None,
                    scenario_recommendation=(scenario_diag or {}).get("recommendation") if scenario_diag else None,
                    scenario_alignment=(scenario_diag or {}).get("scenario_alignment") if scenario_diag else None,
                    candlestick_patterns=(pattern_diag or {}).get("patterns") if pattern_diag else None,
                    candlestick_bias=(pattern_diag or {}).get("pattern_bias") if pattern_diag else None,
                    candlestick_score=(pattern_diag or {}).get("pattern_score") if pattern_diag else None,
                    candlestick_integration=(pattern_diag or {}).get("scenario_integration") if pattern_diag else None,
                    candlestick_alignment=(pattern_diag or {}).get("pattern_alignment") if pattern_diag else None,
                    market_structure_bias=(structure_diag or {}).get("structure_bias") if structure_diag else None,
                    market_structure_location=(structure_diag or {}).get("price_location") if structure_diag else None,
                    market_structure_confirmation=(structure_diag or {}).get("confirmation_summary") if structure_diag else None,
                    market_structure_missing_confirmation=(structure_diag or {}).get("missing_confirmation") if structure_diag else None,
                )
                return result
            result["signal"] = 1
            paper_unlock_signal = bool(unlock_decision is not None and unlock_decision.accepted)
            unlock_profile = (unlock_decision.profile if unlock_decision is not None and unlock_decision.accepted else None)
            unlock_tag = (unlock_decision.tag if unlock_decision is not None and unlock_decision.accepted else None)
            signal_payload = {
                "cycle_id": cycle_id,
                "symbol": symbol,
                "side": verdict,
                "score": score,
                "confidence": conf,
                "candle_ts": candle_ts,
                "paper_unlock": paper_unlock_signal,
                "unlock_profile": unlock_profile,
                "scenario": (scenario_diag or {}).get("scenario") if scenario_diag else None,
                "scenario_directional_bias": (scenario_diag or {}).get("directional_bias") if scenario_diag else None,
                "scenario_alignment": (scenario_diag or {}).get("scenario_alignment") if scenario_diag else None,
                "candlestick_patterns": (pattern_diag or {}).get("patterns") if pattern_diag else None,
                "candlestick_bias": (pattern_diag or {}).get("pattern_bias") if pattern_diag else None,
                "candlestick_score": (pattern_diag or {}).get("pattern_score") if pattern_diag else None,
                "candlestick_integration": (pattern_diag or {}).get("scenario_integration") if pattern_diag else None,
                "candlestick_alignment": (pattern_diag or {}).get("pattern_alignment") if pattern_diag else None,
                "market_structure_bias": (structure_diag or {}).get("structure_bias") if structure_diag else None,
                "market_structure_location": (structure_diag or {}).get("price_location") if structure_diag else None,
                "market_structure_confirmation": (structure_diag or {}).get("confirmation_summary") if structure_diag else None,
                "market_structure_missing_confirmation": (structure_diag or {}).get("missing_confirmation") if structure_diag else None,
                "paper_order_guard_enabled": bool(self.order_leakage_guard_settings.enabled),
                "paper_order_guard_fail_closed": bool(self.order_leakage_guard_settings.fail_closed),
            }
            self.broker.emit("SIGNAL_DETECTED", **signal_payload)
            self.last_signal_by_symbol[symbol] = candle_key

            selected_archetype = extract_archetype(conf, signal_diag or {}, structure_diag or {}, scenario_diag or {})
            pruning_event = build_runtime_pruning_event(
                self.edge_strategy_pruning_settings,
                cycle_id=cycle_id,
                symbol=symbol,
                side=verdict,
                archetype=selected_archetype,
                source_path=("paper_unlock_signal" if paper_unlock_signal else "legacy_score_meta"),
                paper_unlock=paper_unlock_signal,
                score=score,
                confidence=conf,
            )
            if self.edge_strategy_pruning_settings.audit_enabled:
                self.broker.emit(**pruning_event)
            pruning_decision = evaluate_runtime_archetype_pruning(
                self.edge_strategy_pruning_settings,
                archetype=selected_archetype,
            )
            if pruning_decision.blocked:
                self.broker.emit(
                    "SIGNAL_REJECTED",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    side=verdict,
                    reason=pruning_decision.reason,
                    archetype=pruning_decision.archetype,
                    score=score,
                    edge_strategy_pruning_enabled=True,
                    blocked_archetypes=list(self.edge_strategy_pruning_settings.blocked_archetypes),
                    orders_submitted_by_pruning=0,
                    positions_opened_by_pruning=0,
                )
                self._print_once_progress(
                    f"[EDGE STRATEGY PRUNING BLOCKED] symbol={symbol} side={verdict} archetype={pruning_decision.archetype} reason={pruning_decision.reason}"
                )
                return result

            atr = float(last.get("atr", 0.0) or 0.0) or last_price * 0.01
            if verdict == "BUY":
                stop_loss = last_price - Config.ATR_MULT * atr
                take_profit = last_price + Config.ATR_MULT * atr * self.settings.rr
            else:
                stop_loss = last_price + Config.ATR_MULT * atr
                take_profit = last_price - Config.ATR_MULT * atr * self.settings.rr
            qty = self._position_qty(last_price=last_price, stop_loss=stop_loss)
            if qty <= 0:
                self.broker.emit("SIGNAL_REJECTED", cycle_id=cycle_id, symbol=symbol, side=verdict, reason="zero_qty", score=score)
                return result

            order_metadata = {
                "score": score,
                "confidence": conf,
                "combination": conf_comb,
                "timeframe": self.settings.timeframe,
                "cost_model": self.settings.cost_model,
                "candle_ts": str(df.index[-1]),
                "cycle_id": cycle_id,
                "paper_unlock": paper_unlock_signal,
                "unlock_profile": unlock_profile,
                "unlock_tag": unlock_tag,
                "regime": ((signal_diag or {}).get("regime") if paper_unlock_signal else (conf.get("regime") if isinstance(conf, dict) else None)),
                "crypto_scenario": ((scenario_diag or {}).get("scenario") if scenario_diag else None),
                "scenario_directional_bias": ((scenario_diag or {}).get("directional_bias") if scenario_diag else None),
                "scenario_alignment": ((scenario_diag or {}).get("scenario_alignment") if scenario_diag else None),
                "market_structure_bias": ((structure_diag or {}).get("structure_bias") if structure_diag else None),
                "market_structure_location": ((structure_diag or {}).get("price_location") if structure_diag else None),
                "market_structure_confirmation": ((structure_diag or {}).get("confirmation_summary") if structure_diag else None),
            }
            if should_block_paper_order_attempt(settings=self.order_leakage_guard_settings, metadata=order_metadata):
                source_path = "paper_unlock_legacy_execution" if paper_unlock_signal else "legacy_score_meta"
                risk_amount = abs(last_price - stop_loss) * qty
                block_event = build_legacy_paper_order_blocked_event(
                    settings=self.order_leakage_guard_settings,
                    cycle_id=cycle_id,
                    symbol=symbol,
                    side=verdict,
                    score=score,
                    confidence=conf,
                    combination=str(conf_comb or ""),
                    candle_ts=candle_ts,
                    entry_price=last_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    qty=qty,
                    notional=abs(qty * last_price),
                    risk_amount=risk_amount,
                    paper_unlock=paper_unlock_signal,
                    unlock_profile=unlock_profile,
                    source_path=source_path,
                )
                self.broker.emit(**block_event)
                self._print_once_progress(
                    f"[PAPER ORDER BLOCKED] symbol={symbol} side={verdict} reason=paper_order_source_not_authorized source={source_path}"
                )
                return result

            if paper_unlock_signal:
                self.broker.emit(
                    "PAPER_UNLOCK_SIGNAL",
                    cycle_id=cycle_id,
                    symbol=symbol,
                    side=verdict,
                    score=score,
                    confidence=conf,
                    candle_ts=candle_ts,
                    unlock_decision=unlock_decision.to_dict(),
                    live_execution_enabled=False,
                )
                await self._notify_unlock_signal(symbol=symbol, side=verdict, decision=unlock_decision, cycle_id=cycle_id)
            else:
                await self._notify_signal_detected(symbol=symbol, side=verdict, score=score, conf=conf, cycle_id=cycle_id)

            order = self.broker_adapter.place_order(
                symbol=symbol,
                side=verdict,  # type: ignore[arg-type]
                qty=qty,
                price=last_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata=order_metadata,
            )
            result["order"] = 1
            self.broker.emit("PAPER_ORDER_CONFIRMED", cycle_id=cycle_id, symbol=symbol, side=verdict, order_id=order.order_id, qty=qty, price=last_price)
            await self._notify_order_filled(
                symbol=symbol,
                side=verdict,
                order_id=order.order_id,
                qty=qty,
                price=last_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                cycle_id=cycle_id,
            )
            await self._notify_position_opened(symbol=symbol, side=verdict, cycle_id=cycle_id)
            return result
        except asyncio.CancelledError:
            self.broker.emit("ASYNC_TASK_CANCELLED", cycle_id=cycle_id, symbol=symbol, component="evaluate_symbol")
            self.broker.emit("EXCHANGE_CLIENT_CLOSED", cycle_id=cycle_id, symbol=symbol, status="cancelled")
            raise
        except Exception as exc:
            result["error"] = 1
            elapsed_start = fetch_started_at if progress_phase == "fetch" else evaluate_started_at
            elapsed = max(0.0, time.monotonic() - elapsed_start) if elapsed_start else 0.0
            if progress_phase == "fetch":
                self._print_once_progress(
                    f"[FETCH ERROR] symbol={symbol} error_type={exc.__class__.__name__} elapsed_seconds={elapsed:.4f}"
                )
            else:
                self._print_once_progress(
                    f"[EVALUATE ERROR] symbol={symbol} error_type={exc.__class__.__name__} elapsed_seconds={elapsed:.4f}"
                )
            self.broker.emit("SYMBOL_ERROR", cycle_id=cycle_id, symbol=symbol, error=str(exc), error_type=exc.__class__.__name__)
            self.broker.emit("EXCHANGE_CLIENT_CLOSED", cycle_id=cycle_id, symbol=symbol, status="error")
            print(f"[PaperEngine] Symbol error | {symbol} | {exc} | skipped", flush=True)
            return result

    async def _fetch_live_market_data(self, *, symbol: str, limit: int) -> Any:
        client = ExchangeClient(
            exchange_id=Config.EXCHANGE_ID,
            symbol=symbol,
            timeframe=self.settings.timeframe,
            limit=limit,
            api_key=None,
            api_secret=None,
        )
        return await client.fetch_async()

    def _load_cached_market_data(self, *, symbol: str, limit: int, replay: bool, cycle_id: str = "") -> Any:
        cache_dir = self.settings.market_data_cache_dir or self.settings.data_dir
        if replay:
            loaded = load_replay_ohlcv(
                data_dir=cache_dir,
                symbol=symbol,
                timeframe=self.settings.timeframe,
                limit=limit,
                replay_offsets=self._market_data_replay_offsets,
                step=self.settings.market_data_replay_step,
                start_offset=(self.settings.market_data_replay_start_offset or None),
            )
        else:
            loaded = load_cached_ohlcv(
                data_dir=cache_dir,
                symbol=symbol,
                timeframe=self.settings.timeframe,
                limit=limit,
            )
        self.broker.emit(
            "MARKET_DATA_CACHE_USED",
            cycle_id=cycle_id,
            symbol=symbol,
            timeframe=self.settings.timeframe,
            mode=self.settings.market_data_mode,
            cache_path=str(loaded.path),
            rows_available=loaded.rows_available,
            rows_returned=loaded.rows_returned,
            replay_end_offset=loaded.replay_end_offset,
        )
        return loaded.df

    async def _fetch_market_data(self, *, symbol: str, limit: int, cycle_id: str = "") -> Any:
        mode = str(self.settings.market_data_mode or "live").strip().lower()
        if mode not in {"live", "auto", "cache", "replay"}:
            mode = "live"
        if mode == "cache":
            return self._load_cached_market_data(symbol=symbol, limit=limit, replay=False, cycle_id=cycle_id)
        if mode == "replay":
            return self._load_cached_market_data(symbol=symbol, limit=limit, replay=True, cycle_id=cycle_id)
        try:
            df = await self._fetch_live_market_data(symbol=symbol, limit=limit)
            self.broker.emit(
                "MARKET_DATA_LIVE_USED",
                cycle_id=cycle_id,
                symbol=symbol,
                exchange_id=Config.EXCHANGE_ID,
                timeframe=self.settings.timeframe,
                rows_returned=0 if df is None else int(getattr(df, "shape", [0])[0] or 0),
            )
            return df
        except Exception as exc:
            if mode != "auto":
                raise
            self.broker.emit(
                "MARKET_DATA_LIVE_FAILED_FALLBACK",
                cycle_id=cycle_id,
                symbol=symbol,
                exchange_id=Config.EXCHANGE_ID,
                timeframe=self.settings.timeframe,
                error=str(exc),
                error_type=exc.__class__.__name__,
                fallback="local_replay_cache",
            )
            try:
                return self._load_cached_market_data(symbol=symbol, limit=limit, replay=True, cycle_id=cycle_id)
            except CachedMarketDataNotFound:
                raise

    def _position_qty(self, *, last_price: float, stop_loss: float) -> float:
        risk_capital = max(0.0, self.broker.balance * self.settings.risk_per_trade_pct)
        per_unit_risk = abs(last_price - stop_loss)
        if per_unit_risk <= 0 or last_price <= 0:
            return 0.0
        qty = risk_capital / per_unit_risk
        # Conservative notional cap for paper drills: no more than 1x current equity per position.
        max_qty = self.broker.balance / last_price
        return max(0.0, min(qty, max_qty))

    def write_status_file(self) -> None:
        path = self.data_dir / "paper_status.json"
        payload = self.broker.snapshot(self.last_prices)
        execution_snapshot = self.broker_adapter.reconcile()
        monitor_payload = self.position_monitor.write(account=execution_snapshot.account, positions=execution_snapshot.positions)
        payload.update({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "symbols": self.settings.symbols,
            "timeframe": self.settings.timeframe,
            "cost_model": self.settings.cost_model,
            "market_data_mode": self.settings.market_data_mode,
            "market_data_cache_dir": self.settings.market_data_cache_dir,
            "market_data_replay_start_offset": self.settings.market_data_replay_start_offset,
            "market_data_replay_offsets": dict(self._market_data_replay_offsets),
            "cycle_artifacts_enabled": bool(self.settings.cycle_artifacts_enabled),
            "active_cycle_id": self._active_cycle_id,
            "cycle_seq": self._cycle_seq,
            "shutdown_requested": self._shutdown_requested,
            "dashboard_path": str(self.data_dir / "paper_dashboard.html"),
            "performance_report_path": str(self.data_dir / "paper_performance_report.json"),
            "drift_report_path": str(self.data_dir / "paper_drift_report.json"),
            "crypto_scenario_report_path": str(self.data_dir / "crypto_intraday_scenario_report.json"),
            "candlestick_pattern_report_path": str(self.data_dir / "candlestick_pattern_report.json"),
            "pattern_conditioned_shadow_report_path": str(self.data_dir / "pattern_conditioned_shadow_report.json"),
            "scenario_pattern_calibration_report_path": str(self.data_dir / "scenario_pattern_calibration_report.json"),
            "market_structure_map_report_path": str(self.data_dir / "market_structure_map_report.json"),
            "calibrated_structure_shadow_report_path": str(self.data_dir / "calibrated_structure_shadow_report.json"),
            "structure_filter_diagnostics_report_path": str(self.data_dir / "structure_filter_diagnostics_report.json"),
            "structure_context_repair_report_path": str(self.data_dir / "structure_context_repair_report.json"),
            "repaired_structure_shadow_validation_report_path": str(self.data_dir / "repaired_structure_shadow_validation_report.json"),
            "independent_repaired_validation_report_path": str(self.data_dir / "independent_repaired_validation_report.json"),
            "paper_unlock_profile_refinement_report_path": str(self.data_dir / "paper_unlock_profile_refinement_report.json"),
            "paper_unlock_experiment_design_report_path": str(self.data_dir / "paper_unlock_experiment_design_report.json"),
            "paper_unlock_shadow_dry_run_report_path": str(self.data_dir / "paper_unlock_shadow_dry_run_report.json"),
            "paper_unlock_shadow_rate_calibration_report_path": str(self.data_dir / "paper_unlock_shadow_rate_calibration_report.json"),
            "paper_unlock_bounded_cadence_report_path": str(self.data_dir / "paper_unlock_bounded_cadence_report.json"),
            "paper_unlock_shadow_stability_review_report_path": str(self.data_dir / "paper_unlock_shadow_stability_review_report.json"),
            "paper_unlock_activation_draft_report_path": str(self.data_dir / "paper_unlock_activation_draft_report.json"),
            "paper_unlock_experiment_switch_draft_report_path": str(self.data_dir / "paper_unlock_experiment_switch_draft_report.json"),
            "paper_unlock_candidate_audit_report_path": str(self.data_dir / "paper_unlock_candidate_audit_report.json"),
            "paper_unlock_handoff_dry_run_report_path": str(self.data_dir / "paper_unlock_handoff_dry_run_report.json"),
            "telegram_audit_path": str(self.data_dir / "telegram_audit.jsonl"),
            "telegram_enabled": bool(self.telegram.enabled),
            "telegram_read_only": bool(self.telegram.read_only),
            "telegram_allowed_user_count": len(self.telegram.allowed_user_ids),
            "operational_console": {
                "verbose": bool(self.settings.console_verbose),
                "ai_debug": bool(self.settings.ai_debug),
                "header_every_n_cycles": int(self.settings.console_header_every_n_cycles or 0),
            },
            "telegram_proactive_enabled": bool(self.settings.telegram_proactive_enabled),
            "telegram_notify_on_start": bool(self.settings.telegram_notify_on_start),
            "telegram_notify_on_shutdown": bool(self.settings.telegram_notify_on_shutdown),
            "telegram_last_notification_at": self.proactive.state.last_notification_at,
            "telegram_last_notification_type": self.proactive.state.last_notification_type,
            "telegram_proactive_state_path": str(self.proactive.state_path),
            "signal_diagnostics_enabled": bool(self.settings.signal_diagnostics_enabled),
            "signal_diagnostics_backfill_enabled": bool(self.settings.signal_diagnostics_backfill_enabled),
            "paper_signal_diagnostics_report_path": str(self.data_dir / "paper_signal_diagnostics_report.json"),
            "paper_signal_diagnostics_backfill_report_path": str(self.data_dir / "paper_signal_diagnostics_backfill_report.json"),
            "paper_entry_unlock_enabled": bool(self.settings.paper_entry_unlock_enabled),
            "unlock_rejection_analysis_enabled": bool(self.settings.unlock_rejection_analysis_enabled),
            "paper_unlock_rejection_report_path": str(self.data_dir / "paper_unlock_rejection_report.json"),
            "paper_unlock_rejection_analysis": self._read_unlock_rejection_summary(),
            "crypto_scenario_enabled": bool(self.settings.crypto_scenario_enabled),
            "crypto_intraday_scenario_report_path": str(self.data_dir / "crypto_intraday_scenario_report.json"),
            "crypto_intraday_scenario": self._read_crypto_scenario_summary(),
            "candlestick_patterns_enabled": bool(self.settings.candlestick_patterns_enabled),
            "candlestick_pattern_report_path": str(self.data_dir / "candlestick_pattern_report.json"),
            "candlestick_pattern_engine": self._read_candlestick_pattern_summary(),
            "pattern_conditioned_shadow_enabled": bool(self.settings.pattern_conditioned_shadow_enabled),
            "pattern_conditioned_shadow_report_path": str(self.data_dir / "pattern_conditioned_shadow_report.json"),
            "pattern_conditioned_shadow": self._read_pattern_conditioned_shadow_summary(),
            "scenario_pattern_calibration_enabled": bool(self.settings.scenario_pattern_calibration_enabled),
            "scenario_pattern_calibration_report_path": str(self.data_dir / "scenario_pattern_calibration_report.json"),
            "scenario_pattern_calibration": self._read_scenario_pattern_calibration_summary(),
            "market_structure_map_enabled": bool(self.settings.market_structure_map_enabled),
            "market_structure_map_report_path": str(self.data_dir / "market_structure_map_report.json"),
            "market_structure_map": self._read_market_structure_map_summary(),
            "calibrated_structure_shadow_enabled": bool(self.settings.calibrated_structure_shadow_enabled),
            "calibrated_structure_shadow_report_path": str(self.data_dir / "calibrated_structure_shadow_report.json"),
            "calibrated_structure_shadow": self._read_calibrated_structure_shadow_summary(),
            "structure_filter_diagnostics_enabled": bool(self.settings.structure_filter_diagnostics_enabled),
            "structure_filter_diagnostics_report_path": str(self.data_dir / "structure_filter_diagnostics_report.json"),
            "structure_filter_diagnostics": self._read_structure_filter_diagnostics_summary(),
            "structure_context_repair_enabled": bool(self.settings.structure_context_repair_enabled),
            "structure_context_repair_report_path": str(self.data_dir / "structure_context_repair_report.json"),
            "structure_context_repair": self._read_structure_context_repair_summary(),
            "repaired_structure_shadow_validation_enabled": bool(self.settings.repaired_structure_shadow_validation_enabled),
            "repaired_structure_shadow_validation_report_path": str(self.data_dir / "repaired_structure_shadow_validation_report.json"),
            "repaired_structure_shadow_validation": self._read_repaired_structure_shadow_validation_summary(),
            "independent_repaired_validation_enabled": bool(self.settings.independent_repaired_validation_enabled),
            "independent_repaired_validation_report_path": str(self.data_dir / "independent_repaired_validation_report.json"),
            "independent_repaired_validation": self._read_independent_repaired_validation_summary(),
            "paper_unlock_profile_refinement_enabled": bool(self.settings.paper_unlock_profile_refinement_enabled),
            "paper_unlock_profile_refinement_report_path": str(self.data_dir / "paper_unlock_profile_refinement_report.json"),
            "paper_unlock_profile_refinement": self._read_paper_unlock_profile_refinement_summary(),
            "paper_unlock_experiment_design_enabled": bool(self.settings.paper_unlock_experiment_design_enabled),
            "paper_unlock_experiment_design_report_path": str(self.data_dir / "paper_unlock_experiment_design_report.json"),
            "paper_unlock_experiment_design": self._read_paper_unlock_experiment_design_summary(),
            "paper_unlock_shadow_dry_run_enabled": bool(self.settings.paper_unlock_shadow_dry_run_enabled),
            "paper_unlock_shadow_dry_run_report_path": str(self.data_dir / "paper_unlock_shadow_dry_run_report.json"),
            "paper_unlock_shadow_dry_run": self._read_paper_unlock_shadow_dry_run_summary(),
            "paper_unlock_shadow_rate_calibration_enabled": bool(self.settings.paper_unlock_shadow_rate_calibration_enabled),
            "paper_unlock_shadow_rate_calibration_report_path": str(self.data_dir / "paper_unlock_shadow_rate_calibration_report.json"),
            "paper_unlock_shadow_rate_calibration": self._read_paper_unlock_shadow_rate_calibration_summary(),
            "paper_unlock_bounded_cadence_enabled": bool(self.settings.paper_unlock_bounded_cadence_enabled),
            "paper_unlock_bounded_cadence_report_path": str(self.data_dir / "paper_unlock_bounded_cadence_report.json"),
            "paper_unlock_shadow_stability_review_report_path": str(self.data_dir / "paper_unlock_shadow_stability_review_report.json"),
            "paper_unlock_activation_draft_report_path": str(self.data_dir / "paper_unlock_activation_draft_report.json"),
            "paper_unlock_experiment_switch_draft_report_path": str(self.data_dir / "paper_unlock_experiment_switch_draft_report.json"),
            "paper_unlock_bounded_cadence": self._read_paper_unlock_bounded_cadence_summary(),
            "paper_unlock_shadow_stability_review_enabled": bool(self.settings.paper_unlock_shadow_stability_review_enabled),
            "paper_unlock_shadow_stability_review_report_path": str(self.data_dir / "paper_unlock_shadow_stability_review_report.json"),
            "paper_unlock_activation_draft_report_path": str(self.data_dir / "paper_unlock_activation_draft_report.json"),
            "paper_unlock_experiment_switch_draft_report_path": str(self.data_dir / "paper_unlock_experiment_switch_draft_report.json"),
            "paper_unlock_shadow_stability_review": self._read_paper_unlock_shadow_stability_review_summary(),
            "paper_unlock_activation_draft_enabled": bool(self.settings.paper_unlock_activation_draft_enabled),
            "paper_unlock_activation_draft_report_path": str(self.data_dir / "paper_unlock_activation_draft_report.json"),
            "paper_unlock_experiment_switch_draft_report_path": str(self.data_dir / "paper_unlock_experiment_switch_draft_report.json"),
            "paper_unlock_activation_draft": self._read_paper_unlock_activation_draft_summary(),
            "paper_unlock_guarded_enable_enabled": bool(self.settings.paper_unlock_guarded_enable_enabled),
            "paper_unlock_guarded_enable_report_path": str(self.data_dir / "paper_unlock_guarded_enable_report.json"),
            "paper_unlock_guarded_enable": self._read_paper_unlock_guarded_enable_summary(),
            "paper_unlock_runtime_audit_enabled": bool(self.settings.paper_unlock_runtime_audit_enabled),
            "paper_unlock_runtime_audit_report_path": str(self.data_dir / "paper_unlock_runtime_audit_report.json"),
            "paper_unlock_runtime_audit": self._read_paper_unlock_runtime_audit_summary(),
            "paper_unlock_routing_bridge_enabled": bool(self.settings.paper_unlock_routing_bridge_enabled),
            "paper_unlock_routing_bridge_report_path": str(self.data_dir / "paper_unlock_routing_bridge_report.json"),
            "paper_unlock_candidate_audit_enabled": bool(self.settings.paper_unlock_candidate_audit_enabled),
            "paper_unlock_candidate_audit_report_path": str(self.data_dir / "paper_unlock_candidate_audit_report.json"),
            "paper_unlock_handoff_dry_run_enabled": bool(self.settings.paper_unlock_handoff_dry_run_enabled),
            "paper_unlock_handoff_dry_run_report_path": str(self.data_dir / "paper_unlock_handoff_dry_run_report.json"),
            "paper_unlock_supervised_execution_enabled": bool(self.settings.paper_unlock_supervised_execution_enabled),
            "paper_unlock_supervised_execution_report_path": str(self.data_dir / "paper_unlock_supervised_execution_report.json"),
            "paper_unlock_supervised_execution_operator_enable": bool(self.settings.paper_unlock_supervised_execution_operator_enable),
            "paper_unlock_supervised_execution_operator_confirmation_ok": bool(self.supervised_execution_settings.confirmation_ok),
            "lsr_v2_paper_supervised_bridge_enabled": bool(self.settings.lsr_v2_paper_supervised_bridge_enabled),
            "lsr_v2_paper_supervised_bridge_report_path": str(self.data_dir / "lsr_v2_paper_supervised_bridge_report.json"),
            "lsr_v2_paper_supervised_bridge_operator_enable": bool(self.settings.lsr_v2_paper_supervised_bridge_operator_enable),
            "lsr_v2_paper_supervised_bridge_operator_confirmation_ok": bool(self.lsr_v2_bridge_settings.operator_confirmation_ok),
            "paper_unlock": {
                "enabled": bool(self.unlock_settings.enabled),
                "profile": self.unlock_settings.profile,
                "allowed_symbols": list(self.unlock_settings.allowed_symbols),
                "allowed_filters": list(self.unlock_settings.allowed_filters),
                "min_ai_prob": self.unlock_settings.min_ai_prob,
                "min_setup_quality": self.unlock_settings.min_setup_quality,
                "require_tech_gate": self.unlock_settings.require_tech_gate,
                "max_positions": self.unlock_settings.max_positions,
                "live_block": self.unlock_settings.live_block,
                "tag": self.unlock_settings.tag,
            },
            "exploratory_signal_analysis": bool(self.settings.exploratory_signal_analysis),
            "shadow_simulation_enabled": bool(self.settings.shadow_simulation_enabled),
            "paper_shadow_unlock_report_path": str(self.data_dir / "paper_shadow_unlock_report.json"),
            "telegram_proactive": self.proactive.snapshot(),
            "broker_adapter": {
                "active": "PaperBrokerAdapter",
                "exchange_stub": "ExchangeBrokerAdapter",
                "live_execution_enabled": False,
                "reconciliation_status": execution_snapshot.reconciliation_status,
                "warnings": execution_snapshot.warnings,
                "errors": execution_snapshot.errors,
            },
            "paper_position_monitor_path": str(self.data_dir / "paper_position_monitor.json"),
            "position_monitor": monitor_payload,
        })
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _read_unlock_rejection_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_rejection_report.json"
        if not path.exists():
            return {}
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                return {}
            decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
            counts = report.get("counts", {}) if isinstance(report.get("counts"), dict) else {}
            return {
                "status": report.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "dominant_btc_reason": decision.get("dominant_btc_reason", ""),
                "next_patch": decision.get("next_patch", ""),
                "btc_evaluated": counts.get("btc_evaluated", 0),
                "accepted": counts.get("paper_unlock_accepted_evaluations", 0),
                "near_threshold_btc": counts.get("btc_near_threshold_candidates", 0),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def _read_crypto_scenario_summary(self) -> dict[str, Any]:
        path = self.data_dir / "crypto_intraday_scenario_report.json"
        if not path.exists():
            return {}
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                return {}
            decision = report.get("decision", {}) if isinstance(report.get("decision"), dict) else {}
            counts = report.get("counts", {}) if isinstance(report.get("counts"), dict) else {}
            btc = report.get("btc_focus", {}) if isinstance(report.get("btc_focus"), dict) else {}
            return {
                "status": report.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "scenario_events": counts.get("scenario_events", 0),
                "btc_scenario_events": counts.get("btc_scenario_events", 0),
                "btc_scenarios": btc.get("scenarios", {}),
                "btc_directional_bias": btc.get("directional_bias", {}),
                "btc_alignment": btc.get("scenario_alignment", {}),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_lifecycle_report(self) -> dict[str, Any]:
        return write_lifecycle_report(self.data_dir)

    def write_signal_diagnostics_report(self) -> dict[str, Any]:
        if not self.settings.signal_diagnostics_enabled:
            return {}
        return write_signal_diagnostics_report(self.data_dir)

    def write_signal_diagnostics_backfill_report(self) -> dict[str, Any]:
        if not self.settings.signal_diagnostics_backfill_enabled:
            return {}
        return write_signal_diagnostics_backfill_report(self.data_dir)

    def write_shadow_unlock_report(self) -> dict[str, Any]:
        if not self.settings.shadow_simulation_enabled:
            return {}
        return write_shadow_unlock_report(self.data_dir)

    def _read_candlestick_pattern_summary(self) -> dict[str, Any]:
        path = self.data_dir / "candlestick_pattern_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            btc = payload.get("btc_focus", {}) if isinstance(payload.get("btc_focus"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision": decision.get("status", "NA"),
                "pattern_events": counts.get("pattern_events", 0),
                "btc_pattern_events": counts.get("btc_pattern_events", 0),
                "btc_patterns": btc.get("patterns", {}),
                "btc_pattern_bias": btc.get("pattern_bias", {}),
                "btc_pattern_alignment": btc.get("pattern_alignment", {}),
                "next_patch": decision.get("next_patch", ""),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def _read_pattern_conditioned_shadow_summary(self) -> dict[str, Any]:
        path = self.data_dir / "pattern_conditioned_shadow_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            historical = payload.get("historical_shadow", {}) if isinstance(payload.get("historical_shadow"), dict) else {}
            summary = historical.get("summary", {}) if isinstance(historical.get("summary"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "runtime_aligned_candidates": counts.get("runtime_aligned_candidates", 0),
                "historical_candidates": counts.get("historical_candidates", 0),
                "historical_expectancy_r": summary.get("expectancy_r", 0.0),
                "historical_win_rate_pct": summary.get("win_rate_pct", 0.0),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_pattern_conditioned_shadow_report(self) -> dict[str, Any]:
        if not self.settings.pattern_conditioned_shadow_enabled:
            return {}
        return write_pattern_conditioned_shadow_report(self.data_dir)

    def _read_market_structure_map_summary(self) -> dict[str, Any]:
        path = self.data_dir / "market_structure_map_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            focus = decision.get("focus_latest", {}) if isinstance(decision.get("focus_latest"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "runtime_structure_rows": counts.get("runtime_structure_rows", 0),
                "historical_snapshots_evaluated": counts.get("historical_snapshots_evaluated", 0),
                "focus_symbol": decision.get("focus_symbol", ""),
                "focus_price_location": focus.get("price_location", ""),
                "focus_structure_bias": focus.get("structure_bias", ""),
                "focus_confirmation": focus.get("confirmation_summary", ""),
                "focus_map_score": focus.get("map_score", 0.0),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_market_structure_map_report(self) -> dict[str, Any]:
        if not self.settings.market_structure_map_enabled:
            return {}
        return write_market_structure_map_report(self.data_dir)

    def _read_scenario_pattern_calibration_summary(self) -> dict[str, Any]:
        path = self.data_dir / "scenario_pattern_calibration_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            profile = decision.get("candidate_profile", {}) if isinstance(decision.get("candidate_profile"), dict) else {}
            focus = decision.get("focus_bucket_baseline", {}) if isinstance(decision.get("focus_bucket_baseline"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "historical_candidates": counts.get("historical_candidates", 0),
                "runtime_aligned_rows": counts.get("runtime_aligned_rows", 0),
                "candidate_profile": profile.get("name", ""),
                "profile_status": profile.get("status", ""),
                "profile_pattern_score_min": profile.get("pattern_score_min", 0),
                "focus_expectancy_r": focus.get("expectancy_r", 0.0),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_scenario_pattern_calibration_report(self) -> dict[str, Any]:
        if not self.settings.scenario_pattern_calibration_enabled:
            return {}
        return write_scenario_pattern_calibration_report(self.data_dir)

    def _read_calibrated_structure_shadow_summary(self) -> dict[str, Any]:
        path = self.data_dir / "calibrated_structure_shadow_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            best = decision.get("best_variant") or decision.get("best_watchlist_variant") or {}
            if not isinstance(best, dict):
                best = {}
            profile = decision.get("candidate_profile", {}) if isinstance(decision.get("candidate_profile"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "candidate_profile": profile.get("name", ""),
                "profile_status": profile.get("status", ""),
                "structured_candidate_rows": counts.get("structured_candidate_rows", 0),
                "candidate_rows_pre_structure": counts.get("candidate_rows_pre_structure", 0),
                "best_variant": best.get("name", ""),
                "best_expectancy_r": best.get("expectancy_r", 0.0),
                "best_candidates": best.get("candidates", 0),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_calibrated_structure_shadow_report(self) -> dict[str, Any]:
        if not self.settings.calibrated_structure_shadow_enabled:
            return {}
        return write_calibrated_structure_shadow_report(self.data_dir)

    def _read_structure_filter_diagnostics_summary(self) -> dict[str, Any]:
        path = self.data_dir / "structure_filter_diagnostics_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            best = decision.get("best_audit_variant") if isinstance(decision.get("best_audit_variant"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "structured_candidate_rows": counts.get("structured_candidate_rows", 0),
                "audit_variants": counts.get("audit_variants", 0),
                "best_audit_variant": best.get("name", ""),
                "best_expectancy_r": best.get("expectancy_r", 0.0),
                "best_candidates": best.get("candidates", 0),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_structure_filter_diagnostics_report(self) -> dict[str, Any]:
        if not self.settings.structure_filter_diagnostics_enabled:
            return {}
        return write_structure_filter_diagnostics_report(self.data_dir)

    def _read_structure_context_repair_summary(self) -> dict[str, Any]:
        path = self.data_dir / "structure_context_repair_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            transitions = payload.get("transition_matrix", {}) if isinstance(payload.get("transition_matrix"), dict) else {}
            best = decision.get("best_repaired_variant", {}) if isinstance(decision.get("best_repaired_variant"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "structured_candidate_rows": counts.get("structured_candidate_rows", 0),
                "repair_variants": counts.get("repair_variants", 0),
                "best_repaired_variant": best.get("name", ""),
                "repaired_context_count": transitions.get("repaired_context_count", 0),
                "repaired_confirmation_count": transitions.get("repaired_confirmation_count", 0),
                "wait_state_count": transitions.get("wait_state_count", 0),
                "conflict_count": transitions.get("conflict_count", 0),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_structure_context_repair_report(self) -> dict[str, Any]:
        if not self.settings.structure_context_repair_enabled:
            return {}
        return write_structure_context_repair_report(self.data_dir)

    def _read_repaired_structure_shadow_validation_summary(self) -> dict[str, Any]:
        path = self.data_dir / "repaired_structure_shadow_validation_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            matrix = payload.get("hypothesis_matrix", {}) if isinstance(payload.get("hypothesis_matrix"), dict) else {}
            best = decision.get("best_validation_variant", {}) if isinstance(decision.get("best_validation_variant"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "structured_candidate_rows": counts.get("structured_candidate_rows", 0),
                "validation_variants": counts.get("validation_variants", 0),
                "best_validation_variant": best.get("name", ""),
                "map_score_65_79_count": matrix.get("map_score_65_79_count", 0),
                "map_score_65_79_entry_state_count": matrix.get("map_score_65_79_entry_state_count", 0),
                "directional_bos_count": matrix.get("directional_bos_count", 0),
                "confirmation_count": matrix.get("confirmation_count", 0),
                "wait_watchlist_count": matrix.get("wait_watchlist_count", 0),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_repaired_structure_shadow_validation_report(self) -> dict[str, Any]:
        if not self.settings.repaired_structure_shadow_validation_enabled:
            return {}
        return write_repaired_structure_shadow_validation_report(self.data_dir)

    def _read_independent_repaired_validation_summary(self) -> dict[str, Any]:
        path = self.data_dir / "independent_repaired_validation_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            matrix = payload.get("independent_matrix", {}) if isinstance(payload.get("independent_matrix"), dict) else {}
            wf = payload.get("walk_forward", {}) if isinstance(payload.get("walk_forward"), dict) else {}
            wf_checks = wf.get("stability_checks", {}) if isinstance(wf.get("stability_checks"), dict) else {}
            best = decision.get("best_stability_variant", {}) if isinstance(decision.get("best_stability_variant"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "next_patch": decision.get("next_patch", ""),
                "structured_candidate_rows": counts.get("structured_candidate_rows", 0),
                "target_candidate_rows": counts.get("target_candidate_rows", 0),
                "best_stability_variant": best.get("name", ""),
                "target_entry_state_rows": matrix.get("target_entry_state_rows", 0),
                "target_bos_rows": matrix.get("target_bos_rows", 0),
                "positive_fold_rate_pct": wf_checks.get("positive_fold_rate_pct", 0),
                "passes_walk_forward_guard": bool(wf_checks.get("passes_walk_forward_guard", False)),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_refinement_allowed": bool(decision.get("paper_unlock_refinement_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_independent_repaired_validation_report(self) -> dict[str, Any]:
        if not self.settings.independent_repaired_validation_enabled:
            return {}
        return write_independent_repaired_validation_report(self.data_dir)

    def _read_paper_unlock_profile_refinement_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_profile_refinement_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            best = decision.get("best_profile_design_variant", {}) if isinstance(decision.get("best_profile_design_variant"), dict) else {}
            source = payload.get("source_validation", {}) if isinstance(payload.get("source_validation"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "profile_name": decision.get("profile_name", ""),
                "next_patch": decision.get("next_patch", ""),
                "target_candidate_rows": counts.get("target_candidate_rows", 0),
                "best_profile_design_variant": best.get("name", ""),
                "independent_guard_ok": bool(source.get("independent_guard_ok", False)),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_refinement_allowed": bool(decision.get("paper_unlock_refinement_allowed", False)),
                "paper_unlock_experiment_allowed": bool(decision.get("paper_unlock_experiment_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_profile_refinement_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_profile_refinement_enabled:
            return {}
        return write_paper_unlock_profile_refinement_report(self.data_dir)

    def _read_paper_unlock_experiment_design_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_experiment_design_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            best = decision.get("best_experiment_design_variant", {}) if isinstance(decision.get("best_experiment_design_variant"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "profile_name": decision.get("profile_name", ""),
                "experiment_name": decision.get("experiment_name", ""),
                "next_patch": decision.get("next_patch", ""),
                "target_candidate_rows": counts.get("target_candidate_rows", 0),
                "best_experiment_design_variant": best.get("name", ""),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_experiment_allowed": bool(decision.get("paper_unlock_experiment_allowed", False)),
                "paper_orders_enabled": bool(decision.get("paper_orders_enabled", False) or payload.get("paper_orders_enabled", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_experiment_design_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_experiment_design_enabled:
            return {}
        return write_paper_unlock_experiment_design_report(self.data_dir)

    def _read_paper_unlock_shadow_dry_run_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_shadow_dry_run_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            gate = payload.get("shadow_dry_run_gate", {}) if isinstance(payload.get("shadow_dry_run_gate"), dict) else {}
            equity = payload.get("equity_dry_run", {}) if isinstance(payload.get("equity_dry_run"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "profile_name": decision.get("profile_name", ""),
                "experiment_name": decision.get("experiment_name", ""),
                "harness_name": decision.get("harness_name", ""),
                "next_patch": decision.get("next_patch", ""),
                "source_target_rows": counts.get("source_target_rows", 0),
                "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
                "shadow_selected_entries": counts.get("shadow_selected_entries", 0),
                "passes_shadow_dry_run_gate": bool(gate.get("passes_shadow_dry_run_gate", False)),
                "max_consecutive_losses": equity.get("max_consecutive_losses", 0),
                "max_drawdown_pct": equity.get("max_drawdown_pct", 0),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_experiment_allowed": bool(decision.get("paper_unlock_experiment_allowed", False)),
                "paper_orders_enabled": bool(decision.get("paper_orders_enabled", False) or payload.get("paper_orders_enabled", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_shadow_dry_run_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_shadow_dry_run_enabled:
            return {}
        return write_paper_unlock_shadow_dry_run_report(self.data_dir)

    def _read_paper_unlock_shadow_rate_calibration_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_shadow_rate_calibration_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            best = decision.get("best_rate_variant", {}) if isinstance(decision.get("best_rate_variant"), dict) else {}
            return {
                "status": payload.get("status", "NA"),
                "decision_status": decision.get("status", "NA"),
                "calibration_name": payload.get("calibration_name", ""),
                "best_rate_variant": best.get("name", ""),
                "best_selected_entries": best.get("selected_entries", counts.get("best_selected_entries", 0)),
                "source_target_rows": counts.get("source_target_rows", 0),
                "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
                "next_patch": decision.get("next_patch", ""),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_experiment_allowed": bool(decision.get("paper_unlock_experiment_allowed", False)),
                "paper_orders_enabled": bool(decision.get("paper_orders_enabled", False) or payload.get("paper_orders_enabled", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_shadow_rate_calibration_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_shadow_rate_calibration_enabled:
            return {}
        return write_paper_unlock_shadow_rate_calibration_report(self.data_dir)

    def _read_paper_unlock_bounded_cadence_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_bounded_cadence_report.json"
        if not path.exists():
            return {"status": "MISSING", "path": str(path)}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            best = decision.get("best_bounded_cadence_variant", {}) if isinstance(decision.get("best_bounded_cadence_variant"), dict) else {}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            return {
                "status": payload.get("status", "UNKNOWN"),
                "decision": decision.get("status", "UNKNOWN"),
                "collection_name": payload.get("collection_name", ""),
                "best_bounded_cadence_variant": best.get("name", ""),
                "best_selected_entries": best.get("selected_entries", counts.get("best_selected_entries", 0)),
                "entry_candidate_rows": counts.get("entry_candidate_rows", 0),
                "next_patch": decision.get("next_patch", ""),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_experiment_allowed": bool(decision.get("paper_unlock_experiment_allowed", False)),
                "paper_orders_enabled": bool(decision.get("paper_orders_enabled", False) or payload.get("paper_orders_enabled", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_bounded_cadence_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_bounded_cadence_enabled:
            return {}
        return write_paper_unlock_bounded_cadence_report(self.data_dir)


    def _read_paper_unlock_shadow_stability_review_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_shadow_stability_review_report.json"
        if not path.exists():
            return {"status": "MISSING", "path": str(path)}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            checks = payload.get("stability_checks", {}) if isinstance(payload.get("stability_checks"), dict) else {}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            return {
                "status": payload.get("status", "UNKNOWN"),
                "decision_status": decision.get("status", "UNKNOWN"),
                "review_name": payload.get("review_name", ""),
                "best_stability_review_variant": decision.get("best_stability_review_variant", ""),
                "selected_entries": decision.get("selected_entries", counts.get("selected_entries", 0)),
                "next_patch": decision.get("next_patch", ""),
                "sample_ok": bool(checks.get("sample_ok", False)),
                "rolling_window_ok": bool(checks.get("rolling_window_ok", False)),
                "holdout_ok": bool(checks.get("holdout_ok", False)),
                "concentration_ok": bool(checks.get("concentration_ok", False)),
                "temporal_dispersion_ok": bool(checks.get("temporal_dispersion_ok", False)),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_experiment_allowed": bool(decision.get("paper_unlock_experiment_allowed", False)),
                "paper_orders_enabled": bool(decision.get("paper_orders_enabled", False) or payload.get("paper_orders_enabled", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_shadow_stability_review_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_shadow_stability_review_enabled:
            return {}
        return write_paper_unlock_shadow_stability_review_report(self.data_dir)

    def _read_paper_unlock_activation_draft_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_activation_draft_report.json"
        if not path.exists():
            return {"status": "MISSING", "path": str(path)}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            prereq = payload.get("stability_prerequisite", {}) if isinstance(payload.get("stability_prerequisite"), dict) else {}
            counts = payload.get("counts", {}) if isinstance(payload.get("counts"), dict) else {}
            return {
                "status": payload.get("status", "UNKNOWN"),
                "decision_status": decision.get("status", "UNKNOWN"),
                "draft_name": payload.get("draft_name", ""),
                "profile_name": payload.get("profile_name", ""),
                "best_stability_review_variant": decision.get("best_stability_review_variant", ""),
                "selected_entries": decision.get("selected_entries", counts.get("selected_entries", 0)),
                "interlocks_ready": bool(decision.get("interlocks_ready", False)),
                "stability_prerequisite_ok": bool(prereq.get("passes_stability_prerequisite", False)),
                "next_patch": decision.get("next_patch", ""),
                "operational_unlock_allowed": bool(decision.get("operational_unlock_allowed", False)),
                "paper_unlock_experiment_allowed": bool(decision.get("paper_unlock_experiment_allowed", False)),
                "paper_orders_enabled": bool(decision.get("paper_orders_enabled", False) or payload.get("paper_orders_enabled", False)),
                "profile_activation_allowed": bool(decision.get("profile_activation_allowed", False) or payload.get("profile_activation_allowed", False)),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_activation_draft_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_activation_draft_enabled:
            return {}
        return write_paper_unlock_activation_draft_report(self.data_dir)

    def _read_paper_unlock_experiment_switch_draft_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_experiment_switch_draft_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            return {
                "status": payload.get("status"),
                "decision": decision.get("status"),
                "switch_name": payload.get("switch_name"),
                "profile_name": payload.get("profile_name"),
                "selected_entries": decision.get("selected_entries"),
                "activation_draft_ready": decision.get("activation_draft_ready"),
                "switch_implementation_ready": decision.get("switch_implementation_ready"),
                "paper_orders_enabled": payload.get("paper_orders_enabled"),
                "operational_unlock_allowed": payload.get("operational_unlock_allowed"),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_experiment_switch_draft_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_experiment_switch_draft_enabled:
            return {}
        return write_paper_unlock_experiment_switch_draft_report(self.data_dir)

    def _read_paper_unlock_manual_switch_preflight_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_manual_switch_preflight_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            return {
                "status": payload.get("status"),
                "decision": decision.get("status"),
                "preflight_name": payload.get("preflight_name"),
                "switch_name": payload.get("switch_name"),
                "profile_name": payload.get("profile_name"),
                "selected_entries": decision.get("selected_entries"),
                "switch_draft_ready": decision.get("switch_draft_ready"),
                "fail_closed_preflight_ok": decision.get("fail_closed_preflight_ok"),
                "paper_orders_enabled": payload.get("paper_orders_enabled"),
                "operational_unlock_allowed": payload.get("operational_unlock_allowed"),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_manual_switch_preflight_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_manual_switch_preflight_enabled:
            return {}
        return write_paper_unlock_manual_switch_preflight_report(self.data_dir)

    def _read_paper_unlock_manual_activation_patch_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_manual_activation_patch_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            return {
                "status": payload.get("status"),
                "decision": decision.get("status"),
                "activation_patch_name": payload.get("activation_patch_name"),
                "profile_name": payload.get("profile_name"),
                "selected_entries": decision.get("selected_entries"),
                "preflight_guard_ok": decision.get("preflight_guard_ok"),
                "activation_preflight_ok": decision.get("activation_preflight_ok"),
                "future_activation_simulation_ok": decision.get("future_activation_simulation_ok"),
                "paper_orders_enabled": payload.get("paper_orders_enabled"),
                "operational_unlock_allowed": payload.get("operational_unlock_allowed"),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_manual_activation_patch_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_manual_activation_patch_enabled:
            return {}
        return write_paper_unlock_manual_activation_patch_report(self.data_dir)

    def _read_paper_unlock_final_enable_preflight_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_final_enable_preflight_report.json"
        if not path.exists():
            return {"status": "MISSING"}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"status": "INVALID"}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            return {
                "status": payload.get("status"),
                "decision": decision.get("status"),
                "final_preflight_name": payload.get("final_preflight_name"),
                "profile_name": payload.get("profile_name"),
                "selected_entries": decision.get("selected_entries"),
                "activation_patch_guard_ok": decision.get("activation_patch_guard_ok"),
                "final_enable_preflight_ok": decision.get("final_enable_preflight_ok"),
                "paper_order_activation_candidate_allowed": decision.get("paper_order_activation_candidate_allowed"),
                "paper_orders_enabled": payload.get("paper_orders_enabled"),
                "operational_unlock_allowed": payload.get("operational_unlock_allowed"),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_final_enable_preflight_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_final_enable_preflight_enabled:
            return {}
        return write_paper_unlock_final_enable_preflight_report(self.data_dir)

    def _read_paper_unlock_guarded_enable_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_guarded_enable_report.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
        return {
            "status": payload.get("status"),
            "decision": decision.get("status"),
            "enable_name": decision.get("enable_name"),
            "profile_name": decision.get("profile_name"),
            "selected_entries": decision.get("selected_entries"),
            "paper_orders_enabled": payload.get("paper_orders_enabled"),
            "paper_unlock_experiment_allowed": payload.get("paper_unlock_experiment_allowed"),
            "manual_activation_allowed": payload.get("manual_activation_allowed"),
            "operational_unlock_allowed": payload.get("operational_unlock_allowed"),
        }

    def write_paper_unlock_guarded_enable_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_guarded_enable_enabled:
            return {}
        return write_paper_unlock_guarded_enable_report(self.data_dir)

    def _read_paper_unlock_runtime_audit_summary(self) -> dict[str, Any]:
        path = self.data_dir / "paper_unlock_runtime_audit_report.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            runtime = payload.get("runtime_profile_audit", {}) if isinstance(payload.get("runtime_profile_audit"), dict) else {}
            legacy = payload.get("legacy_unlock_audit", {}) if isinstance(payload.get("legacy_unlock_audit"), dict) else {}
            return {
                "status": payload.get("status"),
                "decision_status": decision.get("status"),
                "profile_name": decision.get("profile_name"),
                "latest_cycle_id": decision.get("latest_cycle_id"),
                "runtime_audit_events": decision.get("runtime_audit_events"),
                "legacy_unlock_events": decision.get("legacy_unlock_events"),
                "runtime_accepts_diagnostic": decision.get("runtime_accepts_diagnostic"),
                "runtime_rejects": decision.get("runtime_rejects"),
                "runtime_coverage_ok": decision.get("runtime_coverage_ok"),
                "legacy_profile_counts": legacy.get("legacy_profile_counts"),
                "reject_reason_counts": runtime.get("reject_reason_counts"),
                "paper_orders_enabled": payload.get("paper_orders_enabled"),
                "operational_unlock_allowed": payload.get("operational_unlock_allowed"),
            }
        except Exception as exc:
            return {"status": "READ_ERROR", "error": str(exc)}

    def write_paper_unlock_runtime_audit_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_runtime_audit_enabled:
            return {}
        return write_paper_unlock_runtime_audit_report(self.data_dir)

    def write_paper_unlock_routing_bridge_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_routing_bridge_enabled:
            return {}
        return write_paper_unlock_routing_bridge_report(self.data_dir, self.routing_bridge_settings)

    def write_paper_unlock_candidate_audit_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_candidate_audit_enabled:
            return {}
        return write_paper_unlock_candidate_audit_report(self.data_dir, self.candidate_audit_settings)

    def write_paper_unlock_handoff_dry_run_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_handoff_dry_run_enabled:
            return {}
        return write_paper_unlock_handoff_dry_run_report(self.data_dir, self.handoff_dry_run_settings)

    def write_paper_order_leakage_guard_report(self) -> dict[str, Any]:
        if not self.settings.paper_order_leakage_guard_enabled:
            return {}
        return write_paper_order_leakage_guard_report(self.data_dir, self.order_leakage_guard_settings)

    def write_edge_strategy_runtime_pruning_report(self) -> dict[str, Any]:
        if not self.settings.edge_strategy_pruning_audit_enabled:
            return {}
        return write_edge_strategy_runtime_pruning_report(self.data_dir, self.edge_strategy_pruning_settings)

    def write_lsr_v2_paper_supervised_bridge_report(self) -> dict[str, Any]:
        if not self.settings.lsr_v2_paper_supervised_bridge_enabled:
            return {}
        # s-10d keeps the historical/standalone bridge report available, but it
        # no longer mirrors historical candidate events into paper_events.jsonl.
        # Runtime visibility is handled by the cycle-scoped bridge below.
        return write_lsr_v2_paper_supervised_bridge_report(self.data_dir, self.lsr_v2_bridge_settings)

    def write_lsr_v2_runtime_bridge_report(self) -> dict[str, Any]:
        if not self.settings.lsr_v2_paper_supervised_bridge_enabled:
            return {}
        cycle_id = str((self._last_completed_cycle_summary or {}).get("cycle_id") or self._active_cycle_id or "")
        standalone = {}
        standalone_path = self.data_dir / "lsr_v2_paper_supervised_bridge_report.json"
        if standalone_path.exists():
            try:
                standalone = json.loads(standalone_path.read_text(encoding="utf-8"))
                if not isinstance(standalone, dict):
                    standalone = {}
            except Exception:
                standalone = {}
        promotion = {}
        promotion_path = self.data_dir / "lsr_v2_promotion_gate_report.json"
        if promotion_path.exists():
            try:
                promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
                if not isinstance(promotion, dict):
                    promotion = {}
            except Exception:
                promotion = {}
        return write_lsr_v2_runtime_bridge_artifacts(
            data_dir=self.data_dir,
            cycle_id=cycle_id,
            events=list(self._lsr_v2_runtime_cycle_events),
            settings=self.lsr_v2_runtime_bridge_settings,
            standalone_report=standalone,
            promotion_gate_report=promotion,
        )

    def write_lsr_v2_engine_read_only_artifact_hook_report(self) -> dict[str, Any]:
        if not self.settings.lsr_v2_engine_read_only_artifact_hook_enabled:
            return {}
        return write_lsr_v2_engine_read_only_artifact_hook_report(
            self.data_dir,
            self.lsr_v2_engine_read_only_artifact_hook_settings,
        )

    def write_paper_unlock_supervised_execution_report(self) -> dict[str, Any]:
        if not self.settings.paper_unlock_supervised_execution_enabled:
            return {}
        return write_paper_unlock_supervised_execution_report(self.data_dir, self.supervised_execution_settings)

    def write_candlestick_pattern_report(self) -> dict[str, Any]:
        if not self.settings.candlestick_patterns_enabled:
            return {}
        return write_candlestick_pattern_report(self.data_dir)

    def write_crypto_scenario_report(self) -> dict[str, Any]:
        if not self.settings.crypto_scenario_enabled:
            return {}
        return write_crypto_scenario_report(self.data_dir)

    def write_performance_artifacts(self) -> dict[str, Any]:
        diagnostics = self.write_signal_diagnostics_report()
        backfill = self.write_signal_diagnostics_backfill_report()
        shadow = self.write_shadow_unlock_report()
        crypto_scenario = self.write_crypto_scenario_report()
        candlestick_patterns = self.write_candlestick_pattern_report()
        pattern_conditioned_shadow = self.write_pattern_conditioned_shadow_report()
        scenario_pattern_calibration = self.write_scenario_pattern_calibration_report()
        market_structure_map = self.write_market_structure_map_report()
        calibrated_structure_shadow = self.write_calibrated_structure_shadow_report()
        structure_filter_diagnostics = self.write_structure_filter_diagnostics_report()
        structure_context_repair = self.write_structure_context_repair_report()
        repaired_structure_shadow_validation = self.write_repaired_structure_shadow_validation_report()
        independent_repaired_validation = self.write_independent_repaired_validation_report()
        paper_unlock_profile_refinement = self.write_paper_unlock_profile_refinement_report()
        paper_unlock_experiment_design = self.write_paper_unlock_experiment_design_report()
        paper_unlock_shadow_dry_run = self.write_paper_unlock_shadow_dry_run_report()
        paper_unlock_shadow_rate_calibration = self.write_paper_unlock_shadow_rate_calibration_report()
        paper_unlock_bounded_cadence = self.write_paper_unlock_bounded_cadence_report()
        paper_unlock_shadow_stability_review = self.write_paper_unlock_shadow_stability_review_report()
        paper_unlock_activation_draft = self.write_paper_unlock_activation_draft_report()
        paper_unlock_experiment_switch_draft = self.write_paper_unlock_experiment_switch_draft_report()
        paper_unlock_manual_switch_preflight = self.write_paper_unlock_manual_switch_preflight_report()
        paper_unlock_manual_activation_patch = self.write_paper_unlock_manual_activation_patch_report()
        paper_unlock_final_enable_preflight = self.write_paper_unlock_final_enable_preflight_report()
        paper_unlock_guarded_enable = self.write_paper_unlock_guarded_enable_report()
        paper_unlock_runtime_audit = self.write_paper_unlock_runtime_audit_report()
        paper_unlock_routing_bridge = self.write_paper_unlock_routing_bridge_report()
        paper_unlock_candidate_audit = self.write_paper_unlock_candidate_audit_report()
        paper_unlock_handoff_dry_run = self.write_paper_unlock_handoff_dry_run_report()
        paper_unlock_supervised_execution = self.write_paper_unlock_supervised_execution_report()
        paper_order_leakage_guard = self.write_paper_order_leakage_guard_report()
        edge_strategy_runtime_pruning = self.write_edge_strategy_runtime_pruning_report()
        lsr_v2_paper_supervised_bridge = self.write_lsr_v2_paper_supervised_bridge_report()
        lsr_v2_runtime_bridge = self.write_lsr_v2_runtime_bridge_report()
        lsr_v2_engine_artifact_hook = self.write_lsr_v2_engine_read_only_artifact_hook_report()
        artifacts = write_performance_artifacts(self.data_dir)
        if diagnostics:
            artifacts["signal_diagnostics"] = diagnostics
        if backfill:
            artifacts["signal_diagnostics_backfill"] = backfill
        if shadow:
            artifacts["shadow_unlock"] = shadow
        if crypto_scenario:
            artifacts["crypto_scenario"] = crypto_scenario
        if candlestick_patterns:
            artifacts["candlestick_patterns"] = candlestick_patterns
        if pattern_conditioned_shadow:
            artifacts["pattern_conditioned_shadow"] = pattern_conditioned_shadow
        if scenario_pattern_calibration:
            artifacts["scenario_pattern_calibration"] = scenario_pattern_calibration
        if market_structure_map:
            artifacts["market_structure_map"] = market_structure_map
        if calibrated_structure_shadow:
            artifacts["calibrated_structure_shadow"] = calibrated_structure_shadow
        if structure_filter_diagnostics:
            artifacts["structure_filter_diagnostics"] = structure_filter_diagnostics
        if structure_context_repair:
            artifacts["structure_context_repair"] = structure_context_repair
        if repaired_structure_shadow_validation:
            artifacts["repaired_structure_shadow_validation"] = repaired_structure_shadow_validation
        if independent_repaired_validation:
            artifacts["independent_repaired_validation"] = independent_repaired_validation
        if paper_unlock_profile_refinement:
            artifacts["paper_unlock_profile_refinement"] = paper_unlock_profile_refinement
        if paper_unlock_experiment_design:
            artifacts["paper_unlock_experiment_design"] = paper_unlock_experiment_design
        if paper_unlock_shadow_dry_run:
            artifacts["paper_unlock_shadow_dry_run"] = paper_unlock_shadow_dry_run
        if paper_unlock_shadow_rate_calibration:
            artifacts["paper_unlock_shadow_rate_calibration"] = paper_unlock_shadow_rate_calibration
        if paper_unlock_bounded_cadence:
            artifacts["paper_unlock_bounded_cadence"] = paper_unlock_bounded_cadence
        if paper_unlock_shadow_stability_review:
            artifacts["paper_unlock_shadow_stability_review"] = paper_unlock_shadow_stability_review
        if paper_unlock_activation_draft:
            artifacts["paper_unlock_activation_draft"] = paper_unlock_activation_draft
        if paper_unlock_experiment_switch_draft:
            artifacts["paper_unlock_experiment_switch_draft"] = paper_unlock_experiment_switch_draft
        if paper_unlock_manual_switch_preflight:
            artifacts["paper_unlock_manual_switch_preflight"] = paper_unlock_manual_switch_preflight
        if paper_unlock_manual_activation_patch:
            artifacts["paper_unlock_manual_activation_patch"] = paper_unlock_manual_activation_patch
        if paper_unlock_final_enable_preflight:
            artifacts["paper_unlock_final_enable_preflight"] = paper_unlock_final_enable_preflight
        if paper_unlock_guarded_enable:
            artifacts["paper_unlock_guarded_enable"] = paper_unlock_guarded_enable
        if paper_unlock_runtime_audit:
            artifacts["paper_unlock_runtime_audit"] = paper_unlock_runtime_audit
        if paper_unlock_routing_bridge:
            artifacts["paper_unlock_routing_bridge"] = paper_unlock_routing_bridge
        if paper_unlock_candidate_audit:
            artifacts["paper_unlock_candidate_audit"] = paper_unlock_candidate_audit
        if paper_unlock_handoff_dry_run:
            artifacts["paper_unlock_handoff_dry_run"] = paper_unlock_handoff_dry_run
        if paper_unlock_supervised_execution:
            artifacts["paper_unlock_supervised_execution"] = paper_unlock_supervised_execution
        if paper_order_leakage_guard:
            artifacts["paper_order_leakage_guard"] = paper_order_leakage_guard
        if edge_strategy_runtime_pruning:
            artifacts["edge_strategy_runtime_pruning"] = edge_strategy_runtime_pruning
        if lsr_v2_paper_supervised_bridge:
            artifacts["lsr_v2_paper_supervised_bridge"] = lsr_v2_paper_supervised_bridge
        if lsr_v2_runtime_bridge:
            artifacts["lsr_v2_runtime_bridge"] = lsr_v2_runtime_bridge
        if lsr_v2_engine_artifact_hook:
            artifacts["lsr_v2_engine_read_only_artifact_hook"] = lsr_v2_engine_artifact_hook
        return artifacts

    def format_status(self) -> str:
        s = self.broker.snapshot(self.last_prices)
        return (
            f"Mode: PAPER\nBalance: {s['balance']:.2f}\nEquity: {s['equity']:.2f}\n"
            f"Open: {s['open_positions']} Pending: {s['pending_orders']} DD: {s['drawdown_pct']:.2f}%\n"
            f"Paused: {s['is_paused']} Kill: {s['kill_switch']}\n"
            f"Cycle: {self._cycle_seq} Timeframe: {self.settings.timeframe} Cost: {self.settings.cost_model}\n"
            f"Telegram: enabled={self.telegram.enabled} read_only={self.telegram.read_only} allowed_users={len(self.telegram.allowed_user_ids)}"
        )

    def format_pnl(self) -> str:
        s = self.broker.snapshot(self.last_prices)
        return f"Realized: {s['realized_pnl']:+.2f}\nUnrealized: {s['unrealized_pnl']:+.2f}\nEquity: {s['equity']:.2f}"

    def render_position_monitor(self) -> str:
        snapshot = self.broker_adapter.reconcile()
        self.position_monitor.write(account=snapshot.account, positions=snapshot.positions)
        return self.position_monitor.format_console(account=snapshot.account, positions=snapshot.positions)

    def format_positions(self) -> str:
        snapshot = self.broker_adapter.reconcile()
        self.position_monitor.write(account=snapshot.account, positions=snapshot.positions)
        return self.position_monitor.format_telegram(account=snapshot.account, positions=snapshot.positions)

    def format_orders(self) -> str:
        orders = list(self.broker.orders.values())[-10:]
        if not orders:
            return "No paper orders."
        return "\n".join(
            f"{o.order_id} {o.symbol} {o.side} {o.status} price={o.filled_price or o.requested_price:.6f} reason={o.reason or '-'}"
            for o in orders
        )

    def format_risk(self) -> str:
        return (
            f"Risk/trade: {self.settings.risk_per_trade_pct*100:.2f}%\n"
            f"Max positions: {self.settings.max_positions}\n"
            f"Unlock max positions: {self.unlock_settings.max_positions if self.unlock_settings.enabled else '-'}\n"
            f"Open positions: {len(self.broker.open_positions)}\n"
            f"Paused: {self.broker.is_paused} Kill switch: {self.broker.kill_switch}\n"
            f"Universe: {','.join(self.settings.symbols)}\n"
            f"Cost model: {self.settings.cost_model}"
        )

    def format_report(self) -> str:
        perf_path = self.data_dir / "paper_performance_report.json"
        drift_path = self.data_dir / "paper_drift_report.json"
        dashboard_path = self.data_dir / "paper_dashboard.html"
        perf_status = "NA"
        drift_status = "NA"
        unlock_rejection_status = "NA"
        unlock_rejection_decision = "NA"
        scenario_status = "NA"
        scenario_decision = "NA"
        scenario_btc = 0
        candle_status = "NA"
        candle_decision = "NA"
        candle_btc = 0
        pcs_status = "NA"
        pcs_decision = "NA"
        pcs_hist = 0
        pcs_exp = 0.0
        spc_status = spc_decision = "NA"
        spc_hist = 0
        spc_profile = ""
        spc_profile_score = 0.0
        msm_status = msm_decision = "NA"
        msm_hist = 0
        msm_focus_bias = ""
        msm_focus_confirmation = ""
        try:
            if perf_path.exists():
                perf_status = json.loads(perf_path.read_text(encoding="utf-8")).get("status", "NA")
            if drift_path.exists():
                drift_status = json.loads(drift_path.read_text(encoding="utf-8")).get("status", "NA")
            unlock_path = self.data_dir / "paper_unlock_rejection_report.json"
            if unlock_path.exists():
                unlock_payload = json.loads(unlock_path.read_text(encoding="utf-8"))
                unlock_rejection_status = unlock_payload.get("status", "NA")
                unlock_decision = unlock_payload.get("decision", {}) if isinstance(unlock_payload.get("decision"), dict) else {}
                unlock_rejection_decision = unlock_decision.get("status", "NA")
            scenario_path = self.data_dir / "crypto_intraday_scenario_report.json"
            if scenario_path.exists():
                scenario_payload = json.loads(scenario_path.read_text(encoding="utf-8"))
                scenario_status = scenario_payload.get("status", "NA")
                scenario_dec = scenario_payload.get("decision", {}) if isinstance(scenario_payload.get("decision"), dict) else {}
                scenario_decision = scenario_dec.get("status", "NA")
                scenario_btc = int((scenario_payload.get("counts") or {}).get("btc_scenario_events", 0))
            candle_path = self.data_dir / "candlestick_pattern_report.json"
            if candle_path.exists():
                candle_payload = json.loads(candle_path.read_text(encoding="utf-8"))
                candle_status = candle_payload.get("status", "NA")
                candle_dec = candle_payload.get("decision", {}) if isinstance(candle_payload.get("decision"), dict) else {}
                candle_decision = candle_dec.get("status", "NA")
                candle_btc = int((candle_payload.get("counts") or {}).get("btc_pattern_events", 0))
            pcs_path = self.data_dir / "pattern_conditioned_shadow_report.json"
            if pcs_path.exists():
                pcs_payload = json.loads(pcs_path.read_text(encoding="utf-8"))
                pcs_status = pcs_payload.get("status", "NA")
                pcs_dec = pcs_payload.get("decision", {}) if isinstance(pcs_payload.get("decision"), dict) else {}
                pcs_decision = pcs_dec.get("status", "NA")
                pcs_counts = pcs_payload.get("counts", {}) if isinstance(pcs_payload.get("counts"), dict) else {}
                pcs_hist = int(pcs_counts.get("historical_candidates", 0) or 0)
                pcs_hist_summary = ((pcs_payload.get("historical_shadow") or {}).get("summary") or {}) if isinstance(pcs_payload.get("historical_shadow"), dict) else {}
                pcs_exp = float(pcs_hist_summary.get("expectancy_r", 0.0) or 0.0)
            spc_path = self.data_dir / "scenario_pattern_calibration_report.json"
            if spc_path.exists():
                spc_payload = json.loads(spc_path.read_text(encoding="utf-8"))
                spc_status = spc_payload.get("status", "NA")
                spc_dec = spc_payload.get("decision", {}) if isinstance(spc_payload.get("decision"), dict) else {}
                spc_decision = spc_dec.get("status", "NA")
                spc_counts = spc_payload.get("counts", {}) if isinstance(spc_payload.get("counts"), dict) else {}
                spc_hist = int(spc_counts.get("historical_candidates", 0) or 0)
                spc_profile_payload = spc_dec.get("candidate_profile", {}) if isinstance(spc_dec.get("candidate_profile"), dict) else {}
                spc_profile = str(spc_profile_payload.get("name", "") or "")
                spc_profile_score = float(spc_profile_payload.get("pattern_score_min", 0.0) or 0.0)
            msm_path = self.data_dir / "market_structure_map_report.json"
            if msm_path.exists():
                msm_payload = json.loads(msm_path.read_text(encoding="utf-8"))
                msm_status = msm_payload.get("status", "NA")
                msm_dec = msm_payload.get("decision", {}) if isinstance(msm_payload.get("decision"), dict) else {}
                msm_decision = msm_dec.get("status", "NA")
                msm_counts = msm_payload.get("counts", {}) if isinstance(msm_payload.get("counts"), dict) else {}
                msm_hist = int(msm_counts.get("historical_snapshots_evaluated", 0) or 0)
                msm_focus = msm_dec.get("focus_latest", {}) if isinstance(msm_dec.get("focus_latest"), dict) else {}
                msm_focus_bias = str(msm_focus.get("structure_bias", "") or "")
                msm_focus_confirmation = str(msm_focus.get("confirmation_summary", "") or "")
        except Exception:
            pass
        return (
            self.format_status()
            + "\n"
            + self.format_pnl()
            + f"\nPerformance: {perf_status} Drift: {drift_status}"
            + f"\nAdapter: PaperBrokerAdapter | Exchange: BLOCKED"
            + f"\nProactive: {self.settings.telegram_proactive_enabled} | AI debug: {self.settings.ai_debug}"
            + f"\nShadow simulation: {self.settings.shadow_simulation_enabled} | Unlock: {self.settings.paper_entry_unlock_enabled}"
            + f"\nUnlock profile: {self.unlock_settings.profile} | Symbols: {','.join(self.unlock_settings.allowed_symbols)}"
            + f"\nScenario engine: {self.settings.crypto_scenario_enabled} | Scenario: {scenario_status}/{scenario_decision} | BTC rows: {scenario_btc}"
            + f"\nCandles: {self.settings.candlestick_patterns_enabled} | Pattern: {candle_status}/{candle_decision} | BTC rows: {candle_btc}"
            + f"\nPattern shadow: {pcs_status}/{pcs_decision} | hist candidates: {pcs_hist} | expR: {pcs_exp:+.3f}"
            + f"\nScenario-pattern calib: {spc_status}/{spc_decision} | hist candidates: {spc_hist} | profile: {spc_profile or '-'}"
            + f"\nStructure map: {msm_status}/{msm_decision} | snapshots: {msm_hist} | BTC: {msm_focus_bias or '-'}/{msm_focus_confirmation or '-'}"
            + f"\nLast notification: {self.proactive.state.last_notification_type or '-'} {self.proactive.state.last_notification_at or ''}"
            + f"\nMonitor: {'active' if self.broker.open_positions else 'flat'}"
            + f"\nDashboard: {dashboard_path}"
        )


def _arg_or_config(args: Any, name: str, config_name: str, default: Any) -> Any:
    value = getattr(args, name, None)
    if value is None:
        return getattr(Config, config_name, default)
    return value


def settings_from_args(args: Any) -> PaperEngineSettings:
    symbols = parse_symbol_list(args.symbols or getattr(Config, "PAPER_ASSET_UNIVERSE", "BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT"))
    if not symbols:
        symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]
    return PaperEngineSettings(
        symbols=symbols,
        timeframe=args.timeframe,
        cost_model=args.cost_model,
        balance=float(args.balance),
        poll_seconds=float(args.poll_seconds),
        dry_run_once=bool(args.once),
        max_cycles=max(0, int(_arg_or_config(args, "max_cycles", "PAPER_MAX_CYCLES", 0) or 0)),
        max_positions=int(args.max_positions),
        risk_per_trade_pct=float(args.risk_per_trade_pct),
        rr=float(args.rr),
        mode=args.mode,
        market_data_mode=str(_arg_or_config(args, "market_data_mode", "PAPER_MARKET_DATA_MODE", "live") or "live").lower(),
        market_data_cache_dir=str(_arg_or_config(args, "market_data_cache_dir", "PAPER_MARKET_DATA_CACHE_DIR", "data") or "data"),
        market_data_replay_step=max(1, int(_arg_or_config(args, "market_data_replay_step", "PAPER_MARKET_DATA_REPLAY_STEP", 1) or 1)),
        market_data_replay_start_offset=max(0, int(_arg_or_config(args, "market_data_replay_start_offset", "PAPER_MARKET_DATA_REPLAY_START_OFFSET", 0) or 0)),
        cycle_artifacts_enabled=bool(
            getattr(args, "cycle_artifacts", None)
            if getattr(args, "cycle_artifacts", None) is not None
            else getattr(Config, "PAPER_CYCLE_ARTIFACTS_ENABLED", bool(args.once))
        ),
        console_verbose=bool(_arg_or_config(args, "console_verbose", "PAPER_CONSOLE_VERBOSE", False)),
        ai_debug=bool(_arg_or_config(args, "verbose_ai", "PAPER_AI_DEBUG", False)),
        console_header_every_n_cycles=int(getattr(Config, "PAPER_CONSOLE_HEADER_EVERY_N_CYCLES", 12)),
        console_show_flat_monitor=bool(getattr(Config, "PAPER_CONSOLE_SHOW_FLAT_MONITOR", False)),
        telegram_proactive_enabled=bool(_arg_or_config(args, "telegram_proactive", "TELEGRAM_PROACTIVE_ENABLED", True)),
        telegram_notify_on_start=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_START", True)),
        telegram_notify_on_shutdown=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_SHUTDOWN", True)),
        telegram_notify_on_signal=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_SIGNAL", True)),
        telegram_notify_on_order=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_ORDER", True)),
        telegram_notify_on_position_open=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_POSITION_OPEN", True)),
        telegram_notify_on_position_close=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_POSITION_CLOSE", True)),
        telegram_notify_on_tp_sl=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_TP_SL", True)),
        telegram_notify_on_drift_warn=bool(getattr(Config, "TELEGRAM_NOTIFY_ON_DRIFT_WARN", True)),
        telegram_notify_every_cycle=bool(getattr(Config, "TELEGRAM_NOTIFY_EVERY_CYCLE", False)),
        telegram_notify_no_signal_every_n_cycles=int(getattr(Config, "TELEGRAM_NOTIFY_NO_SIGNAL_EVERY_N_CYCLES", 12)),
        telegram_notify_position_every_n_cycles=int(getattr(Config, "TELEGRAM_NOTIFY_POSITION_EVERY_N_CYCLES", 1)),
        telegram_notify_position_every_seconds=float(getattr(Config, "TELEGRAM_NOTIFY_POSITION_EVERY_SECONDS", 300.0)),
        telegram_notify_position_pnl_delta_pct=float(getattr(Config, "TELEGRAM_NOTIFY_POSITION_PNL_DELTA_PCT", 0.25)),
        telegram_proactive_dedup_seconds=float(getattr(Config, "TELEGRAM_PROACTIVE_DEDUP_SECONDS", 30.0)),
        telegram_proactive_max_messages_per_minute=int(getattr(Config, "TELEGRAM_PROACTIVE_MAX_MESSAGES_PER_MINUTE", 10)),
        signal_diagnostics_enabled=(False if bool(getattr(args, "no_signal_diagnostics", False)) else bool(getattr(Config, "PAPER_SIGNAL_DIAGNOSTICS_ENABLED", True))),
        signal_diagnostics_backfill_enabled=(False if bool(getattr(args, "no_signal_diagnostics_backfill", False)) else bool(getattr(Config, "PAPER_SIGNAL_DIAGNOSTICS_BACKFILL_ENABLED", True))),
        exploratory_signal_analysis=bool(getattr(Config, "PAPER_EXPLORATORY_SIGNAL_ANALYSIS", True)),
        paper_entry_unlock_enabled=bool(_arg_or_config(args, "paper_unlock", "PAPER_ENTRY_UNLOCK_ENABLED", False)),
        unlock_rejection_analysis_enabled=(False if bool(getattr(args, "no_unlock_rejection_analysis", False)) else bool(getattr(Config, "PAPER_UNLOCK_REJECTION_ANALYSIS_ENABLED", True))),
        crypto_scenario_enabled=(False if bool(getattr(args, "no_crypto_scenario", False)) else bool(getattr(Config, "PAPER_CRYPTO_SCENARIO_ENABLED", True))),
        candlestick_patterns_enabled=(False if bool(getattr(args, "no_candlestick_patterns", False)) else bool(getattr(Config, "PAPER_CANDLESTICK_PATTERNS_ENABLED", True))),
        pattern_conditioned_shadow_enabled=(False if bool(getattr(args, "no_pattern_conditioned_shadow", False)) else bool(getattr(Config, "PATTERN_CONDITIONED_SHADOW_ENABLED", True))),
        scenario_pattern_calibration_enabled=(False if bool(getattr(args, "no_scenario_pattern_calibration", False)) else bool(getattr(Config, "SCENARIO_PATTERN_CALIBRATION_ENABLED", True))),
        market_structure_map_enabled=(False if bool(getattr(args, "no_market_structure_map", False)) else bool(getattr(Config, "MARKET_STRUCTURE_MAP_ENABLED", True))),
        calibrated_structure_shadow_enabled=(False if bool(getattr(args, "no_calibrated_structure_shadow", False)) else bool(getattr(Config, "CALIBRATED_STRUCTURE_SHADOW_ENABLED", True))),
        structure_filter_diagnostics_enabled=(False if bool(getattr(args, "no_structure_filter_diagnostics", False)) else bool(getattr(Config, "STRUCTURE_FILTER_DIAGNOSTICS_ENABLED", True))),
        structure_context_repair_enabled=(False if bool(getattr(args, "no_structure_context_repair", False)) else bool(getattr(Config, "STRUCTURE_CONTEXT_REPAIR_ENABLED", True))),
        repaired_structure_shadow_validation_enabled=(False if bool(getattr(args, "no_repaired_structure_shadow_validation", False)) else bool(getattr(Config, "REPAIRED_STRUCTURE_SHADOW_VALIDATION_ENABLED", True))),
        independent_repaired_validation_enabled=(False if bool(getattr(args, "no_independent_repaired_validation", False)) else bool(getattr(Config, "INDEPENDENT_REPAIRED_VALIDATION_ENABLED", True))),
        paper_unlock_profile_refinement_enabled=(False if bool(getattr(args, "no_paper_unlock_profile_refinement", False)) else bool(getattr(Config, "PAPER_UNLOCK_PROFILE_REFINEMENT_ENABLED", True))),
        paper_unlock_experiment_design_enabled=(False if bool(getattr(args, "no_paper_unlock_experiment_design", False)) else bool(getattr(Config, "PAPER_UNLOCK_EXPERIMENT_DESIGN_ENABLED", True))),
        paper_unlock_shadow_dry_run_enabled=(False if bool(getattr(args, "no_paper_unlock_shadow_dry_run", False)) else bool(getattr(Config, "PAPER_UNLOCK_SHADOW_DRY_RUN_ENABLED", True))),
        paper_unlock_shadow_rate_calibration_enabled=(False if bool(getattr(args, "no_paper_unlock_shadow_rate_calibration", False)) else bool(getattr(Config, "PAPER_UNLOCK_SHADOW_RATE_CALIBRATION_ENABLED", True))),
        paper_unlock_bounded_cadence_enabled=(False if bool(getattr(args, "no_paper_unlock_bounded_cadence", False)) else bool(getattr(Config, "PAPER_UNLOCK_BOUNDED_CADENCE_ENABLED", True))),
        paper_unlock_shadow_stability_review_enabled=(False if bool(getattr(args, "no_paper_unlock_shadow_stability_review", False)) else bool(getattr(Config, "PAPER_UNLOCK_SHADOW_STABILITY_REVIEW_ENABLED", True))),
        paper_unlock_activation_draft_enabled=(False if bool(getattr(args, "no_paper_unlock_activation_draft", False)) else bool(getattr(Config, "PAPER_UNLOCK_ACTIVATION_DRAFT_ENABLED", True))),
        paper_unlock_experiment_switch_draft_enabled=(False if bool(getattr(args, "no_paper_unlock_experiment_switch_draft", False)) else bool(getattr(Config, "PAPER_UNLOCK_EXPERIMENT_SWITCH_DRAFT_ENABLED", True))),
        paper_unlock_manual_switch_preflight_enabled=(False if bool(getattr(args, "no_paper_unlock_manual_switch_preflight", False)) else bool(getattr(Config, "PAPER_UNLOCK_MANUAL_SWITCH_PREFLIGHT_ENABLED", True))),
        paper_unlock_manual_activation_patch_enabled=(False if bool(getattr(args, "no_paper_unlock_manual_activation_patch", False)) else bool(getattr(Config, "PAPER_UNLOCK_MANUAL_ACTIVATION_PATCH_ENABLED", True))),
        paper_unlock_final_enable_preflight_enabled=(False if bool(getattr(args, "no_paper_unlock_final_enable_preflight", False)) else bool(getattr(Config, "PAPER_UNLOCK_FINAL_ENABLE_PREFLIGHT_ENABLED", True))),
        paper_unlock_guarded_enable_enabled=(False if bool(getattr(args, "no_paper_unlock_guarded_enable", False)) else bool(getattr(Config, "PAPER_UNLOCK_GUARDED_ENABLE_ENABLED", True))),
        paper_unlock_runtime_audit_enabled=(False if bool(getattr(args, "no_paper_unlock_runtime_audit", False)) else bool(getattr(Config, "PAPER_UNLOCK_RUNTIME_AUDIT_ENABLED", True))),
        paper_unlock_routing_bridge_enabled=(False if bool(getattr(args, "no_paper_unlock_routing_bridge", False)) else bool(getattr(Config, "PAPER_UNLOCK_ROUTING_BRIDGE_ENABLED", True))),
        paper_unlock_candidate_audit_enabled=(False if bool(getattr(args, "no_paper_unlock_candidate_audit", False)) else bool(getattr(Config, "PAPER_UNLOCK_CANDIDATE_AUDIT_ENABLED", True))),
        paper_unlock_handoff_dry_run_enabled=(False if bool(getattr(args, "no_paper_unlock_handoff_dry_run", False)) else bool(getattr(Config, "PAPER_UNLOCK_HANDOFF_DRY_RUN_ENABLED", True))),
        paper_unlock_supervised_execution_enabled=(False if bool(getattr(args, "no_paper_unlock_supervised_execution", False)) else bool(getattr(Config, "PAPER_UNLOCK_SUPERVISED_EXECUTION_ENABLED", True))),
        paper_unlock_supervised_execution_operator_enable=(bool(getattr(args, "paper_unlock_supervised_execution", False)) or bool(getattr(Config, "PAPER_UNLOCK_SUPERVISED_EXECUTION_OPERATOR_ENABLE", False))),
        paper_unlock_supervised_execution_confirm=str(getattr(args, "paper_unlock_supervised_confirm", "") or getattr(Config, "PAPER_UNLOCK_SUPERVISED_EXECUTION_CONFIRM", "") or ""),
        paper_order_leakage_guard_enabled=(False if bool(getattr(args, "no_paper_order_leakage_guard", False)) else bool(getattr(Config, "PAPER_ORDER_LEAKAGE_GUARD_ENABLED", True))),
        edge_strategy_pruning_enabled=bool(getattr(Config, "EDGE_STRATEGY_PRUNING_ENABLED", False)),
        edge_strategy_pruning_audit_enabled=bool(getattr(Config, "EDGE_STRATEGY_PRUNING_AUDIT_ENABLED", True)),
        lsr_v2_paper_supervised_bridge_enabled=(False if bool(getattr(args, "no_lsr_v2_paper_supervised_bridge", False)) else bool(getattr(Config, "LSR_V2_PAPER_SUPERVISED_BRIDGE_ENABLED", True))),
        lsr_v2_paper_supervised_bridge_operator_enable=(bool(getattr(args, "lsr_v2_bridge_operator_enable", False)) or bool(getattr(Config, "LSR_V2_PAPER_SUPERVISED_BRIDGE_OPERATOR_ENABLE", False))),
        lsr_v2_paper_supervised_bridge_confirm=str(getattr(args, "lsr_v2_bridge_confirm", "") or getattr(Config, "LSR_V2_PAPER_SUPERVISED_BRIDGE_CONFIRM", "") or ""),
        lsr_v2_engine_read_only_artifact_hook_enabled=(False if bool(getattr(args, "no_lsr_v2_engine_read_only_artifact_hook", False)) else bool(getattr(Config, "LSR_V2_ENGINE_READ_ONLY_ARTIFACT_HOOK_ENABLED", True))),
        shadow_simulation_enabled=(False if bool(getattr(args, "no_shadow_simulation", False)) else bool(getattr(Config, "PAPER_SHADOW_SIMULATION_ENABLED", True))),
        paper_unlock_profile=str(getattr(args, "paper_unlock_profile", "") or getattr(Config, "PAPER_UNLOCK_PROFILE", "BTC_ONLY_40_Q60")),
        paper_unlock_allowed_symbols=[x.strip() for x in str(getattr(Config, "PAPER_UNLOCK_ALLOWED_SYMBOLS", "BTC/USDT")).replace(";", ",").split(",") if x.strip()],
        paper_unlock_min_ai_prob=float(getattr(Config, "PAPER_UNLOCK_MIN_AI_PROB", 40.0)),
        paper_unlock_min_setup_quality=float(getattr(Config, "PAPER_UNLOCK_MIN_SETUP_QUALITY", 60.0)),
        paper_unlock_max_positions=int(getattr(Config, "PAPER_UNLOCK_MAX_POSITIONS", 1)),
        paper_unlock_live_block=bool(getattr(Config, "PAPER_UNLOCK_LIVE_BLOCK", True)),
    )
