"""Desteklenen futures kontratlarının tanımları.

Yeni bir kontrat eklemek için INSTRUMENTS sözlüğüne bir satır eklemek yeterli.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str        # Sistemin içinde kullandığımız kısa ad, örn. "NQ"
    name: str          # Okunabilir ad
    yahoo_ticker: str  # yfinance'teki sembol (en yakın vadeli sürekli kontrat)
    tick_size: float   # Fiyatın en küçük adımı
    round_step: float  # Psikolojik "yuvarlak" fiyat adımı (örn. NQ için 31.000, 31.100)
    ny_open: str = "09:30"  # New York açılış saati (NY saati). Hisse endeksleri 09:30, altın (COMEX) 08:20


INSTRUMENTS = {
    "NQ": Instrument("NQ", "E-mini Nasdaq-100", "NQ=F", 0.25, 100),
    "ES": Instrument("ES", "E-mini S&P 500", "ES=F", 0.25, 25),
    "GC": Instrument("GC", "Gold", "GC=F", 0.10, 25, ny_open="08:20"),
}


# Intermarket analizi için izlenen yardımcı varlıklar. Bunlar için analiz raporu üretilmez.
# Not: 2 yıllık faiz ve reel faiz yfinance'te güvenilir değil; onlar FRED'den (makro) alınır.
INTERMARKET_ASSETS = {
    "YM": Instrument("YM", "E-mini Dow", "YM=F", 1.0, 100),
    "RTY": Instrument("RTY", "E-mini Russell 2000", "RTY=F", 0.1, 10),
    "DXY": Instrument("DXY", "ABD Dolar Endeksi", "DX-Y.NYB", 0.001, 1),
    "US10Y": Instrument("US10Y", "ABD 10 yıllık faiz (%)", "^TNX", 0.001, 0.1),
    "VIX": Instrument("VIX", "CBOE Volatilite Endeksi", "^VIX", 0.01, 1),
    "SI": Instrument("SI", "Gümüş", "SI=F", 0.005, 1),
}


def get_instrument(symbol: str) -> Instrument:
    """Sembolden Instrument döndürür. Bilinmeyen sembolde anlaşılır bir hata verir."""
    key = symbol.upper()
    if key not in INSTRUMENTS:
        known = ", ".join(INSTRUMENTS)
        raise ValueError(f"Bilinmeyen sembol: {symbol}. Desteklenenler: {known}")
    return INSTRUMENTS[key]
