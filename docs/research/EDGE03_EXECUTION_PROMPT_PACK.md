# Edge Research 03 — Prompt pack di esecuzione locale

Prompt da eseguire in sequenza sul PC (rete abilitata), una fase per sessione.
Ogni fase ha un criterio di STOP esplicito: se fallisce, NON proseguire alla
fase successiva. Live/testnet/exchange restano disabilitati per tutto il
programma; nulla viene promosso al paper runtime.

> Prerequisito branch: fondere in `strat/edge-research-03` sia il branch di
> lavoro cloud (cost model 4h/1d, funding, gate panel, scaffold edge03) sia
> `strat/edge-research-02` (downloader sha256 + panel point-in-time + label
> di regime). Riconciliare al merge: naming cache, firma del panel loader,
> serie label di regime.

---

## Fase 0 — Ambiente e branch

```text
Prompt: Checkout del branch strat/edge-research-03. Installa i requirements
(pip install -r trading_bot/requirements.txt e requirements-dev.txt). Esegui
l'intera suite pytest e python trading_bot/run_cost_model_validation.py.
```

**STOP se:** un test fallisce o il validation runner non esce con 0 (gate PASS).

## Fase 1 — Acquisizione dati

```text
Prompt: Con il downloader sha256-verified di strat/edge-research-02, scarica da
data.binance.vision per i 16 simboli del panel: (a) klines mensili+giornalieri
4h e 1d; (b) archivi mensili fundingRate. Target 6,4 anni dove disponibili;
se lo storico manca, dichiaralo (regola di insufficienza onesta, niente dati
sintetici). Costruisci le cache parquet con le convenzioni:
{slug}_{tf}_cache.parquet (klines, colonne datetime/Open/High/Low/Close/Volume)
e {slug}_funding.parquet (colonne datetime/symbol/funding_rate, rate decimale).
```

**Verifica obbligatoria al primo download funding:** lo schema reale degli
archivi (`calc_time` vs `fundingTime`, `last_funding_rate` vs `fundingRate`,
unità, timezone) va controllato e mappato esplicitamente nel converter —
mapping fail-closed, niente supposizioni. Verificare anche l'intervallo di
settlement per simbolo: non è universalmente 8h (alcuni simboli sono passati a
4h o 1h); l'audit usa l'allowlist {8h, 4h, 1h} rilevata per file.

**STOP se:** sha256 mismatch, schema non riconosciuto, o storico dichiarato
insufficiente per più di metà del panel.

## Fase 2 — Gate di integrità

```text
Prompt: Esegui python trading_bot/run_market_data_integrity_audit.py.
Il raw_data_gate (incluse le serie funding) deve essere PASS.
```

**STOP se:** `raw_data_gate=BLOCKED`. Correggere i dati, mai i check.

## Fase 3 — Dichiarazione ex-ante dei trial

```text
Prompt: Compila docs/research/edge03_trial_declaration_template.md (ipotesi
economica, criteri di kill, griglia con motivazione per ogni config). Registra
le griglie con declare_trials("tsmom", ...) e
declare_trials("funding_carry", ...) — max 12 + 12 config, numerazione
cumulativa 85…108. Committa template compilato e
data/research/edge03_trial_log.json PRIMA di qualunque run.
```

**Da qui in poi nessuna config può cambiare.** Le run su config non dichiarate
falliscono per costruzione (`assert_declared`).

## Fase 4 — Ricerca train/validation

```text
Prompt: Per ogni config dichiarata esegui run_trial_on_panel (research/edge03/
panel_runner.py) sul segmento train/validation (il final OOS 2025-02-24 →
2026-06-10 + dati successivi resta intatto). Scenario conservative, rischio
0.005. Per la famiglia carry: funding_enabled=True e risultati riportati con e
senza funding. Usa panel_oos_with_warmup con declared_max_lookback_bars della
config (obbligatorio). Registra OGNI trial nel report, anche i fallimenti.
```

Analisi richiesta: parameter plateau (config vicine devono comportarsi in modo
simile: un optimum isolato è rumore), densità segnali, turnover, cost-to-edge.

**STOP (kill di famiglia) se:** i criteri di kill dichiarati in Fase 3 scattano.

## Fase 5 — Selezione robusta

```text
Prompt: Sui sopravvissuti della Fase 4: Deflated Sharpe Ratio, PBO via CSCV,
regime_stratified_check con le label di regime del ciclo 2 (richiesto net
PnL > 0 in ≥ 2 regimi), rerun con scenario severe (deve restare positivo),
concentrazione temporale mensile, top-3 trade ≤ 35% del lordo positivo.
```

Diagnostica facoltativa ma raccomandata: confronto spread/slippage realizzati
su alcune entry 4h large-cap vs il modello (tf_mult=1.0 è un'assunzione
conservativa ma è un'assunzione) — solo diagnostica, nessuna ricalibrazione
senza dichiararla.

**STOP se:** nessun sopravvissuto → andare direttamente alla Fase 7 con
NO_CANDIDATE.

## Fase 6 — Accesso unico al final OOS

```text
Prompt: SOLO per i sopravvissuti della Fase 5, UNA volta: esegui sul final OOS
(2025-02-24 → 2026-06-10 + dati più recenti) i 10 gate di STRAT-03-V2 (50 trade
pooled, PF > 1.20, net PnL > 0, DD ≤ 15%, DSR ≥ 0.95, PBO < 0.50, severe
positivo, top-3 ≤ 35%, gate mensile, gate di regime, nessuna contaminazione).
Emetti edge_demonstrated=true/false.
```

**NO_CANDIDATE è una risposta valida e finale. Non iterare contro il final
OOS: qualunque seconda passata lo brucia e chiude comunque il programma.**

## Fase 7 — Chiusura

```text
Prompt: Committa tutti i report (trial log, per-trial, selezione robusta,
final OOS), pusha strat/edge-research-03 e riporta l'esito. Se
edge_demonstrated=true: procedere a STRAT-04-V2 (integrazione dietro flag
disabilitato + campagna paper supervisionata). Se NO_CANDIDATE: il programma
chiude — è l'ultima riapertura dichiarata, nessuna V3 senza cambiamento
documentato delle assunzioni di mercato/costo.
```
