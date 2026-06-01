import asyncio
import sys
import os
import json
import re
import time
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        import os
        os.system('color')  # Abilita i colori ANSI nativi in CMD e PowerShell su Windows
    except Exception:
        pass

# Costanti di colore ANSI per un output premium
RESET   = "\033[0m"
BOLD    = "\033[1m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"


import urllib.request
import signal
import atexit
import pandas as pd
import pandas_ta as ta

from config import Config
from core.client import ExchangeClient
from core.analyzer import TechnicalAnalyzer
from core.engine import DecisionEngine
from core.risk import RiskManager
from core.database import DatabaseManager
from core.notifier import Notifier
from core.commission_model import round_trip_commission

LIMIT     = 500
SLEEP_SEC = 60
COMMISSION_RATE = Config.COMMISSION_RATE  # Centralizzato in Config (Futures: 0.02% per side)

db       = DatabaseManager()
notifier = Notifier(
    telegram_token=Config.TELEGRAM_TOKEN or None,
    telegram_chat_id=Config.TELEGRAM_CHAT_ID or None,
)

_closed_on_shutdown = False


def append_to_log_with_rotation(log_file: str, line: str, *, max_bytes: int = 2_000_000, backup_count: int = 5) -> None:
    """Append a line to a log file while keeping bounded rotated backups.

    This protects long-running live sessions from unbounded data/bot_live.log
    growth.  Rotation is best-effort and fail-closed to the caller: logging
    failures never affect trading flow.
    """
    try:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        if os.path.exists(log_file) and os.path.getsize(log_file) >= max_bytes:
            for idx in range(max(backup_count, 1) - 1, 0, -1):
                src = f"{log_file}.{idx}"
                dst = f"{log_file}.{idx + 1}"
                if os.path.exists(src):
                    if idx + 1 > backup_count:
                        os.remove(src)
                    else:
                        os.replace(src, dst)
            os.replace(log_file, f"{log_file}.1")
        with open(log_file, "a", encoding="utf-8") as lf:
            lf.write(line)
    except Exception:
        pass

def get_btc_price_sync() -> float | None:
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            return float(data["price"])
    except Exception:
        return None

def force_close_active_trade(reason="SHUTDOWN"):
    global _closed_on_shutdown
    if _closed_on_shutdown:
        return
    
    active_trade_file = "data/active_trade.json"
    if not os.path.exists(active_trade_file):
        return
        
    try:
        with open(active_trade_file, "r") as f:
            active_trade = json.load(f)
        if active_trade.get("status") != "ACTIVE":
            return
    except Exception:
        return

    _closed_on_shutdown = True
    print(f"\n{RED}{BOLD}[SHUTDOWN] Rilevato segnale di chiusura del terminale o interruzione ({reason}).{RESET}")
    print(f"{YELLOW}Chiusura forzata della posizione attiva in corso...{RESET}")

    verdict = active_trade["verdict"]
    entry = active_trade["entry"]
    size = active_trade["size"]
    leverage = active_trade.get("leverage", 10.0)
    tp1_hit = active_trade.get("tp1_hit", False)
    pnl_tp1_net = active_trade.get("pnl_tp1_net", 0.0)
    
    current_price = get_btc_price_sync()
    if current_price is None:
        current_price = entry  # fallback
        print(f"{YELLOW}[SHUTDOWN] Impossibile recuperare il prezzo live, uso il prezzo di ingresso come fallback.{RESET}")
        
    if not tp1_hit:
        if verdict == "BUY":
            pnl = size * (current_price - entry)
        else:
            pnl = size * (entry - current_price)
        pnl_total = pnl
    else:
        # Solo la seconda metà viene chiusa a mercato
        if verdict == "BUY":
            pnl_2 = (size / 2) * (current_price - entry)
        else:
            pnl_2 = (size / 2) * (entry - current_price)
        pnl_total = pnl_tp1_net + pnl_2
        
    margin = (size * entry) / leverage
    margin_for_roe = margin / 2 if tp1_hit else margin
    roe = (pnl_total / margin_for_roe) * 100 if margin_for_roe > 0 else 0.0
    
    balance_file = "data/balance_live.txt"
    balance = 100.0
    if os.path.exists(balance_file):
        try:
            with open(balance_file, "r") as f:
                balance = float(f.read().strip())
        except Exception:
            pass
            
    # Se tp1_hit, la prima metà è già nel saldo! Aggiungiamo solo pnl_2 (pnl_total - pnl_tp1_net)
    added_pnl = pnl_total - pnl_tp1_net if tp1_hit else pnl_total
    new_balance = balance + added_pnl
    try:
        with open(balance_file, "w") as f:
            f.write(f"{new_balance:.2f}")
    except Exception:
        pass
        
    try:
        os.remove(active_trade_file)
    except Exception:
        pass
        
    log_file = "data/bot_live.log"
    close_ts = datetime.now(timezone.utc).isoformat()
    log_line = (
        f"[{close_ts}] CLOSE_{reason} | PnL: {pnl_total:.2f} EUR | ROE%: {roe:.2f}% | "
        f"NewBalance: {new_balance:.2f} EUR | ExitPrice: {current_price:.2f}\n"
    )
    append_to_log_with_rotation(log_file, log_line)

    try:
        if Config.TELEGRAM_TOKEN and Config.TELEGRAM_CHAT_ID:
            msg = (
                f"🛑 Posizione Chiusa per Chiusura Terminale ({reason})!\n"
                f"PnL: {'+' if pnl_total >= 0 else ''}{pnl_total:.2f} EUR ({roe:.2f}%)\n"
                f"Nuovo Saldo: {new_balance:.2f} EUR"
            )
            tg_url = f"https://api.telegram.org/bot{Config.TELEGRAM_TOKEN}/sendMessage"
            payload = json.dumps({"chat_id": Config.TELEGRAM_CHAT_ID, "text": msg}).encode('utf-8')
            req = urllib.request.Request(
                tg_url, 
                data=payload, 
                headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=2) as response:
                pass
    except Exception:
        pass

    print(f"{GREEN}[SHUTDOWN] Posizione chiusa a mercato a {current_price:.2f} USDT.{RESET}")
    print(f"{GREEN}[SHUTDOWN] Nuovo saldo salvato: {new_balance:.2f} EUR. Bot arrestato.{RESET}\n")

def shutdown_handler(signum, frame):
    reason = "TERMINAL_CLOSE"
    if signum == signal.SIGINT:
        reason = "CTRL_C"
    elif hasattr(signal, "SIGBREAK") and signum == signal.SIGBREAK:
        reason = "TERMINAL_CLOSE"
    elif signum == signal.SIGTERM:
        reason = "SIGTERM"
        
    force_close_active_trade(reason)
    sys.exit(0)

# Registra i gestori di segnale per intercettare lo spegnimento
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)
if hasattr(signal, "SIGBREAK"):
    signal.signal(signal.SIGBREAK, shutdown_handler)

# Registra atexit per uscite regolari o arresti improvvisi
atexit.register(lambda: force_close_active_trade("NORMAL_EXIT"))


