import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from datetime import datetime
from config import SUPPORTED_MODELS
from data_engine.db_manager import init_db, get_connection
from data_engine.sync_daily import run_daily_eod_pipeline
from data_engine.upstox_client import UpstoxClient
from quant_engine.feature_factory import compute_and_store_daily_scores
from ai_brain.llm_router import LLMRouter
from ai_brain.agent_tools import get_top_candidates_df, parse_user_intent_and_run, build_fallback_trade_plan
from backtest.time_machine_test import run_time_machine_validation
from ui.chart_component import render_stock_trade_chart
from ui.custom_screener import render_custom_screener_tab

st.set_page_config(page_title="AlphaSniper NSE/BSE Terminal", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
[data-testid="stMetricValue"] { font-size: 1.15rem !important; font-weight: 700 !important; white-space: nowrap !important; overflow: visible !important; text-overflow: unset !important; }
[data-testid="stMetricLabel"] p { font-size: 0.78rem !important; white-space: normal !important; line-height: 1.1 !important; }
.stApp > header { display: none; }
div[data-testid="stAppViewContainer"] > div[data-testid="stDecoration"], [data-testid="stDecoration"] { height: 0rem; }
section.main > div, .block-container { padding-top: 1.5rem !important; }
</style>""", unsafe_allow_html=True)
init_db()

if "active_picks_df" not in st.session_state:
    st.session_state.active_picks_df = get_top_candidates_df(mode="MASTER", top_n=5)
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content": build_fallback_trade_plan(st.session_state.active_picks_df)}
    ]

# --- SIDEBAR: SETTINGS & SYNC ---
with st.sidebar:
    st.title("⚡ AlphaSniper")
    st.caption("NSE/BSE Ground-Floor Multibagger & Swing Terminal")

    model_label = st.selectbox("AI Brain Model", list(SUPPORTED_MODELS.keys()), index=0)
    provider_name, model_id = SUPPORTED_MODELS[model_label]
    user_api_key = st.text_input(f"Enter {provider_name.upper()} API Key (or leave blank to use .env)", type="password")
    llm = LLMRouter(provider=provider_name, model=model_id, api_key=user_api_key if user_api_key else None)

    st.divider()
    top_n_slider = st.slider("Default Top N Picks", min_value=1, max_value=20, value=5)

    if st.button("🔄 Run Daily EOD Data Sync", use_container_width=True):
        with st.spinner("Syncing NSE Bhavcopy Delivery, Filings & Recomputing Quant Scores..."):
            run_daily_eod_pipeline(days_back=5)
            st.session_state.active_picks_df = get_top_candidates_df(mode="MASTER", top_n=top_n_slider)
        st.success("Database & Quant Scores Updated!")

    st.divider()
    st.subheader("🕰️ Time-Machine Validator")
    tm_date = st.date_input("Select Historical Test Date")
    tm_mode = st.selectbox("Backtest Mode", ["A", "B", "MASTER"])
    if st.button("Run Point-in-Time Backtest", use_container_width=True):
        with st.spinner(f"Testing {tm_mode} as of {tm_date}..."):
            tm_df = run_time_machine_validation(str(tm_date), mode=tm_mode, top_n=top_n_slider)
            st.session_state.tm_results = tm_df

    st.divider()
    if st.button("⚡ Refresh Live Market Quotes (Upstox API)", use_container_width=True):
        with st.spinner("Fetching live Upstox quotes for scored universe & recomputing trade levels..."):
            live_n = UpstoxClient().refresh_live_quotes_into_db()
            compute_and_store_daily_scores(str(datetime.now().date()))
            st.session_state.active_picks_df = get_top_candidates_df(mode="MASTER", top_n=top_n_slider)
        st.success(f"Live OHLCV upserted for {live_n} instruments; Mode A/B/Master levels recomputed.")

# --- MAIN SPLIT-SCREEN HYBRID LAYOUT ---
left_col, right_col = st.columns([0.60, 0.40], gap="large")

with left_col:
    st.markdown("### 🎯 Daily Conviction Command Center")
    b1, b2, b3 = st.columns(3)

    # Buttons are NON-BLOCKING: they only queue the intent and let the layout render;
    # the scan/plan is executed after ALL columns are drawn (bottom of this script).
    if b1.button(f"🔥 Top {top_n_slider} Overall (Master)", use_container_width=True, type="primary"):
        st.session_state.pending_query = f"Find the best top {top_n_slider} stocks for tomorrow morning across all modes."
        st.session_state.chat_history.append({"role": "user", "content": st.session_state.pending_query})

    if b2.button(f"🚀 Top {top_n_slider} Mode A (CUPID/STLTECH)", use_container_width=True):
        st.session_state.pending_query = f"Find the top {top_n_slider} best stocks from Mode A (Turnaround & Multibagger Sniper) for tomorrow."
        st.session_state.chat_history.append({"role": "user", "content": st.session_state.pending_query})

    if b3.button(f"⚡ Top {top_n_slider} Mode B (Compounders)", use_container_width=True):
        st.session_state.pending_query = f"Find the top {top_n_slider} best stocks from Mode B (High-Velocity Momentum Compounders) for tomorrow."
        st.session_state.chat_history.append({"role": "user", "content": st.session_state.pending_query})

    picks_df = st.session_state.active_picks_df
    if not picks_df.empty:
        selected_sym = st.selectbox(
            "Inspect Candidate on TradingView Chart (with Plotted Entry, Stop-Loss & Targets):",
            picks_df["symbol"].tolist()
        )
        sel_row = picks_df[picks_df["symbol"] == selected_sym].iloc[0].to_dict()

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Entry Trigger", f"₹{sel_row['entry_trigger']}", f"Max: ₹{sel_row['max_chase_price']}")
        m2.metric("Structural Stop-Loss", f"₹{sel_row['stop_loss']}", f"-{sel_row['risk_pct']}% Risk")
        m3.metric("Target 1 (2.5R Free)", f"₹{sel_row['target_1']}")
        m4.metric("Target 2 (5R Swing)", f"₹{sel_row['target_2']}")
        m5.metric("50-EMA Stop Level", f"₹{sel_row['trailing_sl_ema50']}")
        m6.metric("Runner Trail (EMA-65)", f"₹{sel_row['runner_trail_ema65']}")

        render_stock_trade_chart(sel_row["isin"], selected_sym, sel_row)

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Top Picks Breakdown", "🔍 Custom Screener", "🕰️ Time-Machine Results", "🧬 Stock Quarterly X-Ray & Filings"])
    with tab1:
        if not picks_df.empty:
            st.dataframe(picks_df[[
                "symbol", "primary_mode", "close", "master_score", "mode_a_score", "mode_b_score",
                "float_absorption_10d_pct", "delivery_spike_mult", "op_leverage_score",
                "rs_percentile", "entry_trigger", "stop_loss", "target_1", "target_2"
            ]], use_container_width=True)
        else:
            st.info("Click 'Run Daily EOD Data Sync' in the sidebar to populate your local DuckDB database.")
    with tab2:
        render_custom_screener_tab()
    with tab3:
        if "tm_results" in st.session_state and not st.session_state.tm_results.empty:
            st.dataframe(st.session_state.tm_results, use_container_width=True)
        else:
            st.caption("Use the Time-Machine Validator in the sidebar to test historical dates.")
    with tab4:
        if not picks_df.empty:
            con = get_connection()
            meta = con.execute("""
                SELECT company_name, sector, sub_industry, market_cap_cr, total_shares,
                       public_float_shares, promoter_pct, promoter_change_qoq, pledge_pct,
                       pledge_change_qoq, roce_pct, roe_pct, debt_to_equity, cfo_to_pat_ratio,
                       asm_gsm_stage
                FROM instruments WHERE isin = ?
            """, [sel_row["isin"]]).df()
            q_df = con.execute("""
                SELECT quarter_end, filing_date, sales_cr, op_profit_cr, opm_pct,
                       net_profit_cr, eps
                FROM quarterly_results
                WHERE isin = ?
                ORDER BY quarter_end DESC LIMIT 8
            """, [sel_row["isin"]]).df()
            f_df = con.execute("""
                SELECT filing_datetime, category, headline, ai_catalyst_score, ai_summary
                FROM corporate_filings
                WHERE isin = ?
                ORDER BY filing_datetime DESC LIMIT 10
            """, [sel_row["isin"]]).df()
            con.close()

            m = meta.iloc[0].to_dict() if not meta.empty else {}

            def num(v, default=0.0):
                return default if pd.isna(v) else float(v)

            x1, x2, x3, x4, x5 = st.columns(5)
            x1.metric("Market Cap", f"₹{num(m.get('market_cap_cr')):,.0f} Cr")
            x2.metric("ROCE / ROE", f"{num(m.get('roce_pct')):.1f}% / {num(m.get('roe_pct')):.1f}%")
            x3.metric("Debt/Equity", f"{num(m.get('debt_to_equity')):.2f}")
            x4.metric("Promoter %", f"{num(m.get('promoter_pct')):.1f}%", f"Δ {num(m.get('promoter_change_qoq')):+.2f}% QoQ")
            fs = m.get("public_float_shares", 0)
            x5.metric("Float Shares", f"{int(fs):,}" if pd.notna(fs) else "—")
            st.caption(f"{m.get('company_name', '')} | Sector: {m.get('sector', '')} – {m.get('sub_industry', '')} | Pledge: {num(m.get('pledge_pct')):.1f}% | CFO/PAT: {num(m.get('cfo_to_pat_ratio')):.2f} | Surveillance: {m.get('asm_gsm_stage', '')}")

            st.markdown("#### 📋 Last 8 Quarters (Point-in-Time Filing Dates)")
            if q_df.empty:
                st.info("No quarterly results synced for this stock yet.")
            else:
                q_show = q_df.copy()
                q_show["quarter_end"] = q_show["quarter_end"].astype(str)
                q_show["filing_date"] = q_show["filing_date"].astype(str)
                st.dataframe(q_show, use_container_width=True, hide_index=True)

            st.markdown("#### 📰 Recent Corporate Filings (AI Catalyst Scores)")
            if f_df.empty:
                st.info("No corporate filings tracked for this stock yet.")
            else:
                f_show = f_df.copy()
                f_show["filing_datetime"] = f_show["filing_datetime"].astype(str)
                st.dataframe(f_show, use_container_width=True, hide_index=True)
        else:
            st.info("Select a candidate above to load its Quarterly X-Ray, filings and fundamental metadata.")

with right_col:
    st.markdown("### 🤖 AI Research & Trade Strategist")
    chat_container = st.container(height=680)
    with chat_container:
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_prompt = st.chat_input("Ask e.g.: 'Find top 5 best stocks for tomorrow' or 'Top 10 Mode A stocks'...")
    if user_prompt:
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        st.session_state.pending_query = user_prompt
        st.rerun()

# --- NON-BLOCKING INTENT EXECUTION: runs AFTER both columns are fully rendered ---
if "pending_query" in st.session_state:
    q = st.session_state.pop("pending_query")
    with st.spinner("Scanning NSE/BSE universe & structuring trade levels..."):
        df_res, ai_reply = parse_user_intent_and_run(q, llm, default_top_n=top_n_slider)
        if not df_res.empty:
            st.session_state.active_picks_df = df_res
        st.session_state.chat_history.append({"role": "assistant", "content": ai_reply})
    st.rerun()