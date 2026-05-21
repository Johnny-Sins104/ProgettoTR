import os
import sys
import pandas as pd
import numpy as np
import random
import time
from config import Config

INITIAL_BALANCE  = 1000.0
COMMISSION_RATE  = 0.001

def evaluate_dict(last_row, w_t, w_r, t_thresh, r_thresh):
    regime = last_row.get("market_regime", "RANGING")
    if regime == "TRENDING":
        w = w_t
        threshold = t_thresh
    else:
        w = w_r
        threshold = r_thresh

    score = 0
    conf = {k: False for k in w}

    # EMA
    close = last_row["Close"]
    ema = last_row["ema_200"]
    if ema > 0:
        if close > ema:
            score += w.get("ema", 0)
            conf["ema"] = True
        elif close < ema:
            score -= w.get("ema", 0)
            conf["ema"] = True

    # Bias
    bias_val = last_row.get("volume_bias", "NEUTRAL")
    if bias_val == "BULLISH":
        score += w.get("bias", 0)
        conf["bias"] = True
    elif bias_val == "BEARISH":
        score -= w.get("bias", 0)
        conf["bias"] = True

    # Engulfing
    engulfing_val = last_row.get("cdl_engulfing", 0)
    if engulfing_val == 100:
        score += w.get("engulfing", 0)
        conf["engulfing"] = True
    elif engulfing_val == -100:
        score -= w.get("engulfing", 0)
        conf["engulfing"] = True

    # RSI
    rsi = last_row.get("rsi_14", 50)
    if rsi < 30:
        score += w.get("rsi", 0)
        conf["rsi"] = True
    elif rsi > 70:
        score -= w.get("rsi", 0)
        conf["rsi"] = True

    # Near Support/Resistance
    near_sup = bool(last_row.get("near_support", False))
    near_res = bool(last_row.get("near_resistance", False))
    if score > 0 and near_sup:
        score += w.get("support", 0)
        conf["support"] = True
    elif score < 0 and near_res:
        score -= w.get("support", 0)
        conf["support"] = True

    # Psychology
    dist_psy = float(last_row.get("dist_to_psy_level", 999))
    if dist_psy < 0.2:
        conf["psy_level"] = True
        if score > 0:
            score += w.get("psy_level", 0)
        elif score < 0:
            score -= w.get("psy_level", 0)

    # Decision
    engulfing = bool(engulfing_val != 0)
    local_sup = float(last_row.get("local_support", 0))
    local_res = float(last_row.get("local_resistance", 0))

    # Macro indicators (400 candles)
    ema_200 = float(last_row.get("ema_200", 0))
    ema_400 = float(last_row.get("ema_400", 0))
    range_pos_400 = float(last_row.get("range_pos_400", 0.5))

    if score >= threshold:
        verdict = "BUY"
        # Filtro macro trend & market structure (400 candele)
        if regime == "TRENDING":
            if ema_200 > 0 and ema_400 > 0 and ema_200 <= ema_400:
                verdict = "HOLD"
                entry_type = None
        else:
            if range_pos_400 > 0.6:
                verdict = "HOLD"
                entry_type = None

        if verdict == "BUY":
            if engulfing and bias_val == "BULLISH":
                entry_type = "MARKET"
            elif near_res and local_res > 0:
                entry_type = "STOP"
            else:
                entry_type = "LIMIT"
    elif score <= -threshold:
        verdict = "SELL"
        # Filtro macro trend & market structure (400 candele)
        if regime == "TRENDING":
            if ema_200 > 0 and ema_400 > 0 and ema_200 >= ema_400:
                verdict = "HOLD"
                entry_type = None
        else:
            if range_pos_400 < 0.4:
                verdict = "HOLD"
                entry_type = None

        if verdict == "SELL":
            if engulfing and bias_val == "BEARISH":
                entry_type = "MARKET"
            elif near_sup and local_sup > 0:
                entry_type = "STOP"
            else:
                entry_type = "LIMIT"
    else:
        verdict = "HOLD"
        entry_type = None

    # Confluenza pre-entrata (Checklist istituzionale)
    confluence_verdict = "RED"
    confluence_comb = "None"

    if verdict in ("BUY", "SELL"):
        # Pattern: Engulfing or Doji
        has_pattern = False
        cdl_eng = last_row.get("cdl_engulfing", 0)
        cdl_doji = last_row.get("cdl_doji", 0)
        if verdict == "BUY":
            has_pattern = bool(cdl_eng == 100 or cdl_doji == 100)
        elif verdict == "SELL":
            has_pattern = bool(cdl_eng == -100 or cdl_doji == 100)

        # Support / Resistance proximity
        has_sr = False
        if verdict == "BUY":
            has_sr = bool(last_row.get("near_support", False))
        elif verdict == "SELL":
            has_sr = bool(last_row.get("near_resistance", False))

        # Psychological Level (multiples of 250)
        has_psy = bool(float(last_row.get("dist_to_psy_level", 999)) < 0.2)

        # Favorable Volume Bias (5-candle Volume Delta)
        has_bias = False
        bias_val = last_row.get("volume_bias", "NEUTRAL")
        if verdict == "BUY" and bias_val == "BULLISH":
            has_bias = True
        elif verdict == "SELL" and bias_val == "BEARISH":
            has_bias = True

        # Combinations:
        if has_pattern and has_sr and has_psy and has_bias:
            confluence_verdict = "GREEN"
            confluence_comb = "Pattern+Support+Psy+Bias"
        elif has_pattern and has_sr:
            confluence_verdict = "YELLOW"
            confluence_comb = "Pattern+Support"

        # Solo il Semaforo Verde (GREEN) autorizza l'esecuzione
        if confluence_verdict != "GREEN":
            verdict = "HOLD"
            entry_type = None

    return verdict, score, conf, entry_type, confluence_verdict, confluence_comb

