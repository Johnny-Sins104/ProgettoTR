from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

try:
    from trading_bot.core.broker_adapter import AccountSnapshot, PositionSnapshot
    from trading_bot.core.paper_engine import PaperTradingEngine
    from trading_bot.core.paper_position_dashboard import format_live_position_dashboard, progress_bar, progress_to_take_profit
    from trading_bot.core.telegram_proactive import TelegramProactiveNotifier, TelegramProactiveSettings
except ModuleNotFoundError:  # pragma: no cover - supports PYTHONPATH=trading_bot
    from core.broker_adapter import AccountSnapshot, PositionSnapshot
    from core.paper_engine import PaperTradingEngine
    from core.paper_position_dashboard import format_live_position_dashboard, progress_bar, progress_to_take_profit
    from core.telegram_proactive import TelegramProactiveNotifier, TelegramProactiveSettings


class FakeTelegram:
    enabled = True
    chat_id = "chat"

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.edits: list[tuple[int, str]] = []
        self.audit_rows: list[tuple[str, dict]] = []
        self.next_id = 100
        self.edit_ok = True

    async def send_message_return_id(self, text: str, **_kwargs) -> int:
        self.sent.append(text)
        self.next_id += 1
        return self.next_id

    async def send(self, text: str) -> None:
        self.sent.append(text)

    async def edit_message_text(self, *, message_id: int, text: str, **_kwargs) -> bool:
        self.edits.append((message_id, text))
        return self.edit_ok

    def audit(self, event_type: str, **payload) -> None:
        self.audit_rows.append((event_type, payload))


def _account() -> AccountSnapshot:
    return AccountSnapshot(mode="paper", balance=1000.0, equity=1005.0, open_positions=1)


def _position(*, side: str = "BUY", mark: float = 105.0) -> PositionSnapshot:
    if side == "BUY":
        sl, tp, entry = 90.0, 110.0, 100.0
    else:
        sl, tp, entry = 110.0, 90.0, 100.0
    return PositionSnapshot(
        position_id="pos_1",
        symbol="BTC/USDT",
        side=side,
        qty=0.1,
        entry_price=entry,
        mark_price=mark,
        stop_loss=sl,
        take_profit=tp,
        take_profit_1=(entry + tp) / 2,
        take_profit_2=tp,
        unrealized_pnl=1.23,
        unrealized_pnl_pct=0.12,
        reason="test",
    )


def _notifier(tmp_path: Path, telegram: FakeTelegram) -> TelegramProactiveNotifier:
    return TelegramProactiveNotifier(
        telegram,
        state_path=tmp_path / "telegram_proactive_state.json",
        settings=TelegramProactiveSettings(
            enabled=True,
            position_dashboard_single_message=True,
            position_dashboard_update_seconds=20.0,
            position_dashboard_bar_width=10,
            max_messages_per_minute=10,
        ),
    )


def test_buy_dashboard_progress_moves_marker_toward_tp() -> None:
    assert progress_to_take_profit(side="BUY", current=105, stop_loss=90, take_profit=110) == 0.75
    bar, progress, state = progress_bar(side="BUY", current=105, stop_loss=90, take_profit=110, width=10)
    assert "SL 90.00" in bar
    assert "TP 110.00" in bar
    assert "●" in bar
    assert progress == 0.75
    assert state in {"IN_RANGE", "NEAR_TAKE_PROFIT"}


def test_sell_dashboard_progress_moves_marker_toward_lower_tp() -> None:
    assert progress_to_take_profit(side="SELL", current=95, stop_loss=110, take_profit=90) == 0.75
    text = format_live_position_dashboard(account=_account(), position=_position(side="SELL", mark=95), width=10, now_label="12:00:00 UTC")
    assert "BTC/USDT SELL/SHORT" in text
    assert "SL 110.00" in text
    assert "TP 90.00" in text
    assert "●" in text
    assert "Last update: 12:00:00 UTC" in text


def test_first_open_position_sends_one_dashboard_message(tmp_path: Path) -> None:
    telegram = FakeTelegram()
    notifier = _notifier(tmp_path, telegram)
    sent = asyncio.run(notifier.send_or_update_position_dashboard(account=_account(), position=_position(), force=True, reason="position_opened"))
    assert sent is True
    assert len(telegram.sent) == 1
    assert len(telegram.edits) == 0
    state = json.loads((tmp_path / "telegram_proactive_state.json").read_text(encoding="utf-8"))
    assert state["live_position_message_id_by_position"]["pos_1"] == 101
    assert "SL 90.00" in telegram.sent[0]
    assert "TP 110.00" in telegram.sent[0]


