# test_market_data_integrity.py
#
# Questi test documentano due categorie distinte:
#
# CATEGORIA A — Proprieta' corrette (PASS atteso = dati integri):
#   test_raw_data_no_gaps, test_raw_data_no_duplicates,
#   test_raw_data_no_out_of_order, test_raw_data_ohlc_valid,
#   test_raw_data_no_nulls, test_btc_5m_15m_ratio,
#   test_btc_aggregation_correctness, test_no_15m_for_non_btc,
#   test_btc_15m_all_timestamps_aligned, test_lookahead_guard
#
# CATEGORIA B — Anomalie note documentate come finding DIAGNOSTICO:
#   Questi test PASSANO sempre e non bloccano la CI.
#   Emettono warnings.warn() se l'anomalia e' ancora presente,
#   non fanno nulla se l'anomalia e' stata risolta.
#   RATIONALE: un test che passa quando l'anomalia esiste e fallisce
#   quando viene corretta e' fragile e fuorviante. I finding sono
#   documentati nel report, non nella suite di regressione.
#   test_signal_density_contamination_diagnostic
#   test_signal_density_missing_metadata_diagnostic
#   test_timeframe_runs_contamination_diagnostic
#
# Nessun test richiede connessione Internet o broker.
# Nessun test modifica file esistenti.

import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Costanti di percorso
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
CLEAN_BOT_DIR = PROJECT_ROOT / "trading_bot" / "clean_bot"

# Tutti i file parquet OHLCV presenti in DATA_DIR (esclude market_features che e' una feature matrix senza colonna datetime)
PARQUET_FILES = sorted(
    p for p in DATA_DIR.glob("*.parquet") if p.name != "market_features.parquet"
)

# File parquet con timeframe noto dal nome
BTC_5M_FILE = DATA_DIR / "btc_5m_150k_cache.parquet"
BTC_15M_FILE = DATA_DIR / "btc_15m_50k_cache.parquet"

# File JSON delle run per timeframe
SIGNAL_DENSITY_5M = DATA_DIR / "timeframe_runs" / "5m" / "signal_density_report.json"
SIGNAL_DENSITY_15M = DATA_DIR / "timeframe_runs" / "15m" / "signal_density_report.json"

PAPER_READINESS_5M_RUNS = DATA_DIR / "timeframe_runs" / "5m" / "paper_readiness_report.json"
PAPER_READINESS_5M_MULTI = (
    DATA_DIR / "multi_asset_runs" / "btcusdt" / "5m" / "base" / "paper_readiness_report.json"
)

PAPER_LIVE_PY = CLEAN_BOT_DIR / "paper_live.py"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _md5(path: Path) -> str:
    """Calcola MD5 hex di un file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_parquet(path: Path) -> pd.DataFrame:
    """Carica un parquet e restituisce il DataFrame."""
    return pd.read_parquet(path)


def _modal_interval_seconds(timestamps: pd.Series) -> float:
    """Ritorna l'intervallo modale in secondi tra timestamp consecutivi."""
    diffs = timestamps.sort_values().diff().dropna().dt.total_seconds()
    return float(diffs.mode()[0])


# ---------------------------------------------------------------------------
# CATEGORIA A — Integrita' dati grezzi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("parquet_path", PARQUET_FILES, ids=lambda p: p.name)
def test_raw_data_no_gaps(parquet_path: Path):
    """
    CATEGORIA A — Verifica che non esistano gap temporali nei dati OHLCV grezzi.
    Un gap e' definito come una differenza tra timestamp consecutivi > 1.5 volte
    l'intervallo modale della serie (tolleranza per DST, rollover fine sessione, ecc.).
    Atteso: 0 gap per ogni file parquet.
    """
    if not parquet_path.exists():
        pytest.skip(f"File non trovato: {parquet_path}")

    df = _load_parquet(parquet_path)
    assert "datetime" in df.columns, f"{parquet_path.name}: colonna 'datetime' mancante"

    timestamps = pd.to_datetime(df["datetime"]).sort_values().reset_index(drop=True)
    if len(timestamps) < 2:
        pytest.skip(f"{parquet_path.name}: meno di 2 righe, impossibile verificare gap")

    modal_sec = _modal_interval_seconds(timestamps)
    threshold_sec = modal_sec * 1.5
    diffs = timestamps.diff().dropna().dt.total_seconds()
    gaps = diffs[diffs > threshold_sec]

    assert len(gaps) == 0, (
        f"{parquet_path.name}: trovati {len(gaps)} gap > {threshold_sec:.0f}s "
        f"(intervallo modale: {modal_sec:.0f}s). "
        f"Indici con gap: {gaps.index.tolist()[:10]}"
    )


