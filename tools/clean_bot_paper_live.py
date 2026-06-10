from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.clean_bot.paper_live import (
    CleanPaperSettings,
    format_cycle,
    run_cycle,
    run_loop,
    send_telegram_cycle,
    send_telegram_test,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run clean bot spot-style paper live.")
    parser.add_argument("--symbol", default="XRP/USDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--market-data-mode", choices=["auto", "live", "cache"], default="auto")
    parser.add_argument("--balance", type=float, default=100.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.005)
    parser.add_argument("--cost-model", choices=["base", "conservative", "severe"], default="conservative")
    parser.add_argument("--profile", choices=["active", "aggressive", "conservative"], default="active")
    parser.add_argument("--candle-limit", type=int, default=1500)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--telegram", action="store_true")
    parser.add_argument("--telegram-test", action="store_true", help="Send one Telegram test message and exit.")
    parser.add_argument("--telegram-every-cycle", action="store_true", help="Send every cycle summary to Telegram.")
    args = parser.parse_args()
    settings = CleanPaperSettings(
        symbol=args.symbol,
        timeframe=args.timeframe,
        data_dir=args.data_dir,
        market_data_mode=args.market_data_mode,
        balance=args.balance,
        risk_per_trade_pct=args.risk_per_trade_pct,
        cost_model=args.cost_model,
        profile=args.profile,
        candle_limit=args.candle_limit,
        poll_seconds=args.poll_seconds,
        max_cycles=1 if args.once else args.max_cycles,
        telegram_enabled=bool(args.telegram or args.telegram_test),
        telegram_notify_every_cycle=bool(args.telegram and (args.telegram_every_cycle or args.once)),
    )
    if args.telegram_test:
        result = send_telegram_test(settings)
        print(f"TELEGRAM_TEST ok={result.get('ok')} reason={result.get('reason', '')} status={result.get('status', '')}")
        if result.get("body"):
            print(f"telegram_body={result.get('body')}")
        if result.get("error"):
            print(f"telegram_error={result.get('error')}")
        return 0 if result.get("ok") else 2
    if args.once:
        report = run_cycle(settings)
        print(format_cycle(report))
        if settings.telegram_notify_every_cycle:
            result = send_telegram_cycle(settings, report)
            print(f"TELEGRAM_CYCLE ok={result.get('ok')} reason={result.get('reason', '')} status={result.get('status', '')}")
        return 0
    run_loop(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
