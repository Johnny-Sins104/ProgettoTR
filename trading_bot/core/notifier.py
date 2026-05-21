import aiohttp
import asyncio
import json

# Evento globale per segnalare la chiusura da Telegram
telegram_close_event = asyncio.Event()

class Notifier:

    def __init__(
        self,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> None:
        self._token   = telegram_token
        self._chat_id = telegram_chat_id
        self._offset  = 0
        self._polling_task = None

    def send_alert(self, message: str, print_console: bool = True) -> None:
        """Invia su Telegram e, se print_console e' True, stampa a console in un box."""
        if print_console:
            border = "─" * 52
            print(f"\n┌{border}┐")
            for line in message.splitlines():
                print(f"│  {line:<50}│")
            print(f"└{border}┘\n")

        if self._token and self._chat_id:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._send_telegram_async(message))
            except RuntimeError:
                pass

    async def _send_telegram_async(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": message
        }
        async with aiohttp.ClientSession() as session:
            try:
                await session.post(url, json=payload, timeout=5)
            except Exception as e:
                print(f"[NOTIFIER ERROR] Telegram: {e}")

    async def send_interactive_monitor(self, message: str) -> int | None:
        """Invia il monitor con pulsante inline e ritorna il message_id"""
        if not self._token or not self._chat_id:
            return None
            
        escaped = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": f"<pre>{escaped}</pre>",
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text": "❌ Chiudi Posizione (Market)", "callback_data": "close_trade"}
                ]]
            }
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=5) as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return data["result"]["message_id"]
                    else:
                        print(f"[NOTIFIER ERROR] Telegram Send failed: {data}")
            except Exception as e:
                print(f"[NOTIFIER ERROR] Telegram Send Exception: {e}")
        return None

    async def update_interactive_monitor(self, message_id: int, message: str, show_button: bool = True) -> None:
        """Aggiorna il messaggio del monitor esistente."""
        if not self._token or not self._chat_id or not message_id:
            return
            
        escaped = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        url = f"https://api.telegram.org/bot{self._token}/editMessageText"
        payload = {
            "chat_id": self._chat_id,
            "message_id": message_id,
            "text": f"<pre>{escaped}</pre>",
            "parse_mode": "HTML"
        }
        if show_button:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "❌ Chiudi Posizione (Market)", "callback_data": "close_trade"}
                ]]
            }
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=5) as resp:
                    data = await resp.json()
                    if not data.get("ok"):
                        if "message is not modified" not in data.get("description", ""):
                            print(f"[NOTIFIER ERROR] Telegram Edit failed: {data}")
            except Exception as e:
                print(f"[NOTIFIER ERROR] Telegram Edit Exception: {e}")

    async def start_polling(self):
        """Avvia il polling per intercettare i click sui bottoni."""
        if not self._token:
            return
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    payload = {"offset": self._offset, "timeout": 30}
                    async with session.post(url, json=payload, timeout=35) as resp:
                        data = await resp.json()
                        if data.get("ok"):
                            for update in data["result"]:
                                self._offset = update["update_id"] + 1
                                if "callback_query" in update:
                                    cb = update["callback_query"]
                                    if cb.get("data") == "close_trade":
                                        telegram_close_event.set()
                                        cb_url = f"https://api.telegram.org/bot{self._token}/answerCallbackQuery"
                                        await session.post(cb_url, json={"callback_query_id": cb["id"], "text": "Chiusura in corso..."})
                except Exception:
                    pass
                await asyncio.sleep(1)
