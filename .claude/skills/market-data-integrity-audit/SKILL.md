# Skill: market-data-integrity-audit

## Scopo

Verifica l'integrità, la provenienza e l'isolamento dei dataset OHLCV usati nei backtest e nei benchmark. Fail-closed: blocca le fasi successive se i dati sono contaminati, incompleti o privi di metadati tracciabili.

## Controlli implementati

### 1. Inventario raw data
- Scoperta dinamica di tutti i file `.parquet` (esclude `market_features.parquet`)
- Inferenza asset/timeframe dal nome file
- Conteggio righe, periodo, nomi colonne

### 2. Integrità temporale
- **Gap**: diffs > 1.5x intervallo modale → flag
- **Duplicati**: timestamp identici → flag
- **Fuori-ordine**: diff < 0 → flag

### 3. Integrità OHLC
- `High < max(Open, Close)` → violation
- `Low > min(Open, Close)` → violation
- Null in Open/High/Low/Close/Volume → flag

### 4. Verifica aggregazione 5m → 15m (Prompt 3A — aggiornata)
```python
agg15 = df5.resample('15min', closed='left', label='left').agg({
    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
})
```
- Ratio atteso 3.0 (150k / 50k)
- **Overlap completo** (non sample limitato) — Prompt 3A: sample fisso di 500 bar non basta
- **Tutte e 5 le colonne OHLCV confrontate** — Prompt 3A: prima solo Close
- `closed='left', label='left'` espliciti (convenzione Binance)
- Output include `columns_checked` e `per_column_mismatches` per colonna
- `sample_size` = numero di bar nell'overlap completo

### 5. Contaminazione report (hash deduplication)
```python
hashlib.md5(Path(report_file).read_bytes()).hexdigest()
```
- Raggruppa per hash tutti i file `signal_density_report.json`, `paper_readiness_report.json`, `archetype_performance_report.json`, `walkforward_audit_report.json`, `lifecycle_consistency_report.json`
- Gruppi con >1 file → CONTAMINATED
- Verifica che `signal_density_report.json` contenga campi `timeframe`, `asset`, `symbol`, `generated_at`

### 6. Lookahead guard
- Legge `trading_bot/clean_bot/paper_live.py` come testo
- Cerca `len(df) - 2` → conferma uso barra completata
- Cerca guard stale/duplicate bar

### 7. Serie funding (Edge Research 03)

I file `*_funding*.parquet` sono input di ricerca grezzi ma NON OHLCV: vengono instradati a `_check_funding_file()` e tenuti in un inventario separato (`funding_inventory`), mai passati a `_check_ohlcv_file()`.

Controlli (contratto dati: `trading_bot/clean_bot/funding.py`):
- Colonne richieste: `datetime`, `symbol`, `funding_rate`
- Timestamp UTC parseabili, ordinati, senza duplicati né out-of-order
- **Griglia**: timestamp a ore intere; intervallo modale nell'allowlist {1h, 4h, 8h} (Binance ha spostato alcuni simboli USDT-M dal classico 8h al 4h) — rilevato per file, non hardcoded
- **Gap**: diffs > 1.5x intervallo modale → reject (riporta `modal_interval_hours` e `gap_count`)
- Null → reject
- **Range sanity**: `|funding_rate| < 0.0075` (decimale, 0.0001 = 1 bp) — conteggia e respinge le violazioni
- Coerenza per-riga tra `symbol` e slug del filename (`btcusdt_funding.parquet` → tutte le righe BTC/USDT)

Routing gate: i reject delle serie funding confluiscono in `raw_data_gate`. L'**assenza** di file funding NON è un failure (le run carry sono opt-in).

## Architettura a 3 livelli (Prompt 2H)

I gate sono separati. `benchmark_readiness_gate=PASS` è il segnale che autorizza la Fase 3, indipendentemente da `gate_result` (che resta BLOCKED finché i derived artifacts sono contaminati).

| Gate | Condizione PASS | Uso |
|------|----------------|-----|
| `raw_data_gate` | Nessun raw OHLCV rifiutato | Dati grezzi sicuri |
| `derived_artifact_gate` | Nessuna contaminazione in report derivati | Artifact DQ |
| `benchmark_readiness_gate` | raw_data_gate=PASS + aggregation=PASS + no lookahead | Autorizza Fase 3 |
| `gate_result` | Tutti e 3 i gate PASS | Gate complessivo |

**Regola:** Phase 3 usa solo raw OHLCV (non i report derivati contaminati). Quindi `benchmark_readiness_gate=PASS` è sufficiente per procedere anche quando `gate_result=BLOCKED`.

### Category B tests (diagnostici)

I test Category B NON devono fallire la CI quando trovano anomalie: usano `warnings.warn(UserWarning)` e passano sempre. Questo evita l'inversione semantica del vecchio pattern `assert md5_5m == md5_15m` (che passava quando la contaminazione era presente).