def generate_ascii_chart(sl: float, entry: float, tp1: float, tp2: float, current: float, verdict: str, tp1_hit: bool) -> str:
    width = 40
    if tp2 == sl:
        return ""
    
    left_bound = min(sl, current)
    right_bound = max(tp2, current)
    
    denom = right_bound - left_bound
    if denom == 0:
        return ""
        
    entry_pos = int(((entry - left_bound) / denom) * width)
    entry_pos = max(0, min(width, entry_pos))
    
    tp1_pos = int(((tp1 - left_bound) / denom) * width)
    tp1_pos = max(0, min(width, tp1_pos))
    
    curr_pos = int(((current - left_bound) / denom) * width)
    curr_pos = max(0, min(width, curr_pos))
    
    bar_chars = []
    for i in range(width + 1):
        if i == curr_pos:
            if verdict == "BUY":
                color = GREEN if current >= entry else RED
            else:
                color = GREEN if current <= entry else RED
            bar_chars.append(f"{BOLD}{color}●{RESET}{CYAN}")
        elif i == entry_pos:
            bar_chars.append("┼")
        elif i == tp1_pos:
            if tp1_hit:
                bar_chars.append(f"{GREEN}✓{RESET}{CYAN}")
            else:
                bar_chars.append("1")
        else:
            bar_chars.append("─")
            
    bar_str = "".join(bar_chars)
    tp1_status = f"{GREEN}TP1✓{RESET}" if tp1_hit else "TP1"
    return f"{RED}SL{RESET} {CYAN}{bar_str}{RESET} {GREEN}{tp1_status} {GREEN}TP2{RESET}"


