import pandas as pd

from futures_analyzer.news.calendar import calendar_snapshot, explain, normalize_events
from futures_analyzer.news.engine import ingest_news, news_snapshot
from futures_analyzer.news.feeds import parse_rss
from futures_analyzer.news.impact import analyze_headline

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Federal Reserve issues FOMC statement</title>
        <link>https://www.federalreserve.gov/a.htm</link>
        <pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate></item>
  <item><title>Zamanı olmayan haber</title><link>https://x</link></item>
</channel></rss>"""


def test_parse_rss():
    items = parse_rss(RSS, "Fed")

    assert len(items) == 1  # zamanı olmayan atlandı
    assert items[0]["title"] == "Federal Reserve issues FOMC statement"
    assert items[0]["ts"] == pd.Timestamp("2026-09-16 18:00", tz="UTC")
    assert items[0]["source"] == "Fed"


def test_headline_rules():
    assert analyze_headline("Fed signals rate hike ahead")["assets"]["NQ"] == "negative"
    assert analyze_headline("Fed signals rate hike ahead")["assets"]["DXY"] == "positive"
    assert analyze_headline("Fed delivers rate cut")["assets"]["GC"] == "positive"
    assert analyze_headline("New tariffs announced")["assets"]["GC"] == "positive"
    assert analyze_headline("Federal Reserve issues FOMC statement")["assets"]["NQ"] == "unclear"  # ilgili, yön belirsiz


def test_conflicting_rules_are_unclear():
    # "rate cut" (dovish: NQ +) ve "tariffs" (risk-off: NQ -) birlikte
    result = analyze_headline("Rate cut expected despite new tariffs")

    assert result["assets"]["NQ"] == "unclear"
    assert result["confidence"] == "low"


def test_keywords_match_whole_words_only():
    assert analyze_headline("A shortcut to warmer weather")["assets"] == {}  # "cut", "war" geçmiyor


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
    feeds = lambda: parse_rss(RSS, "Fed")  # noqa: E731
    calendar = lambda: [raw_event("CPI m/m", "2026-09-17T08:30:00-04:00")]  # noqa: E731

    assert ingest_news(engine, feeds=feeds, calendar=calendar) == {"news": 1, "events": 1}

    now = pd.Timestamp("2026-09-17 12:00", tz="UTC")
    result = news_snapshot(engine, "NQ", now=now)

    assert result["headlines"][0]["title"] == "Federal Reserve issues FOMC statement"
    assert result["headlines"][0]["hours_ago"] == 18.0
    assert result["headlines"][0]["possible_impact"] == "unclear"
    assert result["calendar"]["event_risk"]["minutes_until"] == 30
    assert result["calendar"]["event_risk"]["imminent"] is True


def test_snapshot_ignores_future_and_old_news(engine):
    ingest_news(engine, feeds=lambda: parse_rss(RSS, "Fed"), calendar=lambda: [])

    assert news_snapshot(engine, "NQ", now=pd.Timestamp("2026-09-16 12:00", tz="UTC"))["headlines"] == []  # henüz yayınlanmadı
    assert news_snapshot(engine, "NQ", now=pd.Timestamp("2026-09-20 12:00", tz="UTC"))["headlines"] == []  # 48 saatten eski
