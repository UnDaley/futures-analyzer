import pytest

from futures_analyzer.ai.manual import MANUAL_MODEL, check_manual_report, manual_prompt
from futures_analyzer.ai.prompt import SYSTEM_PROMPT
from futures_analyzer.data.storage import load_report, save_report

SNAPSHOT = {
    "instrument": "NQ",
    "as_of": "2026-09-23T13:00:00+00:00",
    "price": 30941.0,
    "setup": {"status": "waiting_retest", "open_level": 30982.75},
    "history": {"stats": {}, "days": [{"date": f"2026-09-{day:02d}", "open_level": 30000.0 + day} for day in range(1, 21)]},
}


def test_manual_prompt_contains_instructions_and_data():
    text = manual_prompt(SNAPSHOT)

    assert SYSTEM_PROMPT in text
    assert "30982.75" in text
    assert "<market_data>" in text


def test_valid_report_is_saved_as_validated(engine):
    report_id = save_report(engine, SNAPSHOT)

    result = check_manual_report(engine, report_id, "PRICE: 30941.0\nDirenç: 30982.75")

    assert result == {"validated": True, "unknown_numbers": [], "correction": None}
    saved = load_report(engine, report_id)
    assert saved["report_text"].startswith("PRICE: 30941.0")
    assert saved["report_model"] == MANUAL_MODEL
    assert saved["report_validated"] is True


def test_invented_price_is_flagged_with_correction_text(engine):
    report_id = save_report(engine, SNAPSHOT)

    result = check_manual_report(engine, report_id, "Hedef 31250")

    assert result["validated"] is False
    assert result["unknown_numbers"] == ["31250"]
    assert "31250" in result["correction"]
    assert load_report(engine, report_id)["report_validated"] is False


def test_unknown_report_id(engine):
    with pytest.raises(ValueError):
        check_manual_report(engine, 999, "rapor")


def test_only_recent_history_days_count_as_known_prices(engine):
    # Claude'a yalnızca son 10 gün gider; daha eski günlerin fiyatları raporda "bilinmeyen" sayılır
    report_id = save_report(engine, SNAPSHOT)

    assert check_manual_report(engine, report_id, "Açılış 30001.0")["validated"] is True
    assert check_manual_report(engine, report_id, "Açılış 30015.0")["unknown_numbers"] == ["30015.0"]
