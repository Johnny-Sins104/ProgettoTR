# Claude Prompt Pack - Timeframe Edge Resolution

## Scopo

Questo documento divide la risoluzione dell'edge statistico in dieci patch
sequenziali e verificabili.

Eseguire un solo prompt per sessione. Prima di iniziare una nuova fase,
verificare che il gate della fase precedente sia soddisfatto e che i relativi
artefatti esistano.

Ordine obbligatorio:

1. Integrita dei dati
2. Cost model unificato
3. Hotfix e certificazione delle Fasi 1-2
4. Preflight e ricertificazione di ingresso alla Fase 3
5. Benchmark pulito 5m vs 15m
6. Walk-forward economico
7. Robustezza statistica
8. Shadow outcome e parita runtime
9. Validazione multi-asset
10. Gate finale e sintesi

Un `PASS` tecnico indica solamente che la fase e stata implementata e
verificata. Non dimostra l'esistenza di un edge e non autorizza trading live.

## Politica rischio per la ricerca dell'edge

Durante benchmark, walk-forward e robustezza statistica utilizzare un unico
rischio fisso pari allo `0,5%` dell'equity per trade.

- Non usare `LOW`, `MEDIUM`, `HIGH`, `DYNAMIC` o Kelly per dimostrare l'edge.
- Non scegliere una strategia in base al rendimento amplificato dal sizing.
- Conservare i profili esistenti senza cancellarli, ma escluderli dal benchmark
  principale.
- Il Dynamic Risk potra essere valutato solamente dopo la dimostrazione OOS
  dell'edge, come ablation separata e inizialmente `reduce-only`: potra ridurre
  il rischio fisso, mai aumentarlo.
- Nessun risultato con sizing dinamico puo trasformare una strategia negativa
  o non significativa in `EDGE_CANDIDATE`.

---

## Prompt 1 - Integrita, isolamento e provenienza dei dati

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Implementa la prima fase della pipeline di edge resolution: inventario
dinamico, integrita, provenienza e isolamento dei dati 5m, 15m e 1h.

Prima di modificare il codice leggi:

- docs/edge_statistical_critical_points_report.md
- data/edge_statistical_critical_points_report.json
- trading_bot/run_timeframe_comparison.py
- gli attuali artefatti sotto data/timeframe_runs e data/multi_asset_runs

FATTO GIA OSSERVATO DA VERIFICARE

I file data/timeframe_runs/5m/signal_density_report.json e
data/timeframe_runs/15m/signal_density_report.json hanno mostrato lo stesso
hash. Devi stabilire se si tratta di contaminazione, copia accidentale o
risultato realmente identico. Non assumere la causa.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

Prima dell'implementazione:

1. Ispeziona le skill e i sub-agent disponibili.
2. Crea o aggiorna una skill locale riutilizzabile chiamata
   market-data-integrity-audit. Se l'ambiente supporta le project skills,
   salvala in .claude/skills/market-data-integrity-audit/SKILL.md.
3. La skill deve documentare controlli, comandi, schemi output e regole
   fail-closed per dataset OHLCV.
4. Delega in parallelo, quando possibile, a questi sub-agent:
   - data-forensics-agent: inventario, hash, provenienza, duplicati e gap;
   - candle-aggregation-agent: verifica aggregazione 5m -> 15m -> 1h;
   - leakage-audit-agent: candele incomplete, lookahead e separazione temporale;
   - test-review-agent: revisione indipendente dei test e dei risultati.
5. Ogni sub-agent deve restituire risultati strutturati con evidenze e file
   controllati. Il coordinatore Claude integra i risultati e mantiene la
   responsabilita finale.
6. Se i sub-agent non sono disponibili, esegui gli stessi ruoli in sequenza e
   dichiaralo nel report. Non fingere deleghe inesistenti.

REQUISITI

- Scoprire dinamicamente dataset e report disponibili.
- Verificare schema, asset, timeframe, periodo, righe e timestamp.
- Calcolare hash degli input e rilevare artefatti duplicati tra timeframe.
- Verificare gap, duplicati, ordinamento temporale e timestamp fuori sequenza.
- Verificare la corretta aggregazione delle candele 15m e 1h.
- Escludere candele incomplete.
- Verificare assenza di lookahead.
- Registrare provenienza e dipendenze di ogni artefatto.
- Bloccare le fasi successive quando i dati sono contaminati o insufficienti.
- I test devono verificare proprieta desiderate. Non creare test che passano
  quando un'anomalia continua a esistere e falliscono quando viene risolta.
- Findings e anomalie note devono essere riportati come dati diagnostici o
  test marcati esplicitamente, senza rendere fragile la suite.
- Calcolare hash riproducibili anche per i dataset parquet principali.
- Verificare l'aggregazione 5m -> 15m sull'intero overlap disponibile o su un
  campione deterministico rappresentativo, non solamente sulle prime 20 barre.

OUTPUT RICHIESTI

- .claude/skills/market-data-integrity-audit/SKILL.md, se supportato
- trading_bot/run_market_data_integrity_audit.py
- data/market_data_integrity_status.json
- docs/market_data_integrity_report.md
- test automatici dedicati

VINCOLI

- Non abilitare live trading, testnet o broker.
- Non modificare API key, environment, strategie o stato paper.
- Non cancellare o sovrascrivere artefatti esistenti.
- Non rigenerare dati per nascondere un'incongruenza.
- Ogni input mancante o ambiguo deve risultare esplicitamente nel report.

GATE DI USCITA

La fase puo terminare con:

- PASS: dataset approvati e indipendenti disponibili;
- BLOCKED: contaminazione, provenienza incerta o dati insufficienti.

Il report deve elencare esattamente quali dataset sono approvati per il
benchmark successivo.

VALIDAZIONE FINALE

Esegui i test pertinenti e il runner. Riporta:

