import os
import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# ==============================================================================
#  PAGE CONFIGURATION & PREMIUM DARK CUSTOM CSS
# ==============================================================================
st.set_page_config(
    page_title="Market Regime Performance Diagnostics Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Glassmorphic Premium Stylesheet
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
    
    /* Recommendation Cards */
    .custom-alert {
        padding: 18px;
        border-radius: 8px;
        margin-bottom: 18px;
        border-left: 5px solid;
        box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    }
    .alert-edge {
        background-color: rgba(16, 185, 129, 0.08);
        border-left-color: #10B981;
        color: #A7F3D0;
    }
    .alert-restriction {
        background-color: rgba(239, 68, 68, 0.08);
        border-left-color: #EF4444;
        color: #FECACA;
    }
    .alert-neutral {
        background-color: rgba(156, 163, 175, 0.08);
        border-left-color: #9CA3AF;
        color: #E5E7EB;
    }
</style>
""", unsafe_allow_html=True)

REPORT_PATH = os.path.join("data", "regime_report.json")

# Helper to load report
@st.cache_data(ttl=5)
def load_report(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Errore nel caricamento del report: {e}")
        return None

# ==============================================================================
#  SIDEBAR MANAGEMENT
# ==============================================================================
st.sidebar.markdown("""
<div style='text-align: center; padding-bottom: 20px;'>
    <h2 style='color: #6366F1 !important; margin-bottom: 5px;'>📊 Regime Diagnostics</h2>
    <span style='color: #64748B; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1.5px;'>Performance & Market States</span>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")

report_data = load_report(REPORT_PATH)

if report_data is None:
    st.error("⚠️ Il report di regime non è presente o non è stato calcolato.")
    st.warning("Esegui una simulazione di backtest per generare il report: `python run_custom_backtest.py --candles 3000` nel tuo terminale.")
    
    if st.button("🚀 Avvia Backtest Diagnostico Ora"):
        with st.spinner("Esecuzione simulazione backtest in corso..."):
            try:
                import subprocess
                res = subprocess.run(["python", "run_custom_backtest.py", "--candles", "3000"], capture_output=True, text=True)
                st.success("🎉 Backtest completato con successo!")
                st.rerun()
            except Exception as e:
                st.error(f"Errore durante l'esecuzione: {e}")
    st.stop()

# Extract data
overall = report_data["overall_summary"]
regime_decomp = report_data["regime_decomposition"]
transition = report_data["transition_analysis"]
clusters = report_data["trade_clustering"]
trades_list = report_data.get("trades_list", [])

# Menu Sidebar
menu = st.sidebar.radio(
    "SEZIONE DASHBOARD",
    [
        "🏆 Executive Regime Summary",
        "📊 Detailed Regime Analysis",
        "🔥 Joint Cross-Regime Heatmaps",
        "🔄 Markov Transition Analysis",
        "🧬 Trade Clustering K-Means",
        "💼 Interactive Trade Ledger"
    ]
)

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Data Generazione:**  \n`{report_data['generated_at'][:19].replace('T', ' ')}`")
st.sidebar.markdown(f"**Trade Registrati:** `{overall['total_trades']}`")
st.sidebar.markdown(f"**Win Rate Totale:** `{overall['win_rate_pct']:.1f}%`")
st.sidebar.markdown(f"**Net PnL Totale:** `{overall['net_pnl']:.4f} EUR`")

# ==============================================================================
#  🏆 EXECUTIVE REGIME SUMMARY
# ==============================================================================
if menu == "🏆 Executive Regime Summary":
    st.markdown("<h1>🏆 Executive Regime Summary</h1>", unsafe_allow_html=True)
    st.write("Diagnostica di alto livello per la classificazione e la scomposizione delle performance dell'algoritmo basate sui regimi di mercato.")
    
    # KPI Grid
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Trade Totali</div>
            <div class="kpi-value">{overall['total_trades']}</div>
            <div style="color: #64748B; font-size: 0.85rem;">Esiti closed</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Win Rate</div>
            <div class="kpi-value">{overall['win_rate_pct']:.1f}%</div>
            <div style="color: #10B981; font-size: 0.85rem;">Vinti (parziali inclusi)</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        pnl_color = "#10B981" if overall['net_pnl'] >= 0 else "#EF4444"
        pnl_sign = "+" if overall['net_pnl'] >= 0 else ""
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Net PnL</div>
            <div class="kpi-value" style="background: linear-gradient(90deg, {pnl_color} 0%, #A5B4FC 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{pnl_sign}{overall['net_pnl']:.2f} €</div>
            <div style="color: {pnl_color}; font-size: 0.85rem;">Utile Netto Capitale</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        # Trova profit factor complessivo se presente nei regimi
        pf_val = 1.0
        if "regime" in regime_decomp and len(trades_list) > 0:
            gross_wins = sum([t['pnl'] for t in trades_list if t['pnl'] > 0])
            gross_losses = abs(sum([t['pnl'] for t in trades_list if t['pnl'] < 0]))
            pf_val = gross_wins / gross_losses if gross_losses > 0 else 1.0
        pf_color = "#10B981" if pf_val >= 1.0 else "#EF4444"
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-title">Profit Factor</div>
            <div class="kpi-value" style="background: linear-gradient(90deg, {pf_color} 0%, #A5B4FC 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{pf_val:.2f}</div>
            <div style="color: #64748B; font-size: 0.85rem;">Gross profit / loss</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br><h2>🧠 Dynamic Edge & Trading Restriction Recommendations</h2>", unsafe_allow_html=True)
    st.write("Generato automaticamente basandosi sulle metriche di aspettativa statistica del backtest attuale:")

    # Dynamic Edge recommendation logic
    edges = []
    restrictions = []
    
    # Analyze dimensions for high and low edge
    for dim_name, dim_data in regime_decomp.items():
        for r_name, r_metrics in dim_data.items():
            if r_metrics["total_trades"] >= 2:
                exp = r_metrics["expectancy"]
                wr = r_metrics["win_rate_pct"]
                pnl = r_metrics["net_pnl"]
                
                # Check for Edge
                if exp > 0.005 or (wr > 55.0 and pnl > 0):
                    edges.append({
                        "dim": dim_name, "val": r_name, "exp": exp, "wr": wr, "pnl": pnl, "trades": r_metrics["total_trades"]
                    })
                # Check for Restriction
                elif exp < -0.005 or (wr < 40.0 and pnl < 0):
                    restrictions.append({
                        "dim": dim_name, "val": r_name, "exp": exp, "wr": wr, "pnl": pnl, "trades": r_metrics["total_trades"]
                    })

    # Sort
    edges = sorted(edges, key=lambda x: x["exp"], reverse=True)
    restrictions = sorted(restrictions, key=lambda x: x["exp"])

    col_rec1, col_rec2 = st.columns(2)
    with col_rec1:
        st.markdown("### 🟢 STATISTICAL STRATEGY EDGE")
        if edges:
            for ed in edges[:3]:
                # Friendly names
                dim_title = ed["dim"].replace("_", " ").title()
                st.markdown(f"""
                <div class="custom-alert alert-edge">
                    <strong>High Edge in: {dim_title} → {ed['val']}</strong><br>
                    • Expectancy per trade: <code>{ed['exp']:.5f}</code><br>
                    • Win Rate: <code>{ed['wr']:.1f}%</code> ({ed['trades']} trades)<br>
                    • Total PnL contribution: <code>{ed['pnl']:.4f} EUR</code><br>
                    <em>👉 Sizing recommendation: Standard or Capped Kelly sizing can be applied aggressively here.</em>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="custom-alert alert-neutral">
                <strong>Nessun edge forte statisticamente isolato</strong><br>
                Nessuna singola categoria ha mostrato una aspettativa di trade sufficientemente elevata (trades >= 2 e aspettativa > 0.005). Consigliato raffinamento del modello o aumento della dimensione del test.
            </div>
            """, unsafe_allow_html=True)

    with col_rec2:
        st.markdown("### 🔴 ZONE OF TRADING RESTRICTION")
        if restrictions:
            for re in restrictions[:3]:
                dim_title = re["dim"].replace("_", " ").title()
                st.markdown(f"""
                <div class="custom-alert alert-restriction">
                    <strong>Avoid trading in: {dim_title} → {re['val']}</strong><br>
                    • Expectancy per trade: <code>{re['exp']:.5f}</code><br>
                    • Win Rate: <code>{re['wr']:.1f}%</code> ({re['trades']} trades)<br>
                    • Total PnL drag: <code>{re['pnl']:.4f} EUR</code><br>
                    <em>👉 Filter recommendation: It is statistically advised to implement a risk bypass or hard restriction to HALT new setups in this environment.</em>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="custom-alert alert-neutral">
                <strong>Nessun regime di forte deperimento identificato</strong><br>
                La strategia si comporta in modo omogeneo senza picchi negativi significativi. Eccellente stabilità complessiva.
            </div>
            """, unsafe_allow_html=True)

# ==============================================================================
#  📊 DETAILED REGIME ANALYSIS
# ==============================================================================
elif menu == "📊 Detailed Regime Analysis":
    st.markdown("<h1>📊 Detailed Regime Analysis</h1>", unsafe_allow_html=True)
    st.write("Scomponi ed esplora l'edge della strategia selezionando una singola dimensione quantitativa dal menu.")

    # Selector
    dimensions_map = {
        "Trending vs Ranging": "regime",
        "Volatility Regimes (ATR%)": "volatility_regime",
        "Trading Sessions (Asia/London/NY)": "session",
        "Weekdays": "weekday",
        "AI Confidence Buckets": "confidence_bucket",
        "Funding Environments (EMA Proxy)": "funding_env"
    }
    
    selected_label = st.selectbox("Seleziona Dimensione Decomposizione", list(dimensions_map.keys()))
    selected_dim = dimensions_map[selected_label]
    
    if selected_dim in regime_decomp:
        data = regime_decomp[selected_dim]
        
        # Convert to DataFrame
        df_dim = pd.DataFrame(data).T
        df_dim.index.name = "Regime"
        df_dim = df_dim.reset_index()
        
        # Format table columns
        df_show = df_dim.copy()
        df_show["win_rate_pct"] = df_show["win_rate_pct"].map("{:.1f}%".format)
        df_show["net_pnl"] = df_show["net_pnl"].map("{:+.4f} €".format)
        df_show["profit_factor"] = df_show["profit_factor"].map("{:.2f}".format)
        df_show["expectancy"] = df_show["expectancy"].map("{:+.5f}".format)
        df_show["sharpe_ratio"] = df_show["sharpe_ratio"].map("{:.2f}".format)
        df_show["sortino_ratio"] = df_show["sortino_ratio"].map("{:.2f}".format)
        df_show["max_drawdown"] = df_show["max_drawdown"].map("{:.2f} €".format)
        
        # Display Table
        st.markdown(f"### Metriche di Performance per **{selected_label}**")
        st.dataframe(df_show, use_container_width=True)
        
        # Interactive Plotly Columns
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            fig_pnl = px.bar(
                df_dim, x="Regime", y="net_pnl", 
                title=f"Net PnL per {selected_label}",
                labels={"net_pnl": "Net PnL (EUR)", "Regime": selected_label},
                color="net_pnl",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0
            )
            fig_pnl.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pnl, use_container_width=True)
            
        with col_c2:
            fig_exp = px.bar(
                df_dim, x="Regime", y="expectancy",
                title=f"Expectancy per {selected_label}",
                labels={"expectancy": "Expectancy / Trade", "Regime": selected_label},
                color="expectancy",
                color_continuous_scale="Geyser",
                color_continuous_midpoint=0
            )
            fig_exp.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_exp, use_container_width=True)
            
        # Win Rate Comparison
        fig_wr = px.bar(
            df_dim, x="Regime", y="win_rate_pct",
            title=f"Win Rate % per {selected_label}",
            labels={"win_rate_pct": "Win Rate %", "Regime": selected_label},
            text=df_dim["win_rate_pct"].apply(lambda x: f"{x:.1f}%"),
            color="win_rate_pct",
            color_continuous_scale="Purples"
        )
        fig_wr.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_wr, use_container_width=True)

