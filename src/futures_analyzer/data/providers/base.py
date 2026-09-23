"""Bütün veri sağlayıcıların uyması gereken ortak kurallar.

Her sağlayıcı mumları aynı biçimde döndürür:
- index: "ts" adlı, UTC saat dilimli zaman damgası (mumun açılış zamanı)
- kolonlar: open, high, low, close, volume

Böylece sistemin geri kalanı verinin nereden geldiğini bilmek zorunda kalmaz.
"""

from abc import ABC, abstractmethod

import pandas as pd

from futures_analyzer.instruments import Instrument

CANDLE_COLUMNS = ["open", "high", "low", "close", "volume"]

# Sistemin tanıdığı zaman dilimleri. 4h sağlayıcıdan çekilmez, 1h'den üretilir.
TIMEFRAMES = ["1d", "4h", "1h", "15m", "5m"]


class DataProvider(ABC):
    @abstractmethod
    def fetch_candles(self, instrument: Instrument, timeframe: str) -> pd.DataFrame:
        """Verilen kontrat ve zaman dilimi için mumları standart biçimde döndürür."""
