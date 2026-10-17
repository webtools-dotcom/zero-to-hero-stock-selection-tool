import numpy as np
import pandas as pd
from data_engine.db_manager import get_connection
from quant_engine.anti_scam_filter import apply_anti_scam_and_liquidity_flags
from quant_engine.trade_architect import compute_trade_levels_vectorized

def build_point_in_time_features(as_of_date: str) -> pd.DataFrame:
    """
    Extracts point-in-time market, delivery, quarterly fundamental, and catalyst features
    strictly on or before `as_of_date` (zero look-ahead bias).
    """
    con = get_connection()

    market_df = con.execute("""
        SELECT m.isin, m.trade_date, m.open, m.high, m.low, m.close,
               m.volume, m.delivery_qty, m.delivery_pct, m.turnover_cr
        FROM daily_market m
        WHERE m.trade_date <= CAST(? AS DATE)
          AND m.trade_date >= CAST(? AS DATE) - INTERVAL 380 DAY
        ORDER BY m.isin, m.trade_date ASC
    """, [as_of_date, as_of_date]).df()

    if market_df.empty:
        con.close()
        return pd.DataFrame()

    inst_df = con.execute("""
        SELECT isin, symbol, company_name, sector, sub_industry, market_cap_cr,
               public_float_shares, promoter_pct, promoter_change_qoq,
               pledge_pct, pledge_change_qoq, roce_pct, roe_pct,
               debt_to_equity, cfo_to_pat_ratio, asm_gsm_stage
        FROM instruments
    """).df()

    qtr_df = con.execute("""
        SELECT isin, quarter_end, sales_cr, op_profit_cr, opm_pct, net_profit_cr, eps
        FROM quarterly_results
        WHERE filing_date <= CAST(? AS DATE)
        ORDER BY isin, quarter_end ASC
    """, [as_of_date]).df()

    cat_df = con.execute("""
        SELECT isin, MAX(ai_catalyst_score) AS catalyst_raw_score
        FROM corporate_filings
        WHERE CAST(filing_datetime AS DATE) <= CAST(? AS DATE)
          AND CAST(filing_datetime AS DATE) >= CAST(? AS DATE) - INTERVAL 30 DAY
        GROUP BY isin
    """, [as_of_date, as_of_date]).df()
    con.close()

    # Compute Equal-Weighted Market Index Return for Red-Day Resilience
    mkt_daily = market_df.groupby("trade_date")["close"].pct_change().groupby(market_df["trade_date"]).mean()
    red_dates = set(mkt_daily[mkt_daily <= -0.003].tail(5).index)

    # Vectorized grouped rolling metrics per stock
    g = market_df.groupby("isin", group_keys=False)
    market_df["ret_1d"] = g["close"].pct_change()
    market_df["ret_20d"] = g["close"].pct_change(20)
    market_df["ret_60d"] = g["close"].pct_change(60)
    market_df["ret_120d"] = g["close"].pct_change(120)

    market_df["ema_10"] = g["close"].transform(lambda x: x.ewm(span=10, adjust=False).mean())
    market_df["ema_21"] = g["close"].transform(lambda x: x.ewm(span=21, adjust=False).mean())
    market_df["ema_50"] = g["close"].transform(lambda x: x.ewm(span=50, adjust=False).mean())
    market_df["sma_200"] = g["close"].transform(lambda x: x.rolling(200, min_periods=40).mean())

    tr = np.maximum(
        market_df["high"] - market_df["low"],
        np.maximum(
            (market_df["high"] - g["close"].shift(1)).abs(),
            (market_df["low"] - g["close"].shift(1)).abs()
        )
    )
    market_df["tr"] = tr
    market_df["atr_5"] = g["tr"].transform(lambda x: x.rolling(5, min_periods=3).mean())
    market_df["atr_14"] = g["tr"].transform(lambda x: x.rolling(14, min_periods=5).mean())
    market_df["atr_20"] = g["tr"].transform(lambda x: x.rolling(20, min_periods=5).mean())

    market_df["deliv_10d_sum"] = g["delivery_qty"].transform(lambda x: x.rolling(10, min_periods=3).sum())
    market_df["deliv_5d_mean"] = g["delivery_qty"].transform(lambda x: x.rolling(5, min_periods=2).mean())
    market_df["deliv_60d_median"] = g["delivery_qty"].transform(lambda x: x.rolling(60, min_periods=10).median())

    market_df["median_turnover_60d_cr"] = g["turnover_cr"].transform(lambda x: x.rolling(60, min_periods=5).median())
    market_df["median_turnover_20d_cr"] = g["turnover_cr"].transform(lambda x: x.rolling(20, min_periods=5).median())
    market_df["mean_turnover_3d_cr"] = g["turnover_cr"].transform(lambda x: x.rolling(3, min_periods=1).mean())

    market_df["is_circuit"] = ((market_df["high"] - market_df["low"]) / market_df["low"].clip(lower=0.05)) < 0.001
    market_df["circuit_days_20d"] = g["is_circuit"].transform(lambda x: x.rolling(20, min_periods=5).sum())

    market_df["high_20d"] = g["high"].transform(lambda x: x.rolling(20, min_periods=5).max())
    market_df["high_252d"] = g["high"].transform(lambda x: x.rolling(252, min_periods=30).max())
    market_df["low_5d_min"] = g["low"].transform(lambda x: x.rolling(5, min_periods=1).min())
    market_df["high_10d_p85"] = g["high"].transform(lambda x: x.rolling(10, min_periods=3).quantile(0.85))

    # Prior 60d dormancy range (t-65 to t-5)
    market_df["prior_60d_high"] = g["high"].transform(lambda x: x.shift(5).rolling(60, min_periods=15).max())
    market_df["prior_60d_low"] = g["low"].transform(lambda x: x.shift(5).rolling(60, min_periods=15).min())
    market_df["prior_60d_range_pct"] = (market_df["prior_60d_high"] - market_df["prior_60d_low"]) / market_df["prior_60d_low"].clip(lower=0.05)

    # Pocket Pivot: Down-day volume max over last 10 sessions
    market_df["down_vol"] = np.where(market_df["ret_1d"] < 0, market_df["volume"], 0)
    market_df["max_down_vol_10d"] = g["down_vol"].transform(lambda x: x.shift(1).rolling(10, min_periods=3).max())

    # Red-day resilience
    red_df = market_df[market_df["trade_date"].isin(red_dates)].groupby("isin")["ret_1d"].mean().reset_index()
    red_df.rename(columns={"ret_1d": "red_day_avg_ret"}, inplace=True)

    # Slice latest row per ISIN on as_of_date
    latest_date_val = market_df["trade_date"].max()
    snap = market_df[market_df["trade_date"] == latest_date_val].copy()
    snap = snap.merge(inst_df, on="isin", how="left")
    snap = snap.merge(red_df, on="isin", how="left")
    snap = snap.merge(cat_df, on="isin", how="left")
    snap["red_day_avg_ret"] = snap["red_day_avg_ret"].fillna(0.0)
    snap["catalyst_raw_score"] = snap["catalyst_raw_score"].fillna(0.0)

    # Quarterly Operating Leverage & Turnaround Features
    q_features = []
    if not qtr_df.empty:
        for isin_val, q_group in qtr_df.groupby("isin"):
            q_group = q_group.sort_values("quarter_end")
            q0 = q_group.iloc[-1]
            q_prev = q_group.iloc[-2] if len(q_group) >= 2 else q0
            q_yoy = q_group.iloc[-5] if len(q_group) >= 5 else q_prev
            prior_4 = q_group.iloc[-5:-1] if len(q_group) >= 5 else q_group.iloc[:-1]

            loss_to_profit = (q0["net_profit_cr"] > 0) and ((q_prev["net_profit_cr"] <= 0) or (q_yoy["net_profit_cr"] <= 0))
            pat_yoy_pct = ((q0["net_profit_cr"] - abs(q_yoy["net_profit_cr"])) / max(abs(q_yoy["net_profit_cr"]), 0.5)) * 100.0
            sales_yoy_pct = ((q0["sales_cr"] - q_yoy["sales_cr"]) / max(abs(q_yoy["sales_cr"]), 0.5)) * 100.0
            mean_opm_4q = prior_4["opm_pct"].mean() if not prior_4.empty else q_prev["opm_pct"]
            delta_opm = q0["opm_pct"] - mean_opm_4q
            is_8q_high_ebitda = q0["op_profit_cr"] >= q_group.tail(8)["op_profit_cr"].max()

            q_features.append({
                "isin": isin_val,
                "loss_to_profit": loss_to_profit,
                "pat_yoy_pct": pat_yoy_pct,
                "sales_yoy_pct": sales_yoy_pct,
                "delta_opm": delta_opm,
                "is_8q_high_ebitda": is_8q_high_ebitda
            })
    if q_features:
        snap = snap.merge(pd.DataFrame(q_features), on="isin", how="left")
    else:
        snap["loss_to_profit"] = False
        snap["pat_yoy_pct"] = 0.0
        snap["sales_yoy_pct"] = 0.0
        snap["delta_opm"] = 0.0
        snap["is_8q_high_ebitda"] = False

    snap["loss_to_profit"] = snap["loss_to_profit"].fillna(False)
    snap["pat_yoy_pct"] = snap["pat_yoy_pct"].fillna(0.0)
    snap["sales_yoy_pct"] = snap["sales_yoy_pct"].fillna(0.0)
    snap["delta_opm"] = snap["delta_opm"].fillna(0.0)
    snap["is_8q_high_ebitda"] = snap["is_8q_high_ebitda"].fillna(False)

    snap = apply_anti_scam_and_liquidity_flags(snap)
    snap = compute_trade_levels_vectorized(snap)
    return snap