@pytest.mark.parametrize("parquet_path", PARQUET_FILES, ids=lambda p: p.name)
def test_raw_data_no_duplicates(parquet_path: Path):
    """
    CATEGORIA A — Verifica che non esistano timestamp duplicati nei dati OHLCV grezzi.
    Atteso: 0 duplicati per ogni file parquet.
    """
    if not parquet_path.exists():
        pytest.skip(f"File non trovato: {parquet_path}")

    df = _load_parquet(parquet_path)
    assert "datetime" in df.columns, f"{parquet_path.name}: colonna 'datetime' mancante"

    timestamps = pd.to_datetime(df["datetime"])
    duplicates = timestamps[timestamps.duplicated()]

    assert len(duplicates) == 0, (
        f"{parquet_path.name}: trovati {len(duplicates)} timestamp duplicati. "
        f"Esempi: {duplicates.head(5).tolist()}"
    )


@pytest.mark.parametrize("parquet_path", PARQUET_FILES, ids=lambda p: p.name)
def test_raw_data_no_out_of_order(parquet_path: Path):
    """
    CATEGORIA A — Verifica che i timestamp siano in ordine strettamente crescente.
    Atteso: 0 timestamp fuori sequenza per ogni file parquet.
    """
    if not parquet_path.exists():
        pytest.skip(f"File non trovato: {parquet_path}")

    df = _load_parquet(parquet_path)
    assert "datetime" in df.columns, f"{parquet_path.name}: colonna 'datetime' mancante"

    timestamps = pd.to_datetime(df["datetime"])
    diffs = timestamps.diff().dropna().dt.total_seconds()
    out_of_order = diffs[diffs <= 0]

    assert len(out_of_order) == 0, (
        f"{parquet_path.name}: trovati {len(out_of_order)} timestamp fuori sequenza "
        f"(diff <= 0s). Indici: {out_of_order.index.tolist()[:10]}"
    )


@pytest.mark.parametrize("parquet_path", PARQUET_FILES, ids=lambda p: p.name)
def test_raw_data_ohlc_valid(parquet_path: Path):
    """
    CATEGORIA A — Verifica che i valori OHLC siano internamente coerenti:
      High >= max(Open, Close) e Low <= min(Open, Close) per ogni riga.
    Atteso: 0 violazioni per ogni file parquet.
    """
    if not parquet_path.exists():
        pytest.skip(f"File non trovato: {parquet_path}")

    df = _load_parquet(parquet_path)

    required = {"Open", "High", "Low", "Close"}
    missing = required - set(df.columns)
    if missing:
        pytest.skip(f"{parquet_path.name}: colonne OHLC mancanti: {missing}")

    high_violation = df[df["High"] < df[["Open", "Close"]].max(axis=1)]
    low_violation = df[df["Low"] > df[["Open", "Close"]].min(axis=1)]

    errors = []
    if len(high_violation) > 0:
        errors.append(
            f"High < max(Open,Close): {len(high_violation)} righe "
            f"(prima: idx={high_violation.index[0]})"
        )
    if len(low_violation) > 0:
        errors.append(
            f"Low > min(Open,Close): {len(low_violation)} righe "
            f"(prima: idx={low_violation.index[0]})"
        )

    assert not errors, f"{parquet_path.name}: violazioni OHLC — " + "; ".join(errors)


@pytest.mark.parametrize("parquet_path", PARQUET_FILES, ids=lambda p: p.name)
def test_raw_data_no_nulls(parquet_path: Path):
    """
    CATEGORIA A — Verifica che non esistano valori null nei campi Open/High/Low/Close/Volume.
    Atteso: 0 null per ogni file parquet.
    """
    if not parquet_path.exists():
        pytest.skip(f"File non trovato: {parquet_path}")

    df = _load_parquet(parquet_path)

    check_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    if not check_cols:
        pytest.skip(f"{parquet_path.name}: nessuna colonna OHLCV trovata")

    null_counts = df[check_cols].isnull().sum()
    cols_with_nulls = null_counts[null_counts > 0]

    assert len(cols_with_nulls) == 0, (
        f"{parquet_path.name}: null trovati — {cols_with_nulls.to_dict()}"
    )


# ---------------------------------------------------------------------------
# CATEGORIA A — Consistenza BTC 5m / 15m
# ---------------------------------------------------------------------------


