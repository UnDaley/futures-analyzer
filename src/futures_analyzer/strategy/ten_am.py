"""Powell Trades 10am modeli (açılış + manipülasyon + retest), 5 dakikalık mumlarla.

Kurallar (her işlem günü için, New York saati):
1. Açılış: 10:00 mumunun açılış fiyatı işaretlenir.
2. Manipülasyon: fiyat açılıştan en az `trap_points` (kontrata göre, örn. NQ 15) bir yöne uzaklaşır.
   Yukarı manipülasyon short, aşağı manipülasyon long setup'ı hazırlar. Manipülasyonun ucu takip edilir.
3. Geri kırılım: bir 5M mum açılışın öbür tarafında kapanır.
4. Retest: sonraki bir mum açılışa geri dokunur ve yine kırılım tarafında kapanır. Giriş = açılış fiyatı.
   Mum açılışın manipülasyon tarafında kapanırsa kırılım başarısız sayılır ve 3. adım yeniden beklenir.
   Stop = manipülasyon ucu + 1 tick. Hedef = girişten en az MIN_RR kadar uzaktaki ilk alınmamış likidite
   (önceki gün / Asya / Londra / 08:00-10:00 high-low, 10:00 sonrası dip-tepe, 5M swing'ler).
   Hiçbiri yoksa hedef 2R'dir.
Giriş 12:00'ye kadar oluşmazsa o gün setup yoktur. Açık işlem 16:00'da son kapanışla sonuçlandırılır.

Sonuç ölçümü: hedefe veya stop'a iğneyle dokunulması yeterlidir. Aynı mumda ikisine birden dokunulursa
sıra bilinemeyeceği için sonuç "ambiguous" olur. Retest mumu stop'a da dokunduysa sonuç stop sayılır
(ihtiyatlı varsayım: 5M mumun içindeki sıra bilinemez).

Model yalnızca `now` anından önce kapanmış mumları kullanır; canlı durum ve geçmiş günlerin istatistikleri
aynı fonksiyonla hesaplanır, bu yüzden geçmiş sonuçlar sonradan gelen veriyle değişmez.
"""

from datetime import time

import pandas as pd

from futures_analyzer.instruments import Instrument
from futures_analyzer.market_time import NEW_YORK, drop_incomplete_last_bar, trading_date
from futures_analyzer.structure.swings import HIGH, find_swings

OPEN_TIME = time(10, 0)
ENTRY_DEADLINE = time(12, 0)   # giriş bu saate kadar oluşmalı
DAY_END = time(16, 0)          # açık işlem bu saatte kapanışla sonuçlandırılır
MIN_RR = 1.0                   # hedef girişten en az bu kadar R uzakta olmalı
FALLBACK_RR = 2.0
SWING_LENGTH = 3

# Durumlar: canlı (gün sürüyor) ve sonuç (gün bitti veya işlem kapandı)
BEFORE_OPEN = "before_open"          # 10:00 mumu henüz yok
WAITING = "waiting_manipulation"     # manipülasyon bekleniyor
MANIPULATION = "manipulation"        # manipülasyon oldu, geri kırılım bekleniyor
BROKEN = "waiting_retest"            # açılış geri kırıldı, retest bekleniyor
IN_TRADE = "in_trade"                # giriş oldu, hedef/stop bekleniyor
TARGET, STOP, AMBIGUOUS, TIME_EXIT = "target", "stop", "ambiguous", "time_exit"
NO_SETUP = "no_setup"                # 12:00'ye kadar giriş oluşmadı
NO_DATA = "no_data"                  # 10:00 mumu eksik (tatil, veri boşluğu)
FINISHED = {TARGET, STOP, AMBIGUOUS, TIME_EXIT, NO_SETUP, NO_DATA}

