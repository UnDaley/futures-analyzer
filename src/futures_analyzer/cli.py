"""Komut satırı aracı.

Örnekler:
    python -m futures_analyzer.cli fetch NQ                  # bütün zaman dilimleri
    python -m futures_analyzer.cli fetch NQ --timeframe 1h   # sadece 1h (+ 4h)
    python -m futures_analyzer.cli show NQ --timeframe 4h --limit 10
"""

import argparse
import logging

import pandas as pd

from futures_analyzer.data.ingest import FETCH_TIMEFRAMES, ingest
from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.providers.yahoo import YahooProvider
from futures_analyzer.data.storage import create_tables, get_engine, load_candles
from futures_analyzer.instruments import get_instrument


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


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="futures_analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Veriyi çek ve veritabanına kaydet")
    fetch.add_argument("symbol", help="Örn. NQ, ES, GC")
    fetch.add_argument("--timeframe", choices=FETCH_TIMEFRAMES, help="Boş bırakılırsa hepsi çekilir")
    fetch.set_defaults(func=cmd_fetch)

    show = sub.add_parser("show", help="Kayıtlı son mumları göster")
    show.add_argument("symbol")
    show.add_argument("--timeframe", choices=TIMEFRAMES, default="1h")
    show.add_argument("--limit", type=int, default=10)
    show.set_defaults(func=cmd_show)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
