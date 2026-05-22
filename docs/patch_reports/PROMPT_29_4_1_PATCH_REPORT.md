# PROMPT 29.4.1 — Telegram proactive paper monitoring + clean console

Data: 2026-05-22

## Obiettivo

Rendere il paper engine più adatto a run operative di 4–8 ore:

- console più pulita;
- debug AI disattivato di default;
- notifiche Telegram automatiche su eventi importanti;
- monitor posizione inviato automaticamente quando necessario;
- nessuna modifica alla logica strategica e nessuna abilitazione live reale.

## File modificati

```text
trading_bot/config.py
trading_bot/core/engine.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/run_paper_trading.py
.env.example
docs/patch_reports/PROMPT_29_4_1_PATCH_REPORT.md
```

## Console operativa pulita

Il terminale ora stampa una riga di avvio compatta:

```text
PROGETTOTR PAPER ENGINE | PAPER | 5m | conservative | Telegram ON | Proactive ON | AI debug OFF
assets=BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT poll=300s
```

Ogni ciclo stampa una riga sintetica:

```text
[02:45:00] cycle=15 scanned=4 signals=0 orders=0 pos=0 equity=1000.00 dd=0.00% drift=WARN errors=0
```

I vecchi log ripetitivi:

```text
DEBUG: [AI_HYBRID] ...
```

sono disattivati di default.

## Debug riattivabile

Da CLI:

```powershell
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --poll-seconds 300 --verbose-ai
```

Oppure da `.env`:

```env
PAPER_AI_DEBUG=1
PAPER_CONSOLE_VERBOSE=1
```

## Telegram proattivo

Nuove notifiche automatiche configurabili:

```env
TELEGRAM_PROACTIVE_ENABLED=1
TELEGRAM_NOTIFY_EVERY_CYCLE=0
TELEGRAM_NOTIFY_NO_SIGNAL_EVERY_N_CYCLES=12
TELEGRAM_NOTIFY_POSITION_EVERY_N_CYCLES=1
TELEGRAM_NOTIFY_POSITION_PNL_DELTA_PCT=0.25
TELEGRAM_NOTIFY_ON_SIGNAL=1
TELEGRAM_NOTIFY_ON_ORDER=1
TELEGRAM_NOTIFY_ON_POSITION_OPEN=1
TELEGRAM_NOTIFY_ON_POSITION_CLOSE=1
TELEGRAM_NOTIFY_ON_DRIFT_WARN=1
```

Default scelti per evitare spam:

- non notifica ogni ciclo;
- notifica un summary no-signal ogni 12 cicli;
- notifica subito segnali, ordini, aperture e chiusure posizione;
- notifica monitor posizione quando ci sono posizioni aperte;
- notifica drift WARN/FAIL quando cambia stato.

## Nuovi audit Telegram

Il file:

```text
data/telegram_audit.jsonl
```

può contenere anche:

```text
TELEGRAM_PROACTIVE_NOTIFICATION
```

con `notification_type`, `cycle_seq` e metadati evento.

## Status/report aggiornati

`data/paper_status.json` ora include:

```json
"operational_console": {
  "verbose": false,
  "ai_debug": false,
  "header_every_n_cycles": 12
},
"telegram_proactive": {
  "enabled": true,
  "notify_every_cycle": false,
  "notify_no_signal_every_n_cycles": 12,
  "notify_position_every_n_cycles": 1,
  "notify_position_pnl_delta_pct": 0.25
}
```

`/report` ora mostra anche:

```text
Proactive: True | AI debug: False
```

## Validazione consigliata

Smoke test:

```powershell
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once
```

Run operativo:

```powershell
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --poll-seconds 300
```

Telegram:

```text
/status
/report
/monitor
```

Audit:

```powershell
type data\telegram_audit.jsonl
```

## Note

- Il live reale resta bloccato.
- La strategia non è stata rilassata.
- Questa patch non forza segnali e non aumenta il numero di trade.
- Il tuning della signal density va fatto dopo un run reale paper di 4–8 ore e analisi di `paper_events.jsonl`.
