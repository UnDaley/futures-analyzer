from futures_analyzer.data.ingest import ingest
from futures_analyzer.data.providers.base import DataProvider
from futures_analyzer.data.storage import load_candles
from futures_analyzer.instruments import get_instrument
from tests.conftest import make_hourly_candles


class FakeProvider(DataProvider):
    """İnternete çıkmadan sabit veri döndüren sağlayıcı."""

    def fetch_candles(self, instrument, timeframe):
        return make_hourly_candles("2026-06-15 18:00", 23)


def test_ingest_1h_also_builds_4h(engine):
    saved = ingest(engine, FakeProvider(), get_instrument("NQ"), "1h")

    assert saved == {"1h": 23, "4h": 6}
    assert len(load_candles(engine, "NQ", "4h")) == 6


def test_ingest_twice_keeps_same_row_count(engine):
    ingest(engine, FakeProvider(), get_instrument("NQ"), "1h")
    ingest(engine, FakeProvider(), get_instrument("NQ"), "1h")

    assert len(load_candles(engine, "NQ", "1h")) == 23
