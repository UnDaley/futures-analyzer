"""Geçmişe dönük backtest: analiz motoru geçmişteki anlara "o anda bilinen veriyle" uygulanır.

- Her adımda sadece o andan önce başlamış mumlar kullanılır (build_snapshot); sonuç ise
  sonraki 5 dakikalık mumlarla ölçülür (outcomes.evaluate).
- Claude kullanılmaz: ölçülen şey deterministik skor ve senaryolardır.
- Haberler dahil edilmez (geçmiş haber akışı saklanmıyor); makro seriler gözlem tarihine göre
  filtrelenir. Aylık veriler (CPI vb.) gerçekte ay sonrasında yayınlandığı için makro tarafında
  küçük bir "geleceği görme" payı vardır.
- 5 dakikalık veri yfinance'te ~60 gün olduğu için backtest en fazla ~55 gün geriye gidebilir.
"""

import pandas as pd

from futures_analyzer.analysis import MarketData, build_snapshot
from futures_analyzer.evaluation.outcomes import evaluate
from futures_analyzer.market_time import is_market_open

# Hız için her zaman diliminin son N mumu kullanılır (EMA 200 ve seviyeler için yeterli)
MAX_BARS = 1500


def run_backtest(data: MarketData, start: pd.Timestamp, end: pd.Timestamp, step: pd.Timedelta, progress=None) -> list[dict]:
    five_min = data.candles["5m"]
    records = []
    times = [t for t in pd.date_range(start, end, freq=step) if is_market_open(t)]

    for number, as_of in enumerate(times, start=1):
        snapshot = build_snapshot(data, as_of, news=None, max_bars=MAX_BARS)
        if snapshot["price"] is None or snapshot["scenarios"] is None:
            continue
        score = snapshot["score"]
        records.append({
            "as_of": as_of,
            "price": snapshot["price"],
            "bias": score["bias"],
            "score_total": score["total"],
            "coverage": score["coverage"],
            "components": {name: c["points"] for name, c in score["components"].items()},
            "evaluation": evaluate(five_min, as_of, snapshot["price"], score["bias"], snapshot["scenarios"]),
        })
        if progress:
            progress(number, len(times))
    return records


def records_to_frame(records: list[dict]) -> pd.DataFrame:
    """CSV'ye yazmak için düz tablo."""
    rows = []
    for record in records:
        evaluation = record["evaluation"]
        rows.append({
            "as_of": record["as_of"].isoformat(),
            "price": record["price"],
            "bias": record["bias"],
            "score_total": record["score_total"],
            "coverage": record["coverage"],
            **{f"pts_{name}": value for name, value in record["components"].items()},
            **{f"ret_{name}": value for name, value in evaluation["returns"].items()},
            "direction_correct": evaluation["direction_correct"],
            "scenario_result": evaluation["scenario"].get("result"),
        })
    return pd.DataFrame(rows)
