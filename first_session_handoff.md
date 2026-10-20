# AlphaSniper NSE/BSE Terminal — Session Handoff Document
**Last updated:** 2026-10-20 (IST) · **Built for:** any engineer / AI continuing this project
**Workspace:** `D:\nishant tp\new market tool` (git repo) · **Live UI:** http://localhost:8501

---

## 1. What This Project Is

AlphaSniper is a **local, point-in-time NSE/BSE multibagger & swing-scan terminal** that:
1. Stores full price/delivery history in a local **DuckDB** (`local_data/alpha_terminal.duckdb`).
2. Scores ~2,560 stocks daily into two modes and ranks them:
   - **Mode A — Turnaround & Ground-Floor Multibagger Sniper** (delivery float-absorption + operating-leverage turnaround + AI filing catalysts + Stage-1 dormancy breakout).
   - **Mode B — High-Velocity Momentum Compounder** (RS percentile + DVM quality + VCP/Tightness + delivery confirmation).
   - **Master Score** blends both (current formula: `0.45·A + 0.35·B + 0.10·RS + 0.10·DVM`).
3. Computes **institutional 2-part trade plans** per stock: Entry Trigger (pullback zone), structural stop, Target 1 (2.5R — book 30%), Target 2 (5R swing), and an **EMA-65 runner trail** for the remaining 70%.
4. Backtests any historical date through the **Time-Machine engine** (closing-basis stops, intraday emergency guard, Wyckoff shakeout re-entry).
5. Presents everything in a **Streamlit dark UI**: candlestick + delivery chart with all trade lines, metric cards, custom screener, Time-Machine validator, quarterly X-Ray + filings tabs, and an AI Strategist chat panel.

**Stack:** Python 3.14 (.venv) · duckdb · pandas · numpy · Streamlit · Plotly · litellm (Gemini) · yfinance + screener.in + NSE · Upstox API (live quotes) · Playwright (verification).

---

## 2. Folder / Module Map

| Path | Purpose |
|---|---|
| `data_engine/db_manager.py` | DuckDB singleton schema + migrations (`init_db`, `get_connection(read_only)`) |
| `data_engine/nse_bse_fetcher.py` | NSE bhavcopy + corporate announcements (7-day windows) + fundamentals (screener.in / yfinance) + registry |
| `data_engine/backfill_history.py` | Historical candle backfill (`fetch_stock_history`, `write_candle_batch`, `get_backfill_targets`) |
| `data_engine/sync_daily.py` | `run_daily_eod_pipeline(days_back=N)` — one-button daily refresh |
| `data_engine/upstox_client.py` | Live OHLC quote pull → `daily_market` upsert |
| `quant_engine/feature_factory.py` | `compute_and_store_daily_scores(trade_date)` — features, Mode A/B scores, trade levels, full-column UPSERT |
| `quant_engine/scanner_mode_a.py` | Mode-A scoring (float absorption capped 8.0 pts when float/mcap unknown) |
| `quant_engine/scanner_mode_b.py` | Mode-B scoring |
| `quant_engine/trade_architect.py` | Entry/SL/T1/T2/EMA trails; small-caps (<₹5,000 Cr) use 2.2×ATR & 10% SL cap; `emergency_intraday_sl = entry × 0.875` |
| `ai_brain/llm_router.py` | litellm wrapper (models `gemini/gemini-3.5-flash-lite` default, `timeout=20, num_retries=1`) |
| `ai_brain/catalyst_analyzer.py` | Deterministic filing keyword scores (+16 orders / +14 expansion / −18 red flags) + LLM refinement of top 40 |
| `ai_brain/agent_tools.py` | `get_top_candidates_df()`, `parse_user_intent_and_run()`, `build_fallback_trade_plan(df)` — zero-LLM institutional plan |
| `backtest/time_machine_test.py` | Institutional sim: closing-basis stop, `-12.5%` intraday guard, T1→breakeven floor, EMA-65 double-close trail, Wyckoff re-entry (≤1) |
| `ui/app.py` | Streamlit main layout; all CSS fixes; **buttons queue `st.session_state.pending_query`**; executor runs at the very bottom so both columns always render |
| `ui/chart_component.py` | **Native Plotly** trading chart (candles + EMA-50/65 + 4 hline trade levels + volume/delivery subplot) |
| `ui/custom_screener.py` | Filter-form custom screener tab |
| `config.py` | `DEFAULT_LLM_MODEL`, `SUPPORTED_MODELS`, thresholds |
| `.env` | `GEMINI_API_KEY` (working key), `DEFAULT_LLM_MODEL=gemini/gemini-3.5-flash-lite` (has harmless UTF-8 BOM; python-dotenv still parses) |
| `local_data/alpha_terminal.duckdb` | The single data store (single-writer at a time!) |

