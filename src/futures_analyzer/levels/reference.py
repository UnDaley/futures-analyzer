"""Referans seviyeler: önceki gün, önceki hafta ve içinde bulunulan seans.

Hepsi 1H mumlardan hesaplanır. Günler CME seansına göre bölünür (New York 18:00 - 17:00),
haftalar pazar akşamı 18:00'de başlayan seansla açılır.
"""

import math

import pandas as pd

from futures_analyzer.market_time import trading_date


def session_ranges(hourly: pd.DataFrame) -> pd.DataFrame:
    """Her işlem günü için high ve low. Index: işlem günü (eskiden yeniye)."""
    days = trading_date(hourly.index)
    return hourly.groupby(days).agg(high=("high", "max"), low=("low", "min"))


def week_ranges(hourly: pd.DataFrame) -> pd.DataFrame:
    """Her işlem haftası için high ve low. Index: haftanın pazartesi günü."""
    days = trading_date(hourly.index)
    week_start = days - pd.to_timedelta(days.weekday, unit="D")
    return hourly.groupby(week_start).agg(high=("high", "max"), low=("low", "min"))


def reference_levels(hourly: pd.DataFrame) -> dict:
    """Önceki gün/hafta ve şu anki seansın high/low değerleri.

    Son grup içinde bulunduğumuz (henüz bitmemiş) gün veya haftadır; "önceki" bir öncekidir.
    Yeterli veri yoksa değer None olur.
    """
    days = session_ranges(hourly)
    weeks = week_ranges(hourly)

    return {
        "session_date": days.index[-1].date().isoformat() if len(days) else None,
        "session_high": _pick(days, -1, "high"),
        "session_low": _pick(days, -1, "low"),
        "pdh": _pick(days, -2, "high"),
        "pdl": _pick(days, -2, "low"),
        "pwh": _pick(weeks, -2, "high"),
        "pwl": _pick(weeks, -2, "low"),
    }


def round_number_levels(price: float, step: float, count: int = 2) -> list[float]:
    """Fiyatın altındaki ve üstündeki en yakın `count` yuvarlak seviye.

    Örn. fiyat 30.935, adım 100 -> [30.800, 30.900, 31.000, 31.100]
    """
    below = math.floor(price / step) * step
    levels = [below - i * step for i in range(count)] + [below + (i + 1) * step for i in range(count)]
    return sorted(float(level) for level in levels)


def _pick(table: pd.DataFrame, position: int, column: str) -> float | None:
    if len(table) < abs(position):
        return None
    return float(table[column].iloc[position])
