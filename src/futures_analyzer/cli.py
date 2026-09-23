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
    python -m futures_analyzer.cli report NQ                 # Claude raporu (kaydedilir)
    python -m futures_analyzer.cli prompt NQ                 # API anahtarı olmadan: claude.ai için prompt
    python -m futures_analyzer.cli check-report 12           # claude.ai raporunu yapıştır ve kontrol et
    python -m futures_analyzer.cli record                    # analizleri Claude'suz kaydet
    python -m futures_analyzer.cli evaluate                  # kayıtların sonuçlarını ölç
    python -m futures_analyzer.cli backtest NQ --days 30 --step 4h
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

from futures_analyzer.ai.manual import check_manual_report, manual_prompt
from futures_analyzer.ai.report import ReportError, generate_report
from futures_analyzer.analysis import load_market_data, market_snapshot
from futures_analyzer.evaluation.backtest import records_to_frame, run_backtest
from futures_analyzer.evaluation.journal import evaluate_pending, record_analysis
from futures_analyzer.evaluation.stats import summarize
from futures_analyzer.data.ingest import FETCH_TIMEFRAMES, ingest
from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.providers.yahoo import YahooProvider
from futures_analyzer.data.storage import create_tables, get_engine, load_analyses, load_candles
from futures_analyzer.instruments import INSTRUMENTS, INTERMARKET_ASSETS, get_instrument
from futures_analyzer.macro.ingest import ingest_macro
from futures_analyzer.news.engine import ingest_news
from futures_analyzer.refresh import refresh_all

# Terminale yapıştırılan metnin bittiğini bildiren tuşlar
END_OF_INPUT = "Ctrl+Z ve Enter" if os.name == "nt" else "Ctrl+D"


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
    """Bütün kontratlar, ilişkili varlıklar, makro veriler ve haberler; sonra sonuç ölçümü."""
    errors = refresh_all(get_engine())
    print("Tamamlandı." if not errors else f"Tamamlandı, {len(errors)} adımda hata var (yukarıya bakın).")


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


def cmd_report(args: argparse.Namespace) -> None:
    instrument = get_instrument(args.symbol)
    engine = get_engine()
    create_tables(engine)
    snapshot = market_snapshot(engine, instrument.symbol)
    try:
        report = generate_report(snapshot)
    except ReportError as error:
        print(f"Rapor üretilemedi: {error}")
        raise SystemExit(1)
    analysis_id = record_analysis(engine, snapshot, report)

    print(report["text"])
    print()
    print(f"-- kayıt #{analysis_id} | model: {report['model']} | deneme: {report['attempts']} | token: {report['usage']}")
    if not report["validated"]:
        print(f"!! UYARI: raporda veride olmayan sayılar var: {', '.join(report['unknown_numbers'])}")


def cmd_prompt(args: argparse.Namespace) -> None:
    """API anahtarı olmadan: talimat + veriyi dosyaya yazar, claude.ai'ye yapıştırılır."""
    instrument = get_instrument(args.symbol)
    engine = get_engine()
    create_tables(engine)
    snapshot = market_snapshot(engine, instrument.symbol)
    analysis_id = record_analysis(engine, snapshot)

    out = Path(args.out or f"prompts/{instrument.symbol}_{analysis_id}.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manual_prompt(snapshot), encoding="utf-8")
    print(f"Analiz #{analysis_id} kaydedildi. Prompt dosyası: {out}")
    print("1) Dosyanın içeriğinin tamamını claude.ai'de yeni bir sohbete yapıştırın.")
    print(f"2) Claude'un cevabını kopyalayın ve şu komutu çalıştırıp terminale yapıştırın (bitince {END_OF_INPUT}):")
    print(f"   uv run python -m futures_analyzer.cli check-report {analysis_id}")


def cmd_check_report(args: argparse.Namespace) -> None:
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"Dosya bulunamadı: {path}")
            print("Dosya adını kontrol edin veya dosya vermeden çalıştırıp raporu doğrudan terminale yapıştırın:")
            print(f"  uv run python -m futures_analyzer.cli check-report {args.id}")
            raise SystemExit(1)
        text = path.read_text(encoding="utf-8")
    else:
        print(f"Claude'un raporunu buraya yapıştırın. Bitince yeni bir satırda {END_OF_INPUT} tuşlarına basın:")
        text = sys.stdin.read()
    if not text.strip():
        print("Rapor boş; hiçbir şey kaydedilmedi.")
        raise SystemExit(1)
    try:
        result = check_manual_report(get_engine(), args.id, text)
    except ValueError as error:
        print(error)
        raise SystemExit(1)
    if result["validated"]:
        print(f"Rapor doğrulandı: bütün fiyatlar veride var. Analiz #{args.id} kaydına eklendi.")
        return
    print(f"UYARI: raporda veride olmayan fiyatlar var: {', '.join(result['unknown_numbers'])}")
    print("Rapor 'doğrulanmadı' olarak kaydedildi. Claude'a aynı sohbette şunu yazıp yeni raporu tekrar kontrol edin:\n")
    print(result["correction"])


