import asyncio
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.analyzer import TechnicalAnalyzer
from core.risk import RiskManager

INITIAL_BALANCE  = 1000.0
COMMISSION_RATE  = 0.001

def simulate_backtest_custom(
    df: pd.DataFrame, 
    risk_pct: float, 
    max_leverage: float,
    tp1_rr: float,
    use_be_on_tp1: bool,
    be_sl_ratio: float,
    split_tp1: float  # e.g., 0.5 means 50%, 0.7 means 70%
) -> dict:
    from core.engine import DecisionEngine
    engine   = DecisionEngine()
    risk_mgr = RiskManager()

    balance       = INITIAL_BALANCE
    trades        = []
    open_trade    = None
    pending_trigger = None
    max_drawdown = 0.0
    peak_balance = INITIAL_BALANCE

    rows = df.reset_index()

    for i in range(1, len(rows)):
        row = rows.iloc[i]

        if open_trade is not None:
            hi  = float(row["High"])
            lo  = float(row["Low"])
            sl  = open_trade["sl"]
            entry     = open_trade["entry"]
            size      = open_trade["size"]
            side      = open_trade["side"]
            tp1       = open_trade["tp1"]
            tp2       = open_trade["tp2"]
            tp1_hit   = open_trade.get("tp1_hit", False)

            # Check per TP1
            if not tp1_hit:
                hit_tp1 = (side == "BUY" and hi >= tp1) or (side == "SELL" and lo <= tp1)
                hit_sl = (side == "BUY" and lo <= sl) or (side == "SELL" and hi >= sl)

                if hit_tp1:
                    open_trade["tp1_hit"] = True
                    tp1_hit = True
                    
                    pnl_1 = (size * split_tp1) * (tp1 - entry) if side == "BUY" else (size * split_tp1) * (entry - tp1)
                    comm_1 = (size * split_tp1) * entry * COMMISSION_RATE * 2
                    net_pnl_1 = pnl_1 - comm_1
                    balance += net_pnl_1
                    open_trade["pnl_tp1_net"] = net_pnl_1

                    if use_be_on_tp1:
                        if be_sl_ratio == 0.0:
                            new_sl = entry + (2 * entry * COMMISSION_RATE) if side == "BUY" else entry - (2 * entry * COMMISSION_RATE)
                        else:
                            sl_dist = abs(entry - open_trade["initial_sl"])
                            new_sl = entry + (be_sl_ratio * sl_dist) if side == "BUY" else entry - (be_sl_ratio * sl_dist)
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
                        "balance": balance
                    })
                    open_trade = None
                    if balance <= 0:
                        break

            # Se TP1 è stato già colpito, monitora la seconda parte della posizione (1 - split_tp1)
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

                    remaining_split = 1.0 - split_tp1
                    pnl_2 = (size * remaining_split) * (exit_price_2 - entry) if side == "BUY" else (size * remaining_split) * (entry - exit_price_2)
                    comm_2 = (size * remaining_split) * entry * COMMISSION_RATE * 2
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
                        "balance": balance
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

        # 2. Gestione breakout trigger pendente
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
                targets = risk_mgr.calculate_targets(side, entry_price, atr_val, rr_ratio=current_rr)
                if side == "BUY":
                    targets["tp1"] = entry_price + ((entry_price - targets["sl"]) * tp1_rr)
                else:
                    targets["tp1"] = entry_price - ((targets["sl"] - entry_price) * tp1_rr)

                sl, tp  = targets["sl"], targets["tp"]
                
                risk_per_unit = abs(entry_price - sl)
                if risk_per_unit > 0:
                    current_risk = risk_pct
                    current_lev = max_leverage
                        
                    risk_capital = balance * current_risk
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
                        "tp1": targets["tp1"],
                        "tp2": targets["tp2"],
                        "tp1_hit": False,
                        "pnl_tp1_net": 0.0,
                        "size": size,
                        "window_df": pending_trigger["window_df"],
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
            window   = df.iloc[:i]
            last     = window.iloc[-1]
            res = engine.evaluate(window)
            
            if len(res) == 6:
                verdict, score, active_conf, entry_type, confluence_verdict, confluence_comb = res
            else:
                verdict, score, active_conf, entry_type = res
                confluence_verdict = "GREEN" if verdict in ("BUY", "SELL") else "RED"
                confluence_comb = "Legacy"

            if verdict not in ("BUY", "SELL") or entry_type is None:
                continue

            close_p = float(last["Close"])
            atr_val = float(last["atr"]) if float(last["atr"]) > 0 else close_p * 0.01
            regime = last.get("market_regime", "RANGING")
            current_rr = Config.TRENDING_RR if regime == "TRENDING" else Config.RANGING_RR

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
                "window_df": window.copy(),
                "regime": regime
            }

    wins = len([t for t in trades if t["result"] == "WIN"])
    partial_wins = len([t for t in trades if t["result"] == "WIN_PARTIAL"])
    losses = len([t for t in trades if t["result"] == "LOSS"])
    trade_con_esito = wins + partial_wins + losses
    win_rate = ((wins + partial_wins) / trade_con_esito * 100) if trade_con_esito > 0 else 0.0

    return {
        "final_balance": balance,
        "max_drawdown": max_drawdown,
        "total_trades": len(trades),
        "wins": wins,
        "partial_wins": partial_wins,
        "losses": losses,
        "win_rate": win_rate
    }

async def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

    cache_path = os.path.join("data", "btc_5m_10k_cache.csv")
    if not os.path.exists(cache_path):
        print("[ERROR] Cache non trovata!")
        return
        
    print(f"[INFO] Caricamento dati da {cache_path}...")
    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
    df = TechnicalAnalyzer().add_indicators(df)
    
    print("\n[TEST] Analisi Ottimizzazione Splits e Trailing SL")
    print("==========================================================================================")
    print(f"{'Split TP1':<12}{'TP1_RR':<8}{'Trailing SL type':<24}{'Win Rate %':<12}{'Saldo LOW':<14}{'Trades':<8}")
    print("------------------------------------------------------------------------------------------")
    
    for split in [0.5, 0.6, 0.7]:
        for tp1_rr in [1.5, 2.0]:
            # Scenario A: Trailing SL a Breakeven
            res_a = simulate_backtest_custom(df, 0.03, 4.0, tp1_rr, use_be_on_tp1=True, be_sl_ratio=0.0, split_tp1=split)
            print(f"{split:<12.1f}{tp1_rr:<8.1f}{'Breakeven (0.0)':<24}{res_a['win_rate']:<12.1f}{res_a['final_balance']:<14.2f}{res_a['total_trades']:<8}")
            
            # Scenario B: Nessun Trailing (mantiene SL originale)
            res_b = simulate_backtest_custom(df, 0.03, 4.0, tp1_rr, use_be_on_tp1=False, be_sl_ratio=0.0, split_tp1=split)
            print(f"{split:<12.1f}{tp1_rr:<8.1f}{'Nessuno (SL originale)':<24}{res_b['win_rate']:<12.1f}{res_b['final_balance']:<14.2f}{res_b['total_trades']:<8}")
            
            print("-" * 88)

if __name__ == "__main__":
    asyncio.run(main())