def run_backtest_dict(
    rows_dict: list[dict],
    risk_per_trade: float,
    atr_mult: float,
    trending_rr: float,
    ranging_rr: float,
    w_t: dict,
    w_r: dict,
    t_thresh: int,
    r_thresh: int
) -> dict:
    balance = INITIAL_BALANCE
    trades = []
    open_trade = None
    pending_trigger = None
    max_drawdown = 0.0
    peak_balance = INITIAL_BALANCE

    for i in range(1, len(rows_dict)):
        row = rows_dict[i]

        # 1. Gestione trade aperto
        if open_trade is not None:
            hi  = float(row["High"])
            lo  = float(row["Low"])
            sl  = open_trade["sl"]
            entry = open_trade["entry"]
            size = open_trade["size"]
            side = open_trade["side"]
            tp1 = open_trade["tp1"]
            tp2 = open_trade["tp2"]
            tp1_hit = open_trade.get("tp1_hit", False)

            # Check per TP1
            if not tp1_hit:
                hit_tp1 = (side == "BUY" and hi >= tp1) or (side == "SELL" and lo <= tp1)
                hit_sl = (side == "BUY" and lo <= sl) or (side == "SELL" and hi >= sl)

                if hit_tp1:
                    open_trade["tp1_hit"] = True
                    tp1_hit = True
                    pnl_1 = (size / 2) * (tp1 - entry) if side == "BUY" else (size / 2) * (entry - tp1)
                    comm_1 = (size / 2) * entry * COMMISSION_RATE * 2
                    net_pnl_1 = pnl_1 - comm_1
                    balance += net_pnl_1
                    open_trade["pnl_tp1_net"] = net_pnl_1

                    # Muovi Stop Loss della seconda metà a Breakeven se configurato
                    if Config.USE_BREAKEVEN_ON_TP1:
                        new_sl = entry + (2 * entry * COMMISSION_RATE) if side == "BUY" else entry - (2 * entry * COMMISSION_RATE)
                        sl = new_sl
                        open_trade["sl"] = sl
                        open_trade["be_triggered"] = True
                elif hit_sl:
                    pnl = size * (sl - entry) if side == "BUY" else size * (entry - sl)
                    commission = size * entry * COMMISSION_RATE * 2
                    net_pnl = pnl - commission
                    balance += net_pnl

                    if balance > peak_balance:
                        peak_balance = balance
                    dd = (peak_balance - balance) / peak_balance * 100
                    if dd > max_drawdown:
                        max_drawdown = dd

                    trades.append({
                        "result": "LOSS",
                        "pnl": net_pnl,
                        "balance": balance,
                        "side": side,
                        "entry": entry,
                        "sl": open_trade["initial_sl"],
                        "tp": tp2,
                        "confluence_comb": open_trade.get("confluence_comb", "None")
                    })
                    open_trade = None
                    if balance <= 0:
                        break

            # Se TP1 è stato già colpito, monitora la seconda metà
            if open_trade is not None and open_trade.get("tp1_hit", False):
                hit_tp2 = (side == "BUY" and hi >= tp2) or (side == "SELL" and lo <= tp2)
                hit_sl2 = (side == "BUY" and lo <= sl) or (side == "SELL" and hi >= sl)

                if hit_tp2 or hit_sl2:
                    if hit_tp2 and not hit_sl2:
                        exit_price_2 = tp2
                        result = "WIN"
                    else:
                        exit_price_2 = sl
                        result = "WIN_PARTIAL"

                    pnl_2 = (size / 2) * (exit_price_2 - entry) if side == "BUY" else (size / 2) * (entry - exit_price_2)
                    comm_2 = (size / 2) * entry * COMMISSION_RATE * 2
                    net_pnl_2 = pnl_2 - comm_2
                    balance += net_pnl_2

                    net_pnl_total = open_trade["pnl_tp1_net"] + net_pnl_2

                    if balance > peak_balance:
                        peak_balance = balance
                    dd = (peak_balance - balance) / peak_balance * 100
                    if dd > max_drawdown:
                        max_drawdown = dd

                    trades.append({
                        "result": result,
                        "pnl": net_pnl_total,
                        "balance": balance,
                        "side": side,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp2,
                        "confluence_comb": open_trade.get("confluence_comb", "None")
                    })
                    open_trade = None
                    if balance <= 0:
                        break

            if open_trade is not None:
                if pending_trigger is not None:
                    pending_trigger["ttl"] -= 1
                    if pending_trigger["ttl"] <= 0:
                        pending_trigger = None
                continue

        # 2. Gestione breakout trigger pendente (solo se non c'è una posizione aperta)
        if open_trade is None and pending_trigger is not None:
            hi = float(row["High"])
            lo = float(row["Low"])
            side = pending_trigger["side"]
            sh = pending_trigger["signal_high"]
            sl_level = pending_trigger["signal_low"]
            
            triggered = False
            entry_price = 0.0
            
            if side == "BUY" and hi >= sh:
                triggered = True
                entry_price = max(float(row["Open"]), sh)
            elif side == "SELL" and lo <= sl_level:
                triggered = True
                entry_price = min(float(row["Open"]), sl_level)
                
            if triggered:
                atr_val = pending_trigger["atr_val"]
                current_rr = pending_trigger["current_rr"]
                
                if side == "BUY":
                    sl = entry_price - (atr_val * atr_mult)
                    tp = entry_price + ((entry_price - sl) * current_rr)
                    tp1 = entry_price + ((entry_price - sl) * Config.TP1_RR)
                else:
                    sl = entry_price + (atr_val * atr_mult)
                    tp = entry_price - ((sl - entry_price) * current_rr)
                    tp1 = entry_price - ((sl - entry_price) * Config.TP1_RR)
                    
                risk_per_unit = abs(entry_price - sl)
                if risk_per_unit > 0:
                    regime = pending_trigger["regime"]
                    
                    if risk_per_trade <= 0.03:
                        current_lev = 4.0
                    elif risk_per_trade <= 0.07:
                        current_lev = 8.0
                    else:
                        current_lev = 10.0
                        
                    risk_capital = balance * risk_per_trade
                    if Config.USE_COMMISSION_AWARE_SIZING:
                        size = risk_capital / (risk_per_unit + (2 * entry_price * COMMISSION_RATE))
                    else:
                        size = risk_capital / risk_per_unit
                    max_size = (balance * current_lev) / entry_price
                    size = min(size, max_size)
                    
                    open_trade = {
                        "side": side,
                        "type": "BREAKOUT",
                        "entry": entry_price,
                        "sl": sl,
                        "initial_sl": sl,
                        "be_triggered": False,
                        "tp": tp,
                        "tp1": tp1,
                        "tp2": tp,
                        "tp1_hit": False,
                        "pnl_tp1_net": 0.0,
                        "size": size,
                        "active_conf": pending_trigger["active_conf"],
                        "confluence_comb": pending_trigger["confluence_comb"]
                    }
                pending_trigger = None
            else:
                pending_trigger["ttl"] -= 1
                if pending_trigger["ttl"] <= 0:
                    pending_trigger = None

        # 3. Valuta nuovi segnali
        if open_trade is None and pending_trigger is None:
            last = rows_dict[i-1]
            res = evaluate_dict(last, w_t, w_r, t_thresh, r_thresh)
            verdict, score, active_conf, entry_type, confluence_verdict, confluence_comb = res

            if verdict in ("BUY", "SELL") and entry_type is not None:
                close_p = float(last["Close"])
                atr_val = float(last["atr"]) if float(last["atr"]) > 0 else close_p * 0.01
                regime = last.get("market_regime", "RANGING")
                current_rr = trending_rr if regime == "TRENDING" else ranging_rr

                pending_trigger = {
                    "side": verdict,
                    "signal_high": float(last["High"]),
                    "signal_low": float(last["Low"]),
                    "ttl": 2,
                    "atr_val": atr_val,
                    "current_rr": current_rr,
                    "score": score,
                    "confluence_comb": confluence_comb,
                    "active_conf": active_conf,
                    "regime": regime
                }

    wins = len([t for t in trades if t["result"] == "WIN"])
    partial_wins = len([t for t in trades if t["result"] == "WIN_PARTIAL"])
    losses = len([t for t in trades if t["result"] == "LOSS"])
    breakevens = len([t for t in trades if t["result"] == "BREAKEVEN"])
    
    total_wins = wins + partial_wins
    trade_con_esito = total_wins + losses
    win_rate = (total_wins / trade_con_esito * 100) if trade_con_esito > 0 else 0.0
    net = balance - INITIAL_BALANCE
    pct = (net / INITIAL_BALANCE) * 100

    return {
        "final_balance": balance,
        "net_pnl_pct": pct,
        "total_trades": len(trades),
        "wins": wins,
        "partial_wins": partial_wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown
    }