def test_update_before_interval_does_not_send_or_edit(tmp_path: Path) -> None:
    telegram = FakeTelegram()
    notifier = _notifier(tmp_path, telegram)
    asyncio.run(notifier.send_or_update_position_dashboard(account=_account(), position=_position(), force=True))
    telegram.sent.clear()
    notifier.state.live_position_last_edit_ts_by_position["pos_1"] = time.time()
    skipped = asyncio.run(notifier.send_or_update_position_dashboard(account=_account(), position=_position(mark=106), force=False))
    assert skipped is False
    assert telegram.sent == []
    assert telegram.edits == []


def test_update_after_interval_edits_existing_message_not_send(tmp_path: Path) -> None:
    telegram = FakeTelegram()
    notifier = _notifier(tmp_path, telegram)
    asyncio.run(notifier.send_or_update_position_dashboard(account=_account(), position=_position(), force=True))
    telegram.sent.clear()
    notifier.state.live_position_last_edit_ts_by_position["pos_1"] = time.time() - 30
    edited = asyncio.run(notifier.send_or_update_position_dashboard(account=_account(), position=_position(mark=107), force=False))
    assert edited is True
    assert telegram.sent == []
    assert len(telegram.edits) == 1
    assert telegram.edits[0][0] == 101
    assert "Now:   107.00" in telegram.edits[0][1]


def test_close_finalizes_and_archives_dashboard_message(tmp_path: Path) -> None:
    telegram = FakeTelegram()
    notifier = _notifier(tmp_path, telegram)
    pos = _position(side="BUY", mark=105)
    asyncio.run(notifier.send_or_update_position_dashboard(account=_account(), position=pos, force=True))
    closed = {
        "position_id": "pos_1",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "stop_loss": 90.0,
        "take_profit": 110.0,
        "realized_pnl": 10.0,
        "close_reason": "TP",
    }
    ok = asyncio.run(notifier.finalize_position_dashboard(account=_account(), closed_position=closed, reason="TP", cycle_id="pc"))
    assert ok is True
    assert telegram.edits[-1][0] == 101
    assert "PAPER POSITION CLOSED" in telegram.edits[-1][1]
    state = json.loads((tmp_path / "telegram_proactive_state.json").read_text(encoding="utf-8"))
    assert "pos_1" not in state["live_position_message_id_by_position"]
    assert state["live_position_archived_message_id_by_position"]["pos_1"] == 101


def test_disabled_telegram_does_not_crash(tmp_path: Path) -> None:
    telegram = FakeTelegram()
    telegram.enabled = False
    notifier = _notifier(tmp_path, telegram)
    ok = asyncio.run(notifier.send_or_update_position_dashboard(account=_account(), position=_position(), force=True))
    assert ok is False
    assert telegram.sent == []
    assert telegram.edits == []


def test_engine_single_message_open_suppresses_legacy_open_notification() -> None:
    class FakeBrokerAdapter:
        def reconcile(self):
            return SimpleNamespace(account=_account(), positions=[_position()])

    class FakeProactive:
        def __init__(self) -> None:
            self.state = SimpleNamespace(
                last_position_monitor_cycle={},
                last_position_monitor_sent_at={},
                last_position_pnl_pct={},
                last_position_tp_sl_state={},
            )
            self.dashboard_calls: list[dict] = []
            self.saved = 0

        def save(self) -> None:
            self.saved += 1

        async def send_or_update_position_dashboard(self, **kwargs) -> bool:
            self.dashboard_calls.append(kwargs)
            return True

    async def fake_send_proactive(*_args, **_kwargs) -> bool:
        legacy_calls.append((_args, _kwargs))
        return True

    legacy_calls: list[tuple] = []
    engine = PaperTradingEngine.__new__(PaperTradingEngine)
    engine.settings = SimpleNamespace(
        telegram_notify_on_position_open=True,
        telegram_proactive_enabled=True,
        telegram_position_dashboard_single_message=True,
        telegram_position_dashboard_update_seconds=20.0,
        telegram_notify_position_every_n_cycles=1,
        telegram_notify_position_every_seconds=0.0,
        telegram_notify_position_pnl_delta_pct=0.25,
    )
    engine.telegram = SimpleNamespace(enabled=True)
    engine.broker_adapter = FakeBrokerAdapter()
    engine.proactive = FakeProactive()
    engine._cycle_seq = 1
    engine._send_proactive = fake_send_proactive

    asyncio.run(engine._notify_position_opened(symbol="BTC/USDT", side="BUY", cycle_id="pc_test"))

    assert legacy_calls == []
    assert len(engine.proactive.dashboard_calls) == 1
    assert engine.proactive.dashboard_calls[0]["reason"] == "position_opened"
