"""Komut satırı aracı.

Örnekler:
    python -m futures_analyzer.cli fetch NQ                  # bütün zaman dilimleri
    python -m futures_analyzer.cli fetch NQ --timeframe 1h   # sadece 1h (+ 4h)
    python -m futures_analyzer.cli show NQ --timeframe 4h --limit 10
    python -m futures_analyzer.cli fetch-intermarket
    python -m futures_analyzer.cli fetch-macro
    python -m futures_analyzer.cli fetch-news
    python -m futures_analyzer.cli fetch-all                 # hepsi
    python -m futures_analyzer.cli snapshot NQ
"""

import argparse
import json
import logging

import pandas as pd

from futures_analyzer.analysis import market_snapshot
from futures_analyzer.data.ingest import FETCH_TIMEFRAMES, ingest
from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.providers.yahoo import YahooProvider
from futures_analyzer.data.storage import create_tables, get_engine, load_candles
from futures_analyzer.instruments import INSTRUMENTS, INTERMARKET_ASSETS, get_instrument
from futures_analyzer.macro.ingest import ingest_macro
from futures_analyzer.news.engine import ingest_news


def cmd_fetch(args: argparse.Namespace) -> None:
    instrument = get_instrument(args.symbol)
    engine = get_engine()
    create_tables(engine)
    provider = YahooProvider()

    timeframes = [args.timeframe] if args.timeframe else FETCH_TIMEFRAMES
    for timeframe in timeframes:
        saved = ingest(engine, provider, instrument, timeframe)
        for tf, count in saved.items():
            print(f"{instrument.symbol} {tf}: {count} mum kaydedildi")


def cmd_fetch_intermarket(args: argparse.Namespace) -> None:
    engine = get_engine()
    create_tables(engine)
    provider = YahooProvider()
    for asset in INTERMARKET_ASSETS.values():
        try:
            saved = ingest(engine, provider, asset, "1h")
            print(f"{asset.symbol}: {saved['1h']} mum kaydedildi")
        except Exception as error:
            print(f"{asset.symbol}: HATA ({error})")


def cmd_fetch_macro(args: argparse.Namespace) -> None:
    engine = get_engine()
    create_tables(engine)
    for name, count in ingest_macro(engine).items():
        print(f"{name}: {'HATA' if count < 0 else f'{count} değer kaydedildi'}")


def cmd_fetch_news(args: argparse.Namespace) -> None:
    engine = get_engine()
    create_tables(engine)
    saved = ingest_news(engine)
    print(f"{saved['news']} haber, {saved['events']} takvim olayı kaydedildi")


def cmd_fetch_all(args: argparse.Namespace) -> None:
    """Bütün kontratlar, ilişkili varlıklar, makro veriler ve haberler."""
    for symbol in INSTRUMENTS:
        cmd_fetch(argparse.Namespace(symbol=symbol, timeframe=None))
    cmd_fetch_intermarket(args)
    cmd_fetch_macro(args)
    cmd_fetch_news(args)


def cmd_show(args: argparse.Namespace) -> None:
    instrument = get_instrument(args.symbol)
    df = load_candles(get_engine(), instrument.symbol, args.timeframe, limit=args.limit)
    if df.empty:
        print(f"{instrument.symbol} {args.timeframe} için kayıt yok. Önce 'fetch' çalıştırın.")
        return
    # Okumayı kolaylaştırmak için New York saatini de gösteriyoruz
    df.insert(0, "ny_time", df.index.tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M"))
    with pd.option_context("display.width", 200, "display.max_columns", None):
        print(df)


def cmd_snapshot(args: argparse.Namespace) -> None:
    instrument = get_instrument(args.symbol)
    snapshot = market_snapshot(get_engine(), instrument.symbol)
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="futures_analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Veriyi çek ve veritabanına kaydet")
    fetch.add_argument("symbol", help="Örn. NQ, ES, GC")
    fetch.add_argument("--timeframe", choices=FETCH_TIMEFRAMES, help="Boş bırakılırsa hepsi çekilir")
    fetch.set_defaults(func=cmd_fetch)

    intermarket = sub.add_parser("fetch-intermarket", help="İlişkili varlıkları (YM, RTY, DXY, US10Y, VIX, SI) çek")
    intermarket.set_defaults(func=cmd_fetch_intermarket)

    macro = sub.add_parser("fetch-macro", help="Makro verileri FRED'den çek")
    macro.set_defaults(func=cmd_fetch_macro)

    news = sub.add_parser("fetch-news", help="Haberleri ve ekonomik takvimi çek")
    news.set_defaults(func=cmd_fetch_news)

    fetch_all = sub.add_parser("fetch-all", help="Her şeyi çek: kontratlar, intermarket, makro, haberler")
    fetch_all.set_defaults(func=cmd_fetch_all)

    show = sub.add_parser("show", help="Kayıtlı son mumları göster")
    show.add_argument("symbol")
    show.add_argument("--timeframe", choices=TIMEFRAMES, default="1h")
    show.add_argument("--limit", type=int, default=10)
    show.set_defaults(func=cmd_show)

    snapshot = sub.add_parser("snapshot", help="Her zaman dilimi için göstergeler ve market structure (JSON)")
    snapshot.add_argument("symbol")
    snapshot.set_defaults(func=cmd_snapshot)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
