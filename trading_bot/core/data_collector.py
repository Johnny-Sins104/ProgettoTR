"""
Modulo Memoria (core/data_collector.py) - Versione Ottimizzata (Clean-Data)
Raccoglie le features di mercato depurate da bias temporali ed esegue l'etichettatura localizzata.
"""
import os
import pandas as pd
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import json
from datetime import datetime
from config import Config

# PyArrow Schemas for Candles and Features
CANDLE_SCHEMA = pa.schema([
    ("datetime", pa.timestamp('ns', tz='UTC')),
    ("Open", pa.float64()),
    ("High", pa.float64()),
    ("Low", pa.float64()),
    ("Close", pa.float64()),
    ("Volume", pa.float64())
])

FEATURE_SCHEMA = pa.schema([
    ("rsi", pa.float64()),
    ("adx", pa.float64()),
    ("atr_pct", pa.float64()),
    ("ema_slope", pa.float64()),
    ("close_vs_ema", pa.float64()),
    ("dist_to_psy", pa.float64()),
    ("volume_ratio", pa.float64()),
    ("bb_position", pa.float64()),
    ("engulfing", pa.float64()),
    ("regime", pa.int64()),
    ("in_fvg", pa.int64()),
    ("near_sr", pa.int64()),
    ("volume_bias_enc", pa.int64()),
    ("setup_quality", pa.float64()),
    ("outcome", pa.int64())
])

class DatasetIntegrity:
    @staticmethod
    def validate_schema(df: pl.DataFrame, is_features: bool) -> pl.DataFrame:
        """
        Controlla la presenza e il tipo delle colonne rispetto allo schema predefinito.
        Esegue il cast automatico delle colonne per garantire coerenza totale.
        """
        schema = FEATURE_SCHEMA if is_features else CANDLE_SCHEMA
        missing_cols = []
        
        # Gestione speciale del datetime per i candles
        if not is_features:
            datetime_col = None
            for col in df.columns:
                if col.lower() in ("datetime", "timestamp", "time"):
                    datetime_col = col
                    break
            
            if datetime_col is None:
                missing_cols.append("datetime")
            else:
                if datetime_col != "datetime":
                    df = df.rename({datetime_col: "datetime"})
                
                # Conversione in datetime UTC
                try:
                    if df["datetime"].dtype == pl.String:
                        df = df.with_columns(pl.col("datetime").str.to_datetime(time_zone="UTC"))
                    elif df["datetime"].dtype in (pl.Int64, pl.Float64):
                        val = df["datetime"][0]
                        if val > 1e11: # millisecondi
                            df = df.with_columns(pl.col("datetime").cast(pl.Int64).cast(pl.Datetime("ms")).dt.replace_time_zone("UTC"))
                        else: # secondi
                            df = df.with_columns(pl.col("datetime").cast(pl.Int64).cast(pl.Datetime("s")).dt.replace_time_zone("UTC"))
                    else:
                        df = df.with_columns(pl.col("datetime").cast(pl.Datetime).dt.replace_time_zone("UTC"))
                except Exception as e:
                    raise ValueError(f"Errore nella conversione della colonna datetime: {e}")

        # Verifica le altre colonne del rispettivo schema
        for field in schema:
            col_name = field.name
            if col_name not in df.columns:
                missing_cols.append(col_name)
                continue
            
            # Cast type
            pa_type = field.type
            if pa.types.is_floating(pa_type):
                df = df.with_columns(pl.col(col_name).cast(pl.Float64))
            elif pa.types.is_integer(pa_type):
                df = df.with_columns(pl.col(col_name).cast(pl.Int64))
            elif pa.types.is_timestamp(pa_type):
                df = df.with_columns(pl.col(col_name).cast(pl.Datetime).dt.replace_time_zone("UTC"))

        if missing_cols:
            raise ValueError(f"Colonne mancanti dallo schema: {missing_cols}")
            
        if is_features:
            df = df.select(FEATURE_COLUMNS)
            
        return df

    @staticmethod
    def validate_timestamps(df: pl.DataFrame, expected_delta_min: int = 15) -> None:
        """
        Verifica che i timestamp siano strettamente crescenti e rileva eventuali gap temporali.
        """
        if "datetime" not in df.columns:
            return
            
        is_sorted = df["datetime"].is_sorted()
        if not is_sorted:
            raise ValueError("I timestamp non sono ordinati cronologicamente.")
            
        diffs = df["datetime"].diff().drop_nulls()
        expected_ms = expected_delta_min * 60 * 1000
        
        try:
            diffs_ms = diffs.dt.total_milliseconds()
            gaps = diffs_ms.filter(diffs_ms != expected_ms)
            if gaps.len() > 0:
                print(f"⚠️ Rilevati {gaps.len()} gap/anomalie temporali nei dati rispetto al timeframe di {expected_delta_min}m.")
        except Exception:
            pass

    @staticmethod
    def handle_missing_data(df: pl.DataFrame, max_null_ratio: float = 0.05) -> pl.DataFrame:
        """
        Verifica il tasso di valori nulli per colonna. Rifiuta se > max_null_ratio,
        altrimenti esegue forward-fill e poi backward-fill.
        """
        total_rows = df.height
        if total_rows == 0:
            return df
            
        for col in df.columns:
            null_count = df[col].null_count()
            null_ratio = null_count / total_rows
            if null_ratio > max_null_ratio:
                raise ValueError(
                    f"La colonna '{col}' contiene il {null_ratio:.2%} di valori mancanti, "
                    f"superando il limite tollerato del {max_null_ratio:.2%}."
                )
        
        df = df.fill_null(strategy="forward").fill_null(strategy="backward")
        return df

    @staticmethod
    def detect_and_remove_duplicates(df: pl.DataFrame) -> pl.DataFrame:
        """
        Rileva e rimuove i duplicati basati sulla colonna chiave (datetime o prima colonna).
        """
        if df.height == 0:
            return df
            
        unique_col = "datetime" if "datetime" in df.columns else df.columns[0]
        
        dup_count = df.height - df.unique(subset=[unique_col]).height
        if dup_count > 0:
            print(f"⚠️ Rilevati {dup_count} record duplicati basati su '{unique_col}'. Rimozione in corso...")
            df = df.unique(subset=[unique_col], keep="first")
            df = df.sort(unique_col)
            
        return df

