from __future__ import annotations

import argparse
import asyncio
import os
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.paper_engine import PaperTradingEngine, settings_from_args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ProgettoTR Prompt 29 paper trading engine")
    parser.add_argument("--mode", choices=["paper"], default="paper", help="Prompt 29 is paper-only; live real-money execution is disabled.")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols. Defaults to PAPER_ASSET_UNIVERSE.")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--cost-model", choices=["base", "conservative", "severe"], default="conservative")
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true", help="Run one evaluation cycle then exit. Useful for smoke tests.")
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
    parser.set_defaults(paper_unlock=None)
    parser.add_argument("--paper-unlock", dest="paper_unlock", action="store_true", help="Enable Prompt 29.4.4 paper-only unlock gate for this run.")
    parser.add_argument("--no-paper-unlock", dest="paper_unlock", action="store_false", help="Disable Prompt 29.4.4 paper-only unlock gate for this run.")
    parser.add_argument("--paper-unlock-profile", default="", help="Paper unlock profile. Supported initial profile: BTC_ONLY_40_Q60.")
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    engine = PaperTradingEngine(settings_from_args(args))
    await engine.run()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        # PaperTradingEngine.run() performs the audit logging in its cancellation
        # path.  Suppress the default traceback so operator shutdown is clean.
        pass


if __name__ == "__main__":
    main()
