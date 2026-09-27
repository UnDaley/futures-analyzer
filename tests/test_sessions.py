import pandas as pd

from futures_analyzer.market_time import is_market_open, session_names

NY = "America/New_York"


def ny(*times):
    return pd.DatetimeIndex(times).tz_localize(NY).tz_convert("UTC")


def test_session_names():
    index = ny("2026-06-15 18:00", "2026-06-16 02:55", "2026-06-16 03:00", "2026-06-16 08:00", "2026-06-16 16:55", "2026-06-16 17:00")

    assert list(session_names(index)) == ["asia", "asia", "london", "new_york", "new_york", "closed"]


def test_session_names_follow_new_york_clock_in_winter_and_summer():
    # Aynı UTC saati (13:00) yazın NY 09:00 (new_york), kışın NY 08:00 (new_york);
    # 07:30 UTC ise yazın 03:30 (london), kışın 02:30 (asia)
    summer = pd.DatetimeIndex(["2026-06-16 07:30"]).tz_localize("UTC")
    winter = pd.DatetimeIndex(["2026-01-13 07:30"]).tz_localize("UTC")

    assert list(session_names(summer)) == ["london"]
    assert list(session_names(winter)) == ["asia"]


def test_is_market_open():
    def at(text):
        return pd.Timestamp(text, tz=NY)

    assert is_market_open(at("2026-06-16 10:00"))       # salı
    assert not is_market_open(at("2026-06-16 17:30"))   # günlük ara
    assert not is_market_open(at("2026-06-19 17:30"))   # cuma kapanış sonrası
    assert not is_market_open(at("2026-06-20 12:00"))   # cumartesi
    assert not is_market_open(at("2026-06-21 17:00"))   # pazar açılış öncesi
    assert is_market_open(at("2026-06-21 18:30"))       # pazar akşamı açılış
