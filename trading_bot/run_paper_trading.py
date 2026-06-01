from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_engine import PaperTradingEngine, settings_from_args
from core.paper_once_runner_footer import print_runner_once_footer_from_events, read_latest_cycle_completed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ProgettoTR Prompt 29 paper trading engine")
    parser.add_argument("--mode", choices=["paper"], default="paper", help="Prompt 29 is paper-only; live real-money execution is disabled.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to PAPER_ASSET_UNIVERSE.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--cost-model", choices=["base", "conservative", "severe"], default="conservative")
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true", help="Run one evaluation cycle then exit. Useful for smoke tests.")
    parser.add_argument("--max-cycles", type=int, default=None, help="Stop paper mode after N completed cycles. Default 0 runs until interrupted; --once still takes precedence.")
    parser.add_argument("--market-data-mode", choices=["live", "auto", "cache", "replay"], default=None, help="Paper market data source. live uses the exchange, auto falls back to local replay cache, cache uses the latest local cache window, replay advances through local cached candles.")
    parser.add_argument("--market-data-cache-dir", default=None, help="Directory containing local OHLCV parquet caches for cache/replay paper data.")
    parser.add_argument("--market-data-replay-step", type=int, default=None, help="Number of cached candles to advance per paper cycle in replay/auto fallback mode.")
    parser.add_argument("--market-data-replay-start-offset", type=int, default=None, help="Initial cached candle end-offset for replay/auto fallback mode. Default starts at PAPER_CANDLE_LIMIT.")
    parser.set_defaults(cycle_artifacts=None)
    parser.add_argument("--cycle-artifacts", dest="cycle_artifacts", action="store_true", help="Generate full paper diagnostic/performance artifacts after each cycle.")
    parser.add_argument("--no-cycle-artifacts", dest="cycle_artifacts", action="store_false", help="Skip heavy per-cycle artifacts; useful for continuous paper/replay drills.")
    parser.add_argument("--max-positions", type=int, default=3)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    parser.add_argument("--rr", type=float, default=2.0)
    parser.add_argument("--console-verbose", action="store_true", default=None, help="Print detailed per-cycle diagnostics in the operator console.")
    parser.add_argument("--verbose-ai", action="store_true", default=None, help="Re-enable AI_HYBRID debug prints that are suppressed by default in paper operations.")
    parser.set_defaults(telegram_proactive=None)
    parser.add_argument("--telegram-proactive", dest="telegram_proactive", action="store_true", help="Enable proactive Telegram paper monitoring notifications.")
    parser.add_argument("--no-telegram-proactive", dest="telegram_proactive", action="store_false", help="Disable proactive Telegram notifications for this run.")
    parser.add_argument("--no-signal-diagnostics", action="store_true", help="Disable paper signal-density diagnostics for this run.")
    parser.add_argument("--no-signal-diagnostics-backfill", action="store_true", help="Disable historical NO_SIGNAL diagnostics backfill for this run.")
    parser.add_argument("--no-shadow-simulation", action="store_true", help="Disable paper shadow threshold simulation for this run.")
    parser.add_argument("--no-unlock-rejection-analysis", action="store_true", help="Disable Prompt 29.4.4a unlock rejection report generation for this run.")
    parser.add_argument("--no-crypto-scenario", action="store_true", help="Disable Prompt 29.5.0a crypto intraday scenario diagnostics for this run.")
    parser.add_argument("--no-candlestick-patterns", action="store_true", help="Disable Prompt 29.5.0b candlestick pattern diagnostics for this run.")
    parser.add_argument("--no-pattern-conditioned-shadow", action="store_true", help="Disable Prompt 29.5.0c pattern-conditioned shadow/backtest review for this run.")
    parser.add_argument("--no-scenario-pattern-calibration", action="store_true", help="Disable Prompt 29.5.0d scenario-pattern calibration report generation for this run.")
    parser.add_argument("--no-market-structure-map", action="store_true", help="Disable Prompt 29.5.0e liquidity/supply-demand/structure map diagnostics for this run.")
    parser.add_argument("--no-calibrated-structure-shadow", action="store_true", help="Disable Prompt 29.5.0f calibrated scenario-pattern-structure shadow review for this run.")
    parser.add_argument("--no-structure-filter-diagnostics", action="store_true", help="Disable Prompt 29.5.0g structure filter diagnostics / confirmation quality audit for this run.")
    parser.add_argument("--no-structure-context-repair", action="store_true", help="Disable Prompt 29.5.0h strict structure context repair / confirmation relabeling for this run.")
    parser.add_argument("--no-repaired-structure-shadow-validation", action="store_true", help="Disable Prompt 29.5.0i repaired structure shadow validation / MAP_SCORE_65_79 and BOS audit for this run.")
    parser.add_argument("--no-independent-repaired-validation", action="store_true", help="Disable Prompt 29.5.0j independent repaired validation stability / walk-forward guard for this run.")
    parser.add_argument("--no-paper-unlock-profile-refinement", action="store_true", help="Disable Prompt 29.4.4c paper unlock profile refinement design for this run.")
    parser.add_argument("--no-paper-unlock-experiment-design", action="store_true", help="Disable Prompt 29.4.4d calibrated paper-only unlock experiment design for this run.")
    parser.add_argument("--no-paper-unlock-shadow-dry-run", action="store_true", help="Disable Prompt 29.4.4e paper-only shadow experiment dry-run harness for this run.")
    parser.add_argument("--no-paper-unlock-shadow-rate-calibration", action="store_true", help="Disable Prompt 29.4.4f shadow dry-run sample expansion / rate-limit calibration for this run.")
    parser.add_argument("--no-paper-unlock-bounded-cadence", action="store_true", help="Disable Prompt 29.4.4g bounded cadence expansion / rolling shadow collection for this run.")
    parser.add_argument("--no-paper-unlock-shadow-stability-review", action="store_true", help="Disable Prompt 29.4.4h shadow sample stability review for this run.")
    parser.add_argument("--no-paper-unlock-activation-draft", action="store_true", help="Disable Prompt 29.4.4i guarded paper-only activation draft for this run.")
    parser.add_argument("--no-paper-unlock-experiment-switch-draft", action="store_true", help="Disable Prompt 29.4.4j guarded paper-only experiment switch implementation draft for this run.")
    parser.add_argument("--no-paper-unlock-manual-switch-preflight", action="store_true", help="Disable Prompt 29.4.4k manual paper-only switch dry-run / fail-closed preflight for this run.")
    parser.add_argument("--no-paper-unlock-manual-activation-patch", action="store_true", help="Disable Prompt 29.4.4l explicit manual paper-only activation patch draft for this run.")
    parser.add_argument("--no-paper-unlock-final-enable-preflight", action="store_true", help="Disable Prompt 29.4.4m final manual paper-only enable preflight for this run.")
    parser.add_argument("--no-paper-unlock-guarded-enable", action="store_true", help="Disable Prompt 29.4.4n guarded paper-only enable implementation for this run.")
    parser.add_argument("--no-paper-unlock-runtime-audit", action="store_true", help="Disable Prompt 29.4.4o runtime paper-order audit for this run.")
    parser.add_argument("--no-paper-unlock-routing-bridge", action="store_true", help="Disable Prompt 29.4.4p guarded paper-only routing bridge audit for this run.")
    parser.add_argument("--no-paper-unlock-candidate-audit", action="store_true", help="Disable Prompt 29.4.4q first guarded paper-order candidate audit for this run.")
    parser.add_argument("--no-paper-unlock-handoff-dry-run", action="store_true", help="Disable Prompt 29.4.4r paper order handoff dry-run audit for this run.")
    parser.add_argument("--paper-unlock-supervised-execution", action="store_true", help="Operator-enable Prompt 29.4.4s supervised paper-only execution. Requires --paper-unlock-supervised-confirm.")
    parser.add_argument("--paper-unlock-supervised-confirm", default="", help="Required confirmation phrase for 29.4.4s: I_UNDERSTAND_PAPER_ONLY.")
    parser.add_argument("--no-paper-unlock-supervised-execution", action="store_true", help="Disable Prompt 29.4.4s supervised paper-only execution audit for this run.")
    parser.add_argument("--no-paper-order-leakage-guard", action="store_true", help="Disable Prompt 29.4.4r-1 legacy paper order leakage guard for this run.")
    parser.add_argument("--no-lsr-v2-paper-supervised-bridge", action="store_true", help="Disable Prompt 29.4.4s-10b LSR-v2 paper-supervised bridge runtime audit for this run.")
    parser.add_argument("--no-lsr-v2-engine-read-only-artifact-hook", action="store_true", help="Disable Prompt 29.4.4t-1 read-only LSR-v2 dashboard/lifecycle artifact hook for this run.")
    parser.add_argument("--lsr-v2-bridge-operator-enable", action="store_true", help="Operator-enable LSR-v2 bridge routing diagnostics only; submission remains fail-closed.")
    parser.add_argument("--lsr-v2-bridge-confirm", default="", help="Optional diagnostic confirmation phrase: I_UNDERSTAND_LSR_V2_PAPER_SUPERVISED_ONLY.")
    parser.set_defaults(paper_unlock=None)
    parser.add_argument("--paper-unlock", dest="paper_unlock", action="store_true", help="Enable Prompt 29.4.4 paper-only unlock gate for this run.")
    parser.add_argument("--no-paper-unlock", dest="paper_unlock", action="store_false", help="Disable Prompt 29.4.4 paper-only unlock gate for this run.")
    parser.add_argument("--paper-unlock-profile", default="", help="Paper unlock profile. Supported initial profile: BTC_ONLY_40_Q60.")
    return parser


