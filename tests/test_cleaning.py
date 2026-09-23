import numpy as np
import pandas as pd
import pytest

from futures_analyzer.data.cleaning import clean_candles
from tests.conftest import make_hourly_candles


def test_sorts_and_removes_duplicates():
    df = make_hourly_candles("2026-06-15 18:00", 3)
    shuffled = pd.concat([df.iloc[[2, 0, 1]], df.iloc[[1]]])  # karışık sıra + 1 tekrar

    cleaned = clean_candles(shuffled)

    assert len(cleaned) == 3
    assert cleaned.index.is_monotonic_increasing


def test_drops_missing_prices_and_fills_missing_volume():
    df = make_hourly_candles("2026-06-15 18:00", 3)
    df.iloc[0, df.columns.get_loc("close")] = np.nan
    df.iloc[1, df.columns.get_loc("volume")] = np.nan

    cleaned = clean_candles(df)

    assert len(cleaned) == 2
    assert cleaned["volume"].iloc[0] == 0


def test_drops_impossible_candles():
    df = make_hourly_candles("2026-06-15 18:00", 3)
    df.iloc[1, df.columns.get_loc("high")] = 50  # high, open/close'un altında olamaz

    cleaned = clean_candles(df)

    assert len(cleaned) == 2
    assert df.index[1] not in cleaned.index


def test_converts_to_utc():
    df = make_hourly_candles("2026-06-15 18:00", 2)
    df.index = df.index.tz_convert("America/New_York")

    cleaned = clean_candles(df)

    assert str(cleaned.index.tz) == "UTC"


def test_rejects_timestamps_without_timezone():
    df = make_hourly_candles("2026-06-15 18:00", 2)
    df.index = df.index.tz_localize(None)

    with pytest.raises(ValueError):
        clean_candles(df)
