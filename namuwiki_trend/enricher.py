"""TrendItem에 뉴스 문맥과 Gemini reason을 결합하는 Application Layer."""

from collections.abc import Mapping, Sequence
from typing import Protocol

from namuwiki_trend.gemini_reason_generator import (
    INSUFFICIENT_EVIDENCE_REASON,
    MAX_REASON_LENGTH,
    BatchAnalysisError,
)
from namuwiki_trend.models import NewsArticle, TrendInsight, TrendItem

BatchKey = tuple[int, str]
BatchInput = tuple[TrendItem, list[NewsArticle]]


class NewsProvider(Protocol):
    """뉴스 검색 Provider의 최소 Application Layer 계약."""

    def search(self, keyword: str, limit: int) -> list[NewsArticle]:
        """검색어의 뉴스 문맥을 반환한다."""


class ReasonGenerator(Protocol):
    """reason 생성기의 최소 Application Layer 계약."""

    def generate_reason(self, trend: TrendItem, articles: list[NewsArticle]) -> str:
        """TrendItem과 뉴스 문맥으로 reason을 생성한다."""


class BatchReasonGenerator(Protocol):
    """여러 검색어를 한 번에 분석하는 최소 계약."""

    def generate_reasons(self, items: Sequence[BatchInput]) -> Mapping[BatchKey, str]:
        """뉴스가 있는 TrendItem들의 reason을 반환한다."""


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
        if articles:
            reason_value = self._reason_generator.generate_reason(trend, articles)
        else:
            reason_value = INSUFFICIENT_EVIDENCE_REASON
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

    def enrich_all(self, trends: Sequence[TrendItem]) -> list[TrendInsight]:
        """뉴스를 모두 수집한 뒤 분석 가능한 항목을 Batch로 한 번 보강한다."""
        if not isinstance(trends, Sequence) or isinstance(trends, (str, bytes)):
            raise TypeError(f"trends가 Sequence가 아님: {type(trends).__name__}")

        ranks: set[int] = set()
        keywords: set[str] = set()
        for trend in trends:
            if not isinstance(trend, TrendItem):
                raise TypeError(f"trend가 TrendItem이 아님: {type(trend).__name__}")
            if type(trend.rank) is not int or trend.rank <= 0:
                raise BatchAnalysisError("invalid_input_rank")
            keyword = trend.keyword.strip()
            if not keyword:
                raise BatchAnalysisError("empty_input_keyword")
            if trend.rank in ranks:
                raise BatchAnalysisError("duplicate_input_rank")
            if keyword in keywords:
                raise BatchAnalysisError("duplicate_input_keyword")
            ranks.add(trend.rank)
            keywords.add(keyword)

        contexts: list[tuple[TrendItem, list[NewsArticle]]] = []
        for trend in trends:
            if not isinstance(trend, TrendItem):
                raise TypeError(f"trend가 TrendItem이 아님: {type(trend).__name__}")
            articles = self._news_provider.search(
                trend.keyword, limit=self._article_limit
            )
            contexts.append((trend, articles))

        analyzable = [(trend, articles) for trend, articles in contexts if articles]
        reasons: Mapping[BatchKey, str] = {}
        if analyzable:
            generator = self._reason_generator
            if not hasattr(generator, "generate_reasons"):
                raise TypeError("ReasonGenerator가 Batch 계약을 지원하지 않음")
            reasons = generator.generate_reasons(analyzable)  # type: ignore[attr-defined]

        results: list[TrendInsight] = []
        for trend, articles in contexts:
            key = (trend.rank, trend.keyword)
            if articles and key not in reasons:
                raise BatchAnalysisError("missing_item")
            reason = reasons.get(key, INSUFFICIENT_EVIDENCE_REASON)
            results.append(self._build_insight(trend, articles, reason))
        return sorted(results, key=lambda insight: insight.trend.rank)

    @staticmethod
    def _build_insight(
        trend: TrendItem,
        articles: list[NewsArticle],
        reason_value: object,
    ) -> TrendInsight:
        """reason을 검증하고 TrendInsight를 만든다."""
        if not isinstance(reason_value, str):
            raise TypeError(f"reason이 문자열이 아님: {type(reason_value).__name__}")
        reason = reason_value.strip()
        if not reason:
            raise ValueError("reason이 비어 있음")
        if len(reason) > MAX_REASON_LENGTH:
            raise ValueError(
                f"reason이 최대 길이를 초과함: {len(reason)}자, 최대 {MAX_REASON_LENGTH}자"
            )
        return TrendInsight(trend=trend, reason=reason, articles=tuple(articles))
