"""google_finance 설정 및 로거 모듈.

환경변수를 로딩하고 검증하는 Settings 클래스와
모듈별 로거를 생성하는 get_logger 함수를 제공한다.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """google_finance 프로젝트에 필요한 환경변수를 정의한다.

    .env 파일에서 자동으로 로딩한다. ``STOCK_SYMBOLS``는 단일 종목 CLI를
    방해하지 않도록 빈 기본값을 가지며, Watchlist가 ``get_symbol_list()``를
    호출할 때 비어 있으면 설정 오류로 처리한다.
    """

    stock_symbols: str = ""
    google_finance_locale: str = "en-US"
    gemini_api_key: str | None = None
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    def get_symbol_list(self) -> list[str]:
        """Parse, validate, canonicalize, and deduplicate Watchlist symbols.

        The collector owns the symbol grammar, so this method reuses its validator
        lazily to avoid a module-level circular import.
        """
        raw_symbols = self.stock_symbols.split(",")
        if not self.stock_symbols.strip() or any(not symbol.strip() for symbol in raw_symbols):
            raise ValueError("STOCK_SYMBOLS must contain at least one non-empty symbol")

        from google_finance.collector import validate_symbol

        symbols: list[str] = []
        seen: set[str] = set()
        for raw_symbol in raw_symbols:
            symbol = validate_symbol(raw_symbol)
            if symbol not in seen:
                seen.add(symbol)
                symbols.append(symbol)
        return symbols


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """모듈별 로거를 생성하여 반환한다.

    - 콘솔 핸들러: 모든 로그를 stdout으로 출력
    - 파일 핸들러: RotatingFileHandler로 logs/google_finance.log에 기록
      - 최대 10MB, 백업 파일 5개 유지

    Args:
        name: 로거 이름. 일반적으로 __name__을 전달한다.
        level: 로그 레벨. 기본값은 "INFO".

    Returns:
        설정된 logging.Logger 인스턴스.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper()))

    fmt = logging.Formatter(
        "[{asctime}] [{levelname}] [{name}] {message}",
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    # 파일 핸들러
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "google_finance.log",
        maxBytes=10_485_760,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