# ==============================================================================
#  🔥 JOINT CROSS-REGIME HEATMAPS
# ==============================================================================
elif menu == "🔥 Joint Cross-Regime Heatmaps":
    st.markdown("<h1>🔥 Joint Cross-Regime Heatmaps</h1>", unsafe_allow_html=True)
    st.write("Analizza la correlazione cross-settoriale fra le variabili ambientali di mercato basata sui singoli trade eseguiti.")

    if not trades_list:
        st.warning("Nessun trade registrato nel report per il calcolo delle cross-heatmaps.")
    else:
        df_trades = pd.DataFrame(trades_list)
        
        # Selectors for heatmap dimensions
        col_sel1, col_sel2, col_sel3 = st.columns(3)
        with col_sel1:
            y_axis = st.selectbox("Dimensione Asse Y (Righe)", ["session", "volatility_regime", "regime", "funding_env", "confidence_bucket", "weekday"], index=0)
        with col_sel2:
            x_axis = st.selectbox("Dimensione Asse X (Colonne)", ["volatility_regime", "session", "regime", "funding_env", "confidence_bucket", "weekday"], index=1)
        with col_sel3:
            metric = st.selectbox("Metrica Heatmap", ["Win Rate %", "Expectancy / Trade", "Net PnL (EUR)", "Numero di Trade"], index=0)

        # Build Pivot
        if y_axis == x_axis:
            st.error("Seleziona due dimensioni differenti per le righe e le colonne.")
        else:
            # Custom Aggregators
            if metric == "Win Rate %":
                # win rate = count(wins) / count(total) * 100
                df_trades["is_win"] = df_trades["result"].isin(["WIN", "WIN_PARTIAL"]).astype(int)
                pivot = df_trades.groupby([y_axis, x_axis]).apply(
                    lambda g: (g["is_win"].sum() / (g["result"].isin(["WIN", "WIN_PARTIAL", "LOSS"]).sum()) * 100) if (g["result"].isin(["WIN", "WIN_PARTIAL", "LOSS"]).sum()) > 0 else np.nan
                ).unstack()
                color_scale = "RdYlGn"
                title_metric = "Win Rate (%)"
                fmt = ".1f"
            elif metric == "Expectancy / Trade":
                pivot = df_trades.groupby([y_axis, x_axis])["pnl"].mean().unstack()
                color_scale = "Geyser"
                title_metric = "Expectancy (EUR)"
                fmt = ".4f"
            elif metric == "Net PnL (EUR)":
                pivot = df_trades.groupby([y_axis, x_axis])["pnl"].sum().unstack()
                color_scale = "RdYlGn"
                title_metric = "Net PnL (EUR)"
                fmt = ".2f"
            else:
                pivot = df_trades.groupby([y_axis, x_axis]).size().unstack(fill_value=0)
                color_scale = "Viridis"
                title_metric = "Conteggio Trade"
                fmt = "d"

            pivot = pivot.fillna(0)

            # Draw Heatmap
            fig_hm = px.imshow(
                pivot,
                text_auto=fmt,
                color_continuous_scale=color_scale,
                title=f"Cross Heatmap: {y_axis.upper()} vs {x_axis.upper()} ({title_metric})",
                labels=dict(x=x_axis.replace("_", " ").title(), y=y_axis.replace("_", " ").title(), color=title_metric)
            )
            fig_hm.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                width=900,
                height=550
            )
            st.plotly_chart(fig_hm, use_container_width=True)

