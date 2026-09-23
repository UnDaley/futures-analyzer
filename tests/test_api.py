import pytest
from fastapi.testclient import TestClient

from futures_analyzer.api import app, db_engine
from futures_analyzer.data.storage import save_candles
from tests.conftest import make_hourly_candles


@pytest.fixture
def client(engine):
    app.dependency_overrides[db_engine] = lambda: engine  # gerçek DB yerine test DB'si
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_candles(client, engine):
    save_candles(engine, "NQ", "1h", make_hourly_candles("2026-06-15 18:00", 5))

    response = client.get("/candles", params={"symbol": "nq", "tf": "1h", "limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert set(body[0]) == {"ts", "open", "high", "low", "close", "volume"}


def test_indicators(client, engine):
    save_candles(engine, "NQ", "1h", make_hourly_candles("2026-06-15 18:00", 300))

    body = client.get("/indicators", params={"symbol": "nq"}).json()

    assert body["instrument"] == "NQ"
    assert body["timeframes"]["1h"]["ema_trend"] == "bullish"


def test_unknown_symbol(client):
    assert client.get("/candles", params={"symbol": "XYZ"}).status_code == 404


def test_invalid_timeframe(client):
    assert client.get("/candles", params={"symbol": "NQ", "tf": "3h"}).status_code == 400
