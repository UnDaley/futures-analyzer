"""Temel teknik göstergeler.

Her fonksiyon bir pandas Series (veya DataFrame) alır ve aynı index'li bir Series döndürür.
Yeterli veri yoksa (örn. EMA 200 için 200 mumdan az) değer NaN olur; asla tahmin edilmez.
"""

import numpy as np
import pandas as pd


def ema(close: pd.Series, period: int) -> pd.Series:
    """Üstel hareketli ortalama. Son fiyatlara daha fazla ağırlık verir."""
    return close.ewm(span=period, adjust=False, min_periods=period).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    """Basit hareketli ortalama: son `period` değerin ortalaması."""
    return series.rolling(period, min_periods=period).mean()


def wilder_average(series: pd.Series, period: int) -> pd.Series:
    """Wilder'ın ortalaması. RSI ve ATR bunu kullanır.

    TradingView'deki ta.rma ile aynı: ilk değer, ilk `period` değerin basit ortalamasıdır;
    sonrasında her yeni değer: (önceki ortalama * (period - 1) + yeni değer) / period
    """
    values = series.to_numpy(dtype=float)
    result = np.full(len(values), np.nan)

    valid = np.flatnonzero(~np.isnan(values))
    if len(valid) == 0:
        return pd.Series(result, index=series.index)
    start = valid[0]  # örn. RSI'da ilk değişim NaN olduğu için 1'den başlar
    seed_end = start + period
    if seed_end > len(values):
        return pd.Series(result, index=series.index)

    result[seed_end - 1] = values[start:seed_end].mean()
    for i in range(seed_end, len(values)):
        result[i] = (result[i - 1] * (period - 1) + values[i]) / period
    return pd.Series(result, index=series.index)


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index, 0-100 arası.

    Son `period` mumdaki ortalama yükselişin ortalama düşüşe oranına dayanır.
    """
    change = close.diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)
    avg_gain = wilder_average(gain, period)
    avg_loss = wilder_average(loss, period)

    result = 100 - 100 / (1 + avg_gain / avg_loss)
    # Hiç düşüş yoksa bölme sonsuz olur; bu durumda RSI tanım gereği 100'dür.
    result[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    result[(avg_loss == 0) & (avg_gain == 0)] = 50.0
    return result


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD: hızlı EMA ile yavaş EMA arasındaki fark, onun sinyal çizgisi ve histogram."""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({
        "macd": macd_line,
        "macd_signal": signal_line,
        "macd_hist": macd_line - signal_line,
    })


def true_range(df: pd.DataFrame) -> pd.Series:
    """Bir mumun gerçek aralığı. Önceki kapanıştan boşlukla açılışları da hesaba katar."""
    prev_close = df["close"].shift(1)
    ranges = pd.DataFrame({
        "high_low": df["high"] - df["low"],
        "high_prev_close": (df["high"] - prev_close).abs(),
        "low_prev_close": (df["low"] - prev_close).abs(),
    })
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range: piyasanın mum başına ortalama hareket genişliği (volatilite)."""
    return wilder_average(true_range(df), period)
