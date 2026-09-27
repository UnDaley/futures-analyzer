"""Ekonomik takvim motoru: takvimi çekip kaydeder, bugünkü verileri ve olay riskini özetler.

10:00'da açıklanan veriler (ISM, JOLTS, tüketici güveni...) 10am modelinin manipülasyon hareketini
doğrudan etkileyebildiği için 10:00'a yakın olaylar ayrıca işaretlenir.
"""

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.data.storage import load_events, save_events
from futures_analyzer.market_time import NEW_YORK
from futures_analyzer.news.calendar import calendar_snapshot, explain, fetch_calendar, normalize_events

NEAR_OPEN_MINUTES = 30  # 10:00'a bu kadar yakın olaylar "açılışa yakın" sayılır


def ingest_news(engine: Engine, calendar=fetch_calendar) -> dict[str, int]:
    """Takvimi çekip kaydeder."""
    return {"events": save_events(engine, normalize_events(calendar()))}


def events_snapshot(engine: Engine, now: pd.Timestamp | None = None) -> dict:
    now = now or pd.Timestamp.now(tz="UTC")
    events = load_events(engine)
    return {**calendar_snapshot(events, now), "today": today_events(events, now)}


def today_events(events: list[dict], now: pd.Timestamp) -> list[dict]:
    """Bugünün (New York tarihi) olayları; 10:00'a yakın olanlar `near_open: true`."""
    today = now.tz_convert(NEW_YORK).date()
    ten_am = pd.Timestamp.combine(today, pd.Timestamp("10:00").time()).tz_localize(NEW_YORK)
    result = []
    for event in events:
        local = event["ts"].tz_convert(NEW_YORK)
        if local.date() != today:
            continue
        result.append({
            "title": event["title"],
            "impact": event["impact"],
            "time_ny": local.strftime("%H:%M"),
            "released": bool(event["ts"] <= now),
            "near_open": abs((local - ten_am).total_seconds()) <= NEAR_OPEN_MINUTES * 60,
            "forecast": event["forecast"],
            "previous": event["previous"],
            "why_it_matters": explain(event["title"]),
        })
    return result
