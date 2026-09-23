"""FRED (St. Louis Fed) makro verileri. API anahtarı gerektirmeyen CSV servisini kullanır.

Günlük seriler (faizler) genelde 1 iş günü gecikmeli, aylık seriler (CPI, NFP...)
yayınlandıkları tarihte güncellenir. Her değerin tarihi snapshot'ta ayrıca verilir.
"""

import io

import pandas as pd

from futures_analyzer.http import get_text

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"

# Snapshot'taki ad -> (FRED seri kodu, açıklama)
SERIES = {
    "fed_funds": ("DFF", "Efektif Fed faizi (%)"),
    "fed_target_upper": ("DFEDTARU", "Fed faiz hedef aralığı üst sınırı (%)"),
    "us10y": ("DGS10", "10 yıllık ABD tahvil faizi (%)"),
    "us02y": ("DGS2", "2 yıllık ABD tahvil faizi (%)"),
    "yield_curve_10y2y": ("T10Y2Y", "10 yıllık - 2 yıllık faiz farkı (puan)"),
    "real_yield_10y": ("DFII10", "10 yıllık reel faiz, TIPS (%)"),
    "cpi": ("CPIAUCSL", "TÜFE endeksi"),
    "core_cpi": ("CPILFESL", "Çekirdek TÜFE endeksi"),
    "ppi": ("PPIFIS", "ÜFE (nihai talep) endeksi"),
    "pce": ("PCEPI", "PCE fiyat endeksi"),
    "core_pce": ("PCEPILFE", "Çekirdek PCE fiyat endeksi"),
    "nonfarm_payrolls": ("PAYEMS", "Tarım dışı istihdam (bin kişi)"),
    "unemployment": ("UNRATE", "İşsizlik oranı (%)"),
    "gdp_growth": ("A191RL1Q225SBEA", "Reel GSYH büyümesi, yıllıklandırılmış (%)"),
}


def fetch_fred_series(series_id: str, start: str = "2018-01-01") -> pd.Series:
    url = FRED_CSV_URL.format(series_id=series_id, start=start)
    return parse_fred_csv(get_text(url))


def parse_fred_csv(text: str) -> pd.Series:
    """FRED CSV'sini tarih index'li bir Series'e çevirir. Boş veya "." değerler atılır."""
    df = pd.read_csv(io.StringIO(text))
    dates = pd.to_datetime(df.iloc[:, 0])
    values = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    series = pd.Series(values.to_numpy(), index=dates, name=df.columns[1]).dropna()
    series.index.name = "date"
    return series
