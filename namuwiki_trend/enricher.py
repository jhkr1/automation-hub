"""TrendItem에 뉴스 문맥과 Gemini reason을 결합하는 Application Layer."""

from typing import Protocol

from namuwiki_trend.gemini_reason_generator import MAX_REASON_LENGTH
from namuwiki_trend.models import NewsArticle, TrendInsight, TrendItem


class NewsProvider(Protocol):
    """뉴스 검색 Provider의 최소 Application Layer 계약."""

    def search(self, keyword: str, limit: int) -> list[NewsArticle]:
        """검색어의 뉴스 문맥을 반환한다."""


class ReasonGenerator(Protocol):
    """reason 생성기의 최소 Application Layer 계약."""

    def generate_reason(self, trend: TrendItem, articles: list[NewsArticle]) -> str:
        """TrendItem과 뉴스 문맥으로 reason을 생성한다."""


class TrendEnricher:
    """뉴스 검색과 reason 생성을 조정하여 TrendInsight를 반환한다."""

    def __init__(
        self,
        news_provider: NewsProvider,
        reason_generator: ReasonGenerator,
        *,
        article_limit: int = 5,
    ) -> None:
        if type(article_limit) is not int or article_limit <= 0:
            raise ValueError(f"article_limit은 양의 정수여야 함: {article_limit!r}")
        self._news_provider = news_provider
        self._reason_generator = reason_generator
        self._article_limit = article_limit

    def enrich(self, trend: TrendItem) -> TrendInsight:
        """TrendItem 하나를 뉴스 문맥과 reason으로 보강한다."""
        if not isinstance(trend, TrendItem):
            raise TypeError(f"trend가 TrendItem이 아님: {type(trend).__name__}")

        articles = self._news_provider.search(trend.keyword, limit=self._article_limit)
        reason_value = self._reason_generator.generate_reason(trend, articles)
        if not isinstance(reason_value, str):
            raise TypeError(f"reason이 문자열이 아님: {type(reason_value).__name__}")

        reason = reason_value.strip()
        if not reason:
            raise ValueError("reason이 비어 있음")
        if len(reason) > MAX_REASON_LENGTH:
            raise ValueError(
                f"reason이 최대 길이를 초과함: {len(reason)}자, 최대 {MAX_REASON_LENGTH}자"
            )

        return TrendInsight(
            trend=trend,
            reason=reason,
            articles=tuple(articles),
        )
