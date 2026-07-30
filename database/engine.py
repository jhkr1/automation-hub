"""SQLAlchemy Engine 생성."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from database.config import DatabaseSettings

settings = DatabaseSettings()
engine: Engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)
