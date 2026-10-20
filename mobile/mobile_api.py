import math
import os
import re
import sys
import threading
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER, SUPPORTED_MODELS, UPSTOX_ACCESS_TOKEN
from data_engine.db_manager import get_connection, init_db

IST = ZoneInfo("Asia/Kolkata")
STATIC_DIR = Path(__file__).resolve().parent / "static"
DB_WRITE_LOCK = threading.Lock()
LLM_LOCK = threading.Lock()
scheduler = BackgroundScheduler(timezone=IST)

MODES = {
    "A": ("mode_a_score", "AND s.mode_a_eligible = TRUE"),
    "B": ("mode_b_score", "AND s.mode_b_eligible = TRUE"),
    "MASTER": ("master_score", "AND (s.mode_a_eligible = TRUE OR s.mode_b_eligible = TRUE)"),
}

STATUS_META = {
    "BUY_NOW": {
        "label": "BUY NOW — IN BREAKOUT ZONE",
        "color": "#00E676",
        "priority": 0,
    },
    "PULLBACK_ZONE": {
        "label": "ACCUMULATE — IN PULLBACK ZONE",
        "color": "#FFD600",
        "priority": 1,
    },
    "WAITING": {
        "label": "WAITING — SET SL-L TRIGGER",
        "color": "#2979FF",
        "priority": 2,
    },
    "SKIP_GAP_UP": {
        "label": "SKIP — GAPPED ABOVE MAX CHASE",
        "color": "#FF1744",
        "priority": 3,
    },
}


class ChatRequest(BaseModel):
    user_query: str = Field(min_length=1, max_length=2000)
    top_n: int = Field(default=5, ge=1, le=25)
    risk_rupees: float = Field(default=2000, gt=0, le=10000000)


def _now_ist() -> datetime:
    return datetime.now(IST)


def _iso_now() -> str:
    return _now_ist().isoformat(timespec="seconds")


