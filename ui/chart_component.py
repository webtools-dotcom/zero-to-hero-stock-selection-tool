import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_engine.db_manager import get_connection

GREEN, RED = "#26a69a", "#ef5350"

def render_stock_trade_chart(isin: str, symbol: str, trade_row: dict):
    """
    Institutional TradingView-style chart (native Plotly): candles + EMA-50/EMA-65 in row 1,
    volume coloured by candle direction with delivery_qty overlay in row 2, and all trade
    levels (Entry/SL/T1/T2) as hlines so the axis auto-expands to show every target.
    """
    con = get_connection()
    df = con.execute("""
        SELECT * FROM (
            SELECT trade_date, open, high, low, close, volume, delivery_qty
            FROM daily_market
            WHERE isin = ?
            ORDER BY trade_date DESC
            LIMIT 180
        ) sub
        ORDER BY trade_date ASC
    """, [isin]).df()
    con.close()

    if df.empty:
        st.warning(f"No candle data available for {symbol}.")
        return

    df["date"] = df["trade_date"].astype(str)
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_65"] = df["close"].ewm(span=65, adjust=False).mean()
    df["delivery_qty"] = pd.to_numeric(df["delivery_qty"], errors="coerce").fillna(0)
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    entry = float(trade_row.get("entry_trigger", df.iloc[-1]["close"]))
    sl = float(trade_row.get("stop_loss", entry * 0.93))
    t1 = float(trade_row.get("target_1", entry * 1.15))
    t2 = float(trade_row.get("target_2", entry * 1.35))

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25]
    )

    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=GREEN, decreasing_line_color=RED,
        increasing_fillcolor=GREEN, decreasing_fillcolor=RED, name=symbol,
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df["date"], y=df["ema_50"], name="EMA-50",
                             line=dict(color="#FFD600", width=1.6)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df["date"], y=df["ema_65"], name="EMA-65",
                             line=dict(color="#FF6D00", width=1.6)), row=1, col=1)

    fig.add_hline(y=entry, line_color="#2962FF", line_width=2, line_dash="solid",
                  annotation_text=f"ENTRY TRIGGER: ₹{entry}", annotation_position="top right",
                  annotation_font_color="#2962FF", row=1, col=1)
    fig.add_hline(y=sl, line_color="#FF1744", line_width=2, line_dash="dash",
                  annotation_text=f"STOP LOSS: ₹{sl}", annotation_position="bottom right",
                  annotation_font_color="#FF1744", row=1, col=1)
    fig.add_hline(y=t1, line_color="#00E676", line_width=2, line_dash="dot",
                  annotation_text=f"TARGET 1 (2.5R): ₹{t1}", annotation_position="top right",
                  annotation_font_color="#00E676", row=1, col=1)
    fig.add_hline(y=t2, line_color="#00B0FF", line_width=2, line_dash="dot",
                  annotation_text=f"TARGET 2 (5R): ₹{t2}", annotation_position="top right",
                  annotation_font_color="#00B0FF", row=1, col=1)

    bar_colors = [GREEN if c >= o else RED for o, c in zip(df["open"], df["close"])]
    fig.add_trace(go.Bar(x=df["date"], y=df["volume"], marker_color=bar_colors,
                         opacity=0.75, name="Volume"), row=2, col=1)
    fig.add_trace(go.Bar(x=df["date"], y=df["delivery_qty"], marker_color="#FFB300",
                         opacity=0.45, name="Delivery Qty", marker_line_width=0), row=2, col=1)

    fig.update_layout(
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#d1d4dc", size=11),
        height=460, margin=dict(l=10, r=10, t=25, b=10),
        showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hovermode="x unified", bargap=0.05,
    )
    fig.update_xaxes(rangeslider_visible=False, showgrid=False, row=1, col=1)
    fig.update_xaxes(showgrid=False, row=2, col=1)
    fig.update_yaxes(gridcolor="#1f2430", zeroline=False, row=1, col=1)
    fig.update_yaxes(title_text="Volume", gridcolor="#1f2430", zeroline=False, row=2, col=1)

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
