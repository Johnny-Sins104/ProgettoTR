"""market_feed_ws.py — Closed-candle WebSocket feed using public Binance market data.

TR-INT-03 (Fase 3).

Design constraints:
- FEED_ENABLED = False by default; no network connection is made at import time.
- Only closed candles (k["x"] == True) are dispatched to the callback.
- Deduplication is enforced via close-timestamp watermarks in explicit FeedState.
- Reconnect uses exponential backoff; zombie connections are detected at 90 s.
- Multi-timeframe watermark state is carried in FeedState — no module-level globals.
- No private API keys, no order/trade/submit methods.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Public Binance endpoints (no auth required) ───────────────────────────────
_WS_BASE = "wss://stream.binance.com:9443/stream"
_REST_BASE = "https://api.binance.com/api/v3/klines"

# ── Module-level toggle — must be True before calling run() ──────────────────
FEED_ENABLED: bool = False


@dataclass
class FeedState:
    """All mutable feed state. Always passed explicitly; never stored as a module global."""

    watermarks: dict[str, int] = field(default_factory=dict)
    buffers: dict[str, list] = field(default_factory=dict)
    connected_at: str | None = None
    reconnect_count: int = 0
    last_error: str | None = None


class MarketFeedWS:
    """Public Binance WebSocket feed delivering only closed candles.

    No order, submit, trade, or exchange-mutation methods exist on this class.
    """

    ZOMBIE_TIMEOUT_SEC: int = 90
    RECONNECT_BASE_DELAY: float = 1.0
    RECONNECT_MAX_DELAY: float = 60.0
    # A connection is considered stable only after this many consecutive
    # successful recv() calls.  One frame then a drop is not stable.
    STABLE_MIN_FRAMES: int = 5

    def __init__(self, symbol: str, timeframes: list[str]) -> None:
        self._symbol = symbol.upper().replace("/", "")
        self._timeframes = list(timeframes)
        self._state = FeedState(
            watermarks={tf: 0 for tf in self._timeframes},
            buffers={tf: [] for tf in self._timeframes},
        )

    # ── Health metrics (read-only view of internal state) ─────────────────────

    @property
    def health(self) -> dict[str, Any]:
        return {
            "connected_at": self._state.connected_at,
            "reconnect_count": self._state.reconnect_count,
            "last_error": self._state.last_error,
        }

    # ── Watermark / deduplication ─────────────────────────────────────────────

    def _is_duplicate(self, timeframe: str, close_ts: int) -> bool:
        return close_ts <= self._state.watermarks.get(timeframe, 0)

    def _update_watermark(self, timeframe: str, close_ts: int) -> None:
        self._state.watermarks[timeframe] = close_ts

    def sync_5m_watermark(self, candles_5m: list[dict], state: FeedState) -> None:
        """Add 5m candles to state.buffers['5m'] for all candles closed on or before
        state.watermarks['1m'].

        Operates entirely on the supplied *state* argument — no module globals are
        read or written.  Idempotent: candles already in watermarks['5m'] are skipped.
        """
        ref_ts = state.watermarks.get("1m", 0)
        current_wm = state.watermarks.get("5m", 0)
        for c in candles_5m:
            close_ts = int(c["T"])
            if close_ts <= ref_ts and close_ts > current_wm:
                state.buffers.setdefault("5m", []).append(c)
                current_wm = close_ts
        state.watermarks["5m"] = current_wm

    # ── Message parsing ────────────────────────────────────────────────────────

    @staticmethod
    def _parse_candle(k: dict) -> dict[str, Any]:
        return {
            "t": int(k["t"]),
            "T": int(k["T"]),
            "o": float(k["o"]),
            "h": float(k["h"]),
            "l": float(k["l"]),
            "c": float(k["c"]),
            "v": float(k["v"]),
        }

    def _process_closed_candle(
        self, timeframe: str, k: dict, callback: Callable[[str, dict], None]
    ) -> None:
        """Dispatch one closed kline dict; idempotent via watermark."""
        close_ts = int(k["T"])
        if self._is_duplicate(timeframe, close_ts):
            return
        candle = self._parse_candle(k)
        self._state.buffers.setdefault(timeframe, []).append(candle)
        self._update_watermark(timeframe, close_ts)
        callback(timeframe, candle)

    def handle_message(
        self, raw_msg: str, callback: Callable[[str, dict], None]
    ) -> None:
        """Parse one raw WebSocket message and dispatch closed candles only.

        Open candles (k['x'] == False) are silently ignored.
        """
        try:
            data = json.loads(raw_msg)
        except (json.JSONDecodeError, ValueError):
            return
        stream_data = data.get("data", data)
        if not isinstance(stream_data, dict):
            return
        k = stream_data.get("k")
        if k is None:
            return
        if not k.get("x"):  # open candle — skip
            return
        tf = k.get("i")
        if tf not in self._timeframes:
            return
        self._process_closed_candle(tf, k, callback)

    # ── Exponential backoff ───────────────────────────────────────────────────

    def _backoff_delay(self, attempt: int) -> float:
        """Return the reconnect delay for `attempt` (0-based), capped at MAX."""
        return min(
            self.RECONNECT_MAX_DELAY,
            self.RECONNECT_BASE_DELAY * (2 ** attempt),
        )

    # ── REST bootstrap ────────────────────────────────────────────────────────

    async def _bootstrap_rest(
        self,
        limits: dict[str, int] | None = None,
        *,
        _http_get: Callable | None = None,
    ) -> None:
        """Pre-load closed historical candles from public REST before WS connects.

        The last row from Binance REST may still be open; it is dropped so that
        only confirmed closed candles enter the buffer.
        """
        import aiohttp  # import here: no network at module import time

        effective_limits = limits or {"1m": 200, "5m": 200}

        async def _default_get(url: str) -> list:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    resp.raise_for_status()
                    return await resp.json()

        fetch = _http_get or _default_get

        for tf in self._timeframes:
            limit = effective_limits.get(tf, 200)
            url = (
                f"{_REST_BASE}?symbol={self._symbol}"
                f"&interval={tf}&limit={limit + 1}"
            )
            try:
                rows = await fetch(url)
                # Drop the last row (potentially open)
                closed_rows = rows[:-1] if len(rows) > 1 else []
                loaded = 0
                for row in closed_rows:
                    close_ts = int(row[6])
                    if not self._is_duplicate(tf, close_ts):
                        candle = {
                            "t": int(row[0]),
                            "T": close_ts,
                            "o": float(row[1]),
                            "h": float(row[2]),
                            "l": float(row[3]),
                            "c": float(row[4]),
                            "v": float(row[5]),
                        }
                        self._state.buffers.setdefault(tf, []).append(candle)
                        self._update_watermark(tf, close_ts)
                        loaded += 1
                logger.info("Bootstrap REST %s: %d closed candles loaded", tf, loaded)
            except Exception as exc:
                self._state.last_error = f"bootstrap_rest_{tf}: {exc}"
                logger.warning("Bootstrap REST %s failed: %s", tf, exc)
                raise RuntimeError(f"Bootstrap REST {tf} failed: {exc}") from exc

    # ── Main feed loop ────────────────────────────────────────────────────────

    async def run(
        self,
        callback: Callable[[str, dict], None],
        *,
        bootstrap: bool = True,
        rest_limits: dict[str, int] | None = None,
        _ws_connect: Any = None,
        _http_get: Callable | None = None,
    ) -> None:
        """Start the WebSocket feed loop.  Blocks until cancelled.

        Raises RuntimeError immediately if FEED_ENABLED is False.

        Parameters
        ----------
        callback:
            Called as ``callback(timeframe: str, candle: dict)`` for every new
            closed candle.  Must not block.
        bootstrap:
            If True, load historical closed candles via REST before connecting.
        rest_limits:
            Number of historical candles to request per timeframe.
        _ws_connect / _http_get:
            Dependency-injection hooks for unit tests.  Do not use in production.
        """
        if not FEED_ENABLED:
            raise RuntimeError(
                "FEED_ENABLED is False — set market_feed_ws.FEED_ENABLED = True "
                "before calling run()."
            )

        import websockets as _ws_lib  # import here: no network at module import time

        connect = _ws_connect or _ws_lib.connect
        streams = "/".join(
            f"{self._symbol.lower()}@kline_{tf}" for tf in self._timeframes
        )
        ws_url = f"{_WS_BASE}?streams={streams}"

        if bootstrap:
            await self._bootstrap_rest(rest_limits, _http_get=_http_get)

        attempt = 0
        while True:
            try:
                async with connect(ws_url) as ws:
                    self._state.connected_at = datetime.now(timezone.utc).isoformat()
                    logger.info("WS connected: %s", ws_url)
                    _recv_count = 0

                    while True:
                        try:
                            raw = await asyncio.wait_for(
                                ws.recv(), timeout=self.ZOMBIE_TIMEOUT_SEC
                            )
                        except asyncio.TimeoutError:
                            raise ConnectionError(
                                f"No data for {self.ZOMBIE_TIMEOUT_SEC}s "
                                "(zombie connection)"
                            )
                        _recv_count += 1
                        # Reset backoff only when the connection has delivered
                        # STABLE_MIN_FRAMES consecutive frames — a single recv
                        # followed by a drop is not a stable connection.
                        if _recv_count >= self.STABLE_MIN_FRAMES:
                            attempt = 0
                        self.handle_message(raw, callback)

            except asyncio.CancelledError:
                logger.info("Feed cancelled.")
                raise
            except Exception as exc:
                self._state.last_error = str(exc)
                self._state.reconnect_count += 1
                delay = self._backoff_delay(attempt)
                attempt += 1
                logger.warning(
                    "WS error (reconnect #%d): %s; retrying in %.1fs",
                    self._state.reconnect_count,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
