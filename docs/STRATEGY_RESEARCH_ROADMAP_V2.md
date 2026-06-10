# Strategy Research Roadmap V2 — Edge Research Program 03

## Esito dei cicli precedenti (perché esiste una V2)

I cicli 1–2 (roadmap V1, branch `strat/edge-research-01` e `strat/edge-research-02`)
hanno chiuso con **NO_CANDIDATE** dopo 84 trial cumulativi dichiarati su 6,4 anni
di dati e un panel point-in-time di 16 simboli USDT-M:

- i costi taker (~10 bps round-trip, scenario realistic) eliminano ogni famiglia
  intraday 15m/5m testata (breakout, pullback, cross-sectional momentum);
- l'unico segnale sopravvissuto in-sample era momentum dipendente dal regime bull,
  respinto dal gate di stratificazione per regime.

NO_CANDIDATE è stato un risultato valido, due volte. La V2 riapre il programma
SOLO nelle due direzioni con base strutturale documentata in letteratura e
coerente con la diagnosi dei costi:

1. **TSMOM 4h/1d** — il costo per trade (~10 bps RT, identico: vedi
   `tf_mult_calibration_note` nel cost model) è diluito 10–50x per unità di
   movimento atteso perché i trade puntano a movimenti 10–50x più grandi;
2. **Funding carry** — premio strutturale pagato dai long levereggiati sui
   perpetual; non richiede previsione del prezzo.

> **Cap dichiarato: questa è l'ultima riapertura del programma.** Se la V2
> termina NO_CANDIDATE, il laboratorio chiude per queste assunzioni di
> mercato e di costo. Nessuna V3 senza un cambiamento documentato delle
> assunzioni (es. accesso a fee maker, mercati diversi).

## Principi vincolanti (invariati dalla V1)

- Il final OOS resta intatto fino al gate finale; accesso singolo.
- Ogni tentativo e parametro testato viene contato (registro ex-ante).
- UnifiedCostModel e rischio massimo 0.005 sono obbligatori.
- Nessuna ottimizzazione verso un numero prefissato di trade.
- Nessuna modifica o abilitazione live/testnet/exchange.
- Nessun uso di chiavi private; solo dati storici pubblici.
- Nessuna promozione automatica al paper o live.
- `NO_CANDIDATE` è un risultato valido e terminale. I gate non si abbassano.

Riferimenti metodologici: PBO (Bailey et al.), Deflated Sharpe Ratio
(Bailey & López de Prado), Time Series Momentum (Moskowitz, Ooi & Pedersen) —
link nella roadmap V1.

## Regola contabile del funding (vincolante)

Il funding è un **accrual di PnL sul periodo di detenzione**, non un costo di
transazione: vive in `trading_bot/clean_bot/funding.py` (opt-in,
`funding_enabled=True` + `funding_df` espliciti, fail-closed in entrambe le
direzioni) e non entra mai in `_SCENARIO_PARAMS` del cost model. Convenzione di
segno: il long paga il funding positivo, lo short lo incassa. I risultati della
famiglia carry vanno riportati **con e senza funding** per esporre la
dipendenza del risultato dal carry stesso.

## STRAT-01-V2 — Dataset contract

- Panel point-in-time di 16 simboli USDT-M (riuso del downloader sha256-verified
  e della logica point-in-time da `strat/edge-research-02`).
- Klines **4h e 1d** + archivi mensili **fundingRate** da `data.binance.vision`
  (archivi pubblici, manifest sha256, cache parquet atomiche).
- Naming cache: `{slug}_{tf}_cache.parquet` (klines), `{slug}_funding.parquet`
  (funding) — convenzioni di `clean_bot/data.py` e `clean_bot/funding.py`.
- Target 6,4 anni di storico; regola di insufficienza onesta: se lo storico non
  c'è, dichiararlo, mai sintetizzare.
- Gate di integrità: `run_market_data_integrity_audit.py` esteso alle serie
  funding (griglia per-simbolo {8h, 4h, 1h}, cap |rate| < 0.75%, coerenza
  symbol/filename). `raw_data_gate` deve essere PASS prima di ogni run.

### Final OOS

La finestra OOS intatta del ciclo 2 — **2025-02-24 → 2026-06-10** — più tutti i
dati più recenti scaricati al momento della run. Un solo accesso, al gate
finale, solo per i sopravvissuti alla selezione robusta.

## STRAT-02-V2 — Due famiglie falsificabili

Implementate in `trading_bot/research/edge03/` (lab, mai importato dal runtime):

1. **TSMOM** (`TSMOMFamily`): segno del rendimento di lookback su 4h/1d, stop
   ATR, uscita trailing/tempo. Griglia: lookback × vol-target × timeframe
   (× direzione). Max 12 config.
2. **Funding carry** (`CarryFamily`): short del perp quando il funding è
   persistentemente positivo sopra soglia (z-score o percentile causale della
   serie funding). Richiede `funding_enabled=True`. Max 12 config.

Vincoli:

- dichiarazione ex-ante con `declare_trials()` — numerazione cumulativa
  **85…108** (continua dal 84 dei cicli 1–2), config congelate, run non
  dichiarate vietate (fail-closed);
- template di dichiarazione: `docs/research/edge03_trial_declaration_template.md`;
- stessa interfaccia trade (`clean_bot.Signal`) e UnifiedCostModel
  (scenario conservative nelle run di ricerca);
- gate economici a livello **panel** (`PANEL_VALIDATION_CONFIG`,
  `is_promising_panel`): ≥ 50 trade pooled sul panel, concentrazione temporale
  mensile, warmup dichiarato per strategia (`panel_oos_with_warmup`);
- nessuna integrazione nel paper/live in questa fase.

## STRAT-03-V2 — Selezione robusta e decisione

Su tutte le prove registrate: walk-forward, parameter plateau (non singolo
optimum), DSR, PBO via CSCV, stratificazione per regime, scenario severe.

Un candidato passa soltanto se, nel final OOS post-costi (pooled sul panel):

1. almeno 50 trade (pooled);
2. profit factor > 1.20;
3. net PnL > 0;
4. max drawdown ≤ 15%;
5. Deflated Sharpe probability ≥ 0.95;
6. PBO < 0.50;
7. scenario severe ancora positivo;
8. top 3 trade ≤ 35% del profitto lordo positivo;
9. gate temporale (bucket mensili) superato;
10. **gate di regime: net PnL > 0 in ≥ 2 regimi distinti** (bull/bear/sideways,
    `regime_stratified_check`) — nuovo, eredità diretta del fallimento del
    ciclo 2;
11. nessuna contaminazione final-OOS.

Il report dichiara esplicitamente `edge_demonstrated=true/false`.
Per la famiglia carry: tutti i gate valutati sul PnL **con** funding, e
riportato in parallelo il PnL senza funding.

## STRAT-04-V2 — Paper candidate readiness

Identico alla V1: solo se STRAT-03-V2 dimostra un edge — congelamento config e
hash, integrazione dietro flag disabilitato, campagna paper supervisionata
(STRAT-PAPER-01 invariato). Se nessun candidato passa: `NO_CANDIDATE`,
nessuna integrazione, nessun gate abbassato, **chiusura del programma**.

## Esecuzione

Il programma gira sul PC dell'utente (rete abilitata) seguendo il prompt pack:
`docs/research/EDGE03_EXECUTION_PROMPT_PACK.md`.
