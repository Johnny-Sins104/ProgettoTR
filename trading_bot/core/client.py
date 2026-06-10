import asyncio
import contextlib

try:
    from .aiohttp_compat import install_aiohttp_windows_ssl_context_compat
except Exception:  # pragma: no cover - script-style fallback
    from aiohttp_compat import install_aiohttp_windows_ssl_context_compat  # type: ignore

install_aiohttp_windows_ssl_context_compat()

import aiohttp
import ccxt
import ccxt.async_support as ccxt_async
import pandas as pd
from typing import Optional


class ExchangeClient:
    """Scarica candele OHLCV da un exchange via ccxt (sync o async)."""

    COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

    def __init__(
        self,
        exchange_id: str = "binance",
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        limit: int = 500,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ):
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.limit = limit
        self._credentials = {"apiKey": api_key, "secret": api_secret}

    def fetch(self) -> pd.DataFrame:
        """Fetch sincrono."""
        exchange: ccxt.Exchange = getattr(ccxt, self.exchange_id)(self._credentials)
        raw = exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=self.limit)
        return self._to_dataframe(raw)

    async def fetch_async(self) -> pd.DataFrame:
        """Fetch asincrono."""
        exchange: ccxt_async.Exchange = getattr(ccxt_async, self.exchange_id)(
            self._credentials
        )
        try:
            try:
                raw = await exchange.fetch_ohlcv(
                    self.symbol, self.timeframe, limit=self.limit
                )
            except Exception:
                raw = await self._fetch_binance_public_ohlcv_fallback()
        finally:
            # Prompt 29.1: always attempt to close ccxt/aiohttp resources, even
            # when the surrounding task is being cancelled by CTRL+C.
            close_task = asyncio.create_task(exchange.close())
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.shield(close_task)
        return self._to_dataframe(raw)

    async def _fetch_binance_public_ohlcv_fallback(self) -> list:
        """Fetch public Binance candles directly when ccxt transport fails.

        This keeps paper-live market data usable in the bundled Windows runtime
        without touching private/exchange trading endpoints.
        """
        exchange_id = str(self.exchange_id or "").lower()
        if exchange_id not in {"binance", "binanceusdm"}:
            raise RuntimeError(f"binance_public_fallback_unsupported_exchange:{self.exchange_id}")
        symbol = str(self.symbol or "").replace("/", "").replace(":", "").upper()
        if not symbol:
            raise ValueError("symbol_missing_for_binance_public_fallback")
        interval = str(self.timeframe or "5m")
        limit = max(1, min(int(self.limit or 500), 1000))
        if exchange_id == "binanceusdm":
            url = "https://fapi.binance.com/fapi/v1/klines"
        else:
            url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": symbol, "interval": interval, "limit": str(limit)}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"binance_public_ohlcv_failed:{resp.status}:{text[:200]}")
                rows = await resp.json()
        out = []
        for row in rows:
            out.append([
                int(row[0]),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            ])
        if not out:
            raise RuntimeError("binance_public_ohlcv_empty")
        return out

    def _to_dataframe(self, raw: list) -> pd.DataFrame:
        """Converte la lista OHLCV in DataFrame indicizzato per datetime UTC."""
        df = pd.DataFrame(raw, columns=["timestamp"] + self.COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df.index.name = "datetime"
        df = df.astype(float)
        df.sort_index(inplace=True)
        return df
