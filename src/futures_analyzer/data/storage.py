"""Mumları veritabanına kaydeder ve okur.

Tablo: candles (symbol, timeframe, ts) birincil anahtar.
Aynı mum tekrar kaydedilirse satır çoğalmaz, değerleri güncellenir (upsert).
Bu sayede henüz kapanmamış son mum da sonraki çekişte düzelir.
"""

import pandas as pd
from sqlalchemy import Column, DateTime, Engine, Float, MetaData, String, Table, create_engine, select
from sqlalchemy.dialects import postgresql, sqlite

from futures_analyzer.config import settings
from futures_analyzer.data.providers.base import CANDLE_COLUMNS

metadata = MetaData()

candles_table = Table(
    "candles",
    metadata,
    Column("symbol", String(16), primary_key=True),
    Column("timeframe", String(8), primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    Column("open", Float, nullable=False),
    Column("high", Float, nullable=False),
    Column("low", Float, nullable=False),
    Column("close", Float, nullable=False),
    Column("volume", Float, nullable=False),
)


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or settings.database_url)


def create_tables(engine: Engine) -> None:
    metadata.create_all(engine)


def save_candles(engine: Engine, symbol: str, timeframe: str, df: pd.DataFrame) -> int:
    """Mumları kaydeder (varsa günceller). Kaydedilen mum sayısını döndürür."""
    if df.empty:
        return 0

    rows = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "ts": ts.to_pydatetime(),
            **{col: float(row[col]) for col in CANDLE_COLUMNS},
        }
        for ts, row in df.iterrows()
    ]

    # PostgreSQL ve SQLite (testlerde kullanıyoruz) upsert'i aynı şekilde destekliyor.
    dialect = postgresql if engine.dialect.name == "postgresql" else sqlite
    stmt = dialect.insert(candles_table)
    stmt = stmt.on_conflict_do_update(
        index_elements=["symbol", "timeframe", "ts"],
        set_={col: stmt.excluded[col] for col in CANDLE_COLUMNS},
    )
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def load_candles(engine: Engine, symbol: str, timeframe: str, limit: int | None = None) -> pd.DataFrame:
    """Kayıtlı mumları eskiden yeniye sıralı döndürür. limit verilirse en son N mum."""
    query = (
        select(candles_table.c.ts, *[candles_table.c[col] for col in CANDLE_COLUMNS])
        .where(candles_table.c.symbol == symbol, candles_table.c.timeframe == timeframe)
        .order_by(candles_table.c.ts.desc())
    )
    if limit is not None:
        query = query.limit(limit)

    with engine.connect() as conn:
        df = pd.DataFrame(conn.execute(query).all(), columns=["ts", *CANDLE_COLUMNS])

    # SQLite saat dilimini saklamaz; kaydettiğimiz her şey UTC olduğu için UTC kabul ediyoruz.
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.set_index("ts").sort_index()
