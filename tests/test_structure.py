"""Swing tespiti testleri (10am modelinde hedef adayları için kullanılır).

Test verisinde her mum: high = kapanış + 1, low = kapanış - 1.
Böylece swing'ler doğrudan kapanış dizisindeki tepe ve diplerden okunabilir.
Testlerde swing_length = 2 (her iki yana 2 mum).
"""

import pandas as pd

from futures_analyzer.structure.swings import find_swings

# Yükselen trend: tepeler (index 3 ve 9) ve dipler (index 5 ve 11) giderek yükseliyor
#          index: 0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15
UPTREND = [1, 2, 3, 4, 3, 2, 3, 4, 5, 6, 5, 4, 5, 6, 7, 8]


def bars(closes):
    index = pd.date_range("2026-06-15 18:00", periods=len(closes), freq="1h", tz="UTC")
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 10.0})


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
