import pandas as pd
import pytest

from futures_analyzer.data.storage import load_macro_series
from futures_analyzer.macro.engine import macro_snapshot
from futures_analyzer.macro.fred import SERIES, parse_fred_csv
from futures_analyzer.macro.ingest import ingest_macro, load_macro


def test_parse_fred_csv_skips_missing_values():
    text = "observation_date,DGS10\n2026-09-01,4.79\n2026-09-02,.\n2026-09-03,\n2026-09-04,4.78\n"

    series = parse_fred_csv(text)

    assert series.tolist() == [4.79, 4.78]
    assert [d.date().isoformat() for d in series.index] == ["2026-09-01", "2026-09-04"]


def monthly(values, start="2025-01-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="MS"), dtype=float)


def daily(values, start="2026-08-01"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="B"), dtype=float)


def test_yoy_inflation():
    # 14 ay: endeks 100'den başlayıp her ay 0.5 artıyor
    cpi = monthly([100 + 0.5 * i for i in range(14)])

    result = macro_snapshot({"cpi": cpi})["cpi_yoy"]

    # son ay: 106.5 / 100.5 - 1 = %5.97 ; önceki ay: 106 / 100 - 1 = %6
    assert result["value"] == pytest.approx(5.970, abs=0.001)
    assert result["previous"] == pytest.approx(6.0)
    assert result["trend"] == "flat"
    assert result["date"] == "2026-02-01"


def test_yoy_needs_13_months():
    assert macro_snapshot({"cpi": monthly([100] * 12)})["cpi_yoy"] is None


def test_rate_changes():
    us10y = daily([4.0 + 0.01 * i for i in range(25)])

    result = macro_snapshot({"us10y": us10y})["us10y"]

    assert result["value"] == 4.24
    assert result["change_1d"] == 0.01
    assert result["change_20d"] == 0.2


def test_nfp_change_and_levels():
    result = macro_snapshot({
        "nonfarm_payrolls": monthly([1000, 1150, 1170]),
        "unemployment": monthly([4.0, 4.3]),
    })

    assert result["nfp_change"] == {"value": 20.0, "previous": 150.0, "date": "2025-03-01"}
    assert result["unemployment"]["trend"] == "rising"


def test_missing_series_are_none_not_invented():
    result = macro_snapshot({"us10y": daily([4.0, 4.1])})

    assert result["us02y"] is None
    assert result["cpi_yoy"] is None
    assert result["us10y"]["change_20d"] is None  # 20 günlük veri yok


def test_no_data_at_all():
    assert macro_snapshot({"us10y": pd.Series(dtype=float)}) is None


def test_ingest_continues_when_one_series_fails(engine):
    def fake_fetch(series_id):
        if series_id == "DGS2":
            raise ConnectionError("ağ hatası")
        return daily([1.0, 2.0])

    saved = ingest_macro(engine, fetch=fake_fetch)

    assert saved["us02y"] == -1
    assert saved["us10y"] == 2
    assert load_macro_series(engine, "DGS10").tolist() == [1.0, 2.0]
    assert set(load_macro(engine)) == set(SERIES)
