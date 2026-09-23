"""Değerlendirilmiş analizlerin özet istatistikleri.

"AI güzel konuştu" başarı ölçütü değildir; burada sadece ölçülebilir sonuçlara bakılır:
- Bias'a göre: kaç analiz, 4 saatte yön isabeti, ortalama 4s / 1g getiri
- Skor aralıklarına göre: skor yükseldikçe getiri gerçekten artıyor mu?
- Senaryo sonuçları: tetiklenen senaryoların hedefe mi invalidation'a mı gittiği

Karşılaştırma için "baseline" satırı: bütün analizlerin ortalama getirisi (hiçbir sinyal kullanmadan).
"""

# Sınırlar bias kuralıyla aynı: |skor| >= 15 yönlü, < 15 nötr
SCORE_BUCKETS = ["<=-30", "-30..-15", "-15..15", "15..30", ">=30"]


def score_bucket(score: float) -> str:
    if score <= -30:
        return "<=-30"
    if score <= -15:
        return "-30..-15"
    if score < 15:
        return "-15..15"
    if score < 30:
        return "15..30"
    return ">=30"


def summarize(records: list[dict]) -> dict:
    """records: [{"bias", "score_total", "evaluation": {...}}, ...] (sadece complete olanlar sayılır)"""
    done = [r for r in records if r.get("evaluation") and r["evaluation"].get("complete")]
    return {
        "evaluated": len(done),
        "baseline": _group_stats(done),
        "by_bias": {bias: _group_stats([r for r in done if r["bias"] == bias]) for bias in ("bullish", "bearish", "neutral")},
        "by_score": {
            bucket: _group_stats([r for r in done if score_bucket(r["score_total"]) == bucket]) for bucket in SCORE_BUCKETS
        },
        "scenarios": _scenario_stats(done),
    }


def _group_stats(records: list[dict]) -> dict:
    if not records:
        return {"count": 0}
    returns_4h = [r["evaluation"]["returns"]["4h"] for r in records if r["evaluation"]["returns"]["4h"] is not None]
    returns_1d = [r["evaluation"]["returns"]["1d"] for r in records if r["evaluation"]["returns"]["1d"] is not None]
    hits = [r["evaluation"]["direction_correct"] for r in records if r["evaluation"]["direction_correct"] is not None]
    return {
        "count": len(records),
        "hit_rate_4h": round(sum(hits) / len(hits) * 100, 1) if hits else None,
        "avg_return_4h": _mean(returns_4h),
        "avg_return_1d": _mean(returns_1d),
    }


def _scenario_stats(records: list[dict]) -> dict:
    counts: dict[str, int] = {}
    primary_triggered = primary_target = 0
    for record in records:
        outcome = record["evaluation"]["scenario"]
        result = outcome.get("result", "unknown")
        counts[result] = counts.get(result, 0) + 1
        # Birincil senaryo (bias yönü) tetiklendiyse hedefe ulaştı mı?
        if record["bias"] in ("bullish", "bearish") and outcome.get("triggered") == record["bias"]:
            primary_triggered += 1
            primary_target += result == f"{record['bias']}_target"
    return {
        "outcomes": dict(sorted(counts.items())),
        "primary_triggered": primary_triggered,
        "primary_target_rate": round(primary_target / primary_triggered * 100, 1) if primary_triggered else None,
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None
