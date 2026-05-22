# Prompt 29.4.1a — Telegram proactive operations monitor hardening

Data patch: 2026-05-22

## Obiettivo

Rendere Telegram una console operativa dinamica per il paper trading senza modificare la strategia, senza forzare segnali e senza abilitare live reale.

## File modificati

```text
.env.example
trading_bot/config.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_position_monitor.py
trading_bot/core/telegram_control.py
```

## File aggiunti

```text
trading_bot/core/telegram_proactive.py
docs/patch_reports/PROMPT_29_4_1A_PATCH_REPORT.md
```

## Runtime files nuovi/aggiornati

```text
data/telegram_proactive_state.json
data/telegram_audit.jsonl
data/paper_status.json
data/paper_position_monitor.json
```

## Implementazioni

- `TelegramProactiveNotifier` con stato persistente, deduplica e limite messaggi/minuto.
- Notifica startup `TELEGRAM_STARTUP_NOTIFICATION`.
- Notifica shutdown `TELEGRAM_SHUTDOWN_NOTIFICATION` su CTRL+C/shutdown richiesto.
- Notifiche dedicate per signal/order/position open/position monitor/TP/SL/close/drift/summary.
- Monitor Telegram ora usa lo stesso layout operativo completo del monitor console.
- `/monitor` aggiunto anche all'help/read-only command set.
- `paper_status.json` include stato proattivo, ultimo tipo notifica, ultimo timestamp e path stato.
- `/report` include ultima notifica e stato monitor active/flat.

## Configurazione aggiunta

```env
TELEGRAM_NOTIFY_ON_START=1
TELEGRAM_NOTIFY_ON_SHUTDOWN=1
TELEGRAM_NOTIFY_ON_TP_SL=1
TELEGRAM_NOTIFY_POSITION_EVERY_SECONDS=300
TELEGRAM_PROACTIVE_DEDUP_SECONDS=30
TELEGRAM_PROACTIVE_MAX_MESSAGES_PER_MINUTE=10
```

## Sicurezza

- `ExchangeBrokerAdapter` resta uno stub bloccato.
- `mode=live` non viene introdotto.
- Nessuna API key reale viene usata.
- Nessuna soglia strategica viene modificata.
- Nessun segnale viene forzato.
- Nessun risk parameter viene aumentato.

## Validazione tecnica eseguita

```text
python -m py_compile trading_bot/core/telegram_proactive.py trading_bot/core/telegram_control.py trading_bot/core/paper_position_monitor.py trading_bot/core/paper_engine.py trading_bot/config.py trading_bot/run_paper_trading.py
```

Risultato: OK.

È stato anche eseguito uno smoke test isolato del notifier per verificare:

```text
- primo invio -> sent
- secondo invio identico entro dedup window -> skipped/dedup
- stato persistente aggiornato
```

## Validazione runtime richiesta sul PC operativo

### Test 1 — once

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once
```

Atteso:

```text
- console pulita
- Telegram invia PAPER BOT STARTED
- telegram_audit.jsonl contiene TELEGRAM_STARTUP_NOTIFICATION
- paper_status.json contiene telegram_proactive_state_path
```

### Test 2 — loop + CTRL+C

```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --poll-seconds 300
```

Poi CTRL+C.

Atteso:

```text
- shutdown pulito
- Telegram invia PAPER BOT STOPPED
- telegram_audit.jsonl contiene TELEGRAM_SHUTDOWN_NOTIFICATION
```

### Test 3 — comandi manuali

```text
/status
/report
/monitor
/positions
```

Atteso: tutti rispondono; rate limit e audit restano attivi.

### Test 4 — live ancora bloccato

```cmd
type data\exchange_broker_adapter_stub.json
```

Atteso:

```text
live_execution_enabled=false
status=BLOCKED_DESIGN_STUB
```

## Nota operativa

Il monitor completo BUY/SELL viene inviato automaticamente solo quando esiste una posizione aperta. Se il sistema è flat, `/monitor` continuerà correttamente a rispondere:

```text
No open paper positions.
```
