# Prompt 29.4.2a — Historical signal diagnostics backfill

Data patch: 2026-05-22

## Obiettivo

Usare i vecchi eventi `NO_SIGNAL` presenti in `data/paper_events.jsonl` per costruire una diagnostica storica stimata, separata dalla diagnostica esatta introdotta in 29.4.2.

## File modificati

- `trading_bot/core/paper_signal_diagnostics.py`
- `trading_bot/core/paper_engine.py`
- `trading_bot/core/paper_performance.py`
- `trading_bot/config.py`
- `trading_bot/run_paper_trading.py`
- `.env.example`

## File generato

- `data/paper_signal_diagnostics_backfill_report.json`

## Sicurezza

La patch è diagnostic-only:

- non cambia strategia;
- non abbassa soglie operative;
- non forza segnali;
- non apre ordini;
- non modifica risk sizing;
- non abilita live reale;
- `PAPER_ENTRY_UNLOCK_ENABLED` resta `0`.

## Metodo

Il report separa:

- `exact_diagnostics`: eventi `SIGNAL_DIAGNOSTIC` nuovi;
- `inferred_diagnostics`: eventi `NO_SIGNAL` legacy ricostruiti euristicamente;
- `combined_diagnostics`: esatto + stimato.

I vecchi eventi non contengono tutti i campi della 29.4.2, quindi il backfill viene marcato con:

```text
inference_method = legacy_no_signal_heuristic
inferred = true
exact = false
```

## Validazione consigliata

```cmd
python trading_botun_paper_trading.py --mode paper --timeframe 5m --cost-model conservative --once

type data\paper_signal_diagnostics_backfill_report.json
type data\paper_performance_report.json
type data\paper_status.json
```

## Lettura del report

Il report serve per decidere se il blocco storico è concentrato su:

- `TECH_SCORE_LOW`;
- `META_PROB_LOW`;
- `SETUP_QUALITY_LOW`;
- `POST_META_FILTERED`;
- `NO_TECHNICAL_CANDIDATE`.

Solo dopo questa analisi si potrà decidere se creare una patch paper-only di unlock conservativo. Nessun unlock viene introdotto qui.
