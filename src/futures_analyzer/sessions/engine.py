"""Seans analizi: Asya, Londra ve New York seanslarının high/low değerleri.

5 dakikalık mumlarla çalışır. "Bugün" = içinde bulunulan CME işlem günü (akşam 18:00'de başlar).

Çıktı:
- current_session: şu an hangi seans (piyasa kapalıysa "closed")
- asia / london / new_york: bugünkü seansların high/low değerleri (henüz başlamadıysa None)
- ny_open: New York açılış fiyatı (09:30, altın için 08:20)
- previous_new_york: önceki işlem gününün New York seansı high/low
- taken: Asya/Londra high/low seviyeleri sonraki seanslarda aşıldı mı (likidite alındı mı)
"""

import pandas as pd

from futures_analyzer.instruments import Instrument
from futures_analyzer.market_time import (
    ASIA,
    LONDON,
    NEW_YORK,
    NEW_YORK_SESSION,
    SESSION_HOURS,
    is_market_open,
    session_names,
    trading_date,
)


def sessions_snapshot(five_min: pd.DataFrame, instrument: Instrument, now: pd.Timestamp | None = None) -> dict | None:
    if five_min is None or five_min.empty:
        return None
    now = now or pd.Timestamp.now(tz="UTC")

    days = trading_date(five_min.index)
    names = session_names(five_min.index)
    today = days[-1]
    today_bars = five_min[days == today]
    today_names = names[days == today]

    ranges = {
        name: _range(today_bars[today_names == name], name)
        for name in (ASIA, LONDON, NEW_YORK_SESSION)
    }

    return {
        "trading_date": today.date().isoformat(),
        "current_session": session_names(pd.DatetimeIndex([now]))[0] if is_market_open(now) else "closed",
        **ranges,
        "ny_open": _ny_open(today_bars, instrument.ny_open),
        "previous_new_york": _previous_new_york(five_min, days, names, today),
        "taken": _taken(today_bars, today_names, ranges),
    }


def _range(bars: pd.DataFrame, name: str) -> dict | None:
    if bars.empty:
        return None
    start, end = SESSION_HOURS[name]
    return {
        "high": float(bars["high"].max()),
        "low": float(bars["low"].min()),
        "hours_ny": f"{start}-{end}",
    }


def _ny_open(today_bars: pd.DataFrame, open_time: str) -> dict:
    local_times = today_bars.index.tz_convert(NEW_YORK).strftime("%H:%M")
    at_open = today_bars[local_times == open_time]
    price = float(at_open["open"].iloc[0]) if len(at_open) else None
    return {"time_ny": open_time, "price": price}


def _previous_new_york(five_min, days, names, today) -> dict | None:
    earlier = days < today
    if not earlier.any():
        return None
    previous_day = days[earlier].max()
    bars = five_min[(days == previous_day) & (names == NEW_YORK_SESSION)]
    if bars.empty:
        return None
    return {
        "trading_date": previous_day.date().isoformat(),
        "high": float(bars["high"].max()),
        "low": float(bars["low"].min()),
    }


def _taken(today_bars: pd.DataFrame, today_names: pd.Index, ranges: dict) -> dict:
    """Bir seansın high'ı/low'u, SONRAKİ seanslarda aşıldı mı?

    Örn. asia_high_taken = Londra veya New York'ta Asya high'ının üstüne çıkıldı.
    Sonraki seans henüz başlamadıysa False.
    """
    result = {}
    order = [ASIA, LONDON, NEW_YORK_SESSION]
    for i, name in enumerate(order[:-1]):
        later = today_bars[today_names.isin(order[i + 1:])]
        session_range = ranges[name]
        if session_range is None or later.empty:
            result[f"{name}_high_taken"] = False
            result[f"{name}_low_taken"] = False
            continue
        result[f"{name}_high_taken"] = bool(later["high"].max() > session_range["high"])
        result[f"{name}_low_taken"] = bool(later["low"].min() < session_range["low"])
    return result


def session_levels(snapshot: dict | None) -> list[dict]:
    """Seans seviyelerini destek/direnç motorunun anladığı biçime çevirir."""
    if snapshot is None:
        return []
    levels = []
    for name in (ASIA, LONDON):
        if snapshot[name] is not None:
            levels.append({"price": snapshot[name]["high"], "source": f"{name.upper()}_HIGH"})
            levels.append({"price": snapshot[name]["low"], "source": f"{name.upper()}_LOW"})
    if snapshot["ny_open"]["price"] is not None:
        levels.append({"price": snapshot["ny_open"]["price"], "source": "NY_OPEN"})
    if snapshot["previous_new_york"] is not None:
        levels.append({"price": snapshot["previous_new_york"]["high"], "source": "PREV_NY_HIGH"})
        levels.append({"price": snapshot["previous_new_york"]["low"], "source": "PREV_NY_LOW"})
    return levels