---

## 3. Current Database State (verified numbers)

| Table | Rows | Notes |
|---|---|---|
| `instruments` | 2,659 | 2,579 NSE-keyed; 2,562/2,564 scored stocks have market-cap & float |
| `daily_market` | **555,977** | 745 trade dates: 2023-10-18 → **2026-10-16** |
| `quarterly_results` | **8,978** | 944 ISINs (screener sync; ~272 scored ISINs still missing quarterlies) |
| `corporate_filings` | **16,007** | 30-day NSE announcements; every row has deterministic base score; 29 LLM-refined |
| `daily_quant_scores` | 4,605 | scored dates: 2025-05-15 (1,015) · 2025-07-01 (1,026) · **2026-10-16 (2,564)** — latest live scan |
| Backfill universe | 1,200 active | 273 → 1,200 after candles-only recovery (610 retried successfully after a Yahoo DNS outage) |

**Latest live scores (2026-10-16):** eligible Mode A = 1,614, Mode B = 1,203, master-scored = 2,564.

### Monday Master Top-10 (as of last rescore)
**ADVANCE 91.95 · PREMIERPOL 88.99 · WSTCSTPAPR 88.55 · TIPSMUSIC 88.19 · AVTNPL 85.60 · SHRINGARMS 84.35 · AURUM 82.52 · SGFIN 82.50 · SHANTIGOLD 80.79 · RSL 80.60**

Mode A leaders: AURUM 82.5 / ADVANCE 79.7 / WSTCSTPAPR 79.3 / AVTNPL 76.2 ...
Mode B leaders: TIPSMUSIC 79.5 / PREMIERPOL 76.0 / CASTROLIND 72.6 / LLOYDSENGG 72.4 / RSL 72.2 ...

### Time-Machine Benchmark wick-fix results (old → new sim)
| Symbol | Old wick-stop sim | **New institutional sim** |
|---|---|---|
| STLTECH | -6.32% | **+6.93%** |
| NETWEB | -7.73% | **+62.15%** |
| CUPID | +179.47% | +179.47% (unchanged) |
| ABDL | +35.82% | **+36.56%** |
| PRIVISCL | — | Wyckoff re-entry verified live: stop d25 → reclaim d35 → trail exit d159 |

---

## 4. Golden Rules / Trade Architecture (do not regress these)

1. **Two-part position:** 30% exits at T1 (SL then moved to cost), 70% runner trails the **EMA-65** (2 consecutive daily closes below it, after day ≥30 and close > entry×1.25).
2. **Small-cap calibration** (`market_cap_cr < 5000`): `sl = min(2.2×ATR, 10% cap)`; larger caps: 1.8×ATR / 9%.
3. **`emergency_intraday_sl = entry_trigger × 0.875`** — intraday-only catastrophe exit (exit at open if gapped below). Stored in `daily_quant_scores.emergency_intraday_sl`.
4. **Structural stop is a DAILY-CLOSE rule** — no more wick shakeouts (this fixed STLTECH/NETWEB).
5. **Wyckoff Shakeout-and-Reclaim:** stopped pre-T1 + close ≥ entry_trigger within 15 sessions → auto 1 re-entry at trigger.
6. **`float_pts` cap = 8.0** when `public_float_shares ≤ 0` AND `market_cap_cr ≤ 0` (prevents fake absorption boost).
7. **UPSERT refreshes every non-key column** (`compute_and_store_daily_scores`) — stale-feature bug fixed generically.
8. Eligibility gates (quick reference): `price > 15`, `liquidity/usdvol ≥ $0.4M`, `delivery_qty > 0`, `q_count ≥ 4` (Mode B even deeper), `master_score ≥ 65`.

---

## 5. How To Run Things (copy-paste patterns)