def _mode(mode: str) -> str:
    value = (mode or "MASTER").strip().upper()
    if value not in MODES:
        raise HTTPException(status_code=400, detail="mode must be MASTER, A or B")
    return value


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _txt(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        if math.isnan(value):
            return default
    except (TypeError, ValueError):
        pass
    text = str(value)
    if text in ("NaT", "nan", "None"):
        return default
    return text


def _parse_pullback_zone(text: Any, entry: float) -> tuple[float, float]:
    values = re.findall(r"(\d+(?:\.\d+)?)", _txt(text))
    if len(values) >= 2:
        low, high = float(values[0]), float(values[1])
    elif len(values) == 1:
        low, high = float(values[0]), entry
    else:
        low, high = round(entry * 0.95, 2), entry
    low = min(low, entry)
    high = max(high, entry)
    return round(low, 2), round(high, 2)


def _status(price: float, entry: float, zone_low: float, max_chase: float) -> str:
    if entry <= price <= max_chase:
        return "BUY_NOW"
    if zone_low <= price < entry:
        return "PULLBACK_ZONE"
    if price > max_chase:
        return "SKIP_GAP_UP"
    return "WAITING"


def _instruction(status_code: str, shares: int, position_value: int, entry: float,
                 zone_low: float, max_chase: float, stop: float, distance_pct: float) -> str:
    if status_code == "BUY_NOW":
        return (
            f"Buy {shares:,} shares (₹{position_value:,}) now — price is inside the breakout zone "
            f"below Max Chase ₹{max_chase:,.2f} | Set SL @ ₹{stop:,.2f}"
        )
    if status_code == "PULLBACK_ZONE":
        return (
            f"Accumulate {shares:,} shares (₹{position_value:,}) in the ₹{zone_low:,.2f}–₹{entry:,.2f} "
            f"pullback zone | Set SL @ ₹{stop:,.2f}"
        )
    if status_code == "SKIP_GAP_UP":
        return (
            f"Skip — gapped {abs(distance_pct):.1f}% above Max Chase ₹{max_chase:,.2f}. "
            f"Wait for a pullback toward Entry ₹{entry:,.2f}."
        )
    return (
        f"Set SL-L trigger @ ₹{entry:,.2f} — {abs(distance_pct):.1f}% above price. "
        f"Wait for the breakout, do not chase."
    )


def _quarters_map(con, isins: list[str]) -> dict[str, list[dict]]:
    if not isins:
        return {}
    con.execute("CREATE OR REPLACE TEMP TABLE temp_q_isins(isin VARCHAR)")
    con.executemany("INSERT INTO temp_q_isins VALUES (?)", [(str(i),) for i in isins])
    rows = con.execute(
        """
        SELECT isin, quarter_end, sales_cr, opm_pct, net_profit_cr
        FROM (
            SELECT q.isin, q.quarter_end, q.sales_cr, q.opm_pct, q.net_profit_cr,
                   ROW_NUMBER() OVER (PARTITION BY q.isin ORDER BY q.quarter_end DESC) AS rn
            FROM quarterly_results q
            JOIN temp_q_isins t ON t.isin = q.isin
        )
        WHERE rn <= 4
        ORDER BY isin, quarter_end DESC
        """
    ).fetchall()
    result: dict[str, list[dict]] = {}
    for isin_value, quarter_end, sales_cr, opm_pct, net_profit_cr in rows:
        result.setdefault(str(isin_value), []).append({
            "quarter_end": _txt(quarter_end),
            "sales_cr": round(_num(sales_cr), 2),
            "opm_pct": round(_num(opm_pct), 2),
            "net_profit_cr": round(_num(net_profit_cr), 2),
        })
    return result


def _filings_map(con, isins: list[str]) -> dict[str, dict]:
    if not isins:
        return {}
    con.execute("CREATE OR REPLACE TEMP TABLE temp_f_isins(isin VARCHAR)")
    con.executemany("INSERT INTO temp_f_isins VALUES (?)", [(str(i),) for i in isins])
    rows = con.execute(
        """
        SELECT isin, filing_datetime, category, headline, ai_catalyst_score, ai_summary
        FROM (
            SELECT f.*, ROW_NUMBER() OVER (PARTITION BY f.isin ORDER BY f.filing_datetime DESC) AS rn
            FROM corporate_filings f
            JOIN temp_f_isins t ON t.isin = f.isin
        )
        WHERE rn = 1
        """
    ).fetchall()
    result: dict[str, dict] = {}
    for isin_value, filing_datetime, category, headline, ai_catalyst_score, ai_summary in rows:
        result[str(isin_value)] = {
            "filing_datetime": _txt(filing_datetime),
            "category": _txt(category, "NSE Filing"),
            "headline": _txt(headline, "No recent exchange filing in last 30d"),
            "catalyst_score": round(_num(ai_catalyst_score), 2),
            "summary": _txt(ai_summary),
        }
    return result


def _build_picks(mode: str, top_n: int, risk_rupees: float,
                 live_prices: Optional[dict[str, float]] = None,
                 max_price: Optional[float] = None) -> dict:
    mode = _mode(mode)
    top_n = max(1, min(int(top_n), 25))
    risk_rupees = max(float(risk_rupees or 2000), 1.0)
    order_col, where_clause = MODES[mode]
    pool_size = min(max(top_n * 10, 150), 300)
    price_clause = ""
    con = get_connection(memory_limit="48MB")
    try:
        trade_date = con.execute("SELECT MAX(trade_date) FROM daily_quant_scores").fetchone()[0]
        if not trade_date:
            return {
                "trade_date": None,
                "mode": mode,
                "count": 0,
                "generated_at": _iso_now(),
                "picks": [],
            }

        params: list[Any] = [str(trade_date)]
        if max_price is not None:
            price_clause = "AND s.close <= ?"
            params.append(float(max_price))
        params.append(pool_size)

        cursor = con.execute(
            f"""
            SELECT s.*,
                   i.company_name, i.sector, i.asm_gsm_stage, i.roce_pct, i.roe_pct,
                   i.debt_to_equity, i.promoter_pct, i.promoter_change_qoq,
                   i.pledge_pct, i.public_float_shares
            FROM daily_quant_scores s
            LEFT JOIN instruments i ON i.isin = s.isin
            WHERE s.trade_date = CAST(? AS DATE)
              {where_clause}
              {price_clause}
            ORDER BY s.{order_col} DESC NULLS LAST
            LIMIT ?
            """,
            params,
        )
        columns = [column[0] for column in cursor.description]
        scores = [dict(zip(columns, values)) for values in cursor.fetchall()]

        if not scores:
            return {
                "trade_date": str(trade_date),
                "mode": mode,
                "count": 0,
                "generated_at": _iso_now(),
                "picks": [],
            }

        isins = [str(row["isin"]) for row in scores]
        quarters = _quarters_map(con, isins)
        filings = _filings_map(con, isins)
    finally:
        con.close()

    today_str = str(_now_ist().date())
    picks: list[dict] = []
    for row in scores:
        isin = str(row["isin"])
        entry = round(_num(row.get("entry_trigger")), 2)
        stop = round(_num(row.get("stop_loss")), 2)
        max_chase = round(_num(row.get("max_chase_price")), 2)
        zone_low, zone_high = _parse_pullback_zone(row.get("pullback_zone"), entry)
        eod_close = round(_num(row.get("close")), 2)
        stored_live = row.get("live_price")
        stored_live_date = row.get("live_price_date")
        stored_date_text = str(stored_live_date)[:10] if stored_live_date is not None else ""
        use_stored_live = (
            _num(stored_live) > 0
            and stored_date_text == today_str
            and stored_date_text > str(trade_date)[:10]
        )
        price = float(stored_live) if use_stored_live else eod_close
        is_live = bool(live_prices and isin in live_prices and live_prices[isin] > 0)
        if is_live:
            price = float(live_prices[isin])
        price = round(price, 2)
        if price <= 0 or entry <= 0:
            continue

        market_date = _now_ist().date() if is_live else (stored_live_date if use_stored_live else None)
        price_source = "LIVE" if is_live else ("MARKET" if use_stored_live else "EOD")

        risk_per_share = max(entry - stop, 0.5)
        shares = max(int(risk_rupees / risk_per_share), 0)
        position_value = int(round(shares * price))
        distance_pct = round(((price - entry) / entry) * 100.0, 2)
        status_code = _status(price, entry, zone_low, max_chase)
        meta = STATUS_META[status_code]

        score = round(_num(row.get(order_col)), 2)
        filing = filings.get(isin)
        picks.append({
            "isin": isin,
            "symbol": _txt(row.get("symbol")),
            "company_name": _txt(row.get("company_name"), _txt(row.get("symbol"))),
            "primary_mode": _txt(row.get("primary_mode")),
            "sector": _txt(row.get("sector"), "Unknown"),
            "sub_industry": _txt(row.get("sub_industry"), "Unknown"),
            "score": score,
            "mode_a_score": round(_num(row.get("mode_a_score")), 2),
            "mode_b_score": round(_num(row.get("mode_b_score")), 2),
            "master_score": round(_num(row.get("master_score")), 2),
            "price": price,
            "price_source": price_source,
            "eod_close": eod_close,
            "market_date": _txt(market_date),
            "status_code": status_code,
            "status_label": meta["label"],
            "status_color": meta["color"],
            "distance_to_trigger_pct": distance_pct,
            "action_instruction": _instruction(
                status_code, shares, position_value, entry, zone_low, max_chase, stop, distance_pct
            ),
            "recommended_shares": shares,
            "position_value_rupees": position_value,
            "risk_rupees": round(risk_rupees, 2),
            "entry_trigger": entry,
            "pullback_zone": _txt(row.get("pullback_zone")),
            "pullback_zone_low": zone_low,
            "pullback_zone_high": zone_high,
            "max_chase_price": max_chase,
            "stop_loss": stop,
            "risk_pct": round(_num(row.get("risk_pct")), 2),
            "emergency_intraday_sl": round(_num(row.get("emergency_intraday_sl")), 2),
            "target_1": round(_num(row.get("target_1")), 2),
            "target_2": round(_num(row.get("target_2")), 2),
            "trailing_sl_ema50": round(_num(row.get("trailing_sl_ema50")), 2),
            "runner_trail_ema65": round(_num(row.get("runner_trail_ema65")), 2),
            "market_cap_cr": round(_num(row.get("market_cap_cr")), 2),
            "roce_pct": round(_num(row.get("roce_pct")), 2),
            "roe_pct": round(_num(row.get("roe_pct")), 2),
            "debt_to_equity": round(_num(row.get("debt_to_equity")), 2),
            "promoter_pct": round(_num(row.get("promoter_pct")), 2),
            "promoter_change_qoq": round(_num(row.get("promoter_change_qoq")), 2),
            "pledge_pct": round(_num(row.get("pledge_pct")), 2),
            "asm_gsm_stage": _txt(row.get("asm_gsm_stage"), "NONE"),
            "float_absorption_10d_pct": round(_num(row.get("float_absorption_10d_pct")), 2),
            "delivery_spike_mult": round(_num(row.get("delivery_spike_mult")), 2),
            "op_leverage_score": round(_num(row.get("op_leverage_score")), 2),
            "catalyst_score": round(_num(row.get("catalyst_score")), 2),
            "rs_percentile": round(_num(row.get("rs_percentile")), 2),
            "vcp_coil_score": round(_num(row.get("vcp_coil_score")), 2),
            "dvm_quality_score": round(_num(row.get("dvm_quality_score")), 2),
            "quarters": quarters.get(isin, []),
            "latest_filing": filing or {
                "filing_datetime": "",
                "category": "",
                "headline": "No recent exchange filing in last 30d",
                "catalyst_score": 0.0,
                "summary": "",
            },
        })

    picks.sort(key=lambda item: (STATUS_META[item["status_code"]]["priority"], -item["score"]))
    picks = picks[:top_n]
    for rank, item in enumerate(picks, start=1):
        item["rank"] = rank

    return {
        "trade_date": str(trade_date),
        "mode": mode,
        "count": len(picks),
        "generated_at": _iso_now(),
        "picks": picks,
    }


def _active_universe(limit_per_mode: int = 150) -> list[dict]:
    con = get_connection(memory_limit="48MB")
    try:
        trade_date = con.execute("SELECT MAX(trade_date) FROM daily_quant_scores").fetchone()[0]
        if not trade_date:
            return []
        rows = con.execute(
            """
            WITH a AS (
                SELECT s.isin, i.symbol, i.nse_key, i.bse_key
                FROM daily_quant_scores s
                JOIN instruments i ON i.isin = s.isin
                WHERE s.trade_date = CAST(? AS DATE) AND s.mode_a_eligible = TRUE
                ORDER BY s.mode_a_score DESC NULLS LAST
                LIMIT ?
            ), b AS (
                SELECT s.isin, i.symbol, i.nse_key, i.bse_key
                FROM daily_quant_scores s
                JOIN instruments i ON i.isin = s.isin
                WHERE s.trade_date = CAST(? AS DATE) AND s.mode_b_eligible = TRUE
                ORDER BY s.mode_b_score DESC NULLS LAST
                LIMIT ?
            )
            SELECT isin, symbol, nse_key, bse_key FROM a
            UNION
            SELECT isin, symbol, nse_key, bse_key FROM b
            """,
            [str(trade_date), int(limit_per_mode), str(trade_date), int(limit_per_mode)],
        ).fetchall()
    finally:
        con.close()
    return [
        {"isin": row[0], "symbol": row[1], "nse_key": row[2], "bse_key": row[3]}
        for row in rows
    ]


def _run_eod(days_back: int) -> dict:
    from data_engine.sync_daily import run_daily_eod_pipeline

    with DB_WRITE_LOCK:
        run_daily_eod_pipeline(days_back=days_back)
    con = get_connection()
    try:
        latest = con.execute("SELECT MAX(trade_date) FROM daily_quant_scores").fetchone()[0]
        scored = con.execute(
            "SELECT COUNT(*) FROM daily_quant_scores WHERE trade_date = (SELECT MAX(trade_date) FROM daily_quant_scores)"
        ).fetchone()[0]
    finally:
        con.close()
    return {
        "trade_date": _txt(latest),
        "scored_rows": int(scored),
        "completed_at": _iso_now(),
    }


def _scheduled_eod() -> None:
    try:
        print(f"[scheduler] Starting automatic EOD sync at {_iso_now()}")
        result = _run_eod(2)
        print(f"[scheduler] EOD sync complete: {result}")
    except Exception:
        traceback.print_exc()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
    except Exception:
        traceback.print_exc()
    if os.getenv("DISABLE_SCHEDULER", "0") != "1" and not scheduler.running:
        for hour, minute, job_id in ((16, 40, "eod_sync_1640_ist"), (19, 15, "eod_sync_1915_ist")):
            scheduler.add_job(
                _scheduled_eod,
                CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=IST),
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=1800,
            )
        scheduler.start()
        print(
            "[scheduler] EOD sync armed Mon-Fri 16:40 IST and safety retry 19:15 IST — "
            f"next runs: {scheduler.get_job('eod_sync_1640_ist').next_run_time} / {scheduler.get_job('eod_sync_1915_ist').next_run_time}"
        )
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AlphaSniper Mobile API", version="1.0.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/sniper")
@app.get("/sniper/")
def sniper():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/app")
@app.get("/app/")
def app_alias():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.json")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/apple-touch-icon.png")
def apple_touch_icon():
    return FileResponse(STATIC_DIR / "icon-180.png", media_type="image/png")


