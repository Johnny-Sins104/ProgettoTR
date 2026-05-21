"""
backtest_lab.py — Simulazione isolata con Regime Switching, Ordini Pendenti e Profili di Rischio Multipli (Compounding).
"""
import asyncio
import os
import sys
import pandas as pd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


from config import Config
from core.client import ExchangeClient
from core.analyzer import TechnicalAnalyzer
from core.engine import DecisionEngine
from core.risk import DynamicRiskEngine, RiskManager
from core.visualizer import save_trade_chart
from core.ai_engine import TradingAI

CHARTS_DIR = "data/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

# ------------------------------------------------------------------ #
#  PARAMETRI SIMULAZIONE                                               #
# ------------------------------------------------------------------ #
INITIAL_BALANCE  = 1000.0   # €
COMMISSION_RATE  = Config.COMMISSION_RATE  # Centralizzato in Config (Futures: 0.02% per side)

# ------------------------------------------------------------------ #
#  FETCH + ANALISI                                                     #
# ------------------------------------------------------------------ #
async def fetch_data() -> pd.DataFrame:
    # Determina i percorsi di cache per il timeframe corrente
    timeframe = Config.TIMEFRAME
    if timeframe == "5m":
        csv_path = os.path.join("data", "btc_5m_10k_cache.csv")
        parquet_path = os.path.join("data", "btc_5m_10k_cache.parquet")
    else:
        csv_path = os.path.join("data", "btc_15m_cache.csv")
        parquet_path = os.path.join("data", "btc_15m_cache.parquet")
        
    # Se il parquet non esiste, ma il csv esiste, avvia la migrazione automatica!
    if not os.path.exists(parquet_path) and os.path.exists(csv_path):
        print(f"📦 [MIGRATION] Rilevato file CSV legacy '{csv_path}'. Avvio migrazione automatica a Parquet...")
        try:
            import polars as pl
            from core.data_collector import DatasetIntegrity, DatasetVersioning
            
            # Leggiamo il CSV con Polars
            df_legacy = pl.read_csv(csv_path)
            
            # Validiamo e ripuliamo i dati
            df_legacy = DatasetIntegrity.detect_and_remove_duplicates(df_legacy)
            df_legacy = DatasetIntegrity.validate_schema(df_legacy, is_features=False)
            df_legacy = DatasetIntegrity.handle_missing_data(df_legacy, max_null_ratio=Config.MAX_NULL_TOLERANCE)
            DatasetIntegrity.validate_timestamps(df_legacy, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
            
            # Scriviamo in formato Parquet con compressione Snappy e metadati
            DatasetVersioning.write_parquet_with_metadata(df_legacy, parquet_path, is_features=False)
            
            # Rimuoviamo il vecchio CSV legacy
            os.remove(csv_path)
            print(f"🗑️ [MIGRATION] File CSV legacy '{csv_path}' eliminato per pulire lo spazio di lavoro.")
        except Exception as e:
            print(f"❌ [MIGRATION ERROR] Impossibile migrare {csv_path} a Parquet: {e}. Fallback su caricamento legacy.")
            
    # Ora carica dal file Parquet se esiste
    if os.path.exists(parquet_path):
        print(f"[INIT] Caricamento dati offline da cache Parquet: {parquet_path}...")
        import polars as pl
        from core.data_collector import DatasetIntegrity
        
        df_pl = pl.read_parquet(parquet_path)
        
        # Validazione finale di integrità prima dell'uso
        df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
        df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
        df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
        DatasetIntegrity.validate_timestamps(df_pl, expected_delta_min=Config.EXPECTED_TIMEFRAME_MINUTES)
        
        # Converte in Pandas DataFrame per retrocompatibilità
        df = df_pl.to_pandas()
        if "datetime" in df.columns:
            df.set_index("datetime", inplace=True)
            
        print(f"✅ [INTEGRITY CHECK] Dati offline verificati con successo: {len(df)} candele caricate.")
        return TechnicalAnalyzer().add_indicators(df)
        
    # Altrimenti prova a caricare dal vecchio CSV se la migrazione è fallita ma il file esiste ancora
    elif os.path.exists(csv_path):
        print(f"[INIT] Fallback: Caricamento dati offline da cache CSV legacy: {csv_path}...")
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        return TechnicalAnalyzer().add_indicators(df)
        
    else:
        # Nessun file trovato, scarichiamo dati freschi dall'exchange
        print(f"[INIT] Cache non trovata ({parquet_path}). Download in corso via exchange ({Config.SYMBOL} {Config.TIMEFRAME})...")
        from core.client import ExchangeClient
        client = ExchangeClient(
            exchange_id=Config.EXCHANGE_ID,
            symbol=Config.SYMBOL,
            timeframe=Config.TIMEFRAME,
            limit=1000,
        )
        df = await client.fetch_async()
        if df is None or df.empty:
            raise RuntimeError("Fetch fallito: DataFrame vuoto.")
            
        # Validazione e salvataggio dei dati scaricati direttamente in formato Parquet
        import polars as pl
        from core.data_collector import DatasetIntegrity, DatasetVersioning
        
        # Gestiamo l'indice in Pandas e passiamo a Polars
        df_reset = df.reset_index()
        df_pl = pl.DataFrame(df_reset)
        
        df_pl = DatasetIntegrity.detect_and_remove_duplicates(df_pl)
        df_pl = DatasetIntegrity.validate_schema(df_pl, is_features=False)
        df_pl = DatasetIntegrity.handle_missing_data(df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
        
        DatasetVersioning.write_parquet_with_metadata(df_pl, parquet_path, is_features=False)
        
        return TechnicalAnalyzer().add_indicators(df)


# ------------------------------------------------------------------ #
#  SIMULATORE SINGOLO                                                 #
# ------------------------------------------------------------------ #
def simulate_backtest(
    df: pd.DataFrame, 
    risk_pct: float, 
    max_leverage: float,
    save_charts: bool = False,
    features_df: pd.DataFrame = None,
    wf_folds: list = None
) -> dict:
    engine   = DecisionEngine()  # Inizializzato con i pesi/soglie evoluti di Config
    risk_mgr = DynamicRiskEngine(
        initial_balance=INITIAL_BALANCE,
        vol_lookback=Config.VOL_LOOKBACK,
        dd_caution_pct=Config.DD_CAUTION_PCT,
        dd_reduced_pct=Config.DD_REDUCED_PCT,
        dd_protected_pct=Config.DD_PROTECTED_PCT,
        daily_loss_limit_pct=Config.DAILY_LOSS_LIMIT_PCT,
        profit_lock_pct=Config.PROFIT_LOCK_PCT,
        max_leverage=max_leverage if isinstance(max_leverage, float) else Config.MAX_LEVERAGE,
    )

    balance       = INITIAL_BALANCE
    trades        = []          # lista dict per ogni trade chiuso
    open_trade    = None        # trade corrente in attesa di SL/TP
    pending_trigger = None      # "Pazienza Strategica" Breakout Trigger
    max_drawdown = 0.0
    peak_balance = INITIAL_BALANCE

    # Genera i fold walk-forward in caso non siano stati passati
    if wf_folds is None and Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID" and features_df is not None:
        from core.walk_forward import WalkForwardPipeline
        wf_folds = WalkForwardPipeline.get_wf_splits(
            len(df), 
            N=2000, 
            M=500, 
            embargo_gap=Config.EMBARGO_GAP, 
            df=df
        )

    rows = df.reset_index()  # iteriamo per indice intero

    for i in range(1, len(rows)):
        row = rows.iloc[i]

        # Walk-Forward AI Update
        if Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID" and features_df is not None and wf_folds:
            # Trova il fold di test attivo per l'indice corrente
            active_fold = None
            for fold in wf_folds:
                if fold.test_start <= i <= fold.test_end:
                    active_fold = fold
                    break
            
            if active_fold is None:
                TradingAI().set_active_model(None)
            else:
                TradingAI().ensure_wf_model(df, features_df, active_fold)
                TradingAI().set_active_model(active_fold.test_start)

        # 1. Gestione trade aperto: cerca SL o TP nelle candele successive
        if open_trade is not None:
            hi  = float(row["High"])
            lo  = float(row["Low"])
            sl  = open_trade["sl"]
            entry     = open_trade["entry"]
            size      = open_trade["size"]
            side      = open_trade["side"]
            atr_val   = open_trade.get("atr_val", 0.0)
            be_trig   = open_trade.get("be_triggered", False)

            # Protezione Capitale: Sposta SL a BE se profitto raggiunge 1x ATR
            if atr_val > 0.0 and not be_trig:
                if side == "BUY" and hi >= entry + atr_val:
                    open_trade["be_triggered"] = True
                    open_trade["sl"] = entry
                    sl = entry
                elif side == "SELL" and lo <= entry - atr_val:
                    open_trade["be_triggered"] = True
                    open_trade["sl"] = entry
                    sl = entry

            if Config.USE_SCALE_OUT:
                # ── SCALE-OUT MODE (50/50 split) ──
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
                        pnl_1 = (size / 2) * (tp1 - entry) if side == "BUY" else (size / 2) * (entry - tp1)
                        comm_1 = (size / 2) * entry * COMMISSION_RATE * 2
                        net_pnl_1 = pnl_1 - comm_1
                        balance += net_pnl_1
                        open_trade["pnl_tp1_net"] = net_pnl_1

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
                        risk_mgr.update_equity(balance)  # circuit-breaker equity update

                        if balance > peak_balance: peak_balance = balance
                        dd = (peak_balance - balance) / peak_balance * 100
                        if dd > max_drawdown: max_drawdown = dd

                        trade_num = len(trades) + 1
                        trades.append({
                            "side": side, "result": "LOSS", "pnl": net_pnl,
                            "balance": balance, "entry": entry,
                            "sl": open_trade["initial_sl"], "tp": tp2,
                            "confluence_comb": open_trade.get("confluence_comb", "None"),
                            "ai_prob": open_trade.get("ai_prob", 50.0),
                            "entry_time": open_trade["entry_time"],
                            "exit_time": str(row["datetime"]) if "datetime" in row else str(row.name),
                            "regime": open_trade["regime"],
                            "adx": open_trade["adx"],
                            "atr_pct": open_trade["atr_pct"],
                            "volume": open_trade["volume"],
                            "volume_ratio": open_trade["volume_ratio"],
                            "close_vs_ema": open_trade["close_vs_ema"],
                            "setup_quality": open_trade.get("setup_quality", 0.0)
                        })

                        if save_charts:
                            chart_path = f"{CHARTS_DIR}/trade_{trade_num:03d}_LOSS.html"
                            save_trade_chart(df=open_trade["window_df"],
                                trade_data={"side": side, "entry": entry, "sl": open_trade["initial_sl"], "tp": tp2},
                                filename=chart_path)

                        open_trade = None
                        if balance <= 0: break

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

                        if balance > peak_balance: peak_balance = balance
                        dd = (peak_balance - balance) / peak_balance * 100
                        if dd > max_drawdown: max_drawdown = dd

                        trade_num = len(trades) + 1
                        trades.append({
                            "side": side, "result": result, "pnl": net_pnl_total,
                            "balance": balance, "entry": entry, "sl": sl, "tp": tp2,
                            "confluence_comb": open_trade.get("confluence_comb", "None"),
                            "ai_prob": open_trade.get("ai_prob", 50.0),
                            "entry_time": open_trade["entry_time"],
                            "exit_time": str(row["datetime"]) if "datetime" in row else str(row.name),
                            "regime": open_trade["regime"],
                            "adx": open_trade["adx"],
                            "atr_pct": open_trade["atr_pct"],
                            "volume": open_trade["volume"],
                            "volume_ratio": open_trade["volume_ratio"],
                            "close_vs_ema": open_trade["close_vs_ema"],
                            "setup_quality": open_trade.get("setup_quality", 0.0)
                        })

                        if save_charts:
                            chart_path = f"{CHARTS_DIR}/trade_{trade_num:03d}_{result}.html"
                            save_trade_chart(df=open_trade["window_df"],
                                trade_data={"side": side, "entry": entry, "sl": sl, "tp": tp2},
                                filename=chart_path)

                        open_trade = None
                        if balance <= 0: break

            else:
                # ── SINGLE TARGET MODE (SL / TP diretto) ──
                tp = open_trade["tp"]
                hit_tp = (side == "BUY" and hi >= tp) or (side == "SELL" and lo <= tp)
                hit_sl = (side == "BUY" and lo <= sl) or (side == "SELL" and hi >= sl)

                if hit_tp and not hit_sl:
                    pnl = size * (tp - entry) if side == "BUY" else size * (entry - tp)
                    commission = size * entry * COMMISSION_RATE * 2
                    net_pnl = pnl - commission
                    balance += net_pnl
                    result = "WIN"
                elif hit_sl:
                    pnl = size * (sl - entry) if side == "BUY" else size * (entry - sl)
                    commission = size * entry * COMMISSION_RATE * 2
                    net_pnl = pnl - commission
                    balance += net_pnl
                    result = "BREAKEVEN" if open_trade.get("be_triggered", False) else "LOSS"
                else:
                    net_pnl = None

                if net_pnl is not None:
                    risk_mgr.update_equity(balance)  # circuit-breaker equity update
                    if balance > peak_balance: peak_balance = balance
                    dd = (peak_balance - balance) / peak_balance * 100
                    if dd > max_drawdown: max_drawdown = dd

                    trade_num = len(trades) + 1
                    trades.append({
                        "side": side, "result": result, "pnl": net_pnl,
                        "balance": balance, "entry": entry, "sl": sl, "tp": tp,
                        "confluence_comb": open_trade.get("confluence_comb", "None"),
                        "ai_prob": open_trade.get("ai_prob", 50.0),
                        "entry_time": open_trade["entry_time"],
                        "exit_time": str(row["datetime"]) if "datetime" in row else str(row.name),
                        "regime": open_trade["regime"],
                        "adx": open_trade["adx"],
                        "atr_pct": open_trade["atr_pct"],
                        "volume": open_trade["volume"],
                        "volume_ratio": open_trade["volume_ratio"],
                        "close_vs_ema": open_trade["close_vs_ema"],
                        "setup_quality": open_trade.get("setup_quality", 0.0)
                    })

                    if save_charts:
                        chart_path = f"{CHARTS_DIR}/trade_{trade_num:03d}_{result}.html"
                        save_trade_chart(df=open_trade["window_df"],
                            trade_data={"side": side, "entry": entry, "sl": sl, "tp": tp},
                            filename=chart_path)

                    open_trade = None
                    if balance <= 0: break

            # Se il trade è ancora aperto (nessun target della seconda metà è stato colpito)
            if open_trade is not None:
                # Invecchia il trigger breakout se pendente
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
                # Eseguiamo il trade!
                # Calcoliamo i parametri di rischio del trade usando entry_price effettivo
                atr_val = pending_trigger["atr_val"]
                current_rr = pending_trigger["current_rr"]
                targets = risk_mgr.calculate_targets(side, entry_price, atr_val, rr_ratio=current_rr)
                sl, tp  = targets["sl"], targets["tp"]
                
                risk_per_unit = abs(entry_price - sl)
                if risk_per_unit > 0:
                    risk_pct = pending_trigger["risk_pct"]
                    max_leverage = pending_trigger["max_leverage"]
                    regime = pending_trigger["regime"]
                    ai_prob = pending_trigger.get("ai_prob", 50.0)
                    
                    # Sizing dinamico o Kelly Criterion se attivo
                    if Config.USE_KELLY_SIZING and ai_prob != 50.0:
                        risk_pct_base = 0.15 if risk_pct == "DYNAMIC" else risk_pct
                        current_risk = risk_mgr.calculate_kelly_risk_pct(ai_prob, current_rr, risk_pct_base)
                        current_lev = max_leverage if risk_pct != "DYNAMIC" else 10.0
                    elif risk_pct == "DYNAMIC":
                        thresh = Config.TRENDING_THRESHOLD if regime == "TRENDING" else Config.RANGING_THRESHOLD
                        margin_above = abs(pending_trigger["score"]) - thresh
                        if margin_above >= 15:
                            current_risk = 0.07
                            current_lev = 8.0
                        else:
                            current_risk = 0.03
                            current_lev = 4.0
                    else:
                        current_risk = risk_pct
                        current_lev = max_leverage
                        
                    risk_capital = balance * current_risk
                    if Config.USE_COMMISSION_AWARE_SIZING:
                        size = risk_capital / (risk_per_unit + (2 * entry_price * COMMISSION_RATE))
                    else:
                        size = risk_capital / risk_per_unit
                    max_size = (balance * current_lev) / entry_price
                    size = min(size, max_size)
                    
                    # Estrai indicatori della candela di segnale per l'analisi del regime
                    from core.data_collector import DataCollector
                    last_window = pending_trigger["window_df"]
                    last_row = last_window.iloc[-1]
                    close_val = float(last_row.get("Close", last_row.get("close", 0.0)))
                    ema_200_val = float(last_row.get("ema_200", 0.0))
                    close_vs_ema = ((close_val - ema_200_val) / ema_200_val * 100) if ema_200_val > 0 else 0.0
                    atr_val = float(last_row.get("atr", atr_val))
                    atr_pct = (atr_val / close_val * 100) if close_val > 0 else 0.0
                    
                    # Calcola volume ratio
                    volume_ratio = 1.0
                    if len(last_window) >= 20:
                        vol_mean = last_window.iloc[-20:]["Volume"].mean()
                        if vol_mean > 0:
                            volume_ratio = float(last_row["Volume"]) / vol_mean
                            
                    # Calcola setup quality score tramite SetupFilter
                    from core.setup_filter import SetupFilter
                    setup_quality = SetupFilter.calculate_quality_score(last_row, volume_ratio, side)
                    
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
                        "confluence_comb": pending_trigger["confluence_comb"],
                        "ai_prob": ai_prob,
                        "atr_val": atr_val,
                        
                        # --- regime performance analytics metadata ---
                        "entry_time": str(row["datetime"]) if "datetime" in row else str(row.name),
                        "regime": regime,
                        "adx": float(last_row.get("adx", 0.0)),
                        "atr_pct": float(last_row.get("atr_pct", atr_pct)),
                        "volume": float(last_row.get("Volume", last_row.get("volume", 0.0))),
                        "volume_ratio": volume_ratio,
                        "close_vs_ema": close_vs_ema,
                        "setup_quality": setup_quality
                    }
                pending_trigger = None
            else:
                # Decrementa il TTL del breakout trigger
                pending_trigger["ttl"] -= 1
                if pending_trigger["ttl"] <= 0:
                    pending_trigger = None  # Scaduto: falso breakout scartato!

        # 3. Valuta nuovi segnali
        if open_trade is None and pending_trigger is None:
            window   = df.iloc[:i]
            last     = window.iloc[-1]
            
            if Config.AI_ENABLED and Config.STRATEGY_MODE == "AI_HYBRID":
                # Stage 1: Rules-based Technical Signal Candidate
                tech_verdict, tech_score, conf, entry_type, conf_verdict, conf_comb = engine._evaluate_score(window)
                
                if tech_verdict in ("BUY", "SELL") and entry_type is not None:
                    # Stage 2: Technical Setup Filter & Quality Scoring
                    from core.data_collector import DataCollector
                    from core.setup_filter import SetupFilter
                    
                    features = DataCollector.extract_features(window, len(window) - 1)
                    volume_ratio = features.get("volume_ratio", 1.0)
                    is_tech_ok, setup_quality = SetupFilter.evaluate_setup(tech_verdict, last, volume_ratio)
                    features["setup_quality"] = setup_quality
                    
                    # Stage 2: Meta-Model prediction & Calibration (dual-regime routed)
                    ai = TradingAI()
                    if ai.is_ready():
                        p_cal = ai.predict_probability(features, side=tech_verdict)
                    else:
                        p_cal = 50.0
                        
                    # Stage 2: Expected Value setup ranking & prioritization
                    from core.setup_ranker import SetupRanker
                    candidate = {
                        "side": tech_verdict,
                        "p_cal": p_cal,
                        "rr": Config.TRENDING_RR if last.get("market_regime", "RANGING") == "TRENDING" else Config.RANGING_RR,
                        "setup_quality": setup_quality
                    }
                    
                    ranked = SetupRanker.rank_candidates([candidate], available_slots=1)
                    
                    # Gating: setup must pass both thresholds and have positive EV
                    if ranked and p_cal >= Config.META_PROB_THRESHOLD and is_tech_ok:
                        verdict = tech_verdict
                        score = int(tech_score * (1.0 - Config.AI_WEIGHT) + (p_cal - 50.0) * 2.0 * Config.AI_WEIGHT)
                        active_conf = {
                            "ai_prob": p_cal,
                            "setup_quality": setup_quality,
                            "tech_score": tech_score
                        }
                        confluence_comb = f"{conf_comb}+Meta_OK(p:{p_cal:.1f}%,q:{setup_quality:.1f})"
                    else:
                        verdict = "HOLD"
                        entry_type = None
                        score = 0
                        active_conf = {"ai_prob": p_cal, "setup_quality": setup_quality, "tech_score": tech_score}
                        confluence_comb = f"Meta_Filtered(p:{p_cal:.1f}%,q:{setup_quality:.1f})"
                else:
                    verdict = "HOLD"
                    entry_type = None
                    score = 0
                    active_conf = {"ai_prob": 50.0, "setup_quality": 0.0, "tech_score": tech_score}
                    confluence_comb = "None"
            else:
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

            # R:R dinamico basato sul Regime di Mercato attuale
            regime = last.get("market_regime", "RANGING")
            current_rr = Config.TRENDING_RR if regime == "TRENDING" else Config.RANGING_RR

            ai_prob = active_conf.get("ai_prob", 50.0)

            pending_trigger = {
                "side": verdict,
                "signal_high": float(last["High"]),
                "signal_low": float(last["Low"]),
                "ttl": 1, # Attendi al massimo 1 candela per il breakout (scalping)
                "atr_val": atr_val,
                "current_rr": current_rr,
                "score": score,
                "confluence_comb": confluence_comb,
                "active_conf": active_conf,
                "window_df": window.copy(),
                "risk_pct": risk_pct,
                "max_leverage": max_leverage,
                "regime": regime,
                "ai_prob": ai_prob
            }

    wins = len([t for t in trades if t["result"] == "WIN"])
    partial_wins = len([t for t in trades if t["result"] == "WIN_PARTIAL"])
    losses = len([t for t in trades if t["result"] == "LOSS"])
    breakevens = len([t for t in trades if t["result"] == "BREAKEVEN"])
    
    total_wins = wins + partial_wins
    trade_con_esito = total_wins + losses
    win_rate = (total_wins / trade_con_esito * 100) if trade_con_esito > 0 else 0.0

    return {
        "final_balance": balance,
        "max_drawdown": max_drawdown,
        "trades": trades,
        "total_trades": len(trades),
        "wins": wins,
        "partial_wins": partial_wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": win_rate,
        "risk_diagnostics": risk_mgr.compute_diagnostics(),
        "risk_engine": risk_mgr,   # returned for dashboard printing
    }

# ------------------------------------------------------------------ #
#  MAIN RUNNER                                                        #
# ------------------------------------------------------------------ #
def run_backtest(df: pd.DataFrame) -> None:
    import shutil
    from core.data_collector import DataCollector
    from core.ai_engine import TradingAI

    # Pulisce la cartella dei grafici per evitare accumuli di vecchie run
    if os.path.exists(CHARTS_DIR):
        try:
            shutil.rmtree(CHARTS_DIR)
        except Exception:
            pass
    os.makedirs(CHARTS_DIR, exist_ok=True)

    print("\n==================================================")
    print("  AVVIO BACKTEST MULTI-RISCHIO CON CONGIUNZIONE GENETICA")
    print("==================================================")
    print(f"  Candele caricate : {len(df)}")
    print(f"  Asset            : {Config.SYMBOL} ({Config.TIMEFRAME})")
    print(f"  Soglia Trending  : {Config.TRENDING_THRESHOLD} (ADX > {Config.ADX_THRESHOLD})")
    print(f"  Soglia Ranging   : {Config.RANGING_THRESHOLD} (ADX <= {Config.ADX_THRESHOLD})")
    print(f"  Stop Loss ATR    : {Config.ATR_MULT:.2f}x")
    print(f"  Target R:R       : {Config.TRENDING_RR:.2f}x (Trending) / {Config.RANGING_RR:.2f}x (Ranging)")
    print("==================================================")
    
    # Gestione Inizializzazione AI & Addestramento
    ai = TradingAI()
    original_strategy_mode = Config.STRATEGY_MODE
    ai_metrics = {}
    features_df = None
    wf_folds = None

    if Config.AI_ENABLED:
        print("🤖 [AI INIT] Estrazione features storiche causali per il dataset...")
        from core.data_collector import DataCollector
        from core.walk_forward import WalkForwardPipeline
        features_df = DataCollector.collect_from_backtest_mem(df)
        
        # Generiamo i fold walk-forward puri ed eseguiamo la timeline diagnostica
        wf_folds = WalkForwardPipeline.get_wf_splits(
            len(df), 
            N=2000, 
            M=500, 
            embargo_gap=Config.EMBARGO_GAP, 
            df=df
        )
        WalkForwardPipeline.print_timeline(wf_folds, len(df))
        
        # Generiamo un dataset di addestramento globale sicuro (con purging e localizzazione)
        global_train_df = DataCollector.generate_training_dataset(
            df=df,
            train_start=0,
            train_end=len(df) - 1,
            features_df=features_df,
            label_horizon=100
        )
        samples_count = len(global_train_df)
        
        if samples_count >= Config.AI_MIN_SAMPLES:
            # Salviamo il dataset in formato Parquet con validazione e metadati
            try:
                import polars as pl
                from core.data_collector import DatasetIntegrity, DatasetVersioning
                
                global_train_df_pl = pl.DataFrame(global_train_df)
                global_train_df_pl = DatasetIntegrity.validate_schema(global_train_df_pl, is_features=True)
                global_train_df_pl = DatasetIntegrity.handle_missing_data(global_train_df_pl, max_null_ratio=Config.MAX_NULL_TOLERANCE)
                global_train_df_pl = DatasetIntegrity.detect_and_remove_duplicates(global_train_df_pl)
                
                DatasetVersioning.write_parquet_with_metadata(global_train_df_pl, Config.AI_FEATURES_PATH, is_features=True)
                print(f"💾 Salvati {samples_count} campioni completi in formato Parquet: {Config.AI_FEATURES_PATH}")
            except Exception as e:
                print(f"[WARN] Impossibile salvare features Parquet: {e}")
                
            print("🧠 [AI INIT] Addestramento modello globale XGBoost sicuro...")
            ai_metrics = ai.train(features_df=global_train_df)
            if ai.is_ready():
                Config.STRATEGY_MODE = "AI_HYBRID"
                print(f"🎯 [AI CONFIG] STRATEGY_MODE impostata a '{Config.STRATEGY_MODE}' per il backtest.")
            else:
                print("⚠️ [AI INIT] Addestramento completato ma modello non pronto. Fallback su strategia base.")
        else:
            print(f"⚠️ [AI INIT] Campioni storici insufficienti ({samples_count}/{Config.AI_MIN_SAMPLES}) per attivare l'AI.")

    profiles = [
        {"name": "Basso Rischio (LOW)", "risk": 0.03, "leverage": 4.0},
        {"name": "Medio Rischio (MEDIUM)", "risk": 0.07, "leverage": 8.0},
        {"name": "Alto Rischio (HIGH)", "risk": 0.15, "leverage": 10.0},
        {"name": "Rischio Dinamico (DYNAMIC)", "risk": "DYNAMIC", "leverage": 0.0},
    ]

    results = {}
    for p in profiles:
        if p["risk"] == "DYNAMIC":
            print(f"  Simulazione {p['name']} (Gestione Dinamica)...")
        else:
            print(f"  Simulazione {p['name']} (Rischio: {p['risk']*100:.1f}%, Leva Max: {p['leverage']:.1f}x)...")
        # Salviamo i grafici del trade solo se corrisponde alla classe selezionata nel Config
        is_selected = (Config.RISK_CLASS == p["name"].split()[-1].replace("(", "").replace(")", ""))
        res = simulate_backtest(df, p["risk"], p["leverage"], save_charts=is_selected, features_df=features_df, wf_folds=wf_folds)
        results[p["name"]] = res

    # Stampa tabella comparativa finale
    sep = "=" * 87
    print(f"\n{sep}")
    print(f"  REPORT COMPARATIVO CLASSI DI RISCHIO COMPILATE")
    print(sep)
    print(f"{'Profilo Rischio':<28}{'Rischio %':<11}{'Leva Max':<10}{'Saldo Finale':<18}{'Net PnL %':<12}{'Max DD %':<10}")
    print("-" * 87)
    for p in profiles:
        res = results[p["name"]]
        net_pct = ((res["final_balance"] - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
        net_pct_str = f"{net_pct:+.2f}%"
        dd_str = f"{res['max_drawdown']:.1f}%"
        if p["risk"] == "DYNAMIC":
            r_str = "Dinamico"
            l_str = "Dinamica"
        else:
            r_str = f"{p['risk']*100:.1f}%"
            l_str = f"{p['leverage']:.1f}x"
        print(f"{p['name']:<28}{r_str:<11}{l_str:<10}{res['final_balance']:<18.2f}{net_pct_str:<12}{dd_str:<10}")
    print(sep)

    # Dettaglio del profilo selezionato
    selected_name = f"Alto Rischio (HIGH)" if Config.RISK_CLASS == "HIGH" else (f"Medio Rischio (MEDIUM)" if Config.RISK_CLASS == "MEDIUM" else (f"Rischio Dinamico (DYNAMIC)" if Config.RISK_CLASS == "DYNAMIC" else "Basso Rischio (LOW)"))
    sel_res = results.get(selected_name)
    if sel_res:
        print(f"\n  Dettaglio Profilo Selezionato ({selected_name}):")
        print(f"    Trade totali   : {sel_res['total_trades']}")
        print(f"    Vinti (Full TP): {sel_res['wins']}")
        print(f"    Vinti (Parz TP): {sel_res.get('partial_wins', 0)}")
        print(f"    Pareggiati (BE): {sel_res.get('breakevens', 0)}")
        print(f"    Persi          : {sel_res['losses']}")
        print(f"    Win Rate (Tot) : {sel_res['win_rate']:.1f}%")
        if len(sel_res['trades']) > 0:
            print("\n    Ultimi 5 trade:")
            for t in sel_res['trades'][-5:]:
                icon = f"[{t['result']}]"
                ai_pct_str = f" | AI Conf: {t['ai_prob']:.1f}%" if "ai_prob" in t else ""
                print(f"      {icon:<12} {t['side']:<4} | PnL: {t['pnl']:+.4f} | Saldo: {t['balance']:.2f} EUR{ai_pct_str}")

        # Dynamic Risk Engine dashboard for selected profile
        sel_engine = sel_res.get("risk_engine")
        if sel_engine is not None:
            sel_engine.print_risk_dashboard()
            # Export risk log for offline analysis
            os.makedirs("data", exist_ok=True)
            sel_engine.export_risk_log("data/risk_log.csv", fmt="csv")
            sel_engine.export_risk_log("data/risk_log.json", fmt="json")
            
            # Genera il report di performance sui regimi di mercato
            if "trades" in sel_res and sel_res["trades"]:
                from core.regime_analyzer import RegimePerformanceAnalyzer
                RegimePerformanceAnalyzer.generate_report(sel_res["trades"], df, "data/regime_report.json")

    # Stampa metriche dell'AI se abilitata e addestrata
    if Config.AI_ENABLED:
        print("\n" + "=" * 120)
        print("🧠 DETTAGLI E DIAGNOSTICA DEL PIPELINE DI VALIDAZIONE WALK-FORWARD (PURGED + EMBARGO)")
        print("=" * 120)
        
        # Se abbiamo modelli Walk-Forward nella cache
        if hasattr(ai, "_wf_models") and ai._wf_models:
            print(f"{'Fold':<5}| {'Train Range':<15} | {'Embargo Range':<15} | {'Test Range':<15} | {'Purged':<8} | {'Eff. Train':<11} | {'Eff. Test':<10} | {'Train Acc':<10} | {'Test Acc':<9} | {'F1-Score':<8}")
            print("-" * 120)
            
            fold_idx = 1
            train_accs = []
            test_accs = []
            f1s = []
            total_purged = 0
            
            for k in sorted(ai._wf_models.keys()):
                m = ai._wf_models[k]
                if not m["is_trained"]:
                    continue
                    
                train_range = f"{m['train_start']}->{m['train_end']}"
                emb_range = f"{m['embargo_start']}->{m['embargo_end']}"
                test_range = f"{m['test_start']}->{m['test_end']}"
                
                purged = m["num_purged_samples"]
                eff_train = m["effective_train_size"]
                eff_test = m["effective_test_size"]
                
                t_acc = f"{m['train_accuracy']*100:.2f}%"
                val_acc = f"{m['accuracy']*100:.2f}%"
                f1_val = f"{m['f1']*100:.2f}%"
                
                print(f" {fold_idx:02d}  | {train_range:<15} | {emb_range:<15} | {test_range:<15} | {purged:<8} | {eff_train:<11} | {eff_test:<10} | {t_acc:<10} | {val_acc:<9} | {f1_val:<8}")
                
                train_accs.append(m["train_accuracy"])
                test_accs.append(m["accuracy"])
                f1s.append(m["f1"])
                total_purged += purged
                fold_idx += 1
                
            print("-" * 120)
            if train_accs:
                avg_train_acc = sum(train_accs) / len(train_accs)
                avg_test_acc = sum(test_accs) / len(test_accs)
                avg_f1 = sum(f1s) / len(f1s)
                diff = avg_train_acc - avg_test_acc
                
                avg_eff_train = int(sum(m['effective_train_size'] for m in ai._wf_models.values() if m['is_trained'])/len(train_accs))
                avg_eff_test = int(sum(m['effective_test_size'] for m in ai._wf_models.values() if m['is_trained'])/len(train_accs))
                
                print(f" MED | {'-':<15} | {'-':<15} | {'-':<15} | {int(total_purged/len(train_accs)):<8} | {avg_eff_train:<11} | {avg_eff_test:<10} | {avg_train_acc*100:.2f}% | {avg_test_acc*100:.2f}% | {avg_f1*100:.2f}%")
                print("=" * 120)
                print(f"  [WALK-FORWARD MEDIA ({len(train_accs)} finestre)]")
                print(f"  Accuratezza media in Training (In-Sample) : {avg_train_acc*100:.2f}%")
                print(f"  Accuratezza media Out-of-Sample (Holdout)  : {avg_test_acc*100:.2f}%")
                print(f"  Differenza media (Training vs Holdout)     : {diff*100:.2f}%")
                print(f"  F1-Score medio Out-of-Sample (Holdout)     : {avg_f1*100:.2f}%")
                
                if diff > 0.10:  # Differenza > 10%
                    print("⚠️ WARNING: Possibile Overfitting! Lo scarto supera il 10%.")
                
                # Dettaglio ultimo modello
                last_limit = max(ai._wf_models.keys())
                last_model = ai._wf_models[last_limit]
                if last_model["is_trained"]:
                    print(f"\n  [ULTIMO MODELLO WALK-FORWARD (Limite: {last_limit})]")
                    print(f"  Accuratezza Training : {last_model['train_accuracy']*100:.2f}%")
                    print(f"  Accuratezza Holdout  : {last_model['accuracy']*100:.2f}%")
                    
                    print("\n📊 IMPORTANZA DELLE FEATURES (Top 10):")
                    importances = last_model.get("importances", {})
                    for idx, (feat, val) in enumerate(list(importances.items())[:10]):
                        print(f"  {idx+1:02d}. {feat:<20}: {val*100:.2f}%")
            else:
                print("⚠️ Nessun fold walk-forward è stato addestrato con successo.")
                print("=" * 120)
        else:
            diff = ai.train_accuracy - ai.accuracy
            print(f"  Accuratezza in Training (In-Sample) : {ai.train_accuracy*100:.2f}%")
            print(f"  Accuratezza Out-of-Sample (Holdout)  : {ai.accuracy*100:.2f}%")
            print(f"  Differenza (Training vs Out-of-Sample): {diff*100:.2f}%")
            if diff > 0.10:
                print("⚠️ WARNING: Possibile Overfitting! Lo scarto supera il 10%.")
            print(f"  F1-Score Modello   : {ai.f1*100:.2f}%")
            print(f"  Campioni Dataset   : {ai_metrics.get('samples', 0)}")
            
            print("\n📊 IMPORTANZA DELLE FEATURES (Top 10):")
            importances = ai_metrics.get("importances", {})
            for idx, (feat, val) in enumerate(list(importances.items())[:10]):
                print(f"  {idx+1:02d}. {feat:<20}: {val*100:.2f}%")
        print("=" * 120 + "\n")

    # Ripristina la strategy mode originale
    Config.STRATEGY_MODE = original_strategy_mode
    print()

if __name__ == "__main__":
    print("[INIT] Avvio backtest...")
    df = asyncio.run(fetch_data())
    run_backtest(df)
