"""HTTP API. Şimdilik sadece kayıtlı mumları okumak için.

Çalıştırma: uvicorn futures_analyzer.api:app --reload
"""

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import Engine

from futures_analyzer.analysis import technical_snapshot
from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.storage import get_engine, load_candles
from futures_analyzer.instruments import INSTRUMENTS

app = FastAPI(title="Futures Analyzer", description="Analiz asistanı. Otomatik işlem yapmaz.")


@lru_cache
def db_engine() -> Engine:
    return get_engine()


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
    symbol = symbol.upper()
    if symbol not in INSTRUMENTS:
        raise HTTPException(404, f"Bilinmeyen sembol: {symbol}")
    if tf not in TIMEFRAMES:
        raise HTTPException(400, f"Geçersiz zaman dilimi: {tf}. Seçenekler: {', '.join(TIMEFRAMES)}")

    df = load_candles(engine, symbol, tf, limit=limit)
    return [{"ts": ts.isoformat(), **row} for ts, row in df.to_dict("index").items()]


@app.get("/indicators")
def indicators(symbol: str, engine: Engine = Depends(db_engine)) -> dict:
    symbol = symbol.upper()
    if symbol not in INSTRUMENTS:
        raise HTTPException(404, f"Bilinmeyen sembol: {symbol}")
    return technical_snapshot(engine, symbol)
