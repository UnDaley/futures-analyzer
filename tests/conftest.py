"""Testlerde ortak kullanılan yardımcılar."""

import pandas as pd
import pytest

from futures_analyzer.data.storage import create_tables, get_engine


def make_hourly_candles(start_ny: str, hours: int) -> pd.DataFrame:
    """New York saatiyle start_ny'den başlayan, fiyatı her saat 1 artan 1H mumlar üretir."""
    index = pd.date_range(start_ny, periods=hours, freq="1h", tz="America/New_York").tz_convert("UTC")
    base = pd.Series(range(hours), index=index, dtype=float) + 100
    df = pd.DataFrame({
        "open": base,
        "high": base + 2,
        "low": base - 1,
        "close": base + 1,
        "volume": 10.0,
    })
    df.index.name = "ts"
    return df


@pytest.fixture
def engine(tmp_path):
    """Her test için geçici bir SQLite veritabanı. Docker gerektirmez."""
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    create_tables(engine)
    return engine