async def monitor_active_trade(active_trade: dict) -> None:
    verdict = active_trade["verdict"]
    entry = active_trade["entry"]
    sl = active_trade["sl"]
    initial_sl = active_trade.get("initial_sl", sl)
    be_triggered = active_trade.get("be_triggered", False)
    tp = active_trade["tp"]
    size = active_trade["size"]
    risk_pct = active_trade.get("risk_pct", 0.15)
    leverage = active_trade.get("leverage", 10.0)
    ts = active_trade["timestamp"]
    score = active_trade.get("score", 0)
    regime = active_trade.get("regime", "UNKNOWN")
    threshold = active_trade.get("threshold", 0)
    
    # Scale-out parameters
    tp1 = active_trade.get("tp1", entry + (entry - sl) * Config.TP1_RR if verdict == "BUY" else entry - (sl - entry) * Config.TP1_RR)
    tp2 = active_trade.get("tp2", tp)
    tp1_hit = active_trade.get("tp1_hit", False)
    pnl_tp1_net = active_trade.get("pnl_tp1_net", 0.0)
    
    margin = (size * entry) / leverage
    
    import ccxt.async_support as ccxt_async
    exchange = getattr(ccxt_async, Config.EXCHANGE_ID)({
        "apiKey": Config.API_KEY or None,
        "secret": Config.API_SECRET or None,
    })
    exchange.verbose = False
    
    from core.notifier import telegram_close_event
    telegram_close_event.clear()
    tg_msg_id = None
    last_tg_update = 0
    
    try:
        while True:
            try:
                ticker = await exchange.fetch_ticker(Config.SYMBOL)
                current_price = float(ticker["last"])
            except Exception:
                await asyncio.sleep(1)
                continue
            
            # 1. SCALE-OUT TARGET EVALUATION
            if not tp1_hit:
                hit_tp1 = (verdict == "BUY" and current_price >= tp1) or (verdict == "SELL" and current_price <= tp1)
                hit_sl = (verdict == "BUY" and current_price <= sl) or (verdict == "SELL" and current_price >= sl)
                
                if hit_tp1:
                    # Prima metà chiusa a TP1!
                    tp1_hit = True
                    active_trade["tp1_hit"] = True
                    
                    pnl_1 = (size / 2) * (tp1 - entry) if verdict == "BUY" else (size / 2) * (entry - tp1)
                    comm_1 = round_trip_commission(size / 2, entry, tp1, COMMISSION_RATE)
                    net_pnl_1 = pnl_1 - comm_1
                    
                    balance_file = "data/balance_live.txt"
                    balance = 100.0
                    if os.path.exists(balance_file):
                        try:
                            with open(balance_file, "r") as f:
                                balance = float(f.read().strip())
                        except Exception:
                            pass
                    
                    new_balance = balance + net_pnl_1
                    try:
                        with open(balance_file, "w") as f:
                            f.write(f"{new_balance:.2f}")
                    except Exception:
                        pass
                        
                    active_trade["pnl_tp1_net"] = net_pnl_1
                    pnl_tp1_net = net_pnl_1
                    
                    # Trailing Stop a Breakeven (comprensivo di commissioni) se configurato
                    if Config.USE_BREAKEVEN_ON_TP1:
                        new_sl = entry + (2 * entry * COMMISSION_RATE) if verdict == "BUY" else entry - (2 * entry * COMMISSION_RATE)
                        sl = new_sl
                        active_trade["sl"] = sl
                        active_trade["be_triggered"] = True
                        be_triggered = True
                    
                    try:
                        with open("data/active_trade.json", "w") as f:
                            json.dump(active_trade, f)
                    except Exception as e:
                        print(f"[WARN] Impossibile aggiornare active_trade.json per TP1: {e}")
                        
                    msg = (
                        f"🎉 TAKE PROFIT 1 (TP1) TOCCATO per {verdict} {Config.SYMBOL}!\n"
                        f"Prezzo TP1: {tp1:.2f} USDT | Realizzato: +{net_pnl_1:.2f} EUR (prima metà)\n"
                        f"Nuovo Saldo: {new_balance:.2f} EUR\n"
                        + (f"🛡️ Stop Loss della seconda metà a Breakeven: {sl:.2f} USDT" if Config.USE_BREAKEVEN_ON_TP1 else "Original SL mantenuto.")
                    )
                    print(f"\n{BOLD}{GREEN}{msg}{RESET}\n")
                    notifier.send_alert(msg, print_console=False)
                    
                    # Log
                    log_file = "data/bot_live.log"
                    close_ts = datetime.now(timezone.utc).isoformat()
                    log_line = (
                        f"[{close_ts}] TP1_HIT | PnL_Part: {net_pnl_1:.2f} EUR | "
                        f"Balance: {new_balance:.2f} EUR | SL: {sl:.2f}\n"
                    )
                    append_to_log_with_rotation(log_file, log_line)
                        
                elif hit_sl:
                    # SL colpito prima di TP1: perdita totale intera size
                    pnl = size * (sl - entry) if verdict == "BUY" else size * (entry - sl)
                    commission = round_trip_commission(size, entry, sl, COMMISSION_RATE)
                    net_pnl = pnl - commission
                    
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
                        
                    active_trade_file = "data/active_trade.json"
                    if os.path.exists(active_trade_file):
                        try:
                            os.remove(active_trade_file)
                        except Exception:
                            pass
                            
                    log_file = "data/bot_live.log"
                    close_ts = datetime.now(timezone.utc).isoformat()
                    log_line = (
                        f"[{close_ts}] CLOSE_SL | PnL: {net_pnl:.2f} EUR | ROE%: -100.00% | "
                        f"NewBalance: {new_balance:.2f} EUR | ExitPrice: {current_price:.2f}\n"
                    )
                    append_to_log_with_rotation(log_file, log_line)
                        
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print(f"\n{RED}===================================================={RESET}")
                    print(f"  {BOLD}{RED}🚨 STOP LOSS TOCCATO! POSIZIONE CHIUSA IN PERDITA{RESET}")
                    print(f"  Perdita Realizzata  : {BOLD}{RED}{net_pnl:.2f} EUR{RESET}")
                    print(f"  Nuovo Saldo Disponib: {BOLD}{YELLOW}{new_balance:.2f} EUR{RESET}")
                    print(f"{RED}===================================================={RESET}\n")
                    
                    notifier.send_alert(
                        f"🚨 Stop Loss Toccato per {verdict} {Config.SYMBOL}!\n"
                        f"PnL: {net_pnl:.2f} EUR\n"
                        f"Nuovo Saldo: {new_balance:.2f} EUR",
                        print_console=False
                    )
                    await asyncio.sleep(5)
                    break
            
            else:
                # TP1 colpito, controlla la seconda metà per TP2 o SL
                hit_tp2 = (verdict == "BUY" and current_price >= tp2) or (verdict == "SELL" and current_price <= tp2)
                hit_sl2 = (verdict == "BUY" and current_price <= sl) or (verdict == "SELL" and current_price >= sl)
                
                if hit_tp2 or hit_sl2:
                    if hit_tp2 and not hit_sl2:
                        exit_price_2 = tp2
                        close_verdict = "TP_FULL"
                    else:
                        exit_price_2 = sl
                        close_verdict = "WIN_PARTIAL"
                        
                    pnl_2 = (size / 2) * (exit_price_2 - entry) if verdict == "BUY" else (size / 2) * (entry - exit_price_2)
                    comm_2 = round_trip_commission(size / 2, entry, exit_price_2, COMMISSION_RATE)
                    net_pnl_2 = pnl_2 - comm_2
                    
                    balance_file = "data/balance_live.txt"
                    balance = 100.0
                    if os.path.exists(balance_file):
                        try:
                            with open(balance_file, "r") as f:
                                balance = float(f.read().strip())
                        except Exception:
                            pass
                            
                    new_balance = balance + net_pnl_2
                    try:
                        with open(balance_file, "w") as f:
                            f.write(f"{new_balance:.2f}")
                    except Exception:
                        pass
                        
                    net_pnl_total = pnl_tp1_net + net_pnl_2
                    
                    active_trade_file = "data/active_trade.json"
                    if os.path.exists(active_trade_file):
                        try:
                            os.remove(active_trade_file)
                        except Exception:
                            pass
                            
                    log_file = "data/bot_live.log"
                    close_ts = datetime.now(timezone.utc).isoformat()
                    log_line = (
                        f"[{close_ts}] CLOSE_{close_verdict} | PnL_Total: {net_pnl_total:.2f} EUR | "
                        f"NewBalance: {new_balance:.2f} EUR | ExitPrice: {exit_price_2:.2f}\n"
                    )
                    append_to_log_with_rotation(log_file, log_line)
                        
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print(f"\n{CYAN}===================================================={RESET}")
                    if close_verdict == "TP_FULL":
                        print(f"  {BOLD}{GREEN}🎉 TAKE PROFIT 2 (TP2) TOCCATO! POSIZIONE COMPLETAMENTE CHIUSA IN ATTIVO{RESET}")
                        print(f"  Profitto Totale Real: {BOLD}{GREEN}+{net_pnl_total:.2f} EUR{RESET}")
                    else:
                        print(f"  {BOLD}{YELLOW}🛡️ SECONDA META' STOPPATA (SL/BE). POSIZIONE CHIUSA PARZIALMENTE IN ATTIVO{RESET}")
                        print(f"  Profitto Netto Totale: {BOLD}{GREEN if net_pnl_total >= 0 else RED}{net_pnl_total:+.2f} EUR{RESET}")
                    print(f"  Nuovo Saldo Disponib: {BOLD}{YELLOW}{new_balance:.2f} EUR{RESET}")
                    print(f"{CYAN}===================================================={RESET}\n")
                    
                    notifier.send_alert(
                        f"🔒 Posizione Chiusa in {close_verdict}!\n"
                        f"PnL Totale: {net_pnl_total:+.2f} EUR\n"
                        f"Nuovo Saldo: {new_balance:.2f} EUR",
                        print_console=False
                    )
                    await asyncio.sleep(5)
                    break

            # 2. PnL Non Realizzato ed Equity per Display
            if not tp1_hit:
                pnl = size * (current_price - entry) if verdict == "BUY" else size * (entry - current_price)
                roe = (pnl / margin) * 100 if margin > 0 else 0.0
                active_size = size
                active_margin = margin
            else:
                pnl = (size / 2) * (current_price - entry) if verdict == "BUY" else (size / 2) * (entry - current_price)
                roe = (pnl / (margin / 2)) * 100 if margin > 0 else 0.0
                active_size = size / 2
                active_margin = margin / 2
                
            balance = 100.0
            balance_file = "data/balance_live.txt"
            if os.path.exists(balance_file):
                try:
                    with open(balance_file, "r") as f:
                        balance = float(f.read().strip())
                except Exception:
                    pass
            
            floating_balance = balance + pnl
            
            # Render Dashboard
            os.system('cls' if os.name == 'nt' else 'clear')
            v_color = GREEN if verdict == "BUY" else RED
            pnl_color = GREEN if pnl >= 0 else RED
            pnl_sign = "+" if pnl >= 0 else ""
            
            sep = CYAN + "=" * 52 + RESET
            print(sep)
            print(f"  {BOLD}{WHITE}📈 MONITOR LIVE TICK-BY-TICK — POSIZIONE ATTIVA{RESET}")
            print(sep)
            print(f"  Direzione Trade     : {v_color}{verdict}{RESET}")
            if score != 0:
                print(f"  Motivazione         : {BOLD}{WHITE}Score {score}{RESET} (Soglia {threshold}, {regime})")
            print(f"  Prezzo Ingresso     : {BOLD}{WHITE}{entry:.2f} USDT{RESET}")
            print(f"  Prezzo Attuale      : {BOLD}{YELLOW}{current_price:.2f} USDT{RESET}")
            print(f"  Dimensione Attiva   : {BOLD}{WHITE}{active_size:.6f} BTC{RESET} {"(Seconda Metà)" if tp1_hit else "(Intera size)"}")
            print(f"  Margine Attivo      : {BOLD}{YELLOW}{active_margin:.2f} EUR{RESET} (Leva {leverage:.1f}x)")
            print(sep)
            print(f"  Take Profit 1 (TP1) : {BOLD}{WHITE}{tp1:.2f} USDT{RESET} | {GREEN if tp1_hit else YELLOW}{'✓ HIT' if tp1_hit else '⏳ PENDING'}{RESET}")
            print(f"  Take Profit 2 (TP2) : {BOLD}{WHITE}{tp2:.2f} USDT{RESET} | {YELLOW}⏳ PENDING{RESET}")
            if tp1_hit:
                print(f"  PnL TP1 Realizzato  : {BOLD}{GREEN}+{pnl_tp1_net:.2f} EUR{RESET}")
            print(sep)
            print(f"  PnL Non Realizzato  : {BOLD}{pnl_color}{pnl_sign}{pnl:.2f} EUR{RESET} ({pnl_color}{pnl_sign}{roe:.2f}%{RESET})")
            print(f"  Equity (Saldo+PnL)  : {BOLD}{YELLOW}{floating_balance:.2f} EUR{RESET}")
            print(sep)
            
            bar_str = generate_ascii_chart(sl, entry, tp1, tp2, current_price, verdict, tp1_hit)
            print(f"  Grafico Posizione   : {bar_str}")
            print(sep)
            print(f"  {BOLD}{MAGENTA}🕹️ CONTROLLI MANUALI:{RESET}")
            print(f"  {BOLD}{RED}[C]{RESET} : Chiudi subito l'azione a mercato (Take Profit / Stop Loss manuale)")
            print(f"  {BOLD}{RED}[CTRL+C]{RESET} : Ferma tutto il bot e spegni")
            print(sep)
            
            # Telegram format
            clean_bar = re.sub(r'\x1b\[[0-9;]*m', '', bar_str)
            tg_text = (
                f"📈 MONITOR LIVE TICK-BY-TICK\n"
                f"{'='*30}\n"
                f"Direzione: {verdict}\n"
            )
            if score != 0:
                tg_text += f"Motivo   : Score {score} (>{threshold} {regime})\n"
            tg_text += (
                f"Ingresso : {entry:.2f} USDT\n"
                f"Attuale  : {current_price:.2f} USDT\n"
                f"Size     : {active_size:.6f} BTC\n"
                f"Margine  : {active_margin:.2f} EUR ({leverage:.1f}x)\n"
                f"{'='*30}\n"
                f"TP1      : {tp1:.2f} USDT {'✅ HIT!' if tp1_hit else '⏳ PENDING'}\n"
                f"TP2      : {tp2:.2f} USDT ⏳ PENDING\n"
            )
            if tp1_hit:
                tg_text += f"PnL TP1  : +{pnl_tp1_net:.2f} EUR\n"
            tg_text += (
                f"{'='*30}\n"
                f"PnL Att. : {pnl_sign}{pnl:.2f} EUR ({pnl_sign}{roe:.2f}%)\n"
                f"Equity   : {floating_balance:.2f} EUR\n"
                f"{'='*30}\n"
                f"{clean_bar}\n"
            )
            
            current_time = time.time()
            if current_time - last_tg_update >= 3.0:
                if tg_msg_id is None:
                    tg_msg_id = await notifier.send_interactive_monitor(tg_text)
                else:
                    asyncio.create_task(notifier.update_interactive_monitor(tg_msg_id, tg_text))
                last_tg_update = current_time
            
            # Manual check
            manual_close_terminal = False
            if sys.platform == "win32":
                import msvcrt
                while msvcrt.kbhit():
                    try:
                        ch = msvcrt.getch()
                        key = ch.decode('utf-8', errors='ignore').lower()
                        if key == 'c':
                            manual_close_terminal = True
                    except Exception:
                        pass
            
            manual_close = telegram_close_event.is_set() or manual_close_terminal
            
            if manual_close:
                if not tp1_hit:
                    pnl_total = size * (current_price - entry) if verdict == "BUY" else size * (entry - current_price)
                    comm = round_trip_commission(size, entry, current_price, COMMISSION_RATE)
                    net_pnl_total = pnl_total - comm
                    pnl_to_add = net_pnl_total
                else:
                    pnl_2 = (size / 2) * (current_price - entry) if verdict == "BUY" else (size / 2) * (entry - current_price)
                    comm_2 = round_trip_commission(size / 2, entry, current_price, COMMISSION_RATE)
                    net_pnl_2 = pnl_2 - comm_2
                    net_pnl_total = pnl_tp1_net + net_pnl_2
                    pnl_to_add = net_pnl_2
                
                balance_file = "data/balance_live.txt"
                balance = 100.0
                if os.path.exists(balance_file):
                    try:
                        with open(balance_file, "r") as f:
                            balance = float(f.read().strip())
                    except Exception:
                        pass
                        
                new_balance = balance + pnl_to_add
                try:
                    with open(balance_file, "w") as f:
                        f.write(f"{new_balance:.2f}")
                except Exception:
                    pass
                
                active_trade_file = "data/active_trade.json"
                if os.path.exists(active_trade_file):
                    try:
                        os.remove(active_trade_file)
                    except Exception:
                        pass
                
                close_verdict = "MANUAL_TERMINAL" if manual_close_terminal else "MANUAL_TELEGRAM"
                
                log_file = "data/bot_live.log"
                close_ts = datetime.now(timezone.utc).isoformat()
                log_line = (
                    f"[{close_ts}] CLOSE_{close_verdict} | PnL_Total: {net_pnl_total:.2f} EUR | "
                    f"NewBalance: {new_balance:.2f} EUR | ExitPrice: {current_price:.2f}\n"
                )
                append_to_log_with_rotation(log_file, log_line)
                
                if tg_msg_id:
                    final_text = tg_text + f"\n🛑 POSIZIONE CHIUSA: {close_verdict}"
                    asyncio.create_task(notifier.update_interactive_monitor(tg_msg_id, final_text, show_button=False))
                
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"\n{CYAN}===================================================={RESET}")
                print(f"  {BOLD}{YELLOW}🛑 POSIZIONE CHIUSA MANUALMENTE DA TERMINALE (Tasto 'C'){RESET}" if manual_close_terminal else f"  {BOLD}{YELLOW}🛑 POSIZIONE CHIUSA MANUALMENTE DA TELEGRAM{RESET}")
                print(f"  PnL Totale Realizzato: {BOLD}{GREEN if net_pnl_total >= 0 else RED}{net_pnl_total:+.2f} EUR{RESET}")
                print(f"  Nuovo Saldo Disponib: {BOLD}{YELLOW}{new_balance:.2f} EUR{RESET}")
                print(f"{CYAN}===================================================={RESET}\n")
                
                notifier.send_alert(
                    f"🔒 Posizione Chiusa manualmente in {close_verdict}!\n"
                    f"PnL Totale: {net_pnl_total:+.2f} EUR\n"
                    f"Nuovo Saldo: {new_balance:.2f} EUR",
                    print_console=False
                )
                
                await asyncio.sleep(5)
                break
                
            await asyncio.sleep(1)
            
    finally:
        await exchange.close()


