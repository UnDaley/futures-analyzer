"""Veritabanındaki mumlardan kontratın analiz özetini (snapshot) üretir.

Her zaman dilimi için:
- technical: gösterge değerleri (Faz 2)
- structure: swing'ler, HH/HL, BOS/CHoCH (Faz 3)
Sonraki fazlarda seviyeler, seanslar vb. eklenecek ve Claude'a giden JSON bu olacak.
"""

from sqlalchemy import Engine

from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.storage import load_candles
from futures_analyzer.indicators.engine import add_indicators, latest_snapshot
from futures_analyzer.market_time import drop_incomplete_last_bar
from futures_analyzer.structure.engine import structure_snapshot


def market_snapshot(db: Engine, symbol: str) -> dict:
    """Her zaman dilimi için analiz özeti. Verisi olmayan zaman dilimi None olur."""
    timeframes = {}
    for timeframe in TIMEFRAMES:
        candles = load_candles(db, symbol, timeframe)
        if candles.empty:
            timeframes[timeframe] = None
            continue

        # Göstergeler son (açık olabilen) mumu da gösterir; bu durum last_bar_complete ile belirtilir.
        # Yapı ise kapanışlara dayandığı için sadece kapanmış mumlarla hesaplanır.
        closed = drop_incomplete_last_bar(candles, timeframe)
        timeframes[timeframe] = {
            "technical": latest_snapshot(add_indicators(candles, timeframe), timeframe),
            "structure": structure_snapshot(closed, timeframe) if len(closed) else None,
        }

    return {
        "instrument": symbol,
        "data_source": "yfinance (10-15 dk gecikmeli)",
        "timeframes": timeframes,
    }
