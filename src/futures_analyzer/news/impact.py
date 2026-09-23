"""Haber başlığından olası piyasa etkisi (anahtar kelime kuralları).

Bu bir TAHMİN değil, kaba bir sınıflandırmadır:
- Sadece başlığa bakar, haberin detayını ve piyasanın beklentisini bilmez.
- Aynı haber beklentiye göre ters etki yapabilir (örn. "beklenen" faiz artışı).
Bu yüzden her sonuç "confidence": "low" ile işaretlenir; yorum Claude'a ve kullanıcıya kalır.
"""

import re

POSITIVE, NEGATIVE, NEUTRAL, UNCLEAR = "positive", "negative", "neutral", "unclear"

# (kural adı, anahtar kelimeler (kelime sınırıyla), varlık -> +1 / -1 / 0)
RULES = [
    ("hawkish", ["rate hike", "raises rates", "raise rates", "tighten", "tightening", "hawkish", "higher for longer"],
     {"NQ": -1, "ES": -1, "GC": -1, "DXY": 1, "US10Y": 1}),
    ("dovish", ["rate cut", "cuts rates", "lower rates", "easing", "dovish"],
     {"NQ": 1, "ES": 1, "GC": 1, "DXY": -1, "US10Y": -1}),
    ("risk_off", ["war", "attack", "sanctions", "tariff", "tariffs", "conflict", "geopolitical", "missile", "invasion"],
     {"NQ": -1, "ES": -1, "GC": 1, "VIX": 1}),
    ("fed_policy", ["fomc", "federal open market committee", "monetary policy", "federal funds", "powell"],
     {"NQ": 0, "ES": 0, "GC": 0, "DXY": 0, "US10Y": 0}),
    ("inflation_data", ["consumer price", "personal income and outlays", "pce", "producer price"],
     {"NQ": 0, "ES": 0, "GC": 0, "DXY": 0, "US10Y": 0}),
    ("growth_data", ["gross domestic product", "gdp"],
     {"NQ": 0, "ES": 0, "DXY": 0}),
]


def analyze_headline(title: str) -> dict:
    """Dönüş: {"assets": {varlık: positive/negative/neutral/unclear}, "rules": [...], "confidence": "low"}

    0 değerli kurallar "ilgili ama yönü belirsiz" demektir (unclear).
    Çelişen kurallar aynı varlığa farklı yön verirse sonuç "unclear" olur.
    """
    text = title.lower()
    matched = [(name, effects) for name, keywords, effects in RULES if _contains_any(text, keywords)]

    votes: dict[str, set[int]] = {}
    for _, effects in matched:
        for asset, sign in effects.items():
            votes.setdefault(asset, set()).add(sign)

    assets = {}
    for asset, signs in votes.items():
        directional = signs - {0}
        if len(directional) == 1:
            assets[asset] = POSITIVE if directional.pop() > 0 else NEGATIVE
        else:
            assets[asset] = UNCLEAR  # sadece "ilgili" veya çelişkili
    return {
        "assets": assets,
        "rules": [name for name, _ in matched],
        "confidence": "low",
        "method": "başlıkta anahtar kelime kuralları",
    }


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(keyword)}\b", text) for keyword in keywords)
