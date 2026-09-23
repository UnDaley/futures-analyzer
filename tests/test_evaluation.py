import json

import numpy as np
import pandas as pd

from futures_analyzer.analysis import MarketData, build_snapshot
from futures_analyzer.data.storage import load_analyses, save_candles
from futures_analyzer.evaluation.backtest import records_to_frame, run_backtest
from futures_analyzer.evaluation.journal import evaluate_pending, record_analysis
from futures_analyzer.evaluation.outcomes import direction_correct, forward_returns, scenario_outcome
from futures_analyzer.evaluation.stats import score_bucket, summarize
from futures_analyzer.instruments import get_instrument

T0 = pd.Timestamp("2026-06-16 14:00", tz="UTC")


def flat_5m(start=T0, hours=30, price=100.0):
    index = pd.date_range(start, periods=hours * 12, freq="5min")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 10.0}, index=index)


def set_bar(df, minutes_after, **values):
    ts = T0 + pd.Timedelta(minutes=minutes_after)
    for column, value in values.items():
        df.loc[ts, column] = value


SCENARIOS = {
    "bullish": {"trigger_level": 105, "targets": [{"level": 110}], "invalidation_level": 95},
    "bearish": {"trigger_level": 95, "targets": [{"level": 90}], "invalidation_level": 105},
}


# --- Sonuç ölçümü ---

def test_forward_returns():
    df = flat_5m()
    df.loc[df.index >= T0 + pd.Timedelta(hours=3), "close"] = 101.0  # 3. saatten sonra 101

    returns = forward_returns(df, T0, price=100.0)

    assert returns == {"1h": 0.0, "4h": 1.0, "1d": 1.0}


def test_forward_returns_pending_when_future_missing():
    assert forward_returns(flat_5m(hours=2), T0, 100.0)["4h"] is None


def test_direction_correct():
    assert direction_correct("bullish", {"4h": 0.5}) is True
    assert direction_correct("bearish", {"4h": 0.5}) is False
    assert direction_correct("neutral", {"4h": 0.5}) is None
    assert direction_correct("bullish", {"4h": None}) is None


def test_bullish_trigger_then_target():
    df = flat_5m()
    set_bar(df, 30, close=106.0, high=106.0)   # tetik: kapanış 105 üstü
    set_bar(df, 60, high=110.5, close=108.0)   # hedef 110'a dokundu

    outcome = scenario_outcome(df, T0, SCENARIOS)

    assert outcome["triggered"] == "bullish"
    assert outcome["result"] == "bullish_target"


def test_bearish_trigger_then_invalidated():
    df = flat_5m()
    set_bar(df, 30, close=94.0, low=94.0)      # bearish tetik
    set_bar(df, 60, close=106.0, high=106.0)   # 105 üstü kapanış = invalidation

    assert scenario_outcome(df, T0, SCENARIOS)["result"] == "bearish_invalidated"


def test_wick_alone_does_not_trigger():
    df = flat_5m()
    set_bar(df, 30, high=107.0)  # iğne 105'i aştı ama kapanış 100

    assert scenario_outcome(df, T0, SCENARIOS)["result"] == "no_trigger"


def test_target_and_invalidation_in_same_bar_is_ambiguous():
    df = flat_5m()
    set_bar(df, 30, close=106.0, high=106.0)
    set_bar(df, 60, high=111.0, low=90.0, close=94.0)  # hem hedef hem invalidation

    assert scenario_outcome(df, T0, SCENARIOS)["result"] == "ambiguous"


def test_scenario_pending_until_window_ends():
    assert scenario_outcome(flat_5m(hours=5), T0, SCENARIOS)["result"] == "pending"


# --- İstatistik ---

def record(bias, score, ret_4h, correct, scenario=None):
    return {
        "bias": bias, "score_total": score,
        "evaluation": {
            "complete": True, "returns": {"1h": 0, "4h": ret_4h, "1d": ret_4h},
            "direction_correct": correct, "scenario": scenario or {"result": "no_trigger"},
        },
    }


