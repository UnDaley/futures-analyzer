"""Kontratın analiz özetini (snapshot) üretir. Claude'a giden JSON budur.

Bölümler:
- timeframes: her zaman dilimi için technical (Faz 2) ve structure (Faz 3)
- levels: destek / direnç zone'ları ve referans seviyeler (Faz 4)
- sessions: Asya / Londra / New York high-low, NY açılışı (Faz 5)
- liquidity: BSL/SSL, sweep, FVG, displacement, order block, premium/discount (Faz 6)
- macro: faizler, enflasyon, istihdam, büyüme (Faz 7)
- intermarket: ilişkili varlıklarla uyum, korelasyon, SMT (Faz 8)
- news: ekonomik takvim / olay riski ve resmi kaynaklardan haberler (Faz 9)
- score + scenarios: ağırlıklı analiz skoru ve bullish / bearish / neutral senaryolar (Faz 10)

İki adım:
- load_market_data: veritabanından her şeyi okur
- build_snapshot: verilen `now` anına kadar bilinen veriyle snapshot'ı hesaplar.
  Canlı analiz ve geçmişe dönük backtest (Faz 12) aynı fonksiyonu kullanır.
"""

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.storage import load_candles
from futures_analyzer.indicators.engine import add_indicators, latest_snapshot
from futures_analyzer.instruments import Instrument, get_instrument
from futures_analyzer.intermarket.engine import RELATIONSHIPS, SMT_PAIRS, intermarket_snapshot
from futures_analyzer.levels.engine import levels_snapshot
from futures_analyzer.liquidity.engine import liquidity_snapshot
from futures_analyzer.macro.engine import macro_snapshot
from futures_analyzer.macro.ingest import load_macro
from futures_analyzer.market_time import drop_incomplete_last_bar
from futures_analyzer.news.engine import news_snapshot
from futures_analyzer.scenarios.builder import build_scenarios
from futures_analyzer.scenarios.scoring import score_snapshot
from futures_analyzer.sessions.engine import session_levels, sessions_snapshot
from futures_analyzer.structure.engine import structure_snapshot

DATA_SOURCE = "yfinance (10-15 dk gecikmeli)"


@dataclass
class MarketData:
    instrument: Instrument
    candles: dict[str, pd.DataFrame]            # zaman dilimi -> kontratın mumları
    related_hourly: dict[str, pd.DataFrame]     # ilişkili sembol -> 1H mumlar
    macro: dict[str, pd.Series]                 # makro seriler


def load_market_data(db: Engine, symbol: str) -> MarketData:
    instrument = get_instrument(symbol)
    related = {*RELATIONSHIPS.get(instrument.symbol, {}), SMT_PAIRS.get(instrument.symbol)} - {None}
    return MarketData(
        instrument=instrument,
        candles={timeframe: load_candles(db, instrument.symbol, timeframe) for timeframe in TIMEFRAMES},
        related_hourly={other: load_candles(db, other, "1h") for other in related},
        macro=load_macro(db),
    )


def market_snapshot(db: Engine, symbol: str) -> dict:
    """Şu anki analiz özeti."""
    data = load_market_data(db, symbol)
    now = pd.Timestamp.now(tz="UTC")
    return build_snapshot(data, now, news=news_snapshot(db, data.instrument.symbol, now))


def build_snapshot(data: MarketData, now: pd.Timestamp, news: dict | None = None, max_bars: int | None = None) -> dict:
    """`now` anından ÖNCE başlamış mumlarla snapshot. max_bars: hız için her tablonun son N mumu."""
    instrument = data.instrument
    candles = {tf: _until(df, now, max_bars) for tf, df in data.candles.items()}
    macro = {name: _series_until(series, now) for name, series in data.macro.items()}
    hourly_by_symbol = {instrument.symbol: candles["1h"]}
    hourly_by_symbol.update({other: _until(df, now, max_bars) for other, df in data.related_hourly.items()})

    timeframes = {}
    for timeframe, df in candles.items():
        if df.empty:
            timeframes[timeframe] = None
            continue
        # Göstergeler son (açık olabilen) mumu da gösterir; bu durum last_bar_complete ile belirtilir.
        # Yapı ise kapanışlara dayandığı için sadece kapanmış mumlarla hesaplanır.
        closed = drop_incomplete_last_bar(df, timeframe, now)
        timeframes[timeframe] = {
            "technical": latest_snapshot(add_indicators(df, timeframe), timeframe, now),
            "structure": structure_snapshot(closed, timeframe) if len(closed) else None,
        }

    five_min = candles["5m"]
    # Fiyat: en ayrıntılı (en güncel) zaman diliminin son kapanışı
    latest = next((candles[tf] for tf in ("5m", "15m", "1h") if not candles[tf].empty), None)
    price = float(latest["close"].iloc[-1]) if latest is not None else None
    sessions = sessions_snapshot(five_min, instrument, now) if not five_min.empty else None
    snapshot = {
        "instrument": instrument.symbol,
        "as_of": now.isoformat(),
        "data_source": DATA_SOURCE,
        "price": price,
        "sessions": sessions,
        "levels": levels_snapshot(candles, instrument, extra_levels=session_levels(sessions), now=now),
        "liquidity": liquidity_snapshot(candles, price, now) if price is not None else None,
        "macro": macro_snapshot(macro),
        "intermarket": intermarket_snapshot(instrument.symbol, hourly_by_symbol, macro),
        "news": news,
        "timeframes": timeframes,
    }
    score = score_snapshot(snapshot, candles["1h"], now)
    snapshot["score"] = score
    snapshot["scenarios"] = build_scenarios(snapshot, score)
    return snapshot


def _until(df: pd.DataFrame, now: pd.Timestamp, max_bars: int | None) -> pd.DataFrame:
    df = df[df.index < now]
    return df.tail(max_bars) if max_bars else df


def _series_until(series: pd.Series, now: pd.Timestamp) -> pd.Series:
    """Makro seriler günlük tarihlidir; o günün değeri genelde ertesi gün yayınlanır, bu yüzden
    sadece `now` gününden ÖNCEKİ tarihler kullanılır."""
    if series.empty:
        return series
    return series[series.index < now.tz_convert("UTC").tz_localize(None).normalize()]
