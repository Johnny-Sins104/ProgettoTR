# Roadmap patch future - ProgettoTR

Data: 2026-06-01
Stato base: working tree non normalizzato, molte patch/report non ancora consolidati.

## Obiettivo

Portare ProgettoTR da una lunga sequenza di patch diagnostiche e supervised paper-only a una base operativa piu stabile, testabile e governata. La roadmap mantiene il principio fail-closed: nessuna patch abilita live, testnet, exchange broker, submit, close o mutazioni paper senza gate espliciti, report PASS e conferma operatore.

## Regole fisse per ogni patch

- Ogni patch deve avere scope piccolo, manifest, report e test dedicati.
- Ogni patch deve dichiarare esplicitamente: muta `paper_state`, muta `paper_status`, submit, close, broker call, network send, scheduler start, live/testnet/exchange enablement.
- Ogni patch deve produrre una decisione leggibile: `PASS`, `WARN` o `KEEP_DIAGNOSTIC`.
- Ogni patch deve essere reversibile o protetta da backup prima di mutazioni di stato.
- Prima di una patch di esecuzione serve sempre una patch preflight e, quando utile, una scaffold patch.
- Prima di qualunque commit va separato il rumore dei report generati dal codice sorgente reale.

## Priorita P0 - Stabilizzazione repository

### PATCH 30.0.0A - Working tree normalization

Scopo: separare codice sorgente, report generati, file cancellati e archivi.

Azioni:
- decidere cosa va tracciato tra `docs/patch_reports`, `trading_bot/docs`, `patch_reports.zip` e report runtime;
- aggiornare `.gitignore` per output generati, cache, log e report rigenerabili;
- ripristinare o confermare le cancellazioni dei README patch storici;
- creare un commit solo per la normalizzazione.

Gate di uscita:
- `git status --short` leggibile;
- nessun file runtime generato finisce accidentalmente nel commit;
- tutti i file Python fanno parse.

### PATCH 30.0.0B - Test environment baseline

Scopo: rendere ripetibili i test senza runner manuali.

Azioni:
- aggiungere un file dipendenze dev o aggiornare quello esistente con `pytest`, `pandas`, `polars`, `aiohttp`, eventuali extra ML;
- creare uno script unico `run_tests.ps1` o `python -m trading_bot.tools.run_checks`;
- separare test unitari veloci, test con dipendenze pesanti e test runtime/integration.

Gate di uscita:
- `pytest` installabile e lanciabile;
- suite smoke verde;
- lista esplicita dei test esclusi per dipendenze o runtime esterno.

## Priorita P1 - Correzioni quantitative e rischio

### PATCH 30.1.0A - Commission model consolidation

Scopo: rendere unico il modello commissionale tra live, paper, backtest e sizing.

Azioni:
- introdurre una funzione comune per fee entry/exit;
- allineare `main.py`, `genetic_opt.py`, `multi_trade_manager.py`, `paper_engine.py`, `risk.py`;
- testare TP1, TP2, SL, close manuale, partial close e display open PnL.

Gate di uscita:
- nessun calcolo fee duplicato a mano nei percorsi principali;
- test di regressione su entry/exit price;
- saldo netto coerente tra backtest e paper.

### PATCH 30.1.0B - Portfolio risk current snapshot

Scopo: chiudere definitivamente il bug VaR off-by-one.

Azioni:
- passare `portfolio_var` corrente dentro `_concentration_flags`;
- aggiungere test primo snapshot e snapshot successivi;
- verificare compatibilita con i report di risk esistenti.

Gate di uscita:
- `VAR_LIMIT_EXCEEDED` si attiva sul tick corrente;
- nessuna regressione su esposizione, leverage e concentration flags.

### PATCH 30.1.0C - Friction parity backtest/paper/live

Scopo: evitare backtest ottimistici rispetto al runtime.

Azioni:
- unificare slippage e fee su ingresso/uscita;
- simulare geometricamente entry, SL e TP;
- produrre report comparativo prima/dopo su sample fisso.

Gate di uscita:
- stesso trade fixture produce lo stesso PnL netto tra motori;
- differenze consentite documentate e motivate.

## Priorita P2 - Runtime affidabile 24/7

### PATCH 30.2.0A - JSONL tail reader everywhere

Scopo: eliminare letture intere di `paper_events.jsonl`.

Azioni:
- usare un helper unico per tail JSONL;
- migrare i moduli `paper_unlock_*`, leakage guard e footer;
- aggiungere limiti hard su righe lette e dimensione file.

Gate di uscita:
- nessun `read_text().splitlines()` sui log grandi;
- test su file JSONL grande;
- runner once non degrada con log storico.

### PATCH 30.2.0B - Report registry

Scopo: ridurre la catena rigida di import e writer diagnostici.

Azioni:
- introdurre un registro dei report diagnostici;
- ogni report dichiara dipendenze, frequenza, read-only/mutation;
- il paper engine invoca il registro invece di importare ogni patch a mano.

Gate di uscita:
- engine piu piccolo;
- report disabilitabili senza editare il core;
- test registry con report finto.

### PATCH 30.2.0C - Async teardown and HTTP session lifecycle

Scopo: risolvere hang `--once` e leak `aiohttp`.

