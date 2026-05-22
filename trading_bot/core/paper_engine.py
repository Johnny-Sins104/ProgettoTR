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
from core.paper_position_monitor import PaperPositionMonitor
from core.paper_lifecycle import max_cycle_sequence, write_lifecycle_report
from core.paper_performance import write_performance_artifacts
from core.telegram_control import TelegramControlBot
from core.telegram_proactive import TelegramProactiveNotifier, TelegramProactiveSettings, stable_hash
from core.paper_signal_diagnostics import build_signal_diagnostic, write_signal_diagnostics_report, write_signal_diagnostics_backfill_report
from core.paper_shadow_simulation import write_shadow_unlock_report
from core.paper_unlock_gate import PaperUnlockGateSettings, evaluate_paper_unlock
from core.analyzer import TechnicalAnalyzer


@dataclass
class PaperEngineSettings:
    symbols: list[str]
    timeframe: str = "5m"
    cost_model: str = "conservative"
    balance: float = 1000.0
    poll_seconds: float = 60.0
    dry_run_once: bool = False
    max_positions: int = 3
    risk_per_trade_pct: float = 0.005
    rr: float = 2.0
    mode: str = "paper"
    data_dir: str = "data"
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
        self.position_monitor = PaperPositionMonitor(output_path=self.data_dir / "paper_position_monitor.json")
        self._cycle_seq = max_cycle_sequence(self.data_dir / "paper_events.jsonl")
        self._shutdown_requested = False
        self._active_cycle_id: str | None = None
        self._cycle_started_at: datetime | None = None
        self._last_drift_status: str | None = None
        self._last_position_pnl_pct_by_id: dict[str, float] = {}
        self._last_position_notify_cycle_by_id: dict[str, int] = {}
        self._startup_banner_printed = False
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
        )
        self.exchange_adapter_stub.write_design_stub(self.data_dir / "exchange_broker_adapter_stub.json")
        self.write_status_file()
        self._print_startup_banner()
        await self._notify_startup()
        tg_task = asyncio.create_task(self.telegram.poll_forever(), name="telegram_poll_forever") if self.telegram.enabled else None
        try:
            while True:
                await self.tick()
                if self.settings.dry_run_once:
                    break
                await asyncio.sleep(self.settings.poll_seconds)
        except asyncio.CancelledError:
            self._shutdown_requested = True
            self.broker.emit("SHUTDOWN_REQUESTED", reason="asyncio_cancelled", active_cycle_id=self._active_cycle_id)
            if self._active_cycle_id:
                self.broker.emit("ASYNC_TASK_CANCELLED", cycle_id=self._active_cycle_id, component="paper_engine")
            raise
        finally:
            print("[PaperEngine] Shutdown requested. Closing exchange sessions...") if self._shutdown_requested else None
            self.broker.save()
            self.write_status_file()
            report = self.write_lifecycle_report()
            artifacts = self.write_performance_artifacts()
            self.broker.emit("ENGINE_STOPPED", lifecycle_status=report.get("status"), shutdown_requested=self._shutdown_requested)
            self.broker.save()
            self.write_status_file()
            report = self.write_lifecycle_report()
            artifacts = self.write_performance_artifacts()
            if self._shutdown_requested:
                await self._notify_shutdown(lifecycle_report=report, artifacts=artifacts, reason="CTRL+C / shutdown_requested")
            if tg_task:
                tg_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await tg_task
                self.broker.emit("ASYNC_TASK_CANCELLED", component="telegram_poll_forever")
            self.proactive.save()
            if self._shutdown_requested:
                print("[PaperEngine] Engine stopped cleanly.")

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
        self.broker.emit(
            "CYCLE_STARTED",
            cycle_id=cycle_id,
            symbols=self.settings.symbols,
            timeframe=self.settings.timeframe,
            cost_model=self.settings.cost_model,
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
        self.write_lifecycle_report()
        artifacts = self.write_performance_artifacts()
        drift_status = artifacts.get("drift", {}).get("status") if isinstance(artifacts, dict) else "NA"
        self._print_cycle_summary(summary, drift_status=drift_status)
        monitor_text = self.render_position_monitor()
        if monitor_text and (self.settings.console_verbose or int(summary.get("open_positions") or 0) > 0):
            print(monitor_text)
        elif self.settings.console_show_flat_monitor and not monitor_text:
            print("PAPER POSITION MONITOR | FLAT")
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
        print(self._console_header_line())
        print(f"assets={','.join(self.settings.symbols)} poll={self.settings.poll_seconds:g}s")
        self._startup_banner_printed = True

    def _print_cycle_summary(self, summary: dict[str, Any], *, drift_status: str) -> None:
        header_every = max(0, int(self.settings.console_header_every_n_cycles or 0))
        if header_every and self._cycle_seq > 0 and self._cycle_seq % header_every == 0:
            print(self._console_header_line())
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
        print(base)

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

    async def evaluate_symbol(self, symbol: str, *, cycle_id: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {"symbol": symbol, "scanned": 0, "signal": 0, "order": 0, "error": 0, "no_signal": 0, "skipped": 0}
        client: ExchangeClient | None = None
        try:
            client = ExchangeClient(
                exchange_id=Config.EXCHANGE_ID,
                symbol=symbol,
                timeframe=self.settings.timeframe,
                limit=int(os.getenv("PAPER_CANDLE_LIMIT", "500")),
                api_key=None,
                api_secret=None,
            )
            df = await client.fetch_async()
            self.broker.emit("EXCHANGE_CLIENT_CLOSED", cycle_id=cycle_id, symbol=symbol)
            if df is None or df.empty:
                self.broker.emit("MARKET_DATA_EMPTY", cycle_id=cycle_id, symbol=symbol)
                result["error"] = 1
                return result
            df = TechnicalAnalyzer().add_indicators(df)
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
                    })
                    _entry_type = "PAPER_UNLOCK"
                    _conf_verdict = "PAPER_UNLOCK"
                    conf_comb = f"PaperUnlock({unlock_decision.profile})"

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
                )
                return result
            result["signal"] = 1
            if unlock_decision is not None and unlock_decision.accepted:
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
            self.broker.emit(
                "SIGNAL_DETECTED",
                cycle_id=cycle_id,
                symbol=symbol,
                side=verdict,
                score=score,
                confidence=conf,
                candle_ts=candle_ts,
                paper_unlock=bool(unlock_decision is not None and unlock_decision.accepted),
                unlock_profile=(unlock_decision.profile if unlock_decision is not None and unlock_decision.accepted else None),
            )
            if not (unlock_decision is not None and unlock_decision.accepted):
                await self._notify_signal_detected(symbol=symbol, side=verdict, score=score, conf=conf, cycle_id=cycle_id)
            self.last_signal_by_symbol[symbol] = candle_key
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
            order = self.broker_adapter.place_order(
                symbol=symbol,
                side=verdict,  # type: ignore[arg-type]
                qty=qty,
                price=last_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                metadata={
                    "score": score,
                    "confidence": conf,
                    "combination": conf_comb,
                    "timeframe": self.settings.timeframe,
                    "cost_model": self.settings.cost_model,
                    "candle_ts": str(df.index[-1]),
                    "cycle_id": cycle_id,
                    "paper_unlock": bool(unlock_decision is not None and unlock_decision.accepted),
                    "unlock_profile": (unlock_decision.profile if unlock_decision is not None and unlock_decision.accepted else None),
                    "unlock_tag": (unlock_decision.tag if unlock_decision is not None and unlock_decision.accepted else None),
                    "regime": ((signal_diag or {}).get("regime") if unlock_decision is not None and unlock_decision.accepted else (conf.get("regime") if isinstance(conf, dict) else None)),
                },
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
            self.broker.emit("SYMBOL_ERROR", cycle_id=cycle_id, symbol=symbol, error=str(exc), error_type=exc.__class__.__name__)
            self.broker.emit("EXCHANGE_CLIENT_CLOSED", cycle_id=cycle_id, symbol=symbol, status="error")
            print(f"[PaperEngine] Symbol error | {symbol} | {exc} | skipped")
            return result

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
            "active_cycle_id": self._active_cycle_id,
            "cycle_seq": self._cycle_seq,
            "shutdown_requested": self._shutdown_requested,
            "dashboard_path": str(self.data_dir / "paper_dashboard.html"),
            "performance_report_path": str(self.data_dir / "paper_performance_report.json"),
            "drift_report_path": str(self.data_dir / "paper_drift_report.json"),
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

    def write_performance_artifacts(self) -> dict[str, Any]:
        diagnostics = self.write_signal_diagnostics_report()
        backfill = self.write_signal_diagnostics_backfill_report()
        shadow = self.write_shadow_unlock_report()
        artifacts = write_performance_artifacts(self.data_dir)
        if diagnostics:
            artifacts["signal_diagnostics"] = diagnostics
        if backfill:
            artifacts["signal_diagnostics_backfill"] = backfill
        if shadow:
            artifacts["shadow_unlock"] = shadow
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
        try:
            if perf_path.exists():
                perf_status = json.loads(perf_path.read_text(encoding="utf-8")).get("status", "NA")
            if drift_path.exists():
                drift_status = json.loads(drift_path.read_text(encoding="utf-8")).get("status", "NA")
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
        max_positions=int(args.max_positions),
        risk_per_trade_pct=float(args.risk_per_trade_pct),
        rr=float(args.rr),
        mode=args.mode,
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
        shadow_simulation_enabled=(False if bool(getattr(args, "no_shadow_simulation", False)) else bool(getattr(Config, "PAPER_SHADOW_SIMULATION_ENABLED", True))),
        paper_unlock_profile=str(getattr(args, "paper_unlock_profile", "") or getattr(Config, "PAPER_UNLOCK_PROFILE", "BTC_ONLY_40_Q60")),
        paper_unlock_allowed_symbols=[x.strip() for x in str(getattr(Config, "PAPER_UNLOCK_ALLOWED_SYMBOLS", "BTC/USDT")).replace(";", ",").split(",") if x.strip()],
        paper_unlock_min_ai_prob=float(getattr(Config, "PAPER_UNLOCK_MIN_AI_PROB", 40.0)),
        paper_unlock_min_setup_quality=float(getattr(Config, "PAPER_UNLOCK_MIN_SETUP_QUALITY", 60.0)),
        paper_unlock_max_positions=int(getattr(Config, "PAPER_UNLOCK_MAX_POSITIONS", 1)),
        paper_unlock_live_block=bool(getattr(Config, "PAPER_UNLOCK_LIVE_BLOCK", True)),
    )
