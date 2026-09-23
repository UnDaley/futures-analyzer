import pandas as pd

from futures_analyzer.instruments import get_instrument
from futures_analyzer.market_time import is_market_open, session_names
from futures_analyzer.sessions.engine import session_levels, sessions_snapshot

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


def bars_5m(start_ny: str, end_ny: str, price: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(start_ny, end_ny, freq="5min", tz=NY, inclusive="left").tz_convert("UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 10.0}, index=index)


def set_bar(df, time_ny, **values):
    ts = pd.Timestamp(time_ny, tz=NY).tz_convert("UTC")
    for column, value in values.items():
        df.loc[ts, column] = value


def one_day():
    """Önceki gün (15 Haziran) + bugün (16 Haziran) 10:00'a kadar."""
    df = pd.concat([
        bars_5m("2026-06-14 18:00", "2026-06-15 17:00"),
        bars_5m("2026-06-15 18:00", "2026-06-16 10:00"),
    ])
    set_bar(df, "2026-06-15 11:00", high=120.0)              # önceki NY high
    set_bar(df, "2026-06-15 14:00", low=90.0)                # önceki NY low
    set_bar(df, "2026-06-15 20:00", high=110.0)              # Asya high
    set_bar(df, "2026-06-16 01:00", low=95.0)                # Asya low
    set_bar(df, "2026-06-16 04:00", high=108.0, low=94.0)    # Londra: Asya low'unu aldı
    set_bar(df, "2026-06-16 09:30", open=101.0, high=112.0)  # NY açılışı, Asya high'ını aldı
    return df


NOW = pd.Timestamp("2026-06-16 10:05", tz=NY)


def test_sessions_snapshot():
    result = sessions_snapshot(one_day(), get_instrument("NQ"), now=NOW)

    assert result["trading_date"] == "2026-06-16"
    assert result["current_session"] == "new_york"
    assert (result["asia"]["high"], result["asia"]["low"]) == (110.0, 95.0)
    assert (result["london"]["high"], result["london"]["low"]) == (108.0, 94.0)
    assert (result["new_york"]["high"], result["new_york"]["low"]) == (112.0, 100.0)
    assert result["ny_open"] == {"time_ny": "09:30", "price": 101.0}
    assert result["previous_new_york"] == {"trading_date": "2026-06-15", "high": 120.0, "low": 90.0}
    assert result["taken"] == {
        "asia_high_taken": True,     # NY'de 112 > 110
        "asia_low_taken": True,      # Londra'da 94 < 95
        "london_high_taken": True,   # NY'de 112 > 108
        "london_low_taken": False,
    }


def test_gold_uses_comex_open_time():
    df = one_day()
    set_bar(df, "2026-06-16 08:20", open=99.5)

    result = sessions_snapshot(df, get_instrument("GC"), now=NOW)

    assert result["ny_open"] == {"time_ny": "08:20", "price": 99.5}


def test_sessions_not_started_yet_are_none():
    df = bars_5m("2026-06-15 18:00", "2026-06-16 01:00")  # sadece Asya

    result = sessions_snapshot(df, get_instrument("NQ"), now=pd.Timestamp("2026-06-16 01:00", tz=NY))

    assert result["london"] is None
    assert result["new_york"] is None
    assert result["ny_open"]["price"] is None
    assert result["taken"]["asia_high_taken"] is False


def test_session_levels():
    snapshot = sessions_snapshot(one_day(), get_instrument("NQ"), now=NOW)

    sources = {level["source"]: level["price"] for level in session_levels(snapshot)}

    assert sources == {
        "ASIA_HIGH": 110.0, "ASIA_LOW": 95.0,
        "LONDON_HIGH": 108.0, "LONDON_LOW": 94.0,
        "NY_OPEN": 101.0,
        "PREV_NY_HIGH": 120.0, "PREV_NY_LOW": 90.0,
    }
