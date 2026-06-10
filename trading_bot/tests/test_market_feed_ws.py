"""Tests for trading_bot/clean_bot/market_feed_ws.py — TR-INT-03 (Fase 3).

Required tests:
  test_closed_candle_only
  test_deduplication
  test_reconnect_backoff
  test_zombie_timeout
  test_no_order_methods
  test_5m_watermark_stateful
  test_feed_disabled_by_default
  test_feed_does_not_touch_1m_cost_model
"""
from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import trading_bot.clean_bot.market_feed_ws as feed_module
from trading_bot.clean_bot.market_feed_ws import FeedState, MarketFeedWS


# ── shared helpers ────────────────────────────────────────────────────────────

def _kline_msg(*, closed: bool, tf: str = "1m", close_ts: int = 60_000) -> str:
    """Return a JSON-encoded Binance combined-stream kline message."""
    return json.dumps(
        {
            "stream": f"btcusdt@kline_{tf}",
            "data": {
                "e": "kline",
                "k": {
                    "t": close_ts - 60_000,
                    "T": close_ts,
                    "i": tf,
                    "o": "50000",
                    "h": "51000",
                    "l": "49000",
                    "c": "50500",
                    "v": "100",
                    "x": closed,
                },
            },
        }
    )


def _make_feed(timeframes: tuple[str, ...] = ("1m", "5m")) -> MarketFeedWS:
    return MarketFeedWS("BTCUSDT", list(timeframes))


# ─────────────────────────────────────────────────────────────────────────────
# test_closed_candle_only
# ─────────────────────────────────────────────────────────────────────────────

def test_closed_candle_only():
    """Open candles (k['x']=False) must not invoke the callback."""
    feed = _make_feed()
    calls: list = []

    feed.handle_message(
        _kline_msg(closed=False, tf="1m", close_ts=60_000),
        lambda tf, c: calls.append((tf, c)),
    )

    assert calls == [], "Open candle must not trigger the callback"


def test_closed_candle_only_dispatches_closed():
    """Closed candles (k['x']=True) must invoke the callback exactly once."""
    feed = _make_feed()
    calls: list = []

    feed.handle_message(
        _kline_msg(closed=True, tf="1m", close_ts=60_000),
        lambda tf, c: calls.append((tf, c)),
    )

    assert len(calls) == 1
    tf_seen, candle = calls[0]
    assert tf_seen == "1m"
    assert candle["T"] == 60_000


# ─────────────────────────────────────────────────────────────────────────────
# test_deduplication
# ─────────────────────────────────────────────────────────────────────────────

def test_deduplication():
    """The same close_ts sent twice must trigger the callback exactly once."""
    feed = _make_feed()
    calls: list = []
    msg = _kline_msg(closed=True, tf="1m", close_ts=120_000)

    feed.handle_message(msg, lambda tf, c: calls.append(c))
    feed.handle_message(msg, lambda tf, c: calls.append(c))

    assert len(calls) == 1, f"Expected 1 call, got {len(calls)}"


def test_deduplication_different_timestamps_both_pass():
    """Two distinct close timestamps must both be dispatched."""
    feed = _make_feed()
    calls: list = []

    feed.handle_message(_kline_msg(closed=True, tf="1m", close_ts=60_000),
                        lambda tf, c: calls.append(c["T"]))
    feed.handle_message(_kline_msg(closed=True, tf="1m", close_ts=120_000),
                        lambda tf, c: calls.append(c["T"]))

    assert calls == [60_000, 120_000]


# ─────────────────────────────────────────────────────────────────────────────
# test_reconnect_backoff
# ─────────────────────────────────────────────────────────────────────────────

