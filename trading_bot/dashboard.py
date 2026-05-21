import os
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# Configurazione della Pagina Streamlit con stile premium dark-mode
st.set_page_config(
    page_title="Interpretability & Feature Diagnostics Hub",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Sleek CSS per l'estetica Premium (Glassmorphism, sfumature coerenti)
st.markdown("""
<style>
    /* Styling generale per eliminare elementi di default brutti */
    .stApp {
        background-color: #0E1117;
        color: #E0E6ED;
        font-family: 'Inter', 'Outfit', sans-serif;
    }
    
    /* Titoli ed intestazioni */
    h1, h2, h3 {
        color: #FFFFFF !important;
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }
    
    /* Contenitori Glassmorphic */
    .glass-card {
        background: rgba(22, 26, 34, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
    }
    
    .kpi-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.5) 0%, rgba(15, 23, 42, 0.8) 100%);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 20px 0 rgba(0, 0, 0, 0.2);
        transition: transform 0.2s ease-in-out;
    }
    
    .kpi-card:hover {
        transform: translateY(-2px);
        border-color: rgba(99, 102, 241, 0.4);
    }
    
    .kpi-value {
        font-size: 2.2rem;
        font-weight: 800;
        margin: 5px 0;
        background: linear-gradient(90deg, #6366F1 0%, #A5B4FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .kpi-title {
        font-size: 0.9rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* Alerts customizzati */
    .custom-alert {
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 15px;
        border-left: 5px solid;
    }
    .alert-stable {
        background-color: rgba(16, 185, 129, 0.1);
        border-left-color: #10B981;
        color: #A7F3D0;
    }
    .alert-specialist {
        background-color: rgba(59, 130, 246, 0.1);
        border-left-color: #3B82F6;
        color: #BFDBFE;
    }
    .alert-overfit {
        background-color: rgba(245, 158, 11, 0.1);
        border-left-color: #F59E0B;
        color: #FDE68A;
    }
    .alert-noisy {
        background-color: rgba(239, 68, 68, 0.1);
        border-left-color: #EF4444;
        color: #FECACA;
    }
</style>
""", unsafe_allow_html=True)

REPORT_PATH = os.path.join("data", "feature_diagnostics_report.json")

# Helper per caricare il report JSON
@st.cache_data
def load_report(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)

# Sidebar di navigazione premium
st.sidebar.markdown("""
<div style='text-align: center; padding-bottom: 20px;'>
    <h2 style='color: #6366F1 !important; margin-bottom: 5px;'>🔬 SHAP AI Hub</h2>
    <span style='color: #64748B; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1.5px;'>Trading Interpretability</span>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

report_data = load_report(REPORT_PATH)

if report_data is None:
    st.error("⚠️ Il report diagnostico non è presente o non è stato ancora calcolato.")
    st.warning("Esegui il calcolo dei valori SHAP out-of-line cliccando il bottone sottostante oppure avviando: `python run_diagnostics.py` nel tuo terminale.")
    
    if st.button("🚀 Esegui Diagnostica SHAP Adesso"):
        with st.spinner("Calcolo SHAP in corso... Questo richiederà circa 30-60 secondi per via del calcolo rolling dei fold walk-forward."):
            try:
                from core.diagnostics import FeatureDiagnostics
                diag = FeatureDiagnostics()
                diag.run_diagnostics()
                st.success("🎉 Diagnostica SHAP completata con successo!")
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante il calcolo: {e}")
    st.stop()

# Estrazione dei dati dal report
metadata = report_data["metadata"]
global_diag = report_data["global_diagnostics"]
rolling_diag = report_data["rolling_diagnostics"]
anomalies = report_data["anomalies"]

features_list = metadata["features_list"]

# Menu di navigazione sidebar
menu = st.sidebar.radio(
    "SEZIONE DASHBOARD",
    [
        "🏆 Executive Summary",
        "📊 Global & Regime Attributions",
        "🌊 Local Trade Explanations",
        "🔄 Rolling Feature Stability",
        "🧬 SHAP Dependency Analysis",
        "🛠️ Structural Recommendations"
    ]
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Ultimo Aggiornamento:**  \n`{metadata['timestamp'][:19].replace('T', ' ')}`")
st.sidebar.markdown(f"**Folds Analizzati:** `{metadata['num_folds']}`")
st.sidebar.markdown(f"**Campioni Storici:** `{metadata['num_samples']}`")

# ------------------------------------------------------------------ #
#  🏆 TAB 1: EXECUTIVE SUMMARY                                      #
# ------------------------------------------------------------------ #
if menu == "🏆 Executive Summary":
    st.markdown("<h1>🏆 Executive Interpretability Summary</h1>", unsafe_allow_html=True)
    st.write("Benvenuto nel centro di controllo interpretativo del tuo trading AI. Di seguito trovi i parametri strutturali chiave ricavati dall'analisi di stabilità temporale e dal valore dei payoff SHAP.")
    
    # Calcolo KPI
    stable_drivers = [f for f, d in anomalies.items() if d["classification"] == "STABLE_DRIVER"]
    regime_specs = [f for f, d in anomalies.items() if d["classification"] == "REGIME_SPECIALIST"]
    overfit_cond = [f for f, d in anomalies.items() if d["classification"] == "POTENTIAL_OVERFIT"]
    noisy_feats = [f for f, d in anomalies.items() if d["classification"] == "NOISY"]
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Stable Drivers</div>
            <div class="kpi-value">{len(stable_drivers)}</div>
            <div style="color: #10B981; font-size: 0.85rem;">🟢 Feature Robuste</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Regime Specialists</div>
            <div class="kpi-value">{len(regime_specs)}</div>
            <div style="color: #3B82F6; font-size: 0.85rem;">🔵 Regime-Specifiche</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Potential Overfit</div>
            <div class="kpi-value">{len(overfit_cond)}</div>
            <div style="color: #F59E0B; font-size: 0.85rem;">⚠️ Instabilità Rilevata</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Noisy Features</div>
            <div class="kpi-value">{len(noisy_feats)}</div>
            <div style="color: #EF4444; font-size: 0.85rem;">❌ Suggerita Rimozione</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<h3>📌 Panoramica Anomalie & Avvisi Rapidi</h3>", unsafe_allow_html=True)
    
    # Alerts dinamici per le feature
    for feat, data in anomalies.items():
        cls = data["classification"]
        if cls == "STABLE_DRIVER":
            st.markdown(f"""
            <div class="custom-alert alert-stable">
                <strong>🟢 STABLE DRIVER | {feat}</strong><br/>
                {data['reason']} - <em>Mantenere. {data['action']}</em>
            </div>
            """, unsafe_allow_html=True)
        elif cls == "REGIME_SPECIALIST":
            st.markdown(f"""
            <div class="custom-alert alert-specialist">
                <strong>🔵 REGIME SPECIALIST | {feat}</strong><br/>
                {data['reason']} - <em>Modello Specifico. {data['action']}</em>
            </div>
            """, unsafe_allow_html=True)
        elif cls == "POTENTIAL_OVERFIT":
            st.markdown(f"""
            <div class="custom-alert alert-overfit">
                <strong>⚠️ POTENTIAL OVERFIT ALERT | {feat}</strong><br/>
                {data['reason']} - <strong>{data['action']}</strong>
            </div>
            """, unsafe_allow_html=True)
        elif cls == "NOISY":
            st.markdown(f"""
            <div class="custom-alert alert-noisy">
                <strong>❌ NOISY / UNSTABLE FEATURE | {feat}</strong><br/>
                {data['reason']} - <strong>{data['action']}</strong>
            </div>
            """, unsafe_allow_html=True)

# ------------------------------------------------------------------ #
#  📊 TAB 2: GLOBAL & REGIME ATTRIBUTIONS                             #
# ------------------------------------------------------------------ #
elif menu == "📊 Global & Regime Attributions":
    st.markdown("<h1>📊 Global & Regime-Specific Attributions</h1>", unsafe_allow_html=True)
    st.write("Confronto tra l'importanza basata sul valore di gioco cooperativo SHAP (Mean Absolute SHAP) e l'importanza classica nativa ricavata dai nodi dell'albero XGBoost (Gain/Weight).")

    regime_choice = st.radio("Seleziona Regime Modello", ["TRENDING", "RANGING"], horizontal=True)
    reg_key = regime_choice.lower()
    
    shap_imp = global_diag[reg_key]["shap_importance"]
    xgb_imp = global_diag[reg_key]["xgb_importance"]
    
    # Conversione in DataFrame
    df_compare = pd.DataFrame({
        "Feature": features_list,
        "SHAP Importance %": [shap_imp.get(f, 0.0) * 100 for f in features_list],
        "XGBoost Importance %": [xgb_imp.get(f, 0.0) * 100 for f in features_list]
    }).sort_values(by="SHAP Importance %", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df_compare["Feature"],
        x=df_compare["SHAP Importance %"],
        name="SHAP Attribution %",
        orientation="h",
        marker=dict(color="rgba(99, 102, 241, 0.8)", line=dict(color="#6366F1", width=1))
    ))
    fig.add_trace(go.Bar(
        y=df_compare["Feature"],
        x=df_compare["XGBoost Importance %"],
        name="XGBoost Gain %",
        orientation="h",
        marker=dict(color="rgba(148, 163, 184, 0.4)", line=dict(color="#94A3B8", width=1))
    ))

    fig.update_layout(
        title=f"Confronto Importanza Feature - Modello {regime_choice}",
        barmode="group",
        height=500,
        template="plotly_dark",
        margin=dict(l=150, r=20, t=50, b=50),
        xaxis_title="Importanza Percentuale (%)",
        yaxis_title="Feature",
        legend=dict(x=0.8, y=0.1)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("<h3>⚖️ Analisi Comparativa dei due Regimi</h3>", unsafe_allow_html=True)
    st.write("Di seguito puoi vedere affiancate le importanze SHAP reali per il regime Trending e Ranging. Nota come la sensibilità del modello cambia radicalmente a seconda della struttura di mercato.")
    
    df_reg_compare = pd.DataFrame({
        "Feature": features_list,
        "Trending Model (SHAP)": [global_diag["trending"]["shap_importance"].get(f, 0.0) * 100 for f in features_list],
        "Ranging Model (SHAP)": [global_diag["ranging"]["shap_importance"].get(f, 0.0) * 100 for f in features_list]
    }).sort_values(by="Trending Model (SHAP)", ascending=True)
    
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        y=df_reg_compare["Feature"],
        x=df_reg_compare["Trending Model (SHAP)"],
        name="📈 TRENDING Regime",
        orientation="h",
        marker=dict(color="#10B981")
    ))
    fig2.add_trace(go.Bar(
        y=df_reg_compare["Feature"],
        x=df_reg_compare["Ranging Model (SHAP)"],
        name="📉 RANGING Regime",
        orientation="h",
        marker=dict(color="#3B82F6")
    ))
    
    fig2.update_layout(
        title="TRENDING vs RANGING - Payoff SHAP dei due Modelli Specializzati",
        barmode="group",
        height=550,
        template="plotly_dark",
        margin=dict(l=150, r=20, t=50, b=50),
        xaxis_title="Importanza Percentuale (%)",
        yaxis_title="Feature"
    )
    st.plotly_chart(fig2, use_container_width=True)

# ------------------------------------------------------------------ #
#  🌊 TAB 3: LOCAL TRADE EXPLANATIONS SIMULATOR                      #
# ------------------------------------------------------------------ #
elif menu == "🌊 Local Trade Explanations":
    st.markdown("<h1>🌊 Local Trade Explanations Simulator</h1>", unsafe_allow_html=True)
    st.write("Simula un segnale tecnico inserendo valori custom o usa i pulsanti di default per analizzare *esattamente* perché il modello AI approva o scarta questo trade, scomponendo le forze in tempo reale.")
    
    # Inizializzatore del sotto-modulo live
    from core.diagnostics import FeatureDiagnostics
    from core.ai_engine import TradingAI
    ai = TradingAI()
    
    col_l, col_r = st.columns([1, 2])
    
    with col_l:
        st.markdown("<h3>🛠️ Configura Segnale</h3>", unsafe_allow_html=True)
        regime = st.selectbox("Regime di Mercato Rilevato", ["TRENDING", "RANGING"])
        
        # Slider per ciascuna feature tecnica
        inputs = {}
        inputs["rsi"] = st.slider("RSI (14)", 0.0, 100.0, 50.0, step=1.0)
        inputs["adx"] = st.slider("ADX (14)", 0.0, 100.0, 35.0 if regime == "TRENDING" else 20.0, step=1.0)
        inputs["atr_pct"] = st.slider("ATR %", 0.0, 5.0, 1.2, step=0.1)
        inputs["ema_slope"] = st.slider("EMA Slope (Trend)", -3.0, 3.0, 0.5, step=0.1)
        inputs["close_vs_ema"] = st.slider("Close vs EMA 200 %", -10.0, 10.0, 1.5, step=0.1)
        inputs["dist_to_psy"] = st.slider("Distanza da Livello Psicologico %", 0.0, 2.0, 0.4, step=0.1)
        inputs["volume_ratio"] = st.slider("Volume Ratio", 0.1, 5.0, 1.5, step=0.1)
        inputs["bb_position"] = st.slider("Posizione Macro Range [0,1]", 0.0, 1.0, 0.7, step=0.05)
        inputs["engulfing"] = st.selectbox("Engulfing Pattern", [0.0, 1.0, -1.0])
        inputs["in_fvg"] = st.selectbox("Inside FVG", [0, 1, -1])
        inputs["near_sr"] = st.selectbox("Vicino Supporto/Resistenza", [0, 1, -1])
        inputs["volume_bias_enc"] = st.selectbox("Volume Bias Encoded", [0, 1, -1])
        inputs["regime"] = 1 if regime == "TRENDING" else 0
        
        submit = st.button("🌊 Scomponi Forze SHAP", use_container_width=True)

    with col_r:
        st.markdown("<h3>🎯 Report delle Forze di Attribuzione</h3>", unsafe_allow_html=True)
        
        if submit or 'first_run' not in st.session_state:
            st.session_state['first_run'] = True
            
            # Calcolo spiegazione SHAP locale
            diag = FeatureDiagnostics()
            res = diag.explain_local_sample(inputs, regime, ai)
            
            if res["status"] == "success":
                expected_val = res["expected_value_log_odds"]
                raw_pred = res["raw_prediction_prob"]
                attrs = res["attributions"]
                
                # Conversione in DataFrame
                df_local = pd.DataFrame(attrs)
                df_local["color"] = df_local["shap_value"].apply(lambda val: "#10B981" if val >= 0 else "#EF4444")
                df_local = df_local.sort_values(by="shap_value", ascending=True)
                
                # Plotly Horizontal Bar per scomposizione locale
                fig_local = go.Figure()
                fig_local.add_trace(go.Bar(
                    y=df_local["feature"],
                    x=df_local["shap_value"],
                    orientation="h",
                    marker_color=df_local["color"],
                    text=[f"{v:+.4f}" for v in df_local["shap_value"]],
                    textposition="outside"
                ))
                
                # Titoli e Layout
                fig_local.update_layout(
                    title=f"Spiegazione Decisione Trade - Probabilità Grezza Modello: {raw_pred*100:.2f}%",
                    height=550,
                    template="plotly_dark",
                    margin=dict(l=150, r=80, t=50, b=50),
                    xaxis_title="Payoff SHAP (Log-Odds Attribution)",
                    yaxis_title="Feature Tecnica"
                )
                
                st.plotly_chart(fig_local, use_container_width=True)
                
                # KPI di Probabilità
                p_calibrated = ai.predict_probability(inputs)
                
                st.markdown(f"""
                <div class="glass-card" style="text-align: center;">
                    <h4>🧠 Calcolo del Rischio e Probability Routing:</h4>
                    <span style="font-size: 1.1rem; color: #94A3B8;">Probabilità Grezza (XGBoost): <strong>{raw_pred*100:.2f}%</strong></span><br/>
                    <span style="font-size: 1.5rem; color: #6366F1;">Probabilità Calibrata Isolana/Sigmoide: <strong>{p_calibrated:.2f}%</strong></span><br/>
                    <span style="font-size: 0.95rem; color: #94A3B8; margin-top: 10px; display: inline-block;">
                        Soglia AI Minima per Invio Ordine: <strong>{Config.AI_MIN_CONFIDENCE}%</strong>
                    </span>
                </div>
                """, unsafe_allow_html=True)
                
                if p_calibrated >= Config.AI_MIN_CONFIDENCE:
                    st.success("🟢 SEGNALE APPROVATO: Il segnale tecnico supera il filtro calibrazione Elite ed è abilitato all'esecuzione live.")
                else:
                    st.error("🔴 SEGNALE FILTRATO: Il segnale non raggiunge il livello minimo di confidenza calibrata e viene neutralizzato.")
            else:
                st.error(f"Impossibile simulare spiegazione locale: {res.get('message')}")

# ------------------------------------------------------------------ #
#  🔄 TAB 4: ROLLING FEATURE STABILITY TIMELINE                      #
# ------------------------------------------------------------------ #
elif menu == "🔄 Rolling Feature Stability":
    st.markdown("<h1>🔄 Rolling Feature Stability & Drift Timeline</h1>", unsafe_allow_html=True)
    st.write("Verifica se le relazioni tra indicatori sono costanti nel tempo o se soffrono di **non-stationarity (drift)** tracciando l'evoluzione delle SHAP attributions su tutti i fold walk-forward storici.")

    regime_wf = st.radio("Seleziona Regime", ["TRENDING", "RANGING"], horizontal=True)
    reg_key = "rolling_importances_" + regime_wf.lower()
    
    # Recupera i dati rolling
    rolling_imps = rolling_diag[reg_key]
    folds_data = rolling_diag["folds"]
    
    fold_indices = [f["fold_idx"] for f in folds_data]
    fold_times = [f["test_start_time"][:10] for f in folds_data]
    
    # Seleziona feature da visualizzare
    selected_features = st.multiselect(
        "Seleziona Feature da Tracciare",
        features_list,
        default=features_list[:5]
    )
    
    if selected_features:
        fig_timeline = go.Figure()
        for feat in selected_features:
            fig_timeline.add_trace(go.Scatter(
                x=fold_indices,
                y=rolling_imps[feat],
                mode="lines+markers",
                name=feat,
                line=dict(width=2.5),
                hovertemplate=f"<b>{feat}</b><br/>Fold: %{{x}}<br/>Attribution SHAP: %{{y:.4f}}<extra></extra>"
            ))
            
        fig_timeline.update_layout(
            title=f"Evoluzione Temporale dell'Importanza SHAP - Modello {regime_wf}",
            xaxis=dict(
                tickmode="array",
                tickvals=fold_indices,
                ticktext=[f"F{idx} ({time})" for idx, time in zip(fold_indices, fold_times)],
                title="Fold Temporale (Walk-Forward Test Window)"
            ),
            yaxis_title="Mean Absolute SHAP Value",
            height=550,
            template="plotly_dark",
            legend=dict(orientation="h", y=1.1, x=0)
        )
        st.plotly_chart(fig_timeline, use_container_width=True)
    else:
        st.warning("Seleziona almeno una feature tecnica per tracciare la timeline.")

    # Statistiche di stabilità globale
    stability_scores = rolling_diag["stability_scores"][regime_wf.lower()]
    g_stability = stability_scores["global_stability_index"]
    
    st.markdown("<h3>🎯 Indice di Stabilità Globale del Modello</h3>", unsafe_allow_html=True)
    
    # Colore indicatore basato sul valore
    color_g = "#10B981" if g_stability >= 0.70 else ("#F59E0B" if g_stability >= 0.40 else "#EF4444")
    
    st.markdown(f"""
    <div class="glass-card" style="border-left: 6px solid {color_g};">
        <h4 style="margin:0;">Indice di Stabilità del Rango (Spearman's Rho Medio): <span style="color: {color_g}; font-size: 1.4rem;">{g_stability:.2f}</span></h4>
        <p style="margin-top: 10px; color:#94A3B8;">
            L'indice calcola la correlazione dell'ordine di importanza degli indicatori tra finestre temporali adiacenti. 
            Valori vicini a <strong>1.0</strong> indicano che le feature mantengono la stessa utilità, mentre valori negativi o prossimi a zero 
            rivelano forte instabilità e instradamento errato a causa del non-stationarity di mercato.
        </p>
    </div>
    """, unsafe_allow_html=True)

# ------------------------------------------------------------------ #
#  🧬 TAB 5: SHAP DEPENDENCY ANALYSIS                                #
# ------------------------------------------------------------------ #
elif menu == "🧬 SHAP Dependency Analysis":
    st.markdown("<h1>🧬 SHAP Dependency & Non-Linear Interaction Plots</h1>", unsafe_allow_html=True)
    st.write("Identifica le soglie matematiche precise alle quali un indicatore inizia a esercitare un impatto positivo o negativo sulla probabilità di vincita del trade.")

    regime_dep = st.radio("Seleziona Regime", ["TRENDING", "RANGING"], horizontal=True)
    reg_key = regime_dep.lower()
    
    samples = global_diag[reg_key]["samples"]
    
    if not samples:
        st.warning("Sottoinsieme di campioni insufficienti per compilare la dependency analysis. Addestra il modello globale con più record.")
    else:
        # Ricostruiamo la matrice delle feature e dei relativi shap
        feat_data = []
        shap_data = []
        
        for s in samples:
            feat_data.append(s["features"])
            shap_data.append(s["shap"])
            
        df_feats = pd.DataFrame(feat_data)
        df_shaps = pd.DataFrame(shap_data, columns=features_list)
        
        target_feat = st.selectbox("Seleziona Feature da Analizzare", features_list)
        
        # Scatter Plot della dipendenza
        fig_dep = go.Figure()
        fig_dep.add_trace(go.Scatter(
            x=df_feats[target_feat],
            y=df_shaps[target_feat],
            mode="markers",
            marker=dict(
                size=8,
                color=df_shaps[target_feat],
                colorscale="Bluered",
                showscale=True,
                colorbar=dict(title="Impatto SHAP", thickness=15)
            ),
            hovertemplate=f"Valore Feature: %{{x:.4f}}<br/>Impatto SHAP: %{{y:.4f}}<extra></extra>"
        ))
        
        # Aggiunta linea orizzontale neutra (y = 0)
        fig_dep.add_shape(
            type="line",
            x0=df_feats[target_feat].min(),
            y0=0,
            x1=df_feats[target_feat].max(),
            y1=0,
            line=dict(color="rgba(255, 255, 255, 0.3)", width=1.5, dash="dash")
        )
        
        fig_dep.update_layout(
            title=f"Analisi di Dipendenza SHAP: {target_feat} (Modello {regime_dep})",
            xaxis_title=f"Valore Reale di {target_feat}",
            yaxis_title="Impatto SHAP (Log-Odds)",
            height=500,
            template="plotly_dark"
        )
        st.plotly_chart(fig_dep, use_container_width=True)
        
        st.markdown("<h3>💡 Come interpretare questo grafico</h3>", unsafe_allow_html=True)
        st.markdown("""
        * I punti sopra la linea tratteggiata **y = 0** rappresentano valori della feature che aumentano la probabilità stimata di successo del trade (spingono verso BUY).
        * I punti sotto la linea **y = 0** riducono la probabilità di successo del trade.
        * La forma della distribuzione mostra se l'indicatore ha una relazione lineare o se presenta comportamenti asimmetrici (es. RSI che diventa estremamente negativo solo a valori estremi di ipercomprato/ipervenduto).
        """)

# ------------------------------------------------------------------ #
#  🛠️ TAB 6: STRUCTURAL RECOMMENDATIONS                               #
# ------------------------------------------------------------------ #
elif menu == "🛠️ Structural Recommendations":
    st.markdown("<h1>🛠️ Structural Recommendations & Regularization Panel</h1>", unsafe_allow_html=True)
    st.write("Tabella comparativa di audit per le feature. Rileva i punti critici di overfitting e offre consigli per la regolarizzazione del dataset.")

    rec_records = []
    for feat, data in anomalies.items():
        rec_records.append({
            "Feature": feat,
            "Classificazione": data["classification"],
            "Attribution (Trending)": f"{data['trending_importance']*100:.3f}%",
            "Attribution (Ranging)": f"{data['ranging_importance']*100:.3f}%",
            "Diagnostica": data["reason"],
            "Raccomandazione": data["action"]
        })
        
    df_rec = pd.DataFrame(rec_records)
    
    # Riconfigura nomi colonne per visualizzazione premium
    st.dataframe(
        df_rec,
        column_config={
            "Feature": st.column_config.TextColumn("Feature", width="medium"),
            "Classificazione": st.column_config.TextColumn("Classificazione", width="medium"),
            "Attribution (Trending)": st.column_config.TextColumn("Payoff Trending", width="small"),
            "Attribution (Ranging)": st.column_config.TextColumn("Payoff Ranging", width="small"),
            "Diagnostica": st.column_config.TextColumn("Diagnostica di Stabilità", width="large"),
            "Raccomandazione": st.column_config.TextColumn("Azione Ottimizzante", width="large")
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.markdown("<h3>🛠️ Linee Guida Generali per l'Ottimizzazione dei Segnali AI</h3>", unsafe_allow_html=True)
    st.markdown("""
    1. **Eliminare le Noisy Features**: Feature classificate come `NOISY` hanno una correlazione bassissima out-of-sample e presentano solo rumore di campionamento. Eliminarle abbatterà la dimensionalità del dataset storico del 15%, riducendo i tempi di addestramento walk-forward.
    2. **Regularizzare le Feature con Potential Overfit**: Indicatori che hanno forte dominanza in addestramento ma oscillano del 200% out-of-sample (es. coefficiente di variazione elevato rolling) creano falsi trade Elite e falsano il Kelly Sizing. Aumenta i parametri `min_child_weight` (es. a 5 o 10) e imposta `gamma` > 0.1 per queste feature nel modello XGBoost.
    3. **Struttura per Modello**: Le feature `REGIME_SPECIALIST` devono essere monitorate per regime. Ad esempio, ADX è essenziale solo per il trending model, mentre i livelli psicologici o EMA Slope sono dominanti nel Ranging. Assicurarsi che i pesi della strategia base non creino conflitti con il routing automatico dell'AI.
    """)
