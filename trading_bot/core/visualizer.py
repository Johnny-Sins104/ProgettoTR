import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def save_trade_chart(df: pd.DataFrame, trade_data: dict, filename: str) -> None:
    """
    Genera un grafico HTML interattivo con candele, EMA, RSI e livelli SL/TP/Entry.

    trade_data atteso: {"side": str, "entry": float, "sl": float, "tp": float}
    """
    window = df.iloc[-100:].copy()  # ultimi 100 periodi
    idx    = window.index

    side   = trade_data.get("side", "BUY")
    entry  = trade_data["entry"]
    sl     = trade_data["sl"]
    tp     = trade_data["tp"]

    entry_color = "#3B82F6" if side == "BUY" else "#F59E0B"  # blu=BUY, giallo=SELL

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.7, 0.3],
        vertical_spacing=0.06,
        subplot_titles=(f"Price — {side}", "RSI (14)"),
    )

    # ── Candlestick ───────────────────────────────────────────────── #
    fig.add_trace(
        go.Candlestick(
            x=idx,
            open=window["Open"],
            high=window["High"],
            low=window["Low"],
            close=window["Close"],
            name="Prezzo",
            increasing_line_color="#22C55E",
            decreasing_line_color="#EF4444",
        ),
        row=1, col=1,
    )

    # ── EMA 200 ───────────────────────────────────────────────────── #
    if "ema_200" in window.columns:
        fig.add_trace(
            go.Scatter(
                x=idx,
                y=window["ema_200"],
                mode="lines",
                name="EMA 200",
                line=dict(color="#A855F7", width=1.5, dash="dot"),
            ),
            row=1, col=1,
        )

    # ── Entry / SL / TP orizzontali ───────────────────────────────── #
    for level, color, label, dash in [
        (entry, entry_color, f"Entry {entry:.4f}",    "solid"),
        (tp,    "#22C55E",   f"TP {tp:.4f}",          "dash"),
        (sl,    "#EF4444",   f"SL {sl:.4f}",          "dash"),
    ]:
        fig.add_hline(
            y=level,
            line_color=color,
            line_dash=dash,
            line_width=1.5,
            annotation_text=label,
            annotation_position="right",
            annotation_font_color=color,
            row=1, col=1,
        )

    # ── RSI ───────────────────────────────────────────────────────── #
    if "rsi_14" in window.columns:
        fig.add_trace(
            go.Scatter(
                x=idx,
                y=window["rsi_14"],
                mode="lines",
                name="RSI 14",
                line=dict(color="#F59E0B", width=1.5),
            ),
            row=2, col=1,
        )

    # Livelli RSI 30 / 70
    for level, color, label in [
        (70, "#EF4444", "Overbought 70"),
        (30, "#22C55E", "Oversold 30"),
    ]:
        fig.add_hline(
            y=level,
            line_color=color,
            line_dash="dash",
            line_width=1,
            annotation_text=label,
            annotation_position="right",
            annotation_font_color=color,
            row=2, col=1,
        )

    # ── Layout ───────────────────────────────────────────────────── #
    fig.update_layout(
        title=dict(
            text=f"Trade Debug — {side} | Entry {entry:.4f} | SL {sl:.4f} | TP {tp:.4f}",
            font=dict(size=14),
        ),
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=700,
        margin=dict(l=50, r=120, t=80, b=40),
    )
    fig.update_yaxes(title_text="Prezzo", row=1, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)

    fig.write_html(filename)
    print(f"[VISUALIZER] Grafico salvato -> {filename}")