def test_score_buckets_match_bias_thresholds():
    assert [score_bucket(s) for s in (-40, -15, -14.9, 14.9, 15, 30)] == ["<=-30", "-30..-15", "-15..15", "-15..15", "15..30", ">=30"]


def test_summarize():
    records = [
        record("bullish", 40, 0.5, True, {"triggered": "bullish", "result": "bullish_target"}),
        record("bullish", 20, -0.5, False, {"triggered": "bullish", "result": "bullish_invalidated"}),
        record("bearish", -20, -1.0, True),
        record("neutral", 0, 0.2, None),
        {"bias": "bullish", "score_total": 50, "evaluation": {"complete": False}},  # sayılmaz
    ]

    summary = summarize(records)

    assert summary["evaluated"] == 4
    assert summary["by_bias"]["bullish"] == {"count": 2, "hit_rate_4h": 50.0, "avg_return_4h": 0.0, "avg_return_1d": 0.0}
    assert summary["by_score"][">=30"]["count"] == 1
    assert summary["scenarios"]["primary_triggered"] == 2
    assert summary["scenarios"]["primary_target_rate"] == 50.0


# --- Günlük (kayıt + değerlendirme) ---

def test_record_and_evaluate(engine):
    df = flat_5m()
    df.loc[df.index >= T0 + pd.Timedelta(hours=2), "close"] = 102.0
    save_candles(engine, "NQ", "5m", df)
    snapshot = {
        "instrument": "NQ", "as_of": T0.isoformat(), "price": 100.0,
        "score": {"bias": "bullish", "total": 30.0, "coverage": 80}, "scenarios": SCENARIOS,
    }

    analysis_id = record_analysis(engine, snapshot)
    assert evaluate_pending(engine) == 1

    saved = load_analyses(engine)[0]
    assert saved["id"] == analysis_id
    assert saved["evaluation"]["returns"]["4h"] == 2.0
    assert saved["evaluation"]["direction_correct"] is True
    assert evaluate_pending(engine) == 0  # tamamlananlar tekrar ölçülmez


# --- Backtest: geleceği görme olmamalı ---

def synthetic_market(days=12, seed=7) -> MarketData:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-06-01 22:00", periods=days * 24 * 12, freq="5min", tz="UTC")
    close = pd.Series(20000 + rng.normal(0, 5, len(index)).cumsum(), index=index).round(2)
    five = pd.DataFrame({"open": close.shift(1).fillna(close.iloc[0]), "close": close})
    five["high"] = five[["open", "close"]].max(axis=1) + 2
    five["low"] = five[["open", "close"]].min(axis=1) - 2
    five["volume"] = rng.integers(50, 500, len(index)).astype(float)

    def resample(rule):
        return five.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

    candles = {"1d": resample("1D"), "4h": resample("4h"), "1h": resample("1h"), "15m": resample("15min"), "5m": five}
    return MarketData(instrument=get_instrument("NQ"), candles=candles, related_hourly={}, macro={})


def test_snapshot_does_not_use_future_data():
    data = synthetic_market()
    now = pd.Timestamp("2026-06-09 15:30", tz="UTC")
    past_only = MarketData(
        instrument=data.instrument,
        candles={tf: df[df.index < now] for tf, df in data.candles.items()},
        related_hourly={}, macro={},
    )

    with_future = json.dumps(build_snapshot(data, now), sort_keys=True, default=str)
    without_future = json.dumps(build_snapshot(past_only, now), sort_keys=True, default=str)

    assert with_future == without_future


def test_run_backtest():
    data = synthetic_market()
    start, end = pd.Timestamp("2026-06-08 14:00", tz="UTC"), pd.Timestamp("2026-06-09 14:00", tz="UTC")

    records = run_backtest(data, start, end, pd.Timedelta("4h"))

    assert len(records) >= 5
    assert all(r["evaluation"]["complete"] for r in records)
    frame = records_to_frame(records)
    assert {"as_of", "score_total", "ret_4h", "scenario_result", "pts_trend"} <= set(frame.columns)
