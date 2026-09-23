"""Analiz günlüğü: her analizi kaydeder, zamanı gelince sonucunu ölçer."""

import pandas as pd
from sqlalchemy import Engine

from futures_analyzer.data.storage import load_analyses, load_candles, save_analysis, update_evaluation
from futures_analyzer.evaluation.outcomes import evaluate


def record_analysis(db: Engine, snapshot: dict, report: dict | None = None) -> int:
    """Snapshot'ı (ve varsa Claude raporunu) kaydeder. Kayıt numarasını döndürür."""
    score = snapshot["score"]
    return save_analysis(db, {
        "created_at": pd.Timestamp.now(tz="UTC").to_pydatetime(),
        "as_of": pd.Timestamp(snapshot["as_of"]).to_pydatetime(),
        "instrument": snapshot["instrument"],
        "price": snapshot["price"],
        "bias": score["bias"],
        "score_total": score["total"],
        "coverage": score["coverage"],
        "scenarios": snapshot["scenarios"],
        "snapshot": snapshot,
        "report_text": report["text"] if report else None,
        "report_model": report["model"] if report else None,
        "report_validated": report["validated"] if report else None,
    })


def evaluate_pending(db: Engine) -> int:
    """Sonucu henüz tamamlanmamış kayıtları değerlendirir. Güncellenen kayıt sayısını döndürür."""
    records = [r for r in load_analyses(db) if not (r["evaluation"] or {}).get("complete")]
    five_min_cache: dict[str, pd.DataFrame] = {}
    updated = 0
    for record in records:
        symbol = record["instrument"]
        if symbol not in five_min_cache:
            five_min_cache[symbol] = load_candles(db, symbol, "5m")
        if record["price"] is None:
            continue
        result = evaluate(five_min_cache[symbol], record["as_of"], record["price"], record["bias"], record["scenarios"])
        update_evaluation(db, record["id"], result)
        updated += 1
    return updated
