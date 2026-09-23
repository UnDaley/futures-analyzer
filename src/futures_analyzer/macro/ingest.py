"""Makro serileri FRED'den çekip kaydeder ve veritabanından okur."""

import logging

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.data.storage import load_macro_series, save_macro_series
from futures_analyzer.macro.fred import SERIES, fetch_fred_series

logger = logging.getLogger(__name__)


def ingest_macro(engine: Engine, fetch=fetch_fred_series) -> dict[str, int]:
    """Bütün serileri çeker. Bir seri hata verirse diğerlerine devam eder.

    Dönüş: {snapshot adı: kaydedilen satır sayısı} (hata verenler -1)
    """
    saved = {}
    for name, (series_id, _) in SERIES.items():
        try:
            saved[name] = save_macro_series(engine, series_id, fetch(series_id))
        except Exception as error:  # ağ hatası vb.: o seriyi atla, raporla
            logger.warning("%s (%s) alınamadı: %s", name, series_id, error)
            saved[name] = -1
    return saved


def load_macro(engine: Engine) -> dict[str, pd.Series]:
    return {name: load_macro_series(engine, series_id) for name, (series_id, _) in SERIES.items()}
