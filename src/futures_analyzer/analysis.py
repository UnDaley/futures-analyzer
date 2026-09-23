"""Veritabanındaki mumlardan kontratın analiz özetini (snapshot) üretir.

- levels: destek / direnç zone'ları ve referans seviyeler (Faz 4)
- sessions: Asya / Londra / New York high-low, NY açılışı (Faz 5)
- timeframes: her zaman dilimi için
    - technical: gösterge değerleri (Faz 2)
    - structure: swing'ler, HH/HL, BOS/CHoCH (Faz 3)
Claude'a giden JSON bu özettir.
"""

from sqlalchemy import Engine

from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.storage import load_candles
from futures_analyzer.indicators.engine import add_indicators, latest_snapshot
from futures_analyzer.instruments import get_instrument
from futures_analyzer.levels.engine import levels_snapshot
from futures_analyzer.market_time import drop_incomplete_last_bar
from futures_analyzer.sessions.engine import session_levels, sessions_snapshot
from futures_analyzer.structure.engine import structure_snapshot


def market_snapshot(db: Engine, symbol: str) -> dict:
    """Kontratın analiz özeti. Verisi olmayan zaman dilimi None olur."""
    instrument = get_instrument(symbol)
    candles = {timeframe: load_candles(db, instrument.symbol, timeframe) for timeframe in TIMEFRAMES}

    timeframes = {}
    for timeframe, df in candles.items():
        if df.empty:
            timeframes[timeframe] = None
            continue

        # Göstergeler son (açık olabilen) mumu da gösterir; bu durum last_bar_complete ile belirtilir.
        # Yapı ise kapanışlara dayandığı için sadece kapanmış mumlarla hesaplanır.
        closed = drop_incomplete_last_bar(df, timeframe)
        timeframes[timeframe] = {
            "technical": latest_snapshot(add_indicators(df, timeframe), timeframe),
            "structure": structure_snapshot(closed, timeframe) if len(closed) else None,
        }

    sessions = sessions_snapshot(candles["5m"], instrument)
    return {
        "instrument": instrument.symbol,
        "data_source": "yfinance (10-15 dk gecikmeli)",
        "sessions": sessions,
        "levels": levels_snapshot(candles, instrument, extra_levels=session_levels(sessions)),
        "timeframes": timeframes,
    }