async def async_main(engine: PaperTradingEngine) -> None:
    await engine.run()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "y"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _exit_process(code: int) -> None:
    if _env_bool("PAPER_ONCE_FORCE_OS_EXIT", False):
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(code)
    raise SystemExit(code)


def _start_once_footer_watchdog(
    *,
    enabled: bool,
    started_at: datetime,
    events_path: Path,
    engine_ref: dict[str, Any],
) -> threading.Thread | None:
    """Hardens Windows --once runs where engine finalization can hang after CYCLE_COMPLETED.

    Prompt 29.4.4o-3c is deliberately console/output only. The watchdog does not
    touch gates, risk, routing, broker state, orders, or positions. It only watches
    for a completed cycle already written to paper_events.jsonl, prints the same
    runner fallback footer, then exits the one-shot process if the engine remains
    alive past a small grace window.
    """
    if not enabled:
        return None
    if not _env_bool("PAPER_ONCE_HARD_EXIT_AFTER_COMPLETED", True):
        return None

    poll_seconds = max(0.1, _env_float("PAPER_ONCE_WATCHDOG_POLL_SECONDS", 0.25))
    grace_seconds = max(0.0, _env_float("PAPER_ONCE_HARD_EXIT_GRACE_SECONDS", 3.0))
    timeout_seconds = max(grace_seconds + 1.0, _env_float("PAPER_ONCE_WATCHDOG_TIMEOUT_SECONDS", 300.0))

    def _engine_footer_printed() -> bool:
        engine = engine_ref.get("engine")
        return bool(getattr(engine, "paper_once_console_summary_printed", False)) if engine is not None else False

    def _watch() -> None:
        deadline = time.monotonic() + timeout_seconds
        cycle_seen_at: float | None = None
        cycle_id = ""
        notice_printed = False
        while time.monotonic() < deadline:
            footer_printed = _engine_footer_printed()
            cycle_event = read_latest_cycle_completed(events_path, started_at=started_at)
            if cycle_event:
                if cycle_seen_at is None:
                    cycle_seen_at = time.monotonic()
                    cycle_id = str(cycle_event.get("cycle_id") or "")
                if not notice_printed:
                    print(
                        f"[PAPER ONCE WATCHDOG] cycle_completed_detected=true cycle_id={cycle_id} "
                        f"hard_exit_grace_seconds={grace_seconds:.2f}",
                        flush=True,
                    )
                    notice_printed = True
                if time.monotonic() - cycle_seen_at >= grace_seconds:
                    if not footer_printed and _env_bool("PAPER_ONCE_WATCHDOG_PRINT_FOOTER", False):
                        print_runner_once_footer_from_events(
                            events_path,
                            started_at=started_at,
                            stream=sys.stdout,
                            force=True,
                        )
                    print(
                        f"[PAPER ONCE EXIT] reason=cycle_completed_watchdog_hard_exit cycle_id={cycle_id}",
                        flush=True,
                    )
                    try:
                        sys.stdout.flush()
                        sys.stderr.flush()
                    except Exception:
                        pass
                    os._exit(0)
            time.sleep(poll_seconds)

    thread = threading.Thread(target=_watch, name="paper_once_footer_watchdog", daemon=True)
    thread.start()
    return thread


def main() -> None:
    args = build_parser().parse_args()
    started_at = datetime.now(timezone.utc)
    interrupted = False
    engine = None
    events_path = Path(args.data_dir if hasattr(args, "data_dir") else "data") / "paper_events.jsonl"
    engine_ref: dict[str, Any] = {}
    _start_once_footer_watchdog(
        enabled=bool(args.once),
        started_at=started_at,
        events_path=events_path,
        engine_ref=engine_ref,
    )

    try:
        engine = PaperTradingEngine(settings_from_args(args))
        engine_ref["engine"] = engine
        asyncio.run(async_main(engine))
    except KeyboardInterrupt:
        interrupted = True
    finally:
        if args.once:
            already_printed = False
            if engine is not None:
                already_printed = bool(getattr(engine, "paper_once_console_summary_printed", False))

            printed = False
            if not already_printed:
                printed = print_runner_once_footer_from_events(
                    events_path,
                    started_at=started_at,
                    stream=sys.stdout,
                )

            if interrupted and not printed and not already_printed:
                print("[PAPER ONCE INTERRUPTED]", flush=True)
                print("reason=keyboard_interrupt_before_cycle_completed", flush=True)

    _exit_process(130 if interrupted else 0)


if __name__ == "__main__":
    main()
