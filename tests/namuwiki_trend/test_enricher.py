"""TrendEnricher의 네트워크 비의존 테스트."""

from datetime import datetime, timezone

import pytest

from namuwiki_trend.enricher import TrendEnricher
from namuwiki_trend.gemini_reason_generator import INSUFFICIENT_EVIDENCE_REASON
from namuwiki_trend.models import NewsArticle, TrendInsight, TrendItem


def _trend() -> TrendItem:
    """테스트용 TrendItem을 만든다."""
    return TrendItem(rank=1, keyword="손흥민", href="/Go?q=손흥민")


def _article() -> NewsArticle:
    """테스트용 NewsArticle을 만든다."""
    return NewsArticle(
        title="손흥민 관련 기사",
        url="https://news.example/article",
        source="테스트뉴스",
        published_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
    )


class FakeNewsProvider:
    """뉴스 검색 호출을 기록하는 Fake Provider."""

    def __init__(
        self,
        articles: list[NewsArticle] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.articles = articles if articles is not None else [_article()]
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, keyword: str, limit: int) -> list[NewsArticle]:
        """호출을 기록하고 fake 기사 또는 예외를 반환한다."""
        self.calls.append((keyword, limit))
        if self.error is not None:
            raise self.error
        return self.articles


class FakeReasonGenerator:
    """reason 생성 호출을 기록하는 Fake Generator."""

    def __init__(
        self,
        reason: object = "  뉴스 기반 설명입니다.  ",
        error: Exception | None = None,
    ) -> None:
        self.reason = reason
        self.error = error
        self.calls: list[tuple[TrendItem, list[NewsArticle]]] = []

    def generate_reason(self, trend: TrendItem, articles: list[NewsArticle]) -> object:
        """호출을 기록하고 fake reason 또는 예외를 반환한다."""
        self.calls.append((trend, articles))
        if self.error is not None:
            raise self.error
        return self.reason


def test_enrich_calls_providers_and_returns_trend_insight() -> None:
    """Provider와 Generator를 순서대로 호출하고 결과를 묶는다."""
    news_provider = FakeNewsProvider()
    reason_generator = FakeReasonGenerator()
    enricher = TrendEnricher(news_provider, reason_generator, article_limit=3)

    result = enricher.enrich(_trend())

    assert isinstance(result, TrendInsight)
    assert result.trend == _trend()
    assert result.reason == "뉴스 기반 설명입니다."
    assert result.articles == (_article(),)
    assert news_provider.calls == [("손흥민", 3)]
    assert reason_generator.calls == [(_trend(), news_provider.articles)]


def test_enrich_returns_insufficient_evidence_without_calling_generator() -> None:
    """뉴스가 없으면 근거 부족 결과를 반환하고 Generator를 호출하지 않는다."""
    news_provider = FakeNewsProvider(articles=[])
    reason_generator = FakeReasonGenerator()

    result = TrendEnricher(news_provider, reason_generator).enrich(_trend())

    assert result.articles == ()
    assert result.reason == INSUFFICIENT_EVIDENCE_REASON
    assert reason_generator.calls == []


@pytest.mark.parametrize(
    ("reason", "error", "message"),
    [
        ("  ", ValueError, "reason이 비어 있음"),
        (None, TypeError, "reason이 문자열이 아님"),
        ("가" * 301, ValueError, "reason이 최대 길이를 초과함"),
    ],
)
def test_enrich_validates_reason(reason: object, error: type[Exception], message: str) -> None:
    """Generator 결과를 trim하고 타입·빈 값·최대 길이를 검증한다."""
    with pytest.raises(error, match=message):
        TrendEnricher(FakeNewsProvider(), FakeReasonGenerator(reason=reason)).enrich(_trend())


def test_enrich_propagates_provider_exception() -> None:
    """뉴스 Provider 예외를 원인 그대로 전달한다."""
    expected = RuntimeError("news failure")

    with pytest.raises(RuntimeError) as raised:
        TrendEnricher(FakeNewsProvider(error=expected), FakeReasonGenerator()).enrich(_trend())

    assert raised.value is expected


def test_enrich_propagates_generator_exception() -> None:
    """Reason Generator 예외를 원인 그대로 전달한다."""
    expected = RuntimeError("reason failure")

    with pytest.raises(RuntimeError) as raised:
        TrendEnricher(FakeNewsProvider(), FakeReasonGenerator(error=expected)).enrich(_trend())

    assert raised.value is expected


@pytest.mark.parametrize("limit", [0, -1, 1.5, True])
def test_enricher_rejects_invalid_article_limit(limit: object) -> None:
    """양의 정수가 아닌 article_limit을 거부한다."""
    with pytest.raises(ValueError):
        TrendEnricher(FakeNewsProvider(), FakeReasonGenerator(), article_limit=limit)  # type: ignore[arg-type]
