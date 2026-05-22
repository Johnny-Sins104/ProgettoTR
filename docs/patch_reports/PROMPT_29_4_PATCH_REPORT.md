# PROMPT 29.4 — Paper-to-live execution adapter design + 29.4a Paper position monitor

Data patch: 2026-05-22

## Obiettivo

Separare il paper broker dall'engine tramite un'interfaccia comune e reintrodurre il vecchio monitor operativo posizione in modalità paper-safe.

Il live reale resta esplicitamente bloccato.

## File aggiunti

```text
trading_bot/core/broker_adapter.py
trading_bot/core/paper_position_monitor.py
docs/patch_reports/PROMPT_29_4_PATCH_REPORT.md
```

## File modificati

```text
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
```

## Nuove astrazioni

```text
BrokerAdapter
PaperBrokerAdapter
ExchangeBrokerAdapter
AccountSnapshot
PositionSnapshot
OrderSnapshot
ExecutionSnapshot
LiveExecutionBlocked
```

Metodi standardizzati:

```text
get_balance()
get_positions()
place_order()
cancel_order()
close_position()
fetch_open_orders()
reconcile()
```

## PaperBrokerAdapter

Il paper engine ora espone l'esecuzione paper attraverso `PaperBrokerAdapter`.

La logica strategica non viene modificata:

```text
DecisionEngine -> signal -> PaperBrokerAdapter.place_order() -> PaperBroker.place_market_order()
```

## ExchangeBrokerAdapter

`ExchangeBrokerAdapter` è uno skeleton architetturale bloccato.

Ogni metodo operativo solleva:

```text
LiveExecutionBlocked
```

Viene generato anche:

```text
data/exchange_broker_adapter_stub.json
```

per indicare che l'adapter exchange è presente ma non operativo.

## Paper position monitor

Nuovo file runtime:

```text
data/paper_position_monitor.json
```

Nuovo output console quando ci sono posizioni aperte:

```text
📈 PAPER POSITION MONITOR
==============================
Symbol   : BTC/USDT
Direzione: SELL/SHORT
Motivo   : Score -39 | RANGING
Ingresso : 77018.46 USDT
Attuale  : 77114.20 USDT
Size     : 0.008815
Margine  : 67.89 USDT-equivalent
==============================
TP1      : ... ⏳ PENDING
TP2      : ... ⏳ PENDING
SL       : ... ⏳ ARMED
==============================
PnL Att. : -0.84 USDT (-1.24%)
Equity   : 999.16 USDT-equivalent
==============================
```

Nota: TP1 è display-only, calcolato come midpoint tra ingresso e TP finale. L'esecuzione paper resta a TP singolo fino a quando non verranno introdotte uscite parziali/staged exits.

## Telegram

`/positions` ora usa il monitor paper dettagliato.

Aggiunto alias:

```text
/monitor
```

## Dashboard

`data/paper_dashboard.html` include una sezione nuova:

```text
Open Position Monitor
```

Il report performance ora legge anche:

```text
data/paper_position_monitor.json
```

## Status file

`data/paper_status.json` include ora:

```json
"broker_adapter": {
  "active": "PaperBrokerAdapter",
  "exchange_stub": "ExchangeBrokerAdapter",
  "live_execution_enabled": false,
  "reconciliation_status": "PASS"
}
```

## Validazione sandbox

Eseguito:

```text
python -m py_compile trading_bot/core/broker_adapter.py trading_bot/core/paper_position_monitor.py trading_bot/core/paper_engine.py trading_bot/core/paper_performance.py
```

Risultato:

```text
OK
```

Smoke test adapter:

```text
PaperBrokerAdapter.reconcile() -> PASS
ExchangeBrokerAdapter.get_balance() -> LiveExecutionBlocked
PaperPositionMonitor empty -> No open paper positions.
```

## Comandi di validazione runtime

```powershell
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once

type data\paper_status.json
type data\paper_position_monitor.json
type data\exchange_broker_adapter_stub.json
```

Poi:

```powershell
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --poll-seconds 60
```

Da Telegram:

```text
/status
/positions
/monitor
/report
```

## Stato live reale

```text
LIVE REAL MONEY EXECUTION: BLOCKED
TESTNET: not implemented yet
NEXT STEP: 30.0 — Live execution sandbox / testnet
```
