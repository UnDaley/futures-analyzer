"""Likidite havuzları ve sweep'ler.

- Buy-side liquidity (BSL): henüz aşılmamış swing high'lar. Üstlerinde stop emirleri birikir.
- Sell-side liquidity (SSL): henüz aşılmamış swing low'lar.
- Equal highs/lows: birbirine `tolerance` kadar yakın, aşılmamış iki veya daha fazla swing.
  Tek bir tepeden daha fazla likidite taşıdığı kabul edilir.
- Sweep: bir mumun iğnesi seviyeyi aşıp mum tekrar içeride kapanırsa (likidite alındı, devam edilmedi).
  Mum seviyenin ötesinde kapanırsa bu sweep değil kırılımdır.
"""

import numpy as np
import pandas as pd

from futures_analyzer.structure.swings import HIGH


def liquidity_pools(df: pd.DataFrame, swings: pd.DataFrame, tolerance: float, limit: int = 5) -> dict:
    highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
    unswept_highs, unswept_lows = [], []

    for swing in swings.to_dict("records"):
        after = slice(swing["bar_index"] + 1, None)
        if swing["kind"] == HIGH:
            if not (highs[after] > swing["price"]).any():
                unswept_highs.append(swing)
        elif not (lows[after] < swing["price"]).any():
            unswept_lows.append(swing)

    buy_side = _group(unswept_highs, tolerance, pick=max)
    sell_side = _group(unswept_lows, tolerance, pick=min)
    return {
        # Aşılmamış tepeler zorunlu olarak fiyatın üstünde, dipler altındadır; en yakından uzağa
        "buy_side": sorted(buy_side, key=lambda pool: pool["level"])[:limit],
        "sell_side": sorted(sell_side, key=lambda pool: -pool["level"])[:limit],
    }


def _group(swings: list[dict], tolerance: float, pick) -> list[dict]:
    """Birbirine yakın swing'leri tek havuzda toplar (zone birleştirmeyle aynı mantık)."""
    groups: list[list[dict]] = []
    for swing in sorted(swings, key=lambda s: s["price"]):
        if groups and swing["price"] - groups[-1][0]["price"] <= tolerance:
            groups[-1].append(swing)
        else:
            groups.append([swing])

    return [
        {
            "level": pick(s["price"] for s in group),
            "count": len(group),
            "equal": len(group) >= 2,
            "last_swing_ts": max(s["ts"] for s in group).isoformat(),
        }
        for group in groups
    ]


def find_sweeps(df: pd.DataFrame, swings: pd.DataFrame, lookback: int = 20) -> list[dict]:
    """Son `lookback` mumda olan sweep'ler (eskiden yeniye).

    Her swing için seviyeyi ilk aşan mum bulunur; o mum içeride kapandıysa sweep'tir.
    """
    highs, lows, closes = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    first_recent = len(df) - lookback
    sweeps = []

    for swing in swings.to_dict("records"):
        start = swing["bar_index"] + 1
        level = swing["price"]
        if swing["kind"] == HIGH:
            crossed = np.flatnonzero(highs[start:] > level)
        else:
            crossed = np.flatnonzero(lows[start:] < level)
        if len(crossed) == 0:
            continue

        bar = start + crossed[0]
        closed_back_inside = closes[bar] < level if swing["kind"] == HIGH else closes[bar] > level
        if closed_back_inside and bar >= first_recent:
            sweeps.append({
                "side": "buy_side" if swing["kind"] == HIGH else "sell_side",
                "level": level,
                "sweep_ts": df.index[bar].isoformat(),
                "swing_ts": swing["ts"].isoformat(),
            })

    return sorted(sweeps, key=lambda sweep: sweep["sweep_ts"])
