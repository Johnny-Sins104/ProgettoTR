import argparse
import asyncio
import os
import sys
from pathlib import Path

# Assicuriamoci che l'encoding in output supporti UTF-8 su Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

TRADING_BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TRADING_BOT_DIR.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(TRADING_BOT_DIR))

from config import Config
from core.historical_cache import download_ohlcv_cache
from core.timeframe_profile import equivalent_rows_from_baseline_rows, rows_for_days, normalize_timeframe


def main():
    parser = argparse.ArgumentParser(description="Download paginato OHLCV in cache Parquet")
    parser.add_argument("--candles", type=int, default=10000, help="Numero di candele da scaricare")
    parser.add_argument("--symbol", type=str, default=Config.SYMBOL, help="Simbolo, es. BTC/USDT")
    parser.add_argument("--timeframe", type=str, default=Config.TIMEFRAME, help="Timeframe: 15m, 5m o 3m")
    parser.add_argument("--days", type=float, default=None, help="Scarica una durata temporale invece di un numero fisso di candele")
    parser.add_argument("--equivalent-15m-candles", action="store_true", help="Interpreta --candles come profondità 15m equivalente")
    parser.add_argument("--exchange", type=str, default=Config.EXCHANGE_ID, help="Exchange ccxt, es. binanceusdm")
    parser.add_argument("--data-dir", type=str, default="data", help="Directory cache")
    args = parser.parse_args()

    timeframe = normalize_timeframe(args.timeframe)
    requested_rows = int(args.candles)
    if args.days is not None:
        requested_rows = rows_for_days(float(args.days), timeframe)
    elif args.equivalent_15m_candles:
        requested_rows = equivalent_rows_from_baseline_rows(int(args.candles), baseline_timeframe="15m", target_timeframe=timeframe)

    print(
        f"🤖 Inizio download di {requested_rows} candele "
        f"{timeframe} per {args.symbol} da {args.exchange}..."
    )
    candidate = asyncio.run(
        download_ohlcv_cache(
            requested_rows=int(requested_rows),
            exchange_id=args.exchange,
            symbol=args.symbol,
            timeframe=timeframe,
            data_dir=args.data_dir,
            rate_limit_seconds=float(getattr(Config, "BACKTEST_HISTORY_RATE_LIMIT_SECONDS", 0.25)),
        )
    )
    print(f"✅ Download completato: {candidate.path} ({candidate.rows} candele).")


if __name__ == "__main__":
    main()