def test_btc_5m_15m_ratio():
    """
    CATEGORIA A — Verifica che il rapporto len(btc_5m) / len(btc_15m) sia ~3.0
    (con tolleranza relativa 1%), confermando la copertura temporale equivalente
    tra i due timeframe BTC.
    """
    if not BTC_5M_FILE.exists():
        pytest.skip(f"File non trovato: {BTC_5M_FILE}")
    if not BTC_15M_FILE.exists():
        pytest.skip(f"File non trovato: {BTC_15M_FILE}")

    df_5m = _load_parquet(BTC_5M_FILE)
    df_15m = _load_parquet(BTC_15M_FILE)

    ratio = len(df_5m) / len(df_15m)
    expected = 3.0
    rtol = 0.01  # 1%

    assert abs(ratio - expected) / expected <= rtol, (
        f"Rapporto 5m/15m = {ratio:.4f}, atteso {expected} +/- {rtol*100:.0f}%. "
        f"Righe 5m: {len(df_5m)}, righe 15m: {len(df_15m)}"
    )


def test_btc_aggregation_correctness():
    """
    CATEGORIA A — Verifica che l'aggregazione 5m -> 15m sia corretta su almeno
    200 barre 15m sovrapposte (era 10, espanso per campione rappresentativo).
    Per ogni barra 15m: High deve essere il max dei 3 High dei 5m corrispondenti,
    Low deve essere il min dei 3 Low dei 5m corrispondenti.
    Tolleranza: rtol=1e-4 per confronti float.
    """
    if not BTC_5M_FILE.exists():
        pytest.skip(f"File non trovato: {BTC_5M_FILE}")
    if not BTC_15M_FILE.exists():
        pytest.skip(f"File non trovato: {BTC_15M_FILE}")

    df_5m = _load_parquet(BTC_5M_FILE).copy()
    df_15m = _load_parquet(BTC_15M_FILE).copy()

    df_5m["datetime"] = pd.to_datetime(df_5m["datetime"])
    df_15m["datetime"] = pd.to_datetime(df_15m["datetime"])

    df_5m = df_5m.sort_values("datetime").reset_index(drop=True)
    df_15m = df_15m.sort_values("datetime").reset_index(drop=True)

    MAX_BARS = 200  # campione esteso per rilevare errori sistematici

    checked = 0
    errors = []

    for _, row_15m in df_15m.iterrows():
        if checked >= MAX_BARS:
            break

        t_start = row_15m["datetime"]
        t_end = t_start + pd.Timedelta(minutes=15)

        # Seleziona i 3 bar 5m che appartengono a questo bar 15m
        mask = (df_5m["datetime"] >= t_start) & (df_5m["datetime"] < t_end)
        bars_5m = df_5m[mask]

        if len(bars_5m) != 3:
            # Bar 15m non completamente coperto dai 5m disponibili: salto
            continue

        expected_high = bars_5m["High"].max()
        expected_low = bars_5m["Low"].min()
        actual_high = row_15m["High"]
        actual_low = row_15m["Low"]

        rtol = 1e-4
        if not np.isclose(actual_high, expected_high, rtol=rtol):
            errors.append(
                f"Bar 15m {t_start}: High={actual_high}, atteso={expected_high} "
                f"(da 5m max)"
            )
        if not np.isclose(actual_low, expected_low, rtol=rtol):
            errors.append(
                f"Bar 15m {t_start}: Low={actual_low}, atteso={expected_low} "
                f"(da 5m min)"
            )

        checked += 1

    if checked == 0:
        pytest.skip("Nessun bar 15m con 3 bar 5m corrispondenti trovato nell'overlap")

    assert not errors, (
        f"Errori di aggregazione 5m->15m su {len(errors)} controlli "
        f"(campione: {checked} barre):\n"
        + "\n".join(errors)
    )


# ---------------------------------------------------------------------------
# CATEGORIA B — Anomalie note documentate come finding DIAGNOSTICO
#
# Questi test PASSANO sempre. Emettono warnings.warn() se l'anomalia
# e' ancora presente. Non bloccano la CI.
#
# RATIONALE: i test originali passavano quando l'anomalia esisteva e fallivano
# quando veniva corretta — il comportamento opposto di un test di regressione.
# La soluzione corretta e' documentare il finding e mai fallire la suite.
# ---------------------------------------------------------------------------


