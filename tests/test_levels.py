import pandas as pd

from futures_analyzer.instruments import get_instrument
from futures_analyzer.levels.engine import levels_snapshot
from futures_analyzer.levels.reference import reference_levels, round_number_levels
from futures_analyzer.levels.zones import build_zones, split_by_price
from futures_analyzer.market_time import trading_date

NY = "America/New_York"


def session_bars(days_high_low: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """Her işlem günü için 23 adet 1H mum (önceki akşam 18:00 - 16:00 NY).

    Günün high'ı 5. mumda, low'u 10. mumda; diğer mumlar ortada düz.
    """
    frames = []
    for day, (high, low) in days_high_low.items():
        start = pd.Timestamp(day) - pd.Timedelta(hours=6)  # önceki gün 18:00
        index = pd.date_range(start, periods=23, freq="1h", tz=NY).tz_convert("UTC")
        mid = (high + low) / 2
        df = pd.DataFrame({"open": mid, "high": mid, "low": mid, "close": mid, "volume": 10.0}, index=index)
        df.iloc[5, df.columns.get_loc("high")] = high
        df.iloc[10, df.columns.get_loc("low")] = low
        frames.append(df)
    return pd.concat(frames)


# 15-19 Haziran 2026 (pazartesi-cuma) = geçen hafta, 22-24 Haziran = bu hafta (bugün 24'ü)
TWO_WEEKS = {
    "2026-06-15": (110, 90),
    "2026-06-16": (130, 100),   # geçen haftanın en yükseği
    "2026-06-17": (120, 85),    # geçen haftanın en düşüğü
    "2026-06-18": (115, 95),
    "2026-06-19": (112, 96),
    "2026-06-22": (140, 105),
    "2026-06-23": (150, 108),   # önceki gün
    "2026-06-24": (145, 120),   # içinde bulunulan seans
}


def test_trading_date():
    index = pd.DatetimeIndex([
        "2026-06-14 19:00",  # pazar akşamı -> pazartesi seansı
        "2026-06-15 16:00",  # pazartesi -> pazartesi
        "2026-06-15 18:00",  # pazartesi akşamı -> salı seansı
        "2026-06-19 16:00",  # cuma -> cuma
    ]).tz_localize(NY)

    assert list(trading_date(index).strftime("%Y-%m-%d")) == ["2026-06-15", "2026-06-15", "2026-06-16", "2026-06-19"]


def test_reference_levels():
    levels = reference_levels(session_bars(TWO_WEEKS))

    assert levels == {
        "session_date": "2026-06-24",
        "session_high": 145.0,
        "session_low": 120.0,
        "pdh": 150.0,
        "pdl": 108.0,
        "pwh": 130.0,
        "pwl": 85.0,
    }


def test_reference_levels_with_one_day_only():
    levels = reference_levels(session_bars({"2026-06-24": (145, 120)}))

    assert levels["session_high"] == 145.0
    assert levels["pdh"] is None  # önceki gün verisi yok, uydurulmuyor
    assert levels["pwh"] is None


def test_round_number_levels():
    assert round_number_levels(30935, 100) == [30800, 30900, 31000, 31100]
    assert round_number_levels(31000, 100) == [30900, 31000, 31100, 31200]  # fiyat tam yuvarlak seviyede
    assert round_number_levels(4351.3, 25) == [4325, 4350, 4375, 4400]


def level(price, source):
    return {"price": price, "source": source}


def test_close_levels_merge_into_one_zone():
    zones = build_zones([level(110, "PDH"), level(100, "ROUND"), level(100.5, "SWING_HIGH_1H"), level(103, "VWAP")], tolerance=1)

    assert zones == [
        {"low": 100, "high": 100.5, "sources": ["ROUND", "SWING_HIGH_1H"], "strength": 2},
        {"low": 103, "high": 103, "sources": ["VWAP"], "strength": 1},
        {"low": 110, "high": 110, "sources": ["PDH"], "strength": 1},
    ]


def test_zone_width_never_exceeds_tolerance():
    # 100 -> 100.8 -> 101.6: her biri bir öncekine yakın ama zone 1 puandan geniş olamaz
    zones = build_zones([level(100, "A"), level(100.8, "B"), level(101.6, "C")], tolerance=1)

    assert [(z["low"], z["high"]) for z in zones] == [(100, 100.8), (101.6, 101.6)]


def test_same_source_counted_once():
    zones = build_zones([level(100, "SWING_HIGH_1H"), level(100.2, "SWING_HIGH_1H")], tolerance=1)

    assert zones[0]["strength"] == 1


def test_split_by_price():
    zones = build_zones([level(p, f"L{p}") for p in [90, 95, 100, 105, 110]], tolerance=0)

    result = split_by_price(zones, price=100, limit=1)

    assert [(z["low"], z["distance"]) for z in result["resistance"]] == [(105, 5)]  # en yakın direnç
    assert [(z["low"], z["distance"]) for z in result["support"]] == [(95, 5)]      # en yakın destek
    assert [z["low"] for z in result["at_price"]] == [100]


def five_min_bars(start_ny: str, closes: list[float], volumes: list[float]) -> pd.DataFrame:
    index = pd.date_range(start_ny, periods=len(closes), freq="5min", tz=NY).tz_convert("UTC")
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": volumes})


def test_levels_snapshot():
    candles = {
        "1h": session_bars(TWO_WEEKS),
        "5m": five_min_bars("2026-06-24 10:00", [130, 131, 132], [10, 10, 10]),
    }

    result = levels_snapshot(candles, get_instrument("NQ"))

    assert result["price"] == 132.0
    assert result["reference"]["pdh"] == 150.0
    assert result["reference"]["vwap"] == 131.0
    assert all(z["low"] > 132 for z in result["resistance"])
    assert all(z["high"] < 132 for z in result["support"])
    # PDH (150) bir direnç zone'unda olmalı
    assert any("PDH" in z["sources"] for z in result["resistance"])


def test_vwap_is_not_taken_from_previous_session():
    # Önceki seansın son mumu + yeni seansın ilk mumu (hacim 0 -> VWAP henüz tanımsız)
    five_min = pd.concat([
        five_min_bars("2026-06-23 16:55", [140], [10]),
        five_min_bars("2026-06-23 18:00", [141], [0]),
    ])
    candles = {"1h": session_bars(TWO_WEEKS), "5m": five_min}

    result = levels_snapshot(candles, get_instrument("NQ"))

    assert result["reference"]["vwap"] is None
    assert all("VWAP" not in z["sources"] for side in ["resistance", "support", "at_price"] for z in result[side])


def test_levels_snapshot_needs_data():
    assert levels_snapshot({"1h": session_bars(TWO_WEEKS)}, get_instrument("NQ")) is None
