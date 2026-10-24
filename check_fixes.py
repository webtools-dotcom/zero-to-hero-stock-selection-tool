"""Self-check for the red-day, estimated-delivery and backtest-bias fixes. Run: python check_fixes.py"""
import duckdb
import numpy as np
import pandas as pd

from backtest.time_machine_test import ROUND_TRIP_COST_PCT, find_fill, simulate_two_part_plan
from data_engine.db_manager import scrub_estimated_delivery
from quant_engine.feature_factory import market_red_days, neutralize_snapshot_fundamentals
from quant_engine.scanner_mode_a import score_mode_a


def check_red_days():
    # Day 2: both stocks -1% (red). Day 3: +5% and -1% -> average +2% (not red).
    df = pd.DataFrame({
        "isin": ["A", "A", "A", "B", "B", "B"],
        "trade_date": [1, 2, 3, 1, 2, 3],
        "close": [100.0, 99.0, 103.95, 1000.0, 990.0, 980.1],
    })
    df["ret_1d"] = df.groupby("isin")["close"].pct_change()
    assert market_red_days(df) == {2}, market_red_days(df)


def check_scrub_estimated_delivery():
    con = duckdb.connect()
    con.execute("CREATE TABLE daily_market (volume BIGINT, delivery_qty BIGINT, delivery_pct DOUBLE)")
    con.execute("INSERT INTO daily_market VALUES (1001, 450, 45.0), (1000, 450, 45.0), (1000, 700, 70.0)")
    scrub_estimated_delivery(con)
    rows = con.execute("SELECT delivery_qty FROM daily_market ORDER BY delivery_qty NULLS FIRST").fetchall()
    # floor(1001*0.45)=450 and floor(1000*0.45)=450 are both the fake fingerprint; 700 is real
    assert rows == [(None,), (None,), (700,)], rows


def check_missing_delivery_scores_zero():
    base = dict(public_float_shares=1e7, volume=1e5, market_cap_cr=500.0, loss_to_profit=False,
                pat_yoy_pct=0.0, delta_opm=0.0, is_8q_high_ebitda=False, catalyst_raw_score=0.0,
                prior_60d_range_pct=0.5, close=100.0, sma_200=200.0, high_20d=200.0, mode_a_eligible=True)
    df = pd.DataFrame([
        {**base, "deliv_10d_sum": np.nan, "deliv_5d_mean": np.nan, "deliv_60d_median": np.nan},
        {**base, "deliv_10d_sum": 1e6, "deliv_5d_mean": 6e5, "deliv_60d_median": 1e5},
    ])
    s = score_mode_a(df)["mode_a_score"]
    assert np.isfinite(s.iloc[0]), s.iloc[0]    # missing delivery -> finite score, not NaN
    assert s.iloc[1] == s.iloc[0], s.iloc[1]    # delivery is display-only: it never moves the score


def check_profit_growth_drives_mode_a():
    base = dict(public_float_shares=1e7, volume=1e5, market_cap_cr=500.0, loss_to_profit=False,
                delta_opm=0.0, is_8q_high_ebitda=False, catalyst_raw_score=0.0, prior_60d_range_pct=0.5,
                close=100.0, sma_200=200.0, high_20d=200.0, mode_a_eligible=True,
                deliv_10d_sum=np.nan, deliv_5d_mean=np.nan, deliv_60d_median=np.nan)
    df = pd.DataFrame([{**base, "pat_yoy_pct": 120.0}, {**base, "pat_yoy_pct": 0.0, "loss_to_profit": True}])
    s = score_mode_a(df)["mode_a_score"]
    # Growth is a percentile rank (1.0 vs 0.5 of 20 pts); the loss-to-profit flip adds nothing
    assert round(s.iloc[0] - s.iloc[1], 2) == round(10 * 100 / 73, 2), (s.iloc[0], s.iloc[1])

    # Rank scoring: three stocks that all beat the old 120% cap still get distinct scores
    df3 = pd.DataFrame([{**base, "pat_yoy_pct": g} for g in (150.0, 300.0, 900.0)])
    assert score_mode_a(df3)["mode_a_score"].round(2).nunique() == 3


def check_neutralized_fundamentals():
    snap = pd.DataFrame({"total_shares": [1e7, 2e7], "close": [50.0, 10.0], "roce_pct": [40.0, 5.0],
                         "roe_pct": [30.0, 2.0], "debt_to_equity": [0.0, 3.0], "cfo_to_pat_ratio": [1.5, 0.1],
                         "pledge_pct": [60.0, 0.0], "pledge_change_qoq": [0.0, 0.0],
                         "promoter_change_qoq": [1.0, -1.0], "asm_gsm_stage": ["GSM Stage II", "NONE"]})
    out = neutralize_snapshot_fundamentals(snap)
    for col in ["roce_pct", "roe_pct", "debt_to_equity", "cfo_to_pat_ratio", "pledge_pct", "asm_gsm_stage"]:
        assert out[col].nunique() == 1, col     # same value for every stock -> can't affect ranking
    assert out["market_cap_cr"].tolist() == [50.0, 20.0]


def check_fill_and_costs():
    fwd = pd.DataFrame({"open": [100.0, 101.0, 112.0, 104.0], "high": [102.0, 103.0, 113.0, 106.0],
                        "low": [99.0, 100.0, 111.0, 103.0], "close": [101.0, 102.0, 112.0, 105.0]})
    assert find_fill(fwd, entry_trigger=105.0, max_chase=110.0) == (3, 105.0)   # day 3 gapped above chase
    assert find_fill(fwd, entry_trigger=101.5, max_chase=110.0) == (0, 101.5)
    assert find_fill(fwd, entry_trigger=105.0, max_chase=110.0, window=3) is None

    flat = pd.DataFrame({"open": [100.0] * 5, "high": [100.0] * 5, "low": [100.0] * 5,
                         "close": [100.0] * 5, "ema_65": [100.0] * 5})
    ret, _ = simulate_two_part_plan(flat, 100.0, stop_loss=90.0, target_1=125.0, entry_trigger=100.0)
    assert abs(ret + ROUND_TRIP_COST_PCT) < 1e-9, ret


if __name__ == "__main__":
    for check in [check_red_days, check_scrub_estimated_delivery, check_missing_delivery_scores_zero,
                  check_profit_growth_drives_mode_a, check_neutralized_fundamentals, check_fill_and_costs]:
        check()
        print("ok", check.__name__)