- pipeline_status
- approved_datasets
- rejected_datasets
- duplicate_artifacts
- incomplete_candles
- gaps_detected
- leakage_detected
- files_created
- files_modified
```

---

## Prompt 2 - Cost model unificato e verificabile

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Implementa o consolida un unico cost model diagnostico, economicamente
corretto e riutilizzabile da benchmark, backtest e walk-forward.

PREREQUISITO

Leggi:

- data/market_data_integrity_status.json
- docs/market_data_integrity_report.md
- i moduli cost model ed execution cost gia presenti nel progetto

Se la fase precedente non e PASS, interrompi con BLOCKED senza aggirare il
gate.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Ispeziona le skill e i sub-agent disponibili.
2. Crea o aggiorna la skill locale execution-cost-validation in
   .claude/skills/execution-cost-validation/SKILL.md, se supportato.
3. Delega:
   - cost-model-agent: formula economica, unita e scenari;
   - execution-forensics-agent: commissioni, spread, slippage e fill;
   - integration-agent: integrazione minima con backtest e runner diagnostici;
   - test-review-agent: test indipendenti con casi numerici verificabili.
4. Chiedi ai sub-agent di esplicitare assunzioni e unita di misura.
5. Il coordinatore Claude deve risolvere eventuali divergenze tra agenti e
   documentare la decisione.
6. Se i sub-agent non sono disponibili, esegui i ruoli in sequenza e
   dichiaralo.

REQUISITI

Calcolare separatamente:

- gross PnL
- commissioni maker/taker
- spread
- slippage
- latency
- partial-fill penalty
- net PnL
- gross R
- net R

Usare:

- venue e strumento configurati
- notional
- quantita
- entry
- exit
- distanza iniziale dello stop
- lato BUY o SELL

Supportare scenari:

- optimistic
- realistic
- conservative
- severe

Non convertire direttamente i bps in R senza utilizzare notional e distanza
dello stop.

REQUISITI DI COERENZA E FAIL-CLOSED

- Tutte le API pubbliche del cost model devono produrre lo stesso costo totale
  per lo stesso trade e scenario, salvo differenze esplicitamente documentate.
- `total_cost_amt` deve includere tutte le componenti presenti in
  `total_round_trip_bps`, incluse latency e partial-fill penalty.
- Il costo entry deve usare l'entry notional; il costo exit deve usare l'exit
  notional quando disponibile.
- Validare e respingere side sconosciuti, scenario sconosciuto, prezzi non
  positivi, quantita non positiva e stop uguale all'entry.
- Non sostituire silenziosamente input invalidi con valori di default.
- Evitare un secondo modello divergente: consolidare o adattare i moduli
  esistenti con una sola fonte di verita per formule e scenari.
- Aggiungere test di parita tra `compute_trade_outcome`,
  `apply_cost_to_backtest_trade` e gli adapter usati dai benchmark.

OUTPUT RICHIESTI

- .claude/skills/execution-cost-validation/SKILL.md, se supportato
- modulo cost model condiviso o consolidamento minimo dei moduli esistenti
- data/cost_model_validation.json
- docs/cost_model_validation_report.md
- test unitari e di integrazione

VINCOLI

- Non modificare il comportamento operativo live o paper.
- Non cambiare parametri strategici.
- Non assumere Binance Futures se il runner analizzato simula spot.
- Ogni scenario deve indicare chiaramente le assunzioni.

GATE DI USCITA

PASS solamente se i test numerici dimostrano che gross PnL, costi, net PnL e
net R sono coerenti per BUY e SELL, tutte le API sono in parita, gli input
invalidi sono respinti e la suite pertinente e completamente verde.
```

---

## Prompt 2H - Hotfix e certificazione obbligatoria delle Fasi 1-2

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Esegui una hotfix limitata alle Fasi 1 e 2 prima di iniziare il benchmark.
Devi correggere i problemi rilevati dall'audit indipendente e produrre una
certificazione fail-closed. Non iniziare alcuna parte del benchmark 5m vs 15m.

PROBLEMI CONFERMATI DA RISOLVERE

1. La Fase 1 risulta `BLOCKED`, ma la Fase 2 ha aggirato autonomamente il gate
   dichiarando una presunta istruzione utente.
2. `compute_trade_outcome()` e `apply_cost_to_backtest_trade()` producono costi
   diversi per lo stesso trade.
3. `total_round_trip_bps` include latency e partial-fill penalty, mentre
   `compute_trade_outcome().total_cost_amt` non li addebita.
4. Il cost model accetta side e scenari sconosciuti, prezzi negativi e stop
   uguale all'entry.
5. Il nuovo cost model non e ancora realmente condiviso dai runner che dovranno
   usarlo.
6. La suite di integrita contiene test che passano quando l'anomalia esiste e
   falliscono quando viene risolta.
7. Il controllo di aggregazione del runner usa un campione troppo ridotto.
8. La suite combinata verificata ha prodotto almeno un test fallito.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Aggiorna le skill:
   - .claude/skills/market-data-integrity-audit/SKILL.md
   - .claude/skills/execution-cost-validation/SKILL.md
2. Delega:
   - cost-parity-agent: parita completa delle API del cost model;
   - fail-closed-agent: validazione input e gestione errori;
   - integrity-test-agent: riscrittura dei test fragili;
   - gate-audit-agent: riconciliazione dei gate senza reinterpretazioni;
   - adversarial-review-agent: cerca casi in cui PASS sarebbe falso;
   - test-review-agent: esecuzione indipendente della suite.
3. Nessun sub-agent puo modificare benchmark, strategia o sizing.
4. Se i sub-agent non sono disponibili, esegui gli stessi ruoli in sequenza e
   dichiaralo.

REQUISITI COST MODEL

- Rendere coerenti tutte le API per lo stesso trade.
- Includere commissioni, spread, slippage, latency e partial-fill nel costo.
- Esporre ogni componente anche in amount e bps.
- Usare entry e exit notional correttamente.
- Respingere input invalidi con errori espliciti.
- Usare una sola fonte di verita oppure adapter sottili verificati.
- Aggiungere test di parita per tutti gli scenari, BUY e SELL.
- Aggiungere test con prezzi differenti entry/exit e severe cost.

