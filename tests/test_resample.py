from futures_analyzer.data.resample import resample_to_4h
from tests.conftest import make_hourly_candles

# Bir CME seansı: 18:00'den ertesi gün 17:00'ye kadar 23 saatlik mum
SESSION_HOURS = 23


def ny_hours(df):
    return list(df.index.tz_convert("America/New_York").hour)


def test_buckets_align_to_session_open_in_summer():
    hourly = make_hourly_candles("2026-06-15 18:00", SESSION_HOURS)  # yaz saati (EDT)

    result = resample_to_4h(hourly)

    assert ny_hours(result) == [18, 22, 2, 6, 10, 14]
    assert result.index[0].hour == 22  # 18:00 EDT = 22:00 UTC


def test_buckets_align_to_session_open_in_winter():
    hourly = make_hourly_candles("2026-01-12 18:00", SESSION_HOURS)  # kış saati (EST)

    result = resample_to_4h(hourly)

    assert ny_hours(result) == [18, 22, 2, 6, 10, 14]
    assert result.index[0].hour == 23  # 18:00 EST = 23:00 UTC


def test_ohlcv_aggregation():
    hourly = make_hourly_candles("2026-06-15 18:00", SESSION_HOURS)

    first = resample_to_4h(hourly).iloc[0]  # 18:00-22:00 arası 4 mum

    assert first["open"] == hourly["open"].iloc[0]
    assert first["high"] == hourly["high"].iloc[:4].max()
    assert first["low"] == hourly["low"].iloc[:4].min()
    assert first["close"] == hourly["close"].iloc[3]
    assert first["volume"] == hourly["volume"].iloc[:4].sum()


def test_last_bucket_of_session_is_three_hours():
    hourly = make_hourly_candles("2026-06-15 18:00", SESSION_HOURS)

    last = resample_to_4h(hourly).iloc[-1]  # 14:00-17:00

    assert last["volume"] == 3 * 10


def test_drops_incomplete_first_bucket():
    hourly = make_hourly_candles("2026-06-15 20:00", 6)  # 18:00 dilimine ortasından başlıyor

    result = resample_to_4h(hourly)

    assert ny_hours(result) == [22]
