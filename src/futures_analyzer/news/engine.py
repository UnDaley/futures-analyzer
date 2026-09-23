"""Haber ve ekonomik takvim motoru: veriyi çekip kaydeder, kontrat için özet üretir."""

import logging

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.data.storage import load_events, load_news, save_events, save_news
from futures_analyzer.news.calendar import calendar_snapshot, fetch_calendar, normalize_events
from futures_analyzer.news.feeds import fetch_feeds
from futures_analyzer.news.impact import analyze_headline

logger = logging.getLogger(__name__)

NEWS_HOURS = 48
NEWS_LIMIT = 8


def ingest_news(engine: Engine, feeds=fetch_feeds, calendar=fetch_calendar) -> dict[str, int]:
    """Haberleri ve takvimi çekip kaydeder. Her habere etki analizi eklenir."""
    items = [{**item, "analysis": analyze_headline(item["title"])} for item in feeds()]
    events = normalize_events(calendar())
    return {"news": save_news(engine, items), "events": save_events(engine, events)}


def news_snapshot(engine: Engine, symbol: str, now: pd.Timestamp | None = None) -> dict:
    now = now or pd.Timestamp.now(tz="UTC")
    items = [item for item in load_news(engine, since=now - pd.Timedelta(hours=NEWS_HOURS)) if item["ts"] <= now]

    headlines = []
    for item in items[:NEWS_LIMIT]:
        analysis = item["analysis"] or {}
        headlines.append({
            "time_utc": item["ts"].isoformat(),
            "hours_ago": round((now - item["ts"]).total_seconds() / 3600, 1),
            "source": item["source"],
            "title": item["title"],
            "link": item["link"],
            # Bu kontrat için olası etki (kurallar eşleşmediyse None)
            "possible_impact": analysis.get("assets", {}).get(symbol),
            "all_assets": analysis.get("assets", {}),
            "confidence": analysis.get("confidence", "low"),
        })

    return {
        "calendar": calendar_snapshot(load_events(engine), now),
        "headlines": headlines,
        "note": "Haber etkileri başlıktaki anahtar kelimelere dayalı kaba tahminlerdir (düşük güven). "
                "Kaynaklar şimdilik sadece resmi kurumlar (Fed, BEA); genel piyasa haberleri kapsanmıyor.",
    }