@app.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC_DIR / "icon-192.png", media_type="image/png")


@app.get("/api/health")
def health():
    payload: dict[str, Any] = {
        "status": "ok",
        "time": _iso_now(),
        "service": "alphasniper-mobile",
    }
    try:
        con = get_connection()
        try:
            latest_score = con.execute("SELECT MAX(trade_date) FROM daily_quant_scores").fetchone()[0]
            latest_market = con.execute("SELECT MAX(trade_date) FROM daily_market").fetchone()[0]
            scored = con.execute(
                "SELECT COUNT(*) FROM daily_quant_scores WHERE trade_date = (SELECT MAX(trade_date) FROM daily_quant_scores)"
            ).fetchone()[0]
        finally:
            con.close()
        payload["database"] = {
            "latest_score_date": _txt(latest_score),
            "latest_market_date": _txt(latest_market),
            "scored_rows": int(scored),
            "size_mb": round(Path(str(ROOT / "local_data" / "alpha_terminal.duckdb")).stat().st_size / (1024 * 1024), 1)
            if (ROOT / "local_data" / "alpha_terminal.duckdb").exists() else None,
        }
    except Exception as exc:
        payload["status"] = "degraded"
        payload["database"] = {"error": str(exc)}
    job = scheduler.get_job("eod_sync_1640_ist") if scheduler.running else None
    retry = scheduler.get_job("eod_sync_1915_ist") if scheduler.running else None
    payload["scheduler"] = {
        "running": bool(scheduler.running),
        "next_eod_run": str(job.next_run_time) if job else None,
        "next_safety_retry": str(retry.next_run_time) if retry else None,
        "cron": "Mon-Fri 16:40 + 19:15 Asia/Kolkata",
    }
    return payload


