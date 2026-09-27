"""API anahtarı olmadan Claude raporu: kopyala-yapıştır akışı.

1. manual_prompt: talimatları ve veriyi tek metne koyar (claude.ai'ye yapıştırılır).
2. check_manual_report: claude.ai'den gelen raporu, kaydedilmiş snapshot'la karşılaştırır
   (veride olmayan fiyat var mı) ve raporu o kayda ekler.
"""

from sqlalchemy import Engine

from futures_analyzer.ai.prompt import SYSTEM_PROMPT, build_correction_message, build_user_message, report_data
from futures_analyzer.ai.validation import find_unknown_prices
from futures_analyzer.data.storage import load_report, update_report
from futures_analyzer.instruments import get_instrument

MANUAL_MODEL = "manuel (claude.ai)"


def manual_prompt(snapshot: dict) -> str:
    return (
        "Aşağıdaki talimatlara göre bir 10am modeli raporu yaz.\n\n"
        "<instructions>\n" + SYSTEM_PROMPT + "\n</instructions>\n\n" + build_user_message(snapshot)
    )


def check_manual_report(db: Engine, report_id: int, text: str) -> dict:
    """Dönüş: {"validated", "unknown_numbers", "correction"} (correction: Claude'a yapıştırılacak düzeltme isteği)"""
    record = load_report(db, report_id)
    if record is None:
        raise ValueError(f"#{report_id} numaralı kayıt bulunamadı")
    snapshot = record["snapshot"]
    tick_size = get_instrument(snapshot["instrument"]).tick_size

    unknown = find_unknown_prices(text, report_data(snapshot), tick_size)
    update_report(db, report_id, text.strip(), MANUAL_MODEL, validated=not unknown)
    return {
        "validated": not unknown,
        "unknown_numbers": unknown,
        "correction": build_correction_message(unknown) if unknown else None,
    }