def compute_and_store_daily_scores(as_of_date: str) -> pd.DataFrame:
    from quant_engine.scanner_mode_a import score_mode_a
    from quant_engine.scanner_mode_b import score_mode_b
    from quant_engine.scanner_master import compute_master_ranking

    snap = build_point_in_time_features(as_of_date)
    if snap.empty:
        return pd.DataFrame()

    snap = score_mode_a(snap)
    snap = score_mode_b(snap)
    snap = compute_master_ranking(snap)

    cols = [
        "isin", "trade_date", "symbol", "close", "market_cap_cr", "sub_industry",
        "mode_a_eligible", "mode_b_eligible", "mode_a_score", "mode_b_score",
        "master_score", "primary_mode", "float_absorption_10d_pct",
        "delivery_spike_mult", "op_leverage_score", "catalyst_score",
        "dormancy_score", "dvm_quality_score", "rs_percentile",
        "vcp_coil_score", "sector_sympathy_score", "entry_trigger",
        "pullback_zone", "max_chase_price", "stop_loss", "risk_pct",
        "target_1", "target_2", "trailing_sl_ema50"
    ]
    to_save = snap[cols].copy()
    con = get_connection()
    con.register("temp_scores", to_save)
    con.execute("""
        INSERT INTO daily_quant_scores
        SELECT * FROM temp_scores
        ON CONFLICT (isin, trade_date) DO UPDATE SET
            mode_a_score = EXCLUDED.mode_a_score,
            mode_b_score = EXCLUDED.mode_b_score,
            master_score = EXCLUDED.master_score,
            primary_mode = EXCLUDED.primary_mode,
            entry_trigger = EXCLUDED.entry_trigger,
            stop_loss = EXCLUDED.stop_loss,
            target_1 = EXCLUDED.target_1,
            target_2 = EXCLUDED.target_2,
            trailing_sl_ema50 = EXCLUDED.trailing_sl_ema50;
    """)
    con.close()
    return snap