@app.get("/api/config")
def public_config():
    return {
        "default_provider": DEFAULT_LLM_PROVIDER,
        "default_model": DEFAULT_LLM_MODEL,
        "models": [{"label": label, "provider": provider, "model": model} for label, (provider, model) in SUPPORTED_MODELS.items()],
    }


@app.get("/api/picks")
def picks(
    mode: str = Query(default="MASTER"),
    top_n: int = Query(default=10, ge=1, le=25),
    risk_rupees: float = Query(default=2000, gt=0, le=10000000),
):
    return _build_picks(mode=mode, top_n=top_n, risk_rupees=risk_rupees)


@app.post("/api/live-refresh")
def live_refresh(
    mode: str = Query(default="MASTER"),
    top_n: int = Query(default=10, ge=1, le=25),
    risk_rupees: float = Query(default=2000, gt=0, le=10000000),
    x_upstox_token: Optional[str] = Header(default=None, alias="X-Upstox-Token"),
):
    mode = _mode(mode)
    token = (x_upstox_token or "").strip() or UPSTOX_ACCESS_TOKEN
    if not token:
        raise HTTPException(status_code=400, detail="No Upstox token. Save your token in My Vault.")

    universe = _active_universe(150)
    if not universe:
        raise HTTPException(status_code=503, detail="No scored candidates available for live refresh.")

    keys: list[str] = []
    alias_map: dict[str, str] = {}
    for item in universe:
        isin = str(item["isin"])
        for alias in (item.get("nse_key"), item.get("bse_key"), item.get("symbol")):
            if alias:
                alias_map[str(alias).upper()] = isin
        key = item.get("nse_key") or item.get("bse_key")
        if key:
            keys.append(str(key))

    from data_engine.upstox_client import UpstoxClient

    client = UpstoxClient(access_token=token)
    quotes = client.fetch_batch_live_quotes(keys)
    if not quotes:
        raise HTTPException(status_code=502, detail="Upstox returned no quotes. Your token may have expired.")

    today = _now_ist().date()
    rows: list[tuple[str, float]] = []
    live_prices: dict[str, float] = {}
    seen: set[str] = set()
    for response_key, quote in quotes.items():
        candidates = [str(response_key), str(response_key).split(":")[-1], str(quote.get("symbol") or ""), str(quote.get("instrument_token") or "")]
        isin = None
        for candidate in candidates:
            if candidate and candidate.upper() in alias_map:
                isin = alias_map[candidate.upper()]
                break
        if not isin or isin in seen:
            continue
        last_price = _num(quote.get("last_price"))
        if last_price <= 0:
            continue
        seen.add(isin)
        live_prices[isin] = last_price
        rows.append((isin, last_price))

    if rows:
        with DB_WRITE_LOCK:
            con = get_connection(memory_limit="48MB")
            try:
                con.execute("CREATE OR REPLACE TEMP TABLE temp_mobile_live(isin VARCHAR, close DOUBLE)")
                con.executemany("INSERT INTO temp_mobile_live VALUES (?, ?)", rows)
                con.execute(
                    """
                    UPDATE daily_quant_scores AS s
                    SET live_price = t.close,
                        live_price_date = CAST(? AS DATE),
                        live_updated_at = CURRENT_TIMESTAMP
                    FROM temp_mobile_live t
                    WHERE s.isin = t.isin
                      AND s.trade_date = (SELECT MAX(trade_date) FROM daily_quant_scores);
                    """,
                    [str(today)],
                )
            finally:
                con.close()

    result = _build_picks(mode=mode, top_n=top_n, risk_rupees=risk_rupees, live_prices=live_prices)
    result["live"] = True
    result["updated"] = len(rows)
    result["universe"] = len(universe)
    result["refreshed_at"] = _iso_now()
    import gc

    gc.collect()
    return result