async def monitor_pending_trigger(pending_trigger: dict) -> None:
    side = pending_trigger["side"]
    sh = pending_trigger["signal_high"]
    sl_level = pending_trigger["signal_low"]
    candle_ts = pending_trigger["candle_ts"]
    atr_val = pending_trigger["atr_val"]
    current_rr = pending_trigger["current_rr"]
    score = pending_trigger["score"]
    confluence_comb = pending_trigger["confluence_comb"]
    risk_pct = pending_trigger["risk_pct"]
    max_leverage = pending_trigger["max_leverage"]
    regime = pending_trigger["regime"]
    logs = pending_trigger.get("logs", [])
    
    import ccxt.async_support as ccxt_async
    exchange = getattr(ccxt_async, Config.EXCHANGE_ID)({
        "apiKey": Config.API_KEY or None,
        "secret": Config.API_SECRET or None,
    })
    exchange.verbose = False
    
    pending_trigger_file = "data/pending_trigger.json"
    active_trade_file = "data/active_trade.json"
    
    print(f"\n{CYAN}[BREAKOUT] Avvio monitoraggio breakout per segnale {side}...{RESET}")
    print(f"  Livello di attivazione: {BOLD}{YELLOW}{sh:.2f}{RESET} (BUY) / {BOLD}{YELLOW}{sl_level:.2f}{RESET} (SELL)")
    
    try:
        while True:
            # 1. Controlla scadenza basandosi sulle candele chiuse
            try:
                client = ExchangeClient(
                    exchange_id=Config.EXCHANGE_ID,
                    symbol=Config.SYMBOL,
                    timeframe=Config.TIMEFRAME,
                    limit=5,
                    api_key=Config.API_KEY or None,
                    api_secret=Config.API_SECRET or None,
                )
                df = await client.fetch_async()
                if not df.empty:
                    sig_dt = pd.to_datetime(candle_ts)
                    elapsed_candles = len(df[df.index > sig_dt])
                    if elapsed_candles >= 2:
                        print(f"\n{RED}[BREAKOUT] Trigger breakout scaduto (sono passate {elapsed_candles} candele senza breakout).{RESET}")
                        if os.path.exists(pending_trigger_file):
                            try:
                                os.remove(pending_trigger_file)
                            except Exception:
                                pass
                        notifier.send_alert(
                            f"⏰ Breakout Trigger scaduto per {side} {Config.SYMBOL}.\nNessun breakout entro 2 candele.", 
                            print_console=False
                        )
                        break
            except Exception as e:
                print(f"[WARN] Impossibile verificare scadenza trigger: {e}")

            # 2. Recupera prezzo live ticker
            try:
                ticker = await exchange.fetch_ticker(Config.SYMBOL)
                current_price = float(ticker["last"])
            except Exception:
                await asyncio.sleep(1)
                continue

            # Visualizzazione a schermo
            os.system('cls' if os.name == 'nt' else 'clear')
            sep = CYAN + "=" * 52 + RESET
            print(sep)
            print(f"  {BOLD}{WHITE}⏳ ATTESA BREAKOUT CONFERMA (2 CANDELE MAX){RESET}")
            print(sep)
            print(f"  Direzione Segnale   : {GREEN if side == 'BUY' else RED}{side}{RESET}")
            print(f"  Candela Segnale     : {candle_ts}")
            print(f"  Prezzo Attuale      : {BOLD}{YELLOW}{current_price:.2f} USDT{RESET}")
            if side == "BUY":
                print(f"  Trigger Breakout High: {BOLD}{WHITE}{sh:.2f} USDT{RESET}")
                print(f"  Distanza al breakout: {BOLD}{CYAN}{sh - current_price:.2f} USDT{RESET}")
            else:
                print(f"  Trigger Breakout Low : {BOLD}{WHITE}{sl_level:.2f} USDT{RESET}")
                print(f"  Distanza al breakout: {BOLD}{CYAN}{current_price - sl_level:.2f} USDT{RESET}")
            print(sep)

            # Check trigger condition
            triggered = False
            if side == "BUY" and current_price >= sh:
                triggered = True
            elif side == "SELL" and current_price <= sl_level:
                triggered = True

            if triggered:
                # Esegui!
                entry = current_price
                
                # Calcola stop loss e take profit
                targets = RiskManager().calculate_targets(side, entry, atr_val, rr_ratio=current_rr)
                
                # Legge saldo
                balance_file = "data/balance_live.txt"
                balance = 100.0
                if os.path.exists(balance_file):
                    try:
                        with open(balance_file, "r") as f:
                            balance = float(f.read().strip())
                    except Exception:
                        pass
                
                risk_per_unit = abs(entry - targets["sl"])
                risk_capital = balance * risk_pct
                if Config.USE_COMMISSION_AWARE_SIZING:
                    position_size = risk_capital / (risk_per_unit + (2 * entry * COMMISSION_RATE)) if risk_per_unit > 0 else 0.0
                else:
                    position_size = risk_capital / risk_per_unit if risk_per_unit > 0 else 0.0
                
                max_size = (balance * max_leverage) / entry
                position_size = min(position_size, max_size)

                # Salva posizione attiva
                ts_now = datetime.now(timezone.utc).isoformat()
                active_trade = {
                    "status": "ACTIVE",
                    "verdict": side,
                    "entry": entry,
                    "sl": targets["sl"],
                    "initial_sl": targets["sl"],
                    "be_triggered": False,
                    "tp": targets["tp"],
                    "size": position_size,
                    "risk_pct": risk_pct,
                    "leverage": max_leverage,
                    "timestamp": ts_now,
                    "score": score,
                    "regime": regime,
                    "threshold": Config.TRENDING_THRESHOLD if regime == "TRENDING" else Config.RANGING_THRESHOLD
                }

                try:
                    with open(active_trade_file, "w") as f:
                        json.dump(active_trade, f)
                except Exception:
                    pass

                # Rimuove pending trigger
                if os.path.exists(pending_trigger_file):
                    try:
                        os.remove(pending_trigger_file)
                    except Exception:
                        pass

                # Salva nel database
                db.save_trade({
                    "timestamp": ts_now,
                    "symbol":    Config.SYMBOL,
                    "verdict":   side,
                    "score":     score,
                    "entry":     entry,
                    "sl":        targets["sl"],
                    "tp":        targets["tp"],
                    "logs":      logs,
                })

                # Stampa box
                box_color = GREEN if side == "BUY" else RED
                entry_str = f"Entry: {entry:.2f}"
                sl_str    = f"SL: {targets['sl']:.2f}"
                tp_str    = f"TP: {targets['tp']:.2f}"
                bal_str   = f"Saldo Simulato: {balance:.2f} EUR"

                print(f"\n{box_color}╔════════════════════════════════════════════════════╗")
                print(f"║  🎉 BREAKOUT ATTIVATO! INGRESSO A MERCATO          ║")
                print(f"║  🚨 {side:<4} {Config.SYMBOL:<38} ║")
                print(f"║  {entry_str:<49} ║")
                print(f"║  {sl_str:<49} ║")
                print(f"║  {tp_str:<49} ║")
                print(f"║  {bal_str:<49} ║")
                print(f"╚════════════════════════════════════════════════════╝{RESET}")

                msg = (
                    f"🎉 Breakout Confermato per {side} {Config.SYMBOL}!\n"
                    f"Entry: {entry:.2f} | SL: {targets['sl']:.2f} | TP: {targets['tp']:.2f}\n"
                    f"Size: {position_size:.6f} BTC | R:R: {current_rr:.2f}x"
                )
                notifier.send_alert(msg, print_console=False)
                
                # --- Black Box Logging ---
                log_file = "data/bot_live.log"
                log_line = (
                    f"[{ts_now}] TRIGGER_BREAKOUT_{side} | Score: {score} | Price: {entry:.2f} | "
                    f"SL: {targets['sl']:.2f} | TP: {targets['tp']:.2f} | "
                    f"ATR: {atr_val:.2f} | Size: {position_size:.6f} | "
                    f"Balance: {balance:.2f} EUR | RiskClass: {Config.RISK_CLASS} | "
                    f"Confirmations: {', '.join(logs)}\n"
                )
                append_to_log_with_rotation(log_file, log_line)

                await asyncio.sleep(2)
                break

            await asyncio.sleep(2)

    finally:
        await exchange.close()


