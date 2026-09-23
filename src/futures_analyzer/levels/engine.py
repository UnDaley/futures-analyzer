"""Destek / direnç motoru: bütün seviyeleri toplar, zone'lara birleştirir, fiyata göre ayırır."""

import math

import pandas as pd

from futures_analyzer.indicators.calculations import atr
from futures_analyzer.indicators.vwap import session_vwap
from futures_analyzer.instruments import Instrument
from futures_analyzer.levels.reference import reference_levels, round_number_levels
from futures_analyzer.levels.zones import build_zones, split_by_price
from futures_analyzer.market_time import drop_incomplete_last_bar
from futures_analyzer.structure.engine import SWING_LENGTH
from futures_analyzer.structure.swings import find_swings

# Seviyeler bu kadar yakınsa aynı zone sayılır: 1H ATR'nin çeyreği
ZONE_TOLERANCE_ATR = 0.25
# Swing seviyeleri için bakılan zaman dilimleri ve her birinden alınan son swing sayısı
SWING_TIMEFRAMES = ["4h", "1h"]
SWINGS_PER_TIMEFRAME = 10

REFERENCE_SOURCES = {
    "pdh": "PDH", "pdl": "PDL",
    "pwh": "PWH", "pwl": "PWL",
    "session_high": "SESSION_HIGH", "session_low": "SESSION_LOW",
}


def levels_snapshot(
    candles: dict[str, pd.DataFrame],
    instrument: Instrument,
    extra_levels: list[dict] | None = None,
    now: pd.Timestamp | None = None,
) -> dict | None:
    """candles: zaman dilimi -> mumlar. En az 1h ve 5m verisi gerekir.
    extra_levels: başka motorlardan gelen seviyeler (örn. seans high/low), aynı biçimde.

    Fiyat, seans high/low ve VWAP son (açık olabilen) mumu da kullanır; swing'ler sadece kapanmış mumlarla bulunur.
    """
    hourly, five_min = candles.get("1h"), candles.get("5m")
    if hourly is None or hourly.empty or five_min is None or five_min.empty:
        return None

    price = float(five_min["close"].iloc[-1])
    reference = reference_levels(hourly)
    vwap = _last_value(session_vwap(five_min))
    hourly_atr = _last_value(atr(hourly, 14))

    levels = []
    for key, source in REFERENCE_SOURCES.items():
        if reference[key] is not None:
            levels.append({"price": reference[key], "source": source})
    if vwap is not None:
        levels.append({"price": round(vwap, 2), "source": "VWAP"})
    for level in round_number_levels(price, instrument.round_step):
        levels.append({"price": level, "source": "ROUND"})
    levels.extend(_swing_levels(candles, now))
    levels.extend(extra_levels or [])

    tolerance = round(hourly_atr * ZONE_TOLERANCE_ATR, 2) if hourly_atr else 0.0
    zones = build_zones(levels, tolerance)

    return {
        "price": price,
        "reference": {**reference, "vwap": round(vwap, 2) if vwap is not None else None},
        "zone_tolerance": tolerance,
        **split_by_price(zones, price),
    }


def _swing_levels(candles: dict[str, pd.DataFrame], now: pd.Timestamp | None) -> list[dict]:
    levels = []
    for timeframe in SWING_TIMEFRAMES:
        df = candles.get(timeframe)
        if df is None or df.empty:
            continue
        closed = drop_incomplete_last_bar(df, timeframe, now)
        swings = find_swings(closed, SWING_LENGTH).tail(SWINGS_PER_TIMEFRAME)
        for kind, price in zip(swings["kind"], swings["price"]):
            levels.append({"price": price, "source": f"SWING_{kind.upper()}_{timeframe.upper()}"})
    return levels


def _last_value(series: pd.Series) -> float | None:
    """Son değer; NaN ise None. (Önceki geçerli değere geri dönmüyoruz: örn. yeni seansın VWAP'ı
    henüz tanımsızsa bir önceki seansın VWAP'ını göstermek yanlış olur.)"""
    if series.empty or math.isnan(series.iloc[-1]):
        return None
    return float(series.iloc[-1])