def cmd_record(args: argparse.Namespace) -> None:
    """Claude olmadan, sadece deterministik analizi kaydeder (backtest günlüğü için)."""
    engine = get_engine()
    create_tables(engine)
    for symbol in [args.symbol] if args.symbol else INSTRUMENTS:
        snapshot = market_snapshot(engine, get_instrument(symbol).symbol)
        analysis_id = record_analysis(engine, snapshot)
        score = snapshot["score"]
        print(f"#{analysis_id} {symbol}: fiyat {snapshot['price']} | skor {score['total']} ({score['bias']})")


def cmd_evaluate(args: argparse.Namespace) -> None:
    engine = get_engine()
    create_tables(engine)
    print(f"{evaluate_pending(engine)} kayıt güncellendi (1 günlük sonucu tamamlanmayanlar sonra tekrar ölçülür)")
    print_summary(summarize(load_analyses(engine, args.symbol.upper() if args.symbol else None)))


def cmd_backtest(args: argparse.Namespace) -> None:
    instrument = get_instrument(args.symbol)
    data = load_market_data(get_engine(), instrument.symbol)
    end = pd.Timestamp.now(tz="UTC").floor("h") - pd.Timedelta(days=1)  # sonucu ölçülebilecek son an
    start = end - pd.Timedelta(days=args.days)

    def progress(done, total):
        if done % 20 == 0 or done == total:
            print(f"  {done}/{total}", flush=True)

    print(f"{instrument.symbol} backtest: {start:%Y-%m-%d %H:%M} -> {end:%Y-%m-%d %H:%M} UTC, adım {args.step}")
    records = run_backtest(data, start, end, pd.Timedelta(args.step), progress)
    print_summary(summarize(records))
    if args.csv:
        records_to_frame(records).to_csv(args.csv, index=False)
        print(f"Ayrıntılar: {args.csv}")


def print_summary(summary: dict) -> None:
    print(f"\nDeğerlendirilen analiz: {summary['evaluated']}")
    print(f"{'grup':<16}{'adet':>6}{'isabet 4s %':>13}{'ort. 4s %':>11}{'ort. 1g %':>11}")
    rows = [("hepsi (baseline)", summary["baseline"])]
    rows += [(f"bias {k}", v) for k, v in summary["by_bias"].items()]
    rows += [(f"skor {k}", v) for k, v in summary["by_score"].items()]
    for name, stats in rows:
        print(f"{name:<16}{stats['count']:>6}{_fmt(stats.get('hit_rate_4h')):>13}"
              f"{_fmt(stats.get('avg_return_4h')):>11}{_fmt(stats.get('avg_return_1d')):>11}")
    scenarios = summary["scenarios"]
    print(f"Senaryo sonuçları: {scenarios['outcomes']}")
    print(f"Birincil senaryo tetiklendi: {scenarios['primary_triggered']}, hedefe ulaşma %: {_fmt(scenarios['primary_target_rate'])}")


def _fmt(value) -> str:
    return "-" if value is None else f"{value:g}"


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

    report = sub.add_parser("report", help="Claude ile analiz raporu üret (ANTHROPIC_API_KEY gerekir)")
    report.add_argument("symbol")
    report.set_defaults(func=cmd_report)

    prompt = sub.add_parser("prompt", help="API anahtarı olmadan: claude.ai'ye yapıştırılacak prompt dosyası üret")
    prompt.add_argument("symbol")
    prompt.add_argument("--out", help="Dosya yolu (varsayılan: prompts/<sembol>_<kayıt no>.txt)")
    prompt.set_defaults(func=cmd_prompt)

    check = sub.add_parser("check-report", help="claude.ai'den gelen raporu kontrol et ve analize ekle")
    check.add_argument("id", type=int, help="prompt komutunun verdiği analiz numarası")
    check.add_argument("file", nargs="?", help="Raporun kaydedildiği dosya (verilmezse rapor terminale yapıştırılır)")
    check.set_defaults(func=cmd_check_report)

    record = sub.add_parser("record", help="Analizi (Claude olmadan) kaydet; sembol verilmezse hepsi")
    record.add_argument("symbol", nargs="?")
    record.set_defaults(func=cmd_record)

    evaluate = sub.add_parser("evaluate", help="Kayıtlı analizlerin sonuçlarını ölç ve özetle")
    evaluate.add_argument("symbol", nargs="?")
    evaluate.set_defaults(func=cmd_evaluate)

    backtest = sub.add_parser("backtest", help="Geçmişe dönük backtest (Claude kullanılmaz)")
    backtest.add_argument("symbol")
    backtest.add_argument("--days", type=int, default=30, help="Kaç gün geriye (en fazla ~55)")
    backtest.add_argument("--step", default="4h", help="Analiz aralığı, örn. 1h, 4h")
    backtest.add_argument("--csv", help="Ayrıntıları bu CSV dosyasına yaz")
    backtest.set_defaults(func=cmd_backtest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
