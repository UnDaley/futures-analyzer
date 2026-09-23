"""Market structure testleri.

Test verisinde her mum: high = kapanış + 1, low = kapanış - 1.
Böylece swing'ler doğrudan kapanış dizisindeki tepe ve diplerden okunabilir.
Testlerde swing_length = 2 (her iki yana 2 mum).
"""

import numpy as np
import pandas as pd

from futures_analyzer.structure.breaks import detect_breaks
from futures_analyzer.structure.engine import structure_snapshot
from futures_analyzer.structure.swings import find_swings

# Yükselen trend: tepeler (index 3 ve 9) ve dipler (index 5 ve 11) giderek yükseliyor
#          index: 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
UPTREND = [1, 2, 3, 4, 3, 2, 3, 4, 5, 6, 5, 4, 5, 6, 7, 8]

# Yükselişin ardından sert düşüş: index 15'te yeni tepe, sonra son dip (index 11) kırılıyor
#                                   16 17 18 19 20 21 22
UP_THEN_DOWN = UPTREND + [7, 6, 5, 4, 3, 2, 1]


def bars(closes):
    index = pd.date_range("2026-06-15 18:00", periods=len(closes), freq="1h", tz="UTC")
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0})


def negate(closes):
    """Diziyi ters çevirir: yükselen trend düşen trende dönüşür."""
    return [-c for c in closes]


def test_find_swings_in_uptrend():
    swings = find_swings(bars(UPTREND), length=2)

    assert swings[["kind", "bar_index", "price", "label"]].values.tolist() == [
        ["high", 3, 5.0, None],   # ilk tepe: karşılaştıracak önceki tepe yok
        ["low", 5, 1.0, None],
        ["high", 9, 7.0, "HH"],
        ["low", 11, 3.0, "HL"],
    ]


def test_swing_is_confirmed_only_after_right_side_bars():
    swings = find_swings(bars(UPTREND), length=2)

    assert swings["confirmed_index"].tolist() == [5, 7, 11, 13]  # bar_index + 2


def test_last_bars_cannot_be_swings_yet():
    # Son tepe (index 15) sağında 2 mum olmadığı için henüz swing değil
    swings = find_swings(bars(UPTREND), length=2)

    assert swings["bar_index"].max() < len(UPTREND) - 2


def test_equal_highs_first_one_is_the_swing():
    swings = find_swings(bars([1, 2, 5, 5, 2, 1]), length=2)

    assert swings[swings["kind"] == "high"]["bar_index"].tolist() == [2]


def test_bos_in_uptrend():
    df = bars(UPTREND)
    state = detect_breaks(df, find_swings(df, length=2))

    # index 9'da kapanış 6, ilk tepe (5) üstünde -> BOS
    # index 15'te kapanış 8, ikinci tepe (7) üstünde -> BOS
    assert [(e["type"], e["direction"], e["level"]) for e in state.events] == [
        ("BOS", "bullish", 5.0),
        ("BOS", "bullish", 7.0),
    ]
    assert [e["break_ts"] for e in state.events] == [df.index[9], df.index[15]]
    assert state.trend == "bullish"


def test_choch_when_uptrend_breaks_down():
    df = bars(UP_THEN_DOWN)
    state = detect_breaks(df, find_swings(df, length=2))

    # index 21'de kapanış 2, son dip (3) altında; trend yükselişteyken -> CHoCH
    last = state.events[-1]
    assert (last["type"], last["direction"], last["level"]) == ("CHoCH", "bearish", 3.0)
    assert last["break_ts"] == df.index[21]
    assert state.trend == "bearish"


def test_close_must_break_not_just_the_wick():
    # index 8: kapanış 5 = tepe seviyesi (5). Eşitlik kırılım değil; kırılım index 9'da.
    df = bars(UPTREND)
    state = detect_breaks(df, find_swings(df, length=2))

    assert state.events[0]["break_ts"] == df.index[9]


def test_downtrend_is_mirror_of_uptrend():
    df = bars(negate(UPTREND))
    snapshot = structure_snapshot(df, "1h", length=2)

    assert snapshot["swing_pattern"] == "LH_LL"
    assert snapshot["swing_bias"] == "bearish"
    assert snapshot["trend_by_breaks"] == "bearish"
    assert [e["type"] for e in snapshot["recent_events"]] == ["BOS", "BOS"]


def test_snapshot_uptrend():
    snapshot = structure_snapshot(bars(UPTREND), "1h", length=2)

    assert snapshot["swing_pattern"] == "HH_HL"
    assert snapshot["swing_bias"] == "bullish"
    assert snapshot["trend_by_breaks"] == "bullish"
    assert snapshot["last_swing_high"]["price"] == 7.0
    assert snapshot["last_swing_low"]["price"] == 3.0
    assert snapshot["price_position"] == "above_last_swing_high"  # son kapanış 8 > 7
    # Yukarıdaki tepe zaten kırıldı; aşağıda 3'ün altında kapanış trend dönüşü (CHoCH) olur
    assert snapshot["bullish_break_level"] is None
    assert snapshot["bearish_break_level"]["level"] == 3.0
    assert snapshot["bearish_break_level"]["event"] == "CHoCH"


def test_snapshot_after_choch():
    snapshot = structure_snapshot(bars(UP_THEN_DOWN), "1h", length=2)

    assert snapshot["trend_by_breaks"] == "bearish"
    assert snapshot["swing_pattern"] == "HH_HL"  # yeni swing oluşmadı; yapı etiketleri hâlâ yükseliş
    assert snapshot["price_position"] == "below_last_swing_low"  # son kapanış 1 < 3; etiketlerin geride kaldığını gösterir
    # Son tepe (index 15, high 9) üstünde kapanış tekrar yükselişe dönüş (CHoCH) olur
    assert snapshot["bullish_break_level"]["level"] == 9.0
    assert snapshot["bullish_break_level"]["event"] == "CHoCH"
    assert snapshot["bearish_break_level"] is None


def test_snapshot_without_enough_data():
    snapshot = structure_snapshot(bars([1, 2, 3]), "1h", length=2)

    assert snapshot["swing_pattern"] is None
    assert snapshot["swing_bias"] == "unknown"
    assert snapshot["price_position"] is None
    assert snapshot["trend_by_breaks"] is None
    assert snapshot["recent_events"] == []


def test_no_lookahead_past_events_do_not_change_with_new_data():
    # Rastgele ama tekrarlanabilir bir fiyat yolu
    rng = np.random.default_rng(42)
    closes = (100 + rng.normal(0, 1, 400).cumsum()).round(2).tolist()
    df = bars(closes)
    full_events = detect_breaks(df, find_swings(df, length=3)).events

    for cut in [50, 150, 300]:
        partial = df.iloc[:cut]
        partial_events = detect_breaks(partial, find_swings(partial, length=3)).events
        # Kısmi veride bulunan olaylar, tam verinin ilk olaylarıyla birebir aynı olmalı
        assert partial_events == full_events[:len(partial_events)]
        # Ve tam veride, kesme noktasından önce olup kısmi veride görünmeyen olay olmamalı
        before_cut = [e for e in full_events if e["break_ts"] < df.index[cut]]
        assert len(before_cut) == len(partial_events)
