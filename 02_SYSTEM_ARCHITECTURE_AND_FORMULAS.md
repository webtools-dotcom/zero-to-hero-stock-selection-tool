# 02. SYSTEM ARCHITECTURE, TECH STACK, DATABASE SCHEMA & FORMULAS

## 1. Tech Stack
- **Language:** Python 3.11+
- **Local Analytical Database:** `duckdb` (Single-file columnar analytical DB `alpha_terminal.duckdb` for sub-100ms queries across 2,500+ NSE/BSE equities)
- **Data Processing & Quant:** `pandas`, `numpy`, `scipy`
- **Market Data Sources:**
  - **Upstox API v2 (`requests`):** Uses a 1-year `UPSTOX_ANALYTICS_TOKEN` for official NSE/BSE Instrument Master, Historical Daily/Weekly OHLCV candles, and Batch Live Market Quotes (up to 500 tickers per call).
  - **NSE & BSE Public Data (`requests` with cookie session management):** NSE Daily Full Bhavcopy CSV (Deliverable Quantity & Delivery %), Corporate Announcements API, Shareholding/Free-Float & Promoter Pledge data, ASM/GSM surveillance lists.
  - **Fundamentals (`yfinance` + Screener.in HTML table parser via `beautifulsoup4` / `lxml`):** Quarterly Revenue, Operating Profit, OPM%, Net Profit, EPS, ROCE, ROE, Debt-to-Equity, and 3-year CFO vs. PAT.
- **Multi-AI Layer:** `litellm` + `google-genai` / `groq` (Unified hot-swappable wrapper for Gemini 2.5 Pro/Flash, Groq Llama-3.3-70B / DeepSeek-R1, OpenRouter, OpenAI).
- **Desktop Frontend UI:** `streamlit`, `streamlit-lightweight-charts` (TradingView canvas), `plotly`.

---

## 2. Project Directory Structure

```text
alpha-sniper-terminal/
├── .env.example
├── requirements.txt
├── config.py
├── data_engine/
│   ├── __init__.py
│   ├── db_manager.py
│   ├── upstox_client.py
│   ├── nse_bse_fetcher.py
│   ├── fundamentals_sync.py
│   └── sync_daily.py
├── quant_engine/
│   ├── __init__.py
│   ├── anti_scam_filter.py
│   ├── feature_factory.py
│   ├── trade_architect.py
│   ├── scanner_mode_a.py
│   ├── scanner_mode_b.py
│   └── scanner_master.py
├── ai_brain/
│   ├── __init__.py
│   ├── llm_router.py
│   ├── prompts.py
│   ├── catalyst_analyzer.py
│   └── agent_tools.py
├── backtest/
│   ├── __init__.py
│   └── time_machine_test.py
└── ui/
    ├── __init__.py
    ├── chart_component.py
    ├── custom_screener.py
    └── app.py