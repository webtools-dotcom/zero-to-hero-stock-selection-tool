import streamlit as st
from streamlit_lightweight_charts import renderLightweightCharts
from data_engine.db_manager import get_connection

def render_stock_trade_chart(isin: str, symbol: str, trade_row: dict):
    """
    Renders an interactive TradingView Lightweight Chart with Candlesticks, Delivery Volume,
    and horizontal price lines for Entry Trigger, Stop-Loss, Target 1, Target 2, and 50-EMA.
    """
    con = get_connection()
    df = con.execute("""
        SELECT trade_date, open, high, low, close, volume, delivery_qty
        FROM daily_market
        WHERE isin = ?
        ORDER BY trade_date ASC
        LIMIT 260
    """, [isin]).df()
    con.close()

    if df.empty:
        st.warning(f"No candle data available for {symbol}.")
        return

    df["time"] = df["trade_date"].astype(str)
    candles = df[["time", "open", "high", "low", "close"]].to_dict(orient="records")

    entry = float(trade_row.get("entry_trigger", df.iloc[-1]["close"]))
    sl = float(trade_row.get("stop_loss", entry * 0.93))
    t1 = float(trade_row.get("target_1", entry * 1.15))
    t2 = float(trade_row.get("target_2", entry * 1.35))

    chart_options = {
        "height": 420,
        "layout": {"background": {"type": "solid", "color": "#0e1117"}, "textColor": "#d1d4dc"},
        "grid": {"vertLines": {"color": "#1f2430"}, "horzLines": {"color": "#1f2430"}},
        "timeScale": {"borderColor": "#2B2B43"}
    }

    series = [
        {
            "type": "Candlestick",
            "data": candles,
            "options": {
                "upColor": "#26a69a",
                "downColor": "#ef5350",
                "borderVisible": False,
                "wickUpColor": "#26a69a",
                "wickDownColor": "#ef5350"
            },
            "priceLines": [
                {"price": entry, "color": "#2962FF", "lineWidth": 2, "lineStyle": 0, "axisLabelVisible": True, "title": "ENTRY TRIGGER"},
                {"price": sl, "color": "#FF1744", "lineWidth": 2, "lineStyle": 2, "axisLabelVisible": True, "title": "STOP LOSS"},
                {"price": t1, "color": "#00E676", "lineWidth": 2, "lineStyle": 1, "axisLabelVisible": True, "title": "TARGET 1 (2.5R FREE RIDE)"},
                {"price": t2, "color": "#00B0FF", "lineWidth": 2, "lineStyle": 1, "axisLabelVisible": True, "title": "TARGET 2 (5R SWING)"}
            ]
        }
    ]

    renderLightweightCharts([{"chart": chart_options, "series": series}], key=f"tv_chart_{isin}")