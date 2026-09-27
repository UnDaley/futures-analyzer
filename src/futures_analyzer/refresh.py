"""Bütün verileri güncelleme: kontratların mumları ve ekonomik takvim.

- refresh_all: sırayla hepsini çeker; bir adım hata verirse kaydedip diğerlerine devam eder.
  10am modelinin sonuçları mumlardan her seferinde yeniden hesaplandığı için ayrıca kayıt tutulmaz.
- RefreshJob: dashboard için arka planda (ayrı thread'de) çalıştırır ve durumunu tutar.
  Aynı anda sadece bir güncelleme çalışır.
"""

import threading
from collections import deque

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.data.ingest import FETCH_TIMEFRAMES, ingest
from futures_analyzer.data.providers.yahoo import YahooProvider
from futures_analyzer.data.storage import create_tables
from futures_analyzer.instruments import INSTRUMENTS
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
    step("ekonomik takvim", lambda: f"{ingest_news(engine)['events']} olay")
    return errors


def _counts(saved: dict[str, int]) -> str:
    return ", ".join(f"{tf} {count} mum" for tf, count in saved.items())


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
