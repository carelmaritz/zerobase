from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from ZEROBASE_* environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_prefix="ZEROBASE_", env_file=".env", extra="ignore")

    # "production" enforces a strong secret key; anything else (dev, test) does not.
    env: str = "production"
    database_url: str = "postgresql+psycopg://zerobase:zerobase@localhost:5432/zerobase"
    secret_key: str = ""
    # The first account can always be registered. Further sign-ups need this switched on.
    allow_registration: bool = False
    currency_symbol: str = "£"
    # Set true when served over HTTPS (e.g. behind the bundled Caddy proxy).
    https_only: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