def test_reconnect_backoff():
    """Backoff delay must be exponential and capped at RECONNECT_MAX_DELAY."""
    feed = _make_feed()

    d0 = feed._backoff_delay(0)
    d1 = feed._backoff_delay(1)
    d2 = feed._backoff_delay(2)
    d3 = feed._backoff_delay(3)
    d5 = feed._backoff_delay(5)
    d9 = feed._backoff_delay(9)

    assert d0 == pytest.approx(1.0)   # base * 2^0
    assert d1 == pytest.approx(2.0)   # base * 2^1
    assert d2 == pytest.approx(4.0)   # base * 2^2
    assert d3 == pytest.approx(8.0)   # base * 2^3
    assert d5 == pytest.approx(32.0)  # base * 2^5
    # Attempts beyond 5 are capped
    assert d9 == pytest.approx(MarketFeedWS.RECONNECT_MAX_DELAY)
    # Monotonically non-decreasing
    for a, b in zip([d0, d1, d2, d3, d5], [d1, d2, d3, d5, d9]):
        assert b >= a


def test_reconnect_backoff_async_increments():
    """After a WS failure the loop must sleep with increasing delays."""

    async def _run():
        old = feed_module.FEED_ENABLED
        feed_module.FEED_ENABLED = True
        try:
            feed = _make_feed(("1m",))
            sleep_delays: list[float] = []

            class _FailConnect:
                def __init__(self, url):
                    pass

                async def __aenter__(self):
                    raise ConnectionError("refused")

                async def __aexit__(self, *a):
                    pass

            async def _mock_sleep(d: float) -> None:
                sleep_delays.append(d)
                if len(sleep_delays) >= 3:
                    raise asyncio.CancelledError()

            with patch("asyncio.sleep", _mock_sleep):
                try:
                    await feed.run(
                        lambda tf, c: None,
                        bootstrap=False,
                        _ws_connect=_FailConnect,
                    )
                except asyncio.CancelledError:
                    pass

            assert len(sleep_delays) >= 2
            # First delay must be the base delay
            assert sleep_delays[0] == pytest.approx(MarketFeedWS.RECONNECT_BASE_DELAY)
            # Second delay must be larger (exponential growth)
            assert sleep_delays[1] > sleep_delays[0]
            assert feed.health["reconnect_count"] >= 2
        finally:
            feed_module.FEED_ENABLED = old

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# test_zombie_timeout
# ─────────────────────────────────────────────────────────────────────────────

def test_zombie_timeout():
    """ZOMBIE_TIMEOUT_SEC must equal 90 and a stalled recv() must trigger reconnect."""
    assert MarketFeedWS.ZOMBIE_TIMEOUT_SEC == 90

    async def _run():
        old = feed_module.FEED_ENABLED
        feed_module.FEED_ENABLED = True
        try:
            feed = _make_feed(("1m",))
            # Shorten timeout so the test completes fast
            feed.ZOMBIE_TIMEOUT_SEC = 0.05

            async def _stalled_recv():
                # Blocks much longer than ZOMBIE_TIMEOUT_SEC
                await asyncio.sleep(60)

            class _StalledWS:
                recv = _stalled_recv

            class _StalledConnect:
                def __init__(self, url):
                    pass

                async def __aenter__(self):
                    return _StalledWS()

                async def __aexit__(self, *a):
                    pass

            async def _mock_sleep(d: float) -> None:
                # First sleep after zombie timeout → cancel
                raise asyncio.CancelledError()

            with patch("asyncio.sleep", _mock_sleep):
                try:
                    await feed.run(
                        lambda tf, c: None,
                        bootstrap=False,
                        _ws_connect=_StalledConnect,
                    )
                except asyncio.CancelledError:
                    pass

            assert feed.health["reconnect_count"] >= 1
            err = (feed.health["last_error"] or "").lower()
            assert "zombie" in err or "timeout" in err or "timed out" in err, (
                f"Expected zombie/timeout in last_error, got: {feed.health['last_error']!r}"
            )
        finally:
            feed_module.FEED_ENABLED = old

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# test_no_order_methods
# ─────────────────────────────────────────────────────────────────────────────

def test_no_order_methods():
    """MarketFeedWS must not expose any order/trade mutation methods."""
    banned = {
        "place_order", "submit", "submit_order", "create_order",
        "trade", "buy", "sell", "cancel_order", "execute", "execute_trade",
        "open_position", "close_position", "modify_order",
    }
    public_methods = {
        name for name in dir(MarketFeedWS) if not name.startswith("_")
    }
    overlap = public_methods & banned
    assert not overlap, f"Feed exposes forbidden method(s): {overlap}"


