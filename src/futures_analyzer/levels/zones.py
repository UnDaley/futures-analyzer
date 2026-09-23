"""Seviyeleri zone'lara (fiyat bölgelerine) birleştirir.

Birbirine çok yakın seviyeler (örn. PDH 30.980 ve 4H swing high 30.985) aslında aynı bölgedir.
Seviyeleri fiyata göre sıralayıp soldan sağa gideriz: bir seviye, açık zone'un en alt
noktasından `tolerance` kadar uzaktaysa aynı zone'a girer, değilse yeni zone başlar.
Böylece bir zone'un genişliği hiçbir zaman `tolerance`'ı geçmez.
"""


def build_zones(levels: list[dict], tolerance: float) -> list[dict]:
    """levels: [{"price": 30980.0, "source": "PDH"}, ...]

    Dönüş: [{"low", "high", "sources", "strength"}, ...] fiyata göre artan sırada.
    strength = zone'da birleşen seviye sayısı.
    """
    zones: list[dict] = []
    for level in sorted(levels, key=lambda item: item["price"]):
        price = level["price"]
        if zones and price - zones[-1]["low"] <= tolerance:
            zone = zones[-1]
            zone["high"] = price
            if level["source"] not in zone["sources"]:
                zone["sources"].append(level["source"])
        else:
            zones.append({"low": price, "high": price, "sources": [level["source"]]})

    for zone in zones:
        zone["strength"] = len(zone["sources"])
    return zones


def split_by_price(zones: list[dict], price: float, limit: int = 5) -> dict:
    """Zone'ları fiyatın üstü (direnç), altı (destek) ve fiyatın içinde olduğu diye ayırır.

    Dirençler ve destekler fiyata en yakından uzağa sıralanır. distance = fiyat ile zone'un
    en yakın kenarı arasındaki puan farkı.
    """
    resistance = [dict(z, distance=round(z["low"] - price, 2)) for z in zones if z["low"] > price]
    support = [dict(z, distance=round(price - z["high"], 2)) for z in zones if z["high"] < price]
    at_price = [dict(z, distance=0.0) for z in zones if z["low"] <= price <= z["high"]]

    return {
        "resistance": resistance[:limit],
        "support": list(reversed(support))[:limit],
        "at_price": at_price,
    }
