"""SQLAlchemy ORM metadata의 기본 클래스."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """향후 ORM 모델이 상속할 공통 declarative base."""
