"""Fetch Screener quarterly fundamentals for every traded instrument that has none yet.
Single thread, ~1 request / 2s, backs off on repeated failures, resumable via a done-log."""
import sys, time, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_engine.db_manager import get_connection
from data_engine.screener_and_nse_ings import DeepIndianFundamentals

done_log = Path(sys.argv[1])
done = set(done_log.read_text().split()) if done_log.exists() else set()
con = get_connection(read_only=True)
todo = con.execute("""
    SELECT isin, symbol FROM instruments
    WHERE isin NOT IN (SELECT isin FROM quarterly_results)
      AND isin IN (SELECT DISTINCT isin FROM daily_market WHERE trade_date >= '2025-06-01')
    ORDER BY symbol
""").fetchall()
con.close()
todo = [(i, s) for i, s in todo if i not in done]
print(f"{len(todo)} instruments to fetch", flush=True)

deep = DeepIndianFundamentals()
ok = miss = streak = 0
for n, (isin, sym) in enumerate(todo, 1):
    data = deep.parse_screener_company(sym)
    if data and data.get("quarterly"):
        for attempt in range(20):   # another process (e.g. git) can briefly lock the DB file
            try:
                deep.write_screener_company(isin, data)
                break
            except Exception as e:
                if "being used by another process" not in str(e) or attempt == 19:
                    raise
                time.sleep(15)
        ok += 1; streak = 0
    else:
        miss += 1; streak += 1
    with done_log.open("a") as f:
        f.write(isin + "\n")
    if streak >= 15:          # likely rate-limited: back off instead of hammering
        print(f"[{n}] {streak} misses in a row, sleeping 10 min", flush=True)
        time.sleep(600); streak = 0
    if n % 50 == 0:
        print(f"[{n}/{len(todo)}] ok={ok} miss={miss}", flush=True)
    time.sleep(2.0 + random.random())
print(f"DONE ok={ok} miss={miss}", flush=True)
