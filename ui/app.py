import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from config import SUPPORTED_MODELS
from data_engine.db_manager import init_db, get_connection
from data_engine.sync_daily import run_daily_eod_pipeline
from ai_brain.llm_router import LLMRouter
from ai_brain.agent_tools import get_top_candidates_df, parse_user_intent_and_run
from backtest.time_machine_test import run_time_machine_validation
from ui.chart_component import render_stock_trade_chart
from ui.custom_screener import render_custom_screener_tab

st.set_page_config(page_title="AlphaSniper NSE/BSE Terminal", layout="wide", initial_sidebar_state="expanded")
init_db()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "active_picks_df" not in st.session_state:
    st.session_state.active_picks_df = get_top_candidates_df(mode="MASTER", top_n=5)

# --- SIDEBAR: SETTINGS & SYNC ---
with st.sidebar:
    st.title("⚡ AlphaSniper")
    st.caption("NSE/BSE Ground-Floor Multibagger & Swing Terminal")

    model_label = st.selectbox("AI Brain Model", list(SUPPORTED_MODELS.keys()), index=1)
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

# --- MAIN SPLIT-SCREEN HYBRID LAYOUT ---
left_col, right_col = st.columns([0.60, 0.40], gap="large")

with left_col:
    st.markdown("### 🎯 Daily Conviction Command Center")
    b1, b2, b3 = st.columns(3)

    if b1.button(f"🔥 Top {top_n_slider} Overall (Master)", use_container_width=True, type="primary"):
        q = f"Find the best top {top_n_slider} stocks for tomorrow morning across all modes."
        df_res, ans = parse_user_intent_and_run(q, llm, default_top_n=top_n_slider)
        st.session_state.active_picks_df = df_res
        st.session_state.chat_history.append({"role": "user", "content": q})
        st.session_state.chat_history.append({"role": "assistant", "content": ans})

    if b2.button(f"🚀 Top {top_n_slider} Mode A (CUPID/STLTECH)", use_container_width=True):
        q = f"Find the top {top_n_slider} best stocks from Mode A (Turnaround & Multibagger Sniper) for tomorrow."
        df_res, ans = parse_user_intent_and_run(q, llm, default_top_n=top_n_slider)
        st.session_state.active_picks_df = df_res
        st.session_state.chat_history.append({"role": "user", "content": q})
        st.session_state.chat_history.append({"role": "assistant", "content": ans})

    if b3.button(f"⚡ Top {top_n_slider} Mode B (Compounders)", use_container_width=True):
        q = f"Find the top {top_n_slider} best stocks from Mode B (High-Velocity Momentum Compounders) for tomorrow."
        df_res, ans = parse_user_intent_and_run(q, llm, default_top_n=top_n_slider)
        st.session_state.active_picks_df = df_res
        st.session_state.chat_history.append({"role": "user", "content": q})
        st.session_state.chat_history.append({"role": "assistant", "content": ans})

    picks_df = st.session_state.active_picks_df
    if not picks_df.empty:
        selected_sym = st.selectbox(
            "Inspect Candidate on TradingView Chart (with Plotted Entry, Stop-Loss & Targets):",
            picks_df["symbol"].tolist()
        )
        sel_row = picks_df[picks_df["symbol"] == selected_sym].iloc[0].to_dict()

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Entry Trigger", f"₹{sel_row['entry_trigger']}", f"Max: ₹{sel_row['max_chase_price']}")
        m2.metric("Structural Stop-Loss", f"₹{sel_row['stop_loss']}", f"-{sel_row['risk_pct']}% Risk")
        m3.metric("Target 1 (2.5R Free)", f"₹{sel_row['target_1']}")
        m4.metric("Target 2 (5R Swing)", f"₹{sel_row['target_2']}")
        m5.metric("50-EMA Runner Stop", f"₹{sel_row['trailing_sl_ema50']}")

        render_stock_trade_chart(sel_row["isin"], selected_sym, sel_row)

    tab1, tab2, tab3 = st.tabs(["📊 Top Picks Breakdown", "🔍 Custom Screener", "🕰️ Time-Machine Results"])
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
        with st.spinner("Scanning NSE/BSE universe & structuring trade levels..."):
            df_res, ai_reply = parse_user_intent_and_run(user_prompt, llm, default_top_n=top_n_slider)
            if not df_res.empty:
                st.session_state.active_picks_df = df_res
            st.session_state.chat_history.append({"role": "assistant", "content": ai_reply})
        st.rerun()