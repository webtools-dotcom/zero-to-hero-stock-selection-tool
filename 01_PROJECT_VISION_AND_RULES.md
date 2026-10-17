# 01. PROJECT VISION, CORE RULES & NON-NEGOTIABLES

## 1. What We Are Building
We are building **AlphaSniper Terminal**, an institutional-grade, local-first personal stock research, screening, and trade-structuring terminal for the Indian stock market (**NSE & BSE equities**).

The primary objective of this tool is to identify **asymmetric medium-to-long-term winners (1–2 months to 12+ months holding horizon)** before they become obvious to retail screeners:
1. **Ground-Floor Multibaggers & Turnarounds (Mode A):** Catching dormant small-cap, micro-cap, and mid-cap stocks right as institutional accumulation and fundamental inflection begin (e.g., catching **CUPID** at ₹2.5–₹15 before its rally to ₹350+, or **STLTECH** at ₹85–₹120 right as its quarterly operating margin inflected before rallying to ₹1,000+).
2. **High-Velocity Sector & Momentum Compounders (Mode B):** Catching quality growth leaders and sector sympathy runners (like **HFCL**) coiling in tight volatility contractions (VCP / Pocket Pivots / Inside Bars) right before their next explosive leg up.
3. **Actionable Daily Conviction Engine:** Every day, when the user asks for the **Top N (e.g., Top 5 or Top 10) best stocks for tomorrow morning**, the system evaluates the entire universe and outputs the strongest picks along with a complete, deterministic trade plan:
   - Exact **Entry Trigger Price** & **Pullback Buy Zone**
   - **Max Chase Price** (to avoid buying overextended morning gap-ups)
   - Volatility-adjusted **Structural Stop-Loss (SL)**
   - **Target 1 (2.5R Free-Ride Partial Exit)** & **Target 2 (5R Swing Target)**
   - **Multibagger Trailing Stop Rule** (Weekly 10-EMA / Daily 50-EMA) so 10x runners are ridden all the way up without premature exit caps.

---

## 2. What We EXPLICITLY WANT in This Tool
1. **Three Core Daily Scan Modes (Accessible via 1-Click UI Buttons AND Natural Language Chat):**
   - **Master Scan ("Best Top N Stocks for Tomorrow Morning"):** Pools Mode A and Mode B together and picks the absolute highest-conviction N setups across the entire market (even if all N come from one mode).
   - **Mode A ("Top N Ground-Floor Multibagger / Turnaround Snipers"):** Hunts across **ALL price levels (₹2 to ₹5,000+)** using Free-Float Delivery Absorption, Quarterly Operating Leverage Inflection (Delta OPM% & loss-to-profit flips), AI Corporate Filing Catalyst Asymmetry, and Stage-1 Dormancy Breakouts.
   - **Mode B ("Top N High-Velocity Momentum Compounders"):** Hunts in liquid trends (≥ ₹3 Cr daily turnover) using a custom DVM+ Score (Durability + Valuation/Acceleration + Momentum), Anti-Gravity Relative Strength on red market days, Technical Coils (VCP/Pocket Pivots), and Micro-Sector Sympathy.
2. **Smart "Ignition Liquidity" & Anti-Scam Shield:**
   - Instead of excluding small/micro-caps with high 60-day turnover thresholds, Mode A allows stocks with a 60-day median turnover as low as **₹15 Lakhs/day** PROVIDED their **last 3-day average turnover has surged above ₹75 Lakhs/day** (catching the exact week a dormant stock wakes up).
   - Automatically filters out operator circuit traps (>12 of last 20 days locked in `High == Low` circuits), GSM Stage 2–4 shells, excessive promoter pledging (>25% unless falling rapidly), and retail-dilutive QIP/Rights issues.
3. **Desktop Split-Screen Hybrid UI (Visual Dashboard + AI Analyst Chat):**
   - **Left Panel (60% width):** 1-Click Scan buttons, Top N Leaderboard table, Interactive **TradingView Lightweight Chart** (with Entry, SL, Target 1, Target 2, and EMA-50 plotted directly on the chart), Fundamental Quarterly X-Ray tab, NSE Corporate Announcements tab, and a custom Screener.in/Chartink-style SQL/Filter playground.
   - **Right Panel (40% width):** Persistent AI Research Analyst Chat connected directly to the Python Quant Engine tools.
4. **Hot-Swappable Multi-LLM Brain:**
   - Must support **Google Gemini API**, **Groq API**, **OpenRouter**, and **OpenAI** seamlessly via an API key input in the UI sidebar or `.env`.
5. **Time-Machine Point-in-Time Backtester (`time_machine_test.py`):**
   - Allows passing any historical date (`--date YYYY-MM-DD --mode A --top 10`) to verify without look-ahead bias that the scanner surfaces stocks like CUPID, STLTECH, and HFCL at the start of their moves, and measures 30d, 90d, Max Peak, and Trailing-Stop returns.

---

## 3. What We EXPLICITLY DO NOT WANT (Strict Guardrails)
We previously built a different tool (`nse-trading-assistant`) that was overly academic and conservative. **DO NOT repeat any of the following anti-patterns:**
1. **NO "Today Is Not Our Day" Refusal Gates:** Never block the scanner or return 0 stocks because Nifty 50 is red or India VIX is high or calm. In the Indian market, individual small/mid-cap turnarounds and sector breakouts happen in every regime. The tool must ALWAYS rank and return the best relative Top N outliers requested.
2. **NO ₹25 Crore Turnover Handcuff:** Never hard-code a high 60-day median turnover floor like ₹25 Cr, which deletes 95% of future 10x multibaggers before they grow. Use our **Ignition Liquidity Rule** instead.
3. **NO `RSI < 30` Oversold Dip-Buying Strategy:** We are not looking for 4-day mean-reversion trades that make +0.5% crumbs. We are hunting high-velocity breakouts, institutional delivery absorption, and fundamental turnarounds.
4. **NO Hard Code Gates Blocking Parabolic/High-Momentum Setups:** Never reject a stock because it has high momentum or require a fixed -8% / +16% cap.
5. **NO Upstox Portfolio/Holdings Integration & NO Order Execution:** We only use Upstox API for **Master Instruments, Historical Candles, and Live Market Quotes**. Do not build portfolio syncing or order placement endpoints.
6. **NO Telegram Bot or Mobile Watchers:** Keep 100% of the architecture focused on the local **Desktop Split-Screen UI + Local DuckDB Engine**.