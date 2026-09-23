import pytest

from futures_analyzer.ai.manual import MANUAL_MODEL, check_manual_report, manual_prompt
from futures_analyzer.ai.prompt import SYSTEM_PROMPT
from futures_analyzer.data.storage import load_analysis
from futures_analyzer.evaluation.journal import record_analysis

SNAPSHOT = {
    "instrument": "NQ",
    "as_of": "2026-09-23T13:00:00+00:00",
    "price": 30941.0,
    "levels": {"resistance": [{"low": 30982.75, "high": 30982.75}]},
    "score": {"bias": "bearish", "total": -20.9, "coverage": 100},
    "scenarios": None,
}


def test_manual_prompt_contains_instructions_and_data():
    text = manual_prompt(SNAPSHOT)

    assert SYSTEM_PROMPT in text
    assert "30982.75" in text
    assert "<market_data>" in text


def test_valid_report_is_saved_as_validated(engine):
    analysis_id = record_analysis(engine, SNAPSHOT)

    result = check_manual_report(engine, analysis_id, "PRICE: 30941.0\nDirenç: 30982.75")

    assert result == {"validated": True, "unknown_numbers": [], "correction": None}
    saved = load_analysis(engine, analysis_id)
    assert saved["report_text"].startswith("PRICE: 30941.0")
    assert saved["report_model"] == MANUAL_MODEL
    assert saved["report_validated"] is True


def test_invented_price_is_flagged_with_correction_text(engine):
    analysis_id = record_analysis(engine, SNAPSHOT)

    result = check_manual_report(engine, analysis_id, "Hedef 31250")

    assert result["validated"] is False
    assert result["unknown_numbers"] == ["31250"]
    assert "31250" in result["correction"]
    assert load_analysis(engine, analysis_id)["report_validated"] is False


def test_unknown_analysis_id(engine):
    with pytest.raises(ValueError):
        check_manual_report(engine, 999, "rapor")
