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


INSTRUMENTS = {
    "NQ": Instrument("NQ", "E-mini Nasdaq-100", "NQ=F", 0.25),
    "ES": Instrument("ES", "E-mini S&P 500", "ES=F", 0.25),
    "GC": Instrument("GC", "Gold", "GC=F", 0.10),
}


def get_instrument(symbol: str) -> Instrument:
    """Sembolden Instrument döndürür. Bilinmeyen sembolde anlaşılır bir hata verir."""
    key = symbol.upper()
    if key not in INSTRUMENTS:
        known = ", ".join(INSTRUMENTS)
        raise ValueError(f"Bilinmeyen sembol: {symbol}. Desteklenenler: {known}")
    return INSTRUMENTS[key]
