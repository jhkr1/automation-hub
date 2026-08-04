"""Configuration for the read-only dashboard database connection."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DashboardConfigurationError(RuntimeError):
    """Raised when the dashboard has no usable database connection setting."""


class DashboardSettings(BaseSettings):
    """Load a dashboard-specific URL, with a local MVP fallback to ``DATABASE_URL``."""

    dashboard_database_url: str | None = None
    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    @property
    def selected_database_url(self) -> str:
        """Return the preferred dashboard URL without exposing its value."""
        for value in (self.dashboard_database_url, self.database_url):
            if value and value.strip():
                return value
        raise DashboardConfigurationError(
            "DASHBOARD_DATABASE_URL or DATABASE_URL must be configured"
        )
