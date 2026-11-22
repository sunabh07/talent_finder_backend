"""Typed application configuration, loaded from environment / .env."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------
    app_name: str = "Talent Finder API"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # --- Database ----------------------------------------------------------
    database_url: str
    test_database_url: str | None = None

    # --- CORS --------------------------------------------------------------
    # Kept as a plain string: pydantic-settings JSON-decodes list-typed fields
    # straight from the env file, which would force `["a","b"]` syntax in .env.
    # A comma-separated string is friendlier to read and to document.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Logging -----------------------------------------------------------
    # DEBUG | INFO | WARNING | ERROR. INFO gives one line per request plus
    # business events; DEBUG adds detail from the application's own modules.
    log_level: str = "INFO"
    # text (readable in a terminal) | json (one object per line, for an aggregator)
    log_format: str = "text"
    # Echo every SQL statement. Very noisy; off unless you are debugging a query.
    log_sql: bool = False

    # --- Pagination --------------------------------------------------------
    default_page_size: int = 10
    max_page_size: int = 100

    # --- Uploads (Story 2) -------------------------------------------------
    max_cv_size_mb: int = 10

    # --- AI (Story 7, optional) -------------------------------------------
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.8-flash"

    @property
    def allowed_origins(self) -> list[str]:
        """CORS origins as a list, parsed from the comma-separated setting."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def ai_enabled(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.get_secret_value().strip())

    @property
    def max_cv_size_bytes(self) -> int:
        return int(self.max_cv_size_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so .env is parsed exactly once per process."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
