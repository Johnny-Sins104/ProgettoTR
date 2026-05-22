# Prompt 29.1 — Paper reconciliation + lifecycle hardening

Data patch: 2026-05-22

## Obiettivo

Rendere il paper engine più affidabile ciclo dopo ciclo, soprattutto su:

- shutdown pulito da `CTRL+C`;
- restart recovery;
- lifecycle report persistente;
- reconciliation tra state/events/status;
- gestione errori fetch per singolo simbolo;
- chiusura risorse async ccxt/aiohttp.

## File modificati / aggiunti

```text
trading_bot/core/paper_lifecycle.py      # NUOVO
trading_bot/core/paper_engine.py         # MODIFICATO
trading_bot/core/paper_broker.py         # MODIFICATO
trading_bot/core/client.py               # MODIFICATO
trading_bot/run_paper_trading.py         # MODIFICATO
```

## Implementazioni principali

### 1. Lifecycle report

Aggiunto nuovo output runtime:

```text
data/paper_lifecycle_report.json
```

Contiene:

- cicli avviati/completati/interrotti;
- eventi per tipo;
- eventi per ciclo;
- max cycle sequence;
- duplicate cycle id;
- duplicate cycle sequence;
- ordini nello state;
- ordini submitted/filled/rejected da eventi;
- posizioni open/closed;
- mismatch state/status/events;
- status finale `PASS`, `WARN` o `FAIL`.

### 2. Reconciliation state/events/status

Il modulo `core.paper_lifecycle` legge:

```text
data/paper_state.json
data/paper_events.jsonl
data/paper_status.json
```

e verifica:

- posizioni aperte nello state con evento di apertura;
- posizioni chiuse nello state con evento di chiusura;
- ordini filled con evento fill;
- balance coerente tra state e status;
- numero posizioni aperte coerente tra state e status;
- cicli interrotti;
- sequenze ciclo duplicate;
- JSON corrotti/non leggibili.

### 3. Restart recovery

All'avvio il paper engine ora:

- carica `paper_state.json` se presente;
- ripristina balance, orders, positions, pause e kill switch;
- calcola il prossimo cycle counter leggendo `paper_events.jsonl`;
- logga:

```text
STATE_RESTORED
RECOVERY_COMPLETED
```

### 4. Shutdown pulito

`PaperTradingEngine.run()` ora gestisce `asyncio.CancelledError` e registra:

```text
SHUTDOWN_REQUESTED
ASYNC_TASK_CANCELLED
ENGINE_STOPPED
```

`run_paper_trading.py` sopprime il traceback finale da `KeyboardInterrupt`, lasciando al motore la responsabilità di salvare state/status/report.

Output previsto su interruzione:

```text
[PaperEngine] Shutdown requested. Closing exchange sessions...
[PaperEngine] Engine stopped cleanly.
```

### 5. Chiusura risorse async ccxt/aiohttp

`core/client.py` ora protegge `exchange.close()` con `asyncio.shield()` e `contextlib.suppress(...)`, così la chiusura viene tentata anche durante cancellazione task.

Il paper engine logga:

```text
EXCHANGE_CLIENT_CLOSED
```

su successo, errore o cancellazione.

### 6. Fetch error per simbolo

`evaluate_symbol()` ora mantiene il loop vivo in caso di errore singolo simbolo:

```text
SYMBOL_ERROR
```

Output console:

```text
[PaperEngine] Symbol error | ETH/USDT | <errore> | skipped
```

Il ciclo continua con gli altri asset.

### 7. Event naming più coerente

Il broker ora usa eventi uppercase coerenti:

```text
PAPER_ORDER_SUBMITTED
ORDER_FILLED
POSITION_OPENED
POSITION_CLOSED
```

mantenendo compatibilità logica con il lifecycle report.

## Validazione eseguita in sandbox

Ambiente sandbox privo del pacchetto `ccxt`, quindi il comando runtime completo non può essere eseguito qui.

Eseguiti con successo:

```bash
python -m py_compile trading_bot/core/paper_engine.py trading_bot/core/paper_broker.py trading_bot/core/paper_lifecycle.py trading_bot/core/client.py trading_bot/run_paper_trading.py
```

Eseguito con successo il lifecycle report sui file runtime presenti nello zip:

```bash
PYTHONPATH=trading_bot python - <<'PY'
from core.paper_lifecycle import write_lifecycle_report
r = write_lifecycle_report('data')
print(r['status'])
print(r['cycles'])
print(r['reconciliation'])
PY
```

Risultato sul runtime incluso nello zip:

```text
status: WARN
cycles.started: 6
cycles.completed: 5
cycles.interrupted: 1
warnings:
- interrupted_cycles_detected: ['pc_000005_6e68c5a5']
- duplicate_cycle_sequence: [1]
```

Questo è coerente con lo stato precedente: c'era già un'interruzione sporca/riavvio senza recovery formale. Dopo questa patch, i prossimi run dovrebbero continuare dal max cycle sequence e produrre report più coerenti.

## Comandi di validazione consigliati su Windows

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once

type data\paper_lifecycle_report.json
```

Poi test loop + CTRL+C:

```powershell
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --poll-seconds 60
```

Interrompere con `CTRL+C`.

Target atteso:

```text
nessun traceback sporco
ENGINE_STOPPED in paper_events.jsonl
SHUTDOWN_REQUESTED in paper_events.jsonl
paper_lifecycle_report.json creato
status PASS oppure WARN motivato
```
