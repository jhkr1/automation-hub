"""SQLAlchemy Session factory."""

from sqlalchemy.orm import Session, sessionmaker

from database.engine import engine

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
