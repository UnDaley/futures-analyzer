"""EMA'lara bakarak basit trend sınıflandırması.

Bu sadece EMA dizilişine dayalı trenddir. Tepe/dip yapısına dayalı trend
(Higher High, Lower Low vb.) Faz 3'teki market structure motorunda gelecek.
"""

import math

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"
UNKNOWN = "unknown"  # yeterli veri yok


def classify_ema_trend(close: float, ema20: float, ema50: float, ema200: float) -> str:
    """
    bullish: fiyat EMA 50'nin üstünde ve EMA'lar 20 > 50 > 200 sıralı
    bearish: fiyat EMA 50'nin altında ve EMA'lar 20 < 50 < 200 sıralı
    neutral: ikisi de değil (karışık / geçiş dönemi)
    """
    if any(math.isnan(value) for value in (close, ema20, ema50, ema200)):
        return UNKNOWN
    if close > ema50 and ema20 > ema50 > ema200:
        return BULLISH
    if close < ema50 and ema20 < ema50 < ema200:
        return BEARISH
    return NEUTRAL