# ------------------------------------------------------------------ #
#  GENETIC ALGORITHM UTILITIES                                        #
# ------------------------------------------------------------------ #

def random_weights():
    vals = [random.randint(0, 50) for _ in range(6)]
    s = sum(vals)
    if s == 0:
        return {"ema": 20, "bias": 20, "engulfing": 20, "rsi": 20, "support": 20, "psy_level": 0}
    w = {
        "ema": int(round(vals[0] / s * 100)),
        "bias": int(round(vals[1] / s * 100)),
        "engulfing": int(round(vals[2] / s * 100)),
        "rsi": int(round(vals[3] / s * 100)),
        "support": int(round(vals[4] / s * 100)),
        "psy_level": int(round(vals[5] / s * 100))
    }
    diff = 100 - sum(w.values())
    w["ema"] += diff
    return w

def mutate_weights(w):
    w_new = w.copy()
    keys = list(w.keys())
    k1, k2 = random.sample(keys, 2)
    amount = random.randint(1, 15)
    if w_new[k1] >= amount:
        w_new[k1] -= amount
        w_new[k2] += amount
    return w_new

class Individual:
    def __init__(self, gene=None):
        if gene is None:
            self.gene = {
                "w_t": random_weights(),
                "w_r": random_weights(),
                "atr_mult": round(random.uniform(0.5, 3.0), 2),
                "trending_rr": round(random.uniform(1.5, 4.5), 2),
                "ranging_rr": round(random.uniform(1.2, 3.5), 2),
                "t_thresh": random.randint(20, 75),
                "r_thresh": random.randint(20, 75),
                "adx_t": round(random.uniform(15.0, 35.0), 2)
            }
        else:
            self.gene = gene
        self.fitness = 0.0
        self.res = None

    def calculate_fitness(self, regime_dicts):
        adx_t_nearest = round(self.gene["adx_t"] / 5) * 5
        adx_t_nearest = max(15, min(35, adx_t_nearest))
        rows_dict = regime_dicts[adx_t_nearest]
        
        # Test 1: Basso Rischio (3.0%)
        res_low = run_backtest_dict(
            rows_dict=rows_dict,
            risk_per_trade=0.03,
            atr_mult=self.gene["atr_mult"],
            trending_rr=self.gene["trending_rr"],
            ranging_rr=self.gene["ranging_rr"],
            w_t=self.gene["w_t"],
            w_r=self.gene["w_r"],
            t_thresh=self.gene["t_thresh"],
            r_thresh=self.gene["r_thresh"]
        )
        
        # Test 2: Medio Rischio (7.0%)
        res_med = run_backtest_dict(
            rows_dict=rows_dict,
            risk_per_trade=0.07,
            atr_mult=self.gene["atr_mult"],
            trending_rr=self.gene["trending_rr"],
            ranging_rr=self.gene["ranging_rr"],
            w_t=self.gene["w_t"],
            w_r=self.gene["w_r"],
            t_thresh=self.gene["t_thresh"],
            r_thresh=self.gene["r_thresh"]
        )
        
        # Test 3: Alto Rischio (15.0%)
        res_high = run_backtest_dict(
            rows_dict=rows_dict,
            risk_per_trade=0.15,
            atr_mult=self.gene["atr_mult"],
            trending_rr=self.gene["trending_rr"],
            ranging_rr=self.gene["ranging_rr"],
            w_t=self.gene["w_t"],
            w_r=self.gene["w_r"],
            t_thresh=self.gene["t_thresh"],
            r_thresh=self.gene["r_thresh"]
        )
        
        fit_low = res_low["final_balance"]
        if res_low["max_drawdown"] > 10.0:
            fit_low *= (10.0 / res_low["max_drawdown"]) ** 2
        elif res_low["max_drawdown"] == 0:
            fit_low *= 0.5
            
        fit_med = res_med["final_balance"]
        if res_med["max_drawdown"] > 20.0:
            fit_med *= (20.0 / res_med["max_drawdown"]) ** 2
        elif res_med["max_drawdown"] == 0:
            fit_med *= 0.5
            
        fit_high = res_high["final_balance"]
        if res_high["max_drawdown"] > 35.0:
            fit_high *= (35.0 / res_high["max_drawdown"]) ** 2
        elif res_high["max_drawdown"] == 0:
            fit_high *= 0.5
            
        # Minimo di trade per robustezza (almeno 30 trade)
        min_trades = min(res_low["total_trades"], res_med["total_trades"], res_high["total_trades"])
        if min_trades < 30:
            trade_penalty = (min_trades / 30.0) ** 3
            fit_low *= trade_penalty
            fit_med *= trade_penalty
            fit_high *= trade_penalty
            
        # Se il saldo scende sotto €1000 in una qualsiasi classe, penalizziamo pesantemente
        min_bal = min(res_low["final_balance"], res_med["final_balance"], res_high["final_balance"])
        if min_bal < 1000.0:
            self.fitness = min_bal * 0.1
        else:
            self.fitness = fit_low * 1.0 + fit_med * 1.5 + fit_high * 2.5

        # Moltiplicatore per il Win Rate per favorire configurazioni con "tante win e poche lose" (alta win rate)
        avg_win_rate = (res_low["win_rate"] + res_med["win_rate"] + res_high["win_rate"]) / 3.0
        
        # Penalizziamo progressivamente sotto il 40% di Win Rate, premiamo sopra il 45% o 50%
        win_rate_mult = 1.0
        if avg_win_rate < 40.0:
            win_rate_mult = (avg_win_rate / 40.0) ** 2
        elif avg_win_rate > 50.0:
            win_rate_mult = 1.0 + (avg_win_rate - 50.0) / 100.0
            
        self.fitness *= win_rate_mult
            
        self.res = {
            "low": res_low,
            "med": res_med,
            "high": res_high
        }

