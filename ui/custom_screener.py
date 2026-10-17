import streamlit as st
from data_engine.db_manager import get_connection

def render_custom_screener_tab():
    st.subheader("🔍 Custom Screener.in + Chartink Hybrid Query Builder")
    st.caption("Filter across all pre-computed fundamental, delivery absorption, and technical breakout metrics in under 50ms.")

    col1, col2, col3, col4 = st.columns(4)
    min_float_abs = col1.number_input("Min 10D Float Absorption %", value=1.5, step=0.5)
    min_deliv_mult = col2.number_input("Min 5D Delivery Spike (x)", value=2.0, step=0.5)
    min_rs = col3.number_input("Min Relative Strength Percentile", value=70, step=5)
    max_price = col4.number_input("Max Share Price (₹)", value=5000, step=50)

    default_sql = (
        f"SELECT symbol, primary_mode, close, market_cap_cr, mode_a_score, mode_b_score, master_score, "
        f"float_absorption_10d_pct, delivery_spike_mult, op_leverage_score, rs_percentile, "
        f"entry_trigger, stop_loss, target_1, target_2 "
        f"FROM daily_quant_scores "
        f"WHERE trade_date = (SELECT MAX(trade_date) FROM daily_quant_scores) "
        f"AND float_absorption_10d_pct >= {min_float_abs} "
        f"AND delivery_spike_mult >= {min_deliv_mult} "
        f"AND rs_percentile >= {min_rs} "
        f"AND close <= {max_price} "
        f"ORDER BY master_score DESC LIMIT 50"
    )

    custom_sql = st.text_area("Edit SQL Filter Expression Directly (Optional):", value=default_sql, height=110)
    if st.button("⚡ Execute Instant Scan", type="primary"):
        con = get_connection()
        try:
            res_df = con.execute(custom_sql).df()
            st.dataframe(res_df, use_container_width=True)
        except Exception as e:
            st.error(f"Query Error: {e}")
        finally:
            con.close()