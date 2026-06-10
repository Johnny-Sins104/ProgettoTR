"""Prompt 29.4.1a proactive Telegram notification guardrails.

This module keeps Telegram operational notifications deterministic, auditable
and low-noise.  It is paper-mode only and does not interact with exchange APIs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import time

try:
    from core.paper_position_dashboard import format_closed_position_dashboard, format_live_position_dashboard
except Exception:  # pragma: no cover - package import fallback
    from .paper_position_dashboard import format_closed_position_dashboard, format_live_position_dashboard


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


@dataclass
class TelegramProactiveSettings:
    enabled: bool = True
    notify_on_start: bool = True
    notify_on_shutdown: bool = True
    notify_on_signal: bool = True
    notify_on_order: bool = True
    notify_on_position_open: bool = True
    notify_on_position_close: bool = True
    notify_on_tp_sl: bool = True
    notify_on_drift_warn: bool = True
    notify_every_cycle: bool = False
    notify_no_signal_every_n_cycles: int = 12
    notify_position_every_n_cycles: int = 1
    notify_position_every_seconds: float = 300.0
    notify_position_pnl_delta_pct: float = 0.25
    dedup_seconds: float = 30.0
    max_messages_per_minute: int = 10
    position_dashboard_single_message: bool = True
    position_dashboard_update_seconds: float = 20.0
    position_dashboard_bar_width: int = 20
    position_dashboard_send_close_summary: bool = True


@dataclass
class TelegramProactiveState:
    last_sent_by_key: dict[str, float] = field(default_factory=dict)
    sent_window_ts: list[float] = field(default_factory=list)
    last_position_monitor_sent_at: dict[str, float] = field(default_factory=dict)
    last_position_monitor_cycle: dict[str, int] = field(default_factory=dict)
    last_position_pnl_pct: dict[str, float] = field(default_factory=dict)
    last_position_tp_sl_state: dict[str, str] = field(default_factory=dict)
    last_drift_alert_hash: str = ""
    last_summary_cycle: int = 0
    last_shutdown_notified: bool = False
    last_notification_at: str = ""
    last_notification_type: str = ""
    live_position_message_id_by_position: dict[str, int] = field(default_factory=dict)
    live_position_last_edit_ts_by_position: dict[str, float] = field(default_factory=dict)
    live_position_last_text_hash_by_position: dict[str, str] = field(default_factory=dict)
    live_position_archived_message_id_by_position: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TelegramProactiveState":
        state = cls()
        for key in state.__dataclass_fields__:  # type: ignore[attr-defined]
            value = data.get(key)
            if value is not None:
                setattr(state, key, value)
        return state

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_sent_by_key": self.last_sent_by_key,
            "sent_window_ts": self.sent_window_ts[-200:],
            "last_position_monitor_sent_at": self.last_position_monitor_sent_at,
            "last_position_monitor_cycle": self.last_position_monitor_cycle,
            "last_position_pnl_pct": self.last_position_pnl_pct,
            "last_position_tp_sl_state": self.last_position_tp_sl_state,
            "last_drift_alert_hash": self.last_drift_alert_hash,
            "last_summary_cycle": self.last_summary_cycle,
            "last_shutdown_notified": self.last_shutdown_notified,
            "last_notification_at": self.last_notification_at,
            "last_notification_type": self.last_notification_type,
            "live_position_message_id_by_position": self.live_position_message_id_by_position,
            "live_position_last_edit_ts_by_position": self.live_position_last_edit_ts_by_position,
            "live_position_last_text_hash_by_position": self.live_position_last_text_hash_by_position,
            "live_position_archived_message_id_by_position": self.live_position_archived_message_id_by_position,
        }


class TelegramProactiveNotifier:
    def __init__(self, telegram: Any, *, state_path: str | Path, settings: TelegramProactiveSettings) -> None:
        self.telegram = telegram
        self.state_path = Path(state_path)
        self.settings = settings
        self.state = self._load_state()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enabled and getattr(self.telegram, "enabled", False))

    def _load_state(self) -> TelegramProactiveState:
        if not self.state_path.exists():
            return TelegramProactiveState()
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return TelegramProactiveState.from_dict(data)
        except Exception:
            pass
        return TelegramProactiveState()

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.state.to_dict()
        payload["updated_at"] = utc_now_iso()
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.settings.enabled),
            "telegram_enabled": bool(getattr(self.telegram, "enabled", False)),
            "state_path": str(self.state_path),
            "last_notification_at": self.state.last_notification_at,
            "last_notification_type": self.state.last_notification_type,
            "notify_on_start": bool(self.settings.notify_on_start),
            "notify_on_shutdown": bool(self.settings.notify_on_shutdown),
            "notify_every_cycle": bool(self.settings.notify_every_cycle),
            "notify_no_signal_every_n_cycles": int(self.settings.notify_no_signal_every_n_cycles or 0),
            "notify_position_every_n_cycles": int(self.settings.notify_position_every_n_cycles or 0),
            "notify_position_every_seconds": float(self.settings.notify_position_every_seconds or 0.0),
            "dedup_seconds": float(self.settings.dedup_seconds or 0.0),
            "max_messages_per_minute": int(self.settings.max_messages_per_minute or 0),
            "position_dashboard_single_message": bool(self.settings.position_dashboard_single_message),
            "position_dashboard_update_seconds": float(self.settings.position_dashboard_update_seconds or 0.0),
            "position_dashboard_bar_width": int(self.settings.position_dashboard_bar_width or 0),
        }

    def _audit(self, event_type: str, **payload: Any) -> None:
        audit = getattr(self.telegram, "audit", None)
        if callable(audit):
            audit(event_type, **payload)

    def _rate_allowed(self, now_ts: float) -> bool:
        max_per_min = int(self.settings.max_messages_per_minute or 0)
        if max_per_min <= 0:
            return True
        self.state.sent_window_ts = [t for t in self.state.sent_window_ts if now_ts - float(t) < 60.0]
        return len(self.state.sent_window_ts) < max_per_min


    async def send_or_update_position_dashboard(
        self,
        *,
        account: Any,
        position: Any,
        reason: str = "",
        cycle_id: str = "",
        force: bool = False,
    ) -> bool:
        """Create or edit the single live paper position dashboard message.

        This method only sends/edits Telegram UI state.  It never submits,
        closes, routes, or mutates paper_state/paper_status.
        """
        position_id = str(getattr(position, "position_id", "") or "")
        if not position_id:
            return False
        base = {
            "notification_type": "position_dashboard",
            "position_id": position_id,
            "cycle_id": cycle_id,
            "trigger_reason": reason,
        }
        if not self.settings.enabled:
            self._audit("TELEGRAM_POSITION_DASHBOARD_SKIPPED", status="skipped", reason="proactive_disabled", **base)
            return False
        if not getattr(self.telegram, "enabled", False):
            self._audit("TELEGRAM_POSITION_DASHBOARD_SKIPPED", status="skipped", reason="telegram_disabled", **base)
            return False
        if not bool(self.settings.position_dashboard_single_message):
            self._audit("TELEGRAM_POSITION_DASHBOARD_SKIPPED", status="skipped", reason="single_message_disabled", **base)
            return False

        now_ts = time.time()
        update_seconds = max(0.0, float(self.settings.position_dashboard_update_seconds or 0.0))
        last_edit_ts = float(self.state.live_position_last_edit_ts_by_position.get(position_id, 0.0) or 0.0)
        message_id = self.state.live_position_message_id_by_position.get(position_id)
        if message_id and not force and update_seconds > 0 and now_ts - last_edit_ts < update_seconds:
            self._audit("TELEGRAM_POSITION_DASHBOARD_SKIPPED", status="skipped", reason="update_interval", **base)
            self.save()
            return False

        text = format_live_position_dashboard(
            account=account,
            position=position,
            width=int(self.settings.position_dashboard_bar_width or 20),
        )
        text_hash = stable_hash(text)

        if not message_id:
            if not force and not self._rate_allowed(now_ts):
                self._audit("TELEGRAM_POSITION_DASHBOARD_SKIPPED", status="skipped", reason="max_messages_per_minute", **base)
                self.save()
                return False
            sender = getattr(self.telegram, "send_message_return_id", None)
            if callable(sender):
                new_message_id = await sender(text)
            else:  # fallback for older fakes/tests
                await self.telegram.send(text)
                new_message_id = None
            if new_message_id is not None:
                self.state.live_position_message_id_by_position[position_id] = int(new_message_id)
            self.state.live_position_last_edit_ts_by_position[position_id] = now_ts
            self.state.live_position_last_text_hash_by_position[position_id] = text_hash
            self.state.sent_window_ts.append(now_ts)
            self.state.last_notification_at = utc_now_iso()
            self.state.last_notification_type = "position_dashboard"
            self._audit("TELEGRAM_POSITION_DASHBOARD_SENT", status="sent", message_id=new_message_id, **base)
            self.save()
            return True

        editor = getattr(self.telegram, "edit_message_text", None)
        edit_ok = False
        if callable(editor):
            edit_ok = bool(await editor(message_id=int(message_id), text=text))
        if not edit_ok:
            sender = getattr(self.telegram, "send_message_return_id", None)
            if callable(sender):
                new_message_id = await sender(text)
                if new_message_id is not None:
                    self.state.live_position_message_id_by_position[position_id] = int(new_message_id)
                    message_id = int(new_message_id)
                    edit_ok = True
        if edit_ok:
            self.state.live_position_last_edit_ts_by_position[position_id] = now_ts
            self.state.live_position_last_text_hash_by_position[position_id] = text_hash
            self.state.last_notification_at = utc_now_iso()
            self.state.last_notification_type = "position_dashboard"
            self._audit("TELEGRAM_POSITION_DASHBOARD_EDITED", status="edited", message_id=int(message_id), **base)
            self.save()
            return True
        self._audit("TELEGRAM_POSITION_DASHBOARD_FAILED", status="failed", message_id=int(message_id), **base)
        self.save()
        return False

    async def finalize_position_dashboard(
        self,
        *,
        account: Any,
        closed_position: Any,
        reason: str = "",
        cycle_id: str = "",
    ) -> bool:
        """Final-edit and archive a paper position dashboard on close."""
        if isinstance(closed_position, dict):
            position_id = str(closed_position.get("position_id", "") or "")
        else:
            position_id = str(getattr(closed_position, "position_id", "") or "")
        if not position_id:
            return False
        message_id = self.state.live_position_message_id_by_position.get(position_id)
        base = {
            "notification_type": "position_dashboard_closed",
            "position_id": position_id,
            "cycle_id": cycle_id,
            "trigger_reason": reason,
        }
        if not message_id:
            self._audit("TELEGRAM_POSITION_DASHBOARD_CLOSE_SKIPPED", status="skipped", reason="message_id_absent", **base)
            self.save()
            return False
        if not self.settings.enabled or not getattr(self.telegram, "enabled", False):
            self._audit("TELEGRAM_POSITION_DASHBOARD_CLOSE_SKIPPED", status="skipped", reason="telegram_disabled", **base)
            return False
        text = format_closed_position_dashboard(
            account=account,
            position=closed_position,
            width=int(self.settings.position_dashboard_bar_width or 20),
        )
        editor = getattr(self.telegram, "edit_message_text", None)
        edited = bool(await editor(message_id=int(message_id), text=text)) if callable(editor) else False
        if edited:
            self.state.live_position_archived_message_id_by_position[position_id] = int(message_id)
            self.state.live_position_message_id_by_position.pop(position_id, None)
            self.state.live_position_last_edit_ts_by_position.pop(position_id, None)
            self.state.live_position_last_text_hash_by_position.pop(position_id, None)
            self.state.last_notification_at = utc_now_iso()
            self.state.last_notification_type = "position_dashboard_closed"
            self._audit("TELEGRAM_POSITION_DASHBOARD_CLOSED", status="edited", message_id=int(message_id), **base)
            self.save()
            return True
        self._audit("TELEGRAM_POSITION_DASHBOARD_CLOSE_FAILED", status="failed", message_id=int(message_id), **base)
        self.save()
        return False

    async def send(
        self,
        *,
        event_type: str,
        notification_type: str,
        text: str,
        dedup_key: str | None = None,
        force: bool = False,
        **payload: Any,
    ) -> bool:
        dedup_key = dedup_key or f"{notification_type}:{stable_hash(text)}"
        now_ts = time.time()
        base = {
            "notification_type": notification_type,
            "dedup_key": dedup_key,
            "chat_id": str(getattr(self.telegram, "chat_id", "") or ""),
            **payload,
        }
        if not self.settings.enabled:
            self._audit(event_type, status="skipped", reason="proactive_disabled", **base)
            return False
        if not getattr(self.telegram, "enabled", False):
            self._audit(event_type, status="skipped", reason="telegram_disabled", **base)
            return False
        last_ts = float(self.state.last_sent_by_key.get(dedup_key, 0.0) or 0.0)
        if not force and self.settings.dedup_seconds > 0 and now_ts - last_ts < float(self.settings.dedup_seconds):
            self._audit(event_type, status="skipped", reason="dedup", **base)
            self.save()
            return False
        if not force and not self._rate_allowed(now_ts):
            self._audit(event_type, status="skipped", reason="max_messages_per_minute", **base)
            self.save()
            return False
        try:
            await self.telegram.send(text)
            self.state.last_sent_by_key[dedup_key] = now_ts
            self.state.sent_window_ts.append(now_ts)
            self.state.last_notification_at = utc_now_iso()
            self.state.last_notification_type = notification_type
            self._audit(event_type, status="sent", **base)
            self.save()
            return True
        except Exception as exc:  # defensive; TelegramControlBot.send already catches most errors
            self._audit(event_type, status="failed", reason=str(exc), error_type=exc.__class__.__name__, **base)
            self.save()
            return False
