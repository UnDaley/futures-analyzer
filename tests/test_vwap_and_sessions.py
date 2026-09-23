import math

import pandas as pd

from futures_analyzer.indicators.vwap import session_vwap
from futures_analyzer.market_time import session_start


def ny(*times):
    return pd.DatetimeIndex(times).tz_localize("America/New_York").tz_convert("UTC")


def ny_str(index):
    return list(index.tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M"))


def test_session_starts_at_18_new_york():
    index = ny("2026-06-15 17:59", "2026-06-15 18:00", "2026-06-16 09:30")

    assert ny_str(session_start(index)) == ["2026-06-14 18:00", "2026-06-15 18:00", "2026-06-15 18:00"]


def test_session_start_across_dst_change():
    # DST 8 Mart 2026 pazar günü başladı. Pazar 18:00 açılışı yaz saatinde (EDT).
    index = ny("2026-03-06 10:00", "2026-03-09 10:00")

    starts = session_start(index)

    assert ny_str(starts) == ["2026-03-05 18:00", "2026-03-08 18:00"]
    assert [ts.hour for ts in starts] == [23, 22]  # UTC: EST'de 23:00, EDT'de 22:00


def candles(index, typical_prices, volumes):
    # high = low = close = tipik fiyat, hesabı kolay takip etmek için
    return pd.DataFrame(
        {"high": typical_prices, "low": typical_prices, "close": typical_prices, "volume": volumes},
        index=index,
    )


def test_vwap_accumulates_and_resets_at_session_open():
    index = ny("2026-06-15 15:00", "2026-06-15 16:00", "2026-06-15 18:00")
    df = candles(index, [100.0, 110.0, 200.0], [1.0, 3.0, 2.0])

    # 1. mum: 100
    # 2. mum: (100*1 + 110*3) / 4 = 107.5
    # 3. mum: yeni seans -> sadece kendisi = 200
    assert session_vwap(df).tolist() == [100.0, 107.5, 200.0]


def test_vwap_is_undefined_without_volume():
    index = ny("2026-06-15 18:00", "2026-06-15 19:00")
    df = candles(index, [100.0, 110.0], [0.0, 2.0])

    result = session_vwap(df)

    assert math.isnan(result.iloc[0])
    assert result.iloc[1] == 110.0