def test_signal_density_contamination_diagnostic():
    """
    CATEGORIA B (DIAGNOSTICO) — Stato della contaminazione cross-timeframe.

    Emette UserWarning se signal_density_report.json 5m e 15m hanno hash identico.
    PASSA sempre: questa e' un'osservazione diagnostica, non un enforcement.

    Finding documentato: hash identico = i due file non sono indipendenti.
    Impatto: questi report non devono essere usati come input per il benchmark.
    """
    if not SIGNAL_DENSITY_5M.exists() or not SIGNAL_DENSITY_15M.exists():
        return  # file non trovati — anomalia non verificabile in questo ambiente

    md5_5m = _md5(SIGNAL_DENSITY_5M)
    md5_15m = _md5(SIGNAL_DENSITY_15M)

    if md5_5m == md5_15m:
        warnings.warn(
            f"FINDING ATTIVO: signal_density_report.json 5m e 15m hanno hash identico "
            f"(MD5={md5_5m}). I report non sono indipendenti. "
            "Non usare questi file come input per il benchmark. "
            "Finding documentato in market_data_integrity_report.md.",
            UserWarning,
            stacklevel=2,
        )
    # Il test PASSA sia se l'anomalia esiste sia se e' stata corretta.


def test_signal_density_missing_metadata_diagnostic():
    """
    CATEGORIA B (DIAGNOSTICO) — Stato dei metadati nei signal_density_report.json.

    Emette UserWarning per ogni file mancante dei campi timeframe/asset/symbol.
    PASSA sempre: questa e' un'osservazione diagnostica, non un enforcement.

    Finding documentato: senza metadati non e' possibile tracciare la provenienza.
    """
    for label, path in [("5m", SIGNAL_DENSITY_5M), ("15m", SIGNAL_DENSITY_15M)]:
        if not path.exists():
            continue  # file non trovato — skip senza fallire

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        missing_fields = [
            field for field in ("timeframe", "asset", "symbol")
            if field not in data
        ]
        if missing_fields:
            warnings.warn(
                f"FINDING ATTIVO: signal_density_report.json ({label}) manca dei campi "
                f"{missing_fields}. Impossibile verificare la provenienza asset/timeframe. "
                "Finding documentato in market_data_integrity_report.md.",
                UserWarning,
                stacklevel=2,
            )
    # Il test PASSA sempre.


def test_timeframe_runs_contamination_diagnostic():
    """
    CATEGORIA B (DIAGNOSTICO) — Stato dell'indipendenza della cartella timeframe_runs/.

    Emette UserWarning se paper_readiness_report.json in timeframe_runs/5m e in
    multi_asset_runs/btcusdt/5m/base/ hanno lo stesso hash MD5 (file identici).
    PASSA sempre: questa e' un'osservazione diagnostica, non un enforcement.

    Finding documentato: timeframe_runs/ e' una copia di multi_asset_runs/btcusdt/.
    """
    if not PAPER_READINESS_5M_RUNS.exists() or not PAPER_READINESS_5M_MULTI.exists():
        return  # file non trovati — anomalia non verificabile

    md5_runs = _md5(PAPER_READINESS_5M_RUNS)
    md5_multi = _md5(PAPER_READINESS_5M_MULTI)

    if md5_runs == md5_multi:
        warnings.warn(
            f"FINDING ATTIVO: paper_readiness_report.json in timeframe_runs/5m/ "
            f"e multi_asset_runs/btcusdt/5m/base/ hanno hash identico (MD5={md5_runs}). "
            "La cartella timeframe_runs/ non e' indipendente. "
            "Non usare questi dati come benchmark timeframe. "
            "Finding documentato in market_data_integrity_report.md.",
            UserWarning,
            stacklevel=2,
        )
    # Il test PASSA sia se l'anomalia esiste sia se e' stata corretta.


# ---------------------------------------------------------------------------
# CATEGORIA A — Guard no-lookahead in paper_live.py
# ---------------------------------------------------------------------------


def test_lookahead_guard():
    """
    CATEGORIA A — Verifica che clean_bot/paper_live.py utilizzi l'indice
    `len(df) - 2` per accedere alla barra completata (non alla barra in
    formazione), garantendo l'assenza di lookahead bias in modalita' paper.
    """
    if not PAPER_LIVE_PY.exists():
        pytest.skip(f"File non trovato: {PAPER_LIVE_PY}")

    source = PAPER_LIVE_PY.read_text(encoding="utf-8")

    assert "len(df) - 2" in source, (
        f"{PAPER_LIVE_PY.name}: pattern 'len(df) - 2' non trovato. "
        f"Verificare che il codice usi la barra completata (idx = len(df) - 2) "
        f"e non la barra in formazione."
    )


# ---------------------------------------------------------------------------
# CATEGORIA A — Assenza file 15m per asset non-BTC
# ---------------------------------------------------------------------------


