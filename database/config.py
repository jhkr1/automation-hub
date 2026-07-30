"""데이터베이스 연결 설정."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DatabaseSettings(BaseSettings):
    """환경변수에서 DATABASE_URL을 읽는 데이터베이스 설정."""

    database_url: str

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )
