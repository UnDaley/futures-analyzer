"""Gösterge hesaplarının testleri. Beklenen değerler elle hesaplandı (yorumlarda)."""

import math

import pandas as pd
import pytest

from futures_analyzer.indicators.calculations import atr, ema, macd, rsi, sma, true_range, wilder_average


def series(values):
    return pd.Series(values, dtype=float)


def rounded(s, digits=4):
    return [None if math.isnan(v) else round(v, digits) for v in s]


def test_ema_by_hand():
    # period 3 -> alpha = 2 / (3 + 1) = 0.5
    # 1, 1.5, 2.25, 3.125, 4.0625 ; ilk 2 değer yetersiz veri nedeniyle NaN
    assert rounded(ema(series([1, 2, 3, 4, 5]), 3)) == [None, None, 2.25, 3.125, 4.0625]


def test_ema_of_constant_is_constant():
    assert ema(series([7] * 30), 20).iloc[-1] == pytest.approx(7)


def test_sma():
    assert rounded(sma(series([1, 2, 3, 4]), 2)) == [None, 1.5, 2.5, 3.5]


def test_wilder_average_by_hand():
    # ilk değer: (1 + 2 + 3) / 3 = 2
    # sonra: (2 * 2 + 4) / 3 = 2.6667 ; (2.6667 * 2 + 5) / 3 = 3.4444
    assert rounded(wilder_average(series([1, 2, 3, 4, 5]), 3)) == [None, None, 2.0, 2.6667, 3.4444]


def test_rsi_by_hand():
    # Kapanışlar: 10, 11, 10, 11, 12  (period 2)
    # Değişim:    -,  +1, -1, +1, +1
    # 3. mum: ort. kazanç (1+0)/2 = 0.5, ort. kayıp (0+1)/2 = 0.5 -> RSI 50
    # 4. mum: kazanç (0.5+1)/2 = 0.75, kayıp (0.5+0)/2 = 0.25 -> RS 3 -> RSI 75
    # 5. mum: kazanç (0.75+1)/2 = 0.875, kayıp 0.125 -> RS 7 -> RSI 87.5
    assert rounded(rsi(series([10, 11, 10, 11, 12]), 2)) == [None, None, 50.0, 75.0, 87.5]


def test_rsi_extremes():
    assert rsi(series(range(1, 40)), 14).iloc[-1] == 100      # hep yükseliş
    assert rsi(series(range(40, 1, -1)), 14).iloc[-1] == 0    # hep düşüş
    assert rsi(series([5] * 40), 14).iloc[-1] == 50           # hiç hareket yok


def test_macd_relationships():
    close = series([100 + (i % 7) * 3 + i * 0.5 for i in range(100)])

    result = macd(close)

    expected_macd = ema(close, 12) - ema(close, 26)
    assert result["macd"].iloc[-1] == pytest.approx(expected_macd.iloc[-1])
    assert result["macd_hist"].iloc[-1] == pytest.approx(result["macd"].iloc[-1] - result["macd_signal"].iloc[-1])


def test_true_range_includes_gaps():
    df = pd.DataFrame({
        "high": [10.0, 12.0],
        "low": [9.0, 11.5],
        "close": [9.5, 12.0],
    })
    # 2. mum: high-low = 0.5, ama önceki kapanış 9.5'ten 12'ye boşluk var -> 12 - 9.5 = 2.5
    assert true_range(df).tolist() == [1.0, 2.5]


def test_atr_of_constant_range():
    df = pd.DataFrame({"high": [11.0] * 20, "low": [9.0] * 20, "close": [10.0] * 20})
    assert atr(df, 14).iloc[-1] == pytest.approx(2.0)
