"""Uygulama ayarları. Değerler .env dosyasından veya ortam değişkenlerinden okunur."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://futures:futures@localhost:5432/futures"


settings = Settings()
