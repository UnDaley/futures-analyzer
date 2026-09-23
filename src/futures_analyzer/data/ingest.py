"""Veriyi çek -> temizle -> kaydet adımlarını birleştirir."""

from sqlalchemy import Engine

from futures_analyzer.data.cleaning import clean_candles
from futures_analyzer.data.providers.base import DataProvider
from futures_analyzer.data.resample import resample_to_4h
from futures_analyzer.data.storage import save_candles
from futures_analyzer.instruments import Instrument

# Sağlayıcıdan doğrudan çekilen zaman dilimleri (4h, 1h'den üretilir)
FETCH_TIMEFRAMES = ["1d", "1h", "15m", "5m"]


def ingest(engine: Engine, provider: DataProvider, instrument: Instrument, timeframe: str) -> dict[str, int]:
    """Bir zaman dilimini çekip kaydeder. 1h çekilince 4h de üretilip kaydedilir.

    Dönüş: {zaman dilimi: kaydedilen mum sayısı}
    """
    candles = clean_candles(provider.fetch_candles(instrument, timeframe))
    saved = {timeframe: save_candles(engine, instrument.symbol, timeframe, candles)}

    if timeframe == "1h":
        four_hour = resample_to_4h(candles)
        saved["4h"] = save_candles(engine, instrument.symbol, "4h", four_hour)
    return saved
