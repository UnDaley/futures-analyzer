"""Claude ile analiz raporu üretir.

Akış:
1. Snapshot JSON'u sabit system prompt ile Claude'a gönderilir.
2. Rapordaki fiyatlar snapshot'la karşılaştırılır (validation.py).
3. Veride olmayan fiyat varsa Claude'dan bir kez düzeltmesi istenir. Hâlâ varsa rapor
   "doğrulanmadı" olarak işaretlenir ve bilinmeyen sayılar listelenir; sessizce kabul edilmez.

Model: varsayılan claude-opus-5 (ayarlardaki ANTHROPIC_MODEL ile değiştirilebilir).
Güvenlik sınıflandırıcısı isteği reddederse sunucu tarafı fallback (`fallbacks: "default"`)
isteği otomatik olarak uygun başka bir modelde tekrar çalıştırır.
"""

import anthropic

from futures_analyzer.ai.prompt import SYSTEM_PROMPT, build_correction_message, build_user_message
from futures_analyzer.ai.validation import find_unknown_prices
from futures_analyzer.config import settings
from futures_analyzer.instruments import get_instrument

MAX_TOKENS = 32000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ReportError(Exception):
    """Rapor üretilemedi (anahtar yok, ağ hatası, reddedildi, yarım kaldı...)."""


def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else anthropic.Anthropic()


def generate_report(snapshot: dict, client=None, model: str | None = None) -> dict:
    """Dönüş: {"text", "model", "validated", "unknown_numbers", "attempts", "usage"}"""
    client = client or make_client()
    model = model or settings.anthropic_model
    tick_size = get_instrument(snapshot["instrument"]).tick_size

    messages = [{"role": "user", "content": build_user_message(snapshot)}]
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}

    for attempt in (1, 2):
        response = _call(client, model, messages)
        _add_usage(usage, response.usage)
        text = "".join(block.text for block in response.content if block.type == "text").strip()

        unknown = find_unknown_prices(text, snapshot, tick_size)
        if not unknown or attempt == 2:
            return {
                "text": text,
                "model": response.model,
                "validated": not unknown,
                "unknown_numbers": unknown,
                "attempts": attempt,
                "usage": usage,
            }
        # Yanıtın tamamını (thinking blokları dahil) geçmişe ekleyip düzeltme istiyoruz
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": build_correction_message(unknown)})

    raise AssertionError("ulaşılamaz")


def _call(client, model: str, messages: list):
    try:
        with client.beta.messages.stream(
            model=model,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError as error:
        raise ReportError("Claude API anahtarı geçersiz veya tanımlı değil (ANTHROPIC_API_KEY).") from error
    except anthropic.PermissionDeniedError as error:
        raise ReportError(f"API anahtarının bu modele erişimi yok: {error.message}") from error
    except anthropic.NotFoundError as error:
        raise ReportError(f"Model bulunamadı: {model}") from error
    except anthropic.RateLimitError as error:
        raise ReportError("Claude API istek sınırına ulaşıldı; biraz sonra tekrar deneyin.") from error
    except anthropic.APIStatusError as error:
        raise ReportError(f"Claude API hatası ({error.status_code}): {error.message}") from error
    except anthropic.APIConnectionError as error:
        raise ReportError("Claude API'ye bağlanılamadı; internet bağlantısını kontrol edin.") from error
    except TypeError as error:
        # Kimlik bilgisi hiç bulunamazsa SDK istek anında TypeError verebilir
        raise ReportError(f"Claude API kimlik bilgisi bulunamadı (ANTHROPIC_API_KEY): {error}") from error

    if response.stop_reason == "refusal":
        raise ReportError("İstek güvenlik sınıflandırıcısı tarafından reddedildi (fallback modeli de reddetti).")
    if response.stop_reason == "max_tokens":
        raise ReportError("Rapor çıktı sınırında yarım kaldı.")
    return response


def _add_usage(total: dict, usage) -> None:
    for key in total:
        total[key] += getattr(usage, key, 0) or 0