# ==============================================================================
#  🔄 MARKOV TRANSITION ANALYSIS
# ==============================================================================
elif menu == "🔄 Markov Transition Analysis":
    st.markdown("<h1>🔄 Markov Transition Analysis</h1>", unsafe_allow_html=True)
    st.write("Visualizza la matrice di transizione di stato Markoviana per comprendere la probabilità di variazione del regime di mercato ed analizza le performance dei trade durante tali fasi di transizione.")

    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.markdown("### Matrice di Transizione di Markov (Stato Combinato)")
        m_matrix = transition.get("markov_transition_matrix", {})
        if not m_matrix:
            st.warning("Dati sulla matrice di transizione non disponibili.")
        else:
            df_trans = pd.DataFrame(m_matrix["matrix"], index=m_matrix["index"], columns=m_matrix["columns"])
            
            fig_m = px.imshow(
                df_trans,
                text_auto=".2f",
                color_continuous_scale="Viridis",
                labels=dict(x="Stato Successivo (t+1)", y="Stato Corrente (t)", color="Probabilità")
            )
            fig_m.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_m, use_container_width=True)

    with col_t2:
        st.markdown("### Performance nelle Zone di Transizione vs Stabili")
        st.write("Analisi dei trade aperti entro 5 candele da una transizione di regime (cambio Trending <-> Ranging) confrontati con trade in periodi stabili.")
        
        t_perf = transition.get("transition_performance", {})
        if not t_perf:
            st.warning("Analisi delle performance in transizione non disponibile.")
        else:
            df_perf = pd.DataFrame(t_perf).T
            df_perf.index.name = "Zona"
            df_perf = df_perf.reset_index()
            
            df_perf_show = df_perf.copy()
            df_perf_show["win_rate"] = df_perf_show["win_rate"].map("{:.1f}%".format)
            df_perf_show["net_pnl"] = df_perf_show["net_pnl"].map("{:+.4f} €".format)
            st.dataframe(df_perf_show, use_container_width=True)
            
            # Bar chart of transition performance
            fig_tp = px.bar(
                df_perf, x="Zona", y="net_pnl",
                color="Zona",
                title="Confronto PnL: Stabilità vs Transizione",
                labels={"net_pnl": "Net PnL (EUR)", "Zona": "Zona"},
                color_discrete_map={"STABLE_ZONE": "#10B981", "TRANSITION_ZONE": "#EF4444"}
            )
            fig_tp.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_tp, use_container_width=True)

