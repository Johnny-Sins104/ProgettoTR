# Prompt 29.3 Telegram .env hotfix

Fix mirato: `trading_bot/config.py` ora carica `.env` tramite `python-dotenv` prima che la classe `Config` legga `os.getenv(...)`.

Problema osservato:
- `.env` era leggibile con `load_dotenv()` manuale;
- `trading_bot.config` non caricava `.env` da solo;
- `Config.TELEGRAM_TOKEN` e `Config.TELEGRAM_CHAT_ID` restavano vuoti;
- Telegram rimaneva disabled.

Validazione attesa:

```powershell
python -c "from trading_bot.config import Config; print(Config.TELEGRAM_TOKEN[:8] if Config.TELEGRAM_TOKEN else None); print(Config.TELEGRAM_CHAT_ID); print(Config.TELEGRAM_ALLOWED_USER_IDS)"
```

Output atteso:

```text
prime_8_del_token
5439298818
5439298818
```
