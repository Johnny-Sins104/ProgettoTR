"""
Multi-Trade Manager — Gestione non-bloccante di trade multipli simultanei.
Versione Ottimizzata (Clean-Data): Break-Even a 1.5x ATR con Caching In-Memory.
"""
import os
import json
import time
from datetime import datetime, timezone
from config import Config

TRADES_DIR = "data/trades"
COMMISSION_RATE = Config.COMMISSION_RATE

# Cache in memoria per azzerare I/O non necessario su SSD
_cached_trades = None
_cached_pending = None


def append_to_log_with_rotation(log_path_str: str, text: str, max_bytes: int = 10 * 1024 * 1024) -> None:
    try:
        if os.path.exists(log_path_str) and os.path.getsize(log_path_str) > max_bytes:
            rotated = log_path_str + ".1"
            if os.path.exists(rotated):
                os.remove(rotated)
            os.rename(log_path_str, rotated)
    except Exception:
        pass
    try:
        log_dir = os.path.dirname(log_path_str)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        with open(log_path_str, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _ensure_dir():
    os.makedirs(TRADES_DIR, exist_ok=True)


def get_open_trades() -> list[dict]:
    """Ritorna lista di tutti i trade aperti (dalla cache in memoria se disponibile)."""
    global _cached_trades
    if _cached_trades is not None:
        return list(_cached_trades)

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
    _cached_trades = list(trades)
    return list(_cached_trades)


def count_open_trades() -> int:
    return len(get_open_trades())


def can_open_new_trade() -> bool:
    return count_open_trades() < Config.MAX_CONCURRENT_TRADES


def save_trade(trade: dict) -> str:
    """Salva un nuovo trade su disco ed aggiorna la cache in memoria."""
    global _cached_trades
    _ensure_dir()
    trade_id = f"trade_{int(time.time() * 1000)}"
    trade["trade_id"] = trade_id
    trade["status"] = "ACTIVE"
    trade["opened_at"] = datetime.now(timezone.utc).isoformat()
    fpath = os.path.join(TRADES_DIR, f"{trade_id}.json")
    trade["_file"] = fpath

    # Salva su disco (Write-Through)
    with open(fpath, "w") as f:
        json.dump(trade, f, indent=2)

    # Aggiorna la cache in memoria
    if _cached_trades is None:
        get_open_trades()
    else:
        _cached_trades.append(dict(trade))

    return fpath


def close_trade(trade: dict, exit_price: float, reason: str) -> float:
    """Chiude un trade, aggiorna il saldo e rimuove la cache sia in memoria che su disco."""
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

    # Log con rotazione
    log_file = "data/bot_live.log"
    ts = datetime.now(timezone.utc).isoformat()
    log_line = (
        f"[{ts}] CLOSE_{reason} | {verdict} | Entry: {entry:.2f} | Exit: {exit_price:.2f} | "
        f"PnL: {net_pnl:+.2f} EUR | Balance: {new_balance:.2f} EUR | "
        f"TradeID: {trade.get('trade_id', '?')}\n"
    )
    append_to_log_with_rotation(log_file, log_line)

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

    # Rimuovi il file del trade su disco
    fpath = trade.get("_file", "")
    if fpath and os.path.exists(fpath):
        try:
            os.remove(fpath)
        except Exception:
            pass

    # Rimuovi dalla cache in memoria
    global _cached_trades
    if _cached_trades is not None:
        _cached_trades = [t for t in _cached_trades if t.get("trade_id") != trade.get("trade_id")]

    return net_pnl


def check_all_trades(current_price: float, notifier=None) -> list[dict]:
    """
    Controlla SL/TP di tutti i trade aperti in memoria.
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
            if verdict == "BUY" and current_price >= entry + (atr_val * 1.5):
                be_triggered = True
            elif verdict == "SELL" and current_price <= entry - (atr_val * 1.5):
                be_triggered = True
            
            if be_triggered:
                trade["sl"] = entry
                trade["is_breakeven"] = True
                sl = entry
                
                # Salva modifiche su file JSON (Write-Through)
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


def get_pending_triggers() -> list[dict]:
    """Recupera la lista dei trigger pendenti (con caching in memoria)."""
    global _cached_pending
    if _cached_pending is not None:
        return _cached_pending

    pending_dir = "data/pending"
    if not os.path.exists(pending_dir):
        os.makedirs(pending_dir, exist_ok=True)
        _cached_pending = []
        return _cached_pending

    pending_list = []
    for fname in os.listdir(pending_dir):
        if fname.endswith(".json"):
            fpath = os.path.join(pending_dir, fname)
            try:
                with open(fpath, "r") as f:
                    p = json.load(f)
                p["_file"] = fpath
                pending_list.append(p)
            except Exception:
                pass
    _cached_pending = pending_list
    return _cached_pending


def check_pending_triggers(current_price: float, hi: float, lo: float, notifier=None) -> list[dict]:
    """Controlla i trigger breakout pendenti interamente in memoria (Write-Through)."""
    global _cached_pending
    pending_list = get_pending_triggers()

    opened = []
    active_pending = []

    for pending in pending_list:
        fpath = pending.get("_file", "")
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
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
                continue

            balance = 100.0
            if os.path.exists("data/balance_live.txt"):
                try:
                    with open("data/balance_live.txt", "r") as f:
                        balance = float(f.read().strip())
                except Exception:
                    pass

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
            if fpath and os.path.exists(fpath):
                try:
                    os.remove(fpath)
                except Exception:
                    pass
            if notifier:
                notifier.send_alert(f"🚀 TRADE APERTO! {side} a {ep:.2f} (AI Conf: {trade['ai_prob']:.1f}%)", print_console=False)
        else:
            ttl -= 1
            if ttl <= 0:
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
            else:
                pending["ttl"] = ttl
                if fpath:
                    save_dict = {k: v for k, v in pending.items() if k != "_file"}
                    try:
                        with open(fpath, "w") as f:
                            json.dump(save_dict, f)
                    except Exception:
                        pass
                active_pending.append(pending)

    _cached_pending = active_pending
    return opened


def save_pending_trigger(side: str, signal_high: float, signal_low: float,
                          atr_val: float, current_rr: float, score: int,
                          risk_pct: float, max_leverage: float, regime: str,
                          candle_ts: str, ai_prob: float = 50.0, features: dict = None):
    """Salva un nuovo trigger breakout pendente sia su disco che in memoria."""
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
    pending["_file"] = fpath

    with open(fpath, "w") as f:
        json.dump(pending, f, indent=2)

    # Aggiorna la cache in memoria
    global _cached_pending
    if _cached_pending is None:
        get_pending_triggers()
    else:
        _cached_pending.append(pending)

    return fpath