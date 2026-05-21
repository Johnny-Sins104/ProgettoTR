"""
Modulo Diagnostica Feature (core/diagnostics.py)
Calcola spiegazioni di interpretabilità avanzate (SHAP) globali, locali e rolling.
Identifica feature instabili, sovradimensionate (overfit) e dipendenti dal regime.
"""
import os
import json
import numpy as np
import pandas as pd
import shap
from scipy.stats import spearmanr
from config import Config
from core.ai_engine import TradingAI, FEATURE_NAMES
from core.walk_forward import WalkForwardPipeline
from core.data_collector import DataCollector
from core.analyzer import TechnicalAnalyzer

class FeatureDiagnostics:
    def __init__(self):
        self.report_path = os.path.join("data", "feature_diagnostics_report.json")
        self.features_path = Config.AI_FEATURES_PATH
        self.price_cache_path = os.path.join("data", "btc_15m_cache.csv")
        if not os.path.exists(self.price_cache_path):
            self.price_cache_path = os.path.join("data", "btc_15m_10k_cache.csv")

    def run_diagnostics(self) -> dict:
        """
        Esegue l'intero pipeline diagnostico out-of-line:
        1. Carica il dataset storico dei prezzi e delle features.
        2. Esegue l'addestramento dei modelli walk-forward.
        3. Calcola i valori SHAP globali e specifici per regime.
        4. Esegue l'analisi rolling SHAP su ciascun fold.
        5. Calcola le metriche di stabilità (Spearman Rank Correlation).
        6. Rileva feature noisy/unstable/overfit.
        7. Esporta il report completo in JSON.
        """
        print("\n🔬 [DIAGNOSTICS] Avvio del pipeline di analisi SHAP & Interpretability...")
        
        # --- PHASE 1: Caricamento Dati ---
        if not os.path.exists(self.price_cache_path):
            raise FileNotFoundError(f"Cache dei prezzi non trovata su {self.price_cache_path}")
            
        df_prices = pd.read_csv(self.price_cache_path, index_col=0, parse_dates=True)
        df_prices = TechnicalAnalyzer().add_indicators(df_prices)
        
        print(f"📊 Candele storiche caricate: {len(df_prices)}")
        
        # Estraiamo le features storiche causali
        features_df = DataCollector.collect_from_backtest_mem(df_prices)
        if features_df.empty:
            raise ValueError("Impossibile generare le features causali dal dataset storico.")

        # --- PHASE 2: Generazione e Addestramento Folds Walk-Forward ---
        wf_folds = WalkForwardPipeline.get_wf_splits(
            len(df_prices),
            N=2000,
            M=500,
            embargo_gap=Config.EMBARGO_GAP,
            df=df_prices
        )
        
        if not wf_folds:
            raise ValueError("Nessun fold generato. Dataset troppo piccolo rispetto all'ampiezza di train N.")
            
        print(f"🧠 [WF] Rilevati {len(wf_folds)} folds walk-forward. Addestramento in corso...")
        ai = TradingAI()
        
        # Addestra tutti i modelli walk-forward per popolare ai._wf_models
        for fold in wf_folds:
            ai.ensure_wf_model(df_prices, features_df, fold)
            
        print("✅ Tutti i modelli walk-forward sono addestrati e pronti.")

        # --- PHASE 3: SHAP Global & Regime-Specific Analysis ---
        # Addestriamo il modello globale (se non pronto) per avere la baseline globale
        global_train_df = DataCollector.generate_training_dataset(
            df=df_prices,
            train_start=0,
            train_end=len(df_prices) - 1,
            features_df=features_df,
            label_horizon=100
        )
        
        print(f"📈 Campioni totali nel dataset globale: {len(global_train_df)}")
        ai.train(features_df=global_train_df, save_to_disk=True)
        
        global_results = self._analyze_global_shap(global_train_df, ai)

        # --- PHASE 4: Rolling SHAP & Feature Stability Analysis ---
        rolling_results = self._analyze_rolling_shap(df_prices, features_df, wf_folds, ai)

        # --- PHASE 5: Rilevamento Anomalie (Unstable, Noisy, Overfit) ---
        anomalies = self._detect_anomalies(global_results, rolling_results)

        # --- PHASE 6: Compilazione Report ---
        report = {
            "metadata": {
                "timestamp": pd.Timestamp.now().isoformat(),
                "num_samples": len(global_train_df),
                "num_features": len(FEATURE_NAMES),
                "features_list": FEATURE_NAMES,
                "num_folds": len(wf_folds)
            },
            "global_diagnostics": global_results,
            "rolling_diagnostics": rolling_results,
            "anomalies": anomalies
        }

        # Salvataggio su file JSON
        os.makedirs(os.path.dirname(self.report_path), exist_ok=True)
        with open(self.report_path, "w") as f:
            json.dump(report, f, indent=4)
            
        print(f"💾 [DIAGNOSTICS] Report diagnostico salvato con successo in: {self.report_path}")
        return report

    def _analyze_global_shap(self, global_train_df: pd.DataFrame, ai: TradingAI) -> dict:
        """Calcola valori SHAP sul dataset globale per entrambi i regimi."""
        print("📈 Calcolo SHAP globale per i due regimi...")
        
        # Segmentazione dei dati
        df_trend = global_train_df[global_train_df["regime"] == 1]
        df_range = global_train_df[global_train_df["regime"] == 0]
        
        X_trend = df_trend[FEATURE_NAMES]
        X_range = df_range[FEATURE_NAMES]
        
        # Analisi regime TRENDING
        trend_shap_importance = {}
        trend_shap_values_raw = []
        trend_expected_value = 0.5
        if ai.trending_model is not None and len(X_trend) > 10:
            explainer_t = shap.TreeExplainer(ai.trending_model)
            shap_output_t = explainer_t(X_trend)
            trend_shap_values = shap_output_t.values
            trend_expected_value = float(explainer_t.expected_value)
            
            # Calcolo importanza globale come media del valore assoluto di SHAP
            mean_abs_shap = np.abs(trend_shap_values).mean(axis=0)
            for idx, feat in enumerate(FEATURE_NAMES):
                trend_shap_importance[feat] = float(mean_abs_shap[idx])
                
            # Campionamento di un sottoinsieme per l'analisi locale/interazioni nel dashboard
            sample_size = min(200, len(X_trend))
            sample_indices = np.random.choice(len(X_trend), sample_size, replace=False)
            
            for s_idx in sample_indices:
                trend_shap_values_raw.append({
                    "features": {k: float(v) for k, v in X_trend.iloc[s_idx].to_dict().items()},
                    "shap": [float(x) for x in trend_shap_values[s_idx]]
                })
        
        # Analisi regime RANGING
        range_shap_importance = {}
        range_shap_values_raw = []
        range_expected_value = 0.5
        if ai.ranging_model is not None and len(X_range) > 10:
            explainer_r = shap.TreeExplainer(ai.ranging_model)
            shap_output_r = explainer_r(X_range)
            range_shap_values = shap_output_r.values
            range_expected_value = float(explainer_r.expected_value)
            
            mean_abs_shap = np.abs(range_shap_values).mean(axis=0)
            for idx, feat in enumerate(FEATURE_NAMES):
                range_shap_importance[feat] = float(mean_abs_shap[idx])
                
            sample_size = min(200, len(X_range))
            sample_indices = np.random.choice(len(X_range), sample_size, replace=False)
            
            for s_idx in sample_indices:
                range_shap_values_raw.append({
                    "features": {k: float(v) for k, v in X_range.iloc[s_idx].to_dict().items()},
                    "shap": [float(x) for x in range_shap_values[s_idx]]
                })
                
        # Estraiamo anche l'importanza nativa XGBoost per confronto
        xgb_importance_trend = ai.get_feature_importance_by_regime("TRENDING")
        xgb_importance_range = ai.get_feature_importance_by_regime("RANGING")

        return {
            "trending": {
                "shap_importance": trend_shap_importance,
                "xgb_importance": xgb_importance_trend,
                "expected_value": trend_expected_value,
                "samples": trend_shap_values_raw
            },
            "ranging": {
                "shap_importance": range_shap_importance,
                "xgb_importance": xgb_importance_range,
                "expected_value": range_expected_value,
                "samples": range_shap_values_raw
            }
        }

    def _analyze_rolling_shap(self, df_prices: pd.DataFrame, features_df: pd.DataFrame, wf_folds: list, ai: TradingAI) -> dict:
        """Calcola l'evoluzione rolling delle SHAP attributions e della stabilità su tutti i folds."""
        print("🔄 Calcolo rolling SHAP e stabilità delle feature...")
        
        folds_data = []
        rolling_importances_t = {feat: [] for feat in FEATURE_NAMES}
        rolling_importances_r = {feat: [] for feat in FEATURE_NAMES}
        
        # Per ciascun fold
        for fold in wf_folds:
            state = ai._wf_models.get(fold.test_start)
            if state is None or state.get("trending_model") is None:
                continue
                
            # Generiamo il dataset di addestramento specifico del fold
            df_subset = DataCollector.generate_training_dataset(
                df=df_prices,
                train_start=fold.train_start,
                train_end=fold.train_end,
                features_df=features_df,
                label_horizon=100
            )
            
            if df_subset.empty:
                continue
                
            df_subset_t = df_subset[df_subset["regime"] == 1]
            df_subset_r = df_subset[df_subset["regime"] == 0]
            
            X_t = df_subset_t[FEATURE_NAMES]
            X_r = df_subset_r[FEATURE_NAMES]
            
            fold_imp_t = {}
            fold_imp_r = {}
            
            # Trending
            if len(X_t) > 5:
                expl_t = shap.TreeExplainer(state["trending_model"])
                shap_val_t = expl_t.shap_values(X_t)
                # In XGBoost v2+, shap_values potrebbe essere di forma (N, M) o (N, M, 2) per binario
                if len(shap_val_t.shape) == 3:
                    shap_val_t = shap_val_t[:, :, 1]
                mean_abs_t = np.abs(shap_val_t).mean(axis=0)
                for idx, feat in enumerate(FEATURE_NAMES):
                    val = float(mean_abs_t[idx])
                    fold_imp_t[feat] = val
                    rolling_importances_t[feat].append(val)
            else:
                for feat in FEATURE_NAMES:
                    fold_imp_t[feat] = 0.0
                    rolling_importances_t[feat].append(0.0)
                    
            # Ranging
            if len(X_r) > 5:
                expl_r = shap.TreeExplainer(state["ranging_model"])
                shap_val_r = expl_r.shap_values(X_r)
                if len(shap_val_r.shape) == 3:
                    shap_val_r = shap_val_r[:, :, 1]
                mean_abs_r = np.abs(shap_val_r).mean(axis=0)
                for idx, feat in enumerate(FEATURE_NAMES):
                    val = float(mean_abs_r[idx])
                    fold_imp_r[feat] = val
                    rolling_importances_r[feat].append(val)
            else:
                for feat in FEATURE_NAMES:
                    fold_imp_r[feat] = 0.0
                    rolling_importances_r[feat].append(0.0)
                    
            folds_data.append({
                "fold_idx": fold.fold_idx,
                "test_start_time": str(fold.test_start_time),
                "trending": fold_imp_t,
                "ranging": fold_imp_r
            })
            
        # Calcolo Spearman Rank Correlation di stabilità tra fold successivi
        stability_trend = self._calculate_stability_score(folds_data, "trending")
        stability_range = self._calculate_stability_score(folds_data, "ranging")
        
        return {
            "folds": folds_data,
            "rolling_importances_trending": rolling_importances_t,
            "rolling_importances_ranging": rolling_importances_r,
            "stability_scores": {
                "trending": stability_trend,
                "ranging": stability_range
            }
        }

    def _calculate_stability_score(self, folds_data: list, regime: str) -> dict:
        """
        Calcola la correlazione di rango (Spearman) tra fold adiacenti per verificare
        se l'ordine di importanza delle feature rimane stabile nel tempo.
        """
        if len(folds_data) < 2:
            return {feat: 1.0 for feat in FEATURE_NAMES}
            
        correlations = []
        for i in range(len(folds_data) - 1):
            imp1 = folds_data[i][regime]
            imp2 = folds_data[i+1][regime]
            
            # Costruiamo i vettori ordinati
            v1 = [imp1[f] for f in FEATURE_NAMES]
            v2 = [imp2[f] for f in FEATURE_NAMES]
            
            # Se uno dei vettori contiene solo zeri, saltiamo
            if sum(v1) == 0 or sum(v2) == 0:
                continue
                
            corr, _ = spearmanr(v1, v2)
            if not np.isnan(corr):
                correlations.append(corr)
                
        mean_global_stability = float(np.mean(correlations)) if correlations else 1.0
        
        # Calcolo anche la variabilità (deviazione standard) dell'importanza di ogni singola feature
        feature_stability = {}
        for feat in FEATURE_NAMES:
            history = [f[regime][feat] for f in folds_data]
            mean_val = np.mean(history)
            std_val = np.std(history)
            coef_var = float(std_val / mean_val) if mean_val > 0 else 0.0
            
            feature_stability[feat] = {
                "mean_importance": float(mean_val),
                "std_importance": float(std_val),
                "coefficient_of_variation": coef_var
            }
            
        return {
            "global_stability_index": mean_global_stability,
            "feature_stability_metrics": feature_stability
        }

    def _detect_anomalies(self, global_results: dict, rolling_results: dict) -> dict:
        """
        Rileva e classifica le feature in base ai loro profili di stabilità e comportamento:
        - Stable Drivers: Importanti e stabili (basso coefficiente di variazione).
        - Regime Specialists: Alta importanza in un regime, bassa nell'altro.
        - Unstable/Noisy: Bassissima stabilità e alto coefficiente di variazione.
        - Overfit Candidates: Alta importanza globale ma instabili rolling o con coefficiente di variazione enorme.
        """
        print("🚨 Analisi delle anomalie e classificazione delle feature...")
        
        classifications = {}
        
        trend_global = global_results["trending"]["shap_importance"]
        range_global = global_results["ranging"]["shap_importance"]
        
        trend_stability = rolling_results["stability_scores"]["trending"]["feature_stability_metrics"]
        range_stability = rolling_results["stability_scores"]["ranging"]["feature_stability_metrics"]
        
        for feat in FEATURE_NAMES:
            t_glob = trend_global.get(feat, 0.0)
            r_glob = range_global.get(feat, 0.0)
            
            t_cv = trend_stability[feat]["coefficient_of_variation"]
            r_cv = range_stability[feat]["coefficient_of_variation"]
            
            # Calcolo score di Regime Dependency
            regime_diff = abs(t_glob - r_glob)
            regime_sum = t_glob + r_glob
            regime_score = float(regime_diff / regime_sum) if regime_sum > 0 else 0.0
            
            classification = "NEUTRAL"
            reason = "Profilo standard."
            action = "Nessuna azione richiesta."
            
            # Regole logiche quantitative di classificazione
            if regime_score > 0.40 and max(t_glob, r_glob) > 0.015:
                classification = "REGIME_SPECIALIST"
                dominant = "TRENDING" if t_glob > r_glob else "RANGING"
                reason = f"Significativamente più rilevante nel regime di {dominant} (Differenza: {regime_diff*100:.2f}%)."
                action = f"Mantenere focalizzata specificatamente sul modello {dominant}."
                
            elif max(t_glob, r_glob) > 0.02 and min(t_cv, r_cv) < 0.35:
                classification = "STABLE_DRIVER"
                reason = "Attribuzione SHAP elevata e costantemente stabile tra tutti i fold temporali."
                action = "Colonna portante della strategia. Mantenere con alta priorità."
                
            elif max(t_glob, r_glob) < 0.005 and max(t_cv, r_cv) > 0.80:
                classification = "NOISY"
                reason = "Contributo marginale al guadagno del modello con estrema volatilità rolling."
                action = "Si raccomanda la rimozione o la sostituzione per ridurre la dimensionalità."
                
            elif max(t_glob, r_glob) > 0.03 and max(t_cv, r_cv) > 0.90:
                classification = "POTENTIAL_OVERFIT"
                reason = "Molto importante globalmente ma estremamente volatile out-of-sample o tra fold successivi."
                action = "Regolarizzare con XGBoost (es. aumentare min_child_weight o max_depth ridotto)."

            classifications[feat] = {
                "feature": feat,
                "classification": classification,
                "trending_importance": t_glob,
                "ranging_importance": r_glob,
                "regime_differential": regime_diff,
                "regime_dependency_score": regime_score,
                "trending_coefficient_of_variation": t_cv,
                "ranging_coefficient_of_variation": r_cv,
                "reason": reason,
                "action": action
            }
            
        return classifications

    def explain_local_sample(self, features_dict: dict, regime: str, ai: TradingAI) -> dict:
        """
        Metodo in tempo reale per estrarre la spiegazione SHAP locale per un singolo trade segnale.
        Utilizzato per il debugger del dashboard.
        """
        model = ai.trending_model if regime == "TRENDING" else ai.ranging_model
        if model is None:
            return {"status": "error", "message": f"Modello {regime} non pronto."}
            
        ordered_features = {k: [features_dict.get(k, 0.0)] for k in FEATURE_NAMES}
        X_pred = pd.DataFrame(ordered_features)
        
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_pred)
        if len(shap_values.shape) == 3:
            shap_values = shap_values[:, :, 1]
            
        expected_value = float(explainer.expected_value)
        p_raw = float(model.predict_proba(X_pred)[0][1])
        
        local_attributions = []
        for idx, feat in enumerate(FEATURE_NAMES):
            local_attributions.append({
                "feature": feat,
                "value": float(X_pred.iloc[0][feat]),
                "shap_value": float(shap_values[0][idx])
            })
            
        return {
            "status": "success",
            "regime": regime,
            "expected_value_log_odds": expected_value,
            "raw_prediction_prob": p_raw,
            "attributions": local_attributions
        }