class DatasetVersioning:
    @staticmethod
    def write_parquet_with_metadata(df: pl.DataFrame, file_path: str, is_features: bool) -> None:
        """
        Scrive il DataFrame in formato Parquet con compressione Snappy e inserisce metadati personalizzati.
        """
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        table = df.to_arrow()
        
        custom_metadata = {
            "version": Config.DATASET_VERSION,
            "generated_at": datetime.utcnow().isoformat(),
            "row_count": str(df.height),
            "feature_columns": json.dumps(df.columns),
            "dataset_type": "features" if is_features else "candles"
        }
        
        existing_metadata = table.schema.metadata or {}
        encoded_metadata = {
            **existing_metadata,
            **{k.encode('utf-8'): v.encode('utf-8') for k, v in custom_metadata.items()}
        }
        
        table = table.replace_schema_metadata(encoded_metadata)
        pq.write_table(table, file_path, compression="snappy")
        print(f"💾 File Parquet salvato con successo in {file_path} con metadati di versione '{Config.DATASET_VERSION}' e compressione Snappy.")

    @staticmethod
    def read_metadata(file_path: str) -> dict:
        """
        Legge in modo estremamente efficiente i metadati personalizzati dal Parquet.
        """
        if not os.path.exists(file_path):
            return {}
            
        try:
            parquet_file = pq.ParquetFile(file_path)
            metadata = parquet_file.schema_arrow.metadata
            if not metadata:
                return {}
                
            return {k.decode('utf-8'): v.decode('utf-8') for k, v in metadata.items()}
        except Exception as e:
            print(f"⚠️ Impossibile leggere i metadati Parquet da {file_path}: {e}")
            return {}

# FEATURE_COLUMNS aggiornate: rimosse 'hour' e 'day_of_week' per abbattere l'overfitting
FEATURE_COLUMNS = [
    "rsi",
    "adx",
    "atr_pct",
    "ema_slope",
    "close_vs_ema",
    "dist_to_psy",
    "volume_ratio",
    "bb_position",
    "engulfing",
    "regime",
    "in_fvg",
    "near_sr",
    "volume_bias_enc",
    "setup_quality",
    "outcome"  # Target label (1 = Win, 0 = Loss)
]

