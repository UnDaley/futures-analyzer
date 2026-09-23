import pandas as pd

from futures_analyzer.indicators.calculations import atr
from futures_analyzer.liquidity.displacement import find_displacements, find_order_blocks
from futures_analyzer.liquidity.engine import liquidity_snapshot, premium_discount
from futures_analyzer.liquidity.fvg import find_fvgs, nearest_fvgs
from futures_analyzer.liquidity.pools import find_sweeps, liquidity_pools
from futures_analyzer.structure.swings import find_swings
from tests.conftest import make_hourly_candles
from tests.test_structure import UPTREND, bars


def ohlc(rows):
    """rows: [(open, high, low, close), ...]"""
    index = pd.date_range("2026-06-15 18:00", periods=len(rows), freq="1h", tz="UTC")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=index, dtype=float)
    df["volume"] = 10.0
    return df


# --- Likidite havuzları ve sweep ---

def test_pools_in_uptrend():
    # UPTREND'de tepeler (5, 7) sonradan aşıldı; dipler (1, 3) hiç aşılmadı
    df = bars(UPTREND)
    pools = liquidity_pools(df, find_swings(df, length=2), tolerance=0.5)

    assert pools["buy_side"] == []
    assert [(p["level"], p["equal"]) for p in pools["sell_side"]] == [(3.0, False), (1.0, False)]  # en yakın önce


def test_equal_lows_are_grouped():
    df = bars(UPTREND)
    pools = liquidity_pools(df, find_swings(df, length=2), tolerance=2.5)  # 1 ile 3 arası 2 puan

    assert [(p["level"], p["count"], p["equal"]) for p in pools["sell_side"]] == [(1.0, 2, True)]


def sweep_setup(last_close):
    # index 2'de swing high (high 14), index 6'da iğne 15'e çıkıyor
    df = bars([10, 11, 13, 11, 10, 12, last_close])
    df.iloc[6, df.columns.get_loc("high")] = 15.0
    return df


def test_wick_through_and_close_back_is_a_sweep():
    df = sweep_setup(last_close=13)  # 15'e iğne, 13'te kapanış (< 14)

    sweeps = find_sweeps(df, find_swings(df, length=2))

    assert [(s["side"], s["level"]) for s in sweeps] == [("buy_side", 14.0)]


def test_close_beyond_level_is_not_a_sweep():
    df = sweep_setup(last_close=14.5)  # 14'ün üstünde kapanış = kırılım

    assert find_sweeps(df, find_swings(df, length=2)) == []


# --- FVG ---

def gap_bars(later_lows):
    # 0: high 10, 1: güçlü mum, 2: low 12 -> bullish FVG [10, 12]
    rows = [(9, 10, 8, 9.5), (9.5, 15, 9, 14.5), (14.5, 17, 12, 16.5)]
    rows += [(16, 17, low, 16.5) for low in later_lows]
    return ohlc(rows)


def test_bullish_fvg_open_partial_filled():
    assert [(g["direction"], g["bottom"], g["top"], g["status"]) for g in find_fvgs(gap_bars([13]), 0)] == [
        ("bullish", 10.0, 12.0, "open")
    ]
    assert find_fvgs(gap_bars([13, 11]), 0)[0]["status"] == "partial"
    assert find_fvgs(gap_bars([13, 11, 10]), 0) == []  # doldu, raporlanmaz


def test_bearish_fvg():
    df = ohlc([(20, 21, 19, 20), (20, 20.5, 14, 14.5), (14.5, 17, 13, 13.5)])  # 2. high 17 < 0. low 19

    gaps = find_fvgs(df, 0)

    assert [(g["direction"], g["bottom"], g["top"]) for g in gaps] == [("bearish", 17.0, 19.0)]


def test_small_gaps_are_ignored():
    assert find_fvgs(gap_bars([13]), min_size=3) == []  # boşluk 2 puan


def test_nearest_fvgs():
    fvgs = [
        {"bottom": 90, "top": 95}, {"bottom": 80, "top": 85},
        {"bottom": 105, "top": 110}, {"bottom": 98, "top": 102},
    ]

    result = nearest_fvgs(fvgs, price=100, limit=1)

    assert result["above"] == [{"bottom": 105, "top": 110}]
    assert result["below"] == [{"bottom": 90, "top": 95}]
    assert result["at_price"] == [{"bottom": 98, "top": 102}]


# --- Displacement ve order block ---

def displacement_setup(after=()):
    rows = [(100, 100.75, 99.75, 100.5)] * 18   # sakin mumlar: aralık 1, gövde 0.5
    rows += [(100.5, 100.75, 99.75, 100)]       # index 18: son kırmızı mum (order block adayı)
    rows += [(100, 105.2, 99.9, 105)]           # index 19: güçlü yeşil mum (gövde 5 = ~5 ATR)
    rows += list(after)
    return ohlc(rows)


def test_displacement_detected():
    df = displacement_setup()

    moves = find_displacements(df, atr(df, 14))

    assert [(m["direction"], m["bar_index"]) for m in moves] == [("bullish", 19)]
    assert moves[0]["atr_multiple"] > 4


def test_order_block_status():
    fresh = displacement_setup(after=[(105, 106, 104, 105.5)])
    tested = displacement_setup(after=[(105, 105, 100.5, 101)])       # low 100.5 blok içine girdi
    invalid = displacement_setup(after=[(105, 105, 99, 99.5)])        # blok low'unun (99.75) altında kapanış

    def blocks(df):
        return find_order_blocks(df, find_displacements(df, atr(df, 14)))

    assert [(b["direction"], b["low"], b["high"], b["status"]) for b in blocks(fresh)] == [("bullish", 99.75, 100.75, "fresh")]
    assert blocks(tested)[0]["status"] == "tested"
    # Bullish blok geçersiz oldu. (Düşüş mumu da güçlü olduğu için yeni bir bearish blok doğar; o ayrı.)
    assert [b for b in blocks(invalid) if b["direction"] == "bullish"] == []
    assert [b["direction"] for b in blocks(invalid)] == ["bearish"]


# --- Premium / discount ve motor ---

def test_premium_discount():
    four_hour = ohlc([(150, 200, 150, 160), (160, 170, 100, 120)])

    assert premium_discount(four_hour, price=190)["zone"] == "premium"      # %90
    assert premium_discount(four_hour, price=150)["zone"] == "equilibrium"  # %50
    assert premium_discount(four_hour, price=110)["position_pct"] == 10.0
    assert premium_discount(four_hour, price=110)["zone"] == "discount"


def test_liquidity_snapshot_structure():
    candles = {"1h": make_hourly_candles("2026-06-15 18:00", 300), "15m": pd.DataFrame(), "4h": None}

    result = liquidity_snapshot(candles, price=400)

    assert set(result["timeframes"]["1h"]) == {"buy_side", "sell_side", "recent_sweeps", "fvg", "recent_displacements", "order_blocks"}
    assert result["timeframes"]["15m"] is None
    assert result["premium_discount"] is None