REQUISITI INTEGRITA E GATE

- Non aggirare un gate `BLOCKED`.
- Separare chiaramente:
  - `raw_data_gate`;
  - `derived_artifact_gate`;
  - `benchmark_readiness_gate`.
- La Fase 2 puo essere certificata autonomamente, ma la Fase 3 deve restare
  `BLOCKED` finche `benchmark_readiness_gate` non e PASS.
- Correggere i test che considerano positiva la permanenza di anomalie.
- Rigenerare i report dopo le correzioni.
- Ogni report deve contenere hash degli input principali.

POLITICA RISCHIO DA REGISTRARE

Aggiorna la documentazione di handoff imponendo per le Fasi 3-5:

- rischio fisso `0,5%` per trade;
- esclusione di LOW, MEDIUM, HIGH, DYNAMIC e Kelly dal benchmark principale;
- Dynamic Risk conservato ma non usato per dimostrare l'edge;
- eventuale futura ablation Dynamic esclusivamente reduce-only.

OUTPUT RICHIESTI

- data/phase_1_2_recertification_status.json
- docs/phase_1_2_recertification_report.md
- test aggiornati e nuovi test di parita/fail-closed
- skill aggiornate

GATE DI USCITA

PASS solamente se:

- cost model parity = PASS;
- invalid input rejection = PASS;
- raw_data_gate = PASS;
- benchmark_readiness_gate = PASS;
- tutta la suite pertinente e verde;
- nessun gate e stato aggirato;
- nessun comportamento live o paper e stato modificato.

Se `benchmark_readiness_gate` resta BLOCKED, termina con BLOCKED e non iniziare
la Fase 3.
```

---

## Prompt 3A - Preflight e ricertificazione obbligatoria di ingresso alla Fase 3

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

ESEGUI SOLAMENTE QUESTO PROMPT.
Non iniziare il benchmark 5m vs 15m e non eseguire i prompt successivi.

OBIETTIVO

Correggi i falsi PASS rilevati dalla revisione indipendente della Patch 2H e
produci una ricertificazione realmente fail-closed prima della Fase 3.

STATO INIZIALE DA NON REINTERPRETARE

La Patch 2H attuale stampa PASS, ma non e approvata. La Fase 3 deve restare
BLOCKED finche tutti i problemi sotto non sono corretti e verificati:

1. `risk_per_trade_pct = 0.5` rappresenta il 50% nelle convenzioni del progetto.
   Il rischio fisso richiesto dello 0,5% deve essere rappresentato internamente
   come `0.005`, con label umana separata `0.5%`.
2. La parita del cost model viene verificata solamente su trade flat.
   `compute_trade_outcome()` e `apply_cost_to_backtest_trade()` producono costi
   diversi quando entry ed exit sono differenti.
3. La dichiarazione secondo cui la differenza sui trade non-flat e inferiore
   allo 0,5% del costo e falsa. Sono stati osservati scarti dell'8% con movimento
   prezzo del 20% e del 40% con movimento prezzo del 100%.
4. Il cost model accetta valori non finiti come NaN e Inf e puo produrre PnL,
   R e costi non finiti.
5. Timeframe sconosciuti vengono trattati silenziosamente come 15m.
6. Il controllo `no_live_modified` e assegnato a PASS come costante.
7. Il controllo "shared cost model" prova solamente che il modulo sia
   importabile, non che i runner lo utilizzino.
8. Il controllo aggregazione usa solamente le prime 500 barre e confronta
   solamente Close, non Open/High/Low/Volume.
9. Il runner di ricertificazione esegue solamente due file di test. La raccolta
   della suite completa attuale fallisce su `Config.WEIGHTS_TRENDING`.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Leggi integralmente:
   - docs/CLAUDE_TIMEFRAME_EDGE_RESOLUTION_SUBPROMPTS.md
   - data/market_data_integrity_status.json
   - data/cost_model_validation.json
   - data/phase_1_2_recertification_status.json
   - docs/market_data_integrity_report.md
   - docs/cost_model_validation_report.md
   - docs/phase_1_2_recertification_report.md
   - trading_bot/core/unified_trade_cost.py
   - trading_bot/run_market_data_integrity_audit.py
   - trading_bot/run_phase_1_2_recertification.py
2. Aggiorna le skill:
   - .claude/skills/market-data-integrity-audit/SKILL.md
   - .claude/skills/execution-cost-validation/SKILL.md
3. Delega, se supportato:
   - cost-parity-adversarial-agent;
   - finite-input-validation-agent;
   - aggregation-correctness-agent;
   - gate-falsification-agent;
   - independent-test-agent.
4. Prima di modificare file, salva un manifest con hash e stato Git dei file
   live/paper. A fine lavoro dimostra che questa patch non li ha modificati.
5. I sub-agent non possono iniziare benchmark, ottimizzazione o selezione della
   strategia.

FIX OBBLIGATORI

A. Risk policy

- Usa `risk_per_trade_pct = 0.005` in JSON, codice, esempi CLI e handoff.
- Mostra `0.5%` solamente come label per esseri umani.
- Aggiungi test che dimostri che equity 1000 e rischio 0.005 producono un
  risk budget di 5, non 500.
- Respingi valori di rischio non finiti, <= 0 o incompatibili col benchmark.

B. Parita completa del cost model

- Elimina la "documented approximation" tra le API.
- Usa una sola funzione sorgente per calcolare tutte le componenti amount/bps.
- Quando entry ed exit notional sono disponibili, entrambe le API devono usare
  gli stessi valori.
- Se un adapter non dispone di dati sufficienti per ottenere parita esatta,
  deve richiederli esplicitamente o terminare con errore. Non stimare in
  silenzio.
- Aggiungi test per BUY e SELL, profitto e perdita, tutti gli scenari, severe,
  entry/exit differenti e movimenti prezzo almeno 1%, 20% e 100%.
- La tolleranza di parita deve essere esplicita e stretta.

C. Fail-closed reale

- Tutti gli input numerici pubblici devono essere validati con `math.isfinite`.
- Respingi NaN, +Inf, -Inf, stringhe non numeriche e valori non positivi dove
  non ammessi.
- Respingi timeframe non supportati anziche convertirli implicitamente in 15m.
- Valida coerenza side/stop: BUY richiede stop sotto entry; SELL richiede stop
  sopra entry.
- Verifica che tutti gli output numerici siano finiti prima di restituirli.
- Aggiungi test avversariali per ogni caso.

D. Integrita aggregazione

- Verifica Open, High, Low, Close e Volume, non solamente Close.
- Per BTC confronta l'intero overlap 5m->15m oppure documenta un limite tecnico
  reale. Non usare solamente le prime barre.
- Per gli asset senza raw 15m, verifica invarianti, allineamento timestamp e
  riproducibilita dell'aggregazione generata.
- Usa esplicitamente `closed='left'` e `label='left'`.
- Registra numero barre confrontate, intervallo iniziale/finale, mismatch per
  colonna, tolleranze e hash degli input.

E. Gate e suite

- Nessun gate puo essere PASS tramite costante o semplice ricerca di stringhe.
- `no_live_modified` deve derivare dal manifest before/after creato in questa
  sessione.
- `cost_model_shared` deve essere PASS solamente quando un consumer reale usa
  il modulo. Finche il runner Fase 3 non esiste, usa uno stato esplicito come
  `NOT_YET_APPLICABLE`, senza trasformarlo in un falso PASS.
- Il gate di ingresso alla Fase 3 deve verificare dipendenze e input ammessi,
  impedendo l'uso di `data/timeframe_runs/` e altri artefatti contaminati.
- Esegui almeno:
  - test mirati cost model e integrita;
  - `python -m pytest --collect-only -q`;
  - `python -m pytest -q`.
- Se la suite completa non e verde, registra cause e test falliti e termina
  BLOCKED. Non nascondere errori restringendo arbitrariamente la suite.
- Non correggere comportamento live/paper come effetto collaterale. Se un
  errore richiede tale modifica, termina BLOCKED e documentalo.

OUTPUT RICHIESTI

- data/phase_1_2_recertification_status.json aggiornato
- docs/phase_1_2_recertification_report.md aggiornato
- data/phase_3_entry_preflight_status.json
- docs/phase_3_entry_preflight_report.md
- data/phase_3_entry_preflight_manifest.json
- test di regressione e avversariali aggiornati
- skill aggiornate

GATE DI USCITA

PASS solamente se:

- rischio interno esattamente `0.005`;
- parita completa verificata su trade non-flat;
- tutti gli input non validi e non finiti sono respinti;
- aggregazione OHLCV verificata;
- nessun gate e autocertificato;
- nessun file live/paper e stato modificato durante questa patch;
- raccolta e suite completa sono verdi;
- gli artefatti contaminati sono esclusi in modo verificabile;
- tutti gli output e report concordano.

In qualsiasi altro caso:

- `gate_result = BLOCKED`;
- `approved_for_phase_3 = false`;
- non creare il runner benchmark;
- non iniziare il Prompt 3B.
```

