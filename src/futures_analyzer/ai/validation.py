"""Rapordaki fiyatların veride gerçekten olup olmadığını kontrol eder (uydurma seviye kontrolü).

Yöntem:
1. Snapshot'taki bütün sayılar toplanır.
2. Rapordaki sayılardan fiyat gibi görünenler (güncel fiyatın ±%30'u içinde) bulunur.
3. Snapshot'ta bir tick içinde karşılığı olmayan her fiyat "bilinmeyen" sayılır.

Bu kontrol fiyat seviyelerini yakalar; yüzde, RSI gibi küçük sayılar fiyat aralığına düşmediği için
kapsam dışıdır.
"""

import re

NUMBER_PATTERN = re.compile(r"(?<![\w.])\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?(?![\w])|(?<![\w.])\d+(?:[.,]\d+)?(?![\w])")
PRICE_BAND = 0.30


def snapshot_numbers(value) -> set[float]:
    """Sözlük / liste içindeki bütün sayılar (metin içinde geçenler dahil)."""
    numbers: set[float] = set()
    if isinstance(value, bool):
        return numbers
    if isinstance(value, (int, float)):
        numbers.add(float(value))
    elif isinstance(value, str):
        numbers.update(parse_numbers(value))
    elif isinstance(value, dict):
        for item in value.values():
            numbers |= snapshot_numbers(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            numbers |= snapshot_numbers(item)
    return numbers


def parse_numbers(text: str) -> list[float]:
    """Metindeki sayılar. "30,941.25" ve "30.941" gibi binlik ayırıcılı yazımlar da tanınır."""
    result = []
    for match in NUMBER_PATTERN.finditer(text):
        result.append(_to_float(match.group()))
    return result


def _to_float(raw: str) -> float:
    # Binlik ayırıcılı mı? (1-3 hane, sonra üçerli gruplar)
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?", raw):
        separators = [c for c in raw if c in ".,"]
        thousands = separators[0]
        decimal = separators[-1] if separators[-1] != thousands else None
        integer_part, _, fraction = raw.rpartition(decimal) if decimal else (raw, "", "")
        cleaned = integer_part.replace(thousands, "") + ("." + fraction if decimal else "")
        return float(cleaned)
    return float(raw.replace(",", "."))


def find_unknown_prices(report: str, snapshot: dict, tick_size: float) -> list[str]:
    """Raporda geçen ama snapshot'ta karşılığı olmayan fiyatlar (metin olarak, tekrarsız)."""
    price = snapshot.get("price")
    if not price:
        return []
    known = sorted(snapshot_numbers(snapshot))
    low, high = price * (1 - PRICE_BAND), price * (1 + PRICE_BAND)

    unknown = []
    for match in NUMBER_PATTERN.finditer(report):
        value = _to_float(match.group())
        if not low <= value <= high:
            continue
        if not any(abs(value - k) <= tick_size + 1e-9 for k in known):
            if match.group() not in unknown:
                unknown.append(match.group())
    return unknown
