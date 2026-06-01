import asyncio
import contextlib

try:
    from .aiohttp_compat import install_aiohttp_windows_ssl_context_compat
except Exception:  # pragma: no cover - script-style fallback
    from aiohttp_compat import install_aiohttp_windows_ssl_context_compat  # type: ignore

install_aiohttp_windows_ssl_context_compat()

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
            raw = await exchange.fetch_ohlcv(
                self.symbol, self.timeframe, limit=self.limit
            )
        finally:
            # Prompt 29.1: always attempt to close ccxt/aiohttp resources, even
            # when the surrounding task is being cancelled by CTRL+C.
            close_task = asyncio.create_task(exchange.close())
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.shield(close_task)
        return self._to_dataframe(raw)

    def _to_dataframe(self, raw: list) -> pd.DataFrame:
        """Converte la lista OHLCV in DataFrame indicizzato per datetime UTC."""
        df = pd.DataFrame(raw, columns=["timestamp"] + self.COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df.index.name = "datetime"
        df = df.astype(float)
        df.sort_index(inplace=True)
        return df
