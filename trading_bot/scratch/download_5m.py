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

async def download_5m_10k():
    exchange = ccxt_async.binance()
    symbol = "BTC/USDT"
    timeframe = "5m"
    target_candles = 10000
    
    print(f"🤖 Inizio download di {target_candles} candele a {timeframe} per {symbol}...")
    
    all_candles = []
    limit = 1000  # Limite massimo di Binance per richiesta
    
    # 10,000 candele * 5 minuti in millisecondi
    candle_ms = 5 * 60 * 1000
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
    df = await download_5m_10k()
    out_dir = "data"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "btc_5m_10k_cache.csv")
    df.to_csv(out_path)
    print(f"💾 File salvato con successo in: {out_path}")

if __name__ == "__main__":
    asyncio.run(main())
