"""Gösterge motoru: mumlara bütün göstergeleri ekler ve son durumu özetler.

add_indicators  -> her mum için gösterge kolonları (grafik, backtest için)
latest_snapshot -> son mumun özet sözlüğü (ileride Claude'a gidecek JSON'un parçası)
"""

import math

import pandas as pd

from futures_analyzer.indicators.calculations import atr, ema, macd, rsi, sma
from futures_analyzer.indicators.trend import classify_ema_trend
from futures_analyzer.indicators.vwap import session_vwap
from futures_analyzer.market_time import is_bar_complete

EMA_PERIODS = [20, 50, 100, 200]
RSI_PERIOD = 14
ATR_PERIOD = 14
VOLUME_AVG_PERIOD = 20

# VWAP seans içi bir göstergedir; günlük ve 4H mumlarda anlamlı değil.
VWAP_TIMEFRAMES = {"1h", "15m", "5m"}


def add_indicators(candles: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Mumların yanına gösterge kolonlarını ekleyip yeni bir DataFrame döndürür."""
    df = candles.copy()
    for period in EMA_PERIODS:
        df[f"ema_{period}"] = ema(df["close"], period)
    df[f"rsi_{RSI_PERIOD}"] = rsi(df["close"], RSI_PERIOD)
    df = df.join(macd(df["close"]))
    df[f"atr_{ATR_PERIOD}"] = atr(df, ATR_PERIOD)
    df[f"volume_avg_{VOLUME_AVG_PERIOD}"] = sma(df["volume"], VOLUME_AVG_PERIOD)
    if timeframe in VWAP_TIMEFRAMES:
        df["vwap"] = session_vwap(df)
    return df


def latest_snapshot(df: pd.DataFrame, timeframe: str, now: pd.Timestamp | None = None) -> dict:
    """Son mumun gösterge değerlerini sade bir sözlük olarak döndürür.

    Hesaplanamayan değerler None olur. Hiçbir değer tahmin edilmez.
    """
    last = df.iloc[-1]
    close = float(last["close"])
    volume_avg = _value(last, f"volume_avg_{VOLUME_AVG_PERIOD}")
    vwap = _value(last, "vwap")

    return {
        "timeframe": timeframe,
        "ts": df.index[-1].isoformat(),
        # Kapanmamış mumun hacmi ve fiyatı henüz kesin değildir (örn. relative_volume düşük görünür).
        "last_bar_complete": is_bar_complete(df.index[-1], timeframe, now),
        "close": close,
        "ema": {str(period): _value(last, f"ema_{period}") for period in EMA_PERIODS},
        "ema_trend": classify_ema_trend(
            close, float(last["ema_20"]), float(last["ema_50"]), float(last["ema_200"])
        ),
        "rsi_14": _value(last, f"rsi_{RSI_PERIOD}"),
        "macd": {
            "macd": _value(last, "macd"),
            "signal": _value(last, "macd_signal"),
            "histogram": _value(last, "macd_hist"),
        },
        "atr_14": _value(last, f"atr_{ATR_PERIOD}"),
        "vwap": vwap,
        "above_vwap": None if vwap is None else close > vwap,
        "volume": float(last["volume"]),
        "volume_avg_20": volume_avg,
        "relative_volume": (
            round(float(last["volume"]) / volume_avg, 2) if volume_avg else None
        ),
    }


def _value(row: pd.Series, column: str) -> float | None:
    """Kolon yoksa veya değer NaN ise None, değilse 2 haneye yuvarlanmış sayı."""
    if column not in row or math.isnan(row[column]):
        return None
    return round(float(row[column]), 2)
