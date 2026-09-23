"""Break of Structure (BOS) ve Change of Character (CHoCH) tespiti.

Mumları baştan sona tek tek dolaşırız:
1. O mumda kesinleşen swing'leri "aktif seviye" yaparız (en son swing high ve en son swing low).
2. Kapanış aktif swing high'ın ÜSTÜNDEYSE yukarı kırılım, aktif swing low'un ALTINDAYSA aşağı kırılım.
3. Kırılım mevcut trend yönündeyse BOS, trendin tersineyse CHoCH olur.
   Henüz trend yoksa (ilk kırılım) BOS sayılır.
4. Kırılan seviye bir daha kırılmaz; yeni bir swing oluşmasını bekleriz.

Basitleştirme: CHoCH için "trende ters yöndeki son swing'in kırılması" kuralını kullanıyoruz.
Sadece kapanışlar sayılır, iğneler kırılım sayılmaz.
"""

from dataclasses import dataclass, field

import pandas as pd

from futures_analyzer.structure.swings import HIGH

BULLISH = "bullish"
BEARISH = "bearish"


@dataclass
class StructureState:
    trend: str | None = None          # son kırılımın yönü
    events: list[dict] = field(default_factory=list)
    active_high: dict | None = None   # henüz kırılmamış son swing high
    active_low: dict | None = None    # henüz kırılmamış son swing low


def detect_breaks(df: pd.DataFrame, swings: pd.DataFrame) -> StructureState:
    confirmed_at: dict[int, list[dict]] = {}
    for swing in swings.to_dict("records"):
        confirmed_at.setdefault(swing["confirmed_index"], []).append(swing)

    state = StructureState()
    closes = df["close"].to_numpy()

    for t, close in enumerate(closes):
        for swing in confirmed_at.get(t, []):
            if swing["kind"] == HIGH:
                state.active_high = swing
            else:
                state.active_low = swing

        if state.active_high is not None and close > state.active_high["price"]:
            _record_break(state, BULLISH, state.active_high, df.index[t], float(close))
            state.active_high = None

        if state.active_low is not None and close < state.active_low["price"]:
            _record_break(state, BEARISH, state.active_low, df.index[t], float(close))
            state.active_low = None

    return state


def event_type_for(trend: str | None, direction: str) -> str:
    """Bu yöndeki bir kırılım şu anki trende göre BOS mu CHoCH mu olur?"""
    if trend is not None and trend != direction:
        return "CHoCH"
    return "BOS"


def _record_break(state: StructureState, direction: str, swing: dict, ts: pd.Timestamp, close: float) -> None:
    state.events.append({
        "type": event_type_for(state.trend, direction),
        "direction": direction,
        "level": swing["price"],
        "swing_ts": swing["ts"],
        "break_ts": ts,
        "break_close": close,
    })
    state.trend = direction
