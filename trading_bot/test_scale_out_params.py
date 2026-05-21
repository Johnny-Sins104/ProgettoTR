import asyncio
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.analyzer import TechnicalAnalyzer
import backtest_lab

async def main():
    cache_path = os.path.join("data", "btc_5m_10k_cache.csv")
    if not os.path.exists(cache_path):
        print("❌ Cache non trovata!")
        return
        
    print(f"📈 Caricamento dati da {cache_path}...")
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    df = TechnicalAnalyzer().add_indicators(df)
    
    print("\n🔬 Ricerca del miglior valore di TP1_RR per la strategia di Scale-Out...")
    print("================================================================")
    print(f"{'TP1_RR':<10}{'Win Rate %':<15}{'Saldo LOW':<15}{'Saldo DYNAMIC':<15}{'Total Trades':<15}")
    print("----------------------------------------------------------------")
    
    for tp1_rr in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]:
        Config.TP1_RR = tp1_rr
        
        # Eseguiamo per DYNAMIC e per LOW
        res_low = backtest_lab.simulate_backtest(df, 0.03, 4.0)
        res_dyn = backtest_lab.simulate_backtest(df, "DYNAMIC", 0.0)
        
        print(f"{tp1_rr:<10.1f}{res_dyn['win_rate']:<15.1f}{res_low['final_balance']:<15.2f}{res_dyn['final_balance']:<15.2f}{res_dyn['total_trades']:<15}")
        
if __name__ == "__main__":
    asyncio.run(main())
