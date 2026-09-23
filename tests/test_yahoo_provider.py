import pandas as pd
import pytest

from futures_analyzer.data.providers.base import CANDLE_COLUMNS
from futures_analyzer.data.providers.yahoo import YahooProvider, to_standard_format
from futures_analyzer.instruments import get_instrument


def fake_yahoo_frame():
    """yfinance'in döndürdüğüne benzer bir tablo (büyük harfli kolonlar, fazladan kolonlar)."""
    index = pd.date_range("2026-06-15 18:00", periods=2, freq="1h", tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [10, 20],
            "Dividends": [0.0, 0.0],
            "Stock Splits": [0.0, 0.0],
        },
        index=index,
    )


def test_to_standard_format():
    df = to_standard_format(fake_yahoo_frame(), tick_size=0.25)

    assert list(df.columns) == CANDLE_COLUMNS
    assert df.index.name == "ts"
    assert str(df.index.tz) == "UTC"
    assert df.index[0].hour == 22  # 18:00 EDT


def test_prices_are_rounded_to_tick():
    raw = fake_yahoo_frame()
    raw["Open"] = [4371.7998046875, 4350.60009765625]  # yfinance'ten gelen gerçek örnekler

    df = to_standard_format(raw, tick_size=0.10)

    assert df["open"].tolist() == [4371.8, 4350.6]


def test_unsupported_timeframe():
    with pytest.raises(ValueError):
        YahooProvider().fetch_candles(get_instrument("NQ"), "4h")


@pytest.mark.network
def test_real_fetch():
    """Gerçek veri çeker. Çalıştırmak için: uv run pytest -m network"""
    df = YahooProvider().fetch_candles(get_instrument("NQ"), "1d")

    assert len(df) > 100
    assert list(df.columns) == CANDLE_COLUMNS
