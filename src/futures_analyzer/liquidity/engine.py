"""Likidite / price action motoru.

1H (setup) ve 15M (onay) zaman dilimlerinde likidite havuzları, sweep'ler, FVG'ler,
displacement ve order block'ları; 4H üzerinden premium / discount bölgesini hesaplar.
Sadece kapanmış mumlar ve son ANALYSIS_BARS mum kullanılır.
"""

import pandas as pd

from futures_analyzer.indicators.calculations import atr
from futures_analyzer.liquidity.displacement import find_displacements, find_order_blocks
from futures_analyzer.liquidity.fvg import find_fvgs, nearest_fvgs
from futures_analyzer.liquidity.pools import find_sweeps, liquidity_pools
from futures_analyzer.market_time import drop_incomplete_last_bar
from futures_analyzer.structure.engine import SWING_LENGTH
from futures_analyzer.structure.swings import find_swings

LIQUIDITY_TIMEFRAMES = ["1h", "15m"]
ANALYSIS_BARS = 500
EQUAL_LEVEL_ATR = 0.1        # equal high/low toleransı
FVG_MIN_ATR = 0.1            # bundan küçük boşluklar gürültü sayılır
RECENT_BARS = 20             # sweep ve displacement için "yakın geçmiş"
DEALING_RANGE_BARS = 30      # premium/discount için 4H mum sayısı (~5 işlem günü)


def liquidity_snapshot(candles: dict[str, pd.DataFrame], price: float, now: pd.Timestamp | None = None) -> dict:
    timeframes = {}
    for timeframe in LIQUIDITY_TIMEFRAMES:
        df = candles.get(timeframe)
        if df is None or df.empty:
            timeframes[timeframe] = None
            continue
        closed = drop_incomplete_last_bar(df, timeframe, now).tail(ANALYSIS_BARS)
        timeframes[timeframe] = _timeframe_liquidity(closed, price)

    return {
        "timeframes": timeframes,
        "premium_discount": premium_discount(candles.get("4h"), price, now),
    }


def _timeframe_liquidity(df: pd.DataFrame, price: float) -> dict | None:
    atr_series = atr(df, 14)
    if atr_series.dropna().empty:
        return None
    current_atr = float(atr_series.iloc[-1])

    swings = find_swings(df, SWING_LENGTH)
    displacements = find_displacements(df, atr_series)
    recent_start = len(df) - RECENT_BARS

    return {
        **liquidity_pools(df, swings, tolerance=current_atr * EQUAL_LEVEL_ATR),
        "recent_sweeps": find_sweeps(df, swings, lookback=RECENT_BARS),
        "fvg": nearest_fvgs(find_fvgs(df, min_size=current_atr * FVG_MIN_ATR), price),
        "recent_displacements": [
            {k: v for k, v in move.items() if k != "bar_index"}
            for move in displacements if move["bar_index"] >= recent_start
        ],
        "order_blocks": find_order_blocks(df, displacements)[-3:],
    }


def premium_discount(four_hour: pd.DataFrame | None, price: float, now: pd.Timestamp | None = None) -> dict | None:
    """Son DEALING_RANGE_BARS adet 4H mumun aralığında fiyatın yeri.

    %55 üstü premium (pahalı bölge), %45 altı discount (ucuz bölge), arası equilibrium.
    """
    if four_hour is None or four_hour.empty:
        return None
    recent = drop_incomplete_last_bar(four_hour, "4h", now).tail(DEALING_RANGE_BARS)
    high, low = float(recent["high"].max()), float(recent["low"].min())
    if high == low:
        return None

    position = (price - low) / (high - low) * 100
    if position > 55:
        zone = "premium"
    elif position < 45:
        zone = "discount"
    else:
        zone = "equilibrium"
    return {
        "range_high": high,
        "range_low": low,
        "equilibrium": round((high + low) / 2, 2),
        "position_pct": round(position, 1),
        "zone": zone,
    }
