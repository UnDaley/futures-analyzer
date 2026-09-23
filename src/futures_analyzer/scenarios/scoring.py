"""Analiz skoru: her bileşen -1 (bearish) ile +1 (bullish) arası bir değer alır, ağırlığıyla çarpılır.

Toplam -100 (tamamen bearish) ile +100 (tamamen bullish) arasıdır. Bu bir "başarı olasılığı" DEĞİLDİR;
kanıtların ne kadarının aynı yönü gösterdiğinin ölçüsüdür. Ağırlıklar başlangıç modelidir ve
backtest sonuçlarına göre değiştirilebilir (Faz 12).

Verisi olmayan bileşen 0 sayılır ve `available: false` olarak işaretlenir; `coverage` kaç puanlık
ağırlığın gerçekten hesaplanabildiğini gösterir.
"""

import pandas as pd

from futures_analyzer.market_time import drop_incomplete_last_bar

WEIGHTS = {
    "trend": 20,
    "structure": 20,
    "liquidity": 15,
    "volume": 10,
    "vwap": 10,
    "macro": 10,
    "intermarket": 10,
    "news": 5,
}
BIAS_THRESHOLD = 15  # |toplam| bundan küçükse nötr

DIRECTION = {"bullish": 1, "bearish": -1}


def score_snapshot(snapshot: dict, hourly: pd.DataFrame | None = None, now: pd.Timestamp | None = None) -> dict:
    components = {
        "trend": _trend(snapshot),
        "structure": _structure(snapshot),
        "liquidity": _liquidity(snapshot),
        "volume": _volume(hourly, now),
        "vwap": _vwap(snapshot),
        "macro": _macro(snapshot),
        "intermarket": _intermarket(snapshot),
        "news": _news(snapshot),
    }

    total = 0.0
    coverage = 0
    for name, component in components.items():
        component["weight"] = WEIGHTS[name]
        component["points"] = round(component["value"] * WEIGHTS[name], 1)
        total += component["points"]
        if component["available"]:
            coverage += WEIGHTS[name]

    total = round(total, 1)
    if total >= BIAS_THRESHOLD:
        bias = "bullish"
    elif total <= -BIAS_THRESHOLD:
        bias = "bearish"
    else:
        bias = "neutral"
    return {
        "total": total,
        "bias": bias,
        "strength": abs(total),
        "coverage": coverage,
        "components": components,
        "note": "Skor kanıtların yön uyumunu gösterir, olasılık değildir. Ağırlıklar başlangıç modelidir.",
    }


# --- Bileşenler: her biri {"value": -1..1, "available": bool, "reason": str} döndürür ---

def _component(value: float, available: bool, reason: str) -> dict:
    return {"value": round(max(-1.0, min(1.0, value)), 2), "available": available, "reason": reason}


def _weighted_directions(snapshot: dict, section: str, key: str, weights: dict[str, float]) -> tuple[float, list[str], bool]:
    value, parts, available = 0.0, [], False
    for timeframe, weight in weights.items():
        data = (snapshot["timeframes"].get(timeframe) or {}).get(section) or {}
        direction = data.get(key)
        if direction is None or direction == "unknown":
            continue
        available = True
        value += weight * DIRECTION.get(direction, 0)
        parts.append(f"{timeframe} {direction}")
    return value, parts, available


def _trend(snapshot: dict) -> dict:
    value, parts, available = _weighted_directions(snapshot, "technical", "ema_trend", {"1d": 0.4, "4h": 0.35, "1h": 0.25})
    return _component(value, available, "EMA trendi: " + ", ".join(parts) if parts else "EMA trendi hesaplanamadı")


def _structure(snapshot: dict) -> dict:
    value, parts, available = _weighted_directions(snapshot, "structure", "trend_by_breaks", {"4h": 0.5, "1h": 0.3, "15m": 0.2})
    return _component(value, available, "Son BOS/CHoCH yönü: " + ", ".join(parts) if parts else "Yapı kırılımı yok")


