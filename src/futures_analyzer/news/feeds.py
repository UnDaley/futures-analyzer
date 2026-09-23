"""Güvenilir haber kaynaklarından (RSS) başlıkları alır.

Şimdilik resmi kaynaklar: Fed basın açıklamaları, Fed konuşmaları, BEA (GSYH, PCE vb.).
Not: BLS ve CNBC gibi bazı kaynaklar otomatik erişimi engelliyor (HTTP 403).
Yeni bir RSS kaynağı eklemek için FEEDS sözlüğüne bir satır eklemek yeterli.
"""

import hashlib
import logging
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd

from futures_analyzer.http import get_text

logger = logging.getLogger(__name__)

FEEDS = {
    "Federal Reserve (basın)": "https://www.federalreserve.gov/feeds/press_all.xml",
    "Federal Reserve (konuşma)": "https://www.federalreserve.gov/feeds/speeches.xml",
    "BEA": "https://apps.bea.gov/rss/rss.xml",
}


def fetch_feeds() -> list[dict]:
    items = []
    for source, url in FEEDS.items():
        try:
            items.extend(parse_rss(get_text(url), source))
        except (urllib.error.URLError, ET.ParseError, TimeoutError) as error:
            logger.info("Haber kaynağı alınamadı (%s): %s", source, error)
    return items


def parse_rss(text: str, source: str) -> list[dict]:
    """RSS 2.0 metnini haber listesine çevirir. Zamanı olmayan haberler atlanır."""
    items = []
    for item in ET.fromstring(text).iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate")
        if not title or not published:
            continue
        items.append({
            "id": hashlib.sha1((link or title).encode()).hexdigest()[:16],
            "ts": pd.Timestamp(parsedate_to_datetime(published)).tz_convert("UTC"),
            "source": source,
            "title": title,
            "link": link,
        })
    return items
