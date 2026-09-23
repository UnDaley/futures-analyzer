"""Intermarket analizi: kontratın ilişkili varlıklarla uyumu.

Her ilişkili varlık için:
- change_1d / change_5d: önceki işlem günü kapanışına göre değişim (% veya faizlerde baz puan)
- direction: up / down / flat
- relationship: +1 (aynı yönde hareket beklenir) veya -1 (ters yönde)
- signal: bugün kontratın hareketini doğruluyor mu (confirms) yoksa ayrışıyor mu (diverges)
- correlation_20d: son 20 işlem günü günlük getirilerinin korelasyonu (ilişkinin gerçekten sürüp sürmediğini gösterir)

Ayrıca SMT uyumsuzluğu: eş varlıklardan biri önceki gün high'ını (veya low'unu) alıp diğeri
alamadıysa, hareket teyit edilmemiş demektir.

Günlük kapanışlar 1H mumlardan, CME işlem günlerine göre hesaplanır (günlük yfinance verisi
vade geçişi haftalarında farklı kontrata bakabildiği için).
"""

import math

import pandas as pd

from futures_analyzer.levels.reference import reference_levels
from futures_analyzer.market_time import trading_date

# Kontrat -> {ilişkili varlık: beklenen yön}. US02Y ve REAL_YIELD makro (FRED) verisinden gelir.
RELATIONSHIPS = {
    "NQ": {"ES": 1, "YM": 1, "RTY": 1, "DXY": -1, "US10Y": -1, "US02Y": -1, "VIX": -1},
    "ES": {"NQ": 1, "YM": 1, "RTY": 1, "DXY": -1, "US10Y": -1, "US02Y": -1, "VIX": -1},
    "GC": {"DXY": -1, "US10Y": -1, "REAL_YIELD": -1, "SI": 1},
}
SMT_PAIRS = {"NQ": "ES", "ES": "NQ", "GC": "SI"}
MACRO_ASSETS = {"US02Y": "us02y", "REAL_YIELD": "real_yield_10y"}
YIELD_ASSETS = {"US10Y", "US02Y", "REAL_YIELD"}

# Bu değerlerin altındaki hareketler "flat" sayılır
FLAT_PERCENT = 0.1
FLAT_PERCENT_VIX = 1.0
FLAT_BASIS_POINTS = 2.0
CORRELATION_DAYS = 20


def daily_closes(hourly: pd.DataFrame) -> pd.Series:
    """1H mumlardan işlem günü kapanışları. Son değer içinde bulunulan günün son fiyatıdır."""
    return hourly["close"].groupby(trading_date(hourly.index)).last()


def asset_state(symbol: str, closes: pd.Series) -> dict | None:
    if len(closes) < 2:
        return None
    is_yield = symbol in YIELD_ASSETS
    change_1d = _change(closes, 1, is_yield)
    change_5d = _change(closes, 5, is_yield) if len(closes) > 5 else None
    flat_limit = FLAT_BASIS_POINTS if is_yield else FLAT_PERCENT_VIX if symbol == "VIX" else FLAT_PERCENT
    return {
        "price": round(float(closes.iloc[-1]), 3),
        "date": closes.index[-1].date().isoformat(),
        "unit": "bp" if is_yield else "%",
        "change_1d": change_1d,
        "change_5d": change_5d,
        "direction": _direction(change_1d, flat_limit),
    }


def intermarket_snapshot(symbol: str, hourly_by_symbol: dict[str, pd.DataFrame], macro: dict[str, pd.Series]) -> dict | None:
    """hourly_by_symbol: sembol -> 1H mumlar (kontratın kendisi dahil). macro: makro seriler."""
    own = hourly_by_symbol.get(symbol)
    if own is None or own.empty or symbol not in RELATIONSHIPS:
        return None

    own_closes = daily_closes(own)
    own_state = asset_state(symbol, own_closes)
    if own_state is None:
        return None

    assets = {}
    for other, relationship in RELATIONSHIPS[symbol].items():
        closes = _closes_for(other, hourly_by_symbol, macro)
        state = asset_state(other, closes) if closes is not None else None
        if state is None:
            assets[other] = None
            continue
        assets[other] = {
            **state,
            "relationship": relationship,
            "signal": _signal(own_state["direction"], state["direction"], relationship),
            "correlation_20d": _correlation(own_closes, closes, other in YIELD_ASSETS),
        }

    signals = [a["signal"] for a in assets.values() if a is not None]
    return {
        "instrument": own_state,
        "assets": assets,
        "confirming": signals.count("confirms"),
        "diverging": signals.count("diverges"),
        "smt": _smt(symbol, hourly_by_symbol),
    }


def _closes_for(other: str, hourly_by_symbol: dict, macro: dict) -> pd.Series | None:
    if other in MACRO_ASSETS:
        series = macro.get(MACRO_ASSETS[other])
        return series if series is not None and len(series) else None
    hourly = hourly_by_symbol.get(other)
    return daily_closes(hourly) if hourly is not None and not hourly.empty else None


def _change(closes: pd.Series, days: int, is_yield: bool) -> float:
    now, before = float(closes.iloc[-1]), float(closes.iloc[-1 - days])
    if is_yield:
        return round((now - before) * 100, 1)  # yüzde puan -> baz puan
    return round((now / before - 1) * 100, 2)


def _direction(change: float, flat_limit: float) -> str:
    if abs(change) < flat_limit:
        return "flat"
    return "up" if change > 0 else "down"


def _signal(own_direction: str, other_direction: str, relationship: int) -> str:
    """Varlığın hareketi, beklenen ilişkiye göre kontratın hareketini destekliyor mu?"""
    if own_direction == "flat" or other_direction == "flat":
        return "neutral"
    other_sign = 1 if other_direction == "up" else -1
    own_sign = 1 if own_direction == "up" else -1
    return "confirms" if other_sign * relationship == own_sign else "diverges"


def _correlation(own: pd.Series, other: pd.Series, other_is_yield: bool) -> float | None:
    own_returns = own.pct_change()
    other_returns = other.diff() if other_is_yield else other.pct_change()
    other_returns.index = pd.DatetimeIndex(other_returns.index).normalize()
    joined = pd.concat([own_returns, other_returns], axis=1, join="inner").dropna().tail(CORRELATION_DAYS)
    if len(joined) < CORRELATION_DAYS // 2:
        return None
    value = joined.iloc[:, 0].corr(joined.iloc[:, 1])
    return None if math.isnan(value) else round(float(value), 2)


def _smt(symbol: str, hourly_by_symbol: dict) -> dict | None:
    partner = SMT_PAIRS.get(symbol)
    own, other = hourly_by_symbol.get(symbol), hourly_by_symbol.get(partner)
    if partner is None or own is None or other is None or own.empty or other.empty:
        return None

    taken = {}
    for name, hourly in ((symbol, own), (partner, other)):
        levels = reference_levels(hourly)
        if levels["pdh"] is None:
            return None
        taken[name] = {
            "pdh_taken": levels["session_high"] > levels["pdh"],
            "pdl_taken": levels["session_low"] < levels["pdl"],
        }

    divergence = None
    if taken[symbol]["pdh_taken"] != taken[partner]["pdh_taken"]:
        divergence = "bearish"  # biri yeni tepe yaptı, diğeri teyit etmedi
    elif taken[symbol]["pdl_taken"] != taken[partner]["pdl_taken"]:
        divergence = "bullish"  # biri yeni dip yaptı, diğeri teyit etmedi
    return {"partner": partner, "taken": taken, "divergence": divergence}
