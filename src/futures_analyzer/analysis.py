"""Veritabanındaki mumlardan kontratın analiz özetini (snapshot) üretir.

Şimdilik sadece teknik göstergeler var. Sonraki fazlarda market structure,
seviyeler, seanslar vb. buraya eklenecek ve Claude'a giden JSON bu olacak.
"""

from sqlalchemy import Engine

from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.storage import load_candles
from futures_analyzer.indicators.engine import add_indicators, latest_snapshot


def technical_snapshot(db: Engine, symbol: str) -> dict:
    """Her zaman dilimi için son gösterge değerleri. Verisi olmayan zaman dilimi None olur."""
    timeframes = {}
    for timeframe in TIMEFRAMES:
        candles = load_candles(db, symbol, timeframe)
        if candles.empty:
            timeframes[timeframe] = None
            continue
        timeframes[timeframe] = latest_snapshot(add_indicators(candles, timeframe), timeframe)

    return {
        "instrument": symbol,
        "data_source": "yfinance (10-15 dk gecikmeli)",
        "timeframes": timeframes,
    }
