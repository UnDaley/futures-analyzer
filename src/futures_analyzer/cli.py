"""Komut satırı aracı.

Örnekler:
    python -m futures_analyzer.cli fetch NQ                  # bütün zaman dilimleri
    python -m futures_analyzer.cli fetch NQ --timeframe 1h   # sadece 1h (+ 4h)
    python -m futures_analyzer.cli show NQ --timeframe 4h --limit 10
    python -m futures_analyzer.cli fetch-news                # ekonomik takvim
    python -m futures_analyzer.cli fetch-all                 # hepsi
    python -m futures_analyzer.cli snapshot NQ               # bugünkü 10am setup'ı (JSON)
    python -m futures_analyzer.cli history NQ --days 60      # son günlerin 10am sonuçları
    python -m futures_analyzer.cli report NQ                 # Claude raporu (kaydedilir)
    python -m futures_analyzer.cli prompt NQ                 # API anahtarı olmadan: claude.ai için prompt
    python -m futures_analyzer.cli check-report 12           # claude.ai raporunu yapıştır ve kontrol et
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
from futures_analyzer.analysis import market_snapshot, price_text
from futures_analyzer.data.ingest import FETCH_TIMEFRAMES, ingest
from futures_analyzer.data.providers.base import TIMEFRAMES
from futures_analyzer.data.providers.yahoo import YahooProvider
from futures_analyzer.data.storage import create_tables, get_engine, load_candles, save_report
from futures_analyzer.instruments import get_instrument
from futures_analyzer.market_time import NEW_YORK
from futures_analyzer.news.engine import ingest_news
from futures_analyzer.refresh import refresh_all
from futures_analyzer.strategy.ten_am import recent_days, summarize

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


def cmd_fetch_news(args: argparse.Namespace) -> None:
    engine = get_engine()
    create_tables(engine)
    print(f"{ingest_news(engine)['events']} takvim olayı kaydedildi")


def cmd_fetch_all(args: argparse.Namespace) -> None:
    """Bütün kontratların mumları ve ekonomik takvim."""
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
    report_id = save_report(engine, snapshot, report)

    print(report["text"])
    print()
    print(f"-- kayıt #{report_id} | model: {report['model']} | deneme: {report['attempts']} | token: {report['usage']}")
    if not report["validated"]:
        print(f"!! UYARI: raporda veride olmayan sayılar var: {', '.join(report['unknown_numbers'])}")


def cmd_prompt(args: argparse.Namespace) -> None:
    """API anahtarı olmadan: talimat + veriyi dosyaya yazar, claude.ai'ye yapıştırılır."""
    instrument = get_instrument(args.symbol)
    engine = get_engine()
    create_tables(engine)
    snapshot = market_snapshot(engine, instrument.symbol)
    report_id = save_report(engine, snapshot)

    out = Path(args.out or f"prompts/{instrument.symbol}_{report_id}.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manual_prompt(snapshot), encoding="utf-8")
    print(f"Kayıt #{report_id} oluşturuldu. Prompt dosyası: {out}")
    print("1) Dosyanın içeriğinin tamamını claude.ai'de yeni bir sohbete yapıştırın.")
    print(f"2) Claude'un cevabını kopyalayın ve şu komutu çalıştırıp terminale yapıştırın (bitince {END_OF_INPUT}):")
    print(f"   uv run python -m futures_analyzer.cli check-report {report_id}")


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
        print(f"Rapor doğrulandı: bütün fiyatlar veride var. #{args.id} kaydına eklendi.")
        return
    print(f"UYARI: raporda veride olmayan fiyatlar var: {', '.join(result['unknown_numbers'])}")
    print("Rapor 'doğrulanmadı' olarak kaydedildi. Claude'a aynı sohbette şunu yazıp yeni raporu tekrar kontrol edin:\n")
    print(result["correction"])


def cmd_history(args: argparse.Namespace) -> None:
    """Son günlerin 10am modeli sonuçları ve istatistikleri."""
    instrument = get_instrument(args.symbol)
    five_min = load_candles(get_engine(), instrument.symbol, "5m")
    results = recent_days(five_min, instrument, pd.Timestamp.now(tz="UTC"), args.days)
    if not results:
        print(f"{instrument.symbol} için 5M veri yok. Önce 'fetch' çalıştırın.")
        return

    def p(value: float | None) -> str:
        return "-" if value is None else price_text(value, instrument.tick_size)

    print(f"{'tarih':<12}{'yön':<7}{'açılış':>11}{'giriş (NY)':>12}{'stop':>11}{'hedef':>11}{'R':>7}  sonuç")
    for r in reversed(results):
        entry_time = pd.Timestamp(r["entry"]["ts"]).tz_convert(NEW_YORK).strftime("%H:%M") if r["entry"] else "-"
        target = r["target"]["price"] if r["target"] else None
        r_text = "-" if r["r_multiple"] is None else f"{r['r_multiple']:+.2f}"
        direction = r["direction"] if r["entry"] else "-"
        print(f"{r['date']:<12}{direction:<7}{p(r['open_level']):>11}{entry_time:>12}"
              f"{p(r['stop']):>11}{p(target):>11}{r_text:>7}  {r['status_text']}")
    print_stats(summarize(results))
    if args.csv:
        pd.DataFrame([_flat(r) for r in results]).to_csv(args.csv, index=False)
        print(f"Ayrıntılar: {args.csv}")


def print_stats(stats: dict) -> None:
    print(f"\n{stats['days']} gün, {stats['setups']} setup ({stats['no_setup']} gün setup yok)")
    print(f"Hedef: {stats['wins']}  Stop: {stats['losses']}  Belirsiz: {stats['ambiguous']}  16:00 kapanış: {stats['time_exits']}")
    print(f"Kazanma oranı: {_pct(stats['win_rate'])}  Ortalama R: {_fmt(stats['avg_r'])}  Toplam R: {_fmt(stats['total_r'])}")
    print(f"Long: {stats['long']['setups']} setup, {_pct(stats['long']['win_rate'])}  "
          f"Short: {stats['short']['setups']} setup, {_pct(stats['short']['win_rate'])}")


def _flat(result: dict) -> dict:
    return {
        "date": result["date"],
        "status": result["status"],
        "direction": result["direction"],
        "open_level": result["open_level"],
        "manipulation_extreme": result["manipulation"]["extreme"] if result["manipulation"] else None,
        "entry": result["entry"]["price"] if result["entry"] else None,
        "entry_ts": result["entry"]["ts"] if result["entry"] else None,
        "stop": result["stop"],
        "target": result["target"]["price"] if result["target"] else None,
        "target_source": result["target"]["source"] if result["target"] else None,
        "exit_ts": result["exit"]["ts"] if result["exit"] else None,
        "r_multiple": result["r_multiple"],
    }


def _pct(value) -> str:
    return "-" if value is None else f"%{value:g}"


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

    news = sub.add_parser("fetch-news", help="Ekonomik takvimi çek")
    news.set_defaults(func=cmd_fetch_news)

    fetch_all = sub.add_parser("fetch-all", help="Her şeyi çek: kontratların mumları ve ekonomik takvim")
    fetch_all.set_defaults(func=cmd_fetch_all)

    show = sub.add_parser("show", help="Kayıtlı son mumları göster")
    show.add_argument("symbol")
    show.add_argument("--timeframe", choices=TIMEFRAMES, default="1h")
    show.add_argument("--limit", type=int, default=10)
    show.set_defaults(func=cmd_show)

    snapshot = sub.add_parser("snapshot", help="Bugünkü 10am setup'ı, seviyeler ve geçmiş (JSON)")
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
    check.add_argument("id", type=int, help="prompt komutunun verdiği kayıt numarası")
    check.add_argument("file", nargs="?", help="Raporun kaydedildiği dosya (verilmezse rapor terminale yapıştırılır)")
    check.set_defaults(func=cmd_check_report)

    history = sub.add_parser("history", help="Son günlerin 10am modeli sonuçları (Claude kullanılmaz)")
    history.add_argument("symbol")
    history.add_argument("--days", type=int, default=60, help="Kaç işlem günü geriye")
    history.add_argument("--csv", help="Ayrıntıları bu CSV dosyasına yaz")
    history.set_defaults(func=cmd_history)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
