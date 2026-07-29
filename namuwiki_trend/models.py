"""namuwiki_trend 데이터 모델.

파이프라인에서 모듈 간 데이터를 전달하는 데 사용하는
dataclass를 정의한다.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TrendItem:
    """나무위키 실시간 검색어 순위 항목."""

    rank: int
    keyword: str
    href: str


@dataclass
class TrendKeyword:
    """나무위키에서 수집한 인기 검색어 1건."""

    rank: int
    keyword: str
    collected_at: datetime = field(default_factory=datetime.now)


@dataclass
class NewsArticle:
    """뉴스 문맥 검색 결과 1건."""

    title: str
    url: str
    source: str | None = None
    published_at: datetime | None = None


@dataclass(frozen=True)
class TrendInsight:
    """TrendItem과 뉴스 근거 기반 reason을 묶은 enrichment 결과."""

    trend: TrendItem
    reason: str
    articles: tuple[NewsArticle, ...]


@dataclass
class TrendReport:
    """최종 결과물. 키워드 + 뉴스 + LLM 요약을 합친 보고서 1건."""

    rank: int
    keyword: str
    news_headlines: list[str]
    reason: str
    collected_at: datetime = field(default_factory=datetime.now)
