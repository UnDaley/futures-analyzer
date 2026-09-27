import math

import pandas as pd

from futures_analyzer.indicators.engine import add_indicators, latest_snapshot
from futures_analyzer.indicators.trend import classify_ema_trend
from futures_analyzer.market_time import bar_end
from tests.conftest import make_hourly_candles

NAN = float("nan")


def test_classify_ema_trend():
    assert classify_ema_trend(close=110, ema20=105, ema50=100, ema200=90) == "bullish"
    assert classify_ema_trend(close=85, ema20=90, ema50=95, ema200=100) == "bearish"
    assert classify_ema_trend(close=99, ema20=105, ema50=100, ema200=90) == "neutral"  # fiyat EMA 50 altına indi
    assert classify_ema_trend(close=100, ema20=NAN, ema50=100, ema200=90) == "unknown"


def test_add_indicators_columns():
    df = add_indicators(make_hourly_candles("2026-06-15 18:00", 50), "1h")

    for column in ["ema_20", "ema_200", "rsi_14", "macd", "macd_signal", "macd_hist", "atr_14", "volume_avg_20", "vwap"]:
        assert column in df.columns


def test_vwap_only_for_intraday():
    df = add_indicators(make_hourly_candles("2026-06-15 18:00", 50), "4h")

    assert "vwap" not in df.columns


def test_snapshot_with_too_little_data_does_not_invent_values():
    df = add_indicators(make_hourly_candles("2026-06-15 18:00", 50), "1h")

    snapshot = latest_snapshot(df, "1h")

    assert snapshot["ema"]["20"] is not None
    assert snapshot["ema"]["200"] is None   # 50 mumla EMA 200 hesaplanamaz
    assert snapshot["ema_trend"] == "unknown"


def test_snapshot_of_steady_uptrend():
    df = add_indicators(make_hourly_candles("2026-06-15 18:00", 300), "1h")

    snapshot = latest_snapshot(df, "1h")

    assert snapshot["ema_trend"] == "bullish"
    assert snapshot["rsi_14"] == 100.0
    assert snapshot["atr_14"] == 3.0          # her mum: high - low = 3
    assert snapshot["relative_volume"] == 1.0  # hacim hep 10
    assert snapshot["above_vwap"] is True
    assert snapshot["close"] == df["close"].iloc[-1]


def test_snapshot_values_are_json_friendly():
    df = add_indicators(make_hourly_candles("2026-06-15 18:00", 300), "1h")

    snapshot = latest_snapshot(df, "1h")

    values = [snapshot["rsi_14"], snapshot["atr_14"], *snapshot["ema"].values(), *snapshot["macd"].values()]
    assert all(isinstance(v, float) and not math.isnan(v) for v in values)
    assert isinstance(snapshot["ts"], str)


def test_bar_end():
    ts = pd.Timestamp("2026-06-16 13:00", tz="UTC")
    assert bar_end(ts, "15m") == pd.Timestamp("2026-06-16 13:15", tz="UTC")
    assert bar_end(ts, "4h") == pd.Timestamp("2026-06-16 17:00", tz="UTC")

    # Günlük mum: yfinance tarihi New York gece yarısı olarak verir, gün 17:00 NY'de (21:00 UTC) kapanır
    daily = pd.Timestamp("2026-06-16 00:00", tz="America/New_York").tz_convert("UTC")
    assert bar_end(daily, "1d") == pd.Timestamp("2026-06-16 21:00", tz="UTC")


def test_last_bar_complete_flag():
    df = add_indicators(make_hourly_candles("2026-06-15 18:00", 30), "1h")
    last_ts = df.index[-1]

    # Mum 1 saat sonra kapanır, veri gecikmesi (15 dk) nedeniyle 1 saat 15 dk sonra kesinleşir
    assert latest_snapshot(df, "1h", now=last_ts + pd.Timedelta(minutes=30))["last_bar_complete"] is False
    assert latest_snapshot(df, "1h", now=last_ts + pd.Timedelta(minutes=70))["last_bar_complete"] is False
    assert latest_snapshot(df, "1h", now=last_ts + pd.Timedelta(minutes=75))["last_bar_complete"] is True
