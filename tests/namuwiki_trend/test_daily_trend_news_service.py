from datetime import date, datetime
from types import SimpleNamespace

import pytest

from namuwiki_trend.daily_trend_news_service import DailyTrendNewsService
from namuwiki_trend.models import NewsArticle


def _trend(keyword: str, rank: int) -> SimpleNamespace:
    return SimpleNamespace(
        keyword=keyword,
        appearance_count=2,
        best_rank=rank,
        average_rank=float(rank),
        rank_score=20 - rank,
    )


class FakeQuery:
    def __init__(self, trends: list[object], error: Exception | None = None) -> None:
        self.trends = trends
        self.error = error
        self.calls: list[tuple[date, int]] = []

    def query(self, target_date: date, limit: int) -> list[object]:
        self.calls.append((target_date, limit))
        if self.error:
            raise self.error
        return self.trends


class FakeNewsProvider:
    def __init__(self, articles_by_keyword: dict[str, list[NewsArticle]] | None = None) -> None:
        self.articles_by_keyword = articles_by_keyword or {}
        self.calls: list[tuple[str, int]] = []

    def search(self, keyword: str, limit: int) -> list[NewsArticle]:
        self.calls.append((keyword, limit))
        return self.articles_by_keyword.get(keyword, [])


def test_collects_news_in_trend_and_article_order() -> None:
    trends = [_trend("첫 번째", 1), _trend("두 번째", 2)]
    provider = FakeNewsProvider(
        {
            "첫 번째": [NewsArticle("기사 1", "https://example/1")],
            "두 번째": [NewsArticle("기사 2", "https://example/2")],
        }
    )
    query = FakeQuery(trends)

    result = DailyTrendNewsService(query, provider).collect(date(2026, 7, 30), 2, 3)

    assert [item.trend.keyword for item in result] == ["첫 번째", "두 번째"]
    assert result[0].articles[0].title == "기사 1"
    assert query.calls == [(date(2026, 7, 30), 2)]
    assert provider.calls == [("첫 번째", 3), ("두 번째", 3)]


def test_empty_trends_do_not_call_news_provider() -> None:
    provider = FakeNewsProvider()

    result = DailyTrendNewsService(FakeQuery([]), provider).collect(date(2026, 7, 30))

    assert result == []
    assert provider.calls == []


def test_empty_news_result_is_preserved_as_empty_tuple() -> None:
    result = DailyTrendNewsService(FakeQuery([_trend("뉴스 없음", 1)]), FakeNewsProvider()).collect(
        date(2026, 7, 30)
    )

    assert result[0].articles == ()


@pytest.mark.parametrize("name", ["trend_limit", "news_limit"])
def test_rejects_non_positive_limits(name: str) -> None:
    with pytest.raises(ValueError):
        DailyTrendNewsService(FakeQuery([]), FakeNewsProvider()).collect(
            date(2026, 7, 30), **{name: 0}
        )


def test_rejects_datetime_as_target_date() -> None:
    with pytest.raises(TypeError):
        DailyTrendNewsService(FakeQuery([]), FakeNewsProvider()).collect(datetime.now())


def test_query_exception_is_propagated_without_news_call() -> None:
    expected = RuntimeError("query failed")
    provider = FakeNewsProvider()

    with pytest.raises(RuntimeError) as raised:
        DailyTrendNewsService(FakeQuery([], expected), provider).collect(date(2026, 7, 30))

    assert raised.value is expected
    assert provider.calls == []


def test_news_exception_is_propagated_without_partial_result() -> None:
    class FailingProvider(FakeNewsProvider):
        def search(self, keyword: str, limit: int) -> list[NewsArticle]:
            self.calls.append((keyword, limit))
            raise RuntimeError("news failed")

    with pytest.raises(RuntimeError, match="news failed"):
        DailyTrendNewsService(
            FakeQuery([_trend("실패", 1)]), FailingProvider()
        ).collect(date(2026, 7, 30))


def test_articles_are_exposed_as_tuple() -> None:
    result = DailyTrendNewsService(
        FakeQuery([_trend("테스트", 1)]),
        FakeNewsProvider({"테스트": [NewsArticle("기사", "https://example/1")]}),
    ).collect(date(2026, 7, 30))

    assert isinstance(result[0].articles, tuple)
