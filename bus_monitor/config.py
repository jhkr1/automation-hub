"""Configuration for production bus-monitor providers."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class BusMonitorSettings(BaseSettings):
    """Load bus-monitor provider configuration from the project ``.env`` file."""

    odsay_api_key: str | None = None
    tago_service_key: str | None = None
    gyeonggi_service_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )
