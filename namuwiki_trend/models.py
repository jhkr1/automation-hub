"""namuwiki_trend 데이터 모델.

파이프라인에서 모듈 간 데이터를 전달하는 데 사용하는
dataclass를 정의한다.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TrendKeyword:
    """나무위키에서 수집한 인기 검색어 1건."""

    rank: int
    keyword: str
    collected_at: datetime = field(default_factory=datetime.now)


@dataclass
class NewsArticle:
    """네이버 뉴스 검색 결과 1건."""

    title: str
    summary: str
    link: str
    pub_date: datetime


@dataclass
class TrendReport:
    """최종 결과물. 키워드 + 뉴스 + LLM 요약을 합친 보고서 1건."""

    rank: int
    keyword: str
    news_headlines: list[str]
    reason: str
    collected_at: datetime = field(default_factory=datetime.now)
