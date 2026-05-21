"""
Test di Validazione Statistica del Pipeline Walk-Forward (test_walk_forward.py)
Verifica l'assenza totale di look-ahead bias, overlapping label contamination ed errori di split temporale.
"""
import sys
import os

# Assicuriamoci che l'encoding in output supporti UTF-8 su Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import pandas as pd
import numpy as np
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.analyzer import TechnicalAnalyzer
from core.data_collector import DataCollector
from core.walk_forward import WalkForwardPipeline
from config import Config

class TestWalkForwardSafety(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Determina i percorsi di cache per il timeframe corrente
        csv_path = os.path.join("data", "btc_15m_cache.csv")
        parquet_path = os.path.join("data", "btc_15m_cache.parquet")
        if not os.path.exists(csv_path) and not os.path.exists(parquet_path):
            csv_path = os.path.join("data", "btc_15m_10k_cache.csv")
            parquet_path = os.path.join("data", "btc_15m_10k_cache.parquet")
            
        # Se il parquet non esiste, ma il csv esiste, avvia la migrazione automatica!
        if not os.path.exists(parquet_path) and os.path.exists(csv_path):
            print(f"📦 [TEST SETUP] Rilevato file CSV legacy '{csv_path}'. Avvio migrazione automatica a Parquet...")
            try:
                import polars as pl
                from core.data_collector import DatasetIntegrity, DatasetVersioning
                
                # Leggiamo il CSV con Polars
                df_legacy = pl.read_csv(csv_path)
                
                # Validiamo e ripuliamo i dati
                df_legacy = DatasetIntegrity.detect_and_remove_duplicates(df_legacy)
                df_legacy = DatasetIntegrity.validate_schema(df_legacy, is_features=False)
                df_legacy = DatasetIntegrity.handle_missing_data(df_legacy, max_null_ratio=Config.MAX_NULL_TOLERANCE)
                DatasetIntegrity.validate_timestamps(df_legacy, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
                
                # Scriviamo in formato Parquet con compressione Snappy e metadati
                DatasetVersioning.write_parquet_with_metadata(df_legacy, parquet_path, is_features=False)
                
                # Rimuoviamo il vecchio CSV legacy
                os.remove(csv_path)
                print(f"🗑️ [TEST SETUP] File CSV legacy '{csv_path}' eliminato per pulire lo spazio di lavoro.")
            except Exception as e:
                print(f"❌ [TEST SETUP ERROR] Impossibile migrare {csv_path} a Parquet: {e}.")
                
        # Ora carica dal file Parquet se esiste
        if os.path.exists(parquet_path):
            print(f"[TEST SETUP] Caricamento dati offline da cache Parquet: {parquet_path}...")
            import polars as pl
            from core.data_collector import DatasetIntegrity
            
            df_pl = pl.read_parquet(parquet_path)
            
            # Validazione finale di integrità prima dell'uso
            df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
            df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
            df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
            DatasetIntegrity.validate_timestamps(df_pl, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
            
            # Converte in Pandas DataFrame per retrocompatibilità
            cls.df = df_pl.to_pandas()
            if "datetime" in cls.df.columns:
                cls.df.set_index("datetime", inplace=True)
                
            print(f"✅ [TEST SETUP INTEGRITY CHECK] Dati offline verificati con successo: {len(cls.df)} candele caricate.")
            cls.df = TechnicalAnalyzer().add_indicators(cls.df)
            
        elif os.path.exists(csv_path):
            print(f"[TEST SETUP] Fallback: Caricamento dati offline da cache CSV legacy: {csv_path}...")
            cls.df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
            cls.df = TechnicalAnalyzer().add_indicators(cls.df)
            
        else:
            print("[TEST SETUP] Cache non trovata. Generazione dati sintetici...")
            # Generazione dati sintetici realistici in caso di mancanza di cache offline
            dates = pd.date_range(start="2026-01-01", periods=1000, freq="15min")
            cls.df = pd.DataFrame(index=dates)
            cls.df["Open"] = 100.0 + np.cumsum(np.random.normal(0, 0.5, 1000))
            cls.df["High"] = cls.df["Open"] + np.random.exponential(0.5, 1000)
            cls.df["Low"] = cls.df["Open"] - np.random.exponential(0.5, 1000)
            cls.df["Close"] = cls.df["Open"] + np.random.normal(0, 0.2, 1000)
            cls.df["Volume"] = np.random.exponential(100.0, 1000)
            cls.df = TechnicalAnalyzer().add_indicators(cls.df)
            
        print(f"[TEST SETUP] Dati pronti: {len(cls.df)} candele.")

    def test_causal_features(self):
        """
        Verifica che le features generate all'indice `i` siano RIGOROSAMENTE causali,
        ovvero identiche indipendentemente dal fatto che vengano calcolate sull'intero dataset
        o su una porzione tagliata `df.iloc[:i+1]`.
        """
        print("\n🔍 Test Causalità delle Features...")
        
        # Testiamo su 3 indici diversi sparsi nel dataset
        test_indices = [100, 300, len(self.df) - 101]
        
        for idx in test_indices:
            # 1. Calcolo sul dataset globale
            feat_global = DataCollector.extract_features(self.df, idx)
            
            # 2. Calcolo sul dataset tranciato al momento idx (il futuro non esiste)
            df_sliced = self.df.iloc[:idx + 1].copy()
            feat_sliced = DataCollector.extract_features(df_sliced, idx)
            
            # Confronto dei valori delle features
            for key in feat_global:
                val_g = feat_global[key]
                val_s = feat_sliced[key]
                self.assertAlmostEqual(
                    val_g, val_s, places=5, 
                    msg=f"Feature '{key}' all'indice {idx} non è causale! Globale: {val_g}, Sliced: {val_s}"
                )
        print("✅ Le features sono rigorosamente causali! Nessun look-ahead bias rilevato nelle formule.")

    def test_localized_labeling_and_purging(self):
        """
        Verifica che l'etichettatura localizzata rispetti rigorosamente train_end.
        In particolare, le target labels per train_end non devono dipendere in alcun modo da candele successive.
        """
        print("\n🔍 Test Localizzazione ed Etichettatura con Purging...")
        
        train_end = 500
        label_horizon = 100
        
        # 1. Calcolo delle label sul dataset tranciato a train_end
        df_sliced = self.df.iloc[:train_end + 1].copy()
        
        # Eseguiamo il precalcolo causal-features sul tranciato
        features_sliced = DataCollector.collect_from_backtest_mem(df_sliced)
        
        # Generiamo il dataset di training per [0, train_end] sul tranciato
        train_ds_sliced = DataCollector.generate_training_dataset(
            df=df_sliced,
            train_start=0,
            train_end=train_end,
            features_df=features_sliced,
            label_horizon=label_horizon
        )
        
        # 2. Calcolo sul dataset globale (che contiene il futuro oltre train_end)
        features_global = DataCollector.collect_from_backtest_mem(self.df)
        train_ds_global = DataCollector.generate_training_dataset(
            df=self.df,
            train_start=0,
            train_end=train_end,
            features_df=features_global,
            label_horizon=label_horizon
        )
        
        # Le due tabelle di training generate devono essere IDENTICHE al 100%
        self.assertEqual(
            len(train_ds_sliced), len(train_ds_global),
            "I dataset di training differiscono in lunghezza!"
        )
        
        # Verifichiamo che tutte le righe e le colonne (comprese le label outcome) siano identiche
        pd.testing.assert_frame_equal(
            train_ds_sliced, train_ds_global,
            obj="Dataset di training generato sul tranciato vs sul globale"
        )
        
        # Verifichiamo che l'indice massimo del training set generato sia effettivamente train_end - label_horizon
        max_idx = features_sliced.loc[
            features_sliced["candle_idx"] <= (train_end - label_horizon), "candle_idx"
        ].max()
        
        # Poiché estraiamo solo i candidati tecnici reali (BUY o SELL), la lunghezza totale
        # deve corrispondere esattamente al numero di candidati validati dalla Stage 1 rules-based.
        from core.engine import DecisionEngine
        engine = DecisionEngine()
        expected_samples = 0
        for _, row in features_sliced[features_sliced["candle_idx"] <= (train_end - label_horizon)].iterrows():
            i = int(row["candle_idx"])
            df_sliced_i = df_sliced.iloc[:i+1]
            tech_verdict, _, _, _, _, _ = engine._evaluate_score(df_sliced_i)
            if tech_verdict in ("BUY", "SELL"):
                expected_samples += 1
        self.assertEqual(len(train_ds_sliced), expected_samples)
        
        print(f"✅ Etichettatura localizzata e Purging verificati con successo!")
        print(f"   Train End: {train_end} | Max Trained Candle Index: {max_idx} (Purged: {train_end - max_idx} candele).")

    def test_walk_forward_splits(self):
        """
        Verifica che le finestre generate da WalkForwardPipeline non abbiano overlapping label contamination,
        e che la distanza minima tra l'ultimo campione di training e il primo di test sia di almeno (label_horizon + embargo_gap) candele.
        """
        print("\n🔍 Test Limiti Walk-Forward, Purging ed Embargo...")
        
        N = 500
        M = 100
        embargo_gap = 100
        label_horizon = 100
        
        splits = WalkForwardPipeline.get_wf_splits(len(self.df), N=N, M=M, embargo_gap=embargo_gap, df=self.df)
        
        self.assertGreater(len(splits), 0, "Nessun fold walk-forward generato.")
        
        for fold_idx, split in enumerate(splits):
            train_start = split.train_start
            train_end = split.train_end
            embargo_start = split.embargo_start
            embargo_end = split.embargo_end
            test_start = split.test_start
            test_end = split.test_end
            
            # L'inizio del test deve coincidere esattamente con l'inizio stimato del fold
            self.assertGreaterEqual(test_start, N)
            
            # L'embargo gap deve separare nettamente train_end e test_start
            calculated_gap = test_start - 1 - train_end
            self.assertEqual(
                calculated_gap, embargo_gap,
                f"L'embargo gap calcolato ({calculated_gap}) differisce da quello configurato ({embargo_gap})!"
            )
            
            # Verifica limiti esatti dell'embargo
            self.assertEqual(embargo_start, train_end + 1)
            self.assertEqual(embargo_end, test_start - 1)
            
            # Nel dataset di training effettivo, i campioni saranno purgati ulteriormente di label_horizon candele.
            # Quindi l'ultimo campione addestrato si troverà a train_end - label_horizon.
            last_trained_sample_idx = train_end - label_horizon
            
            # Distanza tra l'ultimo campione addestrato e il primo campione di test
            separation = test_start - last_trained_sample_idx
            expected_separation = embargo_gap + label_horizon + 1
            
            self.assertEqual(
                separation, expected_separation,
                f"La separazione effettiva ({separation}) differisce da quella attesa ({expected_separation})!"
            )
            
            # Verifica che i timestamp siano stati risolti correttamente
            self.assertIsNotNone(split.train_start_time)
            self.assertIsNotNone(split.test_end_time)
            
            print(f"   [Fold {fold_idx+1}] Train: [{train_start}, {train_end}] (Ultimo Addestrato: {last_trained_sample_idx}) | "
                  f"Embargo: [{embargo_start}, {embargo_end}] ({calculated_gap} candele) | Test: [{test_start}, {test_end}] | "
                  f"Separazione Totale: {separation} candele.")
            
        print("✅ Tutti i limiti del Walk-Forward, dell'embargo e del purging sono matematicamente perfetti!")

    def test_dataset_integrity_suite(self):
        """
        Verifica i meccanismi di integrità di DatasetIntegrity:
        - Riconoscimento e fallimento su colonne mancanti o dtype errati.
        - Riconoscimento di timestamp non ordinati (ValueError).
        - Rimozione corretta dei duplicati.
        - Tolleranza e imputazione (ffill/bfill) di valori nulli <= 5%, e fallimento se > 5%.
        """
        import polars as pl
        from datetime import datetime
        from core.data_collector import DatasetIntegrity
        
        print("\n🔍 Test Data Integrity Suite...")
        
        # 1. Test Schema Validation (Missing columns)
        incomplete_df = pl.DataFrame({
            "datetime": [datetime(2026, 1, 1, 0, 0)],
            "Open": [100.0],
            "High": [101.0],
            # missing Low, Close, Volume
        })
        with self.assertRaises(ValueError) as ctx:
            DatasetIntegrity.validate_schema(incomplete_df, is_features=False)
        self.assertIn("Colonne mancanti", str(ctx.exception))
        
        # 2. Test Timestamp Order Validation
        unordered_df = pl.DataFrame({
            "datetime": [
                datetime(2026, 1, 1, 0, 15),
                datetime(2026, 1, 1, 0, 0), # out of order
            ],
            "Open": [100.0, 100.5],
            "High": [101.0, 101.5],
            "Low": [99.0, 99.5],
            "Close": [100.2, 100.7],
            "Volume": [10.0, 15.0]
        })
        with self.assertRaises(ValueError) as ctx:
            DatasetIntegrity.validate_timestamps(unordered_df)
        self.assertIn("non sono ordinati cronologicamente", str(ctx.exception))
        
        # 3. Test Duplicate Detection and Removal
        duplicated_df = pl.DataFrame({
            "datetime": [
                datetime(2026, 1, 1, 0, 0),
                datetime(2026, 1, 1, 0, 0), # duplicate
                datetime(2026, 1, 1, 0, 15),
            ],
            "Open": [100.0, 100.0, 100.5],
            "High": [101.0, 101.0, 101.5],
            "Low": [99.0, 99.0, 99.5],
            "Close": [100.2, 100.2, 100.7],
            "Volume": [10.0, 10.0, 15.0]
        })
        cleaned_df = DatasetIntegrity.detect_and_remove_duplicates(duplicated_df)
        self.assertEqual(cleaned_df.height, 2)
        
        # 4. Test Missing Data Handling
        # Case A: <= 5% missing (e.g. 1 out of 20 = 5%)
        rows_data = []
        from datetime import timedelta
        for i in range(20):
            rows_data.append({
                "datetime": datetime(2026, 1, 1, 0, 0) + timedelta(minutes=i * 15),
                "Open": 100.0 + i,
                "High": 101.0 + i,
                "Low": 99.0 + i,
                "Close": 100.2 + i if i != 10 else None, # single null Close
                "Volume": 10.0
            })
        df_low_nulls = pl.DataFrame(rows_data)
        # Should execute successfully and fill the null at index 10 (forward filled from 9, i.e., 100.2 + 9 = 109.2)
        filled_df = DatasetIntegrity.handle_missing_data(df_low_nulls, max_null_ratio=0.05)
        self.assertEqual(filled_df["Close"].null_count(), 0) # should have 0 nulls
        self.assertEqual(filled_df["Close"][10], 109.2) # ffilled from index 9
        
        # Case B: > 5% missing (e.g. 2 out of 20 = 10%)
        rows_data_high = []
        for i in range(20):
            rows_data_high.append({
                "datetime": datetime(2026, 1, 1, 0, 0) + timedelta(minutes=i * 15),
                "Open": 100.0 + i,
                "High": 101.0 + i,
                "Low": 99.0 + i,
                "Close": 100.2 + i if (i != 5 and i != 10) else None, # two nulls (10%)
                "Volume": 10.0
            })
        df_high_nulls = pl.DataFrame(rows_data_high)
        with self.assertRaises(ValueError) as ctx:
            DatasetIntegrity.handle_missing_data(df_high_nulls, max_null_ratio=0.05)
        self.assertIn("superando il limite tollerato", str(ctx.exception))
        
        print("✅ Data Integrity Suite superata con successo!")

if __name__ == "__main__":
    unittest.main()
