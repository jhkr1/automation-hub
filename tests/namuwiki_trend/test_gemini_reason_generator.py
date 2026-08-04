"""GeminiReasonGenerator의 네트워크 비의존 테스트."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from google.genai import errors

from namuwiki_trend.gemini_reason_generator import (
    DEFAULT_MODEL,
    MAX_REASON_LENGTH,
    GeminiReasonGenerator,
    build_reason_prompt,
)
from namuwiki_trend.models import NewsArticle, TrendItem


class FakeModels:
    """generate_content 최소 인터페이스를 제공하는 fake 모델 클라이언트."""

    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, str]] = []

    def generate_content(self, *, model: str, contents: str) -> object:
        """호출 인자를 저장하고 fake 응답 또는 예외를 반환한다."""
        self.calls.append({"model": model, "contents": contents})
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    """GeminiReasonGenerator 테스트용 fake client."""

    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.models = FakeModels(response=response, error=error)


def _trend(keyword: str = "테스트 검색어") -> TrendItem:
    """테스트용 TrendItem을 만든다."""
    return TrendItem(rank=1, keyword=keyword, href="/Go?q=test")


def _article(
    title: str = "테스트 검색어 관련 주요 기사",
    source: str | None = "테스트뉴스",
) -> NewsArticle:
    """테스트용 NewsArticle을 만든다."""
    return NewsArticle(
        title=title,
        url="https://news.example/article",
        source=source,
        published_at=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
    )


def test_build_reason_prompt_contains_required_rules() -> None:
    """Prompt에 keyword, 기사 문맥, grounding과 출력 제한을 포함한다."""
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
    assert "제공된 기사만으로는 정확한 이유를 확인하기 어렵다." in prompt
    assert _article().url not in prompt


def test_build_reason_prompt_rejects_invalid_input() -> None:
    """Prompt 경계에서 잘못된 TrendItem, 기사 목록과 빈 keyword를 거부한다."""
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
    """기사가 없으면 정확한 이유를 단정하지 않도록 Prompt를 만든다."""
    prompt = build_reason_prompt(_trend(), [])

    assert "제공된 기사가 없음" in prompt
    assert "제공된 기사만으로는 정확한 이유를 확인하기 어렵다." in prompt


def test_build_reason_prompt_handles_multiple_articles_and_trimmed_title() -> None:
    """여러 기사의 제목과 선택적 출처를 trim하여 순서대로 포함한다."""
    prompt = build_reason_prompt(
        _trend(),
        [_article("  첫 번째 제목  "), _article("두 번째 제목", source=None)],
    )

    assert "- 제목: 첫 번째 제목" in prompt
    assert "- 제목: 두 번째 제목" in prompt
    assert "- 출처: 확인되지 않음" in prompt
    assert prompt.index("첫 번째 제목") < prompt.index("두 번째 제목")


def test_build_reason_prompt_rejects_excessive_length() -> None:
    """기사 문맥이 Prompt 최대 길이를 넘으면 임의로 자르지 않고 실패한다."""
    with pytest.raises(ValueError, match="Prompt가 최대 길이를 초과함"):
        build_reason_prompt(_trend(), [_article("가" * 12_001)])


def test_generate_reason_returns_trimmed_response_and_passes_model_prompt() -> None:
    """응답을 trim하고 공식 model identifier와 Prompt를 전달한다."""
    client = FakeClient(response=SimpleNamespace(text="\n  설명입니다.  \n"))
    generator = GeminiReasonGenerator(client=client)

    result = generator.generate_reason(_trend(), [_article()])

    assert result == "설명입니다."
    assert client.models.calls[0]["model"] == DEFAULT_MODEL
    assert "테스트 검색어" in client.models.calls[0]["contents"]
    assert _article().url not in client.models.calls[0]["contents"]


def test_generator_rejects_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """주입된 client가 없고 API Key도 없으면 호출 전에 실패한다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiReasonGenerator()


def test_generate_reason_propagates_sdk_error() -> None:
    """SDK 호출 오류를 무조건 숨기지 않고 원인 그대로 전달한다."""
    expected = RuntimeError("fake SDK failure")
    generator = GeminiReasonGenerator(client=FakeClient(error=expected))

    with pytest.raises(RuntimeError, match="fake SDK failure") as raised:
        generator.generate_reason(_trend(), [])

    assert raised.value is expected


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (None, "응답 객체가 없음"),
        (SimpleNamespace(text=None), "응답 text가 문자열이 아님"),
        (SimpleNamespace(text="  \n"), "응답 text가 비어 있음"),
    ],
)
def test_generate_reason_rejects_invalid_response(response: object, message: str) -> None:
    """응답 객체·text·빈 문자열을 검증한다."""
    generator = GeminiReasonGenerator(client=FakeClient(response=response))

    with pytest.raises(RuntimeError, match=message):
        generator.generate_reason(_trend(), [])


