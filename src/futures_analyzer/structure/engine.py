"""Market structure motoru: swing'leri ve kırılımları bir özet sözlüğüne çevirir.

Çıktıdaki iki farklı "yön" bilgisi:
- trend_by_breaks: son BOS/CHoCH'un yönü
- swing_pattern / swing_bias: son swing high ve swing low'un etiketleri (örn. HH_HL -> bullish)
İkisi farklı olabilir; örneğin CHoCH sonrası henüz yeni swing oluşmamışsa.
"""

import pandas as pd

from futures_analyzer.structure.breaks import BEARISH, BULLISH, detect_breaks, event_type_for
from futures_analyzer.structure.swings import HIGH, LOW, find_swings

# Swing tespitinde her iki yana bakılan mum sayısı. İleride backtest ile ayarlanabilir.
SWING_LENGTH = 3
RECENT_SWINGS = 6
RECENT_EVENTS = 3


def structure_snapshot(df: pd.DataFrame, timeframe: str, length: int = SWING_LENGTH) -> dict:
    """df: sadece KAPANMIŞ mumlar olmalı (kırılımlar kapanışa göre hesaplanır)."""
    swings = find_swings(df, length)
    state = detect_breaks(df, swings)

    last_high = _last_of_kind(swings, HIGH)
    last_low = _last_of_kind(swings, LOW)
    high_label = last_high["label"] if last_high else None
    low_label = last_low["label"] if last_low else None

    return {
        "timeframe": timeframe,
        "swing_length": length,
        "analyzed_until": df.index[-1].isoformat() if len(df) else None,
        "trend_by_breaks": state.trend,
        "swing_pattern": f"{high_label}_{low_label}" if high_label and low_label else None,
        "swing_bias": swing_bias(high_label, low_label),
        # Etiketler yeni swing oluşana kadar geriden gelir; fiyatın son swing'lere göre yeri bunu tamamlar.
        "price_position": price_position(float(df["close"].iloc[-1]), last_high, last_low) if len(df) else None,
        "last_swing_high": _swing_dict(last_high),
        "last_swing_low": _swing_dict(last_low),
        # Fiyat bu seviyelerde KAPANIRSA oluşacak kırılım ve türü
        "bullish_break_level": _next_break(state.active_high, state.trend, BULLISH),
        "bearish_break_level": _next_break(state.active_low, state.trend, BEARISH),
        "recent_swings": [_swing_dict(s) for s in swings.tail(RECENT_SWINGS).to_dict("records")],
        "recent_events": [_event_dict(e) for e in state.events[-RECENT_EVENTS:]],
    }


def swing_bias(high_label: str | None, low_label: str | None) -> str:
    if high_label is None or low_label is None:
        return "unknown"
    if high_label == "HH" and low_label == "HL":
        return BULLISH
    if high_label == "LH" and low_label == "LL":
        return BEARISH
    return "range"


def price_position(close: float, last_high: dict | None, last_low: dict | None) -> str | None:
    """Son kapanış, son swing high'ın üstünde mi, son swing low'un altında mı, arasında mı?"""
    if last_high is None or last_low is None:
        return None
    if close > last_high["price"]:
        return "above_last_swing_high"
    if close < last_low["price"]:
        return "below_last_swing_low"
    return "between_last_swings"


def _last_of_kind(swings: pd.DataFrame, kind: str) -> dict | None:
    of_kind = swings[swings["kind"] == kind]
    return None if of_kind.empty else of_kind.iloc[-1].to_dict()


def _swing_dict(swing: dict | None) -> dict | None:
    if swing is None:
        return None
    return {
        "kind": swing["kind"],
        "price": swing["price"],
        "label": swing["label"],
        "ts": swing["ts"].isoformat(),
    }


def _next_break(swing: dict | None, trend: str | None, direction: str) -> dict | None:
    if swing is None:
        return None
    return {"level": swing["price"], "event": event_type_for(trend, direction), "swing_ts": swing["ts"].isoformat()}


def _event_dict(event: dict) -> dict:
    return {
        "type": event["type"],
        "direction": event["direction"],
        "level": event["level"],
        "break_close": event["break_close"],
        "break_ts": event["break_ts"].isoformat(),
    }