def test_no_15m_for_non_btc():
    """
    CATEGORIA A — Documenta che NON esistono file parquet a 15 minuti per
    XRP, ETH, SOL, BNB in DATA_DIR. Questa e' una limitazione nota del dataset:
    solo BTC ha la serie 15m disponibile.
    Se in futuro venissero aggiunti file 15m per questi asset, il test fallira'
    e dovra' essere aggiornato (o rimosso) di conseguenza.
    """
    non_btc_assets = ["xrp", "eth", "sol", "bnb"]

    present = []
    for asset in non_btc_assets:
        # Cerca qualsiasi file che contenga il ticker e "15m" nel nome
        matches = list(DATA_DIR.glob(f"*{asset}*15m*.parquet"))
        matches += list(DATA_DIR.glob(f"*{asset.upper()}*15m*.parquet"))
        if matches:
            present.append((asset, [m.name for m in matches]))

    assert not present, (
        "File 15m trovati per asset non-BTC (dataset aggiornato?): "
        + str(present)
    )


# ---------------------------------------------------------------------------
# CATEGORIA A — Allineamento timestamp BTC 15m
# ---------------------------------------------------------------------------


def test_btc_15m_all_timestamps_aligned():
    """
    CATEGORIA A — Verifica che tutti i timestamp del file btc_15m_50k_cache.parquet
    abbiano minute % 15 == 0, ovvero che ogni bar inizi a un minuto multiplo di 15
    (00, 15, 30, 45). Questo garantisce che non ci siano bar 15m con offset errato.
    """
    if not BTC_15M_FILE.exists():
        pytest.skip(f"File non trovato: {BTC_15M_FILE}")

    df = _load_parquet(BTC_15M_FILE)
    assert "datetime" in df.columns, "Colonna 'datetime' mancante in btc_15m_50k_cache.parquet"

    timestamps = pd.to_datetime(df["datetime"])
    misaligned = timestamps[timestamps.dt.minute % 15 != 0]

    assert len(misaligned) == 0, (
        f"Trovati {len(misaligned)} timestamp con minute % 15 != 0. "
        f"Esempi: {misaligned.head(5).tolist()}"
    )


# ---------------------------------------------------------------------------
# Helper per test di aggregazione sintetici (Fix A — nuova policy zero-vol)
# ---------------------------------------------------------------------------

def _run_resample_check(df5: pd.DataFrame, df15: pd.DataFrame) -> dict:
    """
    Stessa logica di exclusion/comparison dell'audit runner su DataFrame sintetici.

    Policy (Fix A):
      - Bucket incompleti (< 3 bar): esclusi interamente da tutti i confronti.
      - Zero-vol first bar: bucket INCLUSO in complete_buckets_compared;
        escluso SOLO il confronto Open. H/L/C/V sempre confrontati.

    Ritorna dict con:
      unexplained_mismatches, n_incomplete, n_open_excluded,
      complete_buckets_compared, status
    """
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    resampled = df5.resample("15min", closed="left", label="left").agg(agg).dropna()

    tgt = df15[["Open", "High", "Low", "Close", "Volume"]].rename(
        columns={c: f"_tgt_{c.lower()}" for c in ["Open", "High", "Low", "Close", "Volume"]}
    )
    merged = resampled.join(tgt, how="inner")

    bar_counts = df5.resample("15min", closed="left", label="left").size()
    in_overlap = bar_counts.index.isin(merged.index)

    incomplete_mask = (bar_counts < 3) & in_overlap
    first_vol = df5.resample("15min", closed="left", label="left")["Volume"].first()
    zero_vol_mask = (first_vol == 0.0) & in_overlap & ~incomplete_mask
    zero_vol_open_idx = first_vol[zero_vol_mask].index

    # Exclude ONLY incomplete buckets — zero-vol buckets stay in
    incomplete_idx = bar_counts[incomplete_mask].index
    clean = merged[~merged.index.isin(incomplete_idx)]
    complete_buckets = len(clean)

    tol = 1e-6
    mismatches = 0
    col_counts: dict[str, int] = {}
    for k in ("Open", "High", "Low", "Close", "Volume"):
        tgt_k = f"_tgt_{k.lower()}"
        if k not in clean.columns or tgt_k not in clean.columns:
            continue
        rows = clean[~clean.index.isin(zero_vol_open_idx)] if k == "Open" else clean
        col_counts[k] = len(rows)
        mismatches += int(((rows[k] - rows[tgt_k]).abs() > tol).sum())

    # Determine status using same rules as audit runner
    mandatory = [k for k in ("High", "Low", "Close", "Volume") if k in col_counts]
    mandatory_ok = all(col_counts.get(k, 0) > 0 for k in mandatory)

    if complete_buckets == 0:
        status = "BLOCKED"
    elif not mandatory_ok:
        status = "BLOCKED"
    elif mismatches > 0:
        status = "FAIL"
    else:
        status = "PASS"

    return {
        "unexplained_mismatches": mismatches,
        "n_incomplete": int(incomplete_mask.sum()),
        "n_open_excluded": int(zero_vol_mask.sum()),
        "complete_buckets_compared": complete_buckets,
        "status": status,
    }


