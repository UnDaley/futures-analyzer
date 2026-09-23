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


def test_snapshot(client, engine):
    save_candles(engine, "NQ", "1h", make_hourly_candles("2026-06-15 18:00", 300))

    body = client.get("/snapshot", params={"symbol": "nq"}).json()

    assert body["instrument"] == "NQ"
    assert body["timeframes"]["1h"]["technical"]["ema_trend"] == "bullish"
    assert "structure" in body["timeframes"]["1h"]


def test_unknown_symbol(client):
    assert client.get("/candles", params={"symbol": "XYZ"}).status_code == 404


def test_invalid_timeframe(client):
    assert client.get("/candles", params={"symbol": "NQ", "tf": "3h"}).status_code == 400


def test_dashboard_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Futures Analyzer" in response.text
    assert "lightweight-charts" in response.text


def test_chart_has_python_computed_indicators(client, engine):
    save_candles(engine, "NQ", "1h", make_hourly_candles("2026-06-15 18:00", 300))

    body = client.get("/chart", params={"symbol": "NQ", "tf": "1h", "limit": 50}).json()

    assert len(body["bars"]) == 50
    assert set(body["bars"][0]) == {"time", "open", "high", "low", "close", "volume"}
    assert len(body["lines"]["ema_200"]) == 50   # EMA 200 için ısınma mumları ayrıca yüklendi
    assert body["has_vwap"] is True


def test_analyses_endpoint_hides_snapshot(client, engine):
    from futures_analyzer.evaluation.journal import record_analysis

    record_analysis(engine, {
        "instrument": "NQ", "as_of": "2026-06-16T14:00:00+00:00", "price": 100.0,
        "score": {"bias": "neutral", "total": 0.0, "coverage": 50}, "scenarios": None,
    })

    rows = client.get("/analyses", params={"symbol": "NQ"}).json()

    assert len(rows) == 1
    assert "snapshot" not in rows[0]
    assert rows[0]["bias"] == "neutral"


def test_report_without_api_key_returns_503(client, engine, monkeypatch):
    from futures_analyzer import api
    from futures_analyzer.ai.report import ReportError

    def fail(snapshot):
        raise ReportError("Claude API anahtarı geçersiz veya tanımlı değil (ANTHROPIC_API_KEY).")

    monkeypatch.setattr(api, "generate_report", fail)
    save_candles(engine, "NQ", "1h", make_hourly_candles("2026-06-15 18:00", 300))

    response = client.post("/report", params={"symbol": "NQ"})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]
