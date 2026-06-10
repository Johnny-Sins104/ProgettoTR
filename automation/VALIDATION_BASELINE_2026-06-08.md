# Validation Baseline - 2026-06-08

## Verdict

Il progetto non e pronto per trading live e non esiste ancora una dimostrazione
di edge profittevole. I vecchi risultati quantitativi restano evidenza negativa
o insufficiente, ma devono essere rigenerati dopo TR-INT-02B perche diversi
artefatti usano ancora rischio 1% e la precedente pipeline.

## Validated findings

- `data/clean_bot_backtest_btc_clean.json`: PF 0.698, rendimento -26.15%, ma
  artefatto vecchio con `risk_per_trade_pct=0.01`.
- `data/clean_bot_backtest_xrp_clean.json`: PF 1.629 full sample; optimizer
  second-half PF 1.074, evidenza instabile e artefatti vecchi.
- `data/clean_bot_scalping_1m_audit.json`: 0/2673 accettati, artefatto vecchio
  con rischio 1%.
- Nessuna strategia e attualmente approvata per capitale reale.
- Clean backtest e paper usano ora `UnifiedCostModel` e rischio default 0.005.
- Clean optimizer usa ancora un costo flat locale e non `UnifiedCostModel`.
- Backtest usa Open N+1; paper usa Open della barra successivamente osservata,
  ma il feed causale WebSocket/first-observed-price manca ancora.
- `run_phase_3_entry_preflight.py` confronta solo variazioni durante il run e
  monitora 7 file live/paper; non dimostra una baseline pulita preesistente e
  non include `config.py`, `core/client.py` o moduli Telegram modificati.
- L'optimizer usa la seconda meta sia per classificazione sia nel punteggio e
  accetta `second_pf >= 1.00`: non e vero out-of-sample.
- Il report statistico dichiara periodi fino a giugno/agosto 2025, mentre i
  parquet BTC/XRP 5m terminano il 25 aprile 2026.
- Il clean paper runner legge direttamente `os.getenv` e non carica `.env`.
- Working tree corrente all'ultimo audit: 476 cambiamenti, 416 eliminati,
  45 non tracciati, 15 modificati. Serve normalizzazione prima di commit/live.
- La frase "Fase 3B pronta" e la stima "40%" non sono dimostrate da un gate
  eseguibile corrente.

## Resolved or superseded findings

- Il rischio default clean backtest/paper e ora 0.005.
- Clean backtest e paper instradano i costi tramite `UnifiedCostModel`.
- La divergenza paper a Close della candela segnale e stata rimossa.

## Not validated

- Il dato "Paper LSR-v2: 3 trade, PF 0.48, expectancy -0.55" non e stato
  trovato in un artefatto corrente attribuibile con certezza a LSR-v2.
- "Tecnicamente pronto per il benchmark Fase 3B" non corrisponde a un gate
  eseguibile corrente.
- La percentuale "circa 40% della roadmap" non ha una metrica canonica e non
  deve essere usata come stato ufficiale.

## Live gate

Trading live resta vietato finche non sono completati TR-INT-03, TR-INT-04,
TR-INT-05, la rigenerazione dei benchmark e una normalizzazione controllata del
working tree.
