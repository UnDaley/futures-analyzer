import pandas as pd

from futures_analyzer.intermarket.engine import _signal, asset_state, daily_closes, intermarket_snapshot
from tests.test_levels import session_bars

DAYS = ["2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19", "2026-06-22"]


def closes_to_hourly(closes: list[float]) -> pd.DataFrame:
    """Her işlem günü için sabit fiyatlı 23 adet 1H mum; günün kapanışı = verilen değer."""
    return session_bars({day: (close, close) for day, close in zip(DAYS, closes)})


def test_daily_closes_follow_trading_days():
    closes = daily_closes(closes_to_hourly([100, 101, 102, 103, 104, 105]))

    assert closes.tolist() == [100, 101, 102, 103, 104, 105]
    assert [d.date().isoformat() for d in closes.index] == DAYS


def test_asset_state_percent_and_basis_points():
    index = pd.to_datetime(DAYS[:3])

    stock = asset_state("ES", pd.Series([100.0, 100.0, 101.0], index=index))
    rate = asset_state("US10Y", pd.Series([4.00, 4.00, 4.05], index=index))

    assert (stock["change_1d"], stock["unit"], stock["direction"]) == (1.0, "%", "up")
    assert (rate["change_1d"], rate["unit"], rate["direction"]) == (5.0, "bp", "up")


def test_small_moves_are_flat():
    index = pd.to_datetime(DAYS[:2])

    assert asset_state("ES", pd.Series([100.0, 100.05], index=index))["direction"] == "flat"     # %0.05
    assert asset_state("VIX", pd.Series([15.0, 15.1], index=index))["direction"] == "flat"      # VIX için %1 eşik
    assert asset_state("US10Y", pd.Series([4.00, 4.01], index=index))["direction"] == "flat"   # 1 bp


def test_signal():
    assert _signal("up", "up", 1) == "confirms"      # NQ yukarı, ES yukarı
    assert _signal("up", "down", -1) == "confirms"   # NQ yukarı, DXY aşağı
    assert _signal("up", "up", -1) == "diverges"     # NQ yukarı, VIX yukarı
    assert _signal("up", "flat", 1) == "neutral"
    assert _signal("flat", "up", 1) == "neutral"


def test_intermarket_snapshot():
    hourly = {
        "NQ": closes_to_hourly([100, 101, 102, 103, 104, 105.05]),  # son gün %1 yukarı
        "ES": closes_to_hourly([50, 50.5, 51, 51.5, 52, 52.52]),    # %1 yukarı -> confirms
        "DXY": closes_to_hourly([100, 100, 100, 100, 100, 99]),     # %1 aşağı -> confirms
        "VIX": closes_to_hourly([15, 15, 15, 15, 15, 16]),          # %6.7 yukarı -> diverges
    }
    macro = {"us02y": pd.Series([4.0, 4.0], index=pd.to_datetime(["2026-06-19", "2026-06-22"]))}

    result = intermarket_snapshot("NQ", hourly, macro)

    assert result["instrument"]["direction"] == "up"
    assert result["assets"]["ES"]["signal"] == "confirms"
    assert result["assets"]["DXY"]["signal"] == "confirms"
    assert result["assets"]["VIX"]["signal"] == "diverges"
    assert result["assets"]["US02Y"]["direction"] == "flat"
    assert result["assets"]["YM"] is None       # veri yok -> uydurulmuyor
    assert (result["confirming"], result["diverging"]) == (2, 1)


def test_correlation_needs_enough_days():
    hourly = {"NQ": closes_to_hourly([100, 101, 102, 103, 104, 105]), "ES": closes_to_hourly([50, 51, 52, 53, 54, 55])}

    result = intermarket_snapshot("NQ", hourly, {})

    assert result["assets"]["ES"]["correlation_20d"] is None  # 5 günlük getiri < 10


def test_smt_divergence():
    # Son gün NQ önceki günün high'ını (110) aşıyor, ES aşamıyor
    nq = session_bars({"2026-06-18": (110, 100), "2026-06-19": (115, 105)})
    es = session_bars({"2026-06-18": (60, 50), "2026-06-19": (59, 51)})

    result = intermarket_snapshot("NQ", {"NQ": nq, "ES": es}, {})

    assert result["smt"]["divergence"] == "bearish"
    assert result["smt"]["taken"]["NQ"]["pdh_taken"] is True
    assert result["smt"]["taken"]["ES"]["pdh_taken"] is False