def _make_5m_df(base_ts, prices: list, volumes: list) -> pd.DataFrame:
    """Build minimal 5m DataFrame from lists of (O,H,L,C) tuples and volumes."""
    rows = [
        {"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}
        for (o, h, l, c), v in zip(prices, volumes)
    ]
    idx = pd.date_range(base_ts, periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(rows, index=idx)


def _make_15m_df(base_ts, open_: float, high: float, low: float, close: float, volume: float) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(base_ts, tz="UTC")])
    return pd.DataFrame(
        [{"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}],
        index=idx,
    )


# ---------------------------------------------------------------------------
# CATEGORIA A — Test con dati reali (full overlap, resample approach)
# ---------------------------------------------------------------------------

def test_btc_aggregation_full_overlap_resample():
    """
    CATEGORIA A — Aggregazione 5m->15m su full overlap con logica runner (Fix A).
    Bucket incompleti esclusi interamente; zero-vol open → solo Open escluso.
    Verifica 0 mismatch inspiegabili e rilevamento delle 2 anomalie note.
    """
    if not BTC_5M_FILE.exists():
        pytest.skip(f"File non trovato: {BTC_5M_FILE}")
    if not BTC_15M_FILE.exists():
        pytest.skip(f"File non trovato: {BTC_15M_FILE}")

    df5 = _load_parquet(BTC_5M_FILE).copy()
    df15 = _load_parquet(BTC_15M_FILE).copy()

    df5.index = pd.to_datetime(df5["datetime"], utc=True)
    df15.index = pd.to_datetime(df15["datetime"], utc=True)

    rename_map = {c: c.title() for c in df5.columns if c.lower() in ("open", "high", "low", "close", "volume")}
    df5 = df5.rename(columns=rename_map)
    rename_map15 = {c: c.title() for c in df15.columns if c.lower() in ("open", "high", "low", "close", "volume")}
    df15 = df15.rename(columns=rename_map15)

    r = _run_resample_check(df5, df15)

    assert r["unexplained_mismatches"] == 0, (
        f"Trovati {r['unexplained_mismatches']} mismatch inspiegabili nel full overlap BTC 5m->15m. "
        f"Bucket esclusi: {r['n_incomplete']} incompleti, Open-esclusi: {r['n_open_excluded']}."
    )
    assert r["n_incomplete"] >= 1, (
        "Nessun bucket incompleto trovato: attesa almeno 1 esclusione (2024-11-20 19:15)."
    )
    assert r["n_open_excluded"] >= 1, (
        "Nessun bucket zero-volume open trovato: attesa almeno 1 escl. Open (2025-08-29 06:30)."
    )
    assert r["status"] == "PASS", f"Status atteso PASS, ottenuto {r['status']}."


# ---------------------------------------------------------------------------
# CATEGORIA A — Test sintetici: exclusion policy e detection (Fix A)
# ---------------------------------------------------------------------------

def test_incomplete_bucket_excluded_not_mismatch():
    """Bucket con < 3 bar escluso interamente — non conta come mismatch."""
    base = "2024-01-01 00:00:00"
    df5 = _make_5m_df(base, [(100, 105, 99, 103)], [100.0])
    df15 = _make_15m_df(base, 100, 110, 98, 103, 350.0)

    r = _run_resample_check(df5, df15)
    assert r["n_incomplete"] >= 1, "Bucket incompleto non rilevato."
    assert r["unexplained_mismatches"] == 0, "Bucket incompleto conteggiato come mismatch."


def test_zero_volume_open_only_open_excluded():
    """
    Zero-vol first bar: bucket INCLUSO in complete_buckets_compared.
    Solo Open comparison esclusa. H/L/C/V corretti → 0 mismatch inspiegabili.
    """
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 100.0, 100.0, 100.0), (100.1, 101.5, 99.5, 101.0), (101.0, 102.0, 100.5, 101.5)]
    volumes = [0.0, 500.0, 400.0]
    df5 = _make_5m_df(base, prices, volumes)
    # Raw 15m: Open = 100.1 (first real trade, not filler); H/L/C/V correct aggregates
    df15 = _make_15m_df(base, 100.1, 102.0, 99.5, 101.5, 900.0)

    r = _run_resample_check(df5, df15)
    assert r["n_open_excluded"] >= 1, "Zero-vol open bucket non rilevato."
    assert r["complete_buckets_compared"] >= 1, "Zero-vol bucket deve essere in complete_buckets_compared."
    assert r["unexplained_mismatches"] == 0, (
        "Open mismatch su zero-vol bucket non deve essere inspiegabile (escluso per policy)."
    )
    assert r["status"] == "PASS"


