# Patch Report — Prompt 29.4.4o-3

## 1. Bug osservato
Durante l'esecuzione del trading bot in modalità paper trading temporaneo con l'opzione `--once`:
```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock
```
il ciclo operativo veniva completato e registrato con successo nel database degli eventi (`data/paper_events.jsonl`), ma la console non stampava il footer terminale finale atteso:
```text
[PAPER CYCLE COMPLETED]
...
[PAPER ONCE RESULT] NO_SIGNAL
```
Il problema si verificava sia a livello di console standard sia reindirizzando l'output su un file di log (`> console_once_test.txt 2>&1`).

## 2. Causa probabile
Nel path operativo reale del runner, a causa dell'abrupt termination o del flushing asincrono gestito dal loop di `asyncio`, il footer stampato da `PaperTradingEngine._finish_cycle()` non raggiungeva lo standard output (stdout) prima che il processo venisse terminato dal gestore principale in `run_paper_trading.py`.

## 3. Soluzione implementata
È stato introdotto un meccanismo di **fallback runner-level** robusto all'interno del gestore principale:
1. All'avvio del comando in `run_paper_trading.py`, viene registrato il timestamp di inizio (`started_at`).
2. Nel blocco `finally`, se l'argomento `--once` è attivo, il sistema verifica se il footer console è già stato stampato dall'engine controllando la proprietà `paper_once_console_summary_printed`.
3. In caso contrario, viene invocata la funzione `print_runner_once_footer_from_events()` del nuovo modulo `core/paper_once_runner_footer.py`.
4. Questa funzione legge e decodifica in modo sicuro l'ultimo evento `CYCLE_COMPLETED` registrato in `data/paper_events.jsonl` generato dopo `started_at`, escludendo eventi obsoleti.
5. Ricostruisce il summary completo integrando anche i dati diagnostici degli eventi `GUARDED_PAPER_RUNTIME_AUDIT` e `GUARDED_PAPER_ROUTING_BRIDGE_AUDIT` relativi allo stesso `cycle_id` per compilare in console tutte le statistiche di routing e di audit.
6. La funzione `print_paper_once_console_summary` è stata modificata in `core/paper_once_console_summary.py` per stampare con `flush=True` in modo deterministico su stdout (o stream personalizzato) ed includere i campi `prompt` e `footer_source`.

## 4. File modificati e nuovi
* **Nuovo file:** `trading_bot/core/paper_once_runner_footer.py` (modulo di fallback per il footer).
* **Nuovo file:** `trading_bot/test_paper_once_runner_footer.py` (suite di test unitari completi).
* **Modificato:** `trading_bot/core/paper_once_console_summary.py` (hardenizzazione e supporto prompt/footer_source).
* **Modificato:** `trading_bot/core/paper_engine.py` (esposizione proprietà di avvenuta stampa).
* **Modificato:** `trading_bot/run_paper_trading.py` (runner principale con integrazione nel blocco `finally`).
* **Nuovo file:** `docs/patch_reports/PROMPT_29_4_4O3_PATCH_REPORT.md` (questo report).
* **Nuovo file:** `trading_bot/docs/patch_reports/PROMPT_29_4_4O3_PATCH_REPORT.md` (copia del report).

## 5. Test eseguiti
La suite di validazione ha dato esito positivo al 100%:
1. Esecuzione dei nuovi test unitari (`test_paper_once_runner_footer.py`) che coprono:
   * Stampa dell'ultimo `CYCLE_COMPLETED`.
   * Integrazione dei conteggi di runtime audit (`runtime_audit_events`, `runtime_accepts_diagnostic`, `runtime_rejects`).
   * Integrazione dei conteggi di routing bridge (`would_route_count`, `would_submit_count`, `orders_submitted_by_bridge`).
   * Rifiuto di cicli precedenti a `started_at`.
   * Tolleranza a righe corrotte nel file JSONL.
   * Gestione del file di eventi assente.
2. Superamento di tutti i test di regressione:
   * `test_paper_once_console_summary.py` -> PASS
   * `test_paper_once_runner_footer.py` -> PASS
   * `test_paper_unlock_routing_bridge.py` -> PASS
   * `test_paper_unlock_runtime_audit.py` -> PASS
   * `test_paper_unlock_guarded_enable.py` -> PASS
   * `test_paper_unlock_final_enable_preflight.py` -> PASS
   * `test_paper_unlock_manual_activation_patch.py` -> PASS
   * `test_paper_unlock_manual_switch_preflight.py` -> PASS
3. Compilazione globale del codice (`compileall`) senza alcun errore.

## 6. Sicurezza invariata
I vincoli di sicurezza assoluti sono stati rigorosamente rispettati:
* `operational_unlock_allowed = false`
* `automatic_activation_allowed = false`
* `live_allowed = false`
* `testnet_allowed = false`
* `exchange_broker_allowed = false`
* `orders_submitted = 0`
* `positions_opened = 0`
* `orders_submitted_by_bridge = 0`
* `positions_opened_by_bridge = 0`
* `risk_per_trade_pct = 0.0025`
* `max_positions = 1`

## 7. Istruzioni Windows corrette per validazione
1. Eseguire il comando con reindirizzamento:
```cmd
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1
```
2. Verificare la presenza del footer terminale completo:
```cmd
findstr /n /C:"[PAPER CYCLE COMPLETED]" console_once_test.txt
findstr /n /C:"[PAPER ONCE RESULT]" console_once_test.txt
```
3. Esito atteso:
```text
status = PASS
decision = PAPER_ONCE_RUNNER_FOOTER_READY
footer_source = runner_event_fallback oppure engine
orders_submitted = 0
positions_opened = 0
orders_submitted_by_bridge = 0
positions_opened_by_bridge = 0
operational_unlock_allowed = false
```
