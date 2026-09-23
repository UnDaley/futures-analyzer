"""1 saatlik mumlardan 4 saatlik mum üretir.

4H mumlar CME seans açılışına hizalıdır (New York saati):
18:00, 22:00, 02:00, 06:00, 10:00, 14:00.
Seans 17:00'de kapandığı için 14:00 mumu 3 saatliktir.
"""

import pandas as pd

from futures_analyzer.market_time import floor_to_session_grid


def resample_to_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    """Temizlenmiş 1H mumları 4H mumlara çevirir. Sonuç UTC zaman damgalıdır."""
    if hourly.empty:
        return hourly.copy()

    buckets = floor_to_session_grid(hourly.index, "4h")
    grouped = hourly.groupby(buckets)
    result = pd.DataFrame({
        "open": grouped["open"].first(),
        "high": grouped["high"].max(),
        "low": grouped["low"].min(),
        "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(),
    })
    result.index.name = "ts"

    # Veri bir 4H diliminin ortasından başlıyorsa ilk mum eksik kalır; onu atıyoruz.
    if hourly.index[0] != result.index[0]:
        result = result.iloc[1:]
    return result