---

## Prompt 3A-H - Hotfix finale del preflight Fase 3

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

ESEGUI SOLAMENTE QUESTO PROMPT.
Non iniziare il Prompt 3B e non creare il benchmark.

OBIETTIVO

Correggi i falsi PASS residui del Prompt 3A e produci artefatti di preflight
generati automaticamente, riproducibili e coerenti con i risultati reali.

STATO VERIFICATO DALL'AUDIT INDIPENDENTE

La Fase 3 e attualmente BLOCKED.

Comandi gia eseguiti dalla root del progetto:

- `python -m pytest --collect-only -q` -> 1038 test raccolti;
- `python -m pytest -q` -> 1038 passed, 4 warnings;
- `python trading_bot/run_market_data_integrity_audit.py` -> exit code 1;
- `python trading_bot/run_phase_1_2_recertification.py` -> exit code 1,
  `gate_result=BLOCKED`.

Il full overlap BTC 5m->15m contiene 49.996 barre confrontate e 4 mismatch:

- Open: 2 mismatch;
- High: 1 mismatch;
- Low: 0 mismatch;
- Close: 0 mismatch;
- Volume: 1 mismatch.

Dettagli da investigare, non da nascondere:

- `2024-11-20 19:15:00+00:00`:
  Open aggregato `93230.7`, raw 15m `93582.2`;
  High aggregato `93444.4`, raw 15m `93698.7`;
  Volume aggregato `654.682`, raw 15m `2164.914`.
- `2025-08-29 06:30:00+00:00`:
  Open aggregato `110966.4`, raw 15m `110966.3`.

Gli artefatti sono attualmente incoerenti:

- `data/market_data_integrity_status.json` e
  `data/phase_1_2_recertification_status.json` indicano correttamente BLOCKED;
- `data/phase_3_entry_preflight_status.json` e
  `docs/phase_3_entry_preflight_report.md` dichiarano ancora PASS;
- non esiste un runner che generi automaticamente
  `phase_3_entry_preflight_status.json`;
- il runner di ricertificazione chiama solamente
  `pytest trading_bot/tests/`, non la suite root completa;
- il manifest monitora solo quattro file live/paper, ma il report dichiara che
  il Prompt 3A ha modificato anche `trading_bot/core/engine.py` e creato o
  sostituito runner operativi.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Aggiorna le skill pertinenti.
2. Delega, se supportato:
   - aggregation-root-cause-agent;
   - artifact-consistency-agent;
   - runtime-manifest-agent;
   - adversarial-cost-agent;
   - independent-test-agent.
3. Crea il baseline before realmente prima di modificare file:
   - timestamp UTC completo;
   - `git status --porcelain`;
   - hash SHA-256 dei file runtime eseguibili e degli state file;
   - elenco dei file gia sporchi prima della sessione.
4. Non sovrascrivere o annullare modifiche preesistenti dell'utente.

FIX OBBLIGATORI

