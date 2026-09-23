"""API anahtarı olmadan Claude raporu: kopyala-yapıştır akışı.

1. manual_prompt: talimatları ve veriyi tek metne koyar (claude.ai'ye yapıştırılır).
2. check_manual_report: claude.ai'den gelen raporu, analizin kaydedilmiş snapshot'ıyla karşılaştırır
   (veride olmayan fiyat var mı) ve raporu o analiz kaydına ekler.
"""

from sqlalchemy import Engine

from futures_analyzer.ai.prompt import SYSTEM_PROMPT, build_correction_message, build_user_message
from futures_analyzer.ai.validation import find_unknown_prices
from futures_analyzer.data.storage import load_analysis, update_report
from futures_analyzer.instruments import get_instrument

MANUAL_MODEL = "manuel (claude.ai)"


def manual_prompt(snapshot: dict) -> str:
    return (
        "Aşağıdaki talimatlara göre bir piyasa analiz raporu yaz.\n\n"
        "<instructions>\n" + SYSTEM_PROMPT + "\n</instructions>\n\n" + build_user_message(snapshot)
    )


def check_manual_report(db: Engine, analysis_id: int, text: str) -> dict:
    """Dönüş: {"validated", "unknown_numbers", "correction"} (correction: Claude'a yapıştırılacak düzeltme isteği)"""
    analysis = load_analysis(db, analysis_id)
    if analysis is None:
        raise ValueError(f"#{analysis_id} numaralı analiz bulunamadı")
    snapshot = analysis["snapshot"]
    tick_size = get_instrument(snapshot["instrument"]).tick_size

    unknown = find_unknown_prices(text, snapshot, tick_size)
    update_report(db, analysis_id, text.strip(), MANUAL_MODEL, validated=not unknown)
    return {
        "validated": not unknown,
        "unknown_numbers": unknown,
        "correction": build_correction_message(unknown) if unknown else None,
    }