# ==============================================================================
#  🧬 TRADE CLUSTERING K-MEANS
# ==============================================================================
elif menu == "🧬 Trade Clustering K-Means":
    st.markdown("<h1>🧬 Trade Clustering K-Means</h1>", unsafe_allow_html=True)
    st.write("Raggruppamento automatico dei trade in 4 macro-profili quantitativi (tramite standardizzazione e algoritmo K-Means) per estrarre l'edge strategico specifico.")

    if not clusters:
        st.warning("Dati di clustering non disponibili per questo backtest (numero insufficiente di trade).")
    else:
        # Build cluster list
        cluster_list = []
        scatter_data = []
        
        for c_id, c_data in clusters.items():
            cluster_list.append({
                "ID": c_id,
                "Nome": c_data["name"],
                "Trade totali": c_data["total_trades"],
                "Win Rate %": f"{c_data['win_rate_pct']:.1f}%",
                "Net PnL (€)": f"{c_data['net_pnl']:.4f} €",
                "Centroid ADX": f"{c_data['profile']['adx']:.2f}",
                "Centroid ATR%": f"{c_data['profile']['atr_pct']:.3f}%",
                "Centroid AI Prob": f"{c_data['profile']['ai_prob']:.2f}%",
                "Centroid Setup Quality": f"{c_data['profile']['setup_quality']:.2f}"
            })
            
            # Accumulate scatter data
            for tc in c_data["trade_coords"]:
                tc["cluster_name"] = c_data["name"]
                tc["cluster_id"] = c_id
                scatter_data.append(tc)
                
        df_c_summary = pd.DataFrame(cluster_list)
        st.dataframe(df_c_summary, use_container_width=True)
        
        # Scatter Plot 2D in Plotly
        if scatter_data:
            df_scatter = pd.DataFrame(scatter_data)
            
            st.markdown("### Visualizzazione 2D degli Spazi di Setup dei Trade")
            st.write("Grafico di dispersione che mette a confronto l'indice di Trend (ADX) e l'indice di Volatilità (ATR%) per ciascun trade, raggruppati per Cluster.")
            
            fig_sc = px.scatter(
                df_scatter,
                x="adx",
                y="atr_pct",
                color="cluster_name",
                size=df_scatter["pnl"].abs().fillna(0.0) + 0.1,  # PnL assoluto come dimensione
                hover_data=["pnl", "ai_prob", "result"],
                title="ADX vs ATR% per Cluster (La dimensione del pallino rappresenta l'entità del PnL)",
                labels={"adx": "ADX (Trend Strength)", "atr_pct": "ATR% (Volatility)", "cluster_name": "Cluster"}
            )
            fig_sc.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sc, use_container_width=True)

