"""Application configuration.

Loads environment variables via ``pydantic-settings`` and exposes a single
``settings`` object used throughout the app.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Lead limits
    default_max_leads: int = Field(default=20, alias="DEFAULT_MAX_LEADS")
    max_leads_limit: int = Field(default=100, alias="MAX_LEADS_LIMIT")

    # HTTP
    http_timeout: float = Field(default=20.0, alias="HTTP_TIMEOUT")
    max_concurrent_requests: int = Field(default=5, alias="MAX_CONCURRENT_REQUESTS")
    request_delay_seconds: float = Field(default=1.0, alias="REQUEST_DELAY_SECONDS")
    user_agent: str = Field(
        default="LeadGenBot/1.0 (+https://example.com/bot)",
        alias="USER_AGENT",
    )
    contact_email: str = Field(default="", alias="CONTACT_EMAIL")

    # Storage
    sqlite_path: str = Field(default="./data/leads.db", alias="SQLITE_PATH")
    export_dir: str = Field(default="./data/exports", alias="EXPORT_DIR")

    # OSM endpoints
    nominatim_url: str = Field(
        default="https://nominatim.openstreetmap.org", alias="NOMINATIM_URL"
    )
    overpass_url: str = Field(
        default="https://overpass-api.de/api/interpreter", alias="OVERPASS_URL"
    )

    # Wikidata endpoint
    wikidata_sparql_url: str = Field(
        default="https://query.wikidata.org/sparql", alias="WIKIDATA_SPARQL_URL"
    )

    # Third-party place-search APIs (all optional; the source simply does not
    # register when its key is empty).
    yelp_api_key: str = Field(default="", alias="YELP_API_KEY")
    here_api_key: str = Field(default="", alias="HERE_API_KEY")
    foursquare_api_key: str = Field(default="", alias="FOURSQUARE_API_KEY")

    # Google Maps scraping.  Disabled by default: Google's ToS forbids
    # automated access, and the HTML format changes frequently.  Turn on at
    # your own risk.
    enable_google_maps: bool = Field(default=False, alias="ENABLE_GOOGLE_MAPS")
    google_maps_hl: str = Field(default="en", alias="GOOGLE_MAPS_HL")

    # Health endpoint
    enable_health_endpoint: bool = Field(default=False, alias="ENABLE_HEALTH_ENDPOINT")
    health_host: str = Field(default="127.0.0.1", alias="HEALTH_HOST")
    health_port: int = Field(default=8080, alias="HEALTH_PORT")

    # Parser
    use_llm_parser: bool = Field(default=False, alias="USE_LLM_PARSER")

    # -------- Validators --------

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        return (v or "INFO").upper()

    # -------- Helpers --------

    @property
    def sqlite_path_resolved(self) -> Path:
        p = Path(self.sqlite_path).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def export_dir_resolved(self) -> Path:
        p = Path(self.export_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def nominatim_user_agent(self) -> str:
        """User-Agent string that complies with Nominatim usage policy."""
        base = self.user_agent
        if self.contact_email:
            return f"{base} contact={self.contact_email}"
        return base


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings instance."""
    return Settings()


settings = get_settings()
