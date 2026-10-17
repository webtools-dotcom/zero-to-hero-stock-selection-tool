# 06. SEQUENTIAL PROMPTS FOR YOUR ANTIGRAVITY SESSION

## Prompt 2 (Paste after Prompt 1 finishes creating the base files):
"Now read `05_HISTORICAL_BACKFILL_AND_DEEP_DATA_ENGINE.md` and create both `data_engine/screener_and_nse_ings.py` and `data_engine/backfill_history.py` exactly as specified. 
After creating them:
1. Run `python data_engine/backfill_history.py --limit 60 --years 3` to seed our priority multibagger benchmark stocks (`CUPID`, `STLTECH`, `HFCL`, `TEJASNET`, `NETWEB`, `KAYNES`, `PGEL`, `SHAKTIPUMP`, `TARIL`, `GENUSPOWER`, `ZENTEC`, `WABAG`, etc.) plus the initial batch of NSE equities with 3 years of historical daily candles and 12 quarters of Screener.in P&L data.
2. Run `python data_engine/sync_daily.py` to overlay official NSE Bhavcopy delivery quantities and compute today's Mode A, Mode B, and Master Quant Scores."

---

## Prompt 3 (Paste after Prompt 2 completes the backfill):
"Now let's verify the Mode A, Mode B, and Master Scan engines using `backtest/time_machine_test.py`:
1. Run `python backtest/time_machine_test.py --date 2025-05-15 --mode A --top 10` and `python backtest/time_machine_test.py --date 2025-07-01 --mode MASTER --top 10`.
2. Show me the output table of ranked picks, their Mode A / Mode B scores, Entry Prices, 30D Return %, 90D Return %, Max Peak Multibagger Return %, and Trailing 50-EMA Runner Return %.
3. If any division-by-zero or missing-column edge cases appear on newly listed stocks, fix them cleanly in `quant_engine/feature_factory.py`."

---

## Prompt 4 (Paste to launch and polish the Desktop Terminal):
"Now add a button in the sidebar of `ui/app.py` called `⚡ Live Intraday Quote Refresh (Upstox Batch API)` that calls `UpstoxClient().fetch_batch_live_quotes()` for the active universe during market hours (9:15 AM – 3:30 PM), updates today's live candle & volume in `daily_market`, and recomputes `daily_quant_scores` on the fly so I can catch live breakouts during market hours as well as after market close. Then start the Streamlit server (`streamlit run ui/app.py`) and verify it runs cleanly."