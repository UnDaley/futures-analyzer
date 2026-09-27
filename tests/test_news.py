import pandas as pd

from futures_analyzer.news.calendar import calendar_snapshot, explain, normalize_events
from futures_analyzer.news.engine import events_snapshot, ingest_news


def raw_event(title, date, impact="High", country="USD"):
    return {"title": title, "country": country, "date": date, "impact": impact, "forecast": "0.3%", "previous": "0.2%"}


def test_normalize_events_filters_and_converts():
    events = normalize_events([
        raw_event("CPI m/m", "2026-09-24T08:30:00-04:00"),
        raw_event("CPI m/m", "2026-09-24T08:30:00-04:00"),              # tekrar
        raw_event("German CPI", "2026-09-24T02:00:00-04:00", country="EUR"),
        raw_event("Crude Oil Inventories", "2026-09-24T10:30:00-04:00", impact="Low"),
    ])

    assert [(e["title"], e["ts"]) for e in events] == [("CPI m/m", pd.Timestamp("2026-09-24 12:30", tz="UTC"))]


def test_event_risk():
    events = normalize_events([
        raw_event("Unemployment Claims", "2026-09-24T08:30:00-04:00", impact="Medium"),
        raw_event("CPI m/m", "2026-09-24T10:00:00-04:00"),
        raw_event("PPI m/m", "2026-09-24T07:40:00-04:00"),  # 20 dk önce açıklandı
    ])
    now = pd.Timestamp("2026-09-24 08:00", tz="America/New_York").tz_convert("UTC")

    result = calendar_snapshot(events, now)

    risk = result["event_risk"]
    assert risk["title"] == "CPI m/m"                  # en yakın YÜKSEK etkili olay
    assert risk["minutes_until"] == 120
    assert risk["imminent"] is False
    assert "Enflasyon" in risk["why_it_matters"]
    assert [e["title"] for e in result["just_released"]] == ["PPI m/m"]
    assert [e["title"] for e in result["upcoming"]] == ["Unemployment Claims", "CPI m/m"]


def test_no_events():
    assert calendar_snapshot([], pd.Timestamp("2026-09-24", tz="UTC"))["event_risk"] is None


def test_explain():
    assert "NFP" in explain("Non-Farm Employment Change")
    assert "FOMC" in explain("FOMC Statement")
    assert "oynaklık" in explain("Some Unknown Release")


def test_ingest_and_snapshot(engine):
    events = [
        raw_event("CPI m/m", "2026-09-17T08:30:00-04:00"),
        raw_event("ISM Services PMI", "2026-09-17T10:00:00-04:00", impact="Medium"),
        raw_event("Retail Sales m/m", "2026-09-18T08:30:00-04:00"),
    ]

    assert ingest_news(engine, calendar=lambda: events) == {"events": 3}

    result = events_snapshot(engine, now=pd.Timestamp("2026-09-17 12:00", tz="UTC"))  # NY 08:00

    assert result["event_risk"]["title"] == "CPI m/m"
    assert result["event_risk"]["imminent"] is True
    today = {event["title"]: event for event in result["today"]}
    assert set(today) == {"CPI m/m", "ISM Services PMI"}  # yarınki olay bugünün listesinde yok
    assert today["ISM Services PMI"]["near_open"] is True  # 10:00'da açıklanıyor
    assert today["CPI m/m"]["near_open"] is False
    assert today["CPI m/m"]["released"] is False
