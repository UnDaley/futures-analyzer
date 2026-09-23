"""Uygulama ayarları. Değerler .env dosyasından veya ortam değişkenlerinden okunur."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://futures:futures@localhost:5432/futures"
    # Claude raporu için model ve API anahtarı (.env veya ortam değişkeni).
    # Anahtar boşsa SDK kendi yöntemleriyle arar (ANTHROPIC_API_KEY, `ant auth login` profili...).
    anthropic_model: str = "claude-opus-5"
    anthropic_api_key: str | None = None
    # Dashboard açıkken verileri kaç dakikada bir otomatik güncellesin (0 = kapalı)
    auto_refresh_minutes: int = 15
    # Piyasa açıkken analizler kaç dakikada bir otomatik kaydedilsin (sonuç ölçümü için, 0 = kapalı)
    auto_record_minutes: int = 60


settings = Settings()