A. Root cause aggregazione

- Determina se il mismatch del `2024-11-20 19:15 UTC` deriva da un bucket 15m
  iniziale incompleto. Ogni barra confrontata deve contenere esattamente tre
  barre 5m contigue e allineate.
- Escludi solamente bucket dimostrabilmente incompleti, registrandoli come
  `excluded_incomplete_buckets`; non considerarli mismatch risolti in silenzio.
- Investiga separatamente il mismatch Open del `2025-08-29 06:30 UTC`.
- Non aumentare la tolleranza per forzare PASS senza una giustificazione
  numerica e documentata.
- Se il raw 15m e realmente incoerente col raw 5m, quarantena o rigenera il
  dataset da una fonte canonica; registra hash prima/dopo e provenienza.
- Il gate resta BLOCKED finche ogni mismatch non e risolto oppure quarantinato
  con una policy che impedisca il suo utilizzo nel benchmark.
- L'output aggregazione deve includere:
  `full_overlap_rows`, `complete_buckets_compared`,
  `excluded_incomplete_buckets`, intervallo UTC, tolleranze,
  mismatch dettagliati per timestamp/colonna, hash SHA-256 degli input.

B. Test aggregazione

- Riscrivi `test_btc_aggregation_correctness` affinche verifichi l'intero
  overlap completo, non le prime 200 barre.
- Verifica Open, High, Low, Close e Volume.
- Aggiungi test che dimostrino che un bucket con meno di tre barre viene
  escluso e registrato, non confrontato come completo.
- Aggiungi test che falliscano introducendo un mismatch in ogni colonna OHLCV.

C. Artefatti preflight generati, non manuali

- Crea `trading_bot/run_phase_3_entry_preflight.py`.
- Il runner deve leggere gli artefatti reali, verificarne gli hash e generare:
  - `data/phase_3_entry_preflight_status.json`;
  - `docs/phase_3_entry_preflight_report.md`;
  - il completamento del manifest before/after.
- Non codificare PASS o conteggi test come costanti.
- Se un input gate e BLOCKED, il preflight deve risultare BLOCKED.
- Tutti i report devono concordare su gate, motivazioni, timestamp e hash.

D. Suite realmente completa

- Sostituisci nel gate il comando ristretto a `trading_bot/tests/` con:
  - `python -m pytest --collect-only -q`;
  - `python -m pytest -q`.
- Registra dinamicamente numero raccolto, numero passato, warning, errori,
  return code e comando eseguito.
- Non modificare comportamento runtime live/paper solamente per rendere verdi
  i test.
- La modifica 3A a `trading_bot/core/engine.py` deve essere rimossa solamente
  se confermato che e stata introdotta dal 3A ed e inutile dopo la correzione
  dello stub di test. Preserva ogni modifica preesistente non collegata.
- Qualsiasi modifica runtime necessaria deve mantenere il gate BLOCKED e deve
  essere documentata per revisione separata.

E. Manifest completo

- Il manifest non puo limitarsi a quattro file scelti manualmente.
- Deve confrontare il baseline before/after di tutti i file runtime modificati
  durante la sessione e degli state file paper/live.
- Deve distinguere:
  - dirty preesistente;
  - modificato dal Prompt 3A-H;
  - output diagnostico atteso;
  - modifica runtime non autorizzata.
- `no_live_modified=PASS` solamente se nessun file runtime live/paper e stato
  modificato dal Prompt 3A-H.

F. Residui cost model

- Respingi `atr_pct < 0` con ValueError.
- Non trattare implicitamente `1h` e `4h` come `15m`, oppure `1m` come `5m`.
  Per il benchmark principale limita i timeframe di execution cost a `5m` e
  `15m`, salvo parametri espliciti e verificati per gli altri timeframe.
- Aggiungi test non-flat SELL per profitto e perdita, tutti gli scenari e
  movimenti 1%, 20% e 100%.

OUTPUT RICHIESTI

- trading_bot/run_phase_3_entry_preflight.py
- data/market_data_integrity_status.json rigenerato
- docs/market_data_integrity_report.md rigenerato
- data/phase_1_2_recertification_status.json rigenerato
- docs/phase_1_2_recertification_report.md rigenerato
- data/phase_3_entry_preflight_status.json rigenerato
- docs/phase_3_entry_preflight_report.md rigenerato
- data/phase_3_entry_preflight_manifest.json rigenerato
- test aggiornati
- skill aggiornate

GATE DI USCITA

PASS solamente se tutti questi comandi terminano con exit code 0:

- `python trading_bot/run_market_data_integrity_audit.py`;
- `python trading_bot/run_phase_1_2_recertification.py`;
- `python trading_bot/run_phase_3_entry_preflight.py`;
- `python -m pytest --collect-only -q`;
- `python -m pytest -q`.

Inoltre:

- `benchmark_readiness_gate = PASS`;
- `phase_1_2_recertification_status.gate_result = PASS`;
- `phase_3_entry_preflight_status.gate_result = PASS`;
- `approved_for_phase_3 = true`;
- zero mismatch OHLCV inspiegati;
- nessun PASS hardcoded;
- nessuna modifica runtime live/paper introdotta dalla hotfix;
- tutti gli artefatti concordano.

In qualsiasi altro caso termina con:

