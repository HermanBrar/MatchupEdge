from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    odds_api_key: SecretStr | None = None
    app_mode: str = "demo"
    database_url: str = "sqlite:///./matchupedge.db"
    api_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5175,http://127.0.0.1:5175"
    display_timezone: str = "America/Indianapolis"

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
