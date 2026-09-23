"""Makro özet: her serinin son değeri, tarihi ve değişimi.

- Faizler (günlük): son değer, 1 günlük ve ~1 aylık (20 iş günü) değişim
- Fiyat endeksleri (CPI, PPI, PCE): yıllık değişim % (YoY) ve bir önceki ayın YoY'u
- İstihdam (NFP): aylık değişim (bin kişi)
- Oranlar (işsizlik, GSYH büyümesi): son değer ve bir önceki değer

Veride olmayan seri None olur; hiçbir değer tahmin edilmez.
"""

import pandas as pd

from futures_analyzer.macro.fred import SERIES

DAILY_RATES = ["fed_funds", "fed_target_upper", "us10y", "us02y", "yield_curve_10y2y", "real_yield_10y"]
PRICE_INDEXES = ["cpi", "core_cpi", "ppi", "pce", "core_pce"]
LEVELS = ["unemployment", "gdp_growth"]


def macro_snapshot(series: dict[str, pd.Series]) -> dict | None:
    """series: snapshot adı -> tarih index'li değerler (bkz. fred.SERIES)."""
    if not any(len(s) for s in series.values()):
        return None

    result = {}
    for name in DAILY_RATES:
        result[name] = _rate(series.get(name))
    for name in PRICE_INDEXES:
        result[f"{name}_yoy"] = _yoy(series.get(name))
    result["nfp_change"] = _monthly_change(series.get("nonfarm_payrolls"))
    for name in LEVELS:
        result[name] = _level(series.get(name))
    result["descriptions"] = {name: description for name, (_, description) in SERIES.items()}
    return result


def _rate(s: pd.Series | None) -> dict | None:
    if s is None or s.empty:
        return None
    return {
        "value": _round(s.iloc[-1]),
        "date": s.index[-1].date().isoformat(),
        "change_1d": _round(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else None,
        "change_20d": _round(s.iloc[-1] - s.iloc[-21]) if len(s) >= 21 else None,
    }


def _yoy(s: pd.Series | None) -> dict | None:
    """Aylık endeksin yıllık % değişimi. 13 aydan az veri varsa None."""
    if s is None or len(s) < 13:
        return None
    yoy = (s / s.shift(12) - 1) * 100
    latest, previous = yoy.iloc[-1], yoy.iloc[-2]
    return {
        "value": _round(latest),
        "previous": _round(previous) if pd.notna(previous) else None,
        "trend": _trend(latest, previous),
        "date": s.index[-1].date().isoformat(),
    }


def _monthly_change(s: pd.Series | None) -> dict | None:
    if s is None or len(s) < 3:
        return None
    change = s.diff()
    return {
        "value": _round(change.iloc[-1]),
        "previous": _round(change.iloc[-2]),
        "date": s.index[-1].date().isoformat(),
    }


def _level(s: pd.Series | None) -> dict | None:
    if s is None or s.empty:
        return None
    previous = s.iloc[-2] if len(s) >= 2 else None
    return {
        "value": _round(s.iloc[-1]),
        "previous": _round(previous) if previous is not None else None,
        "trend": _trend(s.iloc[-1], previous) if previous is not None else None,
        "date": s.index[-1].date().isoformat(),
    }


def _trend(latest: float, previous: float | None) -> str | None:
    if previous is None or pd.isna(previous):
        return None
    if abs(latest - previous) < 0.05:
        return "flat"
    return "rising" if latest > previous else "falling"


def _round(value) -> float:
    return round(float(value), 3)