- `gate_result = BLOCKED`;
- `approved_for_phase_3 = false`;
- elenco preciso dei blocker;
- divieto di iniziare il Prompt 3B.
```

---

## Prompt 3B - Benchmark pulito 5m vs 15m

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Costruisci un benchmark indipendente e riproducibile per confrontare 5m, 15m
e l'architettura multi-timeframe candidata.

PREREQUISITI

Leggi e verifica:

- data/phase_3_entry_preflight_status.json
- docs/phase_3_entry_preflight_report.md
- data/phase_3_entry_preflight_manifest.json
- data/market_data_integrity_status.json
- data/cost_model_validation.json
- data/phase_1_2_recertification_status.json
- docs/market_data_integrity_report.md
- docs/cost_model_validation_report.md
- docs/phase_1_2_recertification_report.md

Interrompi con BLOCKED se `phase_3_entry_preflight_status.gate_result`,
`benchmark_readiness_gate` o uno dei gate richiesti non e PASS, oppure se
`approved_for_phase_3` non e `true`. Non reinterpretare o aggirare alcun gate.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Crea o aggiorna la skill locale clean-timeframe-benchmark in
   .claude/skills/clean-timeframe-benchmark/SKILL.md, se supportato.
2. Delega:
   - benchmark-design-agent: matrice sperimentale e comparabilita;
   - timeframe-implementation-agent: runner separati e output isolati;
   - mtf-leakage-agent: allineamento 1h/15m/5m e assenza lookahead;
   - reproducibility-agent: seed, manifest, hash e ripetibilita;
   - test-review-agent: verifica indipendente.
3. Nessun sub-agent puo scegliere il vincitore. Deve solamente produrre
   evidenze.
4. Il coordinatore Claude integra e confronta i risultati.
5. Se i sub-agent non sono disponibili, esegui i ruoli in sequenza.

CONFIGURAZIONI DA CONFRONTARE

1. Strategia eseguita interamente sul 5m.
2. Strategia eseguita interamente sul 15m.
3. Regime 1h e setup 15m.
4. Regime 1h, setup 15m ed execution opzionale 5m.

REGOLE

- Stessi asset e intervalli temporali.
- Stesso capitale, rischio fisso `0,5%` per trade e cost model.
- Il valore numerico interno del rischio deve essere esattamente `0.005`, mai
  `0.5`.
- Processi e cartelle output completamente separati.
- Utilizzare solamente candele completate.
- Il segnale 15m deve essere valido autonomamente.
- Il 5m execution puo modificare solamente entry o fill teorico di un setup
  15m gia confermato.
- Il 5m execution non puo generare nuovi segnali.
- Non selezionare o ottimizzare parametri sul risultato del benchmark.
- Escludere LOW, MEDIUM, HIGH, DYNAMIC e Kelly dal benchmark principale.
- Il sizing deve essere identico tra tutte le configurazioni confrontate.
- Riportare metriche anche in R per impedire che il capitale iniziale o il
  sizing alterino il confronto dell'edge.
- Il runner deve importare e usare realmente `UnifiedCostModel`; aggiungi un
  test d'integrazione che fallisca se il runner usa formule costi alternative.
- Ogni run deve verificare gli hash degli input contro il manifest autorizzato.
- Non usare come input `data/timeframe_runs/`, `data/signal_density/` o altri
  artefatti derivati dichiarati contaminati.

OUTPUT RICHIESTI

- .claude/skills/clean-timeframe-benchmark/SKILL.md, se supportato
- trading_bot/run_clean_timeframe_benchmark.py
- data/timeframe_clean_comparison.json
- docs/timeframe_clean_comparison_report.md
- manifest separati per ogni run
- test di isolamento, allineamento e assenza lookahead

GATE DI USCITA

PASS significa che il confronto e valido e riproducibile. Non significa che
una configurazione possieda un edge.

Il report non deve ancora proclamare un timeframe vincitore.
```

---

## Prompt 4 - Walk-forward economico reale

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Implementa un vero walk-forward economico per le configurazioni ammesse dal
benchmark pulito.

Usa esclusivamente rischio fisso `0,5%` per trade. Non usare LOW, MEDIUM,
HIGH, DYNAMIC o Kelly nel walk-forward principale.

PREREQUISITO

Leggi:

- data/timeframe_clean_comparison.json
- docs/timeframe_clean_comparison_report.md
- gli attuali walkforward_audit_report.json

Gli attuali report walk-forward descrivono soprattutto finestre temporali.
Non considerarli prova di performance economica.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Crea o aggiorna la skill locale economic-walkforward-validation in
   .claude/skills/economic-walkforward-validation/SKILL.md, se supportato.
2. Delega:
   - experimental-design-agent: train, embargo, validation, test e holdout;
   - walkforward-engine-agent: esecuzione economica per fold;
   - leakage-audit-agent: verifica indipendente di contaminazione e lookahead;
   - metrics-agent: metriche aggregate esclusivamente OOS;
   - test-review-agent: test indipendenti.
3. Un sub-agent separato deve tentare di falsificare la validita del
   walk-forward e riportare ogni possibile leakage.
4. Il coordinatore Claude decide il risultato finale sulla base delle
   evidenze.

STRUTTURA OBBLIGATORIA

- train
- embargo
- validation
- test
- holdout finale incontaminato

L'ottimizzazione puo utilizzare solamente train e validation.

PER OGNI FOLD CALCOLARE

- numero trade
- gross e net PnL
- gross e net average R
- profit factor
- win rate
- max drawdown
- costi
- risultati per asset
- risultati per regime
- concentrazione dei profitti
- parametri selezionati e relativa provenienza

OUTPUT RICHIESTI

- .claude/skills/economic-walkforward-validation/SKILL.md, se supportato
- trading_bot/run_economic_walkforward.py
- data/multi_timeframe_walkforward_performance.json
- docs/economic_walkforward_report.md
- test contro leakage, contaminazione e uso scorretto dell'holdout

VINCOLI

- Aggregare solamente risultati realmente out-of-sample.
- Non usare l'holdout per scegliere parametri.
- Non nascondere fold negativi o privi di trade.
- Non modificare il sizing tra fold o configurazioni.

GATE DI USCITA

