from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trading_bot.clean_bot.data import cache_path

try:
    from trading_bot.core.aiohttp_compat import install_aiohttp_windows_ssl_context_compat

    install_aiohttp_windows_ssl_context_compat()
except Exception:
    pass

import aiohttp


INTERVAL_MS = {
    "1m": 60_000,
}

DEFAULT_ENDPOINTS = [
    ("binance_spot", "https://api.binance.com/api/v3/klines"),
    ("binance_spot_api1", "https://api1.binance.com/api/v3/klines"),
    ("binance_us_spot", "https://api.binance.us/api/v3/klines"),
]


def _binance_symbol(symbol: str) -> str:
    return str(symbol or "").replace("/", "").replace(":", "").upper()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dt_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


async def _fetch_chunk(
    session: aiohttp.ClientSession,
    *,
    endpoint: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> list[list[Any]]:
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": "1000",
        "startTime": str(start_ms),
        "endTime": str(end_ms),
    }
    async with session.get(endpoint, params=params, timeout=20) as resp:
        text = await resp.text()
        if resp.status >= 400:
            raise RuntimeError(f"binance_klines_failed:{resp.status}:{text[:240]}")
        rows = await resp.json()
    if not isinstance(rows, list):
        raise RuntimeError(f"binance_klines_unexpected_payload:{str(rows)[:240]}")
    return rows


async def _download_from_endpoint(
    *,
    endpoint: str,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    pause_seconds: float,
) -> list[list[Any]]:
    interval_ms = INTERVAL_MS[interval]
    out: list[list[Any]] = []
    current_ms = start_ms
    async with aiohttp.ClientSession() as session:
        while current_ms < end_ms:
            rows = await _fetch_chunk(
                session,
                endpoint=endpoint,
                symbol=symbol,
                interval=interval,
                start_ms=current_ms,
                end_ms=end_ms,
            )
            if not rows:
                break
            out.extend(rows)
            last_open_ms = int(rows[-1][0])
            next_ms = last_open_ms + interval_ms
            if next_ms <= current_ms:
                break
            current_ms = next_ms
            if pause_seconds > 0:
                await asyncio.sleep(pause_seconds)
    return out


async def download_klines(
    *,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    pause_seconds: float,
    endpoint_name: str | None = None,
) -> tuple[str, list[list[Any]]]:
    binance_symbol = _binance_symbol(symbol)
    endpoints = DEFAULT_ENDPOINTS
    if endpoint_name:
        endpoints = [item for item in DEFAULT_ENDPOINTS if item[0] == endpoint_name or item[1] == endpoint_name]
        if not endpoints:
            endpoints = [(endpoint_name, endpoint_name)]
    errors: list[str] = []
    for name, endpoint in endpoints:
        try:
            rows = await _download_from_endpoint(
                endpoint=endpoint,
                symbol=binance_symbol,
                interval=interval,
                start_ms=_dt_ms(start),
                end_ms=_dt_ms(end),
                pause_seconds=pause_seconds,
            )
            if rows:
                return name, rows
            errors.append(f"{name}:empty")
        except Exception as exc:
            errors.append(f"{name}:{exc}")
    raise RuntimeError("all_binance_public_endpoints_failed:" + " | ".join(errors))


def _rows_to_frame(rows: list[list[Any]], *, include_open_bar: bool, now_ms: int) -> pd.DataFrame:
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if len(row) < 7:
            continue
        close_time_ms = int(row[6])
        if not include_open_bar and close_time_ms >= now_ms:
            continue
        parsed.append(
            {
                "datetime": pd.to_datetime(int(row[0]), unit="ms", utc=True),
                "Open": float(row[1]),
                "High": float(row[2]),
                "Low": float(row[3]),
                "Close": float(row[4]),
                "Volume": float(row[5]),
            }
        )
    if not parsed:
        return pd.DataFrame(columns=["datetime", "Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(parsed)
    return df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)


def _merge_existing(path: Path, fresh: pd.DataFrame, *, replace: bool) -> pd.DataFrame:
    if replace or not path.exists():
        return fresh
    existing = pd.read_parquet(path)
    merged = pd.concat([existing, fresh], ignore_index=True)
    merged["datetime"] = pd.to_datetime(merged["datetime"], utc=True)
    return merged.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)


def _format_report(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "CLEAN BOT 1M DOWNLOAD",
            f"symbol={report['symbol']} timeframe={report['timeframe']} provider={report['provider']}",
            f"start={report['start']} end={report['end']}",
            f"rows_downloaded={report['rows_downloaded']} rows_saved={report['rows_saved']}",
            f"output={report['output']}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Download public Binance 1m OHLCV into the clean bot cache.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--symbol", default="XRP/USDT")
    parser.add_argument("--timeframe", choices=["1m"], default="1m")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--report-output", default="data/clean_bot_download_1m_report.json")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--include-open-bar", action="store_true")
    parser.add_argument("--pause-seconds", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    end = _parse_dt(args.end) or now
    start = _parse_dt(args.start) or (end - timedelta(days=max(1, args.days)))
    if start >= end:
        raise SystemExit("start must be before end")

    output = Path(args.output) if args.output else cache_path(Path(args.data_dir), args.symbol, args.timeframe)
    output.parent.mkdir(parents=True, exist_ok=True)

    provider, rows = asyncio.run(
        download_klines(
            symbol=args.symbol,
            interval=args.timeframe,
            start=start,
            end=end,
            pause_seconds=max(0.0, args.pause_seconds),
            endpoint_name=args.endpoint or None,
        )
    )
    fresh = _rows_to_frame(rows, include_open_bar=args.include_open_bar, now_ms=_dt_ms(now))
    if fresh.empty:
        raise SystemExit("No closed 1m bars downloaded.")
    saved = _merge_existing(output, fresh, replace=args.replace)
    saved.to_parquet(output, index=False)

    report = {
        "report_type": "clean_bot_1m_download",
        "diagnostic_only": True,
        "opens_orders": False,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "provider": provider,
        "start": str(saved["datetime"].iloc[0]),
        "end": str(saved["datetime"].iloc[-1]),
        "rows_downloaded": int(len(fresh)),
        "rows_saved": int(len(saved)),
        "output": str(output),
    }
    report_path = Path(args.report_output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_format_report(report))
        print(f"report={args.report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