# ==============================================================================
#  💼 INTERACTIVE TRADE LEDGER
# ==============================================================================
else:
    st.markdown("<h1>💼 Interactive Trade Ledger</h1>", unsafe_allow_html=True)
    st.write("Registro completo e interattivo dei singoli trade eseguiti con relative etichette ambientali e metriche tecniche.")

    if not trades_list:
        st.info("Nessun trade registrato nel ledger per questa run.")
    else:
        df_ledger = pd.DataFrame(trades_list)
        
        # Search & Filter
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            f_result = st.multiselect("Risultato Trade", df_ledger["result"].unique(), default=df_ledger["result"].unique())
        with col_f2:
            f_session = st.multiselect("Sessione", df_ledger["session"].unique(), default=df_ledger["session"].unique())
        with col_f3:
            f_regime = st.multiselect("Regime di Mercato", df_ledger["regime"].unique(), default=df_ledger["regime"].unique())
            
        # Apply filters
        df_filtered = df_ledger[
            df_ledger["result"].isin(f_result) &
            df_ledger["session"].isin(f_session) &
            df_ledger["regime"].isin(f_regime)
        ]
        
        st.write(f"Mostrando `{len(df_filtered)}` trade su `{len(df_ledger)}` totali:")
        
        # Format for output
        df_led_show = df_filtered.copy()
        
        # Sort columns logically
        columns_to_show = ["entry_time", "side", "result", "pnl", "balance", "entry", "sl", "tp", "regime", "session", "volatility_regime", "funding_env", "confidence_bucket", "adx", "atr_pct", "volume_ratio", "setup_quality", "ai_prob"]
        # Keep only available
        columns_to_show = [c for c in columns_to_show if c in df_led_show.columns]
        
        df_led_show = df_led_show[columns_to_show]
        
        df_led_show["pnl"] = df_led_show["pnl"].map("{:+.4f} €".format)
        df_led_show["balance"] = df_led_show["balance"].map("{:.2f} €".format)
        df_led_show["atr_pct"] = df_led_show["atr_pct"].map("{:.3f}%".format)
        df_led_show["adx"] = df_led_show["adx"].map("{:.2f}".format)
        df_led_show["volume_ratio"] = df_led_show["volume_ratio"].map("{:.2f}".format)
        df_led_show["setup_quality"] = df_led_show["setup_quality"].map("{:.1f}".format)
        df_led_show["ai_prob"] = df_led_show["ai_prob"].map("{:.1f}%".format)
        
        st.dataframe(df_led_show, use_container_width=True)