PASS significa che le performance OOS sono state calcolate correttamente.
Non significa edge dimostrato.
```

---

## Prompt 5 - Robustezza statistica fuori campione

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Valuta rigorosamente la robustezza statistica usando esclusivamente risultati
out-of-sample prodotti dal walk-forward economico.

La robustezza dell'edge deve essere valutata sui risultati ottenuti con rischio
fisso `0,5%`. LOW, MEDIUM, HIGH, DYNAMIC e Kelly restano esclusi.

PREREQUISITO

Leggi:

- data/multi_timeframe_walkforward_performance.json
- docs/economic_walkforward_report.md

Interrompi con BLOCKED se mancano risultati OOS validi.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Crea o aggiorna la skill locale oos-edge-robustness in
   .claude/skills/oos-edge-robustness/SKILL.md, se supportato.
2. Delega:
   - statistical-methods-agent: block bootstrap e permutation test;
   - outlier-regime-agent: concentrazione PnL e stabilita per periodo/regime;
   - risk-agent: drawdown, probabilita di rovina e sensibilita ai costi;
   - adversarial-review-agent: cerca motivi per respingere l'edge;
   - test-review-agent: riproducibilita e correttezza statistica.
3. Il sub-agent adversarial-review-agent deve lavorare indipendentemente dagli
   altri e tentare di falsificare ogni conclusione positiva.
4. Il coordinatore Claude deve riportare sia conferme sia confutazioni.

IMPLEMENTARE

- block bootstrap temporale con seed riproducibile
- permutation test
- confidence interval di net average R
- confidence interval del profit factor
- risultati escludendo top 1, top 3 e top 5 trade
- quota di PnL prodotta dai migliori trade
- stabilita mensile, trimestrale e per regime
- stabilita dei parametri tra fold
- sensibilita a commissioni e slippage
- distribuzione del drawdown
- probabilita di rovina
- stima della potenza statistica

Non usare solamente t-test o bootstrap IID su trade temporalmente dipendenti.

OUTPUT RICHIESTI

- .claude/skills/oos-edge-robustness/SKILL.md, se supportato
- trading_bot/run_edge_robustness_analysis.py
- data/edge_robustness_status.json
- docs/edge_robustness_report.md
- test automatici statistici

GATE DI USCITA

Classificare ogni configurazione come:

- REJECTED
- INSUFFICIENT_EVIDENCE
- RESEARCH_ONLY
- ROBUSTNESS_CANDIDATE

Non dichiarare ancora EDGE_CANDIDATE.
```

---

## Prompt 6 - Shadow outcome e parita runtime/backtest

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Completare il tracker shadow attualmente scaffold-only e verificare la parita
tra backtest e runtime sulle stesse candele completate.

PREREQUISITI

Leggi:

- trading_bot/strategy_runtime/selected_strategy_shadow_outcome_tracker.py
- trading_bot/strategy_runtime/selected_strategy_shadow_journal.py
- trading_bot/run_selected_strategy_shadow_signal_journal.py
- data/edge_robustness_status.json
- docs/edge_robustness_report.md

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Crea o aggiorna la skill locale shadow-outcome-runtime-parity in
   .claude/skills/shadow-outcome-runtime-parity/SKILL.md, se supportato.
2. Delega:
   - shadow-outcome-agent: deduplicazione e risoluzione outcome;
   - runtime-parity-agent: confronto runtime/backtest;
   - execution-safety-agent: dimostrazione che nessun ordine venga aperto;
   - edge-case-agent: BUY, SELL, same-bar TP/SL, stale e duplicate bars;
   - test-review-agent: revisione indipendente.
3. execution-safety-agent deve poter bloccare la patch se rileva una possibile
   chiamata broker o mutazione dello stato paper.
4. Il coordinatore Claude integra e documenta ogni mismatch.

SHADOW OUTCOME

- Deduplicare segnali ripetuti sulla stessa candela usando un fingerprint
  stabile.
- Supportare BUY e SELL.
- Usare solamente candele successive al segnale.
- Risolvere TP, SL, TIME_EXIT, AMBIGUOUS e INSUFFICIENT_DATA.
- Calcolare gross R, costi, net R e bars_to_outcome.
- Applicare una regola conservativa quando TP e SL sono toccati nella stessa
  candela.
- Non trasformare segnali shadow in ordini.
- Non sovrascrivere distruttivamente il journal originale.

PARITA RUNTIME/BACKTEST

Confrontare sulla stessa candela:

- regime 1h
- condizioni e segnale 15m
- eventuale execution 5m
- indicatori
- entry, SL e TP
- parametri
- stale e duplicate bars
- arrotondamenti

OUTPUT RICHIESTI

- .claude/skills/shadow-outcome-runtime-parity/SKILL.md, se supportato
- data/selected_strategy_shadow_resolved_outcomes.jsonl
- data/multi_timeframe_runtime_parity.json
- docs/runtime_parity_and_shadow_report.md
- test automatici dedicati

GATE DI USCITA

PASS solamente se:

- nessun ordine e stato aperto;
- lo stato paper non e stato modificato;
- ogni mismatch runtime/backtest e spiegato;
- gli outcome risolti sono deduplicati e riproducibili.
```

---

## Prompt 7 - Validazione multi-asset e portafoglio

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Validare separatamente e successivamente come portafoglio le configurazioni
non respinte dalle fasi precedenti.

Usare rischio fisso `0,5%` per trade per ogni asset e per il portafoglio.
Non usare LOW, MEDIUM, HIGH, DYNAMIC o Kelly nella validazione principale.

ASSET

- BTC/USDT
- ETH/USDT
- XRP/USDT
- SOL/USDT
- BNB/USDT

PREREQUISITI

Leggi:

- data/edge_robustness_status.json
- data/multi_timeframe_runtime_parity.json
- docs/edge_robustness_report.md
- docs/runtime_parity_and_shadow_report.md

Usa solamente configurazioni con evidenza sufficiente per proseguire.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Crea o aggiorna la skill locale multi-asset-edge-validation in
   .claude/skills/multi-asset-edge-validation/SKILL.md, se supportato.
2. Delega:
   - per-asset-validation-agent: risultati indipendenti per ciascun asset;
   - portfolio-risk-agent: correlazione, esposizione e drawdown aggregato;
   - concentration-agent: concentrazione per asset, regime e periodo;
   - adversarial-review-agent: verifica che asset positivi non nascondano asset
     negativi;
   - test-review-agent: test indipendenti.
3. Quando possibile, usa un sub-agent separato per ogni asset.
4. Il coordinatore Claude deve mantenere risultati per asset separati prima
   dell'aggregazione.

VALIDAZIONE PER ASSET

Produrre separatamente:

- trade
- frequenza
- gross e net PnL
- net average R
- profit factor
- drawdown
- costi
- fold positivi
- risultati per regime
- concentrazione degli outlier

VALIDAZIONE PORTAFOGLIO

Considerare:

- correlazione tra asset e segnali
- esposizione simultanea
- concentrazione per asset e regime
- posizioni correlate
- drawdown complessivo
- frequenza reale dei trade
- rischio complessivo

Non compensare o nascondere un asset negativo aggregandolo con uno positivo.
Non permettere al sizing o alla leva di trasformare un asset negativo in un
risultato apparentemente positivo.

OUTPUT RICHIESTI

- .claude/skills/multi-asset-edge-validation/SKILL.md, se supportato
- trading_bot/run_multi_asset_edge_validation.py
- data/multi_asset_edge_validation.json
- docs/multi_asset_edge_validation_report.md
- test sulla gestione dell'esposizione e sull'aggregazione

GATE DI USCITA

Ogni asset e il portafoglio devono ricevere una classificazione indipendente.
```

