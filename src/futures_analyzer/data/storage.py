"""Mumları veritabanına kaydeder ve okur.

Tablo: candles (symbol, timeframe, ts) birincil anahtar.
Aynı mum tekrar kaydedilirse satır çoğalmaz, değerleri güncellenir (upsert).
Bu sayede henüz kapanmamış son mum da sonraki çekişte düzelir.
"""

import pandas as pd
from sqlalchemy import JSON, Column, DateTime, Engine, Float, MetaData, String, Table, create_engine, select
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


# --- Makro seriler (FRED) ---

macro_table = Table(
    "macro_series",
    metadata,
    Column("series_id", String(32), primary_key=True),
    Column("date", DateTime, primary_key=True),
    Column("value", Float, nullable=False),
)


def save_macro_series(engine: Engine, series_id: str, series: pd.Series) -> int:
    """Makro seriyi kaydeder (varsa günceller). Kaydedilen satır sayısını döndürür."""
    if series.empty:
        return 0
    rows = [{"series_id": series_id, "date": date.to_pydatetime(), "value": float(value)} for date, value in series.items()]
    dialect = postgresql if engine.dialect.name == "postgresql" else sqlite
    stmt = dialect.insert(macro_table)
    stmt = stmt.on_conflict_do_update(index_elements=["series_id", "date"], set_={"value": stmt.excluded.value})
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def load_macro_series(engine: Engine, series_id: str) -> pd.Series:
    query = (
        select(macro_table.c.date, macro_table.c.value)
        .where(macro_table.c.series_id == series_id)
        .order_by(macro_table.c.date)
    )
    with engine.connect() as conn:
        rows = conn.execute(query).all()
    if not rows:
        return pd.Series(dtype=float)
    dates, values = zip(*rows)
    return pd.Series(values, index=pd.DatetimeIndex(dates, name="date"), dtype=float)


# --- Ekonomik takvim ve haberler ---

events_table = Table(
    "economic_events",
    metadata,
    Column("title", String(200), primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    Column("impact", String(16), nullable=False),
    Column("forecast", String(32)),
    Column("previous", String(32)),
)

news_table = Table(
    "news_items",
    metadata,
    Column("id", String(32), primary_key=True),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("source", String(64), nullable=False),
    Column("title", String(500), nullable=False),
    Column("link", String(500)),
    Column("analysis", JSON),
)


def _upsert(engine: Engine, table: Table, rows: list[dict], keys: list[str]) -> int:
    if not rows:
        return 0
    dialect = postgresql if engine.dialect.name == "postgresql" else sqlite
    stmt = dialect.insert(table)
    update = {c.name: stmt.excluded[c.name] for c in table.columns if c.name not in keys}
    stmt = stmt.on_conflict_do_update(index_elements=keys, set_=update)
    with engine.begin() as conn:
        conn.execute(stmt, rows)
    return len(rows)


def save_events(engine: Engine, events: list[dict]) -> int:
    rows = [{**e, "ts": e["ts"].to_pydatetime()} for e in events]
    return _upsert(engine, events_table, rows, ["title", "ts"])


def load_events(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(select(events_table).order_by(events_table.c.ts)).mappings().all()
    return [{**row, "ts": _as_utc(row["ts"])} for row in rows]


def save_news(engine: Engine, items: list[dict]) -> int:
    rows = [{**item, "ts": item["ts"].to_pydatetime()} for item in items]
    return _upsert(engine, news_table, rows, ["id"])


def load_news(engine: Engine, since: pd.Timestamp) -> list[dict]:
    query = select(news_table).where(news_table.c.ts >= since.to_pydatetime()).order_by(news_table.c.ts.desc())
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
    return [{**row, "ts": _as_utc(row["ts"])} for row in rows]


def _as_utc(value) -> pd.Timestamp:
    """SQLite saat dilimini saklamaz; kaydettiğimiz her şey UTC olduğu için UTC kabul ediyoruz."""
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")
