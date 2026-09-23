"""yfinance ile ücretsiz (10-15 dk gecikmeli) futures verisi.

Sınırlar:
- 5m ve 15m verisi sadece son 60 gün için var, 1h yaklaşık 2 yıl.
- "NQ=F" gibi semboller en yakın vadeli kontratı gösterir; vade geçişlerinde
  fiyatta sıçrama olabilir.
"""

import pandas as pd
import yfinance as yf

from futures_analyzer.data.providers.base import CANDLE_COLUMNS, DataProvider
from futures_analyzer.instruments import Instrument

# Zaman dilimi -> (yfinance interval, geriye dönük ne kadar veri istenecek)
YAHOO_SETTINGS = {
    "1d": ("1d", "5y"),
    "1h": ("1h", "730d"),
    "15m": ("15m", "60d"),
    "5m": ("5m", "60d"),
}


class YahooProvider(DataProvider):
    def fetch_candles(self, instrument: Instrument, timeframe: str) -> pd.DataFrame:
        if timeframe not in YAHOO_SETTINGS:
            supported = ", ".join(YAHOO_SETTINGS)
            raise ValueError(f"yfinance bu zaman dilimini desteklemiyor: {timeframe}. Desteklenenler: {supported}")

        interval, period = YAHOO_SETTINGS[timeframe]
        raw = yf.Ticker(instrument.yahoo_ticker).history(interval=interval, period=period)
        if raw.empty:
            raise RuntimeError(f"yfinance {instrument.yahoo_ticker} için veri döndürmedi ({timeframe})")
        return to_standard_format(raw, instrument.tick_size)


def to_standard_format(raw: pd.DataFrame, tick_size: float) -> pd.DataFrame:
    """yfinance çıktısını (Open, High, ... kolonları) standart biçime çevirir."""
    df = raw.rename(columns=str.lower)[CANDLE_COLUMNS].copy()
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
    df.index.name = "ts"

    # yfinance fiyatları düşük hassasiyetle verir (4371.7998046875 gibi).
    # Gerçek fiyatlar hep tick'in katı olduğu için en yakın tick'e yuvarlıyoruz.
    for col in ["open", "high", "low", "close"]:
        df[col] = ((df[col] / tick_size).round() * tick_size).round(6)
    return df