async def run_bot() -> None:
    # --- Fetch ---
    client = ExchangeClient(
        exchange_id=Config.EXCHANGE_ID,
        symbol=Config.SYMBOL,
        timeframe=Config.TIMEFRAME,
        limit=LIMIT,
        api_key=Config.API_KEY or None,
        api_secret=Config.API_SECRET or None,
    )
    df = await client.fetch_async()
    if df is None or df.empty:
        print("[WARN] fetch_async ha restituito dati vuoti — ciclo saltato.")
        return

    # --- Indicators ---
    df = TechnicalAnalyzer().add_indicators(df, is_live=True)

    # --- Decision ---
    engine = DecisionEngine()  # Usa automaticamente le soglie evolute TRENDING_THRESHOLD e RANGING_THRESHOLD
    res = engine.evaluate(df)
    verdict, score, conf, entry_type = res[0], res[1], res[2], res[3]
    confluence_verdict = res[4] if len(res) > 4 else "GREEN"
    confluence_comb = res[5] if len(res) > 5 else "None"
    logs = [f"{k}: CONFIRMED" for k, v in conf.items() if v]

    last       = df.iloc[-1]
    entry      = float(last["Close"])
    atr_val    = float(last["atr"]) if float(last["atr"]) != 0 else entry * 0.01
    ts         = datetime.now(timezone.utc).isoformat()
    candle_ts  = str(last.name)

    # Configura il profilo di rischio di base
    risk_class = Config.RISK_CLASS.upper()
    active_risk_label = risk_class
    if risk_class == "LOW":
        risk_pct, max_leverage = 0.03, 4.0
    elif risk_class == "MEDIUM":
        risk_pct, max_leverage = 0.07, 8.0
    elif risk_class == "HIGH":
        risk_pct, max_leverage = 0.15, 10.0
    else:  # DYNAMIC
        risk_pct, max_leverage = 0.03, 4.0
        active_risk_label = "DYNAMIC"

    # Legge o crea il saldo simulato live (default: 100.0 €)
    import os
    balance_file = "data/balance_live.txt"
    balance = 100.0
    if os.path.exists(balance_file):
        try:
            with open(balance_file, "r") as f:
                balance = float(f.read().strip())
        except Exception:
            pass
    else:
        os.makedirs(os.path.dirname(balance_file), exist_ok=True)
        try:
            with open(balance_file, "w") as f:
                f.write(str(balance))
        except Exception:
            pass

    # Seleziona il colore in base al verdetto
    if verdict == "BUY":
        v_color = BOLD + GREEN
    elif verdict == "SELL":
        v_color = BOLD + RED
    else:
        v_color = BOLD + WHITE
        
    # Calcola il regime di mercato e il dimensionamento del rischio dinamico prima di stampare
    regime = last.get("market_regime", "RANGING")
    if risk_class == "DYNAMIC":
        thresh = Config.TRENDING_THRESHOLD if regime == "TRENDING" else Config.RANGING_THRESHOLD
        margin_above = abs(score) - thresh
        if margin_above >= 15 and verdict in ("BUY", "SELL"):
            risk_pct, max_leverage = 0.07, 8.0
            active_risk_label = "DYNAMIC (MEDIUM)"
        else:
            risk_pct, max_leverage = 0.03, 4.0
            active_risk_label = "DYNAMIC (LOW)"

    sep = CYAN + "=" * 52 + RESET
    print(f"\n{sep}")
    print(f"  {BOLD}{WHITE}{ts[:19]}Z{RESET} | {BOLD}{CYAN}{Config.SYMBOL}{RESET} | {BOLD}{YELLOW}{Config.TIMEFRAME}{RESET}")
    print(f"  Saldo Simulato Live : {BOLD}{YELLOW}{balance:.2f} €{RESET}")
    print(f"  Profilo Rischio     : {BOLD}{MAGENTA}{active_risk_label}{RESET} (Rischio: {risk_pct*100:.1f}% / Leva: {max_leverage:.1f}x)")
    print(f"  Segnale             : {v_color}{verdict}{RESET}  |  Score: {v_color}{score}{RESET}")
    print(sep)

    if verdict in ("BUY", "SELL"):
        # Anti-spam: max 1 trade per candela
        last_signal_file = "data/last_signal.txt"
        if os.path.exists(last_signal_file):
            try:
                with open(last_signal_file, "r") as f:
                    if f.read().strip() == candle_ts:
                        msg_ign = "⚠️ Azione ignorata: trade già eseguito su questa candela."
                        print(f"  {YELLOW}{msg_ign} Attendo la prossima.{RESET}")
                        print(f"{sep}\n")
                        
                        tg_ign_file = "data/last_ign_tg.txt"
                        sent_ign = False
                        if os.path.exists(tg_ign_file):
                            try:
                                with open(tg_ign_file, "r") as tf:
                                    if tf.read().strip() == candle_ts:
                                        sent_ign = True
                            except Exception:
                                pass
                        if not sent_ign:
                            notifier.send_alert(msg_ign, print_console=False)
                            try:
                                with open(tg_ign_file, "w") as tf:
                                    tf.write(candle_ts)
                            except Exception:
                                pass
                        return
            except Exception:
                pass

        current_rr = Config.TRENDING_RR if regime == "TRENDING" else Config.RANGING_RR

        try:
            with open(last_signal_file, "w") as f:
                f.write(candle_ts)
        except Exception:
            pass

        # Salva il trigger breakout pendente per la pazienza strategica (2 candele)
        pending_trigger = {
            "side": verdict,
            "signal_high": float(last["High"]),
            "signal_low": float(last["Low"]),
            "candle_ts": candle_ts,
            "atr_val": atr_val,
            "current_rr": current_rr,
            "score": score,
            "confluence_comb": confluence_comb,
            "risk_pct": risk_pct,
            "max_leverage": max_leverage,
            "regime": regime,
            "logs": logs
        }
        pending_trigger_file = "data/pending_trigger.json"
        os.makedirs(os.path.dirname(pending_trigger_file), exist_ok=True)
        try:
            with open(pending_trigger_file, "w") as f:
                json.dump(pending_trigger, f)
        except Exception as e:
            print(f"[ERROR] Impossibile salvare pending_trigger.json: {e}")

        # Disegna un box grafico colorato di attesa breakout
        box_color = CYAN
        trig_price = float(last["High"]) if verdict == "BUY" else float(last["Low"])
        print(f"\n{box_color}╔════════════════════════════════════════════════════╗")
        print(f"║  ⏳ REGISTRATO TRIGGER BREAKOUT (PAZIENZA STRAT.)  ║")
        print(f"║  🚨 {verdict:<4} {Config.SYMBOL:<38} ║")
        print(f"║  Attesa rottura di: {trig_price:.2f} USDT              ║")
        print(f"║  Score segnale    : {score:<31} ║")
        print(f"║  Confluenza       : {confluence_comb:<31} ║")
        print(f"╚════════════════════════════════════════════════════╝{RESET}")

        msg = (
            f"⏳ REGISTRATO TRIGGER BREAKOUT (PAZIENZA STRAT.)\n"
            f"Asset: {Config.SYMBOL} | Direzione: {verdict}\n"
            f"Attesa rottura di: {trig_price:.2f} USDT\n"
            f"Confluenza: {confluence_comb} | Score: {score}"
        )
        notifier.send_alert(msg, print_console=False)

        # --- Black Box Logging ---
        log_file = "data/bot_live.log"
        log_line = (
            f"[{ts}] PENDING_BREAKOUT_{verdict} | Score: {score} | "
            f"SignalHigh: {last['High']:.2f} | SignalLow: {last['Low']:.2f} | "
            f"ATR: {atr_val:.2f} | Balance: {balance:.2f} EUR | RiskClass: {risk_class} | "
            f"Confirmations: {', '.join(logs)}\n"
        )
        append_to_log_with_rotation(log_file, log_line)
    else:
        print(f"  HOLD — score corrente: {v_color}{score}{RESET}")
        print("  Conferme Attive:")
        for log in logs:
            print(f"    {GREEN}✓{RESET} {log}")
            
        tg_hold_file = "data/last_hold_tg.txt"
        sent_hold = False
        if os.path.exists(tg_hold_file):
            try:
                with open(tg_hold_file, "r") as tf:
                    if tf.read().strip() == candle_ts:
                        sent_hold = True
            except Exception:
                pass
        if not sent_hold:
            notifier.send_alert(f"⏸️ HOLD — Score: {score}\nNessun segnale forte in questa candela.", print_console=False)
            try:
                with open(tg_hold_file, "w") as tf:
                    tf.write(candle_ts)
            except Exception:
                pass

        # --- Black Box Logging ---
        log_file = "data/bot_live.log"
        log_line = (
            f"[{ts}] {verdict} | Score: {score} | Price: {entry:.2f} | "
            f"ATR: {atr_val:.2f} | Balance: {balance:.2f} EUR | RiskClass: {risk_class} | "
            f"Confirmations: {', '.join(logs)}\n"
        )
        append_to_log_with_rotation(log_file, log_line)

    print(f"{sep}\n")