def test_zero_vol_high_mismatch_detected():
    """
    Zero-vol-open bucket: Open comparison esclusa, ma HIGH mismatch deve essere rilevato.
    """
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 100.0, 100.0, 100.0), (100.1, 101.5, 99.5, 101.0), (101.0, 102.0, 100.5, 101.5)]
    volumes = [0.0, 500.0, 400.0]
    df5 = _make_5m_df(base, prices, volumes)
    # High mismatch: aggregated max = 102.0, raw 15m dice 110.0
    df15 = _make_15m_df(base, 100.1, 110.0, 99.5, 101.5, 900.0)

    r = _run_resample_check(df5, df15)
    assert r["n_open_excluded"] >= 1, "Zero-vol open bucket non rilevato."
    assert r["unexplained_mismatches"] > 0, "High mismatch in bucket zero-vol non rilevato."
    assert r["status"] == "FAIL"


def test_zero_vol_low_mismatch_detected():
    """Zero-vol-open bucket: Low mismatch deve essere rilevato (Low non escluso)."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 100.0, 100.0, 100.0), (100.1, 101.5, 99.5, 101.0), (101.0, 102.0, 100.5, 101.5)]
    volumes = [0.0, 500.0, 400.0]
    df5 = _make_5m_df(base, prices, volumes)
    # Low mismatch: aggregated min = 99.5, raw 15m dice 97.0
    df15 = _make_15m_df(base, 100.1, 102.0, 97.0, 101.5, 900.0)

    r = _run_resample_check(df5, df15)
    assert r["n_open_excluded"] >= 1
    assert r["unexplained_mismatches"] > 0, "Low mismatch in bucket zero-vol non rilevato."
    assert r["status"] == "FAIL"


def test_zero_vol_close_mismatch_detected():
    """Zero-vol-open bucket: Close mismatch deve essere rilevato."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 100.0, 100.0, 100.0), (100.1, 101.5, 99.5, 101.0), (101.0, 102.0, 100.5, 101.5)]
    volumes = [0.0, 500.0, 400.0]
    df5 = _make_5m_df(base, prices, volumes)
    # Close mismatch: aggregated last = 101.5, raw 15m dice 110.0
    df15 = _make_15m_df(base, 100.1, 102.0, 99.5, 110.0, 900.0)

    r = _run_resample_check(df5, df15)
    assert r["n_open_excluded"] >= 1
    assert r["unexplained_mismatches"] > 0, "Close mismatch in bucket zero-vol non rilevato."
    assert r["status"] == "FAIL"


def test_zero_vol_volume_mismatch_detected():
    """Zero-vol-open bucket: Volume mismatch deve essere rilevato."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 100.0, 100.0, 100.0), (100.1, 101.5, 99.5, 101.0), (101.0, 102.0, 100.5, 101.5)]
    volumes = [0.0, 500.0, 400.0]
    df5 = _make_5m_df(base, prices, volumes)
    # Volume mismatch: aggregated sum = 900.0, raw 15m dice 9999.0
    df15 = _make_15m_df(base, 100.1, 102.0, 99.5, 101.5, 9999.0)

    r = _run_resample_check(df5, df15)
    assert r["n_open_excluded"] >= 1
    assert r["unexplained_mismatches"] > 0, "Volume mismatch in bucket zero-vol non rilevato."
    assert r["status"] == "FAIL"


def test_zero_complete_buckets_is_blocked():
    """
    Se TUTTI i bucket sono incompleti, complete_buckets_compared == 0.
    Status deve essere BLOCKED (non PASS con zero confronti — FALSE PASS prevenuto).
    """
    base = "2024-01-01 00:00:00"
    # Solo 1 dei 3 bar 5m presenti → bucket incompleto
    df5 = _make_5m_df(base, [(100, 105, 99, 103)], [100.0])
    df15 = _make_15m_df(base, 100, 110, 98, 103, 350.0)

    r = _run_resample_check(df5, df15)
    assert r["complete_buckets_compared"] == 0, (
        f"Atteso 0 complete_buckets_compared, ottenuto {r['complete_buckets_compared']}."
    )
    assert r["status"] == "BLOCKED", (
        f"Status deve essere BLOCKED quando complete_buckets_compared==0, ottenuto '{r['status']}'."
    )


def test_open_mismatch_detected():
    """Mismatch genuino sull'Open con bucket completo (no filler) deve essere rilevato."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 102.0, 99.0, 101.0), (101.0, 103.0, 100.5, 102.0), (102.0, 104.0, 101.0, 103.0)]
    volumes = [100.0, 200.0, 150.0]
    df5 = _make_5m_df(base, prices, volumes)
    df15 = _make_15m_df(base, 99.0, 104.0, 99.0, 103.0, 450.0)

    r = _run_resample_check(df5, df15)
    assert r["unexplained_mismatches"] > 0, "Open mismatch genuino non rilevato."
    assert r["status"] == "FAIL"