```powershell
cd "D:\nishant tp\new market tool"

# Start UI (kills stray instances first)
Get-Process python | ? { (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)").CommandLine -like "*streamlit*" } | % { Stop-Process -Id $_.Id -Force }
Start-Process "cmd.exe" -ArgumentList "/c", ".venv\Scripts\streamlit.exe run ui\app.py --server.port 8501 > $env:TEMP\opencode\st_out.txt 2> $env:TEMP\opencode\st_err.txt" -WindowStyle Hidden

# Rescore any date (ALWAYS via temp .py file, never inline python -c — PowerShell mangles quotes)
& ".venv\Scripts\python.exe" -X utf8 "C:\Users\ADMIN\AppData\Local\Temp\opencode\rescore.py"
#   rescore.py content:
#   import sys, os; os.chdir(r"D:\nishant tp\new market tool"); sys.path.insert(0, os.getcwd())
#   from quant_engine.feature_factory import compute_and_store_daily_scores
#   compute_and_store_daily_scores("2026-10-16")

# Daily pipeline (bhavcopy last N days + filings + scores)
run_daily_eod_pipeline(days_back=5)      # data_engine/sync_daily.py

# Backfill more stocks
.venv\Scripts\python.exe data_engine\backfill_history.py --limit 500 --years 2 --workers 8

# Filing sync (windows of 7 days, deterministic scoring at insert)
sync_recent_corporate_announcements(days_back=30)

# LLM refinement of top filings (paced 4s, retryable fallbacks)
score_unprocessed_filings(llm, limit=40)
```

**Verification via Playwright MCP:** navigate `http://localhost:8501` → click `🔥 Top 5 Overall (Master)` → wait for strategist reply → screenshot full page. Chat panel must show the 🏛️ Institutional Trade Plan header (pre-populated on first load via `build_fallback_trade_plan(active_picks_df)`); chart must show all 4 hlines (ENTRY/SL/T1/T2) + EMA-50/65 lines.

---

## 6. Critical Environment Gotchas (learned the hard way)

