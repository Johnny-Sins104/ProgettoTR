# Prompt 29.4.4s-1 — Signal/Risk Correctness Hardening

## Scope

Patch correttiva prima di ogni avanzamento verso 29.4.4t o execution reale. La patch risolve e/o mette in guardrail i problemi emersi dagli audit su pattern candle, probabilità/calibrazione, Kelly sizing, VaR, commissioni, I/O JSONL e profili hardcoded.

## Safety

- Nessuna abilitazione live.
- Nessuna abilitazione testnet.
- Nessun exchange broker.
- Nessun abbassamento soglie operativo per forzare trade.
- Nessuna riattivazione del legacy execution path.
- Probability compression diagnostic è solo diagnostico.

## Fix implementati

1. `candlestick_patterns.py`
   - Pin-bar/Hammer/Shooting Star ora richiedono wick opposta ridotta.
   - High Wave / Long-Legged Doji viene neutralizzato.
   - Engulfing richiede vero body engulfing con moltiplicatore 1.05.
   - Inside bar default senza tolleranza.
   - Outside bar direzionale richiede chiusura nel terzo corretto del range.
   - Morning/Evening Star richiedono prima candela strong-body.
   - Three-bar reversal richiede chiusura oltre l'apertura della candela precedente.
   - Fake breakdown/reclaim richiede apertura dal lato corretto del livello.
   - Retest hold/reject richiede breakout immediatamente precedente e reazione direzionale.
   - Se bullish e bearish coesistono, il bias diventa HOLD e lo score viene capped a 15.
   - Volume ratio esclude la candela corrente dalla media storica.

2. `calibration.py`
   - Min samples conservativi: isotonic 300, sigmoid 50.

3. `risk.py`
   - Se Kelly è attivo e non trova edge positivo, rischio finale = 0 e size = 0.
   - Il fallback a rischio profilo resta solo quando Kelly è disabilitato esplicitamente.
   - Commission-aware sizing usa default taker coerente con PaperBroker (`Config.COMMISSION_RATE * 2`).

4. `paper_unlock_gate.py`
   - Rimosso hardcode su `BTC_ONLY_40_Q60`.
   - Il profilo configurato non viene più rigettato solo per nome.

5. `portfolio_risk_engine.py`
   - Il flag `VAR_LIMIT_EXCEEDED` usa il VaR corrente dello snapshot, non `self.snapshots[-1]`.

6. `main.py`, `multi_trade_manager.py`, `genetic_opt.py`
   - Le commissioni di uscita usano il prezzo effettivo di uscita, non l'entry price.

7. `setup_engine.py`
   - `near_sr` non attiva più simultaneamente supporto e resistenza; discrimina con `bb_position`.

8. `ai_engine.py`
   - Auto-retrain non dipende più da `lines % AI_RETRAIN_EVERY == 0`; usa delta dall'ultimo retrain.

9. JSONL I/O
   - Aggiunto `core/jsonl_utils.py` con lettura tail bounded.
   - Aggiornati i principali moduli `paper_unlock_*` e leakage/footer per evitare `read_text().splitlines()` su file intero.

10. Probability compression diagnostic
   - Aggiunti `core/probability_compression_diagnostic.py` e `run_probability_compression_diagnostic.py`.
   - Segnala il caso `cost_aware_pass > 0`, `meta_accepted = 0`, `max_p_cal <= gate_min_probability`.
   - Non modifica soglie e non forza trade.

## Test aggiunti

- `test_signal_risk_correctness_hardening.py`
- `test_runtime_risk_io_hardening.py`
- `test_probability_compression_diagnostic.py`

## Validazione sandbox

Passati:

```cmd
python trading_bot\test_signal_risk_correctness_hardening.py
python trading_bot\test_runtime_risk_io_hardening.py
python trading_bot\test_probability_compression_diagnostic.py
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python -m compileall -q trading_bot
```

Non eseguito in sandbox:

```cmd
python trading_bot\run_custom_backtest.py --balance 100 --candles 20000
```

Motivo: ambiente sandbox privo di `pandas_ta`.

## Validazione locale richiesta

```cmd
cd C:\Users\Davide\Desktop\ProgettoTR-main
python -m compileall -q trading_bot
python trading_bot\test_signal_risk_correctness_hardening.py
python trading_bot\test_runtime_risk_io_hardening.py
python trading_bot\test_probability_compression_diagnostic.py
python trading_bot\test_paper_order_leakage_guard.py
python trading_bot\test_paper_unlock_runtime_audit.py
python trading_bot\test_paper_unlock_routing_bridge.py
python trading_bot\test_paper_unlock_candidate_audit.py
python trading_bot\test_paper_unlock_handoff_dry_run.py
python trading_bot\test_paper_unlock_observation.py
python trading_bot\test_paper_once_console_summary.py
python trading_bot\test_paper_once_runner_footer.py
python trading_bot\run_probability_compression_diagnostic.py
```

Poi rieseguire 20k:

```cmd
python trading_bot\run_custom_backtest.py --balance 100 --candles 20000
copy /Y data\signal_density_report.json data\signal_density_20k_after_s1.json
python trading_bot\run_probability_compression_diagnostic.py
```

## Decisione

Dopo installazione questa patch deve essere considerata una correzione qualità/rischio, non un avanzamento verso execution. Non procedere a 29.4.4t finché 20k/50k/100k e observation paper risultano coerenti.
