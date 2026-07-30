import pytest

from database.daily_trend_query import DailyTrendRank
from namuwiki_trend.daily_trend_news_service import DailyTrendNews
from namuwiki_trend.daily_trend_reason_service import DailyTrendReasonService
from namuwiki_trend.models import TrendReason


def _item(keyword: str) -> DailyTrendNews:
    return DailyTrendNews(DailyTrendRank(keyword, 1, 1, 1.0, 10), ())


class FakeGenerator:
    def __init__(self, reasons: dict[str, TrendReason], error_keyword: str | None = None) -> None:
        self.reasons = reasons
        self.error_keyword = error_keyword
        self.calls: list[str] = []

    def generate(self, item: DailyTrendNews) -> TrendReason:
        self.calls.append(item.trend.keyword)
        if item.trend.keyword == self.error_keyword:
            raise RuntimeError("reason generation failed")
        return self.reasons[item.trend.keyword]


def _reason(keyword: str, confidence: str = "medium") -> TrendReason:
    return TrendReason(keyword, f"{keyword} 이유", confidence, (f"https://example/{keyword}",))


def test_empty_input_returns_empty_without_generator_call() -> None:
    generator = FakeGenerator({})

    result = DailyTrendReasonService(generator).generate([])

    assert result == []
    assert generator.calls == []


def test_generates_reasons_in_input_and_call_order() -> None:
    items = [_item("첫 번째"), _item("두 번째")]
    reasons = {item.trend.keyword: _reason(item.trend.keyword) for item in items}
    generator = FakeGenerator(reasons)

    result = DailyTrendReasonService(generator).generate(items)

    assert result == [reasons["첫 번째"], reasons["두 번째"]]
    assert generator.calls == ["첫 번째", "두 번째"]


def test_generator_result_fields_are_preserved() -> None:
    expected = TrendReason("손흥민", "근거 기반 설명", "low", ("url",))
    generator = FakeGenerator({"손흥민": expected})

    result = DailyTrendReasonService(generator).generate([_item("손흥민")])

    assert result[0] is expected
    assert result[0].confidence == "low"
    assert result[0].supporting_articles == ("url",)


def test_duplicate_keywords_are_each_generated() -> None:
    items = [_item("동일"), _item("동일")]
    expected = _reason("동일")
    generator = FakeGenerator({"동일": expected})

    result = DailyTrendReasonService(generator).generate(items)

    assert result == [expected, expected]
    assert generator.calls == ["동일", "동일"]


def test_generator_error_is_propagated_and_later_items_are_not_processed() -> None:
    generator = FakeGenerator(
        {"성공": _reason("성공"), "실패": _reason("실패"), "후속": _reason("후속")},
        error_keyword="실패",
    )

    with pytest.raises(RuntimeError, match="reason generation failed"):
        DailyTrendReasonService(generator).generate(
            [_item("성공"), _item("실패"), _item("후속")]
        )

    assert generator.calls == ["성공", "실패"]


def test_input_sequence_is_not_modified() -> None:
    items = (_item("하나"), _item("둘"))
    generator = FakeGenerator({"하나": _reason("하나"), "둘": _reason("둘")})

    DailyTrendReasonService(generator).generate(items)

    assert items == (_item("하나"), _item("둘"))


def test_invalid_input_is_rejected() -> None:
    generator = FakeGenerator({})

    with pytest.raises(TypeError):
        DailyTrendReasonService(generator).generate([object()])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        DailyTrendReasonService(generator).generate(None)  # type: ignore[arg-type]


def test_news_fallback_result_is_passed_through() -> None:
    fallback = TrendReason("뉴스 없음", "근거 부족", "low", ())
    generator = FakeGenerator({"뉴스 없음": fallback})

    result = DailyTrendReasonService(generator).generate([_item("뉴스 없음")])

    assert result == [fallback]