STATUS_TEXT = {
    BEFORE_OPEN: "10:00 açılışı bekleniyor",
    WAITING: "Manipülasyon bekleniyor",
    MANIPULATION: "Manipülasyon oldu, açılışın geri kırılması bekleniyor",
    BROKEN: "Açılış geri kırıldı, retest bekleniyor",
    IN_TRADE: "Giriş oluştu, hedef veya stop bekleniyor",
    TARGET: "Hedefe ulaştı",
    STOP: "Stop oldu",
    AMBIGUOUS: "Aynı mumda hedef ve stop (sıra belirsiz)",
    TIME_EXIT: "16:00'da hedef/stop olmadan kapandı",
    NO_SETUP: "12:00'ye kadar setup oluşmadı",
    NO_DATA: "10:00 verisi yok",
}


def ten_am_day(five_min: pd.DataFrame, day, instrument: Instrument, now: pd.Timestamp) -> dict:
    """`day` (New York tarihi) için modelin durumu. five_min: bütün 5M mumlar (önceki günler dahil)."""
    closed = drop_incomplete_last_bar(five_min[five_min.index < now], "5m", now)
    today = closed[closed.index.tz_convert(NEW_YORK).date == day]
    today_local = today.index.tz_convert(NEW_YORK)
    day_over = now >= _ny(day, DAY_END)

    result = {
        "date": day.isoformat(),
        "open_time_ny": OPEN_TIME.strftime("%H:%M"),
        "trap_points": instrument.trap_points,
        "open_level": None,
        "direction": None,
        "manipulation": None,
        "break": None,
        "entry": None,
        "stop": None,
        "target": None,
        "risk_points": None,
        "rr": None,
        "exit": None,
        "r_multiple": None,
    }

    at_open = today[today_local.time == OPEN_TIME]
    if at_open.empty:
        status = NO_DATA if now >= _ny(day, ENTRY_DEADLINE) else BEFORE_OPEN
        return _finish(result, status)

    open_level = float(at_open["open"].iloc[0])
    result["open_level"] = open_level
    window = today[(today_local.time >= OPEN_TIME) & (today_local.time < DAY_END)]
    trap, tick = instrument.trap_points, instrument.tick_size

    status = WAITING
    side = extreme = None
    for ts, bar in window.iterrows():
        bar_time = ts.tz_convert(NEW_YORK).time()

        if status in (WAITING, MANIPULATION, BROKEN) and bar_time >= ENTRY_DEADLINE:
            return _finish(result, NO_SETUP)

        if status == WAITING:
            up, down = bar["high"] - open_level, open_level - bar["low"]
            if max(up, down) < trap:
                continue
            # Aynı mum iki yöne de eşiği geçtiyse daha uzağa gidilen taraf manipülasyon sayılır
            side = "short" if up >= down else "long"
            extreme = bar["high"] if side == "short" else bar["low"]
            result["direction"] = side
            result["manipulation"] = {"side": "up" if side == "short" else "down", "ts": ts.isoformat(), "extreme": None}
            status = MANIPULATION
            # Manipülasyon mumu aynı zamanda geri kırılım mumu olabilir (aşağıda kontrol edilir)

        if status == MANIPULATION:
            extreme = max(extreme, bar["high"]) if side == "short" else min(extreme, bar["low"])
            result["manipulation"]["extreme"] = float(extreme)
            if _beyond(bar["close"], open_level, side):
                result["break"] = {"ts": ts.isoformat(), "close": float(bar["close"])}
                status = BROKEN
            continue

        if status == BROKEN:
            touched = bar["high"] >= open_level if side == "short" else bar["low"] <= open_level
            if not touched:
                continue
            if not _beyond(bar["close"], open_level, side):
                # Kırılım tutmadı: manipülasyon tarafına geri döndü, yeni kırılım beklenir
                extreme = max(extreme, bar["high"]) if side == "short" else min(extreme, bar["low"])
                result["manipulation"]["extreme"] = float(extreme)
                result["break"] = None
                status = MANIPULATION
                continue
            stop = _to_tick(extreme + tick if side == "short" else extreme - tick, tick)
            risk = abs(stop - open_level)
            result["entry"] = {"price": open_level, "ts": ts.isoformat()}
            result["stop"] = float(stop)
            result["risk_points"] = round(float(risk), 4)
            result["target"] = pick_target(closed, day, ts, open_level, risk, side, tick)
            result["rr"] = round(abs(result["target"]["price"] - open_level) / risk, 2)
            status = IN_TRADE
            if _stop_hit(bar, stop, side):
                return _close(result, STOP, ts, stop)
            continue

        if status == IN_TRADE:
            stop, target = result["stop"], result["target"]["price"]
            hit_stop = _stop_hit(bar, stop, side)
            hit_target = bar["low"] <= target if side == "short" else bar["high"] >= target
            if hit_stop and hit_target:
                return _close(result, AMBIGUOUS, ts, None)
            if hit_stop:
                return _close(result, STOP, ts, stop)
            if hit_target:
                return _close(result, TARGET, ts, target)

    if status == IN_TRADE and day_over:
        last_ts, last = window.index[-1], window.iloc[-1]
        return _close(result, TIME_EXIT, last_ts, float(last["close"]))
    if status in (WAITING, MANIPULATION, BROKEN) and now >= _ny(day, ENTRY_DEADLINE):
        return _finish(result, NO_SETUP)
    return _finish(result, status)


