"""Bütün verileri güncelleme: kontratlar, ilişkili varlıklar, makro, haberler.

- refresh_all: sırayla hepsini çeker; bir adım hata verirse kaydedip diğerlerine devam eder.
  Sonra piyasa açıksa ve son kayıttan beri yeterli süre geçtiyse analizleri kaydeder (record)
  ve zamanı gelen analizlerin sonuçlarını ölçer (evaluate). Böylece günlük elle tutulmak zorunda kalmaz.
- RefreshJob: dashboard için arka planda (ayrı thread'de) çalıştırır ve durumunu tutar.
  Aynı anda sadece bir güncelleme çalışır.
"""

import threading
from collections import deque

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.config import settings
from futures_analyzer.data.ingest import FETCH_TIMEFRAMES, ingest
from futures_analyzer.data.providers.yahoo import YahooProvider
from futures_analyzer.data.storage import create_tables, load_analyses
from futures_analyzer.evaluation.journal import evaluate_pending, record_analysis
from futures_analyzer.instruments import INSTRUMENTS, INTERMARKET_ASSETS
from futures_analyzer.macro.ingest import ingest_macro
from futures_analyzer.market_time import is_market_open
from futures_analyzer.news.engine import ingest_news


def refresh_all(engine: Engine, log=print) -> list[str]:
    """Her şeyi günceller. Hata mesajlarının listesini döndürür (boşsa her şey yolunda)."""
    create_tables(engine)
    provider = YahooProvider()
    errors: list[str] = []

    def step(name: str, action) -> None:
        try:
            log(f"{name}: {action()}")
        except Exception as error:  # ağ hatası vb.: kaydet ve devam et
            errors.append(f"{name}: {error}")
            log(f"{name}: HATA ({error})")

    for instrument in INSTRUMENTS.values():
        for timeframe in FETCH_TIMEFRAMES:
            step(instrument.symbol, lambda: _counts(ingest(engine, provider, instrument, timeframe)))
    for asset in INTERMARKET_ASSETS.values():
        step(asset.symbol, lambda: _counts(ingest(engine, provider, asset, "1h")))
    step("makro", lambda: _macro_summary(ingest_macro(engine)))
    step("haber ve takvim", lambda: _news_summary(ingest_news(engine)))
    if settings.auto_record_minutes > 0:
        step("analiz kaydı", lambda: auto_record(engine, settings.auto_record_minutes))
    step("sonuç ölçümü", lambda: f"{evaluate_pending(engine)} analiz güncellendi")
    return errors


def auto_record(engine: Engine, every_minutes: int, now: pd.Timestamp | None = None) -> str:
    """Piyasa açıksa, son kaydı `every_minutes` dakikadan eski olan kontratların analizini kaydeder."""
    from futures_analyzer.analysis import market_snapshot  # döngüsel import olmasın diye burada

    now = now or pd.Timestamp.now(tz="UTC")
    if not is_market_open(now):
        return "piyasa kapalı, kayıt yapılmadı"
    saved = []
    for symbol in INSTRUMENTS:
        last = load_analyses(engine, symbol, limit=1)
        if last and now - last[0]["as_of"] < pd.Timedelta(minutes=every_minutes):
            continue
        snapshot = market_snapshot(engine, symbol)
        if snapshot["price"] is not None:
            record_analysis(engine, snapshot)
            saved.append(symbol)
    return f"kaydedildi: {', '.join(saved)}" if saved else "yeni kayıt gerekmedi"


def _counts(saved: dict[str, int]) -> str:
    return ", ".join(f"{tf} {count} mum" for tf, count in saved.items())


def _macro_summary(saved: dict[str, int]) -> str:
    failed = [name for name, count in saved.items() if count < 0]
    return f"{len(saved) - len(failed)} seri güncellendi" + (f", alınamayan: {', '.join(failed)}" if failed else "")


def _news_summary(saved: dict[str, int]) -> str:
    return f"{saved['news']} haber, {saved['events']} takvim olayı"


class RefreshJob:
    """Güncellemeyi arka planda çalıştırır; dashboard durumunu `status()` ile sorar."""

    def __init__(self, engine_factory, refresh=refresh_all):
        self._engine_factory = engine_factory
        self._refresh = refresh
        self._lock = threading.Lock()
        self._log: deque[str] = deque(maxlen=60)
        self.running = False
        self.last_started: pd.Timestamp | None = None
        self.last_finished: pd.Timestamp | None = None
        self.last_errors: list[str] = []

    def start(self) -> bool:
        """Güncellemeyi arka planda başlatır. Zaten çalışıyorsa False döner."""
        if not self._claim():
            return False
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def run_now(self) -> bool:
        """Aynı thread'de çalıştırır (otomatik güncelleme döngüsü ve testler için)."""
        if not self._claim():
            return False
        self._run()
        return True

    def _claim(self) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.last_started = pd.Timestamp.now(tz="UTC")
            self._log.clear()
            return True

    def _run(self) -> None:
        try:
            self.last_errors = self._refresh(self._engine_factory(), log=self._log.append)
        except Exception as error:
            self.last_errors = [str(error)]
            self._log.append(f"HATA: {error}")
        finally:
            self.last_finished = pd.Timestamp.now(tz="UTC")
            self.running = False

    def status(self) -> dict:
        return {
            "running": self.running,
            "last_started": self.last_started.isoformat() if self.last_started else None,
            "last_finished": self.last_finished.isoformat() if self.last_finished else None,
            "errors": self.last_errors,
            "log": list(self._log),
        }
