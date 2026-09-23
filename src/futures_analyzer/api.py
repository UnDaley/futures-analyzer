"""HTTP API ve dashboard.

Çalıştırma: uvicorn futures_analyzer.api:app --reload
Dashboard: http://localhost:8000/
"""

import math
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import Engine

from futures_analyzer.ai.report import ReportError, generate_report
from futures_analyzer.analysis import market_snapshot
from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.storage import create_tables, get_engine, load_analyses, load_candles
from futures_analyzer.evaluation.journal import record_analysis
from futures_analyzer.indicators.engine import VWAP_TIMEFRAMES, add_indicators
from futures_analyzer.instruments import INSTRUMENTS

app = FastAPI(title="Futures Analyzer", description="Analiz asistanı. Otomatik işlem yapmaz.")
DASHBOARD = Path(__file__).parent / "web" / "dashboard.html"
CHART_LINES = ["ema_20", "ema_50", "ema_200", "vwap"]
INDICATOR_WARMUP = 300  # EMA 200'ün oturması için grafikte gösterilenden fazla mum yüklenir


@lru_cache
def db_engine() -> Engine:
    engine = get_engine()
    create_tables(engine)
    return engine


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
    tf: str = "15m",
    limit: int = Query(300, ge=10, le=3000),
    engine: Engine = Depends(db_engine),
) -> dict:
    """Grafik verisi: mumlar + Python'da hesaplanmış EMA ve VWAP. time = Unix saniye (UTC)."""
    symbol, tf = _check_symbol(symbol), _check_timeframe(tf)
    df = add_indicators(load_candles(engine, symbol, tf, limit=limit + INDICATOR_WARMUP), tf).tail(limit)

    bars, lines = [], {name: [] for name in CHART_LINES if name in df.columns}
    for ts, row in df.iterrows():
        time = int(ts.timestamp())
        bars.append({"time": time, **{k: float(row[k]) for k in ("open", "high", "low", "close", "volume")}})
        for name in lines:
            if not math.isnan(row[name]):
                lines[name].append({"time": time, "value": round(float(row[name]), 2)})
    return {"symbol": symbol, "timeframe": tf, "has_vwap": tf in VWAP_TIMEFRAMES, "bars": bars, "lines": lines}


@app.get("/snapshot")
def snapshot(symbol: str, engine: Engine = Depends(db_engine)) -> dict:
    return market_snapshot(engine, _check_symbol(symbol))


@app.get("/analyses")
def analyses(symbol: str | None = None, limit: int = Query(20, ge=1, le=500), engine: Engine = Depends(db_engine)) -> list[dict]:
    """Son kayıtlı analizler (büyük snapshot alanı hariç)."""
    rows = load_analyses(engine, _check_symbol(symbol) if symbol else None, limit=limit)
    return [
        {**{k: v for k, v in row.items() if k != "snapshot"}, "as_of": row["as_of"].isoformat(), "created_at": row["created_at"].isoformat()}
        for row in rows
    ]


@app.post("/report")
def report(symbol: str, engine: Engine = Depends(db_engine)) -> dict:
    """Claude raporu üretir ve kaydeder. API anahtarı yoksa 503 döner."""
    current = market_snapshot(engine, _check_symbol(symbol))
    try:
        result = generate_report(current)
    except ReportError as error:
        raise HTTPException(503, str(error)) from error
    analysis_id = record_analysis(engine, current, result)
    return {"id": analysis_id, **result}
