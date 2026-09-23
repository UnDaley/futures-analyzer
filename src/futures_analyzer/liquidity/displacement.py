"""Displacement ve order block.

- Displacement: gövdesi bir önceki ATR'nin `multiplier` katından büyük ve mumun büyük kısmı
  gövde olan (iğnesi kısa) güçlü mum. Kurumsal alımın/satışın izi kabul edilir.
- Order block: displacement'tan hemen önceki son TERS renkli mum.
  Bullish displacement -> ondan önceki son kırmızı (close < open) mum = bullish order block.
  Durum:
    fresh   : fiyat o mumun aralığına geri dönmedi
    tested  : fiyat aralığa girdi ama ötesinde kapanmadı
    invalid : fiyat aralığın ötesinde kapandı (artık raporlanmaz)
"""

import pandas as pd

BULLISH = "bullish"
BEARISH = "bearish"


def find_displacements(df: pd.DataFrame, atr: pd.Series, multiplier: float = 1.5, min_body_ratio: float = 0.6) -> list[dict]:
    body = (df["close"] - df["open"]).abs()
    bar_range = df["high"] - df["low"]
    prior_atr = atr.shift(1)
    strong = (body >= multiplier * prior_atr) & (body >= min_body_ratio * bar_range)

    result = []
    for position in [i for i, flag in enumerate(strong.to_numpy()) if flag]:
        row = df.iloc[position]
        result.append({
            "direction": BULLISH if row["close"] > row["open"] else BEARISH,
            "bar_index": position,
            "ts": df.index[position].isoformat(),
            "body": round(float(body.iloc[position]), 2),
            "atr_multiple": round(float(body.iloc[position] / prior_atr.iloc[position]), 2),
        })
    return result


def find_order_blocks(df: pd.DataFrame, displacements: list[dict], lookback: int = 5) -> list[dict]:
    """Geçerli (invalid olmayan) order block'lar, eskiden yeniye."""
    opens, closes = df["open"].to_numpy(), df["close"].to_numpy()
    highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
    blocks = []
    seen = set()

    for move in displacements:
        i = move["bar_index"]
        for j in range(i - 1, max(i - 1 - lookback, -1), -1):
            is_opposite = closes[j] < opens[j] if move["direction"] == BULLISH else closes[j] > opens[j]
            if not is_opposite:
                continue
            if j in seen:
                break
            seen.add(j)
            status = _block_status(move["direction"], highs[j], lows[j], i, highs, lows, closes)
            if status != "invalid":
                blocks.append({
                    "direction": move["direction"],
                    "low": float(lows[j]),
                    "high": float(highs[j]),
                    "status": status,
                    "ts": df.index[j].isoformat(),
                })
            break
    return blocks


def _block_status(direction, block_high, block_low, displacement_index, highs, lows, closes) -> str:
    after = slice(displacement_index + 1, None)
    if direction == BULLISH:
        if (closes[after] < block_low).any():
            return "invalid"
        return "tested" if (lows[after] <= block_high).any() else "fresh"
    if (closes[after] > block_high).any():
        return "invalid"
    return "tested" if (highs[after] >= block_low).any() else "fresh"
