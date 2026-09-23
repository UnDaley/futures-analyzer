"""Mum verisini analizden önce temizler."""

import logging

import pandas as pd

from futures_analyzer.data.providers.base import CANDLE_COLUMNS

logger = logging.getLogger(__name__)


def clean_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Standart biçimdeki mumları temizler ve yeni bir DataFrame döndürür.

    - Zaman damgalarını UTC'ye çevirir ve sıralar
    - Aynı zamana ait tekrar eden mumlardan sonuncusunu tutar
    - Fiyatı eksik olan mumları atar
    - Mantıksız mumları atar (örn. high < low)
    """
    if df.index.tz is None:
        raise ValueError("Zaman damgalarında saat dilimi yok; hangi saate ait oldukları belirsiz.")

    df = df[CANDLE_COLUMNS].copy()
    df.index = df.index.tz_convert("UTC")
    df.index.name = "ts"
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=["open", "high", "low", "close"])
    df["volume"] = df["volume"].fillna(0)

    body_high = df[["open", "close"]].max(axis=1)
    body_low = df[["open", "close"]].min(axis=1)
    bad = (df["high"] < body_high) | (df["low"] > body_low)
    if bad.any():
        logger.warning("%d mantıksız mum atıldı", int(bad.sum()))
    return df[~bad]
