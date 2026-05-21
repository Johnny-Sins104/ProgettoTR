import asyncio
import ccxt.async_support as ccxt_async
import pandas as pd
import time
import os
import sys

# Assicuriamoci che l'encoding in output supporti UTF-8 su Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

async def download_10k():
    exchange = ccxt_async.binance()
    symbol = "BTC/USDT"
    timeframe = "15m"
    target_candles = 10000
    
    print(f"🤖 Inizio download di {target_candles} candele a {timeframe} per {symbol}...")
    
    all_candles = []
    limit = 1000  # Limite massimo di Binance per richiesta
    
    # 10,000 candele * 15 minuti in millisecondi
    candle_ms = 15 * 60 * 1000
    now_ms = int(time.time() * 1000)
    start_since = now_ms - (target_candles * candle_ms)
    
    since = start_since
    while len(all_candles) < target_candles:
        try:
            print(f"  Scaricamento lotto da timestamp: {since} (scaricate finora: {len(all_candles)})...")
            candles = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
            if not candles:
                print("  Nessuna altra candela restituita.")
                break
                
            # Evita duplicati/cicli infiniti
            if all_candles and candles[0][0] <= all_candles[-1][0]:
                since = all_candles[-1][0] + 1
                continue
                
            all_candles.extend(candles)
            since = candles[-1][0] + 1
            await asyncio.sleep(0.2)  # Pausa breve per evitare rate limit
        except Exception as e:
            print(f"  Errore durante il download: {e}. Riprovo tra 2 secondi...")
            await asyncio.sleep(2)
            
    await exchange.close()
    
    # Ritaglia per avere esattamente le ultime 10,000
    all_candles = all_candles[-target_candles:]
    
    # Conversione in DataFrame
    columns = ["timestamp", "Open", "High", "Low", "Close", "Volume"]
    df = pd.DataFrame(all_candles, columns=columns)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df.index.name = "datetime"
    df = df.astype(float)
    df.sort_index(inplace=True)
    
    print(f"✅ Completato! {len(df)} candele caricate.")
    return df

async def main():
    df = await download_10k()
    
    from config import Config
    import polars as pl
    from core.data_collector import DatasetIntegrity, DatasetVersioning
    
    # Converte index in colonna per caricamento Polars
    df_reset = df.reset_index()
    df_pl = pl.DataFrame(df_reset)
    
    try:
        df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
        df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
        df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
        DatasetIntegrity.validate_timestamps(df_pl, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
        
        out_dir = "data"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "btc_15m_10k_cache.parquet")
        
        DatasetVersioning.write_parquet_with_metadata(df_pl, out_path, is_features=False)
        print(f"💾 File salvato con successo in formato Parquet: {out_path}")
    except Exception as e:
        print(f"❌ Errore durante la validazione o scrittura del file Parquet scaricato: {e}")

if __name__ == "__main__":
    asyncio.run(main())