---

## Prompt 8 - Gate finale, sintesi e roadmap successiva

```text
Lavora sul progetto:

C:\Users\Davide\Desktop\ProgettoTR-main

OBIETTIVO

Aggregare tutti gli artefatti prodotti dalle fasi precedenti, applicare gate
fail-closed e produrre la classificazione finale delle configurazioni.

PREREQUISITI

Leggi tutti gli artefatti prodotti dalle fasi 1-7. Non assumere PASS: verifica
ogni stato e ogni hash.

ORCHESTRAZIONE CLAUDE OBBLIGATORIA

1. Crea o aggiorna la skill locale edge-resolution-final-gate in
   .claude/skills/edge-resolution-final-gate/SKILL.md, se supportato.
2. Delega:
   - evidence-aggregation-agent: inventario e coerenza degli artefatti;
   - gate-evaluation-agent: applicazione meccanica dei gate;
   - adversarial-review-agent: tentativo indipendente di respingere ogni
     classificazione positiva;
   - safety-audit-agent: verifica live/testnet/broker/state mutation;
   - documentation-agent: sintesi e roadmap successiva;
   - test-review-agent: test end-to-end.
3. gate-evaluation-agent e adversarial-review-agent devono lavorare
   indipendentemente. Ogni disaccordo deve essere mostrato nel report.
4. safety-audit-agent ha diritto di veto.
5. Il coordinatore Claude e responsabile della classificazione finale.

CLASSIFICAZIONI CONSENTITE

- REJECTED
- INSUFFICIENT_EVIDENCE
- RESEARCH_ONLY
- EDGE_CANDIDATE

REQUISITI MINIMI PER EDGE_CANDIDATE

- net average R OOS positivo
- lower confidence bound di net average R maggiore di zero
- profit factor OOS post-costi maggiore di 1
- holdout finale positivo
- maggioranza dei fold positiva
- dipendenza limitata dai migliori trade
- risultati non concentrati in un solo asset o regime
- drawdown entro il limite configurato
- parita runtime/backtest verificata
- campione statisticamente sufficiente
- nessun veto del safety audit
- risultati ottenuti con rischio fisso `0,5%`, senza LOW, MEDIUM, HIGH,
  DYNAMIC o Kelly

Il 15m puo essere indicato come timeframe principale solamente se dimostra un
miglioramento robusto rispetto al 5m. Una minore frequenza o un drawdown
inferiore, da soli, non bastano.

Dynamic Risk non e un requisito per EDGE_CANDIDATE. Se viene analizzato, deve
apparire solamente come ablation successiva e separata, inizialmente
`reduce-only`. Un miglioramento prodotto dal Dynamic Risk non puo correggere
un average R OOS negativo o una significativita insufficiente.

OUTPUT RICHIESTI

- .claude/skills/edge-resolution-final-gate/SKILL.md, se supportato
- trading_bot/run_timeframe_edge_resolution.py
- data/timeframe_edge_resolution_status.json
- docs/timeframe_edge_resolution_report.md
- docs/timeframe_edge_resolution_next_roadmap.md
- test end-to-end

STAMPARE ALLA FINE

- pipeline_status
- data_integrity_status
- best_timeframe_candidate
- best_multi_timeframe_candidate
- edge_proven
- strategies_rejected
- strategies_insufficient_evidence
- strategies_research_only
- strategies_edge_candidate
- holdout_status
- estimated_trades_per_day
- runtime_backtest_parity
- live_trading_allowed
- testnet_allowed
- broker_calls
- paper_state_mutated
- files_created
- files_modified

VINCOLI FINALI

- Un PASS della pipeline non significa edge dimostrato.
- Non abilitare live trading, testnet o broker.
- Non promuovere automaticamente strategie.
- Non dichiarare EDGE_CANDIDATE in presenza di evidenza mancante.
- Mantenere sempre live_trading_allowed=false.

GATE DI USCITA

La fase termina con:

- PASS_WITH_EDGE_CANDIDATE solamente se almeno una configurazione soddisfa
  integralmente tutti i gate;
- PASS_WITHOUT_PROVEN_EDGE se la pipeline e valida ma nessuna configurazione
  supera tutti i gate;
- BLOCKED se artefatti, test, parita runtime o safety audit sono incompleti.

Qualunque stato deve mantenere live_trading_allowed=false.
```

---

## Regola di handoff tra sessioni

Al termine di ogni prompt, chiedere a Claude di aggiungere nel report della
fase una sezione `HANDOFF_FOR_NEXT_PHASE` contenente:

- stato del gate;
- artefatti approvati;
- artefatti respinti;
- hash degli input principali;
- test eseguiti;
- problemi ancora aperti;
- modifiche non correlate trovate e lasciate intatte;
- comando esatto consigliato per avviare la fase successiva.

Non avviare automaticamente la fase successiva nella stessa sessione.
