"""Veritabanı tabloları ve okuma / yazma fonksiyonları.

- candles: mumlar, (symbol, timeframe, ts) birincil anahtar
- economic_events: ekonomik takvim
- reports: Claude raporları ve rapor anındaki snapshot

Mumlar ve olaylar tekrar kaydedilirse satır çoğalmaz, güncellenir (upsert).
Bu sayede henüz kapanmamış son mum da sonraki çekişte düzelir.
"""

import pandas as pd
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
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


# --- Ekonomik takvim ---

events_table = Table(
    "economic_events",
    metadata,
    Column("title", String(200), primary_key=True),
    Column("ts", DateTime(timezone=True), primary_key=True),
    Column("impact", String(16), nullable=False),
    Column("forecast", String(32)),
    Column("previous", String(32)),
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


def _as_utc(value) -> pd.Timestamp:
    """SQLite saat dilimini saklamaz; kaydettiğimiz her şey UTC olduğu için UTC kabul ediyoruz."""
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tz is None else ts.tz_convert("UTC")


# --- Claude raporları ---

reports_table = Table(
    "reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("as_of", DateTime(timezone=True), nullable=False),
    Column("instrument", String(16), nullable=False),
    Column("price", Float),
    Column("setup_status", String(32)),
    Column("snapshot", JSON),
    Column("report_text", Text),
    Column("report_model", String(64)),
    Column("report_validated", Boolean),
)


def save_report(engine: Engine, snapshot: dict, report: dict | None = None) -> int:
    """Snapshot'ı (ve varsa Claude raporunu) kaydeder. Kayıt numarasını döndürür."""
    row = {
        "created_at": pd.Timestamp.now(tz="UTC").to_pydatetime(),
        "as_of": pd.Timestamp(snapshot["as_of"]).to_pydatetime(),
        "instrument": snapshot["instrument"],
        "price": snapshot["price"],
        "setup_status": snapshot["setup"]["status"],
        "snapshot": snapshot,
        "report_text": report["text"] if report else None,
        "report_model": report["model"] if report else None,
        "report_validated": report["validated"] if report else None,
    }
    with engine.begin() as conn:
        result = conn.execute(reports_table.insert().values(**row))
        return int(result.inserted_primary_key[0])


def load_reports(engine: Engine, instrument: str | None = None, limit: int | None = None) -> list[dict]:
    """Rapor metni olan kayıtlar, yeniden eskiye."""
    query = select(reports_table).where(reports_table.c.report_text.is_not(None)).order_by(reports_table.c.as_of.desc())
    if instrument:
        query = query.where(reports_table.c.instrument == instrument)
    if limit:
        query = query.limit(limit)
    with engine.connect() as conn:
        rows = conn.execute(query).mappings().all()
    return [_report_row(row) for row in rows]


def load_report(engine: Engine, report_id: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(select(reports_table).where(reports_table.c.id == report_id)).mappings().first()
    return _report_row(row) if row is not None else None


def update_report(engine: Engine, report_id: int, text: str, model: str, validated: bool) -> None:
    stmt = (
        reports_table.update()
        .where(reports_table.c.id == report_id)
        .values(report_text=text, report_model=model, report_validated=validated)
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def _report_row(row) -> dict:
    return {**row, "as_of": _as_utc(row["as_of"]), "created_at": _as_utc(row["created_at"])}