@app.post("/api/eod-sync")
def eod_sync():
    try:
        result = _run_eod(3)
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"EOD sync failed: {exc}") from exc
    result["ok"] = True
    return result


@app.post("/api/chat")
def chat(
    payload: ChatRequest,
    x_llm_provider: Optional[str] = Header(default=None, alias="X-LLM-Provider"),
    x_llm_model: Optional[str] = Header(default=None, alias="X-LLM-Model"),
    x_llm_key: Optional[str] = Header(default=None, alias="X-LLM-Key"),
):
    from ai_brain.agent_tools import (
        build_fallback_trade_plan,
        get_top_candidates_df,
        parse_query_intent,
        parse_user_intent_and_run,
    )
    from ai_brain.llm_router import LLMRouter

    provider = (x_llm_provider or DEFAULT_LLM_PROVIDER).strip().lower()
    if provider not in {"gemini", "groq", "openrouter", "openai"}:
        provider = "gemini"
    model = (x_llm_model or DEFAULT_LLM_MODEL).strip()
    if "/" not in model:
        model = f"{provider}/{model}"
    api_key = (x_llm_key or "").strip()
    chat_mode, chat_top_n, price_cap = parse_query_intent(payload.user_query, payload.top_n)
    df_picks = None
    answer = ""

    if api_key:
        llm = LLMRouter(provider=provider, model=model, api_key=api_key)
        try:
            with LLM_LOCK:
                df_picks, answer = parse_user_intent_and_run(
                    payload.user_query, llm, default_top_n=payload.top_n
                )
        except Exception as exc:
            traceback.print_exc()
            df_picks = get_top_candidates_df(mode=chat_mode, top_n=chat_top_n, max_price=price_cap)
            answer = build_fallback_trade_plan(
                df_picks, mode=chat_mode, top_n=chat_top_n, max_price=price_cap
            )
            answer = f"{answer}\n\n*LLM unavailable ({type(exc).__name__}); deterministic quant plan served instantly.*"
    else:
        df_picks = get_top_candidates_df(mode=chat_mode, top_n=chat_top_n, max_price=price_cap)
        answer = build_fallback_trade_plan(
            df_picks, mode=chat_mode, top_n=chat_top_n, max_price=price_cap
        )
        answer = f"{answer}\n\n*No LLM key saved in My Vault; deterministic quant plan served instantly.*"

    if not isinstance(answer, str) or not answer.strip():
        df_picks = get_top_candidates_df(mode=chat_mode, top_n=chat_top_n, max_price=price_cap)
        answer = build_fallback_trade_plan(
            df_picks, mode=chat_mode, top_n=chat_top_n, max_price=price_cap
        )

    records: list[dict] = []
    if df_picks is not None and not df_picks.empty:
        card_data = _build_picks(
            mode=chat_mode,
            top_n=min(max(len(df_picks), 1), 25),
            risk_rupees=payload.risk_rupees,
            max_price=price_cap,
        )
        records = card_data.get("picks", [])

    return {
        "answer": answer,
        "picks": records,
        "count": len(records),
        "provider": provider,
        "model": model,
        "price_cap": price_cap,
        "generated_at": _iso_now(),
    }