def crossover(parent1, parent2):
    child_gene = {}
    for k in parent1.gene.keys():
        if k in ("w_t", "w_r"):
            child_gene[k] = parent1.gene[k].copy() if random.random() < 0.5 else parent2.gene[k].copy()
        else:
            child_gene[k] = parent1.gene[k] if random.random() < 0.5 else parent2.gene[k]
    return Individual(child_gene)

def mutate(ind):
    gene = ind.gene.copy()
    k = random.choice(list(gene.keys()))
    if k == "w_t":
        gene["w_t"] = mutate_weights(gene["w_t"])
    elif k == "w_r":
        gene["w_r"] = mutate_weights(gene["w_r"])
    elif k == "atr_mult":
        gene["atr_mult"] = round(max(0.3, min(3.5, gene["atr_mult"] + random.uniform(-0.3, 0.3))), 2)
    elif k == "trending_rr":
        gene["trending_rr"] = round(max(1.2, min(5.0, gene["trending_rr"] + random.uniform(-0.3, 0.3))), 2)
    elif k == "ranging_rr":
        gene["ranging_rr"] = round(max(1.0, min(4.0, gene["ranging_rr"] + random.uniform(-0.2, 0.2))), 2)
    elif k == "t_thresh":
        gene["t_thresh"] = max(15, min(75, gene["t_thresh"] + random.randint(-6, 6)))
    elif k == "r_thresh":
        gene["r_thresh"] = max(15, min(75, gene["r_thresh"] + random.randint(-6, 6)))
    elif k == "adx_t":
        gene["adx_t"] = round(max(15.0, min(35.0, gene["adx_t"] + random.uniform(-2.0, 2.0))), 2)
    return Individual(gene)

