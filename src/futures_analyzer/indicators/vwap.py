"""Seans VWAP'ı (Volume Weighted Average Price).

Seans boyunca işlem gören hacmin ortalama fiyatı. Her CME seans açılışında
(New York saatiyle 18:00) sıfırlanır. Sadece gün içi zaman dilimlerinde anlamlıdır.
"""

import pandas as pd

from futures_analyzer.market_time import session_start


def session_vwap(df: pd.DataFrame) -> pd.Series:
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    session = session_start(df.index)

    price_x_volume = (typical_price * df["volume"]).groupby(session).cumsum()
    cumulative_volume = df["volume"].groupby(session).cumsum()

    # Seansın başında hiç hacim yoksa VWAP tanımsızdır (NaN kalır).
    return price_x_volume / cumulative_volume.where(cumulative_volume > 0)