def pick_target(closed: pd.DataFrame, day, entry_ts: pd.Timestamp, entry: float, risk: float, side: str, tick: float) -> dict:
    """Girişten en az MIN_RR uzaktaki ilk alınmamış likidite; yoksa FALLBACK_RR."""
    candidates = [
        level for level in liquidity_levels(closed, day, entry_ts)
        if (level["price"] < entry if side == "short" else level["price"] > entry)
        and abs(level["price"] - entry) >= MIN_RR * risk
        and not _taken(closed, level, entry_ts, side)
    ]
    if candidates:
        nearest = min(candidates, key=lambda level: abs(level["price"] - entry))
        return {"price": nearest["price"], "source": nearest["name"]}
    price = entry - FALLBACK_RR * risk if side == "short" else entry + FALLBACK_RR * risk
    return {"price": _to_tick(price, tick), "source": f"{FALLBACK_RR:g}R (yakında likidite yok)"}


def liquidity_levels(closed: pd.DataFrame, day, until: pd.Timestamp) -> list[dict]:
    """Hedef adayları. `since`: seviyenin oluştuğu an (sonrasında aşıldıysa alınmış sayılır)."""
    before = closed[closed.index < until]
    if before.empty:
        return []
    sessions = trading_date(before.index)
    today_session = pd.Timestamp(day)
    levels = []

    def add_range(bars: pd.DataFrame, high_name: str, low_name: str) -> None:
        if bars.empty:
            return
        levels.append({"name": high_name, "price": float(bars["high"].max()), "since": bars["high"].idxmax()})
        levels.append({"name": low_name, "price": float(bars["low"].min()), "since": bars["low"].idxmin()})

    earlier = sessions[sessions < today_session]
    if len(earlier):
        add_range(before[sessions == earlier.max()], "Önceki gün yükseği", "Önceki gün düşüğü")
    today = before[sessions == today_session]
    today_local = today.index.tz_convert(NEW_YORK)
    hours = today_local.hour
    add_range(today[(hours >= 18) | (hours < 3)], "Asya yükseği", "Asya düşüğü")
    add_range(today[(hours >= 3) & (hours < 8)], "Londra yükseği", "Londra düşüğü")
    add_range(today[(hours >= 8) & (today_local.time < OPEN_TIME)], "08:00-10:00 yükseği", "08:00-10:00 düşüğü")
    add_range(today[today_local.time >= OPEN_TIME], "10:00 sonrası tepe", "10:00 sonrası dip")

    if len(today) > 2 * SWING_LENGTH:
        swings = find_swings(today, SWING_LENGTH)
        for swing in swings[swings["confirmed_ts"] < until].to_dict("records"):
            name = "5M swing yükseği" if swing["kind"] == HIGH else "5M swing düşüğü"
            levels.append({"name": name, "price": swing["price"], "since": swing["ts"]})
    return levels


