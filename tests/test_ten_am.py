"""10am modeli testleri.

Test verisi: 5 dakikalık düz mumlar (hepsi 100), sonra senaryoya göre belirli mumlar değiştirilir.
Test kontratı: tick 0.25, manipülasyon eşiği 5 puan. Bugün = 16 Eylül 2026 (çarşamba).
"""

from datetime import date

import pandas as pd

from futures_analyzer.analysis import build_snapshot
from futures_analyzer.instruments import Instrument
from futures_analyzer.strategy.ten_am import recent_days, summarize, ten_am_day

NY = "America/New_York"
TEST = Instrument("T", "Test", "T=F", tick_size=0.25, trap_points=5)
DAY = date(2026, 9, 16)
AFTER_DAY = pd.Timestamp("2026-09-16 18:00", tz=NY)


def flat(start_ny: str, end_ny: str, price: float = 100.0) -> pd.DataFrame:
    index = pd.date_range(start_ny, end_ny, freq="5min", tz=NY, inclusive="left").tz_convert("UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price, "volume": 10.0}, index=index)


def two_days() -> pd.DataFrame:
    """Önceki işlem günü (15 Eylül) ve bugün, CME seanslarıyla (18:00-17:00)."""
    return pd.concat([flat("2026-09-14 18:00", "2026-09-15 17:00"), flat("2026-09-15 18:00", "2026-09-16 17:00")])


def bar(df, time_ny, o, h, low, c):
    ts = pd.Timestamp(f"2026-09-16 {time_ny}", tz=NY).tz_convert("UTC")
    df.loc[ts, ["open", "high", "low", "close"]] = [o, h, low, c]


def at(time_ny: str) -> pd.Timestamp:
    return pd.Timestamp(f"2026-09-16 {time_ny}", tz=NY).tz_convert("UTC")


def short_setup() -> pd.DataFrame:
    """Yukarı manipülasyon (108), 10:05'te geri kırılım, 10:15'te retest -> short giriş 100, stop 108.25."""
    df = two_days()
    df.loc[pd.Timestamp("2026-09-15 12:00", tz=NY).tz_convert("UTC"), "low"] = 90.0  # önceki gün düşüğü
    bar(df, "10:00", 100, 107, 100, 106)   # manipülasyon: açılıştan 7 puan yukarı
    bar(df, "10:05", 106, 108, 98, 98)     # uç 108, açılışın altında kapanış
    bar(df, "10:10", 98, 99, 97, 98)       # açılışa dokunmadı
    bar(df, "10:15", 98, 100.5, 99, 99)    # retest: açılışa dokundu, altında kapandı
    return df


def test_short_setup_reaches_target():
    df = short_setup()
    bar(df, "10:30", 99, 99, 89, 90)       # önceki gün düşüğüne (90) iniyor

    result = ten_am_day(df, DAY, TEST, AFTER_DAY)

    assert result["status"] == "target"
    assert result["direction"] == "short"
    assert result["open_level"] == 100.0
    assert result["manipulation"]["extreme"] == 108.0
    assert result["break"]["ts"] == at("10:05").isoformat()
    assert result["entry"] == {"price": 100.0, "ts": at("10:15").isoformat()}
    assert result["stop"] == 108.25
    # 10:00 sonrası dip (97) 1R'den yakın olduğu için atlandı; ilk uygun likidite önceki gün düşüğü
    assert result["target"] == {"price": 90.0, "source": "Önceki gün düşüğü"}
    assert result["rr"] == 1.21
    assert result["r_multiple"] == 1.21
    assert result["exit"]["ts"] == at("10:30").isoformat()


def test_long_setup_hits_stop():
    df = two_days()
    df.loc[pd.Timestamp("2026-09-15 12:00", tz=NY).tz_convert("UTC"), "high"] = 110.0
    bar(df, "10:00", 100, 100, 94, 95)     # aşağı manipülasyon
    bar(df, "10:05", 95, 102, 95, 102)     # açılışın üstünde kapanış
    bar(df, "10:10", 102, 102, 99.5, 101)  # retest -> long giriş 100, stop 93.75
    bar(df, "11:00", 101, 101, 93, 94)     # stop

    result = ten_am_day(df, DAY, TEST, AFTER_DAY)

    assert result["status"] == "stop"
    assert result["direction"] == "long"
    assert result["stop"] == 93.75
    assert result["target"] == {"price": 110.0, "source": "Önceki gün yükseği"}
    assert result["r_multiple"] == -1.0


def test_no_manipulation_means_no_setup():
    result = ten_am_day(two_days(), DAY, TEST, AFTER_DAY)

    assert result["status"] == "no_setup"
    assert result["direction"] is None
    assert result["finished"] is True


def test_trend_without_break_back_means_no_setup():
    df = two_days()
    for minute, price in [("10:00", 106), ("10:30", 110), ("11:30", 115)]:
        bar(df, minute, 100, price, 100, price)

    result = ten_am_day(df, DAY, TEST, AFTER_DAY)

    assert result["status"] == "no_setup"
    assert result["manipulation"]["side"] == "up"
    assert result["entry"] is None


def test_failed_retest_waits_for_a_new_break_and_moves_the_stop():
    df = short_setup()
    bar(df, "10:15", 98, 104, 98, 103)     # retest mumu açılışın ÜSTÜNDE kapandı: kırılım başarısız
    bar(df, "10:20", 103, 109, 99, 99)     # yeni uç 109, yeniden kırılım
    bar(df, "10:25", 99, 100, 99, 99.5)    # retest -> giriş

    result = ten_am_day(df, DAY, TEST, AFTER_DAY)

    assert result["entry"]["ts"] == at("10:25").isoformat()
    assert result["break"]["ts"] == at("10:20").isoformat()
    assert result["stop"] == 109.25


def test_entry_after_deadline_is_not_taken():
    df = two_days()
    bar(df, "10:00", 100, 107, 100, 106)
    bar(df, "11:55", 106, 106, 98, 98)     # kırılım 11:55'te
    bar(df, "12:00", 98, 100.5, 98, 99)    # retest 12:00'de: süre doldu

    assert ten_am_day(df, DAY, TEST, AFTER_DAY)["status"] == "no_setup"


def test_fallback_target_is_two_r_without_liquidity():
    df = short_setup()  # önceki gün düşüğü 90; onu kaldırınca aşağıda likidite kalmaz
    df.loc[pd.Timestamp("2026-09-15 12:00", tz=NY).tz_convert("UTC"), "low"] = 100.0

    result = ten_am_day(df, DAY, TEST, AFTER_DAY)

    assert result["target"]["price"] == 83.5   # 100 - 2 * 8.25
    assert result["target"]["source"].startswith("2R")


def test_open_trade_closes_at_16():
    df = short_setup()
    bar(df, "15:55", 99, 99, 96, 96)

    result = ten_am_day(df, DAY, TEST, AFTER_DAY)

    assert result["status"] == "time_exit"
    assert result["exit"]["price"] == 96.0
    assert result["r_multiple"] == round(4 / 8.25, 2)


def test_stop_on_the_retest_bar_counts_as_stop():
    df = short_setup()
    bar(df, "10:15", 98, 109, 99, 99)      # retest mumu stop'a da dokundu

    assert ten_am_day(df, DAY, TEST, AFTER_DAY)["status"] == "stop"


def test_target_and_stop_in_same_bar_is_ambiguous():
    df = short_setup()
    bar(df, "10:30", 99, 109, 89, 95)

    result = ten_am_day(df, DAY, TEST, AFTER_DAY)

    assert result["status"] == "ambiguous"
    assert result["r_multiple"] is None


def test_live_states_follow_the_day():
    df = short_setup()
    bar(df, "10:30", 99, 99, 89, 90)
    # `now` anına kadar başlamış mumlar görülür; son mum kapanışından 15 dk (veri gecikmesi) geçmeden sayılmaz
    times = ["09:00", "10:05", "10:10", "10:20", "10:30", "10:35", "10:40"]
    states = {now: ten_am_day(df, DAY, TEST, at(now))["status"] for now in times}

    assert states == {
        "09:00": "before_open",
        "10:05": "before_open",      # 10:00 mumu henüz kapanmadı
        "10:10": "manipulation",     # 10:00 mumu: 7 puan yukarı
        "10:20": "waiting_retest",   # 10:05 mumu açılışın altında kapandı
        "10:30": "in_trade",         # 10:15 retest mumu
        "10:35": "in_trade",
        "10:40": "target",           # 10:30 mumu hedefe indi
    }


def test_past_days_do_not_change_with_later_data():
    df = short_setup()
    bar(df, "10:30", 99, 99, 89, 90)
    later = pd.concat([df, flat("2026-09-16 18:00", "2026-09-17 17:00", price=50.0)])

    assert ten_am_day(df, DAY, TEST, AFTER_DAY) == ten_am_day(later, DAY, TEST, pd.Timestamp("2026-09-20", tz=NY))


def test_recent_days_and_summary():
    df = short_setup()
    bar(df, "10:30", 99, 99, 89, 90)

    results = recent_days(df, TEST, pd.Timestamp("2026-09-17 09:00", tz=NY), days=10)
    stats = summarize(results)

    assert [r["date"] for r in results] == ["2026-09-16", "2026-09-15"]
    assert stats["days"] == 2
    assert stats["setups"] == 1
    assert stats["wins"] == 1 and stats["losses"] == 0
    assert stats["win_rate"] == 100.0
    assert stats["total_r"] == 1.21
    assert stats["short"] == {"setups": 1, "win_rate": 100.0}
    assert stats["no_setup"] == 1


def test_snapshot_explains_the_next_step():
    df = short_setup()

    snapshot = build_snapshot(df, TEST, at("10:20"))

    assert snapshot["setup"]["status"] == "waiting_retest"
    assert "100.00" in snapshot["setup"]["next"]
    assert "retest" in snapshot["setup"]["next"]
    names = [level["name"] for level in snapshot["levels"]]
    assert "10:00 açılışı" in names and "Önceki gün düşüğü" in names
    assert snapshot["history"]["days"][0]["date"] == "2026-09-15"
    assert snapshot["price"] == 99.0  # son başlamış mumun (10:15) kapanışı


def test_snapshot_on_weekend_shows_friday():
    friday = pd.concat([flat("2026-09-17 18:00", "2026-09-18 17:00")])

    snapshot = build_snapshot(friday, TEST, pd.Timestamp("2026-09-19 12:00", tz=NY))

    assert snapshot["setup"]["date"] == "2026-09-18"
    assert snapshot["setup"]["status"] == "no_setup"
    assert snapshot["history"]["days"] == []
