"""
Multi-Trade Manager — Gestione non-bloccante di trade multipli simultanei.
Versione Ottimizzata (Clean-Data): Break-Even a 1.5x ATR.
"""
import os
import json
import time
from datetime import datetime, timezone
from config import Config

TRADES_DIR = "data/trades"
COMMISSION_RATE = Config.COMMISSION_RATE


def _ensure_dir():
    os.makedirs(TRADES_DIR, exist_ok=True)


def get_open_trades() -> list[dict]:
    """Ritorna lista di tutti i trade aperti."""
    _ensure_dir()
    trades = []
    for fname in os.listdir(TRADES_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(TRADES_DIR, fname)
            try:
                with open(fpath, "r") as f:
                    trade = json.load(f)
                trade["_file"] = fpath
                trades.append(trade)
            except Exception:
                pass
    return trades


def count_open_trades() -> int:
    return len(get_open_trades())


def can_open_new_trade() -> bool:
    return count_open_trades() < Config.MAX_CONCURRENT_TRADES


def save_trade(trade: dict) -> str:
    """Salva un nuovo trade e ritorna il path del file."""
    _ensure_dir()
    trade_id = f"trade_{int(time.time() * 1000)}"
    trade["trade_id"] = trade_id
    trade["status"] = "ACTIVE"
    trade["opened_at"] = datetime.now(timezone.utc).isoformat()
    fpath = os.path.join(TRADES_DIR, f"{trade_id}.json")
    with open(fpath, "w") as f:
        json.dump(trade, f, indent=2)
    return fpath


def close_trade(trade: dict, exit_price: float, reason: str) -> float:
    """Chiude un trade, aggiorna il saldo, ritorna il PnL netto."""
    entry = trade["entry"]
    size = trade["size"]
    verdict = trade["verdict"]

    if verdict == "BUY":
        pnl = size * (exit_price - entry)
    else:
        pnl = size * (entry - exit_price)

    commission = size * entry * COMMISSION_RATE * 2
    net_pnl = pnl - commission

    # Aggiorna saldo
    balance_file = "data/balance_live.txt"
    balance = 100.0
    if os.path.exists(balance_file):
        try:
            with open(balance_file, "r") as f:
                balance = float(f.read().strip())
        except Exception:
            pass

    new_balance = balance + net_pnl
    try:
        with open(balance_file, "w") as f:
            f.write(f"{new_balance:.2f}")
    except Exception:
        pass

    # Log
    log_file = "data/bot_live.log"
    ts = datetime.now(timezone.utc).isoformat()
    try:
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(
                f"[{ts}] CLOSE_{reason} | {verdict} | Entry: {entry:.2f} | Exit: {exit_price:.2f} | "
                f"PnL: {net_pnl:+.2f} EUR | Balance: {new_balance:.2f} EUR | "
                f"TradeID: {trade.get('trade_id', '?')}\n"
            )
    except Exception:
        pass

    # Salvataggio delle features live per l'apprendimento continuo
    if "features" in trade and trade["features"]:
        try:
            from core.data_collector import DataCollector
            from core.ai_engine import TradingAI
            outcome = 1 if "TP" in reason else 0
            DataCollector.append_live(trade["features"], outcome)
            # Riaddestra automaticamente il modello se ha abbastanza nuovi campioni
            TradingAI().retrain_if_needed()
        except Exception as e:
            print(f"[WARN] Impossibile salvare le features live del trade chiuso: {e}")

    # Rimuovi il file del trade
    fpath = trade.get("_file", "")
    if fpath and os.path.exists(fpath):
        try:
            os.remove(fpath)
        except Exception:
            pass

    return net_pnl


def check_all_trades(current_price: float, notifier=None) -> list[dict]:
    """
    Controlla SL/TP di tutti i trade aperti.
    Sposta lo Stop Loss a Break-Even se il profitto raggiunge 1.5x ATR.
    """
    closed = []
    trades = get_open_trades()
    for trade in trades:
        verdict = trade["verdict"]
        entry = trade["entry"]
        sl = trade["sl"]
        tp = trade["tp"]
        atr_val = trade.get("atr_val", 0.0)
        is_be = trade.get("is_breakeven", False)

        # ── PROTEZIONE CAPITALE OTTIMIZZATA: BREAK-EVEN A 1.5x ATR ── #
        if atr_val > 0.0 and not is_be:
            be_triggered = False
            # Incrementato il moltiplicatore a 1.5x per dare respiro al trade
            if verdict == "BUY" and current_price >= entry + (atr_val * 1.5):
                be_triggered = True
            elif verdict == "SELL" and current_price <= entry - (atr_val * 1.5):
                be_triggered = True
            
            if be_triggered:
                trade["sl"] = entry
                trade["is_breakeven"] = True
                sl = entry
                
                # Salva modifiche su file JSON
                fpath = trade.get("_file", "")
                if fpath and os.path.exists(fpath):
                    try:
                        save_dict = {k: v for k, v in trade.items() if k != "_file"}
                        with open(fpath, "w") as f:
                            json.dump(save_dict, f, indent=2)
                    except Exception as e:
                        print(f"[WARN] Impossibile aggiornare trade per Break-Even: {e}")
                
                if notifier:
                    notifier.send_alert(
                        f"🛡️ BREAK-EVEN TRIGGERATO (1.5x ATR)! {verdict} a {entry:.2f}\n"
                        f"Stop Loss spostato a pareggio.",
                        print_console=True
                    )

        # Controllo standard SL/TP
        hit_tp = (verdict == "BUY" and current_price >= tp) or \
                 (verdict == "SELL" and current_price <= tp)
        hit_sl = (verdict == "BUY" and current_price <= sl) or \
                 (verdict == "SELL" and current_price >= sl)

        if hit_tp:
            net_pnl = close_trade(trade, tp, "TP_HIT")
            result = {"trade": trade, "reason": "TP", "pnl": net_pnl, "exit": tp}
            closed.append(result)
            if notifier:
                notifier.send_alert(f"✅ TP HIT! {verdict} chiuso a {tp:.2f}", print_console=False)
        elif hit_sl:
            reason = "BE_HIT" if trade.get("is_breakeven", False) else "SL_HIT"
            net_pnl = close_trade(trade, sl, reason)
            result = {"trade": trade, "reason": "SL", "pnl": net_pnl, "exit": sl}
            closed.append(result)
            if notifier:
                notifier.send_alert(f"❌ {reason.replace('_', ' ')}! {verdict} chiuso a {sl:.2f}", print_console=False)

    return closed


def check_pending_triggers(current_price: float, hi: float, lo: float, notifier=None) -> list[dict]:
    """Controlla i trigger breakout pendenti."""
    _ensure_dir()
    pending_dir = "data/pending"
    if not os.path.exists(pending_dir):
        os.makedirs(pending_dir, exist_ok=True)
        return []

    opened = []
    for fname in os.listdir(pending_dir):
        if not fname.endswith(".json"): continue
        fpath = os.path.join(pending_dir, fname)
        try:
            with open(fpath, "r") as f: pending = json.load(f)
        except Exception: continue

        side, trigger_price, atr_val = pending["side"], pending["trigger_price"], pending["atr_val"]
        ttl = pending.get("ttl", 2)

        triggered = False
        ep = 0.0
        if side == "BUY" and hi >= trigger_price:
            triggered, ep = True, max(current_price, trigger_price)
        elif side == "SELL" and lo <= trigger_price:
            triggered, ep = True, min(current_price, trigger_price)

        if triggered and can_open_new_trade():
            from core.risk import RiskManager
            rr = pending.get("current_rr", Config.TRENDING_RR)
            risk_pct = RiskManager().calculate_kelly_risk_pct(pending.get("ai_prob", 50.0), rr, pending.get("risk_pct", 0.15))

            sl = ep - atr_val * Config.ATR_MULT if side == "BUY" else ep + atr_val * Config.ATR_MULT
            tp = ep + atr_val * Config.ATR_MULT * rr if side == "BUY" else ep - atr_val * Config.ATR_MULT * rr

            risk_per_unit = abs(ep - sl)
            if risk_per_unit <= 0:
                os.remove(fpath)
                continue

            balance = 100.0
            if os.path.exists("data/balance_live.txt"):
                try:
                    with open("data/balance_live.txt", "r") as f: balance = float(f.read().strip())
                except Exception: pass

            risk_capital = balance * risk_pct
            size = min(risk_capital / (risk_per_unit + 2 * ep * COMMISSION_RATE), (balance * pending.get("max_leverage", 10.0)) / ep)

            trade = {
                "verdict": side, "entry": ep, "sl": sl, "tp": tp, "size": size,
                "risk_pct": risk_pct, "leverage": pending.get("max_leverage", 10.0),
                "ai_prob": pending.get("ai_prob", 50.0), "features": pending.get("features", {}),
                "atr_val": atr_val, "is_breakeven": False
            }
            save_trade(trade)
            opened.append(trade)
            os.remove(fpath)
            if notifier: notifier.send_alert(f"🚀 TRADE APERTO! {side} a {ep:.2f} (AI Conf: {trade['ai_prob']:.1f}%)", print_console=False)
        else:
            ttl -= 1
            if ttl <= 0: os.remove(fpath)
            else:
                pending["ttl"] = ttl
                with open(fpath, "w") as f: json.dump(pending, f)
    return opened


def save_pending_trigger(side: str, signal_high: float, signal_low: float,
                         atr_val: float, current_rr: float, score: int,
                         risk_pct: float, max_leverage: float, regime: str,
                         candle_ts: str, ai_prob: float = 50.0, features: dict = None):
    """Salva un nuovo trigger breakout pendente."""
    pending_dir = "data/pending"
    os.makedirs(pending_dir, exist_ok=True)
    trigger_price = signal_high if side == "BUY" else signal_low
    pending = {
        "side": side, "trigger_price": trigger_price, "signal_high": signal_high,
        "signal_low": signal_low, "atr_val": atr_val, "current_rr": current_rr,
        "score": score, "risk_pct": risk_pct, "max_leverage": max_leverage,
        "regime": regime, "candle_ts": candle_ts, "ttl": 1,
        "ai_prob": ai_prob, "features": features or {}
    }
    fname = f"pending_{int(time.time() * 1000)}.json"
    fpath = os.path.join(pending_dir, fname)
    with open(fpath, "w") as f: json.dump(pending, f, indent=2)
    return fpath