def test_generate_reason_rejects_excessively_long_response() -> None:
    """최대 문자 수를 초과한 응답을 잘라내지 않고 실패시킨다."""
    response = SimpleNamespace(text="가" * (MAX_REASON_LENGTH + 1))
    generator = GeminiReasonGenerator(client=FakeClient(response=response))

    with pytest.raises(ValueError, match="최대 길이를 초과함"):
        generator.generate_reason(_trend(), [])


def _quota_error(
    *,
    retry_delay: str | None = None,
    status: str = "RESOURCE_EXHAUSTED",
    daily: bool = False,
) -> errors.ClientError:
    """테스트용 Gemini quota 오류를 만든다."""
    details: list[dict[str, object]] = []
    if retry_delay is not None:
        details.append(
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": retry_delay,
            }
        )
    if daily:
        details.append(
            {
                "quotaMetric": (
                    "generativelanguage.googleapis.com/"
                    "generate_content_free_tier_requests"
                ),
                "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
            }
        )
    return errors.ClientError(
        429,
        {"error": {"status": status, "details": details}},
    )


class SequencedModels:
    """호출마다 사전 정의된 오류 또는 응답을 반환하는 Fake 모델."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def generate_content(self, *, model: str, contents: str) -> object:
        """다음 결과를 반환한다."""
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def test_generate_reason_enforces_minimum_request_interval() -> None:
    """연속 요청 사이에 설정한 최소 간격만큼 sleeper를 호출한다."""
    current_time = 0.0
    sleeps: list[float] = []
    models = SequencedModels([SimpleNamespace(text="첫 응답"), SimpleNamespace(text="둘째 응답")])
    client = SimpleNamespace(models=models)

    def clock() -> float:
        return current_time

    def sleeper(delay: float) -> None:
        nonlocal current_time
        sleeps.append(delay)
        current_time += delay

    generator = GeminiReasonGenerator(
        client=client,
        min_request_interval_seconds=5.0,
        clock=clock,
        sleeper=sleeper,
    )

    generator.generate_reason(_trend(), [])
    generator.generate_reason(_trend(), [])

    assert models.calls == 2
    assert sleeps == [5.0]


def test_generate_reason_retries_only_resource_exhausted_and_uses_retry_delay() -> None:
    """429 RESOURCE_EXHAUSTED만 retry하고 응답의 retryDelay를 사용한다."""
    sleeps: list[float] = []
    models = SequencedModels(
        [_quota_error(retry_delay="3.5s"), SimpleNamespace(text="재시도 성공")]
    )
    generator = GeminiReasonGenerator(
        client=SimpleNamespace(models=models),
        min_request_interval_seconds=0,
        sleeper=sleeps.append,
    )

    assert generator.generate_reason(_trend(), []) == "재시도 성공"
    assert models.calls == 2
    assert sleeps == [3.5]


def test_generate_reason_does_not_retry_daily_quota_exhaustion() -> None:
    """일일 quota marker가 있으면 RetryInfo가 있어도 즉시 전달한다."""
    error = _quota_error(retry_delay="30s", daily=True)
    sleeps: list[float] = []
    models = SequencedModels([error, SimpleNamespace(text="재시도되어서는 안 됨")])
    generator = GeminiReasonGenerator(
        client=SimpleNamespace(models=models),
        min_request_interval_seconds=0,
        sleeper=sleeps.append,
    )

    with pytest.raises(errors.ClientError) as raised:
        generator.generate_reason(_trend(), [])

    assert raised.value is error
    assert models.calls == 1
    assert sleeps == []


def test_generate_reason_uses_bounded_exponential_retry_when_delay_missing() -> None:
    """retryDelay가 없으면 bounded exponential backoff를 사용한다."""
    error = _quota_error()
    sleeps: list[float] = []
    models = SequencedModels([error])
    generator = GeminiReasonGenerator(
        client=SimpleNamespace(models=models),
        min_request_interval_seconds=0,
        max_retries=2,
        retry_backoff_seconds=2.0,
        sleeper=sleeps.append,
    )

    with pytest.raises(errors.ClientError) as raised:
        generator.generate_reason(_trend(), [])

    assert raised.value is error
    assert models.calls == 3
    assert sleeps == [2.0, 4.0]


@pytest.mark.parametrize(
    "error", [_quota_error(status="INVALID_ARGUMENT"), errors.ClientError(400, {})]
)
def test_generate_reason_does_not_retry_other_sdk_errors(error: errors.ClientError) -> None:
    """429가 아니거나 RESOURCE_EXHAUSTED가 아니면 즉시 전달한다."""
    sleeps: list[float] = []
    models = SequencedModels([error])
    generator = GeminiReasonGenerator(
        client=SimpleNamespace(models=models),
        sleeper=sleeps.append,
    )

    with pytest.raises(errors.ClientError) as raised:
        generator.generate_reason(_trend(), [])

    assert raised.value is error
    assert models.calls == 1
    assert sleeps == []
