"""GeminiReasonGenerator의 네트워크 비의존 테스트."""

from types import SimpleNamespace

import pytest

from namuwiki_trend.gemini_reason_generator import (
    DEFAULT_MODEL,
    MAX_REASON_LENGTH,
    GeminiReasonGenerator,
    build_reason_prompt,
)
from namuwiki_trend.models import TrendItem


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


def test_build_reason_prompt_contains_required_rules() -> None:
    """Prompt에 keyword와 출력·hallucination 제한을 포함한다."""
    prompt = build_reason_prompt(_trend())

    assert "테스트 검색어" in prompt
    assert "한국어 1~2문장" in prompt
    assert "추측하지 않는다" in prompt
    assert "정확한 등재 이유를 확인하기 어렵습니다" in prompt


def test_build_reason_prompt_rejects_invalid_input() -> None:
    """Prompt 경계에서 잘못된 타입과 빈 keyword를 거부한다."""
    with pytest.raises(TypeError, match="TrendItem이 아님"):
        build_reason_prompt("invalid")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="keyword가 비어 있음"):
        build_reason_prompt(_trend("  "))


def test_generate_reason_returns_trimmed_response_and_passes_model_prompt() -> None:
    """응답을 trim하고 공식 model identifier와 Prompt를 전달한다."""
    client = FakeClient(response=SimpleNamespace(text="\n  설명입니다.  \n"))
    generator = GeminiReasonGenerator(client=client)

    result = generator.generate_reason(_trend())

    assert result == "설명입니다."
    assert client.models.calls[0]["model"] == DEFAULT_MODEL
    assert "테스트 검색어" in client.models.calls[0]["contents"]


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
        generator.generate_reason(_trend())

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
        generator.generate_reason(_trend())


def test_generate_reason_rejects_excessively_long_response() -> None:
    """최대 문자 수를 초과한 응답을 잘라내지 않고 실패시킨다."""
    response = SimpleNamespace(text="가" * (MAX_REASON_LENGTH + 1))
    generator = GeminiReasonGenerator(client=FakeClient(response=response))

    with pytest.raises(ValueError, match="최대 길이를 초과함"):
        generator.generate_reason(_trend())
