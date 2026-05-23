# PROMPT 29.5.0d — Scenario-pattern calibration

Data: 2026-05-23  
Stato: implementata come patch diagnostica-only.

## Obiettivo

Calibrare il layer `scenario + candlestick pattern` introdotto con 29.5.0a/29.5.0b e validato in 29.5.0c, senza aumentare operatività.

La patch genera:

```text
data/scenario_pattern_calibration_report.json
```

## File aggiunti

```text
trading_bot/core/scenario_pattern_calibration.py
trading_bot/run_scenario_pattern_calibration.py
trading_bot/test_scenario_pattern_calibration.py
docs/patch_reports/PROMPT_29_5_0D_PATCH_REPORT.md
```

## File aggiornati

```text
trading_bot/config.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/run_paper_trading.py
```

## Cosa fa il nuovo modulo

`core/scenario_pattern_calibration.py`:

- rilegge i parquet storici come 29.5.0c;
- ricalcola scenario e pattern in modo causale;
- valuta il forward outcome con la stessa logica shadow;
- classifica i bucket per `asset + side + scenario`;
- calcola expectancy, win rate, loss rate, TP1, TP2, SL e TIME_EXIT;
- calcola distribuzione `pattern_score`;
- testa soglie `pattern_score >= 50/55/60/65/70`;
- applica filtro conflitti pattern;
- applica filtro range position:
  - BUY support/rejection: `range_pos_400 <= 0.40`;
  - SELL resistance/rejection: `range_pos_400 >= 0.60`;
- produce un candidato non operativo `BTC_BUY_REJECTION_PATTERN_CONFIRMED` solo se i gate statistici passano;
- non apre ordini e non modifica soglie operative.

## Decisioni possibili

```text
KEEP_DIAGNOSTIC
CALIBRATED_PROFILE_CANDIDATE
DO_NOT_USE_PATTERNS
```

Anche in caso di `CALIBRATED_PROFILE_CANDIDATE`, il profilo resta non operativo e richiede ancora 29.5.0e/29.5.0f prima di qualunque paper unlock refinement.

## Profilo candidato monitorato

```text
name = BTC_BUY_REJECTION_PATTERN_CONFIRMED
asset = BTC/USDT
side = BUY
scenario = BUY_REJECTION_CANDIDATE
pattern_bias = BUY
pattern_alignment = PATTERN_SCENARIO_ALIGNED
pattern_score_min = soglia calibrata
exclude_conflicting_bearish_patterns = true
range_pos_400 <= 0.40
no_orders = true
no_live = true
no_testnet = true
```

## Sicurezza

La patch dichiara nel report:

```json
{
  "diagnostic_only": true,
  "opens_orders": false,
  "changes_thresholds": false,
  "changes_paper_unlock_profile": false,
  "enables_live_or_testnet": false,
  "operational_unlock_allowed": false
}
```

## Comando standalone

Da root progetto:

```cmd
python trading_bot\run_scenario_pattern_calibration.py
```

Da `trading_bot/`:

```cmd
python run_scenario_pattern_calibration.py
```

## Comando test

```cmd
cd trading_bot
python test_scenario_pattern_calibration.py
```

## Nota sul sandbox

Nel sandbox di consegna non era disponibile il motore parquet (`pyarrow`/`fastparquet`). Il codice è stato quindi validato con test sintetico e il report presente in `data/` è stato generato tramite fallback dal riepilogo 29.5.0c. Nel tuo ambiente locale, dove il progetto richiede `pyarrow>=15.0.0`, riesegui il comando standalone per ottenere la calibrazione completa con soglie `pattern_score` e filtri range/conflitto calcolati dai parquet.

## Esito report incluso

Il report incluso risulta:

```text
status = WARN
decision = KEEP_DIAGNOSTIC
historical_candidates = 5713
runtime_aligned_rows = 13
candidate_profile = BTC_BUY_REJECTION_PATTERN_CONFIRMED, non operativo
```

Motivo: il fallback conferma il bucket BTC positivo già visto in 29.5.0c, ma non può approvare il profilo perché mancano replay dettagliato, soglie pattern_score e filtri conflitto/range calcolati dai parquet.

## Prossima patch

```text
29.5.0e — Liquidity + supply/demand + structure break engine
```

Dopo 29.5.0e servirà:

```text
29.5.0f — Calibrated scenario-pattern-structure shadow review
```
