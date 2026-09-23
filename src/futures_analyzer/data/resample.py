"""1 saatlik mumlardan 4 saatlik mum üretir.

CME seansı New York saatiyle 18:00'de açılır. 4H mumları bu saate hizalıyoruz:
18:00, 22:00, 02:00, 06:00, 10:00, 14:00 (New York saati).
Seans 17:00'de kapandığı için 14:00 mumu 3 saatliktir.

Hesabı New York'un duvar saatiyle yapıyoruz. Böylece yaz saati (DST)
değişince mumların başlangıç saati UTC'de kayar ama New York'ta hep aynı kalır.
"""

import pandas as pd

NEW_YORK = "America/New_York"
SESSION_OPEN_HOUR = 18


def resample_to_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    """Temizlenmiş 1H mumları 4H mumlara çevirir. Sonuç UTC zaman damgalıdır."""
    if hourly.empty:
        return hourly.copy()

    # New York duvar saati (saat dilimi bilgisi olmadan)
    local = hourly.index.tz_convert(NEW_YORK).tz_localize(None)

    # Saati 18 saat geri kaydırınca seans açılışı gece yarısına denk gelir,
    # böylece 4 saatlik dilimlere bölmek kolaylaşır.
    shift = pd.Timedelta(hours=SESSION_OPEN_HOUR)
    bucket_local = (local - shift).floor("4h") + shift

    # Tekrar UTC'ye çevir. DST geçişi pazar gecesi 02:00'de olur, piyasa o saatte
    # kapalıdır; yine de olmayan bir saate denk gelirse ileri kaydırıyoruz.
    bucket_utc = (
        pd.DatetimeIndex(bucket_local)
        .tz_localize(NEW_YORK, nonexistent="shift_forward")
        .tz_convert("UTC")
    )

    grouped = hourly.groupby(bucket_utc)
    result = pd.DataFrame({
        "open": grouped["open"].first(),
        "high": grouped["high"].max(),
        "low": grouped["low"].min(),
        "close": grouped["close"].last(),
        "volume": grouped["volume"].sum(),
    })
    result.index.name = "ts"

    # Veri bir 4H diliminin ortasından başlıyorsa ilk mum eksik kalır; onu atıyoruz.
    if hourly.index[0] != result.index[0]:
        result = result.iloc[1:]
    return result