def test_no_order_methods_on_instance():
    """Instance must not have order/trade methods either."""
    banned = {
        "place_order", "submit", "submit_order", "create_order",
        "trade", "buy", "sell", "cancel_order", "execute", "execute_trade",
        "open_position", "close_position",
    }
    feed = _make_feed()
    overlap = {m for m in banned if hasattr(feed, m)}
    assert not overlap, f"Feed instance has forbidden attribute(s): {overlap}"


# ─────────────────────────────────────────────────────────────────────────────
# test_5m_watermark_stateful
# ─────────────────────────────────────────────────────────────────────────────

def test_5m_watermark_stateful():
    """sync_5m_watermark must operate on an explicit FeedState; no module globals."""
    # Confirm no module-level mutable globals for candle data
    assert not hasattr(feed_module, "closed_candles_5m"), (
        "Module must not have a global closed_candles_5m"
    )
    assert not hasattr(feed_module, "closed_prices_5m"), (
        "Module must not have a global closed_prices_5m"
    )
    assert not hasattr(feed_module, "_watermarks"), (
        "Module must not have a global _watermarks dict"
    )

    candles_5m = [
        {"t": 0,       "T": 300_000, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"},
        {"t": 300_000, "T": 600_000, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"},
    ]

    # state_a: 1m watermark already at 400_000 → 5m candle T=300_000 eligible
    state_a = FeedState(
        watermarks={"1m": 400_000, "5m": 0},
        buffers={"1m": [], "5m": []},
    )
    # state_b: 1m watermark at 0 → no 5m candle eligible
    state_b = FeedState(
        watermarks={"1m": 0, "5m": 0},
        buffers={"1m": [], "5m": []},
    )

    feed = _make_feed()
    feed.sync_5m_watermark(candles_5m, state_a)
    feed.sync_5m_watermark(candles_5m, state_b)

    assert len(state_a.buffers["5m"]) == 1, "state_a should have 1 synced 5m candle"
    assert state_a.buffers["5m"][0]["T"] == 300_000
    assert state_a.watermarks["5m"] == 300_000

    assert len(state_b.buffers["5m"]) == 0, "state_b should have 0 synced 5m candles"
    assert state_b.watermarks["5m"] == 0

    # States are independent objects
    assert state_a.buffers is not state_b.buffers
    assert state_a.watermarks is not state_b.watermarks


def test_5m_watermark_idempotent():
    """Calling sync_5m_watermark twice must not add duplicates."""
    candles_5m = [
        {"t": 0, "T": 300_000, "o": "1", "h": "1", "l": "1", "c": "1", "v": "1"},
    ]
    state = FeedState(
        watermarks={"1m": 400_000, "5m": 0},
        buffers={"1m": [], "5m": []},
    )
    feed = _make_feed()
    feed.sync_5m_watermark(candles_5m, state)
    feed.sync_5m_watermark(candles_5m, state)
    assert len(state.buffers["5m"]) == 1, "Idempotent: candle must not be added twice"


# ─────────────────────────────────────────────────────────────────────────────
# test_feed_disabled_by_default
# ─────────────────────────────────────────────────────────────────────────────

def test_feed_disabled_by_default():
    """FEED_ENABLED must be False at module level immediately after import."""
    assert feed_module.FEED_ENABLED is False, (
        "FEED_ENABLED must default to False — no accidental live connection"
    )


def test_feed_run_raises_when_disabled():
    """Calling run() with FEED_ENABLED=False must raise RuntimeError, not connect."""
    async def _try_run():
        # Ensure disabled
        old = feed_module.FEED_ENABLED
        feed_module.FEED_ENABLED = False
        try:
            feed = _make_feed()
            await feed.run(lambda tf, c: None, bootstrap=False)
        finally:
            feed_module.FEED_ENABLED = old

    with pytest.raises(RuntimeError, match="FEED_ENABLED"):
        asyncio.run(_try_run())


def test_feed_no_network_at_import():
    """Importing the module must not initiate any network connection.

    Verified by asserting no socket-creating call exists at module scope —
    all heavy imports (websockets, aiohttp) are deferred inside methods.
    """
    src = inspect.getsource(feed_module)
    # websockets and aiohttp imports must be inside function bodies, not at top-level
    lines = src.splitlines()
    top_level_imports = [
        ln.strip()
        for ln in lines
        if ln.startswith("import ") or ln.startswith("from ")
    ]
    for ln in top_level_imports:
        assert "websockets" not in ln, (
            f"websockets must not be imported at module top level: {ln!r}"
        )
        assert "aiohttp" not in ln, (
            f"aiohttp must not be imported at module top level: {ln!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# test_feed_does_not_touch_1m_cost_model
# ─────────────────────────────────────────────────────────────────────────────

def test_feed_does_not_touch_1m_cost_model():
    """Processing 1m closed candles must never invoke unified_trade_cost functions."""
    src = inspect.getsource(feed_module)
    assert "unified_trade_cost" not in src, (
        "market_feed_ws.py must not import or reference unified_trade_cost"
    )


def test_feed_1m_candle_no_cost_model_call():
    """UnifiedCostModel must not be instantiated when a 1m candle is dispatched."""
    with patch(
        "trading_bot.core.unified_trade_cost.UnifiedCostModel"
    ) as mock_ucm:
        feed = _make_feed(("1m",))
        received: list = []
        feed.handle_message(
            _kline_msg(closed=True, tf="1m", close_ts=60_000),
            lambda tf, c: received.append(c),
        )
        assert len(received) == 1, "Callback must fire for closed 1m candle"
        mock_ucm.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_reconnect_backoff_open_then_recv_fail  (Bug-1 regression)
# ─────────────────────────────────────────────────────────────────────────────

def test_reconnect_backoff_open_then_recv_fail():
    """Connection opens but recv() fails immediately — backoff must still grow.

    Three round-trips: WS opens, recv() raises, connection closed.
    Expected sleep sequence: 1.0 s, 2.0 s, 4.0 s (exponential, never reset).
    """

    async def _run():
        old = feed_module.FEED_ENABLED
        feed_module.FEED_ENABLED = True
        try:
            feed = _make_feed(("1m",))
            sleep_delays: list[float] = []
            connect_count = [0]

            class _RecvFailWS:
                async def recv(self):
                    raise ConnectionError("connection reset by peer")

            class _OpenThenFailConnect:
                def __init__(self, url):
                    pass

                async def __aenter__(self):
                    connect_count[0] += 1
                    return _RecvFailWS()

                async def __aexit__(self, *a):
                    pass

            async def _mock_sleep(d: float) -> None:
                sleep_delays.append(d)
                if len(sleep_delays) >= 3:
                    raise asyncio.CancelledError()

            with patch("asyncio.sleep", _mock_sleep):
                try:
                    await feed.run(
                        lambda tf, c: None,
                        bootstrap=False,
                        _ws_connect=_OpenThenFailConnect,
                    )
                except asyncio.CancelledError:
                    pass

            assert connect_count[0] >= 3, (
                f"Expected >=3 WS open attempts, got {connect_count[0]}"
            )
            assert len(sleep_delays) >= 3
            assert sleep_delays[0] == pytest.approx(MarketFeedWS.RECONNECT_BASE_DELAY), (
                f"First delay should be base {MarketFeedWS.RECONNECT_BASE_DELAY}, got {sleep_delays[0]}"
            )
            assert sleep_delays[1] == pytest.approx(MarketFeedWS.RECONNECT_BASE_DELAY * 2), (
                f"Second delay should be {MarketFeedWS.RECONNECT_BASE_DELAY * 2}, got {sleep_delays[1]}"
            )
            assert sleep_delays[2] == pytest.approx(MarketFeedWS.RECONNECT_BASE_DELAY * 4), (
                f"Third delay should be {MarketFeedWS.RECONNECT_BASE_DELAY * 4}, got {sleep_delays[2]}"
            )
        finally:
            feed_module.FEED_ENABLED = old

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# test_reconnect_backoff_one_recv_then_drop  (Bug-3 regression)
# ─────────────────────────────────────────────────────────────────────────────

def test_reconnect_backoff_one_recv_then_drop():
    """One successful recv() then connection drop must NOT reset the backoff.

    Scenario: 3 connections, each delivers exactly one frame before dropping.
    Expected sleep sequence: 1.0 s, 2.0 s, 4.0 s — never reset to 1.0.
    """

    async def _run():
        old = feed_module.FEED_ENABLED
        feed_module.FEED_ENABLED = True
        try:
            feed = _make_feed(("1m",))
            sleep_delays: list[float] = []
            connect_count = [0]

            valid_msg = _kline_msg(closed=True, tf="1m", close_ts=60_000)

            class _OneRecvThenDropWS:
                def __init__(self):
                    self._called = 0

                async def recv(self):
                    self._called += 1
                    if self._called == 1:
                        return valid_msg
                    raise ConnectionError("drop after first frame")

            class _OneRecvThenDropConnect:
                def __init__(self, url):
                    pass

                async def __aenter__(self):
                    connect_count[0] += 1
                    return _OneRecvThenDropWS()

                async def __aexit__(self, *a):
                    pass

            async def _mock_sleep(d: float) -> None:
                sleep_delays.append(d)
                if len(sleep_delays) >= 3:
                    raise asyncio.CancelledError()

            with patch("asyncio.sleep", _mock_sleep):
                try:
                    await feed.run(
                        lambda tf, c: None,
                        bootstrap=False,
                        _ws_connect=_OneRecvThenDropConnect,
                    )
                except asyncio.CancelledError:
                    pass

            assert connect_count[0] >= 3, (
                f"Expected >=3 connect attempts, got {connect_count[0]}"
            )
            assert len(sleep_delays) >= 3
            assert sleep_delays[0] == pytest.approx(MarketFeedWS.RECONNECT_BASE_DELAY), (
                f"Delay[0] should be {MarketFeedWS.RECONNECT_BASE_DELAY}, got {sleep_delays[0]}"
            )
            assert sleep_delays[1] == pytest.approx(MarketFeedWS.RECONNECT_BASE_DELAY * 2), (
                f"Delay[1] should be {MarketFeedWS.RECONNECT_BASE_DELAY * 2}, got {sleep_delays[1]}"
            )
            assert sleep_delays[2] == pytest.approx(MarketFeedWS.RECONNECT_BASE_DELAY * 4), (
                f"Delay[2] should be {MarketFeedWS.RECONNECT_BASE_DELAY * 4}, got {sleep_delays[2]}"
            )
        finally:
            feed_module.FEED_ENABLED = old

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# test_bootstrap_rest_fail_blocks_ws  (Bug-2 regression)
# ─────────────────────────────────────────────────────────────────────────────

def test_bootstrap_rest_fail_blocks_ws():
    """If bootstrap REST fails for any timeframe, run() must not attempt WS at all."""

    async def _run():
        old = feed_module.FEED_ENABLED
        feed_module.FEED_ENABLED = True
        try:
            feed = _make_feed(("1m",))
            ws_attempts = [0]

            class _CountingConnect:
                def __init__(self, url):
                    ws_attempts[0] += 1

                async def __aenter__(self):
                    return AsyncMock()

                async def __aexit__(self, *a):
                    pass

            async def _failing_http_get(url: str) -> list:
                raise ConnectionError("REST endpoint unreachable")

            with pytest.raises(RuntimeError, match="Bootstrap REST"):
                await feed.run(
                    lambda tf, c: None,
                    bootstrap=True,
                    _ws_connect=_CountingConnect,
                    _http_get=_failing_http_get,
                )

            assert ws_attempts[0] == 0, (
                f"WS must not be attempted after bootstrap failure; "
                f"got {ws_attempts[0]} attempt(s)"
            )
        finally:
            feed_module.FEED_ENABLED = old

    asyncio.run(_run())
