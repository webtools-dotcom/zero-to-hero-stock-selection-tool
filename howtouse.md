Look at the chart for **ADVANCE** in your screenshot—that is the exact visual signature we designed this terminal to catch:

* Months of quiet sideways consolidation around ₹100–₹125 tightly hugging the yellow **EMA-50** and orange **EMA-65** lines.


* A sudden **15 Million share delivery volume spike** on the far right of the bottom pane.


* All four institutional levels plotted cleanly on the canvas: **Entry Trigger (`₹164.71`)**, **Structural Stop-Loss (`₹148.24`)**, **Target 1 (`₹205.88`)**, and **Target 2 (`₹247.06`)**.



---

### 💡 Why the Right Chat Box Looked Empty in Your Chrome Tab (And How to Trigger It)

In your screenshot, the white chat container above `Ask e.g.: 'Find top 5 best stocks for tomorrow'...` is blank for a simple reason: **Streamlit stores `chat_history` separately for each browser tab**. When Antigravity clicked **`🔥 Top 5 Overall (Master)`**, it clicked it inside its own test browser, so the report appeared in Antigravity's tab rather than your Chrome tab.

* **In your Chrome window:** Scroll to the top of the left panel and click **`🔥 Top 5 Overall (Master)`** (or type `"Find the top 5 best stocks for tomorrow morning"` in the bottom-right chat input box and press Enter), and the right panel will immediately fill with the complete execution plan.


* **Optional Auto-Load Tweak:** If you want the right-hand panel to already be filled with the Top 5 Master Trade Plan the instant you open `localhost:8501` (without even clicking a button), paste this one-line instruction into Antigravity:
> *"In `ui/app.py`, when `st.session_state.chat_history` is initialized on startup, pre-populate it with one assistant message containing `build_fallback_trade_plan(st.session_state.active_picks_df)` so the right-hand AI Strategist panel is already filled on initial page load."*



---

### 🏆 Your Daily 2-Minute Operating Playbook

Now that your system is completely built and populated with 1,200+ active stocks, 555,000+ daily candles, Screener quarterly P&L data, and 16,000+ scored NSE filings, here is how to run it every day:

1. **Evening Routine (After 4:30 PM IST on Trading Days):**
* Open `http://localhost:8501` and click **`🔄 Run Daily EOD Data Sync`** in the sidebar.


* In ~60 seconds, it pulls that day's official NSE Bhavcopy delivery quantities (`DELIV_QTY`), fetches the latest corporate filings, and recomputes all **Mode A**, **Mode B**, and **Master** scores.
* Click **`🔥 Top 5 Overall`**, **`🚀 Mode A`**, or **`⚡ Mode B`** (or ask the chat for Top 10) to build your watchlist for the next morning.


2. **Morning / Live Market Routine (9:20 AM – 3:30 PM IST):**
* Click **`⚡ Refresh Live Market Quotes (Upstox API)`** in the sidebar.


* Check which watchlist stocks are crossing their **Blue Entry Trigger line** without gapping above their **Max Chase Price**.


* Inspect the **`🧬 Stock Quarterly X-Ray & Filings`** tab for 30 seconds before placing the trade on Upstox to verify the quarterly OPM% trend and recent announcements.




3. **Position Management (The Multibagger Rule):**
* Place your initial stop at the **Structural Stop-Loss** (daily closing basis, with the `-12.5%` catastrophe intraday guard).
* Book **30% quantity at Target 1 (2.5R)** and trail the remaining **70% runner** using the **EMA-65 Runner Trail** so you ride the next **CUPID** or **STLTECH** for its entire multi-month wave.