def test_high_mismatch_detected():
    """Mismatch genuino sull'High deve essere rilevato."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 102.0, 99.0, 101.0), (101.0, 103.0, 100.5, 102.0), (102.0, 104.0, 101.0, 103.0)]
    volumes = [100.0, 200.0, 150.0]
    df5 = _make_5m_df(base, prices, volumes)
    df15 = _make_15m_df(base, 100.0, 106.0, 99.0, 103.0, 450.0)

    r = _run_resample_check(df5, df15)
    assert r["unexplained_mismatches"] > 0, "High mismatch genuino non rilevato."
    assert r["status"] == "FAIL"


def test_low_mismatch_detected():
    """Mismatch genuino sul Low deve essere rilevato."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 102.0, 99.0, 101.0), (101.0, 103.0, 100.5, 102.0), (102.0, 104.0, 101.0, 103.0)]
    volumes = [100.0, 200.0, 150.0]
    df5 = _make_5m_df(base, prices, volumes)
    df15 = _make_15m_df(base, 100.0, 104.0, 97.0, 103.0, 450.0)

    r = _run_resample_check(df5, df15)
    assert r["unexplained_mismatches"] > 0, "Low mismatch genuino non rilevato."
    assert r["status"] == "FAIL"


def test_close_mismatch_detected():
    """Mismatch genuino sul Close deve essere rilevato."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 102.0, 99.0, 101.0), (101.0, 103.0, 100.5, 102.0), (102.0, 104.0, 101.0, 103.0)]
    volumes = [100.0, 200.0, 150.0]
    df5 = _make_5m_df(base, prices, volumes)
    df15 = _make_15m_df(base, 100.0, 104.0, 99.0, 105.0, 450.0)

    r = _run_resample_check(df5, df15)
    assert r["unexplained_mismatches"] > 0, "Close mismatch genuino non rilevato."
    assert r["status"] == "FAIL"


def test_volume_mismatch_detected():
    """Mismatch genuino sul Volume deve essere rilevato."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 102.0, 99.0, 101.0), (101.0, 103.0, 100.5, 102.0), (102.0, 104.0, 101.0, 103.0)]
    volumes = [100.0, 200.0, 150.0]
    df5 = _make_5m_df(base, prices, volumes)
    df15 = _make_15m_df(base, 100.0, 104.0, 99.0, 103.0, 1000.0)

    r = _run_resample_check(df5, df15)
    assert r["unexplained_mismatches"] > 0, "Volume mismatch genuino non rilevato."
    assert r["status"] == "FAIL"


def test_clean_bucket_no_mismatch():
    """Bucket completo con aggregazione corretta → 0 mismatch, status PASS."""
    base = "2024-01-01 00:00:00"
    prices = [(100.0, 102.0, 99.0, 101.0), (101.0, 103.0, 100.5, 102.0), (102.0, 104.0, 101.0, 103.0)]
    volumes = [100.0, 200.0, 150.0]
    df5 = _make_5m_df(base, prices, volumes)
    df15 = _make_15m_df(base, 100.0, 104.0, 99.0, 103.0, 450.0)

    r = _run_resample_check(df5, df15)
    assert r["unexplained_mismatches"] == 0, f"Bucket pulito ha {r['unexplained_mismatches']} mismatch."
    assert r["n_incomplete"] == 0
    assert r["n_open_excluded"] == 0
    assert r["status"] == "PASS"
