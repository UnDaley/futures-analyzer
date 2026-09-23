"""CME seans saatleriyle ilgili ortak hesaplar.

CME futures seansı New York saatiyle 18:00'de açılır, ertesi gün 17:00'de kapanır.
Hesapları New York duvar saatiyle yapıyoruz; böylece yaz saati (DST) değişince
UTC karşılığı kayar ama New York'taki saat hep aynı kalır.
"""

import pandas as pd

NEW_YORK = "America/New_York"
SESSION_OPEN_HOUR = 18
SESSION_CLOSE_HOUR = 17

# yfinance verisi ~15 dk gecikmeli gelir ve son satır henüz dolmamış (hacmi 0 olabilen) mumdur.
# Bir mumu ancak kapanışından bu kadar sonra kesinleşmiş sayıyoruz. Gerçek zamanlı bir
# veri kaynağına geçince bu değer küçültülmeli.
DATA_DELAY = pd.Timedelta(minutes=15)


def floor_to_session_grid(index: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """Her zaman damgasını, seans açılışından başlayan freq'lik dilimin başına indirir.

    freq="4h" -> 18:00, 22:00, 02:00, ... dilimleri
    freq="1D" -> içinde bulunduğu seansın açılışı (18:00)
    Sonuç UTC'dir.
    """
    local = index.tz_convert(NEW_YORK).tz_localize(None)

    # Saati 18 saat geri kaydırınca seans açılışı gece yarısına denk gelir,
    # böylece standart floor ile dilimlere bölebiliriz.
    shift = pd.Timedelta(hours=SESSION_OPEN_HOUR)
    floored = (local - shift).floor(freq) + shift

    # DST geçişi pazar gecesi 02:00'de olur, piyasa o saatte kapalıdır;
    # yine de olmayan bir saate denk gelirse ileri kaydırıyoruz.
    return (
        pd.DatetimeIndex(floored)
        .tz_localize(NEW_YORK, nonexistent="shift_forward")
        .tz_convert("UTC")
    )


def session_start(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Her zaman damgasının ait olduğu seansın açılış zamanı (UTC)."""
    return floor_to_session_grid(index, "1D")


def bar_end(ts: pd.Timestamp, timeframe: str) -> pd.Timestamp:
    """Mumun kapanış zamanı (UTC).

    Günlük mumun zaman damgası işlem gününün tarihidir; o gün New York saatiyle 17:00'de kapanır.
    """
    if timeframe == "1d":
        session_date = ts.tz_convert(NEW_YORK).date()
        close_time = pd.Timestamp(session_date, tz=NEW_YORK) + pd.Timedelta(hours=SESSION_CLOSE_HOUR)
        return close_time.tz_convert("UTC")
    return ts + pd.Timedelta(timeframe)


def is_bar_complete(ts: pd.Timestamp, timeframe: str, now: pd.Timestamp | None = None) -> bool:
    """Mum kapandı ve veri gecikmesi de geçti mi?"""
    now = now or pd.Timestamp.now(tz="UTC")
    return bool(now >= bar_end(ts, timeframe) + DATA_DELAY)


def drop_incomplete_last_bar(df: pd.DataFrame, timeframe: str, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Son mum henüz kesinleşmediyse onu çıkarır. Kapanışa dayalı analizler için."""
    if df.empty or is_bar_complete(df.index[-1], timeframe, now):
        return df
    return df.iloc[:-1]


def trading_date(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Her zaman damgasının ait olduğu işlem günü (New York tarihi, saat 00:00, saat dilimsiz).

    Seans 18:00'de açıldığı için akşam 18:00'den sonrası ertesi günün işlem günüdür.
    Örn. pazar 19:00 -> pazartesi, pazartesi 16:00 -> pazartesi, pazartesi 18:00 -> salı.
    """
    local_start = session_start(index).tz_convert(NEW_YORK).tz_localize(None)
    return (local_start + pd.Timedelta(hours=24 - SESSION_OPEN_HOUR)).floor("D")
