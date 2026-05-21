import os
import sys
import pandas as pd
import numpy as np
import random
import time

# Assicuriamoci che l'encoding in output supporti UTF-8 su Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Aggiunge la directory corrente al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.analyzer import TechnicalAnalyzer
from genetic_opt import Individual, crossover, mutate, run_backtest_dict

def main():
    cache_path = os.path.join("data", "btc_5m_10k_cache.csv")
    if not os.path.exists(cache_path):
        print(f"❌ File di cache non trovato in: {cache_path}")
        return
        
    print(f"📈 Caricamento dati da {cache_path}...")
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    
    print("🔬 Calcolo degli indicatori tecnici avanzati per l'ottimizzazione...")
    df = TechnicalAnalyzer().add_indicators(df)
    
    print(f"[GENETIC] Caricate {len(df)} righe.")
    
    adx_bins = [15, 20, 25, 30, 35]
    regime_dicts = {}
    for adx_t in adx_bins:
        df_temp = df.copy()
        df_temp["market_regime"] = "RANGING"
        df_temp.loc[df_temp["adx"] > adx_t, "market_regime"] = "TRENDING"
        regime_dicts[adx_t] = df_temp.to_dict(orient="records")
        
    # Dimensione popolazione leggermente ridotta per velocità su 10k righe
    POP_SIZE = 100
    GENERATIONS = 20
    
    print(f"\n🧬 Avvio Evoluzione Genetica con Popolazione: {POP_SIZE} su {GENERATIONS} Generazioni...")
    pop = [Individual() for _ in range(POP_SIZE)]
    
    for gen in range(1, GENERATIONS + 1):
        start_t = time.time()
        for ind in pop:
            ind.calculate_fitness(regime_dicts)
        pop.sort(key=lambda x: x.fitness, reverse=True)
        best = pop[0]
        elapsed = time.time() - start_t
        
        low_bal = best.res["low"]["final_balance"]
        low_dd = best.res["low"]["max_drawdown"]
        med_bal = best.res["med"]["final_balance"]
        med_dd = best.res["med"]["max_drawdown"]
        high_bal = best.res["high"]["final_balance"]
        high_dd = best.res["high"]["max_drawdown"]
        trades = best.res["high"]["total_trades"]
        
        print(f"Gen {gen:02d}/{GENERATIONS:02d} | Low: {low_bal:.1f} € (DD:{low_dd:.1f}%) | Med: {med_bal:.1f} € (DD:{med_dd:.1f}%) | High: {high_bal:.1f} € (DD:{high_dd:.1f}%) | Trades: {trades} | Tempo: {elapsed:.2f}s")
        
        next_pop = pop[:15]
        while len(next_pop) < POP_SIZE:
            p1, p2 = random.sample(pop[:30], 2)
            child = crossover(p1, p2)
            if random.random() < 0.35:
                child = mutate(child)
            next_pop.append(child)
        pop = next_pop
 
    pop.sort(key=lambda x: x.fitness, reverse=True)
    best = pop[0]
    g = best.gene
    
    print("\n==================================================")
    print("  PARAMETRI OTTENUTI OTTIMIZZATI SULLE 10.000 CANDELE")
    print("==================================================")
    print(f"  -> Stop Loss ATR Multiplier   : {g['atr_mult']:.2f}")
    print(f"  -> Trending RR                : {g['trending_rr']:.2f}")
    print(f"  -> Ranging RR                 : {g['ranging_rr']:.2f}")
    print(f"  -> ADX Regime Threshold       : {g['adx_t']:.2f}")
    print(f"  -> Trending Signal Threshold  : {g['t_thresh']}")
    print(f"  -> Ranging Signal Threshold   : {g['r_thresh']}")
    print(f"\n  -> Pesi Trending Ottimizzati: {g['w_t']}")
    print(f"  -> Pesi Ranging Ottimizzati : {g['w_r']}")
    
    print("\n==================================================")
    print("  CLASSI DI RISCHIO COMPILATE DEFINITIVE (10K CANDELE)")
    print("==================================================")
    
    for label, risk_val in [("Basso Rischio (Target: ~1200-1500, DD<10%)", 0.03), 
                            ("Medio Rischio (Target: ~2000-3000, DD<20%)", 0.07), 
                            ("Alto Rischio  (Target: 5000+, DD<=35%)", 0.15)]:
        r_c = run_backtest_dict(
            rows_dict=regime_dicts[round(g["adx_t"]/5)*5],
            risk_per_trade=risk_val,
            atr_mult=g["atr_mult"],
            trending_rr=g["trending_rr"],
            ranging_rr=g["ranging_rr"],
            w_t=g["w_t"],
            w_r=g["w_r"],
            t_thresh=g["t_thresh"],
            r_thresh=g["r_thresh"]
        )
        print(f"\n  [{label}]")
        print(f"    Saldo Finale               : {r_c['final_balance']:.2f} €")
        print(f"    Profitto netto             : {r_c['net_pnl_pct']:+.2f}%")
        print(f"    Max Drawdown               : {r_c['max_drawdown']:.1f}%")
        print(f"    Numero di Trade            : {r_c['total_trades']}")
        print(f"    Win Rate                   : {r_c['win_rate']:.1f}%")

if __name__ == "__main__":
    main()
