"""Claude entegrasyonu testleri. Gerçek API'ye bağlanmaz; sahte istemci kullanılır."""

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from futures_analyzer.ai.prompt import REPORT_HISTORY_DAYS, SYSTEM_PROMPT, build_user_message, report_data
from futures_analyzer.ai.report import FALLBACK_BETA, ReportError, generate_report
from futures_analyzer.ai.validation import find_unknown_prices, parse_numbers, snapshot_numbers

SNAPSHOT = {
    "instrument": "NQ",
    "price": 30941.0,
    "levels": {"resistance": [{"low": 30982.75, "high": 30982.75}], "support": [{"low": 30916.5, "high": 30916.5}]},
    "score": {"total": -20.9, "bias": "bearish"},
    "note": "Tetik 31000.0 seviyesi",
}


# --- Doğrulama ---

def test_parse_numbers_handles_separators():
    assert parse_numbers("30,941.25 ve 30.941 ve 30941.5 ve 4350.6") == [30941.25, 30941.0, 30941.5, 4350.6]


def test_snapshot_numbers_walks_nested_values_and_text():
    numbers = snapshot_numbers(SNAPSHOT)

    assert {30941.0, 30982.75, 30916.5, -20.9, 31000.0} <= numbers


def test_known_prices_pass():
    report = "Fiyat 30941.0. Direnç 30982.75, destek 30916.5. Skor -20.9 (olasılık değil). RSI 45."

    assert find_unknown_prices(report, SNAPSHOT, tick_size=0.25) == []


def test_invented_price_is_caught():
    report = "Direnç 30982.75, ardından 31250 hedeflenebilir."

    assert find_unknown_prices(report, SNAPSHOT, tick_size=0.25) == ["31250"]


def test_numbers_far_from_price_are_not_checked():
    # Yüzdeler, RSI, saatler fiyat aralığında değil
    assert find_unknown_prices("RSI 61, 35 dakika, %5.7, 2026", SNAPSHOT, tick_size=0.25) == []


def test_thousands_separator_version_of_known_price_passes():
    assert find_unknown_prices("Direnç 30,982.75", SNAPSHOT, tick_size=0.25) == []


# --- Prompt ---

def test_system_prompt_is_static_and_forbids_invention():
    assert "{" not in SYSTEM_PROMPT.replace("{INSTRUMENT}", "")  # tarih/saat gibi değişken içermez
    assert "uydurma" in SYSTEM_PROMPT or "JSON'da olmayan" in SYSTEM_PROMPT
    assert "tavsiyesi verme" in SYSTEM_PROMPT


def test_user_message_is_deterministic():
    a = build_user_message({"b": 1, "a": 2, "instrument": "NQ"})
    b = build_user_message({"a": 2, "instrument": "NQ", "b": 1})

    assert a == b


def test_report_data_keeps_only_recent_history_days():
    snapshot = {"instrument": "NQ", "history": {"stats": {"days": 30}, "days": [{"date": str(i)} for i in range(30)]}}

    data = report_data(snapshot)

    assert len(data["history"]["days"]) == REPORT_HISTORY_DAYS
    assert data["history"]["stats"] == {"days": 30}
    assert len(snapshot["history"]["days"]) == 30  # orijinal snapshot değişmez


# --- Sahte Claude istemcisi ---

@dataclass
class FakeClient:
    replies: list[str]
    stop_reason: str = "end_turn"
    calls: list[dict] = field(default_factory=list)

    @property
    def beta(self):
        return SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        text = self.replies[len(self.calls) - 1]
        message = SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
            stop_reason=self.stop_reason,
            model="claude-opus-5",
            usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=0),
        )
        return _Stream(message)


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


def test_report_request_shape():
    client = FakeClient(replies=["NQ MARKET ANALYSIS\nPRICE: 30941.0"])

    report = generate_report(SNAPSHOT, client=client, model="claude-opus-5")

    call = client.calls[0]
    assert call["model"] == "claude-opus-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["fallbacks"] == "default" and call["betas"] == [FALLBACK_BETA]
    assert call["system"][0]["text"] == SYSTEM_PROMPT
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert report["validated"] is True
    assert report["attempts"] == 1
    assert report["text"].startswith("NQ MARKET ANALYSIS")


def test_invented_level_triggers_one_correction():
    client = FakeClient(replies=["Hedef 31250", "Hedef 30982.75"])

    report = generate_report(SNAPSHOT, client=client)

    assert report["attempts"] == 2
    assert report["validated"] is True
    second_call_messages = client.calls[1]["messages"]
    assert second_call_messages[1]["role"] == "assistant"            # önceki yanıt geçmişe eklendi
    assert "31250" in second_call_messages[2]["content"]              # düzeltme isteği


def test_still_invented_after_correction_is_flagged_not_hidden():
    client = FakeClient(replies=["Hedef 31250", "Hedef 31300"])

    report = generate_report(SNAPSHOT, client=client)

    assert report["validated"] is False
    assert report["unknown_numbers"] == ["31300"]
    assert report["usage"]["input_tokens"] == 200


def test_refusal_raises():
    with pytest.raises(ReportError):
        generate_report(SNAPSHOT, client=FakeClient(replies=[""], stop_reason="refusal"))


def test_truncated_report_raises():
    with pytest.raises(ReportError):
        generate_report(SNAPSHOT, client=FakeClient(replies=["yarım"], stop_reason="max_tokens"))
