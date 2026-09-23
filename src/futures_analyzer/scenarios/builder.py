"""Senaryo motoru: bullish, bearish ve neutral senaryoları destek/direnç zone'larından kurar.

Kurallar (bütün fiyatlar snapshot'taki zone'lardan gelir, hiçbiri uydurulmaz):
- Bullish tetik  : fiyatın içinde olduğu zone, yoksa en yakın direnç zone'unun ÜSTÜNDE kabul (15M kapanış)
- Bullish hedefler: tetik zone'unun üstündeki direnç zone'larından, tetikten ve birbirinden en az
  yarım ATR uzak olan ilk ikisi (çok yakın zone'lar anlamlı hedef değildir)
- Bullish invalidation: bearish tetik zone'unun altı
- Bearish: aynısının tersi
- Neutral: fiyat iki tetik seviyesinin arasında kalır
Onay için ilgili 1H yapı kırılım seviyesi (varsa) ve olay riski eklenir.
"""


def build_scenarios(snapshot: dict, score: dict) -> dict | None:
    levels = snapshot.get("levels")
    if not levels:
        return None

    at_price = levels["at_price"][0] if levels["at_price"] else None
    resistance, support = list(levels["resistance"]), list(levels["support"])
    up_zone = at_price or (resistance.pop(0) if resistance else None)
    down_zone = at_price or (support.pop(0) if support else None)
    if up_zone is None or down_zone is None:
        return None

    up_trigger, down_trigger = up_zone["high"], down_zone["low"]
    # zone_tolerance = ATR'nin çeyreği -> iki katı yarım ATR
    min_gap = levels["zone_tolerance"] * 2
    structure_1h = (snapshot["timeframes"].get("1h") or {}).get("structure") or {}
    risks = _risk_factors(snapshot, score)

    bullish = {
        "trigger": f"15M kapanışın {up_trigger} üstünde kalması (kabul)",
        "trigger_level": up_trigger,
        "confirmation": _confirmation(structure_1h.get("bullish_break_level"), up_trigger, "üstünde", "yukarı"),
        "targets": _pick_targets(resistance, "low", up_trigger, min_gap),
        "invalidation": f"{down_trigger} altında kapanış",
        "invalidation_level": down_trigger,
        "trigger_zone": up_zone,
        "risk_factors": risks["bullish"],
    }
    bearish = {
        "trigger": f"15M kapanışın {down_trigger} altında kalması (kabul)",
        "trigger_level": down_trigger,
        "confirmation": _confirmation(structure_1h.get("bearish_break_level"), down_trigger, "altında", "aşağı"),
        "targets": _pick_targets(support, "high", down_trigger, min_gap),
        "invalidation": f"{up_trigger} üstüne geri dönüş",
        "invalidation_level": up_trigger,
        "trigger_zone": down_zone,
        "risk_factors": risks["bearish"],
    }
    neutral = {
        "range": [down_trigger, up_trigger],
        "description": f"Fiyat {down_trigger} ile {up_trigger} arasında kalır; iki yönde de kabul yoksa yön belirsizdir.",
        "risk_factors": risks["neutral"],
    }

    primary = {"bullish": "bullish", "bearish": "bearish"}.get(score["bias"], "neutral")
    return {"primary": primary, "bullish": bullish, "bearish": bearish, "neutral": neutral}


def _pick_targets(zones: list[dict], edge: str, trigger: float, min_gap: float, count: int = 2) -> list[dict]:
    """zones fiyata en yakından uzağa sıralı; her hedef bir öncekinden en az min_gap uzakta olmalı."""
    targets, last = [], trigger
    for zone in zones:
        if abs(zone[edge] - last) >= min_gap:
            targets.append(_zone_edge(zone, edge))
            last = zone[edge]
        if len(targets) == count:
            break
    return targets


def _zone_edge(zone: dict, edge: str) -> dict:
    return {"level": zone[edge], "zone": [zone["low"], zone["high"]], "sources": zone["sources"]}


def _confirmation(break_level: dict | None, trigger: float, side: str, direction: str) -> str:
    text = f"Tetik seviyesinin ({trigger}) yeniden test edilip korunması"
    if break_level:
        text += f"; 1H kapanışın {break_level['level']} {side} olması ({direction} {break_level['event']})"
    return text


def _risk_factors(snapshot: dict, score: dict) -> dict:
    """Her senaryoya ters düşen skor bileşenleri + ortak riskler (olay riski, eksik veri)."""
    common = []
    calendar = ((snapshot.get("news") or {}).get("calendar")) or {}
    event = calendar.get("event_risk")
    if event:
        prefix = "YAKIN " if event["imminent"] else ""
        common.append(f"{prefix}OLAY RİSKİ: {event['title']} ({event['minutes_until']} dk sonra)")
    for released in calendar.get("just_released", []):
        common.append(f"Yeni açıklanan veri: {released['title']} (oynaklık sürebilir)")
    missing = [name for name, c in score["components"].items() if not c["available"]]
    if missing:
        common.append("Eksik veri: " + ", ".join(missing))
    if snapshot.get("data_source", "").startswith("yfinance"):
        common.append("Veri 10-15 dk gecikmeli")

    against_bull = [f"{name}: {c['reason']}" for name, c in score["components"].items() if c["value"] < 0]
    against_bear = [f"{name}: {c['reason']}" for name, c in score["components"].items() if c["value"] > 0]
    return {
        "bullish": against_bull + common,
        "bearish": against_bear + common,
        "neutral": common,
    }