1. **DuckDB is single-writer.** Concurrent writers → `IOException ... being used by another process`. Sequence writes strictly; `read_only=True` reads also fail while a writer holds the file. **Never run rescore in parallel with backfill.**
2. **Never run inline `python -c` with quotes / `<` from PowerShell** — the shell eats them. Always write a temp `.py` under `C:\Users\ADMIN\AppData\Local\Temp\opencode\` and run it.
3. **`Start-Process` always errors "Unknown: ChildProcess.kill"** in this harness — harmless; the child process survives (verify via `Get-Process`).
4. **Streamlit caches imported modules** — editing `config.py` / `ai_brain/*` / `ui/chart_component.py` requires a full Streamlit restart to take effect (UI rerun only re-executes `app.py`).
5. **`.env`** has a UTF-8 BOM (harmless) and lives at project root. From temp-dir scripts, `load_dotenv()` may fail (it walks from the caller's cwd) — use `dotenv_values(r".env")`.
6. **Yahoo DNS outage** (`query2.finance.yahoo.com` temp resolution failure) killed most backfills once — a candles-only retry later recovered 610/610. If a big backfill fails oddly, retry it an hour later before assuming data is dead.
7. **Screener.in throttles aggressively under parallel load** (probe hangs >90 s). Sequential mode with delays worked around 23:00-06:00 IST. yfinance `fast_info` returns `shares` reliably but NOT `marketCap` for Indian tickers → compute `mcap = shares × latest stored close / 1e7`.
8. **Gemini free-tier quotas (per project/day):**
   - `gemini-3.6-flash` / `3.5-flash`: **20 requests/day** (burned by file-refine quickly; resets ~03:00 IST).
   - `gemini-3.5-flash-lite` / `3.1-flash-lite` / `3-flash-preview`: separate, larger pool → **default model**.
   - `gemini-2.5-flash`, `2.5-flash-lite`, `2.5-pro`: **404 for new API keys** (deprecated tiers).
   - `gemini-3.7/3.8-flash`: paid-only (429 on free keys).
9. **LLM outage never blocks the UI** — `agent_tools.build_fallback_trade_plan(df)` renders the full quant plan instantly on any 429/timeout; `chat_history` is pre-seeded with it on first page load.
10. **Upstox token** is user-supplied via the UI (upstox refresh happens through the sidebar button). Upstox quote sync last ran 2026-10-17 — upserts **2,564 instruments**.

---

## 7. What Was Delivered, Session by Session

**Session 1 — Core engine + UI**
- DuckDB schema; bhavcopy sync (2 years); hand-rolled fundamentals registry (screener + yfinance); Mode A/B scoring; trade_architect with ATR-blended stops; two-part runner plan; Streamlit UI with Time-Machine validator + custom screener + "Top N" buttons; single-writer discipline everywhere.

**Session 2 — The four big fixes**
1. Runner plan wired into `trade_architect` (`pullback_zone`, `max_chase_price`, `runner_trail_ema65`, `trailing_sl_ema50` all stored).
2. Backfill expanded 273 → 500 → 1,200 stocks (Yahoo DNS kill + full recovery pass).
3. UI: ⚡Refresh-live-quotes button (Upstox), Quarterly X-Ray tab, cosy CSS (metric labels 0.78 rem wrap + values 1.15 rem nowrap).
4. Fixed the stale-feature bug: UPSERT now refreshes every non-key column ("rs_percentile stuck at 50.21" mystery).

**Session 3 — Wick-shakeout + filings + clean scoring**
1. Institutional Time-Machine sim (closing-basis stop / intraday −12.5% guard / Wyckoff re-entry) — benchmark table above.
2. NSE filings: 20 → **16,007** rows in 30 days; keyword scoring instantly; 29 top filings refined by Gemini (order-win +14, order-cancel −7 examples).
3. mcap/float repair: yfinance `fast_info`'s shares × last close → 2,562/2,564 scored stocks fixed; `float_pts` capped at 8 for unknowns; fake-boosted KMEW/GRAPHITE/DEEPAKFERT honestly dropped from Master Top-10.

**Session 4 — Visual & UX hardening (final state)**
1. Chart rewritten to native **Plotly** (subplots, hlines, delivery overlay) — lightweight-charts was silently failing in this Streamlit version.
2. LLM panel made non-blocking: handlers only queue `pending_query`; executor runs post-layout; deterministic fallback plan guarantees content.
3. `setTimeout`/quota saga resolved by moving to flash-lite default pool.
4. Startup chat pre-seeded with the deterministic plan for the day's Top 5.
5. Full verification (Playwright): metric cards, 4-line chart, tabs, populated strategist panel — screenshots in `.playwright-mcp\ui_verify_v4_journal.png` and `ui_verify_v5_prepopulated.png`.

---

## 8. Known Gaps / Next-Steps Backlog (priority order)

1. **~272 scored ISINs still without quarterly results** (mostly thinly traded small-caps; screener throttled during session 3 recovery). A slower overnight sweep with retry reports would lift Mode A precision. Files: temp `retry_fundamentals.py` pattern lives in `C:\Users\ADMIN\AppData\Local\Temp\opencode\` (may be gone — recreate from `data_engine/nse_bse_fetcher.py` sync functions).
2. **Gemini daily quota (flash-lite pool)** — track burn; consider dual-provider round-robin with Groq (`groq/llama-3.3-70b`) as fallback provider in `SUPPORTED_MODELS` (already an option in the UI dropdown).
3. **Time-Machine expanded benchmark suite**: batch 20 benchmark symbols (incl. TOMORROWLAND-style multi-baggers) overnight and publish a proper stats table (avg return, MFE/MAE, hold days).
4. **Backfill alerting** — if `query2.finance.yahoo.com` DNS fails again mid-run, auto-schedule a 60-min retry (pattern used in session "candles-only recovery").
5. **International de-dupe**: some ISINs have both NSE + BSE rows; daily_market is keyed by isin so fine, but the UI candidate widget shows NSE symbol only.
6. **Screener-fallback for the 2 remaining zero-fundamentals stocks** (unknown names — query `market_cap_cr <= 0` or `public_float_shares <= 0`).
7. Optional: **CI-style regression harness** — `pytest`-like checks that the 4 benchmark cases (STLTECH/NETWEB/CUPID/ABDL) still return their documented TM numbers after any engine change (temp `test_sim.py` approach).
8. Optional: **Portfolio/PnL module** — persist executed picks + track multi-part runner exits.

---

## 9. Session-Continuation Checklist (for the next AI/engineer)

1. Read §4 & §5 before touching any engine code — the sim/trade rules are the product's core IP.
2. Start the UI, click `🔥 Top 5 Overall (Master)`, and compare the strategist output against the **latest saved screenshot in `.playwright-mcp\`** to confirm the layout still renders.
3. Run ONE rescore for today's date and confirm row count ≈ 2,564 ± weekly drift; if it's way off, check `.venv`, `.env`, and `local_data/alpha_terminal.duckdb` size (should be ~200-400 MB).
4. If a table needs new columns — add them **both** in `db_manager.init_db()` CREATE and via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and remember the UPSERT refreshes generically (§4.7).
5. Editing any engine/UI module → **restart Streamlit** (§6.4).
6. When quota errors appear in the chat panel, confirm they're caught by `build_fallback_trade_plan` and NOT displayed raw to the user.
7. All temp experiment scripts belong in `C:\Users\ADMIN\AppData\Local\Temp\opencode\`; name them verbosely (e.g., `rescore.py`, `test_fb.py`, `top10_lists.py`) so they survive a session.

**The system is production-usable right now** — rescore + click Master + read the plan, Monday morning style.
