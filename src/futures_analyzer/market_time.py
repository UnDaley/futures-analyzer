"""CME seans saatleriyle ilgili ortak hesaplar.

CME futures seansı New York saatiyle 18:00'de açılır, ertesi gün 17:00'de kapanır.
Hesapları New York duvar saatiyle yapıyoruz; böylece yaz saati (DST) değişince
UTC karşılığı kayar ama New York'taki saat hep aynı kalır.
"""

import pandas as pd

NEW_YORK = "America/New_York"
SESSION_OPEN_HOUR = 18
SESSION_CLOSE_HOUR = 17


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