Test diagnostici corretti:
- `test_signal_density_contamination_diagnostic` — emette UserWarning se contaminazione presente, PASS sempre
- `test_signal_density_missing_metadata_diagnostic` — idem
- `test_timeframe_runs_contamination_diagnostic` — idem

## Schema output (`data/market_data_integrity_status.json`)

```json
{
  "audit_timestamp": "<ISO>",
  "diagnostic_only": true,
  "opens_orders": false,
  "live_trading_allowed": false,
  "raw_data_inventory": [...],
  "report_contamination": {...},
  "timeframe_runs_contamination": {...},
  "aggregation_check": {"status": "PASS", "sample_size": 500, ...},
  "lookahead_check": {...},
  "missing_15m_data": [...],
  "approved_datasets": [...],
  "rejected_datasets": [...],
  "funding_inventory": [...],
  "approved_funding_datasets": [...],
  "rejected_funding_datasets": [...],
  "raw_data_gate": "PASS|BLOCKED",
  "derived_artifact_gate": "PASS|BLOCKED",
  "benchmark_readiness_gate": "PASS|BLOCKED",
  "pipeline_status": "PASS|BLOCKED",
  "gate_result": "PASS|BLOCKED",
  "gate_reasons": [...]
}
```

## Regole fail-closed

| Condizione | Gate |
|-----------|------|
| Gap/duplicate/OOO nei raw data | BLOCKED |
| Null nei raw data | BLOCKED |
| Report senza metadati asset/timeframe | BLOCKED |
| File di report con hash duplicati cross-timeframe | BLOCKED (warning se intra-scenario) |
| `timeframe_runs/` non indipendente da `multi_asset_runs/` | BLOCKED |
| Mancanza dati 15m per asset richiesti nel benchmark | BLOCKED |
| 5m→15m aggregation mismatch > 0 | BLOCKED |
| Lookahead: barra non completata usata | BLOCKED |
| Serie funding: gap/null/off-grid/cap `|rate|`≥0.75%/symbol mismatch | BLOCKED (raw_data_gate) |
| Serie funding assente (nessuna run carry richiesta) | non è un failure |

## Comandi

```bash
# Esegui audit completo
python trading_bot/run_market_data_integrity_audit.py

# Esegui solo i test
python -m pytest trading_bot/tests/test_market_data_integrity.py -v

# Output
cat data/market_data_integrity_status.json | python -m json.tool | head -50
```

## Dataset approvati (audit 2026-06-06)

| File | Asset | Timeframe | Righe | Periodo |
|------|-------|-----------|-------|---------|
| `btc_5m_150k_cache.parquet` | BTC/USDT | 5m | 150000 | 2024-11-20 → 2026-04-25 |
| `btc_15m_50k_cache.parquet` | BTC/USDT | 15m | 50000 | 2024-11-20 → 2026-04-25 |
| `btc_15m_cache.parquet` | BTC/USDT | 15m | 1000 | 2026-05-11 → 2026-05-21 |
| `xrpusdt_5m_150k_cache.parquet` | XRP/USDT | 5m | 150000 | 2024-11-20 → 2026-04-25 |
| `ethusdt_5m_150k_cache.parquet` | ETH/USDT | 5m | 150000 | 2024-11-20 → 2026-04-25 |
| `solusdt_5m_150k_cache.parquet` | SOL/USDT | 5m | 150000 | 2024-11-20 → 2026-04-25 |
| `bnbusdt_5m_150k_cache.parquet` | BNB/USDT | 5m | 150000 | 2024-11-20 → 2026-04-25 |
| `xrpusdt_1m_cache.parquet` | XRP/USDT | 1m | 129599 | 2026-03-04 → 2026-06-02 |

## Dataset / report respinti

| Percorso | Motivo |
|---------|--------|
| `data/timeframe_runs/5m/` | Copia esatta di `multi_asset_runs/btcusdt/5m/base` |
| `data/timeframe_runs/15m/` | Copia esatta di `multi_asset_runs/btcusdt/15m` |
| `*/signal_density_report.json` (tutti) | Nessun metadato asset/timeframe/generated_at |
| `multi_asset_runs/btcusdt/5m/base/` | Duplicato di `timeframe_runs/5m/` |
| `multi_asset_runs/btcusdt/15m/conservative/` | Duplicato di `btcusdt/15m/` |
| `multi_asset_runs/bnbusdt/5m/severe/` | Duplicato di `bnbusdt/5m/` (walkforward, archetype, paper_readiness) |

## Nota su 15m non-BTC

Non esistono file parquet 15m per XRP/ETH/SOL/BNB. Per un benchmark multi-asset 5m vs 15m, il Phase 3 deve aggregare i file 5m a 15m on-the-fly usando la funzione di aggregazione verificata in questa fase.