def _taken(closed: pd.DataFrame, level: dict, until: pd.Timestamp, side: str) -> bool:
    """Seviye oluştuktan sonra girişe kadar aşıldı mı (likidite alındı mı)?"""
    after = closed[(closed.index > level["since"]) & (closed.index < until)]
    if after.empty:
        return False
    return bool(after["low"].min() < level["price"]) if side == "short" else bool(after["high"].max() > level["price"])


def recent_days(five_min: pd.DataFrame, instrument: Instrument, now: pd.Timestamp, days: int, before=None) -> list[dict]:
    """`before` gününden (varsayılan: bugün) önceki son `days` işlem gününün sonucu, yeniden eskiye."""
    closed = five_min[five_min.index < now]
    before = before or now.tz_convert(NEW_YORK).date()
    local = closed.index.tz_convert(NEW_YORK)
    # Sadece 10:00-12:00 arasında mumu olan günler (akşam seansı, tatil ve veri boşlukları hariç)
    in_window = (local.time >= OPEN_TIME) & (local.time < ENTRY_DEADLINE)
    dates = sorted({d for d in local[in_window].date if d < before})
    return [ten_am_day(closed, day, instrument, now) for day in reversed(dates[-days:])]


def summarize(results: list[dict]) -> dict:
    """Günlük sonuçlardan istatistik. R: risk birimi (stop mesafesi)."""
    entries = [r for r in results if r["entry"] is not None and r["status"] in FINISHED]
    wins = [r for r in entries if r["status"] == TARGET]
    losses = [r for r in entries if r["status"] == STOP]
    decided = [r for r in entries if r["r_multiple"] is not None]
    r_values = [r["r_multiple"] for r in decided]
    return {
        "days": len(results),
        "setups": len(entries),
        "wins": len(wins),
        "losses": len(losses),
        "ambiguous": sum(r["status"] == AMBIGUOUS for r in entries),
        "time_exits": sum(r["status"] == TIME_EXIT for r in entries),
        "no_setup": sum(r["status"] == NO_SETUP for r in results),
        "win_rate": round(len(wins) / (len(wins) + len(losses)) * 100, 1) if wins or losses else None,
        "avg_r": round(float(sum(r_values)) / len(r_values), 2) if r_values else None,
        "total_r": round(float(sum(r_values)), 2) if r_values else None,
        "long": _side_stats(entries, "long"),
        "short": _side_stats(entries, "short"),
    }


def _side_stats(entries: list[dict], side: str) -> dict:
    chosen = [r for r in entries if r["direction"] == side]
    wins = sum(r["status"] == TARGET for r in chosen)
    losses = sum(r["status"] == STOP for r in chosen)
    return {"setups": len(chosen), "win_rate": round(wins / (wins + losses) * 100, 1) if wins + losses else None}


def _close(result: dict, status: str, ts: pd.Timestamp, price: float | None) -> dict:
    result["exit"] = {"ts": ts.isoformat(), "price": price}
    if price is not None:
        entry, risk = result["entry"]["price"], result["risk_points"]
        move = entry - price if result["direction"] == "short" else price - entry
        result["r_multiple"] = round(float(move / risk), 2) if risk else None
    return _finish(result, status)


def _finish(result: dict, status: str) -> dict:
    result["status"] = status
    result["status_text"] = STATUS_TEXT[status]
    result["finished"] = status in FINISHED
    return result


def _beyond(close: float, level: float, side: str) -> bool:
    """Kapanış açılışın işlem tarafında mı? (short: altında, long: üstünde)"""
    return close < level if side == "short" else close > level


def _stop_hit(bar, stop: float, side: str) -> bool:
    return bar["high"] >= stop if side == "short" else bar["low"] <= stop


def _to_tick(price: float, tick: float) -> float:
    return round(round(float(price) / tick) * tick, 6)


def _ny(day, clock: time) -> pd.Timestamp:
    return pd.Timestamp.combine(day, clock).tz_localize(NEW_YORK).tz_convert("UTC")
