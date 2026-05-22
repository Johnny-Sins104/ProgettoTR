# Prompt 29.3 — Telegram operational control hardening

Data patch: 2026-05-22

## Obiettivo

Rendere Telegram una console operativa sicura per il paper engine, senza abilitare live reale.

## File modificati

```text
trading_bot/core/telegram_control.py
trading_bot/core/paper_engine.py
trading_bot/config.py
.env.example
```

## Nuovo file runtime

```text
data/telegram_audit.jsonl
```

## Sicurezza implementata

### Allowlist utenti

Variabile:

```text
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
```

Default sicuro:

```text
TELEGRAM_REQUIRE_ALLOWED_USER_IDS=1
```

Se Telegram è abilitato ma l'utente non è in allowlist, il comando viene rifiutato e auditato.

### Audit comandi

Ogni comando genera record JSONL:

```text
TELEGRAM_COMMAND_RECEIVED
TELEGRAM_COMMAND_REJECTED
TELEGRAM_COMMAND_COMPLETED
TELEGRAM_COMMAND_FAILED
TELEGRAM_POLLING_STARTED
TELEGRAM_POLLING_CANCELLED
TELEGRAM_POLLING_ERROR
TELEGRAM_SEND_FAILED
```

### Rate limit

Variabile:

```text
TELEGRAM_RATE_LIMIT_SECONDS=3
```

Default: 3 secondi per utente.

### Read-only mode

Variabile:

```text
TELEGRAM_READ_ONLY=0
```

Se impostata a `1`, blocca:

```text
/pause
/resume
/kill
```

e lascia attivi:

```text
/status
/pnl
/positions
/orders
/risk
/report
/help
```

### Comandi critici

`/kill` senza conferma non agisce.

Serve:

```text
/kill confirm
```

Effetti:
- kill switch persistente;
- engine in pausa;
- chiusura posizioni paper aperte al last known price;
- blocco nuovi ordini;
- audit Telegram;
- evento paper `TELEGRAM_KILL_CONFIRMED`.

## Comandi supportati

```text
/status
/pnl
/positions
/orders
/risk
/pause
/resume
/kill confirm
/report
/help
```

## Eventi paper aggiunti

```text
TELEGRAM_PAUSE_REQUESTED
TELEGRAM_RESUME_REQUESTED
TELEGRAM_KILL_REJECTED
TELEGRAM_KILL_CONFIRMED
```

## Status export aggiornato

`data/paper_status.json` ora include:

```text
telegram_audit_path
telegram_enabled
telegram_read_only
telegram_allowed_user_count
```

## Validazione sandbox

Eseguito:

```text
python -m py_compile trading_bot/core/telegram_control.py trading_bot/core/paper_engine.py trading_bot/config.py
```

Eseguito smoke test locale su:
- utente non autorizzato bloccato;
- utente autorizzato accetta `/status`;
- read-only blocca `/pause`;
- audit file creato.

## Validazione consigliata su Windows

Paper once:

```powershell
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once
```

Verifiche:

```powershell
type data\paper_status.json
type data\telegram_audit.jsonl
```

Se Telegram reale è configurato, impostare `.env`:

```text
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_ALLOWED_USER_IDS=<tuo_numeric_user_id>
TELEGRAM_REQUIRE_ALLOWED_USER_IDS=1
TELEGRAM_READ_ONLY=0
TELEGRAM_RATE_LIMIT_SECONDS=3
```

Poi testare:

```text
/status
/pnl
/positions
/orders
/risk
/report
/pause
/resume
/kill
/kill confirm
```

Nota: `/kill confirm` va testato solo in paper mode.
