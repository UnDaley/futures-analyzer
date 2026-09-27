"""HTTP API ve dashboard.

Çalıştırma: uvicorn futures_analyzer.api:app  (veya ./start.sh)
Dashboard: http://localhost:8000/

Sunucu açıkken veriler arka planda otomatik güncellenir (AUTO_REFRESH_MINUTES, varsayılan 15).
"""

import math
import threading
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Engine

from futures_analyzer.ai.manual import check_manual_report, manual_prompt
from futures_analyzer.ai.report import ReportError, generate_report
from futures_analyzer.analysis import market_snapshot
from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.config import settings
from futures_analyzer.data.storage import create_tables, get_engine, load_candles, load_reports, save_report
from futures_analyzer.indicators.engine import VWAP_TIMEFRAMES, add_indicators
from futures_analyzer.instruments import INSTRUMENTS
from futures_analyzer.refresh import RefreshJob

DASHBOARD = Path(__file__).parent / "web" / "dashboard.html"
ICON = Path(__file__).parent / "web" / "icon.svg"  # sekme simgesi; masaüstü kısayolu da bunu kullanır
CHART_LINES = ["ema_20", "ema_50", "ema_200", "vwap"]  # grafikte isteğe bağlı
INDICATOR_WARMUP = 300  # EMA 200'ün oturması için grafikte gösterilenden fazla mum yüklenir


@lru_cache
def db_engine() -> Engine:
    engine = get_engine()
    create_tables(engine)
    return engine


refresh_job = RefreshJob(db_engine)


def _auto_refresh_loop(minutes: int) -> None:
    """Sunucu açılınca hemen, sonra her `minutes` dakikada bir verileri günceller."""
    while True:
        refresh_job.run_now()
        time.sleep(minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_refresh_minutes > 0:
        threading.Thread(target=_auto_refresh_loop, args=(settings.auto_refresh_minutes,), daemon=True).start()
    yield


app = FastAPI(title="Futures Analyzer", description="Analiz asistanı. Otomatik işlem yapmaz.", lifespan=lifespan)


def _check_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in INSTRUMENTS:
        raise HTTPException(404, f"Bilinmeyen sembol: {symbol}")
    return symbol


def _check_timeframe(tf: str) -> str:
    if tf not in TIMEFRAMES:
        raise HTTPException(400, f"Geçersiz zaman dilimi: {tf}. Seçenekler: {', '.join(TIMEFRAMES)}")
    return tf


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


@app.get("/icon.svg")
def icon() -> FileResponse:
    return FileResponse(ICON, media_type="image/svg+xml")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/candles")
def candles(
    symbol: str,
    tf: str = "1h",
    limit: int = Query(100, ge=1, le=5000),
    engine: Engine = Depends(db_engine),
) -> list[dict]:
    symbol, tf = _check_symbol(symbol), _check_timeframe(tf)
    df = load_candles(engine, symbol, tf, limit=limit)
    return [{"ts": ts.isoformat(), **row} for ts, row in df.to_dict("index").items()]


@app.get("/chart")
def chart(
    symbol: str,
    tf: str = "5m",
    limit: int = Query(300, ge=10, le=3000),
    engine: Engine = Depends(db_engine),
) -> dict:
    """Grafik verisi: mumlar + Python'da hesaplanmış EMA ve VWAP. time = Unix saniye (UTC)."""
    symbol, tf = _check_symbol(symbol), _check_timeframe(tf)
    df = add_indicators(load_candles(engine, symbol, tf, limit=limit + INDICATOR_WARMUP), tf).tail(limit)

    bars, lines = [], {name: [] for name in CHART_LINES if name in df.columns}
    for ts, row in df.iterrows():
        seconds = int(ts.timestamp())
        bars.append({"time": seconds, **{k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}})
        for name in lines:
            if not math.isnan(row[name]):
                lines[name].append({"time": seconds, "value": round(float(row[name]), 2)})
    return {"symbol": symbol, "timeframe": tf, "has_vwap": tf in VWAP_TIMEFRAMES, "bars": bars, "lines": lines}


NO_DATA = "Henüz veri yok. Veriler güncelleniyor; ilk seferde birkaç dakika sürebilir."


def _snapshot_or_409(engine: Engine, symbol: str) -> dict:
    current = market_snapshot(engine, _check_symbol(symbol))
    if current["price"] is None:
        raise HTTPException(409, NO_DATA)
    return current


@app.get("/snapshot")
def snapshot(symbol: str, engine: Engine = Depends(db_engine)) -> dict:
    return _snapshot_or_409(engine, symbol)


@app.get("/reports")
def reports(symbol: str | None = None, limit: int = Query(5, ge=1, le=100), engine: Engine = Depends(db_engine)) -> list[dict]:
    """Son Claude raporları (büyük snapshot alanı hariç)."""
    rows = load_reports(engine, _check_symbol(symbol) if symbol else None, limit=limit)
    return [
        {**{k: v for k, v in row.items() if k != "snapshot"}, "as_of": row["as_of"].isoformat(), "created_at": row["created_at"].isoformat()}
        for row in rows
    ]


@app.post("/report")
def report(symbol: str, engine: Engine = Depends(db_engine)) -> dict:
    """Claude raporu üretir ve kaydeder. API anahtarı yoksa 503 döner."""
    current = _snapshot_or_409(engine, symbol)
    try:
        result = generate_report(current)
    except ReportError as error:
        raise HTTPException(503, str(error)) from error
    return {"id": save_report(engine, current, result), **result}


# --- Terminalsiz kullanım: güncelleme ve claude.ai akışı ---

@app.post("/refresh")
def refresh() -> dict:
    """Verileri arka planda günceller. Durum /refresh/status ile izlenir."""
    return {"started": refresh_job.start(), **refresh_job.status()}


@app.get("/refresh/status")
def refresh_status() -> dict:
    return {**refresh_job.status(), "auto_refresh_minutes": settings.auto_refresh_minutes}


@app.post("/prompt")
def prompt(symbol: str, engine: Engine = Depends(db_engine)) -> dict:
    """Snapshot'ı kaydeder ve claude.ai'ye yapıştırılacak metni döndürür."""
    current = _snapshot_or_409(engine, symbol)
    return {"id": save_report(engine, current), "text": manual_prompt(current)}


class ManualReport(BaseModel):
    id: int
    text: str


@app.post("/check-report")
def check_report(report: ManualReport, engine: Engine = Depends(db_engine)) -> dict:
    """claude.ai'den gelen raporu kontrol eder ve kayda ekler."""
    if not report.text.strip():
        raise HTTPException(400, "Rapor boş")
    try:
        return check_manual_report(engine, report.id, report.text)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
