"""
core/regime_analyzer.py — Performance & Regime Analytics Engine
Redigge un'analisi quantitativa avanzata delle performance del trading bot decomponendo 
i risultati su regimi, sessioni, giorni della settimana, volatilità e classi di confidenza.
"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

class RegimePerformanceAnalyzer:
    @staticmethod
    def tag_trades(trades_list: list, df: pd.DataFrame = None) -> pd.DataFrame:
        """
        Arricchisce i trade con etichette multi-dimensionali basate sul momento di ingresso.
        """
        if not trades_list:
            return pd.DataFrame()
            
        trades_df = pd.DataFrame(trades_list).copy()
        
        # Gestione timestamp d'ingresso
        if "entry_time" in trades_df.columns:
            trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
        else:
            trades_df["entry_time"] = pd.to_datetime(datetime.utcnow())
            
        # 1. Sessione di Trading UTC
        # Asia: 00-08 | Londra: 08-16 | NY: 16-24
        hour = trades_df["entry_time"].dt.hour
        trades_df["session"] = np.where(
            (hour >= 0) & (hour < 8), "ASIA",
            np.where((hour >= 8) & (hour < 16), "LONDON", "NY")
        )
        
        # 2. Giorno della settimana
        trades_df["weekday"] = trades_df["entry_time"].dt.day_name()
        
        # 3. Regimi di Volatilità (basati su percentili ATR%)
        # Se non abbiamo il df macro, usiamo i dati dei trade per stimare i percentili
        if df is not None and "atr_pct" in df.columns:
            atr_series = df["atr_pct"].dropna()
        elif "atr_pct" in trades_df.columns:
            atr_series = trades_df["atr_pct"].dropna()
        else:
            atr_series = pd.Series([0.5] * 10)
            
        if not atr_series.empty:
            vol_low_thresh = float(atr_series.quantile(0.33))
            vol_high_thresh = float(atr_series.quantile(0.66))
        else:
            vol_low_thresh, vol_high_thresh = 0.3, 0.6
            
        # Assegna tag di volatilità
        if "atr_pct" not in trades_df.columns:
            trades_df["atr_pct"] = 0.5
            
        trades_df["volatility_regime"] = np.where(
            trades_df["atr_pct"] < vol_low_thresh, "LOW",
            np.where(trades_df["atr_pct"] > vol_high_thresh, "HIGH", "MEDIUM")
        )
        
        # 4. Proxy del Funding Environment (basato su close_vs_ema)
        # Bullish: close_vs_ema > 0.5 | Bearish: close_vs_ema < -0.5 | Neutral: altrimenti
        if "close_vs_ema" not in trades_df.columns:
            trades_df["close_vs_ema"] = 0.0
            
        trades_df["funding_env"] = np.where(
            trades_df["close_vs_ema"] > 0.5, "BULLISH_FUNDING",
            np.where(trades_df["close_vs_ema"] < -0.5, "BEARISH_FUNDING", "NEUTRAL_FUNDING")
        )
        
        # 5. Classi di Confidenza AI
        if "ai_prob" not in trades_df.columns:
            trades_df["ai_prob"] = 50.0
            
        trades_df["confidence_bucket"] = np.where(
            trades_df["ai_prob"] <= 55.0, "LOW",
            np.where(trades_df["ai_prob"] > 70.0, "HIGH", "MEDIUM")
        )
        
        # Normalizzazione market regime a stringa
        if "regime" in trades_df.columns:
            trades_df["regime"] = trades_df["regime"].apply(
                lambda r: "TRENDING" if str(r).upper() in ("1", "TRENDING") else "RANGING"
            )
        else:
            trades_df["regime"] = "RANGING"
            
        return trades_df

    @staticmethod
    def calculate_sharpe(returns: pd.Series, periods: int = 365) -> float:
        """
        Calcola lo Sharpe ratio annualizzato in modo robusto.
        """
        if returns.empty or returns.std() == 0:
            return 0.0
        return float((returns.mean() / returns.std()) * np.sqrt(periods))

    @staticmethod
    def calculate_sortino(returns: pd.Series, periods: int = 365) -> float:
        """
        Calcola il Sortino ratio annualizzato concentrandosi solo sulle deviazioni negative.
        """
        if returns.empty:
            return 0.0
        downside_returns = returns[returns < 0]
        if downside_returns.empty or downside_returns.std() == 0:
            # Se non ci sono perdite, il Sortino è teoricamente infinito o alto
            return float((returns.mean() / 1e-9) * np.sqrt(periods)) if returns.mean() > 0 else 0.0
        return float((returns.mean() / downside_returns.std()) * np.sqrt(periods))

    @classmethod
    def compute_regime_metrics(cls, tagged_df: pd.DataFrame) -> dict:
        """
        Calcola le metriche di performance aggregate per ciascun regime.
        """
        if tagged_df.empty:
            return {}
            
        dimensions = ["regime", "volatility_regime", "session", "weekday", "confidence_bucket", "funding_env"]
        report = {}
        
        for dim in dimensions:
            report[dim] = {}
            grouped = tagged_df.groupby(dim)
            
            for name, group in grouped:
                total_trades = len(group)
                wins = len(group[group["result"] == "WIN"])
                partial_wins = len(group[group["result"] == "WIN_PARTIAL"])
                losses = len(group[group["result"] == "LOSS"])
                breakevens = len(group[group["result"] == "BREAKEVEN"])
                
                total_wins = wins + partial_wins
                trade_con_esito = total_wins + losses
                
                win_rate = (total_wins / trade_con_esito * 100) if trade_con_esito > 0 else 0.0
                net_pnl = float(group["pnl"].sum())
                
                # Profit Factor
                gross_wins = float(group[group["pnl"] > 0]["pnl"].sum())
                gross_losses = float(group[group["pnl"] < 0]["pnl"].abs().sum())
                profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (gross_wins if gross_wins > 0 else 1.0)
                
                # Expectancy
                avg_win = float(group[group["pnl"] > 0]["pnl"].mean()) if len(group[group["pnl"] > 0]) > 0 else 0.0
                avg_loss = float(group[group["pnl"] < 0]["pnl"].mean()) if len(group[group["pnl"] < 0]) > 0 else 0.0
                
                # Expectancy Formula: (P_win * Avg_Win) + (P_loss * Avg_Loss)
                p_win = total_wins / total_trades
                p_loss = losses / total_trades
                expectancy = (p_win * avg_win) + (p_loss * avg_loss)
                
                # Sharpe & Sortino (trade-level come proxy annualizzato se trades > 3)
                if total_trades >= 3:
                    # Calcolo rendimenti percentuali basati sulla variazione del pnl rispetto al saldo precedente
                    # Per semplicità usiamo i PnL assoluti divisi per una base arbitraria o lo std dev dei PnL
                    pnl_series = group["pnl"]
                    sharpe = cls.calculate_sharpe(pnl_series, periods=100) # 100 trades annuali equivalenti
                    sortino = cls.calculate_sortino(pnl_series, periods=100)
                else:
                    sharpe, sortino = 0.0, 0.0
                    
                # Max Drawdown specifico per la serie temporale di questo regime
                cum_pnl = group["pnl"].cumsum()
                cum_peaks = cum_pnl.cummax()
                drawdowns = cum_peaks - cum_pnl
                max_dd = float(drawdowns.max()) if not drawdowns.empty else 0.0
                
                report[dim][str(name)] = {
                    "total_trades": total_trades,
                    "wins": wins,
                    "partial_wins": partial_wins,
                    "losses": losses,
                    "breakevens": breakevens,
                    "win_rate_pct": win_rate,
                    "net_pnl": net_pnl,
                    "profit_factor": profit_factor,
                    "expectancy": expectancy,
                    "sharpe_ratio": sharpe,
                    "sortino_ratio": sortino,
                    "max_drawdown": max_dd
                }
                
        return report

    @staticmethod
    def build_transition_matrix(df: pd.DataFrame) -> dict:
        """
        Costruisce la matrice di transizione di Markov per il regime di mercato e la volatilità.
        """
        if df is None or df.empty:
            return {}
            
        # Determina regimi e volatilità su base storica
        df_states = df.copy()
        
        # 1. Volatility states (LOW, MEDIUM, HIGH)
        if "atr_pct" in df_states.columns:
            low_q = df_states["atr_pct"].quantile(0.33)
            high_q = df_states["atr_pct"].quantile(0.66)
            df_states["vol_state"] = np.where(
                df_states["atr_pct"] < low_q, "LOW",
                np.where(df_states["atr_pct"] > high_q, "HIGH", "MEDIUM")
            )
        else:
            df_states["vol_state"] = "MEDIUM"
            
        # 2. Market states (TRENDING, RANGING)
        if "regime" in df_states.columns:
            df_states["market_state"] = df_states["regime"].apply(
                lambda r: "TRENDING" if str(r) in ("1", "1.0", "TRENDING") else "RANGING"
            )
        elif "market_regime" in df_states.columns:
            df_states["market_state"] = df_states["market_regime"]
        else:
            df_states["market_state"] = "RANGING"
            
        # Crea stato combinato
        df_states["combined_state"] = df_states["market_state"] + "_" + df_states["vol_state"]
        
        # Costruzione matrice di transizione
        states = df_states["combined_state"].dropna()
        if states.empty or len(states) < 2:
            return {}
            
        transitions = pd.crosstab(states.iloc[:-1].values, states.iloc[1:].values, normalize="index")
        
        return {
            "index": list(transitions.index),
            "columns": list(transitions.columns),
            "matrix": transitions.values.tolist()
        }

    @staticmethod
    def transition_performance_analysis(tagged_df: pd.DataFrame, df: pd.DataFrame) -> dict:
        """
        Analizza i risultati dei trade eseguiti entro 5 candele da una transizione di regime.
        """
        if tagged_df.empty or df is None or df.empty:
            return {}
            
        df_states = df.copy()
        if "regime" in df_states.columns:
            df_states["state"] = df_states["regime"].apply(
                lambda r: "TRENDING" if str(r) in ("1", "1.0", "TRENDING") else "RANGING"
            )
        elif "market_regime" in df_states.columns:
            df_states["state"] = df_states["market_regime"]
        else:
            return {}
            
        # Trova gli indici di transizione (dove il regime cambia)
        df_states["shifted_state"] = df_states["state"].shift(1)
        transition_indices = df_states[df_states["state"] != df_states["shifted_state"]].index
        
        # Creiamo un array booleano per i punti vicini alle transizioni (entro 5 candele)
        near_transition = pd.Series(False, index=df_states.index)
        for idx in transition_indices:
            # Trova l'indice posizionale
            try:
                pos = df_states.index.get_loc(idx)
                start_pos = max(0, pos - 5)
                end_pos = min(len(df_states), pos + 5)
                near_transition.iloc[start_pos:end_pos] = True
            except Exception:
                pass
                
        # Tagga ciascun trade come "TRANSITION_ZONE" o "STABLE_ZONE"
        # Mappiamo i timestamp dei trade sui datetime del df macro
        tagged_df = tagged_df.copy()
        
        # Creiamo una maschera basata sulla vicinanza temporale alle transizioni
        transition_datetimes = df_states[near_transition].index
        
        # Se l'indice è datetime
        if isinstance(transition_datetimes, pd.DatetimeIndex):
            # Troviamo la corrispondenza dei trade
            tagged_df["is_transition_trade"] = tagged_df["entry_time"].dt.floor('15min').isin(transition_datetimes)
        else:
            tagged_df["is_transition_trade"] = False
            
        # Metriche aggregate per le due zone
        zones = ["STABLE_ZONE", "TRANSITION_ZONE"]
        result = {}
        
        for zone in zones:
            is_trans = (zone == "TRANSITION_ZONE")
            sub_df = tagged_df[tagged_df["is_transition_trade"] == is_trans]
            
            total = len(sub_df)
            if total == 0:
                result[zone] = {"total_trades": 0, "win_rate": 0.0, "net_pnl": 0.0}
                continue
                
            wins = len(sub_df[sub_df["result"].isin(["WIN", "WIN_PARTIAL"])])
            losses = len(sub_df[sub_df["result"] == "LOSS"])
            trade_con_esito = wins + losses
            
            wr = (wins / trade_con_esito * 100) if trade_con_esito > 0 else 0.0
            pnl = float(sub_df["pnl"].sum())
            
            result[zone] = {
                "total_trades": total,
                "win_rate": wr,
                "net_pnl": pnl
            }
            
        return result

    @staticmethod
    def cluster_trades(tagged_df: pd.DataFrame, n_clusters: int = 4) -> dict:
        """
        Raggruppa i trade in 4 cluster tramite K-Means basandosi sulle caratteristiche quantitative del setup.
        """
        if tagged_df.empty or len(tagged_df) < n_clusters:
            return {}
            
        # Colonne quantitative per il clustering
        features = ["adx", "atr_pct", "volume_ratio", "ai_prob", "setup_quality"]
        
        # Riempimento nan preventivo
        cluster_data = tagged_df[features].copy()
        cluster_data = cluster_data.fillna(cluster_data.mean()).fillna(0.0)
        
        # Scaling
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(cluster_data)
        
        # K-Means
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        tagged_df = tagged_df.copy()
        tagged_df["cluster"] = kmeans.fit_predict(scaled_features)
        
        # Analisi dei cluster
        centers = kmeans.cluster_centers_
        unscaled_centers = scaler.inverse_transform(centers)
        
        cluster_report = {}
        
        # Definiamo etichette descrittive basate sui centroidi
        # Troviamo gli indici ordinati delle feature
        # ["adx", "atr_pct", "volume_ratio", "ai_prob", "setup_quality"]
        for c_id in range(n_clusters):
            c_trades = tagged_df[tagged_df["cluster"] == c_id]
            total = len(c_trades)
            
            if total == 0:
                continue
                
            wins = len(c_trades[c_trades["result"].isin(["WIN", "WIN_PARTIAL"])])
            losses = len(c_trades[c_trades["result"] == "LOSS"])
            trade_con_esito = wins + losses
            wr = (wins / trade_con_esito * 100) if trade_con_esito > 0 else 0.0
            pnl = float(c_trades["pnl"].sum())
            
            # Profilo centroide
            profile = {features[i]: float(unscaled_centers[c_id][i]) for i in range(len(features))}
            
            # Etichettatura dinamica descrittiva
            # adx > 30: High Trend | atr_pct > 0.6: High Vol | ai_prob > 65: High Conf
            desc = []
            if profile["atr_pct"] > 0.6:
                desc.append("High Volatility")
            elif profile["atr_pct"] < 0.3:
                desc.append("Low Volatility")
            else:
                desc.append("Moderate Volatility")
                
            if profile["adx"] > 30:
                desc.append("Strong Trend")
            else:
                desc.append("Mean Reverting")
                
            if profile["ai_prob"] > 65:
                desc.append("High AI Confidence")
            elif profile["ai_prob"] < 54:
                desc.append("Low AI Confidence")
                
            desc_str = " & ".join(desc) if desc else "Standard Trade Profile"
            
            cluster_report[str(c_id)] = {
                "name": f"Cluster {c_id}: {desc_str}",
                "total_trades": total,
                "win_rate_pct": wr,
                "net_pnl": pnl,
                "profile": profile,
                # Salviamo i punti per il grafico
                "trade_coords": c_trades[["adx", "atr_pct", "pnl", "ai_prob", "result"]].to_dict(orient="records")
            }
            
        return cluster_report

    @classmethod
    def generate_report(cls, trades_list: list, df: pd.DataFrame = None, output_path: str = "data/regime_report.json") -> dict:
        """
        Orchestra il pipeline completo di diagnostica e scrive il report JSON finale su disco.
        """
        if not trades_list:
            print("⚠️ Nessun trade fornito per la compilazione del report di regime.")
            return {}
            
        print(f"📊 Avvio Regime Performance Analytics su {len(trades_list)} record...")
        
        # 1. Tagging dei trade
        tagged_df = cls.tag_trades(trades_list, df)
        
        # 2. Performance per ciascun regime
        regime_metrics = cls.compute_regime_metrics(tagged_df)
        
        # 3. Matrice di transizione storica
        transition_matrix = cls.build_transition_matrix(df)
        
        # 4. Analisi delle transizioni
        transition_perf = cls.transition_performance_analysis(tagged_df, df)
        
        # 5. Clustering dei trade
        cluster_analysis = cls.cluster_trades(tagged_df, n_clusters=min(4, len(tagged_df)))
        
        # 6. Generazione delle metriche generali del report
        wins = len(tagged_df[tagged_df["result"] == "WIN"])
        partial_wins = len(tagged_df[tagged_df["result"] == "WIN_PARTIAL"])
        losses = len(tagged_df[tagged_df["result"] == "LOSS"])
        breakevens = len(tagged_df[tagged_df["result"] == "BREAKEVEN"])
        total = len(tagged_df)
        trade_con_esito = wins + partial_wins + losses
        wr = ((wins + partial_wins) / trade_con_esito * 100) if trade_con_esito > 0 else 0.0
        
        # Convert date columns to string for JSON serialization
        trades_list_serializable = []
        if not tagged_df.empty:
            tagged_df_serial = tagged_df.copy()
            if "entry_time" in tagged_df_serial.columns:
                tagged_df_serial["entry_time"] = pd.to_datetime(tagged_df_serial["entry_time"]).dt.strftime("%Y-%m-%d %H:%M:%S")
            trades_list_serializable = tagged_df_serial.to_dict(orient="records")

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "overall_summary": {
                "total_trades": total,
                "wins": wins,
                "partial_wins": partial_wins,
                "losses": losses,
                "breakevens": breakevens,
                "win_rate_pct": wr,
                "net_pnl": float(tagged_df["pnl"].sum())
            },
            "regime_decomposition": regime_metrics,
            "transition_analysis": {
                "markov_transition_matrix": transition_matrix,
                "transition_performance": transition_perf
            },
            "trade_clustering": cluster_analysis,
            "trades_list": trades_list_serializable
        }
        
        # Scrittura su disco
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=4)
            print(f"✅ Report di Regime salvato con successo in {output_path}!")
        except Exception as e:
            print(f"❌ Impossibile salvare il report in {output_path}: {e}")
            
        return report
