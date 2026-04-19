"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/investment"
    FERNET_KEY: str = ""          # base64-urlsafe 32-byte key; required for secret encryption
    TIINGO_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    APP_VERSION: str = "0.1.0"


settings = Settings()
