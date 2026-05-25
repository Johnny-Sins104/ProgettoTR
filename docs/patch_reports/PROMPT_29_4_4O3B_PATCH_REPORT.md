# Patch Report — Prompt 29.4.4o-3b

## 1. Scope

Patch micro-incrementale sopra `29.4.4o-3` per chiudere due gap di visibilità console:

1. completare il footer `--once` con `positions_opened_by_bridge`;
2. aggiungere log intermedi di avanzamento fetch/evaluation per evitare che il bot sembri bloccato dopo il caricamento del registry modelli.

La patch è esclusivamente console/output. Non modifica gate, rischio, routing, broker, ordini, posizioni, live o testnet.

## 2. File modificati

- `trading_bot/core/paper_once_console_summary.py`
- `trading_bot/core/paper_once_runner_footer.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/test_paper_once_console_summary.py`
- `trading_bot/test_paper_once_runner_footer.py`

## 3. Footer completion

Il footer console ora include:

```text
positions_opened_by_bridge=0
```

quando il routing bridge è presente nel summary. Il prompt stampato dal footer è aggiornato a:

```text
prompt=29.4.4o-3b
```

Sono stati aggiunti fallback più espliciti per flag safety e modalità audit-only:

```text
live_allowed=false
testnet_allowed=false
exchange_broker_allowed=false
orders_submitted_by_bridge=0
positions_opened_by_bridge=0
```

## 4. Progress visibility

Nel path `PaperTradingEngine.evaluate_symbol()` sono stati aggiunti log console flush-only:

```text
[FETCH START] symbol=BTC/USDT timeframe=5m limit=500
[FETCH DONE] symbol=BTC/USDT candles=... elapsed_seconds=...
[EVALUATE START] symbol=BTC/USDT
[EVALUATE DONE] symbol=BTC/USDT side=... signal=... map_score=... structure_state=... elapsed_seconds=...
[FETCH ERROR] symbol=BTC/USDT error_type=... elapsed_seconds=...
[EVALUATE ERROR] symbol=BTC/USDT error_type=... elapsed_seconds=...
```

I log sono attivi di default solo nei run `--once`. È possibile forzarli o disattivarli con:

```cmd
set PAPER_ONCE_PROGRESS_LOGS=1
set PAPER_ONCE_PROGRESS_LOGS=0
```

## 5. Sicurezza invariata

La patch non cambia:

```text
NO gate changes
NO risk changes
NO signal logic changes
NO map_score threshold changes
NO structure_state logic changes
NO confirmation gate changes
NO routing behavior changes
NO broker behavior changes
NO paper order behavior changes
NO live enablement
NO testnet enablement
NO exchange broker enablement
NO automatic activation
NO order submission
NO position opening
NO forced trade
```

Stato atteso invariato:

```text
operational_unlock_allowed=false
automatic_activation_allowed=false
live_allowed=false
testnet_allowed=false
exchange_broker_allowed=false
orders_submitted=0
positions_opened=0
orders_submitted_by_bridge=0
positions_opened_by_bridge=0
risk_per_trade_pct=0.0025
max_positions=1
```

## 6. Test eseguiti

```cmd
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_guarded_enable.py
python trading_bot\test_paper_unlock_final_enable_preflight.py
python trading_bot\test_paper_unlock_manual_activation_patch.py
python trading_bot\test_paper_unlock_manual_switch_preflight.py
python -m compileall -q trading_bot
```

Esito sandbox: PASS.

## 7. Validazione locale consigliata

```cmd
cd C:\Users\Davide\Desktop\ProgettoTR-main
python trading_bot\run_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once --paper-unlock > console_once_test.txt 2>&1
type console_once_test.txt
findstr /n /C:"[FETCH START]" console_once_test.txt
findstr /n /C:"[PAPER CYCLE COMPLETED]" console_once_test.txt
findstr /n /C:"positions_opened_by_bridge=0" console_once_test.txt
findstr /n /C:"[PAPER ONCE RESULT]" console_once_test.txt
python trading_bot\run_paper_unlock_runtime_audit.py
python trading_bot\run_paper_unlock_routing_bridge.py
```

Atteso:

```text
runtime_audit_events=4
routing_bridge_events=4
would_submit_count=0
orders_submitted=0
positions_opened=0
orders_submitted_by_bridge=0
positions_opened_by_bridge=0
status=PASS
```
