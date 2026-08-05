"""GeminiReasonGenerator의 Runtime 기반 네트워크 비의존 테스트."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from llm_runtime.exceptions import LlmDailyQuotaExceededError, LlmRateLimitError
from llm_runtime.models import KeyProfile, LlmJob
from namuwiki_trend.gemini_reason_generator import (
    INSUFFICIENT_EVIDENCE_REASON,
    MAX_REASON_LENGTH,
    GeminiReasonGenerator,
    build_reason_prompt,
)
from namuwiki_trend.models import NewsArticle, TrendItem


class FakeRuntime:
    """Runtime 호출 인자를 기록하는 Fake."""

    def __init__(self, response=None, error=None) -> None:
        self.response = response or SimpleNamespace(text="  설명입니다.  ")
        self.error = error
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _trend(keyword: str = "테스트 검색어") -> TrendItem:
    return TrendItem(rank=1, keyword=keyword, href="/Go?q=test")


def _article(
    title: str = "테스트 검색어 관련 주요 기사",
    source: str | None = "테스트뉴스",
) -> NewsArticle:
    return NewsArticle(
        title=title,
        url="https://news.example/article",
        source=source,
        published_at=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
    )


def test_build_reason_prompt_contains_required_rules() -> None:
    prompt = build_reason_prompt(_trend(), [_article()])

    assert "테스트 검색어" in prompt
    assert "테스트 검색어 관련 주요 기사" in prompt
    assert "테스트뉴스" in prompt
    assert "2026-07-29T10:00:00+00:00" in prompt
    assert "한국어 1~2문장" in prompt
    assert "추측하거나 보완하지 않는다" in prompt
    assert "상충하는 보도" in prompt
    assert "어느 한쪽을 사실로 단정하지 않는다" in prompt
    assert "인기 원인" in prompt
    assert INSUFFICIENT_EVIDENCE_REASON in prompt
    assert _article().url not in prompt


def test_build_reason_prompt_rejects_invalid_input() -> None:
    with pytest.raises(TypeError, match="TrendItem이 아님"):
        build_reason_prompt("invalid", [])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="list가 아님"):
        build_reason_prompt(_trend(), ())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="keyword가 비어 있음"):
        build_reason_prompt(_trend("  "), [])
    with pytest.raises(TypeError, match="NewsArticle가 아님"):
        build_reason_prompt(_trend(), ["invalid"])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="title이 비어 있음"):
        build_reason_prompt(_trend(), [_article("  ")])


def test_build_reason_prompt_handles_no_articles() -> None:
    prompt = build_reason_prompt(_trend(), [])
    assert "제공된 기사가 없음" in prompt
    assert INSUFFICIENT_EVIDENCE_REASON in prompt


def test_build_reason_prompt_handles_multiple_articles_and_trimmed_title() -> None:
    prompt = build_reason_prompt(
        _trend(), [_article("  첫 번째 제목  "), _article("두 번째 제목", None)]
    )
    assert "- 제목: 첫 번째 제목" in prompt
    assert "- 제목: 두 번째 제목" in prompt
    assert "- 출처: 확인되지 않음" in prompt
    assert prompt.index("첫 번째 제목") < prompt.index("두 번째 제목")


def test_build_reason_prompt_rejects_excessive_length() -> None:
    with pytest.raises(ValueError, match="Prompt가 최대 길이를 초과함"):
        build_reason_prompt(_trend(), [_article("가" * 12_001)])


def test_generator_builds_prompt_and_calls_runtime_contract() -> None:
    runtime = FakeRuntime()
    generator = GeminiReasonGenerator(runtime=runtime, profile=KeyProfile.TEST)

    result = generator.generate_reason(_trend(), [_article()])

    call = runtime.calls[0]
    assert result == "설명입니다."
    assert call["job"] is LlmJob.NAMUWIKI
    assert call["profile"] is KeyProfile.TEST
    assert "테스트 검색어" in call["prompt"]
    assert call["estimated_input_tokens"] == max(
        1, (len(call["prompt"]) + 2) // 3
    )
    assert call["max_output_tokens"] is None


def test_generator_uses_character_based_token_estimate() -> None:
    assert GeminiReasonGenerator.estimate_input_tokens("") == 1
    assert GeminiReasonGenerator.estimate_input_tokens("a" * 4) == 2


def test_generator_propagates_runtime_errors_without_retry() -> None:
    error = LlmRateLimitError("rate limited")
    runtime = FakeRuntime(error=error)
    generator = GeminiReasonGenerator(runtime=runtime, profile=KeyProfile.TEST)

    with pytest.raises(LlmRateLimitError) as raised:
        generator.generate_reason(_trend(), [_article()])

    assert raised.value is error
    assert len(runtime.calls) == 1


def test_generator_preserves_daily_quota_contract() -> None:
    error = LlmDailyQuotaExceededError("daily quota exceeded")
    runtime = FakeRuntime(error=error)
    generator = GeminiReasonGenerator(runtime=runtime, profile=KeyProfile.PRODUCTION)

    with pytest.raises(LlmDailyQuotaExceededError):
        generator.generate_reason(_trend(), [_article()])


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (SimpleNamespace(text=None), "응답 text가 문자열이 아님"),
        (SimpleNamespace(text="  \n"), "응답 text가 비어 있음"),
    ],
)
def test_generator_rejects_invalid_runtime_response(response, message: str) -> None:
    generator = GeminiReasonGenerator(
        runtime=FakeRuntime(response=response), profile=KeyProfile.TEST
    )
    with pytest.raises(RuntimeError, match=message):
        generator.generate_reason(_trend(), [])


def test_generator_rejects_excessively_long_response() -> None:
    runtime = FakeRuntime(response=SimpleNamespace(text="가" * (MAX_REASON_LENGTH + 1)))
    generator = GeminiReasonGenerator(runtime=runtime, profile=KeyProfile.TEST)

    with pytest.raises(ValueError, match="최대 길이를 초과함"):
        generator.generate_reason(_trend(), [])


def test_generator_does_not_access_api_key_directly() -> None:
    runtime = FakeRuntime()
    generator = GeminiReasonGenerator(runtime=runtime, profile=KeyProfile.TEST)
    assert "api_key" not in vars(generator)
