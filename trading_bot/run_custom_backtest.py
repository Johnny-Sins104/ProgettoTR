import sys
import os
import pandas as pd
import argparse

# Assicuriamoci che l'encoding in output supporti UTF-8 su Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Aggiunge la directory corrente al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.analyzer import TechnicalAnalyzer
import backtest_lab

def main():
    parser = argparse.ArgumentParser(description="Simulatore di Backtest Personalizzato")
    parser.add_argument("--balance", type=float, default=100.0, help="Capitale iniziale in € (default: 100)")
    parser.add_argument("--candles", type=int, default=5000, help="Numero di candele recenti da testare (default: 5000)")
    
    args = parser.parse_args()
    
    from config import Config
    import polars as pl
    from core.data_collector import DatasetIntegrity, DatasetVersioning
    
    # Percorsi Parquet e CSV candidati
    if Config.TIMEFRAME == "15m":
        parquet_candidates = [
            os.path.join("data", "btc_15m_10k_cache.parquet"),
            os.path.join("data", "btc_15m_cache.parquet"),
        ]
        csv_candidates = [
            os.path.join("data", "btc_15m_10k_cache.csv"),
            os.path.join("data", "btc_15m_cache.csv"),
        ]
    else:
        parquet_candidates = [
            os.path.join("data", "btc_5m_10k_cache.parquet"),
            os.path.join("data", "btc_5m_cache.parquet"),
        ]
        csv_candidates = [
            os.path.join("data", "btc_5m_10k_cache.csv"),
            os.path.join("data", "btc_5m_cache.csv"),
        ]
        
    cache_path = None
    # 1. Cerca cache Parquet
    for pq_p in parquet_candidates:
        if os.path.exists(pq_p):
            cache_path = pq_p
            break
            
    # 2. Se non c'è Parquet, cerca CSV legacy e avvia migrazione
    if cache_path is None:
        for csv_p in csv_candidates:
            if os.path.exists(csv_p):
                target_pq = csv_p.replace(".csv", ".parquet")
                print(f"📦 [MIGRATION] Rilevato file CSV legacy '{csv_p}'. Migrazione automatica in corso...")
                try:
                    df_legacy = pl.read_csv(csv_p)
                    df_legacy = DatasetIntegrity.detect_and_remove_duplicates(df_legacy)
                    df_legacy = DatasetIntegrity.validate_schema(df_legacy, is_features=False)
                    df_legacy = DatasetIntegrity.handle_missing_data(df_legacy, max_null_ratio=Config.MAX_NULL_TOLERANCE)
                    DatasetIntegrity.validate_timestamps(df_legacy, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
                    
                    DatasetVersioning.write_parquet_with_metadata(df_legacy, target_pq, is_features=False)
                    os.remove(csv_p)
                    print(f"🗑️ [MIGRATION] File CSV legacy '{csv_p}' eliminato.")
                    cache_path = target_pq
                    break
                except Exception as e:
                    print(f"❌ [MIGRATION ERROR] Impossibile migrare {csv_p}: {e}")
                    
    # 3. Se ancora nessun file, scarica da exchange
    if cache_path is None:
        print(f"📡 Nessuna cache {Config.TIMEFRAME} trovata. Download da {Config.EXCHANGE_ID}...")
        import asyncio
        from core.client import ExchangeClient
        client = ExchangeClient(
            exchange_id=Config.EXCHANGE_ID,
            symbol=Config.SYMBOL,
            timeframe=Config.TIMEFRAME,
            limit=1000,
        )
        df_raw = asyncio.run(client.fetch_async())
        if df_raw is None or df_raw.empty:
            print("❌ Download fallito.")
            return
            
        save_path = os.path.join("data", f"btc_{Config.TIMEFRAME}_cache.parquet")
        os.makedirs("data", exist_ok=True)
        
        # Converte a Polars, valida, rimuove duplicati
        df_reset = df_raw.reset_index()
        df_pl = pl.DataFrame(df_reset)
        
        df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
        df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
        df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
        
        DatasetVersioning.write_parquet_with_metadata(df_pl, save_path, is_features=False)
        cache_path = save_path
        print(f"💾 Cache salvata: {cache_path} ({df_pl.height} candele)")
        
    print(f"📈 Caricamento dati da {cache_path}...")
    df_pl = pl.read_parquet(cache_path)
    
    # Validazione di sicurezza
    df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
    df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
    df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
    DatasetIntegrity.validate_timestamps(df_pl, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
    
    df = df_pl.to_pandas()
    if "datetime" in df.columns:
        df.set_index("datetime", inplace=True)
        
    print("🔬 Calcolo degli indicatori tecnici avanzati...")
    df = TechnicalAnalyzer().add_indicators(df)
    
    # Taglio del grafico per le ultime N candele
    total_available = len(df)
    if args.candles < total_available:
        print(f"✂️ Taglio del grafico: considero solo le ultime {args.candles} candele recenti su {total_available} totali.")
        df = df.iloc[-args.candles:]
    else:
        print(f"📊 Considero tutte le {total_available} candele disponibili.")
    
    # Configura il saldo iniziale
    backtest_lab.INITIAL_BALANCE = args.balance
    
    # Calcola i giorni equivalenti basati sulla cache effettiva scaricata
    timeframe_min = 15 if Config.TIMEFRAME == "15m" else 5
    giorni = (len(df) * timeframe_min) / 60 / 24
    
    print("\n💰 ==================================================")
    print(f"  AVVIO SIMULAZIONE PERSONALIZZATA")
    print(f"  - Capitale Iniziale : {args.balance:.2f} €")
    print(f"  - Candele analizzate: {len(df)} (circa {giorni:.1f} giorni)")
    print("==================================================")
    
    # Override per la simulazione diagnostica per consentire il transito di trade ed analizzare i regimi
    Config.META_PROB_THRESHOLD = 25.0
    Config.META_QUALITY_THRESHOLD = 25.0
    
    backtest_lab.run_backtest(df)

if __name__ == "__main__":
    main()
