"""Kontratın 10am modeli özetini (snapshot) üretir. Dashboard ve Claude'a giden JSON budur.

Bölümler:
- setup: bugünkü 10am setup'ının durumu, seviyeleri ve sıradaki adım (strategy/ten_am.py)
- levels: bugünün likidite seviyeleri (önceki gün, Asya, Londra, 08:00-10:00, 10:00 sonrası)
- events: bugünkü ekonomik veriler ve en yakın olay riski
- history: son günlerin setup sonuçları ve istatistikleri

build_snapshot yalnızca `now` anından önceki veriyle çalışır; testlerde ve geçmiş günler için
aynı fonksiyon kullanılır.
"""

from datetime import timedelta

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.data.storage import load_candles
from futures_analyzer.instruments import Instrument, get_instrument
from futures_analyzer.market_time import NEW_YORK, is_market_open
from futures_analyzer.news.engine import events_snapshot
from futures_analyzer.strategy.ten_am import (
    BEFORE_OPEN,
    BROKEN,
    IN_TRADE,
    MANIPULATION,
    WAITING,
    liquidity_levels,
    recent_days,
    summarize,
    ten_am_day,
)

DATA_SOURCE = "yfinance (10-15 dk gecikmeli, 5 dakikalık mumlar)"
HISTORY_DAYS = 60
# Grafikte ve raporda gösterilen seviyeler (5M swing'ler kalabalık yaptığı için hariç)
KEY_LEVEL_PREFIXES = ("Önceki gün", "Asya", "Londra", "08:00-10:00")


def market_snapshot(db: Engine, symbol: str) -> dict:
    """Şu anki özet."""
    instrument = get_instrument(symbol)
    now = pd.Timestamp.now(tz="UTC")
    return build_snapshot(load_candles(db, instrument.symbol, "5m"), instrument, now, events=events_snapshot(db, now))


def build_snapshot(five_min: pd.DataFrame, instrument: Instrument, now: pd.Timestamp, events: dict | None = None) -> dict:
    five_min = five_min[five_min.index < now]
    price = float(five_min["close"].iloc[-1]) if not five_min.empty else None
    day = _session_day(now)

    setup = ten_am_day(five_min, day, instrument, now)
    setup["next"] = next_step(setup, instrument)
    history = recent_days(five_min, instrument, now, HISTORY_DAYS, before=day)

    return {
        "instrument": instrument.symbol,
        "as_of": now.isoformat(),
        "data_source": DATA_SOURCE,
        "price": price,
        "last_bar_ts": five_min.index[-1].isoformat() if not five_min.empty else None,
        "market_open": is_market_open(now),
        "setup": setup,
        "levels": key_levels(five_min, day, now, setup),
        "events": events,
        "history": {"stats": summarize(history), "days": [_compact(result) for result in history]},
    }


def key_levels(five_min: pd.DataFrame, day, now: pd.Timestamp, setup: dict) -> list[dict]:
    """Bugünün önemli seviyeleri, yüksekten düşüğe."""
    levels = [
        {"name": level["name"], "price": level["price"]}
        for level in liquidity_levels(five_min, day, now)
        if level["name"].startswith(KEY_LEVEL_PREFIXES)
    ]
    if setup["open_level"] is not None:
        levels.append({"name": "10:00 açılışı", "price": setup["open_level"]})
    return sorted(levels, key=lambda level: -level["price"])


def next_step(setup: dict, instrument: Instrument) -> str:
    """Şu an neyin izlenmesi gerektiği (düz Türkçe)."""
    def p(value: float) -> str:
        return price_text(value, instrument.tick_size)

    status, level, trap = setup["status"], setup["open_level"], instrument.trap_points
    short = setup["direction"] == "short"
    if status == BEFORE_OPEN:
        return (f"10:00 mumunun açılışı bekleniyor. Açılış işaretlendikten sonra fiyatın açılıştan en az "
                f"{trap:g} puan uzaklaşması manipülasyon sayılır.")
    if status == WAITING:
        return (f"Açılış {p(level)}. Fiyat {p(level + trap)} üstüne çıkarsa short, {p(level - trap)} altına inerse "
                f"long setup hazırlanır. 12:00'ye kadar geçerli.")
    if status == MANIPULATION:
        extreme = setup["manipulation"]["extreme"]
        where = "altında" if short else "üstünde"
        return (f"{'Yukarı' if short else 'Aşağı'} manipülasyon oldu (uç {p(extreme)}). Bir 5M mumun {p(level)} {where} "
                f"kapanması bekleniyor; 12:00'ye kadar olmazsa bugün setup yok.")
    if status == BROKEN:
        where = "altında" if short else "üstünde"
        return (f"Açılış geri kırıldı. Fiyatın {p(level)} seviyesine geri dokunup {where} kapanması (retest) bekleniyor. "
                f"Stop manipülasyon ucunun ötesinde olur ({p(setup['manipulation']['extreme'])}).")
    if status == IN_TRADE:
        target = setup["target"]
        return (f"{'Short' if short else 'Long'} setup aktif: giriş {p(setup['entry']['price'])}, stop {p(setup['stop'])}, "
                f"hedef {p(target['price'])} ({target['source']}), R:R {setup['rr']:g}.")
    result = setup["status_text"]
    if setup["r_multiple"] is not None:
        result += f" ({setup['r_multiple']:+g}R)"
    return f"Bugün tamamlandı: {result}. Sıradaki setup bir sonraki işlem gününde 10:00'da."


def price_text(value: float, tick_size: float) -> str:
    decimals = len(f"{tick_size:g}".partition(".")[2])
    return f"{value:.{decimals}f}"


def _session_day(now: pd.Timestamp):
    """Bugün (New York tarihi); hafta sonuysa son cuma."""
    day = now.tz_convert(NEW_YORK).date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _compact(result: dict) -> dict:
    """Geçmiş tablosu için kısa özet."""
    return {
        "date": result["date"],
        "status": result["status"],
        "status_text": result["status_text"],
        "direction": result["direction"],
        "open_level": result["open_level"],
        "entry": result["entry"]["price"] if result["entry"] else None,
        "entry_ts": result["entry"]["ts"] if result["entry"] else None,
        "stop": result["stop"],
        "target": result["target"]["price"] if result["target"] else None,
        "target_source": result["target"]["source"] if result["target"] else None,
        "r_multiple": result["r_multiple"],
    }
