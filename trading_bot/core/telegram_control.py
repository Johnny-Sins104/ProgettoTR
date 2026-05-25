"""Telegram operational control layer for ProgettoTR paper operations.

Prompt 29.3 hardening goals:
- allowlist-based command authorization;
- JSONL audit trail for every command attempt;
- per-user rate limiting;
- optional read-only mode;
- explicit confirmation for destructive commands.

The module remains dependency-light.  If Telegram credentials or aiohttp are not
available, ``send`` prints to console and command handling can still be smoke-tested
locally through ``handle_text``.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable

try:
    import aiohttp
except Exception:  # pragma: no cover - aiohttp is optional in smoke-test envs
    aiohttp = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_bool(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class TelegramCommandState:
    pause_requested: bool = False
    resume_requested: bool = False
    kill_requested: bool = False
    report_requested: bool = False
    last_commands: list[str] = field(default_factory=list)
    last_command_ts_by_user: dict[str, float] = field(default_factory=dict)


CommandHandler = Callable[[str, list[str]], Awaitable[str] | str]


class TelegramControlBot:
    """Small, auditable Telegram command dispatcher.

    Parameters are intentionally plain strings/lists so the class can be used by
    both the runtime engine and isolated smoke tests.
    """

    READ_ONLY_COMMANDS = {"/status", "/pnl", "/positions", "/monitor", "/orders", "/risk", "/report", "/help"}
    WRITE_COMMANDS = {"/pause", "/resume", "/kill"}
    DEFAULT_HELP = "Commands: /status /pnl /positions /monitor /orders /risk /pause /resume /kill confirm /report"

    def __init__(
        self,
        *,
        token: str = "",
        chat_id: str = "",
        allowed_user_ids: Iterable[str] | None = None,
        audit_path: str | Path = "data/telegram_audit.jsonl",
        read_only: bool | None = None,
        rate_limit_seconds: float | None = None,
        require_allowlist: bool | None = None,
    ) -> None:
        self.token = token or ""
        self.chat_id = str(chat_id or "")
        self.allowed_user_ids = {str(x).strip() for x in (allowed_user_ids or []) if str(x).strip()}
        self.audit_path = Path(audit_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_path.touch(exist_ok=True)
        self.read_only = _env_bool("TELEGRAM_READ_ONLY", "0") if read_only is None else bool(read_only)
        self.rate_limit_seconds = (
            float(os.getenv("TELEGRAM_RATE_LIMIT_SECONDS", "3")) if rate_limit_seconds is None else float(rate_limit_seconds)
        )
        self.require_allowlist = (
            _env_bool("TELEGRAM_REQUIRE_ALLOWED_USER_IDS", "1") if require_allowlist is None else bool(require_allowlist)
        )
        self.offset = 0
        self.state = TelegramCommandState()
        self.handlers: dict[str, CommandHandler] = {}
        self.enabled = bool(self.token and self.chat_id and aiohttp is not None)
        self.register("/help", lambda _c, _a: self.DEFAULT_HELP)
        self._session = None  # Pooled ClientSession

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    def register(self, command: str, handler: CommandHandler) -> None:
        self.handlers[command.lower().strip()] = handler

    def audit(self, event_type: str, **payload: Any) -> None:
        record = {"ts": _utc_now_iso(), "event_type": event_type, **payload}
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")

    async def send(self, text: str) -> None:
        if not self.enabled:
            print(f"[TelegramV2 disabled] {text}")
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text[:3900]}
        try:
            session = await self.get_session()
            await session.post(url, json=payload, timeout=8)
        except Exception as exc:
            print(f"[TelegramV2] send failed: {exc}")
            self.audit("TELEGRAM_SEND_FAILED", error=str(exc), error_type=exc.__class__.__name__)

    async def poll_forever(self) -> None:
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        self.audit(
            "TELEGRAM_POLLING_STARTED",
            read_only=self.read_only,
            allowed_user_count=len(self.allowed_user_ids),
            rate_limit_seconds=self.rate_limit_seconds,
        )
        session = await self.get_session()
        while True:
            try:
                async with session.post(url, json={"offset": self.offset, "timeout": 25}, timeout=30) as resp:
                    data = await resp.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        self.offset = int(update.get("update_id", self.offset)) + 1
                        message = update.get("message") or {}
                        text = str(message.get("text") or "").strip()
                        user_id = str((message.get("from") or {}).get("id") or "")
                        chat_id = str((message.get("chat") or {}).get("id") or "")
                        if text:
                            await self.handle_text(text, user_id=user_id, chat_id=chat_id)
            except asyncio.CancelledError:
                self.audit("TELEGRAM_POLLING_CANCELLED")
                raise
            except Exception as exc:
                print(f"[TelegramV2] polling error: {exc}")
                self.audit("TELEGRAM_POLLING_ERROR", error=str(exc), error_type=exc.__class__.__name__)
                await asyncio.sleep(5)

    def _is_authorized(self, *, user_id: str) -> bool:
        if self.allowed_user_ids:
            return bool(user_id and user_id in self.allowed_user_ids)
        if self.require_allowlist:
            return False
        return True

    def _rate_limited(self, *, user_id: str, now_ts: float) -> bool:
        if self.rate_limit_seconds <= 0:
            return False
        key = user_id or "unknown"
        previous = self.state.last_command_ts_by_user.get(key)
        if previous is not None and now_ts - previous < self.rate_limit_seconds:
            return True
        self.state.last_command_ts_by_user[key] = now_ts
        return False

    async def handle_text(self, text: str, *, user_id: str = "", chat_id: str = "") -> str:
        parts = text.strip().split()
        command = parts[0].lower() if parts else ""
        args = parts[1:]
        now_ts = datetime.now(timezone.utc).timestamp()
        authorized = self._is_authorized(user_id=user_id)
        self.state.last_commands.append(text)
        self.state.last_commands = self.state.last_commands[-20:]
        self.audit(
            "TELEGRAM_COMMAND_RECEIVED",
            command=command,
            args=args,
            user_id=str(user_id or ""),
            chat_id=str(chat_id or ""),
            authorized=authorized,
            read_only=self.read_only,
        )
        if not authorized:
            reply = "Access denied. Configure TELEGRAM_ALLOWED_USER_IDS with your numeric Telegram user ID."
            self.audit("TELEGRAM_COMMAND_REJECTED", command=command, user_id=str(user_id or ""), reason="unauthorized")
            await self.send(reply)
            return reply
        if self._rate_limited(user_id=user_id, now_ts=now_ts):
            reply = "Rate limit active. Retry shortly."
            self.audit("TELEGRAM_COMMAND_REJECTED", command=command, user_id=str(user_id or ""), reason="rate_limited")
            await self.send(reply)
            return reply
        if self.read_only and command in self.WRITE_COMMANDS:
            reply = "Telegram read-only mode is active. Write command blocked."
            self.audit("TELEGRAM_COMMAND_REJECTED", command=command, user_id=str(user_id or ""), reason="read_only")
            await self.send(reply)
            return reply
        handler = self.handlers.get(command)
        if not handler:
            reply = self.DEFAULT_HELP
            self.audit("TELEGRAM_COMMAND_REJECTED", command=command, user_id=str(user_id or ""), reason="unknown_command")
            await self.send(reply)
            return reply
        try:
            result = handler(command, args)
            if asyncio.iscoroutine(result):
                result = await result
            reply = str(result)
            self.audit("TELEGRAM_COMMAND_COMPLETED", command=command, user_id=str(user_id or ""), result=reply[:500])
            await self.send(reply)
            return reply
        except Exception as exc:
            reply = f"Command failed: {exc.__class__.__name__}"
            self.audit("TELEGRAM_COMMAND_FAILED", command=command, user_id=str(user_id or ""), error=str(exc), error_type=exc.__class__.__name__)
            await self.send(reply)
            return reply
