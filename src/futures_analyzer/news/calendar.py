"""Ekonomik takvim: yaklaşan yüksek etkili ABD verileri ve olay riski.

Kaynak: faireconomy.media haftalık JSON (Forex Factory takvimi; resmi değildir, anahtar gerektirmez).
Kaynak saatte bir güncellenir ve sık istekleri geçici olarak reddeder (HTTP 429); o durumda
veritabanındaki son başarılı takvim kullanılmaya devam eder.
İsteğe bağlı olarak proje klasöründeki `calendar_manual.json` dosyasına aynı biçimde elle olay
eklenebilir (örn. önemli bir Powell konuşması).

Olay biçimi: {"title", "country", "date" (saat dilimli ISO), "impact" (High/Medium/Low), "forecast", "previous"}
"""

import json
import logging
import urllib.error
from pathlib import Path

import pandas as pd

from futures_analyzer.http import get_text

logger = logging.getLogger(__name__)

CALENDAR_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",  # hafta sonuna doğru yayınlanır
]
MANUAL_CALENDAR = Path("calendar_manual.json")
TRACKED_IMPACTS = {"High", "Medium"}
IMMINENT_MINUTES = 60      # bu kadar dakika içindeyse "yakın olay riski"
RECENT_MINUTES = 30        # yeni açıklandıysa oynaklık sürebilir

# Olay adında geçen anahtar kelime -> neden önemli (Türkçe açıklama)
EVENT_EXPLANATIONS = [
    (("cpi",), "Enflasyon (TÜFE) verisi. Beklentiden yüksek gelirse faiz indirimi beklentileri azalabilir; "
               "tahvil faizleri ve dolar yükselip NQ/ES ve altın üzerinde baskı oluşturabilir. Düşük gelirse tersi."),
    (("ppi",), "Üretici fiyatları. TÜFE'nin öncü göstergesi sayılır; enflasyon beklentilerini ve faiz fiyatlamasını etkileyebilir."),
    (("pce",), "Fed'in tercih ettiği enflasyon ölçüsü. Faiz beklentilerini doğrudan etkileyebilir."),
    (("non-farm", "nonfarm"), "Tarım dışı istihdam (NFP). Güçlü gelirse faizler ve dolar yükselebilir; zayıf gelirse büyüme endişesi "
                              "ve faiz indirimi beklentisi artabilir. Açıklama anında çok sert hareketler olabilir."),
    (("unemployment rate",), "İşsizlik oranı. İşgücü piyasasının gücünü ve Fed'in faiz yolunu etkileyebilir."),
    (("unemployment claims", "jobless claims"), "Haftalık işsizlik başvuruları. İşgücü piyasasındaki ani değişimleri gösterebilir."),
    (("fomc", "federal funds rate", "fed interest rate"), "Fed faiz kararı / FOMC. Faiz, dolar, hisse endeksleri ve altında en yüksek "
                                                          "oynaklığa yol açabilen olaydır; açıklama ve basın toplantısı sırasında yön birkaç kez değişebilir."),
    (("powell", "fed chair"), "Fed Başkanı konuşması. Faiz yolu hakkında ipucu verirse faizler, dolar ve endekslerde sert hareket olabilir."),
    (("gdp",), "Büyüme (GSYH) verisi. Ekonominin gücüne dair beklentileri ve risk iştahını etkileyebilir."),
    (("retail sales",), "Perakende satışlar. Tüketici talebinin gücünü gösterir; büyüme ve enflasyon beklentilerini etkileyebilir."),
    (("ism",), "ISM endeksi. İmalat / hizmet sektörünün yönünü gösteren öncü göstergedir."),
]
DEFAULT_EXPLANATION = "Etkisi yüksek/orta olarak işaretlenmiş veri; açıklama anında oynaklık artabilir."


def fetch_calendar() -> list[dict]:
    """İnternetteki takvimleri ve varsa elle eklenen olayları birleştirir."""
    events = []
    for url in CALENDAR_URLS:
        try:
            events.extend(json.loads(get_text(url)))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as error:
            logger.info("Takvim alınamadı (%s): %s", url, error)
    if MANUAL_CALENDAR.exists():
        events.extend(json.loads(MANUAL_CALENDAR.read_text(encoding="utf-8")))
    return events


def normalize_events(raw_events: list[dict]) -> list[dict]:
    """Sadece ABD'nin yüksek/orta etkili olaylarını alır, zamanı UTC'ye çevirir, tekrarları atar."""
    seen = set()
    events = []
    for raw in raw_events:
        if raw.get("country") != "USD" or raw.get("impact") not in TRACKED_IMPACTS:
            continue
        ts = pd.Timestamp(raw["date"]).tz_convert("UTC")
        key = (raw["title"], ts)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "title": raw["title"],
            "ts": ts,
            "impact": raw["impact"].lower(),
            "forecast": raw.get("forecast") or None,
            "previous": raw.get("previous") or None,
        })
    return sorted(events, key=lambda event: event["ts"])


def explain(title: str) -> str:
    lower = title.lower()
    for keywords, explanation in EVENT_EXPLANATIONS:
        if any(keyword in lower for keyword in keywords):
            return explanation
    return DEFAULT_EXPLANATION


def calendar_snapshot(events: list[dict], now: pd.Timestamp, days_ahead: int = 7, limit: int = 10) -> dict:
    """events: normalize_events çıktısı (veya veritabanından okunan aynı biçim)."""
    horizon = now + pd.Timedelta(days=days_ahead)
    upcoming = [e for e in events if now <= e["ts"] <= horizon]
    recent = [e for e in events if now - pd.Timedelta(minutes=RECENT_MINUTES) <= e["ts"] < now]

    # Olay riski: en yakın yüksek etkili olay (yoksa orta etkili)
    next_event = next((e for e in upcoming if e["impact"] == "high"), None) or (upcoming[0] if upcoming else None)
    event_risk = None
    if next_event is not None:
        minutes = int((next_event["ts"] - now).total_seconds() // 60)
        event_risk = {
            **_event_dict(next_event, now),
            "imminent": minutes <= IMMINENT_MINUTES,
            "why_it_matters": explain(next_event["title"]),
        }

    return {
        "event_risk": event_risk,
        "just_released": [
            {**_event_dict(e, now), "why_it_matters": explain(e["title"])} for e in recent
        ],
        "upcoming": [_event_dict(e, now) for e in upcoming[:limit]],
    }


def _event_dict(event: dict, now: pd.Timestamp) -> dict:
    return {
        "title": event["title"],
        "impact": event["impact"],
        "time_utc": event["ts"].isoformat(),
        "time_ny": event["ts"].tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M"),
        "minutes_until": int((event["ts"] - now).total_seconds() // 60),
        "forecast": event["forecast"],
        "previous": event["previous"],
    }