def main():
    cache_path = os.path.join("data", "btc_15m_cache.csv")
    print(f"[GENETIC] Caricamento cache da {cache_path}...")
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    print(f"[GENETIC] Caricate {len(df)} righe.")
    
    adx_bins = [15, 20, 25, 30, 35]
    regime_dicts = {}
    for adx_t in adx_bins:
        df_temp = df.copy()
        df_temp["market_regime"] = "RANGING"
        df_temp.loc[df_temp["adx"] > adx_t, "market_regime"] = "TRENDING"
        regime_dicts[adx_t] = df_temp.to_dict(orient="records")
        
    POP_SIZE = 150
    GENERATIONS = 30
    
    print(f"\n[GENETIC] Inizializzazione popolazione di {POP_SIZE} individui con Joint Optimization...")
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
        
        print(f"Gen {gen}/{GENERATIONS} | Low: {low_bal:.1f} (DD:{low_dd:.1f}%) | Med: {med_bal:.1f} (DD:{med_dd:.1f}%) | High: {high_bal:.1f} (DD:{high_dd:.1f}%) | Trades: {trades} | Tempo: {elapsed:.2f}s")
        
        next_pop = pop[:20]
        while len(next_pop) < POP_SIZE:
            p1, p2 = random.sample(pop[:40], 2)
            child = crossover(p1, p2)
            if random.random() < 0.4:
                child = mutate(child)
            next_pop.append(child)
        pop = next_pop
 
    pop.sort(key=lambda x: x.fitness, reverse=True)
    best = pop[0]
    g = best.gene
    
    print("\n==================================================")
    print("  RISULTATI OTTIMIZZATORE MULTI-RISCHIO JOINT")
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
    print("  CLASSI DI RISCHIO COMPILATE DEFINITIVE")
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