async def main() -> None:
    print("🤖 Trading Bot avviato (Multi-Trade Mode).")
    print(f"  📊 Max trade simultanei: {Config.MAX_CONCURRENT_TRADES}")
    asyncio.create_task(notifier.start_polling())
    
    import multi_trade_manager as mtm
    
    initial_balance_file = "data/initial_balance.txt"
    balance_file = "data/balance_live.txt"

    # Salva il saldo iniziale al primo avvio
    initial_balance = None
    if os.path.exists(initial_balance_file):
        try:
            with open(initial_balance_file, "r") as f:
                initial_balance = float(f.read().strip())
        except Exception:
            pass
    if initial_balance is None:
        current_bal = 100.0
        if os.path.exists(balance_file):
            try:
                with open(balance_file, "r") as f:
                    current_bal = float(f.read().strip())
            except Exception:
                pass
        initial_balance = current_bal
        os.makedirs(os.path.dirname(initial_balance_file), exist_ok=True)
        with open(initial_balance_file, "w") as f:
            f.write(f"{initial_balance:.2f}")
        print(f"  📌 Saldo iniziale registrato: {initial_balance:.2f} €")

    target_balance = initial_balance * (1 + Config.PROFIT_TARGET_PCT)
    print(f"  🎯 Profit Target: +{Config.PROFIT_TARGET_PCT*100:.0f}% → {target_balance:.2f} € (da {initial_balance:.2f} €)")

    # Migra trade vecchi (legacy single-trade) se presenti
    old_active = "data/active_trade.json"
    old_pending = "data/pending_trigger.json"
    for old_file in [old_active, old_pending]:
        if os.path.exists(old_file):
            try:
                os.remove(old_file)
                print(f"  🗑️ Rimosso file legacy: {old_file}")
            except Exception:
                pass

    import ccxt.async_support as ccxt_async
    exchange = getattr(ccxt_async, Config.EXCHANGE_ID)({
        "apiKey": Config.API_KEY or None,
        "secret": Config.API_SECRET or None,
    })
    exchange.verbose = False

    try:
        while True:
            try:
                # ══ 1. PROFIT TARGET CHECK ══
                current_balance = initial_balance
                if os.path.exists(balance_file):
                    try:
                        with open(balance_file, "r") as f:
                            current_balance = float(f.read().strip())
                    except Exception:
                        pass

                if current_balance >= target_balance:
                    profit_pct = (current_balance - initial_balance) / initial_balance * 100
                    print(f"\n{GREEN}{'='*52}")
                    print(f"  🏆 PROFIT TARGET RAGGIUNTO!")
                    print(f"  Saldo attuale   : {current_balance:.2f} €")
                    print(f"  Saldo iniziale  : {initial_balance:.2f} €")
                    print(f"  Profitto        : +{profit_pct:.1f}%")
                    print(f"{'='*52}{RESET}\n")
                    notifier.send_alert(
                        f"🏆 PROFIT TARGET RAGGIUNTO!\n"
                        f"Saldo: {current_balance:.2f} € (+{profit_pct:.1f}%)\n"
                        f"Bot arrestato automaticamente.",
                        print_console=False
                    )
                    print(f"{GREEN}[SHUTDOWN] Bot fermato — profit target raggiunto. Complimenti! 🎉{RESET}")
                    break

                # ══ 2. FETCH PREZZO CORRENTE ══
                try:
                    ticker = await exchange.fetch_ticker(Config.SYMBOL)
                    current_price = float(ticker["last"])
                    hi = float(ticker.get("high", current_price))
                    lo = float(ticker.get("low", current_price))
                except Exception as e:
                    print(f"  [WARN] Fetch ticker fallito: {e}")
                    await asyncio.sleep(5)
                    continue

                # ══ 3. CHECK TRADE APERTI (SL/TP) ══
                open_trades = mtm.get_open_trades()
                if open_trades:
                    closed_trades = mtm.check_all_trades(current_price, notifier)
                    for ct in closed_trades:
                        t = ct["trade"]
                        pnl_color = GREEN if ct["pnl"] >= 0 else RED
                        icon = "✅" if ct["reason"] == "TP" else "❌"
                        print(f"  {icon} {ct['reason']} | {t['verdict']} | PnL: {pnl_color}{ct['pnl']:+.2f} EUR{RESET} | Exit: {ct['exit']:.2f}")

                # ══ 4. CHECK PENDING TRIGGERS ══
                opened_trades = mtm.check_pending_triggers(current_price, hi, lo, notifier)
                for ot in opened_trades:
                    print(f"  🚀 TRADE APERTO: {ot['verdict']} a {ot['entry']:.2f} | SL: {ot['sl']:.2f} | TP: {ot['tp']:.2f}")

                # ══ 5. STATUS DISPLAY ══
                open_trades = mtm.get_open_trades()  # refresh dopo check
                balance_now = current_balance
                if os.path.exists(balance_file):
                    try:
                        with open(balance_file, "r") as f:
                            balance_now = float(f.read().strip())
                    except Exception:
                        pass

                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                sep = CYAN + "=" * 60 + RESET
                print(f"\n{sep}")
                print(f"  {BOLD}{WHITE}{ts}{RESET} | {BOLD}{CYAN}{Config.SYMBOL}{RESET} | {BOLD}{YELLOW}{Config.TIMEFRAME}{RESET}")
                print(f"  Saldo: {BOLD}{YELLOW}{balance_now:.2f} €{RESET} | Prezzo: {current_price:.2f}")
                print(f"  Trade aperti: {BOLD}{len(open_trades)}/{Config.MAX_CONCURRENT_TRADES}{RESET} | Strategia: {Config.STRATEGY_MODE}")

                # Mostra trade aperti
                if open_trades:
                    for t in open_trades:
                        if t["verdict"] == "BUY":
                            pnl = t["size"] * (current_price - t["entry"])
                        else:
                            pnl = t["size"] * (t["entry"] - current_price)
                        comm = round_trip_commission(t["size"], t["entry"], current_price, COMMISSION_RATE)
                        net = pnl - comm
                        pnl_color = GREEN if net >= 0 else RED
                        print(f"    📈 {t['verdict']} @ {t['entry']:.2f} | SL: {t['sl']:.2f} | TP: {t['tp']:.2f} | PnL: {pnl_color}{net:+.2f}{RESET}")

                # ══ 6. SCAN NUOVI SEGNALI (se sotto il limite) ══
                if mtm.can_open_new_trade():
                    # Fetch dati completi per analisi
                    client = ExchangeClient(
                        exchange_id=Config.EXCHANGE_ID,
                        symbol=Config.SYMBOL,
                        timeframe=Config.TIMEFRAME,
                        limit=LIMIT,
                        api_key=Config.API_KEY or None,
                        api_secret=Config.API_SECRET or None,
                    )
                    df = await client.fetch_async()
                    if df is not None and not df.empty:
                        df = TechnicalAnalyzer().add_indicators(df, is_live=True)
                        engine = DecisionEngine()
                        res = engine.evaluate(df)
                        verdict, score, conf, entry_type = res[0], res[1], res[2], res[3]
                        confluence_comb = res[5] if len(res) > 5 else "None"
                        logs = [f"{k}: ✓" for k, v in conf.items() if v]

                        last = df.iloc[-1]
                        atr_val = float(last["atr"]) if float(last["atr"]) != 0 else float(last["Close"]) * 0.01
                        candle_ts = str(last.name)
                        regime = last.get("market_regime", "RANGING")

                        # Risk profile
                        risk_class = Config.RISK_CLASS.upper()
                        if risk_class == "LOW":
                            risk_pct, max_leverage = 0.03, 4.0
                        elif risk_class == "MEDIUM":
                            risk_pct, max_leverage = 0.07, 8.0
                        elif risk_class == "HIGH":
                            risk_pct, max_leverage = 0.15, 10.0
                        else:
                            risk_pct, max_leverage = 0.03, 4.0

                        if verdict in ("BUY", "SELL"):
                            # Anti-spam: non aprire sulla stessa candela
                            last_signal_file = "data/last_signal.txt"
                            already_signaled = False
                            if os.path.exists(last_signal_file):
                                try:
                                    with open(last_signal_file, "r") as f:
                                        if f.read().strip() == candle_ts:
                                            already_signaled = True
                                except Exception:
                                    pass

                            if not already_signaled:
                                current_rr = Config.TRENDING_RR if regime == "TRENDING" else Config.RANGING_RR
                                try:
                                    with open(last_signal_file, "w") as f:
                                        f.write(candle_ts)
                                except Exception:
                                    pass

                                # Registra trigger breakout pendente con features e probabilità AI per Kelly
                                from core.data_collector import DataCollector
                                current_features = DataCollector.extract_features(df, len(df) - 1)
                                ai_probability = conf.get("ai_prob", 50.0)

                                mtm.save_pending_trigger(
                                    side=verdict,
                                    signal_high=float(last["High"]),
                                    signal_low=float(last["Low"]),
                                    atr_val=atr_val,
                                    current_rr=current_rr,
                                    score=score,
                                    risk_pct=risk_pct,
                                    max_leverage=max_leverage,
                                    regime=regime,
                                    candle_ts=candle_ts,
                                    ai_prob=ai_probability,
                                    features=current_features,
                                )

                                v_color = GREEN if verdict == "BUY" else RED
                                trig = float(last["High"]) if verdict == "BUY" else float(last["Low"])
                                print(f"  ⏳ NUOVO TRIGGER: {v_color}{verdict}{RESET} | Breakout: {trig:.2f} | Score: {score}")
                                notifier.send_alert(
                                    f"⏳ Trigger {verdict} registrato\n"
                                    f"Breakout: {trig:.2f} | Score: {score}",
                                    print_console=False
                                )
                        else:
                            print(f"  Segnale: HOLD | Score: {score} | {', '.join(logs)}")
                else:
                    print(f"  ⚠️ Max trade raggiunti ({Config.MAX_CONCURRENT_TRADES}). Attendo chiusura...")

                # Log
                log_file = "data/bot_live.log"
                ts_log = datetime.now(timezone.utc).isoformat()
                log_line = (
                    f"[{ts_log}] Price: {current_price:.2f} | Balance: {balance_now:.2f} | "
                    f"OpenTrades: {len(open_trades)}/{Config.MAX_CONCURRENT_TRADES}\n"
                )
                append_to_log_with_rotation(log_file, log_line)

                print(f"{sep}\n")

            except Exception as e:
                print(f"[ERROR] {e}")
                import traceback
                traceback.print_exc()

            await asyncio.sleep(SLEEP_SEC)

    finally:
        await exchange.close()
        await notifier.close()


if __name__ == "__main__":
    asyncio.run(main())