class DataCollector:
    @staticmethod
    def calculate_quality_score(row: pd.Series, volume_ratio: float, side: str) -> float:
        """
        Calcola un punteggio quantitativo di qualita del setup (0-100) basato su tre pilastri:
        1. Confluenza Tecnica (max 40)
        2. Forza dei Volumi (max 30)
        3. Posizionamento Macro (max 30)
        """
        from core.setup_filter import SetupFilter
        return SetupFilter.calculate_quality_score(row, volume_ratio, side)

    @staticmethod
    def extract_features(df: pd.DataFrame, idx: int) -> dict:
        """
        Estrae le features tecniche depurate da componenti temporali.
        Garantisce la causalità: calcola le features all'indice `idx` usando solo dati storici fino a `idx`.
        """
        row = df.iloc[idx]
        
        # Pendenza dell'EMA 200 (ultimi 5 periodi)
        ema_slope = 0.0
        if idx >= 5:
            prev_ema = df.iloc[idx - 5]["ema_200"]
            curr_ema = row["ema_200"]
            if prev_ema > 0:
                ema_slope = (curr_ema - prev_ema) / prev_ema * 100
                
        # Close rispetto a EMA 200 in %
        close_vs_ema = 0.0
        if row["ema_200"] > 0:
            close_vs_ema = (row["Close"] - row["ema_200"]) / row["ema_200"] * 100
            
        # ATR % del prezzo
        atr_pct = 0.0
        if row["Close"] > 0:
            atr_pct = (row["atr"] / row["Close"]) * 100
            
        # Volume ratio rispetto alla media rolling a 20 periodi
        volume_ratio = 1.0
        if idx >= 20:
            vol_mean = df.iloc[idx-20:idx+1]["Volume"].mean()
            if vol_mean > 0:
                volume_ratio = row["Volume"] / vol_mean
                
        # FVG logic: 1 se in bull_fvg, -1 se in bear_fvg
        in_fvg = 0
        if row.get("in_bull_fvg", 0) > 0:
            in_fvg = 1
        elif row.get("in_bear_fvg", 0) > 0:
            in_fvg = -1
            
        # Support/Resistance proximity
        near_sr = 0
        if row.get("near_support", False):
            near_sr = 1
        elif row.get("near_resistance", False):
            near_sr = -1
            
        # Volume bias encoding: 1=BULLISH, -1=BEARISH, 0=NEUTRAL
        v_bias = row.get("volume_bias", "NEUTRAL")
        v_bias_enc = 0
        if v_bias == "BULLISH":
            v_bias_enc = 1
        elif v_bias == "BEARISH":
            v_bias_enc = -1
            
        # Market Regime: 1=TRENDING, 0=RANGING
        regime_enc = 1 if row.get("market_regime", "RANGING") == "TRENDING" else 0
        
        return {
            "rsi": float(row.get("rsi_14", 50.0)),
            "adx": float(row.get("adx", 0.0)),
            "atr_pct": float(atr_pct),
            "ema_slope": float(ema_slope),
            "close_vs_ema": float(close_vs_ema),
            "dist_to_psy": float(row.get("dist_to_psy_level", 0.0)),
            "volume_ratio": float(volume_ratio),
            "bb_position": float(row.get("range_pos_400", 0.5)),
            "engulfing": float(row.get("cdl_engulfing", 0) / 100.0),
            "regime": int(regime_enc),
            "in_fvg": int(in_fvg),
            "near_sr": int(near_sr),
            "volume_bias_enc": int(v_bias_enc)
        }

    @staticmethod
    def label_outcome(df: pd.DataFrame, idx: int, side: str, atr_mult: float, rr: float, max_idx: int = None) -> int:
        """
        Simula in avanti l'esito del trade per scopi di addestramento.
        Se viene fornito max_idx, la simulazione del trade è rigorosamente limitata a max_idx candele
        per impedire look-ahead bias fuori dall'orizzonte di training.
        """
        if idx >= len(df) - 1:
            return 0
            
        entry_row = df.iloc[idx]
        entry_price = entry_row["Close"]
        atr = entry_row["atr"]
        if atr <= 0:
            atr = entry_price * 0.01
            
        if side == "BUY":
            sl = entry_price - (atr * atr_mult)
            tp = entry_price + (atr * atr_mult * rr)
        else:
            sl = entry_price + (atr * atr_mult)
            tp = entry_price - (atr * atr_mult * rr)
            
        max_limit = len(df) - idx - 1
        if max_idx is not None:
            max_limit = min(max_limit, max_idx - idx)
            
        max_forward = min(100, max_limit)
        for offset in range(1, max_forward + 1):
            curr_row = df.iloc[idx + offset]
            high = curr_row["High"]
            low = curr_row["Low"]
            
            if side == "BUY":
                hit_sl = low <= sl
                hit_tp = high >= tp
                if hit_sl and hit_tp: return 0
                if hit_tp: return 1
                if hit_sl: return 0
            else:
                hit_sl = high >= sl
                hit_tp = low <= tp
                if hit_sl and hit_tp: return 0
                if hit_tp: return 1
                if hit_sl: return 0
                    
        return 0

    @classmethod
    def collect_from_backtest_mem(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Genera le features storiche per tutte le candele in modo puramente causale.
        Non calcola le label 'outcome' nè raddoppia le righe con la Symmetry Transformation,
        perché queste operazioni devono essere effettuate SOLO localmente in ciascuna finestra
        di training per evitare leakage e violazioni causali.
        """
        records = []
        print("📊 Estrazione features storiche causali in memoria in corso...")
        for i in range(20, len(df)):
            feat = cls.extract_features(df, i)
            feat["candle_idx"] = i
            records.append(feat)
            
        if not records:
            return pd.DataFrame()
            
        cols = [c for c in FEATURE_COLUMNS if c not in ("setup_quality", "outcome")] + ["candle_idx"]
        return pd.DataFrame(records)[cols]

    @classmethod
    def generate_training_dataset(cls, df: pd.DataFrame, train_start: int, train_end: int, features_df: pd.DataFrame, label_horizon: int = 100) -> pd.DataFrame:
        """
        Genera il dataset di addestramento specifico per una finestra [train_start, train_end]
        applicando il purging delle ultime 'label_horizon' candele ed eseguendo l'etichettatura
        con limite temporale rigoroso in 'train_end' (nessun peeking oltre la finestra).
        Filtra estraendo SOLO i candidati validati dalla Stage 1 rules-based.
        Applica inoltre la Symmetry Transformation sui campioni.
        """
        records = []
        
        # Purging: non possiamo usare i campioni alla fine del training window che non hanno
        # abbastanza candele future per determinare l'esito del trade all'interno di train_end.
        max_train_idx = train_end - label_horizon
        
        # Filtriamo le features precalcolate presenti nella finestra di training
        subset = features_df[(features_df["candle_idx"] >= train_start) & (features_df["candle_idx"] <= max_train_idx)]
        
        from core.engine import DecisionEngine
        engine = DecisionEngine()
        
        for _, row in subset.iterrows():
            i = int(row["candle_idx"])
            
            # Utilizziamo solo dati storici fino all'indice i per valutare il setup della Stage 1
            df_sliced = df.iloc[:i+1]
            tech_verdict, tech_score, conf, entry_type, conf_v, conf_c = engine._evaluate_score(df_sliced)
            
            if tech_verdict in ("BUY", "SELL"):
                # Recuperiamo le features causali (esclusi target, setup_quality ed index)
                feat_sample = {col: row[col] for col in FEATURE_COLUMNS if col not in ("setup_quality", "outcome")}
                
                # Calcolo setup_quality
                volume_ratio = float(row["volume_ratio"])
                setup_quality = cls.calculate_quality_score(df.iloc[i], volume_ratio, tech_verdict)
                feat_sample["setup_quality"] = setup_quality
                
                # Generiamo la label localizzata rigorosamente entro il limite train_end
                regime_str = df.iloc[i].get("market_regime", "RANGING")
                rr = Config.TRENDING_RR if regime_str == "TRENDING" else Config.RANGING_RR
                outcome = cls.label_outcome(df, i, tech_verdict, Config.ATR_MULT, rr, max_idx=train_end)
                feat_sample["outcome"] = outcome
                
                # Se è un campione SELL, applichiamo la Symmetry Transformation
                if tech_verdict == "SELL":
                    feat_sample["engulfing"] = -feat_sample["engulfing"]
                    feat_sample["close_vs_ema"] = -feat_sample["close_vs_ema"]
                    feat_sample["ema_slope"] = -feat_sample["ema_slope"]
                    feat_sample["near_sr"] = -feat_sample["near_sr"]
                    feat_sample["volume_bias_enc"] = -feat_sample["volume_bias_enc"]
                    
                records.append(feat_sample)
                
        if not records:
            return pd.DataFrame()
            
        return pd.DataFrame(records)[FEATURE_COLUMNS]

    @classmethod
    def collect_from_backtest(cls, df: pd.DataFrame, parquet_path: str = None) -> int:
        """
        Raccoglie le features per retrocompatibilità e le scrive in formato Parquet con validazione e metadati.
        """
        if parquet_path is None:
            parquet_path = Config.AI_FEATURES_PATH
            
        os.makedirs(os.path.dirname(parquet_path), exist_ok=True)
        new_df = cls.collect_from_backtest_mem(df)
        
        if new_df.empty:
            print("⚠️ Nessun record raccolto dal dataset.")
            return 0
            
        # Rimuove candle_idx e converte in Polars
        save_df_pd = new_df.drop(columns=["candle_idx"])
        save_df_pd["outcome"] = 0  # Valore di default poichè non calcolato
        
        # Converte in Polars DataFrame per validazione e salvataggio
        save_df = pl.DataFrame(save_df_pd)
        
        try:
            save_df = DatasetIntegrity.validate_schema(save_df, is_features=True)
            save_df = DatasetIntegrity.handle_missing_data(save_df, max_null_ratio=Config.MAX_NULL_TOLERANCE)
            save_df = DatasetIntegrity.detect_and_remove_duplicates(save_df)
            
            DatasetVersioning.write_parquet_with_metadata(save_df, parquet_path, is_features=True)
            return save_df.height
        except Exception as e:
            print(f"❌ [BACKTEST COLLECT ERROR] Errore di salvataggio/validazione Parquet: {e}")
            raise e

    @classmethod
    def append_live(cls, features_dict: dict, outcome: int, parquet_path: str = None):
        """
        Aggiunge una riga di features (live) al file Parquet dopo aver validato lo schema.
        """
        if parquet_path is None:
            parquet_path = Config.AI_FEATURES_PATH
            
        record = features_dict.copy()
        record["outcome"] = int(outcome)
        
        # Filtro colonne ordinato secondo FEATURE_COLUMNS
        ordered_record = {col: record.get(col, 0.0) for col in FEATURE_COLUMNS}
        
        # Converte in Polars DataFrame per usare le validazioni di DatasetIntegrity
        row_df = pl.DataFrame([ordered_record])
        
        try:
            # Valida schema
            row_df = DatasetIntegrity.validate_schema(row_df, is_features=True)
            # Gestione dati mancanti
            row_df = DatasetIntegrity.handle_missing_data(row_df, max_null_ratio=Config.MAX_NULL_TOLERANCE)
        except Exception as e:
            print(f"❌ [LIVE APPEND ERROR] Errore di validazione durante append_live: {e}")
            raise e
            
        # Se il file parquet esiste già, carichiamo la tabella esistente, concateniamo e riscriviamo con metadati aggiornati.
        if os.path.exists(parquet_path):
            try:
                # Leggiamo la tabella esistente
                existing_table = pq.read_table(parquet_path)
                existing_df = pl.from_arrow(existing_table)
                
                # Concateniamo i DataFrame
                updated_df = pl.concat([existing_df, row_df])
                
                # Rimuoviamo eventuali duplicati
                updated_df = DatasetIntegrity.detect_and_remove_duplicates(updated_df)
            except Exception as e:
                print(f"⚠️ Errore durante la lettura o il concatenamento del file Parquet esistente, riscrittura da zero: {e}")
                updated_df = row_df
        else:
            updated_df = row_df
            
        # Scrive il file aggiornato con i metadati di versione
        try:
            DatasetVersioning.write_parquet_with_metadata(updated_df, parquet_path, is_features=True)
        except Exception as e:
            print(f"❌ [LIVE APPEND ERROR] Impossibile scrivere file Parquet: {e}")
            raise e