def _liquidity(snapshot: dict) -> dict:
    liquidity = snapshot.get("liquidity")
    if not liquidity:
        return _component(0, False, "Likidite verisi yok")

    value, reasons, available = 0.0, [], False
    zone = liquidity.get("premium_discount")
    if zone:
        available = True
        # Discount bölgesi alış için, premium bölgesi satış için daha elverişli kabul edilir
        value += 0.4 * -(zone["position_pct"] - 50) / 50
        reasons.append(f"fiyat 4H aralığının %{zone['position_pct']}'inde ({zone['zone']})")

    sweeps = []
    moves = []
    for timeframe in ("1h", "15m"):
        data = liquidity["timeframes"].get(timeframe) or {}
        sweeps += data.get("recent_sweeps", [])
        moves += data.get("recent_displacements", [])
    if sweeps:
        available = True
        last = max(sweeps, key=lambda s: s["sweep_ts"])
        # Sell-side likidite alındıysa (dipler süpürüldü) yukarı dönüş, buy-side alındıysa aşağı dönüş ihtimali
        value += 0.3 if last["side"] == "sell_side" else -0.3
        reasons.append(f"son sweep: {last['side']} {last['level']}")
    if moves:
        available = True
        last = max(moves, key=lambda m: m["ts"])
        value += 0.3 * DIRECTION[last["direction"]]
        reasons.append(f"son displacement: {last['direction']}")
    return _component(value, available, "; ".join(reasons) or "Likidite sinyali yok")


def _volume(hourly: pd.DataFrame | None, now: pd.Timestamp | None) -> dict:
    """Son 5 kapanmış 1H mumda hacmin ne kadarı yükselen, ne kadarı düşen mumlarda gerçekleşti."""
    if hourly is None or len(hourly) < 6:
        return _component(0, False, "Hacim verisi yok")
    recent = drop_incomplete_last_bar(hourly, "1h", now).tail(5)
    total_volume = recent["volume"].sum()
    if total_volume <= 0:
        return _component(0, False, "Son mumlarda hacim yok")
    signs = (recent["close"] - recent["open"]).apply(lambda body: 1 if body > 0 else -1 if body < 0 else 0)
    value = float((signs * recent["volume"]).sum() / total_volume)
    return _component(value, True, f"Son 5 saatlik mumda hacmin yön dengesi {value:+.2f}")


def _vwap(snapshot: dict) -> dict:
    technical = (snapshot["timeframes"].get("15m") or {}).get("technical") or {}
    above = technical.get("above_vwap")
    if above is None:
        return _component(0, False, "VWAP hesaplanamadı")
    return _component(1 if above else -1, True, f"Fiyat 15M'de seans VWAP'ının {'üstünde' if above else 'altında'}")


def _macro(snapshot: dict) -> dict:
    macro = snapshot.get("macro")
    if not macro:
        return _component(0, False, "Makro veri yok")
    # Hisse endeksleri için nominal 10Y faiz, altın için reel faiz; faiz artışı olumsuz kabul edilir
    key = "real_yield_10y" if snapshot["instrument"] == "GC" else "us10y"
    rate = macro.get(key)
    if not rate or rate.get("change_20d") is None:
        return _component(0, False, f"{key} değişimi hesaplanamadı")
    change_bp = rate["change_20d"] * 100
    return _component(-change_bp / 25, True, f"{key} son 20 günde {change_bp:+.0f} bp (faiz artışı olumsuz sayılır)")


def _intermarket(snapshot: dict) -> dict:
    intermarket = snapshot.get("intermarket")
    if not intermarket:
        return _component(0, False, "Intermarket verisi yok")
    signs = []
    for asset in intermarket["assets"].values():
        if asset is None:
            continue
        direction = {"up": 1, "down": -1, "flat": 0}[asset["direction"]]
        signs.append(asset["relationship"] * direction)
    if not signs:
        return _component(0, False, "İlişkili varlık verisi yok")
    value = sum(signs) / len(signs)
    reason = f"İlişkili varlıkların bugünkü hareketi kontratı {value:+.2f} yönünde destekliyor"
    smt = intermarket.get("smt") or {}
    if smt.get("divergence"):
        value += 0.5 * DIRECTION[smt["divergence"]]
        reason += f"; {smt['partner']} ile {smt['divergence']} SMT uyumsuzluğu"
    return _component(value, True, reason)


def _news(snapshot: dict) -> dict:
    news = snapshot.get("news") or {}
    impacts = [h["possible_impact"] for h in news.get("headlines", []) if h["hours_ago"] <= 24 and h["possible_impact"]]
    directional = [1 if i == "positive" else -1 for i in impacts if i in ("positive", "negative")]
    if not directional:
        return _component(0, bool(news), "Son 24 saatte yönlü haber sinyali yok")
    value = sum(directional) / len(directional)
    return _component(value, True, f"{len(directional)} yönlü başlık (anahtar kelime, düşük güven)")
