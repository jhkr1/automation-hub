"""Daily Trend와 뉴스 문맥을 결합하는 Application Service."""

from dataclasses import dataclass
from datetime import date

from database.daily_trend_query import DailyTrendQueryService, DailyTrendRank
from namuwiki_trend.models import NewsArticle
from namuwiki_trend.news_context_provider import NewsContextProvider


@dataclass(frozen=True)
class DailyTrendNews:
    """Daily Trend 한 건과 검색된 뉴스 문맥을 묶은 결과 모델."""

    trend: DailyTrendRank
    articles: tuple[NewsArticle, ...]


class DailyTrendNewsService:
    """Daily Trend 조회와 keyword별 뉴스 검색을 조정한다."""

    def __init__(
        self,
        daily_trend_query: DailyTrendQueryService,
        news_provider: NewsContextProvider,
    ) -> None:
        """Initialize the service with query and news dependencies."""
        self._daily_trend_query = daily_trend_query
        self._news_provider = news_provider

    def collect(
        self,
        target_date: date,
        trend_limit: int = 10,
        news_limit: int = 3,
    ) -> list[DailyTrendNews]:
        """Return ordered Daily Trend rows enriched with news articles."""
        self._validate_inputs(target_date, trend_limit, news_limit)
        trends = self._daily_trend_query.query(target_date, limit=trend_limit)
        return [
            DailyTrendNews(
                trend=trend,
                articles=tuple(self._news_provider.search(trend.keyword, limit=news_limit)),
            )
            for trend in trends
        ]

    @staticmethod
    def _validate_inputs(target_date: date, trend_limit: int, news_limit: int) -> None:
        """Validate all inputs before querying or calling the provider."""
        if type(target_date) is not date:
            raise TypeError("target_date must be a date")
        if type(trend_limit) is not int or trend_limit <= 0:
            raise ValueError("trend_limit must be a positive integer")
        if type(news_limit) is not int or news_limit <= 0:
            raise ValueError("news_limit must be a positive integer")