Azioni:
- introdurre teardown strutturato per Telegram/control bot;
- chiudere `ClientSession` in `finally`;
- eliminare dipendenza da `os._exit` dove non necessaria.

Gate di uscita:
- `run_paper_trading.py --once` termina pulito;
- nessun warning di sessione non chiusa;
- watchdog resta solo come ultima protezione.

## Priorita P3 - LSR-v2 supervised paper progression

### PATCH 29.4.4u-69 - Broker submit simulation bridge bundle

Scopo: prossimo step naturale dopo U68, ancora fail-closed.

Azioni:
- simulare il bridge verso broker paper senza submit reale;
- produrre receipt sintetica paper-only;
- verificare che order intent, broker receipt e lifecycle runtime combacino.

Gate di uscita:
- nessun broker submit reale;
- `orders_submitted` e `positions_opened` restano zero salvo modalita esplicitamente simulata;
- report PASS solo con operator gate e runtime evidence completi.

### PATCH 29.4.4u-70 - Paper broker receipt reconciliation

Scopo: controllare coerenza tra order intent, simulated receipt, state e status.

Azioni:
- confrontare ID, symbol, side, size, entry, SL, TP, fee model;
- bloccare mismatch e duplicati;
- generare report di riconciliazione.

Gate di uscita:
- `paper_state` e `paper_status` coerenti;
- nessun ordine duplicato;
- fail-closed su receipt mancante o incoerente.

### PATCH 29.4.4u-71 - Minimal supervised paper submit preflight

Scopo: preparare una futura attivazione paper-only reale, non attivarla.

Azioni:
- definire env vars e phrase di conferma;
- richiedere PASS da U69/U70, leakage guard, risk guard e lifecycle audit;
- stampare un boundary finale di armamento.

Gate di uscita:
- decisione `READY_DIAGNOSTIC`, non submit;
- live/testnet/exchange sempre false;
- single-position e ordinal lock rispettati.

## Priorita P4 - Validazione strategica 29.5.x

### PATCH 29.5.0K - Repaired validation evidence expansion

Scopo: continuare dopo 29.5.0J senza unlock operativo.

Azioni:
- aumentare campione walk-forward;
- separare per asset, lato, regime e sessione;
- stimare expectancy con fee/slippage consolidati.

Gate di uscita:
- decisione `STABILITY_CANDIDATE_DIAGNOSTIC` solo se holdout e fold sono robusti;
- `operational_unlock_allowed=false`.

### PATCH 29.5.0L - Strategy conflict penalty audit

Scopo: correggere segnali candlestick ambigui e near S/R sovrapposti.

Azioni:
- penalizzare pattern bullish e bearish simultanei;
- usare `strong_body_ratio` per Morning/Evening Star;
- disambiguare supporto/resistenza quando esiste solo `near_sr`.

Gate di uscita:
- minor numero di segnali ambigui ad alta confidenza;
- report comparativo pre/post;
- nessuna soglia abbassata per forzare trade.

## Priorita P5 - Performance e manutenzione

### PATCH 30.5.0A - Analyzer incremental window

Scopo: ridurre CPU su indicatori e FVG.

Azioni:
- limitare dataframe a finestra stabile;
- introdurre stato incrementale per FVG in live/paper;
- benchmark su dataset fisso.

Gate di uscita:
- output uguale o differenza spiegata sulle ultime candele;
- tempo ciclo ridotto in modo misurabile.

### PATCH 30.5.0B - Runtime state cache with write-through

Scopo: ridurre I/O su trade e pending trigger.

Azioni:
- cache in memoria per trade/pending;
- scrittura solo su transizioni;
- invalidazione sicura su errore o restart.

Gate di uscita:
- nessuna perdita di stato su restart;
- test open, pending fill, close, TTL expiry.

### PATCH 30.5.0C - ML retrain scheduler fix

Scopo: eliminare il retrain perso per modulo esatto.

Azioni:
- memorizzare ultimo sample index addestrato;
- retrain quando `current - last >= interval`;
- loggare skipped/retrained con motivazione.

Gate di uscita:
- test salto da 999 a 1001;
- nessun retrain duplicato sullo stesso campione.

## Sequenza raccomandata

1. `30.0.0A` normalizzazione repository.
2. `30.0.0B` baseline test.
3. `30.1.0A` commission model consolidation.
4. `30.1.0B` VaR current snapshot.
5. `30.2.0A` JSONL tail reader everywhere.
6. `30.2.0C` async teardown.
7. `29.4.4u-69` broker submit simulation bridge.
8. `29.4.4u-70` receipt reconciliation.
9. `29.5.0K` repaired validation expansion.
10. `29.5.0L` strategy conflict penalty audit.

## Stop conditions

Interrompere la progressione verso submit/close paper reale se uno di questi punti accade:

- test smoke non verdi;
- `paper_state` e `paper_status` divergono;
- leakage guard ritorna WARN non spiegato;
- runtime footer non stampa prompt/source/gate completi;
- qualunque report mostra live/testnet/exchange true;
- campione strategico non stabile su holdout o walk-forward;
- working tree torna illeggibile.

## Nota operativa

Le prossime patch non dovrebbero aggiungere altri cento file senza consolidamento. Prima si stabilizza la base e si rende la suite ripetibile; poi si riprende la sequenza U69+ con confini chiari.
