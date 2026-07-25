"""Configuration, read from the environment.

Nothing in this project reads `os.environ` directly. Every setting is
declared here, with a type and a default, and pydantic-settings does the
reading, converting and validating. Three things follow from that:

  - A typo in a variable name fails at startup with a clear message,
    rather than silently becoming `None` somewhere deep in a worker.
  - Secrets stay out of the code. The database password lives in the
    environment (or a `.env` file that git ignores), never in a commit.
  - The same image runs in development and production; only the
    environment differs. That is the whole idea behind the
    twelve-factor style of configuration.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ------------------------------------------------
    app_name: str = "weather-service"
    environment: Literal["development", "production", "test"] = "development"
    debug: bool = False

    # --- Database ---------------------------------------------------
    # The default points at the Docker Compose service name, "db", which
    # only resolves inside the compose network. Running the API on the
    # host instead means overriding this with localhost.
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://weather:weather@db:5432/weather"
    )
    db_pool_size: int = 5
    db_echo: bool = False  # log every SQL statement; noisy but useful

    # --- Cache ------------------------------------------------------
    redis_url: RedisDsn = Field(default="redis://cache:6379/0")

    # --- External API -----------------------------------------------
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_archive_url: str = "https://archive-api.open-meteo.com/v1/archive"
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 3

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Returns the settings, built once and reused.

    The cache matters for more than speed: FastAPI injects this into
    request handlers, and reading the environment on every request would
    be both wasteful and a source of surprises if the environment
    changed mid-process. It also gives tests a single place to override.
    """
    return Settings()
