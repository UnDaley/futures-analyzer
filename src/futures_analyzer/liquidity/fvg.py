"""Fair Value Gap (FVG) / imbalance.

3 mumlu yapı: ortadaki mum o kadar hızlı hareket etmiştir ki 1. ve 3. mumun iğneleri örtüşmez.
- Bullish FVG: 3. mumun low'u > 1. mumun high'ı. Boşluk: [1. high, 3. low]
- Bearish FVG: 3. mumun high'ı < 1. mumun low'u. Boşluk: [3. high, 1. low]

Durum:
- open: fiyat boşluğa hiç girmedi
- partial: fiyat boşluğa girdi ama tamamen doldurmadı
- filled: boşluk tamamen doldu (artık raporlanmaz)
"""

import pandas as pd

BULLISH = "bullish"
BEARISH = "bearish"


def find_fvgs(df: pd.DataFrame, min_size: float) -> list[dict]:
    """Doldurulmamış (open veya partial) FVG'ler, eskiden yeniye."""
    highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
    gaps = []

    for i in range(2, len(df)):
        if lows[i] - highs[i - 2] >= min_size and lows[i] > highs[i - 2]:
            gaps.append(_with_status(BULLISH, bottom=highs[i - 2], top=lows[i], i=i, df=df, highs=highs, lows=lows))
        elif lows[i - 2] - highs[i] >= min_size and highs[i] < lows[i - 2]:
            gaps.append(_with_status(BEARISH, bottom=highs[i], top=lows[i - 2], i=i, df=df, highs=highs, lows=lows))

    return [gap for gap in gaps if gap["status"] != "filled"]


def _with_status(direction, bottom, top, i, df, highs, lows) -> dict:
    later_highs, later_lows = highs[i + 1:], lows[i + 1:]
    if direction == BULLISH:
        # Fiyat aşağı inip boşluğu doldurur
        filled = (later_lows <= bottom).any()
        entered = (later_lows < top).any()
    else:
        filled = (later_highs >= top).any()
        entered = (later_highs > bottom).any()

    status = "filled" if filled else "partial" if entered else "open"
    return {
        "direction": direction,
        "bottom": float(bottom),
        "top": float(top),
        "status": status,
        "ts": df.index[i - 1].isoformat(),  # boşluğu yaratan ortadaki mum
    }


def nearest_fvgs(fvgs: list[dict], price: float, limit: int = 3) -> dict:
    """Fiyatın üstündeki ve altındaki en yakın açık FVG'ler."""
    above = sorted((g for g in fvgs if g["bottom"] > price), key=lambda g: g["bottom"])
    below = sorted((g for g in fvgs if g["top"] < price), key=lambda g: -g["top"])
    inside = [g for g in fvgs if g["bottom"] <= price <= g["top"]]
    return {"above": above[:limit], "below": below[:limit], "at_price": inside}

