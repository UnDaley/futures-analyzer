import pytest
from fastapi.testclient import TestClient

from futures_analyzer.api import app, db_engine
from futures_analyzer.data.storage import save_candles, save_report
from tests.conftest import make_hourly_candles
from tests.test_ten_am import short_setup


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
    save_candles(engine, "NQ", "5m", short_setup())

    body = client.get("/snapshot", params={"symbol": "nq"}).json()

    assert body["instrument"] == "NQ"
    assert body["history"]["stats"]["days"] == 2      # geçmiş günler 5M veriden hesaplanır
    assert body["history"]["days"][0]["date"] == "2026-09-16"
    # NQ'nun eşiği 15 puan; test verisindeki 8 puanlık hareket manipülasyon sayılmaz
    assert body["history"]["days"][0]["status"] == "no_setup"
    assert body["history"]["days"][0]["open_level"] == 100.0
    assert body["setup"]["next"]
    assert body["events"] == {"event_risk": None, "just_released": [], "upcoming": [], "today": []}


def test_unknown_symbol(client):
    assert client.get("/candles", params={"symbol": "XYZ"}).status_code == 404


def test_invalid_timeframe(client):
    assert client.get("/candles", params={"symbol": "NQ", "tf": "3h"}).status_code == 400


def test_dashboard_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "10am Model" in response.text
    assert "lightweight-charts" in response.text
    assert client.get("/icon.svg").headers["content-type"] == "image/svg+xml"


def test_chart_has_python_computed_indicators(client, engine):
    save_candles(engine, "NQ", "1h", make_hourly_candles("2026-06-15 18:00", 300))

    body = client.get("/chart", params={"symbol": "NQ", "tf": "1h", "limit": 50}).json()

    assert len(body["bars"]) == 50
    assert set(body["bars"][0]) == {"time", "open", "high", "low", "close", "volume"}
    assert len(body["lines"]["ema_200"]) == 50   # EMA 200 için ısınma mumları ayrıca yüklendi
    assert body["has_vwap"] is True


def test_reports_endpoint_lists_only_reports_and_hides_snapshot(client, engine):
    snapshot = {"instrument": "NQ", "as_of": "2026-06-16T14:00:00+00:00", "price": 100.0, "setup": {"status": "in_trade"}}
    save_report(engine, snapshot)  # prompt kopyalandı ama rapor yapıştırılmadı
    save_report(engine, snapshot, {"text": "Rapor", "model": "test", "validated": True})

    rows = client.get("/reports", params={"symbol": "NQ"}).json()

    assert len(rows) == 1
    assert "snapshot" not in rows[0]
    assert rows[0]["report_text"] == "Rapor"
    assert rows[0]["setup_status"] == "in_trade"


def test_report_without_api_key_returns_503(client, engine, monkeypatch):
    from futures_analyzer import api
    from futures_analyzer.ai.report import ReportError

    def fail(snapshot):
        raise ReportError("Claude API anahtarı geçersiz veya tanımlı değil (ANTHROPIC_API_KEY).")

    monkeypatch.setattr(api, "generate_report", fail)
    save_candles(engine, "NQ", "5m", short_setup())

    response = client.post("/report", params={"symbol": "NQ"})

    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_refresh_endpoints_run_in_background(client, engine, monkeypatch):
    import time

    from futures_analyzer import api
    from futures_analyzer.refresh import RefreshJob

    def fake_refresh(engine, log):
        log("NQ 1h: 10 mum")
        return []

    monkeypatch.setattr(api, "refresh_job", RefreshJob(lambda: engine, refresh=fake_refresh))

    assert client.post("/refresh").json()["started"] is True
    for _ in range(50):
        status = client.get("/refresh/status").json()
        if not status["running"]:
            break
        time.sleep(0.05)
    assert status["running"] is False
    assert status["log"] == ["NQ 1h: 10 mum"]
    assert status["errors"] == []


def test_prompt_and_check_report_flow(client, engine):
    save_candles(engine, "NQ", "5m", short_setup())

    prompt = client.post("/prompt", params={"symbol": "NQ"}).json()
    assert "<market_data>" in prompt["text"]
    assert "10am" in prompt["text"]

    result = client.post("/check-report", json={"id": prompt["id"], "text": "Rapor: fiyat verisi yok."}).json()
    assert result["validated"] is True
    assert client.post("/check-report", json={"id": 999, "text": "x"}).status_code == 404
    assert client.post("/check-report", json={"id": prompt["id"], "text": "  "}).status_code == 400


def test_empty_database_gives_friendly_message(client):
    response = client.get("/snapshot", params={"symbol": "NQ"})

    assert response.status_code == 409
    assert "Henüz veri yok" in response.json()["detail"]
