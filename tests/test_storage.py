from futures_analyzer.data.storage import load_candles, save_candles
from tests.conftest import make_hourly_candles


def test_save_and_load(engine):
    df = make_hourly_candles("2026-06-15 18:00", 5)

    save_candles(engine, "NQ", "1h", df)
    loaded = load_candles(engine, "NQ", "1h")

    assert len(loaded) == 5
    assert str(loaded.index.tz) == "UTC"
    assert list(loaded.index) == list(df.index)
    assert loaded["close"].tolist() == df["close"].tolist()


def test_saving_twice_does_not_duplicate_and_updates_values(engine):
    df = make_hourly_candles("2026-06-15 18:00", 5)
    save_candles(engine, "NQ", "1h", df)

    updated = df.copy()
    updated.iloc[-1, updated.columns.get_loc("close")] = 999.0  # son mum kapanmadan önce değişmiş gibi
    save_candles(engine, "NQ", "1h", updated)

    loaded = load_candles(engine, "NQ", "1h")
    assert len(loaded) == 5
    assert loaded["close"].iloc[-1] == 999.0


def test_symbols_and_timeframes_are_separate(engine):
    df = make_hourly_candles("2026-06-15 18:00", 3)
    save_candles(engine, "NQ", "1h", df)
    save_candles(engine, "ES", "1h", df.iloc[:1])

    assert len(load_candles(engine, "NQ", "1h")) == 3
    assert len(load_candles(engine, "ES", "1h")) == 1
    assert load_candles(engine, "NQ", "4h").empty


def test_limit_returns_latest_in_order(engine):
    df = make_hourly_candles("2026-06-15 18:00", 5)
    save_candles(engine, "NQ", "1h", df)

    loaded = load_candles(engine, "NQ", "1h", limit=2)

    assert list(loaded.index) == list(df.index[-2:])
